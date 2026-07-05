# A5d — Pricing + Usage/Spend (display slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat placeholder cost with real per-model pricing, capture per-model token usage in the run pipeline, persist real cost on each run, and make `/dashboard/metrics` + `/budget` live.

**Architecture:** A pure `price_stage` domain function keyed off a `naaf_model_prices` settings dict (by model alias). The runtime stops collapsing input/output tokens so each stage carries `model` + input/output split; `_finish_stage` prices the stage and accumulates a persisted `Run.cost` (migration `0015`) alongside `token_usage`. Two new owner-scoped dashboard routes sum `Run.cost`/`token_usage` for real spend + budget. Display only — no enforcement.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 + Alembic, pydantic-settings; React + Vite + React Query + MSW; pytest + Vitest.

**Reference spec:** `docs/superpowers/specs/2026-07-05-a5d-pricing-usage-design.md`

## Global Constraints

- Python ≥ 3.12; `uv`; env prefix `naaf_`. Domain logic pure (no I/O, no adapter imports).
- API envelope `{success, data, error}` via `crud_router.ok`; `Envelope[...]` response_model. Owner-scoped via `get_uow`.
- Immutability: pydantic entities updated via `model_copy(update={...})`, never mutated.
- Pricing keyed by **model alias** (`opus`/`sonnet`/`haiku`), each `{input, output}` USD-per-1k. Unknown alias → cost `0.0`.
- Default prices (USD per 1k tokens): `opus {input: 0.015, output: 0.075}`, `sonnet {input: 0.003, output: 0.015}`, `haiku {input: 0.001, output: 0.005}`.
- `price_stage(model, input_tokens, output_tokens, prices) = input_tokens/1000·prices[model].input + output_tokens/1000·prices[model].output`; unknown model → `0.0`.
- `Run.cost` (new float column, migration `0015`, `server_default="0"`) accumulates per-stage cost; `RunOut.cost = round(run.cost, 4)`. The flat `COST_PER_1K_TOKENS` is deleted.
- `budget_limit_usd: float = 100.0` setting. `/budget` = `{used = Σ run.cost (owner), limit = budget_limit_usd}` (USD). `/dashboard/metrics` = `{activeAgents, totalSpend = Σ run.cost, totalTokens = Σ run.token_usage, projectCount, workItemCount}`.
- The combined `StageResult.tokens` (= input+output) stays for `Run.token_usage` + the token chart — the split is additive.
- UI poll: `DASHBOARD_POLL_MS` (existing 10s) on `useDashboard` + `useBudget`; components unchanged.
- TDD; failing test first. `make coverage` (80%) + `make lint`; UI `pnpm test` + `pnpm lint` + `pnpm build`.
- Commit format `<type>: <description>`. Backend tests from `projects/server`; UI from `projects/ui`.

## File Structure

**New — backend**
- `projects/server/src/domain/pricing.py` — `ModelPrice`, `price_stage` (pure).
- `projects/server/src/adapters/database/migrations/versions/0015_run_cost.py`.
- Tests: `tests/domain/test_pricing.py`, `tests/interactors/api/test_dashboard_metrics_api.py`.

**Modified — backend**
- `interactors/api/settings.py` — `model_prices`, `budget_limit_usd`.
- `domain/agent/runtime.py` — `StageResult` fields + input/output/model capture.
- `adapters/agent/runtime/fake.py` — split + model on the fake result.
- `domain/runs/run.py` — `Run.cost`.
- `adapters/database/orm.py` — `RunRow.cost`.
- `interactors/worker/handlers.py` — `HandlerContext.model_prices`, cost in `_finish_stage`.
- `interactors/worker/subscription_runner.py` — pass `model_prices`.
- `interactors/api/routes/runs.py` — `RunOut.cost = run.cost`; delete flat constant.
- `interactors/api/routes/dashboard.py` — `/dashboard/metrics` + `/budget` routes.
- `interactors/api/contract.py` — `DashboardMetricsOut`, `BudgetOut`.
- `interactors/api/deps.py` — `get_budget_limit`.

**Modified — UI**
- `lib/api/hooks/useDashboard.ts` + `useBudget.ts` — poll.
- `lib/api/mocks/handlers.ts` — move 2 handlers to `liveHandlers`.
- `lib/api/mocks/fixtures/index.ts` — budget fixture → USD values.
- `lib/api/hooks/useDashboard.test.tsx` (extend) — metrics/budget poll + shape.
- `docs/project-history.md` — status entry (final task).

