import json

import pytest
from adapters.database.orm import Base
from interactors.api.app import create_app
from interactors.api.settings import Settings
from naaf_db.engine import (
    build_async_engine,
    build_async_session_factory,
    build_engine,
    build_session_factory,
)
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

SHARED = "file:memdb_runev?mode=memory&cache=shared&uri=true"


@pytest.fixture
def app_client():
    sync_engine = build_engine(
        f"sqlite:///{SHARED}", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(sync_engine)
    async_engine = build_async_engine(
        f"sqlite+aiosqlite:///{SHARED}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    app = create_app(
        settings=Settings(),
        session_factory=build_session_factory(sync_engine),
        async_session_factory=build_async_session_factory(async_engine),
    )
    client = TestClient(app)
    # exposed so the test can prove no sync queries run during the stream
    client.sync_engine = sync_engine
    return client


def test_run_events_stream_yields_events_then_closes(app_client):
    # Seed via the sync UoW (the write path), through the API's session_factory
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.events import EventType, RunEvent
    from domain.runs.run import Run

    sf = app_client.app.state.session_factory
    uow = SqlUnitOfWork(sf, required_filters={"owner_id": "dev-user"})
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

    # The event-loop-freeze bug is sync (blocking) DB I/O running inside the async
    # request handler. Count sync-engine queries that happen for the whole request —
    # this is the behavioral signal that actually distinguishes the sync vs async
    # implementation (both read the same seeded rows either way, so asserting only on
    # the yielded types would pass even against the unconverted sync `gen()`).
    #
    # NOTE: TestClient's ASGI transport runs the endpoint *and* fully drains the SSE
    # generator before `client.stream()` returns control (it does not interleave with
    # the test reading the body), so the listener must be attached *before* the request
    # is sent, not after headers are "received". The route intentionally keeps ONE sync
    # query off the hot loop (the upfront owner-check `uow.runs.read`, run once before
    # streaming starts) — measure that baseline independently and assert the full
    # request adds nothing beyond it, i.e. the hot loop itself issues zero sync queries.
    from adapters.database.uow import SqlUnitOfWork as _SyncUoW

    def _count_queries(fn):
        count = 0

        def _cb(*_args, **_kwargs):
            nonlocal count
            count += 1

        event.listen(app_client.sync_engine, "before_cursor_execute", _cb)
        try:
            result = fn()
        finally:
            event.remove(app_client.sync_engine, "before_cursor_execute", _cb)
        return count, result

    baseline, _ = _count_queries(
        lambda: _SyncUoW(sf, required_filters={"owner_id": "dev-user"}).runs.read(run.id)
    )

    def _do_stream():
        with app_client.stream("GET", f"/runs/{run.id}/events/stream") as r:
            return "".join(chunk for chunk in r.iter_text())

    total_queries, body = _count_queries(_do_stream)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    types = [json.loads(line[6:])["type"] for line in data_lines]
    assert types == ["log", "run_finished"]
    # the hot streaming loop must not run blocking sync queries on the event loop —
    # the only sync DB work in the whole request should be the upfront owner-check.
    assert total_queries == baseline
