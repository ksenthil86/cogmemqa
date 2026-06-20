# CoGMEM-QA — Phased Build Plan & Block Requirement Briefs

A dependency-ordered decomposition of CoGMEM-QA into **eleven buildable blocks across six phases**. The shared graph and memory API are built first because every later block reads and writes them; agents that seed and consume the graph follow; the build loop, integrity, and audit surfaces come next; evaluation last. Each block has a short requirement brief below.

> **Note:** Provenance write-primitives and the deterministic audit-trail query live in the memory tool set (B2); the audit trail is then surfaced visually in the Inspector (B10). Auditability is therefore a cross-cutting capability, not a separate block.

---

## Roadmap

| Phase | Blocks | Key output | Depends on |
|-------|--------|------------|------------|
| **Phase 1 — Memory Backbone** | B1, B2 | Live four-layer graph + typed memory API | — |
| **Phase 2 — Bootstrap & Test Design** | B3, B4 | Seeded requirements graph + proposed tests | Phase 1 |
| **Phase 3 — Execution & Security** | B5, B6 | Functional & security evidence in the graph | Phase 2 |
| **Phase 4 — Orchestration & Build Loop** | B7, B8 | Health reports + real-time commit-to-test loop | Phase 3 |
| **Phase 5 — Integrity & Audit Surface** | B9, B10 | Lint maintenance + Inspector dashboard | Phase 4 |
| **Phase 6 — Evaluation** | B11 | Baselines, ablations, metrics, locked results | Phases 1–5 |

---

## Block Requirement Briefs

### B1 — Context Graph Foundation

- **Phase:** 1 · **Depends on:** —
- **Data flow:** In: schema (YAML) → Out: live Neo4j graph with constraints

**Purpose.** Stand up the bi-temporal Neo4j graph that is the single source of truth, encoding the four lifecycle layers and three memory bands.

**Requirements**

- Define all node types across the four layers (requirements, capability, implementation, evidence) declaratively in a YAML schema artifact.
- Define cross-layer edges (`REALIZED_BY`, `COMPOSED_OF`, `IMPLEMENTED_BY`, `VERIFIES`, `AFFECTS`, `INFORMED_BY`).
- Every edge shall carry validity intervals (`valid_from` / `valid_to`) to support historical and contradiction queries.
- Enforce id uniqueness constraints and lookup indexes.
- Create or reset the entire schema reproducibly from the YAML artifact.

**Done when**

- The YAML artifact instantiates a clean graph with all constraints.
- A Requirement → File → Test path can be created and traversed in Cypher.

---

### B2 — Shared Memory Tool Set

- **Phase:** 1 · **Depends on:** B1
- **Data flow:** In: graph → Out: typed memory API used by every agent

**Purpose.** One typed API over the graph giving all agents the same memory operations plus the provenance primitives that make decisions auditable.

**Requirements**

- Expose `INGEST` (write events/nodes/edges), `RETRIEVE` (role-scoped context), and `RECONCILE` (resolve contradictions via validity intervals).
- Provide provenance primitives: write `Judgment` and `ReasoningTrace` nodes with `INFORMED_BY` / `HAS_STEP` edges from any agent.
- Provide a deterministic audit-trail query returning Requirement → Functionality → Component → File → Test → Judgment in one traversal.
- No agent shall hold private state — all shared state lives in the graph.
- The API shall be transport-agnostic and callable by both QA agents and the coding agent.

**Done when**

- All operations and provenance writes work against B1.
- The audit-trail query returns a complete chain for a seeded change.

---

### B3 — Requirements Parser Agent

- **Phase:** 2 · **Depends on:** B1, B2
- **Data flow:** In: business spec / PRD → Out: seeded requirements + capability layers

**Purpose.** Bootstrap the graph once at kickoff from the PRD, producing the Requirement → Functionality → Component skeleton that roots all later evidence.

**Requirements**

- Parse a PRD into `Requirement`, `AcceptanceCriterion`, and `Actor` nodes carrying `priority` and `reg_control` properties.
- Derive `Functionality` and `Component` nodes with `REALIZED_BY` / `COMPOSED_OF` edges.
- Preserve source requirement and acceptance-criterion identifiers for end-to-end traceability.
- Be idempotent — re-parsing an updated spec reconciles rather than duplicating nodes.

**Done when**

- Parsing the Meridian PRD yields the full requirements + capability skeleton.
- Every acceptance-criterion node links to its requirement and is queryable.

---

### B4 — Test Case Generator Agent

- **Phase:** 2 · **Depends on:** B2, B3
- **Data flow:** In: graph (uncovered criteria) → Out: Test nodes + `COVERS_CRITERION` edges

**Purpose.** Traverse the graph to find acceptance criteria with no covering test and propose API and UI tests linked to them.

**Requirements**

- Run a coverage-gap query to find `AcceptanceCriterion` nodes with no covering test.
- Propose API and UI test specifications mapped to the criterion each verifies.
- Link each proposed test via `COVERS_CRITERION` / `VERIFIES` edges.
- Avoid generating duplicate tests for already-covered criteria.

**Done when**

- Running against a seeded graph produces tests for all uncovered criteria.
- The coverage-gap query shrinks after generation.

---

### B5 — Functional Tester Agent

