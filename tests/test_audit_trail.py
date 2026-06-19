"""
Integration tests for the deterministic audit-trail query (Task 9).
Requires live Neo4j — uses neo4j_driver fixture from conftest.py.

Full chain seeded for each test:

  Requirement -[REALIZED_BY]->   Functionality -[COMPOSED_OF]->  Component
  Component   -[IMPLEMENTED_BY]-> File         <-[MODIFIES]-     Commit
  Test        -[VERIFIES]->       Functionality
  Judgment    -[INFORMED_BY]->    Requirement
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.memory_api import (
    ingest_node, ingest_edge,
    write_provenance,
    audit_trail,
)
from src.models import (
    Requirement, Functionality, Component, File, Commit,
    Test as DomainTest,
    Judgment, ReasoningTrace,
    RealizedByEdge, ComposedOfEdge, ImplementedByEdge,
    ModifiesEdge, VerifiesEdge, InformedByEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


def _ns() -> str:
    return uuid.uuid4().hex[:8]


# ── Shared fixture: full 7-node audit chain ─────────────────────────────────────

@pytest.fixture()
def chain(neo4j_driver):
    """Seed a complete audit chain and return all node ids."""
    ns = _ns()
    req_id   = f"req-{ns}"
    func_id  = f"func-{ns}"
    comp_id  = f"comp-{ns}"
    file_id  = f"file-{ns}"
    test_id  = f"test-{ns}"
    j_id     = f"j-{ns}"
    cmt_id   = f"cmt-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id,  title="Account opening"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="User registration"))
    ingest_node(neo4j_driver, Component(id=comp_id,  name="RegistrationController"))
    ingest_node(neo4j_driver, File(id=file_id, path="src/registration.py"))
    ingest_node(neo4j_driver, DomainTest(id=test_id, name="test_register_success"))
    ingest_node(neo4j_driver, Judgment(id=j_id, agent_role="supervisor", label="PASS"))
    ingest_node(neo4j_driver, Commit(id=cmt_id, sha="abc123",
                                     message="feat: add registration", timestamp=NOW))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id,  to_id=func_id,  valid_from=NOW))
    ingest_edge(neo4j_driver, ComposedOfEdge(from_id=func_id, to_id=comp_id,  valid_from=NOW))
    ingest_edge(neo4j_driver, ImplementedByEdge(from_id=comp_id, to_id=file_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ModifiesEdge(from_id=cmt_id, to_id=file_id, valid_from=NOW))
    ingest_edge(neo4j_driver, VerifiesEdge(from_id=test_id, to_id=func_id, valid_from=NOW))
    ingest_edge(neo4j_driver, InformedByEdge(from_id=j_id, to_id=req_id, valid_from=NOW))

    return {
        "req_id": req_id, "func_id": func_id, "comp_id": comp_id,
        "file_id": file_id, "test_id": test_id, "j_id": j_id, "cmt_id": cmt_id,
    }


# ── Test 1: returns a list ────────────────────────────────────────────────────

def test_audit_trail_returns_list(neo4j_driver, chain):
    result = audit_trail(neo4j_driver, chain["req_id"])
    assert isinstance(result, list)


# ── Test 2: non-empty for a complete chain ─────────────────────────────────────

def test_audit_trail_non_empty_for_complete_chain(neo4j_driver, chain):
    result = audit_trail(neo4j_driver, chain["req_id"])
    assert len(result) >= 1, "audit_trail must return at least one row for a complete chain"


# ── Test 3: each row has the required keys ─────────────────────────────────────

def test_audit_trail_row_has_required_keys(neo4j_driver, chain):
    result = audit_trail(neo4j_driver, chain["req_id"])
    required = {"requirement", "functionality", "component", "file", "test", "judgment"}
    for row in result:
        assert required == set(row.keys()), (
            f"Row keys {set(row.keys())} do not match expected {required}"
        )


# ── Test 4: values match seeded node ids ──────────────────────────────────────

def test_audit_trail_row_values_match_seeded_ids(neo4j_driver, chain):
    result = audit_trail(neo4j_driver, chain["req_id"])
    assert len(result) == 1
    row = result[0]
    assert row["requirement"]   == chain["req_id"]
    assert row["functionality"] == chain["func_id"]
    assert row["component"]     == chain["comp_id"]
    assert row["file"]          == chain["file_id"]
    assert row["test"]          == chain["test_id"]
    assert row["judgment"]      == chain["j_id"]


# ── Test 5: missing requirement returns empty list ────────────────────────────

def test_audit_trail_unknown_requirement_returns_empty(neo4j_driver):
    result = audit_trail(neo4j_driver, "no-such-req-xyz")
    assert result == [], "audit_trail must return [] for an unknown requirement id"


# ── Test 6: incomplete chain returns empty list ───────────────────────────────

def test_audit_trail_incomplete_chain_returns_empty(neo4j_driver):
    """No INFORMED_BY edge → no complete path → empty result."""
    ns = _ns()
    req_id  = f"req-{ns}"
    func_id = f"func-{ns}"
    comp_id = f"comp-{ns}"
    file_id = f"file-{ns}"
    cmt_id  = f"cmt-{ns}"

    ingest_node(neo4j_driver, Requirement(id=req_id, title="Partial"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))
    ingest_node(neo4j_driver, Component(id=comp_id, name="C"))
    ingest_node(neo4j_driver, File(id=file_id, path="x.py"))
    ingest_node(neo4j_driver, Commit(id=cmt_id, sha="fff",
                                     message="chore", timestamp=NOW))

    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ComposedOfEdge(from_id=func_id, to_id=comp_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ImplementedByEdge(from_id=comp_id, to_id=file_id, valid_from=NOW))
    ingest_edge(neo4j_driver, ModifiesEdge(from_id=cmt_id, to_id=file_id, valid_from=NOW))
    # Missing: VERIFIES, Test node, Judgment, INFORMED_BY

    result = audit_trail(neo4j_driver, req_id)
    assert result == [], "Incomplete chain must return empty list"


# ── Test 7: multiple Judgment nodes produce multiple rows ─────────────────────

def test_audit_trail_two_judgments_produce_two_rows(neo4j_driver, chain):
    """A second Judgment INFORMED_BY the same Requirement adds a second row."""
    ns = _ns()
    j2_id = f"j2-{ns}"
    ingest_node(neo4j_driver, Judgment(id=j2_id, agent_role="functional_tester", label="FAIL"))
    ingest_edge(neo4j_driver, InformedByEdge(from_id=j2_id, to_id=chain["req_id"], valid_from=NOW))

    result = audit_trail(neo4j_driver, chain["req_id"])
    judgment_ids = {row["judgment"] for row in result}
    assert chain["j_id"] in judgment_ids, "First judgment must appear"
    assert j2_id         in judgment_ids, "Second judgment must appear"
