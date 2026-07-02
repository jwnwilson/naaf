# A5 — LLM-Agnostic Agent Runtime + LLM Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NAAF's run pipeline execute real work — a domain-owned, LLM-agnostic agent loop that drives all six stages (`PLAN → PROVISION → IMPLEMENT → VERIFY → PR → LEARN`) against a local workspace, reaching the model only through a single `LLMAdapter` port (Claude by default, LiteLLM optionally).

**Architecture:** A pure **domain `AgentRuntime`** (`LlmAgentRuntime`) owns the reason→call-tool→observe loop. It depends on two ports: `LLMAdapter` (inference: `complete(LLMRequest) -> LLMResponse`) and `Workspace` (filesystem/shell/git). Concrete adapters (`ClaudeLLMAdapter`, `LiteLLMAdapter`, `LocalWorkspace`) live in `adapters/agent/`. The A3 worker wires the chosen adapters and passes a typed `StageContext` into `run_stage`. No provider-specific code touches the loop.

**Tech Stack:** Python 3.12, `uv`, Pydantic v2, pytest + pytest-cov, the `anthropic` SDK (Phase 3), the LiteLLM gateway (Phase 7). Follows the existing hexagonal layout in `projects/server/src`.

## Global Constraints

- **Python ≥ 3.12**, package manager **`uv`**; run tests with `uv run pytest` from repo root.
- **Domain purity:** code under `domain/` has no I/O and no imports from `adapters/` or `interactors/` — it depends only on port Protocols defined in `domain/`.
- **Immutability:** Pydantic models updated via `model_copy(update={...})`, never mutated in place.
- **Entity/DTO base:** domain models subclass `pydantic.BaseModel`; entities subclass `domain.base.Entity` (gives `id`/`created_at`/`updated_at`). IDs are 32-char UUID hex (`domain.base.new_id`).
- **Naming:** settings use the `naaf_` env prefix (pydantic-settings). Constants `UPPER_SNAKE_CASE`, classes `PascalCase`, functions/vars `snake_case`.
- **Lint:** `ruff` (line-length **100**, rules `E,F,I,UP,B`); type-check with `mypy` (`uv run mypy`). Keep files < 400 lines where practical.
- **Testing:** TDD — failing test first, AAA structure, descriptive behavior names. **`make coverage` enforces an 80% gate.** No network in unit tests; the real-key test is opt-in and excluded from the gate.
- **Workflow:** each task is committed with a `<type>: <description>` message; each **phase** ships as its own reviewed PR from a worktree off `origin/main`. Never commit to `main`.
- **Source of truth:** `docs/superpowers/specs/2026-07-02-a5-llm-agnostic-agent-runtime-design.md`.

---

## File Structure

**New (domain — pure):**
- `domain/agent/llm.py` — `LLMAdapter` port + DTOs (`LLMRequest`, `LLMResponse`, `LLMMessage`, `MessageRole`, `ToolCall`, `ToolResult`, `ToolSpec`, `Usage`).
- `domain/agent/workspace.py` — `Workspace` port + `CommandResult`.
- `domain/agent/tools.py` — `TOOL_SPECS` (schemas) + `execute_tool(workspace, call) -> ToolResult` dispatcher.
- `domain/agent/context.py` — `StageContext`, `WorkItemBrief`.
- `domain/agent/prompts.py` — per-stage system prompt + instruction builders.
- `domain/agent/runtime.py` — **modify**: keep `AgentEvent`/`StageResult`/`StageOutcome`/`AgentRuntime` protocol; add concrete `LlmAgentRuntime`.

**New (adapters — I/O):**
- `adapters/agent/llm/__init__.py`, `fake.py` (`FakeLLMAdapter`), `claude.py` (`ClaudeLLMAdapter`), `litellm.py` (`LiteLLMAdapter`).
- `adapters/agent/workspace/__init__.py`, `local.py` (`LocalWorkspace`).

**Modify (interactors / config):**
- `interactors/api/settings.py` — add A5 settings (provider, keys, aliases, limits).
- `interactors/worker/celery_app.py` — `_deps()` selects the runtime + adapters.
- `interactors/worker/handlers.py` — build `StageContext` (coordinated with A3).

**Tests mirror `src/` under `projects/server/tests/`.**

---

## Phase 1 — Ports, DTOs, tools, FakeLLMAdapter (foundation)

Pure-domain contracts + the offline test double. Nothing is wired; no behavior changes. Ships as PR "feat: A5 agent ports + DTOs + fake LLM adapter".

### Task 1: LLM port + DTOs (`domain/agent/llm.py`)

**Files:**
- Create: `projects/server/src/domain/agent/llm.py`
- Test: `projects/server/tests/domain/agent/test_llm.py`

**Interfaces:**
- Produces: `MessageRole(StrEnum)`; `ToolCall(id:str, name:str, args:dict)`; `ToolResult(tool_call_id:str, content:str, is_error:bool=False)`; `ToolSpec(name:str, description:str, parameters:dict)`; `Usage(input_tokens:int=0, output_tokens:int=0)`; `LLMMessage(role:MessageRole, content:str="", tool_calls:list[ToolCall]=[], tool_call_id:str|None=None)`; `LLMRequest(model:str, system:str, messages:list[LLMMessage], tools:list[ToolSpec]=[], max_tokens:int=8192)`; `LLMResponse(content:str="", tool_calls:list[ToolCall]=[], stop_reason:str="end_turn", usage:Usage=Usage())`; `class LLMAdapter(Protocol): def complete(self, request: LLMRequest) -> LLMResponse: ...`

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_llm.py
from domain.agent.llm import (
    LLMMessage, LLMRequest, LLMResponse, MessageRole, ToolCall, Usage,
)


def test_llm_request_defaults_are_empty_and_immutable():
    req = LLMRequest(model="opus", system="be terse", messages=[])
    assert req.tools == []
    assert req.max_tokens == 8192
    updated = req.model_copy(update={"max_tokens": 100})
    assert req.max_tokens == 8192 and updated.max_tokens == 100  # original unchanged


def test_llm_response_carries_tool_calls_and_usage():
    resp = LLMResponse(
        tool_calls=[ToolCall(id="t1", name="bash", args={"cmd": "ls"})],
        stop_reason="tool_use",
        usage=Usage(input_tokens=10, output_tokens=3),
    )
    assert resp.tool_calls[0].name == "bash"
    assert resp.usage.output_tokens == 3


