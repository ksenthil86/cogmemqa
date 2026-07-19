"""
Task 1 tests — Meridian banking app stub (FastAPI ASGI).

Tests run against the ASGI app directly via httpx.AsyncClient (no server needed).
All endpoints are verified for happy-path and failure-path behaviour.
"""
from __future__ import annotations

import pytest
import httpx
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from fixtures.meridian_app.main import app as meridian_app
    return meridian_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── Import sanity ──────────────────────────────────────────────────────────────

def test_meridian_app_importable():
    from fixtures.meridian_app.main import app
    assert app is not None


# ── POST /accounts ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_accounts_returns_201(client):
    resp = await client.post("/accounts", json={"national_id": "NID-001", "name": "Alice"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_post_accounts_duplicate_returns_409(client):
    resp = await client.post("/accounts", json={"national_id": "DUPLICATE", "name": "Bob"})
    assert resp.status_code == 409


# ── POST /kyc/verify ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_kyc_verify_returns_verified(client):
    resp = await client.post("/kyc/verify", json={"account_id": "acc-001"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_post_kyc_verify_missing_account_id_returns_422(client):
    resp = await client.post("/kyc/verify", json={})
    assert resp.status_code == 422


# ── POST /transfers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_transfers_returns_200(client):
    resp = await client.post("/transfers", json={"amount": 100, "balance": 500})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_transfers_insufficient_funds_returns_402(client):
    resp = await client.post("/transfers", json={"amount": 1000, "balance": 50})
    assert resp.status_code == 402
    assert resp.json()["error"] == "INSUFFICIENT_FUNDS"


# ── GET /transactions ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_transactions_returns_list(client):
    resp = await client.get("/transactions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 20


@pytest.mark.asyncio
async def test_get_transactions_bad_page_returns_400(client):
    resp = await client.get("/transactions?page=0")
    assert resp.status_code == 400


# ── GET /fraud/alerts ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_fraud_alerts_low_amount_returns_empty(client):
    resp = await client.get("/fraud/alerts?amount=100")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_fraud_alerts_high_amount_returns_alerts(client):
    resp = await client.get("/fraud/alerts?amount=50000")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
