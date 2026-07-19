# Sprint v10 — Tasks

## Status: Not Started

- [ ] Task 1: Create `backend/` and move the package with history (P0)
  - Acceptance: `git mv src backend/app` (plus `backend/` dir); `git log --follow
    backend/app/api.py` shows pre-move history; nothing else changed yet
  - Files: backend/app/** (moved)

- [ ] Task 2: Import sweep `src.` → `app.` inside the package (P0)
  - Acceptance: no `from src.` / `import src` remains under `backend/app/`;
    `python -c "import app.api"` succeeds from `backend/` (with deps installed)
  - Files: backend/app/*.py, backend/app/agents/*.py (~16 files)

- [ ] Task 3: Move + adapt `pyproject.toml` (P0)
  - Acceptance: `backend/pyproject.toml` with `[tool.setuptools.packages.find]
    include = ["app*"]`, pytest `testpaths = ["tests"]`; `pip install -e
    "backend[dev]"` succeeds; `pip check` clean; root pyproject deleted
  - Files: backend/pyproject.toml

- [ ] Task 4: Move tests + fix conftest/env paths + import sweep (P0)
  - Acceptance: `git mv tests backend/tests`; conftest loads root `.env`/
    `.env.test` via `../../` relative paths; no `src.` imports remain;
    collection succeeds (`pytest --collect-only` from `backend/`)
  - Files: backend/tests/** (~60 files), backend/tests/conftest.py

- [ ] Task 5: Move scripts + fixtures + fix resource paths (P0)
  - Acceptance: `git mv scripts backend/scripts && git mv fixtures backend/fixtures`;
    `sys.path` inserts and fixture paths updated; `memory_api._load_schema()` and
    `ontology.load_ontology()` resolve `../../schema/*.yaml` from `backend/app/`;
    `python backend/scripts/replay_meridian.py --dry-run` passes
  - Files: backend/scripts/*.py, backend/app/memory_api.py, backend/app/ontology.py

- [ ] Task 6: Full backend test suite green from `backend/` (P0)
  - Acceptance: `cd backend && pytest tests/` → 447 passed against live Neo4j
    (seed first via `python scripts/replay_meridian.py`)
  - Files: none (verification gate)

- [ ] Task 7: Root `Makefile` + run-command updates (P1)
  - Acceptance: `make install`, `make dev-backend` (`cd backend && uvicorn
    app.api:app --port 8000`), `make dev-frontend`, `make seed`, `make test`,
    `make test-e2e` all work; README quick-start + run instructions updated to
    the new paths/commands
  - Files: Makefile, README.md

- [ ] Task 8: End-to-end verification (P0)
  - Acceptance: backend via `make dev-backend` + frontend via `make dev-frontend`;
    `/api/health`, `/api/config`, SSE chat smoke, and `POST /api/cypher` all
    respond as before; `npm run test:e2e` → 28 passed (frontend untouched)
  - Files: none (verification gate)

- [ ] Task 9: Sweep stale references + walkthrough (P1)
  - Acceptance: `grep -rn "src\." --include="*.py" backend/` returns nothing;
    README project-structure section reflects the new tree; `.gitignore` entries
    still match (egg-info, __pycache__ under backend/); sprints/v10/WALKTHROUGH.md
    written with any deviations
  - Files: README.md, .gitignore, sprints/v10/WALKTHROUGH.md

- [ ] Task 10: Commit with clean rename detection (P2)
  - Acceptance: single commit where `git show --stat` reports renames
    (`src/api.py → backend/app/api.py`), not adds/deletes; pushed to the
    feature branch
  - Files: git commit