def test_message_role_values():
    assert MessageRole.TOOL == "tool"
    msg = LLMMessage(role=MessageRole.USER, content="hi")
    assert msg.tool_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/agent/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.agent.llm'`

- [ ] **Step 3: Write minimal implementation**

```python
# projects/server/src/domain/agent/llm.py
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    id: str
    name: str
    args: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's arguments


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMMessage(BaseModel):
    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # set when role == TOOL


class LLMRequest(BaseModel):
    model: str
    system: str = ""
    messages: list[LLMMessage] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    max_tokens: int = 8192


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = Field(default_factory=Usage)


class LLMAdapter(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
```

Also create empty `projects/server/src/domain/agent/__init__.py` if missing and `projects/server/tests/domain/agent/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/agent/test_llm.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/agent/llm.py projects/server/tests/domain/agent/
git commit -m "feat: add LLMAdapter port and inference DTOs"
```

### Task 2: Workspace port (`domain/agent/workspace.py`)

**Files:**
- Create: `projects/server/src/domain/agent/workspace.py`
- Test: `projects/server/tests/domain/agent/test_workspace_port.py`

**Interfaces:**
- Produces: `CommandResult(exit_code:int, stdout:str, stderr:str)`; `class Workspace(Protocol)` with `read(path:str)->str`, `write(path:str, content:str)->None`, `edit(path:str, old:str, new:str)->None`, `grep(pattern:str, path:str|None)->str`, `bash(cmd:str, timeout_s:int)->CommandResult`.

- [ ] **Step 1: Write the failing test** (a trivial in-memory stub proves the Protocol shape)

```python
# projects/server/tests/domain/agent/test_workspace_port.py
from domain.agent.workspace import CommandResult, Workspace


class _StubWorkspace:
    def read(self, path): return "content"
    def write(self, path, content): return None
    def edit(self, path, old, new): return None
    def grep(self, pattern, path=None): return ""
    def bash(self, cmd, timeout_s): return CommandResult(exit_code=0, stdout="ok", stderr="")


def test_stub_satisfies_workspace_protocol():
    ws: Workspace = _StubWorkspace()
    assert ws.bash("ls", 5).exit_code == 0
    assert ws.read("x") == "content"
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest projects/server/tests/domain/agent/test_workspace_port.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# projects/server/src/domain/agent/workspace.py
from typing import Protocol

from pydantic import BaseModel


class CommandResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class Workspace(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def edit(self, path: str, old: str, new: str) -> None: ...
    def grep(self, pattern: str, path: str | None) -> str: ...
    def bash(self, cmd: str, timeout_s: int) -> CommandResult: ...
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add Workspace port"`

### Task 3: Tool specs + dispatcher (`domain/agent/tools.py`)

**Files:**
- Create: `projects/server/src/domain/agent/tools.py`
- Test: `projects/server/tests/domain/agent/test_tools.py`

**Interfaces:**
- Consumes: `Workspace`, `CommandResult` (Task 2); `ToolCall`, `ToolResult`, `ToolSpec` (Task 1).
- Produces: `TOOL_SPECS: list[ToolSpec]`; `execute_tool(workspace: Workspace, call: ToolCall) -> ToolResult`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_tools.py
from domain.agent.llm import ToolCall
from domain.agent.tools import TOOL_SPECS, execute_tool
from domain.agent.workspace import CommandResult


class _RecordingWorkspace:
    def __init__(self): self.calls = []
    def read(self, path): self.calls.append(("read", path)); return "file body"
    def write(self, path, content): self.calls.append(("write", path, content))
    def edit(self, path, old, new): self.calls.append(("edit", path, old, new))
    def grep(self, pattern, path=None): return "match"
    def bash(self, cmd, timeout_s): return CommandResult(exit_code=0, stdout="done", stderr="")


def test_tool_specs_cover_the_toolset():
    names = {t.name for t in TOOL_SPECS}
    assert names == {"read_file", "write_file", "edit_file", "grep", "bash"}


def test_execute_read_file_returns_contents():
    ws = _RecordingWorkspace()
    result = execute_tool(ws, ToolCall(id="c1", name="read_file", args={"path": "a.py"}))
    assert result.tool_call_id == "c1"
    assert result.content == "file body"
    assert result.is_error is False


def test_execute_bash_reports_nonzero_as_error():
    class Failing(_RecordingWorkspace):
        def bash(self, cmd, timeout_s):
            return CommandResult(exit_code=1, stdout="", stderr="boom")
    result = execute_tool(Failing(), ToolCall(id="c2", name="bash", args={"cmd": "false"}))
    assert result.is_error is True
    assert "boom" in result.content


def test_execute_unknown_tool_is_error():
    result = execute_tool(_RecordingWorkspace(), ToolCall(id="c3", name="nope", args={}))
    assert result.is_error is True
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# projects/server/src/domain/agent/tools.py
from domain.agent.llm import ToolCall, ToolResult, ToolSpec
from domain.agent.workspace import Workspace

