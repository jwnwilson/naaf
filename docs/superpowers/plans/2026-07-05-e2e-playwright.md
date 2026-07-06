# Playwright End-to-End Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic Playwright e2e test that drives the real full stack through a browser and proves the core journey — chat to lead → lead creates a task → trigger a multi-stage run → see the agent output streamed live on the UI — plus an opt-in real-`claude` smoke variant.

**Architecture:** Fake only the model. A `ScriptedLLMAdapter` plugs into the real `LlmOrchestrator`/`LlmChatResponder`/`LlmAgentRuntime`, so the genuine tool loop + `set_event_sink` → `agent_events` → SSE → `ActivityFeed` pipeline runs unchanged. The e2e boots API + worker + Postgres + UI (live-API) with `naaf_llm_provider=scripted`, and Playwright drives chromium against it.

**Tech Stack:** Python 3.12 / uv / pytest (backend adapter, TDD), Playwright + chromium (e2e), Vite live-API UI, Make (stack orchestration), GitHub Actions (CI).

## Global Constraints

- Python ≥ 3.12, `uv`; backend commands run from `projects/server`. UI/Playwright from `projects/ui`. `make` from repo root `/Users/noel/projects/naaf/.worktrees/e2e-playwright`.
- Immutability (`model_copy`), API envelope `{success,data,error}`, owner-scoping (create with `owner_id=""`, stamped from `required_filters`); dev auth injects `dev-user`.
- The scripted adapter must implement the real port exactly: `complete(request: LLMRequest) -> LLMResponse` plus `set_event_sink(emit)`. It fakes ONLY the model — no other production code is bypassed.
- Deterministic scripted strings are shared: backend `script.py` and UI `e2e/fixtures/scripted.ts` must hold identical values — `TASK_TITLE="E2E streaming task"`, `EPIC_TITLE="E2E Epic"`, `FEATURE_TITLE="E2E Feature"`, `STAGE_TEXT_SCAN="Scanning the repository…"`, `STAGE_TEXT_DONE="Changes applied."`, `CHAT_TEXT_PLAN="Planning the work…"`.
- E2E stack env: `naaf_llm_provider=scripted`, `naaf_agent_runtime=claude_code` (any non-`fake`), dedicated DB `naaf_db_url=postgresql+psycopg://naaf:naaf@localhost:5432/naaf_e2e`. No secrets/keys required by the scripted path.
- The e2e project is created with `autonomyLevel="full_auto"` so the run flows plan→implement→verify→pr→learn with NO gates.
- No fixed `sleep`s in specs — `expect.poll`/web-first assertions only. `retries: 1` and `trace: 'on-first-retry'` in CI.
- TDD for the Python adapter (failing test first). Commit format `<type>: <description>`. Gates: `make lint` + `make coverage` (80%) for backend changes; `pnpm lint` (tsc) for UI.

## File Structure

```
projects/server/src/adapters/agent/scripted/__init__.py       # new package
projects/server/src/adapters/agent/scripted/script.py         # shared scripted constants
projects/server/src/adapters/agent/scripted/adapter.py        # ScriptedLLMAdapter
projects/server/src/adapters/agent/factory.py                 # +scripted branch in build_llm_adapter
projects/server/tests/adapters/agent/test_scripted_adapter.py # adapter unit tests
projects/ui/package.json                                      # +@playwright/test dep + test:e2e script
projects/ui/playwright.config.ts                              # chromium, baseURL, globalSetup, trace
projects/ui/e2e/fixtures/scripted.ts                          # shared constants (mirror script.py)
projects/ui/e2e/support/globalSetup.ts                        # wait for stack health
projects/ui/e2e/smoke.spec.ts                                 # trivial "UI loads" spec (harness proof)
projects/ui/e2e/streaming-journey.spec.ts                     # the journey
Makefile                                                      # e2e (+ e2e-db, e2e-real) targets
.github/workflows/e2e.yml                                     # CI
docs/dogfooding.md OR docs/e2e.md                             # how to run
```

---

## Phase 1 — Backend scripted adapter

### Task 1: Scripted constants + `ScriptedLLMAdapter`

**Files:**
- Create: `projects/server/src/adapters/agent/scripted/__init__.py` (empty)
- Create: `projects/server/src/adapters/agent/scripted/script.py`
- Create: `projects/server/src/adapters/agent/scripted/adapter.py`
- Test: `projects/server/tests/adapters/agent/test_scripted_adapter.py`

