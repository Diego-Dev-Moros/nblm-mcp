"""NotebookLM MCP server — notebooks, sources, grounded chat, and Studio artifacts.

Every tool drives Google's undocumented NotebookLM (Gemini Notebook) web API
through the `notebooklm-py` library, authenticated with the Google session
cookies captured by `nblm-mcp-login`. There is no public consumer API; Google
can change the internal endpoints at any time.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from nblm_mcp.client import get_client, get_config, reset
from nblm_mcp.errors import LOGIN_HINT, to_tool_error
from nblm_mcp.views import (
    artifact_view,
    ask_view,
    generation_view,
    notebook_view,
    source_view,
)

mcp = FastMCP(name="NotebookLM")

T = TypeVar("T")

# Studio artifact kinds this server can generate, mapped to the library method
# that starts the generation. Mind maps are excluded: they return a note rather
# than a pollable artifact and are handled on their own branch.
_GENERATORS = (
    "audio",
    "video",
    "report",
    "study_guide",
    "quiz",
    "flashcards",
    "infographic",
    "slide_deck",
    "mind_map",
)

_DOWNLOADERS = {
    "audio": ("download_audio", ".m4a"),
    "video": ("download_video", ".mp4"),
    "report": ("download_report", ".md"),
    "mind_map": ("download_mind_map", ".json"),
    "infographic": ("download_infographic", ".png"),
    "slide_deck": ("download_slide_deck", ".pdf"),
    "quiz": ("download_quiz", ".json"),
    "flashcards": ("download_flashcards", ".json"),
    "data_table": ("download_data_table", ".csv"),
}


def _handled(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Convert library exceptions into ToolErrors an agent can act on."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped and re-raised below
            from notebooklm import exceptions as nblm

            if isinstance(exc, (nblm.AuthError, nblm.AuthExtractionError)):
                # Drop the cached client so a fresh login is picked up without
                # restarting the server.
                await reset()
            raise to_tool_error(exc) from exc

    return wrapper


def _enum_arg(enum_cls: Any, value: str | None, label: str) -> Any:
    """Resolve a caller-supplied string to an enum member, or raise ToolError."""
    if value is None:
        return None
    try:
        return enum_cls[value.strip().upper()]
    except KeyError:
        allowed = ", ".join(member.name.lower() for member in enum_cls)
        raise ToolError(f"Unknown {label} {value!r}. Allowed values: {allowed}.") from None


async def _source_titles(client: Any, notebook_id: str) -> dict[str, str]:
    """Map source id -> title so citations name a document, not a UUID."""
    try:
        sources = await client.sources.list(notebook_id)
    except Exception:  # noqa: BLE001 - titles are a nicety, never fail the answer
        return {}
    return {s.id: s.title for s in sources if getattr(s, "title", None)}


def _resolve_output_path(output_path: str | None, default_name: str) -> Path:
    cfg = get_config()
    if not output_path:
        target = cfg.download_dir / default_name
    else:
        candidate = Path(output_path).expanduser()
        target = candidate if candidate.is_absolute() else cfg.download_dir / candidate
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@mcp.tool
@_handled
async def auth_status() -> dict:
    """Check whether this server has a working NotebookLM session.

    Call this first when any other tool reports an auth problem. It performs a
    real (cheap) request, so it distinguishes "no cookies stored" from "cookies
    stored but expired".
    """
    from notebooklm.paths import get_active_profile, get_storage_path

    cfg = get_config()
    try:
        storage_path = str(
            Path(cfg.storage_path) if cfg.storage_path else get_storage_path(cfg.profile)
        )
    except Exception:  # noqa: BLE001 - path resolution must not mask the status
        storage_path = cfg.storage_path

    try:
        client = await get_client()
        notebooks = await client.notebooks.list()
    except Exception as exc:  # noqa: BLE001 - reported as data, not an error
        await reset()
        return {
            "authenticated": False,
            "profile": cfg.profile or get_active_profile(),
            "storage_path": storage_path,
            "error": str(exc),
            "next_step": LOGIN_HINT,
        }

    return {
        "authenticated": True,
        "profile": cfg.profile or get_active_profile(),
        "storage_path": storage_path,
        "notebooks_visible": len(notebooks),
    }


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


@mcp.tool
@_handled
async def list_notebooks() -> dict:
    """List the notebooks reachable by the signed-in Google account.

    Returns id, title, and source count for each. Use the ids with every other
    tool — NotebookLM has no lookup by title.
    """
    client = await get_client()
    notebooks = await client.notebooks.list()
    return {"count": len(notebooks), "notebooks": [notebook_view(nb) for nb in notebooks]}


@mcp.tool
@_handled
async def get_notebook(notebook_id: str, include_summary: bool = False) -> dict:
    """Get one notebook with its sources.

    Args:
        notebook_id: The notebook id, as returned by list_notebooks.
        include_summary: Also fetch NotebookLM's own generated summary of the
            notebook. Costs an extra round-trip and can be slow on large
            notebooks, so it is off by default.
    """
    client = await get_client()
    notebook = await client.notebooks.get(notebook_id)
    sources = await client.sources.list(notebook_id)

    result = notebook_view(notebook)
    result["sources"] = [source_view(s) for s in sources]
    if include_summary:
        try:
            result["summary"] = await client.notebooks.get_summary(notebook_id)
        except Exception as exc:  # noqa: BLE001 - a missing summary is not fatal
            result["summary_error"] = str(exc)
    return result


@mcp.tool
@_handled
async def create_notebook(title: str) -> dict:
    """Create an empty notebook.

    A notebook with no sources cannot answer questions — follow up with
    add_source before calling ask.

    Args:
        title: Display title for the new notebook.
    """
    if not title.strip():
        raise ToolError("title cannot be empty.")
    client = await get_client()
    notebook = await client.notebooks.create(title.strip())
    return notebook_view(notebook)


@mcp.tool
@_handled
async def delete_notebook(notebook_id: str, confirm: bool = False) -> dict:
    """Permanently delete a notebook and everything in it.

    This cannot be undone and deletes the notebook's sources, chats, and
    generated artifacts along with it.

    Args:
        notebook_id: The notebook to delete.
        confirm: Must be true. The guard exists so a mistaken tool call cannot
            destroy a notebook; ask the user before setting it.
    """
    if not confirm:
        raise ToolError(
            "Refusing to delete: call again with confirm=true once the user has "
            "agreed. Deleting a notebook also deletes its sources and artifacts."
        )
    client = await get_client()
    await client.notebooks.delete(notebook_id)
    return {"deleted": True, "notebook_id": notebook_id}


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


@mcp.tool
@_handled
async def list_sources(notebook_id: str) -> dict:
    """List the sources in a notebook, with their processing status.

    A source that is not `ready` is still being ingested and will not ground
    answers yet.
    """
    client = await get_client()
    sources = await client.sources.list(notebook_id)
    return {"count": len(sources), "sources": [source_view(s) for s in sources]}


@mcp.tool
@_handled
async def add_source(
    notebook_id: str,
    url: str | None = None,
    text: str | None = None,
    file_path: str | None = None,
    title: str | None = None,
    wait: bool = True,
) -> dict:
    """Add one source to a notebook, from a URL, pasted text, or a local file.

    Pass exactly one of `url`, `text`, or `file_path`.

    Args:
        notebook_id: Notebook to add the source to.
        url: Web page, YouTube video, or Google Docs/Slides link to ingest.
        text: Raw text to paste as a source. Requires `title`.
        file_path: Absolute path to a local file (PDF, txt, md, audio...).
            Read from the machine running this server, not the user's client.
        title: Display title. Required for `text`, optional otherwise.
        wait: Block until the source finishes processing so it is usable
            immediately. Turn off for bulk imports and poll list_sources.
    """
    provided = [
        name for name, value in (("url", url), ("text", text), ("file_path", file_path)) if value
    ]
    if len(provided) != 1:
        raise ToolError(f"Pass exactly one of url, text, or file_path (got: {provided or 'none'}).")

    cfg = get_config()
    client = await get_client()
    timeout = cfg.source_timeout

    if url:
        source = await client.sources.add_url(
            notebook_id, url, wait=wait, wait_timeout=timeout, title=title
        )
    elif text:
        if not title:
            raise ToolError("title is required when adding a text source.")
        source = await client.sources.add_text(
            notebook_id, title, text, wait=wait, wait_timeout=timeout
        )
    else:
        path = Path(file_path).expanduser()  # type: ignore[arg-type]
        if not path.is_file():
            raise ToolError(f"No such file on the server host: {path}")
        source = await client.sources.add_file(
            notebook_id, path, wait=wait, wait_timeout=timeout, title=title
        )

    return source_view(source)


@mcp.tool
@_handled
async def delete_source(notebook_id: str, source_id: str, confirm: bool = False) -> dict:
    """Remove a source from a notebook.

    Args:
        notebook_id: The notebook holding the source.
        source_id: The source to remove, from list_sources.
        confirm: Must be true. Removing a source also drops the citations that
            point at it, so ask the user first.
    """
    if not confirm:
        raise ToolError(
            "Refusing to delete: call again with confirm=true once the user has agreed."
        )
    client = await get_client()
    await client.sources.delete(notebook_id, source_id)
    return {"deleted": True, "notebook_id": notebook_id, "source_id": source_id}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@mcp.tool
@_handled
async def ask(
    notebook_id: str,
    question: str,
    source_ids: list[str] | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Ask a notebook a question and get an answer grounded in its sources.

    The answer comes from Gemini reading the notebook's own sources, with
    citations back to them — use this instead of summarizing the sources
    yourself when a notebook already holds the material.

    Args:
        notebook_id: The notebook to query.
        question: Natural-language question. Specific questions cite better
            than broad ones.
        source_ids: Restrict the answer to these sources. Omit to use all.
        conversation_id: Continue a specific conversation. Omit to continue the
            notebook's current one, matching the web UI.
    """
    if not question.strip():
        raise ToolError("question cannot be empty.")
    client = await get_client()
    result = await client.chat.ask(
        notebook_id, question, source_ids=source_ids, conversation_id=conversation_id
    )
    titles = await _source_titles(client, notebook_id)
    return ask_view(result, titles)


