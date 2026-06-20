# Sprint v4 — Tasks: QA Supervisor (B7)

## Status: Complete (8/8)

---

- [x] Task 1: Extend Report model with health-metric fields (P0)
  - Completed: 2026-06-20 — Added coverage_pct: float=0.0, open_findings_count: int=0, severity_breakdown: str="{}" to Report; 6 new tests (backward compat + integration); full suite 233/233 green; bandit clean
  - Acceptance:
    - `src/models.py` `Report` class gains three new fields with defaults so
      existing graph nodes remain valid:
      ```python
      coverage_pct:        float = 0.0
      open_findings_count: int   = 0
      severity_breakdown:  str   = "{}"   # JSON string
      ```
    - `ingest_node(driver, Report(id="r-1", summary="test", created_at=now,
      coverage_pct=75.0, open_findings_count=2, severity_breakdown='{"low":2}'))`
      writes and reads back all three fields via a direct Cypher query.
    - `tests/test_models.py` still passes (backward compatibility confirmed by
      instantiating `Report` with only `id`, `summary`, `created_at`).
  - Files:
    - `src/models.py`

---

- [x] Task 2: Add `coverage_summary()` to memory_api (P0)
  - Completed: 2026-06-20 — Added coverage_summary(driver)->dict with Cypher aggregate; failing TestRuns excluded; 7 tests in test_coverage_summary.py; 240/240 green; bandit clean
  - Acceptance:
    - `coverage_summary(driver) -> dict` added to `src/memory_api.py`.
    - Returns `{"total_ac": N, "covered_ac": M, "coverage_pct": float}`.
    - "Covered" = at least one `TestRun(outcome="pass")` reachable via
      `INSTANCE_OF → Test → COVERS_CRITERION → AcceptanceCriterion`.
    - Seeded scenario A (0 ACs): returns `{"total_ac": 0, "covered_ac": 0, "coverage_pct": 0.0}`.
    - Seeded scenario B (4 ACs, 2 covered by a passing TestRun): `coverage_pct == 50.0`.
    - Seeded scenario C (all 4 covered): `coverage_pct == 100.0`.
    - A failing TestRun (outcome="fail") does NOT count as coverage.
    - Unit tests in `tests/test_coverage_summary.py`.
  - Files:
    - `src/memory_api.py`
    - `tests/test_coverage_summary.py`

---

- [x] Task 3: Add `security_summary()` to memory_api (P0)
  - Completed: 2026-06-20 — Added security_summary(driver)->dict; status="open" filter; always returns all 3 severity keys; total_open == sum(by_severity); 7 tests green; 247/247 suite; bandit clean
  - Acceptance:
    - `security_summary(driver) -> dict` added to `src/memory_api.py`.
    - Returns `{"total_open": N, "by_severity": {"low": L, "medium": M, "high": H}}`.
    - Only counts `SecurityFinding` nodes with `status="open"`.
    - Closed findings (`status="closed"`) are excluded.
    - Severities not present in the graph are returned as `0` (not omitted).
    - Seeded scenario: 2 low + 1 medium open, 1 high closed → `{"total_open": 3,
      "by_severity": {"low": 2, "medium": 1, "high": 0}}`.
    - Empty graph → `{"total_open": 0, "by_severity": {"low": 0, "medium": 0, "high": 0}}`.
    - Unit tests in `tests/test_security_summary.py`.
  - Files:
    - `src/memory_api.py`
    - `tests/test_security_summary.py`

---

- [x] Task 4: Scaffold QASupervisorAgent (B7) (P0)
  - Completed: 2026-06-20 — Created src/agents/qa_supervisor.py; inherits BaseAgent; no run_fn/scan_fn; compute_health() merges coverage_summary()+security_summary(); tests green
  - Acceptance:
    - `src/agents/qa_supervisor.py` exists and is importable.
    - `QASupervisorAgent` inherits `BaseAgent`.
    - `__init__(role="qa_supervisor", driver=None, llm_fn=call_llm)` — no `run_fn`
      or `scan_fn` (the supervisor uses only Cypher; LLM is optional for summary
      text generation but receives a stub in tests).
    - `compute_health(driver) -> dict` method exists and calls `coverage_summary()`
      and `security_summary()` from `memory_api`, merging results:
      ```python
      {
        "coverage_pct": float,
        "covered_ac": int,
        "total_ac": int,
        "open_findings_count": int,
        "by_severity": {"low": int, "medium": int, "high": int},
      }
      ```
    - Unit tests: importable, `issubclass(QASupervisorAgent, BaseAgent)`,
      `compute_health()` returns expected keys.
  - Files:
    - `src/agents/qa_supervisor.py`
    - `tests/test_qa_supervisor.py` (Tasks 4–6 share this file)

---

