# CoGMEM-QA — one-command workflows (backend/ + frontend/ monorepo)

.PHONY: install dev-backend dev-frontend seed test test-e2e docker-up docker-down

install:            ## Install backend (editable + dev) and frontend deps
	pip install -e "./backend[dev]"
	cd frontend && npm install

docker-up:          ## Start Neo4j
	docker compose up -d

docker-down:        ## Stop Neo4j
	docker compose down

seed:               ## Seed the Meridian graph (schema + replay + portfolio)
	cd backend && python scripts/replay_meridian.py

dev-backend:        ## Run the FastAPI backend on :8000
	cd backend && uvicorn app.api:app --reload --port 8000

dev-frontend:       ## Run the Next.js frontend on :3000
	cd frontend && npm run dev

test:               ## Backend test suite (needs Neo4j up + seeded)
	cd backend && python -m pytest tests/

test-e2e:           ## Frontend Playwright suite
	cd frontend && npm run test:e2e
