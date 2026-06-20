"""
Tests for FunctionalTesterAgent (B5).

Task 2  — scaffold + _derive_http_spec unit tests
Task 3  — run_http_test unit + integration tests
Task 4  — classify_failure unit tests             (appended later)
Task 5  — record_failure integration test         (appended later)
Task 6  — run() integration tests                 (appended later)
"""
from __future__ import annotations

import pytest

# ── Task 2 — scaffold + _derive_http_spec ─────────────────────────────────────

_FUNC_IDS = [
    "func-account-opening",
    "func-kyc",
    "func-money-transfer",
    "func-transaction-history",
    "func-fraud-alerting",
]

_EXPECTED_METHODS = {
    "func-account-opening":     "POST",
    "func-kyc":                 "POST",
    "func-money-transfer":      "POST",
    "func-transaction-history": "GET",
    "func-fraud-alerting":      "GET",
}

_EXPECTED_PATHS = {
    "func-account-opening":     "/accounts",
    "func-kyc":                 "/kyc/verify",
    "func-money-transfer":      "/transfers",
    "func-transaction-history": "/transactions",
    "func-fraud-alerting":      "/fraud/alerts",
}


def _make_subgraph(test_id: str, func_id: str) -> dict:
    """Minimal subgraph dict as returned by memory_api.retrieve()."""
    return {
        "nodes": [
            {"id": test_id, "labels": ["Test"], "props": {"id": test_id, "name": f"test_{test_id}", "type": "api"}},
            {"id": func_id, "labels": ["Functionality"], "props": {"id": func_id, "name": func_id}},
        ],
        "edges": [
            {"type": "VERIFIES", "from_id": test_id, "to_id": func_id},
        ],
    }


def test_functional_tester_agent_importable():
    from src.agents.functional_tester import FunctionalTesterAgent
    assert FunctionalTesterAgent is not None


def test_functional_tester_agent_inherits_base_agent():
    from src.agents.functional_tester import FunctionalTesterAgent
    from src.agent_base import BaseAgent
    assert issubclass(FunctionalTesterAgent, BaseAgent)


def test_functional_tester_agent_accepts_run_fn():
    from src.agents.functional_tester import FunctionalTesterAgent
    stub = lambda spec: {"status_code": 200, "body": {}, "error": None}
    agent = FunctionalTesterAgent(run_fn=stub)
    assert agent.run_fn is stub


def test_func_to_endpoint_map_has_all_five():
    from src.agents.functional_tester import _FUNC_TO_ENDPOINT
    for func_id in _FUNC_IDS:
        assert func_id in _FUNC_TO_ENDPOINT, f"{func_id!r} missing from _FUNC_TO_ENDPOINT"


def test_derive_http_spec_returns_correct_method():
    from src.agents.functional_tester import FunctionalTesterAgent
    agent = FunctionalTesterAgent()
    for func_id in _FUNC_IDS:
        sg = _make_subgraph("test-001", func_id)
        spec = agent._derive_http_spec(sg, "http://localhost:8000")
        assert spec["method"] == _EXPECTED_METHODS[func_id], (
            f"Expected method {_EXPECTED_METHODS[func_id]!r} for {func_id}, got {spec['method']!r}"
        )


def test_derive_http_spec_returns_correct_url():
    from src.agents.functional_tester import FunctionalTesterAgent
    base = "http://localhost:8000"
    agent = FunctionalTesterAgent()
    for func_id in _FUNC_IDS:
        sg = _make_subgraph("test-001", func_id)
        spec = agent._derive_http_spec(sg, base)
        expected_url = base + _EXPECTED_PATHS[func_id]
        assert spec["url"] == expected_url, (
            f"Expected url {expected_url!r} for {func_id}, got {spec['url']!r}"
        )


def test_derive_http_spec_returns_payload_key():
    from src.agents.functional_tester import FunctionalTesterAgent
    agent = FunctionalTesterAgent()
    sg = _make_subgraph("test-001", "func-account-opening")
    spec = agent._derive_http_spec(sg, "http://localhost:8000")
    assert "payload" in spec


