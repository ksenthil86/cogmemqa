"""
Phase 5 end-to-end smoke test — Build-Cycle Integration (B8).

Single gate test for Sprint v5. Uses stub llm_fn, stub run_fn for B5,
and stub scan_fn for B6. No live LLM or HTTP calls.

Pipeline:
  1. Clean Phase 5 + prior phase artefacts
  2. Re-seed Meridian graph via B3+B4 stubs
  3. Seed IMPLEMENTED_BY edges for 3 test file paths
  4. For each of 3 commits: CommitIngestionAgent.ingest_commit() + run_build_cycle()
  5. Assert 3 Commit nodes, 3 COMMIT_INGESTED Judgments, 3 distinct Reports
  6. Assert impact_lookup finds comp-account-opening for AccountController.java
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tests.test_e2e_phase2 import (
    _clean_all_meridian,
    _b4_stub_llm,
    _MERIDIAN_RAW,
    _MERIDIAN_SPEC_TEXT,
    _AC_IDS,
)
from tests.test_e2e_phase3 import _clean_phase3_nodes
from tests.test_e2e_phase4 import _clean_phase4_nodes
from src.provisioner import provision_schema

# ── Test fixture data ─────────────────────────────────────────────────────────

_TEST_SHAS = ["b800001", "b800002", "b800003"]

_TEST_COMMITS = [
    {
        "sha": "b800001",
        "message": "Add input validation for account registration fields",
        "author": "dev@meridian.io",
        "timestamp": "2026-01-15T09:00:00Z",
        "files": [{"path": "src/account/AccountController.java", "change_type": "modified"}],
    },
    {
        "sha": "b800002",
        "message": "Enhance KYC identity verification timeout handling",
        "author": "dev@meridian.io",
        "timestamp": "2026-01-16T10:30:00Z",
        "files": [{"path": "src/kyc/KycService.java", "change_type": "modified"}],
    },
    {
        "sha": "b800003",
        "message": "Fix transfer limit enforcement for cross-border payments",
        "author": "dev@meridian.io",
        "timestamp": "2026-01-17T14:00:00Z",
        "files": [{"path": "src/transfers/TransferEngine.java", "change_type": "modified"}],
    },
]

# (component_id, file_path) for IMPLEMENTED_BY seeding
_COMP_FILE_MAP = [
    ("comp-account-opening", "src/account/AccountController.java"),
    ("comp-kyc",             "src/kyc/KycService.java"),
    ("comp-money-transfer",  "src/transfers/TransferEngine.java"),
]

_TEST_FILE_IDS = [
    f"file-{path.replace('/', '-')}"
    for _, path in _COMP_FILE_MAP
]

_B6_STUB_FINDING = [
    {
        "filename":       "src/account/account_utils.py",
        "issue_severity": "LOW",
        "issue_text":     "Hardcoded password detected in account utilities",
        "test_id":        "B105",
    }
]


# ── Phase 5 cleanup ───────────────────────────────────────────────────────────

def _clean_phase5_nodes(driver) -> None:
    """
    Delete Phase 5 artefacts: test Commits, seeded Files, Reports,
    COMMIT_INGESTED Judgments, TestRun and SecurityFinding nodes,
    and stale non-Meridian AcceptanceCriteria from prior sessions.
    """
    with driver.session() as s:
        s.run(
            "MATCH (c:Commit) WHERE c.sha IN $shas DETACH DELETE c",
            shas=_TEST_SHAS,
        )
        s.run(
            "MATCH (f:File) WHERE f.id IN $ids DETACH DELETE f",
            ids=_TEST_FILE_IDS,
        )
        s.run("MATCH (r:Report) DETACH DELETE r")
        s.run("MATCH (j:Judgment {label: 'COMMIT_INGESTED'}) DETACH DELETE j")
        s.run(
            "MATCH (rt:ReasoningTrace) "
            "WHERE rt.id STARTS WITH 'trace-commit-' DETACH DELETE rt"
        )
        s.run("MATCH (tr:TestRun) DETACH DELETE tr")
        s.run("MATCH (sf:SecurityFinding) DETACH DELETE sf")
        s.run(
            "MATCH (ac:AcceptanceCriterion) WHERE NOT ac.id IN $meridian_ids "
            "DETACH DELETE ac",
            meridian_ids=_AC_IDS,
        )


# ── The gate test ─────────────────────────────────────────────────────────────

def test_build_cycle_replay_e2e(neo4j_driver):
    # ── 1. Schema ─────────────────────────────────────────────────────────────
    provision_schema(neo4j_driver)

    # ── 0. Clean slate (Phase 5 → 4 → 3 → 2 order) ───────────────────────────
    _clean_phase5_nodes(neo4j_driver)
    _clean_phase4_nodes(neo4j_driver)
    _clean_phase3_nodes(neo4j_driver)
    _clean_all_meridian(neo4j_driver)

    # ── 2. B3: parse spec + seed Meridian graph ────────────────────────────────
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

    # ── 4. Seed IMPLEMENTED_BY edges for 3 test file paths ────────────────────
    from src.memory_api import ingest_node, ingest_edge
    from src.models import File, ImplementedByEdge

    now = datetime.now(timezone.utc)
    for comp_id, file_path in _COMP_FILE_MAP:
        file_id = f"file-{file_path.replace('/', '-')}"
        ingest_node(neo4j_driver, File(id=file_id, path=file_path))
        ingest_edge(neo4j_driver, ImplementedByEdge(
            from_id=comp_id, to_id=file_id, valid_from=now,
        ))

    # ── 5. Instantiate stub agents ─────────────────────────────────────────────
    from src.agents.commit_ingestion import CommitIngestionAgent
    from src.agents.functional_tester import FunctionalTesterAgent
    from src.agents.security_tester import SecurityTesterAgent
    from src.agents.qa_supervisor import QASupervisorAgent
    from src.orchestrator import run_build_cycle

    b8 = CommitIngestionAgent(driver=neo4j_driver)
    b5 = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=lambda spec: {"status_code": 200, "body": {"ok": True}, "error": None},
        llm_fn=lambda p: "data_error",
    )
    b6 = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: _B6_STUB_FINDING,
    )
    b7 = QASupervisorAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: "Health OK",
    )

    # ── 6. Replay 3 commits ────────────────────────────────────────────────────
    report_ids: list[str] = []
    for commit_data in _TEST_COMMITS:
        b8.ingest_commit(neo4j_driver, commit_data)
        report_id = run_build_cycle(neo4j_driver, b5, b6, b7)
        report_ids.append(report_id)

    # ── 7. Assertions ──────────────────────────────────────────────────────────

    # 3 Commit nodes
    with neo4j_driver.session() as s:
        commit_count = s.run(
            "MATCH (c:Commit) WHERE c.sha IN $shas RETURN count(c) AS n",
            shas=_TEST_SHAS,
        ).single()["n"]
    assert commit_count == 3, f"Expected 3 Commit nodes, got {commit_count}"

    # 3 COMMIT_INGESTED Judgments
    with neo4j_driver.session() as s:
        j_count = s.run(
            "MATCH (j:Judgment {label: 'COMMIT_INGESTED'}) "
            "WHERE j.id STARTS WITH 'judgment-commit-commit-b8000' "
            "RETURN count(j) AS n"
        ).single()["n"]
    assert j_count == 3, f"Expected 3 COMMIT_INGESTED Judgments, got {j_count}"

    # 3 distinct Report nodes (one per build cycle)
    assert len(set(report_ids)) == 3, (
        f"Expected 3 distinct report IDs, got {report_ids}"
    )
    with neo4j_driver.session() as s:
        r_count = s.run(
            "MATCH (r:Report) WHERE r.id IN $ids RETURN count(r) AS n",
            ids=report_ids,
        ).single()["n"]
    assert r_count == 3, f"Expected 3 Report nodes, got {r_count}"

    # impact_lookup finds comp-account-opening for AccountController.java
    from src.memory_api import impact_lookup

    impacts = impact_lookup(neo4j_driver, ["src/account/AccountController.java"])
    assert len(impacts) >= 1, "impact_lookup returned no results for AccountController.java"
    comp_ids = {row["component_id"] for row in impacts}
    assert "comp-account-opening" in comp_ids, (
        f"Expected comp-account-opening in impact results, got {comp_ids}"
    )
