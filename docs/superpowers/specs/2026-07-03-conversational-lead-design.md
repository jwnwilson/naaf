# Conversational Lead — Plan Work & Dispatch Development by Chat — Design

> Feature **D** of the "dogfood NAAF on itself" effort (sequencing: B → A+C → **D**).
> Goal: converse with a **lead** agent in a project-level thread; the lead creates the
> epic→feature→task tree and proposes development runs you approve in-thread; approved runs are
> developed by the existing subagent pipeline and reviewed as PRs (built on A+C).

## Problem

The chat "lead" is **text-only**: `LlmChatResponder` builds an `LLMRequest` with no `tools` and
returns `.content` — it can talk and `@mention`, but cannot create work items, edit them, or start
a run (`adapters/agent/chat/llm.py`; `interactors/worker/handlers.py:handle_chat`). Separately,
**every thread is bound 1:1 to a work item** (`thread_id == work_item_id`;
`domain/messaging/thread.py` only offers `thread_from_work_item`; `threads.py` routes 404 any id
that isn't a work item). So there is no home for a "plan the whole project from nothing"
conversation, and no way for the lead to act on what you ask.

## Decisions (resolved during brainstorming)

- **Conversation home:** a **project-level thread** — talk to the lead from an empty project; it
  builds the whole tree. (Chosen over anchoring in an existing work-item thread.)
- **Autonomy:** the lead **creates/edits work items automatically** (cheap, reversible), but
  **proposes development runs** as in-thread approvals (reusing the existing question/Option-button
  pattern). Not planner-only, not full autopilot.

## Enabling facts (from code)

- The tool loop is reusable: `LLMRequest.tools: list[ToolSpec]` and `LLMResponse.tool_calls:
  list[ToolCall]` exist (`domain/agent/llm.py`); `LlmAgentRuntime.run_stage` iterates
  complete→execute→feed-ToolResult, coupled to its tools only via `TOOL_SPECS` + `execute_tool`
  (`domain/agent/runtime.py`, `domain/agent/tools.py`).
- `handle_chat` already has full **owner-scoped** access: `HandlerContext` carries `runs`,
  `run_events`, `work_items`, `notifications`, `messages`, `projects`, `bus`, plus `owner_id`
  from the bus message. New rows are created with `owner_id=""` and stamped by the repo's
  `required_filters` (`handlers.py`, `subscription_runner.py:ctx_factory`).
- The `Message` model's `thread_id` is a free string (`domain/messaging/message.py:22`) — a
  `project:<id>` namespace needs **no schema/migration change**; the work is routing/projection.
- Domain create path to reuse: `validate_hierarchy(kind, parent)` (`domain/hierarchy.py`,
  `REQUIRED_PARENT_KIND`: epic→None, feature→EPIC, task→FEATURE) + same-project guard +
  `work_items.create` (`routes/work_items.py:create_work_item`).
- `start_run` sequence to reuse: transition-guard→`runs.create(Run)`→publish `START` to
  `recipient_key(run.id,"lead")`→flip work item to `IN_PROGRESS`
  (`routes/runs.py:start_run:87-128`). All five steps are reachable from `HandlerContext`.

---

## D1 — Project-level thread (new conversation scope)

- **Thread id namespace:** `project:<projectId>`. No `Message` schema change.
- **Projection:** add `thread_from_project(project, messages)` beside `thread_from_work_item`
  (`domain/messaging/thread.py`).
- **Routes** (`interactors/api/routes/threads.py`): teach `get_thread` / `list_messages` /
  `post_message` to resolve a project thread. Replace the unconditional `_read_item_or_404` with a
  scope-aware resolver: a `project:` id reads the project (404 if missing); otherwise the existing
  work-item path. `_messages_for` already filters by `thread_id`, so it works unchanged.
- **Dispatch/bus:** `post_message` currently hardcodes `{"work_item_id": id}` into the bus payload
  and `handle_chat` reads `msg.payload["work_item_id"]`. Generalize the payload to carry a
  **scope** (`{"scope":"project","project_id":id}` vs `{"scope":"work_item","work_item_id":id}`)
  and a recipient key `proj:<id>:lead` for the project lead. `plan_dispatch` still defaults an
  unmentioned human post to `lead`.
- **List:** the project thread is fetched directly by id (`GET /threads/project:<id>`); it does
  **not** need to appear in the work-item `list_threads` projection.

## D2 — The lead gains a tool surface

- **Shared loop:** factor the ~15-line tool loop out of `LlmAgentRuntime.run_stage` into
  `domain/agent/tool_loop.py` (`run_tool_loop(llm, request, execute, *, max_iterations)`), used by
  **both** the code runtime (Workspace tools) and the new orchestrator. Low-risk, keeps them from
  drifting (DRY). The code runtime's behavior is unchanged — same loop, extracted.
- **`LeadOrchestrator`** — a new chat responder that runs the tool loop:
  - Real: `LlmOrchestrator` (reaches the model via the existing `LLMAdapter`, using the lead's
    `model_alias` — lead→opus per `role_model_aliases`).
  - Test/offline: `EchoOrchestrator` (deterministic scripted tool calls), mirroring
    `EchoChatResponder`, so tests and no-key envs run without the model.
- **`OrchestrationTools` capability** (port + adapter over `ctx`): the executor the loop closes
  over — the domain-action analogue of `Workspace`. Domain validation stays pure; all I/O lives in
  the adapter. Tools:
  - `list_board()` → the project's epic→feature→task tree (`build_board_tree`) so the lead can see
    what exists and choose parents.
  - `create_work_item(kind, title, spec?, parent_id?, priority?)` → reuses `validate_hierarchy` +
    same-project guard + `ctx.work_items.create`. Supports epics (no parent), features, tasks.
  - `update_work_item(id, title?, spec?, priority?)` → the PATCH path.
  - `propose_run(work_item_ids)` → see D3 (posts a question, does **not** start a run directly).
- **Scope:** the orchestrator is wired for the **project lead** (project-thread `role=lead`).
  Work-item-thread responders keep today's text-only behavior.

## D3 — Autonomy: auto-create, propose-to-run

- **Creates/edits are automatic and narrated.** The lead posts a short summary of what it created
  ("✓ Epic 'Auth' + 3 features + 6 tasks") into the thread. Items are reversible (edit via feature
  B, delete on the board), so no pre-confirmation.
- **Runs are proposed.** `propose_run(work_item_ids)` posts a **`run_proposal`** question message
  (`kind=question`, `payload={options:[approve,reject], work_item_ids:[...]}`) — reusing the
  Phase-2 question rendering + Option buttons.
  - **Approve** (via the existing `POST /threads/{id}/messages/{msgId}/answer` path, extended to
    recognize `run_proposal`): the worker runs the real `start_run` sequence for each work item id
    (transition-guard → `Run` → publish `START(lead)` → flip to in-progress), then stamps
    `resolved_option` back (idempotent, mirroring gate resolution).
  - **Reject:** no run; the lead is informed in-thread.
- Development then proceeds exactly as A+C: each run drives its own work-item thread + plan/merge
  gates and opens a PR surfaced via C's **View PR**.

## D4 — UI

- A project-level **Chat with lead** entry point (sidebar next to the selected project / a
  dashboard panel) that opens the `project:<id>` thread.
- Rendered by the **existing shared `<Thread>` component** (kind-aware; already renders `question`
  Option buttons and the `@role` composer chips) pointed at the project thread — so run proposals
  and created-item notes need **no new thread UI**.
- New/updated epics/features/tasks appear on the board via existing query invalidation (the
  orchestrator's creates go through the same repos the board reads).

## Data flow

```
Project "Chat with lead"  → POST /threads/project:<pid>/messages "build OAuth login"
  → plan_dispatch → CHAT bus msg (scope=project) → recipient proj:<pid>:lead
  → handle_chat → LeadOrchestrator.run_tool_loop:
        list_board → create_work_item(epic) → create_work_item(feature,parent=epic)
        → create_work_item(task,parent=feature) …  (executed via OrchestrationTools/ctx, owner-scoped)
        → propose_run([task ids])  → posts run_proposal question
  → lead narrates summary into the thread; board refreshes
  → user clicks Approve on the run_proposal
  → answer route (run_proposal) → for each id: start_run sequence → START(lead) on bus
  → existing run pipeline develops each task → plan/merge gates → PR (C: View PR)
```

## Error handling

- `create_work_item` with a bad parent (e.g. task under an epic, or cross-project) → the tool
  returns an `is_error` `ToolResult` (`InvalidHierarchy` message); the lead sees it and can correct
  in the same loop, rather than the run crashing.
- `propose_run` on an item whose status can't transition (already in progress / done) → the
  approval path surfaces the 409 as a thread message; other proposed items still proceed.
- Loop/fan-out bounded by the **existing depth guard**; empty orchestrator replies are skipped (no
  bubble, no fan-out), matching current chat behavior. Tool loop bounded by `max_iterations`.

## Non-goals (YAGNI)

- **The lead does not read the repo to plan.** It plans from the conversation + board; code-reading
  in chat stays deferred (development subagents read the repo during their runs).
- No orchestrator tools for delete / bulk-edit / status-transition (use the board UI).
- No new global token/fan-out budget (depth guard + per-run gates only; aggregate budget pairs
  with the A5d follow-up).
- Work-item-thread leads are not upgraded to the tool surface in this feature.

## Files touched (summary)

| File | Change |
|------|--------|
| `domain/messaging/thread.py` | **new** `thread_from_project` projection |
| `interactors/api/routes/threads.py` | scope-aware thread resolve (`project:` ids); project post/list/get |
| `interactors/api/routes/threads.py` + `domain/messaging/dispatch.py` | scoped bus payload + `proj:<id>:lead` recipient |
| `domain/agent/tool_loop.py` | **new** shared `run_tool_loop` (extracted from `runtime.py`) |
| `domain/agent/runtime.py` | use the shared loop (behavior unchanged) |
| `domain/messaging/orchestrator.py` (+ port) | **new** `LeadOrchestrator` protocol |
| `adapters/agent/chat/orchestrator_llm.py` / `…_echo.py` | **new** `LlmOrchestrator` + `EchoOrchestrator` |
| `domain/agent/orchestration_tools.py` (port) + `adapters/…` (ctx impl) | **new** `OrchestrationTools` (list_board/create/update/propose_run) |
| `interactors/worker/handlers.py` | project-scope in `handle_chat`; wire orchestrator; `run_proposal` handling |
| `interactors/api/routes/threads.py` (answer route) | recognize `run_proposal` → run `start_run` sequence |
| `projects/ui/src/modules/…` (project chat entry + thread mount) | **new** Chat-with-lead affordance → `project:<id>` thread |
| `projects/ui/src/lib/api/mocks/…` | mock project thread + orchestrator responses + run_proposal |
| tests (project-thread routing, OrchestrationTools hierarchy, EchoOrchestrator loop, propose→approve→run) | **new** |

No DB migration (thread_id is a free string; `run_proposal` reuses the existing `question` message
shape). Depends on **A+C** for the run pipeline surfacing (View PR) and on **B** for spec editing.

## Acceptance

From an empty `naaf` project: open **Chat with lead**, say "build \<feature\>"; the lead creates an
epic→feature→task tree (visible on the board), then posts a **run proposal**; you **Approve**;
subagents develop each task and open PRs you review via **View PR** — NAAF running end-to-end on
itself, driven by conversation.
