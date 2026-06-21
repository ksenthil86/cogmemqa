# Sprint v6 — Tasks: CoGMEM-Inspector (B10)

## Status: Not Started (0/10)

---

- [ ] Task 1: FastAPI backend scaffold + health + schema endpoints (P0)
  - Acceptance:
    - `src/api.py` defines a FastAPI `app`.
    - `GET /api/health` returns JSON with keys `coverage_pct`, `covered_ac`,
      `total_ac`, `open_findings_count`, `by_severity`, `report_count`.
      - `coverage_pct` and `covered_ac` come from `memory_api.coverage_summary()`.
      - `open_findings_count` / `by_severity` from `memory_api.security_summary()`.
      - `report_count` from `MATCH (r:Report) RETURN count(r)`.
    - `GET /api/schema` returns JSON list of `{label: str, count: int}` for all
      node labels present in the graph.
    - Both endpoints work with a real Neo4j connection (reads `.env`).
    - `python -m bandit -r src/ -q` clean after adding `src/api.py`.
    - `uvicorn src.api:app --port 8000` starts without import errors.
  - Files:
    - `src/api.py`
    - `pyproject.toml` — add `fastapi[standard]>=0.110`, `uvicorn>=0.29` to
      runtime deps (fastapi already present; add uvicorn)

---

- [ ] Task 2: Graph data endpoint `GET /api/graph` (P0)
  - Acceptance:
    - `GET /api/graph` executes:
      ```cypher
      MATCH (n)-[r]->(m)
      WHERE NOT n:ReasoningTrace AND NOT m:ReasoningTrace
      RETURN n, r, m LIMIT 200
      ```
    - Returns JSON: `{"nodes": [...], "relationships": [...]}`.
    - Each node object: `{id: str, labels: [str], properties: {}}`.
    - Each relationship object: `{id: str, type: str, startNodeId: str,
      endNodeId: str, properties: {}}`.
    - Returns `{"nodes": [], "relationships": []}` when graph is empty (no crash).
    - Endpoint tested manually: `curl http://localhost:8000/api/graph` returns
      valid JSON after `replay_meridian.py` has been run.
  - Files:
    - `src/api.py`

---

- [ ] Task 3: Node expansion endpoint `GET /api/graph/expand` (P0)
  - Acceptance:
    - `GET /api/graph/expand?element_id=<neo4j_element_id>` executes:
      ```cypher
      MATCH (n) WHERE elementId(n) = $element_id
      MATCH (n)-[r]-(neighbour)
      RETURN n, r, neighbour
      ```
    - Returns same `{"nodes": [...], "relationships": [...]}` shape as Task 2.
    - Returns `{"nodes": [], "relationships": []}` for unknown element_id (no crash).
    - `element_id` is passed as a query parameter (string).
  - Files:
    - `src/api.py`

---

- [ ] Task 4: Audit trail endpoint `GET /api/audit/{req_id}` (P0)
  - Acceptance:
    - `GET /api/audit/req-account-opening` returns the provenance chain from
      `demo_summary.py`'s `_provenance_chain()` query:
      ```cypher
      MATCH (r:Requirement {id: $req_id})
        -[:REALIZED_BY]->(func:Functionality)
        -[:COMPOSED_OF]->(comp:Component)
        -[:IMPLEMENTED_BY]->(f:File)
      OPTIONAL MATCH (c:Commit)-[:MODIFIES]->(f)
      RETURN r.id, r.title, func.id, comp.id, f.path, c.sha LIMIT 3
      ```
    - Returns JSON: `{"req_id": str, "chain": [{req, req_title, func,
      comp, file, commit_sha}, ...]}`.
    - Returns `{"req_id": str, "chain": []}` when requirement has no chain.
  - Files:
    - `src/api.py`

---

- [ ] Task 5: Next.js frontend scaffold with NVL dependency (P0)
  - Acceptance:
    - `frontend/` directory created at project root.
    - `frontend/package.json` has dependencies:
      - `next >= 14`, `react >= 18`, `react-dom >= 18`
      - `@neo4j-nvl/react` (latest)
      - `tailwindcss >= 3`, `@tailwindcss/forms`
      - `@radix-ui/react-card`, `lucide-react`
    - `frontend/next.config.mjs` sets `NEXT_PUBLIC_API_URL` default to
      `http://localhost:8000`.
    - `cd frontend && npm install` completes without error.
    - `cd frontend && npm run build` produces a build (even with placeholder page).
    - `frontend/app/layout.tsx` wraps children in Tailwind base styles.
    - `frontend/app/page.tsx` renders a placeholder `<h1>CoGMEM Inspector</h1>`.
  - Files:
    - `frontend/package.json`
    - `frontend/next.config.mjs`
    - `frontend/tailwind.config.ts`
    - `frontend/app/layout.tsx`
    - `frontend/app/page.tsx`
    - `frontend/app/globals.css`

---

