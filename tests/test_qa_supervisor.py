"""
Tests for QASupervisorAgent (B7) — Sprint v4 Tasks 4, 5, 6.

Task 4 — scaffold + compute_health()
Task 5 — generate_report() → Report node + Judgment
Task 6 — run() orchestrator
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

NOW = datetime.now(timezone.utc)

# ── Seed IDs ──────────────────────────────────────────────────────────────────

_T4_AC_ID   = "t4-qs-ac-1"
_T4_TEST_ID = "t4-qs-test-1"
_T4_RUN_ID  = "t4-qs-run-1"
_T4_SF_ID   = "t4-qs-sf-1"


@pytest.fixture()
def seed_t4_health_data(neo4j_driver):
    """Seed one passing TestRun + one open SecurityFinding for integration tests."""
    from src.memory_api import ingest_node, ingest_edge
    from src.models import (
        AcceptanceCriterion, Test, TestRun, SecurityFinding,
        CoversCriterionEdge, InstanceOfEdge,
    )

    ingest_node(neo4j_driver, AcceptanceCriterion(id=_T4_AC_ID, statement="S"))
    ingest_node(neo4j_driver, Test(id=_T4_TEST_ID, name="t", type="api"))
    ingest_edge(neo4j_driver, CoversCriterionEdge(from_id=_T4_TEST_ID, to_id=_T4_AC_ID, valid_from=NOW))
    ingest_node(neo4j_driver, TestRun(id=_T4_RUN_ID, outcome="pass", timestamp=NOW))
    ingest_edge(neo4j_driver, InstanceOfEdge(from_id=_T4_RUN_ID, to_id=_T4_TEST_ID, valid_from=NOW))
    ingest_node(neo4j_driver, SecurityFinding(id=_T4_SF_ID, severity="low", title="X", status="open"))

    yield

    with neo4j_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            ids=[_T4_AC_ID, _T4_TEST_ID, _T4_RUN_ID, _T4_SF_ID],
        )
        s.run(
            "MATCH (j:Judgment)-[:INFORMED_BY]->(n) WHERE n.id IN $ids DETACH DELETE j",
            ids=[_T4_AC_ID, _T4_TEST_ID, _T4_RUN_ID, _T4_SF_ID],
        )
        # Clean up Report nodes created in these tests
        s.run("MATCH (r:Report) WHERE r.id STARTS WITH 'report-' DETACH DELETE r")
        s.run("MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'}) DETACH DELETE j")


# ══════════════════════════════════════════════════════════════════════════════
# Task 4 — scaffold + compute_health()
# ══════════════════════════════════════════════════════════════════════════════

def test_qa_supervisor_importable():
    from src.agents.qa_supervisor import QASupervisorAgent
    assert QASupervisorAgent is not None


def test_qa_supervisor_inherits_base_agent():
    from src.agents.qa_supervisor import QASupervisorAgent
    from src.agent_base import BaseAgent
    assert issubclass(QASupervisorAgent, BaseAgent)


def test_qa_supervisor_default_role():
    from src.agents.qa_supervisor import QASupervisorAgent
    agent = QASupervisorAgent()
    assert agent.role == "qa_supervisor"


def test_qa_supervisor_accepts_llm_fn():
    from src.agents.qa_supervisor import QASupervisorAgent
    stub = lambda p: "ok"
    agent = QASupervisorAgent(llm_fn=stub)
    assert agent.llm_fn is stub


def test_qa_supervisor_has_no_run_fn_or_scan_fn():
    """Supervisor uses only Cypher — no injectable HTTP or scanner."""
    from src.agents.qa_supervisor import QASupervisorAgent
    agent = QASupervisorAgent()
    assert not hasattr(agent, "run_fn")
    assert not hasattr(agent, "scan_fn")


def test_compute_health_returns_expected_keys(neo4j_driver):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver)
    result = agent.compute_health(neo4j_driver)

    assert "coverage_pct" in result
    assert "covered_ac" in result
    assert "total_ac" in result
    assert "open_findings_count" in result
    assert "by_severity" in result


def test_compute_health_by_severity_has_three_keys(neo4j_driver):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver)
    sev = agent.compute_health(neo4j_driver)["by_severity"]

    assert "low" in sev
    assert "medium" in sev
    assert "high" in sev


def test_compute_health_types(neo4j_driver):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver)
    result = agent.compute_health(neo4j_driver)

    assert isinstance(result["coverage_pct"], float)
    assert isinstance(result["covered_ac"], int)
    assert isinstance(result["total_ac"], int)
    assert isinstance(result["open_findings_count"], int)


def test_compute_health_totals_consistent(neo4j_driver):
    """open_findings_count == sum of by_severity values."""
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver)
    result = agent.compute_health(neo4j_driver)
    sev = result["by_severity"]

    assert result["open_findings_count"] == sev["low"] + sev["medium"] + sev["high"]


# ══════════════════════════════════════════════════════════════════════════════
# Task 5 — generate_report()
# ══════════════════════════════════════════════════════════════════════════════

def test_generate_report_returns_string(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    result = agent.generate_report(neo4j_driver)

    assert isinstance(result, str) and result.startswith("report-")


def test_generate_report_creates_report_node(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    report_id = agent.generate_report(neo4j_driver)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (r:Report {id: $id}) RETURN r.coverage_pct AS cov, "
            "r.open_findings_count AS ofc",
            id=report_id,
        ).single()

    assert row is not None, "Report node not found"
    assert row["cov"] >= 0.0
    assert row["ofc"] >= 0


def test_generate_report_creates_health_report_judgment(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    agent.generate_report(neo4j_driver)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'}) RETURN count(j) AS c"
        ).single()["c"]

    assert cnt >= 1


def test_generate_report_creates_reasoning_trace(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    agent.generate_report(neo4j_driver)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'})-[:HAS_STEP]->(rt:ReasoningTrace) "
            "RETURN count(rt) AS c"
        ).single()["c"]

    assert cnt >= 1


def test_generate_report_severity_breakdown_is_valid_json(neo4j_driver, seed_t4_health_data):
    import json
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    report_id = agent.generate_report(neo4j_driver)

    with neo4j_driver.session() as s:
        sb = s.run(
            "MATCH (r:Report {id: $id}) RETURN r.severity_breakdown AS sb",
            id=report_id,
        ).single()["sb"]

    parsed = json.loads(sb)
    assert "low" in parsed and "medium" in parsed and "high" in parsed


# ══════════════════════════════════════════════════════════════════════════════
# Task 6 — run()
# ══════════════════════════════════════════════════════════════════════════════

def test_run_returns_report_id(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    report_id = agent.run(neo4j_driver)

    assert isinstance(report_id, str)
    assert report_id.startswith("report-")


def test_run_creates_report_node_in_graph(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    report_id = agent.run(neo4j_driver)

    with neo4j_driver.session() as s:
        exists = s.run(
            "MATCH (r:Report {id: $id}) RETURN count(r) AS c", id=report_id
        ).single()["c"]

    assert exists == 1


def test_run_twice_produces_distinct_report_ids(neo4j_driver, seed_t4_health_data):
    """Each run() call is a new health snapshot — distinct ids."""
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    id1 = agent.run(neo4j_driver)
    id2 = agent.run(neo4j_driver)

    assert id1 != id2


def test_run_creates_health_report_generated_judgment(neo4j_driver, seed_t4_health_data):
    from src.agents.qa_supervisor import QASupervisorAgent

    agent = QASupervisorAgent(driver=neo4j_driver, llm_fn=lambda p: "Health OK")
    agent.run(neo4j_driver)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'HEALTH_REPORT_GENERATED'}) RETURN count(j) AS c"
        ).single()["c"]

    assert cnt >= 1
