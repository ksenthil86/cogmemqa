"""
Tests for scripts/backfill_portfolio.py — Project → Epic → Requirement.

Runs against real Neo4j (project no-mock policy). Uses a throwaway fake
requirement to prove catch-all behaviour, and cleans it up afterwards.
"""
from __future__ import annotations

import pytest

from scripts.backfill_portfolio import (
    CATCH_ALL_EPIC,
    CURATED,
    EPICS,
    PROJECT,
    backfill_portfolio,
)
from app import memory_api
from app.models import Requirement

FAKE_REQ_ID = "req-testbf01"  # hex-style id → should land in the backlog epic


@pytest.fixture
def seeded(neo4j_driver):
    memory_api.ingest_node(
        neo4j_driver, Requirement(id=FAKE_REQ_ID, title="Backfill fixture req")
    )
    stats = backfill_portfolio(neo4j_driver)
    yield stats
    with neo4j_driver.session() as s:
        s.run("MATCH (r:Requirement {id: $id}) DETACH DELETE r", id=FAKE_REQ_ID)


def test_stats_shape_and_no_orphans(seeded):
    assert set(seeded.keys()) == {"attached", "orphans_remaining"}
    assert seeded["orphans_remaining"] == 0


def test_project_and_epics_exist(neo4j_driver, seeded):
    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (p:Project {id: $pid})-[:HAS_EPIC]->(e:Epic) "
            "RETURN p.name AS name, collect(e.id) AS epics",
            pid=PROJECT.id,
        ).single()
    assert row["name"] == PROJECT.name
    assert set(row["epics"]) == {e.id for e in EPICS}


def test_curated_requirements_under_their_epics(neo4j_driver, seeded):
    with neo4j_driver.session() as s:
        for req_id, epic_id in CURATED.items():
            row = s.run(
                "MATCH (e:Epic)-[:HAS_REQUIREMENT]->(r:Requirement {id: $rid}) "
                "RETURN collect(e.id) AS epics",
                rid=req_id,
            ).single()
            assert row["epics"] == [epic_id], (
                f"{req_id} should be only under {epic_id}, got {row['epics']}"
            )


def test_uncurated_requirement_lands_in_backlog(neo4j_driver, seeded):
    with neo4j_driver.session() as s:
        row = s.run(
            "MATCH (e:Epic)-[:HAS_REQUIREMENT]->(r:Requirement {id: $rid}) "
            "RETURN collect(e.id) AS epics",
            rid=FAKE_REQ_ID,
        ).single()
    assert row["epics"] == [CATCH_ALL_EPIC]


def test_backfill_is_idempotent(neo4j_driver, seeded):
    def edge_count():
        with neo4j_driver.session() as s:
            return s.run(
                "MATCH (:Epic)-[rel:HAS_REQUIREMENT]->(:Requirement) "
                "RETURN count(rel) AS n"
            ).single()["n"]

    before = edge_count()
    rerun = backfill_portfolio(neo4j_driver)
    assert rerun["attached"] == 0
    assert rerun["orphans_remaining"] == 0
    assert edge_count() == before
