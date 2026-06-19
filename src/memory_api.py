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
from src.retrieval_policies import RETRIEVAL_POLICIES

# ─── Schema maps (loaded once at import) ──────────────────────────────────────

def _load_schema() -> dict:
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.yaml")
    with open(schema_path) as f:
        return yaml.safe_load(f)


_SCHEMA = _load_schema()


def _build_edge_map(schema: dict) -> dict[str, tuple[str, str | list[str]]]:
    result: dict[str, tuple[str, str | list[str]]] = {}
    for edge in schema["edges"]:
        to = edge.get("to_label") or edge["to_labels"]
        result[edge["type"]] = (edge["from_label"], to)
    return result


def _build_layer_labels(schema: dict) -> dict[str, list[str]]:
    return {
        layer_name: layer_data["labels"]
        for layer_name, layer_data in schema["layers"].items()
    }


_EDGE_MAP: dict[str, tuple[str, str | list[str]]] = _build_edge_map(_SCHEMA)
_LAYER_LABELS: dict[str, list[str]] = _build_layer_labels(_SCHEMA)


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


# ─── RETRIEVE ─────────────────────────────────────────────────────────────────


def _labels_for_layers(layers: list[str]) -> list[str]:
    """Map a list of layer names to the flat list of Neo4j labels in those layers."""
    result: list[str] = []
    for layer in layers:
        result.extend(_LAYER_LABELS.get(layer, []))
    return result


def retrieve(
    driver: Driver,
    agent_role: str,
    entity_id: str,
    depth: int = 2,
) -> dict:
    """
    Return a role-scoped subgraph centred on *entity_id*.

    Traverses up to *depth* hops in either direction from the start node,
    returning only nodes whose label is in the layers permitted by *agent_role*.
    Also returns all edges between those nodes.

    Return shape::

        {
            "nodes": [{"id": ..., "labels": [...], <props>}, ...],
            "edges": [{"type": ..., "from_id": ..., "to_id": ..., <props>}, ...],
        }

    Raises ValueError for an unrecognised *agent_role*.
    Returns {"nodes": [], "edges": []} when *entity_id* is not in the graph.
    """
    if agent_role not in RETRIEVAL_POLICIES:
        raise ValueError(f"Unknown agent_role: {agent_role!r}")

    allowed_labels = _labels_for_layers(RETRIEVAL_POLICIES[agent_role])

    with driver.session() as session:
        # Step 1 — find reachable nodes within depth hops, filtered by allowed labels.
        # collect() ignores nulls, so OPTIONAL MATCH with no match yields [].
        # List comprehension [{...} | node IN matched] is safe on empty list.
        # depth is an int we control; embedding it in the query string is safe.
        node_rows = session.run(
            f"MATCH (start {{id: $eid}}) "
            f"OPTIONAL MATCH (start)-[*0..{depth}]-(n) "
            f"WHERE any(lbl IN labels(n) WHERE lbl IN $allowed_labels) "
            f"WITH collect(DISTINCT n) AS matched "
            f"RETURN [node IN matched | "
            f"  {{id: node.id, labels: labels(node), props: properties(node)}}] AS nodes",
            eid=entity_id,
            allowed_labels=allowed_labels,
        ).data()

        if not node_rows:
            # MATCH (start) found nothing — entity_id does not exist
            return {"nodes": [], "edges": []}

        raw_nodes: list[dict] = node_rows[0]["nodes"] or []

        if not raw_nodes:
            return {"nodes": [], "edges": []}

        node_ids = [n["id"] for n in raw_nodes]

        # Step 2 — collect all directed edges between the returned nodes.
        edge_rows = session.run(
            "MATCH (a)-[r]->(b) "
            "WHERE a.id IN $node_ids AND b.id IN $node_ids "
            "RETURN collect("
            "  {type: type(r), from_id: a.id, to_id: b.id, props: properties(r)}"
            ") AS edges",
            node_ids=node_ids,
        ).data()

        raw_edges: list[dict] = (edge_rows[0]["edges"] if edge_rows else []) or []

    # ── Flatten into clean dicts ───────────────────────────────────────────────
    nodes = []
    for n in raw_nodes:
        node_dict: dict = {"id": n["id"], "labels": list(n["labels"])}
        node_dict.update(n.get("props", {}))
        nodes.append(node_dict)

    edges = []
    for e in raw_edges:
        edge_dict: dict = {
            "type": e["type"],
            "from_id": e["from_id"],
            "to_id": e["to_id"],
        }
        edge_dict.update(e.get("props", {}))
        edges.append(edge_dict)

    return {"nodes": nodes, "edges": edges}


# ─── MemoryAPI facade (filled in Tasks 7-9) ────────────────────────────────────


class MemoryAPI:
    """Thin facade over the module-level memory functions.  Not yet wired up."""
