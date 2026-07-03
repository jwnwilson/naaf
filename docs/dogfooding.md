# Dogfooding NAAF on Itself

Run NAAF end-to-end against **its own repository** with the real Claude runtime: create a
project linked to the naaf repo, create a Task, start an agent run from the UI, watch it through
the pipeline, approve the gates, and review the PR it opens.

This is the acceptance path for features **A + C** (`docs/superpowers/specs/2026-07-03-dogfood-run-controls-design.md`).

## Prerequisites

- **Docker** running (Postgres + Redis + the worker container).
- One-time UI deps: `cd projects/ui && pnpm install`.
- **`naaf_anthropic_api_key`** — an Anthropic API key (the run fails fast at startup if the real
  runtime is selected without one).
- **`GH_TOKEN`** — a GitHub token with **push + pull-request** scope on the naaf repo
  (`https://github.com/jwnwilson/naaf`). The PR stage runs `gh pr create`; without push access it
  cannot open the PR.

> Experimental dogfood runs open **real PRs** on the repo. Close/label them as needed, or point
> the project at a fork if you want to keep the main repo's PR list clean.

## 1. Bring the stack up in real-Claude mode

```bash
export naaf_anthropic_api_key=sk-ant-...
export GH_TOKEN=ghp_...
make dev NAAF_AGENT_RUNTIME=claude_code
```

`make dev` starts Postgres + Redis, migrates + seeds, then runs the API (`:8000`), the worker,
and the UI (`:5173`, live-API). `NAAF_AGENT_RUNTIME=claude_code` selects the real
`LlmAgentRuntime` (any value other than `fake`); `build_llm_adapter` raises immediately if the
Anthropic key is missing, so a misconfigured key is an obvious startup error, not a mid-run
failure.

## 2. Create the self-project

In the UI (`http://localhost:5173`):

1. Sidebar **PROJECTS → +** (New project).
2. **Name:** `naaf`  ·  **Repo URL:** `https://github.com/jwnwilson/naaf`
3. **Create Project.**

The worker clones `repoUrl` at run time, branches `agent/<run>`, and opens the PR against it.

## 3. Create a Task and start a run

1. Open the `naaf` project's board and create a **Task** (board column **+** or the **New**
   button). Give it a clear title and a spec describing the change you want.
2. Open the task's **Detail** screen. Click **Start run** (in the header or the Agent tab's
   empty-state CTA) and confirm. Only **Task** and **Feature** items expose this control; it is
   disabled (with a tooltip) unless the item is in **To Do**/**In Review** and has no active run.

## 4. Watch it, gate it, review the PR

- The **Agent** tab (run monitor) streams the pipeline: `PROVISION → PLAN → [✋ plan gate] →
  IMPLEMENT → VERIFY → [✋ merge gate] → PR → LEARN`.
- Approve the **plan** and **merge** gates from the monitor (or the work-item thread).
- When the PR stage completes, the monitor shows a **View PR** link (persisted `prUrl` on the
  run) — click through to review the PR on GitHub.

## Validation checklist

- [ ] Stack comes up with `NAAF_AGENT_RUNTIME=claude_code` and both secrets set.
- [ ] `naaf` project created with `repoUrl` = the GitHub repo.
- [ ] Task created; **Start run** enabled only for a startable Task/Feature.
- [ ] Run advances through all six stages in the monitor.
- [ ] Both gates resolvable; approving continues the run.
- [ ] **View PR** appears and opens a real PR on GitHub.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| API/worker exits on start | Missing `naaf_anthropic_api_key` with `claude_code` runtime — export it. |
| PR stage fails, no **View PR** | `GH_TOKEN` missing or lacks push/PR scope on the repo. |
| **Start run** disabled | Item isn't a Task/Feature, isn't in To Do/In Review, or a run is already active (see tooltip). |
| Runs execute but do nothing real | `NAAF_AGENT_RUNTIME` still defaults to `fake` — pass `claude_code`. |

> Secrets come from the environment for now (no secrets-management UI yet — that's the later C
> management plane). The worker compose service already accepts `naaf_anthropic_api_key`,
> `GH_TOKEN`, and `naaf_workspace_root`.
