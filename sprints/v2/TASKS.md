# Sprint v2 — Tasks: Bootstrap & Test Design (B3 + B4)

## Status: In Progress (8/10 complete)

---

- [x] Task 1: LLM client singleton + BaseAgent scaffold (P0)
  - Acceptance:
    - `google-generativeai>=0.8` added to `pyproject.toml` dev + runtime deps.
    - `src/llm.py` exposes `get_gemini_client()` (singleton, reads `GEMINI_API_KEY`
      from `.env`).
    - `src/agent_base.py` defines `BaseAgent(role: str, driver: Driver, llm_fn: Callable[[str], str])`.
      `BaseAgent` stores `self.role`, `self.driver`, `self.llm_fn`. Provides
      `self.retrieve(entity_id, depth)` and `self.write_provenance(...)` convenience
      wrappers that delegate to `memory_api`.
    - `python -c "from src.agent_base import BaseAgent"` imports cleanly.
    - `.env.example` updated with `GEMINI_API_KEY=your_key_here`.
  - Files:
    - `src/llm.py` — `get_gemini_client() -> genai.GenerativeModel`
    - `src/agent_base.py` — `BaseAgent` class
    - `pyproject.toml` — add `google-generativeai>=0.8` to dependencies
    - `.env.example` — add `GEMINI_API_KEY`
  - Completed: 2026-06-19 — Used google-genai>=1.0 (new SDK; google-generativeai is
    deprecated as of 2025). get_gemini_client() is @lru_cache singleton raising ValueError
    with no key. call_llm() wraps genai.Client.models.generate_content(). BaseAgent stores
    role/driver/llm_fn; retrieve() and write_provenance() delegate to memory_api.
    call_llm is the default llm_fn (injectable for testing). 10 tests green; bandit clean.

---

- [x] Task 2: ParsedSpec Pydantic models + Meridian banking fixture (P0)
  - Acceptance:
    - `src/agents/models.py` defines `ParsedActor`, `ParsedAC`, `ParsedRequirement`,
      `ParsedSpec` as Pydantic v2 models.
    - `fixtures/meridian_spec.md` is a structured PRD for Meridian Bank containing exactly
      5 Requirements, 10 AcceptanceCriteria (2 per req), 2 Actors, 5 Functionalities,
      5 Components. All requirement IDs use deterministic slugs (e.g. `req-account-opening`).
    - `fixtures/meridian_parsed.py` (or `.json`) is the ground-truth `ParsedSpec` instance
      matching the Meridian spec — used by tests to seed the graph without an LLM call.
    - `python -c "from src.agents.models import ParsedSpec"` imports cleanly.
  - Files:
    - `src/agents/__init__.py`
    - `src/agents/models.py` — `ParsedActor`, `ParsedAC`, `ParsedRequirement`, `ParsedSpec`
    - `fixtures/meridian_spec.md` — Meridian Bank PRD
    - `fixtures/meridian_parsed.json` — ground-truth JSON for `ParsedSpec`
  - Completed: 2026-06-19 — ParsedActor/ParsedAC/ParsedRequirement/ParsedSpec in
    src/agents/models.py; ProposedTest also defined here (needed by Task 7). Meridian
    spec covers 5 banking requirements (Account Opening, KYC, Money Transfer, Transaction
    History, Fraud Alerting), 10 ACs (2 each), 2 Actors, 5 Functionalities, 5 Components.
    All IDs are deterministic slugs. 21 unit tests green; bandit clean; 108 total.

---

- [x] Task 3: B3 — `parse_spec()`: LLM prompt → validated ParsedSpec (P0)
  - Acceptance:
    - `src/agents/requirements_parser.py` defines `RequirementsParserAgent(BaseAgent)`.
    - `agent.parse_spec(spec_text: str) -> ParsedSpec` builds a prompt instructing the LLM
      to return JSON matching the `ParsedSpec` schema, calls `self.llm_fn(prompt)`, strips
      markdown fences, and validates with `ParsedSpec.model_validate_json(raw)`.
    - Raises `ValueError` with a clear message if the JSON is malformed.
    - Unit test with a stub `llm_fn` that returns pre-baked JSON confirms the method
      parses and validates correctly.
    - Unit test confirms malformed JSON raises `ValueError`.
  - Files:
    - `src/agents/requirements_parser.py` — `RequirementsParserAgent.parse_spec()`
    - `tests/test_requirements_parser.py` — unit tests (stub `llm_fn`, no Neo4j)
  - Completed: 2026-06-19 — Prompt embeds schema field names, rules for deterministic
    slugs, and the spec text; instructs LLM to return JSON only (no fences). _strip_fences()
    uses two regex substitutions to remove ```[lang]\n and \n``` from any side of the
    response. model_validate_json() re-raises as ValueError with context on failure.
    12 unit tests: valid JSON, fenced JSON, wrong-schema JSON, empty response, prompt
    content checks. 120 total tests green; bandit clean.

