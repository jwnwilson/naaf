from pydantic import Field

from domain.base import Entity

EVENT_STATUS = "status"
EVENT_TEXT = "text_block"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_FINAL = "final"
EVENT_ERROR = "error"


class AgentEvent(Entity):
    """A coarse-grained, owner-scoped activity event streamed from an agent turn.

    ``scope`` is the stream key (``thread:<id>`` or ``run:<id>``); ``seq`` is a
    monotonic per-scope counter used for SSE replay/resume; ``payload`` carries
    text / tool name+args / result summary / usage / error depending on ``kind``.
    """

    owner_id: str
    scope: str
    seq: int = 0
    kind: str
    payload: dict = Field(default_factory=dict)


def stream_scope(*, thread_id: str | None = None, run_id: str | None = None) -> str:
    if (thread_id is None) == (run_id is None):
        raise ValueError("stream_scope requires exactly one of thread_id or run_id")
    return f"thread:{thread_id}" if thread_id is not None else f"run:{run_id}"
