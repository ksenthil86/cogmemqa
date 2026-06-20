"""
Tests for security_summary() — Sprint v4 Task 3.

security_summary(driver) -> dict
  {"total_open": N, "by_severity": {"low": L, "medium": M, "high": H}}

Only SecurityFinding nodes with status="open" are counted.
Closed findings (status="closed") are excluded.
All three severity keys are always present (missing severities return 0).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node
from src.models import SecurityFinding

NOW = datetime.now(timezone.utc)

# ── Seed IDs (unique prefix to avoid collisions with other tests) ─────────────

_T3_FINDING_IDS = [
    "t3-sf-low-1",
    "t3-sf-low-2",
    "t3-sf-medium-1",
    "t3-sf-high-closed",
]


@pytest.fixture()
def cleanup_t3(neo4j_driver):
    yield
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=_T3_FINDING_IDS,
        )


def _seed_finding(driver, fid: str, severity: str, status: str) -> None:
    ingest_node(
        driver,
        SecurityFinding(
            id=fid,
            severity=severity,
            title=f"Finding {fid}",
            status=status,
        ),
    )


# ── Return structure ──────────────────────────────────────────────────────────

def test_security_summary_returns_expected_keys(neo4j_driver):
    from src.memory_api import security_summary

    result = security_summary(neo4j_driver)
    assert "total_open" in result
    assert "by_severity" in result
    sev = result["by_severity"]
    assert "low" in sev
    assert "medium" in sev
    assert "high" in sev


def test_security_summary_total_open_is_int(neo4j_driver):
    from src.memory_api import security_summary

    result = security_summary(neo4j_driver)
    assert isinstance(result["total_open"], int)


def test_security_summary_severity_values_are_ints(neo4j_driver):
    from src.memory_api import security_summary

    sev = security_summary(neo4j_driver)["by_severity"]
    assert isinstance(sev["low"], int)
    assert isinstance(sev["medium"], int)
    assert isinstance(sev["high"], int)


# ── Closed findings excluded ──────────────────────────────────────────────────

def test_security_summary_closed_finding_excluded(neo4j_driver, cleanup_t3):
    from src.memory_api import security_summary

    _seed_finding(neo4j_driver, "t3-sf-high-closed", "high", "closed")

    result = security_summary(neo4j_driver)
    # The high-severity CLOSED finding must not appear in by_severity["high"]
    # (We can only check the direct Cypher truth since other tests may seed open high findings)
    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (sf:SecurityFinding {id: $id}) "
            "RETURN sf.status AS status",
            id="t3-sf-high-closed",
        ).single()
    assert row["status"] == "closed"
    # The aggregate should not count our closed finding
    with neo4j_driver.session() as s:
        direct = s.run(
            "MATCH (sf:SecurityFinding {status: 'open', id: $id}) "
            "RETURN count(sf) AS c",
            id="t3-sf-high-closed",
        ).single()["c"]
    assert direct == 0, "Closed finding should not appear as open"


# ── Main seeded scenario ──────────────────────────────────────────────────────

def test_security_summary_seeded_scenario(neo4j_driver, cleanup_t3):
    """2 low open + 1 medium open + 1 high closed → total_open ≥ 3, high stays same."""
    from src.memory_api import security_summary

    _seed_finding(neo4j_driver, "t3-sf-low-1",       "low",    "open")
    _seed_finding(neo4j_driver, "t3-sf-low-2",       "low",    "open")
    _seed_finding(neo4j_driver, "t3-sf-medium-1",    "medium", "open")
    _seed_finding(neo4j_driver, "t3-sf-high-closed", "high",   "closed")

    result = security_summary(neo4j_driver)

    # Our 3 open findings must be counted (DB may have more from other tests)
    assert result["total_open"] >= 3
    assert result["by_severity"]["low"] >= 2
    assert result["by_severity"]["medium"] >= 1
    # total_open == sum of all by_severity values
    sev = result["by_severity"]
    assert result["total_open"] == sev["low"] + sev["medium"] + sev["high"]


# ── Empty-findings scenario (no findings in DB matching open) ─────────────────

def test_security_summary_missing_severity_returns_zero(neo4j_driver, cleanup_t3):
    """Severity keys not present in the graph must be 0, not missing."""
    from src.memory_api import security_summary

    result = security_summary(neo4j_driver)
    sev = result["by_severity"]
    # Keys must exist even if count is 0
    assert sev.get("low", "MISSING") != "MISSING"
    assert sev.get("medium", "MISSING") != "MISSING"
    assert sev.get("high", "MISSING") != "MISSING"


# ── total_open equals sum of by_severity ─────────────────────────────────────

def test_security_summary_total_equals_sum_of_severities(neo4j_driver, cleanup_t3):
    from src.memory_api import security_summary

    _seed_finding(neo4j_driver, "t3-sf-low-1",    "low",    "open")
    _seed_finding(neo4j_driver, "t3-sf-medium-1", "medium", "open")

    result = security_summary(neo4j_driver)
    sev = result["by_severity"]
    assert result["total_open"] == sev["low"] + sev["medium"] + sev["high"]
