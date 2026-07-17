"""
Graph serialization helpers — shared by src/api.py and the chat tools.

Converts neo4j driver objects (Node / Relationship / Path) into the JSON
shape consumed by the NVL frontend:

    {"nodes": [{id, labels, properties}],
     "relationships": [{id, type, startNodeId, endNodeId, properties}]}

Lives in its own module so src/chat_tools.py can reuse the serializers
without importing src/api.py (which would be a circular import).
"""
from __future__ import annotations

from typing import Any


def _sanitize(value: Any) -> Any:
    """Recursively convert neo4j temporal types to ISO strings."""
    try:
        from neo4j.time import DateTime, Date, Time, Duration
        if isinstance(value, (DateTime, Date, Time)):
            return value.iso_format()
        if isinstance(value, Duration):
            return str(value)
    except ImportError:
        pass
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _node_to_dict(node: Any) -> dict:
    """Serialise a neo4j Node to a JSON-safe dict."""
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        "properties": _sanitize(dict(node)),
    }


def _rel_to_dict(rel: Any) -> dict:
    """Serialise a neo4j Relationship to a JSON-safe dict."""
    return {
        "id": rel.element_id,
        "type": rel.type,
        "startNodeId": rel.start_node.element_id,
        "endNodeId": rel.end_node.element_id,
        "properties": _sanitize(dict(rel)),
    }


def _merge_graph(existing: dict, incoming: dict) -> dict:
    """Merge incoming nodes/rels into existing, deduplicating by id."""
    node_ids = {n["id"] for n in existing["nodes"]}
    rel_ids  = {r["id"] for r in existing["relationships"]}

    for node in incoming["nodes"]:
        if node["id"] not in node_ids:
            existing["nodes"].append(node)
            node_ids.add(node["id"])

    for rel in incoming["relationships"]:
        if rel["id"] not in rel_ids:
            existing["relationships"].append(rel)
            rel_ids.add(rel["id"])

    return existing


def extract_graph_from_records(records: Any) -> dict:
    """
    Walk query result records and collect every Node / Relationship / Path
    value into a deduplicated {"nodes": [...], "relationships": [...]} dict.

    Non-graph values (strings, numbers, lists of scalars, ...) are ignored.
    Lists are walked one level deep so `collect(n)` results are picked up.
    """
    from neo4j.graph import Node, Relationship, Path

    nodes: list[dict] = []
    rels:  list[dict] = []
    seen_node_ids: set[str] = set()
    seen_rel_ids:  set[str] = set()

    def _add_node(node: Any) -> None:
        if node.element_id not in seen_node_ids:
            nodes.append(_node_to_dict(node))
            seen_node_ids.add(node.element_id)

    def _add_rel(rel: Any) -> None:
        if rel.element_id not in seen_rel_ids:
            rels.append(_rel_to_dict(rel))
            seen_rel_ids.add(rel.element_id)

    def _walk(value: Any) -> None:
        if isinstance(value, Node):
            _add_node(value)
        elif isinstance(value, Relationship):
            _add_node(value.start_node)
            _add_node(value.end_node)
            _add_rel(value)
        elif isinstance(value, Path):
            for node in value.nodes:
                _add_node(node)
            for rel in value.relationships:
                _add_rel(rel)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    for record in records:
        for value in record.values():
            _walk(value)

    return {"nodes": nodes, "relationships": rels}
