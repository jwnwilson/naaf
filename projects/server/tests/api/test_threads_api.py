from adapters.database.orm import BusMessageRow
from adapters.database.uow import SqlUnitOfWork
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


def test_post_message_does_not_touch_the_bus(client, session_factory):
    # Arrange
    wid = _make_item(session_factory)

    # Act — @mention should be stored but must NOT dispatch to the bus (Phase 3)
    res = client.post(f"/threads/{wid}/messages", json={"content": "@backend do it"})
    assert res.status_code == 201

    # Assert — zero rows in bus_messages
    with session_factory() as session:
        count = session.query(BusMessageRow).count()
    assert count == 0
