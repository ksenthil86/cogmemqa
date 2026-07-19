"""
CoGMEM-QA Inspector API — Sprint v6 (B10).

Thin FastAPI wrapper over src/memory_api.py. Exposes the live Neo4j graph
as JSON endpoints consumed by the Next.js NVL frontend.

Endpoints:
  GET  /api/health          — coverage + security + report counts (B7 metrics)
  GET  /api/schema          — node label counts (for layer colour mapping)
  GET  /api/graph           — default graph snapshot for NVL canvas
  GET  /api/graph/expand    — 1-hop neighbourhood for a given elementId
  GET  /api/audit/{req_id}  — provenance chain for a Requirement
  POST /api/chat            — Gemini agent loop over the graph (chat panel)
  GET  /api/traces          — Judgment → ReasoningTrace decision traces
  GET  /api/reports         — health Report nodes (documents tab)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

_memory_log = logging.getLogger("cogmem.memory")

from app import memory_api  # noqa: E402 — after dotenv
from app.chat_agent import run_chat_agent  # noqa: E402
from app.db import get_driver  # noqa: E402
from app.memory_client import MemoryService  # noqa: E402


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    get_driver().verify_connectivity()
    memory = MemoryService()
    await memory.start()  # best-effort: failure leaves memory.active == False
    app.state.memory_service = memory
    yield
    await memory.stop()


app = FastAPI(
    title="CoGMEM-QA Inspector API",
    description="Live graph API for the CoGMEM-Inspector dashboard",
    version="0.6.0",
    lifespan=_lifespan,
)

_FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Helpers (moved to src/graph_serialization.py; re-exported for back-compat) ─

from app.graph_serialization import (  # noqa: E402, F401
    _sanitize,
    _node_to_dict,
    _rel_to_dict,
    _merge_graph,
)


# ── Endpoints (Task 1: health + schema) ───────────────────────────────────────

@app.get("/api/health")
def get_health() -> dict:
    """Live B7 health metrics: coverage, open findings, report count."""
    driver = get_driver()
    cov = memory_api.coverage_summary(driver)
    sec = memory_api.security_summary(driver)
    with driver.session() as s:
        report_count = s.run(
            "MATCH (r:Report) RETURN count(r) AS n"
        ).single()["n"]
    return {
        "coverage_pct":       cov["coverage_pct"],
        "covered_ac":         cov["covered_ac"],
        "total_ac":           cov["total_ac"],
        "open_findings_count": sec["total_open"],
        "by_severity":        sec["by_severity"],
        "report_count":       report_count,
    }


@app.get("/api/schema")
def get_schema() -> list[dict]:
    """Node label counts — used by the frontend for layer colour mapping."""
    driver = get_driver()
    with driver.session() as s:
        rows = s.run(
            "MATCH (n) "
            "UNWIND labels(n) AS label "
            "RETURN label, count(*) AS count "
            "ORDER BY count DESC"
        ).data()
    return [{"label": r["label"], "count": r["count"]} for r in rows]


@app.get("/api/config")
def get_config() -> dict:
    """Presentation config served from schema/cogmem-qa.yaml (single source of truth)."""
    from app.ontology import load_ontology

    ont = load_ontology()
    return {
        "node_colors": ont.node_colors,
        "node_sizes": ont.node_sizes,
        "demo_scenarios": ont.demo_scenarios,
    }


# ── Endpoints (Tasks 2-4: graph, expand, audit) ───────────────────────────────

@app.get("/api/graph")
def get_graph() -> dict:
    """Default graph snapshot for the NVL canvas (excludes ReasoningTrace)."""
    driver = get_driver()
    nodes: list[dict] = []
    rels:  list[dict] = []
    seen_node_ids: set[str] = set()
    seen_rel_ids:  set[str] = set()

    with driver.session() as s:
        records = s.run(
            # Excludes CoGMEM reasoning steps and neo4j-agent-memory nodes
            # (Message/Conversation/Entity/Preference) from the canvas.
            "MATCH (n)-[r]->(m) "
            "WHERE none(x IN [n, m] WHERE x:ReasoningTrace OR x:Message "
            "OR x:Conversation OR x:Entity OR x:Preference) "
            "RETURN n, r, m LIMIT 200"
        )
        for record in records:
            for node in (record["n"], record["m"]):
                nid = node.element_id
                if nid not in seen_node_ids:
                    nodes.append(_node_to_dict(node))
                    seen_node_ids.add(nid)
            rel = record["r"]
            rid = rel.element_id
            if rid not in seen_rel_ids:
                rels.append(_rel_to_dict(rel))
                seen_rel_ids.add(rid)

    return {"nodes": nodes, "relationships": rels}


@app.get("/api/graph/expand")
def expand_node(element_id: str = Query(..., description="Neo4j elementId of the node to expand")) -> dict:
    """Return the 1-hop neighbourhood of a node by its Neo4j elementId."""
    driver = get_driver()
    nodes: list[dict] = []
    rels:  list[dict] = []
    seen_node_ids: set[str] = set()
    seen_rel_ids:  set[str] = set()

    with driver.session() as s:
        records = s.run(
            "MATCH (n) WHERE elementId(n) = $eid "
            "MATCH (n)-[r]-(neighbour) "
            "RETURN n, r, neighbour",
            eid=element_id,
        )
        for record in records:
            for node in (record["n"], record["neighbour"]):
                nid = node.element_id
                if nid not in seen_node_ids:
                    nodes.append(_node_to_dict(node))
                    seen_node_ids.add(nid)
            rel = record["r"]
            rid = rel.element_id
            if rid not in seen_rel_ids:
                rels.append(_rel_to_dict(rel))
                seen_rel_ids.add(rid)

    return {"nodes": nodes, "relationships": rels}


@app.get("/api/audit/{req_id}")
def get_audit(req_id: str) -> dict:
    """Provenance chain: Requirement → Functionality → Component → File ← Commit."""
    driver = get_driver()
    with driver.session() as s:
        rows = s.run(
            "MATCH (r:Requirement {id: $req_id}) "
            "-[:REALIZED_BY]->(func:Functionality) "
            "-[:COMPOSED_OF]->(comp:Component) "
            "-[:IMPLEMENTED_BY]->(f:File) "
            "OPTIONAL MATCH (c:Commit)-[:MODIFIES]->(f) "
            "RETURN r.id AS req, r.title AS req_title, "
            "       func.id AS func, comp.id AS comp, "
            "       f.path AS file, c.sha AS commit_sha "
            "LIMIT 3",
            req_id=req_id,
        ).data()
    chain = [
        {
            "req":        r["req"],
            "req_title":  r["req_title"],
            "func":       r["func"],
            "comp":       r["comp"],
            "file":       r["file"],
            "commit_sha": r["commit_sha"],
        }
        for r in rows
    ]
    return {"req_id": req_id, "chain": chain}


# ── Endpoints (chat + traces + reports) ───────────────────────────────────────

class ChatTurn(BaseModel):
    role: str  # "user" | "model"
    text: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    # Deprecated: used only as a fallback when conversation memory is inactive.
    history: list[ChatTurn] = []


async def _memory_pre_chat(
    req: ChatRequest, session_id: str
) -> tuple[bool, str | None, list[dict], dict]:
    """Shared memory pre-step: returns (memory_active, memory_block, history, counts)."""
    memory: MemoryService | None = getattr(app.state, "memory_service", None)
    memory_active = bool(memory and memory.active)
    memory_block = None
    history = [t.model_dump() for t in req.history]
    counts = {"entities": 0, "preferences": 0}
    if memory_active:
        # Defense-in-depth: MemoryService already swallows errors, but no
        # memory implementation may ever take down the chat endpoint.
        try:
            memory_block, history = await memory.get_chat_context(session_id, req.message)
            counts = await memory.record_user_message(session_id, req.message)
        except Exception:
            _memory_log.exception("memory pre-chat step failed")
            memory_active = False
            history = [t.model_dump() for t in req.history]
    return memory_active, memory_block, history, counts


async def _memory_post_chat(memory_active: bool, session_id: str, response: str) -> None:
    memory: MemoryService | None = getattr(app.state, "memory_service", None)
    if memory_active and memory is not None:
        try:
            await memory.record_model_message(session_id, response)
        except Exception:
            _memory_log.exception("memory post-chat step failed")


@app.post(
    "/api/chat",
    responses={
        422: {"description": "Empty message"},
        502: {"description": "Chat agent / LLM failure"},
    },
)
async def post_chat(req: ChatRequest) -> dict:
    """
    Run the Gemini tool loop over the graph and return the final answer.

    Conversation memory (neo4j-agent-memory) is best-effort: when active,
    history comes from the stored session and the prompt gains a long-term
    memory block; when inactive, the client-sent history is used.

    Response shape:
      {response, tool_calls: [{name, inputs, duration_ms, output_preview}],
       graph_data: {nodes, relationships}, session_id, memory_active,
       entities_extracted, preferences_detected}
    """
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    session_id = req.session_id or str(uuid4())
    memory_active, memory_block, history, counts = await _memory_pre_chat(req, session_id)

    # Test hook: tests set app.state.chat_generate_fn to stub out Gemini.
    generate_fn = getattr(app.state, "chat_generate_fn", None)
    try:
        result = await run_chat_agent(
            get_driver(),
            req.message,
            history=history,
            generate_fn=generate_fn,
            memory_context=memory_block,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"chat agent failed: {exc}") from exc

    await _memory_post_chat(memory_active, session_id, result["response"])

    result.update(
        session_id=session_id,
        memory_active=memory_active,
        entities_extracted=counts["entities"],
        preferences_detected=counts["preferences"],
    )
    return result


class CypherRequest(BaseModel):
    query: str
    parameters: dict[str, Any] = {}


@app.post(
    "/api/cypher",
    responses={422: {"description": "Empty or non-read-only query"}},
)
def post_cypher(req: CypherRequest) -> dict:
    """
    Execute read-only Cypher against the graph.

    Unlike the create-context-graph scaffold (whose bolt /cypher path has no
    guard), every query goes through chat_tools.assert_read_only.
    Results capped at 100 records.
    """
    from app.chat_tools import CypherWriteError, assert_read_only
    from app.graph_serialization import extract_graph_from_records

    if not req.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")
    try:
        assert_read_only(req.query)
    except CypherWriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    driver = get_driver()
    with driver.session() as s:
        records = list(s.run(req.query, **req.parameters))[:100]

    graph = extract_graph_from_records(records)

    def _render(value: Any) -> Any:
        from neo4j.graph import Node, Path, Relationship

        if isinstance(value, Node):
            return _node_to_dict(value)
        if isinstance(value, Relationship):
            return _rel_to_dict(value)
        if isinstance(value, Path):
            return {"path_length": len(value.relationships)}
        if isinstance(value, (list, tuple)):
            return [_render(v) for v in value]
        return _sanitize(value)

    rows = [{k: _render(v) for k, v in rec.items()} for rec in records]
    return {"rows": rows, "graph": graph}


_SSE_IDLE_TIMEOUT_S = 120.0
_SSE_OVERALL_TIMEOUT_S = 300.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post(
    "/api/chat/stream",
    responses={422: {"description": "Empty message"}},
)
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """
    Streaming variant of POST /api/chat (SSE over a POST body).

    Event order: session_id → (tool_start | tool_end)* → entities_extracted →
    preferences_detected → text_delta* → done. `error` may appear instead of
    text; the stream always terminates with `done`.
    """
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    session_id = req.session_id or str(uuid4())
    generate_fn = getattr(app.state, "chat_generate_fn", None)
    queue: asyncio.Queue = asyncio.Queue()

    async def event_cb(event: str, data: dict) -> None:
        await queue.put({"event": event, "data": data})

    async def run_agent() -> None:
        try:
            memory_active, memory_block, history, counts = await _memory_pre_chat(
                req, session_id
            )
            await event_cb("entities_extracted", {"count": counts["entities"]})
            await event_cb("preferences_detected", {"count": counts["preferences"]})

            result = await run_chat_agent(
                get_driver(),
                req.message,
                history=history,
                generate_fn=generate_fn,
                memory_context=memory_block,
                event_cb=event_cb,
            )
            await _memory_post_chat(memory_active, session_id, result["response"])
            await event_cb("done", {
                "response": result["response"],
                "tool_calls": result["tool_calls"],
                "graph_data": result["graph_data"],
                "session_id": session_id,
                "memory_active": memory_active,
                "entities_extracted": counts["entities"],
                "preferences_detected": counts["preferences"],
            })
        except Exception as exc:  # surfaced to the client as an SSE error event
            logging.getLogger("cogmem.chat").exception("chat stream agent failed")
            await event_cb("error", {"detail": f"chat agent failed: {exc}"})
            await event_cb("done", {"session_id": session_id})

    async def event_generator():
        task = asyncio.create_task(run_agent())
        loop = asyncio.get_running_loop()
        started = loop.time()
        yield _sse("session_id", {"session_id": session_id})
        try:
            while True:
                if loop.time() - started > _SSE_OVERALL_TIMEOUT_S:
                    yield _sse("error", {"detail": "Request exceeded maximum duration"})
                    yield _sse("done", {"session_id": session_id})
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_IDLE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    yield _sse("error", {"detail": "Request timed out"})
                    yield _sse("done", {"session_id": session_id})
                    break
                yield _sse(event["event"], event["data"])
                if event["event"] == "done":
                    break
        finally:
            task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/traces")
def get_traces(agent_role: str | None = None) -> list[dict]:
    """Decision traces: Judgment nodes with their ordered ReasoningTrace steps."""
    driver = get_driver()
    cypher = (
        "MATCH (j:Judgment) "
        + ("WHERE j.agent_role = $agent_role " if agent_role else "")
        + "OPTIONAL MATCH (j)-[:HAS_STEP]->(t:ReasoningTrace) "
        "WITH j, t ORDER BY t.timestamp "
        "WITH j, collect(t) AS steps "
        "RETURN j, steps "
        "ORDER BY j.id DESC LIMIT 50"
    )
    params = {"agent_role": agent_role} if agent_role else {}
    with driver.session() as s:
        rows = list(s.run(cypher, **params))

    traces = []
    for row in rows:
        j = row["j"]
        traces.append({
            "id":         j.get("id"),
            "label":      j.get("label"),
            "agent_role": j.get("agent_role"),
            "confidence": j.get("confidence"),
            "reasoning":  j.get("reasoning"),
            "steps": [
                {
                    "id":        t.get("id"),
                    "decision":  t.get("decision"),
                    "content":   t.get("content"),
                    "timestamp": _sanitize(t.get("timestamp")),
                }
                for t in row["steps"]
            ],
        })
    return traces


@app.get("/api/reports")
def get_reports() -> list[dict]:
    """Health Report nodes, newest first — powers the Documents tab."""
    driver = get_driver()
    with driver.session() as s:
        rows = s.run(
            "MATCH (r:Report) RETURN r ORDER BY r.created_at DESC LIMIT 50"
        ).data()
    return [
        {
            "id":                  r["r"].get("id"),
            "summary":             r["r"].get("summary"),
            "coverage_pct":        r["r"].get("coverage_pct"),
            "open_findings_count": r["r"].get("open_findings_count"),
            "created_at":          _sanitize(r["r"].get("created_at")),
        }
        for r in rows
    ]