BASH_TIMEOUT_S = 120

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(name="read_file", description="Read a file from the workspace.",
             parameters={"type": "object", "properties": {"path": {"type": "string"}},
                         "required": ["path"]}),
    ToolSpec(name="write_file", description="Create or overwrite a file.",
             parameters={"type": "object",
                         "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                         "required": ["path", "content"]}),
    ToolSpec(name="edit_file", description="Replace an exact string in a file.",
             parameters={"type": "object",
                         "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                        "new": {"type": "string"}},
                         "required": ["path", "old", "new"]}),
    ToolSpec(name="grep", description="Search the workspace with a regex.",
             parameters={"type": "object",
                         "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                         "required": ["pattern"]}),
    ToolSpec(name="bash", description="Run a shell command in the workspace.",
             parameters={"type": "object", "properties": {"cmd": {"type": "string"}},
                         "required": ["cmd"]}),
]


def execute_tool(workspace: Workspace, call: ToolCall) -> ToolResult:
    def ok(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text)

    def err(text: str) -> ToolResult:
        return ToolResult(tool_call_id=call.id, content=text, is_error=True)

    a = call.args
    try:
        if call.name == "read_file":
            return ok(workspace.read(a["path"]))
        if call.name == "write_file":
            workspace.write(a["path"], a["content"])
            return ok(f"wrote {a['path']}")
        if call.name == "edit_file":
            workspace.edit(a["path"], a["old"], a["new"])
            return ok(f"edited {a['path']}")
        if call.name == "grep":
            return ok(workspace.grep(a["pattern"], a.get("path")))
        if call.name == "bash":
            r = workspace.bash(a["cmd"], BASH_TIMEOUT_S)
            body = f"exit={r.exit_code}\n{r.stdout}\n{r.stderr}".strip()
            return err(body) if r.exit_code != 0 else ok(body)
        return err(f"unknown tool: {call.name}")
    except KeyError as e:
        return err(f"missing argument {e} for tool {call.name}")
    except Exception as e:  # tool errors are recoverable — report, don't crash the loop
        return err(f"{type(e).__name__}: {e}")
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add agent tool specs and dispatcher"`

### Task 4: FakeLLMAdapter (`adapters/agent/llm/fake.py`)

**Files:**
- Create: `projects/server/src/adapters/agent/llm/__init__.py`, `projects/server/src/adapters/agent/llm/fake.py`
- Test: `projects/server/tests/adapters/agent/llm/test_fake.py` (+ `__init__.py`)

**Interfaces:**
- Consumes: `LLMAdapter`, `LLMRequest`, `LLMResponse` (Task 1).
- Produces: `FakeLLMAdapter(scripted: list[LLMResponse])` — returns each scripted response in order per `complete` call; records the requests it received on `.requests`; raises `IndexError` if over-consumed.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/llm/test_fake.py
from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.llm import LLMRequest, LLMResponse, ToolCall


def test_fake_returns_scripted_responses_in_order():
    fake = FakeLLMAdapter([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="bash", args={"cmd": "ls"})],
                    stop_reason="tool_use"),
        LLMResponse(content="done", stop_reason="end_turn"),
    ])
    r1 = fake.complete(LLMRequest(model="m", messages=[]))
    r2 = fake.complete(LLMRequest(model="m", messages=[]))
    assert r1.stop_reason == "tool_use"
    assert r2.content == "done"
    assert len(fake.requests) == 2
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# projects/server/src/adapters/agent/llm/fake.py
from domain.agent.llm import LLMRequest, LLMResponse


class FakeLLMAdapter:
    """Scripted LLMAdapter for offline tests. Returns responses in order."""

    def __init__(self, scripted: list[LLMResponse]):
        self._scripted = list(scripted)
        self._i = 0
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        resp = self._scripted[self._i]
        self._i += 1
        return resp
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add FakeLLMAdapter test double"`

### Task 5: StageContext (`domain/agent/context.py`)

**Files:**
- Create: `projects/server/src/domain/agent/context.py`
- Test: `projects/server/tests/domain/agent/test_context.py`

**Interfaces:**
- Consumes: `AgentDefinition` (`domain.team`), `Stage` (`domain.runs.run`).
- Produces: `WorkItemBrief(title:str, body:str="", acceptance_criteria:list[str]=[])`; `StageContext(run_id:str, role:str, stage:Stage, workspace_path:str, work_item:WorkItemBrief, agent:AgentDefinition, verify_attempts:int=0, artifacts:dict[str,str]={})`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_context.py
from domain.agent.context import StageContext, WorkItemBrief
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def test_stage_context_holds_the_run_inputs():
    agent = AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND,
                            model_alias="sonnet")
    ctx = StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/ws",
        work_item=WorkItemBrief(title="Add X", acceptance_criteria=["does X"]),
        agent=agent,
    )
    assert ctx.stage is Stage.IMPLEMENT
    assert ctx.agent.model_alias == "sonnet"
    assert ctx.verify_attempts == 0
    assert ctx.artifacts == {}
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# projects/server/src/domain/agent/context.py
from pydantic import BaseModel, Field

from domain.runs.run import Stage
from domain.team import AgentDefinition


class WorkItemBrief(BaseModel):
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)


class StageContext(BaseModel):
    run_id: str
    role: str
    stage: Stage
    workspace_path: str
    work_item: WorkItemBrief
    agent: AgentDefinition
    verify_attempts: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add StageContext contract"`

- [ ] **Phase 1 gate:** `uv run pytest projects/server/tests/domain/agent projects/server/tests/adapters/agent -q` all green; `uv run ruff check` and `uv run mypy` clean. Open PR "feat: A5 agent ports, DTOs, tools, fake LLM adapter". Merge before Phase 2.

---

## Phase 2 — The domain agent loop (`LlmAgentRuntime`) + prompts

The LLM-agnostic heart. Ships as PR "feat: A5 domain agent loop".

### Task 6: Stage prompts (`domain/agent/prompts.py`)

**Files:**
- Create: `projects/server/src/domain/agent/prompts.py`
- Test: `projects/server/tests/domain/agent/test_prompts.py`

**Interfaces:**
- Consumes: `StageContext` (Task 5), `Stage` (`domain.runs.run`).
- Produces: `system_prompt(ctx: StageContext) -> str`; `stage_instruction(ctx: StageContext) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_prompts.py
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.prompts import stage_instruction, system_prompt
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def _ctx(stage, persona="You are a senior engineer."):
    return StageContext(
        run_id="r", role="engineer", stage=stage, workspace_path="/ws",
        work_item=WorkItemBrief(title="Add feature", body="details",
                                acceptance_criteria=["it works"]),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND,
                              persona_prompt=persona),
    )


def test_system_prompt_includes_persona():
    assert "senior engineer" in system_prompt(_ctx(Stage.IMPLEMENT))


def test_instruction_is_stage_specific():
    assert "plan.md" in stage_instruction(_ctx(Stage.PLAN)).lower()
    assert "test" in stage_instruction(_ctx(Stage.VERIFY)).lower()


def test_instruction_includes_acceptance_criteria():
    assert "it works" in stage_instruction(_ctx(Stage.IMPLEMENT))
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# projects/server/src/domain/agent/prompts.py
from domain.agent.context import StageContext
from domain.runs.run import Stage

_BASE = (
    "You are an autonomous software engineer working in a git workspace. "
    "Use the provided tools to inspect and change files and run commands. "
    "When you have completed the stage, stop calling tools and give a one-line summary."
)

_STAGE_INSTRUCTIONS = {
    Stage.PLAN: "Read the ticket and relevant files, then write an implementation plan to plan.md.",
    Stage.PROVISION: "Ensure the workspace is on a fresh agent branch and note anything needed.",
    Stage.IMPLEMENT: "Implement the ticket. Edit files, run the build, and commit your changes.",
    Stage.VERIFY: ("You are QA in a fresh context. Run the tests, lint, and build, and check the "
                   "acceptance criteria. Report whether the work is done."),
    Stage.PR: "Push the branch and open a pull request summarizing the plan, changes, and QA result.",
    Stage.LEARN: "Distill durable lessons from this run into a short memory diff and commit it.",
}


def system_prompt(ctx: StageContext) -> str:
    persona = ctx.agent.persona_prompt or f"You are the {ctx.role} agent."
    return f"{persona}\n\n{_BASE}"


def stage_instruction(ctx: StageContext) -> str:
    wi = ctx.work_item
    criteria = "\n".join(f"- {c}" for c in wi.acceptance_criteria) or "- (none given)"
    return (
        f"# Ticket: {wi.title}\n\n{wi.body}\n\n"
        f"## Acceptance criteria\n{criteria}\n\n"
        f"## Your task ({ctx.stage.value})\n{_STAGE_INSTRUCTIONS[ctx.stage]}"
    )
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add per-stage agent prompts"`

