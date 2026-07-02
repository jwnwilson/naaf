# Containerized Worker Pool + Workspace + Real PRs (Design)

**Date:** 2026-07-02
**Status:** Approved (design) — ready for implementation plan(s)
**Phase:** A4 (sandbox / execution), slices 1+2 combined — egress hardening (slice 3) deferred

## Summary

Move the run worker into a **persistent, role-configured pool of Docker containers**, give
each run a **real cloned-repo workspace**, and produce a **real Pull Request via a GitHub
App**. The runtime that operates on the workspace stays behind the existing `AgentRuntime`
port (`FakeAgentRuntime` today, `LlmAgentRuntime` from A5 when integrated), so this slice
delivers the **execution environment and the PR pipeline**, not the agent itself.

Because A5 has already merged the `Workspace` port, `StageContext` (with `workspace_path`),
`LlmAgentRuntime`, tools, and the `LLMAdapter` port, this slice **builds on those seams**
rather than duplicating them: it supplies the missing **real Workspace adapter** plus the
container/git/GitHub-App plumbing. The runtime hand-off (wiring `LlmAgentRuntime` +
`StageContext` + a real `LLMAdapter` into the handler) is a **merge-time integration
checkpoint**, kept decoupled from this slice so parallel A5 work doesn't collide.

## Background & current state

- The run pipeline (`PLAN → PROVISION → IMPLEMENT → VERIFY → PR → LEARN`) is driven by a
  **single host Celery worker** (`worker_concurrency=1`) that drains **all** runs' agent
  messages from the Postgres bus (`bus_messages`, recipient key `run:<id>:<role>`) and calls
  the `AgentRuntime` inline. `PROVISION` and `PR` are **no-op stub stages**
  (`_STUB_STAGES = {PROVISION, PR, LEARN}`).
- **A5 already merged (on `main`):** `domain/agent/workspace.py` (`Workspace` port:
  `read/write/edit/grep/bash`), `domain/agent/context.py` (`StageContext` with
  `run_id, role, stage, workspace_path, work_item, agent, …`), `LlmAgentRuntime`
  (agent loop over `LLMAdapter` + tools + `Workspace`), `domain/agent/tools.py`,
  `domain/agent/llm.py`. **Missing:** any real `Workspace` adapter, GitHub/git plumbing,
  container/worker-pool infra, and the handler→`StageContext`→`LlmAgentRuntime` wiring.
- `docker-compose.yml` has only `postgres` + `redis`; there is **no Dockerfile** and no
  worker service. `Settings` uses env prefix `naaf_` (`db_url`, `auth_mode`,
  `celery_broker_url`).

## Goals

1. A **role-configured worker pool** in `docker-compose` (a scalable `worker` service); each
   worker claims only the bus messages for the role(s) it is configured to run.
2. **Multi-worker-safe claiming** — no two workers process the same message.
3. A **real `Workspace` adapter** (filesystem + shell over a cloned repo dir) implementing
   A5's `domain/agent/workspace.py` port.
4. **Real PRs via a GitHub App** — `PROVISION` clones the repo + mints a per-run token;
   `PR` commits + pushes an `agent/<work-item>` branch + opens a PR; teardown cleans the
   workspace + revokes the token.
5. Surface the PR: `Run.pr_url` + `RunOut.prUrl` + a **"View PR"** link in the run monitor.
6. Everything testable **without** Docker/GitHub (ports + fakes; SQLite).

## Non-Goals (deferred / out of scope)

- **Egress proxy + network hardening** (A4 slice 3) — deny-all + per-project allowlist.
- **Dynamic/app-managed container lifecycle** — the pool is static (docker-compose scale);
  the app never touches the Docker socket.
- **Real LLM agent behavior** — the runtime stays `FakeAgentRuntime` by default in this
  slice; wiring `LlmAgentRuntime` is the merge-time A5 checkpoint (below).
- **Per-model pricing / usage billing** (A5d).

## Architecture

Hexagonal, following the existing ports. New external I/O (git, GitHub, shell) lives behind
ports with fake adapters; the containerization is a deployment concern (compose), not app code.

### 1. Containerized worker pool

- A `Dockerfile` (repo root or `projects/server/`) builds an image with the server code +
  `git` + `uv`, entrypoint = the Celery worker.
- A `worker` service in `docker-compose.yml`, **scalable to N replicas**, sharing the same
  Postgres (`naaf_db_url`) + Redis broker. Per-worker config via env:
  - `naaf_worker_roles` — comma-separated roles the worker runs (e.g. `lead,backend`).
  - GitHub App creds + workspace root (below).
