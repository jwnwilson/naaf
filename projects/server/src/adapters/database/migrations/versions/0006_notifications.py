"""notifications

Revision ID: 0006_notifications
Revises: 0005_subscriber_cursors
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_notifications"
down_revision = "0005_subscriber_cursors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("work_item_id", sa.String(32), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.String(), nullable=False, server_default=""),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("source_seq", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_seq"),
    )
    op.create_index(op.f("ix_notifications_owner_id"), "notifications", ["owner_id"], unique=False)
    op.create_index(op.f("ix_notifications_run_id"), "notifications", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_run_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_owner_id"), table_name="notifications")
    op.drop_table("notifications")
