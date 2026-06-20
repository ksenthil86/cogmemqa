"""
Tests for impact_lookup() — Sprint v5 Task 3.

Seeds an isolated Requirement → Functionality → Component → File chain
so tests are independent of the Meridian graph state.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

NOW = datetime.now(timezone.utc)

# ── Seed IDs ──────────────────────────────────────────────────────────────────

_T3_FILE_PATH_A  = "src/t3/ImpactTestA.java"
_T3_FILE_PATH_B  = "src/t3/ImpactTestB.java"
_T3_UNKNOWN_PATH = "src/unknown/NoMapping.java"

_T3_IDS_A = {
    "req":  "req-t3-001",
    "func": "func-t3-001",
    "comp": "comp-t3-001",
    "file": "file-t3-ImpactTestA",
}
_T3_IDS_B = {
    "req":  "req-t3-002",
    "func": "func-t3-002",
    "comp": "comp-t3-002",
    "file": "file-t3-ImpactTestB",
}

_ALL_T3_NODE_IDS = list(_T3_IDS_A.values()) + list(_T3_IDS_B.values())


@pytest.fixture()
def seed_t3_chain(neo4j_driver):
    """Seed two independent Requirement→Functionality→Component→File chains."""
    from src.memory_api import ingest_node, ingest_edge
    from src.models import (
        Requirement, Functionality, Component, File,
        RealizedByEdge, ComposedOfEdge, ImplementedByEdge,
    )

    for ids, path, suffix in (
        (_T3_IDS_A, _T3_FILE_PATH_A, "A"),
        (_T3_IDS_B, _T3_FILE_PATH_B, "B"),
    ):
        ingest_node(neo4j_driver, Requirement(id=ids["req"], title=f"T3 Req {suffix}"))
        ingest_node(neo4j_driver, Functionality(id=ids["func"], name=f"T3 Func {suffix}"))
        ingest_node(neo4j_driver, Component(id=ids["comp"], name=f"T3 Comp {suffix}"))
        ingest_node(neo4j_driver, File(id=ids["file"], path=path))
        ingest_edge(neo4j_driver, RealizedByEdge(from_id=ids["req"], to_id=ids["func"], valid_from=NOW))
        ingest_edge(neo4j_driver, ComposedOfEdge(from_id=ids["func"], to_id=ids["comp"], valid_from=NOW))
        ingest_edge(neo4j_driver, ImplementedByEdge(from_id=ids["comp"], to_id=ids["file"], valid_from=NOW))

    yield

    with neo4j_driver.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=_ALL_T3_NODE_IDS)


# ══════════════════════════════════════════════════════════════════════════════
# impact_lookup() tests
# ══════════════════════════════════════════════════════════════════════════════

def test_impact_lookup_returns_list(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_UNKNOWN_PATH])
    assert isinstance(result, list)


def test_impact_lookup_empty_for_unknown_file(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_UNKNOWN_PATH])
    assert result == []


def test_impact_lookup_finds_component(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_FILE_PATH_A])
    assert len(result) == 1
    assert result[0]["component_id"] == _T3_IDS_A["comp"]


def test_impact_lookup_finds_requirement(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_FILE_PATH_A])
    assert len(result) == 1
    assert result[0]["requirement_id"] == _T3_IDS_A["req"]
    assert result[0]["functionality_id"] == _T3_IDS_A["func"]


def test_impact_lookup_multiple_paths_returns_one_row_each(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_FILE_PATH_A, _T3_FILE_PATH_B])
    comp_ids = {r["component_id"] for r in result}
    assert _T3_IDS_A["comp"] in comp_ids
    assert _T3_IDS_B["comp"] in comp_ids


def test_impact_lookup_known_and_unknown_path(neo4j_driver, seed_t3_chain):
    """Only matched paths appear in the result; unknown paths are silently skipped."""
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_FILE_PATH_A, _T3_UNKNOWN_PATH])
    assert len(result) == 1
    assert result[0]["component_id"] == _T3_IDS_A["comp"]


def test_impact_lookup_result_has_all_four_keys(neo4j_driver, seed_t3_chain):
    from src.memory_api import impact_lookup
    result = impact_lookup(neo4j_driver, [_T3_FILE_PATH_A])
    assert len(result) == 1
    row = result[0]
    assert "file_path" in row
    assert "component_id" in row
    assert "functionality_id" in row
    assert "requirement_id" in row
