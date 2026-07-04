# Live Agents Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mocked dashboard "running agents" panel (and the "ACTIVE AGENTS" metric count) with real data showing which team roles are live and running, driven by active runs.

**Architecture:** A pure domain aggregator joins the enabled `AgentDefinition` roster with active runs (`status ∈ {running, awaiting_gate}`) into one role-oriented row each, marking a role "running" when an active run's current stage maps to it. A new owner-scoped `GET /agents` endpoint serves it; the UI polls it (~5s) and renders running/idle rows. No new persistence, no migration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (read-only aggregation), pydantic v2; React + Vite + Tailwind + React Query + MSW; pytest + Vitest.

**Reference spec:** `docs/superpowers/specs/2026-07-04-live-agents-dashboard-design.md`

## Global Constraints

- Python ≥ 3.12; `uv`; env prefix `naaf_`. Domain logic is pure — no I/O, no adapter imports.
- API envelope: every response is `{success, data, error}` via `crud_router.ok`; `Envelope[...]` response_model.
- Owner scoping: `GET /agents` reads through the owner-scoped `get_uow`; the UoW stamps `owner_id` on every query. No cross-owner data.
- Immutability: pydantic models via `model_copy`/fresh construction, never mutated in place.
- Role mapping (canonical): stage-role → `AgentRole`: `lead→LEAD`, `engineer→BACKEND`, `qa→QA`. Stage → stage-role: `plan/provision/pr/learn→lead`, `implement→engineer`, `verify→qa`.
- Row order (fixed): `lead, architect, backend, frontend, qa, devops`; any other role (e.g. `custom`) sorts last.
- Concurrent same-role runs collapse to one row — the **most-recently-started** run wins (by `started_at`, fallback `created_at`).
- `awaiting_gate` counts as running. Progress = (stages with status `passed`) / 6 total pipeline stages.
- Refresh: React Query `refetchInterval` (`AGENTS_POLL_MS = 5000`), paused when tab hidden (default `refetchIntervalInBackground: false`) — same as `useBoard`/`BOARD_POLL_MS`.
- TDD: failing test first; AAA; descriptive names. `make coverage` (80% gate) + `make lint` green; UI `pnpm test` + `pnpm lint` + `pnpm build` green.
- Commit format: `<type>: <description>`.
- Backend tests run from `projects/server` (`uv run pytest ...`); UI tests from `projects/ui` (`pnpm test`).

## File Structure

**New — backend**
- `projects/server/src/domain/live_agents.py` — `LiveAgent` value object, role/stage maps, `build_live_agents(...)` pure aggregator.
- `projects/server/src/interactors/api/routes/agents.py` — `GET /agents` route.
- Tests: `projects/server/tests/domain/test_live_agents.py`, `projects/server/tests/interactors/api/test_agents_api.py`.

**Modified — backend**
- `projects/server/src/interactors/api/contract.py` — add `AgentOut`.
- `projects/server/src/interactors/api/routes/__init__.py` — register `agents_router`.

**Modified — UI**
- `projects/ui/src/lib/api/hooks/useAgents.ts` — role-oriented `Agent` type + `AGENTS_POLL_MS` + `refetchInterval`.
- `projects/ui/src/lib/api/mocks/fixtures/index.ts` — reshape `agents` seed to the new shape.
- `projects/ui/src/lib/api/mocks/handlers.ts` — move `/agents` handler from `mockOnlyHandlers` to `liveHandlers`.
- `projects/ui/src/modules/dashboard/RunningAgentsPanel.tsx` (+ `.test.tsx`) — render role rows, drop Pause/Assign.
- `projects/ui/src/modules/dashboard/MetricCards.tsx` (+ `.test.tsx`) — active count from `useAgents`.
- `projects/ui/src/lib/api/hooks/useAgents.test.tsx` (new) — hook shape + poll.
- `projects/ui/src/modules/dashboard/DashboardScreen.test.tsx` — update if it asserts old agent fields.
- `docs/project-history.md` — status entry (final task).

---

### Task 1: Domain aggregator — `build_live_agents`

**Files:**
- Create: `projects/server/src/domain/live_agents.py`
- Create: `projects/server/tests/domain/test_live_agents.py`

