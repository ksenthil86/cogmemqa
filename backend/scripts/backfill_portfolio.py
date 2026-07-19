#!/usr/bin/env python3
"""
Backfill the portfolio layer: Project → Epics → every Requirement.

Idempotent — safe to run repeatedly against a live database. Creates the
Meridian project + four epics, attaches the five curated requirements to
their themed epics, then bulk-attaches every remaining parentless
Requirement to the catch-all "General Backlog" epic so no orphans remain.

Usage:
    python scripts/backfill_portfolio.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import memory_api
from app.models import Project, Epic, HasEpicEdge, HasRequirementEdge

PROJECT = Project(
    id="proj-meridian",
    name="Meridian Bank Digital Platform",
    description="Retail banking platform: onboarding, payments, and fraud controls",
)

EPICS: list[Epic] = [
    Epic(id="epic-customer-onboarding", name="Customer Onboarding",
         description="Account opening and KYC compliance"),
    Epic(id="epic-payments", name="Payments",
         description="Money transfer and transaction history"),
    Epic(id="epic-risk-fraud", name="Risk & Fraud",
         description="Fraud detection and alerting"),
    Epic(id="epic-backlog", name="General Backlog",
         description="Catch-all epic for unassigned requirements"),
]

CURATED: dict[str, str] = {  # requirement id → epic id
    "req-account-opening":     "epic-customer-onboarding",
    "req-kyc":                 "epic-customer-onboarding",
    "req-money-transfer":      "epic-payments",
    "req-transaction-history": "epic-payments",
    "req-fraud-alerting":      "epic-risk-fraud",
}

CATCH_ALL_EPIC = "epic-backlog"


def backfill_portfolio(driver) -> dict:
    """MERGE the portfolio hierarchy; returns {"attached": n, "orphans_remaining": n}."""
    now = datetime.now(timezone.utc)

    memory_api.ingest_node(driver, PROJECT)
    for epic in EPICS:
        memory_api.ingest_node(driver, epic)
        memory_api.ingest_edge(driver, HasEpicEdge(
            from_id=PROJECT.id, to_id=epic.id, valid_from=now,
        ))

    # Curated requirements go to their themed epics first, so the catch-all
    # query below never claims them.
    for req_id, epic_id in CURATED.items():
        memory_api.ingest_edge(driver, HasRequirementEdge(
            from_id=epic_id, to_id=req_id, valid_from=now,
        ))

    # Bulk catch-all: one Cypher MERGE (not per-node ingest calls — the live
    # DB has ~1550 loader-less requirements).
    with driver.session() as s:
        attached = s.run(
            "MATCH (e:Epic {id: $epic_id}) "
            "MATCH (r:Requirement) "
            "WHERE NOT (:Epic)-[:HAS_REQUIREMENT]->(r) "
            "MERGE (e)-[rel:HAS_REQUIREMENT]->(r) "
            "ON CREATE SET rel.valid_from = $now, rel.valid_to = null "
            "RETURN count(rel) AS attached",
            epic_id=CATCH_ALL_EPIC, now=now,
        ).single()["attached"]
        orphans = s.run(
            "MATCH (r:Requirement) WHERE NOT (:Epic)-[:HAS_REQUIREMENT]->(r) "
            "RETURN count(r) AS n"
        ).single()["n"]

    return {"attached": attached, "orphans_remaining": orphans}


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")  # repo-root .env
    from app.db import get_driver

    driver = get_driver()
    stats = backfill_portfolio(driver)
    print(f"Portfolio backfill complete: {stats}")


if __name__ == "__main__":
    main()
