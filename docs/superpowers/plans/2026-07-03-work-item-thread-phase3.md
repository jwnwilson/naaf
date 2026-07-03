# Work-Item Thread — Phase 3 (`@mention` → bus dispatch, agent↔agent + loop guards) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the work-item thread the live coordination substrate: posting a message that `@mentions` a role (or, with no mention, `@lead`) dispatches it onto that role's per-work-item queue; a worker wakes the role-agent, it replies into the same thread, and a reply that mentions another role fans out again — all bounded by a fan-out **depth guard** so agent↔agent chatter cannot loop forever.

**Architecture:** A new bus message `type=CHAT` with a **work-item-scoped** recipient (`wi:{work_item_id}:{role}`), published by `POST /threads/{id}/messages` for `route_targets(content)`. The worker's `dispatch` routes `CHAT` to a new `handle_chat`, which loads recent thread history, asks a `ChatResponder` port for the role's reply, posts it as an agent `Message`, and re-dispatches the reply's mentions at `depth+1` while `depth < MAX_FANOUT_DEPTH`. Two responders ship: a deterministic `EchoChatResponder` (offline/tests) and an `LlmChatResponder` (reaches the model only through the existing `LLMAdapter` port). Human posts start at `depth=0`; agent replies carry an incremented depth. This realizes the design's "agents discover and dispatch messages to each other" and closes `docs/TODO.md`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), pytest (SQLite in tests). React + Vite + Tailwind, TanStack Query, MSW, Vitest.

## Global Constraints

