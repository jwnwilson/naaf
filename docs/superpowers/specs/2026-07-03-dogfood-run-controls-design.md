# Dogfood NAAF on Itself + Run Controls in the UI — Design

> Features **A + C** of the "dogfood NAAF on itself" effort (sequencing: B → **A+C** → D).
> Goal: run NAAF end-to-end against its own GitHub repo with the real Claude runtime, and give
> the user a UI control to start an agent run on a work item and watch it through to a PR.

## Problem

The real agent runtime (`LlmAgentRuntime`, all six stages `PROVISION → PLAN → IMPLEMENT →
VERIFY → PR → LEARN`) is already built and wired, and the run monitor renders live `RunOut` /
`RunEvent` with gate approve/reject. But two things block actually *using* it on the naaf repo:

1. **No reproducible dogfood setup.** Running the real runtime requires the right env
   (`naaf_agent_runtime=claude_code`, `naaf_anthropic_api_key`, `GH_TOKEN`) and a project whose
   `repoUrl` points at the naaf repo. This is possible today but undocumented and unvalidated.
2. **No in-product way to start a run.** `POST /work-items/{id}/runs` exists, but **nothing in the
   UI calls it** — no button, no empty-state CTA, no `useStartRun` hook. And the PR a run
   produces is only a plain-text log line (`"PR opened: <url>"`), not a first-class, clickable
   affordance (`pr_url` lives only inside a `RunEvent` payload, not on the `Run`).

## Decisions (resolved during brainstorming)

- **Repo target:** the **real naaf GitHub repo**. Agents clone `project.repoUrl`, branch
  `agent/<run>`, and open a real PR reviewed on GitHub. Zero new backend code for the repo path.
- **PR surfacing:** **first-class** — persist `pr_url` on the `Run`, expose `prUrl` on `RunOut`,
  render a **View PR** link in the monitor. Closes the tracked A5 follow-up (§ "A5 follow-ups #1").
- **Run eligibility (UI):** offer **Start run** on **Task and Feature** items only; epics remain
  containers. UI-level gate — the backend stays permissive.

---

## A — Dogfood setup (configuration + validation; ~no feature code)

The runtime is already wired, so A is about making it reproducible and proving it works.

### The self-project
Create a project named `naaf` whose **`repoUrl` = the naaf GitHub repo** (via the existing Create
Project modal). Add a small, **optional** convenience so setup is one repeatable command:

- A seed flag / `make dogfood` target that idempotently creates (or no-ops if present) a project
  pointing at the repo. Kept light; if skipped, the user just uses the Create Project modal.

### Real-Claude run mode
```
make dev NAAF_AGENT_RUNTIME=claude_code   # with the two secrets exported:
#   naaf_anthropic_api_key=sk-...          (LLM)
#   GH_TOKEN=ghp_...                        (push + PR on the naaf repo)
```
All compose/worker plumbing already accepts these (`docker-compose.yml` worker env, `Makefile`
`dev`/`worker`). `build_runtime` returns the real `LlmAgentRuntime` for any non-`fake` value;
`build_llm_adapter` fails fast if the key is empty.

### Deliverable: a dogfooding runbook
`docs/dogfooding.md` (or under `docs/superpowers/`) documenting:
- **Prerequisites:** Docker running, one-time `cd projects/ui && pnpm install`, `GH_TOKEN` with
  push + PR scope on the repo, `naaf_anthropic_api_key`.
- **Exact commands** to bring the stack up in real-Claude mode and create the self-project.
- **Validation checklist:** create a **Task** → **Start run** → watch the monitor → approve the
  plan + merge gates → **PR opens** → review it on GitHub. This is the acceptance test for A.

If validation surfaces real pipeline bugs, they are fixed during implementation (that is the
point of dogfooding); none are anticipated as blockers given the pipeline already runs e2e with
`FakeAgentRuntime`.

---

## C — Start & manage runs from the UI (the code)

### C1 — `useStartRun` hook
`projects/ui/src/lib/api/hooks/useStartRun.ts` — `apiPost<RunOut>('/work-items/{id}/runs')`. On
success, invalidate the work-item's run query (`useWorkItemRun` key) and the board query (the item
flips to `in_progress`). Surfaces `isPending` + `error` for the control.

### C2 — Start-run control
Shown only for **Task** and **Feature** work items (UI-level gate; backend unchanged):

- **Detail header button** (`modules/detail/ItemHeader.tsx` / `DetailScreen.tsx`) — **Start run**,
  sitting alongside feature B's **Edit** button.
- **Agent-tab empty state** (`DetailScreen.tsx` — today `<EmptyBody message="No active run" />`)
  becomes a **Start run** CTA for eligible items.
