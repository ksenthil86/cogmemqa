"""
Integration tests for the Neo4j schema provisioner (Task 3).
Requires a live Neo4j instance — uses the neo4j_driver fixture from conftest.py.
"""
import pytest
from src.provisioner import provision_schema

# All 19 node labels defined in schema.yaml — each has unique_key = id
EXPECTED_CONSTRAINED_LABELS = {
    "Requirement", "AcceptanceCriterion", "Actor",
    "Functionality", "Component",
    "File", "Contract", "Endpoint", "UIElement",
    "Test", "TestRun", "Failure", "Artifact", "Commit", "Scan",
    "Judgment", "ReasoningTrace", "SecurityFinding", "Report",
}

# Properties explicitly marked index: true in schema.yaml (not constraint-backing indexes)
EXPECTED_RANGE_INDEXES = {
    ("Requirement", "title"),
    ("Functionality", "name"),
    ("Component", "name"),
    ("File", "path"),
    ("Endpoint", "path"),
    ("Failure", "error_signature"),
    ("Commit", "sha"),
}


def _get_constraints(driver) -> list[dict]:
    with driver.session() as session:
        return session.run("SHOW CONSTRAINTS").data()


def _get_range_indexes(driver) -> set[tuple[str, str]]:
    """Return (label, property) pairs for explicit RANGE indexes (not constraint-backing)."""
    with driver.session() as session:
        rows = session.run("SHOW INDEXES").data()
    result = set()
    for row in rows:
        if (
            row.get("entityType") == "NODE"
            and row.get("type") == "RANGE"
            and row.get("owningConstraint") is None
        ):
            for label in row.get("labelsOrTypes", []):
                for prop in row.get("properties", []):
                    result.add((label, prop))
    return result


def test_provision_creates_uniqueness_constraints(neo4j_driver):
    provision_schema(neo4j_driver)

    constraints = _get_constraints(neo4j_driver)
    constrained_labels = set()
    for c in constraints:
        if c.get("type") == "UNIQUENESS" and c.get("entityType") == "NODE":
            for label in c.get("labelsOrTypes", []):
                constrained_labels.add(label)

    missing = EXPECTED_CONSTRAINED_LABELS - constrained_labels
    assert not missing, f"Missing uniqueness constraints for labels: {missing}"


def test_provision_creates_range_indexes(neo4j_driver):
    provision_schema(neo4j_driver)

    indexed = _get_range_indexes(neo4j_driver)
    missing = EXPECTED_RANGE_INDEXES - indexed
    assert not missing, f"Missing range indexes: {missing}"


def test_provision_is_idempotent(neo4j_driver):
    provision_schema(neo4j_driver)  # first call
    provision_schema(neo4j_driver)  # second call — must not raise
    # If we reach here with no exception the test passes
    constraints = _get_constraints(neo4j_driver)
    assert len(constraints) >= len(EXPECTED_CONSTRAINED_LABELS)
