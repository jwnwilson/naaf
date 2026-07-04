from adapters.database.orm import BusMessageRow
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.question import run_proposal_payload
from domain.messaging.thread import project_thread_id
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _project(session_factory, owner="dev-user", name="naaf") -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name=name))
    return p.id


def test_get_project_thread_returns_project_name(client, session_factory):
    pid = _project(session_factory, name="naaf")
    body = client.get(f"/threads/{project_thread_id(pid)}").json()
    assert body["success"]
    assert body["data"]["id"] == project_thread_id(pid)
    assert body["data"]["title"] == "naaf"


def test_post_to_project_thread_persists_and_dispatches_to_lead(client, session_factory):
    pid = _project(session_factory)
    tid = project_thread_id(pid)
    res = client.post(f"/threads/{tid}/messages", json={"content": "build oauth login"})
    assert res.status_code == 201
    # message is listable under the project thread
    listed = client.get(f"/threads/{tid}/messages").json()["data"]
    assert [m["content"] for m in listed] == ["build oauth login"]
    # a CHAT bus row addressed to the project lead
    with session_factory() as s:
        chat = [r for r in s.query(BusMessageRow).all() if r.type == "chat"]
    assert len(chat) == 1
    assert chat[0].role == "lead"
    assert chat[0].recipient == f"proj:{pid}:lead"
    assert chat[0].payload.get("thread_id") == tid
    assert chat[0].payload.get("project_id") == pid


def test_missing_project_thread_is_404(client):
    assert client.get("/threads/project:deadbeef/messages").status_code == 404


def _seed_run_proposal(session_factory, owner="dev-user"):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name="naaf"))
        epic = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, kind=WorkItemKind.EPIC, title="E"))
        feat = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, parent_id=epic.id, kind=WorkItemKind.FEATURE, title="F"))
        task = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, parent_id=feat.id, kind=WorkItemKind.TASK,
            title="T", status=WorkItemStatus.TODO))
        q = uow.messages.create(Message(
            owner_id="", thread_id=project_thread_id(p.id),
            author_kind=AuthorKind.AGENT, author_role="lead", kind=MessageKind.QUESTION,
            content="Start development on these items?",
            payload=run_proposal_payload([task.id]),
        ))
    return p.id, task.id, q.id


def test_run_proposal_approve_starts_a_run(client, session_factory):
    pid, task_id, msg_id = _seed_run_proposal(session_factory)
    answer_url = f"/threads/{project_thread_id(pid)}/messages/{msg_id}/answer"
    res = client.post(answer_url, json={"option": "approve"})
    assert res.status_code == 200
    assert res.json()["data"]["payload"]["resolved_option"] == "approve"
    # a run now exists for the task and it is in_progress
    runs = client.get(f"/runs?work_item={task_id}").json()["data"]
    assert len(runs) == 1
    assert client.get(f"/work-items/{task_id}").json()["data"]["status"] == "in_progress"


def test_run_proposal_reject_starts_no_run(client, session_factory):
    pid, task_id, msg_id = _seed_run_proposal(session_factory)
    answer_url = f"/threads/{project_thread_id(pid)}/messages/{msg_id}/answer"
    res = client.post(answer_url, json={"option": "reject"})
    assert res.status_code == 200
    assert res.json()["data"]["payload"]["resolved_option"] == "reject"
    assert client.get(f"/runs?work_item={task_id}").json()["data"] == []
