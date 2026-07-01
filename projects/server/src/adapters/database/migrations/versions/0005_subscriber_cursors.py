"""subscriber cursors

Revision ID: 0005_subscriber_cursors
Revises: 0004_event_global_seq
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_subscriber_cursors"
down_revision = "0004_event_global_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriber_cursors",
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("last_global_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("subscriber_cursors")
