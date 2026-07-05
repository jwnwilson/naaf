# End-to-End Tests

NAAF's e2e suite uses [Playwright](https://playwright.dev/) and runs against a full local stack
(API + Celery worker + Vite UI) wired to an isolated `naaf_e2e` Postgres database.

## What the suite covers

| Spec | Tag | What it verifies |
|------|-----|------------------|
| `smoke.spec.ts` | — | API health-check + UI root loads |
| `streaming-journey.spec.ts` | — | Full chat→task→run pipeline using the scripted LLM adapter |
| `streaming-journey.spec.ts` | `@real` | Same flow with a live Claude subscription (loose assertions) |

The **scripted journey** covers:

1. Create a project (API) with `full_auto` autonomy (no gate interrupts).
2. Navigate to the board; send a chat message to the lead agent.
3. Assert the activity feed streams `CHAT_TEXT_PLAN` (deterministic scripted output).
4. Poll the API until a work item with `TASK_TITLE` appears in the DB.
5. Open the task detail page; start a run.
6. Assert the run monitor streams `STAGE_TEXT_SCAN` and `STAGE_TEXT_DONE`.
7. Assert the run status reaches at least the `verify` stage.

## How the ScriptedLLMAdapter works

`projects/server/src/adapters/agent/scripted/` contains a fake LLM adapter selected by
`naaf_llm_provider=scripted`. It replaces only the model layer — everything else
(orchestrator, pub/sub bus, worker, API, UI) is real production code.

The adapter emits a fixed sequence of deterministic text events defined in `script.py`.
The matching constants in `projects/ui/e2e/fixtures/scripted.ts` must stay in sync
with `script.py`; a drift between the two files will cause `toContainText` assertions
to fail, catching regressions immediately.

The scripted adapter requires no API key and no network access, making the suite
fast and hermetic.

## Running locally

### Scripted stack (default — CI-equivalent)

```bash
make e2e
```

This command:

1. Starts Postgres + Redis via `docker compose -p naaf up -d` (reuses the naaf project
   so it shares containers with `make dev` without port conflicts).
2. Runs `alembic upgrade head` against `naaf_e2e`.
3. Truncates all e2e tables and re-seeds (idempotent).
4. Boots the worker, API (:8000), and UI (:5173) with `naaf_llm_provider=scripted`.
5. Waits for both services to be ready.
6. Runs the full Playwright suite (excludes `@real` tests by default).
7. Tears everything down on exit (portable cleanup: tries `fuser`, falls back to `lsof`).

Pass `E2E_SPEC=e2e/smoke.spec.ts` to run a single spec file:

```bash
make e2e E2E_SPEC=e2e/smoke.spec.ts
```

### Real-Claude smoke test (subscription required)

```bash
make e2e-real
```

This boots the same stack but with `naaf_llm_provider=claude_cli` and `NAAF_E2E_REAL=1`,
then runs only tests tagged `@real`. Assertions are deliberately loose (no exact-string
checks) because real LLM output varies.

Requirements:

- A valid `naaf_anthropic_api_key` in `.env` or the environment.
- An active Anthropic subscription (the `claude_cli` adapter uses the Claude CLI).

## CI

The `e2e` GitHub Actions workflow (`.github/workflows/e2e.yml`) runs on every pull request
and `workflow_dispatch`. It:

1. Provisions Postgres 16 and Redis 7 as **service containers** (already healthy when the
   job step runs — no `docker compose up` needed).
2. Installs `postgresql-client` so `psql`/`createdb`/`pg_isready` are available on the runner.
3. Installs Python + uv + Node + pnpm + Playwright Chromium.
4. Runs `make e2e` with `CI=true` and
   `NAAF_E2E_DB_URL=postgresql+psycopg://naaf:naaf@localhost:5432/naaf_e2e`.

### CI vs local DB provisioning

When `CI=true` (or `NAAF_E2E_SKIP_COMPOSE=1`) the `e2e-db` Makefile target takes a different
path from the local one:

| Step | Local | CI |
|------|-------|-----|
| Start services | `docker compose -p naaf up -d postgres redis` | skipped (service containers) |
| Wait for Postgres | `docker compose exec pg_isready` | `pg_isready -h localhost` directly |
| Create `naaf_e2e` DB | `docker compose exec createdb` | `PGPASSWORD=... createdb -h localhost` |
| Truncate tables | `docker compose exec psql` | `PGPASSWORD=... psql -h localhost` |
| Alembic / seed | `naaf_db_url=... uv run alembic` | same (URL already points at localhost) |

The `@real` tests are **never** run in CI — `NAAF_E2E_REAL` is not set in the workflow.

## Viewing a failing trace

Playwright saves HTML reports and traces on failure. To view the last report:

```bash
pnpm --dir projects/ui exec playwright show-report
```

This opens an interactive browser report with screenshots, video, and network logs.
Trace files (for the `--trace on-first-retry` default) can be inspected via the
"Traces" tab in the report.
