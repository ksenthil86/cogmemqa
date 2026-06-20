# Sprint v4 — PRD: QA Supervisor (B7)

## Overview

Build the **QA Supervisor Agent** (B7), which aggregates live evidence already in the graph from Phases 1–3 and produces a `Report` node capturing two health signals chosen for dissertation evaluation: **test-execution coverage %** (how many AcceptanceCriteria are backed by a passing TestRun) and **open security findings** (count + severity breakdown). The agent writes full provenance — a `Judgment(label="HEALTH_REPORT_GENERATED")` and `ReasoningTrace` — so auditors can trace any health verdict back to the TestRun and SecurityFinding nodes that drove it.

---

## Goals

- Two new memory-API query functions added to `src/memory_api.py`:
  `coverage_summary(driver)` and `security_summary(driver)`, each unit-tested
  against seeded data.
- `Report` model extended (still backward-compatible) with `coverage_pct: float`,
  `open_findings_count: int`, and `severity_breakdown: str` (JSON blob).
- `QASupervisorAgent` (B7) at `src/agents/qa_supervisor.py` reads the graph,
  calls both query functions, ingests a `Report` node, and writes a provenance
  `Judgment` — all without a live LLM (metrics are deterministic Cypher).
- All new behaviour unit-tested against a real Neo4j instance (same pattern as
  previous sprints — no mocks).
- A Phase 4 e2e gate test (`test_e2e_phase4.py`) seeds the full Meridian dataset
  (B3 → B4 → B5 stub → B6 stub), calls `b7.run(driver)`, and asserts the Report
  + Judgment exist with plausible metric values.

---

## User Stories

- As a **QA Supervisor agent**, I want to read TestRun and SecurityFinding nodes
  from the shared graph and produce a Report node — so any agent or auditor can
  query current project health without scraping raw evidence themselves.
- As an **auditor**, I want the Report's Judgment to be INFORMED_BY the concrete
  TestRun and SecurityFinding nodes that drove it — so I can drill down from a
  health summary to the underlying test evidence in one graph traversal.
- As a **dissertation evaluator**, I want the coverage_pct and
  open_findings_count fields to be deterministically computable from the graph
  state — so I can reproduce the reported numbers from the raw nodes at any point
  in time.

---

## Technical Architecture

### Stack additions (Sprint v4)

No new runtime dependencies. Pure Cypher aggregate queries over the existing
Neo4j graph already populated by Sprints v1–v3.

| Layer | Component |
|-------|-----------|
| Memory API | `coverage_summary()` + `security_summary()` in `src/memory_api.py` |
| Data model | `Report` extended (backward-compatible field additions) |
| Agent | `src/agents/qa_supervisor.py` — `QASupervisorAgent(B7)` |
| Tests | `tests/test_qa_supervisor.py` + `tests/test_e2e_phase4.py` |

### Report Model (extended)

The existing `Report(BaseNode)` already has `summary: str` and `created_at`.
Sprint v4 adds three new optional fields (all have defaults so existing nodes
remain valid):

```python
class Report(BaseNode):
    summary:              str
    created_at:           datetime
    coverage_pct:         float = 0.0
    open_findings_count:  int   = 0
    severity_breakdown:   str   = "{}"   # JSON: {"low": N, "medium": M, "high": H}
```

### New Memory-API Query Functions

**`coverage_summary(driver) -> dict`**

```
Cypher:
  MATCH (ac:AcceptanceCriterion)
  OPTIONAL MATCH (tr:TestRun {outcome:"pass"})-[:INSTANCE_OF]->(t:Test)
                 -[:COVERS_CRITERION]->(ac)
  RETURN
    count(DISTINCT ac)             AS total_ac,
    count(DISTINCT CASE WHEN tr IS NOT NULL THEN ac END) AS covered_ac

Returns: {"total_ac": N, "covered_ac": M, "coverage_pct": (M/N*100) or 0.0}
```

