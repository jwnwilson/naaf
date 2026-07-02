# Run Monitor Live + Run Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the UI run monitor to the live A3 run API (RunOut/RunEventOut + SSE + gate resolve) and give runs token/cost tracking so the monitor's usage display is real.

**Architecture:** Backend first — accumulate per-stage `tokens` onto `Run.token_usage`, expose `tokenUsage` + derived `cost` on `RunOut`. Then the frontend run monitor adopts `RunOut`/`RunEventOut` as source of truth (hooks, timeline, log stream, header with status/stage/timestamps/usage, gate Approve/Reject), with run mock fixtures reshaped to the live contract behind `VITE_LIVE_API`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic, pytest. React 18, TypeScript strict, @tanstack/react-query v5, MSW v2, vitest, pnpm.

## Global Constraints

- **Immutability:** Pydantic models updated via `model_copy(update={...})`; React state updated immutably.
- **API envelope:** every response is `{success, data, error}` (+ `meta` for pagination). camelCase `*Out` fields ARE the JSON keys.
- **Owner scoping:** every owned row carries `owner_id`; the UnitOfWork applies it as a required filter. Cross-owner reads → 404. (The run endpoints already enforce this — unchanged.)
- **Persistence isolation:** ALL SQLAlchemy access lives ONLY in `adapters/database` repositories.
- **Cost is derived, never stored:** `cost = round(token_usage / 1000 * COST_PER_1K_TOKENS, 4)`; single source of truth is `token_usage`.
- **Placeholder constants (documented):** `TOKENS_PER_STEP = 350` (fake runtime), `COST_PER_1K_TOKENS = 0.003` (flat rate; real per-model pricing is A5).
- **IDs** 32-char hex; timestamps via `iso(...)` / `.isoformat()`.
- **TDD:** failing test first; AAA; descriptive names. `make coverage` (80%) + `make lint` green (backend); `pnpm test` + `pnpm lint` + `tsc --noEmit` green (UI) before PR.
- **Package managers:** backend `uv` (commands from repo root via `make`, or `cd projects/server && uv run …`); UI `pnpm` from `projects/ui` (never npm).
- **Test-harness (UI):** ONE global MSW server (`src/test/setup.ts`, `onUnhandledRequest: "error"`, auto-reset). Register per-test handlers with `server.use(...)` — NEVER a standalone `setupServer`. To assert a value survives an optimistic→invalidate→refetch cycle, use a STATEFUL handler (mutation stores → GET returns it).
- **Out of scope / stays mocked:** the `Agent` entity + `/agents`, the dashboard "Running Agents" panel, the board "Live Agents" ribbon, real per-model pricing, starting a run from the UI.

---

## File Structure

**Backend (`projects/server/src`):**
- Modify `domain/agent/runtime.py` — `StageResult.tokens`.
- Modify `adapters/agent/runtime/fake.py` — deterministic per-stage tokens.
- Modify `domain/runs/run.py` — `Run.token_usage`.
- Modify `adapters/database/orm.py` — `RunRow.token_usage` column.
- Create `adapters/database/migrations/versions/0008_run_token_usage.py`.
- Modify `interactors/worker/handlers.py` — accumulate tokens in `_run_stage_inline` + STAGE_PASSED payload.
- Modify `interactors/api/contract.py` — `RunOut.tokenUsage` + `cost`.
- Modify `interactors/api/routes/runs.py` — `COST_PER_1K_TOKENS` + `_run_out` mapping.
- Tests: `tests/adapters/agent/test_fake_runtime.py`, `tests/adapters/database/test_run_repository.py`, `tests/adapters/test_migrations.py`, `tests/interactors/worker/test_pipeline_integration.py`, `tests/api/test_runs_api.py`.

**Frontend (`projects/ui/src`):**
- Modify `lib/api/schema.d.ts` — add `RunOut`/`RunEventOut`/`StageStateOut`/`GateOut`; (Task 9) retire `AgentRun`/`RunStep`/`LogLine`.
- Modify `lib/api/queryKeys.ts` — `runEvents`.
- Modify `lib/api/hooks/useWorkItemRun.ts`, `lib/api/hooks/useRun.ts`; Create `lib/api/hooks/useResolveGate.ts`; Modify `lib/api/hooks/index.ts`.
- Modify `modules/detail/StepTimeline.tsx`, `modules/detail/LogStream.tsx`, `modules/detail/AgentMonitor.tsx` (+ co-located tests).
- Modify `lib/api/mocks/handlers.ts`, `lib/api/mocks/db.ts`, `lib/api/mocks/fixtures/index.ts`, `lib/api/mocks/handlers.test.ts`.

---

## Task 1: Per-stage token output in the runtime

**Files:**
- Modify: `projects/server/src/domain/agent/runtime.py`
- Modify: `projects/server/src/adapters/agent/runtime/fake.py`
- Test: `projects/server/tests/adapters/agent/test_fake_runtime.py`

**Interfaces:**
- Produces: `StageResult` gains `tokens: int = 0`; `FakeAgentRuntime.run_stage(...)` returns `StageResult` with `tokens = TOKENS_PER_STEP * len(outcome.events)` (`TOKENS_PER_STEP = 350`, module constant in `fake.py`).

- [ ] **Step 1: Write the failing test**

