"""
Unit and integration tests for the LLM client and BaseAgent scaffold (Task 1).

Unit tests: no Neo4j, no live LLM.
Integration tests: use neo4j_driver fixture, still no live LLM.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.memory_api import ingest_node, ingest_edge
from src.models import (
    Requirement, Functionality,
    Judgment, ReasoningTrace,
    RealizedByEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


# ── Unit tests: LLM client ────────────────────────────────────────────────────

def test_get_gemini_client_raises_without_api_key():
    """get_gemini_client() must raise ValueError when GEMINI_API_KEY is unset."""
    from src.llm import get_gemini_client
    get_gemini_client.cache_clear()
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            get_gemini_client()
    get_gemini_client.cache_clear()


def test_call_llm_uses_injected_fn():
    """call_llm_with is a convenience that calls an arbitrary callable."""
    from src.llm import call_llm_with
    stub = lambda prompt: f"response-to: {prompt}"  # noqa: E731
    result = call_llm_with("hello", llm_fn=stub)
    assert result == "response-to: hello"


# ── Unit tests: BaseAgent instantiation ───────────────────────────────────────

def test_base_agent_stores_role_and_driver():
    from src.agent_base import BaseAgent
    agent = BaseAgent(role="supervisor", driver=None, llm_fn=lambda p: "ok")
    assert agent.role == "supervisor"
    assert agent.driver is None


def test_base_agent_llm_fn_is_callable():
    from src.agent_base import BaseAgent
    stub_fn = lambda p: f"stub:{p}"  # noqa: E731
    agent = BaseAgent(role="supervisor", driver=None, llm_fn=stub_fn)
    assert agent.llm_fn("x") == "stub:x"


def test_base_agent_llm_fn_defaults_to_call_llm():
    """When no llm_fn is provided, the agent uses the module-level call_llm."""
    from src.agent_base import BaseAgent
    from src.llm import call_llm
    agent = BaseAgent(role="supervisor", driver=None)
    assert agent.llm_fn is call_llm


# ── Integration tests: BaseAgent.retrieve() ───────────────────────────────────

def test_base_agent_retrieve_delegates_to_memory_api(neo4j_driver):
    """BaseAgent.retrieve() must return the same result as memory_api.retrieve()."""
    from src.agent_base import BaseAgent
    from src.memory_api import retrieve

    ns = uuid.uuid4().hex[:8]
    req_id = f"req-{ns}"
    ingest_node(neo4j_driver, Requirement(id=req_id, title="Test req"))

    agent = BaseAgent(role="supervisor", driver=neo4j_driver, llm_fn=lambda p: "")
    result = agent.retrieve(req_id, depth=1)

    direct = retrieve(neo4j_driver, "supervisor", req_id, depth=1)
    assert result == direct


def test_base_agent_retrieve_respects_role_scoping(neo4j_driver):
    """Retrieve through requirements_parser role must not return reasoning layer."""
    from src.agent_base import BaseAgent

    ns = uuid.uuid4().hex[:8]
    req_id  = f"req-{ns}"
    func_id = f"func-{ns}"
    ingest_node(neo4j_driver, Requirement(id=req_id, title="R"))
    ingest_node(neo4j_driver, Functionality(id=func_id, name="F"))
    ingest_edge(neo4j_driver, RealizedByEdge(from_id=req_id, to_id=func_id, valid_from=NOW))

    agent = BaseAgent(role="requirements_parser", driver=neo4j_driver, llm_fn=lambda p: "")
    result = agent.retrieve(req_id, depth=2)
    labels = {lbl for n in result["nodes"] for lbl in n["labels"]}
    assert "Judgment" not in labels, "requirements_parser must not see Reasoning layer"
    assert "Requirement" in labels


def test_base_agent_retrieve_unknown_entity_returns_empty(neo4j_driver):
    from src.agent_base import BaseAgent
    agent = BaseAgent(role="supervisor", driver=neo4j_driver, llm_fn=lambda p: "")
    result = agent.retrieve("nonexistent-xyz", depth=2)
    assert result == {"nodes": [], "edges": []}


# ── Integration tests: BaseAgent.write_provenance() ───────────────────────────

def test_base_agent_write_provenance_returns_judgment_id(neo4j_driver):
    from src.agent_base import BaseAgent

    ns = uuid.uuid4().hex[:8]
    j = Judgment(id=f"j-{ns}", agent_role="supervisor", label="TEST")

    agent = BaseAgent(role="supervisor", driver=neo4j_driver, llm_fn=lambda p: "")
    result = agent.write_provenance(j, [], [])
    assert result == j.id


def test_base_agent_write_provenance_persists_judgment_with_traces(neo4j_driver):
    from src.agent_base import BaseAgent

    ns = uuid.uuid4().hex[:8]
    j  = Judgment(id=f"j-{ns}",  agent_role="supervisor", label="PASS")
    tr = ReasoningTrace(id=f"tr-{ns}", agent_role="supervisor",
                        decision="All good", timestamp=NOW)

    req_id = f"req-{ns}"
    ingest_node(neo4j_driver, Requirement(id=req_id, title="R"))

    agent = BaseAgent(role="supervisor", driver=neo4j_driver, llm_fn=lambda p: "")
    agent.write_provenance(j, [tr], informed_by_ids=[req_id])

    with neo4j_driver.session() as session:
        has_step = session.run(
            "MATCH ({id: $jid})-[:HAS_STEP]->() RETURN count(*) AS cnt",
            jid=j.id,
        ).single()["cnt"]
        informed = session.run(
            "MATCH ({id: $jid})-[:INFORMED_BY]->() RETURN count(*) AS cnt",
            jid=j.id,
        ).single()["cnt"]
    assert has_step == 1
    assert informed == 1
