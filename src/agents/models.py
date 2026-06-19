"""
Pydantic v2 models for agent-parsed artefacts.

ParsedSpec is the structured output of the Requirements Parser Agent (B3).
ProposedTest is the per-criterion output of the Test Case Generator Agent (B4).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Requirements Parser output (B3) ───────────────────────────────────────────


class ParsedActor(BaseModel):
    """An actor / stakeholder extracted from the product spec."""
    id: str
    name: str
    role: Optional[str] = None


class ParsedAC(BaseModel):
    """One acceptance criterion extracted from the product spec."""
    id: str
    statement: str
    actor_role: Optional[str] = None


class ParsedRequirement(BaseModel):
    """One requirement with its derived capability nodes."""
    id: str
    title: str
    priority: str
    reg_control: Optional[str] = None
    acceptance_criteria: list[ParsedAC]
    # Derived Capability layer nodes (one-to-one with requirement in this sprint)
    functionality_id: str
    functionality_name: str
    component_id: str
    component_name: str


class ParsedSpec(BaseModel):
    """Full structured output from parsing a product spec document."""
    actors: list[ParsedActor]
    requirements: list[ParsedRequirement]


# ── Test Case Generator output (B4) ───────────────────────────────────────────


class ProposedTest(BaseModel):
    """One test specification proposed by the Test Case Generator."""
    ac_id: str
    name: str
    type: str           # "api" | "ui" | "unit"
    verifies_functionality_id: str
    description: Optional[str] = None