---

- [x] Task 4: B3 — `seed_graph()`: ingest requirements + capability skeleton (P0)
  - Acceptance:
    - `agent.seed_graph(driver, parsed: ParsedSpec) -> list[str]` (returns requirement ids)
      ingests for each `ParsedRequirement`:
        - `Requirement` node, `Functionality` node, `Component` node
        - `REALIZED_BY` edge (Req → Func) and `COMPOSED_OF` edge (Func → Comp)
      and for each `ParsedAC`:
        - `AcceptanceCriterion` node (but no `COVERS_CRITERION` to a Test yet — gap for B4)
      and for each `ParsedActor`: `Actor` node.
    - Calling `seed_graph` twice with the same `ParsedSpec` is idempotent: node count
      does not increase (MERGE-based via `ingest_node`).
    - Integration test (uses `neo4j_driver` fixture):
        - Seed Meridian `ParsedSpec` once → assert 5 Requirement nodes exist.
        - Seed twice → assert still 5 Requirement nodes (idempotency).
        - Assert `REALIZED_BY` edges exist from each Req to its Functionality.
  - Files:
    - `src/agents/requirements_parser.py` — `RequirementsParserAgent.seed_graph()`
    - `tests/test_requirements_parser.py` — integration tests added
  - Completed: 2026-06-19 — seed_graph() iterates ParsedActor → Actor nodes, then per
    ParsedRequirement: Functionality + Component + Requirement nodes, REALIZED_BY and
    COMPOSED_OF edges (with datetime.now(utc) valid_from), then AcceptanceCriterion
    nodes per AC. All 10 integration tests green (node counts, edge existence,
    idempotency). 130 total tests green; bandit clean.

---

- [x] Task 5: B3 — provenance write after seed + `run()` orchestrator (P0)
  - Acceptance:
    - After `seed_graph`, the agent calls `write_provenance` with:
        - A `Judgment(agent_role="requirements_parser", label="SEEDED")` node.
        - One `ReasoningTrace` listing the count of seeded requirements.
        - `informed_by_ids` = all ingested requirement ids.
    - `agent.run(spec_text: str) -> str` orchestrates `parse_spec → seed_graph →
      write_provenance` and returns the Judgment id.
    - Integration test: call `run()` with a stub `llm_fn` (returns Meridian JSON) and
      assert that a `Judgment` node with `label="SEEDED"` exists in Neo4j and has
      `INFORMED_BY` edges to at least one Requirement.
  - Files:
    - `src/agents/requirements_parser.py` — provenance + `run()` method
    - `tests/test_requirements_parser.py` — provenance integration test added
  - Completed: 2026-06-19 — run() hashes spec_text (SHA-256 first 12 chars) to build
    deterministic judgment_id and trace_id; Judgment(label="SEEDED"), ReasoningTrace
    (decision="Seeded N requirements..."), INFORMED_BY edges to all 5 req ids.
    Idempotent: same spec → same hash → same MERGE node. 6 new integration tests green
    (return type, Judgment node, HAS_STEP→ReasoningTrace, INFORMED_BY×5, graph seeds,
    idempotency). 136 total tests green; bandit clean.

---

