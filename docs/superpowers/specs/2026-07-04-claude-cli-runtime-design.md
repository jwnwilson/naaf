# Claude Code CLI Runtime + naaf MCP Server — Design

> Run naaf's agents on your Claude **subscription** via headless `claude -p`, with **no Anthropic
> API key**. A single new `LLMAdapter` powers runs + chat by reusing the existing agent classes;
> an **MCP server** lets Claude Code call naaf's own domain functionality.

## Problem

Today naaf reaches the model only through the `LLMAdapter` port — `ClaudeLLMAdapter` (Anthropic
API, metered per token) or `LiteLLMAdapter`. A Claude Pro/Max **subscription** can't authenticate
those; it's only usable via Claude apps / the `claude` CLI. Users want the (token-heavy) agent
runs — and the lead-chat — to run on their subscription instead, cost-effectively.

## Decisions (resolved during brainstorming)

- **Mechanism:** a new `LLMAdapter` implementation, `ClaudeCliLLMAdapter`, that shells out to
  `claude -p` (subscription-authed). Selected by `naaf_llm_provider=claude_cli`.
- **Reuse existing interfaces:** the adapter works with the **existing** `LlmAgentRuntime`,
  `LlmChatResponder`, and `LlmOrchestrator` — **no new runtime/responder/orchestrator classes**.
- **Repo access for the lead-chat:** a **naaf MCP server** (Approach A) exposing a **broad
  read/write domain surface**; Claude Code calls naaf's tools itself during a `claude -p` run.
