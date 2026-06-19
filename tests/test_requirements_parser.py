"""
Unit and integration tests for RequirementsParserAgent (Tasks 3 & 4).

Unit tests (Tasks 3): no Neo4j, no live LLM.
Integration tests (Task 4): use neo4j_driver fixture, still no live LLM.
"""
import json
from pathlib import Path

import pytest

from src.agents.models import ParsedSpec

MERIDIAN_JSON = Path(__file__).parent.parent / "fixtures" / "meridian_parsed.json"
MERIDIAN_RAW  = MERIDIAN_JSON.read_text()
MERIDIAN_SPEC = ParsedSpec.model_validate_json(MERIDIAN_RAW)


def _make_agent(llm_fn):
    from src.agents.requirements_parser import RequirementsParserAgent
    return RequirementsParserAgent(
        role="requirements_parser",
        driver=None,
        llm_fn=llm_fn,
    )


# ── Test 1: import ─────────────────────────────────────────────────────────────

def test_requirements_parser_agent_importable():
    from src.agents.requirements_parser import RequirementsParserAgent
    assert RequirementsParserAgent


# ── Test 2: inherits BaseAgent ─────────────────────────────────────────────────

def test_requirements_parser_is_base_agent_subclass():
    from src.agent_base import BaseAgent
    from src.agents.requirements_parser import RequirementsParserAgent
    assert issubclass(RequirementsParserAgent, BaseAgent)


# ── Test 3: parse_spec with valid JSON stub ────────────────────────────────────

def test_parse_spec_returns_parsed_spec_on_valid_json():
    from src.agents.models import ParsedSpec
    agent = _make_agent(llm_fn=lambda p: MERIDIAN_RAW)
    result = agent.parse_spec("any spec text")
    assert isinstance(result, ParsedSpec)
    assert len(result.requirements) == 5


# ── Test 4: strip markdown fences from LLM response ───────────────────────────

def test_parse_spec_strips_json_markdown_fence():
    fenced = f"```json\n{MERIDIAN_RAW}\n```"
    agent = _make_agent(llm_fn=lambda p: fenced)
    result = agent.parse_spec("spec")
    assert len(result.requirements) == 5


def test_parse_spec_strips_plain_markdown_fence():
    fenced = f"```\n{MERIDIAN_RAW}\n```"
    agent = _make_agent(llm_fn=lambda p: fenced)
    result = agent.parse_spec("spec")
    assert len(result.requirements) == 5


def test_parse_spec_handles_leading_trailing_whitespace():
    spaced = f"\n\n  {MERIDIAN_RAW}  \n\n"
    agent = _make_agent(llm_fn=lambda p: spaced)
    result = agent.parse_spec("spec")
    assert len(result.requirements) == 5


# ── Test 5: malformed JSON raises ValueError ──────────────────────────────────

def test_parse_spec_raises_value_error_on_invalid_json():
    agent = _make_agent(llm_fn=lambda p: "this is not json at all")
    with pytest.raises(ValueError, match="parse_spec"):
        agent.parse_spec("spec")


def test_parse_spec_raises_value_error_on_empty_response():
    agent = _make_agent(llm_fn=lambda p: "")
    with pytest.raises(ValueError, match="parse_spec"):
        agent.parse_spec("spec")


def test_parse_spec_raises_value_error_on_wrong_schema():
    agent = _make_agent(llm_fn=lambda p: '{"unexpected": true}')
    with pytest.raises(ValueError, match="parse_spec"):
        agent.parse_spec("spec")


# ── Test 6: prompt contains essential schema hints ────────────────────────────

def test_parse_spec_prompt_mentions_json():
    captured = {}
    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return MERIDIAN_RAW

    agent = _make_agent(llm_fn=capture_fn)
    agent.parse_spec("the spec")

    prompt = captured["prompt"]
    assert "JSON" in prompt or "json" in prompt, "Prompt must mention JSON output format"


def test_parse_spec_prompt_includes_spec_text():
    captured = {}
    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return MERIDIAN_RAW

    agent = _make_agent(llm_fn=capture_fn)
    agent.parse_spec("UNIQUE_SPEC_SENTINEL_STRING")

    assert "UNIQUE_SPEC_SENTINEL_STRING" in captured["prompt"], (
        "Prompt must embed the spec text"
    )


