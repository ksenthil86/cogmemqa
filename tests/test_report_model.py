"""
Tests for the extended Report model (Sprint v4 Task 1).

Verifies that three new health-metric fields are present with correct defaults
and that the model remains backward-compatible with the two-field constructor
already exercised by test_models.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

NOW = datetime.now(timezone.utc)


# ── Backward-compatibility ────────────────────────────────────────────────────

def test_report_backward_compatible_minimal_fields():
    """Existing two-field instantiation still works after Sprint v4 extension."""
    from src.models import Report

    r = Report(id="rp-compat", summary="legacy", created_at=NOW)
    assert r.id == "rp-compat"
    assert r.summary == "legacy"
    assert r.created_at == NOW


def test_report_new_fields_have_correct_defaults():
    """coverage_pct, open_findings_count, severity_breakdown all default correctly."""
    from src.models import Report

    r = Report(id="rp-defaults", summary="x", created_at=NOW)
    assert r.coverage_pct == 0.0
    assert r.open_findings_count == 0
    assert r.severity_breakdown == "{}"


# ── Field types and values ────────────────────────────────────────────────────

def test_report_coverage_pct_accepts_float():
    from src.models import Report

    r = Report(id="rp-cov", summary="x", created_at=NOW, coverage_pct=75.5)
    assert r.coverage_pct == 75.5


def test_report_open_findings_count_accepts_int():
    from src.models import Report

    r = Report(id="rp-of", summary="x", created_at=NOW, open_findings_count=3)
    assert r.open_findings_count == 3


def test_report_severity_breakdown_accepts_json_string():
    from src.models import Report

    breakdown = json.dumps({"low": 2, "medium": 1, "high": 0})
    r = Report(id="rp-sb", summary="x", created_at=NOW, severity_breakdown=breakdown)
    parsed = json.loads(r.severity_breakdown)
    assert parsed["low"] == 2
    assert parsed["medium"] == 1
    assert parsed["high"] == 0


# ── Integration: ingest_node + read back via Cypher ──────────────────────────

_REPORT_ID = "rp-integration-t1"


@pytest.fixture(autouse=False)
def cleanup_report(neo4j_driver):
    yield
    with neo4j_driver.session() as s:
        s.run("MATCH (n {id: $id}) DETACH DELETE n", id=_REPORT_ID)


def test_report_new_fields_persisted_via_ingest_node(neo4j_driver, cleanup_report):
    """ingest_node writes all three new fields; they round-trip via Cypher."""
    from src.memory_api import ingest_node
    from src.models import Report

    breakdown = json.dumps({"low": 2, "medium": 1, "high": 0})
    ingest_node(
        neo4j_driver,
        Report(
            id=_REPORT_ID,
            summary="Coverage 75.0% · 3 open findings",
            created_at=NOW,
            coverage_pct=75.0,
            open_findings_count=3,
            severity_breakdown=breakdown,
        ),
    )

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (r:Report {id: $id}) "
            "RETURN r.coverage_pct AS cov, r.open_findings_count AS ofc, "
            "       r.severity_breakdown AS sb",
            id=_REPORT_ID,
        ).single()

    assert row is not None, "Report node not found after ingest"
    assert row["cov"] == 75.0
    assert row["ofc"] == 3
    assert json.loads(row["sb"])["low"] == 2
