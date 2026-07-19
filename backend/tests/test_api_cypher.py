"""Tests for POST /api/cypher — guarded read-only Cypher endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _node_count(client) -> int:
    data = client.post(
        "/api/cypher", json={"query": "MATCH (n) RETURN count(n) AS c"}
    ).json()
    return data["rows"][0]["c"]


def test_read_query_returns_rows_and_graph(client):
    data = client.post(
        "/api/cypher",
        json={"query": "MATCH (r:Requirement) RETURN r LIMIT 3"},
    ).json()
    assert len(data["rows"]) == 3
    assert data["rows"][0]["r"]["labels"] == ["Requirement"]
    assert len(data["graph"]["nodes"]) == 3


def test_parameters_supported(client):
    data = client.post(
        "/api/cypher",
        json={
            "query": "MATCH (r:Requirement {id: $rid}) RETURN r.title AS title",
            "parameters": {"rid": "req-account-opening"},
        },
    ).json()
    assert data["rows"][0]["title"] == "Account Opening"


def test_write_query_rejected_and_graph_unchanged(client):
    before = _node_count(client)
    resp = client.post("/api/cypher", json={"query": "CREATE (n:Hacked) RETURN n"})
    assert resp.status_code == 422
    assert "CREATE" in resp.json()["detail"]
    assert _node_count(client) == before


def test_call_rejected(client):
    resp = client.post("/api/cypher", json={"query": "CALL db.labels()"})
    assert resp.status_code == 422


def test_comment_smuggled_write_rejected(client):
    resp = client.post(
        "/api/cypher", json={"query": "MATCH (n) //x\nDETACH DELETE n"}
    )
    assert resp.status_code == 422


def test_empty_query_rejected(client):
    assert client.post("/api/cypher", json={"query": "  "}).status_code == 422


def test_record_cap_100(client):
    data = client.post(
        "/api/cypher", json={"query": "MATCH (r:Requirement) RETURN r.id"}
    ).json()
    assert len(data["rows"]) == 100
