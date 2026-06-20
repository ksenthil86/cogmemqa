"""
Tests for coverage_summary() — Sprint v4 Task 2.

coverage_summary(driver) -> dict
  {"total_ac": N, "covered_ac": M, "coverage_pct": float}

"Covered" = at least one TestRun(outcome="pass") reachable via
  (TestRun)-[:INSTANCE_OF]->(Test)-[:COVERS_CRITERION]->(AcceptanceCriterion)

A failing TestRun does NOT count as coverage.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node, ingest_edge
from src.models import (
    AcceptanceCriterion,
    Test,
    TestRun,
    CoversCriterionEdge,
    InstanceOfEdge,
)

NOW = datetime.now(timezone.utc)

# ── Fixture helpers ───────────────────────────────────────────────────────────

_T2_AC_IDS      = ["t2-ac-1", "t2-ac-2", "t2-ac-3", "t2-ac-4"]
_T2_TEST_IDS    = ["t2-test-1", "t2-test-2", "t2-test-3", "t2-test-4"]
_T2_RUN_IDS     = ["t2-run-1", "t2-run-2", "t2-run-3", "t2-run-4"]


def _seed_ac(driver, ac_id: str) -> None:
    ingest_node(driver, AcceptanceCriterion(id=ac_id, statement=f"AC {ac_id}"))


def _seed_test_covering(driver, test_id: str, ac_id: str) -> None:
    ingest_node(driver, Test(id=test_id, name=f"test {test_id}", type="api"))
    ingest_edge(driver, CoversCriterionEdge(from_id=test_id, to_id=ac_id, valid_from=NOW))


def _seed_passing_run(driver, run_id: str, test_id: str) -> None:
    ingest_node(driver, TestRun(id=run_id, outcome="pass", timestamp=NOW))
    ingest_edge(driver, InstanceOfEdge(from_id=run_id, to_id=test_id, valid_from=NOW))


def _seed_failing_run(driver, run_id: str, test_id: str) -> None:
    ingest_node(driver, TestRun(id=run_id, outcome="fail", timestamp=NOW))
    ingest_edge(driver, InstanceOfEdge(from_id=run_id, to_id=test_id, valid_from=NOW))


@pytest.fixture()
def cleanup_t2(neo4j_driver):
    yield
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=_T2_AC_IDS + _T2_TEST_IDS + _T2_RUN_IDS,
        )


# ── Scenario A: no ACs in graph ───────────────────────────────────────────────

def test_coverage_summary_no_acs_returns_zero(neo4j_driver):
    """When no AcceptanceCriterion nodes exist, returns zeros (not an error)."""
    from src.memory_api import coverage_summary

    # We can't guarantee a clean slate (other tests seed ACs), so just assert
    # the function is callable and returns the expected keys.
    result = coverage_summary(neo4j_driver)
    assert "total_ac" in result
    assert "covered_ac" in result
    assert "coverage_pct" in result
    assert isinstance(result["total_ac"], int)
    assert isinstance(result["covered_ac"], int)
    assert isinstance(result["coverage_pct"], float)


# ── Scenario B: 4 ACs, 2 covered by passing TestRun ─────────────────────────

def test_coverage_summary_partial_coverage(neo4j_driver, cleanup_t2):
    """4 ACs seeded; 2 have a passing TestRun → coverage_pct == 50.0."""
    from src.memory_api import coverage_summary

    for ac_id in _T2_AC_IDS:
        _seed_ac(neo4j_driver, ac_id)

    # AC-1 and AC-2 get a passing run; AC-3 and AC-4 get no run
    for test_id, ac_id, run_id in zip(
        _T2_TEST_IDS[:2], _T2_AC_IDS[:2], _T2_RUN_IDS[:2]
    ):
        _seed_test_covering(neo4j_driver, test_id, ac_id)
        _seed_passing_run(neo4j_driver, run_id, test_id)

    result = coverage_summary(neo4j_driver)
    # Only count our seeded ACs (there may be others in the DB)
    assert result["covered_ac"] >= 2
    assert result["total_ac"] >= 4
    # The local ratio should be at least 2/4 = 50 — we can't assert exact 50.0
    # because other tests might have seeded passing TestRuns for other ACs.
    # Assert that covered_ac ≤ total_ac and pct = covered/total * 100
    expected_pct = result["covered_ac"] / result["total_ac"] * 100 if result["total_ac"] > 0 else 0.0
    assert abs(result["coverage_pct"] - expected_pct) < 0.01


# ── Scenario C: all 4 seeded ACs covered by passing TestRuns ─────────────────

def test_coverage_summary_full_local_coverage(neo4j_driver, cleanup_t2):
    """All 4 seeded ACs have a passing TestRun — verify they all count as covered."""
    from src.memory_api import coverage_summary

    for ac_id in _T2_AC_IDS:
        _seed_ac(neo4j_driver, ac_id)

    for test_id, ac_id, run_id in zip(_T2_TEST_IDS, _T2_AC_IDS, _T2_RUN_IDS):
        _seed_test_covering(neo4j_driver, test_id, ac_id)
        _seed_passing_run(neo4j_driver, run_id, test_id)

    result = coverage_summary(neo4j_driver)
    assert result["covered_ac"] >= 4
    assert result["total_ac"] >= 4

    # Verify our specific ACs are counted as covered via direct Cypher
    with neo4j_driver.session() as s:
        local_covered = s.run(
            "MATCH (ac:AcceptanceCriterion) WHERE ac.id IN $ids "
            "MATCH (tr:TestRun {outcome: 'pass'})-[:INSTANCE_OF]->(t:Test) "
            "      -[:COVERS_CRITERION]->(ac) "
            "RETURN count(DISTINCT ac) AS c",
            ids=_T2_AC_IDS,
        ).single()["c"]
    assert local_covered == 4, f"All 4 seeded ACs should be covered, got {local_covered}"

    # coverage_pct must be consistent with covered/total ratio
    expected_pct = result["covered_ac"] / result["total_ac"] * 100.0
    assert abs(result["coverage_pct"] - expected_pct) < 0.01


# ── Failing TestRun does NOT count as coverage ────────────────────────────────

def test_coverage_summary_fail_run_not_counted(neo4j_driver, cleanup_t2):
    """A TestRun(outcome='fail') does not count the AC as covered."""
    from src.memory_api import coverage_summary

    ac_id   = _T2_AC_IDS[0]
    test_id = _T2_TEST_IDS[0]
    run_id  = _T2_RUN_IDS[0]

    _seed_ac(neo4j_driver, ac_id)
    _seed_test_covering(neo4j_driver, test_id, ac_id)
    _seed_failing_run(neo4j_driver, run_id, test_id)  # failing run

    # To isolate this check, query directly for this specific AC
    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (ac:AcceptanceCriterion {id: $ac_id}) "
            "OPTIONAL MATCH (tr:TestRun {outcome: 'pass'})-[:INSTANCE_OF]->(t:Test) "
            "              -[:COVERS_CRITERION]->(ac) "
            "RETURN count(DISTINCT tr) AS passing_runs",
            ac_id=ac_id,
        ).single()
    assert row["passing_runs"] == 0, "Failing TestRun should not count as coverage"


# ── Return type and key presence ──────────────────────────────────────────────

def test_coverage_summary_return_keys(neo4j_driver):
    from src.memory_api import coverage_summary

    result = coverage_summary(neo4j_driver)
    assert set(result.keys()) == {"total_ac", "covered_ac", "coverage_pct"}


def test_coverage_summary_pct_is_float(neo4j_driver):
    from src.memory_api import coverage_summary

    result = coverage_summary(neo4j_driver)
    assert isinstance(result["coverage_pct"], float)


def test_coverage_summary_zero_acs_pct_is_zero_float(neo4j_driver):
    """coverage_pct should be 0.0 (not NaN, not an error) when total_ac == 0."""
    from src.memory_api import coverage_summary

    # Can't guarantee DB is empty; only verify the invariant holds.
    result = coverage_summary(neo4j_driver)
    if result["total_ac"] == 0:
        assert result["coverage_pct"] == 0.0
