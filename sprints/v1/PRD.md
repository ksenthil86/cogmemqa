# Sprint v1 — PRD: Memory Backbone (B1 + B2)

## Overview

Stand up the bi-temporal Neo4j context graph and the shared memory API that every
later agent will read and write. This sprint produces no agents — it produces the
**single source of truth** (B1) and the **one typed interface** into it (B2). Nothing
in Phases 2–6 can be built before this sprint is complete.

## Goals

- A YAML schema artifact declaratively defines all four-layer node types and all
  cross-layer edge types; the provisioner applies it to a clean Neo4j instance.
- The graph enforces id-uniqueness constraints and bi-temporal validity intervals
  (`valid_from` / `valid_to`) on every edge.
- A typed Python memory API exposes exactly three operations — `INGEST`, `RETRIEVE`,
  `RECONCILE` — callable by any future agent without touching the driver directly.
- Provenance write-primitives create `Judgment` and `ReasoningTrace` nodes linked via
  `INFORMED_BY` / `HAS_STEP` edges, making every future agent decision auditable.
- A deterministic audit-trail Cypher query traverses the full chain
  `Requirement → Functionality → Component → File → Test → Judgment` in one call.

## User Stories

- As a **QA agent**, I want to write test outcomes and judgments to a shared graph so
  that every other agent can read them without being told about them out-of-band.
- As a **coding agent**, I want to write commit and file-change events to the same graph
  so that the QA agents pick them up automatically on the next retrieve cycle.
- As an **auditor**, I want one deterministic query that traces any shipped change back
  to the business requirement that motivated it, with no similarity thresholds or
  approximations.
- As a **developer**, I want the entire schema to be declared in one YAML artifact and
  applied reproducibly so that I can reset and re-seed the graph in CI without manual
  steps.

## Technical Architecture

### Stack

| Layer | Technology |
|-------|-----------|
| Graph DB | Neo4j 5.x (Community, Docker) |
| Driver | `neo4j` Python driver 5.x |
| Schema spec | PyYAML (YAML artifact → provisioner) |
| Domain models | Pydantic v2 |
| API surface | Plain Python module (`memory_api.py`) — no HTTP in v1 |
| Testing | pytest + pytest-asyncio |
| Runtime | Python 3.11+ |
| Infra | Docker Compose (Neo4j only in v1) |

> **Context graph visualizer**: Use [create-context-graph.dev](https://create-context-graph.dev/)
> to sketch and validate the four-layer schema before committing nodes/edges to `schema.yaml`.
> Paste the exported structure directly into the YAML artifact.

### Four-Layer Node Inventory

```
Requirements Layer (the "why")
  Requirement          id · title · priority · reg_control
  AcceptanceCriterion  id · statement · status
  Actor                id · name · role

Capability Layer (drift-resistant spine)
  Functionality        id · name · description · status
  Component            id · name · status

Implementation Layer (changes frequently)
  File                 id · path · language · module
  Contract             id · name
  Endpoint             id · path · method
  UIElement            id · name · type

Evidence Layer (grows continuously)
  Test                 id · name · type · status
  TestRun              id · outcome · duration · timestamp
  Failure              id · error_signature · label · confidence
  Artifact             id · type · uri · hash
  Commit               id · sha · message · author · timestamp
  Scan                 id · tool · timestamp · commit_sha

Reasoning Memory (cross-cutting, auditable)
  Judgment             id · agent_role · label · confidence · reasoning
  ReasoningTrace       id · agent_role · decision · timestamp
  SecurityFinding      id · severity · status · title
  Report               id · summary · created_at
```

### Cross-Layer Edge Types (all carry `valid_from` / `valid_to`)

```
REALIZED_BY       Requirement      → Functionality
COMPOSED_OF       Functionality    → Component
IMPLEMENTED_BY    Component        → File
VERIFIES          Test             → Functionality
COVERS_CRITERION  Test             → AcceptanceCriterion
AFFECTS           SecurityFinding  → Component
INFORMED_BY       Judgment         → Requirement / AcceptanceCriterion / Context
HAS_STEP          Judgment         → ReasoningTrace
MODIFIES          Commit           → File
INSTANCE_OF       TestRun          → Test
JUDGED            AcceptanceCriterion → Judgment
```

### Component Diagram

```
  schema.yaml
      │
      ▼
  provision_schema.py ──► Neo4j (Docker)
                               │
                    ┌──────────▼──────────┐
                    │     memory_api.py   │
                    │  ┌───────────────┐  │
                    │  │  INGEST()     │  │
                    │  │  RETRIEVE()   │  │
                    │  │  RECONCILE()  │  │
                    │  │  provenance() │  │  ← writes Judgment + ReasoningTrace
                    │  │  audit_trail()│  │  ← reads full Req→Judgment chain
                    │  └───────────────┘  │
                    └─────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Neo4j Graph       │
                    │  [Requirements]     │
                    │  [Capability]       │
                    │  [Implementation]   │
                    │  [Evidence]         │
                    └─────────────────────┘
```

### Data Flow

```
INGEST(node | edge | event)
  → validate via Pydantic model
  → MERGE into Neo4j (idempotent on id)
  → set valid_from = now(), valid_to = null on new edges

RETRIEVE(agent_role, entity_id, depth?)
  → run role-scoped Cypher (role determines which layers are traversed)
  → return typed node + edge list

RECONCILE(entity_id, new_truth)
  → find edges to the entity where valid_to IS NULL
  → if contradicted by new_truth: set valid_to = now()
  → INGEST new edge with valid_from = now()

provenance(judgment_data, trace_steps, informed_by_ids)
  → MERGE Judgment node
  → MERGE ReasoningTrace nodes, link via HAS_STEP
  → link Judgment → context nodes via INFORMED_BY

audit_trail(requirement_id)
  → single Cypher: MATCH path from Requirement down to Judgment
  → return ordered node list
```

## Out of Scope (v2+)

- Any agent logic (Requirements Parser, Test Case Generator, etc.)
- FastAPI / HTTP transport wrapper around the memory API
- LLM integration (Gemini, embeddings)
- Lint operation (B9 — Phase 5)
- CoGMEM-Inspector UI (B10 — Phase 5)
- The synthetic banking application (B11 — Phase 6)
- Security scanning (Bandit, Semgrep — Phase 3)
- Playwright test execution (Phase 3)

## Dependencies

- None — greenfield sprint. Docker must be available to run Neo4j locally.
- Future sprints (v2 onward) depend on this sprint being green.
