from domain.agent.events import EVENT_FINAL, EVENT_STATUS
from domain.messaging.chat import ChatTurn
from domain.runs.messages import AgentMessage, MessageType
from interactors.worker.handlers import HandlerContext, build_event_sink, handle_chat


class _Recorder:
    def __init__(self):
        self.events = []

    def create(self, dto):
        self.events.append(dto)
        return dto


class _Responder:
    """Fake chat responder that drives the sink like the real streaming adapter."""
    def __init__(self):
        self._emit = None

    def set_event_sink(self, emit):
        self._emit = emit

    def respond(self, role, history, title):
        if self._emit:
            self._emit("text_block", {"text": "partial"})
        return "final reply"


class _Messages:
    def __init__(self):
        self.created = []

    def read_multi(self, **kw):
        class P:
            results: list = []
        return P()

    def create(self, dto):
        self.created.append(dto)
        return dto


def test_build_event_sink_persists_events_with_scope():
    rec = _Recorder()
    ctx = HandlerContext(runs=None, run_events=None, work_items=None, notifications=None,
                         bus=None, runtime=None, agent_events=rec)
    sink = build_event_sink(ctx, "thread:t")
    sink(EVENT_STATUS, {"state": "working"})
    assert rec.events[0].scope == "thread:t"
    assert rec.events[0].kind == EVENT_STATUS


def test_handle_chat_emits_status_then_final_around_reply(monkeypatch):
    rec = _Recorder()
    msgs = _Messages()
    ctx = HandlerContext(runs=None, run_events=None, work_items=None, notifications=None,
                         bus=None, runtime=None, agent_events=rec, messages=msgs,
                         chat_responder=_Responder())
    monkeypatch.setattr("interactors.worker.handlers._work_item_title_by_id", lambda c, w: "T")
    msg = AgentMessage(owner_id="u1", run_id="", recipient="wi:w1:backend", role="backend",
                       type=MessageType.CHAT, payload={"work_item_id": "w1", "depth": 0})
    handle_chat(msg, ctx)
    kinds = [e.kind for e in rec.events]
    assert kinds[0] == EVENT_STATUS
    assert EVENT_FINAL in kinds
    assert msgs.created and msgs.created[0].content == "final reply"
