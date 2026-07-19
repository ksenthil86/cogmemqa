# Sprint v10 — PRD: Backend Folder Restructure

## Overview

Move all Python API/agent code from the repo root (`src/`, `tests/`, `scripts/`,
`fixtures/`, `pyproject.toml`) into a self-contained `backend/` folder, mirroring
the create-context-graph scaffold layout (`backend/app/*`). The repo becomes a
clean two-service monorepo: `backend/` + `frontend/`, with shared artifacts
(`schema/`, `docker-compose.yml`) at the root. **No behavior changes** — the API
contract, tests, and frontend are untouched except for path/import updates.

## Goals

- `backend/` is self-contained: `backend/app/` (package, renamed from `src`),
  `backend/tests/`, `backend/scripts/`, `backend/fixtures/`, `backend/pyproject.toml`.
- `uvicorn app.api:app` runs from `backend/`; all 447 tests pass from `backend/`.
- Git history preserved (`git mv`, no delete+create).
- A root `Makefile` gives one-command workflows: `make install`, `make dev-backend`,
  `make dev-frontend`, `make seed`, `make test`, `make test-e2e`.
- `schema/cogmem-qa.yaml` + `schema/schema.yaml` stay at the repo root (shared
  source of truth); backend resolves them relative to its own location.

## User Stories

- As a maintainer, I want backend code isolated in one folder, so backend and
  frontend can be developed, containerized, and CI'd independently.
- As a new contributor, I want the repo layout to match the well-known scaffold
  convention, so I know where everything lives immediately.
- As the frontend, I want the API contract unchanged, so nothing breaks.

## Technical Architecture

```
cogmemqa/
├── backend/
│   ├── app/            ← was src/  (package renamed: `from app import …`)
│   │   └── agents/
│   ├── tests/          ← was tests/
│   ├── scripts/        ← was scripts/  (replay_meridian, backfill, provision…)
│   ├── fixtures/       ← was fixtures/
│   └── pyproject.toml  ← was ./pyproject.toml
├── frontend/           (unchanged)
├── schema/             (unchanged — shared: schema.yaml + cogmem-qa.yaml)
├── docker-compose.yml  (unchanged)
├── Makefile            (new)
└── .env / .env.example / .env.test  (root — loaded via explicit paths)
```

Path-sensitive code to update: `memory_api._load_schema()` and
`ontology.load_ontology()` (…/schema relative to the package file gains one
level), `tests/conftest.py` dotenv paths, `scripts/*` `sys.path` inserts.

## Out of Scope (v11+)

- Dockerfile.backend / Dockerfile.frontend + prod compose (scaffold has them)
- Renaming test files or splitting the agent swarm from the API package
- CI pipeline changes, publishing the package
- Any API or frontend behavior change

## Dependencies

- Sprint v9 shipped (447 pytest / 28 Playwright green baseline)
- ~55 Python files import `src.*` — the sweep is mechanical but broad
- DISSERTATION_SUMMARY.md / sprint docs reference `src/…` paths (update only
  README; historical sprint docs stay as-is)
