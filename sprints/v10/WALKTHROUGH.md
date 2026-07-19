# Sprint v10 — Walkthrough

## What shipped

The backend moved into a self-contained `backend/` folder (scaffold-style
layout), with zero API/behavior changes:

- `src/` → `backend/app/` (package renamed; all imports `src.*` → `app.*`,
  swept across app + tests + scripts, ~55 files)
- `tests/` → `backend/tests/`, `scripts/` → `backend/scripts/`,
  `fixtures/` → `backend/fixtures/`, `pyproject.toml` → `backend/pyproject.toml`
  (`packages.find include = ["app*"]`)
- All moves via `git mv` — history follows the files
- `schema/` stays at the repo root (shared source of truth); the four
  path resolvers (`memory_api._load_schema`, `ontology.load_ontology`,
  `provisioner._SCHEMA_PATH`, `scripts/validate_schema.py`) gained one `..`
- `tests/conftest.py` loads root `.env`/`.env.test` via `../../`
- New root `Makefile`: `install`, `docker-up/down`, `seed`, `dev-backend`
  (`cd backend && uvicorn app.api:app`), `dev-frontend`, `test`, `test-e2e`
- README: quick-start commands, run instructions, and the project-structure
  tree updated to the new layout

## Verification

- `pip install -e "./backend[dev]"` + `pip check` clean
- 447 pytest green from `backend/` (after `scripts/replay_meridian.py` seed)
- Live smoke on the moved backend: `/api/health` 200, `/api/config` serves
  YAML colors, `/api/cypher` returns the 4 epics, SSE chat streamed
  `session_id → tool_start/tool_end → text_delta → done`
- 28 Playwright green (frontend untouched)

## Deviations

- Pre-existing lint warnings (regex style in provisioner, complexity in
  validate_schema) were left as-is — out of scope for a pure move.
- The v9 feature work was committed separately *before* the move so the
  restructure commit shows clean renames instead of adds/deletes.