```python
# add to projects/server/tests/adapters/agent/test_fake_runtime.py
from adapters.agent.runtime.fake import TOKENS_PER_STEP, FakeAgentRuntime
from domain.runs.run import Stage


def test_run_stage_reports_tokens_proportional_to_steps():
    rt = FakeAgentRuntime()
    outcome = rt.run_stage("lead", Stage.PLAN, {})
    assert outcome.result.tokens == TOKENS_PER_STEP * len(outcome.events)
    assert outcome.result.tokens > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_fake_runtime.py::test_run_stage_reports_tokens_proportional_to_steps -v`
Expected: FAIL — `ImportError: cannot import name 'TOKENS_PER_STEP'` (and `StageResult` has no `tokens`).

- [ ] **Step 3: Add `tokens` to `StageResult`**

In `projects/server/src/domain/agent/runtime.py`, extend `StageResult`:

```python
class StageResult(BaseModel):
    passed: bool
    summary: str = ""
    tokens: int = 0
```

- [ ] **Step 4: Emit deterministic tokens from the fake runtime**

In `projects/server/src/adapters/agent/runtime/fake.py`, add the constant near the top (after imports) and set `tokens` in the returned result:

```python
TOKENS_PER_STEP = 350  # deterministic placeholder; real token counts arrive with the A5 runtime
```

In `run_stage`, change the return to:

```python
        tokens = TOKENS_PER_STEP * len(events)
        return StageOutcome(events=events, result=StageResult(passed=passed, summary=summary, tokens=tokens))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_fake_runtime.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/domain/agent/runtime.py projects/server/src/adapters/agent/runtime/fake.py projects/server/tests/adapters/agent/test_fake_runtime.py
git commit -m "feat: per-stage token output in agent runtime"
```

---

## Task 2: `Run.token_usage` field + persistence

**Files:**
- Modify: `projects/server/src/domain/runs/run.py`
- Modify: `projects/server/src/adapters/database/orm.py` (`RunRow`, ~line 66-81)
- Create: `projects/server/src/adapters/database/migrations/versions/0008_run_token_usage.py`
- Test: `projects/server/tests/adapters/database/test_run_repository.py`, `projects/server/tests/adapters/test_migrations.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Run.token_usage: int = 0`; `RunRow.token_usage` column (`Integer`, default 0); migration `0008_run_token_usage` (`down_revision = "0007_messages"`). Run round-trips `token_usage` through the repository.

> The domain field and the ORM column MUST land together: `SqlRepository.create` inserts every non-None field, so a `Run.token_usage` without a `RunRow` column breaks run creation.

- [ ] **Step 1: Write the failing tests**

```python
# add to projects/server/tests/adapters/database/test_run_repository.py
def test_run_persists_token_usage(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.run import Run
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id="w1", project_id="p1", autonomy_level="full_auto",
                token_usage=1750)
        )
        got = uow.runs.read(run.id)
    assert got.token_usage == 1750
```

```python
# add to projects/server/tests/adapters/test_migrations.py
def test_migration_adds_run_token_usage(tmp_path):
    import os, sqlite3, subprocess
    from pathlib import Path
    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    r = subprocess.run(["uv", "run", "alembic", "upgrade", "head"],
                       cwd=server, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    cols = {row[1] for row in con.execute("PRAGMA table_info(runs)")}
    assert "token_usage" in cols
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_run_repository.py::test_run_persists_token_usage tests/adapters/test_migrations.py::test_migration_adds_run_token_usage -v`
Expected: FAIL — `Run` has no `token_usage` (validation/attr error) and `runs.token_usage` column missing.

- [ ] **Step 3: Add the domain field**

In `projects/server/src/domain/runs/run.py`, add to `Run` (after `max_verify_loops`):

```python
    token_usage: int = 0
```

- [ ] **Step 4: Add the ORM column**

In `projects/server/src/adapters/database/orm.py`, add to `RunRow` (after `max_verify_loops`, before `started_at`):

