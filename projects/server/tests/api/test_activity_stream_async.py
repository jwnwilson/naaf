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

SHARED = "file:memdb_activity?mode=memory&cache=shared&uri=true"


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


def test_activity_stream_yields_events_then_closes(app_client):
    # Seed via the sync UoW (the write path), through the API's session_factory
    from adapters.database.uow import SqlUnitOfWork
    from domain.agent.events import AgentEvent, stream_scope

    scope_thread = "t-async-1"
    scope = stream_scope(thread_id=scope_thread)
    sf = app_client.app.state.session_factory
    uow = SqlUnitOfWork(sf, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.agent_events.create(AgentEvent(owner_id="", scope=scope, kind="status", payload={}))
        uow.agent_events.create(AgentEvent(owner_id="", scope=scope, kind="final", payload={}))

    # The event-loop-freeze bug is sync (blocking) DB I/O running inside the async
    # request handler. Count sync-engine queries that happen *during* the stream call —
    # this is the behavioral signal that actually distinguishes the sync vs async
    # implementation (both read the same seeded rows either way, so asserting only on
    # the yielded kinds would pass even against the unconverted sync `_stream`).
    sync_query_count = 0

    def _count_sync_query(*_args, **_kwargs):
        nonlocal sync_query_count
        sync_query_count += 1

    event.listen(app_client.sync_engine, "before_cursor_execute", _count_sync_query)
    try:
        with app_client.stream("GET", f"/threads/{scope_thread}/activity/stream?after=0") as r:
            body = "".join(chunk for chunk in r.iter_text())
    finally:
        event.remove(app_client.sync_engine, "before_cursor_execute", _count_sync_query)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    kinds = [json.loads(line[6:])["kind"] for line in data_lines]
    assert kinds == ["status", "final"]
    # the stream must not run blocking sync queries on the event loop
    assert sync_query_count == 0
