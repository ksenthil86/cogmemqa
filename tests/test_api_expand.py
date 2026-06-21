"""
Tests for GET /api/graph/expand — Sprint v6 Task 3.

Verifies 1-hop neighbourhood expansion by Neo4j elementId:
response shape, node/rel structure, graceful handling of unknown IDs,
and that the focal node itself is included in the response.
All tests use real Neo4j (project no-mock policy).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from src.api import app
    return TestClient(app)


@pytest.fixture(scope="module")
def real_element_id():
    """Return a real Neo4j elementId for a Requirement node that has neighbours."""
    from src.db import get_driver
    driver = get_driver()
    with driver.session() as s:
        row = s.run(
            "MATCH (n:Requirement)-[r]-() "
            "RETURN elementId(n) AS eid, count(r) AS degree "
            "ORDER BY degree DESC LIMIT 1"
        ).single()
    assert row is not None, "No connected Requirement node found — run replay_meridian.py first"
    return row["eid"]


# ── Status ─────────────────────────────────────────────────────────────────────

def test_expand_known_node_returns_200(client, real_element_id):
    resp = client.get("/api/graph/expand", params={"element_id": real_element_id})
    assert resp.status_code == 200, resp.text


def test_expand_unknown_id_returns_200_not_500(client):
    resp = client.get("/api/graph/expand", params={"element_id": "4:00000000-0000-0000-0000-000000000000:99999"})
    assert resp.status_code == 200, resp.text


# ── Top-level response shape ───────────────────────────────────────────────────

def test_expand_response_has_nodes_key(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    assert "nodes" in data


def test_expand_response_has_relationships_key(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    assert "relationships" in data


def test_expand_nodes_is_list(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    assert isinstance(data["nodes"], list)


def test_expand_relationships_is_list(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    assert isinstance(data["relationships"], list)


# ── Unknown ID returns empty lists (no crash) ─────────────────────────────────

def test_expand_unknown_id_returns_empty_nodes(client):
    data = client.get("/api/graph/expand", params={"element_id": "4:00000000-0000-0000-0000-000000000000:99999"}).json()
    assert data["nodes"] == []


def test_expand_unknown_id_returns_empty_relationships(client):
    data = client.get("/api/graph/expand", params={"element_id": "4:00000000-0000-0000-0000-000000000000:99999"}).json()
    assert data["relationships"] == []


# ── Focal node is included in response ────────────────────────────────────────

def test_expand_focal_node_included(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert real_element_id in node_ids, (
        f"Focal node {real_element_id!r} not found in expand response"
    )


# ── Node shape ────────────────────────────────────────────────────────────────

def test_expand_node_has_id(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    if data["nodes"]:
        assert "id" in data["nodes"][0]


def test_expand_node_has_labels(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    if data["nodes"]:
        node = data["nodes"][0]
        assert "labels" in node
        assert isinstance(node["labels"], list)


def test_expand_node_has_properties(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    if data["nodes"]:
        assert "properties" in data["nodes"][0]


# ── Relationship shape ────────────────────────────────────────────────────────

def test_expand_relationship_has_required_fields(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    if data["relationships"]:
        rel = data["relationships"][0]
        for field in ("id", "type", "startNodeId", "endNodeId", "properties"):
            assert field in rel, f"Relationship missing field {field!r}"


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_expand_no_duplicate_node_ids(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids)), "Duplicate node IDs in expand response"


def test_expand_no_duplicate_relationship_ids(client, real_element_id):
    data = client.get("/api/graph/expand", params={"element_id": real_element_id}).json()
    ids = [r["id"] for r in data["relationships"]]
    assert len(ids) == len(set(ids)), "Duplicate relationship IDs in expand response"


# ── Missing parameter ─────────────────────────────────────────────────────────

def test_expand_missing_param_returns_422(client):
    resp = client.get("/api/graph/expand")
    assert resp.status_code == 422, (
        f"Expected 422 for missing element_id, got {resp.status_code}"
    )
