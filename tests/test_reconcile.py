"""
Integration tests for the RECONCILE operation (Task 7).
Requires live Neo4j — uses neo4j_driver fixture from conftest.py.

Scenario:
  Requirement -[REALIZED_BY]-> Functionality1  (old, active)
  reconcile(driver, req_id, Req -[REALIZED_BY]-> Functionality2)
  → Requirement -[REALIZED_BY]-> Functionality1  (expired: valid_to IS NOT NULL)
    Requirement -[REALIZED_BY]-> Functionality2  (active: valid_to IS NULL)
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node, ingest_edge, reconcile
from src.models import (
    Requirement, Functionality, Component,
    RealizedByEdge, ComposedOfEdge,
)

T1 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 6, 19, 0, 0, 0, tzinfo=timezone.utc)


def _edge_props(driver, from_id: str, to_id: str, rel_type: str) -> dict | None:
    with driver.session() as session:
        row = session.run(
            f"MATCH (a {{id: $from_id}})-[r:{rel_type}]->(b {{id: $to_id}}) "
            "RETURN properties(r) AS props",
            from_id=from_id,
            to_id=to_id,
        ).single()
        return row["props"] if row else None


def _all_edge_props(driver, from_id: str, rel_type: str) -> list[dict]:
    """Properties of every edge of rel_type outgoing from from_id."""
    with driver.session() as session:
        return [
            row["props"]
            for row in session.run(
                f"MATCH (a {{id: $from_id}})-[r:{rel_type}]->(b) "
                "RETURN properties(r) AS props",
                from_id=from_id,
            )
        ]


@pytest.fixture()
def pair(neo4j_driver):
    """Seed one Requirement and two Functionality nodes."""
    ns = uuid.uuid4().hex[:8]
    req_id   = f"req-{ns}"
    func1_id = f"func1-{ns}"
    func2_id = f"func2-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id, title="Account opening"))
    ingest_node(neo4j_driver, Functionality(id=func1_id, name="Old registration"))
    ingest_node(neo4j_driver, Functionality(id=func2_id, name="New registration"))

    return {"req_id": req_id, "func1_id": func1_id, "func2_id": func2_id}


# ── Test 1: old edge is expired ────────────────────────────────────────────────

def test_reconcile_expires_old_edge(neo4j_driver, pair):
    """reconcile must set valid_to on the previously-active edge."""
    ingest_edge(neo4j_driver, RealizedByEdge(
        from_id=pair["req_id"], to_id=pair["func1_id"], valid_from=T1,
    ))

    reconcile(
        neo4j_driver,
        pair["req_id"],
        RealizedByEdge(from_id=pair["req_id"], to_id=pair["func2_id"], valid_from=T2),
    )

    props = _edge_props(neo4j_driver, pair["req_id"], pair["func1_id"], "REALIZED_BY")
    assert props is not None, "Old edge must still exist in graph"
    assert props.get("valid_to") is not None, "Old edge valid_to must be set after reconcile"


# ── Test 2: new edge is active ─────────────────────────────────────────────────

def test_reconcile_new_edge_is_active(neo4j_driver, pair):
    """New edge ingested by reconcile must have valid_to = null."""
    ingest_edge(neo4j_driver, RealizedByEdge(
        from_id=pair["req_id"], to_id=pair["func1_id"], valid_from=T1,
    ))

    reconcile(
        neo4j_driver,
        pair["req_id"],
        RealizedByEdge(from_id=pair["req_id"], to_id=pair["func2_id"], valid_from=T2),
    )

    props = _edge_props(neo4j_driver, pair["req_id"], pair["func2_id"], "REALIZED_BY")
    assert props is not None, "New edge must exist in graph"
    assert props.get("valid_to") is None, "New edge valid_to must be null (active)"


# ── Test 3: both edges remain in the graph ────────────────────────────────────

def test_reconcile_preserves_old_edge_for_history(neo4j_driver, pair):
    """Old edge must remain queryable after reconcile (bi-temporal audit)."""
    ingest_edge(neo4j_driver, RealizedByEdge(
        from_id=pair["req_id"], to_id=pair["func1_id"], valid_from=T1,
    ))

    reconcile(
        neo4j_driver,
        pair["req_id"],
        RealizedByEdge(from_id=pair["req_id"], to_id=pair["func2_id"], valid_from=T2),
    )

    all_props = _all_edge_props(neo4j_driver, pair["req_id"], "REALIZED_BY")
    assert len(all_props) == 2, f"Expected 2 REALIZED_BY edges, got {len(all_props)}"


# ── Test 4: expired valid_to is later than original valid_from ─────────────────

def test_reconcile_valid_to_after_valid_from(neo4j_driver, pair):
    """valid_to on the expired edge must be strictly after its valid_from."""
    ingest_edge(neo4j_driver, RealizedByEdge(
        from_id=pair["req_id"], to_id=pair["func1_id"], valid_from=T1,
    ))

    reconcile(
        neo4j_driver,
        pair["req_id"],
        RealizedByEdge(from_id=pair["req_id"], to_id=pair["func2_id"], valid_from=T2),
    )

    props = _edge_props(neo4j_driver, pair["req_id"], pair["func1_id"], "REALIZED_BY")
    vf = props["valid_from"]
    vt = props["valid_to"]
    assert vt > vf, "valid_to on expired edge must be after valid_from"


# ── Test 5: only same edge type is expired ─────────────────────────────────────

def test_reconcile_does_not_touch_other_edge_types(neo4j_driver):
    """reconcile on REALIZED_BY must not expire COMPOSED_OF edges."""
    ns = uuid.uuid4().hex[:8]
    func_id = f"func-{ns}"
    comp_id  = f"comp-{ns}"
    func2_id = f"func2-{ns}"

    ingest_node(neo4j_driver, Functionality(id=func_id,  name="F1"))
    ingest_node(neo4j_driver, Component(id=comp_id, name="C"))
    ingest_node(neo4j_driver, Functionality(id=func2_id, name="F2"))

    ingest_edge(neo4j_driver, ComposedOfEdge(
        from_id=func_id, to_id=comp_id, valid_from=T1,
    ))

    # Reconcile REALIZED_BY from func_id — COMPOSED_OF must be untouched
    reconcile(
        neo4j_driver,
        func_id,
        RealizedByEdge(from_id=func_id, to_id=func2_id, valid_from=T2),
    )

    comp_props = _edge_props(neo4j_driver, func_id, comp_id, "COMPOSED_OF")
    assert comp_props is not None
    assert comp_props.get("valid_to") is None, "COMPOSED_OF must not be expired by REALIZED_BY reconcile"


# ── Test 6: no existing edge — reconcile still ingests new edge ────────────────

def test_reconcile_no_prior_edge_ingests_new(neo4j_driver):
    """If no active edge exists, reconcile still creates the new edge."""
    ns = uuid.uuid4().hex[:8]
    req_id  = f"req-{ns}"
    func_id = f"func-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))

    reconcile(
        neo4j_driver,
        req_id,
        RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=T2),
    )

    props = _edge_props(neo4j_driver, req_id, func_id, "REALIZED_BY")
    assert props is not None, "Edge must be created even when no prior edge existed"
    assert props.get("valid_to") is None, "New edge must be active"


# ── Test 7: second reconcile expires the previous reconcile's edge ─────────────

def test_reconcile_chained_two_steps(neo4j_driver):
    """Two successive reconciles: only the final edge is active."""
    ns = uuid.uuid4().hex[:8]
    req_id   = f"req-{ns}"
    func1_id = f"func1-{ns}"
    func2_id = f"func2-{ns}"
    func3_id = f"func3-{ns}"
    T3 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func1_id, name="F1"))
    ingest_node(neo4j_driver, Functionality(id=func2_id, name="F2"))
    ingest_node(neo4j_driver, Functionality(id=func3_id, name="F3"))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func1_id, valid_from=T1))
    reconcile(neo4j_driver, req_id,
              RealizedByEdge(from_id=req_id, to_id=func2_id, valid_from=T2))
    reconcile(neo4j_driver, req_id,
              RealizedByEdge(from_id=req_id, to_id=func3_id, valid_from=T3))

    all_props = _all_edge_props(neo4j_driver, req_id, "REALIZED_BY")
    active = [p for p in all_props if p.get("valid_to") is None]
    assert len(active) == 1, f"Exactly 1 active edge expected, got {len(active)}"
    assert len(all_props) == 3, f"All 3 edges should remain in graph, got {len(all_props)}"