- [ ] Task 6: `GraphCanvas` NVL component (P0)
  - Acceptance:
    - `frontend/components/GraphCanvas.tsx` renders an NVL `InteractiveNvlWrapper`
      (or `NvlWrapper`) fed with nodes and relationships fetched from
      `GET /api/graph`.
    - Node colour is determined by the first label:
      - `Requirement | AcceptanceCriterion | Actor` → `#3B82F6` (blue)
      - `Functionality` → `#6366F1` (indigo)
      - `Component | File | Commit` → `#22C55E` (green)
      - `Test | TestRun | SecurityFinding | Report` → `#F59E0B` (amber)
      - `Judgment | ReasoningTrace` → `#A855F7` (purple)
      - anything else → `#6B7280` (gray)
    - Node caption shows `node.properties.id` if present, else the first label.
    - Component calls a `onNodeClick(nodeId: string)` prop when a node is clicked.
    - Fetches graph data on mount via `useEffect`; shows a loading state while fetching.
    - Canvas fills its container (height: 100%, width: 100%).
  - Files:
    - `frontend/components/GraphCanvas.tsx`

---

- [ ] Task 7: Node expansion wired to `GraphCanvas` (P0)
  - Acceptance:
    - Clicking a node in `GraphCanvas` calls `GET /api/graph/expand?element_id=<id>`.
    - The returned nodes and relationships are merged into the existing canvas state
      (no duplicate nodes — merge by `id`).
    - Newly added nodes appear in the canvas without a full page reload.
    - The clicked node is visually highlighted (border or size change) after click.
    - `onNodeClick` is passed down from `page.tsx` to `GraphCanvas`.
  - Files:
    - `frontend/components/GraphCanvas.tsx`
    - `frontend/app/page.tsx`

---

- [ ] Task 8: `HealthPanel` component (P0)
  - Acceptance:
    - `frontend/components/HealthPanel.tsx` fetches `GET /api/health` on mount.
    - Renders four metric cards:
      - **Coverage** — `{covered_ac}/{total_ac} ACs ({coverage_pct}%)`
      - **Open Findings** — total count + `low / medium / high` breakdown
      - **Reports Generated** — report_count
      - **Status** — "HEALTHY" if `coverage_pct >= 100 && open_findings_count == 0`,
        else "NEEDS REVIEW"
    - Shows a skeleton/loading state while fetching.
    - Updates every 30 seconds via `setInterval` (live refresh).
  - Files:
    - `frontend/components/HealthPanel.tsx`

---

- [ ] Task 9: `AuditPanel` component + page layout (P1)
  - Acceptance:
    - `frontend/components/AuditPanel.tsx` accepts `reqId: string | null` prop.
    - When `reqId` is non-null, fetches `GET /api/audit/{reqId}` and renders
      the chain as a vertical step list:
      ```
      req-account-opening (Account Opening)
        → func-account-opening
        → comp-account-opening
        → src/account/AccountController.java
        ← Commit b800001
      ```
    - Shows "(no chain found)" when chain is empty.
    - Shows "(select a Requirement node)" when `reqId` is null.
    - `frontend/app/page.tsx` wires everything together:
      - Left sidebar (280 px): `HealthPanel` stacked above `AuditPanel`
      - Main area: `GraphCanvas` fills remaining width and full height
      - When a node with label `Requirement` is clicked, sets `selectedReqId`
        state → passed to `AuditPanel` as `reqId`
  - Files:
    - `frontend/components/AuditPanel.tsx`
    - `frontend/app/page.tsx`

---

- [ ] Task 10: Integration smoke + README update (P1)
  - Acceptance:
    - `cd frontend && npm run build` exits 0.
    - `python -m bandit -r src/ -q` still produces no output.
    - `pytest tests/` still returns 298 passed, 0 failed.
    - `README.md` updated with a new **"Inspector Dashboard"** section:
      ```markdown
      ## Inspector Dashboard (Sprint v6)

      After seeding the graph with `replay_meridian.py`, start the dashboard:

      # Terminal 1 — backend
      uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

      # Terminal 2 — frontend
      cd frontend && npm run dev

      Open http://localhost:3000
      ```
    - `sprints/v6/TASKS.md` all 10 tasks marked complete.
  - Files:
    - `README.md`
    - `sprints/v6/TASKS.md`

---

## Task Order & Dependencies

```
Task 1  (FastAPI scaffold + health + schema endpoints)
  └── Task 2  (GET /api/graph)
        └── Task 3  (GET /api/graph/expand)
              └── Task 4  (GET /api/audit/{req_id})
                    └── Task 5  (Next.js scaffold + NVL install)
                          └── Task 6  (GraphCanvas component)
                                └── Task 7  (node expansion wired)
                                      └── Task 8  (HealthPanel)
                                            └── Task 9  (AuditPanel + page layout)
                                                  └── Task 10 (smoke test + README)
```

## Sprint v6 Definition of Done

- [ ] `uvicorn src.api:app --port 8000` starts; all 5 API endpoints return valid JSON
- [ ] `cd frontend && npm run build` exits 0
- [ ] `http://localhost:3000` renders NVL graph canvas with coloured nodes
- [ ] Clicking a node expands its neighbours in the canvas
- [ ] Health panel shows live coverage %, findings, report count
- [ ] Clicking a Requirement node populates audit trail panel
- [ ] `pytest tests/` → 298/298 green (no regressions)
- [ ] `python -m bandit -r src/ -q` → clean