---

### Task 1: Pricing — pure function + settings config

**Files:**
- Create: `projects/server/src/domain/pricing.py`
- Modify: `projects/server/src/interactors/api/settings.py`
- Create: `projects/server/tests/domain/test_pricing.py`

**Interfaces:**
- Produces: `ModelPrice(BaseModel){input: float, output: float}`; `price_stage(model: str, input_tokens: int, output_tokens: int, prices: dict[str, ModelPrice]) -> float`; settings fields `model_prices: dict[str, ModelPrice]`, `budget_limit_usd: float`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/domain/test_pricing.py`:

```python
from domain.pricing import ModelPrice, price_stage

PRICES = {
    "opus": ModelPrice(input=0.015, output=0.075),
    "sonnet": ModelPrice(input=0.003, output=0.015),
    "haiku": ModelPrice(input=0.001, output=0.005),
}


def test_price_stage_applies_input_and_output_rates_separately():
    # 1000 input @ 0.003 + 2000 output @ 0.015 = 0.003 + 0.030 = 0.033
    assert price_stage("sonnet", 1000, 2000, PRICES) == 0.033


def test_price_stage_opus_more_expensive_than_haiku():
    assert price_stage("opus", 1000, 1000, PRICES) > price_stage("haiku", 1000, 1000, PRICES)


def test_price_stage_unknown_model_is_zero():
    assert price_stage("gpt-9", 5000, 5000, PRICES) == 0.0


def test_price_stage_zero_tokens_is_zero():
    assert price_stage("opus", 0, 0, PRICES) == 0.0


