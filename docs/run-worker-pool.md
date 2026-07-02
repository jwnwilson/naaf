# Run-Book: Worker Pool

## Starting the worker

```bash
# 1. Bring up infrastructure
docker compose up -d postgres redis

# 2. Apply migrations (from projects/server)
cd projects/server && make db-upgrade && cd -

# 3. Build and start the default worker (all roles)
docker compose up --build worker
```

The `worker` service image is built from the repo root `Dockerfile`. On first run Docker
builds the image; subsequent `up --build` calls only rebuild if sources changed.

---

## Scaling by role (DISJOINT invariant)

Each Celery worker subscribes to queues for every role listed in `naaf_worker_roles`.
Because the worker processes one message per recipient at a time (sequential per-agent
queue), **two workers sharing a role will both dequeue from the same role queue, creating
double-processing for any agent assigned that role.**

**Rule: every role must be served by exactly one worker at a time.**

### Correct — disjoint role sets

```bash
# Worker A: planning roles
docker compose run -d --rm \
  -e naaf_worker_roles=lead,architect \
  worker

# Worker B: delivery roles
docker compose run -d --rm \
  -e naaf_worker_roles=backend,frontend,qa,devops \
  worker
```

Each role appears in exactly one worker's `naaf_worker_roles` list.

### Wrong — overlapping roles (DO NOT do this yet)

```bash
# DANGER: both workers subscribe to "backend"
docker compose run -d -e naaf_worker_roles=lead,backend worker
docker compose run -d -e naaf_worker_roles=backend,frontend worker
```

Overlapping roles will double-process messages for the shared role. This restriction will
be lifted once per-recipient advisory-lock hardening lands (tracked as a follow-up).

---

## Environment variables

| Variable | Purpose | Default (compose) |
|---|---|---|
| `naaf_db_url` | PostgreSQL DSN | `postgresql+psycopg://naaf:naaf@postgres:5432/naaf` |
| `naaf_celery_broker_url` | Redis broker DSN | `redis://redis:6379/0` |
| `naaf_worker_roles` | Comma-separated roles this worker handles | `lead,architect,backend,frontend,qa,devops` |

---

## Checking worker health

```bash
# Tail live logs
docker compose logs -f worker

# Inspect registered queues (requires a running worker)
docker compose exec worker uv run celery -A interactors.worker.celery_app:celery_app inspect active_queues
```
