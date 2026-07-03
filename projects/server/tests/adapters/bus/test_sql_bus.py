import pytest
from adapters.bus.factory import build_message_bus
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_bus_adapter_delegates_publish_claim_ack(session_factory):
    uow = SqlUnitOfWork(session_factory)
    with uow.transaction():
        bus = build_message_bus(uow)
        bus.publish(AgentMessage(owner_id="u1", run_id="r1",
            recipient=recipient_key("r1", "lead"), role="lead", type=MessageType.START))
        claimed = bus.claim_next(["lead"])
        assert claimed is not None and claimed.role == "lead"
        bus.ack(claimed)
        assert bus.claim_next() is None
