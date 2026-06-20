"""
Pydantic v2 domain models for the CoGMEM-QA four-layer context graph.

Every node model inherits from BaseNode (validates id is non-empty).
Every edge model inherits from BaseEdge (valid_from required, valid_to defaults None).

19 node models  ·  11 edge models
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ─── Base classes ──────────────────────────────────────────────────────────────


class BaseNode(BaseModel):
    """Common base for all graph node models. Validates that id is non-empty."""

    id: str

    @field_validator("id")
    @classmethod
    def id_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id must be a non-empty string")
        return v


class BaseEdge(BaseModel):
    """Common base for all graph edge models. Carries bi-temporal validity interval."""

    from_id: str
    to_id: str
    valid_from: datetime
    valid_to: Optional[datetime] = None


# ─── Requirements layer ────────────────────────────────────────────────────────


class Requirement(BaseNode):
    title: str
    priority: Optional[str] = None
    reg_control: Optional[str] = None


class AcceptanceCriterion(BaseNode):
    statement: str
    status: Optional[str] = None


class Actor(BaseNode):
    name: str
    role: Optional[str] = None


# ─── Capability layer ──────────────────────────────────────────────────────────


class Functionality(BaseNode):
    name: str
    description: Optional[str] = None
    status: Optional[str] = None


class Component(BaseNode):
    name: str
    status: Optional[str] = None


# ─── Implementation layer ──────────────────────────────────────────────────────


class File(BaseNode):
    path: str
    language: Optional[str] = None
    module: Optional[str] = None


class Contract(BaseNode):
    name: str


class Endpoint(BaseNode):
    path: str
    method: str


class UIElement(BaseNode):
    name: str
    type: Optional[str] = None


# ─── Evidence layer ────────────────────────────────────────────────────────────


class Test(BaseNode):
    name: str
    type: Optional[str] = None
    status: Optional[str] = None


class TestRun(BaseNode):
    outcome: str
    timestamp: datetime
    duration: Optional[float] = None


class Failure(BaseNode):
    error_signature: str
    label: Optional[str] = None
    confidence: Optional[float] = None


class Artifact(BaseNode):
    type: str
    uri: str
    hash: Optional[str] = None


class Commit(BaseNode):
    sha: str
    message: str
    timestamp: datetime
    author: Optional[str] = None


class Scan(BaseNode):
    tool: str
    timestamp: datetime
    commit_sha: Optional[str] = None


# ─── Reasoning layer ───────────────────────────────────────────────────────────


class Judgment(BaseNode):
    agent_role: str
    label: str
    confidence: Optional[float] = None
    reasoning: Optional[str] = None


class ReasoningTrace(BaseNode):
    agent_role: str
    decision: str
    timestamp: datetime


class SecurityFinding(BaseNode):
    severity: str
    title: str
    status: Optional[str] = None


class Report(BaseNode):
    summary: str
    created_at: datetime
    coverage_pct: float = 0.0
    open_findings_count: int = 0
    severity_breakdown: str = "{}"


# ─── Edge models ───────────────────────────────────────────────────────────────
# One model per relationship type defined in schema.yaml.
# All carry valid_from / valid_to from BaseEdge.


class RealizedByEdge(BaseEdge):
    """Requirement -[REALIZED_BY]-> Functionality"""


class ComposedOfEdge(BaseEdge):
    """Functionality -[COMPOSED_OF]-> Component"""


class ImplementedByEdge(BaseEdge):
    """Component -[IMPLEMENTED_BY]-> File"""


class VerifiesEdge(BaseEdge):
    """Test -[VERIFIES]-> Functionality"""


class CoversCriterionEdge(BaseEdge):
    """Test -[COVERS_CRITERION]-> AcceptanceCriterion"""


class AffectsEdge(BaseEdge):
    """SecurityFinding -[AFFECTS]-> Component"""


class InformedByEdge(BaseEdge):
    """Judgment -[INFORMED_BY]-> (Requirement | AcceptanceCriterion | Functionality | Component | File)"""


class HasStepEdge(BaseEdge):
    """Judgment -[HAS_STEP]-> ReasoningTrace"""


class ModifiesEdge(BaseEdge):
    """Commit -[MODIFIES]-> File"""


class InstanceOfEdge(BaseEdge):
    """TestRun -[INSTANCE_OF]-> Test"""


class JudgedEdge(BaseEdge):
    """AcceptanceCriterion -[JUDGED]-> Judgment"""
