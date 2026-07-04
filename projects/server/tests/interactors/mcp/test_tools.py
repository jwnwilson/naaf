import pytest
from adapters.database.uow import SqlUnitOfWork
from domain.errors import InvalidHierarchy
from domain.messaging.message import MessageKind
from domain.messaging.thread import project_thread_id
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.mcp import tools


def _uow(session_factory, owner="u1"):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})


def _project(uow, name="naaf"):
    return uow.projects.create(Project(owner_id="", name=name))


def test_list_projects_and_create_hierarchy(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        p = _project(uow)
        assert [x["name"] for x in tools.list_projects(uow)] == ["naaf"]

        epic_msg = tools.create_work_item(uow, "u1", p.id, "epic", "Auth")
        assert "created epic" in epic_msg
        epic_id = epic_msg.split("id=")[-1]
        feat_msg = tools.create_work_item(uow, "u1", p.id, "feature", "OAuth", parent_id=epic_id)
        assert "created feature" in feat_msg

        with pytest.raises(InvalidHierarchy):
            tools.create_work_item(uow, "u1", p.id, "task", "bad", parent_id=epic_id)


def test_propose_run_posts_question(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        p = _project(uow)
        tools.propose_run(uow, "u1", p.id, ["t1", "t2"])
        msgs = uow.messages.read_multi(filters={"thread_id": project_thread_id(p.id)}).results
    assert len(msgs) == 1 and msgs[0].kind is MessageKind.QUESTION
    assert msgs[0].payload["work_item_ids"] == ["t1", "t2"]


def test_get_and_transition_and_start_run(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        p = _project(uow)
        task = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, kind=WorkItemKind.TASK, title="T",
            status=WorkItemStatus.TODO,
        ))
        got = tools.get_work_item(uow, task.id)
        assert got["kind"] == "task" and got["status"] == "todo"

        started = tools.start_run(uow, "u1", task.id)
        assert started["status"] in ("queued", "running")
        runs = tools.list_runs(uow, task.id)
        assert len(runs) == 1 and runs[0]["workItemId"] == task.id
        # item is now in_progress; transition back is a legal edge for the test
        assert tools.get_work_item(uow, task.id)["status"] == "in_progress"
