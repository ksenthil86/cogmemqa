# Sprint v2 — PRD: Bootstrap & Test Design (B3 + B4)

## Overview

Bring the first two agents to life on top of the memory backbone built in Sprint v1.
The **Requirements Parser** (B3) reads a structured product spec and seeds the graph's
requirements + capability layers. The **Test Case Generator** (B4) queries the graph for
uncovered acceptance criteria and proposes Test nodes linked back to those criteria — all
writes go through the B2 memory API so both agents share an identical view of truth.

This sprint produces no UI and no test execution — only graph-resident evidence produced
by LLM-backed agents interacting through the shared Neo4j brain.

---

## Goals

- A `RequirementsParserAgent` (B3) can parse a structured PRD text and populate
  `Requirement`, `AcceptanceCriterion`, `Actor`, `Functionality`, and `Component` nodes
  with all cross-layer edges, writing a provenance `Judgment` for the parse decision.
- Every parse call is idempotent — re-running against an updated spec reconciles changed
  nodes rather than duplicating them.
- A `coverage_gaps()` query returns all `AcceptanceCriterion` nodes that have no
  `COVERS_CRITERION` edge into any `Test` node.
- A `TestCaseGeneratorAgent` (B4) iterates the coverage gaps, proposes test specifications
  per criterion via LLM, ingests `Test` nodes with `COVERS_CRITERION` + `VERIFIES` edges,
  and writes a `Judgment` + `ReasoningTrace` per proposal.
- A phase-2 e2e smoke test seeds the Meridian banking spec, verifies coverage gaps shrink
  after B4 runs, and confirms the audit trail reaches from a `Requirement` down to a `Test`.

---

## User Stories

- As a **QA agent swarm**, I want a bootstrapped requirements + capability graph so that I
  start with a traceable skeleton instead of an empty database.
- As a **Test Case Generator**, I want to query uncovered criteria and link my proposals
  to them so that no acceptance criterion is forgotten and every test has a business anchor.
- As an **auditor**, I want every agent decision (parse, propose) backed by a `Judgment`
  and `ReasoningTrace` so that I can inspect why a node was created and which spec line
  it came from.
- As a **developer**, I want both agents to be testable without live LLM calls so that
  the test suite runs fast and deterministically in CI.

---

## Technical Architecture

### Stack additions (Sprint v2)

| Layer | Technology |
|-------|-----------|
| LLM provider | Google Gemini 2.0 Flash (`google-generativeai>=0.8`) |
| Agent base | `src/agent_base.py` — wraps memory API + LLM client |
| B3 agent | `src/agents/requirements_parser.py` |
| B4 agent | `src/agents/test_case_generator.py` |
| Spec fixture | `fixtures/meridian_spec.md` — Meridian banking PRD (input to B3) |
| ParsedSpec model | Pydantic v2 model in `src/agents/models.py` |
| New memory op | `coverage_gaps()` added to `src/memory_api.py` |
| New env vars | `GEMINI_API_KEY` in `.env` |

> **LLM swappability.** Both agents receive an `llm_fn: Callable[[str], str]` at
> construction time. Tests inject a deterministic stub; production passes the real
> Gemini client. No agent hard-codes a provider.

### Component Diagram

```
 fixtures/meridian_spec.md
          │
          ▼
  RequirementsParserAgent (B3)
    ├─ parse_spec(text)  ──► llm_fn(prompt)  ◄── Gemini / stub
    │      └─ returns ParsedSpec (Pydantic)
    └─ seed_graph(parsed) ──► memory_api.ingest_node / ingest_edge
                           └─► memory_api.write_provenance
                                       │
                                       ▼
                             Neo4j Context Graph (B1/B2)
                   ┌─────── Requirements layer seeded ────────┐
                   │  Requirement  AcceptanceCriterion  Actor  │
                   │  Functionality  Component                 │
                   │  edges: REALIZED_BY, COMPOSED_OF          │
                   │         COVERS_CRITERION skeleton         │
                   └──────────────────────────────────────────┘
                                       │
                           coverage_gaps(driver) ◄── memory_api
                                       │
                                       ▼
  TestCaseGeneratorAgent (B4)
    ├─ propose_tests(gaps) ──► llm_fn(prompt) ◄── Gemini / stub
    │      └─ returns list[ProposedTest] (Pydantic)
    └─ ingest_tests(tests) ──► memory_api.ingest_node / ingest_edge
                           └─► memory_api.write_provenance
                                       │
                                       ▼
                             Neo4j Context Graph
                   ┌─────── Evidence layer seeded ────────────┐
                   │  Test nodes (one per proposed spec)       │
                   │  edges: COVERS_CRITERION, VERIFIES        │
                   │  Judgment + ReasoningTrace per proposal   │
                   └──────────────────────────────────────────┘
```

### Meridian Banking Spec (B3 input)

A concise structured PRD covering a synthetic retail banking app with:
- **5 Requirements** (Account Opening, KYC, Money Transfer, Transaction History,
  Fraud Alerting) carrying `priority` and `reg_control`
