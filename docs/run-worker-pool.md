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
docker compose run -d --rm -e naaf_worker_roles=lead,backend worker
docker compose run -d --rm -e naaf_worker_roles=backend,frontend worker
```

Overlapping roles will double-process messages for the shared role. This restriction will
be lifted once per-recipient advisory-lock hardening lands (tracked as a follow-up).

### Wrong — `--scale` on the default worker (DO NOT do this yet)

```bash
# DANGER: the default `worker` service is configured with ALL roles, so this
# starts N identical all-roles workers — every role is shared across N workers.
docker compose up --scale worker=3 worker
```

`--scale` replicates the **same** `naaf_worker_roles`, so it violates one-in-flight-per-recipient
exactly like overlapping roles above. To run more workers, add **per-role services** (or use the
disjoint-role `docker compose run` form above) so each role lives in exactly one worker — never
`--scale` the default all-roles service until the advisory-lock hardening lands.

> **Also load-bearing:** each worker container runs Celery with `worker_concurrency=1`
> (set in `celery_app.py`) — a single in-container dispatcher. Do **not** add
> `--concurrency=N` to the worker entrypoint; concurrent pool workers inside one container
> share the same roles and would race on the same recipient (which `SKIP LOCKED` does not
> prevent).

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