- **Phase:** 3 · **Depends on:** B2, B4
- **Data flow:** In: tests + app under test → Out: TestRun / Failure / Artifact nodes + triage labels

**Purpose.** Execute API and UI tests, classify failures into six categories using graph-retrieved context, and record evidence.

**Requirements**

- Execute Playwright (UI) and HTTP/API tests against the application under test.
- Record `TestRun` outcomes, `Failure` nodes with `error_signature`, and `Artifact` nodes (screenshots, HAR files).
- Classify each failure into one of six categories using context retrieved from the graph (e.g. prior similar failures).
- Store a `Judgment` and `ReasoningTrace` for every triage decision.

**Done when**

- A test run records outcomes and artifacts in the graph.
- Each failure carries a category label backed by a reasoning trace.

---

### B6 — Security Tester Agent

- **Phase:** 3 · **Depends on:** B2, B3
- **Data flow:** In: source + scanners → Out: SecurityFinding nodes + `AFFECTS` edges

**Purpose.** Run static-analysis scans and map findings to the components and requirements they affect.

**Requirements**

- Run Bandit and Semgrep scans over the codebase.
- Create `SecurityFinding` nodes with `severity`, `status`, and `title`.
- Map findings to affected `Component` nodes (and upward to `Requirement`) via `AFFECTS` edges.
- Store a reasoning trace for each finding to support audit.

**Done when**

- A scan produces `SecurityFinding` nodes linked to components.
- Findings are traceable to the requirements they impact.

---

### B7 — QA Supervisor Agent

- **Phase:** 4 · **Depends on:** B3–B6
- **Data flow:** In: full graph → Out: Report nodes + health signals

**Purpose.** Monitor overall project health through aggregate Cypher queries and surface risks.

**Requirements**

- Run aggregate queries for unimplemented requirements, regressed functionalities, coverage, and open security findings.
- Produce `Report` nodes summarising health, with provenance to the underlying evidence.
- Detect regressions by comparing current versus prior validity intervals.
- Expose health signals for consumption by the Inspector.

**Done when**

- Supervisor reports correctly list unimplemented and regressed items on a seeded graph.
- Each report is traceable to the evidence behind it.

---

### B8 — Coding Agent & Build-Cycle Integration

- **Phase:** 4 · **Depends on:** B1, B2
- **Data flow:** In: commits → Out: real-time graph updates (Commit / File nodes, `MODIFIES` edges)

**Purpose.** Wire the coding agent and commits into the build loop so the graph updates in real time as code changes.

**Requirements**

- On each commit, ingest `Commit` nodes and update `File` and `MODIFIES` edges.
- Trigger the relevant agents (generate, test, scan) on changed components.
- Propagate a changed file upward through the four layers to the affected requirements.
- Keep short-term (build-cycle) memory in sync with each commit.

**Done when**

- A commit on the replayable history updates the graph and reaches its requirement.
- The end-to-end loop (commit → test → triage → report) runs unattended.

---

### B9 — Lint & Memory Maintenance

- **Phase:** 5 · **Depends on:** B2
- **Data flow:** In: graph over time → Out: repaired or flagged judgments

**Purpose.** Add lint as a first-class fourth memory operation that detects and repairs stale or contradicted judgments (memory rot).

**Requirements**

- Detect cached judgments invalidated by newer commits or test runs (drift detection).
- Reconcile or expire stale `Judgment` and `Failure` classifications using validity intervals.
- Run both on demand and on a schedule within the build loop.
- Record every lint action as an auditable reasoning trace.

**Done when**

- A contradicting event causes lint to flag or repair the stale judgment.
- Drift-stability metrics improve with lint enabled versus disabled.

---

### B10 — CoGMEM-Inspector (Audit Visualization)

- **Phase:** 5 · **Depends on:** B2, B7
- **Data flow:** In: graph → Out: interactive compliance dashboard

**Purpose.** A web UI rendering the four-layer graph as a clickable compliance dashboard where any node expands into its provenance subgraph.

**Requirements**

- Render the four layers and three memory bands (Cytoscape.js + FastAPI).
- Expand any node into its full provenance subgraph in one click.
- Visualise the deterministic audit trail for any shipped change.
- Surface supervisor health signals (unimplemented, regressed, findings).

**Done when**

- An auditor can click a change and see its requirement-rooted trail.
- The dashboard reflects live graph state.

---

### B11 — Evaluation Harness & Benchmark

- **Phase:** 6 · **Depends on:** All
- **Data flow:** In: synthetic app + baselines → Out: metrics, charts, locked results

**Purpose.** Build the synthetic banking benchmark with replayable commits and injected regressions, and measure CoGMEM-QA against baselines and ablations.

**Requirements**

- Provide a synthetic banking app (account opening, transactions) with 30–50 replayable commits and injected regressions.
- Implement baselines (no-memory, filesystem-agent, Zep/Mem0g) and ablations (no shared memory, no requirements layer, no supervisor, no lint).
- Measure requirements coverage, triage F1, supervisor precision, audit-query latency, and drift stability.
- Produce longitudinal charts and comparison tables, with a locked result set (seeds, LLM versions, costs).

**Done when**

- All baselines and ablations run on the replayable history.
- Metrics and charts are reproducible from a fixed seed.
