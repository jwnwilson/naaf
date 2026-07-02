from adapters.bus.factory import build_message_bus
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.source import Item, PoisonOutcome
from domain.project import Project
from domain.runs.events import EventType
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run, RunStatus
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.worker.bus_source import BusSource


def _msg(run_id="r1", owner_id="u1", role="lead"):
    return AgentMessage(
        owner_id=owner_id,
        run_id=run_id,
        recipient=recipient_key(run_id, role),
        role=role,
        type=MessageType.START,
    )


def _sys_uow(session_factory):
    return SqlUnitOfWork(session_factory)  # no owner filter — system level


def _publish(session_factory, role):
    s = session_factory()
    build_message_bus(s).publish(AgentMessage(owner_id="u1", run_id="r1",
        recipient=recipient_key("r1", role), role=role, type=MessageType.START))
    s.commit()
    s.close()


def test_bus_source_only_fetches_configured_roles(session_factory):
    """BusSource(roles=['backend']) only claims messages for that role."""
    _publish(session_factory, "lead")
    _publish(session_factory, "backend")
    source = BusSource(roles=["backend"])
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        item = source.fetch_next(uow)
    assert item is not None and item.message.role == "backend"


def test_fetch_next_returns_item_and_advance_acks(session_factory):
    """fetch_next claims a pending message as Item; advance acks it so second fetch is None."""
    # Arrange
    s = session_factory()
    msg = _msg()
    build_message_bus(s).publish(msg)
    s.commit()
    s.close()

    src = BusSource()

    # Act: fetch_next inside a transaction
    uow = _sys_uow(session_factory)
    with uow.transaction():
        item = src.fetch_next(uow)
        assert item is not None
        assert item.owner_id == "u1"
        assert item.message.id == msg.id
        assert item.position == 0
        src.advance(item, uow)

    # Assert: message is done — second fetch returns None
    uow2 = _sys_uow(session_factory)
    with uow2.transaction():
        assert src.fetch_next(uow2) is None


def test_fetch_next_returns_none_when_empty(session_factory):
    """fetch_next returns None when the bus is empty."""
    src = BusSource()
    uow = _sys_uow(session_factory)
    with uow.transaction():
        assert src.fetch_next(uow) is None


def test_on_poison_fails_run_acks_message_returns_continue(session_factory):
    """on_poison acks the message, marks the run FAILED with ended_at set,
    emits a RUN_FINISHED event, and returns PoisonOutcome.CONTINUE."""
    # Arrange: seed a run
    owned = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with owned.transaction():
        project = owned.projects.create(Project(owner_id="", name="p1"))
        work_item = owned.work_items.create(
            WorkItem(
                owner_id="",
                project_id=project.id,
                kind=WorkItemKind.TASK,
                title="t1",
                status=WorkItemStatus.IN_PROGRESS,
            )
        )
        run = owned.runs.create(
            Run(
                owner_id="",
                work_item_id=work_item.id,
                project_id=project.id,
                autonomy_level="full_auto",
            )
        )

    # Publish and claim a message so we have an Item
    s = session_factory()
    msg = AgentMessage(
        owner_id="u1",
        run_id=run.id,
        recipient=recipient_key(run.id, "lead"),
        role="lead",
        type=MessageType.START,
    )
    build_message_bus(s).publish(msg)
    s.commit()
    s.close()

    s2 = session_factory()
    claimed = build_message_bus(s2).claim_next()
    s2.commit()
    s2.close()

    item = Item(message=claimed, owner_id=claimed.owner_id, position=0)

    # Act
    src = BusSource()
    outcome = src.on_poison(item, ValueError("boom"), lambda: SqlUnitOfWork(session_factory))

    # Assert: CONTINUE returned, run is FAILED with ended_at set, message not redelivered
    assert outcome is PoisonOutcome.CONTINUE

    owned2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with owned2.transaction():
        failed_run = owned2.runs.read(run.id)
        run_events = owned2.run_events.read_multi(filters={"run_id": run.id})

    assert failed_run.status == RunStatus.FAILED
    assert failed_run.ended_at is not None

    finished_events = [e for e in run_events.results if e.type == EventType.RUN_FINISHED]
    assert len(finished_events) == 1
    assert finished_events[0].payload["status"] == "failed"

    # Message should be acked (not redelivered)
    uow = _sys_uow(session_factory)
    with uow.transaction():
        assert src.fetch_next(uow) is None
