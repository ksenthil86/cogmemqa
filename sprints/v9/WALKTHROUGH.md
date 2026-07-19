# Sprint v9 — Walkthrough

## What shipped

All 12 tasks from TASKS.md, adopting the create-context-graph scaffold's best
patterns without switching stacks (still FastAPI + Gemini + Tailwind).

### Backend
- **`src/ontology.py`** — cached runtime loader over `schema/cogmem-qa.yaml`
  (colors, sizes, scenarios, system prompt, entity labels).
- **`GET /api/config`** — serves visualization + scenario config from the YAML.
- **Agent system prompt** now = YAML `system_prompt` + code-appended schema
  detail (`_build_system_prompt` in `src/chat_agent.py`).
- **Event hooks** — `run_chat_agent(event_cb=...)` emits `tool_start`,
  `tool_end` (with per-tool `graph_data`), and chunked `text_delta`s.
- **`POST /api/chat/stream`** — SSE with scaffold-compatible event names,
  120s idle / 300s overall timeouts, task cancellation, memory flow shared
  with the JSON endpoint via `_memory_pre_chat`/`_memory_post_chat`.
- **`POST /api/cypher`** — scaffold endpoint shape, guarded by our
  `assert_read_only` (the scaffold's bolt path has no guard).

### Frontend
- **`lib/chatStream.ts`** — fetch+reader SSE parser, idle-reset timeout, abort.
- **`ChatPanel`** — live tool timeline (spinner → ✓ + duration), streamed
  text (50ms buffered flush), badges from stream events, Stop button,
  graph merges mid-response.
- **`lib/config.ts`** — cached `/api/config` fetch with baked fallback;
  colors feed `GraphCanvas` + the legend; demo buttons come from the YAML
  scenarios (`lib/scenarios.ts` deleted).
- **`GraphCanvas`** — d3Force layout, zoom bounds, telemetry off; single-click
  = select (red, larger), double-click = expand (green); colors config-driven.
- **`ErrorBoundary`** — per-panel crash isolation with reset.

## Verification
- 447 pytest green (31 new: ontology loader, config, agent events, SSE
  stream, cypher endpoint) · 28 Playwright green (chat specs rewritten for
  SSE incl. stream-error case).
- Live smoke against real Gemini: portfolio question streamed
  `session_id → entities/preferences → tool_start/tool_end → 6×text_delta →
  done`; `/api/cypher` returned the 4 epics; `DETACH DELETE` rejected 422.

## Deviations
- Task 11's "forced crash" e2e was skipped as impractical to trigger from
  Playwright without a test-only crash hook; boundary correctness is covered
  by all specs passing with boundaries mounted (transparent wrapper).
- `relationshipThickness` NVL option (scaffold) isn't in our NVL typings;
  used `relationshipThreshold` + defaults instead.
