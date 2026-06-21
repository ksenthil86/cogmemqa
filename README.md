# CoGMEM-QA

Memory-grounded multi-agent QA swarm for software delivery pipelines.  
All agents share a typed Neo4j knowledge graph as their single source of truth — no direct agent-to-agent calls, every decision recorded as a provenance chain.

Built as part of an M.Tech dissertation (BITS Pilani, AI & ML).

---

## Quick Start

> Full walkthrough in 6 steps. Assumes Docker and Python 3.11+ are installed.

```bash
# 1. Clone
git clone https://github.com/ksenthil86/cogmemqa.git
cd cogmemqa

# 2. Install Python dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env — set GEMINI_API_KEY if you want live LLM calls (optional for demo)

# 4. Start Neo4j
docker compose up -d
# Wait ~15 s, then verify: docker compose ps

# 5. Seed the graph (runs all agents over 5 commits)
python scripts/replay_meridian.py

# 6. Install frontend and start the inspector dashboard
cd frontend && npm install && npm run dev &    # Terminal A — frontend (port 3000)
cd .. && uvicorn src.api:app --port 8000       # Terminal B — backend  (port 8000)
```

Open **http://localhost:3000**

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

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | backend agents + API |
| Node.js | 18+ | frontend (Next.js 15) |
| Docker | any | Neo4j via `docker compose` |
| Gemini API key | — | live LLM calls (optional; demo uses stubs) |

---

## Step-by-Step Setup

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/ksenthil86/cogmemqa.git
cd cogmemqa
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

`.env` defaults (Neo4j password matches `docker-compose.yml`):

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=cogmempassword
GEMINI_API_KEY=your_key_here
```

`GEMINI_API_KEY` is only needed for live LLM calls. The demo (`replay_meridian.py`) uses deterministic stubs and works without it.

### 3. Start Neo4j

```bash
docker compose up -d
```

Neo4j browser: [http://localhost:7474](http://localhost:7474) — login `neo4j` / `cogmempassword`

Wait ~15 seconds, then check it's healthy:

```bash
docker compose ps
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Run the Demo (CLI)

### Seed the graph — replay five commits

```bash
python scripts/replay_meridian.py
```

Provisions the Neo4j schema, seeds the Meridian Banking spec (5 requirements, 10 ACs, 10 tests), then replays 5 commits through the full agent pipeline (B5 → B6 → B7).

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

### Inspect the graph (CLI)

```bash
python scripts/demo_summary.py
```

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

Query a specific requirement:

```bash
python scripts/demo_summary.py --req req-kyc
```

### Dry run (no Neo4j needed)

```bash
python scripts/replay_meridian.py --dry-run
```

---

## Inspector Dashboard (Sprint v6)

After seeding the graph, start the full dashboard:

```bash
# Terminal 1 — API backend (port 8000)
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Next.js frontend (port 3000)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

**What you'll see:**

| Panel | Description |
|---|---|
| Graph canvas (main) | All CoGMEM nodes coloured by layer; click any node to expand neighbours |
| Health panel (sidebar) | Live coverage %, findings by severity, report count, HEALTHY / NEEDS REVIEW; refreshes every 30 s |
| Audit trail (sidebar) | Click a Requirement node → shows full provenance chain: Req → Func → Comp → File ← Commit |

**Node colour key:**

| Colour | Layer | Node types |
|---|---|---|
| Blue | Requirements | Requirement, AcceptanceCriterion, Actor |
| Indigo | Capability | Functionality |
| Green | Implementation | Component, File, Commit |
| Amber | Evidence | Test, TestRun, SecurityFinding, Report |
| Purple | Reasoning | Judgment, ReasoningTrace |

---

## Run the Test Suite

```bash
pytest tests/
```

362 tests run against a real Neo4j instance (no mocks). Each module cleans its own nodes.

Run a specific phase gate:

```bash
pytest tests/test_e2e_phase5.py   # Sprint v5 gate (298 total)
pytest tests/test_e2e_phase4.py   # Sprint v4 gate
pytest tests/test_e2e_phase3.py   # Sprint v3 gate
pytest tests/test_e2e_phase2.py   # Sprint v2 gate
pytest tests/test_e2e.py          # Sprint v1 gate (77 tests)
```

Run the FastAPI endpoint tests (Sprint v6):

```bash
pytest tests/test_api.py tests/test_api_graph.py tests/test_api_expand.py tests/test_api_audit.py
```

Run the frontend E2E tests (Playwright):

```bash
cd frontend && npx playwright test
```

---

## Security Scan

```bash
python -m bandit -r src/ -q
```

Zero findings. `fixtures/meridian_app/` contains intentional Bandit findings used as test targets for B6 and is excluded from the scan.

---

## Project Structure

```
cogmemqa/
├── docker-compose.yml            ← Neo4j 5.x service
├── pyproject.toml                ← Python dependencies + tool config
├── .env.example                  ← copy to .env and fill in keys
├── schema/
│   └── schema.yaml               ← 19 node types, 11 edge types, 5 layers
├── fixtures/
│   ├── meridian_spec.md          ← Meridian Bank PRD (5 reqs, 10 ACs)
│   ├── meridian_parsed.json      ← ground-truth parsed spec
│   ├── meridian_commits.json     ← 5 deterministic commit fixtures
│   └── meridian_app/             ← FastAPI stub (intentional B105 finding)
├── src/
│   ├── api.py                    ← FastAPI inspector API (5 endpoints)
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
├── frontend/                     ← Next.js 15 inspector dashboard
│   ├── app/                      ← App Router pages
│   ├── components/
│   │   ├── GraphCanvas.tsx       ← NVL interactive graph (InteractiveNvlWrapper)
│   │   ├── HealthPanel.tsx       ← live metrics sidebar
│   │   └── AuditPanel.tsx        ← provenance chain sidebar
│   └── package.json
├── scripts/
│   ├── replay_meridian.py        ← demo entry point
│   └── demo_summary.py           ← live graph query
├── sprints/
│   ├── v1/ … v6/                 ← PRD + TASKS per sprint
└── tests/
    ├── conftest.py               ← session-scoped Neo4j driver fixture
    ├── test_e2e.py               ← Phase 1 gate (77 tests)
    ├── test_e2e_phase2.py        ← Phase 2 gate
    ├── test_e2e_phase3.py        ← Phase 3 gate
    ├── test_e2e_phase4.py        ← Phase 4 gate
    ├── test_e2e_phase5.py        ← Phase 5 gate (298 total)
    ├── test_api.py               ← /api/health + /api/schema (Sprint v6)
    ├── test_api_graph.py         ← /api/graph (Sprint v6)
    ├── test_api_expand.py        ← /api/graph/expand (Sprint v6)
    └── test_api_audit.py         ← /api/audit/{req_id} (Sprint v6)
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
