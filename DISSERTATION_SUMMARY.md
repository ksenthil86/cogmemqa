# CoGMEM-QA: Implementation Report
## Sprints v1–v5 — Memory-Grounded Multi-Agent QA System

---

### 1. Overview

CoGMEM-QA is a multi-agent quality assurance swarm built for software delivery pipelines. Its defining design principle is **shared context through a knowledge graph**: all agents read from and write to the same Neo4j graph; no agent calls another directly. Every decision is recorded as a provenance chain — Judgment → ReasoningTrace → evidence nodes — enabling end-to-end traceability from business requirements through to security findings.

The system was built across five incremental sprints, each delivering a tested, Bandit-clean vertical slice. The final build totals **298 integration and unit tests, zero security findings, and a two-command live demo** that seeds the graph and replays five deterministic commits.

---

### 2. Overall Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     CoGMEM-QA Agent Swarm                    │
│                                                              │
│  ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
│  │    B3     │  │    B4     │  │    B5    │  │    B6    │  │
│  │ Require-  │  │  Test     │  │ Func.    │  │ Security │  │
│  │ ments     │  │  Case     │  │ Tester   │  │ Tester   │  │
│  │ Parser    │  │  Gen.     │  │          │  │ (Bandit) │  │
│  └─────┬─────┘  └─────┬─────┘  └────┬─────┘  └─────┬────┘  │
│        │              │             │               │        │
│        └──────────────┴─────────────┴───────────────┘        │
│                              │                               │
│                     READS / WRITES                           │
│                              │                               │
│              ┌───────────────▼──────────────┐                │
│              │       Neo4j Graph            │                │
│              │   (shared memory store)      │                │
│              │                              │                │
│              │  Requirements → Functionality│                │
│              │  → Component → File          │                │
│              │  Tests, TestRuns, Findings   │                │
│              │  Commits, Reports, Judgments │                │
│              └───────────────┬──────────────┘                │
│                              │                               │
│                     READS / WRITES                           │
│                              │                               │
│              ┌───────────────▼──────────────┐                │
│              │    B7  QA Supervisor          │                │
│              │  coverage_summary()           │                │
│              │  security_summary()           │                │
│              │  → Report node + Judgment     │                │
│              └──────────────────────────────┘                │
│                                                              │
│  ┌──────────┐  ← B8 CommitIngestionAgent triggers cycle      │
│  │    B8    │     ingest_commit() → impact_lookup()          │
│  │ Commit   │     → run_build_cycle(b5, b6, b7)             │
│  │ Ingester │                                               │
│  └──────────┘                                               │
└──────────────────────────────────────────────────────────────┘
```

**Graph Layer Model (5 layers, 19 node types, 11 edge types):**

```
Layer 1 — Requirements:   Requirement, AcceptanceCriterion, Actor
Layer 2 — Capability:     Functionality
Layer 3 — Implementation: Component, File, Commit
Layer 4 — Evidence:       Test, TestRun, SecurityFinding, Report
Layer 5 — Reasoning:      Judgment, ReasoningTrace
```

All edges carry `valid_from` / `valid_to` timestamps enabling bi-temporal reconciliation (RECONCILE operation sets `valid_to = now()` on superseded edges before writing the replacement).

---

### 3. Sprint v1 — Memory Backbone (B1 + B2)

**Objective:** Establish the shared graph schema, database provisioner, domain models, and core memory API that all subsequent agents depend on.

**Key deliverables:**

- **`schema/schema.yaml`** — declarative specification of all 19 node types and 11 edge types across 5 layers.
- **`src/provisioner.py`** — idempotent schema provisioner that creates 19 UNIQUENESS constraints and 7 RANGE indexes via `CREATE CONSTRAINT IF NOT EXISTS`. Safe to run repeatedly.
- **`src/models.py`** — 19 node Pydantic v2 models + 11 edge models. `BaseNode` enforces non-empty `id`; `BaseEdge` carries `valid_from`/`valid_to=None`.
- **`src/memory_api.py`** — five core operations:
  - `ingest_node()` / `ingest_edge()` — MERGE-based idempotent writes.
  - `retrieve()` — two-query traversal respecting per-role layer policies (`src/retrieval_policies.py`).
  - `reconcile()` — bi-temporal edge supersession.
  - `write_provenance()` — Judgment + ReasoningTrace + INFORMED_BY edges.
  - `audit_trail()` — full Requirement → Functionality → Component → File → Commit → Test → Judgment chain.
- **`tests/test_e2e.py`** — Phase 1 gate: provisions schema, ingests full multi-layer chain, exercises retrieve / reconcile / provenance / audit_trail.

**Test coverage:** 77/77 green.

---

### 4. Sprint v2 — Agent Bootstrap (B3 + B4)

**Objective:** Introduce the `BaseAgent` pattern and the first two reasoning agents: requirements parsing and test case generation.

**Key deliverables:**

- **`src/llm.py`** — `call_llm(prompt)` wraps the `google-genai >= 1.0` SDK via an `@lru_cache` singleton client. All agents receive `llm_fn` as an injectable callable so tests run without live API calls.
- **`src/agent_base.py`** — `BaseAgent(role, driver, llm_fn)` base class. Exposes `.retrieve()` and `.write_provenance()` as thin wrappers over `memory_api`, eliminating boilerplate in subclasses.
- **`fixtures/meridian_spec.md`** — Meridian Bank product requirements document: 5 requirements (Account Opening, KYC, Money Transfer, Transaction History, Fraud Alerting), 10 acceptance criteria, 2 actors.
- **`src/agents/requirements_parser.py` (B3)** — `RequirementsParserAgent.parse_spec()` calls the LLM to extract structured JSON; `seed_graph()` ingests all nodes across layers 1–3; writes a `SEEDED` Judgment.
- **`src/agents/test_case_generator.py` (B4)** — `TestCaseGeneratorAgent.propose_tests()` generates one `ProposedTest` per AC via the LLM; `ingest_tests()` writes Test nodes with `COVERS_CRITERION` edges; writes `TEST_PROPOSED` Judgments.
- **`tests/test_e2e_phase2.py`** — Phase 2 gate with shared helpers (`_clean_all_meridian`, `_b4_stub_llm`) reused by all subsequent e2e tests.

**Test coverage:** 162/162 green.

---

### 5. Sprint v3 — Execution & Security (B5 + B6)

**Objective:** Add agents that execute tests against a live application and scan source code for security issues.

**Key deliverables:**

- **`fixtures/meridian_app/main.py`** — FastAPI ASGI stub with 5 endpoints modelling the Meridian banking app. Contains an intentional Bandit B105 finding (`ACCOUNT_PASSWORD = "account-dev-password-2024"`) used to exercise B6's reporting path.
- **`src/agents/functional_tester.py` (B5)** — `FunctionalTesterAgent` with injectable `run_fn: Callable[[dict], dict]`. `run_http_test(driver, test_id)` retrieves the Test node, derives an HTTP spec via `_derive_http_spec`, calls `run_fn`, creates a `TestRun` node with `INSTANCE_OF` edge, and writes `FUNCTIONAL_RUN_COMPLETE` / `FAILURE_CLASSIFIED` Judgments.
- **`src/agents/security_tester.py` (B6)** — `SecurityTesterAgent` with injectable `scan_fn`. The default scan uses `[sys.executable, "-m", "bandit", ...]` (path-portable, Bandit not assumed on `$PATH`). Creates `SecurityFinding` nodes with `AFFECTS → Component` edges; writes `SECURITY_FINDING` and `SECURITY_SCAN_COMPLETE` Judgments.

**Notable engineering fix:** Full-suite test isolation required scoping all count assertions to known IDs via `INFORMED_BY` edge traversal, preventing interference from orphaned Judgment nodes left by other test modules.

**Test coverage:** 266/266 green.

---

### 6. Sprint v4 — QA Supervisor (B7)

**Objective:** Introduce an orchestrating agent that aggregates health signals from the graph and writes a structured `Report` node.

**Key deliverables:**

- **`coverage_summary(driver)`** in `memory_api` — counts AC nodes covered by at least one passing `TestRun` via an OPTIONAL MATCH pattern, returns `{total_ac, covered_ac, coverage_pct}`.
- **`security_summary(driver)`** in `memory_api` — counts open `SecurityFinding` nodes by severity, returns `{total_open, by_severity}`.
- **`src/agents/qa_supervisor.py` (B7)** — `QASupervisorAgent.compute_health()` pulls both summaries; `generate_report()` calls the LLM for a one-sentence summary, creates a `Report` node (carrying `coverage_pct`, `open_findings_count`, `severity_breakdown`), and writes a `HEALTH_REPORT_GENERATED` Judgment informed by all passing TestRun IDs and open SecurityFinding IDs.
- **`Report` model** — backward-compatible extension of `BaseNode` with `created_at: datetime`, `coverage_pct: float`, `open_findings_count: int`, `severity_breakdown: str` (JSON-encoded).

**Notable engineering fix:** `test_coverage_summary_full_local_coverage` initially polluted the global AC count. Fixed by scoping the assertion to the seeded Meridian AC IDs only. Additionally, stale ACs from prior sessions were purged in `_clean_phase4_nodes` with `WHERE NOT ac.id IN $meridian_ids`.

**Test coverage:** 266/266 green (18 new unit tests for B7 + 9 new e2e assertions).

---

### 7. Sprint v5 — Build-Cycle Integration (B8)

**Objective:** Close the loop by ingesting version-control commits, computing impact, and triggering a full B5→B6→B7 build cycle per commit. Deliver a standalone demo requiring no external git trigger.

**Key deliverables:**

- **`fixtures/meridian_commits.json`** — 5 deterministic commit objects, one per Meridian component, with Java file paths (`src/account/AccountController.java`, etc.) mapping to known component IDs.
- **`src/agents/commit_ingestion.py` (B8)** — `CommitIngestionAgent.ingest_commit()` MERGEs `Commit` + `File` nodes, creates `MODIFIES` edges, and writes a `COMMIT_INGESTED` Judgment.
- **`impact_lookup(driver, file_paths)`** in `memory_api` — reverse traversal `File ←[IMPLEMENTED_BY]← Component ←[COMPOSED_OF]← Functionality ←[REALIZED_BY]← Requirement`, returning the full chain for any changed file.
- **`src/orchestrator.py`** — `run_build_cycle(driver, b5, b6, b7, scan_path)` sequences B5→B6→B7 and returns the `report_id`.
- **`scripts/replay_meridian.py`** — self-contained demo: seeds graph (B3+B4+IMPLEMENTED_BY), then for each of 5 commits: ingest → impact_lookup → reset per-cycle evidence → run_build_cycle → print formatted output. Supports `--dry-run` (validates fixtures without Neo4j).
- **`scripts/demo_summary.py`** — read-only live graph query: shows commit count, coverage, open findings, report count, Judgment counts, and a structural provenance chain for any requirement.

**Build-Cycle Loop (per commit):**

```
  Git Commit Data
        │
        ▼
  B8: ingest_commit()
  ┌─────────────────────┐
  │  Commit node        │
  │  File node(s)       │
  │  MODIFIES edges     │
  │  COMMIT_INGESTED J  │
  └──────────┬──────────┘
             │
             ▼
  impact_lookup(file_paths)
  → Component → Functionality → Requirement

             │
             ▼
  ┌──────────────────────────────────┐
  │  run_build_cycle(b5, b6, b7)    │
  │                                 │
  │  B5: run_http_test() × N tests  │
  │  → TestRun nodes (pass/fail)    │
  │                                 │
  │  B6: scan(src/) via Bandit      │
  │  → SecurityFinding nodes        │
  │                                 │
  │  B7: coverage_summary()         │
  │      security_summary()         │
  │  → Report node                  │
  │  → HEALTH_REPORT_GENERATED J    │
  └──────────────────────────────────┘
             │
             ▼
  Formatted per-commit output:
  ► Commit b800001  "Add input validation..."
    Changed:  src/account/AccountController.java
    Impact:   comp-account-opening → func-account-opening → req-account-opening
    B5:  10 tests run, 10 pass
    B6:  1 open finding(s) (1 LOW)
    B7:  report-056161e4ee  coverage 100.0%  1 open finding(s)
    ✓  COMMIT_INGESTED  (commit-b800001)
