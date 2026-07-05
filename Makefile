.PHONY: install test coverage lint run db-upgrade db-reset worker dev secret-key e2e-db e2e

# Load .env (if present) and export it so every child process — the worker,
# API, alembic, seed launched by `make dev`/`run`/`worker` — inherits it,
# regardless of the cwd it runs from. Put naaf_secret_key here (see .env.example;
# generate one with `make secret-key`). Agent credentials still go through the
# Settings > Secrets UI, not .env.
-include .env
export

# Postgres URL shared by the live dev stack (API, worker, alembic, seed).
# Override, e.g.: make dev NAAF_DB_URL=postgresql+psycopg://user:pass@host:5432/db
NAAF_DB_URL ?= postgresql+psycopg://naaf:naaf@localhost:5432/naaf

# Dedicated Postgres URL for the e2e stack (isolated from the dev DB).
NAAF_E2E_DB_URL ?= postgresql+psycopg://naaf:naaf@localhost:5432/naaf_e2e

# Agent runtime for `make dev`. Defaults to the no-LLM FakeAgentRuntime so the stack
# runs end-to-end with zero config. For the real LLM runtime:
#   make dev NAAF_AGENT_RUNTIME=claude_code naaf_anthropic_api_key=sk-... (exported)
NAAF_AGENT_RUNTIME ?= fake

install:
	uv sync

# Generate a Fernet key for naaf_secret_key (secrets encryption at rest).
# Set the printed value as naaf_secret_key in the server environment.
secret-key:
	@uv run python -m interactors.cli.gen_secret_key

test:
	uv run pytest

coverage:
	uv run pytest --cov --cov-report=term-missing --cov-fail-under=80

lint:
	uv run ruff check .
	uv run mypy projects/server/src libs/crud_router/src

run:
	uv run uvicorn interactors.api.app:create_app --factory --reload

db-upgrade:
	cd projects/server && uv run alembic upgrade head

db-reset:
	docker compose down -v && docker compose up -d postgres
	sleep 3
	cd projects/server && uv run alembic upgrade head
	uv run python -m interactors.cli.seed

worker:
	cd projects/server && uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info

# One command to run + validate the whole stack:
#   Postgres + Redis (docker) -> migrate + seed -> API (:8000) + worker + UI (:5173, live).
# All processes share Postgres via naaf_db_url. Ctrl-C stops everything.
dev:
	@echo "▶ NAAF full stack — API http://localhost:8000 · UI http://localhost:5173 (live) · runtime=$(NAAF_AGENT_RUNTIME). Ctrl-C stops everything."
	docker compose up -d postgres redis
	@echo "⏳ waiting for Postgres…"
	@tries=0; until docker compose exec -T postgres pg_isready -U naaf -d naaf >/dev/null 2>&1; do \
		tries=$$((tries+1)); [ $$tries -ge 30 ] && { echo "Postgres not ready after 30s"; exit 1; }; sleep 1; \
	done
	cd projects/server && naaf_db_url="$(NAAF_DB_URL)" uv run alembic upgrade head
	-naaf_db_url="$(NAAF_DB_URL)" uv run python -m interactors.cli.seed
	@naaf_db_url="$(NAAF_DB_URL)" naaf_agent_runtime="$(NAAF_AGENT_RUNTIME)" bash -c 'trap "echo; echo ▲ stopping…; kill 0" EXIT INT TERM; \
		( cd projects/server && uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info ) & \
		( uv run uvicorn interactors.api.app:create_app --factory --reload ) & \
		( cd projects/ui && VITE_LIVE_API=true pnpm dev ) & \
		wait'

# Provision the e2e database (idempotent — safe to re-run).
# Starts postgres + redis (reuses the naaf compose project if already running, e.g. from
# make dev in the primary checkout, to avoid port conflicts), creates naaf_e2e if missing,
# runs migrations, seeds.
e2e-db:
	docker compose -p naaf up -d postgres redis
	@echo "⏳ waiting for Postgres…"
	@tries=0; until docker compose -p naaf exec -T postgres pg_isready -U naaf -d naaf >/dev/null 2>&1; do \
		tries=$$((tries+1)); [ $$tries -ge 30 ] && { echo "Postgres not ready after 30s"; exit 1; }; sleep 1; \
	done
	@docker compose -p naaf exec -T postgres psql -U naaf -tc "SELECT 1 FROM pg_database WHERE datname='naaf_e2e'" | grep -q 1 \
		|| docker compose -p naaf exec -T postgres createdb -U naaf naaf_e2e
	cd projects/server && naaf_db_url="$(NAAF_E2E_DB_URL)" uv run alembic upgrade head
	-naaf_db_url="$(NAAF_E2E_DB_URL)" uv run python -m interactors.cli.seed

# Boot the scripted stack against naaf_e2e, run Playwright, then tear everything down.
# Pass E2E_SPEC=e2e/smoke.spec.ts to target a single spec file.
e2e: e2e-db
	@echo "▶ e2e — scripted stack (API :8000 · UI :5173) then Playwright"
	@naaf_db_url="$(NAAF_E2E_DB_URL)" naaf_llm_provider=scripted naaf_agent_runtime=claude_code bash -c '\
		bg_pids=(); \
		cleanup() { \
			printf "\n▲ stopping…\n"; \
			[ $${#bg_pids[@]} -gt 0 ] && kill "$${bg_pids[@]}" 2>/dev/null; \
			lsof -ti:8000 -ti:5173 2>/dev/null | xargs kill 2>/dev/null; \
			wait; \
		}; \
		trap "cleanup" EXIT; \
		trap "cleanup; exit 130" INT; \
		trap "cleanup; exit 143" TERM; \
		( cd projects/server && uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info ) & bg_pids+=( $$! ); \
		( uv run uvicorn interactors.api.app:create_app --factory --port 8000 ) & bg_pids+=( $$! ); \
		( cd projects/ui && VITE_LIVE_API=true pnpm dev --port 5173 --strictPort ) & bg_pids+=( $$! ); \
		echo "⏳ waiting for API (http://localhost:8000/health)…"; \
		tries=0; until curl -sf http://localhost:8000/health >/dev/null 2>&1; do \
			tries=$$((tries+1)); [ $$tries -ge 60 ] && { echo "API not ready after 60s"; exit 1; }; sleep 1; \
		done; \
		echo "✓ API ready"; \
		echo "⏳ waiting for UI (http://localhost:5173)…"; \
		tries=0; until curl -sf http://localhost:5173 >/dev/null 2>&1; do \
			tries=$$((tries+1)); [ $$tries -ge 60 ] && { echo "UI not ready after 60s"; exit 1; }; sleep 1; \
		done; \
		echo "✓ UI ready"; \
		cd projects/ui && pnpm exec playwright test $${E2E_SPEC:-}; \
	'