**`security_summary(driver) -> dict`**

```
Cypher:
  MATCH (sf:SecurityFinding {status: "open"})
  RETURN sf.severity AS sev, count(sf) AS cnt

Returns: {"total_open": N, "by_severity": {"low": L, "medium": M, "high": H}}
```

### Component Diagram

```
  ┌─────────────────────────────────────────────────────────┐
  │  Neo4j Context Graph                                    │
  │  [TestRun / SecurityFinding nodes from Sprints v1–v3]  │
  └─────────────┬────────────────┬────────────────┬─────────┘
                │                │                │
        coverage_summary()  security_summary()   ...
                │                │
      ┌─────────▼────────────────▼───────────┐
      │       QASupervisorAgent  B7          │
      │   compute_health()  ← merges both   │
      │   generate_report() ← ingests node  │
      │   run()             ← orchestrates  │
      └─────────────────┬────────────────────┘
                        │  ingest_node / write_provenance
                        ▼
  ┌──────────────────────────────────────────────────────────┐
  │  Report node (coverage_pct, open_findings_count, ...)   │
  │  Judgment(label="HEALTH_REPORT_GENERATED")              │
  │    └─[INFORMED_BY]→ TestRun nodes (passed)             │
  │    └─[INFORMED_BY]→ SecurityFinding nodes (open)        │
  └──────────────────────────────────────────────────────────┘
```

### Data Flow

```
b7.run(driver):
  metrics = compute_health(driver)
    coverage = coverage_summary(driver)    # Cypher aggregate
    security = security_summary(driver)    # Cypher aggregate

  report_id = generate_report(driver, metrics)
    ingest_node(Report(
      id=f"report-{timestamp_hash}",
      summary=f"Coverage {pct:.1f}% · {open_N} open findings",
      coverage_pct=pct,
      open_findings_count=open_N,
      severity_breakdown=json.dumps(by_severity),
      created_at=now,
    ))
    informed_by = [all passing TestRun ids] + [all open SecurityFinding ids]
    write_provenance(
      Judgment(label="HEALTH_REPORT_GENERATED"),
      [ReasoningTrace(decision=summary_text)],
      informed_by,
    )
  return report_id
```

---

## Out of Scope (v5+)

- Regression detection (TestRun outcome history comparison) — not needed for
  the dissertation evaluation signals selected for this sprint.
- Unimplemented-requirements health signal — deferred; depends on File/Commit
  coverage which B8 will provide.
- B8 — Coding Agent & Build-Cycle Integration — deferred to Sprint v5.
- CoGMEM-Inspector dashboard (B10) — deferred to Sprint v5/v6.
- Evaluation harness (B11) — Phase 6.

---

## Dependencies

- **Sprint v3 complete** — `TestRun`, `Failure`, and `SecurityFinding` nodes
  must exist in the schema and be seedable via the Phase 3 stubs; B5 and B6
  agent code must be importable.
- **`Report` in schema.yaml** — already defined (Sprint v1 schema); no new
  YAML changes required.
- **No new pyproject.toml deps** — all queries use existing `neo4j` driver;
  `json` stdlib for severity_breakdown serialisation.

---

## Sprint v4 Definition of Done

- [ ] `coverage_summary(driver)` and `security_summary(driver)` unit-tested and
      green against real Neo4j (seeded test data, no mocks)
- [ ] `Report` model extended with `coverage_pct`, `open_findings_count`,
      `severity_breakdown` (backward-compatible defaults)
- [ ] `QASupervisorAgent.run(driver)` returns a `report_id` and writes a
      `Report` node + `Judgment(label="HEALTH_REPORT_GENERATED")` to the graph
- [ ] `tests/test_qa_supervisor.py` green (unit + integration)
- [ ] `tests/test_e2e_phase4.py::test_health_report_e2e` green end-to-end
- [ ] `pytest tests/` all green with no regressions
- [ ] Bandit scan on `src/` clean
