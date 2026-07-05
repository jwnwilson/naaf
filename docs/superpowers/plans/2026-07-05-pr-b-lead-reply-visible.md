# PR-B: Make lead chat failures/empties visible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A lead (or role) chat turn always leaves a visible persisted `Message` — the actual error reason on failure, or a placeholder when the model returns no text — instead of silently vanishing.

**Architecture:** Root cause — several worker paths finish a chat turn with **no** persisted `Message` (which is all `GET /threads/{id}/messages` reads): (1) empty/whitespace replies are dropped by a guard; (2) the Claude CLI adapter ignores `is_error` on the chat path (`has_report=False`), so a session-limit/timeout/crash returns as ordinary (often empty) content; (3) the project-thread tool loop returns empty text on tool-only turns; (4) exceptions re-raise and roll back the whole turn, leaving only an activity `error` event (not a message). Fix in two layers: the CLI adapter **raises** on `is_error` for the chat path (routing CLI errors into the handler's `except`), and the handler **persists** a reason message on error (without re-raising, so it's durable and not retried) and a **placeholder** message on empty-but-successful turns.

**Tech Stack:** Python 3.12 / pytest. Package manager `uv`.

## Global Constraints

- Immutability (Pydantic `model_copy`); API envelope unchanged.
- TDD: failing test first; AAA; descriptive names.
- Domain snake_case; no camelCase leakage.
- Behavior decisions (locked by the user): on failure show the **actual reason**; on empty-but-successful show a **placeholder**. This intentionally changes `test_chat_empty_reply_is_not_posted_or_dispatched` and `test_handle_chat_emits_error_when_respond_raises`.
- The `is_error` change must affect ONLY the chat/orchestrator path (`has_report=False`); the run-stage path (`has_report=True`) is unchanged.
- Gates: `make coverage` (80%) + `make lint` (ruff + mypy) green before PR.

---

### Task 1: CLI adapter raises on `is_error` for the chat path

