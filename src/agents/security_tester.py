"""
B6 — Security Tester Agent.

Runs a static security scan (Bandit by default) over the application source,
ingests each finding as a SecurityFinding node linked to the affected Component
via an AFFECTS edge, and writes provenance Judgments per finding and a summary
Judgment on completion.
"""
from __future__ import annotations

import json
import logging
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

from neo4j import Driver

from src.agent_base import BaseAgent
from src import memory_api
from src.llm import call_llm
import hashlib

from src.models import AffectsEdge, Judgment, ReasoningTrace, SecurityFinding

log = logging.getLogger(__name__)

# ── File → Component keyword map ──────────────────────────────────────────────

_FILE_KEYWORDS: dict[str, str] = {
    "account":     "comp-account-opening",
    "kyc":         "comp-kyc",
    "transfer":    "comp-money-transfer",
    "transaction": "comp-transaction-history",
    "fraud":       "comp-fraud-alerting",
}

# ── Default scan_fn (real Bandit runner) ──────────────────────────────────────

def _default_scan_fn(source_path: str) -> list[dict]:
    """
    Run Bandit over *source_path* and return the raw results list.

    Returns [] if Bandit is not installed or finds no issues.
    Each dict has at minimum: filename, issue_severity, issue_text, test_id.
    """
    try:
        proc = subprocess.run(  # nosec
            [sys.executable, "-m", "bandit", "-r", source_path, "-f", "json", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = proc.stdout or proc.stderr
        if not output.strip():
            return []
        data = json.loads(output)
        return data.get("results", [])
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        log.warning("_default_scan_fn: bandit scan failed — %s", exc)
        return []


# ── Agent ──────────────────────────────────────────────────────────────────────

class SecurityTesterAgent(BaseAgent):
    """
    B6 — Security Tester.

    Accepts an injectable scan_fn so the test suite can pass deterministic
    stub findings without running a real Bandit process.
    """

    def __init__(
        self,
        role: str = "security_tester",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
        scan_fn: Callable[[str], list[dict]] = _default_scan_fn,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)
        self.scan_fn = scan_fn

    def _map_file_to_component(self, filename: str) -> Optional[str]:
        """
        Return the Component slug for *filename* by keyword matching (case-insensitive).

        Returns None if no keyword matches.
        """
        lower = filename.lower()
        for keyword, comp_id in _FILE_KEYWORDS.items():
            if keyword in lower:
                return comp_id
        return None

    def ingest_findings(self, driver: Driver, findings: list[dict]) -> list[str]:
        """
        Ingest a list of Bandit result dicts into the graph.

        For each finding:
          - Creates SecurityFinding node with deterministic id "finding-{test_id}-{idx}".
          - Creates AFFECTS edge → Component if file keyword matches.
          - Writes Judgment(label="SECURITY_FINDING") + ReasoningTrace via write_provenance.

        Returns list of SecurityFinding node ids (same order as input).
        """
        finding_ids: list[str] = []
        now = datetime.now(timezone.utc)

        for idx, raw in enumerate(findings):
            bandit_test_id = raw.get("test_id", f"unknown-{idx}")
            issue_severity = raw.get("issue_severity", "LOW").lower()
            issue_text = raw.get("issue_text", "")
            filename = raw.get("filename", "")

            finding_id = f"finding-{bandit_test_id}-{idx}"

            memory_api.ingest_node(
                driver,
                SecurityFinding(
                    id=finding_id,
                    severity=issue_severity,
                    title=issue_text[:120],
                    status="open",
                ),
            )

            comp_id = self._map_file_to_component(filename)
            if comp_id:
                memory_api.ingest_edge(
                    driver,
                    AffectsEdge(from_id=finding_id, to_id=comp_id, valid_from=now),
                )

            judgment = Judgment(
                id=f"judgment-security-finding-{finding_id}",
                agent_role=self.role,
                label="SECURITY_FINDING",
            )
            trace = ReasoningTrace(
                id=f"trace-security-finding-{finding_id}",
                agent_role=self.role,
                decision=issue_text[:200],
                timestamp=now,
            )
            self.write_provenance(judgment, [trace], [finding_id])
            finding_ids.append(finding_id)

        return finding_ids

    def run(self, driver: Driver, source_path: str) -> list[str]:
        """
        Full B6 pipeline: scan → ingest → provenance summary.

        1. Calls scan_fn(source_path) → raw Bandit findings.
        2. Calls ingest_findings(driver, findings) → SecurityFinding node ids.
        3. Writes Judgment(label="SECURITY_SCAN_COMPLETE") + ReasoningTrace
           informed_by all finding ids.

        Returns the list of SecurityFinding node ids.
        """
        raw_findings = self.scan_fn(source_path)
        finding_ids = self.ingest_findings(driver, raw_findings)

        n = len(finding_ids)
        now = datetime.now(timezone.utc)
        path_hash = hashlib.sha256(source_path.encode()).hexdigest()[:10]
        judgment = Judgment(
            id=f"judgment-security-scan-complete-{path_hash}",
            agent_role=self.role,
            label="SECURITY_SCAN_COMPLETE",
        )
        trace = ReasoningTrace(
            id=f"trace-security-scan-complete-{path_hash}",
            agent_role=self.role,
            decision=f"Scanned {source_path}: {n} findings",
            timestamp=now,
        )
        self.write_provenance(judgment, [trace], finding_ids)

        return finding_ids