**Interfaces:**
- Consumes: `domain.team.AgentDefinition`, `domain.team.AgentRole`, `domain.runs.run.Run`, `Stage`, `StageState`, `StageStatus`, `RunStatus`.
- Produces:
  - `LiveAgent(BaseModel)` — fields `role: AgentRole`, `model: str`, `status: str` (`"running"|"idle"`), `run_id: str | None = None`, `work_item_id: str | None = None`, `current_stage: Stage | None = None`, `progress: float | None = None`, `token_usage: int = 0`.
  - `build_live_agents(definitions: list[AgentDefinition], active_runs: list[Run]) -> list[LiveAgent]`.
  - `STAGE_ROLE_TO_AGENT_ROLE: dict[str, AgentRole]`, `STAGE_TO_STAGE_ROLE: dict[Stage, str]`, `ROLE_ORDER: list[AgentRole]`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/domain/test_live_agents.py`:

```python
from datetime import UTC, datetime

from domain.live_agents import build_live_agents
from domain.runs.run import Run, RunStatus, Stage, StageState, StageStatus
from domain.team import AgentDefinition, AgentRole


def _defn(role: AgentRole, model: str = "sonnet") -> AgentDefinition:
    return AgentDefinition(owner_id="o", team_id="t", role=role, model_alias=model)


def _run(stage: Stage, role: str, *, status=RunStatus.RUNNING, wi="wi1",
         passed: int = 0, tokens: int = 0, started=None) -> Run:
    stages = [StageState(stage=stage, status=StageStatus.RUNNING, role=role)]
    stages += [StageState(stage=Stage.PLAN, status=StageStatus.PASSED)] * passed
    return Run(
        owner_id="o", work_item_id=wi, project_id="p", autonomy_level="gated_all",
        status=status, current_stage=stage, stages=stages, token_usage=tokens,
        started_at=started,
    )


def test_all_roster_roles_idle_when_no_active_runs():
    rows = build_live_agents([_defn(AgentRole.LEAD), _defn(AgentRole.QA)], [])
    assert {r.role for r in rows} == {AgentRole.LEAD, AgentRole.QA}
    assert all(r.status == "idle" and r.run_id is None and r.token_usage == 0 for r in rows)


def test_engineer_stage_lights_up_backend_role():
    rows = build_live_agents(
        [_defn(AgentRole.BACKEND)],
        [_run(Stage.IMPLEMENT, "engineer", wi="wiX", tokens=500)],
    )
    backend = next(r for r in rows if r.role == AgentRole.BACKEND)
    assert backend.status == "running"
    assert backend.work_item_id == "wiX"
    assert backend.current_stage == Stage.IMPLEMENT
    assert backend.token_usage == 500


def test_lead_and_qa_mappings():
    rows = build_live_agents(
        [_defn(AgentRole.LEAD), _defn(AgentRole.QA)],
        [_run(Stage.PLAN, "lead"), _run(Stage.VERIFY, "qa")],
    )
    by_role = {r.role: r for r in rows}
    assert by_role[AgentRole.LEAD].status == "running"
    assert by_role[AgentRole.QA].status == "running"


def test_awaiting_gate_counts_as_running():
    rows = build_live_agents(
        [_defn(AgentRole.LEAD)],
        [_run(Stage.PLAN, "lead", status=RunStatus.AWAITING_GATE)],
    )
    assert rows[0].status == "running"


def test_progress_is_passed_over_total():
    rows = build_live_agents(
        [_defn(AgentRole.BACKEND)],
        [_run(Stage.IMPLEMENT, "engineer", passed=3)],
    )
    assert rows[0].progress == 0.5  # 3 passed / 6 total stages


