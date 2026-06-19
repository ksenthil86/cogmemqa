"""
Neo4j schema provisioner.

Reads schema/schema.yaml and applies UNIQUENESS constraints and RANGE indexes
to a Neo4j instance. Safe to re-run — all statements use IF NOT EXISTS.

Called by:
  - scripts/provision_schema.py (CLI entry point)
  - tests/test_e2e.py (integration gate)
"""
import os
import re
import yaml
from neo4j import Driver

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.yaml")
_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _safe(name: str, context: str) -> str:
    """Reject names that are not safe to embed in a Cypher identifier."""
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Unsafe identifier in schema ({context}): {name!r}")
    return name


def provision_schema(driver: Driver, schema_path: str | None = None) -> None:
    """
    Apply all constraints and indexes declared in schema.yaml to *driver*.

    Idempotent — uses IF NOT EXISTS on every statement.
    """
    path = schema_path or _SCHEMA_PATH
    with open(path) as f:
        schema = yaml.safe_load(f)

    with driver.session() as session:
        for node in schema["nodes"]:
            label = _safe(node["label"], "node label")
            unique_key = node.get("unique_key")

            if unique_key:
                key = _safe(unique_key, f"{label}.unique_key")
                constraint_name = f"cogmem_{label.lower()}_{key}_unique"
                session.run(
                    f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
                )

            for prop in node.get("properties", []):
                if prop.get("index"):
                    prop_name = _safe(prop["name"], f"{label} property name")
                    index_name = f"cogmem_{label.lower()}_{prop_name}_idx"
                    session.run(
                        f"CREATE INDEX {index_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.{prop_name})"
                    )
