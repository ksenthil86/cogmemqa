"""
Tests for the conversation-memory flow in POST /api/chat.

The neo4j-agent-memory client is substituted with a FakeMemoryService set
on app.state.memory_service (same injection pattern as chat_generate_fn),
so no Gemini or embedding calls happen. Neo4j stays real for the agent
tools, per the project no-mock policy.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from src.api import app


class FakeMemoryService:
    """Records calls; returns canned context/counts."""

    def __init__(
        self,
        memory_block: str | None = None,
        turns: list[dict] | None = None,
        counts: dict | None = None,
        raise_on_calls: bool = False,
    ):
        self.active = True
        self.memory_block = memory_block
        self.turns = turns or []
        self.counts = counts or {"entities": 0, "preferences": 0}
        self.raise_on_calls = raise_on_calls
        self.recorded_user: list[tuple[str, str]] = []
        self.recorded_model: list[tuple[str, str]] = []

    async def get_chat_context(self, session_id, query):
        if self.raise_on_calls:
            raise RuntimeError("memory boom")
        return self.memory_block, self.turns

    async def record_user_message(self, session_id, text):
        if self.raise_on_calls:
            raise RuntimeError("memory boom")
        self.recorded_user.append((session_id, text))
        return self.counts

    async def record_model_message(self, session_id, text):
        if self.raise_on_calls:
            raise RuntimeError("memory boom")
        self.recorded_model.append((session_id, text))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    for attr in ("chat_generate_fn",):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    # lifespan re-creates memory_service each TestClient run; drop the fake
    if hasattr(app.state, "memory_service"):
        delattr(app.state, "memory_service")


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(function_calls=None, candidates=[], text=text)


def _stub_generate(seen: list):
    async def stub(contents, config):
        seen.append((list(contents), config))
        return _text_response("ok")
    return stub


# ── session handling ──────────────────────────────────────────────────────────

def test_chat_generates_session_id_when_missing(client):
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = FakeMemoryService()
    data = client.post("/api/chat", json={"message": "hi"}).json()
    assert data["session_id"]
    assert len(data["session_id"]) >= 32  # uuid4


def test_chat_echoes_provided_session_id(client):
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = FakeMemoryService()
    data = client.post(
        "/api/chat", json={"message": "hi", "session_id": "sess-abc"}
    ).json()
    assert data["session_id"] == "sess-abc"


def test_chat_records_both_turns_with_same_session(client):
    fake = FakeMemoryService()
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = fake
    client.post("/api/chat", json={"message": "hello", "session_id": "s1"})
    assert fake.recorded_user == [("s1", "hello")]
    assert fake.recorded_model == [("s1", "ok")]


# ── badges ────────────────────────────────────────────────────────────────────

def test_chat_surfaces_extraction_counts(client):
    fake = FakeMemoryService(counts={"entities": 3, "preferences": 1})
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = fake
    data = client.post("/api/chat", json={"message": "I'm Senthil"}).json()
    assert data["memory_active"] is True
    assert data["entities_extracted"] == 3
    assert data["preferences_detected"] == 1


# ── prompt/history injection ──────────────────────────────────────────────────

def test_memory_block_reaches_system_instruction(client):
    seen: list = []
    fake = FakeMemoryService(memory_block="## Relevant Knowledge\n- likes P0 first")
    app.state.chat_generate_fn = _stub_generate(seen)
    app.state.memory_service = fake
    client.post("/api/chat", json={"message": "what do I like?"})
    _contents, config = seen[0]
    assert "likes P0 first" in config.system_instruction
    assert "Long-term memory" in config.system_instruction


def test_server_side_history_reaches_contents(client):
    seen: list = []
    fake = FakeMemoryService(turns=[
        {"role": "user", "text": "first question"},
        {"role": "model", "text": "first answer"},
    ])
    app.state.chat_generate_fn = _stub_generate(seen)
    app.state.memory_service = fake
    client.post("/api/chat", json={"message": "follow-up"})
    contents, _config = seen[0]
    assert len(contents) == 3
    assert contents[0].role == "user" and contents[0].parts[0].text == "first question"
    assert contents[1].role == "model" and contents[1].parts[0].text == "first answer"
    assert contents[2].parts[0].text == "follow-up"


def test_client_history_used_when_memory_inactive(client):
    seen: list = []
    fake = FakeMemoryService()
    fake.active = False
    app.state.chat_generate_fn = _stub_generate(seen)
    app.state.memory_service = fake
    data = client.post("/api/chat", json={
        "message": "follow-up",
        "history": [{"role": "user", "text": "earlier"}],
    }).json()
    contents, _config = seen[0]
    assert len(contents) == 2
    assert contents[0].parts[0].text == "earlier"
    assert data["memory_active"] is False
    assert fake.recorded_user == []


# ── failure isolation ─────────────────────────────────────────────────────────

def test_chat_survives_raising_memory_service(client):
    # Even a memory service that raises must never take down the chat
    # endpoint — it falls back to the client-held history path.
    fake = FakeMemoryService(raise_on_calls=True)
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = fake
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "ok"
    assert data["memory_active"] is False
    assert data["entities_extracted"] == 0
    assert data["preferences_detected"] == 0


def test_chat_survives_inactive_memory_service(client):
    fake = FakeMemoryService()
    fake.active = False
    app.state.chat_generate_fn = _stub_generate([])
    app.state.memory_service = fake
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert resp.json()["memory_active"] is False
