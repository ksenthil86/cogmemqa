"""
Phase 3 end-to-end smoke test — Execution & Security (B5 + B6).

Single gate test for Sprint v3. Uses stub llm_fn + stub run_fn for B5;
real Bandit for B6.

Pipeline:
  1. provision_schema (idempotent)
  2. Re-seed Meridian graph via B3 + B4 stubs (same as phase 2)
  3. B5: FunctionalTesterAgent.run() → TestRun + Failure nodes
  4. Assert TestRun count, Failure count, FAILURE_CLASSIFIED + FUNCTIONAL_RUN_COMPLETE
  5. B6: SecurityTesterAgent.run("fixtures/meridian_app") — real Bandit scan
  6. Assert SecurityFinding, AFFECTS edge, SECURITY_SCAN_COMPLETE
  7. Verify INSTANCE_OF chain: TestRun → Test → AcceptanceCriterion queryable
"""
from __future__ import annotations

from tests.test_e2e_phase2 import (
    _clean_all_meridian,
    _b4_stub_llm,
    _MERIDIAN_RAW,
    _MERIDIAN_SPEC_TEXT,
    _TEST_IDS,
    _AC_IDS,
)
from src.provisioner import provision_schema


# ── Phase 3 stub helpers ──────────────────────────────────────────────────────

def _make_b5_stub_run_fn():
    """Return a run_fn that passes the first 8 calls and fails the next 2 (402)."""
    call_count = [0]

    def stub_run_fn(spec: dict) -> dict:
        call_count[0] += 1
        if call_count[0] <= 8:
            return {"status_code": 200, "body": {"ok": True}, "error": None}
        return {"status_code": 402, "body": {"error": "INSUFFICIENT_FUNDS"}, "error": None}

    return stub_run_fn


# ── Cleanup helpers ───────────────────────────────────────────────────────────

def _clean_phase3_nodes(driver) -> None:
    """Delete Phase 3 execution/security nodes to ensure a clean starting state."""
    with driver.session() as s:
        # TestRun nodes linked to Meridian test ids
        s.run(
            "MATCH (tr:TestRun)-[:INSTANCE_OF]->(t:Test) WHERE t.id IN $ids DETACH DELETE tr",
            ids=_TEST_IDS,
        )
        # Failure nodes for Meridian tests
        s.run(
            "MATCH (f:Failure) WHERE f.id IN $ids DETACH DELETE f",
            ids=[f"{tid}-failure" for tid in _TEST_IDS],
        )
        # FAILURE_CLASSIFIED Judgments informed by Meridian tests
        s.run(
            "MATCH (j:Judgment {label: 'FAILURE_CLASSIFIED'})-[:INFORMED_BY]->(t) "
            "WHERE t.id IN $ids DETACH DELETE j",
            ids=_TEST_IDS,
        )
        # FUNCTIONAL_RUN_COMPLETE Judgments informed by Meridian tests
        s.run(
            "MATCH (j:Judgment {label: 'FUNCTIONAL_RUN_COMPLETE'})-[:INFORMED_BY]->(t) "
            "WHERE t.id IN $ids DETACH DELETE j",
            ids=_TEST_IDS,
        )
        # SecurityFinding Judgments (global — no per-test scoping)
        s.run("MATCH (j:Judgment {label: 'SECURITY_FINDING'}) DETACH DELETE j")
        s.run("MATCH (j:Judgment {label: 'SECURITY_SCAN_COMPLETE'}) DETACH DELETE j")
        # SecurityFinding nodes and their AFFECTS edges
        s.run("MATCH (sf:SecurityFinding) DETACH DELETE sf")


# ── The gate test ─────────────────────────────────────────────────────────────

