# Sprint v6 — PRD: CoGMEM-Inspector (B10 — Audit Visualization Dashboard)

## Sprint Overview

Build the CoGMEM-Inspector: a browser-based audit dashboard that renders the live Neo4j
graph as an interactive visualization using the Neo4j Visualization Library (NVL). An
auditor or dissertation evaluator can see the full 5-layer graph, click any node to expand
its provenance subgraph, and trace any requirement through to its commits, tests, and
health reports — all from a single browser window after running `replay_meridian.py`.

This sprint implements B10 (CoGMEM-Inspector) using NVL instead of the originally planned
Cytoscape.js. B9 (Lint & Memory Maintenance) is deferred. B11 is Sprint v7.

---

## Goals

- A FastAPI backend exposes the existing `memory_api` as HTTP endpoints — no new graph
  logic, just a thin HTTP wrapper.
- A Next.js + NVL frontend renders the live graph with nodes coloured by layer (layer 1
  Requirements = blue, layer 3 Implementation = green, layer 4 Evidence = amber,
  layer 5 Reasoning = purple).
- Clicking any graph node expands its 1-hop neighbourhood in the canvas.
- A health panel shows live B7 metrics: coverage %, open findings by severity, report count.
- An audit trail panel shows the full provenance chain for any selected Requirement node.
- After `python scripts/replay_meridian.py`, opening `http://localhost:3000` shows a fully
  populated, interactive graph with no manual data entry.

---

## User Stories

- As a **dissertation evaluator**, I want to open a browser and see the live CoGMEM-QA
  graph, so I can verify the provenance chain without reading Cypher.
- As a **QA lead**, I want to click a Requirement node and see every Test, Commit, and
  Judgment that traces back to it, so I can audit coverage in one view.
- As a **demo presenter**, I want the dashboard to reflect real graph state after a replay,
  so the demo requires no hardcoded data.

---

## Technical Architecture

### Stack

- **Backend:** FastAPI (Python) — thin HTTP wrapper over `src/memory_api.py`
- **Frontend:** Next.js 14 (App Router) + `@neo4j-nvl/react` + Tailwind CSS + shadcn/ui
- **Graph canvas:** Neo4j Visualization Library (NVL) — purpose-built for Neo4j data
- **Database:** existing Neo4j 5.x instance (bolt://localhost:7687) — no schema changes

### Component Diagram

```
Browser (port 3000)
│
├── NVL Graph Canvas          ← full graph, click to expand node
├── Health Panel              ← coverage %, findings, report count (from /api/health)
└── Audit Trail Panel         ← requirement → provenance chain (from /api/audit/{req_id})
        │
        ▼ HTTP (localhost:8000)
FastAPI Backend (src/api.py)
│
├── GET  /api/graph           ← default graph (all nodes + edges, LIMIT 200)
├── GET  /api/graph/expand    ← 1-hop neighbourhood for a given node elementId
├── GET  /api/health          ← coverage_summary() + security_summary() + report count
├── GET  /api/audit/{req_id}  ← provenance chain via _provenance_chain() query
└── GET  /api/schema          ← node labels + counts (for layer colour mapping)
        │
        ▼ neo4j driver
src/memory_api.py             ← unchanged; all graph logic stays here
        │
        ▼
Neo4j (bolt://localhost:7687)
```

### New Files

```
cogmemqa/
├── src/
│   └── api.py                        ← FastAPI app (new)
└── frontend/
    ├── package.json                  ← Next.js + @neo4j-nvl/react + tailwind
    ├── next.config.mjs
    ├── tailwind.config.ts
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                  ← main dashboard page
    │   └── globals.css
    └── components/
        ├── GraphCanvas.tsx           ← NVL wrapper component
        ├── HealthPanel.tsx           ← coverage + findings cards
        └── AuditPanel.tsx            ← provenance chain for selected requirement
```

### Node Layer → Colour Mapping

| Layer | Labels | Colour |
|-------|--------|--------|
| 1 — Requirements | Requirement, AcceptanceCriterion, Actor | Blue (#3B82F6) |
| 2 — Capability | Functionality | Indigo (#6366F1) |
| 3 — Implementation | Component, File, Commit | Green (#22C55E) |
| 4 — Evidence | Test, TestRun, SecurityFinding, Report | Amber (#F59E0B) |
| 5 — Reasoning | Judgment, ReasoningTrace | Purple (#A855F7) |

### Default Graph Query

```cypher
MATCH (n)-[r]->(m)
WHERE NOT n:ReasoningTrace AND NOT m:ReasoningTrace
RETURN n, r, m LIMIT 200
```

ReasoningTrace nodes are filtered from the default view (too many; visible only on
expand) to keep the canvas readable.

### Node Expansion Query

```cypher
MATCH (n) WHERE elementId(n) = $elementId
MATCH (n)-[r]-(neighbour)
RETURN n, r, neighbour
```

---

## Out of Scope

- B9 Lint & Memory Maintenance — deferred
- Authentication / login for the dashboard
- Real-time graph updates via WebSocket (static snapshot per page load)
- GDS algorithms (Louvain, PageRank) — Bolt-only, adds complexity
- Write operations from the UI (read-only dashboard)
- Mobile layout

---

## Dependencies

| Dependency | Status |
|---|---|
| Sprint v5 complete (298 tests green) | ✅ |
| Neo4j running + seeded via replay_meridian.py | ✅ prerequisite at runtime |
| Node.js 18+ for Next.js frontend | install on dev machine |
| `@neo4j-nvl/react` npm package | installed in Task 5 |

---

## Sprint v6 Definition of Done

- [ ] `src/api.py` FastAPI app runs on port 8000; all 5 endpoints return valid JSON
- [ ] `python -m bandit -r src/ -q` still clean after adding `src/api.py`
- [ ] `cd frontend && npm run build` completes without errors
- [ ] `http://localhost:3000` renders the NVL canvas with nodes after replay
- [ ] Clicking a node in the canvas expands its neighbours
- [ ] Health panel shows live coverage %, finding counts, report count
- [ ] Clicking a Requirement node populates the audit trail panel
- [ ] No existing Python tests broken (`pytest tests/` still 298/298 green)