- [x] Task 6: `coverage_gaps()` Cypher query in `src/memory_api.py` (P1)
  - Acceptance:
    - `memory_api.coverage_gaps(driver) -> list[dict]` runs:
      ```cypher
      MATCH (ac:AcceptanceCriterion)
      WHERE NOT (:Test)-[:COVERS_CRITERION]->(ac)
      OPTIONAL MATCH (r:Requirement)<-[:REALIZED_BY]-(:Functionality)<-[:VERIFIES]-(:Test),
                     (ac)<-[:COVERS_CRITERION]-(:Test)
      RETURN ac.id AS ac_id, ac.statement AS statement
      ```
      (simplified: just `MATCH (ac) WHERE NOT (:Test)-[:COVERS_CRITERION]->(ac)
      RETURN ac.id, ac.statement`)
    - Returns `[]` when all criteria are covered.
    - Integration tests (`tests/test_coverage_gap.py`):
        - Seed 2 AcceptanceCriteria with no Tests → `coverage_gaps()` returns 2 rows.
        - Add a `COVERS_CRITERION` edge to one → returns 1 row.
        - Add to the second → returns `[]`.
  - Files:
    - `src/memory_api.py` — `coverage_gaps(driver) -> list[dict]`
    - `tests/test_coverage_gap.py` — 6 integration tests
  - Completed: 2026-06-19 — Single-query Cypher: MATCH (ac:AcceptanceCriterion) WHERE
    NOT (:Test)-[:COVERS_CRITERION]->(ac) RETURN ac.id AS ac_id, ac.statement AS
    statement. Returns list[dict]. Tests use autouse fixture to DETACH DELETE the 4
    test-specific nodes before each test (prevents state leakage across sessions from
    the session-scoped neo4j_driver). Checks by ID membership, not total count, to
    survive alongside Meridian ACs seeded by other test modules. 142 total tests
    green; bandit clean.

---

- [x] Task 7: B4 — `propose_tests()`: LLM prompt per gap → ProposedTest models (P1)
  - Acceptance:
    - `src/agents/models.py` adds `ProposedTest(BaseModel)` with fields:
        `ac_id: str`, `name: str`, `type: Literal["api", "ui", "unit"]`,
        `verifies_functionality_id: str`, `description: Optional[str]`.
    - `src/agents/test_case_generator.py` defines `TestCaseGeneratorAgent(BaseAgent)`.
    - `agent.propose_tests(gaps: list[dict]) -> list[ProposedTest]` iterates gaps,
      builds a prompt per gap (includes `ac_id`, `statement`, asks for JSON), calls
      `self.llm_fn(prompt)`, validates, collects results. Skips gaps where LLM returns
      malformed JSON (logs warning, continues).
    - Unit tests with stub `llm_fn`:
        - Stub returns valid JSON → list of `ProposedTest` objects returned.
        - Stub returns malformed JSON for one gap → that gap skipped, others processed.
  - Files:
    - `src/agents/models.py` — add `ProposedTest` (was already defined in Task 2)
    - `src/agents/test_case_generator.py` — `TestCaseGeneratorAgent.propose_tests()`
    - `tests/test_test_case_generator.py` — unit tests (stub `llm_fn`, no Neo4j)
  - Completed: 2026-06-19 — TestCaseGeneratorAgent(BaseAgent) with propose_tests():
    one LLM call per gap, prompt embeds ac_id + statement, asks for JSON ProposedTest.
    _strip_fences() strips markdown code fences. Malformed JSON → log.warning + skip,
    processing continues. 12 unit tests: import, inheritance, valid/empty/malformed
    responses, prompt content checks, fence stripping, one-call-per-gap. 154 total
    tests green; bandit clean.

---