**Interfaces:**
- Consumes: `LLMRequest`, `LLMResponse`, `ToolCall`, `Usage`, `MessageRole` from `domain.agent.llm`; `EventSink` from `adapters.agent.claude_cli.stream_runner`.
- Produces:
  - `script.py` constants: `TASK_TITLE`, `EPIC_TITLE`, `FEATURE_TITLE`, `STAGE_TEXT_SCAN`, `STAGE_TEXT_DONE`, `CHAT_TEXT_PLAN` (exact values in Global Constraints).
  - `ScriptedLLMAdapter` with `set_event_sink(emit) -> None` and `complete(request: LLMRequest) -> LLMResponse`. Branches: `report` in request tools → run-stage (emits scripted events + returns a `report` tool-call `passed=True`); `create_work_item` in tools → lead planning (scripted `list_board`→`create_work_item`×3→`propose_run`→final text, chaining `parent_id` by parsing `id=(\w+)` from the last TOOL message); else → plain chat.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_scripted_adapter.py
from adapters.agent.scripted.adapter import ScriptedLLMAdapter
from adapters.agent.scripted.script import (
    CHAT_TEXT_PLAN, EPIC_TITLE, FEATURE_TITLE, STAGE_TEXT_SCAN, TASK_TITLE,
)
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolSpec

REPORT_TOOL = ToolSpec(name="report", description="", parameters={"type": "object", "properties": {}})
CREATE_TOOL = ToolSpec(name="create_work_item", description="", parameters={"type": "object", "properties": {}})


def _req(tools, messages):
    return LLMRequest(model="m", system="", messages=messages, tools=tools)


def test_run_stage_emits_events_and_reports_passed():
    events = []
    a = ScriptedLLMAdapter()
    a.set_event_sink(lambda k, p: events.append((k, p)))
    resp = a.complete(_req([REPORT_TOOL], [LLMMessage(role=MessageRole.USER, content="do plan")]))
    kinds = [k for k, _ in events]
    assert kinds == ["text_block", "tool_call", "tool_result", "text_block"]
    assert events[0][1]["text"] == STAGE_TEXT_SCAN
    report = next(c for c in resp.tool_calls if c.name == "report")
    assert report.args["passed"] is True


def test_lead_plan_walks_list_epic_feature_task_proposerun_then_text():
    a = ScriptedLLMAdapter()
    msgs = [LLMMessage(role=MessageRole.USER, content="build notes")]

    def next_call():
        return a.complete(_req([CREATE_TOOL], msgs))

    # step 0 → list_board
    r = next_call(); assert r.tool_calls[0].name == "list_board"
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="board is empty", tool_call_id=r.tool_calls[0].id)]
    # step 1 → create epic
    r = next_call(); assert r.tool_calls[0].args == {"kind": "epic", "title": EPIC_TITLE}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created epic 'E2E Epic' id=epic123", tool_call_id=r.tool_calls[0].id)]
    # step 2 → create feature under epic123
    r = next_call(); assert r.tool_calls[0].args == {"kind": "feature", "title": FEATURE_TITLE, "parent_id": "epic123"}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created feature 'E2E Feature' id=feat456", tool_call_id=r.tool_calls[0].id)]
    # step 3 → create task under feat456
    r = next_call(); assert r.tool_calls[0].args == {"kind": "task", "title": TASK_TITLE, "parent_id": "feat456"}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created task 'E2E streaming task' id=task789", tool_call_id=r.tool_calls[0].id)]
    # step 4 → propose_run on task789
    r = next_call(); assert r.tool_calls[0].name == "propose_run" and r.tool_calls[0].args == {"work_item_ids": ["task789"]}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="proposed run", tool_call_id=r.tool_calls[0].id)]
    # step 5 → final text, no tool calls
    r = next_call(); assert r.stop_reason == "end_turn" and not r.tool_calls and TASK_TITLE in r.content


def test_lead_plan_emits_a_chat_activity_event():
    events = []
    a = ScriptedLLMAdapter()
    a.set_event_sink(lambda k, p: events.append((k, p)))
    a.complete(_req([CREATE_TOOL], [LLMMessage(role=MessageRole.USER, content="build notes")]))
    assert ("text_block", {"text": CHAT_TEXT_PLAN}) in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_scripted_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: adapters.agent.scripted`.

- [ ] **Step 3: Write the constants + adapter**

```python
# projects/server/src/adapters/agent/scripted/script.py
"""Deterministic scripted strings shared with the e2e UI fixtures
(projects/ui/e2e/fixtures/scripted.ts). Keep the two in sync."""

