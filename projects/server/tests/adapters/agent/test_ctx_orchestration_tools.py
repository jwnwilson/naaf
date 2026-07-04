import pytest
from adapters.agent.orchestration_tools import CtxOrchestrationTools
from adapters.database.uow import SqlUnitOfWork
from domain.errors import InvalidHierarchy
from domain.messaging.message import MessageKind
from domain.messaging.thread import project_thread_id
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind


class FakeBus:
    def __init__(self):
        self.published = []

    def publish(self, msg):
        self.published.append(msg)


def _tools(uow, project_id):
    return CtxOrchestrationTools(
        work_items=uow.work_items,
        projects=uow.projects,
        messages=uow.messages,
        bus=FakeBus(),
        owner_id="u1",
        project_id=project_id,
    )


def test_create_work_item_enforces_hierarchy_and_persists(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="naaf"))
        epic = uow.work_items.create(WorkItem(
            owner_id="", project_id=project.id, kind=WorkItemKind.EPIC, title="Auth"))
        tools = _tools(uow, project.id)

        res = tools.create_work_item("feature", "OAuth", parent_id=epic.id)
        assert "created feature" in res
        items = uow.work_items.read_multi(filters={"project_id": project.id}).results
        features = [w for w in items if w.kind is WorkItemKind.FEATURE]
        assert [f.title for f in features] == ["OAuth"]


def test_create_task_under_epic_is_invalid(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="naaf"))
        epic = uow.work_items.create(WorkItem(
            owner_id="", project_id=project.id, kind=WorkItemKind.EPIC, title="Auth"))
        tools = _tools(uow, project.id)
        with pytest.raises(InvalidHierarchy):
            tools.create_work_item("task", "Login route", parent_id=epic.id)


def test_propose_run_posts_a_run_proposal_question(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="naaf"))
        tools = _tools(uow, project.id)
        tools.propose_run(["t1", "t2"])

        msgs = uow.messages.read_multi(filters={"thread_id": project_thread_id(project.id)}).results
        assert len(msgs) == 1
        q = msgs[0]
        assert q.kind is MessageKind.QUESTION
        assert q.payload["run_proposal"] is True
        assert q.payload["work_item_ids"] == ["t1", "t2"]
