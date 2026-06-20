# Sprint v5 — Tasks: Build-Cycle Integration (B8)

## Status: Complete (8/8)

---

- [x] Task 1: Meridian commit fixture data (P0)
  - Completed: 2026-06-20 — 5-commit JSON fixture covering all Meridian components; structure validated against acceptance criteria; bandit clean
  - Acceptance:
    - `fixtures/meridian_commits.json` exists and is valid JSON.
    - Contains exactly 5 commit objects, one per Meridian component.
    - Each object has keys: `sha`, `message`, `author`, `timestamp`, `files`
      where `files` is a list of `{"path": ..., "change_type": ...}` objects.
    - File paths map to the five Meridian components:
      | sha | file path | component |
      |---|---|---|
      | b800001 | `src/account/AccountController.java` | `comp-account-opening` |
      | b800002 | `src/kyc/KycService.java` | `comp-kyc` |
      | b800003 | `src/transfers/TransferEngine.java` | `comp-money-transfer` |
      | b800004 | `src/history/TransactionRepository.java` | `comp-transaction-history` |
      | b800005 | `src/fraud/FraudDetector.java` | `comp-fraud-alerting` |
    - `python -c "import json; json.load(open('fixtures/meridian_commits.json'))"` exits 0.
  - Files:
    - `fixtures/meridian_commits.json`

---

- [x] Task 2: `CommitIngestionAgent` — tests then implementation (P0)
  - Completed: 2026-06-20 — CommitIngestionAgent inherits BaseAgent; ingest_commit() MERGEs Commit+File nodes, MODIFIES edges, writes COMMIT_INGESTED Judgment+ReasoningTrace; 12 tests green; 278/278 suite; bandit clean
  - Acceptance:
    - `src/agents/commit_ingestion.py` exists with `CommitIngestionAgent(BaseAgent)`.
    - `__init__(role="commit_ingestion", driver=None, llm_fn=call_llm)`.
    - `ingest_commit(driver, commit_data: dict) -> str` method:
      - Returns `f"commit-{commit_data['sha']}"`.
      - `MERGE`s a `Commit` node with `id`, `sha`, `message`, `author`, `timestamp`.
      - `MERGE`s a `File` node per `commit_data["files"]` entry
        (id = `f"file-{path.replace('/', '-')}"`, path = the file path string).
      - Creates `Commit -[MODIFIES]-> File` edge for each file.
      - Writes `Judgment(label="COMMIT_INGESTED")` + `ReasoningTrace` via
        `write_provenance`, `informed_by=[commit_id]`.
    - `run(driver, commit_data) -> str` delegates to `ingest_commit`.
    - `tests/test_commit_ingestion.py` green with ≥9 tests covering:
      - importable, `BaseAgent` subclass, default role, no `run_fn`/`scan_fn`
      - `ingest_commit` returns correct id
      - `Commit` node exists after call
      - `File` node(s) exist after call
      - `MODIFIES` edge exists
      - `COMMIT_INGESTED` Judgment exists
      - `run()` returns same id as `ingest_commit()`
  - Files:
    - `src/agents/commit_ingestion.py`
    - `tests/test_commit_ingestion.py`

---

- [x] Task 3: `impact_lookup()` in `memory_api` — tests then implementation (P0)
  - Completed: 2026-06-20 — impact_lookup(driver, file_paths) added to memory_api; UNWIND+MATCH traverses File←IMPLEMENTED_BY←Component←COMPOSED_OF←Functionality←REALIZED_BY←Requirement; returns [] for unknown paths; DISTINCT prevents duplicates; 7 tests green; 285/285 suite; bandit clean
  - Acceptance:
    - `impact_lookup(driver, file_paths: list[str]) -> list[dict]` added to
      `src/memory_api.py`.
    - Traverses upward:
      `(File) ←[IMPLEMENTED_BY]- (Component) ←[COMPOSED_OF]- (Functionality)
               ←[REALIZED_BY]- (Requirement)`
    - Returns `[]` for file paths with no `IMPLEMENTED_BY` edge in the graph.
    - Returns `[{"file_path": str, "component_id": str,
       "functionality_id": str, "requirement_id": str}]` for known files.
    - Uses `DISTINCT` on result rows to avoid duplicates.
    - `tests/test_impact_lookup.py` green with ≥6 tests covering:
      - returns list type
      - empty list for unknown file path
      - finds component when `IMPLEMENTED_BY` edge exists (seeded in fixture)
      - finds requirement via full chain
      - multiple paths returns result for each matched path
      - result dict has all four expected keys
  - Files:
    - `src/memory_api.py`
    - `tests/test_impact_lookup.py`