TASK_TITLE = "E2E streaming task"
EPIC_TITLE = "E2E Epic"
FEATURE_TITLE = "E2E Feature"
STAGE_TEXT_SCAN = "Scanning the repository…"
STAGE_TEXT_DONE = "Changes applied."
CHAT_TEXT_PLAN = "Planning the work…"
```

```python
# projects/server/src/adapters/agent/scripted/adapter.py
"""A deterministic LLMAdapter for e2e tests. Fakes ONLY the model: it plugs into
the real LlmOrchestrator / LlmChatResponder / LlmAgentRuntime, so the genuine
tool loop and set_event_sink → agent_events → SSE → UI pipeline run unchanged.
"""
import re

from domain.agent.llm import LLMMessage, LLMRequest, LLMResponse, MessageRole, ToolCall, Usage

from adapters.agent.scripted.script import (
    CHAT_TEXT_PLAN,
    EPIC_TITLE,
    FEATURE_TITLE,
    STAGE_TEXT_DONE,
    STAGE_TEXT_SCAN,
    TASK_TITLE,
)

_ID_RE = re.compile(r"id=(\w+)")


class ScriptedLLMAdapter:
    def __init__(self) -> None:
        self._emit = None

    def set_event_sink(self, emit) -> None:
        self._emit = emit

    def complete(self, request: LLMRequest) -> LLMResponse:
        tool_names = {t.name for t in request.tools}
        if "report" in tool_names:
            return self._run_stage()
        if "create_work_item" in tool_names:
            return self._lead_plan(request.messages)
        return self._plain_chat()

    def _run_stage(self) -> LLMResponse:
        if self._emit is not None:
            self._emit("text_block", {"text": STAGE_TEXT_SCAN})
            self._emit("tool_call", {"name": "edit_file", "input": {}})
            self._emit("tool_result", {"result": "ok"})
            self._emit("text_block", {"text": STAGE_TEXT_DONE})
        return LLMResponse(
            content=STAGE_TEXT_DONE,
            tool_calls=[ToolCall(id="report-1", name="report",
                                 args={"passed": True, "summary": "scripted stage ok"})],
            stop_reason="tool_use",
            usage=Usage(output_tokens=10),
        )

    def _lead_plan(self, messages: list[LLMMessage]) -> LLMResponse:
        results = [m for m in messages if m.role == MessageRole.TOOL]
        step = len(results)

        def tool(name: str, args: dict) -> LLMResponse:
            return LLMResponse(
                tool_calls=[ToolCall(id=f"c{step}", name=name, args=args)],
                stop_reason="tool_use", usage=Usage(output_tokens=5),
            )

        if step == 0:
            if self._emit is not None:
                self._emit("text_block", {"text": CHAT_TEXT_PLAN})
            return tool("list_board", {})
        if step == 1:
            return tool("create_work_item", {"kind": "epic", "title": EPIC_TITLE})
        if step == 2:
            return tool("create_work_item",
                        {"kind": "feature", "title": FEATURE_TITLE, "parent_id": self._last_id(results)})
        if step == 3:
            if self._emit is not None:
                self._emit("tool_call", {"name": "create_work_item", "input": {"title": TASK_TITLE}})
            return tool("create_work_item",
                        {"kind": "task", "title": TASK_TITLE, "parent_id": self._last_id(results)})
        if step == 4:
            return tool("propose_run", {"work_item_ids": [self._last_id(results)]})
        return LLMResponse(
            content=f"Created the plan and proposed a run on '{TASK_TITLE}'.",
            stop_reason="end_turn", usage=Usage(output_tokens=8),
        )

    @staticmethod
    def _last_id(results: list[LLMMessage]) -> str:
        m = _ID_RE.search(results[-1].content)
        return m.group(1) if m else ""

    def _plain_chat(self) -> LLMResponse:
        if self._emit is not None:
            self._emit("text_block", {"text": "Acknowledged."})
        return LLMResponse(content="Acknowledged.", stop_reason="end_turn", usage=Usage(output_tokens=4))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_scripted_adapter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/scripted projects/server/tests/adapters/agent/test_scripted_adapter.py
