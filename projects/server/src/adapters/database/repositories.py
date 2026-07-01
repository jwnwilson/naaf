from domain.project import Project
from domain.runs.events import RunEvent
from domain.runs.run import Run
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem
from sqlalchemy import func, select

from adapters.database.orm import (
    AgentDefinitionRow,
    ProjectRow,
    RunEventRow,
    RunRow,
    TeamRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


class TeamRepository(SqlRepository[Team]):
    orm_model = TeamRow
    dto = Team


class AgentDefinitionRepository(SqlRepository[AgentDefinition]):
    orm_model = AgentDefinitionRow
    dto = AgentDefinition


class RunRepository(SqlRepository[Run]):
    orm_model = RunRow
    dto = Run


class RunEventRepository(SqlRepository[RunEvent]):
    orm_model = RunEventRow
    dto = RunEvent

    def create(self, dto: RunEvent) -> RunEvent:  # type: ignore[override]
        q = select(func.coalesce(func.max(RunEventRow.seq), 0) + 1).where(
            RunEventRow.run_id == dto.run_id
        )
        for key, value in self.required_filters.items():
            q = q.where(getattr(RunEventRow, key) == value)
        next_seq = self.session.execute(q).scalar_one()
        gq = select(func.coalesce(func.max(RunEventRow.global_seq), 0) + 1)  # global, no filters
        next_global = self.session.execute(gq).scalar_one()
        return super().create(dto.model_copy(update={"seq": next_seq, "global_seq": next_global}))
