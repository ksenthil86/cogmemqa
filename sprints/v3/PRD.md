# Sprint v3 — PRD: Execution & Security (B5 + B6)

## Overview

Bring execution evidence into the graph by building two agents on top of the
Phase 2 skeleton. The **Functional Tester** (B5) reads the Test nodes proposed
by B4, executes HTTP calls against the Meridian banking stub, and writes
`TestRun` / `Failure` nodes with LLM-classified triage labels back to the shared
brain. The **Security Tester** (B6) runs Bandit over the Meridian app source,
turns each finding into a `SecurityFinding` node linked to the affected
`Component` via `AFFECTS`, and writes a provenance record per finding.

By sprint end the graph contains live execution evidence (pass/fail outcomes +
security findings) traceable all the way back to the business requirements that
motivated each test and component.

---

## Goals

- A minimal Meridian banking app stub (FastAPI, 5 endpoints) serves as the
  *application under test* for B5 and the *code under scan* for B6; some
  endpoints deterministically fail and some source lines trigger real Bandit
  findings to make the demos non-trivial.
- `FunctionalTesterAgent` (B5) reads `Test` nodes from the graph, runs HTTP
  calls via an injectable `run_fn`, ingests `TestRun` nodes (`INSTANCE_OF` →
  Test) and, for each failure, classifies it into one of six categories via
  LLM, writing a `Failure` node and a `Judgment(label="FAILURE_CLASSIFIED")`.
- `SecurityTesterAgent` (B6) accepts an injectable `scan_fn` that wraps Bandit,
  ingests `SecurityFinding` nodes, maps file paths to `Component` slugs via
  keyword matching, creates `AFFECTS` edges, and writes a provenance
  `Judgment(label="SECURITY_SCAN_COMPLETE")`.
- All agent operations use the Sprint v1 memory API (no agent holds private
  state) and are testable without a live LLM or a running server (stub
  `run_fn` / `scan_fn` / `llm_fn` injected at construction).
- A Phase 3 e2e gate test seeds Meridian data, runs B5 with a deterministic
  stub, runs B6 on the real Meridian app source, and asserts the full
  evidence chain (`TestRun` → `Test` → `AcceptanceCriterion`, `SecurityFinding`
  → `Component` → `Requirement`) is queryable.

---

## User Stories

- As a **Functional Tester agent**, I want to read proposed tests from the
  shared graph, execute them, and write outcomes back — so every test result is
  immediately visible to every other agent without point-to-point messaging.
- As a **Security Tester agent**, I want to scan the application code and link
  findings to the components they affect — so an auditor can trace a CVE back
  to the requirement it threatens.
- As an **auditor**, I want every failed test and security finding backed by a
  `Judgment` + `ReasoningTrace` — so I can replay the triage reasoning, not
  just see the verdict.
- As a **developer**, I want both agents to accept injectable `run_fn` /
  `scan_fn` / `llm_fn` callables — so the test suite is deterministic and
  needs no live server, scanner, or LLM key.

---

## Technical Architecture

### Stack additions (Sprint v3)

| Layer | Technology |
|-------|-----------|
| App under test | FastAPI 0.110+ (`fixtures/meridian_app/main.py`) |
| HTTP client | `httpx>=0.27` (async-compatible, used by B5 in production) |
| Security scanner | `bandit[toml]>=1.7` (already a dev dep) + subprocess JSON output |
| B5 agent | `src/agents/functional_tester.py` |
| B6 agent | `src/agents/security_tester.py` |
| New graph nodes | `TestRun`, `Failure` (B5); `SecurityFinding` (B6) — all in `src/models.py` ✓ |
| New graph edges | `INSTANCE_OF` (TestRun→Test), `AFFECTS` (SecurityFinding→Component) — in schema ✓ |
| New env vars | `MERIDIAN_APP_URL=http://localhost:8000` (optional; tests use stub) |

> **Injection pattern (consistent with B3/B4).** Every agent accepts three
> swappable callables: `llm_fn` (LLM backend), `run_fn` (HTTP runner, B5 only),
> `scan_fn` (scanner, B6 only).  Tests inject deterministic stubs; production
> passes the real clients.