@mcp.tool
@_handled
async def chat_history(notebook_id: str, limit: int = 20) -> dict:
    """Read past question/answer turns for a notebook's current conversation.

    Args:
        notebook_id: The notebook whose conversation to read.
        limit: Maximum number of turns to return, newest conversation first.
    """
    client = await get_client()
    turns = await client.chat.get_history(notebook_id, limit=limit)
    return {
        "count": len(turns),
        "turns": [{"question": question, "answer": answer} for question, answer in turns],
    }


# ---------------------------------------------------------------------------
# Studio artifacts
# ---------------------------------------------------------------------------


@mcp.tool
@_handled
async def list_artifacts(notebook_id: str, kind: str | None = None) -> dict:
    """List generated Studio artifacts in a notebook.

    Use this to poll a generation started with wait=false: the artifact reports
    `status: completed` when it is ready to download.

    Args:
        notebook_id: The notebook to inspect.
        kind: Filter by type — audio, video, report, quiz, flashcards,
            mind_map, infographic, slide_deck, or data_table.
    """
    from notebooklm.types import ArtifactType

    client = await get_client()
    artifact_type = _enum_arg(ArtifactType, kind, "artifact kind")
    artifacts = await client.artifacts.list(notebook_id, artifact_type)
    return {"count": len(artifacts), "artifacts": [artifact_view(a) for a in artifacts]}


