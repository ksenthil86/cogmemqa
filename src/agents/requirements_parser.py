"""
B3 — Requirements Parser Agent.

Reads a product spec document and populates the graph's requirements +
capability layers via the shared memory API.
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable, Optional

from datetime import datetime, timezone

from neo4j import Driver

from src.agent_base import BaseAgent
from src.agents.models import ParsedSpec
from src import memory_api
from src.llm import call_llm
from src.models import (
    Requirement,
    AcceptanceCriterion,
    Actor,
    Functionality,
    Component,
    Judgment,
    ReasoningTrace,
    RealizedByEdge,
    ComposedOfEdge,
)

_PARSE_SPEC_PROMPT = """\
You are a requirements analyst.  Read the product specification below and extract
its contents into a JSON object that exactly matches this schema:

{{
  "actors": [
    {{"id": "<kebab-slug>", "name": "<display name>", "role": "<role_slug>"}}
  ],
  "requirements": [
    {{
      "id": "<req-kebab-slug>",
      "title": "<title>",
      "priority": "P0|P1|P2",
      "reg_control": "<regulation string or null>",
      "acceptance_criteria": [
        {{"id": "<ac-slug>", "statement": "<full statement>", "actor_role": "<role or null>"}}
      ],
      "functionality_id": "<func-kebab-slug>",
      "functionality_name": "<display name>",
      "component_id": "<comp-kebab-slug>",
      "component_name": "<display name>"
    }}
  ]
}}

Rules:
- Use deterministic kebab-case slugs for all IDs (e.g. "req-account-opening").
- Include exactly one Functionality and one Component per Requirement.
- Include ALL acceptance criteria listed in the spec.
- Return ONLY the JSON object — no markdown fences, no explanation text.

Product Specification:
---
{spec_text}
---

JSON:"""


def _strip_fences(text: str) -> str:
    """Remove leading ```[lang] and trailing ``` markers from LLM output."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class RequirementsParserAgent(BaseAgent):
    """
    B3 — Requirements Parser.

    Parses a product spec document into a `ParsedSpec` and seeds the graph's
    requirements + capability layers.
    """

    def __init__(
        self,
        role: str = "requirements_parser",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)

    def parse_spec(self, spec_text: str) -> ParsedSpec:
        """
        Call the LLM to parse *spec_text* into a validated `ParsedSpec`.

        Strips markdown code fences from the response before validation.
        Raises `ValueError` with a descriptive message on malformed output.
        """
        prompt = _PARSE_SPEC_PROMPT.format(spec_text=spec_text)
        raw = self.llm_fn(prompt)
        raw = _strip_fences(raw)

        try:
            return ParsedSpec.model_validate_json(raw)
        except Exception as exc:
            raise ValueError(
                f"parse_spec: LLM returned output that could not be parsed as ParsedSpec. "
                f"Error: {exc!s}. Raw (first 200 chars): {raw[:200]!r}"
            ) from exc

    def seed_graph(self, driver: Driver, parsed: ParsedSpec) -> list[str]:
        """
        Ingest a ParsedSpec into the graph.

        For each ParsedRequirement:  Requirement, Functionality, Component nodes
        + REALIZED_BY (Req → Func) and COMPOSED_OF (Func → Comp) edges.
        For each ParsedAC:           AcceptanceCriterion node.
        For each ParsedActor:        Actor node.

        Idempotent — safe to call multiple times with the same ParsedSpec.
        Returns the list of requirement ids that were ingested.
        """
        for actor in parsed.actors:
            memory_api.ingest_node(driver, Actor(id=actor.id, name=actor.name, role=actor.role))

        req_ids: list[str] = []
        for req in parsed.requirements:
            memory_api.ingest_node(driver, Functionality(
                id=req.functionality_id,
                name=req.functionality_name,
            ))
            memory_api.ingest_node(driver, Component(
                id=req.component_id,
                name=req.component_name,
            ))
            memory_api.ingest_node(driver, Requirement(
                id=req.id,
                title=req.title,
                priority=req.priority,
                reg_control=req.reg_control,
            ))
            now = datetime.now(timezone.utc)
            memory_api.ingest_edge(driver, RealizedByEdge(from_id=req.id, to_id=req.functionality_id, valid_from=now))
            memory_api.ingest_edge(driver, ComposedOfEdge(from_id=req.functionality_id, to_id=req.component_id, valid_from=now))

            for ac in req.acceptance_criteria:
                memory_api.ingest_node(driver, AcceptanceCriterion(
                    id=ac.id,
                    statement=ac.statement,
                ))

            req_ids.append(req.id)

        return req_ids

    def run(self, spec_text: str) -> str:
        """
        Full B3 pipeline: parse_spec → seed_graph → write_provenance.

        Uses a SHA-256 hash of the spec text to build a deterministic judgment
        id so that calling run() twice with the same spec is idempotent.
        Returns the Judgment node's id.
        """
        parsed = self.parse_spec(spec_text)
        req_ids = self.seed_graph(self.driver, parsed)

        spec_hash = hashlib.sha256(spec_text.encode()).hexdigest()[:12]
        judgment_id = f"judgment-requirements-parser-{spec_hash}"
        trace_id = f"trace-requirements-parser-{spec_hash}"
        now = datetime.now(timezone.utc)

        judgment = Judgment(
            id=judgment_id,
            agent_role=self.role,
            label="SEEDED",
        )
        trace = ReasoningTrace(
            id=trace_id,
            agent_role=self.role,
            decision=f"Seeded {len(req_ids)} requirements into the graph.",
            timestamp=now,
        )
        return self.write_provenance(judgment, [trace], req_ids)