def test_two_runs_same_role_most_recent_wins():
    older = _run(Stage.IMPLEMENT, "engineer", wi="old",
                 started=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _run(Stage.IMPLEMENT, "engineer", wi="new",
                 started=datetime(2026, 6, 1, tzinfo=UTC))
    rows = build_live_agents([_defn(AgentRole.BACKEND)], [older, newer])
    backend = next(r for r in rows if r.role == AgentRole.BACKEND)
    assert backend.work_item_id == "new"


def test_run_role_without_roster_row_lights_nothing():
    rows = build_live_agents([_defn(AgentRole.LEAD)], [_run(Stage.IMPLEMENT, "engineer")])
    assert rows[0].role == AgentRole.LEAD and rows[0].status == "idle"


def test_rows_in_fixed_role_order():
    rows = build_live_agents(
        [_defn(AgentRole.QA), _defn(AgentRole.LEAD), _defn(AgentRole.BACKEND)], []
    )
    assert [r.role for r in rows] == [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/test_live_agents.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.live_agents'`.

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/live_agents.py`:

```python
from pydantic import BaseModel

from domain.runs.run import Run, Stage, StageStatus
from domain.team import AgentDefinition, AgentRole

# Pipeline dispatch stage-role -> roster AgentRole.
STAGE_ROLE_TO_AGENT_ROLE: dict[str, AgentRole] = {
    "lead": AgentRole.LEAD,
    "engineer": AgentRole.BACKEND,
    "qa": AgentRole.QA,
}

# Fallback: which stage-role runs each stage (when a StageState carries no role).
STAGE_TO_STAGE_ROLE: dict[Stage, str] = {
    Stage.PLAN: "lead",
    Stage.PROVISION: "lead",
    Stage.PR: "lead",
    Stage.LEARN: "lead",
    Stage.IMPLEMENT: "engineer",
    Stage.VERIFY: "qa",
}

# Fixed display order for roster rows.
ROLE_ORDER: list[AgentRole] = [
    AgentRole.LEAD,
    AgentRole.ARCHITECT,
    AgentRole.BACKEND,
    AgentRole.FRONTEND,
    AgentRole.QA,
    AgentRole.DEVOPS,
]

_TOTAL_STAGES = len(list(Stage))  # 6


class LiveAgent(BaseModel):
    role: AgentRole
    model: str
    status: str = "idle"  # "running" | "idle"
    run_id: str | None = None
    work_item_id: str | None = None
    current_stage: Stage | None = None
    progress: float | None = None
    token_usage: int = 0


def _current_agent_role(run: Run) -> AgentRole | None:
    if run.current_stage is None:
        return None
    stage_role: str | None = None
    for s in run.stages:
        if s.stage == run.current_stage:
            stage_role = s.role
            break
    if stage_role is None:
        stage_role = STAGE_TO_STAGE_ROLE.get(run.current_stage)
    if stage_role is None:
        return None
    return STAGE_ROLE_TO_AGENT_ROLE.get(stage_role)


def _progress(run: Run) -> float:
    passed = sum(1 for s in run.stages if s.status == StageStatus.PASSED)
    return round(passed / _TOTAL_STAGES, 2)


def _order_key(agent: LiveAgent) -> int:
    return ROLE_ORDER.index(agent.role) if agent.role in ROLE_ORDER else len(ROLE_ORDER)


def build_live_agents(
    definitions: list[AgentDefinition], active_runs: list[Run]
) -> list[LiveAgent]:
    """Join the enabled roster with active runs into one row per role.

    Each enabled AgentDefinition becomes an idle row; an active run whose current
    stage maps to a roster role marks that row running. Concurrent same-role runs
    collapse to the most-recently-started one.
    """
    rows: dict[AgentRole, LiveAgent] = {}
    for d in definitions:
        if not d.enabled:
            continue
        rows.setdefault(d.role, LiveAgent(role=d.role, model=d.model_alias))

    # Sort oldest-first so the most recent run overwrites last (wins).
    def _started(r: Run):
        return r.started_at or r.created_at or r.id

    for run in sorted(active_runs, key=_started):
        role = _current_agent_role(run)
        if role is None or role not in rows:
            continue
        rows[role] = LiveAgent(
            role=role,
            model=rows[role].model,
            status="running",
            run_id=run.id,
            work_item_id=run.work_item_id,
            current_stage=run.current_stage,
            progress=_progress(run),
            token_usage=run.token_usage,
        )

    return sorted(rows.values(), key=_order_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/test_live_agents.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/live_agents.py projects/server/tests/domain/test_live_agents.py
git commit -m "feat: live-agents domain aggregator (roster + active runs -> role rows)"
```

---

### Task 2: Backend route — `GET /agents`

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py`
- Create: `projects/server/src/interactors/api/routes/agents.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Create: `projects/server/tests/interactors/api/test_agents_api.py`

**Interfaces:**
- Consumes: `build_live_agents`, `LiveAgent` (Task 1); `uow.agent_definitions`, `uow.runs` (existing); `get_uow`; `crud_router.Envelope`/`ok`.
- Produces: `AgentOut` contract (`role, model, status, runId, workItemId, currentStage, progress, tokenUsage`); `GET /agents` → `Envelope[list[AgentOut]]`; `agents_router`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/interactors/api/test_agents_api.py`:

```python
def _seed_roster(client):
    """Create a team + two agent definitions (lead, backend) via the API/DB."""
    team = client.post("/teams", json={"name": "Core"}).json()["data"]
    return team["id"]


def test_agents_endpoint_returns_roster_all_idle_without_runs(client):
    # The dev seed / a fresh DB may have no definitions; assert envelope + list shape.
    resp = client.get("/agents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert all(row["status"] in ("running", "idle") for row in body["data"])


def test_agents_reflects_a_running_backend(client, running_backend_run):
    # running_backend_run fixture: an enabled backend AgentDefinition + a run whose
    # current stage is IMPLEMENT (engineer). See conftest note below.
    rows = client.get("/agents").json()["data"]
    backend = next((r for r in rows if r["role"] == "backend"), None)
    assert backend is not None
    assert backend["status"] == "running"
    assert backend["currentStage"] == "implement"
    assert backend["workItemId"] == running_backend_run["work_item_id"]


def test_agents_is_owner_scoped(client_other_owner, running_backend_run):
    rows = client_other_owner.get("/agents").json()["data"]
    assert all(r["status"] == "idle" for r in rows)  # other owner sees no running rows
```

Note on fixtures: reuse the existing `client` / `client_other_owner` fixtures in
`projects/server/tests/interactors/api/conftest.py`. Add a `running_backend_run` fixture there that,
using the same owner-scoped UoW the app uses, (1) creates a `Team` + an enabled `AgentDefinition`
with `role=AgentRole.BACKEND`, and (2) inserts a `Run` with `status=RunStatus.RUNNING`,
`current_stage=Stage.IMPLEMENT`, and a `StageState(stage=IMPLEMENT, status=RUNNING, role="engineer")`,
returning a dict with its `work_item_id`. Follow how existing run/agent-definition tests seed rows
(look for a `uow`/`session_factory` fixture and `uow.runs.create(...)` / `uow.agent_definitions.create(...)`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_agents_api.py -v`
Expected: FAIL — `GET /agents` 404 (route not registered) / `AgentOut` import error.

- [ ] **Step 3: Write minimal implementation**

Add `AgentOut` to `projects/server/src/interactors/api/contract.py` (near `AgentDefinitionOut`):

```python
class AgentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: str
    model: str
    status: str  # "running" | "idle"
    runId: str | None = None
    workItemId: str | None = None
    currentStage: str | None = None
    progress: float | None = None
    tokenUsage: int
```

Create `projects/server/src/interactors/api/routes/agents.py`:

```python
from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.live_agents import LiveAgent, build_live_agents
from fastapi import APIRouter, Depends

from interactors.api.contract import AgentOut
from interactors.api.deps import get_uow

router = APIRouter(prefix="/agents", tags=["agents"])


def _agent_out(a: LiveAgent) -> AgentOut:
    return AgentOut(
        role=a.role.value,
        model=a.model,
        status=a.status,
        runId=a.run_id,
        workItemId=a.work_item_id,
        currentStage=a.current_stage.value if a.current_stage else None,
        progress=a.progress,
        tokenUsage=a.token_usage,
    )


@router.get("", response_model=Envelope[list[AgentOut]])
def list_agents(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    definitions = uow.agent_definitions.read_multi(
        filters={"enabled": True}, page_size=100
    ).results
    active_runs = uow.runs.read_multi(
        filters={"status__in": ["running", "awaiting_gate"]}, page_size=100
    ).results
    return ok([_agent_out(a) for a in build_live_agents(definitions, active_runs)])
```

Register it in `projects/server/src/interactors/api/routes/__init__.py`: add the import
`from interactors.api.routes.agents import router as agents_router` and, inside `register_routers`,
`app.include_router(agents_router)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_agents_api.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full backend suite + lint**

Run:
```bash
cd projects/server && uv run pytest -q
cd /Users/noel/projects/naaf/.worktrees/live-agents && make lint
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/agents.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/interactors/api/test_agents_api.py
git commit -m "feat: GET /agents endpoint serving live role rows"
```

---

### Task 3: UI hook + type + poll + mocks

**Files:**
- Modify: `projects/ui/src/lib/api/hooks/useAgents.ts`
- Create: `projects/ui/src/lib/api/hooks/useAgents.test.tsx`
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`

**Interfaces:**
- Produces: role-oriented `Agent` type `{ role: string; model: string; status: "running" | "idle"; runId: string | null; workItemId: string | null; currentStage: string | null; progress: number | null; tokenUsage: number }`; `AGENTS_POLL_MS = 5000`; `useAgents(pollMs?)` polling the reshaped `/agents`.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/lib/api/hooks/useAgents.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useAgents, AGENTS_POLL_MS } from "./useAgents";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("fetches role-oriented live agents", async () => {
  server.use(
    http.get("/api/agents", () =>
      HttpResponse.json({
        success: true,
        error: null,
        data: [
          { role: "lead", model: "opus", status: "running", runId: "r1",
            workItemId: "wi1", currentStage: "plan", progress: 0.5, tokenUsage: 1200 },
          { role: "backend", model: "sonnet", status: "idle", runId: null,
            workItemId: null, currentStage: null, progress: null, tokenUsage: 0 },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useAgents(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(2));
  expect(result.current.data?.[0].role).toBe("lead");
  expect(result.current.data?.[0].status).toBe("running");
});

test("exposes a poll interval", () => {
  expect(AGENTS_POLL_MS).toBe(5000);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- useAgents`
Expected: FAIL — `AGENTS_POLL_MS` not exported / type mismatch.

- [ ] **Step 3: Write minimal implementation**

Replace `projects/ui/src/lib/api/hooks/useAgents.ts` with:

```ts
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export type Agent = {
  role: string;
  model: string;
  status: "running" | "idle";
  runId: string | null;
  workItemId: string | null;
  currentStage: string | null;
  progress: number | null;
  tokenUsage: number;
};

// The roster lights up as runs advance server-side; poll while mounted so the
// panel stays live. Paused when the tab is hidden (refetchIntervalInBackground
// defaults to false), matching useBoard/BOARD_POLL_MS.
export const AGENTS_POLL_MS = 5000;

export function useAgents(pollMs: number = AGENTS_POLL_MS) {
  return useQuery({
    queryKey: queryKeys.agents(),
    queryFn: () => apiFetch<Agent[]>("/agents"),
    refetchInterval: pollMs,
  });
}
```

Reshape the `agents` seed in `projects/ui/src/lib/api/mocks/fixtures/index.ts`. Import the new type
(`import type { Agent } from "../../hooks/useAgents";`) and replace the old `agents` array with
role-oriented rows (a running lead, an idle backend, an idle qa):

```ts
const agents: Agent[] = [
  {
    role: "lead",
    model: "claude-opus-4-8",
    status: "running",
    runId: "run-1",
    workItemId: "wi-task-3",
    currentStage: "plan",
    progress: 0.33,
    tokenUsage: 12400,
  },
  {
    role: "backend",
    model: "claude-sonnet-4-6",
    status: "idle",
    runId: null,
    workItemId: null,
    currentStage: null,
    progress: null,
    tokenUsage: 0,
  },
  {
    role: "qa",
    model: "claude-haiku-4-5",
    status: "idle",
    runId: null,
    workItemId: null,
    currentStage: null,
    progress: null,
    tokenUsage: 0,
  },
];
```

(If the old `Agent` schema import — `components["schemas"]["Agent"]` — is now unused elsewhere in the
fixtures file, leave the generated `schema.d.ts` untouched; just stop importing that alias for the
agents array.)

In `projects/ui/src/lib/api/mocks/handlers.ts`, **move** the agents handler from `mockOnlyHandlers`
to `liveHandlers`: delete `http.get(\`${BASE}/agents\`, () => ok(seed.agents))` (and its `// ── Agents`
comment) from the `mockOnlyHandlers` array, and add the same line into the `liveHandlers` array (any
position — it is a literal path). The handler body stays `ok(seed.agents)` (now returning the
reshaped rows). This makes live mode pass `/agents` through to the backend while mock mode still
renders the reshaped fixtures.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test -- useAgents`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useAgents.ts projects/ui/src/lib/api/hooks/useAgents.test.tsx projects/ui/src/lib/api/mocks/fixtures/index.ts projects/ui/src/lib/api/mocks/handlers.ts
git commit -m "feat: reshape useAgents to role rows + poll, /agents becomes live-backed"
```

---

### Task 4: RunningAgentsPanel — render role rows

**Files:**
- Modify: `projects/ui/src/modules/dashboard/RunningAgentsPanel.tsx`
- Modify: `projects/ui/src/modules/dashboard/RunningAgentsPanel.test.tsx`

**Interfaces:**
- Consumes: `useAgents`, `Agent` (Task 3).

- [ ] **Step 1: Update the test to the new behavior (write it first, expect fail)**

Replace `projects/ui/src/modules/dashboard/RunningAgentsPanel.test.tsx` with tests for the new
role-row rendering (the panel no longer has Pause/Assign buttons; rows are keyed by role). The MSW
default seed (Task 3) is a running `lead` + idle `backend`/`qa`:

```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { RunningAgentsPanel } from "./RunningAgentsPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RunningAgentsPanel />
    </QueryClientProvider>,
  );
}

describe("RunningAgentsPanel", () => {
  it("shows the panel header", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText(/Running Agents/i)).toBeInTheDocument(),
    );
  });

  it("renders a running role with its work item and an idle role", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("lead")).toBeInTheDocument());
    expect(screen.getByText("wi-task-3")).toBeInTheDocument(); // running lead's work item
    expect(screen.getByText("backend")).toBeInTheDocument();   // idle row
  });

  it("shows the active (running) count in the header", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/1 active/)).toBeInTheDocument());
  });
});
```

Run: `cd projects/ui && pnpm test -- RunningAgentsPanel`
Expected: FAIL — panel still renders old `agent.id`/buttons; `screen.getByText("lead")` not found.

- [ ] **Step 2: Write the implementation**

Replace `projects/ui/src/modules/dashboard/RunningAgentsPanel.tsx` with:

```tsx
import { Card } from "../../components/ui/Card";
import { ProgressBar } from "../../components/ui/ProgressBar";
import { PulseDot } from "../../components/ui/PulseDot";
import { useAgents } from "../../lib/api/hooks/useAgents";
import type { Agent } from "../../lib/api/hooks/useAgents";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function RunningRow({ agent }: { agent: Agent }) {
  return (
    <div className="flex items-center gap-3 px-[15px] py-3">
      <PulseDot />
      <div className="flex-1 min-w-0">
        <div className="text-[11px] font-semibold text-text-2 truncate">{agent.role}</div>
        {agent.currentStage && (
          <div className="text-[10px] text-text-5 truncate">
            {agent.workItemId ?? "—"} · {agent.currentStage}
          </div>
        )}
        {agent.progress != null && (
          <div className="mt-1">
            <ProgressBar value={agent.progress} height={2} />
          </div>
        )}
      </div>
      <span className="font-mono text-[10px] text-text-5 shrink-0">
        {formatTokens(agent.tokenUsage)}
      </span>
    </div>
  );
}

function IdleRow({ agent }: { agent: Agent }) {
  return (
    <div className="flex items-center gap-3 px-[15px] py-3">
      <span
        className="rounded-full border border-[#2e3038] shrink-0"
        style={{ width: 6, height: 6 }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[11px] text-text-5 truncate">{agent.role}</div>
      </div>
      <span className="font-mono text-[10px] text-text-5 shrink-0">{agent.model}</span>
    </div>
  );
}

export function RunningAgentsPanel() {
  const { data: agents, isLoading } = useAgents();

  if (isLoading || !agents) {
    return (
      <div className="bg-bg-surface border border-border rounded-[8px] p-[15px] h-[200px] animate-pulse" />
    );
  }

  const runningAgents = agents.filter((a) => a.status === "running");
  const idleAgents = agents.filter((a) => a.status !== "running");

  return (
    <Card>
      <div className="flex items-center gap-2 px-[15px] pt-[15px] pb-3 border-b border-border">
        <span className="text-[12.5px] font-semibold text-text-2">Running Agents</span>
        <span className="text-[11px] text-[#4a8c68]">{runningAgents.length} active</span>
      </div>
      <div className="divide-y divide-[rgba(255,255,255,0.05)]">
        {runningAgents.map((agent) => (
          <RunningRow key={agent.role} agent={agent} />
        ))}
        {idleAgents.map((agent) => (
          <IdleRow key={agent.role} agent={agent} />
        ))}
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd projects/ui && pnpm test -- RunningAgentsPanel`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add projects/ui/src/modules/dashboard/RunningAgentsPanel.tsx projects/ui/src/modules/dashboard/RunningAgentsPanel.test.tsx
git commit -m "feat: RunningAgentsPanel renders live role rows"
```

---

### Task 5: MetricCards — active-agents count from live data

**Files:**
- Modify: `projects/ui/src/modules/dashboard/MetricCards.tsx`
- Modify: `projects/ui/src/modules/dashboard/MetricCards.test.tsx`

**Interfaces:**
- Consumes: `useAgents` (Task 3), `useDashboard`/`useBudget` (existing).

- [ ] **Step 1: Update the test first (expect fail)**

The "ACTIVE AGENTS" number now comes from `useAgents` (count of running rows), not
`metrics.activeAgents`. With the MSW default seed (one running `lead`), the card should read `1`.
Update `projects/ui/src/modules/dashboard/MetricCards.test.tsx` — keep the existing card tests that
assert TOTAL SPEND / PROJECTS from `metrics`, and change the active-agents assertion to expect the
value derived from `useAgents`. Add/adjust:

```tsx
it("shows the active-agents count from live agents", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MetricCards />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("ACTIVE AGENTS")).toBeInTheDocument());
  // MSW seed has exactly one running role (lead)
  await waitFor(() => expect(screen.getByText(/1 running now/)).toBeInTheDocument());
});
```

(If the existing file asserts a specific `metrics.activeAgents` value for this card, replace that
expectation with the one above. Leave the other card assertions unchanged.)

Run: `cd projects/ui && pnpm test -- MetricCards`
Expected: FAIL — card still shows `metrics.activeAgents`.

- [ ] **Step 2: Write the implementation**

In `projects/ui/src/modules/dashboard/MetricCards.tsx`, import `useAgents` and derive the count;
replace both `metrics.activeAgents` references with `activeCount`:

```tsx
import { useAgents } from "../../lib/api/hooks/useAgents";
...
export function MetricCards() {
  const { data: metrics, isLoading } = useDashboard();
  const { data: budget } = useBudget();
  const { data: agents } = useAgents();
  const activeCount = (agents ?? []).filter((a) => a.status === "running").length;

  if (isLoading || !metrics) {
    return ( /* unchanged loading skeleton */ );
  }

  const spendPct = budget ? Math.min(1, budget.used / budget.limit) : 0;

  return (
    <div className="grid grid-cols-4 gap-3">
      <MetricCard
        label="ACTIVE AGENTS"
        value={activeCount}
        sub={
          <span className="flex items-center gap-[5px] text-[#4a8c68]">
            {activeCount > 0 && (
              <span
                data-testid="active-agents-dot"
                className="inline-block rounded-full bg-[#4a8c68]"
                style={{ width: 6, height: 6 }}
              />
            )}
            {activeCount} running now
          </span>
        }
      />
      {/* TOTAL SPEND / TOTAL TOKENS / PROJECTS cards unchanged */}
    </div>
  );
}
```

(Keep the three other `MetricCard`s exactly as they are, still reading from `metrics`/`budget`.)

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd projects/ui && pnpm test -- MetricCards`
Expected: PASS.

- [ ] **Step 4: Run the full UI suite (catch DashboardScreen fallout)**

Run: `cd projects/ui && pnpm test`
Expected: all pass. If `DashboardScreen.test.tsx` (or any other test) asserted old agent fields
(`agent.id`, Pause/Assign buttons, `type`/`name`), update those assertions to the new role-row shape
in the same commit — the reshaped MSW seed is the single source, so no test should reference the
retired fields.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/dashboard/MetricCards.tsx projects/ui/src/modules/dashboard/MetricCards.test.tsx
git commit -m "feat: ACTIVE AGENTS metric reflects live running-role count"
```

---

### Task 6: Gates, docs, and PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Run all gates**

Run:
```bash
cd /Users/noel/projects/naaf/.worktrees/live-agents
make coverage   # 80% gate
make lint
cd projects/ui && pnpm test && pnpm lint && pnpm build
```
Expected: coverage ≥ 80%, lint clean, UI green + builds. If backend coverage dips, add a targeted
aggregator test (e.g. a run with `current_stage=None` → role resolves to None → no row lights up).

- [ ] **Step 2: Update project history**

Add a dated status entry to `docs/project-history.md` (top of the `## Status (2026-07-04)` section)
summarizing: the dashboard live-agents panel + ACTIVE AGENTS count are now real — a `GET /agents`
endpoint aggregates the enabled AgentDefinition roster with active runs into role rows (lead/backend/
qa light up as runs advance; engineer→backend mapping), polled every 5s; TokenChart/ActivityFeed
stay mocked. Link the spec + this plan.

- [ ] **Step 3: Commit docs**

```bash
git add docs/project-history.md
git commit -m "docs: record live-agents dashboard feature"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/live-agents-dashboard
gh pr create --title "feat: live agents on the dashboard — real running-role panel" --body "$(cat <<'EOF'
## Summary
- New owner-scoped `GET /agents` endpoint: a pure domain aggregator (`build_live_agents`) joins the enabled `AgentDefinition` roster with active runs (`running`/`awaiting_gate`) into one row per role, marking a role running when a run's current stage maps to it (`lead→lead`, `engineer→backend`, `qa→qa`; most-recent run wins on ties).
- Dashboard `RunningAgentsPanel` + the "ACTIVE AGENTS" metric card are now live-backed, polling every 5s (paused when tab hidden). `/agents` moved from MSW mock-only to live-backed; fixtures reshaped so mock mode still renders.
- No new persistence/migration — read-only aggregation. TokenChart, ActivityFeed, and other metric cards stay mocked (out of scope).

Design: `docs/superpowers/specs/2026-07-04-live-agents-dashboard-design.md` · Plan: `docs/superpowers/plans/2026-07-04-live-agents-dashboard.md`

## Test plan
- [ ] `make coverage` ≥ 80% · `make lint` clean
- [ ] `cd projects/ui && pnpm test && pnpm build` green
- [ ] Aggregator: idle-when-no-runs, engineer→backend, lead/qa, awaiting_gate=running, most-recent-wins, progress, fixed order
- [ ] `GET /agents`: envelope, owner-scoping, running vs idle
- [ ] Manual: `make dev`, start a run on a task, watch the matching role flip to running on the dashboard within ~5s
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Concept "live agent = roster role, running/idle" → Tasks 1 (aggregator) + 4 (panel). ✓
- Role mapping (lead/engineer→backend/qa; stage→role fallback) → Task 1 maps, tested. ✓
- `AgentOut` shape → Task 2 contract; consumed as `Agent` in Task 3. ✓
- Backend join endpoint `GET /agents` (enabled roster + active runs, owner-scoped) → Task 2. ✓
- Polling (~5s, hidden-pause) → Task 3 `AGENTS_POLL_MS` + `refetchInterval`. ✓
- Scope: panel (Task 4) + ACTIVE AGENTS count (Task 5); TokenChart/ActivityFeed untouched. ✓
- Fixed role order, concurrent-collapse most-recent, awaiting_gate running, progress passed/6 → Task 1 tests. ✓
- Mocks reshaped + moved to live → Task 3. ✓
- Read-only rows (Pause/Assign dropped) → Task 4. ✓
- No migration/persistence → confirmed (Tasks 1–2 are read-only). ✓

**2. Placeholder scan:** No TBD/TODO/"add validation" left. The one fixture-note ("if the old schema import is unused…") is a concrete instruction, not a placeholder. Test-fixture seeding in Task 2 points at the exact repos/fields to use rather than pasting an unknown conftest verbatim (the conftest shape must be read in-repo) — this is a deliberate, bounded instruction, not a vague deferral.

**3. Type consistency:** `LiveAgent` (snake_case domain) → `AgentOut` (camelCase contract) → UI `Agent` (camelCase) fields line up: `role, model, status, run_id/runId, work_item_id/workItemId, current_stage/currentStage, progress, token_usage/tokenUsage`. `build_live_agents(definitions, active_runs)` signature identical in Tasks 1 and 2. `useAgents`/`AGENTS_POLL_MS`/`Agent` identical across Tasks 3–5. Role strings (`"lead"`,`"backend"`,`"qa"`) consistent between aggregator, route, fixtures, and panel/metric tests.