---

- [x] Task 4: `run_build_cycle()` orchestrator — tests then implementation (P0)
  - Completed: 2026-06-20 — run_build_cycle(driver, b5, b6, b7, scan_path="src") in src/orchestrator.py; sequences b5.run→b6.run→b7.run and returns report_id; 6 pure unit tests with call-tracking stubs (no Neo4j); 291/291 suite; bandit clean
  - Acceptance:
    - `src/orchestrator.py` exists.
    - `run_build_cycle(driver, b5, b6, b7, scan_path: str = "src") -> str`:
      - Calls `b5.run(driver)`.
      - Calls `b6.run(driver, scan_path)`.
      - Calls `b7.run(driver)` and returns its return value (the `report_id`).
    - `tests/test_orchestrator.py` green with ≥4 tests:
      - `run_build_cycle` is importable from `src.orchestrator`
      - returns the `report_id` string from `b7.run()`
      - b5, b6, b7 are each called exactly once (use call flags on stub objects)
      - returned value is a non-empty string starting with `"report-"`
    - Stubs used in tests carry a `called` flag and return canned values;
      no Neo4j connection required for these unit tests.
  - Files:
    - `src/orchestrator.py`
    - `tests/test_orchestrator.py`

---

- [x] Task 5: Enhanced replay script `scripts/replay_meridian.py` (P0)
  - Completed: 2026-06-20 — Self-contained demo script; seeds Meridian graph (B3+B4+IMPLEMENTED_BY), replays 5 commits with formatted per-commit output showing impact chain+health metrics; resets TestRun/SecurityFinding before each cycle for consistent 10-test/10-pass display; --dry-run validates fixtures without Neo4j; 3 dry-run tests green; 294/294 suite; bandit clean
  - Acceptance:
    - `scripts/replay_meridian.py` is a self-contained demo entry point.
    - Seeds the full Meridian graph (B3→B4) at startup so no prior setup is needed.
    - Seeds `IMPLEMENTED_BY` edges connecting the five Meridian components to their
      fixture file paths before replaying commits.
    - For each of the 5 commits in `fixtures/meridian_commits.json`, prints a
      formatted block to stdout:
      ```
      ► Commit b800001  "Add input validation for account opening"
        Changed:  src/account/AccountController.java
        Impact:   comp-account-opening → func-account-opening → req-001
        B5:  10 tests run, 10 pass
        B6:  1 open finding (LOW)
        B7:  report-<id>  coverage 100.0%  1 open finding
        ✓  COMMIT_INGESTED
      ```
    - Prints a closing line after all commits:
      `"5/5 commits ingested. Run scripts/demo_summary.py to inspect graph."`
    - Supports `--dry-run` flag: validates fixtures and exits 0 without touching Neo4j.
    - Uses stub agents throughout (stub `llm_fn`, stub `run_fn`, stub `scan_fn`)
      so no live service calls are made.
    - `impact_lookup()` result is used to populate the "Impact:" line.
    - Bandit scan of `scripts/replay_meridian.py` produces zero findings.
  - Files:
    - `scripts/replay_meridian.py`

---

- [x] Task 6: Demo summary script `scripts/demo_summary.py` (P0)
  - Completed: 2026-06-20 — Read-only query script; shows commit count, coverage_summary(), security_summary(), report count, judgment counts, and structural provenance chain (Req→Func→Comp→File←Commit) with graceful fallback; --req flag for any requirement; 3 tests green; 297/297 suite; bandit clean
  - Acceptance:
    - `scripts/demo_summary.py` is a read-only query script — no writes to Neo4j.
    - When run after `replay_meridian.py`, prints a formatted graph summary:
      ```
      CoGMEM-QA — Graph Summary
      ==========================
      Commits ingested:    5
      Coverage:          100.0%  (10/10 ACs)
      Open findings:       1      (low: 1, medium: 0, high: 0)
      Reports generated:   5

      Audit trail for req-001 (Account Opening):
        req-001 → func-account-opening → comp-account-opening
                → src/account/AccountController.java ← Commit b800001
        Judgments: COMMIT_INGESTED, HEALTH_REPORT_GENERATED
      ```
    - Counts are queried live from Neo4j (not hardcoded).
    - Commit count = `MATCH (c:Commit) WHERE c.sha STARTS WITH 'b8000' RETURN count(c)`.
    - Coverage and open findings come from `coverage_summary()` and
      `security_summary()` in `memory_api`.
    - Report count = `MATCH (r:Report) RETURN count(r)`.
    - Audit trail uses `audit_trail(driver, "req-001")` from `memory_api`; if
      the result is empty, prints `"  (no complete audit trail found)"` instead
      of crashing.
    - Supports `--req <id>` flag to print the audit trail for a different
      requirement (defaults to `req-001`).
    - Bandit scan of `scripts/demo_summary.py` produces zero findings.
  - Files:
    - `scripts/demo_summary.py`

