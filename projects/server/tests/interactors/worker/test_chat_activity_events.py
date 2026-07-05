"""Tests for the independent-commit event sink.

Design contract: build_event_sink opens its OWN SqlUnitOfWork per event and
commits immediately, so events are visible to a separate UoW (the polling SSE)
before the surrounding chat-turn transaction finishes.
"""
from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import EVENT_ERROR, EVENT_FINAL, EVENT_STATUS, stream_scope
from domain.runs.messages import AgentMessage, MessageType
from interactors.worker.handlers import HandlerContext, build_event_sink, handle_chat

# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------


class _Responder:
    """Fake chat responder; can call the injected sink or raise on demand."""

    def __init__(self, *, raises: Exception | None = None):
        self._emit = None
        self._raises = raises

    def set_event_sink(self, emit):
        self._emit = emit

    def respond(self, role, history, title):
        if self._raises:
            raise self._raises
        if self._emit:
            self._emit("text_block", {"text": "partial"})
        return "final reply"


class _FakeMessages:
    def __init__(self):
        self.created = []

    def read_multi(self, **kw):
        class _P:
            results: list = []

        return _P()

    def create(self, dto):
        self.created.append(dto)
        return dto


# ---------------------------------------------------------------------------
# Test 1 — each emit commits in its own transaction, visible to a second UoW
# ---------------------------------------------------------------------------


def test_build_event_sink_commits_each_event_independently(session_factory):
    """Calling sink() once is enough — a fresh UoW sees the event immediately."""
    scope = stream_scope(thread_id="t")
    owner_id = "u1"

    sink = build_event_sink(session_factory, owner_id, scope)
    assert sink is not None, "sink should be non-None when session_factory is provided"

    # Call with NO enclosing uow.transaction()
    sink(EVENT_STATUS, {"state": "working"})

    # A completely separate UoW must see the committed row
    reader = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with reader.transaction():
        events = reader.agent_events.list_after(scope, 0)

    assert len(events) == 1
    assert events[0].scope == scope
    assert events[0].kind == EVENT_STATUS
    assert events[0].payload == {"state": "working"}


# ---------------------------------------------------------------------------
# Test 2 — handle_chat persists status … final in order and posts a message
# ---------------------------------------------------------------------------


def test_handle_chat_persists_status_then_final(session_factory, monkeypatch):
    """handle_chat emits EVENT_STATUS before calling respond(), EVENT_FINAL after."""
    owner_id = "u2"
    work_item_id = "wi-abc"
    scope = stream_scope(thread_id=work_item_id)

    msgs = _FakeMessages()
    ctx = HandlerContext(
        runs=None,
        run_events=None,
        work_items=None,
        notifications=None,
        bus=None,
        runtime=None,
        messages=msgs,
        chat_responder=_Responder(),
        session_factory=session_factory,
    )
    monkeypatch.setattr(
        "interactors.worker.handlers._work_item_title_by_id", lambda c, w: "T"
    )

    msg = AgentMessage(
        owner_id=owner_id,
        run_id="",
        recipient=f"wi:{work_item_id}:backend",
        role="backend",
        type=MessageType.CHAT,
        payload={"work_item_id": work_item_id, "depth": 0},
    )
    handle_chat(msg, ctx)

    # Read back persisted events via a fresh UoW
    reader = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with reader.transaction():
        events = reader.agent_events.list_after(scope, 0)

    kinds = [e.kind for e in events]
    assert kinds[0] == EVENT_STATUS, f"first event should be status, got {kinds}"
    assert EVENT_FINAL in kinds, f"final event missing; got {kinds}"
    # Ensure the reply message was posted
    assert msgs.created, "agent message should have been posted"
    assert msgs.created[0].content == "final reply"


# ---------------------------------------------------------------------------
# Test 3 — error path: handle_chat re-raises AND persists an error event
# ---------------------------------------------------------------------------


def test_handle_chat_on_respond_error_posts_reason_and_does_not_raise(session_factory, monkeypatch):
    """When chat_responder.respond() raises, handle_chat must not propagate.

    Instead it commits an EVENT_ERROR row AND persists a visible agent message
    whose content contains the failure reason.
    """
    owner_id = "u3"
    work_item_id = "wi-err"
    scope = stream_scope(thread_id=work_item_id)

    msgs = _FakeMessages()
    ctx = HandlerContext(
        runs=None,
        run_events=None,
        work_items=None,
        notifications=None,
        bus=None,
        runtime=None,
        messages=msgs,
        chat_responder=_Responder(raises=RuntimeError("boom")),
        session_factory=session_factory,
    )
    monkeypatch.setattr(
        "interactors.worker.handlers._work_item_title_by_id", lambda c, w: "T"
    )

    msg = AgentMessage(
        owner_id=owner_id,
        run_id="",
        recipient=f"wi:{work_item_id}:backend",
        role="backend",
        type=MessageType.CHAT,
        payload={"work_item_id": work_item_id, "depth": 0},
    )

    handle_chat(msg, ctx)  # must not raise

    # Error event must have been committed independently
    reader = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with reader.transaction():
        events = reader.agent_events.list_after(scope, 0)

    kinds = [e.kind for e in events]
    assert EVENT_ERROR in kinds, f"error event missing; got {kinds}"
    error_event = next(e for e in events if e.kind == EVENT_ERROR)
    assert "boom" in error_event.payload.get("message", "")

    # A single visible agent message with the reason must have been posted
    assert len(msgs.created) == 1, f"expected 1 posted message, got {len(msgs.created)}"
    assert "boom" in msgs.created[0].content
