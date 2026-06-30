"""contract fields

Revision ID: 0002_contract_fields
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_contract_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_items",
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
    )
    op.add_column(
        "agent_definitions",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "agent_definitions",
        sa.Column("token_limit", sa.Integer(), nullable=False, server_default="200000"),
    )
    # remap legacy status values to the UI-canonical 5-set
    op.execute("UPDATE work_items SET status = 'todo' WHERE status = 'to_do'")
    op.execute("UPDATE work_items SET status = 'done' WHERE status = 'approved'")
    op.execute("UPDATE work_items SET status = 'todo' WHERE status IN ('blocked', 'failed')")


def downgrade() -> None:
    op.drop_column("agent_definitions", "token_limit")
    op.drop_column("agent_definitions", "enabled")
    op.drop_column("work_items", "priority")
