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
pip install -e "./backend[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env — set GEMINI_API_KEY if you want live LLM calls (optional for demo)

# 4. Start Neo4j
docker compose up -d
# Wait ~15 s, then verify: docker compose ps

# 5. Seed the graph (runs all agents over 5 commits)
cd backend && python scripts/replay_meridian.py

# 6. Install frontend and start the inspector dashboard
cd frontend && npm install && npm run dev &    # Terminal A — frontend (port 3000)
cd backend && uvicorn app.api:app --port 8000       # Terminal B — backend  (port 8000)
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
pip install -e "./backend[dev]"
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
cd backend && python scripts/replay_meridian.py
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
cd backend && python scripts/demo_summary.py
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
cd backend && python scripts/demo_summary.py --req req-kyc
```

### Dry run (no Neo4j needed)

```bash
cd backend && python scripts/replay_meridian.py --dry-run
```

---

## Inspector Dashboard (Sprint v6)

After seeding the graph, start the full dashboard:

```bash
# Terminal 1 — API backend (port 8000)
cd backend && uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Next.js frontend (port 3000)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

**What you'll see (v7 three-panel layout):**

| Panel | Description |
|---|---|
| Chat (left) | Ask questions in natural language; a Gemini agent answers via Cypher tools. Shows the tool-call timeline plus badges for graph labels, extracted entities, and detected preferences |
| Context graph (middle) | NVL canvas coloured by layer; nodes returned by chat tools merge in live; click a node for details / "Ask about this" |
| Decision traces / Documents (right) | Real Judgment → ReasoningTrace chains with agent-role filters; Documents tab lists health Reports |

### Chat API (v9)

The chat panel streams over SSE. Endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/chat/stream` | SSE chat — events: `session_id`, `tool_start`, `tool_end` (with `graph_data`), `text_delta`, `entities_extracted`, `preferences_detected`, `error`, `done`. 120s idle / 300s overall timeout |
| `POST /api/chat` | Non-streaming JSON variant (kept for compatibility) |
| `GET /api/config` | Node colors/sizes + demo scenarios, served from `schema/cogmem-qa.yaml` — the single source of truth also feeding the agent system prompt |
| `POST /api/cypher` | Read-only Cypher (`{query, parameters}`); write clauses and `CALL` are rejected with 422 |

### Conversation memory

The chat is backed by [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory)
(same Neo4j instance, Gemini via LiteLLM — reuses `GEMINI_API_KEY`). Each turn
is stored per session (the browser keeps a `session_id` in sessionStorage);
entities and preferences are extracted from user messages, and relevant
long-term knowledge is injected into the agent prompt. Memory is best-effort:
if it fails to start, chat still works using client-held history.

Notes:

- `MEMORY_ENABLED=false` disables memory (set in `.env.test` so the pytest
  suite makes no Gemini calls).
- Do **not** set `MEMORY_API_KEY` or `NAM_*` env vars — they silently
  reconfigure the library (hosted NAMS backend / settings overrides).
- The embedding model (`gemini-embedding-001`, 3072 dims) is locked into the
  vector indexes on first startup. To change it later, drop the
  `*_embedding_idx` indexes and re-embed.
- Memory nodes (`Message`, `Conversation`, `Entity`, `Preference`) live in the
  same database but are excluded from the graph canvas.
- Messages are scoped per session, but extracted entities/preferences are
  **global** (single-user design, matching the library defaults) — every
  session shares the same long-term knowledge.

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
cd backend && pytest tests/
```

362 tests run against a real Neo4j instance (no mocks). Each module cleans its own nodes.

Run a specific phase gate:

```bash
cd backend && pytest tests/test_e2e_phase5.py   # Sprint v5 gate (298 total)
cd backend && pytest tests/test_e2e_phase4.py   # Sprint v4 gate
cd backend && pytest tests/test_e2e_phase3.py   # Sprint v3 gate
cd backend && pytest tests/test_e2e_phase2.py   # Sprint v2 gate
cd backend && pytest tests/test_e2e.py          # Sprint v1 gate (77 tests)
```

Run the FastAPI endpoint tests (Sprint v6):

```bash
cd backend && pytest tests/test_api.py tests/test_api_graph.py tests/test_api_expand.py tests/test_api_audit.py
```

Run the frontend E2E tests (Playwright):

```bash
cd frontend && npx playwright test
```

---

## Security Scan

```bash
python -m bandit -r backend/app/ -q
```

Zero findings. `fixtures/meridian_app/` contains intentional Bandit findings used as test targets for B6 and is excluded from the scan.

---

## Project Structure

```
cogmemqa/
├── docker-compose.yml            ← Neo4j 5.x service
├── Makefile                      ← install / dev-backend / dev-frontend / seed / test
├── .env.example                  ← copy to .env and fill in keys
├── schema/                       ← shared source of truth (backend + tooling)
│   ├── schema.yaml               ← 21 node types, 13 edge types, 6 layers
│   └── cogmem-qa.yaml            ← create-context-graph domain (drives /api/config + prompt)
├── backend/                      ← self-contained Python service
│   ├── pyproject.toml            ← dependencies + tool config
│   ├── app/
│   │   ├── api.py                ← FastAPI inspector API (chat, SSE, config, cypher…)
│   │   ├── chat_agent.py         ← Gemini function-calling loop
│   │   ├── chat_tools.py         ← predefined Cypher tools + read-only guard
│   │   ├── memory_client.py      ← neo4j-agent-memory conversation memory
│   │   ├── ontology.py           ← runtime loader over schema/cogmem-qa.yaml
│   │   ├── db.py                 ← Neo4j driver singleton
│   │   ├── models.py             ← 21 Pydantic node models + 13 edge models
│   │   ├── memory_api.py         ← INGEST / RETRIEVE / RECONCILE / provenance
│   │   ├── provisioner.py        ← schema constraints + indexes (idempotent)
│   │   ├── retrieval_policies.py ← per-role graph layer access control
│   │   ├── agent_base.py / orchestrator.py / llm.py
│   │   └── agents/               ← B3-B8 QA agent swarm
│   ├── fixtures/                 ← Meridian spec, commits, stub app
│   ├── scripts/
│   │   ├── replay_meridian.py    ← demo entry point
│   │   ├── backfill_portfolio.py ← Project → Epic → Requirement backfill
│   │   └── demo_summary.py       ← live graph query
│   └── tests/                    ← 447 pytest (e2e gates + API + chat + memory)
├── frontend/                     ← Next.js 15 inspector dashboard
│   ├── app/                      ← App Router pages
│   ├── components/               ← ChatPanel, ContextGraphPanel, GraphCanvas…
│   ├── lib/                      ← chatStream (SSE), config, api, types
│   └── package.json
└── sprints/
    └── v1/ … v10/                ← PRD + TASKS per sprint
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