---

- [x] Task 7: Phase 5 gate test `tests/test_e2e_phase5.py` (P0)
  - Completed: 2026-06-20 — test_build_cycle_replay_e2e passes in 1.1s; _clean_phase5_nodes scrubs Commits/Files/Reports/Judgments/TestRuns/SecurityFindings; seeds IMPLEMENTED_BY for 3 Meridian components; replays 3 commits via B8+run_build_cycle; asserts 3 Commit nodes, 3 COMMIT_INGESTED Judgments, 3 distinct Report IDs, impact_lookup finds comp-account-opening; 298/298 suite; bandit clean
  - Acceptance: `tests/test_e2e_phase5.py::test_build_cycle_replay_e2e` passes.
    The test (no live LLM, all stub agents):
    1. Calls `_clean_phase5_nodes(driver)` — deletes `Commit` nodes with
       sha in `["b800001","b800002","b800003"]`, related `File` nodes seeded
       for this test, all `Report` nodes, all `COMMIT_INGESTED` Judgments,
       and stale non-Meridian `AcceptanceCriterion` nodes.
    2. Re-seeds Meridian graph via B3+B4 stubs (reuses phase 4 e2e helpers).
    3. Seeds `IMPLEMENTED_BY` edges: for each of the 3 test commits, creates a
       `File` node (if absent) and links it to the corresponding Meridian component.
    4. Loops over first 3 commits (sha `b800001`–`b800003`):
       a. `b8.ingest_commit(driver, commit_data)` — commit ingested
       b. `run_build_cycle(driver, b5_stub, b6_stub, b7_stub)`
    5. Asserts (after all 3 commits processed):
       - 3 `Commit` nodes exist with `sha IN ["b800001","b800002","b800003"]`
       - 3 `Judgment(label="COMMIT_INGESTED")` nodes exist
       - 3 distinct `Report` nodes exist
       - `impact_lookup(driver, ["src/account/AccountController.java"])`
         returns ≥1 row with `component_id == "comp-account-opening"`
  - Files:
    - `tests/test_e2e_phase5.py`

---

- [x] Task 8: Full test suite green + bandit clean (P0)
  - Completed: 2026-06-20 — 298/298 tests green (0 failures, 0 skips); bandit -r src/ produces no output; replay_meridian.py --dry-run exits 0
  - Acceptance:
    - `pytest tests/` returns 0 failures and 0 skips (all prior + Sprint v5 tests).
    - `python -m bandit -r src/ -f txt -q` produces no output (zero findings).
    - `python scripts/replay_meridian.py --dry-run` exits 0.
  - Files: none (verification only)

---

## Task Order & Dependencies

```
Task 1  (commit fixture data)
  └── Task 2  (CommitIngestionAgent + tests)
        └── Task 3  (impact_lookup + tests)
              └── Task 4  (orchestrator + tests)
                    ├── Task 5  (replay script — uses Tasks 2, 3, 4)
                    │     └── Task 6  (demo_summary — read-only; depends on replay seeding graph)
                    └── Task 7  (phase 5 gate e2e — uses Tasks 2, 3, 4)
                          └── Task 8  (full suite + bandit + dry-run smoke)
```

## Demo flow (two commands, no git)

```bash
python scripts/replay_meridian.py    # seeds Meridian graph + replays 5 commits
python scripts/demo_summary.py       # prints live graph state + audit trail
```

## Sprint v5 Definition of Done

- [x] `CommitIngestionAgent.ingest_commit()` unit-tested green
- [x] `impact_lookup()` unit-tested green (finds chain; returns [] for unknown files)
- [x] `run_build_cycle()` unit-tested green
- [x] `scripts/replay_meridian.py` prints formatted per-commit output for all 5 commits
- [x] `scripts/demo_summary.py` prints live graph state + audit trail
- [x] `scripts/replay_meridian.py --dry-run` exits 0
- [x] `tests/test_e2e_phase5.py::test_build_cycle_replay_e2e` green
- [x] `pytest tests/` all green, no regressions (298/298)
- [x] `python -m bandit -r src/ -q` clean
