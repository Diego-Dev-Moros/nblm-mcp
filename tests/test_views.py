from __future__ import annotations

from conftest import (
    FakeArtifact,
    FakeAskResult,
    FakeGenerationStatus,
    FakeNotebook,
    FakeSource,
)

from nblm_mcp.views import (
    artifact_view,
    ask_view,
    generation_view,
    notebook_view,
    source_view,
)


def test_notebook_view_flattens_datetimes():
    view = notebook_view(FakeNotebook())
    assert view["id"] == "nb-1"
    assert view["created_at"] == "2026-01-02T00:00:00+00:00"
    assert view["last_viewed_at"] is None


def test_source_view_lowercases_enums():
    view = source_view(FakeSource())
    assert view["status"] == "ready"
    assert view["type"] == "url"


def test_artifact_view_keeps_duration_and_status():
    view = artifact_view(FakeArtifact())
    assert view["kind"] == "audio"
    assert view["status"] == "completed"
    assert view["duration_seconds"] == 610.5


def test_generation_view_renames_task_id():
    view = generation_view(FakeGenerationStatus())
    assert view["artifact_id"] == "art-1"
    assert view["status"] == "pending"


def test_ask_view_resolves_citation_titles():
    view = ask_view(FakeAskResult(), {"src-1": "Paper"})
    assert view["answer"].startswith("The paper argues")
    assert view["citations"][0]["source_title"] == "Paper"
    assert view["suggested_follow_ups"] == ["What about the limitations?"]


def test_ask_view_without_titles_leaves_them_null():
    view = ask_view(FakeAskResult())
    assert view["citations"][0]["source_title"] is None
