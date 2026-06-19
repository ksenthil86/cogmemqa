"""
Integration tests for memory_api.coverage_gaps() (Task 6).

Uses the shared neo4j_driver fixture — no live LLM.

coverage_gaps() scans ALL AcceptanceCriterion nodes in the graph, so tests
check by ID membership rather than exact count to stay isolated from data
seeded by other test modules.

Test-specific nodes are deleted before each test to prevent state leakage
from earlier runs (the neo4j_driver fixture is session-scoped).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src import memory_api
from src.models import AcceptanceCriterion, Test, CoversCriterionEdge


# ── Stable IDs used only by this module ──────────────────────────────────────

_AC_1 = "ac-cg-test-1"
_AC_2 = "ac-cg-test-2"
_TEST_1 = "test-cg-covers-1"
_TEST_2 = "test-cg-covers-2"

_ALL_IDS = [_AC_1, _AC_2, _TEST_1, _TEST_2]


# ── Cleanup fixture: remove test-specific nodes before every test ─────────────

@pytest.fixture(autouse=True)
def clean_test_nodes(neo4j_driver):
    """Delete the four test-specific nodes (and all their relationships) before
    each test so state from a previous run does not leak across tests."""
    with neo4j_driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=_ALL_IDS,
        )
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gap_ids(driver) -> set[str]:
    """Return the set of ac_id values from coverage_gaps()."""
    return {row["ac_id"] for row in memory_api.coverage_gaps(driver)}


def _seed_acs(driver) -> None:
    memory_api.ingest_node(driver, AcceptanceCriterion(id=_AC_1, statement="Gap test AC one."))
    memory_api.ingest_node(driver, AcceptanceCriterion(id=_AC_2, statement="Gap test AC two."))


def _cover(driver, test_id: str, ac_id: str) -> None:
    """Ingest a Test node and a COVERS_CRITERION edge to the given AC."""
    memory_api.ingest_node(driver, Test(id=test_id, name=f"Test {test_id}"))
    memory_api.ingest_edge(
        driver,
        CoversCriterionEdge(from_id=test_id, to_id=ac_id, valid_from=datetime.now(timezone.utc)),
    )


# ── Test: function is importable ──────────────────────────────────────────────

def test_coverage_gaps_importable():
    assert callable(memory_api.coverage_gaps)


# ── Test: seeded ACs with no tests appear in gaps ─────────────────────────────

def test_coverage_gaps_returns_uncovered_acs(neo4j_driver):
    _seed_acs(neo4j_driver)
    gaps = _gap_ids(neo4j_driver)
    assert _AC_1 in gaps, f"{_AC_1!r} should be in coverage_gaps() result"
    assert _AC_2 in gaps, f"{_AC_2!r} should be in coverage_gaps() result"


# ── Test: covering one AC removes it from gaps ────────────────────────────────

def test_coverage_gaps_covered_ac_removed(neo4j_driver):
    _seed_acs(neo4j_driver)
    _cover(neo4j_driver, _TEST_1, _AC_1)
    gaps = _gap_ids(neo4j_driver)
    assert _AC_1 not in gaps, f"{_AC_1!r} is covered — must not appear in coverage_gaps()"
    assert _AC_2 in gaps, f"{_AC_2!r} is still uncovered — must appear in coverage_gaps()"


# ── Test: covering both ACs removes both from gaps ────────────────────────────

def test_coverage_gaps_all_covered_removes_both(neo4j_driver):
    _seed_acs(neo4j_driver)
    _cover(neo4j_driver, _TEST_1, _AC_1)
    _cover(neo4j_driver, _TEST_2, _AC_2)
    gaps = _gap_ids(neo4j_driver)
    assert _AC_1 not in gaps
    assert _AC_2 not in gaps


# ── Test: result rows have required keys ──────────────────────────────────────

def test_coverage_gaps_row_has_required_keys(neo4j_driver):
    _seed_acs(neo4j_driver)
    rows = memory_api.coverage_gaps(neo4j_driver)
    our_rows = [r for r in rows if r["ac_id"] in (_AC_1, _AC_2)]
    assert len(our_rows) == 2, "Expected both test ACs in coverage_gaps() result"
    for row in our_rows:
        assert "ac_id" in row
        assert "statement" in row


# ── Test: returns a list (not a generator or None) ────────────────────────────

def test_coverage_gaps_returns_list(neo4j_driver):
    result = memory_api.coverage_gaps(neo4j_driver)
    assert isinstance(result, list)
