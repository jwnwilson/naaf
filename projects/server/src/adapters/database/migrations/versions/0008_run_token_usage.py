"""run token_usage

Revision ID: 0008_run_token_usage
Revises: 0007_messages
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_run_token_usage"
down_revision = "0007_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("runs", "token_usage")