def test_parse_spec_prompt_mentions_actors_and_requirements():
    captured = {}
    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return MERIDIAN_RAW

    agent = _make_agent(llm_fn=capture_fn)
    agent.parse_spec("spec")

    prompt = captured["prompt"].lower()
    assert "actors" in prompt or "requirements" in prompt, (
        "Prompt must reference the ParsedSpec schema fields"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests: seed_graph() (Task 4)
# Uses neo4j_driver fixture — no live LLM.
# Meridian fixture uses fixed slug IDs so counts are measured by id membership.
# ══════════════════════════════════════════════════════════════════════════════

def _count_nodes(driver, label: str, ids: list[str]) -> int:
    with driver.session() as session:
        return session.run(
            f"MATCH (n:{label}) WHERE n.id IN $ids RETURN count(n) AS cnt",
            ids=ids,
        ).single()["cnt"]


def _edge_exists(driver, from_id: str, to_id: str, rel_type: str) -> bool:
    with driver.session() as session:
        cnt = session.run(
            f"MATCH (a {{id: $fid}})-[r:{rel_type}]->(b {{id: $tid}}) "
            "RETURN count(r) AS cnt",
            fid=from_id, tid=to_id,
        ).single()["cnt"]
        return cnt > 0


def _make_seeding_agent(driver):
    from src.agents.requirements_parser import RequirementsParserAgent
    return RequirementsParserAgent(
        role="requirements_parser",
        driver=driver,
        llm_fn=lambda p: MERIDIAN_RAW,
    )


# ── Test: seed_graph returns requirement ids ───────────────────────────────────

def test_seed_graph_returns_list_of_requirement_ids(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    result = agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    assert isinstance(result, list)
    expected_ids = {r.id for r in MERIDIAN_SPEC.requirements}
    assert set(result) == expected_ids


# ── Test: node counts after seeding ───────────────────────────────────────────

def test_seed_graph_ingests_five_requirement_nodes(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    req_ids = [r.id for r in MERIDIAN_SPEC.requirements]
    assert _count_nodes(neo4j_driver, "Requirement", req_ids) == 5


def test_seed_graph_ingests_five_functionality_nodes(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    func_ids = [r.functionality_id for r in MERIDIAN_SPEC.requirements]
    assert _count_nodes(neo4j_driver, "Functionality", func_ids) == 5


def test_seed_graph_ingests_five_component_nodes(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    comp_ids = [r.component_id for r in MERIDIAN_SPEC.requirements]
    assert _count_nodes(neo4j_driver, "Component", comp_ids) == 5


def test_seed_graph_ingests_ten_acceptance_criterion_nodes(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    ac_ids = [ac.id for r in MERIDIAN_SPEC.requirements for ac in r.acceptance_criteria]
    assert _count_nodes(neo4j_driver, "AcceptanceCriterion", ac_ids) == 10


def test_seed_graph_ingests_two_actor_nodes(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    actor_ids = [a.id for a in MERIDIAN_SPEC.actors]
    assert _count_nodes(neo4j_driver, "Actor", actor_ids) == 2


# ── Test: edges after seeding ─────────────────────────────────────────────────

def test_seed_graph_creates_realized_by_edges(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    for req in MERIDIAN_SPEC.requirements:
        assert _edge_exists(neo4j_driver, req.id, req.functionality_id, "REALIZED_BY"), (
            f"Missing REALIZED_BY edge: {req.id} → {req.functionality_id}"
        )


def test_seed_graph_creates_composed_of_edges(neo4j_driver):
    agent = _make_seeding_agent(neo4j_driver)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    for req in MERIDIAN_SPEC.requirements:
        assert _edge_exists(neo4j_driver, req.functionality_id, req.component_id, "COMPOSED_OF"), (
            f"Missing COMPOSED_OF edge: {req.functionality_id} → {req.component_id}"
        )


# ── Test: idempotency ─────────────────────────────────────────────────────────

def test_seed_graph_is_idempotent_requirement_nodes(neo4j_driver):
    """Calling seed_graph twice must not duplicate Requirement nodes."""
    agent = _make_seeding_agent(neo4j_driver)
    req_ids = [r.id for r in MERIDIAN_SPEC.requirements]

    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)

    assert _count_nodes(neo4j_driver, "Requirement", req_ids) == 5


def test_seed_graph_is_idempotent_edges(neo4j_driver):
    """Calling seed_graph twice must not duplicate REALIZED_BY edges."""
    agent = _make_seeding_agent(neo4j_driver)
    req = MERIDIAN_SPEC.requirements[0]

    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)
    agent.seed_graph(neo4j_driver, MERIDIAN_SPEC)

    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (a {id: $fid})-[r:REALIZED_BY]->(b {id: $tid}) RETURN count(r) AS cnt",
            fid=req.id, tid=req.functionality_id,
        ).single()["cnt"]
    assert cnt == 1, "REALIZED_BY edge must not be duplicated by a second seed_graph call"


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests: run() + provenance (Task 5)
# Uses neo4j_driver fixture — no live LLM.
# ══════════════════════════════════════════════════════════════════════════════

MERIDIAN_SPEC_TEXT = (
    Path(__file__).parent.parent / "fixtures" / "meridian_spec.md"
).read_text()


def _make_run_agent(driver):
    from src.agents.requirements_parser import RequirementsParserAgent
    return RequirementsParserAgent(
        role="requirements_parser",
        driver=driver,
        llm_fn=lambda p: MERIDIAN_RAW,
    )


# ── Test: run() returns a judgment id string ───────────────────────────────────

def test_run_returns_string_judgment_id(neo4j_driver):
    agent = _make_run_agent(neo4j_driver)
    result = agent.run(MERIDIAN_SPEC_TEXT)
    assert isinstance(result, str) and result.strip(), "run() must return a non-empty judgment id"


# ── Test: Judgment node with label SEEDED exists after run() ──────────────────

def test_run_creates_seeded_judgment_node(neo4j_driver):
    agent = _make_run_agent(neo4j_driver)
    judgment_id = agent.run(MERIDIAN_SPEC_TEXT)
    with neo4j_driver.session() as session:
        row = session.run(
            "MATCH (j:Judgment {id: $jid}) RETURN j.label AS label",
            jid=judgment_id,
        ).single()
    assert row is not None, f"No Judgment node found with id={judgment_id!r}"
    assert row["label"] == "SEEDED"


# ── Test: ReasoningTrace node linked to Judgment ─────────────────────────────

def test_run_creates_reasoning_trace_linked_to_judgment(neo4j_driver):
    agent = _make_run_agent(neo4j_driver)
    judgment_id = agent.run(MERIDIAN_SPEC_TEXT)
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (j:Judgment {id: $jid})-[:HAS_STEP]->(t:ReasoningTrace) RETURN count(t) AS cnt",
            jid=judgment_id,
        ).single()["cnt"]
    assert cnt >= 1, "Judgment must have at least one HAS_STEP → ReasoningTrace edge"


# ── Test: Judgment has INFORMED_BY edges to requirement nodes ─────────────────

def test_run_judgment_has_informed_by_edges_to_requirements(neo4j_driver):
    agent = _make_run_agent(neo4j_driver)
    judgment_id = agent.run(MERIDIAN_SPEC_TEXT)
    req_ids = [r.id for r in MERIDIAN_SPEC.requirements]
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (j:Judgment {id: $jid})-[:INFORMED_BY]->(r:Requirement) "
            "WHERE r.id IN $req_ids RETURN count(r) AS cnt",
            jid=judgment_id,
            req_ids=req_ids,
        ).single()["cnt"]
    assert cnt == 5, f"Expected 5 INFORMED_BY → Requirement edges, got {cnt}"


# ── Test: run() also seeds the graph (requirements exist) ────────────────────

def test_run_seeds_graph_requirements(neo4j_driver):
    agent = _make_run_agent(neo4j_driver)
    agent.run(MERIDIAN_SPEC_TEXT)
    req_ids = [r.id for r in MERIDIAN_SPEC.requirements]
    assert _count_nodes(neo4j_driver, "Requirement", req_ids) == 5


# ── Test: run() is idempotent — calling twice still yields exactly 1 Judgment ─

def test_run_is_idempotent_single_judgment(neo4j_driver):
    """run() called twice with same spec must not duplicate the Judgment node."""
    agent = _make_run_agent(neo4j_driver)
    jid1 = agent.run(MERIDIAN_SPEC_TEXT)
    jid2 = agent.run(MERIDIAN_SPEC_TEXT)
    assert jid1 == jid2, "run() must return the same Judgment id on repeated calls with the same spec"
    with neo4j_driver.session() as session:
        cnt = session.run(
            "MATCH (j:Judgment {id: $jid}) RETURN count(j) AS cnt",
            jid=jid1,
        ).single()["cnt"]
    assert cnt == 1, "Judgment node must not be duplicated by a second run() call"
