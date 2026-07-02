# Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY projects/server ./projects/server
# naaf-server and naaf-crud-router live in [dependency-groups] dev, so --no-dev
# would omit the application code entirely. Use --frozen without --no-dev.
RUN uv sync --frozen

WORKDIR /app/projects/server
# Celery worker + beat (matches the Makefile `worker` target)
CMD ["uv", "run", "celery", "-A", "interactors.worker.celery_app:celery_app", "worker", "--beat", "--loglevel=info"]