### Task 7: `LlmAgentRuntime` loop (`domain/agent/runtime.py`)

**Files:**
- Modify: `projects/server/src/domain/agent/runtime.py` (append the concrete class; keep existing `AgentEvent`/`StageResult`/`StageOutcome`/`AgentRuntime`)
- Test: `projects/server/tests/domain/agent/test_llm_runtime.py`

**Interfaces:**
- Consumes: `LLMAdapter`, `LLMRequest`, `LLMResponse`, `LLMMessage`, `MessageRole`, `ToolCall` (Task 1); `Workspace` (Task 2); `TOOL_SPECS`, `execute_tool` (Task 3); `StageContext` (Task 5); `system_prompt`, `stage_instruction` (Task 6); `AgentEvent`, `StageResult`, `StageOutcome` (existing).
- Produces: `LlmAgentRuntime(llm: LLMAdapter, workspace: Workspace, max_iterations: int = 25)` with `run_stage(role: str, stage: Stage, ctx: StageContext) -> StageOutcome`.

**Loop contract (design §4.1):** build the request from the context; call `llm.complete`; for each `ToolCall`, run `execute_tool` and append a `TOOL` message; loop until `stop_reason != "tool_use"` or `max_iterations` reached; emit an `AgentEvent` per assistant message and per tool call; derive `StageResult` — `passed=False` only if the loop exhausted iterations without finishing, otherwise `passed=True` with the final assistant text as the summary. (VERIFY's richer verdict via a `report` tool is Task 15.)

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_llm_runtime.py
from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.llm import LLMResponse, ToolCall
from domain.agent.runtime import LlmAgentRuntime
from domain.agent.workspace import CommandResult
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


class _Workspace:
    def __init__(self): self.written = {}
    def read(self, path): return self.written.get(path, "")
    def write(self, path, content): self.written[path] = content
    def edit(self, path, old, new): self.written[path] = self.written[path].replace(old, new)
    def grep(self, pattern, path=None): return ""
    def bash(self, cmd, timeout_s): return CommandResult(exit_code=0, stdout="ok", stderr="")


def _ctx(stage=Stage.IMPLEMENT):
    return StageContext(
        run_id="r", role="engineer", stage=stage, workspace_path="/ws",
        work_item=WorkItemBrief(title="Add X"),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND,
                              model_alias="sonnet", token_limit=1000),
    )


def test_runtime_executes_tool_calls_then_finishes():
    ws = _Workspace()
    llm = FakeLLMAdapter([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="write_file",
                    args={"path": "a.py", "content": "x=1"})], stop_reason="tool_use"),
        LLMResponse(content="Implemented X.", stop_reason="end_turn"),
    ])
    runtime = LlmAgentRuntime(llm=llm, workspace=ws)
    outcome = runtime.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    assert ws.written["a.py"] == "x=1"
    assert outcome.result.passed is True
    assert "Implemented X." in outcome.result.summary
    assert any("write_file" in e.message for e in outcome.events)


def test_runtime_passes_role_model_alias_to_the_request():
    llm = FakeLLMAdapter([LLMResponse(content="done", stop_reason="end_turn")])
    LlmAgentRuntime(llm=llm, workspace=_Workspace()).run_stage("engineer", Stage.PLAN, _ctx(Stage.PLAN))
    assert llm.requests[0].model == "sonnet"
    assert llm.requests[0].max_tokens == 1000


def test_runtime_fails_when_iterations_exhausted():
    # always asks for another tool call -> never terminates within the cap
    loop = [LLMResponse(tool_calls=[ToolCall(id="t", name="bash", args={"cmd": "ls"})],
                        stop_reason="tool_use") for _ in range(5)]
    runtime = LlmAgentRuntime(llm=FakeLLMAdapter(loop), workspace=_Workspace(), max_iterations=3)
    outcome = runtime.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    assert outcome.result.passed is False
    assert "iteration" in outcome.result.summary.lower()
```

- [ ] **Step 2: Run to verify it fails** — `... test_llm_runtime.py -v` → FAIL (`ImportError: cannot import name 'LlmAgentRuntime'`).

- [ ] **Step 3: Implement (append to `domain/agent/runtime.py`)**

```python
# add these imports at the top of domain/agent/runtime.py
from domain.agent.context import StageContext
from domain.agent.llm import (
    LLMAdapter, LLMMessage, LLMRequest, MessageRole,
)
from domain.agent.prompts import stage_instruction, system_prompt
from domain.agent.tools import TOOL_SPECS, execute_tool
from domain.agent.workspace import Workspace

# ... existing AgentEvent / StageResult / StageOutcome / AgentRuntime stay ...


