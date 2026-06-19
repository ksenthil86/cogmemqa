#!/usr/bin/env python3
"""
Standalone validator for schema/schema.yaml.

Checks:
  - Required top-level keys present (version, layers, nodes, edges)
  - Every node has a label, unique_key, and at least one property
  - Every property has a name and type
  - Every edge has type, from_label (or to_labels / to_label), and properties
  - All from_label / to_label values reference known node labels
  - Every edge declares valid_from and valid_to properties
  - Layer assignments cover every node label with no gaps or extras

Exit 0 on success, exit 1 with error list on failure.
"""
import os
import sys
import yaml


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.yaml")
REQUIRED_TOP_LEVEL = {"version", "layers", "nodes", "edges"}


def validate(schema: dict) -> list[str]:
    errors: list[str] = []

    # Top-level keys
    for key in REQUIRED_TOP_LEVEL:
        if key not in schema:
            errors.append(f"Missing top-level key: '{key}'")
    if errors:
        return errors  # can't continue without these

    known_labels: set[str] = {n["label"] for n in schema["nodes"] if "label" in n}

    # Nodes
    for node in schema["nodes"]:
        label = node.get("label", "<unknown>")
        if "label" not in node:
            errors.append("Node entry missing 'label'")
        if "unique_key" not in node:
            errors.append(f"Node '{label}' missing 'unique_key'")
        props = node.get("properties") or []
        if not props:
            errors.append(f"Node '{label}' has no properties")
        for prop in props:
            if "name" not in prop:
                errors.append(f"Node '{label}': property missing 'name'")
            if "type" not in prop:
                errors.append(
                    f"Node '{label}': property '{prop.get('name', '?')}' missing 'type'"
                )

    # Layers ↔ node labels
    layer_labels: set[str] = set()
    for layer_name, layer_data in schema["layers"].items():
        for lbl in layer_data.get("labels", []):
            if lbl in layer_labels:
                errors.append(f"Label '{lbl}' appears in more than one layer")
            layer_labels.add(lbl)
    for lbl in known_labels - layer_labels:
        errors.append(f"Node '{lbl}' not assigned to any layer")
    for lbl in layer_labels - known_labels:
        errors.append(f"Layer references unknown label '{lbl}'")

    # Edges
    for edge in schema["edges"]:
        etype = edge.get("type", "<unknown>")
        if "type" not in edge:
            errors.append("Edge entry missing 'type'")
        if "from_label" not in edge:
            errors.append(f"Edge '{etype}' missing 'from_label'")
        else:
            if edge["from_label"] not in known_labels:
                errors.append(
                    f"Edge '{etype}': unknown from_label '{edge['from_label']}'"
                )

        to_labels = edge.get("to_labels") or (
            [edge["to_label"]] if "to_label" in edge else []
        )
        if not to_labels:
            errors.append(f"Edge '{etype}' missing 'to_label' or 'to_labels'")
        for lbl in to_labels:
            if lbl not in known_labels:
                errors.append(f"Edge '{etype}': unknown to_label '{lbl}'")

        prop_names = {p["name"] for p in edge.get("properties", []) if "name" in p}
        if "valid_from" not in prop_names:
            errors.append(f"Edge '{etype}' missing 'valid_from' property")
        if "valid_to" not in prop_names:
            errors.append(f"Edge '{etype}' missing 'valid_to' property")

    return errors


def main() -> None:
    if not os.path.exists(SCHEMA_PATH):
        print(f"ERROR: schema file not found: {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(SCHEMA_PATH) as f:
        schema = yaml.safe_load(f)

    errors = validate(schema)

    if errors:
        print(f"Schema validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        sys.exit(1)

    node_count = len(schema["nodes"])
    edge_count = len(schema["edges"])
    layer_count = len(schema["layers"])
    print(
        f"Schema valid ✓  "
        f"({node_count} nodes, {edge_count} edge types, {layer_count} layers)"
    )


if __name__ == "__main__":
    main()