- [x] Task 5: Implement `generate_report()` → Report node + Judgment (P0)
  - Completed: 2026-06-20 — generate_report() ingests Report node (coverage_pct, open_findings_count, severity_breakdown JSON), writes HEALTH_REPORT_GENERATED Judgment+ReasoningTrace informed_by passing TestRun+open SecurityFinding ids; tests green
  - Acceptance:
    - `generate_report(driver) -> str` method on `QASupervisorAgent`.
    - Calls `compute_health(driver)` internally.
    - Ingests a `Report` node with:
      - `id = f"report-{sha256(str(now_ms))[:10]}"` (deterministic per millisecond)
      - `summary` = LLM-generated or stub-generated one-liner describing the metrics
      - `coverage_pct`, `open_findings_count`, `severity_breakdown` populated
      - `created_at` set to `datetime.now(timezone.utc)`
    - Writes `Judgment(label="HEALTH_REPORT_GENERATED")` + `ReasoningTrace` via
      `write_provenance`, with `informed_by` = list of passing TestRun ids + open
      SecurityFinding ids (or `["report-summary"]` if none exist).
    - Returns the `report_id` string.
    - Integration tests:
      - Seed a passing TestRun and an open SecurityFinding before calling.
      - Assert `Report` node exists with correct `coverage_pct` ≥ 0.0.
      - Assert `Judgment(label="HEALTH_REPORT_GENERATED")` exists.
      - Assert `ReasoningTrace` linked to that Judgment exists.
  - Files:
    - `src/agents/qa_supervisor.py`
    - `tests/test_qa_supervisor.py`

---

- [x] Task 6: Implement `run()` orchestrator (P0)
  - Completed: 2026-06-20 — run() delegates to generate_report(); two calls produce distinct report ids (new snapshot each time); tests green; 265/265 suite; bandit clean
  - Acceptance:
    - `run(driver) -> str` method on `QASupervisorAgent` that calls
      `generate_report(driver)` and returns the `report_id`.
    - Calling `run()` twice produces two distinct `Report` node ids
      (each call is a new snapshot; idempotency is NOT required here — each
      call represents a new health check).
    - Integration test:
      - Call `b7.run(driver)` with stub `llm_fn` returning `"Health OK"`.
      - Assert the returned string starts with `"report-"`.
      - Assert a `Report` node with that id exists in the graph.
      - Assert a `Judgment(label="HEALTH_REPORT_GENERATED")` node exists.
  - Files:
    - `src/agents/qa_supervisor.py`
    - `tests/test_qa_supervisor.py`

---

- [x] Task 7: Phase 4 e2e smoke test (P0)
  - Completed: 2026-06-20 — test_health_report_e2e passes; _clean_phase4_nodes scrubs stale ACs from prior sessions ensuring coverage_pct==100.0; all 9 assertions green
  - Acceptance: `tests/test_e2e_phase4.py::test_health_report_e2e` passes.
    The test (no live LLM, stub run_fn for B5, stub scan_fn for B6):
    1. Re-seeds Meridian graph via B3 + B4 stubs (same helpers as phase 2/3 e2e).
    2. Runs B5 with stub run_fn: all 10 calls return 200 (all pass, so
       `covered_ac` will be 10 and `coverage_pct` will be 100.0).
    3. Runs B6 with stub scan_fn returning 1 open LOW finding with
       filename `"src/account/account_stub.py"`.
    4. Instantiates `QASupervisorAgent` with stub `llm_fn` returning `"Health OK"`.
    5. Calls `b7.run(driver)` → asserts return value is a non-empty string.
    6. Asserts `Report` node exists with `coverage_pct == 100.0`.
    7. Asserts `Report.open_findings_count == 1`.
    8. Asserts `Judgment(label="HEALTH_REPORT_GENERATED")` exists.
    9. Asserts `severity_breakdown` JSON parses and contains `"low": 1`.
  - Files:
    - `tests/test_e2e_phase4.py`

---

- [x] Task 8: Full test suite green + bandit clean (P0)
  - Completed: 2026-06-20 — 266/266 tests green; bandit -r src/ produces no output
  - Acceptance:
    - `pytest tests/` returns 0 failures and 0 skips (all prior + Sprint v4 tests).
    - `python -m bandit -r src/ -f txt -q` produces no output (zero findings).
  - Files: none (verification only)

---

## Task Order & Dependencies

```
Task 1  (extend Report model)
  └── Task 2  (coverage_summary query)
        └── Task 3  (security_summary query)
              └── Task 4  (QASupervisorAgent scaffold + compute_health)
                    └── Task 5  (generate_report → Report + Judgment)
                          └── Task 6  (run() orchestrator)
                                └── Task 7  (Phase 4 e2e)
                                      └── Task 8  (full suite + bandit)
```

## Sprint v4 Definition of Done

- [x] `coverage_summary()` and `security_summary()` unit-tested green
- [x] `Report` model extended (backward-compatible)
- [x] `QASupervisorAgent.run(driver)` ingests `Report` + `HEALTH_REPORT_GENERATED` Judgment
- [x] `tests/test_qa_supervisor.py` green (18 tests)
- [x] `tests/test_e2e_phase4.py::test_health_report_e2e` green
- [x] `pytest tests/` all green, no regressions (266/266)
- [x] Bandit scan on `src/` clean
