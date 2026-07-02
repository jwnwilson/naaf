from domain.base import utcnow
from domain.runs.messages import AgentMessage, MessageStatus, MessageType
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.database.orm import BusMessageRow


class SqlMessageBus:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish(self, msg: AgentMessage) -> None:
        self.session.add(BusMessageRow(
            id=msg.id, owner_id=msg.owner_id, run_id=msg.run_id, recipient=msg.recipient,
            role=msg.role, type=msg.type.value, payload=msg.payload, status=msg.status.value,
        ))
        self.session.flush()

    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        """Claim the next pending message for processing.

        FOR UPDATE SKIP LOCKED prevents two workers claiming the SAME row. The
        one-in-flight-per-recipient invariant additionally relies on roles being
        partitioned across workers (one role → one worker); a Postgres advisory
        lock per recipient is the follow-up for multiple workers sharing a role.
        """
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
