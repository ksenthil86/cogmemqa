"""
Tests for the chat/traces/reports endpoints — Sprint chat feature.

Gemini is stubbed via app.state.chat_generate_fn (the API-level injection
hook); Neo4j is real, per the project no-mock policy.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from app.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    if hasattr(app.state, "chat_generate_fn"):
        del app.state.chat_generate_fn


def _model_content(text: str = "x") -> types.Content:
    return types.Content(role="model", parts=[types.Part.from_text(text=text)])


def _tool_call_response(name: str, args: dict | None = None) -> SimpleNamespace:
    fc = SimpleNamespace(name=name, args=args or {})
    return SimpleNamespace(
        function_calls=[fc], candidates=[SimpleNamespace(content=_model_content())], text=None,
    )


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(function_calls=None, candidates=[], text=text)


# ── POST /api/chat ────────────────────────────────────────────────────────────

def test_chat_runs_tool_then_answers(client):
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("get_health")
        return _text_response("Coverage is 100%.")

    app.state.chat_generate_fn = stub
    resp = client.post("/api/chat", json={"message": "What is coverage?"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["response"] == "Coverage is 100%."
    assert [t["name"] for t in data["tool_calls"]] == ["get_health"]
    tool = data["tool_calls"][0]
    assert tool["duration_ms"] >= 0
    assert "coverage_pct" in tool["output_preview"]
    assert data["graph_data"] == {"nodes": [], "relationships": []}


def test_chat_merges_graph_data(client):
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("list_requirements")
        return _text_response("Here are the requirements.")

    app.state.chat_generate_fn = stub
    data = client.post("/api/chat", json={"message": "list reqs"}).json()
    assert len(data["graph_data"]["nodes"]) > 0
    node = data["graph_data"]["nodes"][0]
    assert set(node) == {"id", "labels", "properties"}


def test_chat_history_passed_to_model(client):
    seen: list = []

    async def stub(contents, config):
        seen.append(list(contents))
        return _text_response("ok")

    app.state.chat_generate_fn = stub
    client.post("/api/chat", json={
        "message": "follow-up",
        "history": [
            {"role": "user", "text": "first question"},
            {"role": "model", "text": "first answer"},
        ],
    })
    contents = seen[0]
    assert len(contents) == 3  # 2 history turns + new message
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[2].parts[0].text == "follow-up"


def test_chat_max_iteration_bailout(client):
    async def always_call(contents, config):
        return _tool_call_response("get_health")

    app.state.chat_generate_fn = always_call
    data = client.post("/api/chat", json={"message": "loop forever"}).json()
    assert "tool-call limit" in data["response"]
    assert len(data["tool_calls"]) == 10  # _MAX_ITERATIONS


def test_chat_tool_error_fed_back_to_model(client):
    calls = {"n": 0}

    async def stub(contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_response("execute_cypher", {"query": "MATCH (n) DELETE n"})
        return _text_response("I cannot modify the graph.")

    app.state.chat_generate_fn = stub
    data = client.post("/api/chat", json={"message": "delete everything"}).json()
    assert data["tool_calls"][0]["error"]
    assert data["response"] == "I cannot modify the graph."


def test_chat_empty_message_422(client):
    resp = client.post("/api/chat", json={"message": "   "})
    assert resp.status_code == 422


def test_chat_llm_failure_502(client):
    async def broken(contents, config):
        raise RuntimeError("gemini exploded")

    app.state.chat_generate_fn = broken
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 502


def test_chat_cors_preflight_allows_post(client):
    resp = client.options("/api/chat", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert resp.status_code == 200
    assert "POST" in resp.headers["access-control-allow-methods"]


# ── GET /api/traces ───────────────────────────────────────────────────────────

def test_traces_shape(client):
    resp = client.get("/api/traces")
    assert resp.status_code == 200
    traces = resp.json()
    assert isinstance(traces, list)
    assert traces, "seeded graph should contain Judgment nodes"
    trace = traces[0]
    assert {"id", "label", "agent_role", "confidence", "reasoning", "steps"} <= set(trace)
    for step in trace["steps"]:
        assert {"id", "decision", "content", "timestamp"} <= set(step)


def test_traces_agent_role_filter(client):
    all_traces = client.get("/api/traces").json()
    roles = {t["agent_role"] for t in all_traces}
    role = next(iter(roles))
    filtered = client.get(f"/api/traces?agent_role={role}").json()
    assert filtered
    assert all(t["agent_role"] == role for t in filtered)


# ── GET /api/reports ──────────────────────────────────────────────────────────

def test_reports_shape(client):
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert isinstance(reports, list)
    assert reports, "seeded graph should contain Report nodes"
    report = reports[0]
    assert {"id", "summary", "coverage_pct", "open_findings_count", "created_at"} <= set(report)


def test_chat_system_prompt_sourced_from_ontology(client):
    """The agent persona must come from schema/cogmem-qa.yaml at runtime."""
    seen: list = []

    async def stub(contents, config):
        seen.append(config)
        return _text_response("ok")

    app.state.chat_generate_fn = stub
    client.post("/api/chat", json={"message": "hi"})
    from app.ontology import load_ontology
    prompt = seen[0].system_instruction
    assert load_ontology().system_prompt in prompt
    assert "Graph schema (node labels by layer):" in prompt
