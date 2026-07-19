"""Tests for POST /api/chat/stream — SSE chat with live tool events."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from src.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    for attr in ("chat_generate_fn", "memory_service"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _model_content() -> types.Content:
    return types.Content(role="model", parts=[types.Part.from_text(text="x")])


def _tool_call_response(name: str) -> SimpleNamespace:
    fc = SimpleNamespace(name=name, args={})
    return SimpleNamespace(
        function_calls=[fc],
        candidates=[SimpleNamespace(content=_model_content())],
        text=None,
    )


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(function_calls=None, candidates=[], text=text)


def _parse_sse(body: str) -> list[tuple[str, str]]:
    """Return [(event, raw_data_json)] pairs from an SSE body."""
    events = []
    current_event = None
    for line in body.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: ") and current_event:
            events.append((current_event, line[len("data: "):]))
            current_event = None
    return events


def test_stream_event_sequence(client):
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("get_health")
        return _text_response("Coverage is 100%.")

    app.state.chat_generate_fn = stub
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "coverage?", "session_id": "s-sse"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["x-accel-buffering"] == "no"
        body = resp.read().decode()

    events = _parse_sse(body)
    names = [e for e, _ in events]
    assert names[0] == "session_id"
    assert "tool_start" in names and "tool_end" in names
    assert names.index("tool_start") < names.index("tool_end")
    assert "text_delta" in names
    assert names[-1] == "done"

    import json
    session = json.loads(dict(events)["session_id"])
    assert session["session_id"] == "s-sse"
    done = json.loads(events[-1][1])
    assert done["response"] == "Coverage is 100%."
    assert done["tool_calls"][0]["name"] == "get_health"


def test_stream_extraction_events_present(client):
    async def stub(contents, config):
        return _text_response("hi")

    app.state.chat_generate_fn = stub
    with client.stream("POST", "/api/chat/stream", json={"message": "hello"}) as resp:
        body = resp.read().decode()
    names = [e for e, _ in _parse_sse(body)]
    assert "entities_extracted" in names
    assert "preferences_detected" in names


def test_stream_error_event_on_agent_failure(client):
    async def stub(contents, config):
        raise RuntimeError("boom")

    app.state.chat_generate_fn = stub
    with client.stream("POST", "/api/chat/stream", json={"message": "hi"}) as resp:
        assert resp.status_code == 200  # error travels inside the stream
        body = resp.read().decode()
    events = _parse_sse(body)
    names = [e for e, _ in events]
    assert "error" in names
    assert names[-1] == "done"


def test_stream_empty_message_rejected(client):
    resp = client.post("/api/chat/stream", json={"message": "   "})
    assert resp.status_code == 422
