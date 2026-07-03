# Work-Item Thread — Phase 2 (runs narrate into the thread + gates-as-questions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an agent run visible *inside* the work-item thread — the run pipeline posts role-attributed `Message`s as it progresses, and each human gate renders as a resolvable `question` message (Approve/Reject) in the thread and inbox.

**Architecture:** The worker's `HandlerContext` gains a `messages` repository. A `narrate(...)` helper writes `Message`s (thread_id = work item id, `author_kind=agent`, `author_role=<stage role>`) at run-lifecycle points. A gate additionally emits a `question` message carrying `{options,[…], run_id, gate_kind}`; resolving it (via the existing `POST /runs/{id}/gate` **or** a new thread-native `POST /threads/{workItemId}/messages/{msgId}/answer`) publishes the same `GATE_RESOLVED` bus message, and the worker stamps the question message's `resolved_option`. Phase 1 already renders `text`/`question`/`file_write` message kinds; the FE work here is wiring the (currently inert) question Option buttons to an answer mutation and showing the resolved state.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), pytest (SQLite in tests). React + Vite + Tailwind, TanStack Query, MSW, Vitest.

## Global Constraints

- Builds on Phase 1 (merged, PR #33). Phase-1 facts assumed present: `domain/messaging/message.py` has `AuthorKind{USER,AGENT}`, `MessageKind{TEXT,FILE_WRITE,QUESTION,EVENT}`, and `Message{owner_id, thread_id(==work_item_id), author_kind, author_role, model_alias, kind, content, mentions, payload, run_id}`; `uow.messages` is a `MessageRepository`; the FE `<Thread>`/`MessageItem` render `question` options as buttons (inert).
- API envelope `{success,data,error}` (+meta); owner scoping via UnitOfWork; `*Out` models never leak `owner_id`.
- Immutability: Pydantic models updated via `model_copy(update=...)`.
- Worker repos stamp `owner_id` from `required_filters` when created with `owner_id=""` (same pattern as `emit()` for `RunEvent`).
- Roles vocabulary: `lead, architect, backend, frontend, qa, devops`. Stage→role mapping already exists in `handlers.py` (`advance` hands PLAN/PR/LEARN to `lead`/`curator`, IMPLEMENT to `engineer`, VERIFY to `qa`).
- `RunEvent`/SSE stays the low-level observability stream — thread messages are the **human narrative**, added *alongside* events, never replacing them.
- Gate kinds: `GateKind{PLAN, MERGE}`; decisions: `approve|reject`.
- TDD: failing test first; AAA; descriptive names. Commit format `<type>: <description>`. Gates: `make coverage` (80%) + `make lint`; FE `pnpm vitest run` + `pnpm tsc --noEmit` + `pnpm build`.
- Backend commands from `projects/server`; frontend from `projects/ui`.

---

## File structure

**Backend (`projects/server/src`)**
- Modify `interactors/worker/handlers.py` — add `messages` to `HandlerContext`; add `narrate()` + `_question()`; call them at lifecycle/gate points; mark question resolved on `GATE_RESOLVED`.
- Modify `interactors/worker/subscription_runner.py` — pass a `MessageRepository` into `HandlerContext`.
- Modify `interactors/worker/bus_source.py` — pass `messages=None` in the dead-letter `HandlerContext` (no narration on that path).
- Modify `interactors/api/routes/threads.py` — add `POST /threads/{id}/messages/{msgId}/answer`.
- Modify `interactors/api/contract.py` — add `AnswerIn`.
- (No new migration — `question` payload uses the existing `payload` JSON column.)

**Backend tests (`projects/server/tests`)**
- Create `tests/domain/messaging/test_question.py` — question option/resolution helpers (pure).
- Modify `tests/interactors/worker/…` (the handlers test module) — narration + gate→question + resolve marks the message.
- Modify `tests/api/test_threads_api.py` — the `/answer` endpoint.

**Frontend (`projects/ui/src`)**
- Create `lib/api/hooks/useAnswerQuestion.ts`; export from `lib/api/hooks/index.ts`.
- Modify `components/thread/MessageItem.tsx` — wire question Option buttons to the answer mutation; render resolved state.
- Modify `lib/api/mocks/handlers.ts` + `db.ts` — mock the `/answer` route + a seeded `question` message.
- Modify `components/thread/Thread.test.tsx` (or a new `MessageItem.test.tsx`) — answer-click + resolved-state tests.

---

## Task 1: Question domain helpers (options + resolution)

**Files:**
- Create: `projects/server/src/domain/messaging/question.py`
- Test: `projects/server/tests/domain/messaging/test_question.py`

**Interfaces:**
- Produces: `APPROVE_REJECT: list[dict]` = `[{"id":"approve","label":"Approve"},{"id":"reject","label":"Reject"}]`; `question_payload(run_id: str, gate_kind: str) -> dict` (→ `{"options": APPROVE_REJECT, "run_id": run_id, "gate_kind": gate_kind, "resolved_option": None}`); `resolve_payload(payload: dict, option: str) -> dict` (returns a **new** dict with `resolved_option=option`); `is_valid_option(payload: dict, option: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/messaging/test_question.py`:

```python
from domain.messaging.question import (
    APPROVE_REJECT,
    is_valid_option,
    question_payload,
    resolve_payload,
)


def test_question_payload_carries_options_and_run_link():
    p = question_payload(run_id="run1", gate_kind="plan")
    assert p["options"] == APPROVE_REJECT
    assert p["run_id"] == "run1"
    assert p["gate_kind"] == "plan"
    assert p["resolved_option"] is None


def test_resolve_payload_is_immutable_and_sets_option():
    p = question_payload(run_id="run1", gate_kind="plan")
    resolved = resolve_payload(p, "approve")
    assert resolved["resolved_option"] == "approve"
    assert p["resolved_option"] is None  # original untouched


def test_is_valid_option():
    p = question_payload(run_id="run1", gate_kind="plan")
    assert is_valid_option(p, "approve") is True
    assert is_valid_option(p, "reject") is True
    assert is_valid_option(p, "banana") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_question.py -q`
Expected: FAIL (`ModuleNotFoundError: domain.messaging.question`).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/messaging/question.py`:

```python
APPROVE_REJECT: list[dict] = [
    {"id": "approve", "label": "Approve"},
    {"id": "reject", "label": "Reject"},
]


def question_payload(run_id: str, gate_kind: str) -> dict:
    return {
        "options": APPROVE_REJECT,
        "run_id": run_id,
        "gate_kind": gate_kind,
        "resolved_option": None,
    }


def is_valid_option(payload: dict, option: str) -> bool:
    return any(o["id"] == option for o in payload.get("options", []))


def resolve_payload(payload: dict, option: str) -> dict:
    return {**payload, "resolved_option": option}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_question.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/question.py projects/server/tests/domain/messaging/test_question.py
git commit -m "feat: question message payload + resolution helpers"
```

---

## Task 2: Give the worker a `messages` repository

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` (the `HandlerContext` dataclass)
- Modify: `projects/server/src/interactors/worker/subscription_runner.py` (`ctx_factory`)
- Modify: `projects/server/src/interactors/worker/bus_source.py` (dead-letter `HandlerContext`)
- Test: exercised by Task 3 (the narration handler test).

**Interfaces:**
- Produces: `HandlerContext.messages: Any` (a `MessageRepository | None` — `None` only on the dead-letter path, mirroring `notifications`).

- [ ] **Step 1: Add the field to `HandlerContext`**

In `handlers.py`, the `HandlerContext` dataclass currently has fields `runs, run_events, work_items, notifications, bus, runtime, workspace_root, role_aliases, projects`. Add a `messages` field next to `notifications`:

```python
    notifications: Any  # NotificationRepository | None — None in dead-letter cleanup
    messages: Any = None  # MessageRepository | None — None in dead-letter cleanup
```

(Place `messages` after `notifications`. It defaults to `None` so the dead-letter site that omits it stays valid.)

- [ ] **Step 2: Wire it in `subscription_runner.py`**

In `subscription_runner.py`, `ctx_factory` builds owner-scoped repos. Add the import alongside the other repository imports at the top of the file (find the existing `from adapters.database.repositories import ...` line and add `MessageRepository`), then add to the `HandlerContext(...)` call:

```python
            messages=MessageRepository(uow.session, required_filters=scope),
```

(Insert it right after the `notifications=...` line.)

- [ ] **Step 3: Confirm the dead-letter site compiles**

`bus_source.py` builds a `HandlerContext(runs=…, run_events=…, work_items=…, notifications=None, bus=…, runtime=None)`. Because `messages` now defaults to `None`, no change is required there — but add `messages=None,` explicitly after `notifications=None,` for clarity.

- [ ] **Step 4: Verify nothing broke**

Run: `cd projects/server && uv run pytest tests/interactors -q`
Expected: PASS (existing worker tests unaffected — the new field is optional).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/src/interactors/worker/subscription_runner.py projects/server/src/interactors/worker/bus_source.py
git commit -m "feat: expose a messages repository on the worker HandlerContext"
```

---

## Task 3: Narrate the run into the thread

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py`
- Test: `projects/server/tests/interactors/worker/test_thread_narration.py` (create)

**Interfaces:**
- Consumes: `HandlerContext.messages` (Task 2), `Message`/`AuthorKind`/`MessageKind` (Phase 1).
- Produces: `narrate(ctx, run, *, role: str, content: str, kind: MessageKind = MessageKind.TEXT, payload: dict | None = None) -> None` — creates a thread message; **no-ops when `ctx.messages is None`**.

The narration points (add calls; do NOT remove any existing `emit(...)` RunEvent — narration is additive):
- `handle_lead` START, right after `emit(ctx, run, EventType.RUN_STARTED, role="lead")`: `narrate(ctx, run, role="lead", content=f"Starting work on \"{_work_item_title(ctx, run)}\". Planning now.")`.
- `_finish_stage`, after the `emit(... STAGE_PASSED/STAGE_FAILED ...)`: narrate the role's result — `narrate(ctx, run, role=role, content=f"{stage.value} {'passed' if outcome.result.passed else 'failed'}: {outcome.result.summary or '(no summary)'}")`.
- `advance` `Finish` branch, after `emit(... RUN_FINISHED ...)`: `narrate(ctx, run, role="lead", content=f"Run finished: {step.status.value}.")`.

- [ ] **Step 1: Write the failing test**

Create `tests/interactors/worker/test_thread_narration.py`. This drives one full `FakeAgentRuntime` run and asserts thread messages appear. Model the setup on the existing worker/handler test in `tests/interactors/worker/` (open that directory, reuse its fixtures/helpers for building a `HandlerContext` with `FakeAgentRuntime`, a seeded work item, and draining the bus). The assertion:

```python
# after driving a run to completion for work item `wid` owned by `owner`:
msgs = uow.messages.read_multi(filters={"thread_id": wid}, order_by="created_at").results
kinds_roles = [(m.author_kind.value, m.author_role, m.kind.value) for m in msgs]
# lead announces the start
assert ("agent", "lead", "text") in kinds_roles
# at least one stage result was narrated by a non-lead role (e.g. engineer/qa)
assert any(r in {"engineer", "qa"} for (_ak, r, _k) in kinds_roles)
# a run-finished line exists
assert any("Run finished" in m.content for m in msgs)
# every narrated message links back to the run and is thread-scoped
assert all(m.thread_id == wid and m.run_id is not None for m in msgs)
```

If the existing worker test file already builds a run end-to-end, copy its harness verbatim into this new test and add the assertions above. If no such harness exists, build the `HandlerContext` directly with in-memory SQLite repos + `FakeAgentRuntime` and publish a `START` `AgentMessage`, draining via the same dispatch path the other worker tests use.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_thread_narration.py -q`
Expected: FAIL — no messages are created yet (empty `msgs`).

- [ ] **Step 3: Write minimal implementation**

In `handlers.py`, add the helper near `emit(...)`:

```python
def _work_item_title(ctx: HandlerContext, run: Run) -> str:
    try:
        wi = ctx.work_items.read(run.work_item_id)
        return getattr(wi, "title", "") or run.work_item_id
    except RecordNotFound:
        return run.work_item_id


def narrate(
    ctx: HandlerContext,
    run: Run,
    *,
    role: str,
    content: str,
    kind: MessageKind = MessageKind.TEXT,
    payload: dict | None = None,
) -> None:
    """Post a human-readable message into the run's work-item thread.

    Additive to RunEvents; no-ops on the dead-letter path where messages is None.
    """
    if ctx.messages is None:
        return
    ctx.messages.create(Message(
        owner_id="",  # stamped from required_filters
        thread_id=run.work_item_id,
        author_kind=AuthorKind.AGENT,
        author_role=role,
        kind=kind,
        content=content,
        payload=payload or {},
        run_id=run.id,
    ))
```

Add the imports at the top of `handlers.py`:

```python
from domain.messaging.message import AuthorKind, Message, MessageKind
```

Then insert the three `narrate(...)` calls at the points listed under **Interfaces** above. For `_finish_stage`, the function already has `run`, `role`, `stage`, and `outcome` in scope — add the narrate call after the existing `emit(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_thread_narration.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/tests/interactors/worker/test_thread_narration.py
git commit -m "feat: run pipeline narrates lifecycle into the work-item thread"
```

---

## Task 4: Gates render as `question` messages

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` (`advance` GateStep branch + `handle_lead` GATE_RESOLVED)
- Test: `projects/server/tests/interactors/worker/test_gate_question.py` (create)

**Interfaces:**
- Consumes: `question_payload`/`resolve_payload` (Task 1), `narrate` (Task 3).
- Produces: on a gate, a `question` message in the thread with `payload = question_payload(run.id, gate.kind.value)`; on resolution, the matching unresolved question message's `payload.resolved_option` is set, and a lead follow-up line is narrated.

- [ ] **Step 1: Write the failing test**

Create `tests/interactors/worker/test_gate_question.py`. Drive a run to its first gate (PLAN gate — `advance` sets `AWAITING_GATE`), then resolve it. Reuse the harness from Task 3's test. Assertions:

```python
# at the gate:
qs = [m for m in uow.messages.read_multi(filters={"thread_id": wid}, order_by="created_at").results
      if m.kind.value == "question"]
assert len(qs) == 1
q = qs[0]
assert q.author_role == "lead"
assert q.payload["run_id"] == run_id
assert q.payload["gate_kind"] == "plan"
assert q.payload["resolved_option"] is None
assert [o["id"] for o in q.payload["options"]] == ["approve", "reject"]

# after publishing GATE_RESOLVED {decision: "approve"} and draining:
q2 = uow.messages.read(q.id)
assert q2.payload["resolved_option"] == "approve"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_gate_question.py -q`
Expected: FAIL — no `question` message is created at the gate.

- [ ] **Step 3: Write minimal implementation**

In `handlers.py` `advance`, the `GateStep` branch currently sets `AWAITING_GATE` + `pending_gate` and emits `GATE_REQUESTED`. After the existing `emit(ctx, run, EventType.GATE_REQUESTED, ...)`, add:

```python
            from domain.messaging.message import MessageKind
            from domain.messaging.question import question_payload
            narrate(
                ctx, run, role="lead",
                kind=MessageKind.QUESTION,
                content=f"{step.kind.value.capitalize()} gate — review and approve to continue.",
                payload=question_payload(run.id, step.kind.value),
            )
```

(If `MessageKind`/`narrate` are already imported at module scope from Task 3, drop the local import and use them directly — prefer the module-level import.)

Add a helper to resolve the question message, and call it from `handle_lead`'s `GATE_RESOLVED` branch:

```python
def _resolve_question(ctx: HandlerContext, run: Run, option: str) -> None:
    """Mark the run's latest unresolved question message with the chosen option."""
    if ctx.messages is None:
        return
    from domain.messaging.question import resolve_payload
    rows = ctx.messages.read_multi(
        filters={"thread_id": run.work_item_id}, order_by="created_at"
    ).results
    for m in reversed(rows):
        if m.kind.value == "question" and m.payload.get("run_id") == run.id \
                and m.payload.get("resolved_option") is None:
            ctx.messages.update(
                m.id, m.model_copy(update={"payload": resolve_payload(m.payload, option)})
            )
            return
```

In `handle_lead`, the `GATE_RESOLVED` branch handles `approve` and the `else` (reject). In **both** paths, after the existing `emit(... GATE_RESOLVED ...)`, add:

```python
        _resolve_question(ctx, run, msg.payload.get("decision", ""))
        narrate(ctx, run, role="lead",
                content=f"Gate {msg.payload.get('decision')}d — "
                        f"{'continuing.' if msg.payload.get('decision') == 'approve' else 'stopping.'}")
```

Confirm `ctx.messages.update(id, entity)` is the repository's update signature (same as `ctx.work_items.update(...)` used in `couple`). If the repo lacks `update`, use `create` semantics is wrong here — check `MessageRepository`/`SqlRepository` for the `update` method (it exists; `work_items.update` is used in `couple`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_gate_question.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/tests/interactors/worker/test_gate_question.py
git commit -m "feat: gates emit a resolvable question message into the thread"
```

---

## Task 5: `POST /threads/{id}/messages/{msgId}/answer`

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py` (add `AnswerIn`)
- Modify: `projects/server/src/interactors/api/routes/threads.py`
- Test: `projects/server/tests/api/test_threads_api.py`

**Interfaces:**
- Consumes: `is_valid_option` (Task 1), `uow.messages`, `uow.runs`, the bus.
- Produces: `AnswerIn{option: str}`; `POST /threads/{id}/messages/{msgId}/answer` — validates the message is an unresolved `question` in the caller's thread, then publishes a `GATE_RESOLVED` `AgentMessage` (decision = option) to the run's lead (same mechanism as `POST /runs/{id}/gate`). Returns the (still-unresolved-here) `MessageOut` — the worker stamps `resolved_option` asynchronously.

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_threads_api.py`. This needs a `question` message row + a run. Insert them directly via the UoW in an arrange helper (mirror the existing `_make_item`), then POST an answer and assert a bus message was published. Assertions:

```python
def test_answer_question_publishes_gate_resolution(client, session_factory):
    wid, run_id, msg_id = _seed_question(session_factory)  # arrange: work item + run + question msg
    res = client.post(f"/threads/{wid}/messages/{msg_id}/answer", json={"option": "approve"})
    assert res.status_code == 200
    # a GATE_RESOLVED bus message now exists for that run
    from adapters.database.orm import BusMessageRow
    with session_factory() as s:
        rows = s.query(BusMessageRow).filter(BusMessageRow.run_id == run_id).all()
    assert any(r.type == "gate_resolved" and r.payload.get("decision") == "approve" for r in rows)


def test_answer_rejects_unknown_option(client, session_factory):
    wid, _run_id, msg_id = _seed_question(session_factory)
    assert client.post(f"/threads/{wid}/messages/{msg_id}/answer", json={"option": "banana"}).status_code == 422


def test_answer_foreign_thread_is_404(client, session_factory):
    other_wid, _r, msg_id = _seed_question(session_factory, owner="someone-else")
    assert client.post(f"/threads/{other_wid}/messages/{msg_id}/answer", json={"option": "approve"}).status_code == 404
```

Write `_seed_question(session_factory, owner="dev-user")` in the test module: create a work item, a `Run` (via `uow.runs`), and a `question` `Message` (`author_kind=AGENT, author_role="lead", kind=QUESTION, payload=question_payload(run.id,"plan"), run_id=run.id, thread_id=wid`); return `(wid, run_id, msg_id)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -k answer -q`
Expected: FAIL (404/route missing).

- [ ] **Step 3: Write minimal implementation**

In `contract.py`, add:

```python
class AnswerIn(BaseModel):
    option: str

    @field_validator("option")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("option must not be empty")
        return v
```

In `threads.py`, add the route (uses the bus like `runs.py::resolve_gate`). Add imports at the top: `from adapters.bus.ports import MessageBus`, `from domain.messaging.question import is_valid_option`, `from domain.runs.messages import AgentMessage, MessageType, recipient_key`, `from interactors.api.auth import get_owner_id`, `from interactors.api.deps import get_bus`, and `AnswerIn` from contract, plus `HTTPException` (already imported).

```python
@router.post("/{id}/messages/{msg_id}/answer", response_model=Envelope[MessageOut])
def answer_question(
    id: str,
    msg_id: str,
    body: AnswerIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    owner_id: str = Depends(get_owner_id),  # noqa: B008
    bus: MessageBus = Depends(get_bus),  # noqa: B008
):
    _read_item_or_404(uow, id)  # owner-scoped thread existence
    try:
        message = uow.messages.read(msg_id)
    except RecordNotFound as exc:
        raise HTTPException(status_code=404, detail="message not found") from exc
    if message.thread_id != id or message.kind is not MessageKind.QUESTION:
        raise HTTPException(status_code=404, detail="not a question in this thread")
    if not is_valid_option(message.payload, body.option):
        raise HTTPException(status_code=422, detail="invalid option")
    run_id = message.payload.get("run_id")
    if run_id:
        uow.runs.read(run_id)  # owner-scoped 404 if foreign
        bus.publish(AgentMessage(
            owner_id=owner_id,
            run_id=run_id,
            recipient=recipient_key(run_id, "lead"),
            role="lead",
            type=MessageType.GATE_RESOLVED,
            payload={"decision": body.option},
        ))
    return ok(_message_out(message))
```

Import `MessageKind` in `threads.py` (extend the existing `from domain.messaging.message import ...` line to include `MessageKind`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -k answer -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Full backend gate**

Run: `cd projects/server && uv run pytest -q && make lint`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/threads.py projects/server/tests/api/test_threads_api.py
git commit -m "feat: answer a question message to resolve a run gate from the thread"
```

---

## Task 6: FE — answer hook + wire the question Option buttons

**Files:**
- Create: `projects/ui/src/lib/api/hooks/useAnswerQuestion.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts`
- Modify: `projects/ui/src/components/thread/MessageItem.tsx`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`, `db.ts`, `fixtures/index.ts`
- Test: `projects/ui/src/components/thread/Thread.test.tsx` (extend)

**Interfaces:**
- Produces: `useAnswerQuestion(workItemId)` → `mutate({ msgId, option })` POSTing `/threads/{workItemId}/messages/{msgId}/answer`, invalidating `threadMessages(workItemId)`; `MessageItem` question options become buttons that call it and reflect `payload.resolved_option`.

- [ ] **Step 1: Write the failing test**

Extend `Thread.test.tsx` (`MessageItem` block): render a `question` message with `payload.resolved_option: "approve"` and assert the Approve button shows a resolved/selected state (e.g. `disabled` or an `aria-pressed`/checkmark) while Reject is not selected. And render an unresolved question and assert clicking Approve calls the mutation. Since `MessageItem` will need `workItemId` + an answer handler, thread the handler via a prop to keep the unit test simple:

```tsx
it("marks the chosen option resolved", () => {
  render(<MessageItem message={msg({ kind: "question", content: "Plan gate", payload: { options: [{ id: "approve", label: "Approve" }, { id: "reject", label: "Reject" }], resolved_option: "approve" } })} />);
  const approve = screen.getByRole("button", { name: /Approve/ });
  expect(approve).toBeDisabled();
});

it("calls onAnswer when an option is clicked", () => {
  const onAnswer = vi.fn();
  render(<MessageItem message={msg({ id: "q1", kind: "question", payload: { options: [{ id: "approve", label: "Approve" }, { id: "reject", label: "Reject" }], resolved_option: null } })} onAnswer={onAnswer} />);
  screen.getByRole("button", { name: /Approve/ }).click();
  expect(onAnswer).toHaveBeenCalledWith("q1", "approve");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/components/thread/Thread.test.tsx`
Expected: FAIL (`onAnswer` not a prop; buttons inert/not disabled).

- [ ] **Step 3: Implement**

Create `useAnswerQuestion.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export function useAnswerQuestion(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ msgId, option }: { msgId: string; option: string }) =>
      apiFetch(`/threads/${workItemId}/messages/${msgId}/answer`, {
        method: "POST",
        body: JSON.stringify({ option }),
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.threadMessages(workItemId) });
    },
  });
}
```

(Match `apiFetch`'s real signature — check `lib/api/client.ts` for how it takes method/body; adapt if it wraps `fetch` differently.)

In `MessageItem.tsx`, add an optional `onAnswer?: (msgId: string, option: string) => void` prop. In the question-options render, make each option a `<button>` that: is `disabled` when `payload.resolved_option` is set; shows a selected style when `option.id === resolved_option`; and calls `onAnswer?.(message.id, option.id)` on click. In `Thread.tsx`, pass `onAnswer` down from a `useAnswerQuestion(workItemId)` mutation (so `<Thread>` wires it; `MessageItem`'s unit test can still pass `onAnswer` directly).

- [ ] **Step 4: Mock the route + a seeded question**

In `handlers.ts`, add a POST handler for `/threads/:id/messages/:msgId/answer` that sets the matching message's `payload.resolved_option = option` in `db` and returns `{success,data:message}`. Add a `db.resolveQuestion(msgId, option)` mutation (immutable array replace). In `fixtures/index.ts`, add one `question` message (`kind:"question"`, `payload:{options:[{id:"approve",label:"Approve"},{id:"reject",label:"Reject"}],run_id:"run-1",gate_kind:"plan",resolved_option:null}`) to a thread so the UI shows it.

- [ ] **Step 5: Run tests + gates**

Run: `cd projects/ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useAnswerQuestion.ts projects/ui/src/lib/api/hooks/index.ts projects/ui/src/components/thread/MessageItem.tsx projects/ui/src/components/thread/Thread.tsx projects/ui/src/lib/api/mocks projects/ui/src/components/thread/Thread.test.tsx
git commit -m "feat: wire question Option buttons to resolve run gates from the thread"
```

---

## Task 7: Docs + full verification, open PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Note the change** — add a "Work-item threads (Phase 2)" paragraph to `docs/project-history.md`: the run pipeline now narrates lifecycle/stage progress into the work-item thread as role-attributed messages, and human gates render as `question` messages resolvable from the thread/inbox (Option buttons) via `POST /threads/{id}/messages/{msgId}/answer` (routes to the same `GATE_RESOLVED` bus path as `POST /runs/{id}/gate`); the worker stamps the chosen option back onto the message. Still deferred to Phase 3: `@mention` → bus dispatch (agent↔agent), structured `file_write` cards from the runtime, loop guards.

- [ ] **Step 2: Full gates**

Run:
```bash
cd projects/server && make coverage && make lint
cd ../ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build
```
Expected: backend ≥80% coverage + lint clean; frontend green.

- [ ] **Step 3: Commit + push + PR**

```bash
git add docs/project-history.md
git commit -m "docs: record work-item threads phase 2"
git push -u origin docs/work-item-thread-phase2
gh pr create --title "feat: runs narrate into the work-item thread + gates-as-questions (phase 2)" \
  --body "$(cat <<'EOF'
