"""Activity replay and SSE stream endpoint tests."""
from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import EVENT_STATUS, EVENT_TEXT, AgentEvent


def _seed(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:w1", kind=EVENT_STATUS))
        uow.agent_events.create(
            AgentEvent(owner_id="", scope="thread:w1", kind=EVENT_TEXT, payload={"text": "hello"})
        )


def test_activity_replay_returns_events_after_seq(client, session_factory):
    _seed(session_factory)
    resp = client.get("/threads/w1/activity?after=1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["seq"] for e in data] == [2]
    assert data[0]["kind"] == "text_block"
    assert data[0]["payload"] == {"text": "hello"}


def test_activity_replay_empty_when_none(client):
    resp = client.get("/threads/nope/activity?after=0")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
