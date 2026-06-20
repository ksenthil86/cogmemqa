"""
B8 — Commit Ingestion Agent.

On each commit, ingests Commit + File nodes and MODIFIES edges into the shared
Neo4j graph, then writes a COMMIT_INGESTED Judgment + ReasoningTrace for
auditability. No LLM or HTTP calls — graph writes only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from neo4j import Driver

from src.agent_base import BaseAgent
from src import memory_api
from src.llm import call_llm
from src.models import Commit, File, Judgment, ModifiesEdge, ReasoningTrace

log = logging.getLogger(__name__)


class CommitIngestionAgent(BaseAgent):
    """
    B8 — Commit Ingestion.

    Ingests commit metadata from a plain dict into the shared graph and writes
    a COMMIT_INGESTED Judgment so every downstream agent can trace changes back
    to their originating commit.
    """

    def __init__(
        self,
        role: str = "commit_ingestion",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)

    def ingest_commit(self, driver: Driver, commit_data: dict) -> str:
        """
        Ingest one commit from a dict into the shared graph.

        commit_data schema::

            {
              "sha":       str,
              "message":   str,
              "author":    str,
              "timestamp": str,   # ISO-8601, e.g. "2026-01-15T09:00:00Z"
              "files": [
                {"path": str, "change_type": str},
                ...
              ]
            }

        Creates:
          - Commit node
          - File node per files[] entry  (MERGE — idempotent)
          - Commit -[MODIFIES]-> File edge per files[] entry
          - Judgment(label="COMMIT_INGESTED") + ReasoningTrace via write_provenance

        Returns the commit_id string (``"commit-{sha}"``).
        """
        now = datetime.now(timezone.utc)
        sha = commit_data["sha"]
        commit_id = f"commit-{sha}"

        ts_raw = commit_data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = now

        memory_api.ingest_node(driver, Commit(
            id=commit_id,
            sha=sha,
            message=commit_data.get("message", ""),
            author=commit_data.get("author", "unknown"),
            timestamp=ts,
        ))

        file_ids: list[str] = []
        for file_entry in commit_data.get("files", []):
            path = file_entry["path"]
            file_id = f"file-{path.replace('/', '-')}"
            memory_api.ingest_node(driver, File(id=file_id, path=path))
            memory_api.ingest_edge(driver, ModifiesEdge(
                from_id=commit_id,
                to_id=file_id,
                valid_from=now,
            ))
            file_ids.append(file_id)

        judgment = Judgment(
            id=f"judgment-commit-{commit_id}",
            agent_role=self.role,
            label="COMMIT_INGESTED",
        )
        trace = ReasoningTrace(
            id=f"trace-commit-{commit_id}",
            agent_role=self.role,
            decision=f"Ingested commit {sha}: {commit_data.get('message', '')}",
            timestamp=now,
        )
        self.write_provenance(judgment, [trace], [commit_id])

        log.info("ingest_commit: %s (%d file(s))", commit_id, len(file_ids))
        return commit_id

    def run(self, driver: Driver, commit_data: dict) -> str:
        """Ingest a single commit. Returns the commit_id."""
        return self.ingest_commit(driver, commit_data)
