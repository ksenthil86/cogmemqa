"""
Tests for src/chat_tools.py — read-only guard + predefined retrieval tools.

Tool tests hit real Neo4j (project no-mock policy); the graph must be seeded
via scripts/replay_meridian.py.  Guard tests are pure functions, no DB.
"""
from __future__ import annotations

import pytest

from src.chat_tools import (
    CHAT_TOOLS,
    CypherWriteError,
    assert_read_only,
    execute_cypher,
    get_audit_chain,
    get_health,
    get_open_security_findings,
    list_requirements,
    run_tool,
)


# ── assert_read_only ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "MATCH (n) RETURN n",
    "MATCH (n:Requirement) WHERE n.priority = 'P0' RETURN n.title ORDER BY n.id",
    "UNWIND [1,2,3] AS x RETURN x",
    "MATCH (a)-[r]->(b) WITH a, count(r) AS c RETURN a.id, c LIMIT 5",
    # write keywords inside string literals must NOT trip the guard
    "MATCH (n) WHERE n.title = 'CREATE account' RETURN n",
    'MATCH (n) WHERE n.msg = "please DELETE me" RETURN n',
])
def test_read_only_allows(query):
    assert_read_only(query)  # must not raise


@pytest.mark.parametrize("query", [
    "CREATE (n:Hack) RETURN n",
    "MERGE (n:Hack {id: 'x'})",
    "MATCH (n) DELETE n",
    "MATCH (n) DETACH DELETE n",
    "MATCH (n) SET n.x = 1 RETURN n",
    "MATCH (n) REMOVE n.title RETURN n",
    "DROP CONSTRAINT foo",
    "FOREACH (x IN [1] | CREATE (:Y))",
    "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
    "CALL db.labels()",
    "CALL apoc.periodic.iterate('x', 'y', {})",
    # case variations
    "match (n) delete n",
    "MaTcH (n) SeT n.x = 1",
    # comment smuggling
    "MATCH (n) //comment\nDELETE n",
    "MATCH (n) /* block */ SET n.x = 1 RETURN n",
])
def test_read_only_rejects(query):
    with pytest.raises(CypherWriteError):
        assert_read_only(query)


# ── predefined tools (real Neo4j, seeded graph) ───────────────────────────────

def test_get_health_shape(neo4j_driver):
    result = get_health(neo4j_driver)
    for key in ("coverage_pct", "covered_ac", "total_ac",
                "open_findings_count", "by_severity", "report_count"):
        assert key in result.data
    assert result.graph is None


def test_list_requirements_capped_with_total(neo4j_driver):
    result = list_requirements(neo4j_driver)
    assert result.data["showing"] <= 25
    assert result.data["total_requirements"] >= result.data["showing"]
    assert len(result.graph["nodes"]) == result.data["showing"]
    ids = [r["id"] for r in result.data["requirements"]]
    # curated (non-hex) Meridian requirements sort before bulk-seeded hex ids
    assert "req-account-opening" in ids


def test_list_requirements_search(neo4j_driver):
    result = list_requirements(neo4j_driver, search="opening")
    ids = [r["id"] for r in result.data["requirements"]]
    assert "req-account-opening" in ids


def test_get_audit_chain_returns_graph(neo4j_driver):
    result = get_audit_chain(neo4j_driver, "req-account-opening")
    assert result.graph is not None
    assert len(result.graph["nodes"]) >= 4  # Req → Func → Comp → File
    labels = {lbl for n in result.graph["nodes"] for lbl in n["labels"]}
    assert {"Requirement", "Functionality", "Component", "File"} <= labels
    node = result.graph["nodes"][0]
    assert set(node) == {"id", "labels", "properties"}


def test_get_audit_chain_unknown_requirement(neo4j_driver):
    result = get_audit_chain(neo4j_driver, "req-does-not-exist")
    assert "error" in result.data


def test_get_open_security_findings(neo4j_driver):
    result = get_open_security_findings(neo4j_driver)
    assert isinstance(result.data, list)
    for row in result.data:
        assert {"finding_id", "severity", "finding_title",
                "requirement_title", "requirement_priority"} <= set(row)


def test_execute_cypher_returns_rows_and_graph(neo4j_driver):
    result = execute_cypher(neo4j_driver, "MATCH (r:Requirement) RETURN r LIMIT 2")
    assert len(result.data) == 2
    assert result.graph is not None
    assert len(result.graph["nodes"]) == 2


def test_execute_cypher_scalar_rows_have_no_graph(neo4j_driver):
    result = execute_cypher(neo4j_driver, "MATCH (r:Requirement) RETURN count(r) AS n")
    assert result.data[0]["n"] > 0
    assert result.graph is None


def test_execute_cypher_write_rejected_and_graph_unchanged(neo4j_driver):
    with neo4j_driver.session() as s:
        before = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]

    result = execute_cypher(neo4j_driver, "CREATE (n:Hack {id: 'boom'}) RETURN n")
    assert "error" in result.data

    with neo4j_driver.session() as s:
        after = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    assert after == before


def test_run_tool_unknown_name(neo4j_driver):
    result = run_tool(neo4j_driver, "nonexistent_tool", {})
    assert "error" in result.data


def test_run_tool_bad_args(neo4j_driver):
    result = run_tool(neo4j_driver, "get_audit_chain", {"bogus_param": 1})
    assert "error" in result.data


def test_registry_declarations_match_names():
    for name, spec in CHAT_TOOLS.items():
        assert spec.declaration.name == name


def test_get_portfolio_returns_hierarchy(neo4j_driver):
    from scripts.backfill_portfolio import backfill_portfolio, PROJECT, EPICS
    from src.chat_tools import get_portfolio

    backfill_portfolio(neo4j_driver)  # idempotent — safe if already seeded
    result = get_portfolio(neo4j_driver)

    assert isinstance(result.data, list) and len(result.data) == len(EPICS)
    row = result.data[0]
    assert row["project_id"] == PROJECT.id
    assert {"epic_id", "epic_name", "requirement_count"} <= set(row.keys())
    # graph payload contains the project + epics for the canvas
    labels = {lbl for n in result.graph["nodes"] for lbl in n["labels"]}
    assert {"Project", "Epic"} <= labels
