from datetime import datetime

from domain.base import new_id, utcnow
from sqlalchemy import JSON, DateTime, ForeignKey, String
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
    status: Mapped[str] = mapped_column(String(16), default="to_do", nullable=False)


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