- [x] Task 8: B4 — `ingest_tests()`: Test nodes + edges + provenance (P1)
  - Acceptance:
    - `agent.ingest_tests(driver, proposed: list[ProposedTest]) -> list[str]`
      (returns Test node ids).
    - For each `ProposedTest`:
        - Ingests `Test` node (id from `proposed.ac_id + "-test"`, or uuid-based).
        - Ingests `COVERS_CRITERION` edge: Test → AcceptanceCriterion.
        - Ingests `VERIFIES` edge: Test → Functionality (uses `verifies_functionality_id`).
        - Calls `write_provenance` with `Judgment(label="TEST_PROPOSED")`,
          one `ReasoningTrace(decision=proposed.name)`, `informed_by_ids=[proposed.ac_id]`.
    - Integration tests (uses `neo4j_driver` fixture, no live LLM):
        - Seed 2 AC nodes + 1 Functionality node, then call `ingest_tests` with 2
          `ProposedTest` objects → assert 2 Test nodes exist with correct edges.
        - Assert `coverage_gaps()` returns `[]` after ingestion.
        - Assert 2 Judgment nodes with `label="TEST_PROPOSED"` exist.
    - `agent.run(driver) -> list[str]` orchestrates
      `coverage_gaps → propose_tests → ingest_tests` and returns test ids.
  - Files:
    - `src/agents/test_case_generator.py` — `ingest_tests()` + `run()` method
    - `tests/test_test_case_generator.py` — integration tests added
  - Completed: 2026-06-19 — ingest_tests(): Test node id = ac_id+"-test";
    COVERS_CRITERION (Test→AC) + VERIFIES (Test→Func) edges; Judgment(label=
    "TEST_PROPOSED") + ReasoningTrace + INFORMED_BY→AC per proposed test.
    run(): coverage_gaps → propose_tests → ingest_tests. 7 integration tests:
    return ids, Test nodes, COVERS/VERIFIES edges, coverage_gaps closes,
    Judgment count, run() e2e gap closure. 161 total tests green; bandit clean.

---

- [ ] Task 9: Bandit scan + pyproject.toml deps lock (P0)
  - Acceptance:
    - `python -m bandit -r src/ -q` exits 0 (no findings in new agent code).
    - `pyproject.toml` includes `google-generativeai>=0.8` under `[project.dependencies]`.
    - `.env.example` has `GEMINI_API_KEY=your_key_here`.
    - All Sprint v1 tests still pass (`pytest tests/ -q` shows 77+ tests, 0 failures).
  - Files:
    - `pyproject.toml` — updated dependencies
    - `.env.example` — updated

---

- [ ] Task 10: Phase 2 e2e smoke test (P0)
  - Acceptance: `tests/test_e2e_phase2.py::test_bootstrap_and_test_design_e2e` passes.
    The test uses a stub `llm_fn` (no live LLM calls) and:
    1. Calls `provision_schema` (idempotent, reuses Sprint v1 provisioner).
    2. Instantiates `RequirementsParserAgent` with stub returning Meridian JSON.
    3. Calls `agent.run(meridian_spec_text)` → asserts 5 Requirement nodes + 5
       Functionality nodes + 10 AcceptanceCriterion nodes exist in graph.
    4. Asserts `coverage_gaps(driver)` returns 10 gaps (no tests yet).
    5. Instantiates `TestCaseGeneratorAgent` with stub returning valid `ProposedTest` JSON.
    6. Calls `agent.run(driver)` → asserts 10 Test nodes exist with `COVERS_CRITERION` edges.
    7. Asserts `coverage_gaps(driver)` returns `[]` (all criteria covered).
    8. Calls `audit_trail(driver, first_requirement_id)` → asserts non-empty (Req → Func
       chain is now reachable).
    9. Asserts at least one `Judgment` with `label="TEST_PROPOSED"` exists.
  - Files:
    - `tests/test_e2e_phase2.py` — single test function `test_bootstrap_and_test_design_e2e`

---

## Task Order & Dependencies

```
Task 1 (LLM client + BaseAgent)
  └── Task 2 (ParsedSpec models + Meridian fixture)
        └── Task 3 (B3 parse_spec — unit tests)
              └── Task 4 (B3 seed_graph — integration tests)
                    └── Task 5 (B3 provenance + run())
                          └── Task 6 (coverage_gaps query)
                                └── Task 7 (B4 propose_tests — unit tests)
                                      └── Task 8 (B4 ingest_tests + run())
                                            └── Task 9 (bandit + dep check)
                                                  └── Task 10 (Phase 2 e2e)
```

## Sprint v2 Definition of Done

- [ ] `pytest tests/` passes green with no skips
- [ ] `RequirementsParserAgent.run()` seeds Meridian graph (with stub llm_fn)
- [ ] `coverage_gaps()` returns `[]` after B4 ingests tests
- [ ] `tests/test_e2e_phase2.py::test_bootstrap_and_test_design_e2e` is the Phase 2 gate
- [ ] Bandit scan on `src/` is clean
- [ ] No live LLM calls needed to run the test suite