def test_settings_ship_default_prices_and_budget():
    from interactors.api.settings import Settings
    s = Settings()
    assert s.budget_limit_usd == 100.0
    assert s.model_prices["sonnet"].output == 0.015
    assert set(s.model_prices) >= {"opus", "sonnet", "haiku"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/test_pricing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.pricing'`.

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/pricing.py`:

```python
from pydantic import BaseModel


class ModelPrice(BaseModel):
    """USD per 1000 tokens for a model alias."""

    input: float
    output: float


def price_stage(
    model: str, input_tokens: int, output_tokens: int, prices: dict[str, ModelPrice]
) -> float:
    """Cost of one stage's LLM usage. Unknown model → 0.0 (e.g. an alias with no
    configured price, or the subscription path where cost is notional)."""
    p = prices.get(model)
    if p is None:
        return 0.0
    return round(input_tokens / 1000 * p.input + output_tokens / 1000 * p.output, 6)
```

Add to `projects/server/src/interactors/api/settings.py` — import `ModelPrice` and add the two fields (place them next to `model_aliases`):

```python
from domain.pricing import ModelPrice
...
    model_prices: dict[str, ModelPrice] = {
        "opus": ModelPrice(input=0.015, output=0.075),
        "sonnet": ModelPrice(input=0.003, output=0.015),
        "haiku": ModelPrice(input=0.001, output=0.005),
    }
    budget_limit_usd: float = 100.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/test_pricing.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/pricing.py projects/server/src/interactors/api/settings.py projects/server/tests/domain/test_pricing.py
git commit -m "feat: per-model pricing function + model_prices/budget settings"
```

---

### Task 2: Capture per-model usage in the runtime

**Files:**
- Modify: `projects/server/src/domain/agent/runtime.py`
- Modify: `projects/server/src/adapters/agent/runtime/fake.py`
- Create: `projects/server/tests/domain/agent/test_runtime_usage.py`

**Interfaces:**
- Consumes: `LLMResponse.usage` (`input_tokens`/`output_tokens`), `ctx.agent.model_alias`.
- Produces: `StageResult` gains `input_tokens: int = 0`, `output_tokens: int = 0`, `model: str = ""`. All runtimes populate them.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/domain/agent/test_runtime_usage.py`:

```python
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.llm import LLMResponse, Usage
from domain.agent.runtime import LlmAgentRuntime
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


class _FakeLLM:
    """Returns one non-tool response with scripted usage, ending the stage."""

    def __init__(self):
        self._n = 0

    def complete(self, request):
        self._n += 1
        return LLMResponse(
            content="done", tool_calls=[], stop_reason="end_turn",
            usage=Usage(input_tokens=120, output_tokens=30),
        )


class _NoWorkspace:
    pass


def _ctx():
    return StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/x",
        work_item=WorkItemBrief(title="T"),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND, model_alias="sonnet"),
    )


def test_run_stage_captures_input_output_split_and_model():
    rt = LlmAgentRuntime(_FakeLLM(), workspace_factory=lambda _p: _NoWorkspace())
    outcome = rt.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    res = outcome.result
    assert res.input_tokens == 120
    assert res.output_tokens == 30
    assert res.tokens == 150            # combined stays
    assert res.model == "sonnet"        # the request alias


def test_fake_runtime_sets_split_and_model():
    from adapters.agent.runtime.fake import FakeAgentRuntime
    outcome = FakeAgentRuntime().run_stage("engineer", Stage.IMPLEMENT, _ctx())
    res = outcome.result
    assert res.input_tokens + res.output_tokens == res.tokens
    assert res.model == "sonnet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/agent/test_runtime_usage.py -v`
Expected: FAIL — `StageResult` has no `input_tokens`/`model`.

- [ ] **Step 3: Write minimal implementation**

In `projects/server/src/domain/agent/runtime.py`, extend `StageResult`:

```python
class StageResult(BaseModel):
    passed: bool
    summary: str = ""
    tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
```

In `run_stage`, track input/output separately and stamp the model on each `StageResult`. Replace `total_tokens = 0` with two accumulators and update the loop + all three construction sites:

```python
        final_text = ""
        total_input = 0
        total_output = 0

        for _ in range(self._max_iterations):
            response = self._llm.complete(request.model_copy(update={"messages": messages}))
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
```

Then each `StageResult(...)` (the `report` return, the no-tool return, and the max-iterations return) gains the same three fields. For the `report` return:

```python
                    result=StageResult(
                        passed=bool(report.args.get("passed", ctx.stage is not Stage.VERIFY)),
                        summary=str(report.args.get("summary", final_text or "ok")),
                        tokens=total_input + total_output,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        model=request.model,
                    ),
```

the no-tool return:

```python
                    result=StageResult(
                        passed=ctx.stage is not Stage.VERIFY,
                        summary=final_text or "ok",
                        tokens=total_input + total_output,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        model=request.model,
                    ),
```

and the max-iterations return:

```python
            result=StageResult(
                passed=False,
                summary="stopped: max iterations reached",
                tokens=total_input + total_output,
                input_tokens=total_input,
                output_tokens=total_output,
                model=request.model,
            ),
```

In `projects/server/src/adapters/agent/runtime/fake.py`, split the fake tokens and stamp the model so fake runs (used by `make dev`) still produce a priced cost:

```python
        tokens = TOKENS_PER_STEP * len(events)
        in_tok = tokens * 7 // 10
        result = StageResult(
            passed=passed, summary=summary, tokens=tokens,
            input_tokens=in_tok, output_tokens=tokens - in_tok,
            model=ctx.agent.model_alias or "sonnet",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/domain/agent/test_runtime_usage.py -v`
Expected: both PASS. (`request.model` = `ctx.agent.model_alias or "default"`, so `"sonnet"` here.)

- [ ] **Step 5: Run the broader agent-runtime tests + commit**

Run: `cd projects/server && uv run pytest tests/domain/agent -q`
Expected: green (the new fields have defaults, so existing StageResult uses are unaffected).

```bash
git add projects/server/src/domain/agent/runtime.py projects/server/src/adapters/agent/runtime/fake.py projects/server/tests/domain/agent/test_runtime_usage.py
git commit -m "feat: capture per-stage input/output token split + model in the runtime"
```

---

### Task 3: Persist Run.cost + accumulate in the worker + RunOut.cost

**Files:**
- Modify: `projects/server/src/domain/runs/run.py`
- Modify: `projects/server/src/adapters/database/orm.py`
- Create: `projects/server/src/adapters/database/migrations/versions/0015_run_cost.py`
- Modify: `projects/server/src/interactors/worker/handlers.py`
- Modify: `projects/server/src/interactors/worker/subscription_runner.py`
- Modify: `projects/server/src/interactors/api/routes/runs.py`
- Create: `projects/server/tests/interactors/worker/test_run_cost.py`

**Interfaces:**
- Consumes: `price_stage`, `ModelPrice` (Task 1); `StageResult.model/input_tokens/output_tokens` (Task 2).
- Produces: `Run.cost: float = 0.0`; `RunRow.cost`; `HandlerContext.model_prices: dict[str, ModelPrice] | None`; `_finish_stage` accumulates `run.cost`; `RunOut.cost = round(run.cost, 4)`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/interactors/worker/test_run_cost.py`:

```python
from domain.agent.runtime import AgentEvent, StageOutcome, StageResult
from domain.pricing import ModelPrice
from domain.runs.run import Run, RunStatus, Stage, StageState, StageStatus
from interactors.worker.handlers import HandlerContext, _finish_stage


class _Repo:
    def __init__(self):
        self.saved = None
    def read(self, _id):
        return self.saved
    def update(self, _id, dto):
        self.saved = dto
        return dto
    def create(self, dto):
        self.saved = dto
        return dto


def _ctx():
    return HandlerContext(
        runs=_Repo(), run_events=_Repo(), work_items=_Repo(), notifications=None,
        bus=None, runtime=None, messages=_Repo(),
        model_prices={"sonnet": ModelPrice(input=0.003, output=0.015)},
    )


def _run():
    return Run(
        owner_id="o", work_item_id="wi", project_id="p", autonomy_level="gated_all",
        status=RunStatus.RUNNING, current_stage=Stage.IMPLEMENT,
        stages=[StageState(stage=Stage.IMPLEMENT, status=StageStatus.RUNNING, role="engineer")],
    )


def test_finish_stage_accumulates_priced_cost_and_tokens():
    ctx = _ctx()
    ctx.runs.saved = _run()
    outcome = StageOutcome(
        events=[AgentEvent(message="hi")],
        result=StageResult(passed=True, summary="ok", tokens=3000,
                            input_tokens=1000, output_tokens=2000, model="sonnet"),
    )
    _finish_stage(ctx, ctx.runs.saved, "engineer", Stage.IMPLEMENT, outcome)
    saved = ctx.runs.saved
    assert saved.token_usage == 3000
    # 1000/1000*0.003 + 2000/1000*0.015 = 0.033
    assert round(saved.cost, 4) == 0.033


def test_finish_stage_unknown_model_costs_zero():
    ctx = _ctx()
    ctx.runs.saved = _run()
    outcome = StageOutcome(
        events=[], result=StageResult(passed=True, tokens=500, input_tokens=500, model="mystery"),
    )
    _finish_stage(ctx, ctx.runs.saved, "engineer", Stage.IMPLEMENT, outcome)
    assert ctx.runs.saved.cost == 0.0
```

Note: `_finish_stage` calls `emit()` and `narrate()` which use `ctx.run_events`/`ctx.messages`; the `_Repo` stub above absorbs those `.create(...)` calls. If `_finish_stage` calls a helper that needs another ctx field, stub it the same minimal way — inspect `handlers.py` `emit`/`narrate`/`_save` for the exact repos touched and give each a `_Repo()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_run_cost.py -v`
Expected: FAIL — `Run` has no `cost` / `HandlerContext` has no `model_prices`.

- [ ] **Step 3: Write minimal implementation**

Add `cost` to the domain `Run` (`projects/server/src/domain/runs/run.py`), next to `token_usage`:

```python
    token_usage: int = 0
    cost: float = 0.0
```

Add the ORM column (`projects/server/src/adapters/database/orm.py`, in `RunRow`, next to `token_usage`):

```python
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
```

Ensure `Float` is imported at the top of `orm.py` (`from sqlalchemy import ..., Float, ...`).

Create the migration `projects/server/src/adapters/database/migrations/versions/0015_run_cost.py`:

```python
"""run cost column

Revision ID: 0015_run_cost
Revises: 0014_agent_events
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_run_cost"
down_revision = "0014_agent_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("cost", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("runs", "cost")
```

Add `model_prices` to `HandlerContext` (`projects/server/src/interactors/worker/handlers.py`) — import `price_stage`, `ModelPrice`, and add the field after `role_aliases`:

```python
from domain.pricing import ModelPrice, price_stage
...
    role_aliases: dict[str, str] | None = field(default=None)
    model_prices: dict[str, "ModelPrice"] | None = None
```

In `_finish_stage`, compute and accumulate cost in the same `model_copy`:

```python
    stage_cost = price_stage(
        outcome.result.model, outcome.result.input_tokens, outcome.result.output_tokens,
        ctx.model_prices or {},
    )
    _save(ctx, run.model_copy(update={
        "stages": [*run.stages[:-1], updated_entry],
        "token_usage": run.token_usage + outcome.result.tokens,
        "cost": run.cost + stage_cost,
    }))
```

Wire it in `subscription_runner.py` — the `HandlerContext(...)` construction (add alongside `role_aliases=_s.role_model_aliases`):

```python
            role_aliases=_s.role_model_aliases,
            model_prices=_s.model_prices,
```

Update `RunOut.cost` in `projects/server/src/interactors/api/routes/runs.py` — delete `COST_PER_1K_TOKENS` (line ~31) and change the `_run_out` cost line:

```python
        cost=round(run.cost, 4),
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd projects/server && uv run pytest tests/interactors/worker/test_run_cost.py -v
DB=$(mktemp -u).db; naaf_db_url="sqlite:///$DB" uv run alembic upgrade head; echo "EXIT: $?"
```
Expected: cost tests PASS; `alembic upgrade head` exits 0 (0015 applies on SQLite — `add_column` is SQLite-safe).

- [ ] **Step 5: Run the full backend suite + lint + commit**

Run:
```bash
cd projects/server && uv run pytest -q
cd /Users/noel/projects/naaf/.worktrees/a5d && make lint
```
Expected: green. (Existing run/RunOut tests still pass — `Run.cost` defaults to 0.)

```bash
git add projects/server/src/domain/runs/run.py projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/migrations/versions/0015_run_cost.py projects/server/src/interactors/worker/handlers.py projects/server/src/interactors/worker/subscription_runner.py projects/server/src/interactors/api/routes/runs.py projects/server/tests/interactors/worker/test_run_cost.py
git commit -m "feat: persist per-model Run.cost + real RunOut.cost (migration 0015)"
```

---

### Task 4: Live `/dashboard/metrics` + `/budget`

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py`
- Modify: `projects/server/src/interactors/api/routes/dashboard.py`
- Modify: `projects/server/src/interactors/api/deps.py`
- Create: `projects/server/tests/interactors/api/test_dashboard_metrics_api.py`

**Interfaces:**
- Consumes: `uow.runs`/`uow.projects`/`uow.work_items` (owner-scoped `read_multi`, `.total` for counts); `get_uow`; settings `budget_limit_usd` (via `get_budget_limit`).
- Produces: `DashboardMetricsOut{activeAgents, totalSpend, totalTokens, projectCount, workItemCount}`, `BudgetOut{used, limit}`; routes `GET /dashboard/metrics`, `GET /budget`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/interactors/api/test_dashboard_metrics_api.py`:

```python
from adapters.database.uow import SqlUnitOfWork
from domain.runs.run import Run, RunStatus


def _seed_run(session_factory, owner: str, *, cost: float, tokens: int, status=RunStatus.SUCCEEDED):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction() as u:
        u.runs.create(Run(
            owner_id="", work_item_id="wi", project_id="p", autonomy_level="gated_all",
            status=status, token_usage=tokens, cost=cost,
        ))


def test_metrics_sums_cost_and_tokens_owner_scoped(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=0.50, tokens=1000)
    _seed_run(session_factory, "dev-user", cost=0.25, tokens=500)
    body = client.get("/dashboard/metrics").json()
    assert body["success"] is True
    data = body["data"]
    assert data["totalSpend"] == 0.75
    assert data["totalTokens"] == 1500
    assert "projectCount" in data and "workItemCount" in data and "activeAgents" in data


def test_metrics_excludes_other_owner(client, client_other_owner, session_factory):
    _seed_run(session_factory, "dev-user", cost=9.99, tokens=9999)
    data = client_other_owner.get("/dashboard/metrics").json()["data"]
    assert data["totalSpend"] == 0.0
    assert data["totalTokens"] == 0


def test_metrics_counts_active_runs(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=0.0, tokens=0, status=RunStatus.RUNNING)
    assert client.get("/dashboard/metrics").json()["data"]["activeAgents"] == 1


def test_budget_used_is_total_spend_and_limit_from_settings(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=1.20, tokens=100)
    body = client.get("/budget").json()["data"]
    assert body["used"] == 1.20
    assert body["limit"] == 100.0  # Settings.budget_limit_usd default


def test_budget_owner_scoped(client_other_owner, session_factory):
    _seed_run(session_factory, "dev-user", cost=5.0, tokens=100)
    assert client_other_owner.get("/budget").json()["data"]["used"] == 0.0
```

Note: reuse the existing `client`, `client_other_owner`, `session_factory` fixtures in `projects/server/tests/interactors/api/conftest.py` (the agents/dashboard tests already use them).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_dashboard_metrics_api.py -v`
Expected: FAIL — routes 404 / `DashboardMetricsOut` import error.

- [ ] **Step 3: Write minimal implementation**

Add contract models to `projects/server/src/interactors/api/contract.py` (near the other dashboard models):

```python
class DashboardMetricsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activeAgents: int
    totalSpend: float
    totalTokens: int
    projectCount: int
    workItemCount: int


class BudgetOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    used: float
    limit: float
```

Add a settings dep to `projects/server/src/interactors/api/deps.py` (mirrors the existing `get_max_attachment_bytes`):

```python
def get_budget_limit(request: Request) -> float:
    return request.app.state.settings.budget_limit_usd
```

Add the two routes to `projects/server/src/interactors/api/routes/dashboard.py` (extend imports: `DashboardMetricsOut`, `BudgetOut` from contract; `get_budget_limit` from deps):

```python
_RUN_SCAN = 1000  # sum runs in Python — bounded at local single-user scale


@router.get("/dashboard/metrics", response_model=Envelope[DashboardMetricsOut])
def dashboard_metrics(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    runs = uow.runs.read_multi(page_size=_RUN_SCAN).results
    active = uow.runs.read_multi(
        filters={"status__in": ["running", "awaiting_gate"]}, page_size=1
    ).total
    projects = uow.projects.read_multi(page_size=1).total
    work_items = uow.work_items.read_multi(page_size=1).total
    return ok(DashboardMetricsOut(
        activeAgents=active,
        totalSpend=round(sum(r.cost for r in runs), 4),
        totalTokens=sum(r.token_usage for r in runs),
        projectCount=projects,
        workItemCount=work_items,
    ))


@router.get("/budget", response_model=Envelope[BudgetOut])
def budget(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    limit: float = Depends(get_budget_limit),  # noqa: B008
):
    runs = uow.runs.read_multi(page_size=_RUN_SCAN).results
    return ok(BudgetOut(used=round(sum(r.cost for r in runs), 4), limit=limit))
```

(The `dashboard_router` is already registered in `routes/__init__.py`; these are new endpoints on the same router.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_dashboard_metrics_api.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full backend suite + lint + commit**

Run: `cd projects/server && uv run pytest -q && cd /Users/noel/projects/naaf/.worktrees/a5d && make lint`
Expected: green.

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/dashboard.py projects/server/src/interactors/api/deps.py projects/server/tests/interactors/api/test_dashboard_metrics_api.py
git commit -m "feat: live GET /dashboard/metrics + GET /budget (real spend)"
```

---

### Task 5: UI — move handlers live + poll

**Files:**
- Modify: `projects/ui/src/lib/api/hooks/useDashboard.ts`
- Modify: `projects/ui/src/lib/api/hooks/useBudget.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts`
- Modify: `projects/ui/src/lib/api/hooks/useDashboard.test.tsx`

**Interfaces:**
- Consumes: `DASHBOARD_POLL_MS` (already exported from `useDashboard.ts`).

- [ ] **Step 1: Write the failing test**

Extend `projects/ui/src/lib/api/hooks/useDashboard.test.tsx` — add a test that `useDashboard` (metrics) fetches the live shape and that both metrics + budget are polled. Add (keep existing tests):

```tsx
import { useDashboard } from "./useDashboard";
import { useBudget } from "../hooks/useBudget";

test("useDashboard fetches live metrics", async () => {
  server.use(
    http.get("/api/dashboard/metrics", () =>
      HttpResponse.json({ success: true, error: null,
        data: { activeAgents: 2, totalSpend: 1.5, totalTokens: 4200, projectCount: 3, workItemCount: 9 } }),
    ),
  );
  const { result } = renderHook(() => useDashboard(), { wrapper });
  await waitFor(() => expect(result.current.data?.totalSpend).toBe(1.5));
});

test("useBudget fetches live used/limit", async () => {
  server.use(
    http.get("/api/budget", () =>
      HttpResponse.json({ success: true, error: null, data: { used: 1.5, limit: 100 } }),
    ),
  );
  const { result } = renderHook(() => useBudget(), { wrapper });
  await waitFor(() => expect(result.current.data?.limit).toBe(100));
});
```

(If `useBudget`'s import path differs, use `./useBudget`. Reuse the file's existing inline `wrapper` + `server` imports.)

- [ ] **Step 2: Run test to verify it fails / establishes the target**

Run: `cd projects/ui && pnpm test -- useDashboard`
Expected: the two new tests fail only if the handlers aren't wired — but they use `server.use` overrides so they should pass once imports resolve; the real behavioral change is the poll + handler move below. Proceed to implement, then confirm the FULL suite (Step 4) — the existing `handlers.test.ts` assertion about `/dashboard/metrics` being mock-only will now FAIL and must be updated in this task.

- [ ] **Step 3: Write minimal implementation**

Add `refetchInterval` to `useDashboard` (`projects/ui/src/lib/api/hooks/useDashboard.ts`) — it already exports `DASHBOARD_POLL_MS`:

```ts
export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard(),
    queryFn: () => apiFetch<DashboardMetrics>("/dashboard/metrics"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}
```

Add polling to `useBudget` (`projects/ui/src/lib/api/hooks/useBudget.ts`) — import the constant:

```ts
import { DASHBOARD_POLL_MS } from "./useDashboard";
...
export function useBudget() {
  return useQuery({
    queryKey: queryKeys.budget(),
    queryFn: () => apiFetch<Budget>("/budget"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}
```

In `projects/ui/src/lib/api/mocks/handlers.ts`, MOVE the `/dashboard/metrics` and `/budget` handlers from `mockOnlyHandlers` into `liveHandlers` (bodies unchanged: `ok(seed.metrics)` / `ok(seed.budget)`). After the move, `mockOnlyHandlers` should contain only `/projects/:id/board`.

Update `projects/ui/src/lib/api/mocks/fixtures/index.ts` — retune the `budget` fixture to USD so mock mode is coherent with the new semantics:

```ts
const budget: Budget = {
  used: 42.85,
  limit: 100,
};
```

If `projects/ui/src/lib/api/mocks/handlers.test.ts` has an assertion that `/dashboard/metrics` (or `/budget`) stays mock-only, update it: those are now live. The invariant to keep asserting is that `/projects/:id/board` remains mock-only (match `/\/projects\/:id\/board/`, not a broad `/dashboard/`).

- [ ] **Step 4: Run the full UI suite + lint + build**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: all green. `MetricCards` renders unchanged. Confirm no test still asserts `/dashboard/metrics` or `/budget` are mock-only.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useDashboard.ts projects/ui/src/lib/api/hooks/useBudget.ts projects/ui/src/lib/api/mocks/handlers.ts projects/ui/src/lib/api/mocks/fixtures/index.ts projects/ui/src/lib/api/hooks/useDashboard.test.tsx
git commit -m "feat: poll + live-back /dashboard/metrics and /budget"
```

---

### Task 6: Gates, docs, and PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Run all gates**

Run:
```bash
cd /Users/noel/projects/naaf/.worktrees/a5d
make coverage   # 80% gate
make lint
cd projects/ui && pnpm test && pnpm lint && pnpm build
```
Expected: coverage ≥ 80%, lint clean, UI green + builds.

- [ ] **Step 2: Update project history**

Add a dated entry to `docs/project-history.md` (top of the latest `## Status` section) summarizing: real per-model pricing (`model_prices` settings + `price_stage`), per-stage input/output/model captured in the runtime, persisted `Run.cost` (migration `0015`) replacing the flat cost, live `/dashboard/metrics` + `/budget` (real spend, USD budget from `naaf_budget_limit_usd`), UI polling; note the subscription cost is notional, and enforcement (settable Budget entity + run-halting + monthly reset) is deferred to A5d-2. Also update the **Current state**/**Outstanding** sections: the dashboard now has **no** mock-only endpoints except `/projects/:id/board`, and A5d's display slice is done (enforcement remains). Link the spec + plan.

- [ ] **Step 3: Commit docs**

```bash
git add docs/project-history.md
git commit -m "docs: record A5d pricing + usage/spend (display slice)"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/a5d-pricing-usage
gh pr create --title "feat: A5d — real per-model pricing + live spend/budget (display slice)" --body "$(cat <<'EOF'
## Summary
- **Per-model pricing:** a `naaf_model_prices` settings dict (by alias) + a pure `price_stage(model, input, output, prices)`; output priced ~5× input. Defaults for opus/sonnet/haiku, overridable.
- **Usage capture:** the runtime stops collapsing tokens — each `StageResult` carries `input_tokens`/`output_tokens`/`model` (combined `tokens` unchanged for the chart).
- **Persisted cost:** new `Run.cost` column (migration `0015`), accumulated per stage at finish via `price_stage` (captures run-time prices). `RunOut.cost` reads it; the flat `COST_PER_1K_TOKENS` is gone.
- **Live dashboard:** owner-scoped `GET /dashboard/metrics` (Σ cost / Σ tokens / counts / active runs) and `GET /budget` (used = Σ cost, limit = `naaf_budget_limit_usd`, default $100). UI polls both every 10s; `/dashboard/metrics` + `/budget` moved mock-only → live — **the dashboard is now fully live** (only `/projects/:id/board` remains mocked).
- **Note:** Claude-CLI subscription cost is notional (flat-rate sub); shown as an estimate.
- **Deferred to A5d-2:** settable per-owner Budget entity + set-budget UI, worker enforcement (halt runs at cap), monthly reset, per-model breakdown.

Design: `docs/superpowers/specs/2026-07-05-a5d-pricing-usage-design.md` · Plan: `docs/superpowers/plans/2026-07-05-a5d-pricing-usage.md`

## Test plan
- [x] `make coverage` ≥ 80% · `make lint` clean
- [x] `cd projects/ui && pnpm test && pnpm build` green
- [x] `price_stage` (input/output rates, unknown→0); runtime captures split+model; fake runtime too
- [x] `_finish_stage` accumulates priced `Run.cost` + tokens; migration `0015` up/down on SQLite
- [x] `/dashboard/metrics` (Σ spend/tokens, counts, active) + `/budget` (used/limit) owner-scoped
- [ ] Manual: `make dev`, run a task, watch TOTAL SPEND + the budget bar grow with real per-model cost
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Pricing config + pure `price_stage` (by alias, unknown→0, input/output split) → Task 1. ✓
- Capture per-model usage (StageResult split + model; runtime; fake) → Task 2. ✓
- Persist `Run.cost` (migration 0015) + accumulate in `_finish_stage` + `RunOut.cost` reads it + delete flat → Task 3. ✓
- Live `/dashboard/metrics` (Σ cost/tokens/counts/active) + `/budget` (used=Σcost, limit=setting), owner-scoped, contract models → Task 4. ✓
- UI move handlers live + poll `useDashboard`/`useBudget`, components unchanged, budget fixture USD → Task 5. ✓
- Subscription-notional note + deferred A5d-2 items → design + docs (Task 6); not implemented. ✓

**2. Placeholder scan:** No TBD/TODO/"add validation". Test-stub notes (Task 3 `_Repo`, Task 4 fixtures) point at concrete existing patterns. The Task 5 Step-2 note about `handlers.test.ts` is a concrete instruction (update the mock-only assertion), not a deferral.

**3. Type consistency:** `ModelPrice{input,output}` and `price_stage(model, input_tokens, output_tokens, prices)` identical across Tasks 1/3/4. `StageResult` new fields (`input_tokens`, `output_tokens`, `model`) consistent in Tasks 2/3. `Run.cost: float` ↔ `RunRow.cost` ↔ migration `cost` ↔ `RunOut.cost = round(run.cost,4)` ↔ dashboard `sum(r.cost)` all agree. `DashboardMetricsOut`/`BudgetOut` fields match the UI schema (`totalSpend`,`totalTokens`,`projectCount`,`workItemCount`,`activeAgents`; `used`,`limit`). `DASHBOARD_POLL_MS` reused in Task 5.