**Files:**
- Modify: `projects/server/src/adapters/agent/claude_cli/adapter.py:125-134`
- Test: `projects/server/tests/adapters/agent/claude_cli/test_claude_cli_adapter.py` (match the existing file's location/name — confirm with `find projects/server/tests -name 'test_claude_cli_adapter.py'`)

**Interfaces:**
- Consumes: `data["is_error"]`, `data["result"]` from the runner.
- Produces: on the `not has_report` branch, `complete()` **raises** `RuntimeError(reason)` when `is_error` is true (reason = the CLI `result` text, or a fallback). The `has_report=True` branch is unchanged.

- [ ] **Step 1: Write the failing test**

Add to the adapter test file (reuse its existing fake-runner/adapter construction — the existing `test_error_result_marks_stage_failed` shows the `is_error` + `tools=[REPORT]` setup; this new test uses NO report tool):

```python
def test_chat_path_raises_on_cli_error():
    # A no-report (chat) request whose runner reports is_error must raise,
    # so the worker surfaces the reason instead of returning silent content.
    adapter = _adapter(runner=_fake_runner({
        "result": "You've hit your session limit · resets 11:30pm",
        "is_error": True,
    }))
    with pytest.raises(RuntimeError, match="session limit"):
        adapter.complete(_chat_request())  # a request WITHOUT the report tool
```

> Match the file's existing helpers for building the adapter, the fake runner, and a no-tools request. If it has no "no-report request" helper, build an `LLMRequest` with `tools=[]` (or omit tools) the way `LlmChatResponder` does.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/claude_cli/test_claude_cli_adapter.py::test_chat_path_raises_on_cli_error -v`
Expected: FAIL — no exception raised (adapter currently returns `LLMResponse(content=...)`).

- [ ] **Step 3: Write minimal implementation**

In `adapter.py`, change the `not has_report` branch (currently lines 133-134):

```python
        if not has_report:
            if is_error:
                raise RuntimeError(text or "the Claude CLI reported an error")
            return LLMResponse(content=text, stop_reason="end_turn", usage=usage)
```

(Leave the `has_report=True` report-mapping branch below completely unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/agent/claude_cli/test_claude_cli_adapter.py -v`
Expected: PASS (new test + all existing adapter tests, including the report-tool `is_error` ones which are untouched).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/claude_cli/adapter.py projects/server/tests/adapters/agent/claude_cli/test_claude_cli_adapter.py
git commit -m "fix: surface Claude CLI errors on the chat path instead of returning silent content"
```

---

### Task 2: Handler persists a reason on error and a placeholder on empty

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` (`_handle_project_chat` ~551-586, `handle_chat` ~589-641; add two module-level constants + one helper)
- Test: `projects/server/tests/interactors/worker/test_chat_dispatch.py`, `tests/interactors/worker/test_chat_activity_events.py`, `tests/interactors/worker/test_project_chat.py`

**Interfaces:**
- Consumes: `_post_agent_message(ctx, thread_id, role, content)` (existing).
- Produces: helper `_error_reply(exc: Exception) -> str`; constant `_EMPTY_REPLY_PLACEHOLDER: str`. On `respond()` exception → emit `EVENT_ERROR`, post `_error_reply(exc)` as a message, and **return without re-raising**. On empty (non-error) `reply_text` → post `_EMPTY_REPLY_PLACEHOLDER` instead of dropping. Fan-out stays gated on a genuine non-empty reply.

- [ ] **Step 1: Write the failing tests**

In `test_chat_dispatch.py`, replace `test_chat_empty_reply_is_not_posted_or_dispatched` with the new intended behavior (keep the same fixtures/fakes it used):

```python
def test_chat_empty_reply_posts_placeholder_and_does_not_fan_out(...):
    # Empty responder output now leaves a visible placeholder message,
    # but must NOT fan out to other roles.
    # ... arrange a responder that returns "" ...
    handle_chat(msg, ctx)
    posted = [m for m in ctx.messages.created if m.author_kind is AuthorKind.AGENT]
    assert len(posted) == 1
    assert posted[0].content  # non-empty placeholder
    assert no_chat_was_published(ctx.bus)  # match the file's existing bus assertion helper
```

In `test_chat_activity_events.py`, replace `test_handle_chat_emits_error_when_respond_raises` with:

```python
def test_handle_chat_on_respond_error_posts_reason_and_does_not_raise(...):
    # A responder that raises must NOT propagate; instead an error event is
    # emitted AND a visible agent message with the reason is persisted.
    # ... arrange a responder whose respond() raises RuntimeError("boom") ...
    handle_chat(msg, ctx)  # no pytest.raises — must not raise
    assert any(e.kind == EVENT_ERROR for e in <committed agent_events>)
    posted = [m for m in ctx.messages.created if m.author_kind is AuthorKind.AGENT]
    assert len(posted) == 1
    assert "boom" in posted[0].content
```

In `test_project_chat.py`, add a project-thread error test mirroring the above but through `_handle_project_chat` (orchestrator whose `respond` raises):

```python
def test_project_chat_on_error_posts_lead_reason_and_does_not_raise(...):
    handle_chat(project_msg, ctx)  # project:<id> thread → _handle_project_chat
    posted = [m for m in ctx.messages.created if m.author_role == "lead"]
    assert len(posted) == 1 and "boom" in posted[0].content
```

> Reuse each file's existing context/fakes (fake responder/orchestrator, fake messages repo exposing `.created`, fake bus). Match the existing assertion helpers for "no chat published" and "committed agent events".

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_dispatch.py tests/interactors/worker/test_chat_activity_events.py tests/interactors/worker/test_project_chat.py -v`
Expected: FAIL — current code drops empty replies and re-raises on error (no reason message posted).

- [ ] **Step 3: Write minimal implementation**

In `handlers.py`, add near the other module constants:

```python
_EMPTY_REPLY_PLACEHOLDER = "_(the agent finished without a reply)_"


def _error_reply(exc: Exception) -> str:
    return f"⚠️ The agent hit an error: {exc}"
```

Rewrite the tail of `_handle_project_chat` (the `try/except/finally` + post):

```python
    try:
        reply_text = ctx.lead_orchestrator.respond(history, project.name, tools)
    except Exception as exc:
        if sink:
            sink(EVENT_ERROR, {"message": str(exc)})
        _post_agent_message(ctx, thread_id, "lead", _error_reply(exc))
        return
    finally:
        if sink:
            ctx.lead_orchestrator.set_event_sink(None)
    if sink:
        sink(EVENT_FINAL, {"text": reply_text})
    _post_agent_message(ctx, thread_id, "lead", reply_text.strip() or _EMPTY_REPLY_PLACEHOLDER)
```

Rewrite the tail of `handle_chat`:

```python
    try:
        reply_text = ctx.chat_responder.respond(role, history, title)
    except Exception as exc:
        if sink:
            sink(EVENT_ERROR, {"message": str(exc)})
        _post_agent_message(ctx, work_item_id, role, _error_reply(exc))
        return
    finally:
        if sink:
            ctx.chat_responder.set_event_sink(None)
    if sink:
        sink(EVENT_FINAL, {"text": reply_text})
    text = reply_text.strip()
    if not text:
        _post_agent_message(ctx, work_item_id, role, _EMPTY_REPLY_PLACEHOLDER)
        return
    _post_agent_message(ctx, work_item_id, role, reply_text)
    for target in plan_fanout(reply_text, depth + 1):
        _publish_chat(ctx, work_item_id, msg.owner_id, target, depth + 1)
```

Rationale for not re-raising: a chat failure (e.g. session limit) should surface once as a visible message, not be retried as a poison bus message. The error remains observable via both the persisted message and the independent `EVENT_ERROR` activity event.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_dispatch.py tests/interactors/worker/test_chat_activity_events.py tests/interactors/worker/test_project_chat.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/tests/interactors/worker/test_chat_dispatch.py projects/server/tests/interactors/worker/test_chat_activity_events.py projects/server/tests/interactors/worker/test_project_chat.py
git commit -m "fix: persist a visible message on lead chat error/empty reply"
```

---

### Task 3: Verify gates and open the PR

**Files:** none.

- [ ] **Step 1: Backend gates**

Run: `cd /Users/noel/projects/naaf/.worktrees/<slug> && make coverage && make lint`
Expected: coverage ≥ 80%; ruff + mypy clean. (Run `make` from the worktree root — the Makefile is repo-root.)

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin <branch>
gh pr create --title "fix: lead chat always leaves a visible message (error reason / placeholder)" \
  --body "Root cause + fix per docs/superpowers/plans/2026-07-05-pr-b-lead-reply-visible.md. Lead chat turns could finish with no persisted Message (empty-drop guard; CLI is_error returned as silent content; tool-only turns; exception rollback), so replies vanished even after refresh. Fix: the Claude CLI adapter raises on is_error (chat path); the worker persists the actual error reason on failure (no re-raise) and a placeholder on empty-but-successful turns. Intentionally updates test_chat_empty_reply_* and test_handle_chat_emits_error_*. Test plan: adapter is_error-raises test; handler error-reason + empty-placeholder + no-fan-out + project-thread tests; make coverage + make lint."
```

---

## Self-Review
- Four no-message conditions (empty-drop, CLI is_error-as-content, tool-only empty, exception rollback) → Task 1 (is_error raises → routes to except) + Task 2 (except posts reason; empty posts placeholder). ✓
- `is_error` change scoped to `has_report=False` only; run stages untouched. ✓
- Locked decisions encoded: reason on error, placeholder on empty; the two affected tests are explicitly replaced. ✓
- Not re-raising is deliberate (visible once, not retried) — rationale stated for the reviewer. ✓
- Fan-out stays gated on a genuine non-empty reply (placeholder/error do not fan out). ✓
- No placeholders in the plan; test steps name real files and reuse existing fakes. ✓
