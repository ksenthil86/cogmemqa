"""
Tests for SecurityTesterAgent (B6).

Task 7  — scaffold + _map_file_to_component unit tests
Task 8  — ingest_findings integration tests
Task 9  — run() integration tests
"""
from __future__ import annotations

import pytest

# ── Task 7 — scaffold + _map_file_to_component ────────────────────────────────

_KEYWORD_TO_COMPONENT = {
    "account":     "comp-account-opening",
    "kyc":         "comp-kyc",
    "transfer":    "comp-money-transfer",
    "transaction": "comp-transaction-history",
    "fraud":       "comp-fraud-alerting",
}


def test_security_tester_agent_importable():
    from src.agents.security_tester import SecurityTesterAgent
    assert SecurityTesterAgent is not None


def test_security_tester_agent_inherits_base_agent():
    from src.agents.security_tester import SecurityTesterAgent
    from src.agent_base import BaseAgent
    assert issubclass(SecurityTesterAgent, BaseAgent)


def test_security_tester_agent_accepts_scan_fn():
    from src.agents.security_tester import SecurityTesterAgent
    stub = lambda path: []
    agent = SecurityTesterAgent(scan_fn=stub)
    assert agent.scan_fn is stub


def test_file_keywords_map_has_all_five():
    from src.agents.security_tester import _FILE_KEYWORDS
    for keyword, comp_id in _KEYWORD_TO_COMPONENT.items():
        assert keyword in _FILE_KEYWORDS, f"{keyword!r} missing from _FILE_KEYWORDS"
        assert _FILE_KEYWORDS[keyword] == comp_id


@pytest.mark.parametrize("filename,expected_comp", [
    ("src/account/AccountController.java",       "comp-account-opening"),
    ("src/kyc/KycVerifier.py",                   "comp-kyc"),
    ("services/transfer_service.py",             "comp-money-transfer"),
    ("src/transaction/TransactionHistory.java",  "comp-transaction-history"),
    ("src/fraud/FraudAlerts.py",                 "comp-fraud-alerting"),
    # keyword appears anywhere in path
    ("/path/to/AccountRepository.java",          "comp-account-opening"),
])
def test_map_file_to_component_known_keywords(filename, expected_comp):
    from src.agents.security_tester import SecurityTesterAgent
    agent = SecurityTesterAgent()
    result = agent._map_file_to_component(filename)
    assert result == expected_comp, f"Expected {expected_comp!r} for {filename!r}, got {result!r}"


def test_map_file_to_component_unknown_returns_none():
    from src.agents.security_tester import SecurityTesterAgent
    agent = SecurityTesterAgent()
    result = agent._map_file_to_component("src/utils/helpers.py")
    assert result is None


def test_map_file_to_component_case_insensitive():
    from src.agents.security_tester import SecurityTesterAgent
    agent = SecurityTesterAgent()
    assert agent._map_file_to_component("src/KYC/verifier.py") == "comp-kyc"
    assert agent._map_file_to_component("src/ACCOUNT/ctrl.py") == "comp-account-opening"


def test_default_scan_fn_is_callable():
    from src.agents.security_tester import SecurityTesterAgent
    agent = SecurityTesterAgent()
    assert callable(agent.scan_fn)


# ── Task 8 — ingest_findings ──────────────────────────────────────────────────

_T8_COMP_ID = "comp-account-opening"

_T8_FINDINGS = [
    {
        "filename": "src/account/AccountController.java",   # "account" → comp-account-opening
        "issue_severity": "LOW",
        "issue_text": "Possible hardcoded password: 'meridian-dev-secret-2024'",
        "test_id": "B105",
    },
    {
        "filename": "src/kyc/KycVerifier.py",              # "kyc" → comp-kyc
        "issue_severity": "MEDIUM",
        "issue_text": "Use of weak MD5 hash detected",
        "test_id": "B324",
    },
    {
        "filename": "fixtures/unknown_module.py",          # no keyword match → no AFFECTS
        "issue_severity": "HIGH",
        "issue_text": "SQL injection vulnerability detected",
        "test_id": "B608",
    },
]

_T8_FINDING_IDS = [
    "finding-B105-0",
    "finding-B324-1",
    "finding-B608-2",
]


@pytest.fixture(autouse=False)
def seed_t8_component(neo4j_driver):
    """Ensure the Component node exists for AFFECTS edge creation."""
    from src.memory_api import ingest_node
    from src.models import Component

    ingest_node(neo4j_driver, Component(id=_T8_COMP_ID, name="Account Opening"))
    ingest_node(neo4j_driver, Component(id="comp-kyc", name="KYC"))
    yield
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=_T8_FINDING_IDS,
        )
        # Also clean up Judgments for these findings
        s.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(f) WHERE f.id IN $ids DETACH DELETE j",
            ids=_T8_FINDING_IDS,
        )


