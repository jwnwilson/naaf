from datetime import datetime

from domain.base import new_id, utcnow
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class _Timestamped:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class ProjectRow(_Timestamped, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    repo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(32), default="gated_all", nullable=False)


class WorkItemRow(_Timestamped, Base):
    __tablename__ = "work_items"
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True, nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(String, default="", nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="todo", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)


class AttachmentRow(_Timestamped, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_owner_wi", "owner_id", "work_item_id"),
        UniqueConstraint("owner_id", "work_item_id", "filename", name="uq_attachment_name"),
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)


class TeamRow(_Timestamped, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class AgentDefinitionRow(_Timestamped, Base):
    __tablename__ = "agent_definitions"
    team_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("teams.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    persona_prompt: Mapped[str] = mapped_column(String, default="", nullable=False)
    model_alias: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    runtime_adapter: Mapped[str] = mapped_column(String(64), default="claude_code", nullable=False)
    memory_scope: Mapped[str] = mapped_column(String(32), default="project", nullable=False)
    capability_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_limit: Mapped[int] = mapped_column(Integer, default=200000, nullable=False)


class RunRow(_Timestamped, Base):
    __tablename__ = "runs"
    work_item_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    autonomy_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pending_gate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_gates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    verify_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_verify_loops: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RunEventRow(_Timestamped, Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq"),)
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    global_seq: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


# system table (not owner-scoped): per-subscriber fan-out cursor
class SubscriberCursorRow(Base):
    __tablename__ = "subscriber_cursors"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_global_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class NotificationRow(_Timestamped, Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("source_seq"),)
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    work_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(String, default="", nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_seq: Mapped[int] = mapped_column(Integer, nullable=False)


# persisted via BusMessageRepository (adapters/database); the SqlMessageBus
# adapter delegates to uow.bus_messages
class BusMessageRow(_Timestamped, Base):
    __tablename__ = "bus_messages"
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    recipient: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MessageRow(_Timestamped, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_owner_thread", "owner_id", "thread_id"),)
    thread_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    author_kind: Mapped[str] = mapped_column(String(8), default="user", nullable=False)
    author_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SecretRow(_Timestamped, Base):
    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_secret_owner_name"),)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    hint: Mapped[str] = mapped_column(String(8), default="", nullable=False)