- **Autonomy:** `--permission-mode bypassPermissions` (full auto in the run's workspace).
- **Capture output like other adapters:** `complete()` maps `claude -p`'s JSON into a normal
  `LLMResponse` (content + usage; a synthesized `report` tool-call on stage runs).

## 1. `ClaudeCliLLMAdapter(LLMAdapter)`

`adapters/agent/claude_cli/adapter.py`. Implements the existing port:
`complete(request: LLMRequest) -> LLMResponse`.

- **Build the prompt** from `request.messages` (the transcript) + `request.system`.
- **Invoke** `claude -p <prompt> --output-format json --permission-mode bypassPermissions`
  `[--append-system-prompt <system>] [--add-dir <cwd>] [--mcp-config <cfg>] [--allowed-tools …]`
  via `subprocess.run(cwd=…, env=…, timeout=…)`. A small private helper builds the argv, runs it,
  and parses the JSON (`{result, is_error, usage:{input_tokens,output_tokens,…}, …}`). The helper
  takes an injectable `runner` callable so **no real `claude` runs in tests**.
- **Return** `LLMResponse(content=result, usage=Usage(input_tokens, output_tokens), stop_reason=…)`
  — captured from the JSON, mirroring how `ClaudeLLMAdapter`/`LiteLLMAdapter` map their responses.
- **VERIFY pass/fail:** when `request.tools` contains the `report` spec (true only on stage runs),
  the adapter appends a short instruction ("end with `VERDICT: PASS|FAIL — <summary>`") to the
  system prompt and maps Claude's verdict into a synthesized `report` **tool-call**
  (`LLMResponse(tool_calls=[ToolCall("report", {passed, summary})], stop_reason="tool_use")`). The
  existing runtime already special-cases `report`, so VERIFY semantics (default-fail unless PASS)
  are preserved — entirely inside the `LLMResponse` contract. Otherwise the adapter returns plain
  text (chat / orchestrator paths).

**Per-owner construction:** the adapter carries `owner_id`, `db_url`, `github_token`, and the model
alias map — needed to (a) scope the MCP server, (b) auth `gh` in the workspace. `github_token` and
any relevant env go into the `claude` subprocess env; `ANTHROPIC_API_KEY` is **not** set (the
subscription is used).

### How the existing classes reuse it
- **`LlmAgentRuntime`** (run stages): calls `complete()` with `TOOL_SPECS` (incl. `report`). The
  adapter runs `claude -p` in the workspace; Claude Code does the edits / bash / tests / `git push`
  / `gh pr create`; the adapter returns the result (+ report for VERIFY). The runtime's own
  `Workspace` tools simply aren't exercised (Claude Code does its own file/bash work).
- **`LlmChatResponder`** (work-item thread text chat): `complete()` → plain text reply.
- **`LlmOrchestrator`** (project lead-chat): `respond()` → `run_tool_loop` → `complete()` **once**.
  With the MCP server configured, Claude Code creates the epic→feature→task tree and proposes runs
  **via naaf's MCP tools itself**, then returns a summary; the loop sees no naaf tool-calls and
  ends. naaf's `execute_orchestration_tool`/`run_tool_loop` machinery is bypassed on this path —
  Claude Code drives the tools. **No `LlmOrchestrator` change.**

## 2. naaf MCP server — the interface to the repo

`interactors/mcp/server.py`: a stdio MCP server (via the `mcp` Python SDK), launched as a
subprocess by `claude -p` through the generated `--mcp-config`. It reads `naaf_db_url` + `owner_id`
from its env, opens its own **owner-scoped** `SqlUnitOfWork`, and exposes a broad read/write
surface — each tool a thin wrapper over existing code:

- **write:** `create_work_item`, `update_work_item`, `propose_run`, `start_run`, `transition_status`
- **read:** `list_projects`, `list_board`, `get_work_item`, `list_runs`, `get_thread`

Owner scoping comes from env; **project/work-item ids are tool arguments**, so the
`LLMAdapter.complete()` interface needs no extra parameters (it stays context-free). The lead-chat
prompt names the project (the orchestrator passes the project *name* as `title`); Claude Code
resolves the id itself via `list_projects` before creating items — so neither the adapter nor the
existing `LlmOrchestrator` needs to thread a `project_id` through `complete()`. Wraps `CtxOrchestrationTools` (create/update/list_board/propose_run), the run-start
sequence (`interactors/api/run_start.start_run`), `validate_transition`, and the message/run repos.
Adds an `mcp` dependency.

**Config generation:** the adapter writes a minimal mcp-config JSON pointing `claude` at
`{command: "uv", args: ["run","python","-m","interactors.mcp.server"], env: {naaf_db_url, owner_id}}`
and passes `--mcp-config <path>` + `--allowed-tools "mcp__naaf__*"` (bypassPermissions also permits
them). The config is attached to **both** the orchestrator's and the runtime's `claude`
invocations, so Claude Code can read naaf (get_work_item, list_runs) during a run too — the broad
surface, available in both contexts.

## 3. Wiring & config

- **Factory** (`adapters/agent/factory.py`): a `claude_cli` branch (keyed on
  `settings.llm_provider == "claude_cli"`) builds the per-owner `ClaudeCliLLMAdapter` and wires it
  into `LlmAgentRuntime` + `LlmChatResponder` + `LlmOrchestrator` — **requiring no Anthropic key**.
  `build_agent_deps` gains `owner_id` + `db_url` params for the MCP scoping; `github_token` flows to
  the adapter's subprocess env.
- **ctx_factory** (`subscription_runner.py`): in `claude_cli` mode, always build per-owner deps
  (owner_id is in hand → MCP scoping), not the global fallback. `build_global_agent_deps` returns
  `None` globals in `claude_cli` mode (no global owner).
- **Settings** (`interactors/api/settings.py`): `naaf_claude_bin` (default `claude`),
  `naaf_claude_timeout_s` (default 900), and `naaf_llm_provider` accepts `claude_cli`.

## Data flow

```
naaf_llm_provider=claude_cli:
  run stage  → LlmAgentRuntime.run_stage → ClaudeCliLLMAdapter.complete(tools incl. report)
    → claude -p (bypassPermissions, --add-dir workspace, --mcp-config naaf)
      → Claude Code edits/tests/pushes/opens PR (+ may read naaf via MCP)
    → JSON → LLMResponse(content, usage, report tool-call w/ VERDICT) → StageResult
  lead chat  → LlmOrchestrator.respond → ClaudeCliLLMAdapter.complete(--mcp-config naaf)
      → Claude Code calls mcp__naaf__create_work_item / propose_run (owner-scoped DB writes)
    → JSON → LLMResponse(text) → summary
```

## Error handling

- `claude` missing / nonzero exit / unparseable JSON → the adapter returns a failed `LLMResponse`
  (empty content, `is_error`) so the runtime records a failed stage (halts the run) rather than
  crashing the worker; the error text is surfaced in the stage summary.
- MCP server DB/errors are returned as tool errors to Claude Code (recoverable in its loop);
  domain validation (`InvalidHierarchy`, `InvalidTransition`) surfaces as tool-error content.
- `naaf_claude_timeout_s` bounds each invocation; a timeout → failed stage.
- No Anthropic key is required or read in `claude_cli` mode.

## Testing

- **Adapter:** injectable `runner` → fake JSON. `complete()` maps result/usage → `LLMResponse`;
  synthesizes the `report` tool-call (PASS/FAIL) only when `report` is in `request.tools`; failure
  JSON → failed response. argv includes the expected flags (bypassPermissions, --mcp-config when
  configured).
- **Existing classes unchanged** are covered by their current tests; a focused test drives
  `LlmAgentRuntime` and `LlmOrchestrator` with a fake-runner `ClaudeCliLLMAdapter` to confirm the
  reuse (stage result; orchestrator returns text and issues no naaf tool-calls).
- **MCP tools:** each tool handler tested by calling it directly against a real `SqlUnitOfWork`
  (create respects hierarchy; start_run transitions; transition_status validates; reads return the
  expected shape). The stdio/protocol wrapper is thin; the live `claude ↔ MCP` loop is validated by
  the dogfood pass.
- Gates: `make coverage` (80%) + `make lint` green.

## Non-goals

- No cross-stage session resume; no MCP auth beyond owner-scoping-from-env; no sandbox
  (bypassPermissions runs on the host — A4). No token *pricing* (we keep `tokens` for run usage;
  subscription cost is notional). No changes to `LlmAgentRuntime`/`LlmChatResponder`/
  `LlmOrchestrator`. The API-key adapters (`ClaudeLLMAdapter`/`LiteLLMAdapter`) remain for users
  who prefer metered API.

## Files (summary)

| File | Change |
|------|--------|
| `adapters/agent/claude_cli/adapter.py` | **new** `ClaudeCliLLMAdapter` (+ argv/JSON helper, injectable runner) |
| `adapters/agent/claude_cli/mcp_config.py` | **new** generate the `--mcp-config` JSON |
| `interactors/mcp/server.py` | **new** owner-scoped stdio MCP server (10 tools over existing code) |
| `adapters/agent/factory.py` | `claude_cli` branch; `build_agent_deps(owner_id, db_url, …)` |
| `interactors/worker/subscription_runner.py` | per-owner deps in `claude_cli` mode |
| `interactors/api/settings.py` | `claude_bin`, `claude_timeout_s`, `llm_provider=claude_cli` |
| `projects/server/pyproject.toml` | add `mcp` |
| `docs/dogfooding.md` | document the `claude_cli` provider (subscription, no key) |
| tests (adapter, reuse, MCP tools) | **new** |

## Acceptance

With `naaf_llm_provider=claude_cli` and Claude Code logged in via a subscription (no Anthropic key):
a task's **Start run** drives implement/verify/PR on the subscription and opens a real PR; **Chat
with lead** creates the epic→feature→task tree via naaf's MCP tools and proposes runs — all on the
subscription, reusing the existing runtime/chat/orchestrator.
