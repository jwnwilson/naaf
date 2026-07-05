"""run cost column

Revision ID: 0015_run_cost
Revises: 0014_agent_events
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_run_cost"
down_revision = "0014_agent_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("cost", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("runs", "cost")
