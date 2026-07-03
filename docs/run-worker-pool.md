# Running the NAAF Worker Pool

## Prerequisites

```bash
docker compose up -d postgres redis
make db-upgrade
```

---

## Fake pipeline (no API keys required)

The default `naaf_agent_runtime=fake` runs the full plan→implement→verify→pr→learn pipeline
using `FakeAgentRuntime` — no LLM calls, no real git operations.

```bash
# Build and start the worker (fake mode is the default)
docker compose up --build worker

# In a separate terminal, start the API server (host-side, same postgres)
cd projects/server && make run

# Trigger a run
curl -s -X POST http://localhost:8000/work-items/<work_item_id>/runs \
     -H "Authorization: Bearer dev-token" | jq .

# Watch the worker logs drain the pipeline
docker compose logs -f worker
```

The worker polls the Celery queue, picks up the run task, and drives it through each stage.
Gate decisions (plan gate, merge gate) can be approved via:

```bash
curl -s -X POST http://localhost:8000/runs/<run_id>/gate \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{"decision":"approve"}'
```

---

## Real E2E (live LLM + real GitHub PR)

Set the following in your environment or a local `.env` file before starting the worker:

| Variable | Description |
|---|---|
| `naaf_agent_runtime` | Set to `claude_code` |
| `naaf_anthropic_api_key` | Your Anthropic API key |
| `GH_TOKEN` | A GitHub personal access token with `repo` scope (push access to the target repo) |

The project's `repo_url` must point to a GitHub repository the token can push to.

```bash
export naaf_agent_runtime=claude_code
export naaf_anthropic_api_key=sk-ant-...
export GH_TOKEN=ghp_...

docker compose up --build worker
```

The entrypoint runs `gh auth setup-git` when `GH_TOKEN` is set, configuring both git-HTTPS
and the `gh` CLI so `git clone`, `git push`, and `gh pr create` all authenticate via the token.

Once a run completes the `pr` stage, confirm:
- A real branch `agent/<run_id>` exists on the GitHub repo
- `GET /runs/<run_id>` shows `pr_url` pointing to the opened pull request

---

## Scaling by role — the disjoint-roles invariant

> **Bus dispatch roles are `lead`, `engineer`, and `qa` only.** These are the three roles the
> run pipeline hands off to via the message bus (`lead` drives plan/gate/pr/learn,
> `engineer` drives implement, `qa` drives verify). Roles like `architect`, `backend`,
> `frontend`, `devops`, and `curator` are **model-selection** roles — they control which LLM
> config is used inside an agent, but they are never bus message recipients and never appear
> in a `naaf_worker_roles` list.

Each bus dispatch role may be **in-flight in at most one worker at a time**. To scale
capacity, run multiple worker containers with **non-overlapping** `naaf_worker_roles` values
drawn from `{lead, engineer, qa}`. Every dispatch role must appear in exactly one worker.

**Correct — two workers with disjoint dispatch roles:**

```yaml
# docker-compose.override.yml
services:
  worker-engineer:
    build: .
    depends_on: [postgres, redis]
    environment:
      naaf_db_url: postgresql+psycopg://naaf:naaf@postgres:5432/naaf
      naaf_celery_broker_url: redis://redis:6379/0
      naaf_agent_runtime: ${naaf_agent_runtime:-fake}
      naaf_anthropic_api_key: ${naaf_anthropic_api_key:-}
      naaf_workspace_root: /workspaces
      naaf_worker_roles: "engineer"
      GH_TOKEN: ${GH_TOKEN:-}
    volumes:
      - naaf_workspaces:/workspaces

  worker-lead-qa:
    build: .
    depends_on: [postgres, redis]
    environment:
      naaf_db_url: postgresql+psycopg://naaf:naaf@postgres:5432/naaf
      naaf_celery_broker_url: redis://redis:6379/0
      naaf_agent_runtime: ${naaf_agent_runtime:-fake}
      naaf_anthropic_api_key: ${naaf_anthropic_api_key:-}
      naaf_workspace_root: /workspaces
      naaf_worker_roles: "lead,qa"
      GH_TOKEN: ${GH_TOKEN:-}
    volumes:
      - naaf_workspaces:/workspaces
```

**WRONG — do NOT do either of these:**

```bash
# BAD: --scale duplicates the default all-roles worker — every role is now claimed
# by two workers; both can pick up the same task simultaneously.
docker compose up --scale worker=2

# BAD: --concurrency=N lets a single worker run N tasks in parallel threads,
# violating the one-in-flight-per-recipient rule.
# (Do not add --concurrency to the entrypoint.)
```

> **Why this matters:** The advisory-lock hardening that enforces mutual exclusion at the
> database level is not yet shipped. Until then, disjoint role sets in separate containers is
> the only safe way to scale throughput without triggering duplicate task processing.

### Scaling caveat — Celery Beat duplication

The worker entrypoint runs `celery worker --beat`, so **every scaled container runs its own
Celery Beat scheduler**. This causes duplicate periodic task firing: the
`dispatch-subscriptions` beat task runs once per container, and because the `notifications`
subscription is not role-partitioned, scaled workers double-drain it.

**Recommendation:** Run a single worker container with empty `naaf_worker_roles` (the
default) for all E2E and development work — one Beat, no duplication. Disjoint-role
multi-worker mode is **advanced/experimental** until proper multi-worker Beat handling and
per-recipient advisory locking land as a follow-up.
