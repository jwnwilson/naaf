"""event global seq

Revision ID: 0004_event_global_seq
Revises: 0003_runs
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_event_global_seq"
down_revision = "0003_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run_events", sa.Column("global_seq", sa.Integer(), nullable=True))
    op.create_index("ix_run_events_global_seq", "run_events", ["global_seq"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_run_events_global_seq", table_name="run_events")
    op.drop_column("run_events", "global_seq")
