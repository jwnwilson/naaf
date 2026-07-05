# A5d — real per-model pricing + usage/spend (display slice) — design

> Status: approved for planning · 2026-07-05
> Feature: replace the flat placeholder cost with **real per-model pricing**, capture per-model
> token usage in the run pipeline, persist real cost on each run, and make the last two mocked
> dashboard endpoints — `/dashboard/metrics` and `/budget` — live. **Display only** — no budget
> enforcement (that is the A5d-2 follow-up).

## Goal

Runs today track a single cumulative `Run.token_usage` int and expose a **flat** cost
(`token_usage/1000 × 0.003`); there is **no per-model attribution and no budget concept**. The
dashboard's `/dashboard/metrics` (spend/tokens/counts) and `/budget` (used/limit) are the only
remaining MSW-mock-only endpoints.

This slice makes cost **real and per-model**, persists it, and lights up those two endpoints —
finishing the dashboard. It stops short of a settable budget entity and run-halting enforcement,
which build on this usage data in **A5d-2**.

## Key decisions (from brainstorming)

- **Scope: display-first.** Pricing + per-model usage capture + persisted cost + live
  `/dashboard/metrics` + `/budget`. **No enforcement, no settable Budget entity** this slice.
- **Pricing config:** a `naaf_model_prices` settings dict, keyed by the same **model alias** the
  pipeline already uses (`opus`/`sonnet`/`haiku`), each `{input, output}` USD-per-1k. Unknown alias →
  cost 0 (logged). Mirrors how `model_aliases` is configured.
- **Input/output split matters:** Claude output costs ≈5× input, so real pricing needs the split
  (the adapters already return both; only `runtime.py` collapses them).
- **Cost storage: persist `Run.cost`.** A new float column (migration `0015`), accumulated per stage
  at stage-finish using per-model prices — captures the price at run-time, cheap to read.
- **Budget: USD, config-sourced.** `/budget` returns `{used = Σ Run.cost (owner, all-time), limit =
  naaf_budget_limit_usd}` (default `$100`). No Budget table this slice.
- **Subscription caveat:** for the Claude-CLI **subscription** runtime, per-token cost is *notional*
  (the sub is flat-rate); the dashboard labels spend "estimated."

## 1. Pricing — config + pure function

- **Settings** (`interactors/api/settings.py`): `budget_limit_usd: float = 100.0` and
  `model_prices: dict[str, ModelPrice]` where `ModelPrice = {input: float, output: float}` (USD per
  1k tokens), defaulted for `opus`/`sonnet`/`haiku` at current Claude list prices. Overridable via
  `naaf_model_prices` / `naaf_budget_limit_usd` (pydantic-settings JSON for the dict).
- **Pure domain function** `domain/pricing.py`:
  `price_stage(model: str, input_tokens: int, output_tokens: int, prices: dict[str, ...]) -> float`
  = `input_tokens/1000 × prices[model].input + output_tokens/1000 × prices[model].output`, rounded;
  unknown `model` → `0.0`. No I/O; unit-testable.

## 2. Capture per-model usage in the run pipeline

- **`StageResult`** (`domain/agent/runtime.py`) gains `input_tokens: int = 0`,
  `output_tokens: int = 0`, `model: str = ""`. The existing `tokens: int` (combined) stays for
  `Run.token_usage` + the token chart — purely additive.
- **`LlmAgentRuntime.run_stage`**: accumulate `input`/`output` separately across the tool loop
  (today `runtime.py:73` sums them into one int) and stamp `model = ctx.agent.model_alias` (the alias
  the request used). The three `StageResult(...)` construction sites carry the new fields.
- No adapter changes — `LLMResponse.usage` already carries `input_tokens`/`output_tokens`; the model
  is known from the stage's `AgentDefinition.model_alias`.

## 3. Persist real cost on the Run

