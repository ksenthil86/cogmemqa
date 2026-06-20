"""
B7 — QA Supervisor Agent.

Aggregates live evidence from the shared graph (TestRun + SecurityFinding nodes
produced by B5 and B6) and produces a Report node capturing two health signals:
  - test-execution coverage % (ACs backed by a passing TestRun)
  - open security findings count + severity breakdown

No injectable run_fn or scan_fn — the supervisor uses only Cypher queries.
llm_fn is used to generate the human-readable summary line in the Report.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from neo4j import Driver

from src.agent_base import BaseAgent
from src import memory_api
from src.llm import call_llm
from src.models import Judgment, ReasoningTrace, Report

log = logging.getLogger(__name__)


class QASupervisorAgent(BaseAgent):
    """
    B7 — QA Supervisor.

    Reads TestRun and SecurityFinding nodes from the shared graph,
    computes health metrics via coverage_summary() and security_summary(),
    and ingests a Report node + Judgment(label="HEALTH_REPORT_GENERATED").
    """

    def __init__(
        self,
        role: str = "qa_supervisor",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)

    def compute_health(self, driver: Driver) -> dict:
        """
        Merge coverage_summary() and security_summary() into one health dict.

        Returns:
          {
            "coverage_pct":        float,
            "covered_ac":          int,
            "total_ac":            int,
            "open_findings_count": int,
            "by_severity":         {"low": int, "medium": int, "high": int},
          }
        """
        cov = memory_api.coverage_summary(driver)
        sec = memory_api.security_summary(driver)
        return {
            "coverage_pct":        cov["coverage_pct"],
            "covered_ac":          cov["covered_ac"],
            "total_ac":            cov["total_ac"],
            "open_findings_count": sec["total_open"],
            "by_severity":         sec["by_severity"],
        }

    def generate_report(self, driver: Driver) -> str:
        """
        Compute health metrics, ingest a Report node, write provenance.

        Returns the report_id.
        """
        metrics = self.compute_health(driver)
        now = datetime.now(timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        report_id = f"report-{hashlib.sha256(str(now_ms).encode()).hexdigest()[:10]}"

        summary_prompt = (
            f"One sentence: coverage {metrics['coverage_pct']:.1f}% "
            f"({metrics['covered_ac']}/{metrics['total_ac']} ACs), "
            f"{metrics['open_findings_count']} open security findings."
        )
        summary = self.llm_fn(summary_prompt)

        severity_breakdown = json.dumps(metrics["by_severity"])

        memory_api.ingest_node(
            driver,
            Report(
                id=report_id,
                summary=summary,
                created_at=now,
                coverage_pct=metrics["coverage_pct"],
                open_findings_count=metrics["open_findings_count"],
                severity_breakdown=severity_breakdown,
            ),
        )

        # Build informed_by list from passing TestRuns + open SecurityFindings
        with driver.session() as s:
            tr_ids = [
                r["id"] for r in s.run(
                    "MATCH (tr:TestRun {outcome: 'pass'}) RETURN tr.id AS id LIMIT 50"
                ).data()
            ]
            sf_ids = [
                r["id"] for r in s.run(
                    "MATCH (sf:SecurityFinding {status: 'open'}) RETURN sf.id AS id LIMIT 50"
                ).data()
            ]

        informed_by = tr_ids + sf_ids if (tr_ids or sf_ids) else ["report-summary"]

        judgment = Judgment(
            id=f"judgment-health-report-{report_id}",
            agent_role=self.role,
            label="HEALTH_REPORT_GENERATED",
        )
        trace = ReasoningTrace(
            id=f"trace-health-report-{report_id}",
            agent_role=self.role,
            decision=summary,
            timestamp=now,
        )
        self.write_provenance(judgment, [trace], informed_by)

        log.info(
            "generate_report: %s — coverage %.1f%%, %d open findings",
            report_id,
            metrics["coverage_pct"],
            metrics["open_findings_count"],
        )
        return report_id

    def run(self, driver: Driver) -> str:
        """
        Full B7 pipeline: compute health → ingest Report → write provenance.

        Each call produces a new Report snapshot (not idempotent by design).
        Returns the report_id.
        """
        return self.generate_report(driver)
