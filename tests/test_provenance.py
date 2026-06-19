"""
Integration tests for the provenance write-primitives (Task 8).
Requires live Neo4j — uses neo4j_driver fixture from conftest.py.

write_provenance creates:
  Judgment node
  N ReasoningTrace nodes, each linked by HAS_STEP from the Judgment
  INFORMED_BY edges from the Judgment to each node in informed_by_ids
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node, ingest_edge, write_provenance
from src.models import (
    Requirement, Functionality,
    Judgment, ReasoningTrace,
    RealizedByEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
T1  = datetime(2026, 6, 19, 12,  0, 1, tzinfo=timezone.utc)
T2  = datetime(2026, 6, 19, 12,  0, 2, tzinfo=timezone.utc)


def _ns() -> str:
    return uuid.uuid4().hex[:8]


def _count_rels(driver, from_id: str, rel_type: str) -> int:
    with driver.session() as session:
        return session.run(
            f"MATCH ({{id: $fid}})-[r:{rel_type}]->() RETURN count(r) AS cnt",
            fid=from_id,
        ).single()["cnt"]


def _node_exists(driver, node_id: str) -> bool:
    with driver.session() as session:
        return session.run(
            "MATCH (n {id: $id}) RETURN count(n) AS cnt",
            id=node_id,
        ).single()["cnt"] > 0


def _rels_to(driver, from_id: str, to_id: str, rel_type: str) -> int:
    with driver.session() as session:
        return session.run(
            f"MATCH (a {{id: $fid}})-[r:{rel_type}]->(b {{id: $tid}}) "
            "RETURN count(r) AS cnt",
            fid=from_id,
            tid=to_id,
        ).single()["cnt"]


# ── Shared fixture ─────────────────────────────────────────────────────────────

@pytest.fixture()
def context(neo4j_driver):
    """Seed a Requirement + Functionality, return their ids."""
    ns = _ns()
    req_id  = f"req-{ns}"
    func_id = f"func-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id, title="KYC check"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="Identity verification"))
    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW))

    return {"req_id": req_id, "func_id": func_id}


# ── Test 1: returns judgment id ────────────────────────────────────────────────

def test_write_provenance_returns_judgment_id(neo4j_driver, context):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")
    tr = ReasoningTrace(id=f"tr-{ns}", agent_role="supervisor",
                        decision="All criteria met", timestamp=T1)

    result = write_provenance(neo4j_driver, j, [tr], [context["req_id"]])
    assert result == j.id


# ── Test 2: Judgment node is in the graph ──────────────────────────────────────

def test_write_provenance_creates_judgment_node(neo4j_driver, context):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")

    write_provenance(neo4j_driver, j, [], [])

    assert _node_exists(neo4j_driver, j.id), "Judgment node must exist after write_provenance"


# ── Test 3: ReasoningTrace nodes are in the graph ─────────────────────────────

def test_write_provenance_creates_trace_nodes(neo4j_driver, context):
    ns = _ns()
    j   = Judgment(id=f"j-{ns}",  agent_role="supervisor", label="PASS")
    tr1 = ReasoningTrace(id=f"tr1-{ns}", agent_role="supervisor",
                         decision="Step 1 checked", timestamp=T1)
    tr2 = ReasoningTrace(id=f"tr2-{ns}", agent_role="supervisor",
                         decision="Step 2 checked", timestamp=T2)

    write_provenance(neo4j_driver, j, [tr1, tr2], [])

    assert _node_exists(neo4j_driver, tr1.id), "First ReasoningTrace must exist"
    assert _node_exists(neo4j_driver, tr2.id), "Second ReasoningTrace must exist"


# ── Test 4: HAS_STEP edges from Judgment to each trace ────────────────────────

def test_write_provenance_creates_has_step_edges(neo4j_driver, context):
    ns = _ns()
    j   = Judgment(id=f"j-{ns}",  agent_role="supervisor", label="PASS")
    tr1 = ReasoningTrace(id=f"tr1-{ns}", agent_role="supervisor",
                         decision="Step 1", timestamp=T1)
    tr2 = ReasoningTrace(id=f"tr2-{ns}", agent_role="supervisor",
                         decision="Step 2", timestamp=T2)

    write_provenance(neo4j_driver, j, [tr1, tr2], [])

    assert _rels_to(neo4j_driver, j.id, tr1.id, "HAS_STEP") == 1, \
        "HAS_STEP must exist from Judgment to first ReasoningTrace"
    assert _rels_to(neo4j_driver, j.id, tr2.id, "HAS_STEP") == 1, \
        "HAS_STEP must exist from Judgment to second ReasoningTrace"


# ── Test 5: correct HAS_STEP count ────────────────────────────────────────────

def test_write_provenance_has_step_count_matches_trace_steps(neo4j_driver):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")
    traces = [
        ReasoningTrace(id=f"tr{i}-{ns}", agent_role="supervisor",
                       decision=f"Step {i}", timestamp=NOW)
        for i in range(3)
    ]

    write_provenance(neo4j_driver, j, traces, [])

    assert _count_rels(neo4j_driver, j.id, "HAS_STEP") == 3


# ── Test 6: INFORMED_BY edges from Judgment to each informed_by_id ─────────────

def test_write_provenance_creates_informed_by_edges(neo4j_driver, context):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")

    write_provenance(neo4j_driver, j, [], [context["req_id"], context["func_id"]])

    assert _rels_to(neo4j_driver, j.id, context["req_id"],  "INFORMED_BY") == 1, \
        "INFORMED_BY must point to Requirement"
    assert _rels_to(neo4j_driver, j.id, context["func_id"], "INFORMED_BY") == 1, \
        "INFORMED_BY must point to Functionality"


# ── Test 7: correct INFORMED_BY count ─────────────────────────────────────────

def test_write_provenance_informed_by_count_matches_ids(neo4j_driver, context):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")

    write_provenance(neo4j_driver, j, [], [context["req_id"], context["func_id"]])

    assert _count_rels(neo4j_driver, j.id, "INFORMED_BY") == 2


# ── Test 8: empty trace_steps and informed_by_ids ─────────────────────────────

def test_write_provenance_zero_traces_and_zero_informed(neo4j_driver):
    ns = _ns()
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="SKIP")

    result = write_provenance(neo4j_driver, j, [], [])

    assert result == j.id
    assert _node_exists(neo4j_driver, j.id)
    assert _count_rels(neo4j_driver, j.id, "HAS_STEP") == 0
    assert _count_rels(neo4j_driver, j.id, "INFORMED_BY") == 0


# ── Test 9: write_provenance is idempotent ────────────────────────────────────

def test_write_provenance_idempotent(neo4j_driver, context):
    """Calling twice must not duplicate nodes or edges."""
    ns = _ns()
    j  = Judgment(id=f"j-{ns}", agent_role="supervisor", label="PASS")
    tr = ReasoningTrace(id=f"tr-{ns}", agent_role="supervisor",
                        decision="Once", timestamp=T1)

    write_provenance(neo4j_driver, j, [tr], [context["req_id"]])
    write_provenance(neo4j_driver, j, [tr], [context["req_id"]])

    assert _count_rels(neo4j_driver, j.id, "HAS_STEP")    == 1
    assert _count_rels(neo4j_driver, j.id, "INFORMED_BY") == 1
