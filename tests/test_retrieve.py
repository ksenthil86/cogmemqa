"""
Integration tests for the RETRIEVE operation (Task 6).
Requires live Neo4j — uses neo4j_driver fixture from conftest.py.

Chain seeded for each test:
  Requirement -[REALIZED_BY]-> Functionality -[COMPOSED_OF]-> Component
                                                               |
                                                    [IMPLEMENTED_BY]
                                                               |
                                                             File
  Test -[VERIFIES]-> Functionality
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.memory_api import ingest_node, ingest_edge, retrieve
from src.models import (
    Requirement, Functionality, Component, File,
    Test as DomainTest,
    RealizedByEdge, ComposedOfEdge, ImplementedByEdge, VerifiesEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


# ── Shared fixture: a seeded 4-layer chain with unique ids per test ────────────

@pytest.fixture()
def chain(neo4j_driver):
    """Seed a 5-node, 4-layer chain and return their ids."""
    ns = uuid.uuid4().hex[:8]
    req_id   = f"req-{ns}"
    func_id  = f"func-{ns}"
    comp_id  = f"comp-{ns}"
    file_id  = f"file-{ns}"
    test_id  = f"test-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id, title="Account opening"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="User registration"))
    ingest_node(neo4j_driver, Component(id=comp_id, name="RegistrationController"))
    ingest_node(neo4j_driver, File(id=file_id, path="src/registration.py"))
    ingest_node(neo4j_driver, DomainTest(id=test_id, name="test_register_success"))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id,  to_id=func_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ComposedOfEdge(from_id=func_id, to_id=comp_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ImplementedByEdge(from_id=comp_id, to_id=file_id, valid_from=NOW))
    ingest_edge(neo4j_driver, VerifiesEdge(from_id=test_id,  to_id=func_id, valid_from=NOW))

    return {
        "req_id": req_id, "func_id": func_id, "comp_id": comp_id,
        "file_id": file_id, "test_id": test_id,
    }


def _node_labels(result: dict) -> set[str]:
    """Return the set of Neo4j labels seen across all nodes in the result."""
    labels: set[str] = set()
    for node in result["nodes"]:
        labels.update(node.get("labels", []))
    return labels


def _node_ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"]}


# ── Test 1: return type ────────────────────────────────────────────────────────

def test_retrieve_returns_nodes_and_edges_keys(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "supervisor", chain["req_id"], depth=4)
    assert "nodes" in result
    assert "edges" in result
    assert isinstance(result["nodes"], list)
    assert isinstance(result["edges"], list)


# ── Test 2: supervisor gets all layers ────────────────────────────────────────

def test_supervisor_sees_all_layers(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "supervisor", chain["req_id"], depth=4)
    ids = _node_ids(result)
    for expected_id in chain.values():
        assert expected_id in ids, f"supervisor should see {expected_id}"


def test_supervisor_sees_requirement_label(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "supervisor", chain["req_id"], depth=4)
    labels = _node_labels(result)
    assert "Requirement" in labels


def test_supervisor_result_includes_edges(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "supervisor", chain["req_id"], depth=4)
    assert len(result["edges"]) > 0


# ── Test 3: functional_tester is scoped to capability+implementation+evidence ──

def test_functional_tester_excludes_requirement_label(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "functional_tester", chain["func_id"], depth=3)
    labels = _node_labels(result)
    assert "Requirement" not in labels, (
        "functional_tester must not receive Requirements layer nodes"
    )


def test_functional_tester_sees_capability_layer(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "functional_tester", chain["func_id"], depth=3)
    ids = _node_ids(result)
    assert chain["func_id"] in ids, "functional_tester should see Functionality nodes"
    assert chain["comp_id"] in ids, "functional_tester should see Component nodes"


def test_functional_tester_sees_implementation_layer(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "functional_tester", chain["func_id"], depth=3)
    ids = _node_ids(result)
    assert chain["file_id"] in ids, "functional_tester should see File nodes"


def test_functional_tester_sees_evidence_layer(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "functional_tester", chain["func_id"], depth=3)
    ids = _node_ids(result)
    assert chain["test_id"] in ids, "functional_tester should see Test nodes"


# ── Test 4: depth limits traversal ────────────────────────────────────────────

def test_depth_one_returns_direct_neighbours_only(neo4j_driver, chain):
    result = retrieve(neo4j_driver, "supervisor", chain["func_id"], depth=1)
    ids = _node_ids(result)
    # func is depth 0; req, comp, test are depth 1; file is depth 2 — should be excluded
    assert chain["file_id"] not in ids, "depth=1 must not reach File (2 hops away)"
    assert chain["func_id"] in ids   # the starting node itself


# ── Test 5: unknown role raises ValueError ─────────────────────────────────────

def test_unknown_role_raises(neo4j_driver, chain):
    with pytest.raises(ValueError, match="Unknown agent_role"):
        retrieve(neo4j_driver, "ghost_agent", chain["req_id"])


# ── Test 6: missing entity returns empty ──────────────────────────────────────

def test_missing_entity_returns_empty(neo4j_driver):
    result = retrieve(neo4j_driver, "supervisor", "no-such-id-xyz", depth=2)
    assert result == {"nodes": [], "edges": []}
