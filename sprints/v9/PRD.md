# Sprint v9 — PRD: Scaffold-Informed Upgrades (SSE Streaming + Ontology-Driven Config)

## Overview

Adopt the best patterns from the `create-context-graph` scaffold (`~/Desktop/contextqa-scaffold`)
into the existing CoGMEM Inspector, without switching frameworks (we keep FastAPI + Gemini +
Tailwind; the scaffold uses LangGraph + Claude + Chakra — we port behavior, not stacks).
The two headline adoptions are **SSE streaming chat** (live tool timeline instead of a single
JSON response) and **runtime ontology-driven config** from `schema/cogmem-qa.yaml` (colors,
demo scenarios, and system prompt served from the YAML instead of being hardcoded in
three places). Plus targeted graph-UX and robustness upgrades.

## Goals

- Chat streams over SSE: tool calls appear in the timeline the moment they start, text arrives
  incrementally, and the graph panel updates mid-response.
- `schema/cogmem-qa.yaml` becomes the single source of truth at runtime: node colors, node
  sizes, demo scenarios, and the agent system prompt are loaded from it (no more triplicated
  hardcoding in `chat_agent.py`, `GraphCanvas.tsx`, `scenarios.ts`).
- A read-only `POST /api/cypher` endpoint exists (scaffold endpoint shape, **our**
  `assert_read_only` guard — the scaffold's bolt path has no guard).
- Graph canvas gains scaffold UX: selection/expansion styling, tuned NVL options,
  SSR-safe dynamic import, double-click expand.
- One NVL crash can no longer blank the whole app (error boundary per panel).

## User Stories

- As a QA lead, I want to see each tool call the moment the agent starts it, so long
  queries feel alive instead of frozen.
- As a QA lead, I want the graph to light up while the agent is still answering, so I can
  follow its investigation in real time.
- As a maintainer, I want colors/scenarios/prompt defined once in `cogmem-qa.yaml`, so a
  schema change doesn't require touching three code files.
- As a power user, I want to run my own read-only Cypher against the graph from tooling,
  so I can answer questions the predefined tools don't cover.
- As a user, I want a crash in one panel to show an error card, not a white screen.

## Technical Architecture

```
frontend (Next.js + Tailwind)                 backend (FastAPI)
┌────────────────────────────┐                ┌──────────────────────────────┐
│ ChatPanel                  │  POST /api/    │ /api/chat/stream (SSE)       │
│  lib/chatStream.ts ────────┼──chat/stream──▶│  asyncio.Queue ◀─ emit hooks │
│  (fetch+reader, idle reset)│  event stream  │  in chat_agent tool loop     │
│ ContextGraphPanel          │                │ /api/config ◀─ ontology.py   │
│  GraphCanvas (NVL, styled) │◀─/api/config──│  loads schema/cogmem-qa.yaml │
│ DecisionPanel              │                │ /api/cypher (assert_read_only)│
│ ErrorBoundary × 3          │                │ POST /api/chat (kept, compat)│
└────────────────────────────┘                └──────────────────────────────┘
```

SSE events (scaffold-compatible names): `session_id`, `tool_start {name, inputs}`,
`tool_end {name, duration_ms, output_preview, graph_data}`, `text_delta {text}`,
`entities_extracted {count}`, `preferences_detected {count}`, `done`, `error`.
Dual timeout on the stream: 120s idle / 300s overall; `X-Accel-Buffering: no`.

## Out of Scope (v10+)

- Switching agent framework (LangGraph), LLM provider (Claude), or UI kit (Chakra)
- GDS endpoints (Louvain/PageRank) — requires the graph-data-science plugin
- NAMS hosted memory backend, multi-tenant `domain` scoping
- The scaffold's `splitThinkingAndResponse` heuristic (fragile; our tool timeline is better)
- Document browser parity (our Reports tab stays as-is this sprint)
- pydantic-settings migration and bucketed memory-error health payloads

## Dependencies

- Sprint v7 (chat + Cypher tools) and v8 (conversation memory) shipped
- `schema/cogmem-qa.yaml` (conforming domain file, verified against live graph)
- Reference code: `~/Desktop/contextqa-scaffold` — `backend/app/routes.py:251-335`
  (SSE route), `backend/app/context_graph_client.py:26-129` (event collector),
  `frontend/components/ChatInterface.tsx:232-440` (SSE consumption),
  `frontend/components/ContextGraphView.tsx:199-393,680-726` (graph UX)
- Live Neo4j seeded via `scripts/replay_meridian.py`
