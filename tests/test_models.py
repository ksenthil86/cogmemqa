"""
Unit tests for Pydantic domain models (Task 4).
Pure unit tests — no Neo4j required.
"""
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

# ── Node imports ──────────────────────────────────────────────────────────────
from src.models import (
    # requirements layer
    Requirement, AcceptanceCriterion, Actor,
    # capability layer
    Functionality, Component,
    # implementation layer
    File, Contract, Endpoint, UIElement,
    # evidence layer
    Test, TestRun, Failure, Artifact, Commit, Scan,
    # reasoning layer
    Judgment, ReasoningTrace, SecurityFinding, Report,
    # base classes
    BaseNode, BaseEdge,
    # edge models
    RealizedByEdge, ComposedOfEdge, ImplementedByEdge,
    VerifiesEdge, CoversCriterionEdge, AffectsEdge,
    InformedByEdge, HasStepEdge, ModifiesEdge,
    InstanceOfEdge, JudgedEdge,
)

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


# ── Test 1: valid models pass ─────────────────────────────────────────────────

def test_requirement_valid():
    r = Requirement(id="REQ-001", title="Account opening")
    assert r.id == "REQ-001"
    assert r.title == "Account opening"
    assert r.priority is None
    assert r.reg_control is None


def test_requirement_with_all_fields():
    r = Requirement(id="REQ-002", title="KYC", priority="P0", reg_control="AML-4")
    assert r.reg_control == "AML-4"


def test_test_model_valid():
    t = Test(id="TEST-001", name="test_login_success")
    assert t.id == "TEST-001"
    assert t.type is None
    assert t.status is None


def test_judgment_valid():
    j = Judgment(id="JDG-001", agent_role="functional_tester", label="env_issue")
    assert j.confidence is None
    assert j.reasoning is None


def test_testrun_valid():
    tr = TestRun(id="RUN-001", outcome="passed", timestamp=NOW)
    assert tr.duration is None


def test_commit_valid():
    c = Commit(id="CMT-001", sha="abc123", message="feat: account opening", timestamp=NOW)
    assert c.author is None


def test_all_node_labels_instantiate():
    """Smoke-test: every node model can be constructed with minimal required fields."""
    models_and_fields = [
        (Requirement,       {"id": "r1", "title": "T"}),
        (AcceptanceCriterion, {"id": "ac1", "statement": "S"}),
        (Actor,             {"id": "a1", "name": "N"}),
        (Functionality,     {"id": "f1", "name": "N"}),
        (Component,         {"id": "c1", "name": "N"}),
        (File,              {"id": "fi1", "path": "/a.py"}),
        (Contract,          {"id": "ct1", "name": "N"}),
        (Endpoint,          {"id": "ep1", "path": "/api", "method": "GET"}),
        (UIElement,         {"id": "ui1", "name": "N"}),
        (Test,              {"id": "t1", "name": "N"}),
        (TestRun,           {"id": "tr1", "outcome": "passed", "timestamp": NOW}),
        (Failure,           {"id": "fl1", "error_signature": "NullPointer"}),
        (Artifact,          {"id": "ar1", "type": "screenshot", "uri": "s3://x"}),
        (Commit,            {"id": "cm1", "sha": "abc", "message": "msg", "timestamp": NOW}),
        (Scan,              {"id": "sc1", "tool": "bandit", "timestamp": NOW}),
        (Judgment,          {"id": "jd1", "agent_role": "tester", "label": "ok"}),
        (ReasoningTrace,    {"id": "rt1", "agent_role": "tester", "decision": "D", "timestamp": NOW}),
        (SecurityFinding,   {"id": "sf1", "severity": "HIGH", "title": "SQLi"}),
        (Report,            {"id": "rp1", "summary": "S", "created_at": NOW}),
    ]
    for ModelClass, fields in models_and_fields:
        instance = ModelClass(**fields)
        assert instance.id == fields["id"]


# ── Test 2: missing required field raises ValidationError ─────────────────────

def test_requirement_missing_title_raises():
    with pytest.raises(ValidationError) as exc_info:
        Requirement(id="REQ-003")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("title",) for e in errors)


def test_endpoint_missing_method_raises():
    with pytest.raises(ValidationError):
        Endpoint(id="EP-001", path="/api/v1/login")


def test_testrun_missing_timestamp_raises():
    with pytest.raises(ValidationError):
        TestRun(id="RUN-002", outcome="failed")


def test_judgment_missing_label_raises():
    with pytest.raises(ValidationError):
        Judgment(id="JDG-002", agent_role="supervisor")


# ── Test 3: id must be a non-empty string ─────────────────────────────────────

def test_empty_id_raises():
    with pytest.raises(ValidationError) as exc_info:
        Requirement(id="", title="T")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("id",) for e in errors)


def test_whitespace_only_id_raises():
    with pytest.raises(ValidationError):
        Requirement(id="   ", title="T")


# ── Test 4: edge model defaults valid_to to None ──────────────────────────────

def test_edge_valid_to_defaults_to_none():
    edge = RealizedByEdge(from_id="REQ-001", to_id="FUNC-001", valid_from=NOW)
    assert edge.valid_to is None


def test_edge_valid_to_can_be_set():
    later = datetime(2026, 12, 31, tzinfo=timezone.utc)
    edge = RealizedByEdge(
        from_id="REQ-001", to_id="FUNC-001",
        valid_from=NOW, valid_to=later,
    )
    assert edge.valid_to == later


def test_all_edge_models_default_valid_to_none():
    """Every edge model must default valid_to to None."""
    edge_instances = [
        RealizedByEdge(from_id="a", to_id="b", valid_from=NOW),
        ComposedOfEdge(from_id="a", to_id="b", valid_from=NOW),
        ImplementedByEdge(from_id="a", to_id="b", valid_from=NOW),
        VerifiesEdge(from_id="a", to_id="b", valid_from=NOW),
        CoversCriterionEdge(from_id="a", to_id="b", valid_from=NOW),
        AffectsEdge(from_id="a", to_id="b", valid_from=NOW),
        InformedByEdge(from_id="a", to_id="b", valid_from=NOW),
        HasStepEdge(from_id="a", to_id="b", valid_from=NOW),
        ModifiesEdge(from_id="a", to_id="b", valid_from=NOW),
        InstanceOfEdge(from_id="a", to_id="b", valid_from=NOW),
        JudgedEdge(from_id="a", to_id="b", valid_from=NOW),
    ]
    for edge in edge_instances:
        assert edge.valid_to is None, f"{type(edge).__name__}.valid_to should default to None"


def test_edge_missing_valid_from_raises():
    with pytest.raises(ValidationError):
        RealizedByEdge(from_id="a", to_id="b")