class LlmAgentRuntime:
    """LLM-agnostic agent loop. Reaches the model only through the LLMAdapter port."""

    def __init__(self, llm: LLMAdapter, workspace: Workspace, max_iterations: int = 25):
        self._llm = llm
        self._workspace = workspace
        self._max_iterations = max_iterations

    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome:
        events: list[AgentEvent] = []
        messages = [LLMMessage(role=MessageRole.USER, content=stage_instruction(ctx))]
        request = LLMRequest(
            model=ctx.agent.model_alias or "default",
            system=system_prompt(ctx),
            messages=messages,
            tools=TOOL_SPECS,
            max_tokens=ctx.agent.token_limit,
        )
        final_text = ""
        for _ in range(self._max_iterations):
            response = self._llm.complete(request.model_copy(update={"messages": messages}))
            if response.content:
                final_text = response.content
                events.append(AgentEvent(message=response.content))
            if response.stop_reason != "tool_use" or not response.tool_calls:
                return StageOutcome(events=events,
                                    result=StageResult(passed=True, summary=final_text or "ok"))
            # execute tools, append assistant + tool messages, loop
            messages = [*messages, LLMMessage(role=MessageRole.ASSISTANT,
                                              content=response.content,
                                              tool_calls=response.tool_calls)]
            for call in response.tool_calls:
                events.append(AgentEvent(message=f"tool:{call.name} {call.args}"))
                tr = execute_tool(self._workspace, call)
                messages.append(LLMMessage(role=MessageRole.TOOL, content=tr.content,
                                           tool_call_id=call.id))
        return StageOutcome(events=events,
                            result=StageResult(passed=False,
                                               summary="stopped: max iterations reached"))
```

- [ ] **Step 4: Run to verify it passes** — all 3 tests PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add LlmAgentRuntime domain agent loop"`

- [ ] **Phase 2 gate:** full suite green (`make coverage` ≥ 80%), `make lint` clean. PR "feat: A5 domain agent loop". Merge before Phase 3.

---

## Phase 3 — `ClaudeLLMAdapter` (default provider) + settings

Ships as PR "feat: A5 Claude LLM adapter". Adds the `anthropic` dependency and translates neutral DTOs ↔ the Anthropic Messages API (patterns per the claude-api reference: `client.messages.create`, tools, `tool_use`/`tool_result`, `usage`).

### Task 8: add `anthropic` dependency + A5 settings

**Files:**
- Modify: `projects/server/pyproject.toml` (add `"anthropic>=0.40"` to `dependencies`)
- Modify: `projects/server/src/interactors/api/settings.py`
- Test: `projects/server/tests/interactors/test_settings.py` (create if absent)

**Interfaces:**
- Produces on `Settings`: `llm_provider:str="claude"`, `anthropic_api_key:str=""`, `anthropic_base_url:str=""`, `litellm_base_url:str=""`, `litellm_key:str=""`, `model_aliases:dict[str,str]={}`, `agent_max_iterations:int=25`, `agent_bash_timeout_s:int=120`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/interactors/test_settings.py
from interactors.api.settings import Settings


def test_llm_defaults_to_claude():
    s = Settings()
    assert s.llm_provider == "claude"
    assert s.agent_max_iterations == 25


def test_naaf_env_prefix_overrides(monkeypatch):
    monkeypatch.setenv("naaf_llm_provider", "litellm")
    monkeypatch.setenv("naaf_agent_max_iterations", "5")
    s = Settings()
    assert s.llm_provider == "litellm"
    assert s.agent_max_iterations == 5
```

- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** — add fields to the existing `Settings` model:

```python
# in projects/server/src/interactors/api/settings.py, add to the Settings class body
    llm_provider: str = "claude"          # "claude" | "litellm"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""          # blank = Anthropic default
    litellm_base_url: str = ""
    litellm_key: str = ""
    model_aliases: dict[str, str] = {}    # alias -> concrete model id (claude adapter)
    agent_max_iterations: int = 25
    agent_bash_timeout_s: int = 120
```

Add `"anthropic>=0.40"` to `projects/server/pyproject.toml` dependencies, then `uv sync`.

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add A5 LLM settings and anthropic dependency"`

### Task 9: `ClaudeLLMAdapter`

**Files:**
- Create: `projects/server/src/adapters/agent/llm/claude.py`
- Test: `projects/server/tests/adapters/agent/llm/test_claude.py`

**Interfaces:**
- Consumes: `LLMAdapter`, `LLMRequest`, `LLMResponse`, `LLMMessage`, `MessageRole`, `ToolCall`, `ToolSpec`, `Usage` (Task 1).
- Produces: `ClaudeLLMAdapter(api_key:str, base_url:str="", aliases:dict[str,str]|None=None, client=None)`; `complete(request) -> LLMResponse`. `client` is injectable for tests (a fake exposing `.messages.create(...)`).

Translation rules: `LLMRequest.tools` → Anthropic tool dicts `{name, description, input_schema}`; neutral messages → Anthropic `messages` (ASSISTANT with `tool_calls` → content blocks incl. `tool_use`; TOOL → a user message with a `tool_result` block); resolve `request.model` via `aliases` (fallback to the string as-is); read back `response.content` text blocks, `tool_use` blocks → `ToolCall`, `stop_reason`, and `usage`.

- [ ] **Step 1: Write the failing test** (fake Anthropic client — no network)

```python
# projects/server/tests/adapters/agent/llm/test_claude.py
from types import SimpleNamespace

from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolSpec


class _FakeMessages:
    def __init__(self, reply): self._reply = reply; self.seen = None
    def create(self, **kwargs): self.seen = kwargs; return self._reply


class _FakeClient:
    def __init__(self, reply): self.messages = _FakeMessages(reply)


def _reply(blocks, stop="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=7, output_tokens=2))


def test_translates_text_reply_and_usage():
    reply = _reply([SimpleNamespace(type="text", text="hello")])
    adapter = ClaudeLLMAdapter(api_key="k", aliases={"sonnet": "claude-sonnet-4-6"},
                               client=_FakeClient(reply))
    resp = adapter.complete(LLMRequest(model="sonnet", system="s",
                                       messages=[LLMMessage(role=MessageRole.USER, content="hi")]))
    assert resp.content == "hello"
    assert resp.usage.input_tokens == 7
    assert adapter._client.messages.seen["model"] == "claude-sonnet-4-6"  # alias resolved


def test_translates_tool_use_block_into_toolcall():
    reply = _reply([SimpleNamespace(type="tool_use", id="tu1", name="bash", input={"cmd": "ls"})],
                   stop="tool_use")
    adapter = ClaudeLLMAdapter(api_key="k", client=_FakeClient(reply))
    resp = adapter.complete(LLMRequest(model="claude-opus-4-8", system="",
                                       messages=[], tools=[ToolSpec(name="bash",
                                       description="d", parameters={"type": "object"})]))
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].name == "bash" and resp.tool_calls[0].args == {"cmd": "ls"}
    assert adapter._client.messages.seen["tools"][0]["name"] == "bash"
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** (real client built lazily; injectable for tests)

```python
# projects/server/src/adapters/agent/llm/claude.py
from domain.agent.llm import (
    LLMMessage, LLMRequest, LLMResponse, MessageRole, ToolCall, Usage,
)

