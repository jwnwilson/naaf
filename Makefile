.PHONY: install test coverage lint run db-upgrade db-reset worker dev

# Postgres URL shared by the live dev stack (API, worker, alembic, seed).
# Override, e.g.: make dev NAAF_DB_URL=postgresql+psycopg://user:pass@host:5432/db
NAAF_DB_URL ?= postgresql+psycopg://naaf:naaf@localhost:5432/naaf

install:
	uv sync

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
	@echo "▶ NAAF full stack — API http://localhost:8000 · UI http://localhost:5173 (live). Ctrl-C stops everything."
	docker compose up -d postgres redis
	@echo "⏳ waiting for Postgres…"
	@tries=0; until docker compose exec -T postgres pg_isready -U naaf -d naaf >/dev/null 2>&1; do \
		tries=$$((tries+1)); [ $$tries -ge 30 ] && { echo "Postgres not ready after 30s"; exit 1; }; sleep 1; \
	done
	cd projects/server && naaf_db_url="$(NAAF_DB_URL)" uv run alembic upgrade head
	-naaf_db_url="$(NAAF_DB_URL)" uv run python -m interactors.cli.seed
	@naaf_db_url="$(NAAF_DB_URL)" bash -c 'trap "echo; echo ▲ stopping…; kill 0" EXIT INT TERM; \
		( cd projects/server && uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info ) & \
		( uv run uvicorn interactors.api.app:create_app --factory --reload ) & \
		( cd projects/ui && VITE_LIVE_API=true pnpm dev ) & \
		wait'
