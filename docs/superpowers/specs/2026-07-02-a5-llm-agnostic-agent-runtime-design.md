# A5 — LLM-Agnostic Agent Runtime + LLM Adapter — Design

**Date:** 2026-07-02
**Status:** Draft design, pending user review
**Milestone:** A5 (real agent execution)
**Builds on:** A1 control plane + A2 UI + A3 run pipeline (Local-First bus, `Run` model, stage state machine, `AgentRuntime` port, `FakeAgentRuntime`) — merged / in progress on `main`.

## 1. Problem & goal

A3 gives NAAF a durable run pipeline driven by **scripted fake agents** — the stages advance, but no model does any thinking or touches any code. A5 makes the agent **real**: a stage is executed by an actual LLM running an agent loop (reason → call tools → edit files → run commands → repeat) against the run's workspace.

The defining constraint from the user: **the agent-runtime logic is our own, and it is LLM-service-agnostic.** We own the loop. The model is reached only through a single port (`LLMAdapter`), so the same runtime works against Claude (default) or, via LiteLLM, any other provider — with no change to the runtime logic.

### Success criterion

> With `naaf_llm_provider=claude` and an API key configured, starting a run drives the **full `PLAN → PROVISION → IMPLEMENT → VERIFY → PR → LEARN` pipeline** via a **domain `AgentRuntime`** that calls an LLM through the `LLMAdapter` port and uses a tool set to read/edit files and run commands in a local workspace: it clones the project repo, creates an `agent/<task>` branch, edits code, runs tests, opens a real PR via `gh`, and commits a memory diff — streaming real agent logs to the Agent-Monitor throughout. Switching `naaf_llm_provider=litellm` routes the identical runtime through the LiteLLM gateway with no code change. `make coverage` (80%) + `make lint` green; the loop is fully unit-tested with a `FakeLLMAdapter` (no network).

## 2. Scope

