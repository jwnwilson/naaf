import pytest
from domain.agent.events import (
    EVENT_STATUS,
    AgentEvent,
    stream_scope,
)


def test_stream_scope_builds_thread_key():
    assert stream_scope(thread_id="project:abc") == "thread:project:abc"


def test_stream_scope_builds_run_key():
    assert stream_scope(run_id="deadbeef") == "run:deadbeef"


def test_stream_scope_requires_exactly_one_target():
    with pytest.raises(ValueError):
        stream_scope()
    with pytest.raises(ValueError):
        stream_scope(thread_id="t", run_id="r")


def test_agent_event_defaults_are_immutable_friendly():
    ev = AgentEvent(owner_id="u1", scope="thread:t", kind=EVENT_STATUS)
    assert ev.seq == 0
    assert ev.payload == {}
    updated = ev.model_copy(update={"seq": 3})
    assert updated.seq == 3 and ev.seq == 0  # original unchanged
