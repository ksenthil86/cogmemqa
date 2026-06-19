"""
Unit tests for ParsedSpec Pydantic models and the Meridian banking fixture (Task 2).
No Neo4j or LLM required.
"""
import json
from pathlib import Path
from typing import Optional

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MERIDIAN_JSON = FIXTURES_DIR / "meridian_parsed.json"


# ── Test 1: imports ────────────────────────────────────────────────────────────

def test_models_import_cleanly():
    from src.agents.models import ParsedActor, ParsedAC, ParsedRequirement, ParsedSpec
    assert all([ParsedActor, ParsedAC, ParsedRequirement, ParsedSpec])


# ── Test 2: individual model validation ───────────────────────────────────────

def test_parsed_actor_valid():
    from src.agents.models import ParsedActor
    actor = ParsedActor(id="actor-customer", name="Customer", role="account_holder")
    assert actor.id == "actor-customer"
    assert actor.name == "Customer"


def test_parsed_actor_role_optional():
    from src.agents.models import ParsedActor
    actor = ParsedActor(id="actor-anon", name="Anonymous")
    assert actor.role is None


def test_parsed_ac_valid():
    from src.agents.models import ParsedAC
    ac = ParsedAC(id="ac-ao-1", statement="User can create account")
    assert ac.statement == "User can create account"


def test_parsed_ac_actor_role_optional():
    from src.agents.models import ParsedAC
    ac = ParsedAC(id="ac-ao-1", statement="System does X")
    assert ac.actor_role is None


def test_parsed_requirement_valid():
    from src.agents.models import ParsedAC, ParsedRequirement
    req = ParsedRequirement(
        id="req-account-opening",
        title="Account Opening",
        priority="P0",
        acceptance_criteria=[
            ParsedAC(id="ac-ao-1", statement="Customer can register"),
            ParsedAC(id="ac-ao-2", statement="Duplicate is rejected"),
        ],
        functionality_id="func-account-opening",
        functionality_name="Account Opening Flow",
        component_id="comp-account-opening",
        component_name="AccountController",
    )
    assert req.id == "req-account-opening"
    assert len(req.acceptance_criteria) == 2


def test_parsed_requirement_reg_control_optional():
    from src.agents.models import ParsedRequirement
    req = ParsedRequirement(
        id="req-x",
        title="X",
        priority="P1",
        acceptance_criteria=[],
        functionality_id="func-x",
        functionality_name="X Flow",
        component_id="comp-x",
        component_name="XController",
    )
    assert req.reg_control is None


def test_parsed_requirement_missing_title_raises():
    from pydantic import ValidationError
    from src.agents.models import ParsedRequirement
    with pytest.raises(ValidationError):
        ParsedRequirement(
            id="req-x",
            priority="P0",
            acceptance_criteria=[],
            functionality_id="func-x",
            functionality_name="X",
            component_id="comp-x",
            component_name="X",
        )


def test_parsed_spec_valid():
    from src.agents.models import ParsedAC, ParsedActor, ParsedRequirement, ParsedSpec
    spec = ParsedSpec(
        actors=[ParsedActor(id="actor-1", name="User")],
        requirements=[
            ParsedRequirement(
                id="req-1",
                title="T",
                priority="P0",
                acceptance_criteria=[ParsedAC(id="ac-1", statement="S")],
                functionality_id="func-1",
                functionality_name="F",
                component_id="comp-1",
                component_name="C",
            )
        ],
    )
    assert len(spec.requirements) == 1


# ── Test 3: Meridian fixture loads and validates ───────────────────────────────

def test_meridian_json_file_exists():
    assert MERIDIAN_JSON.exists(), f"Meridian fixture not found at {MERIDIAN_JSON}"


def test_meridian_parsed_json_loads_as_parsed_spec():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    assert isinstance(spec, ParsedSpec)


def test_meridian_spec_has_five_requirements():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    assert len(spec.requirements) == 5


def test_meridian_spec_has_ten_acceptance_criteria():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    total_acs = sum(len(r.acceptance_criteria) for r in spec.requirements)
    assert total_acs == 10, f"Expected 10 ACs total, got {total_acs}"


def test_meridian_spec_has_two_actors():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    assert len(spec.actors) == 2


def test_meridian_spec_has_five_functionalities():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    func_ids = {r.functionality_id for r in spec.requirements}
    assert len(func_ids) == 5, f"Expected 5 distinct functionality ids, got {len(func_ids)}"


def test_meridian_spec_has_five_components():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    comp_ids = {r.component_id for r in spec.requirements}
    assert len(comp_ids) == 5


def test_meridian_requirement_ids_are_unique():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    ids = [r.id for r in spec.requirements]
    assert len(ids) == len(set(ids)), "Requirement ids must be unique"


def test_meridian_ac_ids_are_globally_unique():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    ac_ids = [ac.id for r in spec.requirements for ac in r.acceptance_criteria]
    assert len(ac_ids) == len(set(ac_ids)), "AC ids must be globally unique"


def test_meridian_each_requirement_has_exactly_two_acs():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    for req in spec.requirements:
        assert len(req.acceptance_criteria) == 2, (
            f"{req.id} has {len(req.acceptance_criteria)} ACs, expected 2"
        )


def test_meridian_spec_markdown_exists():
    md_path = FIXTURES_DIR / "meridian_spec.md"
    assert md_path.exists(), f"Meridian spec markdown not found at {md_path}"


def test_meridian_priorities_are_valid():
    from src.agents.models import ParsedSpec
    spec = ParsedSpec.model_validate_json(MERIDIAN_JSON.read_text())
    valid = {"P0", "P1", "P2"}
    for req in spec.requirements:
        assert req.priority in valid, f"{req.id} has invalid priority {req.priority!r}"