```

**Notable engineering fix:** FunctionalTesterAgent is idempotent — re-running on an already-tested graph produces no new `TestRun` nodes. Fixed by resetting `TestRun` and `SecurityFinding` nodes before each commit cycle in the replay script.

**Test coverage:** 298/298 green.

---

### 8. Quality Gate Summary

| Sprint | Blocks | Tests Added | Cumulative | Bandit |
|--------|--------|-------------|------------|--------|
| v1     | B1, B2 | 77          | 77         | Clean  |
| v2     | B3, B4 | 85          | 162        | Clean  |
| v3     | B5, B6 | 104         | 266        | Clean  |
| v4     | B7     | —           | 266        | Clean  |
| v5     | B8     | 32          | 298        | Clean  |

**Demo (two commands, no external dependencies beyond Neo4j):**

```bash
python scripts/replay_meridian.py    # seeds graph + replays 5 commits
python scripts/demo_summary.py       # prints live graph state + provenance chain
```

---

### 9. Design Decisions and Lessons

**Shared state over direct coupling.** The graph-as-memory pattern means agents never call each other, eliminating tight coupling. Adding a new agent requires only that it reads/writes agreed node types — no interface contracts, no message queues.

**Injectable callables for testability.** Every agent accepts `llm_fn`, `run_fn`, and `scan_fn` as constructor arguments. This enabled 298 tests to run without any live LLM, HTTP, or subprocess calls in the unit/e2e suite, while the production code path uses real implementations.

**MERGE-based idempotency.** All graph writes use Cypher `MERGE`, making every operation safe to replay. The replay script deliberately exploits this to re-seed the Meridian graph before each demo run.

**Bi-temporal edge history.** The RECONCILE operation preserves superseded edges with `valid_to` timestamps rather than deleting them, enabling historical queries — a foundation for the audit trail and future compliance use cases.

**Test isolation in a shared database.** Because Neo4j persists state across sessions, each e2e test module owns a `_clean_phaseN_nodes()` function and calls cleanup in reverse-phase order (5→4→3→2). All count assertions are scoped to known IDs via `INFORMED_BY` traversal rather than global counts.
