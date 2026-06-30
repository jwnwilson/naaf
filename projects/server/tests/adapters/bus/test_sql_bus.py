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


def test_same_recipient_one_in_flight_fifo(session_factory):
    """Verify that two messages to the same recipient enforce one-in-flight + FIFO order.

    - Publish M1 (lead), then M2 (lead) → both pending
    - claim_next → returns M1 (older), M1 now in-flight
    - claim_next → returns None (M2 blocked: lead has in-flight M1)
    - ack(M1) → M1 done
    - claim_next → returns M2 (now unblocked)
    """
    bus = SqlMessageBus()
    s = session_factory()

    # Publish M1, commit to set created_at before M2
    m1 = _msg(role="lead", payload={"order": 1})
    bus.publish(m1, s)
    s.commit()

    # Publish M2 to same recipient
    m2 = _msg(role="lead", payload={"order": 2})
    bus.publish(m2, s)
    s.commit()

    # claim_next → returns M1 (older created_at)
    claimed1 = bus.claim_next(s)
    s.commit()
    assert claimed1 is not None
    assert claimed1.id == m1.id
    assert claimed1.payload == {"order": 1}
    assert claimed1.status == MessageStatus.CLAIMED

    # claim_next → returns None (M2 blocked by in-flight M1)
    claimed2 = bus.claim_next(s)
    s.commit()
    assert claimed2 is None

    # ack(M1) → M1 done, frees the recipient
    bus.ack(claimed1, s)
    s.commit()

    # claim_next → now returns M2 (previously blocked, now unblocked)
    claimed3 = bus.claim_next(s)
    s.commit()
    assert claimed3 is not None
    assert claimed3.id == m2.id
    assert claimed3.payload == {"order": 2}
    assert claimed3.status == MessageStatus.CLAIMED
