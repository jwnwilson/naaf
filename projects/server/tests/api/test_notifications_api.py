def test_list_and_mark_read(client, session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.notifications.notification import Notification, NotificationType
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        n = uow.notifications.create(Notification(owner_id="", run_id="r1",
            type=NotificationType.GATE_PENDING, title="Action needed", source_seq=1))
    listed = client.get("/notifications").json()
    assert listed["success"] and listed["data"][0]["runId"] == "r1"
    assert listed["data"][0]["read"] is False and "owner_id" not in listed["data"][0]
    after = client.post(f"/notifications/{n.id}/read").json()["data"]
    assert after["read"] is True
    assert client.get("/notifications?read=false").json()["data"] == []
