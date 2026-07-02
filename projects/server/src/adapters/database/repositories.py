from domain.base import utcnow
from domain.messaging.message import Message
from domain.messaging.subscriber import CursorState
from domain.notifications.notification import Notification
from domain.project import Project
from domain.runs.events import RunEvent
from domain.runs.run import Run
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.database.orm import (
    AgentDefinitionRow,
    MessageRow,
    NotificationRow,
    ProjectRow,
    RunEventRow,
    RunRow,
    SubscriberCursorRow,
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


class NotificationRepository(SqlRepository[Notification]):
    orm_model = NotificationRow
    dto = Notification


class MessageRepository(SqlRepository[Message]):
    orm_model = MessageRow
    dto = Message


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

    def list_after(self, after: int, limit: int = 100) -> list[RunEvent]:
        rows = self.session.execute(
            select(RunEventRow)
            .where(RunEventRow.global_seq.isnot(None), RunEventRow.global_seq > after)
            .order_by(RunEventRow.global_seq)
            .limit(limit)
        ).scalars().all()
        return [self._to_dto(r) for r in rows]


class SubscriberCursorRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, name: str) -> CursorState:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            return CursorState()
        return CursorState(last_global_seq=row.last_global_seq, retries=row.retries)

    def save(self, name: str, state: CursorState) -> None:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            row = SubscriberCursorRow(name=name)
            self.session.add(row)
        row.last_global_seq = state.last_global_seq
        row.retries = state.retries
        row.updated_at = utcnow()
        self.session.flush()
