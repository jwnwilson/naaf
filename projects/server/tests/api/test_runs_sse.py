"""SSE run-event stream tests."""
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Run


def test_sse_streams_existing_events_and_closes_on_finish(client, session_factory):
    """Stream yields seeded events and closes after run_finished is emitted."""
    # Arrange: seed a run + two events directly via the shared UoW
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id="w", project_id="p", autonomy_level="full_auto")
        )
        uow.run_events.create(
            RunEvent(owner_id="", run_id=run.id, type=EventType.LOG, payload={"message": "hi"})
        )
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id=run.id,
                type=EventType.RUN_FINISHED,
                payload={"status": "succeeded"},
            )
        )

    # Act: stream from the SSE endpoint
    with client.stream("GET", f"/runs/{run.id}/events/stream") as resp:
        assert resp.status_code == 200
        body = "".join(chunk for chunk in resp.iter_text())

    # Assert: both events appear in the body
    assert "hi" in body
    assert "run_finished" in body


def test_sse_respects_after_cursor(client, session_factory):
    """after=<seq> skips events with seq <= cursor."""
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id="w", project_id="p", autonomy_level="full_auto")
        )
        ev_log = uow.run_events.create(
            RunEvent(owner_id="", run_id=run.id, type=EventType.LOG, payload={"message": "skip-me"})
        )
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id=run.id,
                type=EventType.RUN_FINISHED,
                payload={"status": "succeeded"},
            )
        )

    with client.stream(
        "GET", f"/runs/{run.id}/events/stream", params={"after": ev_log.seq}
    ) as resp:
        assert resp.status_code == 200
        body = "".join(chunk for chunk in resp.iter_text())

    assert "skip-me" not in body
    assert "run_finished" in body
