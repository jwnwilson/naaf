import pytest
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind
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


def _uow(factory):
    return SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})


def test_transaction_commits_multiple_writes_atomically(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        proj = uow.projects.create(Project(owner_id="u1", name="naaf"))
        uow.work_items.create(
            WorkItem(owner_id="u1", project_id=proj.id, kind=WorkItemKind.EPIC, title="Auth")
        )
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 1
    assert uow2.work_items.read_multi().total == 1


def test_transaction_rolls_back_on_error(session_factory):
    uow = _uow(session_factory)
    with pytest.raises(RuntimeError):
        with uow.transaction():
            uow.projects.create(Project(owner_id="u1", name="naaf"))
            raise RuntimeError("boom")
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 0


def test_delete_where_respects_owner_and_in_filter(session_factory):
    from adapters.database.uow import SqlUnitOfWork

    a = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a.transaction():
        p1 = a.projects.create(Project(owner_id="a", name="p1"))
        p2 = a.projects.create(Project(owner_id="a", name="p2"))

    other = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with other.transaction():
        pb = other.projects.create(Project(owner_id="b", name="pb"))

    a2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a2.transaction():
        removed = a2.projects.delete_where(id__in=[p1.id, p2.id, pb.id])
        assert removed == 2  # pb belongs to owner "b" and is filtered out

    b2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with b2.transaction():
        assert b2.projects.read(pb.id).id == pb.id  # untouched


def test_delete_project_cascade_removes_all_descendants(session_factory):
    from adapters.database.orm import BusMessageRow
    from adapters.database.uow import SqlUnitOfWork
    from domain.agent.events import EVENT_TEXT, AgentEvent
    from domain.attachments.attachment import Attachment
    from domain.errors import RecordNotFound
    from domain.messaging.message import Message
    from domain.notifications.notification import Notification, NotificationType
    from domain.runs.events import EventType, RunEvent
    from domain.runs.messages import AgentMessage, MessageType
    from domain.runs.run import Run
    from domain.work_item import WorkItem, WorkItemKind
    from sqlalchemy import func, select

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="u1", name="p"))
        wi = uow.work_items.create(
            WorkItem(owner_id="u1", project_id=p.id, kind=WorkItemKind.TASK, title="t")
        )
        run = uow.runs.create(
            Run(owner_id="u1", work_item_id=wi.id, project_id=p.id, autonomy_level="gated_all")
        )
        uow.run_events.create(RunEvent(owner_id="u1", run_id=run.id, type=EventType.LOG))
        uow.notifications.create(
            Notification(owner_id="u1", run_id=run.id, type=NotificationType.RUN_SUCCEEDED,
                         title="done", source_seq=1)
        )
        uow.bus_messages.publish(
            AgentMessage(owner_id="u1", run_id=run.id, recipient="run:x:lead",
                         role="lead", type=MessageType.START)
        )
        uow.attachments.create(
            Attachment(owner_id="u1", work_item_id=wi.id, filename="a.txt",
                       content_type="text/plain", size=1)
        )
        uow.messages.create(Message(owner_id="u1", thread_id=wi.id, content="hi"))
        uow.messages.create(Message(owner_id="u1", thread_id=f"project:{p.id}", content="proj"))
        uow.agent_events.create(AgentEvent(owner_id="u1", scope=f"run:{run.id}", kind=EVENT_TEXT))
        uow.agent_events.create(AgentEvent(owner_id="u1", scope=f"thread:{wi.id}", kind=EVENT_TEXT))
        uow.agent_events.create(
            AgentEvent(owner_id="u1", scope=f"thread:project:{p.id}", kind=EVENT_TEXT)
        )

    act = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with act.transaction():
        act.delete_project_cascade(p.id)

    check = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with check.transaction():
        assert check.work_items.read_multi(page_size=0).total == 0
        assert check.runs.read_multi(page_size=0).total == 0
        assert check.run_events.read_multi(page_size=0).total == 0
        assert check.notifications.read_multi(page_size=0).total == 0
        assert check.attachments.read_multi(page_size=0).total == 0
        assert check.messages.read_multi(page_size=0).total == 0
        assert check.agent_events.read_multi(page_size=0).total == 0
        bus_total = check.session.execute(
            select(func.count()).select_from(BusMessageRow)
        ).scalar_one()
        assert bus_total == 0
        with pytest.raises(RecordNotFound):
            check.projects.read(p.id)


def test_delete_where_cannot_bypass_owner_scope(session_factory):
    from adapters.database.uow import SqlUnitOfWork

    owner_b = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with owner_b.transaction():
        pb = owner_b.projects.create(Project(owner_id="b", name="pb"))

    # Owner "a" tries to delete owner "b"'s row by passing owner_id explicitly.
    owner_a = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with owner_a.transaction():
        removed = owner_a.projects.delete_where(owner_id="b", id=pb.id)
        assert removed == 0  # required owner scope ("a") wins; nothing matches

    check_b = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with check_b.transaction():
        assert check_b.projects.read(pb.id).id == pb.id  # untouched
