"""
Unit and integration tests for TestCaseGeneratorAgent (Tasks 7 & 8).

Unit tests (Task 7):  no Neo4j, no live LLM.
Integration tests (Task 8): use neo4j_driver fixture, still no live LLM.
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


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests: ingest_tests() + run() (Task 8)
# Uses neo4j_driver fixture — no live LLM.
# ══════════════════════════════════════════════════════════════════════════════

from datetime import datetime, timezone
from src import memory_api
from src.agents.models import ProposedTest
from src.models import AcceptanceCriterion, Functionality

# Stable IDs used only by Task 8 integration tests
_IT_AC_1    = "ac-it8-1"
_IT_AC_2    = "ac-it8-2"
_IT_FUNC    = "func-it8"
_IT_TEST_1  = f"{_IT_AC_1}-test"
_IT_TEST_2  = f"{_IT_AC_2}-test"
_IT_NODES   = [_IT_AC_1, _IT_AC_2, _IT_FUNC, _IT_TEST_1, _IT_TEST_2]

_IT_PROPOSED_1 = ProposedTest(
    ac_id=_IT_AC_1,
    name="test_it8_one",
    type="api",
    verifies_functionality_id=_IT_FUNC,
    description="Integration test proposal 1.",
)
_IT_PROPOSED_2 = ProposedTest(
    ac_id=_IT_AC_2,
    name="test_it8_two",
    type="unit",
    verifies_functionality_id=_IT_FUNC,
    description="Integration test proposal 2.",
)


@pytest.fixture(autouse=False)
def clean_it8_nodes(neo4j_driver):
    """Delete Task 8 test-specific nodes (and all relationships) before each test."""
    # also clean Judgment nodes for these ACs
    judgment_ids = [
        f"judgment-test-proposed-{_IT_AC_1}",
        f"judgment-test-proposed-{_IT_AC_2}",
    ]
    all_ids = _IT_NODES + judgment_ids
    with neo4j_driver.session() as session:
        session.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=all_ids)
    yield
    with neo4j_driver.session() as session:
        session.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=all_ids)


def _seed_it8_prerequisites(driver) -> None:
    memory_api.ingest_node(driver, AcceptanceCriterion(id=_IT_AC_1, statement="IT8 AC one."))
    memory_api.ingest_node(driver, AcceptanceCriterion(id=_IT_AC_2, statement="IT8 AC two."))
    memory_api.ingest_node(driver, Functionality(id=_IT_FUNC, name="IT8 Functionality"))


def _make_it8_agent(driver):
    from src.agents.test_case_generator import TestCaseGeneratorAgent
    return TestCaseGeneratorAgent(
        role="test_case_generator",
        driver=driver,
        llm_fn=lambda p: json.dumps(_PROPOSED_1),
    )


# ── Test: ingest_tests returns list of test ids ───────────────────────────────

def test_ingest_tests_returns_test_ids(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    result = agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    assert isinstance(result, list)
    assert set(result) == {_IT_TEST_1, _IT_TEST_2}


# ── Test: Test nodes exist after ingest ──────────────────────────────────────

def test_ingest_tests_creates_test_nodes(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (t:Test) WHERE t.id IN $ids RETURN count(t) AS cnt",
            ids=[_IT_TEST_1, _IT_TEST_2],
        ).single()["cnt"]
    assert cnt == 2


# ── Test: COVERS_CRITERION edges from Test → AC ──────────────────────────────

def test_ingest_tests_creates_covers_criterion_edges(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    with neo4j_driver.session() as session:
        for test_id, ac_id in [(_IT_TEST_1, _IT_AC_1), (_IT_TEST_2, _IT_AC_2)]:
            cnt = session.run(
                "MATCH (t:Test {id: $tid})-[:COVERS_CRITERION]->(ac:AcceptanceCriterion {id: $acid}) "
                "RETURN count(*) AS cnt",
                tid=test_id, acid=ac_id,
            ).single()["cnt"]
            assert cnt == 1, f"Missing COVERS_CRITERION: {test_id} → {ac_id}"


# ── Test: VERIFIES edges from Test → Functionality ────────────────────────────

def test_ingest_tests_creates_verifies_edges(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (t:Test)-[:VERIFIES]->(f:Functionality {id: $fid}) "
            "WHERE t.id IN $tids RETURN count(t) AS cnt",
            fid=_IT_FUNC, tids=[_IT_TEST_1, _IT_TEST_2],
        ).single()["cnt"]
    assert cnt == 2


# ── Test: coverage_gaps returns [] for these ACs after ingest ─────────────────

def test_ingest_tests_closes_coverage_gaps(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    gap_ids = {r["ac_id"] for r in memory_api.coverage_gaps(neo4j_driver)}
    assert _IT_AC_1 not in gap_ids
    assert _IT_AC_2 not in gap_ids


# ── Test: Judgment nodes with label TEST_PROPOSED exist ──────────────────────

def test_ingest_tests_creates_test_proposed_judgments(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    agent = _make_it8_agent(neo4j_driver)
    agent.ingest_tests(neo4j_driver, [_IT_PROPOSED_1, _IT_PROPOSED_2])
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (j:Judgment {label: 'TEST_PROPOSED'}) "
            "WHERE j.id IN $jids RETURN count(j) AS cnt",
            jids=[
                f"judgment-test-proposed-{_IT_AC_1}",
                f"judgment-test-proposed-{_IT_AC_2}",
            ],
        ).single()["cnt"]
    assert cnt == 2


# ── Test: run() orchestrates gaps → propose → ingest → returns test ids ───────

def test_run_returns_test_ids(neo4j_driver, clean_it8_nodes):
    _seed_it8_prerequisites(neo4j_driver)
    # Stub always returns a ProposedTest for whichever AC is passed
    def stub_llm(prompt: str) -> str:
        # Extract ac_id from the prompt (it's always present)
        import re as _re
        m = _re.search(r"Acceptance Criterion ID\s*:\s*(\S+)", prompt)
        ac_id = m.group(1) if m else _IT_AC_1
        return json.dumps({
            "ac_id": ac_id,
            "name": f"test_{ac_id.replace('-', '_')}",
            "type": "api",
            "verifies_functionality_id": _IT_FUNC,
            "description": "Auto-proposed.",
        })

    from src.agents.test_case_generator import TestCaseGeneratorAgent
    agent = TestCaseGeneratorAgent(
        role="test_case_generator",
        driver=neo4j_driver,
        llm_fn=stub_llm,
    )
    result = agent.run(neo4j_driver)
    assert isinstance(result, list)
    # Our two test ACs must be covered
    gap_ids = {r["ac_id"] for r in memory_api.coverage_gaps(neo4j_driver)}
    assert _IT_AC_1 not in gap_ids
    assert _IT_AC_2 not in gap_ids
