from datetime import UTC, datetime

import pytest
from adapters.database.orm import Base
from adapters.database.repositories import BusMessageRepository
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _pub(repo, role, owner="u1"):
    repo.publish(AgentMessage(owner_id=owner, run_id="r1",
        recipient=recipient_key("r1", role), role=role, type=MessageType.START))


def test_publish_claim_ack_round_trip(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead")
    claimed = repo.claim_next()
    assert claimed is not None and claimed.role == "lead"
    repo.ack(claimed)
    assert repo.claim_next() is None  # acked (done), nothing pending


def test_claim_next_filters_by_role(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead")
    _pub(repo, "engineer")
    assert repo.claim_next(["engineer"]).role == "engineer"


def test_claim_next_is_cross_owner(session):
    # a repo built with an owner filter still claims other owners' messages
    repo = BusMessageRepository(session, required_filters={"owner_id": "u2"})
    _pub(repo, "lead", owner="u1")
    assert repo.claim_next() is not None  # NOT owner-scoped


def test_busy_recipient_excluded(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead")  # same recipient run:r1:lead
    _pub(repo, "lead")
    first = repo.claim_next()
    assert first is not None
    # second message for the same recipient is blocked while the first is claimed
    assert repo.claim_next() is None


def test_fifo_ordering_and_post_ack_unblocking(session):
    # Arrange: two messages for the same recipient with explicit, ordered created_at
    repo = BusMessageRepository(session)
    t1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 1, 12, 0, 1, tzinfo=UTC)
    m1 = AgentMessage(
        id="m1fifo",
        owner_id="u1",
        run_id="r1",
        recipient=recipient_key("r1", "lead"),
        role="lead",
        type=MessageType.START,
        created_at=t1,
    )
    m2 = AgentMessage(
        id="m2fifo",
        owner_id="u1",
        run_id="r1",
        recipient=recipient_key("r1", "lead"),
        role="lead",
        type=MessageType.START,
        created_at=t2,
    )
    repo.publish(m1)
    repo.publish(m2)

    # Act + Assert: oldest message is claimed first
    first = repo.claim_next()
    assert first is not None and first.id == "m1fifo"

    # Recipient is busy — second message is blocked
    assert repo.claim_next() is None

    # After ack, the second message becomes claimable
    repo.ack(first)
    second = repo.claim_next()
    assert second is not None and second.id == "m2fifo"


def test_independent_recipients_both_claimable(session):
    # Arrange: one message per recipient (different roles, same run)
    repo = BusMessageRepository(session)
    repo.publish(AgentMessage(
        owner_id="u1", run_id="r1",
        recipient=recipient_key("r1", "lead"),
        role="lead", type=MessageType.START,
    ))
    repo.publish(AgentMessage(
        owner_id="u1", run_id="r1",
        recipient=recipient_key("r1", "engineer"),
        role="engineer", type=MessageType.START,
    ))

    # Act + Assert: different recipients do not block each other
    first = repo.claim_next(["lead"])
    second = repo.claim_next(["engineer"])
    assert first is not None
    assert second is not None


def test_no_matching_role_returns_none(session):
    # Arrange: only a "lead" message exists
    repo = BusMessageRepository(session)
    _pub(repo, "lead")

    # Act + Assert: claiming for "qa" finds nothing
    assert repo.claim_next(["qa"]) is None