_MAX_TOKENS_CAP = 16000


class ClaudeLLMAdapter:
    def __init__(self, api_key: str, base_url: str = "",
                 aliases: dict[str, str] | None = None, client=None):
        self._aliases = aliases or {}
        if client is not None:
            self._client = client
        else:
            import anthropic
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.Anthropic(**kwargs)

    def complete(self, request: LLMRequest) -> LLMResponse:
        reply = self._client.messages.create(
            model=self._aliases.get(request.model, request.model),
            max_tokens=min(request.max_tokens, _MAX_TOKENS_CAP),
            system=request.system,
            tools=[{"name": t.name, "description": t.description,
                    "input_schema": t.parameters} for t in request.tools],
            messages=[self._to_anthropic(m) for m in request.messages],
        )
        text = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
        tool_calls = [ToolCall(id=b.id, name=b.name, args=dict(b.input))
                      for b in reply.content if getattr(b, "type", "") == "tool_use"]
        return LLMResponse(
            content=text, tool_calls=tool_calls, stop_reason=reply.stop_reason,
            usage=Usage(input_tokens=reply.usage.input_tokens,
                        output_tokens=reply.usage.output_tokens),
        )

    @staticmethod
    def _to_anthropic(m: LLMMessage) -> dict:
        if m.role is MessageRole.TOOL:
            return {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}]}
        if m.role is MessageRole.ASSISTANT and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                       for c in m.tool_calls]
            return {"role": "assistant", "content": blocks}
        role = "assistant" if m.role is MessageRole.ASSISTANT else "user"
        return {"role": role, "content": m.content}
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add ClaudeLLMAdapter (Anthropic SDK)"`

### Task 10: opt-in real-key integration test

**Files:**
- Modify: `pyproject.toml` — register a marker under `[tool.pytest.ini_options]`: `markers = ["integration: hits a real LLM; opt-in"]`.
- Create: `projects/server/tests/integration/test_claude_live.py` (+ `__init__.py`)

- [ ] **Step 1: Write the test (skips unless a key is set)**

```python
# projects/server/tests/integration/test_claude_live.py
import os

import pytest

from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("naaf_anthropic_api_key"), reason="no key")
def test_real_claude_completes_a_prompt():
    adapter = ClaudeLLMAdapter(api_key=os.environ["naaf_anthropic_api_key"],
                               aliases={"opus": "claude-opus-4-8"})
    resp = adapter.complete(LLMRequest(model="opus", system="Reply with the single word OK.",
                                       messages=[LLMMessage(role=MessageRole.USER, content="go")],
                                       max_tokens=16))
    assert "OK" in resp.content.upper()
```

- [ ] **Step 2: Verify it is excluded from the gate** — `uv run pytest -m "not integration" -q` collects without running it; `make coverage` unaffected.
- [ ] **Step 3: Commit** — `git commit -m "test: add opt-in Claude live integration test"`

- [ ] **Phase 3 gate:** `make coverage` (excludes integration) ≥ 80%, `make lint` clean. PR "feat: A5 Claude LLM adapter + settings".

---

## Phase 4 — LocalWorkspace + worker wiring + StageContext (end-to-end PLAN/IMPLEMENT/VERIFY)

Ships as PR "feat: A5 local workspace + wire real runtime". **Coordinate the `handlers.py` edit with the A3 owner** (design §10).

### Task 11: `LocalWorkspace` adapter

**Files:**
- Create: `projects/server/src/adapters/agent/workspace/__init__.py`, `projects/server/src/adapters/agent/workspace/local.py`
- Test: `projects/server/tests/adapters/agent/workspace/test_local.py` (+ `__init__.py`)

**Interfaces:**
- Consumes: `Workspace`, `CommandResult` (Task 2).
- Produces: `LocalWorkspace(root: str | Path)`; implements the `Workspace` port confined to `root`; `bash` runs via `subprocess.run(cwd=root, timeout=timeout_s)`.

- [ ] **Step 1: Write the failing test** (uses `tmp_path`)

```python
# projects/server/tests/adapters/agent/workspace/test_local.py
import pytest

from adapters.agent.workspace.local import LocalWorkspace


def test_write_read_edit_roundtrip(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("a.txt", "hello world")
    assert ws.read("a.txt") == "hello world"
    ws.edit("a.txt", "world", "there")
    assert ws.read("a.txt") == "hello there"


def test_bash_runs_in_root_and_captures_exit(tmp_path):
    ws = LocalWorkspace(tmp_path)
    ws.write("x.txt", "hi")
    r = ws.bash("ls", 10)
    assert r.exit_code == 0 and "x.txt" in r.stdout


def test_path_escape_is_rejected(tmp_path):
    ws = LocalWorkspace(tmp_path)
    with pytest.raises(ValueError):
        ws.read("../secret")
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# projects/server/src/adapters/agent/workspace/local.py
import subprocess
from pathlib import Path

from domain.agent.workspace import CommandResult


class LocalWorkspace:
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        p = (self._root / path).resolve()
        if not p.is_relative_to(self._root):
            raise ValueError(f"path escapes workspace: {path}")
        return p

    def read(self, path: str) -> str:
        return self._resolve(path).read_text()

    def write(self, path: str, content: str) -> None:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def edit(self, path: str, old: str, new: str) -> None:
        p = self._resolve(path)
        text = p.read_text()
        if text.count(old) != 1:
            raise ValueError(f"expected exactly one occurrence of old text in {path}")
        p.write_text(text.replace(old, new))

    def grep(self, pattern: str, path: str | None) -> str:
        target = self._resolve(path) if path else self._root
        r = subprocess.run(["grep", "-rn", pattern, str(target)],
                           capture_output=True, text=True)
        return r.stdout

    def bash(self, cmd: str, timeout_s: int) -> CommandResult:
        try:
            r = subprocess.run(cmd, shell=True, cwd=self._root, capture_output=True,
                               text=True, timeout=timeout_s)
            return CommandResult(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(exit_code=124, stdout="", stderr=f"timeout after {timeout_s}s")
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add LocalWorkspace adapter"`

### Task 12: adapter/runtime factory + worker wiring (`celery_app.py`)

**Files:**
- Create: `projects/server/src/adapters/agent/factory.py`
- Modify: `projects/server/src/interactors/worker/celery_app.py` (`_deps()`)
- Test: `projects/server/tests/adapters/agent/test_factory.py`