def test_ingest_findings_returns_finding_ids(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    ids = agent.ingest_findings(neo4j_driver, _T8_FINDINGS)

    assert isinstance(ids, list)
    assert len(ids) == 3


def test_ingest_findings_creates_security_finding_nodes(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    finding_ids = agent.ingest_findings(neo4j_driver, _T8_FINDINGS)

    with neo4j_driver.session() as s:
        rows = s.run(
            "MATCH (f:SecurityFinding) WHERE f.id IN $ids RETURN f.id AS id, f.severity AS sev",
            ids=finding_ids,
        ).data()
    assert len(rows) == 3
    severities = {r["sev"] for r in rows}
    assert "low" in severities
    assert "medium" in severities
    assert "high" in severities


def test_ingest_findings_affects_edge_created_for_mapped_file(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    finding_ids = agent.ingest_findings(neo4j_driver, _T8_FINDINGS)

    # Finding 0 (main.py → "account" keyword) and Finding 1 (kyc_service.py → "kyc") should have AFFECTS
    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (f:SecurityFinding)-[:AFFECTS]->(c:Component) "
            "WHERE f.id IN $ids RETURN count(*) AS c",
            ids=finding_ids,
        ).single()["c"]
    assert count == 2, f"Expected 2 AFFECTS edges (account + kyc), got {count}"


def test_ingest_findings_no_affects_for_unknown_file(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    finding_ids = agent.ingest_findings(neo4j_driver, _T8_FINDINGS)

    # Finding 2 (unknown_module.py) should NOT have an AFFECTS edge
    unknown_id = finding_ids[2]
    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (f:SecurityFinding {id: $id})-[:AFFECTS]->() RETURN count(*) AS c",
            id=unknown_id,
        ).single()["c"]
    assert count == 0


def test_ingest_findings_writes_security_finding_judgment(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    finding_ids = agent.ingest_findings(neo4j_driver, _T8_FINDINGS)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (j:Judgment {label: 'SECURITY_FINDING'})-[:INFORMED_BY]->(f:SecurityFinding) "
            "WHERE f.id IN $ids RETURN count(j) AS c",
            ids=finding_ids,
        ).single()["c"]
    assert count == 3, f"Expected 3 SECURITY_FINDING Judgments, got {count}"


def test_ingest_findings_empty_list_returns_empty(neo4j_driver, seed_t8_component):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(driver=neo4j_driver)
    result = agent.ingest_findings(neo4j_driver, [])
    assert result == []


# ── Task 9 — run() orchestrator ───────────────────────────────────────────────

_T9_SOURCE_PATH = "fixtures/meridian_app"
_T9_STUB_FINDINGS = [
    {
        "filename": "src/account/AccountController.py",
        "issue_severity": "LOW",
        "issue_text": "Hardcoded password found in account controller",
        "test_id": "B105",
    },
    {
        "filename": "src/kyc/KycService.py",
        "issue_severity": "MEDIUM",
        "issue_text": "Use of weak MD5 hash in KYC service",
        "test_id": "B324",
    },
]
_T9_FINDING_IDS = ["finding-B105-0", "finding-B324-1"]


@pytest.fixture(autouse=False)
def seed_t9_components(neo4j_driver):
    """Ensure Component nodes exist for AFFECTS edges in run() tests."""
    from src.memory_api import ingest_node
    from src.models import Component

    ingest_node(neo4j_driver, Component(id="comp-account-opening", name="Account Opening"))
    ingest_node(neo4j_driver, Component(id="comp-kyc", name="KYC"))
    yield
    with neo4j_driver.session() as s:
        s.run(
            "MATCH (f:SecurityFinding) WHERE f.id IN $ids DETACH DELETE f",
            ids=_T9_FINDING_IDS,
        )
        s.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(f) WHERE f.id IN $ids DETACH DELETE j",
            ids=_T9_FINDING_IDS,
        )
        # Remove SECURITY_SCAN_COMPLETE judgment (identified by label + no specific finding link)
        s.run(
            "MATCH (j:Judgment {label: 'SECURITY_SCAN_COMPLETE'}) "
            "WHERE NOT (j)-[:INFORMED_BY]->() OR "
            "       (j)-[:INFORMED_BY]->(:SecurityFinding) DETACH DELETE j"
        )


def test_run_returns_finding_ids(neo4j_driver, seed_t9_components):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: _T9_STUB_FINDINGS,
    )
    result = agent.run(neo4j_driver, _T9_SOURCE_PATH)

    assert isinstance(result, list)
    assert len(result) == 2


def test_run_creates_security_finding_nodes(neo4j_driver, seed_t9_components):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: _T9_STUB_FINDINGS,
    )
    finding_ids = agent.run(neo4j_driver, _T9_SOURCE_PATH)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (f:SecurityFinding) WHERE f.id IN $ids RETURN count(f) AS c",
            ids=finding_ids,
        ).single()["c"]
    assert count == 2


def test_run_calls_scan_fn_with_source_path(neo4j_driver, seed_t9_components):
    from src.agents.security_tester import SecurityTesterAgent

    captured_paths: list[str] = []

    def capturing_scan_fn(path: str) -> list[dict]:
        captured_paths.append(path)
        return _T9_STUB_FINDINGS

    agent = SecurityTesterAgent(driver=neo4j_driver, scan_fn=capturing_scan_fn)
    agent.run(neo4j_driver, _T9_SOURCE_PATH)

    assert captured_paths == [_T9_SOURCE_PATH]


def test_run_writes_security_scan_complete_judgment(neo4j_driver, seed_t9_components):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: _T9_STUB_FINDINGS,
    )
    agent.run(neo4j_driver, _T9_SOURCE_PATH)

    with neo4j_driver.session() as s:
        count = s.run(
            "MATCH (j:Judgment {label: 'SECURITY_SCAN_COMPLETE'}) RETURN count(j) AS c"
        ).single()["c"]
    assert count >= 1


def test_run_empty_scan_returns_empty_list(neo4j_driver, seed_t9_components):
    from src.agents.security_tester import SecurityTesterAgent

    agent = SecurityTesterAgent(
        driver=neo4j_driver,
        scan_fn=lambda path: [],
    )
    result = agent.run(neo4j_driver, _T9_SOURCE_PATH)

    assert result == []