- Builds on Phase 1 + Phase 2 (both on `main`, PRs #33/#35). Assumed present: `Message{author_kind, author_role, kind, content, mentions, payload, run_id, thread_id(==work_item_id)}`; `MessageKind{TEXT,FILE_WRITE,QUESTION,EVENT}`; `uow.messages`; `domain/messaging/mentions.py` (`parse_mentions`, `route_targets`, `TEAM_ROLES`, `DEFAULT_ROLE`); the worker `HandlerContext` with `messages`; `narrate()`; `POST /threads/{id}/messages` (persist-only + parse mentions, **no dispatch yet**).
- Bus facts: `AgentMessage{owner_id, run_id, recipient, role, type, payload, status}`; `recipient_key(run_id, role)="run:{run_id}:{role}"`; `claim_next(roles)` claims the oldest pending message whose `recipient` has no in-flight claim (one-in-flight-per-recipient); `dispatch(msg, ctx)` routes by `msg.role` to `_HANDLERS`.
- Runtime facts: `LLMAdapter.complete(LLMRequest) -> LLMResponse`; `LLMMessage`, `MessageRole`, `LLMRequest`, `LLMResponse` in `domain/agent/llm`; `FakeLLMAdapter(scripted)` for offline tests; adapter chosen in `adapters/agent/factory.py` by settings.
- API envelope `{success,data,error}`; owner scoping via UnitOfWork; `*Out` never leaks `owner_id`. Immutability via `model_copy`. Worker repos stamp `owner_id` from `required_filters`.
- **Loop guards** live in the domain: `MAX_FANOUT_DEPTH` bounds agent→agent hops; only `TEAM_ROLES` are addressable; the existing one-in-flight-per-recipient invariant + depth cap prevent runaway loops. A human post resets depth to 0.
- TDD; commit `<type>: <description>`; gates `make coverage` (80%) + `make lint`; FE `pnpm vitest run` + `pnpm tsc --noEmit` + `pnpm build`.
- Out of scope (later slices): structured `file_write` cards from the runtime; agents using tools/reading the repo mid-chat (Phase-3 replies are tool-less conversational replies); per-thread token/cost budget enforcement (ties into A5d).

---

## File structure

**Backend (`projects/server/src`)**
- Modify `domain/runs/messages.py` — add `MessageType.CHAT`; add `chat_recipient(work_item_id, role)`.
- Create `domain/messaging/dispatch.py` — `MAX_FANOUT_DEPTH`, `ChatDispatch` value + `plan_dispatch(text, depth) -> list[str]` (targets under the depth cap).
- Create `domain/messaging/chat.py` — `ChatTurn` (role+content), `ChatResponder` Protocol (`respond(role, history, title) -> str`).
- Create `adapters/agent/chat/echo.py` — `EchoChatResponder`.
- Create `adapters/agent/chat/llm.py` — `LlmChatResponder(llm: LLMAdapter, model_aliases)`.
- Modify `adapters/agent/factory.py` — `build_chat_responder(settings)`.
- Modify `interactors/worker/handlers.py` — `HandlerContext.chat_responder`; `handle_chat`; `dispatch` routes `CHAT`.
- Modify `interactors/worker/subscription_runner.py` — pass `chat_responder`; ensure the worker claims all `TEAM_ROLES` for chat (role set).
- Modify `interactors/worker/bus_source.py` — `chat_responder=None` on the dead-letter path.
- Modify `interactors/api/routes/threads.py` — `POST …/messages` publishes CHAT for `route_targets`.

**Backend tests (`projects/server/tests`)**
- Create `tests/domain/messaging/test_dispatch.py`.
- Create `tests/interactors/worker/test_chat_dispatch.py` (echo responder end-to-end + depth guard).
- Modify `tests/api/test_threads_api.py` (post now dispatches — replace the old bus-isolation test).

**Frontend (`projects/ui/src`)**
- Modify `components/thread/ThreadComposer.tsx` — `@role` mention chips (click-to-insert) so humans can address agents.
- Modify its test.

---

## Task 1: Bus `CHAT` type + work-item recipient

**Files:**
- Modify: `projects/server/src/domain/runs/messages.py`
- Test: `projects/server/tests/domain/messaging/test_dispatch.py` (also covers Task 2; create in Task 2 — here add a focused unit)

**Interfaces:**
- Produces: `MessageType.CHAT = "chat"`; `chat_recipient(work_item_id: str, role: str) -> str` returning `f"wi:{work_item_id}:{role}"`.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/messaging/test_dispatch.py` with (more added in Task 2):

```python
from domain.runs.messages import MessageType, chat_recipient


def test_chat_message_type_exists():
    assert MessageType.CHAT.value == "chat"


def test_chat_recipient_is_work_item_scoped():
    assert chat_recipient("wi1", "backend") == "wi:wi1:backend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_dispatch.py -q`
Expected: FAIL (`AttributeError: CHAT` / `ImportError: chat_recipient`).

- [ ] **Step 3: Write minimal implementation**

In `domain/runs/messages.py`, add `CHAT = "chat"` to `MessageType`, and add below `recipient_key`:

```python
def chat_recipient(work_item_id: str, role: str) -> str:
    return f"wi:{work_item_id}:{role}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_dispatch.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/runs/messages.py projects/server/tests/domain/messaging/test_dispatch.py
git commit -m "feat: bus CHAT message type + work-item-scoped recipient key"
```

---

## Task 2: Fan-out dispatch planning + depth guard (domain)

**Files:**
- Create: `projects/server/src/domain/messaging/dispatch.py`
- Test: `projects/server/tests/domain/messaging/test_dispatch.py` (extend)

**Interfaces:**
- Consumes: `route_targets` (`domain/messaging/mentions.py`).
- Produces: `MAX_FANOUT_DEPTH = 4`; `plan_dispatch(text: str, depth: int) -> list[str]` — returns `route_targets(text)` when `depth < MAX_FANOUT_DEPTH`, else `[]` (the cap is reached, stop fanning out).

- [ ] **Step 1: Write the failing test** — append to `tests/domain/messaging/test_dispatch.py`:

```python
from domain.messaging.dispatch import MAX_FANOUT_DEPTH, plan_dispatch


def test_plan_dispatch_routes_mentions_below_cap():
    assert plan_dispatch("@backend look here", 0) == ["backend"]


def test_plan_dispatch_defaults_to_lead_below_cap():
    assert plan_dispatch("no mention", 0) == ["lead"]


def test_plan_dispatch_stops_at_the_depth_cap():
    assert plan_dispatch("@backend @qa keep going", MAX_FANOUT_DEPTH) == []
    assert plan_dispatch("@backend", MAX_FANOUT_DEPTH - 1) == ["backend"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_dispatch.py -q`
Expected: FAIL (`ModuleNotFoundError: domain.messaging.dispatch`).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/messaging/dispatch.py`:

```python
from domain.messaging.mentions import route_targets

MAX_FANOUT_DEPTH = 4  # max agent->agent hops before the thread pauses for a human


def plan_dispatch(text: str, depth: int) -> list[str]:
    """Roles to dispatch a message to at ``depth``.

    Below the cap, honour @mentions (or default to lead). At/above the cap,
    return no targets so an agent->agent chain cannot loop forever — a human
    message (depth 0) is required to continue.
    """
    if depth >= MAX_FANOUT_DEPTH:
        return []
    return route_targets(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_dispatch.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/dispatch.py projects/server/tests/domain/messaging/test_dispatch.py
git commit -m "feat: fan-out dispatch planning with a depth guard"
```

---

## Task 3: `ChatResponder` port + `EchoChatResponder`

**Files:**
- Create: `projects/server/src/domain/messaging/chat.py`
- Create: `projects/server/src/adapters/agent/chat/__init__.py`, `projects/server/src/adapters/agent/chat/echo.py`
- Test: `projects/server/tests/adapters/agent/test_echo_responder.py`

**Interfaces:**
- Produces: `ChatTurn(BaseModel){role: str, content: str}`; `ChatResponder(Protocol){ respond(self, role: str, history: list[ChatTurn], title: str) -> str }`; `EchoChatResponder` — deterministic, returns `f"[{role}] ack"` (and, if constructed with `mention=<role>`, appends ` @{mention}` so tests can drive fan-out).

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/agent/test_echo_responder.py`:

```python
from adapters.agent.chat.echo import EchoChatResponder
from domain.messaging.chat import ChatTurn


def test_echo_responds_with_role_ack():
    r = EchoChatResponder()
    out = r.respond("backend", [ChatTurn(role="user", content="hi")], "My Task")
    assert out == "[backend] ack"


def test_echo_can_mention_a_partner_for_fanout_tests():
    r = EchoChatResponder(mention="qa")
    out = r.respond("backend", [], "My Task")
    assert "@qa" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_echo_responder.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/messaging/chat.py`:

```python
from typing import Protocol

from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: str  # "user" or a team role (lead/backend/…)
    content: str


class ChatResponder(Protocol):
    def respond(self, role: str, history: list[ChatTurn], title: str) -> str: ...
```

Create `projects/server/src/adapters/agent/chat/__init__.py` (empty), and `projects/server/src/adapters/agent/chat/echo.py`:

```python
from domain.messaging.chat import ChatTurn


class EchoChatResponder:
    """Deterministic ChatResponder for offline/tests. Optionally mentions a
    partner role so fan-out/loop-guard behaviour can be driven without an LLM."""

    def __init__(self, mention: str | None = None):
        self._mention = mention

    def respond(self, role: str, history: list[ChatTurn], title: str) -> str:
        text = f"[{role}] ack"
        if self._mention:
            text += f" @{self._mention}"
        return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_echo_responder.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/chat.py projects/server/src/adapters/agent/chat/
git commit -m "feat: ChatResponder port + deterministic EchoChatResponder"
```

---

## Task 4: `LlmChatResponder` (LLM-backed) + factory

**Files:**
- Create: `projects/server/src/adapters/agent/chat/llm.py`
- Modify: `projects/server/src/adapters/agent/factory.py`
- Test: `projects/server/tests/adapters/agent/test_llm_responder.py`

**Interfaces:**
- Consumes: `LLMAdapter`, `LLMRequest`, `LLMMessage`, `MessageRole`, `LLMResponse` (`domain/agent/llm`); `FakeLLMAdapter` for the test.
- Produces: `LlmChatResponder(llm: LLMAdapter, model: str = "")` — maps `history` to a system persona + a single user transcript, calls `llm.complete(...)`, returns `response.text` (or the field the `LLMResponse` exposes — check `domain/agent/llm`). `build_chat_responder(settings) -> ChatResponder` returning `EchoChatResponder()` when `settings.agent_runtime == "fake"`, else `LlmChatResponder(build_llm_adapter(settings), …)`.

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/agent/test_llm_responder.py`. Inspect `adapters/agent/llm/fake.py` + `domain/agent/llm.py` for the exact `LLMResponse`/`LLMRequest` fields before writing:

```python
from adapters.agent.chat.llm import LlmChatResponder
from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.llm import LLMResponse  # confirm constructor fields
from domain.messaging.chat import ChatTurn


def test_llm_responder_returns_model_text():
    fake = FakeLLMAdapter(scripted=[LLMResponse(text="On it — checking middleware.py.")])
    r = LlmChatResponder(fake)
    out = r.respond("backend", [ChatTurn(role="user", content="@backend check auth")], "Auth task")
    assert out == "On it — checking middleware.py."
```

(If `LLMResponse` uses a field other than `text`, adjust both the fixture and the assertion to that field — the point is the responder returns the model's text verbatim.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_llm_responder.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/adapters/agent/chat/llm.py` (adapt field names to the real `domain/agent/llm` API — `run_stage` in `domain/agent/runtime.py` is the reference for constructing `LLMRequest`/`LLMMessage`):

```python
from domain.agent.llm import LLMAdapter, LLMMessage, LLMRequest, MessageRole
from domain.messaging.chat import ChatTurn

_PERSONA = (
    "You are the {role} agent on a software team, collaborating in a task thread. "
    "Reply concisely to the latest message. You may @mention another role "
    "(lead, architect, backend, frontend, qa, devops) to hand off or ask a question."
)


def _transcript(history: list[ChatTurn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in history)


class LlmChatResponder:
    def __init__(self, llm: LLMAdapter, model: str = ""):
        self._llm = llm
        self._model = model

    def respond(self, role: str, history: list[ChatTurn], title: str) -> str:
        request = LLMRequest(
            model=self._model,
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content=_PERSONA.format(role=role)),
                LLMMessage(
                    role=MessageRole.USER,
                    content=f"Task: {title}\n\nThread so far:\n{_transcript(history)}\n\n"
                            f"Reply as @{role}.",
                ),
            ],
        )
        return self._llm.complete(request).text
```

In `factory.py`, add (reuse the existing adapter builder used by `build_runtime`):

```python
def build_chat_responder(settings):
    from adapters.agent.chat.echo import EchoChatResponder
    if settings.agent_runtime == "fake":
        return EchoChatResponder()
    from adapters.agent.chat.llm import LlmChatResponder
    return LlmChatResponder(build_llm_adapter(settings))
```

(Use whatever the file already calls its LLM-adapter builder — check `factory.py`; `build_runtime` already constructs one. Match `settings.agent_runtime`'s real values.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_llm_responder.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/chat/llm.py projects/server/src/adapters/agent/factory.py projects/server/tests/adapters/agent/test_llm_responder.py
git commit -m "feat: LLM-backed ChatResponder + factory selection"
```

---

## Task 5: `handle_chat` — the worker dispatches and replies

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py`
- Modify: `projects/server/src/interactors/worker/subscription_runner.py`
- Modify: `projects/server/src/interactors/worker/bus_source.py`
- Test: `projects/server/tests/interactors/worker/test_chat_dispatch.py` (create)

**Interfaces:**
- Consumes: `chat_recipient` (Task 1), `plan_dispatch`/`MAX_FANOUT_DEPTH` (Task 2), `ChatResponder`/`ChatTurn` (Task 3), `Message`/`AuthorKind`/`MessageKind`.
- Produces: `HandlerContext.chat_responder` (a `ChatResponder | None`); `handle_chat(msg, ctx)`; `dispatch` routes `type == MessageType.CHAT` to it; a `_publish_chat(ctx, work_item_id, owner_id, role, depth)` helper.

`handle_chat(msg, ctx)`:
1. Read `work_item_id = msg.payload["work_item_id"]`, `depth = msg.payload.get("depth", 0)`, `role = msg.role`.
2. Load thread history: `ctx.messages.read_multi(filters={"thread_id": work_item_id}, order_by="created_at").results` → `[ChatTurn(role=(m.author_role or "user"), content=m.content) for m in rows]`.
3. `reply_text = ctx.chat_responder.respond(role, history, title)` (title via `_work_item_title`).
4. Post the reply: `narrate(ctx, run=None…)` won't fit (it needs a run); instead create the `Message` directly — author_kind=AGENT, author_role=role, kind=TEXT, thread_id=work_item_id, content=reply_text, run_id=None. (Add a small `_post_agent_message(ctx, work_item_id, role, content)` helper, or inline.)
5. Fan out: `for target in plan_dispatch(reply_text, depth + 1): _publish_chat(ctx, work_item_id, msg.owner_id, target, depth + 1)`.

`_publish_chat` publishes an `AgentMessage(owner_id, run_id="", recipient=chat_recipient(work_item_id, role), role=role, type=MessageType.CHAT, payload={"work_item_id": work_item_id, "depth": depth})`.

- [ ] **Step 1: Write the failing test**

Create `tests/interactors/worker/test_chat_dispatch.py`. Reuse the worker-test harness patterns in `tests/interactors/worker/` (build a `HandlerContext` with owner-scoped in-memory repos; here inject `chat_responder=EchoChatResponder(...)` and drain the bus). Two behaviors:

```python
# (a) a CHAT message to @backend produces an agent reply in the thread
def test_chat_dispatch_posts_agent_reply(...):
    # arrange: work item wid owned by owner; publish AgentMessage(type=CHAT, role="backend",
    #   recipient=chat_recipient(wid,"backend"), payload={"work_item_id": wid, "depth": 0})
    # act: drain the bus once (dispatch -> handle_chat with EchoChatResponder())
    msgs = uow.messages.read_multi(filters={"thread_id": wid}, order_by="created_at").results
    assert any(m.author_kind.value == "agent" and m.author_role == "backend"
               and m.content == "[backend] ack" for m in msgs)

# (b) the depth guard stops an @-mention chain (EchoChatResponder(mention="qa") ping-pong)
def test_chat_fanout_stops_at_max_depth(...):
    # arrange responder that always @mentions a partner; publish an initial CHAT at depth 0
    # act: drain the bus to quiescence
    # assert: number of agent messages is bounded (<= MAX_FANOUT_DEPTH + 1), not unbounded
    agent_msgs = [m for m in ...results if m.author_kind.value == "agent"]
    assert len(agent_msgs) <= MAX_FANOUT_DEPTH + 1
```

For (b), use `EchoChatResponder(mention="qa")` for the backend role and `EchoChatResponder(mention="backend")` for qa — or a single responder that mentions a fixed partner — so the chain would loop forever without the guard; assert it terminates.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_dispatch.py -q`
Expected: FAIL (`dispatch` raises "unknown role" for a CHAT to a role with no `_HANDLERS` entry, or no reply is posted).

- [ ] **Step 3: Write minimal implementation**

In `handlers.py`:
- Add `chat_responder: Any = None` to `HandlerContext` (among the trailing defaulted fields, like `messages`).
- Import `chat_recipient`, `MessageType` (already imported), `plan_dispatch`, `ChatTurn`, `MessageKind`/`AuthorKind`/`Message` (Phase-2 imports likely already present).
- Add the helpers + `handle_chat` per **Interfaces** above.
- In `dispatch`, route CHAT before the role-handler lookup:

```python
def dispatch(msg: AgentMessage, ctx: HandlerContext) -> None:
    if msg.type is MessageType.CHAT:
        handle_chat(msg, ctx)
        return
    handler = _HANDLERS.get(msg.role)
    if handler is None:
        raise ValueError(f"unknown role: {msg.role!r}")
    handler(msg, ctx)
```

In `subscription_runner.py` `ctx_factory`, pass `chat_responder=build_chat_responder(_s)` (import `build_chat_responder` from `adapters.agent.factory`). Ensure the worker's claimed role set includes all `TEAM_ROLES` so any mentioned role's CHAT is claimed — check how the role set is configured (`naaf_worker_roles` / the bound roles in `subscription_runner`); if the worker is role-filtered, the plan's local/dev default must claim all `TEAM_ROLES`. In `bus_source.py`, add `chat_responder=None,` to the dead-letter `HandlerContext`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_dispatch.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/src/interactors/worker/subscription_runner.py projects/server/src/interactors/worker/bus_source.py projects/server/tests/interactors/worker/test_chat_dispatch.py
git commit -m "feat: handle_chat dispatches thread mentions to role-agents with a depth guard"
```

---

## Task 6: `POST /threads/{id}/messages` dispatches to the bus

**Files:**
- Modify: `projects/server/src/interactors/api/routes/threads.py`
- Test: `projects/server/tests/api/test_threads_api.py`

**Interfaces:**
- Consumes: `plan_dispatch` (Task 2), `chat_recipient`/`AgentMessage`/`MessageType` (Task 1), `get_bus`, `get_owner_id`.
- Produces: `post_message` now publishes a `CHAT` `AgentMessage` for each `plan_dispatch(content, 0)` target (human posts start at depth 0), alongside persisting the message.

- [ ] **Step 1: Write the failing test** — REPLACE the Phase-1 `test_post_message_does_not_touch_the_bus` (that invariant is intentionally reversed in Phase 3) and add:

```python
def test_post_message_dispatches_chat_to_mentioned_roles(client, session_factory):
    wid = _make_item(session_factory)
    client.post(f"/threads/{wid}/messages", json={"content": "@backend please check auth"})
    from adapters.database.orm import BusMessageRow
    with session_factory() as s:
        rows = s.query(BusMessageRow).all()
    chat = [r for r in rows if r.type == "chat"]
    assert len(chat) == 1
    assert chat[0].role == "backend"
    assert chat[0].recipient == f"wi:{wid}:backend"
    assert chat[0].payload.get("work_item_id") == wid
    assert chat[0].payload.get("depth") == 0


def test_post_message_with_no_mention_dispatches_to_lead(client, session_factory):
    wid = _make_item(session_factory)
    client.post(f"/threads/{wid}/messages", json={"content": "status?"})
    from adapters.database.orm import BusMessageRow
    with session_factory() as s:
        chat = [r for r in s.query(BusMessageRow).all() if r.type == "chat"]
    assert [r.role for r in chat] == ["lead"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -k "dispatch" -q`
Expected: FAIL (no bus rows — post is persist-only).

- [ ] **Step 3: Write minimal implementation**

In `threads.py`, add `get_bus`, `get_owner_id`, `plan_dispatch`, `chat_recipient`, `AgentMessage`, `MessageType`, `MessageBus` imports. Change `post_message` to accept `bus: MessageBus = Depends(get_bus)` and `owner_id: str = Depends(get_owner_id)`, and after `created = uow.messages.create(...)` add:

```python
    for role in plan_dispatch(payload.content, 0):
        bus.publish(AgentMessage(
            owner_id=owner_id,
            run_id="",
            recipient=chat_recipient(wid, role),
            role=role,
            type=MessageType.CHAT,
            payload={"work_item_id": wid, "depth": 0, "trigger_message_id": created.id},
        ))
```

(`wid` is the work-item id already resolved in the handler. Publishing after persist keeps the human message first in the thread. The bus publish shares the request UoW/transaction — same pattern as `start_run` in `runs.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -q`
Expected: PASS (the two new tests + the rest; the removed bus-isolation test is gone).

- [ ] **Step 5: Full backend gate**

Run: `cd projects/server && uv run pytest -q && make lint`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/routes/threads.py projects/server/tests/api/test_threads_api.py
git commit -m "feat: posting a thread message dispatches @mentions to the agent bus"
```

---

## Task 7: FE — `@role` mention chips in the composer

**Files:**
- Modify: `projects/ui/src/components/thread/ThreadComposer.tsx`
- Test: `projects/ui/src/components/thread/ThreadComposer.test.tsx` (create if absent)

**Interfaces:**
- Produces: a row of `@role` chips (`lead/architect/backend/frontend/qa/devops`) under the composer input; clicking one inserts `@role ` into the input value (so a human can address an agent without remembering the vocabulary). No API shape change — the existing `useSendMessage` POST already carries the content, and the backend (Task 6) dispatches.

- [ ] **Step 1: Write the failing test**

Create `ThreadComposer.test.tsx`: render the composer, click the `@backend` chip, assert the input value now contains `@backend`. (Wrap with `QueryClientProvider`; mock `useSendMessage` or provide a client — mirror `ConversationPane.test.tsx` setup.)

```tsx
it("inserts a role mention when a chip is clicked", async () => {
  renderWithClient(<ThreadComposer workItemId="wi1" />);
  screen.getByRole("button", { name: "@backend" }).click();
  expect(screen.getByPlaceholderText(/message/i)).toHaveValue("@backend ");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/components/thread/ThreadComposer.test.tsx`
Expected: FAIL (no chips).

- [ ] **Step 3: Implement** — add a `ROLES` const and a chip row in `ThreadComposer.tsx`; each chip is a `<button type="button">@{role}</button>` whose `onClick` sets `value` to `` `${value}${value && !value.endsWith(" ") ? " " : ""}@${role} ` `` (append with a separating space). Keep existing send behavior. Style to match the design D3 composer chips (small mono pills).

- [ ] **Step 4: Run tests + gates**

Run: `cd projects/ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/thread/ThreadComposer.tsx projects/ui/src/components/thread/ThreadComposer.test.tsx
git commit -m "feat: @role mention chips in the thread composer"
```

---

## Task 8: Docs + full verification, open PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Note the change** — add a "Work-item threads (Phase 3) — built" paragraph: posting a thread message now dispatches `@mention`s (or, with none, `@lead`) onto work-item-scoped bus queues (`wi:{id}:{role}`, `type=CHAT`); the worker's `handle_chat` wakes the role-agent (a `ChatResponder` — `EchoChatResponder` offline, `LlmChatResponder` via the `LLMAdapter` port), posts its reply into the thread, and re-dispatches the reply's mentions up to `MAX_FANOUT_DEPTH` (agent↔agent, bounded; a human message resets depth). FE: `@role` mention chips in the composer. Closes `docs/TODO.md` ("agents discover and dispatch messages to each other"). Still deferred: structured `file_write` cards, tools-in-chat (agents reading the repo mid-conversation), per-thread token/cost budget (A5d).

- [ ] **Step 2: Full gates**

Run:
```bash
cd projects/server && make coverage && make lint
cd ../ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build
```
Expected: backend ≥80% + lint clean; frontend green.

- [ ] **Step 3: Commit + push + PR**

```bash
git add docs/project-history.md
git commit -m "docs: record work-item threads phase 3"
git push -u origin docs/work-item-thread-phase3
gh pr create --title "feat: @mention dispatch — agents reply and coordinate in the thread (phase 3)" \
  --body "$(cat <<'EOF'
## Summary
- Posting a thread message dispatches its `@mention`s (or `@lead` by default) onto work-item-scoped bus queues (`wi:{id}:{role}`, `type=CHAT`).
- The worker's `handle_chat` wakes the role-agent via a `ChatResponder` port (`EchoChatResponder` offline / `LlmChatResponder` through the existing `LLMAdapter`), posts its reply into the thread, and re-dispatches the reply's mentions — agent↔agent — bounded by `MAX_FANOUT_DEPTH` (a human message resets depth).
- FE: `@role` mention chips in the composer.

Completes the thread-as-substrate design (Phases 1 #33, 2 #35). Deferred: structured file_write cards, tools-in-chat, per-thread budget (A5d). Spec: docs/superpowers/specs/2026-07-03-work-item-thread-substrate-design.md

## Test plan
- Backend: CHAT type + recipient, depth-guarded `plan_dispatch`, echo + LLM responders, `handle_chat` reply + fan-out-stops-at-cap, `POST /threads/.../messages` dispatch — `make coverage` ≥80%, `make lint` clean.
- Frontend: composer mention chips — `pnpm vitest run`, `pnpm tsc --noEmit`, `pnpm build`.
EOF
)"
```

---

## Self-review

**Spec coverage (Phase 3 rows):**
- `@mention` → bus dispatch → Tasks 1, 6 (human entry) + Task 5 (agent fan-out). ✓
- Agent replies into the thread → Tasks 3, 4, 5. ✓
- Default-to-lead when no mention → Task 2 (`plan_dispatch`→`route_targets`) + Task 6. ✓
- Loop guards (depth cap, team-role addressing, one-in-flight) → Task 2 (`MAX_FANOUT_DEPTH`), Task 5 (fan-out at depth+1), existing bus invariant. ✓
- Out of scope (file_write cards, tools-in-chat, budget) → not in any task; noted in Task 8.

**Placeholder scan:** No banned placeholders; every code step has concrete code. Tasks 4 and 5 explicitly instruct verifying the real `LLMResponse`/`LLMRequest` field names and the worker-test harness before coding (the plan cannot invent APIs it hasn't confirmed) and give the exact assertions to hit.

**Type/name consistency:** `chat_recipient(work_item_id, role)` (Task 1) used in Tasks 5–6; `MessageType.CHAT` (Task 1) in Tasks 5–6; `plan_dispatch(text, depth)`/`MAX_FANOUT_DEPTH` (Task 2) in Tasks 5–6; `ChatResponder.respond(role, history, title)` + `ChatTurn` (Task 3) in Tasks 4–5; `HandlerContext.chat_responder` (Task 5) built by `build_chat_responder` (Task 4). CHAT payload keys `{work_item_id, depth, trigger_message_id}` consistent between Task 5 (`_publish_chat`/`handle_chat`) and Task 6 (`post_message`).

**Open risks to confirm during implementation (flagged in-task):**
- The exact `LLMResponse` text field and `LLMRequest`/`LLMMessage` constructor (Task 4) — mirror `domain/agent/runtime.py::run_stage`.
- The worker's claimed-role set must include all `TEAM_ROLES` so any mentioned role's CHAT is claimed (Task 5) — verify against `subscription_runner`/`naaf_worker_roles`; a role-filtered worker that doesn't claim a mentioned role would leave that CHAT unprocessed.
- `AgentMessage.run_id=""` for chat — confirm `BusMessageRow.run_id` accepts an empty string (nullable/`""`); if it is non-nullable with a FK-like constraint, store the work-item id there instead and keep `payload.work_item_id` authoritative.
