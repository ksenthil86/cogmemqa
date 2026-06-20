# Sprint v3 — Tasks: Execution & Security (B5 + B6)

## Status: Complete (10/10)

---

- [x] Task 1: Meridian banking app stub — FastAPI ASGI with 5 routes (P0)
  - Acceptance:
    - `fixtures/meridian_app/main.py` defines a FastAPI `app` importable as an
      ASGI application (no external server required for tests).
    - Five endpoints present: `POST /accounts`, `POST /kyc/verify`,
      `POST /transfers`, `GET /transactions`, `GET /fraud/alerts`.
    - `POST /accounts` returns 201 normally; 409 if `body.national_id == "DUPLICATE"`.
    - `POST /transfers` returns 402 with `{"error": "INSUFFICIENT_FUNDS"}` if
      `body.amount > body.balance`; 200 otherwise.
    - `GET /fraud/alerts?amount=N` returns a non-empty list if N > 10000; `[]` otherwise.
    - At least one intentional Bandit finding present in the file (e.g. a
      hardcoded `SECRET_KEY` string constant → B105).
    - `python -c "from fixtures.meridian_app.main import app"` imports cleanly.
  - Files:
    - `fixtures/meridian_app/__init__.py`
    - `fixtures/meridian_app/main.py`
    - `pyproject.toml` — add `fastapi>=0.110`, `httpx>=0.27` to runtime deps
  - Completed: 2026-06-20 — 11/11 tests green; B105 finding confirmed; src/ bandit clean

---

- [x] Task 2: FunctionalTesterAgent scaffold + `run_fn` injection (P0)
  - Acceptance:
    - `src/agents/functional_tester.py` defines `FunctionalTesterAgent(BaseAgent)`.
    - Constructor: `__init__(role, driver, llm_fn, run_fn)` where
      `run_fn: Callable[[dict], dict]` defaults to a real httpx caller.
      Signature: `run_fn({"method", "url", "payload"}) -> {"status_code", "body", "error"}`.
    - `_FUNC_TO_ENDPOINT` dict maps each Meridian `functionality_id` to
      `(method, path)` tuple.
    - `_derive_http_spec(test_node: dict, base_url: str) -> dict` converts a
      Test node dict (from `retrieve()`) into the `run_fn` input dict using the
      endpoint map.
    - Unit tests: importable, inherits `BaseAgent`, `_derive_http_spec` returns
      correct method/url for each Meridian functionality id.
  - Files:
    - `src/agents/functional_tester.py`
    - `tests/test_functional_tester.py` — scaffold unit tests
  - Completed: 2026-06-20 — 8/8 tests green; bandit clean; _derive_http_spec navigates VERIFIES edge

---

- [x] Task 3: `run_http_test(driver, test_id)` → TestRun node (P0)
  - Acceptance:
    - `agent.run_http_test(driver, test_id: str) -> tuple[str, bool]`
      (returns `(test_run_id, passed)`).
    - Retrieves the Test node from the graph (via `self.retrieve(test_id)`).
    - Derives HTTP spec via `_derive_http_spec` using the node's
      `verifies_functionality_id` and `MERIDIAN_APP_URL` env var
      (default: `http://localhost:8000`).
    - Calls `self.run_fn(spec)` → result dict.
    - Outcome: `"pass"` if `status_code < 400 and error is None`, else `"fail"`.
    - Ingests `TestRun(id=f"{test_id}-run-{timestamp_ms}", outcome, timestamp)`.
    - Ingests `INSTANCE_OF` edge: TestRun → Test.
    - Unit tests (stub `run_fn` returning 200 → pass, 409 → fail):
        - Pass outcome creates TestRun with `outcome="pass"`.
        - Fail outcome creates TestRun with `outcome="fail"`.
    - Integration test (neo4j_driver + stub `run_fn`): TestRun node and
      INSTANCE_OF edge exist after call.
  - Files:
    - `src/agents/functional_tester.py` — add `run_http_test()`
    - `tests/test_functional_tester.py` — unit + integration tests added
  - Completed: 2026-06-20 — 13/13 tests green; bandit clean; TestRun+INSTANCE_OF verified in graph

---

- [x] Task 4: `classify_failure(driver, test_id, error_sig)` → category + Judgment (P1)
  - Acceptance:
    - `agent.classify_failure(driver, test_id: str, error_sig: str) -> str`
      returns one of the six category strings:
      `"regression"`, `"environment"`, `"flaky"`, `"spec_gap"`,
      `"data_error"`, `"blocker"`.
    - Prompt includes: AC statement (from `retrieve(test_id)`), the
      `error_sig`, and the last 3 TestRun outcomes for this Test (graph query).
    - `self.llm_fn(prompt)` → strip fences → validate one of 6 categories
      (raises `ValueError` if LLM returns unrecognised category, falls back to
      `"blocker"`).
    - Writes `Judgment(label="FAILURE_CLASSIFIED")` + `ReasoningTrace(decision=category)`
      via `write_provenance`, with `informed_by_ids=[test_id]`.
    - Unit tests (stub `llm_fn` → valid category / invalid → fallback):
        - Valid response returns correct category string.
        - Unknown response falls back to `"blocker"`.
    - Prompt must contain the AC statement and the word "category".
  - Files:
    - `src/agents/functional_tester.py` — add `classify_failure()`
    - `tests/test_functional_tester.py` — unit tests added
  - Completed: 2026-06-20 — 19/19 tests green; bandit clean; all 6 categories + fallback + prompt assertions verified

