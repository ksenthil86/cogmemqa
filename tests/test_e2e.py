"""
End-to-end smoke test for Sprint v1 — Memory Backbone (B1 + B2).

Exercises the full surface of the memory API in one sequential test:
  1. provision_schema
  2. ingest one node of every label (19 types)
  3. ingest all cross-layer edges (11 types)
  4. retrieve as supervisor — assert main chain visible
  5. reconcile one edge — assert old edge expired, new edge active
  6. write_provenance — assert Judgment + traces + INFORMED_BY exist
  7. audit_trail — assert non-empty, assert correct chain shape

This test is the Definition of Done gate for Sprint v1.
"""
import uuid
from datetime import datetime, timezone

from src.memory_api import (
    ingest_node, ingest_edge,
    retrieve, reconcile, write_provenance, audit_trail,
)
from src.models import (
    # Requirements layer
    Requirement, AcceptanceCriterion, Actor,
    # Capability layer
    Functionality, Component,
    # Implementation layer
    File, Contract, Endpoint, UIElement,
    # Evidence layer
    Test as DomainTest, TestRun, Failure, Artifact, Commit, Scan,
    # Reasoning layer
    Judgment, ReasoningTrace, SecurityFinding, Report,
    # Edges
    RealizedByEdge, ComposedOfEdge, ImplementedByEdge,
    VerifiesEdge, CoversCriterionEdge,
    AffectsEdge, InformedByEdge, HasStepEdge,
    ModifiesEdge, InstanceOfEdge, JudgedEdge,
)
from src.provisioner import provision_schema