**Interfaces:**
- Produces: `build_llm_adapter(settings) -> LLMAdapter` (returns `ClaudeLLMAdapter` for `llm_provider=="claude"`, `LiteLLMAdapter` for `"litellm"` — the latter arrives in Phase 7; raise `ValueError` for unknown until then); `build_runtime(settings, workspace_root: str) -> AgentRuntime` (returns `FakeAgentRuntime` when `agent_runtime=="fake"`, else `LlmAgentRuntime(build_llm_adapter(settings), LocalWorkspace(workspace_root), settings.agent_max_iterations)`).

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_factory.py
from adapters.agent.factory import build_llm_adapter, build_runtime
from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.runtime import LlmAgentRuntime


class _S:  # minimal settings stand-in
    llm_provider = "claude"; anthropic_api_key = "k"; anthropic_base_url = ""
    model_aliases = {"opus": "claude-opus-4-8"}; agent_max_iterations = 9
    agent_runtime = "claude_code"


def test_build_llm_adapter_returns_claude(monkeypatch):
    monkeypatch.setattr(ClaudeLLMAdapter, "__init__",
                        lambda self, **kw: setattr(self, "_client", object()) or None)
    assert isinstance(build_llm_adapter(_S()), ClaudeLLMAdapter)


def test_build_runtime_wires_local_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(ClaudeLLMAdapter, "__init__",
                        lambda self, **kw: setattr(self, "_client", object()) or None)
    rt = build_runtime(_S(), str(tmp_path))
    assert isinstance(rt, LlmAgentRuntime)
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** the factory; then update `_deps()` to call `build_runtime(...)` instead of hardcoding `FakeAgentRuntime()`. Add `agent_runtime: str = "claude_code"` to `Settings`.

```python
# projects/server/src/adapters/agent/factory.py
from adapters.agent.llm.claude import ClaudeLLMAdapter
from adapters.agent.workspace.local import LocalWorkspace
from domain.agent.runtime import AgentRuntime, LlmAgentRuntime


def build_llm_adapter(settings):
    if settings.llm_provider == "claude":
        return ClaudeLLMAdapter(api_key=settings.anthropic_api_key,
                                base_url=settings.anthropic_base_url,
                                aliases=settings.model_aliases)
    if settings.llm_provider == "litellm":
        from adapters.agent.llm.litellm import LiteLLMAdapter  # Phase 7
        return LiteLLMAdapter(base_url=settings.litellm_base_url, key=settings.litellm_key)
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")


def build_runtime(settings, workspace_root: str) -> AgentRuntime:
    if getattr(settings, "agent_runtime", "claude_code") == "fake":
        from adapters.agent.runtime.fake import FakeAgentRuntime
        return FakeAgentRuntime()
    return LlmAgentRuntime(build_llm_adapter(settings), LocalWorkspace(workspace_root),
                           settings.agent_max_iterations)
```

- [ ] **Step 4: Run to verify it passes.** Keep A3 pipeline tests green by setting `naaf_agent_runtime=fake` in the test env/fixtures.
- [ ] **Step 5: Commit** — `git commit -m "feat: wire runtime factory into worker deps"`

### Task 13: build `StageContext` in `handlers.py` (coordinated with A3)

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` — replace the inline `{"verify_attempts": …}` passed to `runtime.run_stage` with a `StageContext` built from the run, its work item (via `ctx.work_items.read`), and the acting role's `AgentDefinition` (looked up from the team; add an `agent_definitions` repo handle to `HandlerContext` or resolve from a passed map).
- Test: `projects/server/tests/interactors/worker/test_stage_context.py`

**Interfaces:**
- Consumes: `StageContext`, `WorkItemBrief` (Task 5); `_run_stage_inline` currently calls `ctx.runtime.run_stage(role, stage, {"verify_attempts": run.verify_attempts})`.
- Produces: a `build_stage_context(ctx, run, role, stage, workspace_root) -> StageContext` helper in `handlers.py`, used by `_run_stage_inline`.

- [ ] **Step 1: Write the failing test** — construct a `HandlerContext` with fakes; assert `build_stage_context` returns a `StageContext` whose `work_item.title`, `agent.model_alias`, and `verify_attempts` match the seeded run/work-item/agent.

```python
# projects/server/tests/interactors/worker/test_stage_context.py
from domain.agent.context import StageContext
from domain.runs.run import Stage
# (build a HandlerContext with in-memory fakes exposing .work_items.read and an
#  agent-definition lookup; seed a WorkItem "Add login" and a BACKEND AgentDefinition
#  with model_alias="sonnet"; then:)
def test_build_stage_context_populates_from_run(handler_ctx, run):
    from interactors.worker.handlers import build_stage_context
    sc = build_stage_context(handler_ctx, run, "engineer", Stage.IMPLEMENT, "/ws")
    assert isinstance(sc, StageContext)
    assert sc.work_item.title == "Add login"
    assert sc.agent.model_alias == "sonnet"
    assert sc.verify_attempts == run.verify_attempts
```

- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** `build_stage_context` + swap the `run_stage(...)` call to pass it. Extend `HandlerContext` with an `agent_definitions` handle (resolve role→AgentDefinition for the run's team); default to a synthesized `AgentDefinition` when none is configured so fakes stay simple.
- [ ] **Step 4: Run to verify it passes** — this file plus the existing worker/pipeline tests (with `FakeAgentRuntime`) stay green.
- [ ] **Step 5: Commit** — `git commit -m "feat: build StageContext in run handlers"`

- [ ] **Phase 4 gate:** `make coverage` ≥ 80%, `make lint` clean. Manual smoke (documented in the PR): with `naaf_llm_provider=claude` + key, `docker compose up -d postgres`, `make worker`, start a run on a fixture work-item, watch real PLAN/IMPLEMENT/VERIFY events. PR "feat: A5 local workspace + real runtime wiring".

---

## Phase 5 — PROVISION + PR stages (real, local)

Ships as PR "feat: A5 PROVISION and PR stages". Uses the same loop/tools; adds workspace provisioning and PR capture. **No sandbox / GitHub App — operator git/`gh` creds** (design §6).

### Task 14: workspace provisioning for PROVISION

**Files:**
- Create: `projects/server/src/adapters/agent/provision.py`
- Test: `projects/server/tests/adapters/agent/test_provision.py`

**Interfaces:**
- Consumes: `Project.repo` (a GitHub URL or local path).
- Produces: `provision_workspace(repo: str, run_id: str, root: str) -> str` — clones/copies the repo into `<root>/<run_id>`, checks out a new `agent/<run_id>` branch, returns the workspace path. Idempotent (re-use if it exists).

- [ ] **Step 1: Write the failing test** — with a local git repo in `tmp_path` as `repo`, assert `provision_workspace` produces a directory on branch `agent/<run_id>` containing the repo's files. (Use `git init` + a commit in the fixture.)
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** using `subprocess` (`git clone <repo> <dest>` for URLs/paths, then `git -C <dest> checkout -b agent/<run_id>`).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add local workspace provisioning"`

