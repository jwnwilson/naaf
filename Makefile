.PHONY: install test coverage lint run db-upgrade db-reset worker dev secret-key e2e-db e2e e2e-real

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

# PG connection parts for direct psql/createdb in CI (no docker compose exec available).
# Default values match the local docker compose service and the CI service container config.
NAAF_E2E_PG_HOST     ?= localhost
NAAF_E2E_PG_PORT     ?= 5432
NAAF_E2E_PG_USER     ?= naaf
NAAF_E2E_PG_PASSWORD ?= naaf

# Agent runtime for `make dev`. Defaults to `claude_code` (real agents; needs a Claude
# subscription or `naaf_anthropic_api_key=sk-...` exported). For a no-LLM, zero-config run
# (CI / no key): make dev NAAF_AGENT_RUNTIME=fake
NAAF_AGENT_RUNTIME ?= claude_code

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
	uv run mypy projects/server/src libs/crud_router/src libs/db/src

# uvicorn --reload watches the process CWD (the repo root) by default, which
# includes the git-ignored .worktrees/ trees and every tests/ dir. A .py change
# anywhere there restarts the API mid-request — fatal to long in-flight agent
# turns: the chat's SSE stream + polling hit a restarting API and freeze. Scope
# the watcher to the backend source only so worktree/test churn can't restart it.
RELOAD_FLAGS = --reload --reload-dir projects/server/src --reload-exclude '*/tests/*'

run:
	uv run uvicorn interactors.api.app:create_app --factory $(RELOAD_FLAGS)

db-upgrade:
	cd projects/server && uv run alembic upgrade head

db-reset:
	docker compose down -v && docker compose up -d postgres
	sleep 3
	cd projects/server && uv run alembic upgrade head
	uv run python -m interactors.cli.seed

# Worker command wrapped in watchmedo so code edits auto-restart it, mirroring
# uvicorn's --reload. Celery has no hot-reload, so without this a long-running
# worker silently runs stale code until manually restarted. --signal SIGTERM
# lets Celery shut down gracefully between reloads.
WORKER_CMD = uv run watchmedo auto-restart --directory=./src --pattern='*.py' --recursive --signal SIGTERM -- celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info

worker:
	cd projects/server && $(WORKER_CMD)

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
		( cd projects/server && $(WORKER_CMD) ) & \
		( uv run uvicorn interactors.api.app:create_app --factory $(RELOAD_FLAGS) ) & \
		( cd projects/ui && VITE_LIVE_API=true pnpm dev ) & \
		wait'

# Provision the e2e database (idempotent — safe to re-run).
#
# LOCAL path (default): starts postgres + redis via docker compose (reuses the naaf
#   project to avoid port conflicts with `make dev`), waits for readiness, creates
#   naaf_e2e if absent, migrates, truncates state from prior runs, seeds.
#
# CI path (CI=true or NAAF_E2E_SKIP_COMPOSE=1): Postgres is a GitHub Actions service
#   container — skips `docker compose up` and `docker compose exec`; waits for readiness
#   and provisions the DB directly via psql/createdb against NAAF_E2E_PG_* vars.
e2e-db:
	@if [ "$(CI)" = "true" ] || [ "$(NAAF_E2E_SKIP_COMPOSE)" = "1" ]; then \
		echo "⏳ CI: waiting for Postgres service…"; \
		tries=0; until pg_isready -h "$(NAAF_E2E_PG_HOST)" -p "$(NAAF_E2E_PG_PORT)" -U "$(NAAF_E2E_PG_USER)" >/dev/null 2>&1; do \
			tries=$$((tries+1)); [ $$tries -ge 30 ] && { echo "Postgres not ready after 30s"; exit 1; }; sleep 1; \
		done; \
		echo "⏳ CI: creating naaf_e2e if missing…"; \
		PGPASSWORD="$(NAAF_E2E_PG_PASSWORD)" psql -h "$(NAAF_E2E_PG_HOST)" -p "$(NAAF_E2E_PG_PORT)" -U "$(NAAF_E2E_PG_USER)" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='naaf_e2e'" | grep -q 1 \
			|| PGPASSWORD="$(NAAF_E2E_PG_PASSWORD)" createdb -h "$(NAAF_E2E_PG_HOST)" -p "$(NAAF_E2E_PG_PORT)" -U "$(NAAF_E2E_PG_USER)" naaf_e2e; \
	else \
		docker compose -p naaf up -d postgres redis; \
		echo "⏳ waiting for Postgres…"; \
		tries=0; until docker compose -p naaf exec -T postgres pg_isready -U naaf -d naaf >/dev/null 2>&1; do \
			tries=$$((tries+1)); [ $$tries -ge 30 ] && { echo "Postgres not ready after 30s"; exit 1; }; sleep 1; \
		done; \
		docker compose -p naaf exec -T postgres psql -U naaf -tc "SELECT 1 FROM pg_database WHERE datname='naaf_e2e'" | grep -q 1 \
			|| docker compose -p naaf exec -T postgres createdb -U naaf naaf_e2e; \
	fi
	cd projects/server && naaf_db_url="$(NAAF_E2E_DB_URL)" uv run alembic upgrade head
	@echo "🧹 wiping e2e DB state from previous runs…"
	@if [ "$(CI)" = "true" ] || [ "$(NAAF_E2E_SKIP_COMPOSE)" = "1" ]; then \
		PGPASSWORD="$(NAAF_E2E_PG_PASSWORD)" psql -h "$(NAAF_E2E_PG_HOST)" -p "$(NAAF_E2E_PG_PORT)" -U "$(NAAF_E2E_PG_USER)" -d naaf_e2e -c \
			"TRUNCATE TABLE agent_definitions, agent_events, attachments, bus_messages, messages, notifications, projects, run_events, runs, secrets, subscriber_cursors, teams, work_items RESTART IDENTITY CASCADE;" \
			>/dev/null; \
	else \
		docker compose -p naaf exec -T postgres psql -U naaf -d naaf_e2e -c \
			"TRUNCATE TABLE agent_definitions, agent_events, attachments, bus_messages, messages, notifications, projects, run_events, runs, secrets, subscriber_cursors, teams, work_items RESTART IDENTITY CASCADE;" \
			>/dev/null; \
	fi
	-naaf_db_url="$(NAAF_E2E_DB_URL)" uv run python -m interactors.cli.seed