### Meridian Banking App Stub

```
fixtures/meridian_app/
  main.py          # FastAPI ASGI app — 5 endpoints
  __init__.py
```

Five endpoints covering the five Meridian requirements:

| Route | Behaviour |
|-------|-----------|
| `POST /accounts` | Returns 201 with new account; 409 if `national_id == "DUPLICATE"` |
| `POST /kyc/verify` | Returns `{"status": "VERIFIED"}`; 422 if account_id missing |
| `POST /transfers` | Returns 200; 402 if `payload.amount > payload.balance` (INSUFFICIENT_FUNDS) |
| `GET  /transactions` | Returns paginated list (20 items); 400 if `page < 1` |
| `GET  /fraud/alerts` | Returns `[]`; `[{…}]` if query param `?amount` > 10000 |

**Intentional Bandit findings** (makes B6 non-trivial):
- `SECRET_KEY = "meridian-dev-secret-2024"` → B105 / hardcoded password
- `subprocess.run(["echo", user_ref], shell=False)` — kept safe but bandit still flags the import pattern

### Component Diagram

```
                ┌────────────────────────────────────────┐
                │  Neo4j Context Graph                   │
                │  [Test nodes from Sprint v2]           │
                └────────────────┬───────────────────────┘
                                 │  retrieve(Test ids)
                    ┌────────────▼────────────┐
                    │  FunctionalTesterAgent  │  B5
                    │  ┌─────────────────┐   │
                    │  │ run_fn(spec)    │   │  ← httpx / stub
                    │  └────────┬────────┘   │
                    │           │ outcome     │
                    │  ┌────────▼────────┐   │
                    │  │ llm_fn(prompt)  │   │  ← Gemini / stub
                    │  └────────┬────────┘   │
                    └────────────┼────────────┘
                                 │  ingest_node / write_provenance
                                 ▼
                ┌────────────────────────────────────────┐
                │  Evidence layer — TestRun / Failure    │
                │  TestRun ──[INSTANCE_OF]──► Test       │
                │  Failure  (label=category)             │
                │  Judgment  (FAILURE_CLASSIFIED)        │
                └────────────────────────────────────────┘

  fixtures/meridian_app/main.py
                 │  scan_fn(path)
     ┌───────────▼───────────┐
     │  SecurityTesterAgent  │  B6
     │  Bandit JSON output   │
     └───────────┬───────────┘
                 │  ingest_node / ingest_edge / write_provenance
                 ▼
  ┌────────────────────────────────────────────────────┐
  │  Requirements layer — SecurityFinding              │
  │  SecurityFinding ──[AFFECTS]──► Component         │
  │  Judgment  (SECURITY_SCAN_COMPLETE)                │
  └────────────────────────────────────────────────────┘
```

### Failure Classification Categories (B5)

The LLM classifies each failing `TestRun` into exactly one of:

| Category | Meaning |
|----------|---------|
| `regression` | Previously passing, now failing (graph history shows prior pass) |
| `environment` | Network / infra issue (connection error, timeout) |
| `flaky` | Intermittent — no deterministic failure signal |
| `spec_gap` | AC statement too vague to derive a passing test |
| `data_error` | Bad test payload / fixture data |
| `blocker` | App not running or dependency unavailable |

LLM prompt includes the `ac_statement`, `error_signature`, and (via `retrieve()`)
the last 3 `TestRun` outcomes for the same `Test` — enabling regression detection
without a separate query.

### B5 HTTP Spec Derivation

`FunctionalTesterAgent` maps each Test node's `verifies_functionality_id` to an
HTTP spec using a built-in endpoint map:

```python
_FUNC_TO_ENDPOINT = {
    "func-account-opening":    ("POST", "/accounts"),
    "func-kyc":                ("POST", "/kyc/verify"),
    "func-money-transfer":     ("POST", "/transfers"),
    "func-transaction-history":("GET",  "/transactions"),
    "func-fraud-alerting":     ("GET",  "/fraud/alerts"),
}
```

