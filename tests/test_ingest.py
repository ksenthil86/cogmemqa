"""
Integration tests for INGEST operation (Task 5).
Requires live Neo4j — uses neo4j_driver fixture from conftest.py.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node, ingest_edge
from src.models import (
    Requirement, Functionality, Component, File,
    Commit, Test, Judgment,
    RealizedByEdge, ImplementedByEdge, ModifiesEdge, VerifiesEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


def fresh_id(prefix: str = "test") -> str:
    """Generate a unique id so each test run is independent."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def node_count(driver, label: str, node_id: str) -> int:
    with driver.session() as session:
        result = session.run(
            f"MATCH (n:{label} {{id: $id}}) RETURN count(n) AS cnt",
            id=node_id,
        )
        return result.single()["cnt"]


def edge_props(driver, from_id: str, to_id: str, rel_type: str) -> dict | None:
    with driver.session() as session:
        result = session.run(
            f"MATCH (a {{id: $from_id}})-[r:{rel_type}]->(b {{id: $to_id}}) "
            "RETURN properties(r) AS props",
            from_id=from_id,
            to_id=to_id,
        )
        row = result.single()
        return row["props"] if row else None


# ── Test 1: ingest_node is idempotent ─────────────────────────────────────────

def test_ingest_node_returns_id(neo4j_driver):
    req_id = fresh_id("req")
    req = Requirement(id=req_id, title="Account opening flow")
    result = ingest_node(neo4j_driver, req)
    assert result == req_id


def test_ingest_node_same_node_twice_count_is_one(neo4j_driver):
    req_id = fresh_id("req")
    req = Requirement(id=req_id, title="KYC verification")

    ingest_node(neo4j_driver, req)
    ingest_node(neo4j_driver, req)

    assert node_count(neo4j_driver, "Requirement", req_id) == 1


def test_ingest_node_persists_required_properties(neo4j_driver):
    func_id = fresh_id("func")
    func = Functionality(id=func_id, name="User login", status="active")
    ingest_node(neo4j_driver, func)

    with neo4j_driver.session() as session:
        row = session.run(
            "MATCH (n:Functionality {id: $id}) RETURN n", id=func_id
        ).single()
    node = row["n"]
    assert node["name"] == "User login"
    assert node["status"] == "active"


def test_ingest_node_second_call_updates_properties(neo4j_driver):
    req_id = fresh_id("req")
    ingest_node(neo4j_driver, Requirement(id=req_id, title="Original"))
    ingest_node(neo4j_driver, Requirement(id=req_id, title="Updated"))

    with neo4j_driver.session() as session:
        row = session.run(
            "MATCH (n:Requirement {id: $id}) RETURN n.title AS title", id=req_id
        ).single()
    assert row["title"] == "Updated"


def test_ingest_multiple_different_nodes(neo4j_driver):
    ids = [fresh_id("req") for _ in range(3)]
    for i, nid in enumerate(ids):
        ingest_node(neo4j_driver, Requirement(id=nid, title=f"Req {i}"))
    for nid in ids:
        assert node_count(neo4j_driver, "Requirement", nid) == 1


# ── Test 2: ingest_edge creates relationship with valid_from ──────────────────

def test_ingest_edge_valid_from_is_set(neo4j_driver):
    req_id = fresh_id("req")
    func_id = fresh_id("func")

    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))

    edge = RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW)
    ingest_edge(neo4j_driver, edge)

    props = edge_props(neo4j_driver, req_id, func_id, "REALIZED_BY")
    assert props is not None, "REALIZED_BY relationship not found"
    assert "valid_from" in props


def test_ingest_edge_valid_to_is_null_by_default(neo4j_driver):
    req_id = fresh_id("req")
    func_id = fresh_id("func")
    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW))

    props = edge_props(neo4j_driver, req_id, func_id, "REALIZED_BY")
    assert props.get("valid_to") is None


def test_ingest_edge_twice_does_not_duplicate(neo4j_driver):
    req_id = fresh_id("req")
    func_id = fresh_id("func")
    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))

    edge = RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW)
    ingest_edge(neo4j_driver, edge)
    ingest_edge(neo4j_driver, edge)

    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (a {id: $from_id})-[r:REALIZED_BY]->(b {id: $to_id}) "
            "RETURN count(r) AS cnt",
            from_id=req_id,
            to_id=func_id,
        ).single()["cnt"]
    assert cnt == 1


def test_ingest_edge_modifies(neo4j_driver):
    commit_id = fresh_id("cmt")
    file_id = fresh_id("file")
    ingest_node(neo4j_driver, Commit(id=commit_id, sha="abc123", message="feat: add auth", timestamp=NOW))
    ingest_node(neo4j_driver, File(id=file_id, path="src/auth.py"))

    ingest_edge(neo4j_driver, ModifiesEdge(from_id=commit_id, to_id=file_id, valid_from=NOW))

    props = edge_props(neo4j_driver, commit_id, file_id, "MODIFIES")
    assert props is not None
    assert "valid_from" in props


def test_ingest_edge_preserves_valid_from_on_second_call(neo4j_driver):
    """Second ingest of same edge must NOT overwrite the original valid_from."""
    req_id = fresh_id("req")
    func_id = fresh_id("func")
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later = datetime(2026, 12, 31, tzinfo=timezone.utc)

    ingest_node(neo4j_driver, Requirement(id=req_id, title="T"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=earlier))
    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=later))

    props = edge_props(neo4j_driver, req_id, func_id, "REALIZED_BY")
    # ON CREATE only — second call must not overwrite
    stored_vf = props["valid_from"]
    # Neo4j returns datetime as neo4j.time.DateTime — compare year/month/day
    assert stored_vf.year == 2026 and stored_vf.month == 1 and stored_vf.day == 1