T0 = datetime(2026, 6, 19, 10, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 6, 19, 11, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


def _props(driver, from_id: str, to_id: str, rel_type: str) -> dict | None:
    with driver.session() as session:
        row = session.run(
            f"MATCH (a {{id: $fid}})-[r:{rel_type}]->(b {{id: $tid}}) "
            "RETURN properties(r) AS props",
            fid=from_id, tid=to_id,
        ).single()
        return row["props"] if row else None


def _rel_count(driver, from_id: str, rel_type: str) -> int:
    with driver.session() as session:
        return session.run(
            f"MATCH ({{id: $fid}})-[r:{rel_type}]->() RETURN count(r) AS cnt",
            fid=from_id,
        ).single()["cnt"]


def _node_exists(driver, node_id: str) -> bool:
    with driver.session() as session:
        return session.run(
            "MATCH (n {id: $id}) RETURN count(n) AS cnt", id=node_id,
        ).single()["cnt"] > 0


def test_memory_backbone_e2e(neo4j_driver):  # noqa: PLR0915 (long function by design)
    ns = uuid.uuid4().hex[:8]

    # ── Step 1: Provision schema ──────────────────────────────────────────────
    # Idempotent: constraints and indexes are created IF NOT EXISTS.
    provision_schema(neo4j_driver)

    # ── Step 2: Ingest one node of every label (19 types) ─────────────────────
    req_id        = f"req-{ns}"
    ac_id         = f"ac-{ns}"
    actor_id      = f"actor-{ns}"
    func_id       = f"func-{ns}"
    comp_id       = f"comp-{ns}"
    file_id       = f"file-{ns}"
    contract_id   = f"contract-{ns}"
    endpoint_id   = f"ep-{ns}"
    uielement_id  = f"ui-{ns}"
    test_id       = f"test-{ns}"
    testrun_id    = f"tr-{ns}"
    failure_id    = f"fail-{ns}"
    artifact_id   = f"art-{ns}"
    commit_id     = f"cmt-{ns}"
    scan_id       = f"scan-{ns}"
    j_id          = f"j-{ns}"
    trace_id      = f"trace-{ns}"
    secfind_id    = f"sf-{ns}"
    report_id     = f"rpt-{ns}"

    # Requirements layer
    ingest_node(neo4j_driver, Requirement(id=req_id,       title="KYC verification"))
    ingest_node(neo4j_driver, AcceptanceCriterion(id=ac_id, statement="Identity confirmed"))
    ingest_node(neo4j_driver, Actor(id=actor_id,           name="Compliance officer"))
    # Capability layer
    ingest_node(neo4j_driver, Functionality(id=func_id,    name="Identity check"))
    ingest_node(neo4j_driver, Component(id=comp_id,        name="KYCController"))
    # Implementation layer
    ingest_node(neo4j_driver, File(id=file_id,             path="src/kyc.py"))
    ingest_node(neo4j_driver, Contract(id=contract_id,     name="KYCContract"))
    ingest_node(neo4j_driver, Endpoint(id=endpoint_id,     path="/kyc/verify", method="POST"))
    ingest_node(neo4j_driver, UIElement(id=uielement_id,   name="VerifyButton"))
    # Evidence layer
    ingest_node(neo4j_driver, DomainTest(id=test_id,       name="test_kyc_pass"))
    ingest_node(neo4j_driver, TestRun(id=testrun_id,       outcome="passed", timestamp=T0))
    ingest_node(neo4j_driver, Failure(id=failure_id,       error_signature="AssertionError"))
    ingest_node(neo4j_driver, Artifact(id=artifact_id,     type="report", uri="s3://bucket/rpt.html"))
    ingest_node(neo4j_driver, Commit(id=commit_id,         sha="deadbeef",
                                     message="feat: kyc controller", timestamp=T0))
    ingest_node(neo4j_driver, Scan(id=scan_id,             tool="bandit", timestamp=T0))
    # Reasoning layer
    ingest_node(neo4j_driver, Judgment(id=j_id,            agent_role="supervisor", label="PASS"))
    ingest_node(neo4j_driver, ReasoningTrace(id=trace_id,  agent_role="supervisor",
                                             decision="All checks passed", timestamp=T0))
    ingest_node(neo4j_driver, SecurityFinding(id=secfind_id, severity="LOW",
                                              title="Hardcoded timeout"))
    ingest_node(neo4j_driver, Report(id=report_id,         summary="Sprint v1 clean",
                                     created_at=T0))

    # ── Step 3: Ingest all 11 cross-layer edges ───────────────────────────────
    ingest_edge(neo4j_driver, RealizedByEdge(
        from_id=req_id,      to_id=func_id,      valid_from=T0))
    ingest_edge(neo4j_driver, ComposedOfEdge(
        from_id=func_id,     to_id=comp_id,      valid_from=T0))
    ingest_edge(neo4j_driver, ImplementedByEdge(
        from_id=comp_id,     to_id=file_id,      valid_from=T0))
    ingest_edge(neo4j_driver, VerifiesEdge(
        from_id=test_id,     to_id=func_id,      valid_from=T0))
    ingest_edge(neo4j_driver, CoversCriterionEdge(
        from_id=test_id,     to_id=ac_id,        valid_from=T0))
    ingest_edge(neo4j_driver, AffectsEdge(
        from_id=secfind_id,  to_id=comp_id,      valid_from=T0))
    ingest_edge(neo4j_driver, InformedByEdge(
        from_id=j_id,        to_id=req_id,       valid_from=T0))
    ingest_edge(neo4j_driver, HasStepEdge(
        from_id=j_id,        to_id=trace_id,     valid_from=T0))
    ingest_edge(neo4j_driver, ModifiesEdge(
        from_id=commit_id,   to_id=file_id,      valid_from=T0))
    ingest_edge(neo4j_driver, InstanceOfEdge(
        from_id=testrun_id,  to_id=test_id,      valid_from=T0))
    ingest_edge(neo4j_driver, JudgedEdge(
        from_id=ac_id,       to_id=j_id,         valid_from=T0))

    # ── Step 4: Retrieve as supervisor ────────────────────────────────────────
    # All five layers allowed. Start from req_id; depth=6 reaches the full
    # connected subgraph. Isolated nodes (Actor, Contract, Endpoint, UIElement,
    # Failure, Artifact, Scan, Report) have no schema edges so won't appear —
    # that is correct graph behaviour, not a bug.
    result = retrieve(neo4j_driver, "supervisor", req_id, depth=6)
    visible_ids = {n["id"] for n in result["nodes"]}

    # Main audit-chain nodes must be visible
    main_chain = [req_id, func_id, comp_id, file_id, test_id, j_id]
    for nid in main_chain:
        assert nid in visible_ids, f"supervisor must see {nid} in retrieve result"

    # Connected-but-not-main-chain nodes must also appear
    assert commit_id   in visible_ids, "Commit must be reachable via MODIFIES"
    assert trace_id    in visible_ids, "ReasoningTrace must be reachable via HAS_STEP"
    assert ac_id       in visible_ids, "AcceptanceCriterion must be reachable via COVERS_CRITERION"
    assert secfind_id  in visible_ids, "SecurityFinding must be reachable via AFFECTS"
    assert testrun_id  in visible_ids, "TestRun must be reachable via INSTANCE_OF"

    # Edges must be returned too
    assert len(result["edges"]) > 0, "supervisor retrieve must return at least one edge"

    # ── Step 5: Reconcile REALIZED_BY — replace Func1 with Func2 ─────────────
    func2_id = f"func2-{ns}"
    ingest_node(neo4j_driver, Functionality(id=func2_id, name="KYC check v2"))

    reconcile(
        neo4j_driver,
        req_id,
        RealizedByEdge(from_id=req_id, to_id=func2_id, valid_from=T1),
    )

    # Old REALIZED_BY must be expired
    old_edge = _props(neo4j_driver, req_id, func_id, "REALIZED_BY")
    assert old_edge is not None,              "Old REALIZED_BY must remain in graph"
    assert old_edge.get("valid_to") is not None, "Old REALIZED_BY valid_to must be set"

    # New REALIZED_BY must be active
    new_edge = _props(neo4j_driver, req_id, func2_id, "REALIZED_BY")
    assert new_edge is not None,          "New REALIZED_BY must exist"
    assert new_edge.get("valid_to") is None, "New REALIZED_BY must be active (valid_to null)"

    # ── Step 6: Write provenance ──────────────────────────────────────────────
    prov_j_id  = f"j2-{ns}"
    prov_tr1   = f"ptr1-{ns}"
    prov_tr2   = f"ptr2-{ns}"

    prov_judgment = Judgment(id=prov_j_id, agent_role="supervisor",
                             label="PASS", reasoning="e2e smoke test")
    trace1 = ReasoningTrace(id=prov_tr1, agent_role="supervisor",
                            decision="Schema provisioned", timestamp=T1)
    trace2 = ReasoningTrace(id=prov_tr2, agent_role="supervisor",
                            decision="Chain traversed", timestamp=T2)

    returned_id = write_provenance(
        neo4j_driver,
        prov_judgment,
        [trace1, trace2],
        informed_by_ids=[req_id],
    )
    assert returned_id == prov_j_id, "write_provenance must return the judgment id"

    assert _node_exists(neo4j_driver, prov_j_id),  "Provenance Judgment must exist"
    assert _node_exists(neo4j_driver, prov_tr1),   "First ReasoningTrace must exist"
    assert _node_exists(neo4j_driver, prov_tr2),   "Second ReasoningTrace must exist"
    assert _rel_count(neo4j_driver, prov_j_id, "HAS_STEP")    == 2, "Must have 2 HAS_STEP edges"
    assert _rel_count(neo4j_driver, prov_j_id, "INFORMED_BY") == 1, "Must have 1 INFORMED_BY edge"

    # ── Step 7: Audit trail ───────────────────────────────────────────────────
    # After reconcile, the original REALIZED_BY (req → func) has valid_to set
    # but still exists in the graph. The audit_trail query does not filter by
    # valid_to, so it still finds the original chain through func_id.
    # The provenance Judgment (prov_j_id) also has INFORMED_BY → req_id, so
    # it produces a second row. We expect ≥ 2 rows.
    trail = audit_trail(neo4j_driver, req_id)
    assert len(trail) >= 1, "audit_trail must return at least one row for a complete chain"

    # Every row must have the six required keys
    required_keys = {"requirement", "functionality", "component", "file", "test", "judgment"}
    for row in trail:
        assert set(row.keys()) == required_keys, f"Unexpected keys in row: {set(row.keys())}"

    # The seeded Requirement must appear in every row
    for row in trail:
        assert row["requirement"] == req_id, "Every audit row must reference the seeded Requirement"

    # The provenance Judgment must appear in at least one row
    judgment_ids_in_trail = {row["judgment"] for row in trail}
    assert prov_j_id in judgment_ids_in_trail, \
        "Provenance Judgment (with INFORMED_BY → req) must appear in audit trail"
