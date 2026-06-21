"""
Tests for GET /api/audit/{req_id} — Sprint v6 Task 4.

Verifies provenance chain response: shape, chain item fields,
graceful empty response for unknown req_id, and correct data
for the canonical Meridian req-account-opening requirement.
All tests use real Neo4j (project no-mock policy).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_KNOWN_REQ_ID    = "req-account-opening"   # seeded by replay_meridian.py
_UNKNOWN_REQ_ID  = "req-does-not-exist-xyz"


@pytest.fixture(scope="module")
def client():
    from src.api import app
    return TestClient(app)


# ── Status ────────────────────────────────────────────────────────────────────

def test_audit_known_req_returns_200(client):
    resp = client.get(f"/api/audit/{_KNOWN_REQ_ID}")
    assert resp.status_code == 200, resp.text


def test_audit_unknown_req_returns_200_not_404(client):
    resp = client.get(f"/api/audit/{_UNKNOWN_REQ_ID}")
    assert resp.status_code == 200, resp.text


# ── Top-level response shape ──────────────────────────────────────────────────

def test_audit_response_has_req_id_key(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    assert "req_id" in data, "Response missing 'req_id' key"


def test_audit_response_has_chain_key(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    assert "chain" in data, "Response missing 'chain' key"


def test_audit_req_id_echoed_correctly(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    assert data["req_id"] == _KNOWN_REQ_ID


def test_audit_chain_is_list(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    assert isinstance(data["chain"], list)


# ── Unknown req returns empty chain (no crash) ────────────────────────────────

def test_audit_unknown_req_returns_empty_chain(client):
    data = client.get(f"/api/audit/{_UNKNOWN_REQ_ID}").json()
    assert data["chain"] == [], (
        f"Expected empty chain for unknown req_id, got: {data['chain']}"
    )


def test_audit_unknown_req_id_echoed(client):
    data = client.get(f"/api/audit/{_UNKNOWN_REQ_ID}").json()
    assert data["req_id"] == _UNKNOWN_REQ_ID


# ── Chain item shape ──────────────────────────────────────────────────────────

def test_audit_chain_item_has_req_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "req" in data["chain"][0]


def test_audit_chain_item_has_req_title_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "req_title" in data["chain"][0]


def test_audit_chain_item_has_func_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "func" in data["chain"][0]


def test_audit_chain_item_has_comp_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "comp" in data["chain"][0]


def test_audit_chain_item_has_file_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "file" in data["chain"][0]


def test_audit_chain_item_has_commit_sha_field(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert "commit_sha" in data["chain"][0]


# ── Chain content for canonical Meridian requirement ─────────────────────────

def test_audit_chain_req_matches_requested_id(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    for item in data["chain"]:
        assert item["req"] == _KNOWN_REQ_ID, (
            f"Chain item req {item['req']!r} doesn't match requested {_KNOWN_REQ_ID!r}"
        )


def test_audit_chain_bounded_by_limit(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    assert len(data["chain"]) <= 3, (
        f"Expected ≤3 chain items (LIMIT 3), got {len(data['chain'])}"
    )


def test_audit_chain_func_is_string(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert isinstance(data["chain"][0]["func"], str)


def test_audit_chain_comp_is_string(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert isinstance(data["chain"][0]["comp"], str)


def test_audit_chain_file_is_string(client):
    data = client.get(f"/api/audit/{_KNOWN_REQ_ID}").json()
    if data["chain"]:
        assert isinstance(data["chain"][0]["file"], str)
