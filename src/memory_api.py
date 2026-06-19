"""
Shared memory API — single interface over the Neo4j context graph.

Operations:
  INGEST     — write nodes and edges (Task 5)
  RETRIEVE   — role-scoped context query (Task 6)
  RECONCILE  — expire stale edges and replace them (Task 7)
  provenance — write Judgment + ReasoningTrace nodes (Task 8)
  audit_trail — deterministic Req→Judgment chain (Task 9)
"""
from __future__ import annotations

import os
import re
import yaml
from neo4j import Driver
from pydantic import BaseModel

from src.models import BaseNode, BaseEdge

# ─── Schema edge map (loaded once at import) ───────────────────────────────────
# Maps EDGE_TYPE → (from_label, to_label | list[to_label])

def _load_edge_map() -> dict[str, tuple[str, str | list[str]]]:
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.yaml")
    with open(schema_path) as f:
        schema = yaml.safe_load(f)
    result: dict[str, tuple[str, str | list[str]]] = {}
    for edge in schema["edges"]:
        to = edge.get("to_label") or edge["to_labels"]
        result[edge["type"]] = (edge["from_label"], to)
    return result


_EDGE_MAP: dict[str, tuple[str, str | list[str]]] = _load_edge_map()


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _edge_type_from_class(cls: type) -> str:
    """Derive Neo4j relationship type from edge model class name.

    RealizedByEdge  → REALIZED_BY
    CoversCriterionEdge → COVERS_CRITERION
    VerifiesEdge → VERIFIES
    """
    name = cls.__name__
    if name.endswith("Edge"):
        name = name[:-4]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _node_props(node: BaseNode) -> dict:
    """All non-None model fields except id (used as the MERGE key)."""
    return node.model_dump(exclude={"id"}, exclude_none=True)


# ─── INGEST ────────────────────────────────────────────────────────────────────


def ingest_node(driver: Driver, node: BaseNode) -> str:
    """
    MERGE a node on (label, id) and update its properties.

    Returns the node's id.
    Idempotent — calling twice with the same node is safe; a second call with
    updated fields will overwrite existing properties.
    """
    label = type(node).__name__
    props = _node_props(node)
    with driver.session() as session:
        session.run(
            f"MERGE (n:{label} {{id: $id}}) SET n += $props",
            id=node.id,
            props=props,
        )
    return node.id


def ingest_edge(driver: Driver, edge: BaseEdge) -> None:
    """
    MERGE a directed relationship between two nodes identified by from_id / to_id.

    On creation:  sets valid_from from the edge model; valid_to = null.
    On match:     leaves valid_from / valid_to unchanged (idempotent).

    The relationship type and the source-node label are derived from the edge
    model class name and the schema edge map.  The target-node label is omitted
    for INFORMED_BY (which has multiple possible target labels); for all other
    edge types the schema label is used for an efficient index lookup.
    """
    edge_type = _edge_type_from_class(type(edge))
    from_label, to_label_spec = _EDGE_MAP[edge_type]

    if isinstance(to_label_spec, list):
        to_match = "MATCH (b) WHERE b.id = $to_id"
    else:
        to_match = f"MATCH (b:{to_label_spec} {{id: $to_id}})"

    cypher = (
        f"MATCH (a:{from_label} {{id: $from_id}}) "
        f"{to_match} "
        f"MERGE (a)-[r:{edge_type}]->(b) "
        f"ON CREATE SET r.valid_from = $valid_from, r.valid_to = null"
    )
    with driver.session() as session:
        session.run(
            cypher,
            from_id=edge.from_id,
            to_id=edge.to_id,
            valid_from=edge.valid_from,
        )


# ─── MemoryAPI facade (filled in Tasks 6-9) ────────────────────────────────────


class MemoryAPI:
    """Thin facade over the module-level memory functions.  Not yet wired up."""