git commit -m "feat: ScriptedLLMAdapter for deterministic e2e agent behavior"
```

---

### Task 2: Wire `scripted` into `build_llm_adapter`

**Files:**
- Modify: `projects/server/src/adapters/agent/factory.py`
- Test: `projects/server/tests/adapters/agent/test_scripted_wiring.py`

**Interfaces:**
- Consumes: `ScriptedLLMAdapter` (Task 1); `build_llm_adapter(settings)`.
- Produces: `build_llm_adapter(settings)` returns a `ScriptedLLMAdapter` when `settings.llm_provider == "scripted"`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_scripted_wiring.py
from adapters.agent.factory import build_llm_adapter
from adapters.agent.scripted.adapter import ScriptedLLMAdapter
from interactors.api.settings import Settings


def test_build_llm_adapter_returns_scripted_for_scripted_provider():
    settings = Settings().model_copy(update={"llm_provider": "scripted"})
    assert isinstance(build_llm_adapter(settings), ScriptedLLMAdapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_scripted_wiring.py -v`
Expected: FAIL — `ValueError: unknown llm_provider: scripted`.

- [ ] **Step 3: Add the branch**

In `projects/server/src/adapters/agent/factory.py`, add near the top of `build_llm_adapter` (before the `claude`/`litellm` branches is fine):

```python
    if settings.llm_provider == "scripted":
        from adapters.agent.scripted.adapter import ScriptedLLMAdapter
        return ScriptedLLMAdapter()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_scripted_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Backend gate + commit**

```bash
cd /Users/noel/projects/naaf/.worktrees/e2e-playwright && make lint && make coverage
git add projects/server/src/adapters/agent/factory.py projects/server/tests/adapters/agent/test_scripted_wiring.py
git commit -m "feat: register scripted provider in build_llm_adapter"
```
Expected: lint clean; coverage ≥ 80%.

---

## Phase 2 — Playwright harness

### Task 3: Playwright install + config + a smoke spec

**Files:**
- Modify: `projects/ui/package.json` (add `@playwright/test` devDep + `"test:e2e": "playwright test"`)
- Create: `projects/ui/playwright.config.ts`
- Create: `projects/ui/e2e/support/globalSetup.ts`
- Create: `projects/ui/e2e/smoke.spec.ts`

**Interfaces:**
- Produces: a runnable Playwright project (`pnpm --dir projects/ui exec playwright test`) that, given an already-running stack, waits for API health then asserts the UI loads. `globalSetup` default-exports an async fn that polls `http://localhost:8000/health` until 200 (60s timeout, throws with a clear message otherwise).

- [ ] **Step 1: Install Playwright**

```bash
cd projects/ui && pnpm add -D @playwright/test && pnpm exec playwright install chromium
```
Add to `package.json` scripts: `"test:e2e": "playwright test"`.

- [ ] **Step 2: Write the config + globalSetup**

```ts
// projects/ui/playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/support/globalSetup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

```ts
// projects/ui/e2e/support/globalSetup.ts
export default async function globalSetup() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch("http://localhost:8000/health");
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(
    "e2e stack API not healthy at http://localhost:8000/health within 60s — " +
    "start it with `make e2e` (which boots the scripted stack).",
  );
}
```

- [ ] **Step 3: Write the smoke spec**

```ts
// projects/ui/e2e/smoke.spec.ts
import { expect, test } from "@playwright/test";

test("the UI shell loads against the live stack", async ({ page }) => {
  await page.goto("/");
  // The app shell renders a sidebar with PROJECTS; assert something stable is visible.
  await expect(page.getByText(/projects/i).first()).toBeVisible();
});
```

- [ ] **Step 4: Verify (requires the stack — deferred to Task 4)**

This spec is validated in Task 4 once `make e2e` can boot the stack. For now, only assert it type-checks:
Run: `cd projects/ui && pnpm exec tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/package.json projects/ui/pnpm-lock.yaml projects/ui/playwright.config.ts projects/ui/e2e
git commit -m "feat: playwright config + globalSetup + smoke spec"
```

---

### Task 4: `make e2e` boots the scripted stack + smoke passes

**Files:**
- Modify: `Makefile` (add `e2e-db`, `e2e` targets)
- Reference: the existing `dev` target's process orchestration.

**Interfaces:**
- Produces: `make e2e` — creates/migrates/seeds the `naaf_e2e` database, boots API + worker + UI (live-API) with the scripted env, waits, runs `playwright test`, and tears the stack down on exit. `make e2e-db` provisions just the e2e database (idempotent).

- [ ] **Step 1: Read the existing `dev` target**

Read the `dev`/`run`/`worker` recipes in `Makefile` to mirror their process spawning and the `-include .env` env handling. Note the ports (API :8000, UI :5173) and the `trap ... kill 0` pattern.

- [ ] **Step 2: Add the `e2e-db` + `e2e` targets**

Add to `Makefile` (model the spawn/trap on `dev`; adjust flag names to match the real recipes):

```makefile
NAAF_E2E_DB_URL ?= postgresql+psycopg://naaf:naaf@localhost:5432/naaf_e2e

