"""
BaseAgent — shared scaffold for all CoGMEM-QA agents.

Every agent subclass receives:
  - role: str — controls which graph layers are visible via RETRIEVE
  - driver: neo4j.Driver — the shared Neo4j connection
  - llm_fn: Callable[[str], str] — LLM backend (default: call_llm → Gemini)

The two convenience methods (retrieve, write_provenance) delegate directly to
the module-level memory API functions so agents never touch the driver directly.
"""
from __future__ import annotations

from typing import Callable, Optional

from neo4j import Driver

from src import memory_api
from src.llm import call_llm
from src.models import Judgment, ReasoningTrace


class BaseAgent:
    """Common scaffold for all CoGMEM-QA agents."""

    def __init__(
        self,
        role: str,
        driver: Optional[Driver],
        llm_fn: Callable[[str], str] = call_llm,
    ) -> None:
        self.role = role
        self.driver = driver
        self.llm_fn = llm_fn

    def retrieve(self, entity_id: str, depth: int = 2) -> dict:
        """Role-scoped subgraph retrieval centred on *entity_id*."""
        return memory_api.retrieve(self.driver, self.role, entity_id, depth)

    def write_provenance(
        self,
        judgment: Judgment,
        trace_steps: list[ReasoningTrace],
        informed_by_ids: list[str],
    ) -> str:
        """Write Judgment + ReasoningTrace nodes and return judgment id."""
        return memory_api.write_provenance(
            self.driver, judgment, trace_steps, informed_by_ids
        )
