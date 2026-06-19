"""
B4 — Test Case Generator Agent.

Iterates coverage gaps (AcceptanceCriterion nodes with no COVERS_CRITERION
edge) and proposes ProposedTest specifications via the LLM.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from neo4j import Driver

from src.agent_base import BaseAgent
from src.agents.models import ProposedTest
from src.llm import call_llm

log = logging.getLogger(__name__)

_PROPOSE_TEST_PROMPT = """\
You are a QA engineer. Given the acceptance criterion below, propose exactly one
test that verifies it.  Return ONLY a JSON object matching this schema — no
markdown fences, no extra text:

{{
  "ac_id": "{ac_id}",
  "name": "<snake_case_test_name>",
  "type": "api" | "ui" | "unit",
  "verifies_functionality_id": "<func-kebab-slug>",
  "description": "<one-sentence description of what the test does>"
}}

Acceptance Criterion ID : {ac_id}
Statement               : {statement}

JSON:"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class TestCaseGeneratorAgent(BaseAgent):
    """
    B4 — Test Case Generator.

    Reads coverage gaps from the shared memory API and proposes test
    specifications for each uncovered AcceptanceCriterion via the LLM.
    """

    def __init__(
        self,
        role: str = "test_case_generator",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)

    def propose_tests(self, gaps: list[dict]) -> list[ProposedTest]:
        """
        For each gap dict (keys: ac_id, statement), ask the LLM to propose
        one ProposedTest.  Gaps where the LLM returns malformed JSON are
        skipped with a warning; processing continues for remaining gaps.

        Returns a list of validated ProposedTest objects (may be shorter than
        *gaps* if some were skipped).
        """
        results: list[ProposedTest] = []
        for gap in gaps:
            prompt = _PROPOSE_TEST_PROMPT.format(
                ac_id=gap["ac_id"],
                statement=gap["statement"],
            )
            raw = self.llm_fn(prompt)
            raw = _strip_fences(raw)
            try:
                results.append(ProposedTest.model_validate_json(raw))
            except Exception as exc:
                log.warning(
                    "propose_tests: skipping gap %r — LLM output could not be "
                    "parsed as ProposedTest. Error: %s. Raw (first 200 chars): %r",
                    gap["ac_id"],
                    exc,
                    raw[:200],
                )
        return results
