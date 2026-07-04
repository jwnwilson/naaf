# Dogfooding NAAF on Itself — Live Pass Runbook

Run NAAF end-to-end against **its own repository** with the real Claude runtime: enter your
credentials in the **Settings → Secrets** UI, create a project linked to the naaf repo, then
either create a Task and **Start run** or **Chat with lead** to plan the work, approve the gates,
and review the PR the agents open.

Credentials are managed in the app (encrypted, injected into runs) — **not** via env vars. The only
environment value the server needs is `naaf_secret_key`, a non-credential master key used to
encrypt secrets at rest.

Covers features **A+C** (run controls), **D** (conversational lead), and secrets management.

## Prerequisites

- **Docker** running (Postgres + Redis).
- One-time UI deps: `cd projects/ui && pnpm install`.
- **`naaf_secret_key`** — a Fernet key for encrypting stored secrets. Generate one:
  ```bash
  make secret-key            # prints a fresh key, e.g. 041fL8iRCx…O80=
  ```
  Keep it stable across restarts — losing it makes previously stored secrets undecryptable (you'd
  just re-enter them in the UI).
- Have ready (you'll paste these into the UI, not the shell):
  - an **Anthropic API key**;
  - a **GitHub token** with **push + pull-request** scope on `https://github.com/jwnwilson/naaf`.

> Experimental dogfood runs open **real PRs** on the repo and spend **real Anthropic tokens**.
> Close/label PRs as needed, or point the project at a fork to keep the main repo's PR list clean.

## 1. Bring the stack up in real-Claude mode

```bash
export naaf_secret_key="$(make -s secret-key)"      # generate + export in one step
make dev NAAF_AGENT_RUNTIME=claude_code
```

`make dev` starts Postgres + Redis, migrates + seeds, then runs the API (`:8000`), the worker, and
the UI (`:5173`, live-API). `NAAF_AGENT_RUNTIME=claude_code` selects the real `LlmAgentRuntime`
(any value other than `fake`). No Anthropic/GitHub env vars are needed — those come from the UI.

## 2. Enter your credentials in the UI

In the UI (`http://localhost:5173`) go to **Settings → Secrets** and set:

- **Anthropic API key** → Save (shows `Set ••••<last4>`).
- **GitHub token** → Save.

Values are encrypted at rest and write-only — the raw value is never shown again. A run resolves
**your** stored keys per owner (falling back to any env values only if a secret is unset).

## 3. Create the self-project

Sidebar **PROJECTS → +** (New project):

- **Name:** `naaf`  ·  **Repo URL:** `https://github.com/jwnwilson/naaf` → **Create Project.**

The worker clones `repoUrl` at run time, branches `agent/<run>`, and opens the PR against it, using
your stored GitHub token for `git`/`gh`.

## 4a. Drive it directly — create a Task and Start run

1. Open the `naaf` board and create a **Task** (board column **+** or **New**) with a clear title
   and a spec describing the change.
2. On the task's **Detail** screen click **Start run** and confirm. (Only Task/Feature items show
   it; disabled unless the item is in **To Do**/**In Review** with no active run.)

## 4b. …or plan by conversation — Chat with lead

1. On the `naaf` board, open **Chat with lead** (right rail).
2. Describe what you want ("add X"). The lead creates an epic → features → tasks (they appear on
   the board, which polls live) and posts a **run proposal**.
3. Click **Approve** on the proposal to start development on the proposed tasks.

## 5. Watch it, gate it, review the PR

- The **Agent** tab (run monitor) streams `PROVISION → PLAN → [✋ plan gate] → IMPLEMENT → VERIFY →
  [✋ merge gate] → PR → LEARN`.
- Approve the **plan** and **merge** gates from the monitor or the thread.
- When the PR stage completes, the monitor shows a **View PR** link — click through to review the
  real PR on GitHub.

## Validation checklist

- [ ] `make secret-key` → exported as `naaf_secret_key`; stack up with `NAAF_AGENT_RUNTIME=claude_code`.
- [ ] Anthropic key + GitHub token saved in **Settings → Secrets** (both show `Set ••••…`).
- [ ] `naaf` project created with `repoUrl` = the GitHub repo.
- [ ] A run starts (Start run, or Chat-with-lead → Approve) and advances through all six stages.
- [ ] Both gates resolvable; approving continues the run.
- [ ] **View PR** appears and opens a real PR on GitHub.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Saving a secret returns a 500 | `naaf_secret_key` not set — generate with `make secret-key` and export it before starting the API. |
| Run fails at PLAN with a key error | No Anthropic key stored (Settings → Secrets) and none in env. |
| PR stage fails, no **View PR** | GitHub token missing or lacking push/PR scope on the repo. |
| **Start run** disabled | Item isn't a Task/Feature, isn't in To Do/In Review, or a run is already active (see tooltip). |
| Runs execute but do nothing real | `NAAF_AGENT_RUNTIME` still defaults to `fake` — pass `claude_code`. |
| Lead-created items don't show | The board polls every ~5s; give it a moment (or reload). |

> `naaf_secret_key` is the one env value the server needs — it is a master **encryption** key, not a
> credential. The Anthropic/GitHub secrets live in the app's encrypted store; a stored secret
> overrides the matching env var, so legacy `naaf_anthropic_api_key`/`GH_TOKEN` env still work as a
> fallback when a secret isn't set.
