from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import EVENT_STATUS, EVENT_TEXT, AgentEvent


def _uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})


def test_create_assigns_monotonic_seq_per_scope(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        a = uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
        b = uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_TEXT))
        c = uow.agent_events.create(
            AgentEvent(owner_id="", scope="thread:OTHER", kind=EVENT_STATUS)
        )
        assert (a.seq, b.seq) == (1, 2)
        assert c.seq == 1  # per-scope counter, independent of thread:t


def test_list_after_returns_only_newer_events_in_order(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_TEXT))
        rows = uow.agent_events.list_after("thread:t", after=1)
        assert [r.seq for r in rows] == [2]
        assert rows[0].kind == EVENT_TEXT


def test_owner_scoping_hides_other_owners_events(session_factory):
    with SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"}).transaction() as uow:
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
    with SqlUnitOfWork(session_factory, required_filters={"owner_id": "u2"}).transaction() as uow:
        assert uow.agent_events.list_after("thread:t", after=0) == []
