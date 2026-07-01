from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageStatus, MessageType, recipient_key
from domain.runs.run import Stage


def test_run_event_defaults():
    e = RunEvent(owner_id="u1", run_id="r1", type=EventType.LOG, role="lead", stage=Stage.PLAN)
    assert e.seq == 0
    assert e.payload == {}
    assert e.type is EventType.LOG


def test_recipient_key_and_message():
    assert recipient_key("r1", "engineer") == "run:r1:engineer"
    m = AgentMessage(owner_id="u1", run_id="r1", recipient="run:r1:lead",
                     role="lead", type=MessageType.START)
    assert m.status is MessageStatus.PENDING
    assert m.id  # auto id
