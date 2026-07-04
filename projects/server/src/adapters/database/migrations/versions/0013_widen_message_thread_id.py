"""widen messages.thread_id for project threads

Project threads are keyed "project:<32-hex>" (40 chars), which overflowed the
32-char column and 500'd on Postgres (SQLite doesn't enforce varchar length).

Revision ID: 0013_widen_message_thread_id
Revises: 0012_attachments
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_widen_message_thread_id"
down_revision = "0012_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch mode: SQLite (tests) can't ALTER COLUMN TYPE in place; Postgres alters directly.
    with op.batch_alter_table("messages") as batch:
        batch.alter_column(
            "thread_id",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.alter_column(
            "thread_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
