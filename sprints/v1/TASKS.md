# Sprint v1 — Tasks: Memory Backbone (B1 + B2)

## Status: In Progress (5/10 complete)

---

- [x] Task 1: Scaffold project structure and dev environment (P0)
  - Acceptance: `docker compose up -d` starts Neo4j; `pytest` runs (0 tests, no errors);
    `python -c "from src.memory_api import MemoryAPI"` imports cleanly.
  - Files:
    - `docker-compose.yml` — Neo4j 5.x service with bolt on 7687, browser on 7474
    - `.env.example` — NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    - `pyproject.toml` — deps: neo4j, pydantic>=2, pyyaml, pytest, pytest-asyncio, python-dotenv
    - `src/__init__.py`
    - `src/db.py` — `get_driver()` singleton that reads .env
    - `tests/__init__.py`
    - `tests/conftest.py` — pytest fixture: `neo4j_driver` (uses test .env)
  - Completed: 2026-06-19 — Python 3.13, neo4j:5-community via Docker, setuptools.build_meta
    backend (not legacy), bandit clean, Neo4j connectivity verified end-to-end.

---

- [x] Task 2: Draft the YAML graph schema artifact (P0)
  - Acceptance: `schema.yaml` exists and passes `python scripts/validate_schema.py` (checks
    all required keys present, every edge references a known node label).
  - Notes: Use [create-context-graph.dev](https://create-context-graph.dev/) to sketch the
    four-layer graph visually first, then transcribe into YAML.
  - Files:
    - `schema/schema.yaml` — declares:
        - `nodes`: label, properties (name + type), unique_key
        - `edges`: type, from_label, to_label, properties (valid_from, valid_to always included)
        - `layers`: maps each label to requirements / capability / implementation / evidence / reasoning
    - `scripts/validate_schema.py` — loads YAML, asserts structural correctness
  - Completed: 2026-06-19 — 19 nodes across 5 layers, 11 edge types, all bi-temporal.
    YAML anchors used for temporal properties. Multi-target INFORMED_BY uses `to_labels` list.
    12 pytest tests green; validate_schema.py exits 0; bandit clean.

---

- [x] Task 3: Neo4j schema provisioner (P0)
  - Acceptance: Running `python scripts/provision_schema.py` on an empty Neo4j instance
    creates all uniqueness constraints and lookup indexes declared in `schema.yaml`.
    Re-running is idempotent (no errors on second run).
  - Files:
    - `scripts/provision_schema.py` — reads `schema/schema.yaml`; for each node with
      `unique_key`, issues `CREATE CONSTRAINT IF NOT EXISTS`; for each node property
      marked `index: true`, issues `CREATE INDEX IF NOT EXISTS`
  - Completed: 2026-06-19 — 19 UNIQUENESS constraints + 7 RANGE indexes applied.
    Logic extracted to src/provisioner.py (importable by e2e test). _safe() guard
    validates label/property names before Cypher embedding. 3 integration tests green;
    idempotency confirmed (identical output on second run); bandit clean.

---

- [x] Task 4: Pydantic domain models for all node types (P0)
  - Acceptance: Every node label in `schema.yaml` has a corresponding Pydantic v2
    `BaseModel` in `src/models.py`. `from src.models import Requirement, Test, Judgment`
    imports without error. Models validate `id` as non-empty string.
  - Files:
    - `src/models.py` — one class per node label (20 classes total);
      edge models carry `valid_from: datetime`, `valid_to: datetime | None = None`
    - `tests/test_models.py` — 3 unit tests: valid model passes, missing required field
      raises ValidationError, edge model defaults valid_to to None
  - Completed: 2026-06-19 — 19 node models + 11 edge models. BaseNode validates
    non-empty id (including whitespace-only strings). BaseEdge carries valid_from/valid_to.
    PytestCollectionWarning for Test/TestRun suppressed in pyproject.toml.
    17 unit tests green; 32 total suite green; bandit clean.

---

- [x] Task 5: INGEST operation (P0)
  - Acceptance: `memory_api.ingest_node(driver, node)` MERGEs the node on its `id`
    (idempotent). `memory_api.ingest_edge(driver, edge)` MERGEs the relationship,
    setting `valid_from=now()` on creation. Calling both twice does not duplicate data.
  - Files:
    - `src/memory_api.py` — `ingest_node(driver, node: BaseModel) -> str` (returns id);
      `ingest_edge(driver, edge: EdgeModel) -> None`
    - `tests/test_ingest.py` — integration test: ingest same Requirement twice, assert
      node count = 1; ingest an edge, assert property `valid_from` is set
  - Completed: 2026-06-19 — MERGE on (label, id) for nodes; ON CREATE SET for edge
    valid_from ensures second ingest does not overwrite. Edge type derived via
    CamelCase→UPPER_SNAKE conversion of class name; from/to labels loaded from schema
    YAML at import time. 10 integration tests green; 42 total; bandit clean.

---

- [ ] Task 6: RETRIEVE operation (P0)
  - Acceptance: `memory_api.retrieve(driver, agent_role, entity_id, depth=2)` returns a
    dict with `nodes` and `edges` lists scoped to the layers that role is allowed to see.
    Role `"functional_tester"` does not return Requirements layer nodes; role `"supervisor"`
    returns all layers.
  - Files:
    - `src/retrieval_policies.py` — dict mapping agent role → allowed layers
    - `src/memory_api.py` — `retrieve(driver, agent_role, entity_id, depth) -> dict`
      builds a parameterised Cypher using the policy and traversal depth
    - `tests/test_retrieve.py` — integration test: seed a 4-layer chain, assert
      supervisor gets all layers, functional_tester gets capability + implementation + evidence

---

- [ ] Task 7: RECONCILE operation (P1)
  - Acceptance: `memory_api.reconcile(driver, entity_id, new_edge)` sets `valid_to=now()`
    on any existing edge of the same type to `entity_id` where `valid_to IS NULL`, then
    ingests the new edge. Historical edge is preserved with `valid_to` set (queryable).
  - Files:
    - `src/memory_api.py` — `reconcile(driver, entity_id, new_edge: EdgeModel) -> None`
    - `tests/test_reconcile.py` — integration test: add two REALIZED_BY edges from
      the same Requirement at different times; assert only the latest has `valid_to IS NULL`,
      old edge has `valid_to` set

---

- [ ] Task 8: Provenance write-primitives (P1)
  - Acceptance: `memory_api.write_provenance(driver, judgment, trace_steps, informed_by_ids)`
    creates a `Judgment` node, N `ReasoningTrace` nodes linked via `HAS_STEP` edges, and
    `INFORMED_BY` edges from the Judgment to each node in `informed_by_ids`. All nodes are
    retrievable by id after the call.
  - Files:
    - `src/memory_api.py` — `write_provenance(driver, judgment: Judgment,
      trace_steps: list[ReasoningTrace], informed_by_ids: list[str]) -> str` (returns judgment id)
    - `tests/test_provenance.py` — integration test: write a judgment with 2 trace steps
      and 1 informed_by link; query the Judgment node and assert both HAS_STEP and
      INFORMED_BY relationships exist

---

- [ ] Task 9: Deterministic audit-trail Cypher query (P1)
  - Acceptance: `memory_api.audit_trail(driver, requirement_id)` returns an ordered list of
    dicts with keys `requirement`, `functionality`, `component`, `file`, `test`, `judgment`
    for every complete path from the given Requirement down to a Judgment node. Returns empty
    list (not error) when no path exists.
  - Files:
    - `src/memory_api.py` — `audit_trail(driver, requirement_id: str) -> list[dict]`
      issues a single Cypher MATCH on the path
      `(r:Requirement)-[:REALIZED_BY]->(:Functionality)-[:COMPOSED_OF]->(:Component)
      -[:IMPLEMENTED_BY]->(:File)<-[:MODIFIES]-(:Commit),
      (:Test)-[:VERIFIES]->(:Functionality),
      (:Judgment)-[:INFORMED_BY]->(r)`
    - `tests/test_audit_trail.py` — integration test: assert the query returns the seeded
      chain; assert the function handles a requirement with no downstream path gracefully

---

- [ ] Task 10: End-to-end integration smoke test (P1)
  - Acceptance: One pytest test (`tests/test_e2e.py`) exercises the full B1 + B2 surface
    in sequence — provision schema, ingest a full Requirement→Functionality→Component→File→
    Test→Judgment chain, retrieve it as supervisor role, reconcile one edge, write provenance,
    run audit_trail — and all assertions pass. This test is the "done" gate for v1.
  - Files:
    - `tests/test_e2e.py` — single test function `test_memory_backbone_e2e` that:
        1. Calls `provision_schema` against test Neo4j
        2. Ingests one node of every layer type
        3. Ingests all cross-layer edges
        4. Calls `retrieve` as supervisor, asserts full chain visible
        5. Calls `reconcile` on one edge, asserts old edge expired
        6. Calls `write_provenance`, asserts Judgment + traces exist
        7. Calls `audit_trail(requirement_id)`, asserts non-empty result

---

## Task Order & Dependencies

```
Task 1 (scaffold)
  └── Task 2 (schema YAML)
        └── Task 3 (provisioner)
              └── Task 4 (domain models)
                    ├── Task 5 (INGEST)
                    │     ├── Task 6 (RETRIEVE)
                    │     ├── Task 7 (RECONCILE)
                    │     └── Task 8 (provenance)
                    │           └── Task 9 (audit trail)
                    │                 └── Task 10 (e2e smoke test)
                    └── (supports all above)
```

## Sprint v1 Definition of Done

- [ ] `pytest tests/` passes green with no skips
- [ ] `python scripts/provision_schema.py` is idempotent on a fresh Neo4j
- [ ] `tests/test_e2e.py::test_memory_backbone_e2e` is the single source of integration truth
- [ ] No agent code exists yet — all logic is graph + memory API only