.PHONY: e2e-db e2e
e2e-db:
	@docker compose up -d postgres
	@docker compose exec -T postgres psql -U naaf -tc "SELECT 1 FROM pg_database WHERE datname='naaf_e2e'" | grep -q 1 \
		|| docker compose exec -T postgres createdb -U naaf naaf_e2e
	@cd projects/server && naaf_db_url="$(NAAF_E2E_DB_URL)" uv run alembic upgrade head
	@cd projects/server && naaf_db_url="$(NAAF_E2E_DB_URL)" uv run python -m interactors.cli.seed

e2e: e2e-db
	@echo "▶ e2e — scripted stack (API :8000 · UI :5173) then Playwright"
	@bash -c 'trap "echo; echo ▲ stopping…; kill 0" EXIT INT TERM; \
	  export naaf_db_url="$(NAAF_E2E_DB_URL)" naaf_llm_provider=scripted naaf_agent_runtime=claude_code; \
	  ( cd projects/server && uv run uvicorn interactors.api.app:create_app --factory --port 8000 ) & \
	  ( cd projects/server && uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info ) & \
	  ( cd projects/ui && VITE_LIVE_API=true pnpm dev --port 5173 --strictPort ) & \
	  ( cd projects/ui && pnpm exec playwright test "$${E2E_SPEC:-}" ; echo "playwright exit=$$?" ) ; \
	  kill 0'
```

(If `docker compose exec postgres createdb` isn't available in the image, use `psql -U naaf -c "CREATE DATABASE naaf_e2e"`; adapt to what the repo's postgres service supports. Match the API/worker/UI spawn commands to the real `dev` recipe — provider/runtime env is the key addition.)

- [ ] **Step 3: Run the smoke spec end-to-end**

Run: `cd /Users/noel/projects/naaf/.worktrees/e2e-playwright && E2E_SPEC=e2e/smoke.spec.ts make e2e`
Expected: stack boots, `globalSetup` sees health, `smoke.spec.ts` passes (1 passed), stack tears down. Iterate on the recipe until green (the smoke test proves the harness before the journey depends on it).

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat: make e2e boots the scripted stack and runs playwright"
```

---

## Phase 3 — The journey

### Task 5: The streaming journey spec

**Files:**
- Create: `projects/ui/e2e/fixtures/scripted.ts`
- Create: `projects/ui/e2e/streaming-journey.spec.ts`

**Interfaces:**
- Consumes: the running scripted stack (Task 4); the scripted constants (must equal `script.py`).
- Produces: `streaming-journey.spec.ts` — the full journey with `expect.poll`/web-first assertions.

**Before writing:** open the app in the running stack and capture the real selectors/roles for: creating a project, opening the project chat, the composer input + send, the board task card, the Start-run button, the run monitor, and the `ActivityFeed`/`activity-feed`/`activity-typing` test ids. Use `data-testid`s where they exist (`activity-feed`, `activity-typing` from the streaming feature); add stable `data-testid`s to the UI where a robust selector is missing (small, additive — commit them with this task).

- [ ] **Step 1: Write the shared fixture**

```ts
// projects/ui/e2e/fixtures/scripted.ts
// MUST mirror projects/server/src/adapters/agent/scripted/script.py
export const TASK_TITLE = "E2E streaming task";
export const EPIC_TITLE = "E2E Epic";
export const FEATURE_TITLE = "E2E Feature";
export const STAGE_TEXT_SCAN = "Scanning the repository…";
export const STAGE_TEXT_DONE = "Changes applied.";
export const CHAT_TEXT_PLAN = "Planning the work…";
```

