"""
Unit tests for TestCaseGeneratorAgent.propose_tests() (Task 7).

All tests use a stub llm_fn — no Neo4j, no live LLM required.
"""
from __future__ import annotations

import json
import warnings

import pytest

from src.agents.models import ProposedTest


# ── Fixture data ──────────────────────────────────────────────────────────────

_GAP_1 = {
    "ac_id": "ac-ao-1",
    "statement": "Customer can register a new savings account.",
}
_GAP_2 = {
    "ac_id": "ac-kyc-1",
    "statement": "System verifies customer identity within 60 seconds.",
}

_PROPOSED_1 = {
    "ac_id": "ac-ao-1",
    "name": "test_account_registration_happy_path",
    "type": "api",
    "verifies_functionality_id": "func-account-opening",
    "description": "POST /accounts with valid payload returns 201.",
}
_PROPOSED_2 = {
    "ac_id": "ac-kyc-1",
    "name": "test_kyc_verification_within_timeout",
    "type": "api",
    "verifies_functionality_id": "func-kyc",
    "description": "KYC verification completes within 60 s.",
}


def _make_agent(llm_fn):
    from src.agents.test_case_generator import TestCaseGeneratorAgent
    return TestCaseGeneratorAgent(
        role="test_case_generator",
        driver=None,
        llm_fn=llm_fn,
    )


# ── Test: import ──────────────────────────────────────────────────────────────

def test_test_case_generator_importable():
    from src.agents.test_case_generator import TestCaseGeneratorAgent
    assert TestCaseGeneratorAgent


# ── Test: inherits BaseAgent ──────────────────────────────────────────────────

def test_test_case_generator_is_base_agent_subclass():
    from src.agent_base import BaseAgent
    from src.agents.test_case_generator import TestCaseGeneratorAgent
    assert issubclass(TestCaseGeneratorAgent, BaseAgent)


# ── Test: propose_tests returns list of ProposedTest ─────────────────────────

def test_propose_tests_returns_list_of_proposed_tests():
    responses = iter([json.dumps(_PROPOSED_1), json.dumps(_PROPOSED_2)])
    agent = _make_agent(llm_fn=lambda p: next(responses))
    result = agent.propose_tests([_GAP_1, _GAP_2])
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(t, ProposedTest) for t in result)


# ── Test: empty gaps returns empty list ──────────────────────────────────────

def test_propose_tests_empty_gaps_returns_empty_list():
    agent = _make_agent(llm_fn=lambda p: (_ for _ in ()).throw(AssertionError("should not call llm")))
    result = agent.propose_tests([])
    assert result == []


# ── Test: correct ac_id and fields on returned ProposedTest ──────────────────

def test_propose_tests_maps_fields_correctly():
    agent = _make_agent(llm_fn=lambda p: json.dumps(_PROPOSED_1))
    result = agent.propose_tests([_GAP_1])
    t = result[0]
    assert t.ac_id == _PROPOSED_1["ac_id"]
    assert t.name == _PROPOSED_1["name"]
    assert t.type == _PROPOSED_1["type"]
    assert t.verifies_functionality_id == _PROPOSED_1["verifies_functionality_id"]


# ── Test: prompt includes ac_id and statement ─────────────────────────────────

def test_propose_tests_prompt_includes_gap_fields():
    captured = {}
    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(_PROPOSED_1)

    agent = _make_agent(llm_fn=capture_fn)
    agent.propose_tests([_GAP_1])

    assert _GAP_1["ac_id"] in captured["prompt"]
    assert _GAP_1["statement"] in captured["prompt"]


# ── Test: prompt asks for JSON output ────────────────────────────────────────

def test_propose_tests_prompt_mentions_json():
    captured = {}
    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(_PROPOSED_1)

    agent = _make_agent(llm_fn=capture_fn)
    agent.propose_tests([_GAP_1])

    assert "json" in captured["prompt"].lower() or "JSON" in captured["prompt"]


# ── Test: malformed JSON for one gap is skipped, others processed ─────────────

def test_propose_tests_skips_malformed_gap():
    responses = iter(["not valid json at all", json.dumps(_PROPOSED_2)])
    agent = _make_agent(llm_fn=lambda p: next(responses))
    result = agent.propose_tests([_GAP_1, _GAP_2])
    # first gap skipped, second succeeds
    assert len(result) == 1
    assert result[0].ac_id == _PROPOSED_2["ac_id"]


# ── Test: all malformed → empty list (no exception raised) ───────────────────

def test_propose_tests_all_malformed_returns_empty():
    agent = _make_agent(llm_fn=lambda p: "{ broken json }")
    result = agent.propose_tests([_GAP_1, _GAP_2])
    assert result == []


# ── Test: markdown fences stripped from LLM response ─────────────────────────

def test_propose_tests_strips_json_fences():
    fenced = f"```json\n{json.dumps(_PROPOSED_1)}\n```"
    agent = _make_agent(llm_fn=lambda p: fenced)
    result = agent.propose_tests([_GAP_1])
    assert len(result) == 1
    assert result[0].ac_id == _PROPOSED_1["ac_id"]


def test_propose_tests_strips_plain_fences():
    fenced = f"```\n{json.dumps(_PROPOSED_1)}\n```"
    agent = _make_agent(llm_fn=lambda p: fenced)
    result = agent.propose_tests([_GAP_1])
    assert len(result) == 1


# ── Test: one gap per LLM call ───────────────────────────────────────────────

def test_propose_tests_calls_llm_once_per_gap():
    call_count = {"n": 0}
    def counting_fn(prompt: str) -> str:
        call_count["n"] += 1
        return json.dumps(_PROPOSED_1)

    agent = _make_agent(llm_fn=counting_fn)
    agent.propose_tests([_GAP_1, _GAP_2])
    assert call_count["n"] == 2