### Task 15: PROVISION + PR handler stages

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` — `_run_stage_inline` for `Stage.PROVISION` calls `provision_workspace(...)` (records the path on the run/ctx); the loop then runs against that workspace. `Stage.PR` runs the lead loop whose instruction/tools push the branch and `gh pr create`; capture the printed PR URL into a `RunEvent` payload.
- Modify: `projects/server/src/domain/agent/prompts.py` — flesh the PR-stage instruction to require `gh pr create` and to print the URL as the final line.
- Test: `projects/server/tests/interactors/worker/test_provision_pr.py` (drive with `FakeLLMAdapter` scripting the tool calls; a fake workspace records the `bash` commands and returns a fake PR URL).

- [ ] **Step 1–5:** standard TDD cycle — failing test asserting (a) PROVISION sets a workspace on branch `agent/<run_id>`, (b) PR stage emits a `RunEvent` carrying the captured PR URL. Implement, verify, commit `feat: run PROVISION and PR stages`.

- [ ] **Phase 5 gate:** `make coverage` ≥ 80%, `make lint` clean. PR "feat: A5 PROVISION + PR stages (local)".

---

## Phase 6 — LEARN stage (real memory-diff commit)

Ships as PR "feat: A5 LEARN stage". A curator-role loop distills the run into a memory diff committed to project memory.

### Task 16: LEARN handler stage + curator prompt

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` — `Stage.LEARN` runs a curator loop (role `"curator"`, cheap alias) whose instruction is to append durable lessons to the project memory file (`CLAUDE.md`/`AGENTS.md`) and commit them on the agent branch.
- Modify: `projects/server/src/domain/agent/prompts.py` — curator instruction: read `progress.md`/diff, propose a small memory addition, write + `git commit` it; keep it under a size cap.
- Test: `projects/server/tests/interactors/worker/test_learn.py` — with `FakeLLMAdapter` scripting a `write_file` + `bash("git commit …")`, assert LEARN produces a memory-file change and a passing `StageResult`.

- [ ] **Step 1–5:** standard TDD cycle. Implement, verify, commit `feat: run LEARN stage (memory diff commit)`.

- [ ] **Phase 6 gate:** `make coverage` ≥ 80%, `make lint` clean. PR "feat: A5 LEARN stage".

---

## Phase 7 — `LiteLLMAdapter` (provider-swap route)

Ships as PR "feat: A5 LiteLLM adapter". Proves provider-agnosticism: switching `naaf_llm_provider=litellm` runs the identical runtime through the gateway.

### Task 17: `LiteLLMAdapter`

**Files:**
- Create: `projects/server/src/adapters/agent/llm/litellm.py`
- Test: `projects/server/tests/adapters/agent/llm/test_litellm.py`
- Modify: `docker-compose.yml` (add a version-pinned `litellm` service on `:4000`) + `docs/deployment.md` note; `factory.build_llm_adapter` already branches on `"litellm"`.

**Interfaces:**
- Consumes: `LLMAdapter`, DTOs (Task 1).
- Produces: `LiteLLMAdapter(base_url:str, key:str, client=None)`; `complete(request) -> LLMResponse`. LiteLLM exposes an OpenAI-compatible `/chat/completions`; translate neutral DTOs ↔ OpenAI `messages`/`tools`/`tool_calls`, mapping `finish_reason=="tool_calls"` → `stop_reason="tool_use"` and reading `usage`.

- [ ] **Step 1: Write the failing test** — fake OpenAI-compatible client returning a `tool_calls` choice; assert the adapter yields a `ToolCall` and `stop_reason="tool_use"`, and that neutral `TOOL` messages serialize to `{role:"tool", tool_call_id, content}`.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** the translation (mirrors `ClaudeLLMAdapter` but OpenAI shape). Per-run budget-key minting is a follow-up hook (leave a `budget_key: str | None = None` parameter wired but optional).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add LiteLLMAdapter (gateway route)"`

- [ ] **Phase 7 gate:** `make coverage` ≥ 80%, `make lint` clean. PR "feat: A5 LiteLLM adapter + compose service". Update `docs/project-history.md`: A5 shipped (LLM-agnostic runtime, Claude + LiteLLM adapters, all six stages real & local).

---

## Self-Review

- **Spec coverage:** domain `AgentRuntime` (Task 7) ✓; `LLMAdapter` port + DTOs (Task 1) ✓; `ClaudeLLMAdapter` (Task 9) ✓; `LiteLLMAdapter` (Task 17) ✓; `Workspace` port + `LocalWorkspace` (Tasks 2, 11) ✓; tool set (Task 3) ✓; `StageContext` + A3 coordination (Tasks 5, 13) ✓; per-role model via `model_alias` (Task 7 test) ✓; all six stages real (Tasks 7 PLAN/IMPLEMENT/VERIFY, 14–15 PROVISION/PR, 16 LEARN) ✓; settings/provider selection (Tasks 8, 12) ✓; FakeLLMAdapter unit path + opt-in live test (Tasks 4, 10) ✓; `usage` captured for A5d (Task 9) ✓.
- **Placeholder scan:** foundational tasks (1–12) carry complete code; the stage-handler tasks (13–16) and Phase 7 give exact files/interfaces + representative code with the standard TDD cycle — no "TBD"/"implement later".
- **Type consistency:** `ToolCall(id,name,args)`, `ToolResult(tool_call_id,content,is_error)`, `LLMResponse(content,tool_calls,stop_reason,usage)`, `Workspace.bash(cmd,timeout_s)->CommandResult`, `LlmAgentRuntime(llm,workspace,max_iterations)`, `build_runtime(settings,workspace_root)`, `StageContext(run_id,role,stage,workspace_path,work_item,agent,verify_attempts,artifacts)` are used consistently across tasks.
