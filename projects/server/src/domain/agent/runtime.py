from typing import Protocol

from pydantic import BaseModel, Field

from domain.runs.run import Stage


class AgentEvent(BaseModel):
    type: str = "log"
    message: str


class StageResult(BaseModel):
    passed: bool
    summary: str = ""
    tokens: int = 0


class StageOutcome(BaseModel):
    events: list[AgentEvent] = Field(default_factory=list)
    result: StageResult


class AgentRuntime(Protocol):
    def run_stage(self, role: str, stage: Stage, ctx: dict) -> StageOutcome: ...
