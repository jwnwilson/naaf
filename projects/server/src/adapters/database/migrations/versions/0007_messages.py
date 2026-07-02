"""messages

Revision ID: 0007_messages
Revises: 0006_notifications
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_messages"
down_revision = "0006_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("thread_id", sa.String(32), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_owner_id"), "messages", ["owner_id"], unique=False)
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)
    op.create_index("ix_messages_owner_thread", "messages", ["owner_id", "thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_owner_thread", table_name="messages")
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_owner_id"), table_name="messages")
    op.drop_table("messages")
