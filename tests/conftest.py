"""Shared fakes: the tools are exercised against a stand-in client, never Google."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from nblm_mcp import client as client_module


@dataclass
class FakeEnum:
    name: str

    @property
    def value(self) -> str:
        return self.name.lower()


@dataclass
class FakeNotebook:
    id: str = "nb-1"
    title: str = "Research"
    emoji: str | None = "📚"
    sources_count: int = 2
    is_owner: bool = True
    created_at: datetime | None = datetime(2026, 1, 2, tzinfo=timezone.utc)
    last_viewed_at: datetime | None = None


@dataclass
class FakeSource:
    id: str = "src-1"
    title: str | None = "Paper"
    url: str | None = "https://example.com/paper"
    status: Any = field(default_factory=lambda: FakeEnum("READY"))
    kind: Any = field(default_factory=lambda: FakeEnum("URL"))
    word_count: int | None = 1200
    created_at: datetime | None = None


@dataclass
class FakeArtifact:
    id: str = "art-1"
    title: str = "Deep Dive: Paper"
    kind: Any = field(default_factory=lambda: FakeEnum("AUDIO"))
    status_str: str = "completed"
    report_kind: str | None = None
    duration_seconds: float | None = 610.5
    url: str | None = None
    created_at: datetime | None = None

    @property
    def is_completed(self) -> bool:
        return self.status_str == "completed"


@dataclass
class FakeGenerationStatus:
    task_id: str = "art-1"
    status: Any = field(default_factory=lambda: FakeEnum("PENDING"))
    url: str | None = None
    error: str | None = None


@dataclass
class FakeReference:
    source_id: str = "src-1"
    citation_number: int | None = 1
    cited_text: str | None = "the relevant passage"


@dataclass
class FakeNextStep:
    question: str = "What about the limitations?"


@dataclass
class FakeAskResult:
    answer: str = "The paper argues X [1]."
    conversation_id: str | None = "conv-1"
    turn_number: int = 1
    is_follow_up: bool = False
    references: list = field(default_factory=lambda: [FakeReference()])
    next_steps: list = field(default_factory=lambda: [FakeNextStep()])


class FakeNotebooks:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.created: list[str] = []

    async def list(self) -> list[FakeNotebook]:
        return [FakeNotebook()]

    async def get(self, notebook_id: str) -> FakeNotebook:
        return FakeNotebook(id=notebook_id)

    async def get_summary(self, notebook_id: str) -> str:
        return "A summary."

    async def create(self, title: str) -> FakeNotebook:
        self.created.append(title)
        return FakeNotebook(id="nb-new", title=title)

    async def delete(self, notebook_id: str) -> None:
        self.deleted.append(notebook_id)


class FakeSources:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    async def list(self, notebook_id: str, **kwargs: Any) -> list[FakeSource]:
        return [FakeSource()]

    async def add_url(self, notebook_id: str, url: str, **kwargs: Any) -> FakeSource:
        self.calls.append(("add_url", {"url": url, **kwargs}))
        return FakeSource(url=url)

    async def add_text(
        self, notebook_id: str, title: str, content: str, **kwargs: Any
    ) -> FakeSource:
        self.calls.append(("add_text", {"title": title, "content": content, **kwargs}))
        return FakeSource(title=title, url=None)

    async def add_file(self, notebook_id: str, file_path: Any, **kwargs: Any) -> FakeSource:
        self.calls.append(("add_file", {"file_path": str(file_path), **kwargs}))
        return FakeSource(title=str(file_path), url=None)

    async def delete(self, notebook_id: str, source_id: str) -> None:
        self.deleted.append(source_id)


class FakeChat:
    def __init__(self) -> None:
        self.asked: list[dict] = []

    async def ask(self, notebook_id: str, question: str, **kwargs: Any) -> FakeAskResult:
        self.asked.append({"notebook_id": notebook_id, "question": question, **kwargs})
        return FakeAskResult()

    async def get_history(self, notebook_id: str, limit: int = 100, **kwargs: Any) -> list:
        return [("Q1", "A1"), ("Q2", "A2")][:limit]


class FakeArtifacts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.downloads: list[tuple[str, str, str]] = []

    async def list(self, notebook_id: str, artifact_type: Any = None) -> list[FakeArtifact]:
        self.calls.append(("list", {"artifact_type": artifact_type}))
        return [FakeArtifact()]

    async def get(self, notebook_id: str, artifact_id: str) -> FakeArtifact:
        return FakeArtifact(id=artifact_id)

    async def generate_audio(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_audio", kwargs))
        return FakeGenerationStatus()

    async def generate_video(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_video", kwargs))
        return FakeGenerationStatus()

    async def generate_report(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_report", kwargs))
        return FakeGenerationStatus()

    async def generate_study_guide(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_study_guide", kwargs))
        return FakeGenerationStatus()

    async def generate_quiz(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_quiz", kwargs))
        return FakeGenerationStatus()

    async def generate_flashcards(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_flashcards", kwargs))
        return FakeGenerationStatus()

    async def generate_infographic(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_infographic", kwargs))
        return FakeGenerationStatus()

    async def generate_slide_deck(self, notebook_id: str, **kwargs: Any) -> FakeGenerationStatus:
        self.calls.append(("generate_slide_deck", kwargs))
        return FakeGenerationStatus()

    async def generate_mind_map(self, notebook_id: str, **kwargs: Any) -> Any:
        self.calls.append(("generate_mind_map", kwargs))

        @dataclass
        class Result:
            mind_map: Any = field(default_factory=lambda: {"root": "Paper"})
            note_id: str | None = "note-1"

        return Result()

    async def wait_for_completion(
        self, notebook_id: str, task_id: str, **kwargs: Any
    ) -> FakeGenerationStatus:
        self.calls.append(("wait_for_completion", {"task_id": task_id, **kwargs}))
        return FakeGenerationStatus(task_id=task_id, status=FakeEnum("COMPLETED"))

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: Any = None
    ) -> str:
        self.downloads.append(("audio", output_path, artifact_id))
        return output_path


class FakeClient:
    def __init__(self) -> None:
        self.notebooks = FakeNotebooks()
        self.sources = FakeSources()
        self.chat = FakeChat()
        self.artifacts = FakeArtifacts()


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    """Install a fake client for every tool call in the test."""
    client = FakeClient()

    async def _get_client() -> FakeClient:
        return client

    monkeypatch.setattr(client_module, "get_client", _get_client)
    import nblm_mcp.server as server_module

    monkeypatch.setattr(server_module, "get_client", _get_client)
    return client