## Summary
- The run pipeline posts role-attributed messages into the work-item thread as it progresses (start, per-stage result, finish).
- Human gates render as resolvable `question` messages; resolving one (Option buttons in the thread/inbox, or the existing `POST /runs/{id}/gate`) drives the same `GATE_RESOLVED` bus path, and the worker stamps `resolved_option` back onto the message.
- New endpoint `POST /threads/{id}/messages/{msgId}/answer`.

Builds on Phase 1 (#33). Deferred to Phase 3: `@mention` → bus dispatch (agent↔agent), structured file_write cards, loop guards. Spec: docs/superpowers/specs/2026-07-03-work-item-thread-substrate-design.md

## Test plan
- Backend: question helpers, thread narration over a full FakeAgentRuntime run, gate→question + resolution, `/answer` endpoint — `make coverage` ≥80%, `make lint` clean.
- Frontend: question Option buttons (answer + resolved state), mocks — `pnpm vitest run`, `pnpm tsc --noEmit`, `pnpm build`.
EOF
)"
```

---

## Self-review

**Spec coverage (Phase 2 rows):**
- Runs narrate into the thread → Tasks 2, 3. ✓
- Gates render + resolve as `question` messages → Tasks 1, 4; thread-native resolution → Task 5; FE buttons → Task 6. ✓
- `RunEvent`/SSE unchanged (narration additive) → Task 3 keeps every `emit(...)`. ✓
- Out of scope (Phase 3): `@mention` dispatch, structured file_write cards, loop guards → not in any task; noted in Task 7 docs.

**Placeholder scan:** No banned placeholders; every code step carries concrete code. Tasks 3–4 instruct reusing the existing worker-test harness (the plan can't reproduce a harness it hasn't read) and name the exact assertions — the implementer must open `tests/interactors/worker/` first; if no end-to-end harness exists there, Task 3 Step 1 gives the fallback (build the context directly + publish START).

**Type/name consistency:** `question_payload`/`resolve_payload`/`is_valid_option` (Task 1) are used identically in Tasks 4 and 5. `narrate(ctx, run, *, role, content, kind, payload)` signature consistent across Tasks 3–4. `HandlerContext.messages` (Task 2) consumed by Tasks 3–4. `AnswerIn{option}` (Task 5) matches the FE `useAnswerQuestion({msgId,option})` body (Task 6). `MessageKind.QUESTION`/`resolved_option` payload key consistent BE (Tasks 1,4,5) ↔ FE (Task 6).

**Open risk to confirm during implementation:** `ctx.messages.update(id, entity)` must exist on `MessageRepository` — `couple()` uses `ctx.work_items.update(...)` so the generic `SqlRepository.update` is available; Task 4 Step 3 calls this out to verify before relying on it.
