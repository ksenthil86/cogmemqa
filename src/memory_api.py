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
from datetime import datetime, timezone
from neo4j import Driver
from pydantic import BaseModel

from src.models import BaseNode, BaseEdge, Judgment, ReasoningTrace, HasStepEdge, InformedByEdge
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


# ─── RECONCILE ────────────────────────────────────────────────────────────────


def reconcile(driver: Driver, entity_id: str, new_edge: BaseEdge) -> None:
    """
    Expire all active outgoing edges of the same type from *entity_id*, then
    ingest *new_edge* as the current (active) replacement.

    "Active" means valid_to IS NULL.  After this call:
      - Every previously-active edge of that type FROM entity_id has valid_to
        set to the current wall-clock time (the historical record is preserved).
      - new_edge is ingested via ingest_edge (idempotent MERGE + ON CREATE SET).
    """
    edge_type = _edge_type_from_class(type(new_edge))
    with driver.session() as session:
        session.run(
            f"MATCH ({{id: $eid}})-[r:{edge_type}]->() "
            f"WHERE r.valid_to IS NULL "
            f"SET r.valid_to = datetime()",
            eid=entity_id,
        )
    ingest_edge(driver, new_edge)


# ─── PROVENANCE ───────────────────────────────────────────────────────────────


def write_provenance(
    driver: Driver,
    judgment: Judgment,
    trace_steps: list[ReasoningTrace],
    informed_by_ids: list[str],
) -> str:
    """
    Write an auditable provenance record for an agent decision.

    Creates:
      - The Judgment node.
      - One ReasoningTrace node per step in *trace_steps*, linked from the
        Judgment via HAS_STEP edges.
      - One INFORMED_BY edge from the Judgment to each id in *informed_by_ids*
        (the nodes referenced must already exist in the graph).

    All writes are idempotent (MERGE-based via ingest_node / ingest_edge).

    Returns the judgment's id.
    """
    now = datetime.now(tz=timezone.utc)

    ingest_node(driver, judgment)

    for trace in trace_steps:
        ingest_node(driver, trace)
        ingest_edge(driver, HasStepEdge(
            from_id=judgment.id,
            to_id=trace.id,
            valid_from=now,
        ))

    for target_id in informed_by_ids:
        ingest_edge(driver, InformedByEdge(
            from_id=judgment.id,
            to_id=target_id,
            valid_from=now,
        ))

    return judgment.id


# ─── COVERAGE GAPS ────────────────────────────────────────────────────────────


def coverage_gaps(driver: Driver) -> list[dict]:
    """
    Return all AcceptanceCriterion nodes not yet covered by any Test.

    A criterion is "covered" when a Test node points to it via a
    COVERS_CRITERION edge.  Returns a list of dicts with keys:
      ac_id     — the AcceptanceCriterion's id
      statement — its statement text
    Returns [] when every criterion has at least one covering Test.
    """
    with driver.session() as session:
        rows = session.run(
            "MATCH (ac:AcceptanceCriterion) "
            "WHERE NOT (:Test)-[:COVERS_CRITERION]->(ac) "
            "RETURN ac.id AS ac_id, ac.statement AS statement"
        ).data()
    return rows


# ─── COVERAGE SUMMARY ────────────────────────────────────────────────────────


def coverage_summary(driver: Driver) -> dict:
    """
    Return aggregate test-execution coverage metrics.

    "Covered" means the AcceptanceCriterion has at least one TestRun with
    outcome="pass" reachable via:
      (TestRun)-[:INSTANCE_OF]->(Test)-[:COVERS_CRITERION]->(AcceptanceCriterion)

    A failing TestRun does NOT count.

    Returns a dict with keys:
      total_ac     — total AcceptanceCriterion nodes in the graph
      covered_ac   — ACs with ≥1 passing TestRun
      coverage_pct — covered_ac / total_ac * 100, or 0.0 when total_ac == 0
    """
    with driver.session() as session:
        row = session.run(
            "MATCH (ac:AcceptanceCriterion) "
            "OPTIONAL MATCH (tr:TestRun {outcome: 'pass'})-[:INSTANCE_OF]->(t:Test) "
            "              -[:COVERS_CRITERION]->(ac) "
            "RETURN "
            "  count(DISTINCT ac)                                          AS total_ac, "
            "  count(DISTINCT CASE WHEN tr IS NOT NULL THEN ac END)        AS covered_ac"
        ).single()

    total   = row["total_ac"]
    covered = row["covered_ac"]
    pct     = (covered / total * 100.0) if total > 0 else 0.0
    return {"total_ac": total, "covered_ac": covered, "coverage_pct": pct}


