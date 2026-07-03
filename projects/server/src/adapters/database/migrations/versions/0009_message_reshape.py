"""reshape messages for work-item threads

Revision ID: 0009_message_reshape
Revises: 0008_run_token_usage
Create Date: 2026-07-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_message_reshape"
down_revision = "0008_run_token_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("messages")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("thread_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("author_kind", sa.String(length=8), nullable=False),
        sa.Column("author_role", sa.String(length=32), nullable=True),
        sa.Column("model_alias", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mentions", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_messages_owner_thread", "messages", ["owner_id", "thread_id"])


def downgrade() -> None:
    op.drop_table("messages")
