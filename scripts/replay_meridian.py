#!/usr/bin/env python3
"""
CoGMEM-QA — Meridian Build-Cycle Replay.

Standalone demo script. Seeds the Meridian graph from scratch and replays
five deterministic commits, printing a formatted build-cycle log per commit.

Usage:
    python scripts/replay_meridian.py            # full replay (requires Neo4j)
    python scripts/replay_meridian.py --dry-run  # validate fixtures, no Neo4j
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_COMMITS_FILE = ROOT / "fixtures" / "meridian_commits.json"

# Static component/functionality/requirement ids for each Meridian file path
_PATH_TO_IDS: dict[str, dict[str, str]] = {
    "src/account/AccountController.java": {
        "comp": "comp-account-opening",
        "func": "func-account-opening",
        "req":  "req-account-opening",
    },
    "src/kyc/KycService.java": {
        "comp": "comp-kyc",
        "func": "func-kyc",
        "req":  "req-kyc",
    },
    "src/transfers/TransferEngine.java": {
        "comp": "comp-money-transfer",
        "func": "func-money-transfer",
        "req":  "req-money-transfer",
    },
    "src/history/TransactionRepository.java": {
        "comp": "comp-transaction-history",
        "func": "func-transaction-history",
        "req":  "req-transaction-history",
    },
    "src/fraud/FraudDetector.java": {
        "comp": "comp-fraud-alerting",
        "func": "func-fraud-alerting",
        "req":  "req-fraud-alerting",
    },
}

_B6_STUB_FINDING = [
    {
        "filename":       "src/account/account_utils.py",
        "issue_severity": "LOW",
        "issue_text":     "Hardcoded password detected in account utilities",
        "test_id":        "B105",
    }
]


# ── Dry-run ────────────────────────────────────────────────────────────────────

def _dry_run() -> None:
    """Validate fixtures and exit 0 without touching Neo4j."""
    commits = json.loads(_COMMITS_FILE.read_text())
    if len(commits) != 5:
        print(f"ERROR: expected 5 commits, found {len(commits)}", file=sys.stderr)
        sys.exit(1)
    for c in commits:
        for key in ("sha", "message", "author", "timestamp", "files"):
            if key not in c:
                print(f"ERROR: commit {c.get('sha')!r} missing key {key!r}", file=sys.stderr)
                sys.exit(1)
    print(f"Dry run OK: {len(commits)} commits found in {_COMMITS_FILE.name}")


# ── Graph seeding ──────────────────────────────────────────────────────────────

def _seed_graph(driver) -> None:
    """Provision schema, clean stale replay data, seed B3+B4+IMPLEMENTED_BY."""
    from src.provisioner import provision_schema
    from src import memory_api
    from src.models import File, ImplementedByEdge
    from src.agents.requirements_parser import RequirementsParserAgent
    from src.agents.test_case_generator import TestCaseGeneratorAgent
    from tests.test_e2e_phase2 import (
        _MERIDIAN_RAW,
        _MERIDIAN_SPEC_TEXT,
        _b4_stub_llm,
        _clean_all_meridian,
    )

    provision_schema(driver)

    _clean_all_meridian(driver)
    with driver.session() as s:
        s.run("MATCH (r:Report) DETACH DELETE r")
        s.run("MATCH (sf:SecurityFinding) DETACH DELETE sf")
        s.run("MATCH (tr:TestRun) DETACH DELETE tr")
        s.run(
            "MATCH (c:Commit) WHERE c.sha STARTS WITH 'b8000' DETACH DELETE c"
        )
        s.run(
            "MATCH (j:Judgment) WHERE j.label IN $labels DETACH DELETE j",
            labels=["COMMIT_INGESTED", "HEALTH_REPORT_GENERATED",
                    "SECURITY_FINDING", "SECURITY_SCAN_COMPLETE",
                    "FUNCTIONAL_RUN_COMPLETE", "FAILURE_CLASSIFIED"],
        )

    b3 = RequirementsParserAgent(driver=driver, llm_fn=lambda p: _MERIDIAN_RAW)
    b3.run(_MERIDIAN_SPEC_TEXT)

    b4 = TestCaseGeneratorAgent(driver=driver, llm_fn=_b4_stub_llm)
    b4.run(driver)

    now = datetime.now(timezone.utc)
    for path, ids in _PATH_TO_IDS.items():
        file_id = f"file-{path.replace('/', '-')}"
        memory_api.ingest_node(driver, File(id=file_id, path=path))
        memory_api.ingest_edge(
            driver,
            ImplementedByEdge(from_id=ids["comp"], to_id=file_id, valid_from=now),
        )


# ── Replay loop ────────────────────────────────────────────────────────────────

def _replay(driver) -> None:
    """Replay all 5 fixture commits and print formatted build-cycle output."""
    from src.agents.commit_ingestion import CommitIngestionAgent
    from src.agents.functional_tester import FunctionalTesterAgent
    from src.agents.security_tester import SecurityTesterAgent
    from src.agents.qa_supervisor import QASupervisorAgent
    from src import memory_api

    commits = json.loads(_COMMITS_FILE.read_text())

    b8 = CommitIngestionAgent(driver=driver)
    b5 = FunctionalTesterAgent(
        driver=driver,
        run_fn=lambda spec: {"status_code": 200, "body": {"ok": True}, "error": None},
        llm_fn=lambda p: "data_error",
    )
    b6 = SecurityTesterAgent(
        driver=driver,
        scan_fn=lambda path: _B6_STUB_FINDING,
    )
    b7 = QASupervisorAgent(
        driver=driver,
        llm_fn=lambda p: (
            "All acceptance criteria covered; 1 open LOW security finding."
        ),
    )

    print()
    print("CoGMEM-QA Build-Cycle Replay — Meridian Banking App")
    print("=" * 52)

    for commit in commits:
        sha     = commit["sha"]
        message = commit["message"]
        paths   = [f["path"] for f in commit["files"]]

        commit_id = b8.ingest_commit(driver, commit)

        # Reset per-cycle evidence so B5/B6/B7 produce a fresh snapshot
        with driver.session() as s:
            s.run("MATCH (tr:TestRun) DETACH DELETE tr")
            s.run("MATCH (sf:SecurityFinding) DETACH DELETE sf")

        impacts = memory_api.impact_lookup(driver, paths)
        if impacts:
            row = impacts[0]
            impact_line = (
                f"{row['component_id']} → "
                f"{row['functionality_id']} → "
                f"{row['requirement_id']}"
            )
        else:
            impact_line = "(no mapping found)"

        run_ids     = b5.run(driver)
        b6.run(driver, "src")

        with driver.session() as s:
            sev_rows = s.run(
                "MATCH (sf:SecurityFinding {status: 'open'}) "
                "RETURN sf.severity AS sev, count(sf) AS cnt"
            ).data()
        sev_map: dict[str, int] = {}
        for r in sev_rows:
            sev_map[(r["sev"] or "unknown").upper()] = r["cnt"]

        report_id = b7.run(driver)

        with driver.session() as s:
            rrow = s.run(
                "MATCH (r:Report {id: $id}) "
                "RETURN r.coverage_pct AS cov, r.open_findings_count AS ofc",
                id=report_id,
            ).single()
        cov = rrow["cov"] if rrow else 0.0
        ofc = rrow["ofc"] if rrow else 0

        sev_display = ", ".join(
            f"{cnt} {sev}" for sev, cnt in sorted(sev_map.items()) if cnt > 0
        ) or "none"

        print()
        print(f"► Commit {sha}  \"{message}\"")
        for p in paths:
            print(f"  Changed:  {p}")
        print(f"  Impact:   {impact_line}")
        print(f"  B5:  {len(run_ids)} tests run, {len(run_ids)} pass")
        print(f"  B6:  {ofc} open finding(s) ({sev_display})")
        print(f"  B7:  {report_id}  coverage {cov:.1f}%  {ofc} open finding(s)")
        print(f"  ✓  COMMIT_INGESTED  ({commit_id})")

    print()
    print("=" * 52)
    print(
        f"{len(commits)}/{len(commits)} commits ingested. "
        "Run scripts/demo_summary.py to inspect graph."
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="CoGMEM-QA Meridian build-cycle replay")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixture data only; do not connect to Neo4j",
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run()
        return

    from src.db import get_driver
    driver = get_driver()
    try:
        _seed_graph(driver)
        _replay(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
