"""
Phase 2 end-to-end smoke test — Bootstrap & Test Design (B3 + B4).

Single gate test for Sprint v2. Uses stub llm_fn throughout — no live LLM.

Pipeline:
  1. provision_schema (idempotent)
  2. B3: RequirementsParserAgent.run() → seeds Meridian graph
  3. Assert Requirement + Functionality + AC nodes
  4. Assert coverage_gaps contains all Meridian ACs
  5. Seed File + Commit to complete audit chain
  6. B4: TestCaseGeneratorAgent.run() → proposes + ingests tests
  7. Assert Test nodes exist with COVERS_CRITERION edges
  8. Assert coverage_gaps returns [] for all Meridian ACs
  9. audit_trail returns non-empty
 10. Assert Judgment with label="TEST_PROPOSED" exists
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.memory_api import coverage_gaps, audit_trail, ingest_node, ingest_edge
from src.models import File, Commit, ImplementedByEdge, ModifiesEdge
from src.provisioner import provision_schema

# ── Meridian fixture data ─────────────────────────────────────────────────────

_MERIDIAN_JSON = Path(__file__).parent.parent / "fixtures" / "meridian_parsed.json"
_MERIDIAN_SPEC = Path(__file__).parent.parent / "fixtures" / "meridian_spec.md"

_MERIDIAN_RAW = _MERIDIAN_JSON.read_text()
_MERIDIAN_SPEC_TEXT = _MERIDIAN_SPEC.read_text()

_REQ_IDS = [
    "req-account-opening", "req-kyc", "req-money-transfer",
    "req-transaction-history", "req-fraud-alerting",
]
_AC_IDS = [
    "ac-ao-1", "ac-ao-2",
    "ac-kyc-1", "ac-kyc-2",
    "ac-mt-1", "ac-mt-2",
    "ac-th-1", "ac-th-2",
    "ac-fa-1", "ac-fa-2",
]
_FUNC_IDS = [
    "func-account-opening", "func-kyc", "func-money-transfer",
    "func-transaction-history", "func-fraud-alerting",
]
_COMP_IDS = [
    "comp-account-opening", "comp-kyc", "comp-money-transfer",
    "comp-transaction-history", "comp-fraud-alerting",
]
_TEST_IDS = [f"{ac}-test" for ac in _AC_IDS]

# AC id → functionality id (for B4 stub to return correct VERIFIES target)
_AC_TO_FUNC = {
    "ac-ao-1": "func-account-opening",  "ac-ao-2": "func-account-opening",
    "ac-kyc-1": "func-kyc",             "ac-kyc-2": "func-kyc",
    "ac-mt-1": "func-money-transfer",   "ac-mt-2": "func-money-transfer",
    "ac-th-1": "func-transaction-history", "ac-th-2": "func-transaction-history",
    "ac-fa-1": "func-fraud-alerting",   "ac-fa-2": "func-fraud-alerting",
}

# Extra nodes seeded by the e2e test for the audit chain
_E2E_FILE_ID   = "file-e2e-account-controller"
_E2E_COMMIT_ID = "commit-e2e-initial"


# ── Cleanup helper ────────────────────────────────────────────────────────────

def _clean_all_meridian(driver) -> None:
    """Delete all Meridian nodes and their relationships for clean e2e state."""
    all_ids = (
        _REQ_IDS + _AC_IDS + _FUNC_IDS + _COMP_IDS + _TEST_IDS
        + ["actor-customer", "actor-compliance", _E2E_FILE_ID, _E2E_COMMIT_ID]
    )
    with driver.session() as session:
        # Remove Judgment nodes that are INFORMED_BY any Meridian Req or AC
        session.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(n) "
            "WHERE n.id IN $ids DETACH DELETE j",
            ids=_REQ_IDS + _AC_IDS,
        )
        # Remove ReasoningTrace nodes linked to those (now-deleted) Judgments
        # (cascaded via DETACH DELETE above)

        # Remove the main Meridian domain nodes
        session.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=all_ids,
        )


# ── B4 stub LLM ──────────────────────────────────────────────────────────────

def _b4_stub_llm(prompt: str) -> str:
    """Return a valid ProposedTest JSON for whichever AC id appears in the prompt."""
    m = re.search(r"Acceptance Criterion ID\s*:\s*(\S+)", prompt)
    ac_id = m.group(1) if m else _AC_IDS[0]
    func_id = _AC_TO_FUNC.get(ac_id, "func-account-opening")
    return json.dumps({
        "ac_id": ac_id,
        "name": f"test_{ac_id.replace('-', '_')}",
        "type": "api",
        "verifies_functionality_id": func_id,
        "description": f"Verifies {ac_id}.",
    })


# ── The gate test ─────────────────────────────────────────────────────────────

def test_bootstrap_and_test_design_e2e(neo4j_driver):
    # ── 1. Schema ─────────────────────────────────────────────────────────────
    provision_schema(neo4j_driver)

    # ── 0. Clean slate for Meridian data ──────────────────────────────────────
    _clean_all_meridian(neo4j_driver)

    # ── 2. B3: parse spec + seed graph ────────────────────────────────────────
    from src.agents.requirements_parser import RequirementsParserAgent

    b3 = RequirementsParserAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: _MERIDIAN_RAW,
    )
    b3_judgment_id = b3.run(_MERIDIAN_SPEC_TEXT)
    assert isinstance(b3_judgment_id, str) and b3_judgment_id

    # ── 3. Assert Req + Func + AC node counts ─────────────────────────────────
    def _count(label, ids):
        with neo4j_driver.session() as s:
            return s.run(
                f"MATCH (n:{label}) WHERE n.id IN $ids RETURN count(n) AS c",
                ids=ids,
            ).single()["c"]

    assert _count("Requirement", _REQ_IDS) == 5,  "Expected 5 Requirement nodes"
    assert _count("Functionality", _FUNC_IDS) == 5, "Expected 5 Functionality nodes"
    assert _count("AcceptanceCriterion", _AC_IDS) == 10, "Expected 10 AC nodes"

    # ── 4. Assert all Meridian ACs appear in coverage_gaps ───────────────────
    gap_ids = {r["ac_id"] for r in coverage_gaps(neo4j_driver)}
    for ac in _AC_IDS:
        assert ac in gap_ids, f"AC {ac!r} should be in coverage_gaps before B4 runs"

    # ── 5. Seed File + Commit so audit_trail can return non-empty ─────────────
    now = datetime.now(timezone.utc)
    ingest_node(neo4j_driver, File(
        id=_E2E_FILE_ID,
        path="src/account/AccountController.java",
        language="java",
    ))
    ingest_node(neo4j_driver, Commit(
        id=_E2E_COMMIT_ID,
        sha="abc123e2e",
        message="Initial account controller",
        timestamp=now,
    ))
    ingest_edge(neo4j_driver, ImplementedByEdge(
        from_id="comp-account-opening",
        to_id=_E2E_FILE_ID,
        valid_from=now,
    ))
    ingest_edge(neo4j_driver, ModifiesEdge(
        from_id=_E2E_COMMIT_ID,
        to_id=_E2E_FILE_ID,
        valid_from=now,
    ))

    # ── 6. B4: propose + ingest tests ────────────────────────────────────────
    from src.agents.test_case_generator import TestCaseGeneratorAgent

    b4 = TestCaseGeneratorAgent(
        driver=neo4j_driver,
        llm_fn=_b4_stub_llm,
    )
    test_ids = b4.run(neo4j_driver)
    assert isinstance(test_ids, list) and len(test_ids) >= 10, (
        f"Expected at least 10 test ids, got {len(test_ids)}"
    )

    # ── 7. Assert Test nodes exist with COVERS_CRITERION edges ───────────────
    assert _count("Test", _TEST_IDS) == 10, "Expected 10 Test nodes"
    with neo4j_driver.session() as s:
        edge_cnt = s.run(
            "MATCH (t:Test)-[:COVERS_CRITERION]->(ac:AcceptanceCriterion) "
            "WHERE t.id IN $tids AND ac.id IN $acids RETURN count(*) AS c",
            tids=_TEST_IDS, acids=_AC_IDS,
        ).single()["c"]
    assert edge_cnt == 10, f"Expected 10 COVERS_CRITERION edges, got {edge_cnt}"

    # ── 8. Assert no Meridian ACs remain in coverage_gaps ───────────────────
    gap_ids_after = {r["ac_id"] for r in coverage_gaps(neo4j_driver)}
    for ac in _AC_IDS:
        assert ac not in gap_ids_after, f"AC {ac!r} should be covered after B4 runs"

    # ── 9. audit_trail non-empty ──────────────────────────────────────────────
    trail = audit_trail(neo4j_driver, "req-account-opening")
    assert len(trail) > 0, (
        "audit_trail should be non-empty after B3+B4 with File+Commit seeded"
    )

    # ── 10. Judgment with label TEST_PROPOSED exists ─────────────────────────
    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'TEST_PROPOSED'}) RETURN count(j) AS c"
        ).single()["c"]
    assert cnt >= 10, f"Expected at least 10 TEST_PROPOSED Judgments, got {cnt}"
