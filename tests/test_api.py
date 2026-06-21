"""
Tests for src/api.py — Sprint v6 Task 1.

FastAPI health and schema endpoints. Uses TestClient (ASGI, no running server).
All tests hit real Neo4j — consistent with project no-mock policy.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── import guard ──────────────────────────────────────────────────────────────

def test_api_importable():
    from src.api import app
    assert app is not None


# ── /api/health ───────────────────────────────────────────────────────────────

def test_health_returns_200():
    from src.api import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200, resp.text


def test_health_response_has_required_keys():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/health").json()
    for key in (
        "coverage_pct",
        "covered_ac",
        "total_ac",
        "open_findings_count",
        "by_severity",
        "report_count",
    ):
        assert key in data, f"Missing key in /api/health response: {key!r}"


def test_health_coverage_pct_is_float():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/health").json()
    assert isinstance(data["coverage_pct"], float), (
        f"coverage_pct should be float, got {type(data['coverage_pct'])}"
    )


def test_health_by_severity_has_three_keys():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/health").json()
    sev = data["by_severity"]
    for key in ("low", "medium", "high"):
        assert key in sev, f"Missing severity key {key!r} in by_severity"


def test_health_report_count_is_int():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/health").json()
    assert isinstance(data["report_count"], int), (
        f"report_count should be int, got {type(data['report_count'])}"
    )


def test_health_total_ac_is_non_negative():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/health").json()
    assert data["total_ac"] >= 0
    assert data["covered_ac"] >= 0


# ── /api/schema ───────────────────────────────────────────────────────────────

def test_schema_returns_200():
    from src.api import app
    client = TestClient(app)
    resp = client.get("/api/schema")
    assert resp.status_code == 200, resp.text


def test_schema_returns_list():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/schema").json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"


def test_schema_items_have_label_and_count():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/schema").json()
    if data:
        item = data[0]
        assert "label" in item, f"Missing 'label' key in schema item: {item}"
        assert "count" in item, f"Missing 'count' key in schema item: {item}"
        assert isinstance(item["label"], str)
        assert isinstance(item["count"], int)


def test_schema_count_non_negative():
    from src.api import app
    client = TestClient(app)
    data = client.get("/api/schema").json()
    for item in data:
        assert item["count"] >= 0, f"Negative count for label {item['label']!r}"
