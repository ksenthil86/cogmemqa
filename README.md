# CoGMEM-QA

Memory-grounded multi-agent QA swarm for software delivery pipelines.  
All agents share a typed Neo4j knowledge graph as their single source of truth — no direct agent-to-agent calls, every decision recorded as a provenance chain.

Built as part of an M.Tech dissertation (BITS Pilani, AI & ML).

---

## Architecture

```
Commit Data
    │
    ▼
B8  CommitIngestionAgent   → Commit + File nodes + MODIFIES edges
    │
    ▼
    impact_lookup()        → File → Component → Functionality → Requirement
    │
    ▼
B5  FunctionalTesterAgent  → TestRun nodes (pass/fail per Test)
B6  SecurityTesterAgent    → SecurityFinding nodes (Bandit scan)
    │
    ▼
B7  QASupervisorAgent      → Report node (coverage %, open findings)
    │
    ▼
    Neo4j Graph            ← all agents read/write here
    Judgment + ReasoningTrace ← every decision recorded with provenance
```

**Agents:**

| Block | Agent | Role |
|---|---|---|
| B3 | `RequirementsParserAgent` | Parses spec → seeds Requirement/AC/Component graph |
| B4 | `TestCaseGeneratorAgent` | Proposes test cases per acceptance criterion |
| B5 | `FunctionalTesterAgent` | Runs HTTP tests → TestRun nodes |
| B6 | `SecurityTesterAgent` | Bandit scan → SecurityFinding nodes |
| B7 | `QASupervisorAgent` | Aggregates coverage + findings → Report node |
| B8 | `CommitIngestionAgent` | Ingests commits → triggers build cycle |

---

## Prerequisites

