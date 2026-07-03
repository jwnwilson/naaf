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
