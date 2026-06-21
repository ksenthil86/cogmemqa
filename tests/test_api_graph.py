"""
Tests for GET /api/graph — Sprint v6 Task 2.

Verifies response shape, node/relationship structure, deduplication,
and that ReasoningTrace nodes are excluded from the default canvas view.
All tests use real Neo4j (consistent with project no-mock policy).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from src.api import app
    return TestClient(app)


# ── Status ────────────────────────────────────────────────────────────────────

def test_graph_returns_200(client):
    resp = client.get("/api/graph")
    assert resp.status_code == 200, resp.text


# ── Top-level response shape ──────────────────────────────────────────────────

def test_graph_response_has_nodes_key(client):
    data = client.get("/api/graph").json()
    assert "nodes" in data, "Response missing 'nodes' key"


def test_graph_response_has_relationships_key(client):
    data = client.get("/api/graph").json()
    assert "relationships" in data, "Response missing 'relationships' key"


def test_graph_nodes_is_list(client):
    data = client.get("/api/graph").json()
    assert isinstance(data["nodes"], list)


def test_graph_relationships_is_list(client):
    data = client.get("/api/graph").json()
    assert isinstance(data["relationships"], list)


# ── Node shape ────────────────────────────────────────────────────────────────

def test_graph_node_has_id_field(client):
    data = client.get("/api/graph").json()
    if data["nodes"]:
        node = data["nodes"][0]
        assert "id" in node, f"Node missing 'id': {node}"


def test_graph_node_has_labels_field(client):
    data = client.get("/api/graph").json()
    if data["nodes"]:
        node = data["nodes"][0]
        assert "labels" in node, f"Node missing 'labels': {node}"
        assert isinstance(node["labels"], list)


def test_graph_node_has_properties_field(client):
    data = client.get("/api/graph").json()
    if data["nodes"]:
        node = data["nodes"][0]
        assert "properties" in node, f"Node missing 'properties': {node}"
        assert isinstance(node["properties"], dict)


def test_graph_node_id_is_string(client):
    data = client.get("/api/graph").json()
    if data["nodes"]:
        assert isinstance(data["nodes"][0]["id"], str)


# ── Relationship shape ────────────────────────────────────────────────────────

def test_graph_relationship_has_id_field(client):
    data = client.get("/api/graph").json()
    if data["relationships"]:
        rel = data["relationships"][0]
        assert "id" in rel, f"Relationship missing 'id': {rel}"


def test_graph_relationship_has_type_field(client):
    data = client.get("/api/graph").json()
    if data["relationships"]:
        rel = data["relationships"][0]
        assert "type" in rel, f"Relationship missing 'type': {rel}"
        assert isinstance(rel["type"], str)


def test_graph_relationship_has_start_node_id(client):
    data = client.get("/api/graph").json()
    if data["relationships"]:
        rel = data["relationships"][0]
        assert "startNodeId" in rel, f"Relationship missing 'startNodeId': {rel}"


def test_graph_relationship_has_end_node_id(client):
    data = client.get("/api/graph").json()
    if data["relationships"]:
        rel = data["relationships"][0]
        assert "endNodeId" in rel, f"Relationship missing 'endNodeId': {rel}"


def test_graph_relationship_has_properties_field(client):
    data = client.get("/api/graph").json()
    if data["relationships"]:
        rel = data["relationships"][0]
        assert "properties" in rel
        assert isinstance(rel["properties"], dict)


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_graph_no_duplicate_node_ids(client):
    data = client.get("/api/graph").json()
    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids)), "Duplicate node IDs in /api/graph response"


def test_graph_no_duplicate_relationship_ids(client):
    data = client.get("/api/graph").json()
    ids = [r["id"] for r in data["relationships"]]
    assert len(ids) == len(set(ids)), "Duplicate relationship IDs in /api/graph response"


# ── Content constraints ───────────────────────────────────────────────────────

def test_graph_excludes_reasoning_trace_nodes(client):
    data = client.get("/api/graph").json()
    for node in data["nodes"]:
        assert "ReasoningTrace" not in node["labels"], (
            f"ReasoningTrace node leaked into /api/graph response: {node['id']}"
        )


def test_graph_relationship_count_within_limit(client):
    # LIMIT 200 bounds relationship rows returned by the Cypher query.
    # Unique nodes can exceed 200 since each node appears in multiple rows.
    data = client.get("/api/graph").json()
    assert len(data["relationships"]) <= 200, (
        f"Expected ≤200 relationships (LIMIT clause), got {len(data['relationships'])}"
    )