def test_execution_and_security_e2e(neo4j_driver):
    # ── 1. Schema ─────────────────────────────────────────────────────────────
    provision_schema(neo4j_driver)

    # ── 0. Clean slate ────────────────────────────────────────────────────────
    _clean_phase3_nodes(neo4j_driver)
    _clean_all_meridian(neo4j_driver)

    # ── 2. B3: parse spec + seed graph ────────────────────────────────────────
    from src.agents.requirements_parser import RequirementsParserAgent

    b3 = RequirementsParserAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: _MERIDIAN_RAW,
    )
    b3.run(_MERIDIAN_SPEC_TEXT)

    # ── 3. B4: propose + ingest tests ────────────────────────────────────────
    from src.agents.test_case_generator import TestCaseGeneratorAgent

    b4 = TestCaseGeneratorAgent(
        driver=neo4j_driver,
        llm_fn=_b4_stub_llm,
    )
    generated_test_ids = b4.run(neo4j_driver)
    assert len(generated_test_ids) >= 10, (
        f"B4 should generate ≥10 tests, got {len(generated_test_ids)}"
    )

    # ── 4. B5: run functional tests ───────────────────────────────────────────
    from src.agents.functional_tester import FunctionalTesterAgent

    b5 = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_b5_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    test_run_ids = b5.run(neo4j_driver)

    # ── 5. Assert ≥10 TestRun nodes ──────────────────────────────────────────
    assert len(test_run_ids) >= 10, f"Expected ≥10 TestRun ids returned, got {len(test_run_ids)}"
    with neo4j_driver.session() as s:
        tr_count = s.run("MATCH (tr:TestRun) RETURN count(tr) AS c").single()["c"]
    assert tr_count >= 10, f"Expected ≥10 TestRun nodes in graph, got {tr_count}"

    # ── 6. Assert 2 Failure nodes with label="data_error" ────────────────────
    with neo4j_driver.session() as s:
        failure_count = s.run(
            "MATCH (f:Failure {label: 'data_error'}) RETURN count(f) AS c"
        ).single()["c"]
    assert failure_count == 2, f"Expected 2 Failure(label=data_error) nodes, got {failure_count}"

    # ── 7. Assert 2 FAILURE_CLASSIFIED Judgments for Meridian tests ──────────
    with neo4j_driver.session() as s:
        fc_count = s.run(
            "MATCH (j:Judgment {label: 'FAILURE_CLASSIFIED'})-[:INFORMED_BY]->(t:Test) "
            "WHERE t.id IN $ids RETURN count(DISTINCT j) AS c",
            ids=_TEST_IDS,
        ).single()["c"]
    assert fc_count == 2, f"Expected 2 FAILURE_CLASSIFIED Judgments for Meridian tests, got {fc_count}"

    # ── 8. Assert 1 FUNCTIONAL_RUN_COMPLETE Judgment for Meridian tests ──────
    with neo4j_driver.session() as s:
        frc_count = s.run(
            "MATCH (j:Judgment {label: 'FUNCTIONAL_RUN_COMPLETE'})-[:INFORMED_BY]->(t:Test) "
            "WHERE t.id IN $ids RETURN count(DISTINCT j) AS c",
            ids=_TEST_IDS,
        ).single()["c"]
    assert frc_count == 1, f"Expected 1 FUNCTIONAL_RUN_COMPLETE Judgment for Meridian tests, got {frc_count}"

    # ── 9. B6: security scan (real Bandit on meridian_app fixture) ────────────
    from src.agents.security_tester import SecurityTesterAgent

    b6 = SecurityTesterAgent(driver=neo4j_driver)
    finding_ids = b6.run(neo4j_driver, "fixtures/meridian_app")

    # ── 10. Assert ≥1 SecurityFinding node ───────────────────────────────────
    assert len(finding_ids) >= 1, f"Expected ≥1 SecurityFinding id returned, got {len(finding_ids)}"
    with neo4j_driver.session() as s:
        sf_count = s.run("MATCH (sf:SecurityFinding) RETURN count(sf) AS c").single()["c"]
    assert sf_count >= 1, f"Expected ≥1 SecurityFinding nodes in graph, got {sf_count}"

    # ── 11. Assert ≥1 AFFECTS edge ────────────────────────────────────────────
    with neo4j_driver.session() as s:
        affects_count = s.run(
            "MATCH (sf:SecurityFinding)-[:AFFECTS]->(c:Component) RETURN count(*) AS c"
        ).single()["c"]
    assert affects_count >= 1, f"Expected ≥1 AFFECTS edge (finding → Component), got {affects_count}"

    # ── 12. Assert 1 SECURITY_SCAN_COMPLETE Judgment ─────────────────────────
    with neo4j_driver.session() as s:
        ssc_count = s.run(
            "MATCH (j:Judgment {label: 'SECURITY_SCAN_COMPLETE'}) RETURN count(j) AS c"
        ).single()["c"]
    assert ssc_count == 1, f"Expected 1 SECURITY_SCAN_COMPLETE Judgment, got {ssc_count}"

    # ── 13. Verify INSTANCE_OF chain: TestRun → Test → AcceptanceCriterion ───
    with neo4j_driver.session() as s:
        chain_count = s.run(
            "MATCH (tr:TestRun)-[:INSTANCE_OF]->(t:Test)-[:COVERS_CRITERION]->(ac:AcceptanceCriterion) "
            "WHERE t.id IN $test_ids AND ac.id IN $ac_ids "
            "RETURN count(*) AS c",
            test_ids=_TEST_IDS,
            ac_ids=_AC_IDS,
        ).single()["c"]
    assert chain_count >= 10, (
        f"Expected ≥10 TestRun→Test→AC chains, got {chain_count}"
    )