def test_derive_http_spec_unknown_func_id_raises():
    from src.agents.functional_tester import FunctionalTesterAgent
    agent = FunctionalTesterAgent()
    sg = _make_subgraph("test-001", "func-unknown-xyz")
    try:
        agent._derive_http_spec(sg, "http://localhost:8000")
        assert False, "Expected KeyError or ValueError"
    except (KeyError, ValueError):
        pass


# ── Task 3 — run_http_test ─────────────────────────────────────────────────────

_T3_TEST_ID   = "test-t3-account-opening"
_T3_FUNC_ID   = "func-account-opening"
_T3_IDS       = [_T3_TEST_ID, _T3_FUNC_ID]


@pytest.fixture(autouse=False)
def seed_t3_nodes(neo4j_driver):
    """Seed prerequisite Test + Functionality + VERIFIES edge for Task 3 tests."""
    from datetime import datetime, timezone
    from src.memory_api import ingest_node, ingest_edge
    from src.models import Test, Functionality, VerifiesEdge

    now = datetime.now(timezone.utc)
    ingest_node(neo4j_driver, Test(id=_T3_TEST_ID, name="test_account_opening", type="api"))
    ingest_node(neo4j_driver, Functionality(id=_T3_FUNC_ID, name="Account Opening"))
    ingest_edge(neo4j_driver, VerifiesEdge(from_id=_T3_TEST_ID, to_id=_T3_FUNC_ID, valid_from=now))
    yield
    # teardown — remove test nodes and any TestRun nodes linked to them
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (tr:TestRun)-[:INSTANCE_OF]->(t:Test) WHERE t.id IN $ids DETACH DELETE tr",
            ids=[_T3_TEST_ID],
        )
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=_T3_IDS)


