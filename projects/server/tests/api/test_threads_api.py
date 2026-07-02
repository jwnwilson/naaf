from adapters.database.uow import SqlUnitOfWork
from domain.runs.run import Run


def _make_run(session_factory, owner="dev-user", wid="w1") -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wid, project_id="p1", autonomy_level="gated_all")
        )
    return run.id


def test_list_threads_projects_runs(client, session_factory):
    run_id = _make_run(session_factory)
    body = client.get("/threads").json()
    assert body["success"]
    row = next(t for t in body["data"] if t["id"] == run_id)
    assert row["agentId"] == "lead"
    assert row["workItemId"] == "w1"
    assert "owner_id" not in row


def test_post_then_list_messages_oldest_first(client, session_factory):
    run_id = _make_run(session_factory)
    client.post(f"/threads/{run_id}/messages", json={"content": "first"})
    client.post(f"/threads/{run_id}/messages", json={"content": "second"})
    body = client.get(f"/threads/{run_id}/messages").json()
    assert body["success"]
    assert [m["content"] for m in body["data"]] == ["first", "second"]
    assert body["data"][0]["role"] == "user"
    assert body["data"][0]["conversationId"] == run_id


def test_post_message_returns_201_and_created(client, session_factory):
    run_id = _make_run(session_factory)
    res = client.post(f"/threads/{run_id}/messages", json={"content": "hi", "agentId": "lead"})
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["content"] == "hi"
    assert data["agentId"] == "lead"
    assert data["role"] == "user"


def test_empty_content_is_rejected(client, session_factory):
    run_id = _make_run(session_factory)
    res = client.post(f"/threads/{run_id}/messages", json={"content": "   "})
    assert res.status_code == 422


def test_foreign_thread_is_404(client, session_factory):
    # a run owned by someone else
    other_run = _make_run(session_factory, owner="someone-else", wid="w9")
    assert client.get(f"/threads/{other_run}/messages").status_code == 404
    assert client.post(f"/threads/{other_run}/messages", json={"content": "x"}).status_code == 404


def test_messages_do_not_touch_the_bus(client, session_factory):
    run_id = _make_run(session_factory)
    client.post(f"/threads/{run_id}/messages", json={"content": "hi"})
    # persist-only: no bus_messages row was written by the chat send
    from sqlalchemy import text
    with session_factory() as s:
        count = s.execute(text("SELECT COUNT(*) FROM bus_messages")).scalar_one()
    assert count == 0
