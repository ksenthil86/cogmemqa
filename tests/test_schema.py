"""
TDD tests for schema/schema.yaml structural validity.
These tests define what a valid schema must contain before the file is written.
"""
import os
import pytest
import yaml

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.yaml")

EXPECTED_NODE_LABELS = {
    # requirements layer
    "Requirement", "AcceptanceCriterion", "Actor",
    # capability layer
    "Functionality", "Component",
    # implementation layer
    "File", "Contract", "Endpoint", "UIElement",
    # evidence layer
    "Test", "TestRun", "Failure", "Artifact", "Commit", "Scan",
    # reasoning layer
    "Judgment", "ReasoningTrace", "SecurityFinding", "Report",
}

EXPECTED_EDGE_TYPES = {
    "REALIZED_BY", "COMPOSED_OF", "IMPLEMENTED_BY",
    "VERIFIES", "COVERS_CRITERION", "AFFECTS",
    "INFORMED_BY", "HAS_STEP", "MODIFIES",
    "INSTANCE_OF", "JUDGED",
}

EXPECTED_LAYERS = {"requirements", "capability", "implementation", "evidence", "reasoning"}


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def known_labels(schema):
    return {n["label"] for n in schema["nodes"]}


def test_schema_file_exists():
    assert os.path.exists(SCHEMA_PATH), "schema/schema.yaml must exist"


def test_required_top_level_keys(schema):
    for key in ("version", "layers", "nodes", "edges"):
        assert key in schema, f"Missing top-level key: '{key}'"


def test_all_expected_layers_present(schema):
    defined = set(schema["layers"].keys())
    assert defined == EXPECTED_LAYERS, f"Layer mismatch: {defined.symmetric_difference(EXPECTED_LAYERS)}"


def test_all_expected_node_labels_present(schema):
    defined = {n["label"] for n in schema["nodes"]}
    missing = EXPECTED_NODE_LABELS - defined
    assert not missing, f"Missing node labels: {missing}"


def test_every_node_has_unique_key(schema):
    for node in schema["nodes"]:
        assert "unique_key" in node, f"Node '{node['label']}' missing 'unique_key'"


def test_every_node_has_properties(schema):
    for node in schema["nodes"]:
        assert node.get("properties"), f"Node '{node['label']}' has empty properties"


def test_every_node_property_has_name_and_type(schema):
    for node in schema["nodes"]:
        for prop in node.get("properties", []):
            assert "name" in prop, f"{node['label']}: property missing 'name'"
            assert "type" in prop, (
                f"{node['label']}: property '{prop.get('name', '?')}' missing 'type'"
            )


def test_all_expected_edge_types_present(schema):
    defined = {e["type"] for e in schema["edges"]}
    missing = EXPECTED_EDGE_TYPES - defined
    assert not missing, f"Missing edge types: {missing}"


def test_edge_from_labels_are_known(schema, known_labels):
    for edge in schema["edges"]:
        label = edge["from_label"]
        assert label in known_labels, (
            f"Edge '{edge['type']}': unknown from_label '{label}'"
        )


def test_edge_to_labels_are_known(schema, known_labels):
    for edge in schema["edges"]:
        targets = edge.get("to_labels") or [edge.get("to_label")]
        for label in targets:
            assert label in known_labels, (
                f"Edge '{edge['type']}': unknown to_label '{label}'"
            )


def test_every_edge_has_temporal_properties(schema):
    for edge in schema["edges"]:
        prop_names = {p["name"] for p in edge.get("properties", [])}
        assert "valid_from" in prop_names, (
            f"Edge '{edge['type']}' missing 'valid_from'"
        )
        assert "valid_to" in prop_names, (
            f"Edge '{edge['type']}' missing 'valid_to'"
        )


def test_layers_cover_all_node_labels(schema):
    """Every node label must appear in exactly one layer."""
    layer_labels: set[str] = set()
    for layer_data in schema["layers"].values():
        layer_labels.update(layer_data["labels"])
    defined = {n["label"] for n in schema["nodes"]}
    diff = defined.symmetric_difference(layer_labels)
    assert not diff, f"Layer/node label mismatch: {diff}"
