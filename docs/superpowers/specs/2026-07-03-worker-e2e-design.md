# Containerized Worker Running the E2E Run (Design)

**Date:** 2026-07-03
**Status:** Approved (design) — ready for implementation plan
**Phase:** A4 slice 1 (re-based) + wiring the merged A5 E2E run into a container

## Summary

Package the agent worker as a **Docker service that runs the full end-to-end run** already
merged on `main` (PROVISION clones the repo → real `LlmAgentRuntime` implements/verifies in a
per-run workspace → the agent opens a PR via `gh` → LEARN curates), and add **role-filtered
claiming** so the pool can be scoped by role. The container carries everything the E2E run
needs: `git` + the `gh` CLI, the LLM key, a workspace volume, and a `GH_TOKEN` for git/PR auth.

This **supersedes the stale PR #18 (Plan A)**, which was based on `main` before the eight A5
phases landed and whose worker service lacked the E2E environment. This slice is a **fresh
branch off current `main`** that re-implements Plan A's role-filtering on top of the merged
code and adds the Dockerfile + a fully E2E-wired `worker` compose service.

## Background & current state (all on `main`)

The end-to-end run is **built and works via the host worker** (`make worker`):

- **Runtime factory** `adapters/agent/factory.py` — `build_runtime(settings)` returns
  `FakeAgentRuntime` (`naaf_agent_runtime=fake`) or `LlmAgentRuntime` (Claude / LiteLLM).
- **PROVISION** `adapters/agent/provision.py::provision_workspace(repo, run_id, root)` —
  `git clone <repo> <root>/<run_id>` + `agent/<run_id>` branch. Skips gracefully if the
  project has no repo.
- **IMPLEMENT/VERIFY** — `LlmAgentRuntime` runs the agent loop (read/write/edit/grep/bash
  tools) on a `LocalWorkspace` rooted at the run's workspace.
- **PR** — the agent runs `gh pr create` (per `domain/agent/prompts.py`); `handlers.py::
  _capture_pr_url` scrapes the URL from the stage output via `_PR_URL_RE` and stores it.
- **LEARN** — curator agent distills the run.
- **Settings** (`naaf_` prefix) already include `llm_provider`, `anthropic_api_key`,
  `agent_runtime`, `workspace_root` (`/tmp/naaf-workspaces`), `model_aliases`,
  `role_model_aliases`, etc.

**What is missing:** there is **no Dockerfile and no `worker` service** in
`docker-compose.yml` — the worker only runs on the host. And there is **no role-filtered
claiming** (a single host worker drains all roles). This slice fills both.

## Goals

1. A `Dockerfile` that builds a worker image with `git`, the `gh` CLI, `uv`, and the app.
2. A scalable `worker` service in `docker-compose.yml`, wired with the full E2E environment,
   that runs the merged pipeline end-to-end inside the container.
3. **Git/PR auth** in the container via a `GH_TOKEN` (both `git` over HTTPS and `gh pr create`).
4. **Role-filtered claiming** — `naaf_worker_roles` + `claim_next(roles)` + `BusSource(roles)`
   — so workers can be scoped to a role subset (role-partitioned pool).
5. A run-book: disjoint-roles invariant + the real-E2E setup (LLM key, `GH_TOKEN`, repo).

## Non-Goals (deferred)

- **Egress proxy / network hardening** (A4 slice 3).
- **GitHub App per-run installation tokens** — this slice uses a single `GH_TOKEN`; the App
  (short-lived per-run tokens) is a later hardening.
- **Dynamic/app-managed container lifecycle** — the pool is static (docker-compose scale by
  disjoint roles).
- **New E2E pipeline logic** — the run is already built on `main`; this slice only
  containerizes + role-scopes the worker. No change to `provision.py`, the runtime, or the
  PR-capture logic.
- **Per-recipient advisory-lock** for multiple workers sharing a role — role partition is the
  invariant; advisory-lock hardening is a follow-up (as in Plan A).

## Architecture

### 1. Worker image (`Dockerfile`, repo root)

- `FROM python:3.12-slim`; install `git`, `ca-certificates`, and the **`gh` CLI** (GitHub's
  apt repo or the released `.deb`); copy `uv` from `ghcr.io/astral-sh/uv`.
- Copy `pyproject.toml`, `uv.lock`, `libs/`, `projects/server/`; `RUN uv sync --frozen`
  (NOT `--no-dev` — the app packages `naaf-server`/`naaf-crud-router` are in the `dev`
  dependency-group).
- An **entrypoint script** that, when `GH_TOKEN` is set, runs `gh auth setup-git` (so `git`
  HTTPS operations and `gh` both authenticate), then `exec`s the Celery worker+beat from
  `projects/server` (the same command as the `make worker` target).

