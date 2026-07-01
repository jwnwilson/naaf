from enum import StrEnum

from pydantic import Field

from domain.base import Entity
from domain.runs.run import Stage


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    LOG = "log"
    STAGE_PASSED = "stage_passed"
    STAGE_FAILED = "stage_failed"
    GATE_REQUESTED = "gate_requested"
    GATE_RESOLVED = "gate_resolved"
    RUN_FINISHED = "run_finished"


class RunEvent(Entity):
    owner_id: str
    run_id: str
    seq: int = 0
    global_seq: int = 0
    stage: Stage | None = None
    role: str | None = None
    type: EventType
    payload: dict = Field(default_factory=dict)
