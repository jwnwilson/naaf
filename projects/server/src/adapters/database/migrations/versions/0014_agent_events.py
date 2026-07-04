"""agent_events table for streamed agent activity

Revision ID: 0014_agent_events
Revises: 0013_widen_message_thread_id
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_agent_events"
down_revision = "0013_widen_message_thread_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "seq"),
    )
    op.create_index(op.f("ix_agent_events_owner_id"), "agent_events", ["owner_id"], unique=False)
    op.create_index(op.f("ix_agent_events_scope"), "agent_events", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_events_scope"), table_name="agent_events")
    op.drop_index(op.f("ix_agent_events_owner_id"), table_name="agent_events")
    op.drop_table("agent_events")