# ─── SECURITY SUMMARY ─────────────────────────────────────────────────────────


def security_summary(driver: Driver) -> dict:
    """
    Return aggregate open-security-finding metrics.

    Only SecurityFinding nodes with status="open" are counted.
    Closed findings are excluded.

    Returns a dict with keys:
      total_open   — total open SecurityFinding nodes
      by_severity  — {"low": L, "medium": M, "high": H}
                     all three keys are always present; missing severities = 0
    """
    with driver.session() as session:
        rows = session.run(
            "MATCH (sf:SecurityFinding {status: 'open'}) "
            "RETURN sf.severity AS sev, count(sf) AS cnt"
        ).data()

    by_severity: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    for row in rows:
        sev = (row["sev"] or "").lower()
        if sev in by_severity:
            by_severity[sev] = row["cnt"]

    total_open = sum(by_severity.values())
    return {"total_open": total_open, "by_severity": by_severity}


# ─── IMPACT LOOKUP ────────────────────────────────────────────────────────────


def impact_lookup(driver: Driver, file_paths: list[str]) -> list[dict]:
    """
    Given a list of changed file paths, return the upstream impact chain for
    each path that has a Component -[IMPLEMENTED_BY]-> File link in the graph.

    Traverses upward:
      (File) <-[IMPLEMENTED_BY]- (Component)
             <-[COMPOSED_OF]-   (Functionality)
             <-[REALIZED_BY]-   (Requirement)

    Returns a list of dicts, one per matched (file_path, component) pair:
      {
        "file_path":       str,
        "component_id":    str,
        "functionality_id": str,
        "requirement_id":  str,
      }

    Paths with no IMPLEMENTED_BY edge are silently skipped (result is []).
    Uses DISTINCT to avoid duplicate rows.
    """
    with driver.session() as session:
        rows = session.run(
            "UNWIND $paths AS path "
            "MATCH (f:File {path: path}) "
            "MATCH (comp:Component)-[:IMPLEMENTED_BY]->(f) "
            "MATCH (func:Functionality)-[:COMPOSED_OF]->(comp) "
            "MATCH (req:Requirement)-[:REALIZED_BY]->(func) "
            "RETURN DISTINCT "
            "  f.path    AS file_path, "
            "  comp.id   AS component_id, "
            "  func.id   AS functionality_id, "
            "  req.id    AS requirement_id",
            paths=file_paths,
        ).data()
    return rows


# ─── AUDIT TRAIL ──────────────────────────────────────────────────────────────


def audit_trail(driver: Driver, requirement_id: str) -> list[dict]:
    """
    Return the deterministic audit chain anchored at *requirement_id*.

    Traverses the full provenance path in a single Cypher MATCH:

      (Requirement) -[REALIZED_BY]->  (Functionality)
                    -[COMPOSED_OF]->  (Component)
                    -[IMPLEMENTED_BY]-> (File) <-[MODIFIES]- (Commit)
      (Test)        -[VERIFIES]->     (Functionality)
      (Judgment)    -[INFORMED_BY]->  (Requirement)

    Each row in the result is a dict with keys:
      requirement, functionality, component, file, test, judgment

    Returns [] when *requirement_id* does not exist or no complete path exists.
    """
    with driver.session() as session:
        rows = session.run(
            "MATCH (r:Requirement {id: $req_id})"
            "-[:REALIZED_BY]->(func:Functionality)"
            "-[:COMPOSED_OF]->(comp:Component)"
            "-[:IMPLEMENTED_BY]->(f:File)"
            "<-[:MODIFIES]-(:Commit),"
            " (t:Test)-[:VERIFIES]->(func),"
            " (j:Judgment)-[:INFORMED_BY]->(r)"
            " RETURN r.id    AS requirement,"
            "        func.id AS functionality,"
            "        comp.id AS component,"
            "        f.id    AS file,"
            "        t.id    AS test,"
            "        j.id    AS judgment",
            req_id=requirement_id,
        ).data()
    return rows


# ─── MemoryAPI facade (Tasks 7-9 complete) ────────────────────────────────────


class MemoryAPI:
    """Thin facade over the module-level memory functions.  Not yet wired up."""
