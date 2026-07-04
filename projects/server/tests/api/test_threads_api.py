from adapters.database.orm import BusMessageRow
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.question import question_payload
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _make_item(session_factory, owner="dev-user", wid="wi1", title="OAuth refresh") -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        item = uow.work_items.create(WorkItem(
            id=wid, owner_id="", project_id="p1", kind=WorkItemKind.TASK,
            title=title, status=WorkItemStatus.IN_PROGRESS,
        ))
    return item.id


def test_list_threads_are_work_items(client, session_factory):
    wid = _make_item(session_factory)
    body = client.get("/threads").json()
    assert body["success"]
    row = next(t for t in body["data"] if t["id"] == wid)
    assert row["workItemId"] == wid
    assert row["title"] == "OAuth refresh"
    assert row["status"] == "in_progress"
    assert "owner_id" not in row


def test_post_then_list_messages_oldest_first(client, session_factory):
    wid = _make_item(session_factory)
    client.post(f"/threads/{wid}/messages", json={"content": "first"})
    client.post(f"/threads/{wid}/messages", json={"content": "second"})
    body = client.get(f"/threads/{wid}/messages").json()
    assert [m["content"] for m in body["data"]] == ["first", "second"]
    assert body["data"][0]["authorKind"] == "user"
    assert body["data"][0]["threadId"] == wid


def test_post_parses_mentions_and_defaults_author_user(client, session_factory):
    wid = _make_item(session_factory)
    res = client.post(f"/threads/{wid}/messages", json={"content": "@backend do the thing"})
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["authorKind"] == "user"
    assert data["kind"] == "text"
    assert data["mentions"] == ["backend"]


def test_empty_content_is_rejected(client, session_factory):
    wid = _make_item(session_factory)
    assert client.post(f"/threads/{wid}/messages", json={"content": "   "}).status_code == 422


def test_foreign_thread_is_404(client, session_factory):
    other = _make_item(session_factory, owner="someone-else", wid="wi9")
    assert client.get(f"/threads/{other}/messages").status_code == 404
    assert client.post(f"/threads/{other}/messages", json={"content": "x"}).status_code == 404


def test_thread_detail_returns_files_written(client, session_factory):
    wid = _make_item(session_factory)
    body = client.get(f"/threads/{wid}").json()
    assert body["success"]
    assert body["data"]["id"] == wid
    assert body["data"]["filesWritten"] == []


def _seed_agent_message(session_factory, wid, role, content, model=None, owner="dev-user"):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        uow.messages.create(Message(
            owner_id="", thread_id=wid, author_kind=AuthorKind.AGENT,
            author_role=role, model_alias=model, content=content,
        ))


def test_thread_detail_enriches_participants_with_name_and_model(client, session_factory):
    wid = _make_item(session_factory)
    _seed_agent_message(session_factory, wid, "lead", "assigning")
    _seed_agent_message(session_factory, wid, "backend", "on it", model="claude-opus-4")
    client.post(f"/threads/{wid}/messages", json={"content": "use option B"})  # user

    data = client.get(f"/threads/{wid}").json()["data"]
    by_role = {p["role"]: p for p in data["participantDetails"]}
    assert by_role["lead"]["name"] == "Lead Agent"
    assert by_role["backend"]["model"] == "claude-opus-4"
    assert by_role["backend"]["status"] == "idle"  # no active run
    assert by_role["user"]["kind"] == "user"
    assert by_role["user"]["model"] is None


def test_thread_detail_marks_participant_running_from_active_run_stage(client, session_factory):
    from domain.runs.run import RunStatus, Stage, StageState, StageStatus
    wid = _make_item(session_factory, wid="wi_run")
    _seed_agent_message(session_factory, wid, "backend", "working")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.runs.create(Run(
            owner_id="", work_item_id=wid, project_id="p1", autonomy_level="gated_all",
            status=RunStatus.RUNNING,
            stages=[StageState(stage=Stage.IMPLEMENT, status=StageStatus.RUNNING, role="backend")],
        ))

    data = client.get(f"/threads/{wid}").json()["data"]
    backend = next(p for p in data["participantDetails"] if p["role"] == "backend")
    assert backend["status"] == "running"


def _seed_question(session_factory, owner="dev-user"):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        wi = uow.work_items.create(WorkItem(
            owner_id="", project_id="p1", kind=WorkItemKind.TASK,
            title="Gated task", status=WorkItemStatus.IN_PROGRESS,
        ))
        run = uow.runs.create(Run(
            owner_id="", work_item_id=wi.id, project_id="p1", autonomy_level="gated_all"
        ))
        msg = uow.messages.create(Message(
            owner_id="",
            thread_id=wi.id,
            author_kind=AuthorKind.AGENT,
            author_role="lead",
            kind=MessageKind.QUESTION,
            content="Plan gate — review and approve to continue.",
            payload=question_payload(run.id, "plan"),
            run_id=run.id,
        ))
    return wi.id, run.id, msg.id


def test_answer_question_publishes_gate_resolution(client, session_factory):
    wid, run_id, msg_id = _seed_question(session_factory)
    res = client.post(f"/threads/{wid}/messages/{msg_id}/answer", json={"option": "approve"})
    assert res.status_code == 200
    with session_factory() as s:
        rows = s.query(BusMessageRow).filter(BusMessageRow.run_id == run_id).all()
    assert any(r.type == "gate_resolved" and r.payload.get("decision") == "approve" for r in rows)


def test_answer_rejects_unknown_option(client, session_factory):
    wid, _run_id, msg_id = _seed_question(session_factory)
    res = client.post(f"/threads/{wid}/messages/{msg_id}/answer", json={"option": "banana"})
    assert res.status_code == 422


def test_answer_foreign_thread_is_404(client, session_factory):
    other_wid, _r, msg_id = _seed_question(session_factory, owner="someone-else")
    res = client.post(
        f"/threads/{other_wid}/messages/{msg_id}/answer", json={"option": "approve"}
    )
    assert res.status_code == 404


def test_answer_already_resolved_is_409(client, session_factory):
    from domain.messaging.question import resolve_payload
    wid, run_id, msg_id = _seed_question(session_factory)
    # Mark the question message as already resolved before calling /answer
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        msg = uow.messages.read(msg_id)
        uow.messages.update(msg_id, msg.model_copy(update={
            "payload": resolve_payload(msg.payload, "approve")
        }))
    res = client.post(f"/threads/{wid}/messages/{msg_id}/answer", json={"option": "approve"})
    assert res.status_code == 409
    assert "already resolved" in res.json()["detail"]


def test_post_message_dispatches_chat_to_mentioned_roles(client, session_factory):
    # Arrange
    wid = _make_item(session_factory)

    # Act
    client.post(f"/threads/{wid}/messages", json={"content": "@backend please check auth"})

    # Assert — one CHAT bus row for backend at depth 0
    with session_factory() as s:
        rows = s.query(BusMessageRow).all()
    chat = [r for r in rows if r.type == "chat"]
    assert len(chat) == 1
    assert chat[0].role == "backend"
    assert chat[0].recipient == f"wi:{wid}:backend"
    assert chat[0].payload.get("work_item_id") == wid
    assert chat[0].payload.get("depth") == 0


def test_post_message_with_no_mention_dispatches_to_lead(client, session_factory):
    # Arrange
    wid = _make_item(session_factory)

    # Act
    client.post(f"/threads/{wid}/messages", json={"content": "status?"})

    # Assert — one CHAT bus row for lead (default)
    with session_factory() as s:
        chat = [r for r in s.query(BusMessageRow).all() if r.type == "chat"]
    assert [r.role for r in chat] == ["lead"]
