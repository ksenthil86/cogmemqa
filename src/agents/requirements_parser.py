"""
B3 — Requirements Parser Agent.

Reads a product spec document and populates the graph's requirements +
capability layers via the shared memory API.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from neo4j import Driver

from src.agent_base import BaseAgent
from src.agents.models import ParsedSpec
from src.llm import call_llm

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
