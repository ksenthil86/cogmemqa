# Sprint v5 — PRD: Build-Cycle Integration (B8)

## Sprint Overview

Implement the build-cycle loop so that when code changes, the shared Neo4j graph
reflects the commit, traces the change upward to its parent Requirements, and
re-runs the B5→B6→B7 pipeline automatically. A deterministic Meridian replay
script drives five pre-crafted commits so the loop can be demonstrated and
audited without any real Git dependency.

---

## Goals

- `CommitIngestionAgent` ingests `Commit` + `File` nodes and `MODIFIES` edges
  and writes a `COMMIT_INGESTED` Judgment to the graph after each commit.
- `impact_lookup(driver, file_paths)` traverses the graph upward
  (`File ← IMPLEMENTED_BY ← Component ← COMPOSED_OF ← Functionality ← REALIZED_BY ← Requirement`)
  and returns the affected Components and Requirements for any set of changed files.
- `run_build_cycle(driver, b5, b6, b7)` orchestrates B5 → B6 → B7 in sequence
  and returns the new health `report_id`.
- `fixtures/meridian_commits.json` defines five deterministic commits covering
  all five Meridian components; each commit touches one file.
- `scripts/replay_meridian.py` is a self-contained demo entry point: seeds the
  Meridian graph, replays all five commits, and prints a formatted per-commit
  block showing changed files, impact chain, and health metrics.
- `scripts/demo_summary.py` queries the graph after a replay and prints the final
  state: commit count, coverage %, open findings, report count, and the full
  audit trail for a chosen Requirement.
- Phase 5 gate test: replay three commits; assert three `Commit` nodes, three
  `COMMIT_INGESTED` Judgments, and three distinct `Report` nodes exist.

---

## User Stories

- As a **QA lead**, I want every merged commit to automatically update the shared
  graph and re-run the health check, so I always have an up-to-date audit trail
  without manual intervention.
- As a **dissertation evaluator**, I want to run a single script that replays a
  deterministic commit history and produces a traceable build log in Neo4j, so I
  can inspect the system's provenance chain end-to-end.

---

## Technical Architecture

### New files

```
cogmemqa/
├── fixtures/
│   └── meridian_commits.json          ← 5 deterministic commits (Task 1)
├── scripts/
│   └── replay_meridian.py             ← End-to-end replay driver (Task 5)
├── src/
│   ├── agents/
│   │   └── commit_ingestion.py        ← CommitIngestionAgent (Task 2)
│   └── orchestrator.py                ← run_build_cycle() function (Task 4)
└── tests/
    ├── test_commit_ingestion.py        ← Unit tests (Task 2)
    ├── test_impact_lookup.py           ← Unit tests (Task 3)
    ├── test_orchestrator.py            ← Unit tests (Task 4)
    └── test_e2e_phase5.py             ← Gate test (Task 6)
```

### Component flow per commit

```
 fixtures/meridian_commits.json
         │
         ▼
 CommitIngestionAgent.ingest_commit(driver, commit_data)
   ├── MERGE Commit node  (sha, message, author, timestamp)
   ├── MERGE File nodes   (one per files[*].path)
   ├── MERGE Commit -[MODIFIES]-> File edges
   └── write_provenance → Judgment(COMMIT_INGESTED) + ReasoningTrace
         │
         ▼
 impact_lookup(driver, file_paths)
   └── Cypher: File ← IMPLEMENTED_BY ← Component ← COMPOSED_OF ← Functionality
                   ← REALIZED_BY ← Requirement
   returns [{file_path, component_id, functionality_id, requirement_id}]
         │
         ▼
 run_build_cycle(driver, b5, b6, b7)
   ├── b5.run(driver)           ← FunctionalTesterAgent (re-runs all tests)
   ├── b6.run(driver, "src")    ← SecurityTesterAgent  (re-scans)
   └── b7.run(driver)           ← QASupervisorAgent    (new Report snapshot)
         │
         ▼
    report_id   (written to Neo4j; one distinct Report per commit)
```

### Commit fixture schema

```json
[
  {
    "sha": "b800001",
    "message": "Add input validation for account opening",
    "author": "dev@meridian.io",
    "timestamp": "2026-01-15T09:00:00Z",
    "files": [
      {"path": "src/account/AccountController.java", "change_type": "modified"}
    ]
  },
  ...
]
```

### CommitIngestionAgent

```python
class CommitIngestionAgent(BaseAgent):
    role = "commit_ingestion"

    def ingest_commit(self, driver: Driver, commit_data: dict) -> str:
        # 1. MERGE Commit node
        # 2. MERGE File nodes + MODIFIES edges
        # 3. write_provenance(Judgment(COMMIT_INGESTED), [ReasoningTrace], [commit_id])
        return commit_id

    def run(self, driver: Driver, commit_data: dict) -> str:
        return self.ingest_commit(driver, commit_data)
```

### impact_lookup (memory_api addition)

```python
def impact_lookup(driver: Driver, file_paths: list[str]) -> list[dict]:
    """
    Return [{file_path, component_id, functionality_id, requirement_id}]
    for each file_path that has an upstream Component-Functionality-Requirement chain.
    Returns [] for files with no IMPLEMENTED_BY edge.
    """
```

### run_build_cycle (src/orchestrator.py)

```python
def run_build_cycle(driver, b5, b6, b7, scan_path: str = "src") -> str:
    b5.run(driver)
    b6.run(driver, scan_path)
    return b7.run(driver)
```

---

## Out of Scope

- Real Git integration (webhooks, `git log` parsing, git triggers) — replay script only
- Component-scoped agent triggering (B5/B6 run globally per cycle, not filtered per component)
- B9 lint / memory-maintenance agent
- B10 CoGMEM-Inspector dashboard
- B11 evaluation harness — deferred; mid-dissertation review stops at Sprint v5

---

## Dependencies

| Dependency | Status |
|---|---|
| B3 RequirementsParserAgent | ✅ Sprint v2 complete |
| B4 TestCaseGeneratorAgent | ✅ Sprint v2 complete |
| B5 FunctionalTesterAgent | ✅ Sprint v3 complete |
| B6 SecurityTesterAgent | ✅ Sprint v3 complete |
| B7 QASupervisorAgent | ✅ Sprint v4 complete |
| Neo4j + Meridian fixture | ✅ Seeded by phase 4 e2e helpers |

---

## Sprint v5 Definition of Done

- [ ] `CommitIngestionAgent.ingest_commit()` unit-tested green
- [ ] `impact_lookup()` unit-tested green (finds chain, returns [] for unknown files)
- [ ] `run_build_cycle()` unit-tested green
- [ ] `scripts/replay_meridian.py` runs without error (stub agents, no live LLM)
- [ ] `tests/test_e2e_phase5.py::test_build_cycle_replay_e2e` green
- [ ] `pytest tests/` all green, no regressions
- [ ] `python -m bandit -r src/ -q` clean