- [ ] **Step 2: Write the journey spec**

```ts
// projects/ui/e2e/streaming-journey.spec.ts
import { expect, test } from "@playwright/test";
import { STAGE_TEXT_SCAN, STAGE_TEXT_DONE, TASK_TITLE } from "./fixtures/scripted";

test("chat → lead creates a task → run streams multi-stage output", async ({ page }) => {
  // 1. Create a project with full_auto autonomy (no gates) via the API, then open the board.
  const res = await page.request.post("http://localhost:8000/projects", {
    data: { name: "E2E Project", autonomyLevel: "full_auto" },
  });
  expect(res.ok()).toBeTruthy();
  await page.goto("/");

  // 2. Open the project chat and send a message. (Selectors: adjust to the real UI in Step-before.)
  await page.getByText("E2E Project").click();
  await page.getByTestId("thread-composer-input").fill("Build a notes feature");
  await page.getByTestId("thread-composer-send").click();

  // 3. Chat → lead streams: the activity feed shows the scripted planning text.
  await expect(page.getByTestId("activity-feed")).toContainText("Planning the work…", { timeout: 20_000 });

  // 4. Lead creates the task — it appears on the board.
  await expect
    .poll(async () => (await page.request.get("http://localhost:8000/work-items")).ok(), { timeout: 20_000 })
    .toBeTruthy();
  await expect(page.getByText(TASK_TITLE)).toBeVisible({ timeout: 20_000 });

  // 5. Open the task and start a run.
  await page.getByText(TASK_TITLE).click();
  await page.getByTestId("start-run-button").click();

  // 6. Run streams multi-stage output into the run monitor.
  await expect(page.getByTestId("activity-feed")).toContainText(STAGE_TEXT_SCAN, { timeout: 30_000 });
  await expect(page.getByTestId("activity-feed")).toContainText(STAGE_TEXT_DONE, { timeout: 30_000 });

  // 7. Run advances through stages (full_auto → no gates). Assert a later stage / completion signal.
  await expect(page.getByTestId("run-status")).toContainText(/verify|done|complete|learn/i, { timeout: 45_000 });
});
```

- [ ] **Step 3: Run the journey**

Run: `cd /Users/noel/projects/naaf/.worktrees/e2e-playwright && E2E_SPEC=e2e/streaming-journey.spec.ts make e2e`
Expected: 1 passed. Iterate on selectors/timeouts using the Playwright trace (`playwright show-trace`) until green. Where a selector is fragile, add a `data-testid` in the UI component and commit it with this task.

- [ ] **Step 4: Full e2e run + commit**

Run: `cd /Users/noel/projects/naaf/.worktrees/e2e-playwright && make e2e`
Expected: smoke + journey both pass.

```bash
git add projects/ui/e2e projects/ui/src   # include any data-testid additions
git commit -m "feat: streaming journey e2e (chat → task → run → streamed output)"
```

---

## Phase 4 — CI + real-claude smoke

### Task 6: CI workflow, `@real` smoke variant, docs

**Files:**
- Create: `.github/workflows/e2e.yml`
- Modify: `projects/ui/e2e/streaming-journey.spec.ts` (add a `@real`-tagged loosened variant OR a `test.describe` guarded by `process.env.NAAF_E2E_REAL`)
- Modify: `Makefile` (`e2e-real` target)
- Create/modify: `docs/e2e.md`

**Interfaces:**
- Produces: a CI job that boots the scripted stack and runs the suite (excluding `@real`), uploading Playwright artifacts on failure; a `make e2e-real` that runs the loosened smoke against `naaf_llm_provider=claude_cli`.

- [ ] **Step 1: Add the CI workflow**

```yaml
# .github/workflows/e2e.yml
name: e2e
on: [pull_request, workflow_dispatch]
jobs:
  playwright:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_USER: naaf, POSTGRES_PASSWORD: naaf, POSTGRES_DB: naaf }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U naaf" --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "pnpm", cache-dependency-path: projects/ui/pnpm-lock.yaml }
      - run: uv sync
        working-directory: projects/server
      - run: pnpm install
        working-directory: projects/ui
      - run: pnpm exec playwright install --with-deps chromium
        working-directory: projects/ui
      - name: Run e2e (scripted)
        run: make e2e
        env:
          CI: "true"
          NAAF_E2E_DB_URL: postgresql+psycopg://naaf:naaf@localhost:5432/naaf_e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: playwright-report, path: projects/ui/playwright-report, retention-days: 7 }
```

