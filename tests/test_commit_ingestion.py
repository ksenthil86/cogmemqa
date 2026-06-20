"""
Tests for CommitIngestionAgent (B8) — Sprint v5 Task 2.

Covers: scaffold, ingest_commit(), MODIFIES edges, COMMIT_INGESTED Judgment,
and run() delegation.
"""
from __future__ import annotations

import pytest

# ── Test commit data ───────────────────────────────────────────────────────────

_T2_SHA       = "t2-test-sha-001"
_T2_COMMIT_ID = f"commit-{_T2_SHA}"
_T2_FILE_PATH = "src/test/CommitIngestionTest.java"
_T2_FILE_ID   = f"file-{_T2_FILE_PATH.replace('/', '-')}"

_T2_COMMIT_DATA = {
    "sha":       _T2_SHA,
    "message":   "Unit-test commit for CommitIngestionAgent",
    "author":    "test@meridian.io",
    "timestamp": "2026-01-15T09:00:00Z",
    "files": [
        {"path": _T2_FILE_PATH, "change_type": "modified"},
    ],
}


@pytest.fixture()
def clean_t2(neo4j_driver):
    """Remove nodes created by Task 2 tests before and after each test."""
    def _clean():
        with neo4j_driver.session() as s:
            s.run("MATCH (c:Commit {sha: $sha}) DETACH DELETE c", sha=_T2_SHA)
            s.run("MATCH (f:File {id: $fid}) DETACH DELETE f", fid=_T2_FILE_ID)
            s.run(
                "MATCH (j:Judgment {label: 'COMMIT_INGESTED'}) "
                "WHERE j.id STARTS WITH 'judgment-commit-commit-t2' "
                "DETACH DELETE j"
            )
            s.run(
                "MATCH (rt:ReasoningTrace) "
                "WHERE rt.id STARTS WITH 'trace-commit-commit-t2' "
                "DETACH DELETE rt"
            )

    _clean()
    yield
    _clean()


# ══════════════════════════════════════════════════════════════════════════════
# Scaffold tests (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_commit_ingestion_agent_importable():
    from src.agents.commit_ingestion import CommitIngestionAgent
    assert CommitIngestionAgent is not None


def test_commit_ingestion_agent_is_base_agent():
    from src.agents.commit_ingestion import CommitIngestionAgent
    from src.agent_base import BaseAgent
    assert issubclass(CommitIngestionAgent, BaseAgent)


def test_commit_ingestion_default_role():
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent()
    assert agent.role == "commit_ingestion"


def test_commit_ingestion_accepts_llm_fn():
    from src.agents.commit_ingestion import CommitIngestionAgent
    stub = lambda p: "ok"
    agent = CommitIngestionAgent(llm_fn=stub)
    assert agent.llm_fn is stub


def test_commit_ingestion_has_no_run_fn_or_scan_fn():
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent()
    assert not hasattr(agent, "run_fn")
    assert not hasattr(agent, "scan_fn")


# ══════════════════════════════════════════════════════════════════════════════
# ingest_commit() integration tests
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_commit_returns_commit_id(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    result = agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)
    assert result == _T2_COMMIT_ID


def test_ingest_commit_creates_commit_node(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (c:Commit {sha: $sha}) RETURN c.message AS msg, c.author AS author",
            sha=_T2_SHA,
        ).single()

    assert row is not None, "Commit node not found"
    assert row["msg"] == _T2_COMMIT_DATA["message"]
    assert row["author"] == _T2_COMMIT_DATA["author"]


def test_ingest_commit_creates_file_node(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)

    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (f:File {id: $fid}) RETURN f.path AS path",
            fid=_T2_FILE_ID,
        ).single()

    assert row is not None, f"File node {_T2_FILE_ID!r} not found"
    assert row["path"] == _T2_FILE_PATH


def test_ingest_commit_creates_modifies_edge(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (c:Commit {sha: $sha})-[:MODIFIES]->(f:File {id: $fid}) "
            "RETURN count(*) AS c",
            sha=_T2_SHA,
            fid=_T2_FILE_ID,
        ).single()["c"]

    assert cnt == 1, "Expected 1 MODIFIES edge"


def test_ingest_commit_creates_commit_ingested_judgment(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'COMMIT_INGESTED'}) "
            "WHERE j.id STARTS WITH 'judgment-commit-' "
            "RETURN count(j) AS c"
        ).single()["c"]

    assert cnt >= 1, "Expected at least 1 COMMIT_INGESTED Judgment"


def test_ingest_commit_creates_reasoning_trace(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    agent.ingest_commit(neo4j_driver, _T2_COMMIT_DATA)

    with neo4j_driver.session() as s:
        cnt = s.run(
            "MATCH (j:Judgment {label: 'COMMIT_INGESTED'})"
            "-[:HAS_STEP]->(rt:ReasoningTrace) "
            "WHERE j.id STARTS WITH 'judgment-commit-' "
            "RETURN count(rt) AS c"
        ).single()["c"]

    assert cnt >= 1, "Expected ReasoningTrace linked to COMMIT_INGESTED Judgment"


def test_run_returns_same_id_as_ingest_commit(neo4j_driver, clean_t2):
    from src.agents.commit_ingestion import CommitIngestionAgent
    agent = CommitIngestionAgent(driver=neo4j_driver)
    result = agent.run(neo4j_driver, _T2_COMMIT_DATA)
    assert result == _T2_COMMIT_ID