def test_run_http_test_pass_returns_true(neo4j_driver, seed_t3_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    stub = lambda spec: {"status_code": 200, "body": {"ok": True}, "error": None}
    agent = FunctionalTesterAgent(driver=neo4j_driver, run_fn=stub)
    test_run_id, passed = agent.run_http_test(neo4j_driver, _T3_TEST_ID)

    assert passed is True
    assert isinstance(test_run_id, str) and test_run_id


def test_run_http_test_fail_returns_false(neo4j_driver, seed_t3_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    stub = lambda spec: {"status_code": 409, "body": {"error": "conflict"}, "error": None}
    agent = FunctionalTesterAgent(driver=neo4j_driver, run_fn=stub)
    test_run_id, passed = agent.run_http_test(neo4j_driver, _T3_TEST_ID)

    assert passed is False
    assert isinstance(test_run_id, str) and test_run_id


def test_run_http_test_error_fn_returns_false(neo4j_driver, seed_t3_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    stub = lambda spec: {"status_code": 0, "body": {}, "error": "connection refused"}
    agent = FunctionalTesterAgent(driver=neo4j_driver, run_fn=stub)
    _, passed = agent.run_http_test(neo4j_driver, _T3_TEST_ID)

    assert passed is False


def test_run_http_test_creates_testrun_node(neo4j_driver, seed_t3_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    stub = lambda spec: {"status_code": 200, "body": {}, "error": None}
    agent = FunctionalTesterAgent(driver=neo4j_driver, run_fn=stub)
    test_run_id, _ = agent.run_http_test(neo4j_driver, _T3_TEST_ID)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (tr:TestRun {id: $id}) RETURN tr.outcome AS outcome",
            id=test_run_id,
        ).single()
    assert row is not None
    assert row["outcome"] == "pass"


def test_run_http_test_creates_instance_of_edge(neo4j_driver, seed_t3_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    stub = lambda spec: {"status_code": 409, "body": {}, "error": None}
    agent = FunctionalTesterAgent(driver=neo4j_driver, run_fn=stub)
    test_run_id, _ = agent.run_http_test(neo4j_driver, _T3_TEST_ID)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (tr:TestRun {id: $tr_id})-[:INSTANCE_OF]->(t:Test {id: $t_id}) RETURN count(*) AS c",
            tr_id=test_run_id, t_id=_T3_TEST_ID,
        ).single()
    assert row["c"] == 1


# ── Task 4 — classify_failure ──────────────────────────────────────────────────

_T4_TEST_ID  = "test-t4-classify"
_T4_AC_ID    = "ac-t4-classify"
_T4_FUNC_ID  = "func-account-opening"
_T4_AC_STMT  = "The system shall open a new account when valid data is provided."
_VALID_CATEGORIES = {"regression", "environment", "flaky", "spec_gap", "data_error", "blocker"}


@pytest.fixture(autouse=False)
def seed_t4_nodes(neo4j_driver):
    """Seed Test + AC + COVERS_CRITERION + VERIFIES for classify_failure tests."""
    from datetime import datetime, timezone
    from src.memory_api import ingest_node, ingest_edge
    from src.models import Test, AcceptanceCriterion, Functionality, CoversCriterionEdge, VerifiesEdge

    now = datetime.now(timezone.utc)
    ingest_node(neo4j_driver, Test(id=_T4_TEST_ID, name="test_t4_classify", type="api"))
    ingest_node(neo4j_driver, AcceptanceCriterion(id=_T4_AC_ID, statement=_T4_AC_STMT))
    ingest_node(neo4j_driver, Functionality(id=_T4_FUNC_ID, name="Account Opening"))
    ingest_edge(neo4j_driver, CoversCriterionEdge(from_id=_T4_TEST_ID, to_id=_T4_AC_ID, valid_from=now))
    ingest_edge(neo4j_driver, VerifiesEdge(from_id=_T4_TEST_ID, to_id=_T4_FUNC_ID, valid_from=now))
    yield
    # teardown
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(t) WHERE t.id = $tid DETACH DELETE j",
            tid=_T4_TEST_ID,
        )
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=[_T4_TEST_ID, _T4_AC_ID],
        )


def test_classify_failure_valid_category_returned(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: "data_error",
    )
    category = agent.classify_failure(neo4j_driver, _T4_TEST_ID, "HTTP 402 INSUFFICIENT_FUNDS")
    assert category == "data_error"


def test_classify_failure_unknown_category_falls_back_to_blocker(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: "totally_unknown_value",
    )
    category = agent.classify_failure(neo4j_driver, _T4_TEST_ID, "timeout")
    assert category == "blocker"


def test_classify_failure_prompt_contains_ac_statement(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    captured: list[str] = []

    def capturing_llm(prompt: str) -> str:
        captured.append(prompt)
        return "environment"

    agent = FunctionalTesterAgent(driver=neo4j_driver, llm_fn=capturing_llm)
    agent.classify_failure(neo4j_driver, _T4_TEST_ID, "connection refused")
    assert captured, "llm_fn was not called"
    assert _T4_AC_STMT in captured[0], "Prompt must contain the AC statement"


def test_classify_failure_prompt_contains_word_category(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    captured: list[str] = []

    def capturing_llm(prompt: str) -> str:
        captured.append(prompt)
        return "regression"

    agent = FunctionalTesterAgent(driver=neo4j_driver, llm_fn=capturing_llm)
    agent.classify_failure(neo4j_driver, _T4_TEST_ID, "500 Internal Server Error")
    assert "category" in captured[0].lower(), "Prompt must contain the word 'category'"


def test_classify_failure_writes_failure_classified_judgment(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        llm_fn=lambda p: "spec_gap",
    )
    agent.classify_failure(neo4j_driver, _T4_TEST_ID, "422 Unprocessable Entity")

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (j:Judgment {label: 'FAILURE_CLASSIFIED'})-[:INFORMED_BY]->(t) "
            "WHERE t.id = $tid RETURN count(j) AS c",
            tid=_T4_TEST_ID,
        ).single()
    assert row["c"] >= 1


def test_classify_failure_all_valid_categories_accepted(neo4j_driver, seed_t4_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    for cat in _VALID_CATEGORIES:
        agent = FunctionalTesterAgent(
            driver=neo4j_driver,
            llm_fn=lambda p, c=cat: c,
        )
        result = agent.classify_failure(neo4j_driver, _T4_TEST_ID, "some error")
        assert result == cat, f"Expected {cat!r} to be accepted, got {result!r}"


# ── Task 5 — record_failure ────────────────────────────────────────────────────

_T5_TEST_ID = "test-t5-record"
_T5_ERROR   = "HTTP 402 INSUFFICIENT_FUNDS"
_T5_CAT     = "data_error"
_T5_FAIL_ID = f"{_T5_TEST_ID}-failure"


@pytest.fixture(autouse=False)
def seed_t5_nodes(neo4j_driver):
    """Seed a minimal Test node for record_failure tests."""
    from src.memory_api import ingest_node
    from src.models import Test

    ingest_node(neo4j_driver, Test(id=_T5_TEST_ID, name="test_t5_record", type="api"))
    yield
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=[_T5_TEST_ID, _T5_FAIL_ID],
        )


def test_record_failure_returns_failure_id(neo4j_driver, seed_t5_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(driver=neo4j_driver)
    failure_id = agent.record_failure(neo4j_driver, _T5_TEST_ID, _T5_ERROR, _T5_CAT)

    assert failure_id == _T5_FAIL_ID


def test_record_failure_node_exists_with_correct_label(neo4j_driver, seed_t5_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(driver=neo4j_driver)
    failure_id = agent.record_failure(neo4j_driver, _T5_TEST_ID, _T5_ERROR, _T5_CAT)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (f:Failure {id: $id}) RETURN f.label AS label, f.error_signature AS sig",
            id=failure_id,
        ).single()
    assert row is not None, "Failure node not found in graph"
    assert row["label"] == _T5_CAT
    assert row["sig"] == _T5_ERROR


def test_record_failure_node_has_confidence(neo4j_driver, seed_t5_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(driver=neo4j_driver)
    failure_id = agent.record_failure(neo4j_driver, _T5_TEST_ID, _T5_ERROR, _T5_CAT)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (f:Failure {id: $id}) RETURN f.confidence AS conf",
            id=failure_id,
        ).single()
    assert row["conf"] == pytest.approx(0.9)


def test_record_failure_idempotent(neo4j_driver, seed_t5_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(driver=neo4j_driver)
    id1 = agent.record_failure(neo4j_driver, _T5_TEST_ID, _T5_ERROR, _T5_CAT)
    id2 = agent.record_failure(neo4j_driver, _T5_TEST_ID, _T5_ERROR, _T5_CAT)

    assert id1 == id2
    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (f:Failure {id: $id}) RETURN count(f) AS c", id=id1
        ).single()["c"]
    assert count == 1


# ── Task 6 — run() orchestrator ────────────────────────────────────────────────

_T6_PASS_TEST = "test-t6-pass"
_T6_FAIL_TEST = "test-t6-fail"
_T6_AC_PASS   = "ac-t6-pass"
_T6_AC_FAIL   = "ac-t6-fail"
_T6_FUNC_ID   = "func-account-opening"
_T6_ALL_TEST_IDS = [_T6_PASS_TEST, _T6_FAIL_TEST]


@pytest.fixture(autouse=False)
def seed_t6_nodes(neo4j_driver):
    """Seed 2 Tests with ACs and VERIFIES + COVERS_CRITERION edges for run() tests."""
    from datetime import datetime, timezone
    from src.memory_api import ingest_node, ingest_edge
    from src.models import (
        Test, AcceptanceCriterion, Functionality,
        CoversCriterionEdge, VerifiesEdge,
    )
    now = datetime.now(timezone.utc)
    ingest_node(neo4j_driver, Functionality(id=_T6_FUNC_ID, name="Account Opening"))
    for test_id, ac_id, ac_stmt in [
        (_T6_PASS_TEST, _T6_AC_PASS, "Account opens successfully with valid data."),
        (_T6_FAIL_TEST, _T6_AC_FAIL, "Account opening rejects duplicate national ID."),
    ]:
        ingest_node(neo4j_driver, Test(id=test_id, name=f"test_{test_id}", type="api"))
        ingest_node(neo4j_driver, AcceptanceCriterion(id=ac_id, statement=ac_stmt))
        ingest_edge(neo4j_driver, CoversCriterionEdge(from_id=test_id, to_id=ac_id, valid_from=now))
        ingest_edge(neo4j_driver, VerifiesEdge(from_id=test_id, to_id=_T6_FUNC_ID, valid_from=now))
    yield
    # teardown — remove TestRun, Failure, Judgment nodes linked to these tests
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (tr:TestRun)-[:INSTANCE_OF]->(t) WHERE t.id IN $ids DETACH DELETE tr",
            ids=_T6_ALL_TEST_IDS,
        )
        s.run(
            "MATCH (f:Failure) WHERE f.id IN $ids DETACH DELETE f",
            ids=[f"{tid}-failure" for tid in _T6_ALL_TEST_IDS],
        )
        s.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(n) WHERE n.id IN $ids DETACH DELETE j",
            ids=_T6_ALL_TEST_IDS + [_T6_AC_PASS, _T6_AC_FAIL],
        )
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=_T6_ALL_TEST_IDS + [_T6_AC_PASS, _T6_AC_FAIL],
        )