- **Migration `0015_run_cost`** (down_revision `0014_agent_events`): add `runs.cost` — `Float`,
  `nullable=False`, `server_default="0"`. Domain `Run.cost: float = 0.0` (`domain/runs/run.py`); ORM
  `RunRow.cost` (`adapters/database/orm.py`).
- **`handlers._finish_stage`** (`interactors/worker/handlers.py`): alongside the existing
  `token_usage` accumulation, compute the stage's cost with `price_stage(result.model,
  result.input_tokens, result.output_tokens, settings.model_prices)` and set
  `run.cost = run.cost + stage_cost` in the same `model_copy(update=…)`. Prices are read from the
  worker's settings (already available in the worker context).
- **`RunOut.cost`** (`routes/runs.py:_run_out`): return `run.cost` directly. **Delete** the
  `COST_PER_1K_TOKENS` constant and the flat formula.

## 4. Live `/dashboard/metrics` + `/budget`

Two new owner-scoped routes added to `routes/dashboard.py` (registered already), matching the
existing UI schema shapes:

- `GET /dashboard/metrics` → `DashboardMetricsOut{activeAgents, totalSpend, totalTokens,
  projectCount, workItemCount}`:
  - `totalSpend = Σ run.cost` over the owner's runs; `totalTokens = Σ run.token_usage`.
  - `projectCount = count(projects)`, `workItemCount = count(work_items)` (owner-scoped).
  - `activeAgents = count(runs where status ∈ {running, awaiting_gate})` (kept for contract fidelity;
    the UI card already derives its number from `useAgents`).
- `GET /budget` → `BudgetOut{used, limit}`: `used = Σ run.cost` (owner), `limit =
  settings.budget_limit_usd`.

Aggregation sums via `read_multi` in Python (bounded at local single-user scale), consistent with the
existing `routes/dashboard.py` token/activity aggregators. New contract models `DashboardMetricsOut` /
`BudgetOut` (camelCase) alongside the others.

## 5. UI

- Move the `/dashboard/metrics` + `/budget` handlers from `mockOnlyHandlers` → `liveHandlers`
  (`mocks/handlers.ts`), bodies unchanged (`ok(seed.metrics)` / `ok(seed.budget)`), so mock mode still
  renders and live mode passes through to the backend.
- Add `refetchInterval: DASHBOARD_POLL_MS` (the existing 10s constant) to `useDashboard` and
  `useBudget` so spend stays live, paused when the tab is hidden.
- **`MetricCards` is unchanged** (contract shapes match). After this, `/projects/:id/board` is the
  only remaining mock-only endpoint.

## 6. Testing

- **`price_stage`**: input/output rates applied separately; unknown model → 0; zero tokens → 0.
- **Pipeline**: `run_stage` populates `input_tokens`/`output_tokens`/`model` on `StageResult` (fake
  adapter with a scripted `Usage`); `_finish_stage` accumulates `run.cost` from per-model prices
  alongside `token_usage`.
- **Routes**: `/dashboard/metrics` (spend = Σ cost, tokens = Σ usage, project/work-item counts,
  active-run count; owner-scoped so another owner's runs are excluded); `/budget` (used = Σ cost,
  limit = setting; owner-scoped); migration `0015` up/down on SQLite.
- **UI (vitest)**: `useDashboard`/`useBudget` set the poll interval and resolve the live shape; both
  handlers are live-backed.
- **Gates**: `make coverage` (80%) + `make lint`; UI `pnpm test` + `pnpm lint` + `pnpm build`.

## Out of scope / deferred (A5d-2 — enforcement)

- A settable, per-owner **`Budget` entity** + set-budget endpoint + UI (this slice's limit is config).
- **Enforcement**: the worker halting/failing a run when the owner's spend exceeds the budget.
- **Monthly reset / budget periods** (this slice's `used` is all-time).
- Per-model **spend breakdown** view (the per-model data now exists on `StageResult`, but only the
  combined cost is persisted on the run; a breakdown would enrich the RunEvent payload or add a usage
  table — future).
- LiteLLM per-run budget-key minting (pairs with enforcement).
