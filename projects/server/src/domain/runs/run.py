from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import Entity


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_GATE = "awaiting_gate"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    PLAN = "plan"
    PROVISION = "provision"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    PR = "pr"
    LEARN = "learn"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    GATED = "gated"


class GateKind(StrEnum):
    PLAN = "plan"
    MERGE = "merge"


class StageState(BaseModel):
    stage: Stage
    status: StageStatus = StageStatus.PENDING
    role: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Gate(BaseModel):
    kind: GateKind
    stage: Stage


class Run(Entity):
    owner_id: str
    work_item_id: str
    project_id: str
    autonomy_level: str
    status: RunStatus = RunStatus.QUEUED
    current_stage: Stage | None = None
    stages: list[StageState] = Field(default_factory=list)
    pending_gate: Gate | None = None
    resolved_gates: list[GateKind] = Field(default_factory=list)
    verify_attempts: int = 0
    max_verify_loops: int = 3
    token_usage: int = 0
    cost: float = 0.0
    pr_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
