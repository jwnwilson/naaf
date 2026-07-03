"""run pr_url

Revision ID: 0010_run_pr_url
Revises: 0009_message_reshape
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_run_pr_url"
down_revision = "0009_message_reshape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("pr_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "pr_url")
