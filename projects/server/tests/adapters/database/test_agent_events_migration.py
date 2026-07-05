from adapters.database.orm import AgentEventRow
from sqlalchemy import inspect


def test_agent_event_row_table_shape():
    cols = {c.name for c in AgentEventRow.__table__.columns}
    assert {"id", "owner_id", "scope", "seq", "kind", "payload", "created_at", "updated_at"} <= cols


def test_agent_events_table_created_by_metadata(session_factory):
    # session_factory fixture runs Base.metadata.create_all — table must exist.
    insp = inspect(session_factory().get_bind())
    assert "agent_events" in insp.get_table_names()