---

- [x] Task 5: `record_failure(driver, test_id, error_sig, category)` → Failure node (P1)
  - Acceptance:
    - `agent.record_failure(driver, test_id: str, error_sig: str, category: str) -> str`
      returns the Failure node id.
    - Ingests `Failure(id=f"{test_id}-failure", error_signature=error_sig,
      label=category, confidence=0.9)` node.
    - Integration test (neo4j_driver): Failure node exists after call with
      correct `label` property.
  - Files:
    - `src/agents/functional_tester.py` — add `record_failure()`
    - `tests/test_functional_tester.py` — integration test added
  - Completed: 2026-06-20 — 23/23 tests green; bandit clean; 4 tests: return id, label, confidence, idempotency

---

- [x] Task 6: `FunctionalTesterAgent.run(driver, test_ids)` orchestrator (P0)
  - Acceptance:
    - `agent.run(driver, test_ids: list[str] | None = None) -> list[str]`
      (returns list of TestRun ids).
    - If `test_ids` is None: queries graph for all `Test` nodes with
      `type="api"` that have no `INSTANCE_OF` ← TestRun edge yet
      (avoids re-running already-executed tests).
    - For each test_id: `run_http_test()` → if fail: `classify_failure()` +
      `record_failure()`.
    - After all runs: `write_provenance(Judgment(label="FUNCTIONAL_RUN_COMPLETE"),
      [ReasoningTrace(decision=f"Ran {n} tests: {pass_count} passed, {fail_count} failed")],
      informed_by_ids=test_ids)`.
    - Returns list of TestRun node ids.
    - Integration test (neo4j_driver + stub `run_fn` + stub `llm_fn`):
        - Seed 2 Test nodes + their AC nodes.
        - Stub `run_fn`: first test → 200 (pass), second → 409 (fail).
        - Assert 2 TestRun nodes with correct outcomes.
        - Assert 1 Failure node exists (for the failed test).
        - Assert 1 Judgment(label="FAILURE_CLASSIFIED") exists.
        - Assert 1 Judgment(label="FUNCTIONAL_RUN_COMPLETE") exists.
  - Files:
    - `src/agents/functional_tester.py` — add `run()`
    - `tests/test_functional_tester.py` — integration tests added
  - Completed: 2026-06-20 — 29/29 tests green; bandit clean; run() uses _execute_http_test() internal, skips un-routable tests gracefully

---

- [x] Task 7: SecurityTesterAgent scaffold + `scan_bandit(source_path)` (P0)
  - Acceptance:
    - `src/agents/security_tester.py` defines `SecurityTesterAgent(BaseAgent)`.
    - Constructor: `__init__(role, driver, llm_fn, scan_fn)` where
      `scan_fn: Callable[[str], list[dict]]` defaults to a real Bandit runner.
    - Default `scan_fn`: runs `bandit -r {path} -f json -q` via `subprocess.run`,
      parses `results` array from JSON output. Each result dict has at least:
      `filename`, `issue_severity` (`HIGH`/`MEDIUM`/`LOW`), `issue_text`, `test_id`.
    - `_map_file_to_component(filename: str) -> str | None` performs keyword
      matching against the `_FILE_KEYWORDS` dict
      (`"account"→"comp-account-opening"`, `"kyc"→"comp-kyc"`, etc.).
    - Unit tests: importable, inherits BaseAgent, `_map_file_to_component`
      returns correct component slug for each keyword, returns None for unknown.
  - Files:
    - `src/agents/security_tester.py`
    - `tests/test_security_tester.py` — scaffold unit tests
  - Completed: 2026-06-20 — 13/13 tests green; subprocess nosec'd; bandit clean; case-insensitive keyword matching

---