- **10 AcceptanceCriteria** (2 per requirement) with `statement` + `status`
- **2 Actors** (Customer, Compliance Officer)
- **5 Functionalities** (one per requirement), **5 Components** (one per functionality)

This fixture is deterministic — B3 tests seed from a known `ParsedSpec` object, not
from a live LLM parse of the markdown.

### ParsedSpec Pydantic model

```python
class ParsedRequirement(BaseModel):
    id: str                          # deterministic slug, e.g. "req-kyc"
    title: str
    priority: str                    # "P0" / "P1" / "P2"
    reg_control: Optional[str]
    acceptance_criteria: list[ParsedAC]
    functionality_id: str            # slug for the derived Functionality node
    functionality_name: str
    component_id: str                # slug for the derived Component node
    component_name: str

class ParsedAC(BaseModel):
    id: str                          # deterministic slug, e.g. "ac-kyc-1"
    statement: str
    actor_role: Optional[str]

class ParsedSpec(BaseModel):
    actors: list[ParsedActor]
    requirements: list[ParsedRequirement]
```

### LLM Prompt Strategy

**B3 prompt** asks Gemini to read the PRD text and return a JSON object matching
`ParsedSpec`. The prompt includes:
- The schema definition (field names + types)
- The full PRD text
- An instruction to use deterministic slug IDs

**B4 prompt** (per coverage gap) asks Gemini to propose one test specification for a
given `AcceptanceCriterion` statement. It returns a `ProposedTest` JSON object with:
`name`, `type` ("api" | "ui" | "unit"), `verifies_functionality_id`.

### coverage_gaps() Cypher

```cypher
MATCH (ac:AcceptanceCriterion)
OPTIONAL MATCH (t:Test)-[:COVERS_CRITERION]->(ac)
WITH ac, count(t) AS test_count
WHERE test_count = 0
MATCH (r:Requirement)-[:REALIZED_BY]->(:Functionality)
      <-[:VERIFIES]-(:Test)
      , (r)-[:COVERS_CRITERION]->(ac)
...
```

Simpler form used in implementation:

```cypher
MATCH (ac:AcceptanceCriterion)
WHERE NOT (:Test)-[:COVERS_CRITERION]->(ac)
OPTIONAL MATCH (r:Requirement)--(ac)
RETURN ac.id AS ac_id, ac.statement AS statement, r.id AS req_id
```

### Data Flow

```
B3 RUN:
  parse_spec(spec_text)
    → prompt Gemini → JSON → ParsedSpec (validated)
  seed_graph(parsed)
    → for each requirement:
        ingest_node(Requirement)
        ingest_node(Functionality) + ingest_edge(REALIZED_BY)
        ingest_node(Component)     + ingest_edge(COMPOSED_OF)
        for each AC:
          ingest_node(AcceptanceCriterion)
        for each actor:
          ingest_node(Actor)
    → write_provenance(Judgment("parsing complete"), [trace], informed_by=[req_ids])

B4 RUN:
  gaps = coverage_gaps(driver)
  for each gap:
    proposed = llm_fn(prompt_for_gap)
    test = Test(...)
    ingest_node(test)
    ingest_edge(COVERS_CRITERION: test → ac)
    ingest_edge(VERIFIES: test → functionality)
    write_provenance(Judgment("test proposed"), [trace], informed_by=[ac_id])
```

---

## Out of Scope (v3+)

- Test execution (Playwright / HTTP runner) — that is B5 (Phase 3)
- Security scanning agent — B6 (Phase 3)
- Any real banking application code to test against — B11 (Phase 6)
- FastAPI HTTP transport wrapper around memory_api
- QA Supervisor Agent — B7 (Phase 4)
- Coding Agent / build-cycle integration — B8 (Phase 4)
- Re-ranking or embedding-based retrieval enhancements
- The `LINT` memory operation — B9 (Phase 5)
- CoGMEM-Inspector UI — B10 (Phase 5)

---

## Dependencies

- **Sprint v1 complete** — B1 (graph + schema) and B2 (memory API: INGEST, RETRIEVE,
  RECONCILE, write_provenance, audit_trail) must be green. `pytest tests/` must pass 77
  tests with no skips.
- **Gemini API key** — `GEMINI_API_KEY` must be set in `.env` for live agent runs.
  Tests use an injected stub so CI does not require the key.
- **No new infrastructure** — Neo4j still runs via Docker Compose from Sprint v1.
  No new Docker services are added in this sprint.

---

## Sprint v2 Definition of Done

- [ ] `pytest tests/` green with no skips (all Sprint v1 tests + new Sprint v2 tests)
- [ ] `RequirementsParserAgent.seed_graph(ParsedSpec)` correctly seeds and is idempotent
- [ ] `coverage_gaps(driver)` returns the expected set of uncovered criteria
- [ ] `TestCaseGeneratorAgent.ingest_tests(driver, proposed)` ingests tests + provenance
- [ ] `tests/test_e2e_phase2.py::test_bootstrap_and_test_design_e2e` passes green
- [ ] Bandit scan on `src/` is clean