def _make_t6_stub_run_fn():
    """Stub run_fn: first call → 200 (pass), second call → 409 (fail)."""
    calls = iter([
        {"status_code": 200, "body": {"account_id": "acc-001"}, "error": None},
        {"status_code": 409, "body": {"error": "conflict"}, "error": None},
    ])
    return lambda spec: next(calls)


def test_run_returns_list_of_test_run_ids(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_t6_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    result = agent.run(neo4j_driver, _T6_ALL_TEST_IDS)

    assert isinstance(result, list)
    assert len(result) == 2


def test_run_creates_testrun_nodes_with_correct_outcomes(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_t6_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    run_ids = agent.run(neo4j_driver, _T6_ALL_TEST_IDS)

    with neo4j_driver.session() as s:
        rows = s.run(
            "MATCH (tr:TestRun) WHERE tr.id IN $ids RETURN tr.id AS id, tr.outcome AS outcome",
            ids=run_ids,
        ).data()
    outcomes = {r["outcome"] for r in rows}
    assert "pass" in outcomes
    assert "fail" in outcomes


def test_run_creates_failure_node_for_failed_test(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_t6_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    agent.run(neo4j_driver, _T6_ALL_TEST_IDS)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (f:Failure) WHERE f.id = $id RETURN count(f) AS c",
            id=f"{_T6_FAIL_TEST}-failure",
        ).single()["c"]
    assert count == 1


def test_run_creates_failure_classified_judgment(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_t6_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    agent.run(neo4j_driver, _T6_ALL_TEST_IDS)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (j:Judgment {label: 'FAILURE_CLASSIFIED'}) RETURN count(j) AS c"
        ).single()["c"]
    assert count >= 1


def test_run_creates_functional_run_complete_judgment(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=_make_t6_stub_run_fn(),
        llm_fn=lambda p: "data_error",
    )
    agent.run(neo4j_driver, _T6_ALL_TEST_IDS)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (j:Judgment {label: 'FUNCTIONAL_RUN_COMPLETE'}) RETURN count(j) AS c"
        ).single()["c"]
    assert count >= 1


def test_run_none_test_ids_auto_discovers_api_tests(neo4j_driver, seed_t6_nodes):
    from src.agents.functional_tester import FunctionalTesterAgent

    # Both t6 tests are type="api" and have no TestRun yet; auto-discover should find them
    calls = []
    stub_run_fn = lambda spec: calls.append(spec) or {"status_code": 200, "body": {}, "error": None}

    agent = FunctionalTesterAgent(
        driver=neo4j_driver,
        run_fn=stub_run_fn,
        llm_fn=lambda p: "environment",
    )
    result = agent.run(neo4j_driver, test_ids=None)

    # At minimum both t6 tests should have been run (there may be more in the DB)
    assert len(result) >= 2