- [x] Task 8: `SecurityTesterAgent.ingest_findings(driver, findings)` → SecurityFinding + AFFECTS (P1)
  - Acceptance:
    - `agent.ingest_findings(driver, findings: list[dict]) -> list[str]`
      returns list of SecurityFinding node ids.
    - For each finding: ingests `SecurityFinding(id=f"finding-{test_id}-{idx}",
      severity=issue_severity.lower(), title=issue_text[:120], status="open")`.
    - If `_map_file_to_component(filename)` returns a non-None slug:
        - Ingests `AFFECTS` edge: SecurityFinding → Component.
    - Writes `Judgment(label="SECURITY_FINDING")` + `ReasoningTrace(decision=issue_text)`
      + `INFORMED_BY` → SecurityFinding node, via `write_provenance`.
    - Integration test (neo4j_driver + stub findings list with known filenames):
        - Assert SecurityFinding nodes created.
        - Assert AFFECTS edges created for findings with mapped component.
        - Assert Judgment(label="SECURITY_FINDING") nodes created.
  - Files:
    - `src/agents/security_tester.py` — add `ingest_findings()`
    - `tests/test_security_tester.py` — integration tests added
  - Completed: 2026-06-20 — 19/19 tests green; bandit clean; filenames must contain keyword (not just directory); 6 integration tests including AFFECTS + no-AFFECTS + Judgment verification

---

- [x] Task 9: `SecurityTesterAgent.run(driver, source_path)` orchestrator (P0)
  - Acceptance:
    - `agent.run(driver, source_path: str) -> list[str]` returns list of
      SecurityFinding ids.
    - Calls `self.scan_fn(source_path)` → raw findings.
    - Calls `self.ingest_findings(driver, raw_findings)` → finding ids.
    - Writes `Judgment(label="SECURITY_SCAN_COMPLETE")` +
      `ReasoningTrace(decision=f"Scanned {source_path}: {n} findings")` +
      `INFORMED_BY` → all finding ids, via `write_provenance`.
    - Returns finding ids.
    - Integration test (neo4j_driver + stub `scan_fn` returning 2 findings):
        - Assert 2 SecurityFinding nodes.
        - Assert Judgment(label="SECURITY_SCAN_COMPLETE") exists.
  - Files:
    - `src/agents/security_tester.py` — add `run()`
    - `tests/test_security_tester.py` — integration tests added
  - Completed: 2026-06-20 — 24/24 tests green; bandit clean; 5 integration tests including scan_fn capture, empty scan, SECURITY_SCAN_COMPLETE judgment

---

- [x] Task 10: Phase 3 e2e smoke test (P0)
  - Acceptance: `tests/test_e2e_phase3.py::test_execution_and_security_e2e` passes.
    The test (no live LLM, no live server, real Bandit on meridian_app source):
    1. Re-uses `_clean_all_meridian()` from phase 2 + re-seeds B3 + B4 via stubs
       (same fixture logic as `test_e2e_phase2.py`).
    2. Instantiates `FunctionalTesterAgent` with stub `run_fn`: first 8 calls return
       200 (pass), last 2 calls return 402 (INSUFFICIENT_FUNDS fail) + stub `llm_fn`
       that returns `"data_error"`.
    3. Calls `b5.run(driver)` → asserts ≥ 10 TestRun nodes exist in graph.
    4. Asserts 2 Failure nodes with `label="data_error"` exist.
    5. Asserts 2 Judgment nodes with `label="FAILURE_CLASSIFIED"` exist.
    6. Asserts 1 Judgment with `label="FUNCTIONAL_RUN_COMPLETE"` exists.
    7. Calls `b6.run(driver, "fixtures/meridian_app")` with real Bandit scan.
    8. Asserts ≥ 1 SecurityFinding node exists (Bandit finds the hardcoded secret).
    9. Asserts ≥ 1 AFFECTS edge exists (finding → comp-account-opening or similar).
   10. Asserts 1 Judgment with `label="SECURITY_SCAN_COMPLETE"` exists.
   11. Verifies INSTANCE_OF chain: TestRun → Test → AcceptanceCriterion queryable.
  - Files:
    - `tests/test_e2e_phase3.py` — single test function `test_execution_and_security_e2e`

---

## Task Order & Dependencies

```
Task 1  (Meridian app stub + pyproject deps)
  └── Task 2  (FunctionalTesterAgent scaffold)
        └── Task 3  (run_http_test + TestRun node)
              └── Task 4  (classify_failure + Judgment)
                    └── Task 5  (record_failure + Failure node)
                          └── Task 6  (run() orchestrator)
                                └── Task 7  (SecurityTesterAgent scaffold)
                                      └── Task 8  (ingest_findings + AFFECTS)
                                            └── Task 9  (run() orchestrator)
                                                  └── Task 10 (Phase 3 e2e)
```

## Sprint v3 Definition of Done

- [x] `pytest tests/` passes green with no skips (227/227)
- [x] `fixtures/meridian_app/main.py` runs as FastAPI ASGI with ≥ 1 Bandit finding
- [x] `FunctionalTesterAgent.run()` writes TestRun + Failure nodes (stub run_fn)
- [x] `SecurityTesterAgent.run()` writes SecurityFinding + AFFECTS (real Bandit)
- [x] `tests/test_e2e_phase3.py::test_execution_and_security_e2e` passes green
- [x] Bandit scan on `src/` is clean (agent code is clean; meridian_app stub is intentionally dirty)
