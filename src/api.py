"""
CoGMEM-QA Inspector API — Sprint v6 (B10).

Thin FastAPI wrapper over src/memory_api.py. Exposes the live Neo4j graph
as JSON endpoints consumed by the Next.js NVL frontend.

Endpoints:
  GET /api/health          — coverage + security + report counts (B7 metrics)
  GET /api/schema          — node label counts (for layer colour mapping)
  GET /api/graph           — default graph snapshot for NVL canvas
  GET /api/graph/expand    — 1-hop neighbourhood for a given elementId
  GET /api/audit/{req_id}  — provenance chain for a Requirement
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from src import memory_api  # noqa: E402 — after dotenv
from src.db import get_driver  # noqa: E402


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    get_driver().verify_connectivity()
    yield


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
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node_to_dict(node: Any) -> dict:
    """Serialise a neo4j Node to a JSON-safe dict."""
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        "properties": dict(node),
    }


def _rel_to_dict(rel: Any) -> dict:
    """Serialise a neo4j Relationship to a JSON-safe dict."""
    return {
        "id": rel.element_id,
        "type": rel.type,
        "startNodeId": rel.start_node.element_id,
        "endNodeId": rel.end_node.element_id,
        "properties": dict(rel),
    }


def _merge_graph(existing: dict, incoming: dict) -> dict:
    """Merge incoming nodes/rels into existing, deduplicating by id."""
    node_ids = {n["id"] for n in existing["nodes"]}
    rel_ids  = {r["id"] for r in existing["relationships"]}

    for node in incoming["nodes"]:
        if node["id"] not in node_ids:
            existing["nodes"].append(node)
            node_ids.add(node["id"])

    for rel in incoming["relationships"]:
        if rel["id"] not in rel_ids:
            existing["relationships"].append(rel)
            rel_ids.add(rel["id"])

    return existing


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
            "MATCH (n)-[r]->(m) "
            "WHERE NOT n:ReasoningTrace AND NOT m:ReasoningTrace "
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
