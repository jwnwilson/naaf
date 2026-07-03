"""Tests for handle_chat.

Verifies agent replies are posted and the depth guard terminates chains.
"""

from dataclasses import dataclass, field

from adapters.agent.chat.echo import EchoChatResponder
from domain.base import new_id, utcnow
from domain.errors import RecordNotFound
from domain.messaging.dispatch import MAX_FANOUT_DEPTH
from domain.messaging.message import AuthorKind, Message
from domain.runs.messages import AgentMessage, MessageType, chat_recipient
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.worker import handlers
from interactors.worker.handlers import HandlerContext

OWNER = "dev-user"


# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeBus:
    published: list = field(default_factory=list)

    def publish(self, msg) -> None:
        self.published.append(msg)


class FakeWorkItemRepo:
    def __init__(self):
        self.saved: dict = {}

    def create(self, wi):
        self.saved[wi.id] = wi
        return wi

    def read(self, id_):
        try:
            return self.saved[id_]
        except KeyError:
            raise RecordNotFound(id_) from None


class _Page:
    def __init__(self, results):
        self.results = results


class FakeMessageRepo:
    def __init__(self):
        self.saved: dict = {}

    def create(self, msg: Message) -> Message:
        msg_id = msg.id or new_id()
        owner = msg.owner_id or OWNER
        stored = msg.model_copy(update={"id": msg_id, "owner_id": owner,
                                        "created_at": msg.created_at or utcnow()})
        self.saved[stored.id] = stored
        return stored

    def read(self, id_):
        try:
            return self.saved[id_]
        except KeyError:
            raise RecordNotFound(id_) from None

    def read_multi(self, filters=None, order_by=None, page_size=None, page_number=None):
        results = list(self.saved.values())
        if filters:
            thread_id = filters.get("thread_id")
            if thread_id:
                results = [m for m in results if m.thread_id == thread_id]
        if order_by == "created_at":
            results = sorted(results, key=lambda m: m.created_at or utcnow())
        return _Page(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(chat_responder) -> tuple[HandlerContext, FakeWorkItemRepo, FakeMessageRepo, FakeBus]:
    work_items = FakeWorkItemRepo()
    messages = FakeMessageRepo()
    bus = FakeBus()
    ctx = HandlerContext(
        runs=None,
        run_events=None,
        work_items=work_items,
        notifications=None,
        bus=bus,
        runtime=None,
        messages=messages,
        chat_responder=chat_responder,
    )
    return ctx, work_items, messages, bus


def _make_chat_msg(wid: str, role: str, depth: int = 0) -> AgentMessage:
    return AgentMessage(
        owner_id=OWNER,
        run_id="",
        recipient=chat_recipient(wid, role),
        role=role,
        type=MessageType.CHAT,
        payload={"work_item_id": wid, "depth": depth},
    )


def _drain(bus: FakeBus, ctx: HandlerContext) -> None:
    """Drain all published chat messages from the bus by dispatching them."""
    while bus.published:
        msg = bus.published.pop(0)
        handlers.dispatch(msg, ctx)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chat_dispatch_posts_agent_reply():
    """A CHAT message to @backend produces an agent reply in the thread."""
    wid = "wi-chat-1"
    wi = WorkItem(id=wid, owner_id=OWNER, project_id="p1", kind=WorkItemKind.TASK,
                  title="Auth task", status=WorkItemStatus.IN_PROGRESS)
    ctx, work_items, messages, bus = _make_ctx(EchoChatResponder())
    work_items.create(wi)

    msg = _make_chat_msg(wid, "backend", depth=0)
    handlers.dispatch(msg, ctx)

    agent_msgs = [
        m for m in messages.saved.values()
        if m.thread_id == wid and m.author_kind == AuthorKind.AGENT
    ]
    assert len(agent_msgs) == 1
    assert agent_msgs[0].author_role == "backend"
    assert agent_msgs[0].content == "[backend] ack"


def test_chat_fanout_stops_at_max_depth():
    """The depth guard terminates a would-be-infinite echo ping-pong chain."""
    wid = "wi-chat-2"
    wi = WorkItem(id=wid, owner_id=OWNER, project_id="p1", kind=WorkItemKind.TASK,
                  title="Loop task", status=WorkItemStatus.IN_PROGRESS)
    # Responder always @mentions qa — without the guard this would loop forever
    ctx, work_items, messages, bus = _make_ctx(EchoChatResponder(mention="qa"))
    work_items.create(wi)

    # Seed the chain with an initial backend CHAT at depth 0
    bus.published.append(_make_chat_msg(wid, "backend", depth=0))
    _drain(bus, ctx)

    agent_msgs = [
        m for m in messages.saved.values()
        if m.author_kind == AuthorKind.AGENT and m.thread_id == wid
    ]
    assert len(agent_msgs) == MAX_FANOUT_DEPTH, (
        f"Expected exactly {MAX_FANOUT_DEPTH} agent messages, got {len(agent_msgs)}"
    )
