.PHONY: install test coverage lint run db-upgrade db-reset

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
