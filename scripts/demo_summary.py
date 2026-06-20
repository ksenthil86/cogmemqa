#!/usr/bin/env python3
"""
CoGMEM-QA — Graph Summary.

Read-only query script. Run after scripts/replay_meridian.py to display
the current state of the shared Neo4j graph: commit history, coverage,
open security findings, health reports, and a provenance chain for any
chosen requirement.

Usage:
    python scripts/demo_summary.py
    python scripts/demo_summary.py --req req-kyc
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_DEFAULT_REQ = "req-account-opening"


# ── Queries ────────────────────────────────────────────────────────────────────

def _commit_count(driver) -> int:
    with driver.session() as s:
        return s.run(
            "MATCH (c:Commit) WHERE c.sha STARTS WITH 'b8000' "
            "RETURN count(c) AS n"
        ).single()["n"]


def _report_count(driver) -> int:
    with driver.session() as s:
        return s.run("MATCH (r:Report) RETURN count(r) AS n").single()["n"]


def _judgment_summary(driver) -> dict[str, int]:
    with driver.session() as s:
        rows = s.run(
            "MATCH (j:Judgment) WHERE j.label IN $labels "
            "RETURN j.label AS label, count(j) AS cnt",
            labels=["COMMIT_INGESTED", "HEALTH_REPORT_GENERATED"],
        ).data()
    return {r["label"]: r["cnt"] for r in rows}


def _provenance_chain(driver, req_id: str) -> list[dict]:
    """
    Return the structural chain:
      Requirement → Functionality → Component → File ← Commit

    Uses OPTIONAL MATCH for the Commit so the chain is returned even when
    no commit has touched the file yet.
    """
    with driver.session() as s:
        rows = s.run(
            "MATCH (r:Requirement {id: $req_id}) "
            "-[:REALIZED_BY]->(func:Functionality) "
            "-[:COMPOSED_OF]->(comp:Component) "
            "-[:IMPLEMENTED_BY]->(f:File) "
            "OPTIONAL MATCH (c:Commit)-[:MODIFIES]->(f) "
            "RETURN r.id AS req, r.title AS req_title, "
            "       func.id AS func, comp.id AS comp, "
            "       f.path AS file, c.sha AS commit_sha "
            "LIMIT 3",
            req_id=req_id,
        ).data()
    return rows


# ── Display ────────────────────────────────────────────────────────────────────

def _print_summary(driver, req_id: str) -> None:
    from src import memory_api

    cov      = memory_api.coverage_summary(driver)
    sec      = memory_api.security_summary(driver)
    commits  = _commit_count(driver)
    reports  = _report_count(driver)
    j_counts = _judgment_summary(driver)
    chain    = _provenance_chain(driver, req_id)

    by_sev = sec["by_severity"]

    print()
    print("CoGMEM-QA — Graph Summary")
    print("=" * 42)
    print(f"Commits ingested:  {commits:>4}")
    print(
        f"Coverage:          {cov['coverage_pct']:>6.1f}%"
        f"  ({cov['covered_ac']}/{cov['total_ac']} ACs)"
    )
    print(
        f"Open findings:     {sec['total_open']:>4}"
        f"      (low: {by_sev['low']}, medium: {by_sev['medium']}, high: {by_sev['high']})"
    )
    print(f"Reports generated: {reports:>4}")

    ci  = j_counts.get("COMMIT_INGESTED", 0)
    hrg = j_counts.get("HEALTH_REPORT_GENERATED", 0)
    if ci or hrg:
        print(
            f"Judgments:         {ci} COMMIT_INGESTED, "
            f"{hrg} HEALTH_REPORT_GENERATED"
        )

    print()
    if chain:
        first = chain[0]
        title = first.get("req_title") or req_id
        print(f"Provenance chain for {req_id} ({title}):")
        print(
            f"  {first['req']} → {first['func']} → {first['comp']}"
        )
        file_part = f"→ {first['file']}"
        if first.get("commit_sha"):
            file_part += f" ← Commit {first['commit_sha']}"
        print(f"  {file_part}")
        if len(chain) > 1:
            for row in chain[1:]:
                extra = f"  → {row['file']}"
                if row.get("commit_sha"):
                    extra += f" ← Commit {row['commit_sha']}"
                print(extra)
    else:
        print(f"Provenance chain for {req_id}:")
        print("  (no chain found — run scripts/replay_meridian.py first)")

    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CoGMEM-QA graph summary — run after replay_meridian.py"
    )
    parser.add_argument(
        "--req",
        default=_DEFAULT_REQ,
        metavar="REQ_ID",
        help=f"requirement id for provenance chain (default: {_DEFAULT_REQ})",
    )
    args = parser.parse_args()

    from src.db import get_driver
    driver = get_driver()
    try:
        _print_summary(driver, args.req)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