(The `make e2e` recipe's `docker compose up -d postgres` step is a no-op/limited in CI where Postgres is a service container — guard `e2e-db` so it uses the service DB when `CI=true`, e.g. skip `docker compose up` and run `alembic upgrade` + seed directly against `NAAF_E2E_DB_URL`. Adjust the target so both local and CI work.)

- [ ] **Step 2: Add the `@real` smoke variant**

In `streaming-journey.spec.ts`, add a guarded loosened test:

```ts
const REAL = process.env.NAAF_E2E_REAL === "1";
test.describe("@real real-claude smoke", () => {
  test.skip(!REAL, "set NAAF_E2E_REAL=1 with naaf_llm_provider=claude_cli to run");
  test("a task is created and some output streams (loose assertions)", async ({ page }) => {
    // Same flow, but assert only: a work item was created + the activity feed became non-empty.
    // (No exact-string assertions — real output varies.)
  });
});
```

Add `Makefile` `e2e-real` that boots with `naaf_llm_provider=claude_cli` + a real token and runs only `--grep @real`.

- [ ] **Step 3: Write the docs**

Create `docs/e2e.md`: what the suite covers, `make e2e` (scripted, CI), `make e2e-real` (subscription smoke), how the `ScriptedLLMAdapter` fakes only the model, and how to view a failing trace (`pnpm --dir projects/ui exec playwright show-report`).

- [ ] **Step 4: Verify + commit**

Run locally once more: `make e2e` (green). Push the branch and let the `e2e` workflow run on the PR; confirm it's green (or iterate).

```bash
git add .github/workflows/e2e.yml projects/ui/e2e/streaming-journey.spec.ts Makefile docs/e2e.md
git commit -m "ci: e2e workflow + real-claude smoke variant + docs"
```

---

## Final verification (before PR)

- [ ] `make e2e` green locally (smoke + journey).
- [ ] Backend `make lint` + `make coverage` (≥80%) green.
- [ ] `pnpm --dir projects/ui exec tsc --noEmit` clean.
- [ ] CI `e2e` workflow green on the PR.
- [ ] Push + open PR (focused title, summary, test plan).

## Self-review notes (addressed)

- **Spec coverage:** scripted adapter fakes only the model (T1) + wired via provider (T2); full-stack harness + `make e2e` (T4) with health-gated globalSetup (T3); journey covers chat→lead-stream→task-created→multi-stage run stream (T5); CI + `@real` smoke + docs (T6). `full_auto` autonomy removes gates so the run streams all stages (Global Constraints + T5 step 1).
- **Determinism:** shared constants in `script.py`/`scripted.ts` (Global Constraints); adapter is pure-scripted (T1). Drift between the two fails the journey's `toContainText`.
- **Type consistency:** scripted strings identical across `script.py` (T1) and `scripted.ts` (T5); the adapter's `complete`/`set_event_sink` match the real `LLMAdapter` port + the `set_event_sink` passthrough the runtime/orchestrator already call.
- **Deferred (out of scope, per spec):** gate approve/reject flows, visual-regression, multi-browser, parallel runs.
- **Known soft spots the implementer resolves live:** exact UI selectors/`data-testid`s (T5 discovery step); the `make e2e` recipe's exact spawn commands (mirror `dev`, T4); the CI vs local Postgres-provisioning branch in `e2e-db` (T6 step 1).
- **Repo/PROVISION/PR-stage risk (T5):** the scripted e2e has no real git repo or `gh` token, so the PROVISION and PR stages must not require one. Create the e2e project with **no `repo_url`** so PROVISION takes its skip path, and scope the journey's assertions to streaming through the **PLAN → IMPLEMENT → VERIFY** stages (step 6 asserts the scripted stage text; step 7 asserts the run reaches `verify`/`running`, not necessarily full completion through PR/LEARN). If PROVISION or a later stage errors without a repo, the implementer either (a) confirms the skip path keeps the run streaming to VERIFY, or (b) seeds a throwaway local repo path — resolved by running the journey and reading the run events. Do NOT loosen the streamed-text assertions; only the terminal-state assertion may target VERIFY instead of LEARN.
