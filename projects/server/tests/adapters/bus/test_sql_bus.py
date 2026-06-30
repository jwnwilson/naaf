from adapters.bus.sql import SqlMessageBus
from domain.runs.messages import AgentMessage, MessageStatus, MessageType, recipient_key


def _msg(run="r1", role="lead", **kw):
    return AgentMessage(owner_id="u1", run_id=run, recipient=recipient_key(run, role),
                        role=role, type=MessageType.START, **kw)


def test_publish_claim_ack_roundtrip(session_factory):
    bus = SqlMessageBus()
    s = session_factory()
    bus.publish(_msg(), s)
    s.commit()
    claimed = bus.claim_next(s)
    s.commit()
    assert claimed is not None and claimed.status is MessageStatus.CLAIMED
    again = bus.claim_next(s)
    s.commit()  # one-in-flight-per-recipient
    assert again is None
    bus.ack(claimed, s)
    s.commit()
    assert bus.claim_next(s) is None  # nothing pending


def test_fifo_per_recipient_and_independent_recipients(session_factory):
    bus = SqlMessageBus()
    s = session_factory()
    bus.publish(_msg(role="lead"), s)
    bus.publish(_msg(role="engineer"), s)
    s.commit()
    a = bus.claim_next(s)
    s.commit()
    b = bus.claim_next(s)
    s.commit()  # different recipient → claimable
    assert {a.role, b.role} == {"lead", "engineer"}