# Boot the scripted stack against naaf_e2e, run Playwright, then tear everything down.
# Pass E2E_SPEC=e2e/smoke.spec.ts to target a single spec file.
e2e: e2e-db
	@echo "▶ e2e — scripted stack (API :8000 · UI :5173) then Playwright"
	@if [ "$(CI)" != "true" ]; then \
		echo "🔪 killing any leftover celery/uvicorn/vite from previous runs…"; \
		pkill -f "interactors.worker.celery_app" 2>/dev/null || true; \
		fuser -k 8000/tcp 5173/tcp 2>/dev/null || lsof -ti:8000 -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true; \
		sleep 1; \
	fi
	@naaf_db_url="$(NAAF_E2E_DB_URL)" naaf_llm_provider=scripted naaf_agent_runtime=claude_code bash -c '\
		bg_pids=(); \
		cleanup() { \
			printf "\n▲ stopping…\n"; \
			[ $${#bg_pids[@]} -gt 0 ] && kill "$${bg_pids[@]}" 2>/dev/null; \
			[ "$(CI)" = "true" ] || pkill -f "interactors.worker.celery_app" 2>/dev/null || true; \
			fuser -k 8000/tcp 5173/tcp 2>/dev/null || lsof -ti:8000 -ti:5173 2>/dev/null | xargs kill 2>/dev/null || true; \
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

# Boot the stack with the real Claude CLI adapter and run only @real-tagged tests.
# Requires naaf_anthropic_api_key in .env or the environment (Claude subscription).
# naaf_llm_provider=claude_cli selects the real LLM; NAAF_E2E_REAL=1 enables the tests.
e2e-real: e2e-db
	@echo "▶ e2e-real — real Claude CLI stack (API :8000 · UI :5173) then Playwright @real tests"
	@if [ "$(CI)" != "true" ]; then \
		echo "🔪 killing any leftover celery/uvicorn/vite from previous runs…"; \
		pkill -f "interactors.worker.celery_app" 2>/dev/null || true; \
		fuser -k 8000/tcp 5173/tcp 2>/dev/null || lsof -ti:8000 -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true; \
		sleep 1; \
	fi
	@NAAF_E2E_REAL=1 naaf_db_url="$(NAAF_E2E_DB_URL)" naaf_llm_provider=claude_cli naaf_agent_runtime=claude_code bash -c '\
		bg_pids=(); \
		cleanup() { \
			printf "\n▲ stopping…\n"; \
			[ $${#bg_pids[@]} -gt 0 ] && kill "$${bg_pids[@]}" 2>/dev/null; \
			[ "$(CI)" = "true" ] || pkill -f "interactors.worker.celery_app" 2>/dev/null || true; \
			fuser -k 8000/tcp 5173/tcp 2>/dev/null || lsof -ti:8000 -ti:5173 2>/dev/null | xargs kill 2>/dev/null || true; \
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
		cd projects/ui && pnpm exec playwright test --grep "@real" $${E2E_SPEC:-}; \
	'
