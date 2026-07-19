"""Tests for GET /api/config — ontology-driven presentation config."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_config_returns_200(client):
    assert client.get("/api/config").status_code == 200


def test_config_shape(client):
    data = client.get("/api/config").json()
    for key in ("node_colors", "node_sizes", "demo_scenarios"):
        assert key in data


def test_config_colors_from_yaml(client):
    data = client.get("/api/config").json()
    assert data["node_colors"]["Requirement"] == "#2563EB"
    assert data["node_colors"]["Project"] == "#F43F5E"
    assert data["node_sizes"]["Project"] == 30


def test_config_scenarios(client):
    data = client.get("/api/config").json()
    assert len(data["demo_scenarios"]) == 3
    assert all(s["prompts"] for s in data["demo_scenarios"])
