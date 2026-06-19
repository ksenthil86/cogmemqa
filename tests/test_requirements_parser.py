"""
Unit tests for RequirementsParserAgent.parse_spec() (Task 3).
No Neo4j, no live LLM — stub llm_fn used throughout.
"""
import json
from pathlib import Path

import pytest

MERIDIAN_JSON = Path(__file__).parent.parent / "fixtures" / "meridian_parsed.json"
MERIDIAN_RAW = MERIDIAN_JSON.read_text()


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