```python
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

- [ ] **Step 5: Add the migration**

```python
# projects/server/src/adapters/database/migrations/versions/0008_run_token_usage.py
"""run token_usage

Revision ID: 0008_run_token_usage
Revises: 0007_messages
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_run_token_usage"
down_revision = "0007_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("runs", "token_usage")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_run_repository.py tests/adapters/test_migrations.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add projects/server/src/domain/runs/run.py projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/migrations/versions/0008_run_token_usage.py projects/server/tests/adapters/database/test_run_repository.py projects/server/tests/adapters/test_migrations.py
git commit -m "feat: track token_usage on runs"
```

---

## Task 3: Accumulate stage tokens onto the run

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` (`_run_stage_inline`, ~line 62-79)
- Test: `projects/server/tests/interactors/worker/test_pipeline_integration.py`

**Interfaces:**
- Consumes: `StageResult.tokens` (Task 1), `Run.token_usage` (Task 2).
- Produces: after each real (non-stub) stage, `run.token_usage += outcome.result.tokens`; the `STAGE_PASSED` event payload gains `"tokens"`. Invariant: a finished run's `token_usage` equals the sum of `tokens` across its `stage_passed` events.

- [ ] **Step 1: Write the failing test**

```python
# add to projects/server/tests/interactors/worker/test_pipeline_integration.py
def test_run_accumulates_token_usage_from_stages(session_factory):
    rt = FakeAgentRuntime()
    _wi_id, run_id = _seed(session_factory, "full_auto")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, events = _read_run(session_factory, run_id)
    passed_tokens = sum(e.payload.get("tokens", 0) for e in events if e.type.value == "stage_passed")
    assert run.token_usage > 0
    assert run.token_usage == passed_tokens
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_pipeline_integration.py::test_run_accumulates_token_usage_from_stages -v`
Expected: FAIL — `run.token_usage` is 0 (no accumulation) and `stage_passed` payloads have no `tokens`.

- [ ] **Step 3: Accumulate + emit tokens in `_run_stage_inline`**

In `projects/server/src/interactors/worker/handlers.py`, in `_run_stage_inline`, replace the tail (from the `final_status` line to the `return`) with:

```python
    final_status = StageStatus.PASSED if outcome.result.passed else StageStatus.FAILED
    updated_entry = run.stages[-1].model_copy(update={"status": final_status, "ended_at": utcnow()})
    run = _save(ctx, run.model_copy(update={
        "stages": [*run.stages[:-1], updated_entry],
        "token_usage": run.token_usage + outcome.result.tokens,
    }))
    event_type = EventType.STAGE_PASSED if outcome.result.passed else EventType.STAGE_FAILED
    emit(ctx, run, event_type, stage=stage, role=role,
         payload={"summary": outcome.result.summary, "tokens": outcome.result.tokens})
    return outcome.result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_pipeline_integration.py -v`
Expected: PASS (existing pipeline tests still pass).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/tests/interactors/worker/test_pipeline_integration.py
git commit -m "feat: accumulate stage tokens onto the run"
```

---

## Task 4: Expose `tokenUsage` + derived `cost` on `RunOut`

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py` (`RunOut`)
- Modify: `projects/server/src/interactors/api/routes/runs.py` (`COST_PER_1K_TOKENS`, `_run_out`)
- Test: `projects/server/tests/api/test_runs_api.py`

**Interfaces:**
- Consumes: `Run.token_usage` (Task 2).
- Produces: `RunOut` gains `tokenUsage: int` and `cost: float`; `COST_PER_1K_TOKENS = 0.003` in `routes/runs.py`; `_run_out` sets `tokenUsage=run.token_usage`, `cost=round(run.token_usage / 1000 * COST_PER_1K_TOKENS, 4)`.

- [ ] **Step 1: Write the failing test**

```python
# add to projects/server/tests/api/test_runs_api.py
def test_run_out_exposes_token_usage_and_cost(client, session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.run import Run
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id="w1", project_id="p1", autonomy_level="full_auto",
                token_usage=2000)
        )
    body = client.get(f"/runs/{run.id}").json()["data"]
    assert body["tokenUsage"] == 2000
    assert body["cost"] == 0.006  # 2000/1000 * 0.003
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_runs_api.py::test_run_out_exposes_token_usage_and_cost -v`
Expected: FAIL — response has no `tokenUsage`/`cost`.

- [ ] **Step 3: Add the contract fields**

In `projects/server/src/interactors/api/contract.py`, add to `RunOut` (after `endedAt`):

```python
    tokenUsage: int
    cost: float
```

- [ ] **Step 4: Populate them in the mapper**

In `projects/server/src/interactors/api/routes/runs.py`, add the constant near the top (after imports):

```python
COST_PER_1K_TOKENS = 0.003  # flat placeholder; real per-model pricing is A5
```

In `_run_out`, add these two arguments to the `RunOut(...)` construction (after `endedAt=...`):

```python
        tokenUsage=run.token_usage,
        cost=round(run.token_usage / 1000 * COST_PER_1K_TOKENS, 4),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/api/test_runs_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/runs.py projects/server/tests/api/test_runs_api.py
git commit -m "feat: expose tokenUsage + derived cost on RunOut"
```

- [ ] **Step 7: Backend gate**

Run: `cd /Users/noel/projects/naaf/.worktrees/run-monitor-live && make coverage && make lint`
Expected: coverage ≥80%, ruff + mypy clean. Fix any fallout before the frontend tasks.

---

## Task 5: Add live run types to the UI schema

**Files:**
- Modify: `projects/ui/src/lib/api/schema.d.ts`

Purely additive — add the live types the hooks/components will consume. The mock `AgentRun`/`RunStep`/`LogLine` stay defined until Task 9 (so the mock layer keeps compiling during Tasks 6–8).

**Interfaces:**
- Produces, under `components["schemas"]`:

```ts
        StageStateOut: {
            stage: string;
            status: string;
            role?: string | null;
            startedAt?: string | null;
            endedAt?: string | null;
        };
        GateOut: {
            kind: string;
            stage: string;
        };
        RunOut: {
            id: string;
            workItemId: string;
            projectId: string;
            autonomyLevel: string;
            status: string;
            currentStage?: string | null;
            stages: components["schemas"]["StageStateOut"][];
            pendingGate?: components["schemas"]["GateOut"] | null;
            createdAt: string;
            updatedAt: string;
            startedAt?: string | null;
            endedAt?: string | null;
            tokenUsage: number;
            cost: number;
        };
        RunEventOut: {
            id: string;
            runId: string;
            seq: number;
            stage?: string | null;
            role?: string | null;
            type: string;
            payload: Record<string, unknown>;
            createdAt: string;
        };
```

- [ ] **Step 1: Add the four schema blocks**

Insert the `StageStateOut`, `GateOut`, `RunOut`, `RunEventOut` blocks above (verbatim) into the `components["schemas"]` object in `projects/ui/src/lib/api/schema.d.ts` (e.g. next to the existing `AgentRun` block).

- [ ] **Step 2: Verify typecheck is still clean**

Run: `cd projects/ui && pnpm exec tsc --noEmit`
Expected: no NEW errors (additive change; existing code untouched).

- [ ] **Step 3: Commit**

```bash
git add projects/ui/src/lib/api/schema.d.ts
git commit -m "feat: add live RunOut/RunEventOut types to ui schema"
```

---

## Task 6: Run hooks (fetch + events + SSE + gate)

**Files:**
- Modify: `projects/ui/src/lib/api/queryKeys.ts`
- Modify: `projects/ui/src/lib/api/hooks/useWorkItemRun.ts`
- Modify: `projects/ui/src/lib/api/hooks/useRun.ts`
- Create: `projects/ui/src/lib/api/hooks/useResolveGate.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts`
- Test: `projects/ui/src/lib/api/hooks/useRun.test.tsx` (extend), `projects/ui/src/lib/api/hooks/useResolveGate.test.tsx` (new)

**Interfaces:**
- Consumes: `RunOut`, `RunEventOut` (Task 5); `apiFetch`, `apiList`, `apiPost`; `useEventSource`.
- Produces:
  - `queryKeys.runEvents(runId)` → `["run", runId, "events"]`.
  - `useWorkItemRun(itemId)` → `UseQueryResult<RunOut | null>` via `GET /runs?work_item={itemId}` (returns `results[0] ?? null`).
  - `useRun(runId)` → `{ run: RunOut | undefined, events: RunEventOut[], isStreaming: boolean }` — `GET /runs/{id}` + `GET /runs/{id}/events` history + SSE `/api/runs/{id}/events/stream?after={lastSeq}`.
  - `useResolveGate(runId)` → `UseMutationResult` posting `{decision: "approve"|"reject"}` to `/runs/{id}/gate`, invalidating `queryKeys.run(runId)` + `queryKeys.runEvents(runId)`.

- [ ] **Step 1: Write the failing tests**

```tsx
// projects/ui/src/lib/api/hooks/useResolveGate.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useResolveGate } from "./useResolveGate";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a gate decision and resolves", async () => {
  server.use(
    http.post("/api/runs/r1/gate", async ({ request }) => {
      const body = (await request.json()) as { decision: string };
      return HttpResponse.json({ success: true, error: null, data: { id: "r1", decision: body.decision } });
    }),
  );
  const { result } = renderHook(() => useResolveGate("r1"), { wrapper });
  await act(async () => { await result.current.mutateAsync({ decision: "approve" }); });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
});
```

Add to `projects/ui/src/lib/api/hooks/useRun.test.tsx` a test that `useRun` merges history from `/runs/:id/events`:

```tsx
test("useRun returns the run and its event history", async () => {
  server.use(
    http.get("/api/runs/r1", () => HttpResponse.json({ success: true, error: null,
      data: { id: "r1", workItemId: "w1", projectId: "p1", autonomyLevel: "full_auto",
        status: "running", currentStage: "plan", stages: [], pendingGate: null,
        createdAt: "2026-07-02T00:00:00Z", updatedAt: "2026-07-02T00:00:00Z",
        startedAt: null, endedAt: null, tokenUsage: 700, cost: 0.0021 } })),
    http.get("/api/runs/r1/events", () => HttpResponse.json({ success: true, error: null,
      data: [{ id: "e1", runId: "r1", seq: 1, stage: "plan", role: "lead", type: "log",
        payload: { message: "hi" }, createdAt: "2026-07-02T00:00:00Z" }] })),
  );
  const { result } = renderHook(() => useRun("r1"), { wrapper });
  await waitFor(() => expect(result.current.run?.tokenUsage).toBe(700));
  await waitFor(() => expect(result.current.events).toHaveLength(1));
});
```

(Use the existing wrapper/imports already in `useRun.test.tsx`; import `server` from `../mocks/server` and `http, HttpResponse` from `msw`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useResolveGate.test.tsx src/lib/api/hooks/useRun.test.tsx`
Expected: FAIL — `useResolveGate` missing; `useRun` returns old `{run, logLines, isStreaming}` shape (no `events`).

- [ ] **Step 3: Add the query key**

In `projects/ui/src/lib/api/queryKeys.ts`, add inside the object:

```ts
  runEvents: (runId: string) => ["run", runId, "events"] as const,
```

- [ ] **Step 4: Rewrite `useWorkItemRun.ts`**

```ts
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];

export function useWorkItemRun(itemId: string) {
  return useQuery({
    queryKey: ["work-item-run", itemId],
    queryFn: async (): Promise<RunOut | null> => {
      const { results } = await apiList<RunOut>("/runs", { work_item: itemId });
      return results[0] ?? null;
    },
    enabled: Boolean(itemId),
  });
}
```

- [ ] **Step 5: Rewrite `useRun.ts`**

```ts
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiList } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];
export type RunEventOut = components["schemas"]["RunEventOut"];

export function useRun(runId: string): {
  run: RunOut | undefined;
  events: RunEventOut[];
  isStreaming: boolean;
} {
  const runQuery = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => apiFetch<RunOut>(`/runs/${runId}`),
  });
  const historyQuery = useQuery({
    queryKey: queryKeys.runEvents(runId),
    queryFn: () => apiList<RunEventOut>(`/runs/${runId}/events`),
    select: (page) => page.results,
  });

  const history = historyQuery.data ?? [];
  const [streamed, setStreamed] = useState<RunEventOut[]>([]);
  const lastSeq = history.length ? history[history.length - 1].seq : 0;

  useEventSource<RunEventOut>(
    runQuery.data ? `/api/runs/${runId}/events/stream?after=${lastSeq}` : null,
    (ev) => setStreamed((prev) => [...prev, ev]),
  );

  const events = [...history, ...streamed];
  return {
    run: runQuery.data,
    events,
    isStreaming: !!runQuery.data && runQuery.data.status === "running",
  };
}
```

- [ ] **Step 6: Create `useResolveGate.ts`**

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";

type GateDecision = { decision: "approve" | "reject" };

export function useResolveGate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: GateDecision) => apiPost(`/runs/${runId}/gate`, vars),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void qc.invalidateQueries({ queryKey: queryKeys.runEvents(runId) });
    },
  });
}
```

- [ ] **Step 7: Export from `hooks/index.ts`**

Add:

```ts
export { useResolveGate } from "./useResolveGate";
export type { RunOut, RunEventOut } from "./useRun";
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/`
Expected: PASS, pristine output.

- [ ] **Step 9: Commit**

```bash
git add projects/ui/src/lib/api/queryKeys.ts projects/ui/src/lib/api/hooks/
git commit -m "feat: run hooks consume RunOut/RunEventOut + gate resolve"
```

---

## Task 7: `StepTimeline` + `LogStream` render live shapes

**Files:**
- Modify: `projects/ui/src/modules/detail/StepTimeline.tsx`
- Modify: `projects/ui/src/modules/detail/LogStream.tsx`
- Test: co-located `StepTimeline.test.tsx` (new/extend), `LogStream.test.tsx` (new/extend)

**Interfaces:**
- Consumes: `StageStateOut`, `RunEventOut` (Task 5).
- Produces: `StepTimeline({ stages }: { stages: StageStateOut[] })`; `LogStream({ events }: { events: RunEventOut[] })`.

- [ ] **Step 1: Write the failing tests**

```tsx
// projects/ui/src/modules/detail/StepTimeline.test.tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { StepTimeline } from "./StepTimeline";

test("renders one node per stage with its label", () => {
  render(<StepTimeline stages={[
    { stage: "plan", status: "passed", role: "lead", startedAt: null, endedAt: null },
    { stage: "implement", status: "running", role: "backend", startedAt: null, endedAt: null },
  ]} />);
  expect(screen.getByText("plan")).toBeInTheDocument();
  expect(screen.getByText("implement")).toBeInTheDocument();
});
```

```tsx
// projects/ui/src/modules/detail/LogStream.test.tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { LogStream } from "./LogStream";

test("renders a log event and a stage_passed token line", () => {
  render(<LogStream events={[
    { id: "e1", runId: "r1", seq: 1, stage: "plan", role: "lead", type: "log",
      payload: { message: "Reading ticket" }, createdAt: "2026-07-02T00:00:00Z" },
    { id: "e2", runId: "r1", seq: 2, stage: "plan", role: "lead", type: "stage_passed",
      payload: { summary: "ok", tokens: 1050 }, createdAt: "2026-07-02T00:00:01Z" },
  ]} />);
  expect(screen.getByText(/Reading ticket/)).toBeInTheDocument();
  expect(screen.getByText(/1050 tok/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm exec vitest run src/modules/detail/StepTimeline.test.tsx src/modules/detail/LogStream.test.tsx`
Expected: FAIL — components expect the old `steps`/`lines` props.

- [ ] **Step 3: Rewrite `StepTimeline.tsx`**

Replace the file with a `StageStateOut`-driven version (circle state mapped from `status`):

```tsx
import { Fragment } from "react";
import type { components } from "../../lib/api/schema";

type StageStateOut = components["schemas"]["StageStateOut"];

type Circle = "done" | "active" | "failed" | "pending";
function circle(status: string): Circle {
  if (status === "passed") return "done";
  if (status === "running" || status === "gated") return "active";
  if (status === "failed") return "failed";
  return "pending"; // pending, skipped
}

const CHECK_ICON = (
  <svg width="9" height="9" viewBox="0 0 9 9" fill="none" aria-hidden="true">
    <path d="M1.5 4.5l2 2L7.5 2" stroke="currentColor" strokeWidth="1.4"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function StageCircle({ state, index }: { state: Circle; index: number }) {
  if (state === "done") {
    return (
      <div className="flex items-center justify-center text-[#8a8d96]"
        style={{ width: 20, height: 20, borderRadius: "50%", background: "#1e2028", border: "1.5px solid #36393f" }}>
        {CHECK_ICON}
      </div>
    );
  }
  if (state === "active") {
    return (
      <div className="flex items-center justify-center font-mono text-[#bab7f6] animate-[pulse_2s_infinite]"
        style={{ width: 22, height: 22, borderRadius: "50%", background: "rgba(124,108,240,0.15)", border: "2px solid #7c6cf0", fontSize: 8 }}>
        {index + 1}
      </div>
    );
  }
  if (state === "failed") {
    return (
      <div className="flex items-center justify-center font-mono text-[#f0a0a0]"
        style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(240,120,120,0.12)", border: "1.5px solid #7a3a3a", fontSize: 9 }}>
        ✕
      </div>
    );
  }
  return <div style={{ width: 20, height: 20, borderRadius: "50%", background: "#0f1012", border: "1.5px solid #1a1c22" }} />;
}

export function StepTimeline({ stages }: { stages: StageStateOut[] }) {
  return (
    <div className="flex items-start px-5 py-3.5">
      {stages.map((s, idx) => {
        const state = circle(s.status);
        const prevDone = idx > 0 && circle(stages[idx - 1].status) === "done";
        return (
          <Fragment key={`${s.stage}-${idx}`}>
            {idx > 0 && (
              <div className="flex-1" style={{ height: 1.5, marginTop: 10, background: prevDone ? "#7c6cf0" : "#1e2028" }} />
            )}
            <div className="flex flex-col items-center" style={{ gap: 4 }}>
              <StageCircle state={state} index={idx} />
              <span className="font-mono" style={{ fontSize: 8.5, color: state === "active" ? "#bab7f6" : "#2e3038" }}>
                {s.stage}
              </span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Rewrite `LogStream.tsx`**

Replace the `LogLine` rendering with a `RunEventOut`-driven version:

```tsx
import type { components } from "../../lib/api/schema";

type RunEventOut = components["schemas"]["RunEventOut"];

function formatTimestamp(ts: string): string {
  try { return new Date(ts).toISOString().slice(11, 19); } catch { return ts; }
}

function lineFor(ev: RunEventOut): string {
  const p = ev.payload as Record<string, unknown>;
  switch (ev.type) {
    case "log": return String(p.message ?? "");
    case "stage_started": return `▶ ${ev.stage} started`;
    case "stage_passed": return `✓ ${ev.stage} (${Number(p.tokens ?? 0)} tok)`;
    case "stage_failed": return `✕ ${ev.stage} failed`;
    case "gate_requested": return `⏸ gate: ${String(p.kind ?? "")}`;
    case "gate_resolved": return `▶ gate ${String(p.decision ?? "")}`;
    case "run_started": return "▶ run started";
    case "run_finished": return `■ run ${String(p.status ?? "finished")}`;
    default: return ev.type;
  }
}

function LogEntry({ ev }: { ev: RunEventOut }) {
  return (
    <div className="flex gap-2 items-baseline">
      <span className="flex-shrink-0" style={{ color: "#28292e" }}>{formatTimestamp(ev.createdAt)}</span>
      {ev.stage && <span style={{ color: "#6b6e76" }}>{ev.stage}</span>}
      <span style={{ color: "#42454e" }}>{lineFor(ev)}</span>
    </div>
  );
}

export function LogStream({ events }: { events: RunEventOut[] }) {
  return (
    <div className="flex flex-col gap-1 px-5 py-3 font-mono text-[10.5px] overflow-y-auto">
      {events.map((ev) => <LogEntry key={ev.id} ev={ev} />)}
    </div>
  );
}
```

> If the existing `LogStream.tsx` has extra layout/props consumed by `AgentMonitor`, preserve the outer container styling; only the per-line shape changes. Task 8 passes `events` to it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/modules/detail/StepTimeline.test.tsx src/modules/detail/LogStream.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/modules/detail/StepTimeline.tsx projects/ui/src/modules/detail/LogStream.tsx projects/ui/src/modules/detail/StepTimeline.test.tsx projects/ui/src/modules/detail/LogStream.test.tsx
git commit -m "feat: timeline + log stream render live run shapes"
```

---

## Task 8: `AgentMonitor` renders a live run + gate controls

**Files:**
- Modify: `projects/ui/src/modules/detail/AgentMonitor.tsx`
- Test: `projects/ui/src/modules/detail/AgentMonitor.test.tsx`

**Interfaces:**
- Consumes: `useRun`, `useResolveGate` (Task 6); `StepTimeline`, `LogStream` (Task 7); `RunOut` (Task 5).
- Produces: `AgentMonitor({ runId })` renders the run header (agent = current stage `role` or `"lead"`; status; current stage; started timestamp; token/cost), the stage timeline, the event log, and — when `run.pendingGate` is set — Approve/Reject buttons wired to `useResolveGate`.

- [ ] **Step 1: Write the failing test**

```tsx
// projects/ui/src/modules/detail/AgentMonitor.test.tsx  (replace mock-era test)
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { AgentMonitor } from "./AgentMonitor";

function renderMonitor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><AgentMonitor runId="r1" /></QueryClientProvider>);
}

const RUN = {
  id: "r1", workItemId: "w1", projectId: "p1", autonomyLevel: "gated_all",
  status: "awaiting_gate", currentStage: "plan",
  stages: [{ stage: "plan", status: "gated", role: "lead", startedAt: "2026-07-02T00:00:00Z", endedAt: null }],
  pendingGate: { kind: "plan", stage: "plan" },
  createdAt: "2026-07-02T00:00:00Z", updatedAt: "2026-07-02T00:00:00Z",
  startedAt: "2026-07-02T00:00:00Z", endedAt: null, tokenUsage: 1050, cost: 0.0032,
};

test("renders status + token usage and resolves a pending gate", async () => {
  const gate = vi.fn();
  server.use(
    http.get("/api/runs/r1", () => HttpResponse.json({ success: true, error: null, data: RUN })),
    http.get("/api/runs/r1/events", () => HttpResponse.json({ success: true, error: null, data: [] })),
    http.post("/api/runs/r1/gate", async ({ request }) => {
      gate((await request.json() as { decision: string }).decision);
      return HttpResponse.json({ success: true, error: null, data: RUN });
    }),
  );
  renderMonitor();
  expect(await screen.findByText(/awaiting_gate/)).toBeInTheDocument();
  expect(screen.getByText(/1050|1\.0k|1\.1k/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /approve/i }));
  expect(gate).toHaveBeenCalledWith("approve");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/modules/detail/AgentMonitor.test.tsx`
Expected: FAIL — current `AgentMonitor` uses `useAgents` + `AgentRun` fields (`run.agentId`, `run.tokenUsage` via mock), no gate buttons.

- [ ] **Step 3: Rewrite `AgentMonitor.tsx`**

```tsx
import { Avatar, ProgressBar, PulseDot, StatusBadge } from "../../components/ui";
import { useRun, useResolveGate } from "../../lib/api/hooks";
import { LogStream } from "./LogStream";
import { StepTimeline } from "./StepTimeline";

function formatTokens(n: number): string {
  return n >= 1_000 ? `${(n / 1_000).toFixed(1)}k` : String(n);
}

function roleInitials(role: string): string {
  return role.slice(0, 2).toUpperCase();
}

export function AgentMonitor({ runId }: { runId: string }) {
  const { run, events, isStreaming } = useRun(runId);
  const gate = useResolveGate(runId);

  if (!run) {
    return (
      <div className="flex items-center justify-center p-8 font-mono text-[11px] text-[#42454e]">
        Loading…
      </div>
    );
  }

  const currentStage = run.stages.find((s) => s.stage === run.currentStage);
  const role = currentStage?.role ?? "lead";
  const startedAt = run.startedAt ? new Date(run.startedAt).toISOString().slice(0, 19).replace("T", " ") : "—";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
        <Avatar initials={roleInitials(role)} variant="agent" size={22} />
        <div className="flex flex-col" style={{ gap: 2 }}>
          <span className="text-[11px] font-semibold text-text-1">{role}</span>
          <span className="font-mono text-[9.5px]" style={{ color: "#42454e" }}>
            {run.status}{run.currentStage ? ` · ${run.currentStage}` : ""} · {startedAt}
          </span>
        </div>
        <div className="flex items-center gap-1.5 ml-2">
          {isStreaming && <PulseDot size={6} />}
          <StatusBadge kind={isStreaming ? "running" : "idle"} />
        </div>
        <div className="flex flex-col items-end ml-auto" style={{ gap: 2 }}>
          <span className="font-mono text-[10px] text-text-1">{formatTokens(run.tokenUsage)} tok</span>
          <span className="font-mono text-[9px]" style={{ color: "#42454e" }}>${run.cost.toFixed(4)}</span>
        </div>
      </div>

      {/* Pending gate */}
      {run.pendingGate && (
        <div className="flex items-center gap-2 px-5 py-2 flex-shrink-0"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.07)", background: "rgba(124,108,240,0.06)" }}>
          <span className="font-mono text-[10px] text-[#bab7f6]">
            gate: {run.pendingGate.kind} ({run.pendingGate.stage})
          </span>
          <div className="flex gap-2 ml-auto">
            <button aria-label="approve" disabled={gate.isPending}
              onClick={() => gate.mutate({ decision: "approve" })}
              className="rounded-[5px] px-2 py-1 text-[10px] text-accent disabled:opacity-40"
              style={{ background: "rgba(124,108,240,0.18)" }}>
              Approve
            </button>
            <button aria-label="reject" disabled={gate.isPending}
              onClick={() => gate.mutate({ decision: "reject" })}
              className="rounded-[5px] px-2 py-1 text-[10px] text-[#c4c5cb] disabled:opacity-40"
              style={{ border: "1px solid rgba(255,255,255,0.12)" }}>
              Reject
            </button>
          </div>
        </div>
      )}

      <StepTimeline stages={run.stages} />
      <div className="flex-1 overflow-y-auto">
        <LogStream events={events} />
      </div>
    </div>
  );
}
```

> If `ProgressBar` becomes unused after this rewrite, drop it from the import to keep lint clean.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/modules/detail/AgentMonitor.test.tsx`
Expected: PASS, pristine.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/detail/AgentMonitor.tsx projects/ui/src/modules/detail/AgentMonitor.test.tsx
git commit -m "feat: AgentMonitor renders live run + gate controls"
```

---

## Task 9: Reshape run mocks to the live contract; retire the dead run mock surface

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts`
- Modify: `projects/ui/src/lib/api/mocks/db.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.test.ts`
- Modify: `projects/ui/src/lib/api/schema.d.ts` (retire mock shapes)
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts`

**Interfaces:**
- Produces: the mock `/runs`, `/runs/:id`, `/runs/:id/events`, `/runs/:id/events/stream`, `/runs/:id/gate` handlers return `RunOut`/`RunEventOut` shapes and live in `liveHandlers` (bypass under `VITE_LIVE_API`). Retired: `/work-items/:id/run`, `/runs/:id/stream`, and the `AgentRun`/`RunStep`/`LogLine` schema + fixtures.

- [ ] **Step 1: Reshape run fixtures**

In `projects/ui/src/lib/api/mocks/fixtures/index.ts`, replace the `agentRuns`/run-step/log-line fixtures with `RunOut`-shaped runs and a `runEvents` list of `RunEventOut`. Provide at least one run with `stages`, a `pendingGate: null` run and one `awaiting_gate` run with a `pendingGate`, `tokenUsage`/`cost` set, and a handful of `runEvents` (`log`, `stage_passed` with `tokens`). Keep the `Agent` fixtures (still used by the mocked panels). Export `runs` and `runEvents`.

- [ ] **Step 2: Update `db.ts`**

Replace `agentRuns`/`findRun` internals to hold `RunOut[]` (`runs`) and expose `runsForWorkItem(workItemId)` (filter by `workItemId`, newest first) and `eventsForRun(runId)`. Remove `logs`/`buildRunStream` remnants tied to `LogLine`. Keep the `Agent`/dashboard/board mock data intact.

- [ ] **Step 3: Move + reshape the run handlers in `handlers.ts`**

Remove `/work-items/:id/run` and `/runs/:id/stream`. Add/move into `liveHandlers`:
- `GET /runs` (honour `?work_item=` filter) → `ok(db.runs…, meta)`.
- `GET /runs/:id` → `ok(run)` or `notFound()`.
- `GET /runs/:id/events` → `ok(db.eventsForRun(id))`.
- `GET /runs/:id/events/stream` → an SSE `text/event-stream` response emitting the run's `RunEventOut` frames (reuse the existing stream helper, reshaped to `RunEventOut`).
- `POST /runs/:id/gate` → `ok(run)`.
Remove the now-unused `AgentRun`/`RunStep`/`LogLine` imports.

- [ ] **Step 4: Retire the mock shapes in `schema.d.ts`**

Delete the `AgentRun`, `RunStep`, and `LogLine` schema blocks. (`Agent` stays.)

- [ ] **Step 5: Update `handlers.test.ts`**

Assert `/runs` is a live handler (honours `VITE_LIVE_API`) and that `/work-items/:id/run` and `/runs/:id/stream` no longer appear. Follow the file's existing introspection approach.

```ts
test("/runs is a live handler and legacy run paths are gone", () => {
  expect(liveHandlers.some((h) => String(h.info.path).endsWith("/runs"))).toBe(true);
  const all = [...liveHandlers, ...mockOnlyHandlers].map((h) => String(h.info.path));
  expect(all.some((p) => p.includes("/work-items/:id/run"))).toBe(false);
  expect(all.some((p) => p.endsWith("/runs/:id/stream"))).toBe(false);
});
```

- [ ] **Step 6: Verify grep + typecheck + suite**

Run: `cd projects/ui && grep -rn "AgentRun\|RunStep\|LogLine" src` → expect NO matches.
Run: `cd projects/ui && pnpm exec tsc --noEmit && pnpm test`
Expected: tsc fully clean; all tests pass, pristine.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/lib/api/mocks projects/ui/src/lib/api/schema.d.ts
git commit -m "chore: reshape run mocks to live contract; retire dead run mock surface"
```

---

## Task 10: Final gates + docs

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Backend gate**

Run: `cd /Users/noel/projects/naaf/.worktrees/run-monitor-live && make coverage && make lint`
Expected: coverage ≥80%, ruff + mypy clean.

- [ ] **Step 2: UI gate**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm exec tsc --noEmit`
Expected: all pass, pristine.

- [ ] **Step 3: Note the slice in project history**

Add one bullet under the status area of `docs/project-history.md`: the run monitor is now wired to the live A3 API (RunOut/RunEventOut + SSE + gate Approve/Reject), and runs track `token_usage` with a derived `cost` on `RunOut`; the dashboard/board agent panels + real pricing stay deferred.

- [ ] **Step 4: Commit**

```bash
git add docs/project-history.md
git commit -m "docs: record run-monitor-live slice"
```

---

## Self-Review Notes (author)

- **Spec coverage:** usage tracking — `StageResult.tokens`+fake (T1), `Run.token_usage`+ORM+migration (T2), accumulation+STAGE_PASSED tokens (T3), `RunOut.tokenUsage`+derived cost (T4) ✓; run monitor — types (T5), hooks incl. SSE + `useWorkItemRun`→`/runs?work_item=` + gate (T6), timeline+log (T7), AgentMonitor status/stage/timestamps/usage + gate UI (T8) ✓; mock reshape + `liveHandlers` + retire mock shapes (T9) ✓; agent panels/pricing deferred (Global Constraints) ✓.
- **Type consistency:** `Run.token_usage` (T2) → accumulated (T3) → `RunOut.tokenUsage`/`cost` (T4) → UI `RunOut` (T5) → hooks (T6) → components (T7/T8). `StageStateOut`/`RunEventOut` shapes identical across T5→T7→T8. `queryKeys.runEvents` defined once (T6).
- **Sequencing safety:** domain field + ORM column together (T2) so `SqlRepository.create` doesn't break; UI schema additive (T5) keeps the mock layer compiling through T6–T8; mock shapes retired only in T9 (tsc fully clean at T9, mirroring the messaging-foundation InboxItem approach).
- **Known adaptation:** T9's fixtures/db/handlers reshape is described (not verbatim) because it depends on the current mock file internals; the implementer follows the existing structure. T3's token invariant uses `.get("tokens", 0)` so stub stages (which bypass the runtime) don't break the assertion.
