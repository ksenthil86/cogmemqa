"""Tests for the agent event hooks (tool_start/tool_end/text_delta)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types

from app.chat_agent import run_chat_agent


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


@pytest.fixture
def collect():
    events: list[tuple[str, dict]] = []

    async def cb(event: str, data: dict) -> None:
        events.append((event, data))

    return events, cb


async def test_event_sequence(neo4j_driver, collect):
    events, cb = collect
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("get_health")
        return _text_response("Coverage is 100%.")

    result = await run_chat_agent(
        neo4j_driver, "coverage?", generate_fn=stub, event_cb=cb
    )
    names = [e for e, _ in events]
    assert names[0] == "tool_start"
    assert names[1] == "tool_end"
    assert names[2:] and all(n == "text_delta" for n in names[2:])

    start = dict(events[0][1])
    assert start == {"name": "get_health", "inputs": {}}
    end = events[1][1]
    assert end["name"] == "get_health"
    assert end["duration_ms"] >= 0
    assert "coverage_pct" in end["output_preview"]

    streamed = "".join(d["text"] for e, d in events if e == "text_delta")
    assert streamed == result["response"] == "Coverage is 100%."


async def test_text_deltas_chunk_long_answers(neo4j_driver, collect):
    events, cb = collect
    long_text = "word " * 100  # 500 chars

    async def stub(contents, config):
        return _text_response(long_text)

    result = await run_chat_agent(neo4j_driver, "hi", generate_fn=stub, event_cb=cb)
    deltas = [d["text"] for e, d in events if e == "text_delta"]
    assert len(deltas) > 1
    assert "".join(deltas) == result["response"]


async def test_no_callback_unchanged(neo4j_driver):
    async def stub(contents, config):
        return _text_response("ok")

    result = await run_chat_agent(neo4j_driver, "hi", generate_fn=stub)
    assert result["response"] == "ok"


async def test_tool_end_carries_graph_data(neo4j_driver, collect):
    events, cb = collect
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("list_requirements")
        return _text_response("done")

    await run_chat_agent(neo4j_driver, "list", generate_fn=stub, event_cb=cb)
    end = next(d for e, d in events if e == "tool_end")
    assert end["graph_data"] and end["graph_data"]["nodes"]