`run_fn` receives `{"method": "POST", "url": "http://…/accounts", "payload": {…}}` 
and returns `{"status_code": 201, "body": {…}, "error": None}`.

### B6 File-to-Component Mapping

```python
_FILE_KEYWORDS = {
    "account":     "comp-account-opening",
    "kyc":         "comp-kyc",
    "transfer":    "comp-money-transfer",
    "transaction": "comp-transaction-history",
    "fraud":       "comp-fraud-alerting",
}
```

If no keyword matches, the finding is ingested without an `AFFECTS` edge (still
auditable via its `Judgment`).

### Data Flow

```
B5 RUN:
  test_ids = query graph for Test nodes where type="api" and no TestRun yet
  for each test_id:
    test_node, ac_statement = retrieve(test_id)
    spec  = _derive_http_spec(test_node)           # endpoint map lookup
    result = run_fn(spec)                          # httpx / stub
    ingest TestRun (INSTANCE_OF → test_id)
    if result["status_code"] >= 400 or result["error"]:
      category = llm_fn(classify_prompt)           # Gemini / stub
      ingest Failure (label=category)
      write_provenance(Judgment("FAILURE_CLASSIFIED"), [trace], [ac_id])
  write_provenance(Judgment("FUNCTIONAL_RUN_COMPLETE"), [summary_trace], test_ids)

B6 RUN:
  raw_findings = scan_fn(source_path)              # bandit JSON / stub
  for each finding:
    ingest SecurityFinding (severity, title, status="open")
    comp_id = _map_file_to_component(finding["filename"])
    if comp_id:
      ingest AFFECTS edge (SecurityFinding → Component)
    write_provenance(Judgment("SECURITY_FINDING"), [trace], [comp_id or []])
  write_provenance(Judgment("SECURITY_SCAN_COMPLETE"), [summary], finding_ids)
```

---

## Out of Scope (v4+)

- Playwright / browser UI test execution — B5 HTTP-only in this sprint
- Semgrep scanner integration — B6 uses Bandit only; Semgrep deferred
- `Report` nodes and QA Supervisor health aggregation — B7 (Phase 4)
- Coding Agent / commit-triggered build loop — B8 (Phase 4)
- `LINT` memory operation and drift-detection — B9 (Phase 5)
- CoGMEM-Inspector dashboard UI — B10 (Phase 5)
- Evaluation harness / ablation runs — B11 (Phase 6)

---

## Dependencies

- **Sprint v2 complete** — B3 (`RequirementsParserAgent`) and B4
  (`TestCaseGeneratorAgent`) must be green; `Test` nodes for all Meridian ACs
  must be seedable via the existing e2e fixture.
- **FastAPI + httpx** — add to `pyproject.toml` runtime deps; `fastapi` and
  `httpx` not yet present (they serve the banking stub + run HTTP tests).
- **Neo4j still runs via Docker Compose** from Sprint v1 — no new services.
- **Bandit** — already a dev dep; `bandit -f json` subprocess call added.
- **No live LLM required** for tests — stub `llm_fn` / `run_fn` / `scan_fn`
  injected throughout.

---

## Sprint v3 Definition of Done

- [ ] `pytest tests/` green with no skips (all prior tests + new Sprint v3 tests)
- [ ] `fixtures/meridian_app/main.py` is a runnable FastAPI ASGI app with ≥ 1
      intentional Bandit finding
- [ ] `FunctionalTesterAgent.run(driver, test_ids)` writes `TestRun` + `Failure`
      nodes to graph (stub `run_fn`)
- [ ] `SecurityTesterAgent.run(driver, source_path)` writes `SecurityFinding` +
      `AFFECTS` edges (real Bandit on `fixtures/meridian_app/`)
- [ ] `tests/test_e2e_phase3.py::test_execution_and_security_e2e` passes green
- [ ] Bandit scan on `src/` is clean (agent code itself; app stub is intentionally dirty)
