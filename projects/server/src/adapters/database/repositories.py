from domain.base import utcnow
from domain.messaging.message import Message
from domain.messaging.subscriber import CursorState
from domain.notifications.notification import Notification
from domain.project import Project
from domain.runs.events import RunEvent
from domain.runs.messages import AgentMessage, MessageStatus, MessageType
from domain.runs.run import Run
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.database.orm import (
    AgentDefinitionRow,
    BusMessageRow,
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


class BusMessageRepository:
    """Cross-owner work-queue repository for bus messages.

    NOT owner-scoped: the worker claims pending messages across ALL owners, so
    claim_next must not filter by owner. `required_filters` is accepted only so the
    UnitOfWork._repo() helper can build it uniformly — it is deliberately ignored.
    (Same shape as SubscriberCursorRepository.)
    """

    def __init__(self, session: Session, required_filters: dict | None = None) -> None:
        self.session = session

    def publish(self, msg: AgentMessage) -> None:
        self.session.add(BusMessageRow(
            id=msg.id, owner_id=msg.owner_id, run_id=msg.run_id, recipient=msg.recipient,
            role=msg.role, type=msg.type.value, payload=msg.payload, status=msg.status.value,
        ))
        self.session.flush()

    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        busy = select(BusMessageRow.recipient).where(BusMessageRow.status == "claimed")
        q = select(BusMessageRow).where(
            BusMessageRow.status == "pending", BusMessageRow.recipient.notin_(busy)
        )
        if roles:
            q = q.where(BusMessageRow.role.in_(roles))
        q = q.order_by(BusMessageRow.created_at).limit(1)
        if self.session.get_bind().dialect.name != "sqlite":
            q = q.with_for_update(skip_locked=True)
        row = self.session.execute(q).scalar_one_or_none()
        if row is None:
            return None
        row.status = "claimed"
        row.claimed_at = utcnow()
        self.session.flush()
        return self._to_msg(row)

    def ack(self, msg: AgentMessage) -> None:
        row = self.session.get(BusMessageRow, msg.id)
        if row is None:
            raise RuntimeError(f"ack: message {msg.id} not found")
        row.status = MessageStatus.DONE.value
        self.session.flush()

    def _to_msg(self, row: BusMessageRow) -> AgentMessage:
        return AgentMessage(id=row.id, owner_id=row.owner_id, run_id=row.run_id,
                            recipient=row.recipient, role=row.role, type=MessageType(row.type),
                            payload=row.payload, status=MessageStatus(row.status),
                            created_at=row.created_at, claimed_at=row.claimed_at)
