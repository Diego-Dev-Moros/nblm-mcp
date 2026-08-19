from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError

import nblm_mcp.server as server_module
from nblm_mcp.config import Config


def call(tool):
    """Unwrap a FastMCP tool object back to its async function."""
    return getattr(tool, "fn", tool)


@pytest.fixture(autouse=True)
def isolated_download_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        server_module, "get_config", lambda: Config(download_dir=tmp_path / "downloads")
    )


async def test_list_notebooks(fake_client):
    result = await call(server_module.list_notebooks)()
    assert result["count"] == 1
    assert result["notebooks"][0]["id"] == "nb-1"


async def test_get_notebook_includes_sources_and_optional_summary(fake_client):
    plain = await call(server_module.get_notebook)("nb-1")
    assert plain["sources"][0]["id"] == "src-1"
    assert "summary" not in plain

    detailed = await call(server_module.get_notebook)("nb-1", include_summary=True)
    assert detailed["summary"] == "A summary."


async def test_create_notebook_rejects_blank_title(fake_client):
    with pytest.raises(ToolError):
        await call(server_module.create_notebook)("   ")


async def test_delete_notebook_requires_confirmation(fake_client):
    with pytest.raises(ToolError, match="confirm=true"):
        await call(server_module.delete_notebook)("nb-1")
    assert fake_client.notebooks.deleted == []

    result = await call(server_module.delete_notebook)("nb-1", confirm=True)
    assert result["deleted"] is True
    assert fake_client.notebooks.deleted == ["nb-1"]


async def test_delete_source_requires_confirmation(fake_client):
    with pytest.raises(ToolError):
        await call(server_module.delete_source)("nb-1", "src-1")
    assert fake_client.sources.deleted == []


async def test_add_source_requires_exactly_one_input(fake_client):
    with pytest.raises(ToolError, match="exactly one"):
        await call(server_module.add_source)("nb-1")
    with pytest.raises(ToolError, match="exactly one"):
        await call(server_module.add_source)("nb-1", url="https://a", text="b")


async def test_add_source_text_requires_title(fake_client):
    with pytest.raises(ToolError, match="title is required"):
        await call(server_module.add_source)("nb-1", text="some notes")


async def test_add_source_url_passes_wait_timeout(fake_client):
    view = await call(server_module.add_source)("nb-1", url="https://example.com/x")
    assert view["url"] == "https://example.com/x"
    name, kwargs = fake_client.sources.calls[0]
    assert name == "add_url"
    assert kwargs["wait"] is True
    assert kwargs["wait_timeout"] == 180.0


async def test_add_source_file_rejects_missing_path(fake_client, tmp_path):
    with pytest.raises(ToolError, match="No such file"):
        await call(server_module.add_source)("nb-1", file_path=str(tmp_path / "nope.pdf"))


async def test_add_source_file_accepts_existing_path(fake_client, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("hello")
    await call(server_module.add_source)("nb-1", file_path=str(path))
    name, kwargs = fake_client.sources.calls[0]
    assert name == "add_file"
    assert kwargs["file_path"] == str(path)


async def test_ask_returns_citations_with_titles(fake_client):
    result = await call(server_module.ask)("nb-1", "What does it say?")
    assert result["citations"][0]["source_title"] == "Paper"
    assert result["conversation_id"] == "conv-1"


async def test_ask_rejects_empty_question(fake_client):
    with pytest.raises(ToolError):
        await call(server_module.ask)("nb-1", "  ")


async def test_chat_history_limits_turns(fake_client):
    result = await call(server_module.chat_history)("nb-1", limit=1)
    assert result["count"] == 1
    assert result["turns"][0] == {"question": "Q1", "answer": "A1"}


async def test_generate_artifact_rejects_unknown_kind(fake_client):
    with pytest.raises(ToolError, match="Unknown kind"):
        await call(server_module.generate_artifact)("nb-1", "podcast")


async def test_generate_artifact_rejects_unknown_enum_value(fake_client):
    with pytest.raises(ToolError, match="Unknown audio_format"):
        await call(server_module.generate_artifact)("nb-1", "audio", audio_format="spicy")


async def test_generate_artifact_maps_audio_options_to_enums(fake_client):
    from notebooklm.types import AudioFormat, AudioLength

    result = await call(server_module.generate_artifact)(
        "nb-1", "audio", audio_format="deep_dive", audio_length="short"
    )
    name, kwargs = fake_client.artifacts.calls[0]
    assert name == "generate_audio"
    assert kwargs["audio_format"] is AudioFormat.DEEP_DIVE
    assert kwargs["audio_length"] is AudioLength.SHORT
    assert result["status"] == "pending"
    assert "next_step" in result


async def test_generate_artifact_defaults_report_format(fake_client):
    from notebooklm.types import ReportFormat

    await call(server_module.generate_artifact)("nb-1", "report")
    _, kwargs = fake_client.artifacts.calls[0]
    assert kwargs["report_format"] is ReportFormat.BRIEFING_DOC


async def test_generate_artifact_waits_when_asked(fake_client):
    result = await call(server_module.generate_artifact)("nb-1", "audio", wait=True)
    assert result["status"] == "completed"
    assert "next_step" not in result
    assert (
        "wait_for_completion",
        {"task_id": "art-1", "timeout": 600.0},
    ) in fake_client.artifacts.calls


async def test_generate_artifact_mind_map_returns_the_map(fake_client):
    result = await call(server_module.generate_artifact)("nb-1", "mind_map")
    assert result["kind"] == "mind_map"
    assert result["mind_map"] == {"root": "Paper"}
    assert result["note_id"] == "note-1"


async def test_list_artifacts_maps_kind_filter(fake_client):
    from notebooklm.types import ArtifactType

    await call(server_module.list_artifacts)("nb-1", kind="audio")
    _, kwargs = fake_client.artifacts.calls[0]
    assert kwargs["artifact_type"] is ArtifactType.AUDIO


async def test_download_artifact_writes_into_download_dir(fake_client, tmp_path):
    result = await call(server_module.download_artifact)("nb-1", "art-1")
    assert result["path"].startswith(str(tmp_path / "downloads"))
    assert result["path"].endswith(".m4a")
    assert (tmp_path / "downloads").is_dir()


async def test_download_artifact_rejects_incomplete_artifact(fake_client, monkeypatch):
    from conftest import FakeArtifact

    async def pending_get(notebook_id, artifact_id):
        return FakeArtifact(id=artifact_id, status_str="in_progress")

    monkeypatch.setattr(fake_client.artifacts, "get", pending_get)
    with pytest.raises(ToolError, match="not completed"):
        await call(server_module.download_artifact)("nb-1", "art-1")


async def test_missing_session_reports_our_login_command():
    from nblm_mcp.errors import to_tool_error

    error = to_tool_error(
        FileNotFoundError("Storage file not found: /root/.notebooklm/storage_state.json")
    )
    assert "nblm-mcp-login" in str(error)


async def test_unrelated_file_error_is_not_reported_as_a_login_problem():
    from nblm_mcp.errors import to_tool_error

    error = to_tool_error(FileNotFoundError("no such file: /tmp/report.pdf"))
    assert "nblm-mcp-login" not in str(error)