- Python 3.11+
- Docker (for Neo4j)
- A [Google AI Studio](https://aistudio.google.com) API key (Gemini) — only needed for live LLM calls; demo runs with stubs

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/ksenthil86/cogmemqa.git
cd cogmemqa
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your Gemini API key:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=cogmempassword
GEMINI_API_KEY=your_key_here
```

### 3. Start Neo4j

```bash
docker compose up -d
```

Neo4j browser is available at [http://localhost:7474](http://localhost:7474)  
(login: `neo4j` / `cogmempassword`)

Wait ~15 seconds for Neo4j to be ready, then verify:

```bash
docker compose ps
```

---

## Run the Demo

Two commands seed the full Meridian Banking graph, replay five deterministic commits through the agent pipeline, and print a live graph summary.

### Step 1 — Replay five commits

```bash
python scripts/replay_meridian.py
```

This will:
- Provision the Neo4j schema (constraints + indexes)
- Seed the Meridian spec: 5 requirements, 10 acceptance criteria, 10 tests
- Replay 5 commits, running B5 → B6 → B7 after each one
- Print a formatted build-cycle log per commit

Expected output:

```
CoGMEM-QA Build-Cycle Replay — Meridian Banking App
====================================================

► Commit b800001  "Add input validation for account registration fields"
  Changed:  src/account/AccountController.java
  Impact:   comp-account-opening → func-account-opening → req-account-opening
  B5:  10 tests run, 10 pass
  B6:  1 open finding(s) (1 LOW)
  B7:  report-056161e4ee  coverage 100.0%  1 open finding(s)
  ✓  COMMIT_INGESTED  (commit-b800001)

...

5/5 commits ingested. Run scripts/demo_summary.py to inspect graph.
```

### Step 2 — Inspect the graph

```bash
python scripts/demo_summary.py
```

Expected output:

```
CoGMEM-QA — Graph Summary
==========================================
Commits ingested:     5
Coverage:           100.0%  (10/10 ACs)
Open findings:        1      (low: 1, medium: 0, high: 0)
Reports generated:    5
Judgments:         5 COMMIT_INGESTED, 5 HEALTH_REPORT_GENERATED

Provenance chain for req-account-opening (Account Opening):
  req-account-opening → func-account-opening → comp-account-opening
  → src/account/AccountController.java ← Commit b800001
```

To inspect a different requirement:

```bash
python scripts/demo_summary.py --req req-kyc
```

### Dry run (no Neo4j needed)

Validate fixture data without connecting to Neo4j:

```bash
python scripts/replay_meridian.py --dry-run
```

---

## Inspector Dashboard (Sprint v6)

After seeding the graph with `replay_meridian.py`, start the live inspector dashboard:

```bash
# Terminal 1 — backend
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

The dashboard shows:
- **Graph canvas** (main area) — all CoGMEM nodes coloured by layer; click any node to expand its neighbours
- **Health panel** (sidebar) — live coverage %, open findings by severity, report count, HEALTHY / NEEDS REVIEW status; auto-refreshes every 30 s
- **Audit trail** (sidebar) — click a Requirement node in the canvas to see its full provenance chain: Requirement → Functionality → Component → File ← Commit

Frontend dependencies: `cd frontend && npm install`

---

## Run the Test Suite

```bash
pytest tests/
```

All 298 tests run against a real Neo4j instance (no mocks). Each test module
cleans its own nodes at the start.

Run a specific phase gate:

```bash
pytest tests/test_e2e_phase5.py   # Sprint v5 gate
pytest tests/test_e2e_phase4.py   # Sprint v4 gate
pytest tests/test_e2e_phase3.py   # Sprint v3 gate
pytest tests/test_e2e_phase2.py   # Sprint v2 gate
pytest tests/test_e2e.py          # Sprint v1 gate
```

---

## Security Scan

```bash
python -m bandit -r src/ -q
```

Zero findings. The `fixtures/meridian_app/` directory contains intentional
Bandit findings (used as test targets for B6) and is excluded from the scan.

---

## Project Structure

```
cogmemqa/
├── docker-compose.yml            ← Neo4j 5.x service
├── pyproject.toml                ← dependencies + tool config
├── schema/
│   └── schema.yaml               ← 19 node types, 11 edge types, 5 layers
├── fixtures/
│   ├── meridian_spec.md          ← Meridian Bank PRD (5 reqs, 10 ACs)
│   ├── meridian_parsed.json      ← ground-truth parsed spec
│   ├── meridian_commits.json     ← 5 deterministic commit fixtures
│   └── meridian_app/             ← FastAPI stub (intentional B105 finding)
├── src/
│   ├── db.py                     ← Neo4j driver singleton
│   ├── models.py                 ← 19 Pydantic node models + 11 edge models
│   ├── memory_api.py             ← INGEST / RETRIEVE / RECONCILE / provenance
│   ├── provisioner.py            ← schema constraints + indexes (idempotent)
│   ├── retrieval_policies.py     ← per-role graph layer access control
│   ├── agent_base.py             ← BaseAgent(role, driver, llm_fn)
│   ├── orchestrator.py           ← run_build_cycle(driver, b5, b6, b7)
│   ├── llm.py                    ← Gemini client (google-genai)
│   └── agents/
│       ├── requirements_parser.py    ← B3
│       ├── test_case_generator.py    ← B4
│       ├── functional_tester.py      ← B5
│       ├── security_tester.py        ← B6
│       ├── qa_supervisor.py          ← B7
│       └── commit_ingestion.py       ← B8
├── scripts/
│   ├── replay_meridian.py        ← demo entry point
│   └── demo_summary.py           ← live graph query
├── sprints/
│   ├── v1/  v2/  v3/  v4/  v5/  ← PRD + TASKS per sprint
└── tests/
    ├── conftest.py               ← session-scoped Neo4j driver fixture
    ├── test_e2e.py               ← Phase 1 gate (77 tests)
    ├── test_e2e_phase2.py        ← Phase 2 gate
    ├── test_e2e_phase3.py        ← Phase 3 gate
    ├── test_e2e_phase4.py        ← Phase 4 gate
    └── test_e2e_phase5.py        ← Phase 5 gate (298 total)
```

---

## Graph Schema

Five layers, read bottom-up:

```
Layer 5 — Reasoning:      Judgment, ReasoningTrace
Layer 4 — Evidence:       Test, TestRun, SecurityFinding, Report
Layer 3 — Implementation: Component, File, Commit
Layer 2 — Capability:     Functionality
Layer 1 — Requirements:   Requirement, AcceptanceCriterion, Actor
```

All edges carry `valid_from` / `valid_to` timestamps for bi-temporal history.  
Every agent decision writes `Judgment → HAS_STEP → ReasoningTrace` + `INFORMED_BY` edges to evidence nodes.

---

## Sprints

| Sprint | Blocks | Description | Tests |
|---|---|---|---|
| v1 | B1, B2 | Memory backbone — schema, provisioner, memory API | 77 |
| v2 | B3, B4 | Agent bootstrap — requirements parser, test case generator | 162 |
| v3 | B5, B6 | Execution & security — functional tester, Bandit scanner | 266 |
| v4 | B7 | QA supervisor — health aggregation, Report node | 266 |
| v5 | B8 | Build-cycle integration — commit ingestion, impact lookup, replay | 298 |
| v6 | B10 | CoGMEM-Inspector dashboard — FastAPI + Next.js 15 + NVL graph canvas | 362 |

See [DISSERTATION_SUMMARY.md](DISSERTATION_SUMMARY.md) for the full implementation report.