- **Disabled states** with an explanatory tooltip:
  - status not startable (not `TODO`/`IN_REVIEW`, per `domain/transitions.py`) → e.g. "Move to To
    Do to start";
  - a run is already active (`useWorkItemRun` returns a `running`/`queued` run) → "Run already in
    progress".
- **Lightweight confirm** before starting ("Start an agent run on this task? This uses the model
  and opens a PR.") — a real run costs tokens and creates a PR. Reuse the `Modal` primitive.
- **Error handling:** a 409 (invalid transition) is caught and shown inline on the control; the
  button re-enables. No silent failure.

### C3 — First-class PR surfacing
**Backend:**
- Add a nullable `pr_url` column to the `Run` ORM + domain entity (Alembic migration).
- On run finish, stamp the captured URL onto the `Run`. The regex extraction already exists
  (`_capture_pr_url` / `_PR_URL_RE` in `interactors/worker/handlers.py`, which emits a `RunEvent`
  with `payload.pr_url`); reuse it to also persist `run.pr_url` (immutable update via
  `model_copy`).
- Expose `prUrl` on `RunOut` (`interactors/api/contract.py`, set in `_run_out`).

**UI:**
- Render a **View PR** link/badge in the run-monitor header (`modules/detail/AgentMonitor.tsx`)
  when `run.prUrl` is set (opens the PR in a new tab).

### C4 — Mock-mode parity
- A `POST /work-items/{id}/runs` MSW handler that creates a mock run (status `running`), so the
  start→watch flow works with `VITE_USE_MOCKS`.
- `prUrl` populated on the mock `RunOut` so **View PR** is demoable without a backend.

## Data flow (C)

```
Detail "Start run" (Task/Feature, startable)
  → confirm dialog → useStartRun → POST /work-items/{id}/runs
  → backend: validate_transition→IN_PROGRESS, create queued Run, publish START(lead) to bus,
    flip work item to in_progress
  → invalidate run + board queries; monitor shows the live run (RunOut + SSE RunEvents)
  → worker drives PROVISION→PLAN→[plan gate]→IMPLEMENT→VERIFY→[merge gate]→PR→LEARN
  → PR stage: agent pushes agent/<run> + gh pr create; _capture_pr_url stamps run.pr_url
  → RunOut.prUrl set → monitor shows "View PR" → user reviews on GitHub
```

## Non-goals (YAGNI)

- **No explicit backend "one active run per work item" guard** — the status-transition rule
  already rejects a second concurrent start; the UI additionally disables the button.
- **No backend type restriction** — epics remain runnable via the raw API; Task/Feature scoping is
  a UI affordance only.
- **No run cancel / retry UI, no board-card run button** — Detail-screen only. Easy follow-ups.
- **No secrets-management UI** — real-mode secrets come from env for now (C management plane,
  later); the runbook documents this explicitly.

## Files touched (summary)

| File | Change |
|------|--------|
| `docs/dogfooding.md` | **new** runbook + validation checklist (A) |
| `projects/server/src/interactors/cli/seed.py` (+ Makefile) | **optional** idempotent self-project seed / `make dogfood` (A) |
| `projects/server/src/adapters/database/orm.py` + `domain/…/run.py` | add `pr_url` column/field (C3) |
| `projects/server/alembic/versions/…` | **new** migration for `pr_url` (C3) |
| `projects/server/src/interactors/worker/handlers.py` | stamp `run.pr_url` on finish (C3) |
| `projects/server/src/interactors/api/contract.py` + `routes/runs.py` | expose `prUrl` on `RunOut` (C3) |
| `projects/ui/src/lib/api/hooks/useStartRun.ts` (+ index) | **new** start-run mutation (C1) |
| `projects/ui/src/modules/detail/ItemHeader.tsx` / `DetailScreen.tsx` | Start-run button + empty-state CTA + confirm (C2) |
| `projects/ui/src/modules/detail/AgentMonitor.tsx` | **View PR** link (C3) |
| `projects/ui/src/lib/api/mocks/handlers.ts` (+ mock store) | mock start-run + `prUrl` (C4) |
| tests (backend pr_url + serialization; UI hook/button/CTA/link) | **new** |

## Acceptance

- Real-mode: from a freshly seeded `naaf` project, a user creates a Task, clicks **Start run**,
  watches the pipeline in the monitor, approves the gates, and clicks **View PR** to review a real
  PR on GitHub. (This is the A validation checklist, now driven entirely from the UI.)
- Mock-mode: the same start→watch→View PR flow is demoable without a backend.
