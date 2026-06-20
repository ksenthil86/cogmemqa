"""
Phase 4 end-to-end smoke test — QA Supervisor (B7).

Single gate test for Sprint v4. Uses stub llm_fn, stub run_fn for B5,
and stub scan_fn for B6 (1 open LOW finding).

Pipeline:
  1. provision_schema (idempotent)
  2. Re-seed Meridian graph via B3 + B4 stubs (same helpers as phase 2/3)
  3. B5: all 10 calls return 200 (all pass) → coverage_pct will be 100.0
  4. B6: stub scan_fn returns 1 open LOW finding → open_findings_count == 1
  5. B7: QASupervisorAgent.run() → Report node + HEALTH_REPORT_GENERATED Judgment
  6. Assert Report.coverage_pct == 100.0
  7. Assert Report.open_findings_count == 1
  8. Assert severity_breakdown["low"] == 1
  9. Assert Judgment(label="HEALTH_REPORT_GENERATED") exists
"""
from __future__ import annotations

import json

from tests.test_e2e_phase2 import (
    _clean_all_meridian,
    _b4_stub_llm,
    _MERIDIAN_RAW,
    _MERIDIAN_SPEC_TEXT,
    _TEST_IDS,
    _AC_IDS,
)
from tests.test_e2e_phase3 import _clean_phase3_nodes
from src.provisioner import provision_schema


# ── Phase 4 cleanup ───────────────────────────────────────────────────────────

def _clean_phase4_nodes(driver) -> None:
    """
    Delete Phase 4 Report nodes, HEALTH_REPORT_GENERATED Judgments,
    and any AcceptanceCriterion nodes left by unit-test fixtures from prior
    sessions (ensures coverage_pct == 100.0 only reflects Meridian ACs).
    """
    with driver.session() as s:
        s.run("MATCH (r:Report) DETACH DELETE r")
        s.run("MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'}) DETACH DELETE j")
        s.run(
            "MATCH (rt:ReasoningTrace) "
            "WHERE rt.id STARTS WITH 'trace-health-report-' DETACH DELETE rt"
        )
        # Remove stale ACs not in the Meridian set (left by unit-test fixtures
        # from previous sessions that ran without cleanup).
        s.run(
            "MATCH (ac:AcceptanceCriterion) WHERE NOT ac.id IN $meridian_ids "
            "DETACH DELETE ac",
            meridian_ids=_AC_IDS,
        )


# ── B6 stub finding ───────────────────────────────────────────────────────────

_B6_STUB_FINDINGS = [
    {
        "filename": "src/account/account_stub.py",
        "issue_severity": "LOW",
        "issue_text": "Hardcoded password in account stub",
        "test_id": "B105",
    }
]


# ── The gate test ─────────────────────────────────────────────────────────────

def test_health_report_e2e(neo4j_driver):
    # ── 1. Schema ─────────────────────────────────────────────────────────────
    provision_schema(neo4j_driver)

    # ── 0. Clean slate (Phase 4 → Phase 3 → Phase 2 order) ───────────────────
    _clean_phase4_nodes(neo4j_driver)
    _clean_phase3_nodes(neo4j_driver)
    _clean_all_meridian(neo4j_driver)

    # ── 2. B3: parse spec + seed graph ────────────────────────────────────────
    from src.agents.requirements_parser import RequirementsParserAgent

    b3 = RequirementsParserAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: _MERIDIAN_RAW,
    )
    b3.run(_MERIDIAN_SPEC_TEXT)

    # ── 3. B4: propose + ingest tests ─────────────────────────────────────────
    from src.agents.test_case_generator import TestCaseGeneratorAgent

    b4 = TestCaseGeneratorAgent(driver=neo4j_driver, llm_fn=_b4_stub_llm)
    generated_ids = b4.run(neo4j_driver)
    assert len(generated_ids) >= 10, f"B4 should generate ≥10 tests, got {len(generated_ids)}"

    # ── 4. B5: all 10 tests pass ──────────────────────────────────────────────
    from src.agents.functional_tester import FunctionalTesterAgent

    b5 = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=lambda spec: {"status_code": 200, "body": {"ok": True}, "error": None},
        llm_fn=lambda p: "data_error",
    )
    test_run_ids = b5.run(neo4j_driver)
    assert len(test_run_ids) >= 10, f"B5 should produce ≥10 TestRun ids, got {len(test_run_ids)}"

    # Verify all Meridian ACs have a passing TestRun (precondition for 100% coverage)
    with neo4j_driver.session() as s:
        covered = s.run(
            "MATCH (ac:AcceptanceCriterion) WHERE ac.id IN $ids "
            "MATCH (tr:TestRun {outcome: 'pass'})-[:INSTANCE_OF]->(t:Test) "
            "      -[:COVERS_CRITERION]->(ac) "
            "RETURN count(DISTINCT ac) AS c",
            ids=_AC_IDS,
        ).single()["c"]
    assert covered == 10, f"All 10 Meridian ACs should be covered after B5 all-pass, got {covered}"

    # ── 5. B6: stub scan — 1 open LOW finding ─────────────────────────────────
    from src.agents.security_tester import SecurityTesterAgent

    b6 = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: _B6_STUB_FINDINGS,
    )
    finding_ids = b6.run(neo4j_driver, "src/account")
    assert len(finding_ids) == 1, f"Expected 1 SecurityFinding, got {len(finding_ids)}"

    # ── 6. B7: generate health report ─────────────────────────────────────────
    from src.agents.qa_supervisor import QASupervisorAgent

    b7 = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    report_id = b7.run(neo4j_driver)

    # ── 7. Assertions ─────────────────────────────────────────────────────────
    assert isinstance(report_id, str) and len(report_id) > 0, "run() must return a non-empty string"

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (r:Report {id: $id}) "
            "RETURN r.coverage_pct AS cov, r.open_findings_count AS ofc, "
            "       r.severity_breakdown AS sb",
            id=report_id,
        ).single()

    assert row is not None, f"Report node {report_id!r} not found in graph"
    assert row["cov"] == 100.0, f"Expected coverage_pct == 100.0, got {row['cov']}"
    assert row["ofc"] == 1, f"Expected open_findings_count == 1, got {row['ofc']}"

    sb = json.loads(row["sb"])
    assert sb["low"] == 1, f"Expected severity_breakdown['low'] == 1, got {sb}"

    with neo4j_driver.session() as s:
        j_cnt = s.run(
            "MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'}) RETURN count(j) AS c"
        ).single()["c"]
    assert j_cnt >= 1, f"Expected ≥1 HEALTH_REPORT_GENERATED Judgment, got {j_cnt}"