**In:**
- A **domain `AgentRuntime`** object holding the agent loop (LLM-agnostic; depends only on ports).
- The **`LLMAdapter` port** (inference-level: `complete(LLMRequest) -> LLMResponse`) + request/response DTOs, in `domain/agent/`.
- Two adapters: **`ClaudeLLMAdapter`** (Anthropic SDK, default) and **`LiteLLMAdapter`** (LiteLLM gateway). Provider chosen by `naaf_llm_provider`.
- A **tool set** (read / write / edit / grep / bash / git) defined in the domain and executed through a **`Workspace` port**, with a **local workspace adapter**.
- **`StageContext`** — the typed contract the worker passes into `run_stage` (workspace, work item, resolved `AgentDefinition`, prior artifacts). Coordinated with A3.
- **Per-role model selection** via `AgentDefinition.model_alias`.
- **All six stages real, run locally:** `PLAN`, `IMPLEMENT`, `VERIFY` (LLM-driven agent loops); plus **`PROVISION`** (clone the project repo + create the `agent/<task>` branch), **`PR`** (push the branch + `gh pr create` with the operator's GitHub credentials), and **`LEARN`** (a curator-role loop that distills the run into a memory-diff commit).
- **`FakeLLMAdapter`** (scripted completions) for unit-testing the real loop; one **opt-in** real-key integration test outside the coverage gate.
- Settings (`naaf_` prefix) for provider, keys, base URLs, model-alias map.

**Out (later milestones):**
- **Sandbox isolation & hardening, egress proxy, GitHub App identity, credential broker** → **A4**. A5 runs the loop **locally in the worker** against a local workspace with the operator's existing git/`gh` credentials; PROVISION/PR are real but unsandboxed.
- **The memory-diff review UI and role/project memory scopes** → **A6**. A5's `LEARN` produces a real memory-diff commit; the reviewable-diff UI and richer memory model come later.
- Live token/cost accounting and budget **enforcement** → **A5d** (A5 records `usage` from `LLMResponse`; enforcement is later).
- Architect cross-model review, parallel engineers, RAG → **Phase B**. A5 uses the A1 default team (lead + engineer + QA).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Who owns the agent loop | **We do** — a domain `AgentRuntime` object, not Claude Code / the Claude Agent SDK | Only way the runtime can be genuinely LLM-agnostic and work through LiteLLM to any provider |
| LLM access | **Single `LLMAdapter` port**, inference-level (`complete`) | One seam for all model access; runtime stays agnostic; provider is a config choice |
| Default provider | **`claude`** (`ClaudeLLMAdapter`, Anthropic SDK) | The "Claude SDK" lives inside the adapter, not the loop |
| Multi-provider | **`LiteLLMAdapter`** routes through the LiteLLM gateway | Alias routing, budgets, and non-Claude providers with zero runtime change |
| Per-role model | Resolve `AgentDefinition.model_alias` → `LLMRequest.model` | Config already carries it; lead=frontier, engineers=mid, QA=cheap |
| Tool execution | Domain tool set + **`Workspace` port**; local adapter now | Keeps the loop pure/testable; sandbox swap-in is an A4 adapter change |
| Test double | **`FakeLLMAdapter`** (scripted completions) injected into the real runtime | Higher fidelity than a scripted runtime; exercises the actual loop offline |
| Stage scope | **All six stages real**, run locally | Deliver an end-to-end run (clone → branch → code → test → PR → memory) now; the loop + Workspace port make git/`gh` just tools |
| PROVISION / PR | **Real but unsandboxed** — local git clone + `gh pr create` with operator creds | Full pipeline value now; the A4 sandbox/GitHub App is a `Workspace`/identity swap later, no loop change |
| LEARN | **Real memory-diff commit** now; review UI + memory scopes deferred to A6 | The curator loop is just another role; the reviewable-diff UX is separable |
| Sandbox | **Deferred to A4** — run locally in the worker | A5's novelty is the agnostic loop; isolation is orthogonal |

## 4. Architecture

Hexagonal, per `docs/architecture.md`: the loop is pure domain logic; every I/O boundary (model, filesystem, shell, git) is a port with an adapter.

```
interactors/worker  ─ builds StageContext, selects adapters, calls run_stage ─┐
                                                                              ▼
domain/agent/AgentRuntime.run_stage(ctx: StageContext) -> StageOutcome   (pure, agnostic)
   │  builds LLMRequest (system=persona, messages, tools)
   │  loop: LLMAdapter.complete(req) → handle tool_calls → Workspace tools → append results → repeat
   │  until stop_reason == "end_turn" (or a stage-specific "report" tool) → StageResult(passed, summary)
   ├─ port  LLMAdapter.complete(LLMRequest) -> LLMResponse
   │        ├ adapters/agent/llm/claude.py   ClaudeLLMAdapter   (Anthropic SDK)   ← default
   │        └ adapters/agent/llm/litellm.py  LiteLLMAdapter     (LiteLLM gateway)
   └─ port  Workspace  (read/write/edit/grep/bash/git)
            └ adapters/agent/workspace/local.py  LocalWorkspace  (cwd-scoped)
```

### 4.1 Domain `AgentRuntime` (`domain/agent/runtime.py`)

A concrete domain object implementing the existing `AgentRuntime` protocol (`run_stage(role, stage, ctx) -> StageOutcome`), constructed with an `LLMAdapter` and a `Workspace`. It is the agent loop:

1. Build an `LLMRequest`: `system` = role persona + stage instructions, `messages` = ticket/context/prior-artifacts, `tools` = the tool schemas the stage allows (filtered by `capability_grants`), `model` = the role's resolved alias, `max_tokens`/token cap from `AgentDefinition.token_limit`.
2. Call `LLMAdapter.complete(req)`.
3. If the response contains tool calls, execute each via the `Workspace` port, append `tool_result`s, and loop (bounded by a max-iterations guard).
4. Emit an `AgentEvent` per model message / tool call for the live log.
5. Terminate on `end_turn` or an explicit `report` tool call; derive `StageResult(passed, summary)` — for `VERIFY`, `passed` is the agent's structured verdict (tests/lint/criteria).

The loop contains **no** provider-specific code. `FakeAgentRuntime` remains for cheap pipeline tests; the real runtime is what production wires.

### 4.2 `LLMAdapter` port + DTOs (`domain/agent/llm.py`)

Defined in the domain so the runtime imports no adapter:
```python
class Role(StrEnum): SYSTEM; USER; ASSISTANT; TOOL
class ToolCall(BaseModel): id: str; name: str; args: dict
class LLMMessage(BaseModel): role: Role; content: str; tool_calls: list[ToolCall]; tool_call_id: str | None
class LLMRequest(BaseModel): model: str; system: str; messages: list[LLMMessage]; tools: list[ToolSpec]; max_tokens: int
class LLMResponse(BaseModel): content: str; tool_calls: list[ToolCall]; stop_reason: str; usage: Usage
class LLMAdapter(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
```
The DTOs are a **neutral, provider-agnostic shape**. Each adapter translates to/from its wire format. `Usage` (input/output tokens) is carried through for A5d.

### 4.3 LLM adapters (`adapters/agent/llm/`)

- **`ClaudeLLMAdapter`** (default) — uses the `anthropic` SDK (`messages.create`), model `claude-opus-4-8` family via alias map, adaptive thinking, streaming for large outputs, typed-exception handling. Maps neutral DTOs ↔ Anthropic content blocks / `tool_use` / `tool_result`.
- **`LiteLLMAdapter`** — points at `naaf_litellm_base_url` with `naaf_litellm_key`; resolves `model_alias` → concrete model server-side; mints the **per-run budget key** (spec §6/§9 PROVISION) when available. Speaks LiteLLM's OpenAI-compatible or Anthropic-passthrough shape.

Selection: `naaf_llm_provider` (`claude` | `litellm`) chooses the adapter in the worker's `_deps()`.

### 4.4 Tools + `Workspace` port (`domain/agent/tools.py`, port in `domain/agent/`)

Tool schemas (`ToolSpec`) are domain constants: `read_file`, `write_file`, `edit_file`, `grep`, `bash`, `git`. Execution goes through:
```python
class Workspace(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def edit(self, path: str, old: str, new: str) -> None: ...
    def grep(self, pattern: str, path: str | None) -> str: ...
    def bash(self, cmd: str, timeout_s: int) -> CommandResult: ...
```
`LocalWorkspace` (adapter) confines all paths to the run's workspace root (path-traversal guarded) and runs `bash` with a timeout. Git and `gh` are reached via `bash` for now. The A4 sandbox is a future `Workspace` implementation — the loop is unchanged.

### 4.5 `StageContext` — the A3-coordinated contract (`domain/agent/context.py`)

Today `run_stage` receives `{"verify_attempts": …}`. A real run needs a typed context:
```python
class StageContext(BaseModel):
    run_id: str; role: str; stage: Stage
    workspace_path: str
    work_item: WorkItemBrief          # title, body, acceptance_criteria
    agent: AgentDefinition            # persona, model_alias, capability_grants, token_limit
    verify_attempts: int
    artifacts: dict[str, str]         # e.g. {"plan.md": "...", "progress.md": "..."}
```
Populating it is an edit to A3's `interactors/worker/handlers.py`. **Coordination:** define `StageContext` in `domain/agent/` as the shared contract; `FakeAgentRuntime` ignores the extra fields (stays green); the handler edit is made with the A3 owner to avoid collision.

### 4.6 Wiring (`interactors/worker/celery_app.py`)

`_deps()` becomes: read `naaf_llm_provider` → construct the `LLMAdapter` → construct `LocalWorkspace` per run → construct the real `AgentRuntime(llm, workspace)` (or `FakeAgentRuntime` when `naaf_agent_runtime=fake`, retained for pipeline tests). Single contained change.

## 5. Per-role model selection

Each `AgentDefinition` already carries `role`, `persona_prompt`, `model_alias`, `capability_grants`, `token_limit`. `run_stage` resolves the acting role's `AgentDefinition` (from `StageContext.agent`) and sets `LLMRequest.model = model_alias`. Under `claude`, the adapter maps the alias to an Anthropic model ID; under `litellm`, the gateway resolves it. Default aliases: lead/architect → frontier, engineers → mid, QA → cheap.

## 6. Stage → agent-loop mapping (all six real in A5)

| Stage | Role | Loop goal | Terminal signal |
|---|---|---|---|
| PLAN | lead | Read ticket + context → write `plan.md` in workspace | `report` tool / `end_turn` |
| PROVISION | lead | Ensure the run workspace (local clone/worktree of `Project.repo`) + create `agent/<task>` branch | branch ready |
| IMPLEMENT | engineer | Edit files, run build, commit to `agent/<task>` branch | `end_turn` with clean build |
| VERIFY | qa | Fresh context (ticket + diff only): run tests/lint, check acceptance criteria | `report(passed, summary)` |
| PR | lead | Push branch; `gh pr create` with plan/changes/QA summary (operator creds) | PR URL captured |
| LEARN | curator | Distill the run into a memory diff; commit it to project memory (`CLAUDE.md`/`docs/adr/`) | `end_turn` |

**Local-execution notes:** PROVISION clones/worktrees the project repo under the worker's workspace root (no sandbox — A4). PR uses the operator's `gh`/GitHub token (no GitHub App — A4). LEARN writes a real memory-diff commit; the reviewable-diff UI is A6. The `Workspace` port makes git/`gh` ordinary tools, so swapping in the A4 sandbox/identity later needs no loop change.

## 7. Config & settings (`naaf_` prefix)

`naaf_llm_provider` (`claude` default), `naaf_anthropic_api_key`, `naaf_litellm_base_url`, `naaf_litellm_key`, `naaf_model_aliases` (alias → concrete model for the `claude` adapter), `naaf_agent_max_iterations`, `naaf_agent_bash_timeout_s`. Provider/API keys are validated at worker startup; missing key for the selected provider fails fast.

## 8. Testing

- **Unit (in the 80% gate):** the real `AgentRuntime` loop driven by a **`FakeLLMAdapter`** that returns scripted `LLMResponse`s (including tool-call sequences) → asserts tool dispatch, iteration bounds, event emission, and `StageResult`. `LocalWorkspace` tested against a temp dir. Adapter DTO-translation tested with recorded fixtures (no network).
- **Integration (opt-in, outside the gate):** a `@pytest.mark.integration` test that runs one real stage against a fixture repo with a real key, skipped unless `naaf_anthropic_api_key` is set.
- Existing A3 pipeline tests keep using `FakeAgentRuntime`.
- TDD throughout: failing test first, AAA, behavior names.

## 9. Error handling & conventions (carried)

Immutable Pydantic (`model_copy`); typed exceptions from the SDK mapped to domain errors; a hung/looping agent is bounded by `naaf_agent_max_iterations` and per-`bash` timeout; tool errors return `is_error` results the model can recover from; no secrets in logs or transcripts; `bash`/path inputs are treated as untrusted and confined to the workspace root.

## 10. A3 coordination (integration risk)

The two touch points with the in-progress A3 work are (1) expanding the `run_stage` `ctx` into `StageContext` (edit in `handlers.py`) and (2) selecting the real runtime in `_deps()`. Both are additive: `StageContext` is defined here as the contract, `FakeAgentRuntime` tolerates the richer ctx, and the handler/deps edits are landed in coordination with the A3 owner so neither branch clobbers the other.

## 11. Implementation phasing (for the plan)

1. **Ports + DTOs + FakeLLMAdapter** — `LLMAdapter`/`LLMRequest`/`LLMResponse`, `Workspace`, `ToolSpec`, `StageContext` in the domain; `FakeLLMAdapter`; unit scaffolding. (No behavior change; nothing wired.)
2. **Domain `AgentRuntime` loop** — the agnostic loop against `FakeLLMAdapter` + a temp-dir `LocalWorkspace`, fully unit-tested; PLAN/IMPLEMENT/VERIFY prompts.
3. **`ClaudeLLMAdapter`** — Anthropic SDK translation + settings + opt-in integration test.
4. **Worker wiring + `StageContext`** — `_deps()` provider selection + `handlers.py` context population (coordinated with A3); end-to-end local run of PLAN/IMPLEMENT/VERIFY.
5. **PROVISION + PR stages (local)** — repo clone/worktree provisioning from `Project.repo`, `agent/<task>` branch; push + `gh pr create`; capture PR URL onto the run. (Unsandboxed; A4 swaps the `Workspace`/identity.)
6. **LEARN stage** — curator-role loop → memory-diff commit to project memory.
7. **`LiteLLMAdapter`** — gateway translation, alias routing, per-run budget key; compose service + docs.

Each phase is an independently reviewable PR, green on `make coverage` + `make lint`.
