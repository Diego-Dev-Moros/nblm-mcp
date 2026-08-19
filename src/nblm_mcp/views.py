"""Serializers turning notebooklm-py dataclasses into JSON-safe dicts.

Tool responses are what the calling model actually reads, so these keep only
fields an agent can act on and flatten enums/datetimes to plain strings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _enum(value: Any) -> str | None:
    """Render an enum (or plain value) as a lowercase string."""
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name.lower()
    inner = getattr(value, "value", value)
    return str(inner).lower()


def notebook_view(notebook: Any) -> dict:
    return {
        "id": notebook.id,
        "title": notebook.title,
        "emoji": getattr(notebook, "emoji", None),
        "sources_count": getattr(notebook, "sources_count", 0),
        "is_owner": getattr(notebook, "is_owner", True),
        "created_at": _iso(getattr(notebook, "created_at", None)),
        "last_viewed_at": _iso(getattr(notebook, "last_viewed_at", None)),
    }


def source_view(source: Any) -> dict:
    return {
        "id": source.id,
        "title": getattr(source, "title", None),
        "url": getattr(source, "url", None),
        "type": _enum(getattr(source, "kind", None)),
        "status": _enum(getattr(source, "status", None)),
        "word_count": getattr(source, "word_count", None),
        "created_at": _iso(getattr(source, "created_at", None)),
    }


def artifact_view(artifact: Any) -> dict:
    return {
        "id": artifact.id,
        "title": artifact.title,
        "kind": _enum(getattr(artifact, "kind", None)),
        "status": getattr(artifact, "status_str", None),
        "report_kind": getattr(artifact, "report_kind", None),
        "duration_seconds": getattr(artifact, "duration_seconds", None),
        "url": getattr(artifact, "url", None),
        "created_at": _iso(getattr(artifact, "created_at", None)),
    }


def generation_view(status: Any) -> dict:
    return {
        "artifact_id": status.task_id,
        "status": _enum(getattr(status, "status", None)),
        "url": getattr(status, "url", None),
        "error": getattr(status, "error", None),
    }


def reference_view(reference: Any, titles: dict[str, str] | None = None) -> dict:
    source_id = getattr(reference, "source_id", None)
    return {
        "citation_number": getattr(reference, "citation_number", None),
        "source_id": source_id,
        "source_title": (titles or {}).get(source_id),
        "cited_text": getattr(reference, "cited_text", None),
    }


def ask_view(result: Any, titles: dict[str, str] | None = None) -> dict:
    references = getattr(result, "references", None) or []
    return {
        "answer": result.answer,
        "conversation_id": getattr(result, "conversation_id", None),
        "turn_number": getattr(result, "turn_number", None),
        "is_follow_up": getattr(result, "is_follow_up", None),
        "citations": [reference_view(ref, titles) for ref in references],
        "suggested_follow_ups": [
            getattr(step, "question", None) or str(step)
            for step in (getattr(result, "next_steps", None) or [])
        ],
    }