- Each replica runs the **existing** Celery worker loop unchanged in shape — Beat +
  `dispatch-subscriptions` + `process-subscription` — but the `agent-bus` source is
  **role-filtered** (next).

### 2. Role-filtered, multi-worker-safe claiming

- The message bus's `claim_next` gains an optional **role filter**: claim only pending
  `bus_messages` whose recipient role ∈ the worker's `naaf_worker_roles`. `BusSource`
  reads the roles from `Settings` and passes them.
- **Concurrency safety:** the claim uses Postgres **`SELECT … FOR UPDATE SKIP LOCKED`** so
  concurrent workers never grab the same row. This lives in the `SqlMessageBus` adapter; the
  SQLite test path keeps the current plain single-threaded claim (SQLite has no
  `SKIP LOCKED`, and tests are single-threaded). "One-in-flight per `run:<id>:<role>`"
  still holds — a message stays claimed until acked.
- Domain note: role is already a first-class column on `bus_messages` (`role`), so the
  filter is a `WHERE role IN (:roles)` — no schema change.

### 3. Real Workspace adapter (implements A5's port)

- Add `adapters/agent/workspace/local.py` — `LocalWorkspace(root: str)` implementing
  `domain/agent/workspace.py`:
  - `read/write/edit/grep` operate on files under `root` (the run's `workspace_path`).
  - `bash(cmd, timeout_s)` runs the command with `cwd=root` and a timeout, returning
    `CommandResult(exit_code, stdout, stderr)`. (Sandboxing/egress for `bash` is slice 3;
    here it is a local subprocess in the workdir.)
  - Path-safety: reject/normalize paths that escape `root`.
- This is the surface A5's `LlmAgentRuntime` (and its tools) already expect. A5 likely ships
  an in-memory fake for tool tests; this adds the real filesystem-backed adapter.

### 4. SCM port — clone / commit / push / PR (GitHub App)

- A new `Scm` port (protocol in `domain/scm/` — non-persistence port, co-located like
  `Workspace`) with the run's source-control lifecycle:
  - `mint_installation_token(repo) -> ScmToken` (short-lived, ~1h),
  - `clone(repo, token, dest, branch)` (clone + create/checkout `agent/<work-item>`),
  - `commit_and_push(dest, branch, message, token)`,
  - `open_pull_request(repo, head, base, title, body, token) -> pr_url`,
  - `revoke_token(token)`.
- **Real adapter** (`adapters/github/`): git via subprocess for clone/commit/push; GitHub
  REST for App-JWT → installation token → PR; `PyJWT` (or equiv) for the App JWT. Auth from
  `Settings`: `naaf_github_app_id`, `naaf_github_app_private_key` (PEM), installation
  resolved per repo.
- **Fake adapter** (in-memory): records calls, returns a synthetic `pr_url`; used by all
  handler/pipeline tests so no network/git is touched.

### 5. Pipeline wiring — fill the `PROVISION` / `PR` stubs

The worker's `HandlerContext` gains a `workspace_root`, an `Scm`, and a per-run
`RunWorkspace` record (token + workdir + branch), threaded through the run's stages:

- **PROVISION** (was stub): `scm.mint_installation_token(repo)` → `scm.clone(repo, token,
  workdir, branch=agent/<work-item-id>)`. Emit a `RunEvent` (provisioned). Store token +
  workdir on the run's handler context.
- **IMPLEMENT**: the configured `AgentRuntime` runs. Under the current fake path — to keep
  this slice **decoupled from A5's runtime/ctx wiring** — the handler writes a deterministic
  run-marker file into the workspace (e.g. `.naaf/run-<id>.md` with the work-item title) so
  the PR is non-empty, then commits it. **At the A5 checkpoint** this marker step is removed:
  `LlmAgentRuntime`, operating on `LocalWorkspace`, produces the real edits.
- **PR** (was stub): `scm.commit_and_push(workdir, branch, message, token)` (if uncommitted)
  → `scm.open_pull_request(repo, head=branch, base=default, title, body, token) -> pr_url`.
  Persist `pr_url` on the run; emit a `RunEvent` carrying it.
- **Teardown (LEARN)**: remove the per-run workdir (handler-level filesystem cleanup — the
  `Workspace` port has no lifecycle method; the run's provisioning owns the dir) +
  `scm.revoke_token(token)`. **The container persists** — cleanup is per-run inside the
  long-lived worker, not container destruction.

### 6. Surface the PR

- `Run` gains `pr_url: str | None = None`; `RunOut` gains `prUrl: str | None`; `_run_out`
  maps it. `RunRow` + Alembic migration add the `pr_url` column.
- The run monitor (`AgentMonitor`) shows a **"View PR"** link when `run.prUrl` is set — the
  natural payoff of the monitor shipped in the run-monitor-live slice.

## A5 integration seam & pre-merge checkpoint

- The **only** coupling to A5 is the `AgentRuntime` port + the `Workspace` port + the
  `StageContext.workspace_path` field — all already on `main`. This slice provides a real
  `Workspace` adapter and a real `workspace_path` (the cloned dir).
- This slice keeps `FakeAgentRuntime` as the default runtime and does **not** modify the
  handler's `run_stage(role, stage, ctx)` invocation shape or A5's `StageContext` wiring
  (avoiding conflicts with in-flight A5 work).
- **Pre-merge checkpoint:** before merging, verify whether A5's `LlmAgentRuntime` handler
  wiring (build `StageContext` with `workspace_path`, select `LlmAgentRuntime`, inject a
  real `LLMAdapter`) has landed. If ready, integrate: drop the fake run-marker step and let
  `LlmAgentRuntime` (on `LocalWorkspace`) produce the edits; select the runtime by config.
  If not, ship with the fake path — the marker produces a real (placeholder) PR and the swap
  lands with A5.

## Config, image, compose

- `Settings` (`naaf_` prefix) adds: `worker_roles: str = ""` (comma-separated),
  `workspace_root: str = "/workspaces"`, `github_app_id: str = ""`,
  `github_app_private_key: str = ""` (PEM or path), `runtime: str = "fake"` (`fake` | `llm`
  — the runtime selector for the A5 checkpoint).
- `Dockerfile`: server image (Python 3.12, `uv sync`, `git`), worker entrypoint.
- `docker-compose.yml`: a `worker` service (build the image; `naaf_worker_roles` +
  creds; depends on postgres/redis). Scale by **disjoint-role** workers (per-role services or
  `docker compose run -e naaf_worker_roles=…`), NOT `--scale` on the default all-roles service
  (that replicates the same roles and breaks one-in-flight-per-recipient — see the run-book).

## Error handling

- Every external boundary (git, GitHub, shell) behind a port with **typed domain errors**
  (`ScmError`, `WorkspaceError`) — no silent swallowing. A failed clone/push/PR fails the
  stage → the run fails via the existing poison/`on_poison` path (which already acks + marks
  the run failed + revokes... extend teardown to revoke the token on failure too).
- Token is always revoked and the workspace always cleaned, even on stage failure
  (teardown runs in a `finally`-style path).
- `bash` timeouts return a non-zero `CommandResult` rather than hanging.

## Testing

TDD; ≥80% backend coverage; ports + fakes so no Docker/GitHub/network in the suite.

- **Bus claim:** role-filter selects only configured roles; two "workers" (two sessions)
  don't double-claim (Postgres `SKIP LOCKED` verified in a Postgres-marked test or reasoned;
  SQLite path unit-tested for the role filter).
- **LocalWorkspace:** read/write/edit/grep over a `tmp_path`; `bash` runs a command with
  cwd + timeout; path-escape rejected.
- **Scm fake:** handler tests drive PROVISION→IMPLEMENT→PR→teardown against the fake Scm +
  LocalWorkspace(tmp): asserts clone→branch→(marker commit)→push→`open_pull_request` called,
  `pr_url` persisted on the run + `RunOut.prUrl` exposed, token minted at PROVISION +
  revoked at teardown (incl. on failure).
- **Migration:** `runs.pr_url` column added.
- **Real adapters** (git subprocess, GitHub REST): thin; integration/manually verified. The
  containerized pool + a real PR is a **manual end-to-end check** (documented run-book), not
  pytest-able.

## Decomposition — two sequenced plans under this spec

This spec is large; it becomes **two implementation plans**, sequenced A→B:

- **Plan A — Pooled/containerized worker + safe claiming:** Dockerfile + compose `worker`
  service; `naaf_worker_roles`; role-filtered `SKIP LOCKED` claim; runtime still fake,
  in-container. Deliverable: multiple role-scoped workers drain the bus safely.
- **Plan B — Workspace + Git/PR via GitHub App:** `LocalWorkspace` adapter; `Scm`
  port + fake + real GitHub-App adapter; wire `PROVISION`/`IMPLEMENT`(marker)/`PR`/teardown;
  `Run.pr_url` + `RunOut.prUrl` + monitor link + migration. Deliverable: a run produces a
  real PR.

Each plan produces working, tested software on its own; Plan B builds on Plan A.

## Open questions

None blocking. `runtime` selector + the A5 handler wiring are resolved at the pre-merge A5
checkpoint. The GitHub App must be created + installed on the target repo before the manual
end-to-end PR check (a setup step in the run-book, not code).