@mcp.tool
@_handled
async def generate_artifact(
    notebook_id: str,
    kind: str,
    instructions: str | None = None,
    source_ids: list[str] | None = None,
    language: str = "en",
    audio_format: str | None = None,
    audio_length: str | None = None,
    report_format: str | None = None,
    difficulty: str | None = None,
    quantity: str | None = None,
    wait: bool = False,
) -> dict:
    """Generate a Studio artifact (podcast, report, quiz, mind map...).

    Generation runs server-side and is slow — an audio overview commonly takes
    several minutes — and it consumes the account's daily Studio quota. Prefer
    the default wait=false and poll with list_artifacts.

    Args:
        notebook_id: Notebook whose sources feed the generation.
        kind: One of audio, video, report, study_guide, quiz, flashcards,
            infographic, slide_deck, mind_map.
        instructions: Free-text steer for the output ("focus on the pricing
            section", "explain it for beginners").
        source_ids: Restrict generation to these sources. Omit to use all.
        language: BCP-47 language code for the output, e.g. "en", "es".
        audio_format: audio only — deep_dive, brief, critique, or debate.
        audio_length: audio only — short, default, or long.
        report_format: report only — briefing_doc, study_guide, or blog_post.
        difficulty: quiz/flashcards only — easy, medium, or hard.
        quantity: quiz/flashcards only — fewer, standard, or more.
        wait: Block until the artifact is ready (or the configured timeout
            elapses) instead of returning as soon as it is queued.
    """
    from notebooklm.types import (
        AudioFormat,
        AudioLength,
        QuizDifficulty,
        QuizQuantity,
        ReportFormat,
    )

    kind = kind.strip().lower()
    if kind not in _GENERATORS:
        raise ToolError(f"Unknown kind {kind!r}. Allowed values: {', '.join(_GENERATORS)}.")

    cfg = get_config()
    client = await get_client()
    artifacts = client.artifacts

    if kind == "mind_map":
        result = await artifacts.generate_mind_map(
            notebook_id, source_ids=source_ids, language=language, instructions=instructions
        )
        # Mind maps are persisted as a note, not as a pollable artifact.
        return {
            "kind": "mind_map",
            "status": "completed",
            "note_id": result.note_id,
            "mind_map": result.mind_map,
        }

    if kind == "audio":
        status = await artifacts.generate_audio(
            notebook_id,
            source_ids=source_ids,
            language=language,
            instructions=instructions,
            audio_format=_enum_arg(AudioFormat, audio_format, "audio_format"),
            audio_length=_enum_arg(AudioLength, audio_length, "audio_length"),
        )
    elif kind == "video":
        status = await artifacts.generate_video(
            notebook_id, source_ids=source_ids, language=language, instructions=instructions
        )
    elif kind == "report":
        status = await artifacts.generate_report(
            notebook_id,
            report_format=_enum_arg(ReportFormat, report_format, "report_format")
            or ReportFormat.BRIEFING_DOC,
            source_ids=source_ids,
            language=language,
            extra_instructions=instructions,
        )
    elif kind == "study_guide":
        status = await artifacts.generate_study_guide(
            notebook_id,
            source_ids=source_ids,
            language=language,
            extra_instructions=instructions,
        )
    elif kind == "infographic":
        status = await artifacts.generate_infographic(
            notebook_id, source_ids=source_ids, language=language, instructions=instructions
        )
    elif kind == "slide_deck":
        status = await artifacts.generate_slide_deck(
            notebook_id, source_ids=source_ids, language=language, instructions=instructions
        )
    else:  # quiz, flashcards
        generate = artifacts.generate_quiz if kind == "quiz" else artifacts.generate_flashcards
        status = await generate(
            notebook_id,
            source_ids=source_ids,
            instructions=instructions,
            quantity=_enum_arg(QuizQuantity, quantity, "quantity"),
            difficulty=_enum_arg(QuizDifficulty, difficulty, "difficulty"),
        )

    if wait:
        status = await artifacts.wait_for_completion(
            notebook_id, status.task_id, timeout=cfg.generation_timeout
        )

    result = generation_view(status)
    result["kind"] = kind
    if not wait:
        result["next_step"] = (
            "Generation is running server-side. Poll list_artifacts "
            f"(kind={kind!r}) until this artifact reports status 'completed'."
        )
    return result


@mcp.tool
@_handled
async def download_artifact(
    notebook_id: str,
    artifact_id: str,
    output_path: str | None = None,
) -> dict:
    """Download a completed Studio artifact to a file on the server host.

    Args:
        notebook_id: The notebook holding the artifact.
        artifact_id: The artifact to download, from list_artifacts.
        output_path: Destination path. A bare filename lands in the configured
            download directory; omit it to name the file after the artifact.
    """
    client = await get_client()
    artifact = await client.artifacts.get(notebook_id, artifact_id)
    kind = str(getattr(getattr(artifact, "kind", None), "value", "")) or "unknown"

    if kind not in _DOWNLOADERS:
        raise ToolError(f"Artifact kind {kind!r} cannot be downloaded by this server.")
    if not artifact.is_completed:
        raise ToolError(
            f"Artifact is {artifact.status_str}, not completed — nothing to download yet."
        )

    method_name, suffix = _DOWNLOADERS[kind]
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in artifact.title).strip()
    target = _resolve_output_path(output_path, f"{safe_title or artifact_id}{suffix}")

    written = await getattr(client.artifacts, method_name)(notebook_id, str(target), artifact_id)
    return {"artifact_id": artifact_id, "kind": kind, "path": str(written)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