### 2. `worker` compose service (`docker-compose.yml`)

- `build: .`, `depends_on: [postgres, redis]`, scalable by **disjoint** `naaf_worker_roles`.
- Environment (E2E):
  - `naaf_db_url` (the compose postgres), `naaf_celery_broker_url` (the compose redis),
  - `naaf_agent_runtime` — **default `fake`** (CI / no-key envs work); set `claude_code` for
    a real run,
  - `naaf_anthropic_api_key` — passed from the host env / `.env` (blank in fake mode),
  - `naaf_workspace_root` — a path under a named `workspaces` volume,
  - `naaf_worker_roles`,
  - `GH_TOKEN` — from the host env / `.env` (blank in fake mode).
- A named `workspaces` volume mounted at `naaf_workspace_root` so clones live outside the
  container layer and can be inspected.

### 3. Role-filtered claiming (re-implemented on current `main`)

Identical in intent to Plan A (which is not merged):

- `Settings.worker_roles: str = ""` + `worker_roles_list` (csv → trimmed list).
- `MessageBus.claim_next(roles: list[str] | None = None)` — add `role IN roles` when `roles`
  is truthy; preserve the existing `FOR UPDATE SKIP LOCKED` + busy-recipient exclusion +
  ordering. `roles=None`/empty claims any (back-compat).
- `BusSource(roles)` passes them; the `agent-bus` subscription builds
  `BusSource(Settings().worker_roles_list or None)`.
- **Invariant:** one-in-flight per recipient (`run:<id>:<role>`) is preserved by
  **partitioning roles one-per-worker** (each role served by exactly one worker) + the
  existing per-container `worker_concurrency=1`. Advisory-lock hardening for multiple workers
  sharing a role is a follow-up. The run-book warns against overlapping roles and against
  `docker compose up --scale` on the default (all-roles) service.

## Data flow (an E2E run in the container)

1. `POST /work-items/{id}/runs` (API on host or in a container) enqueues a run + START on the bus.
2. A worker container claims the run's `lead` message (filtered to its roles), drives PLAN.
3. **PROVISION:** `git clone` the project's `repo_url` into `naaf_workspace_root/<run_id>`
   (auth via the container's `gh`-configured git credential).
4. **IMPLEMENT/VERIFY:** `LlmAgentRuntime` (real, when `naaf_agent_runtime=claude_code`) edits +
   runs the repo's checks in the workspace via bash tools.
5. **PR:** the agent runs `gh pr create` (authed by `GH_TOKEN`); `_capture_pr_url` records the URL.
6. **LEARN:** curator distills; the run ends `succeeded`; `pr_url` is on the run.

In **fake mode** (default), steps 3–6 run the scripted `FakeAgentRuntime` (provision skips if no
repo / uses a local path) so the pipeline shape is exercised in-container without keys.

## Error handling

- PROVISION already fails the stage (not the worker) on git errors; unchanged.
- Missing `GH_TOKEN` in real mode → `gh`/git auth fails at the PR/clone step → the stage fails
  and the run fails via the existing poison path. The run-book makes the required env explicit.
- `agent_runtime=claude_code` without `naaf_anthropic_api_key` raises at factory build (existing
  behavior) — documented as a required env for real runs.

## Testing

TDD; ≥80% backend coverage; ports + fakes; no live LLM/GitHub in the suite.

- **Role filter (SQLite):** `claim_next(["backend"])` claims only backend; `claim_next()` any;
  no-match → None. `BusSource(roles)` fetches only configured roles; default drains any
  (existing pipeline unaffected). `Settings.worker_roles_list` parsing.
- **Container (Docker available in dev):** `docker build` succeeds; in-image
  `import interactors.worker.celery_app` runs; `gh --version` + `git --version` present in the
  image; `docker compose config -q` valid.
- **Fake E2E smoke (manual/dev, documented):** with `naaf_agent_runtime=fake` and a project
  whose `repo_url` is a local path (or no repo → provision skips), a started run drains to
  `succeeded` inside the container.
- **Real E2E (manual run-book):** `naaf_agent_runtime=claude_code` + `naaf_anthropic_api_key` +
  `GH_TOKEN` + a GitHub repo → a real PR appears on `agent/<run_id>` and `pr_url` shows in the
  monitor. Not pytest-able.

## Rollout / housekeeping

- Fresh branch `feat/worker-e2e` off current `main`. **Close PR #18** (superseded) with a note
  pointing here.
- Sequenced: role-filtering code (settings → claim_next → BusSource) first, then the Dockerfile
  + entrypoint + compose worker service + run-book, then gates/docs.

## Open questions

None blocking. The `gh` CLI install method (apt repo vs pinned `.deb`) is an implementation
detail resolved in the plan; a version pin is preferred for reproducibility.
