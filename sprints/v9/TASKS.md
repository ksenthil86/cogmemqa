# Sprint v9 — Tasks

## Status: Complete

- [x] Task 1: Backend ontology loader — `src/ontology.py` (P0)
  - Acceptance: `load_ontology()` parses `schema/cogmem-qa.yaml` once (cached) and exposes
    `node_colors`, `node_sizes`, `demo_scenarios`, `system_prompt`; unit test asserts all
    15 labels have colors and 3 scenarios load
  - Files: src/ontology.py, tests/test_ontology_loader.py

- [x] Task 2: `GET /api/config` endpoint (P0)
  - Acceptance: returns `{node_colors, node_sizes, demo_scenarios}` from the loader;
    test asserts shape + Requirement color `#2563EB`
  - Files: src/api.py, tests/test_api_config.py

- [x] Task 3: Wire agent system prompt from ontology (P0)
  - Acceptance: `chat_agent._SYSTEM_PROMPT` base text comes from `load_ontology().system_prompt`
    (graph-schema block + memory-context block still appended in code); existing chat tests green
  - Files: src/chat_agent.py, tests/test_chat_api.py (assert prompt sourced from YAML)

- [x] Task 4: Emit hooks in the tool loop (P0)
  - Acceptance: `run_chat_agent` accepts optional `event_cb`; `_execute_function_calls`
    calls it with `tool_start` before and `tool_end` (incl. `graph_data`) after each tool;
    final text delivered as chunked `text_delta` events; no behavior change when `event_cb=None`
  - Files: src/chat_agent.py, tests/test_chat_agent_events.py

- [x] Task 5: `POST /api/chat/stream` SSE route (P0)
  - Acceptance: streams `session_id → tool_start/tool_end* → text_delta* →
    entities_extracted → preferences_detected → done` with `text/event-stream`,
    `X-Accel-Buffering: no`; 120s idle + 300s overall timeout → `error` then `done`;
    task cancelled in finally; memory flow (record/extract) identical to POST /api/chat;
    stub-driven test parses the event sequence via `client.stream(...)`
  - Files: src/api.py, tests/test_chat_stream.py

- [x] Task 6: `POST /api/cypher` read-only endpoint (P0)
  - Acceptance: executes arbitrary Cypher through `chat_tools.assert_read_only` +
    `extract_graph_from_records`, 100-record cap; `CREATE`/`CALL` rejected with 422 and
    graph unchanged (test); returns `{rows, graph}` in /api/graph node shape
  - Files: src/api.py, tests/test_api_cypher.py

- [x] Task 7: Frontend SSE client — `lib/chatStream.ts` (P0)
  - Acceptance: `streamChat({message, sessionId, onEvent, signal})` does fetch POST +
    `body.getReader()` parse of `event:`/`data:` pairs buffered on newlines; idle timer
    reset on every event (abort after 120s silence); AbortController support
  - Files: frontend/lib/chatStream.ts, frontend/lib/types.ts

- [x] Task 8: ChatPanel live streaming UX (P0)
  - Acceptance: `tool_start` renders a spinner row immediately; `tool_end` flips it to
    ✓ + duration and pushes `graph_data` to the canvas mid-response; `text_delta` appends
    (throttled ~50ms flush); badges from `entities_extracted`/`preferences_detected`
    events; error event → red card; Stop button aborts; e2e chat.spec updated with a
    canned SSE body
  - Files: frontend/components/ChatPanel.tsx, frontend/tests/e2e/chat.spec.ts

- [x] Task 9: Config-driven colors + scenarios (P1)
  - Acceptance: `GraphCanvas.getNodeColor` and the ContextGraphPanel legend read colors
    from `/api/config` (fallback to current constants if fetch fails); demo buttons come
    from `demo_scenarios` prompts; `lib/scenarios.ts` deleted
  - Files: frontend/lib/config.ts (new fetch + cache), frontend/components/GraphCanvas.tsx,
    frontend/components/ContextGraphPanel.tsx, frontend/components/ChatPanel.tsx

- [x] Task 10: Graph canvas UX upgrades (P1)
  - Acceptance: NVL options `{layout:"d3Force", minZoom:0.1, maxZoom:5,
    relationshipThickness:2, disableTelemetry:true}`; selected node styled red + 1.3×,
    expanded nodes green; expand moves to double-click (single-click = select only);
    `@neo4j-nvl/react` imported via `next/dynamic` (SSR-safe); existing graph e2e specs
    updated for double-click
  - Files: frontend/components/GraphCanvas.tsx, frontend/tests/e2e/graphcanvas.spec.ts,
    frontend/tests/e2e/expansion.spec.ts

- [x] Task 11: ErrorBoundary per panel (P1)
  - Acceptance: class-component boundary with "Something went wrong — Reset" card wraps
    each of the three panels in page.tsx; a thrown render error in one panel leaves the
    other two functional (e2e assertion with a forced error)
  - Files: frontend/components/ErrorBoundary.tsx, frontend/app/page.tsx

- [x] Task 12: Deprecate-but-keep JSON chat + docs (P2)
  - Acceptance: `POST /api/chat` remains for compatibility (tests still green) and README
    documents the SSE endpoint, event names, `/api/config`, `/api/cypher`; sprint
    WALKTHROUGH.md written
  - Files: README.md, sprints/v9/WALKTHROUGH.md
