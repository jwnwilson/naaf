"""secrets

Revision ID: 0011_secrets
Revises: 0010_run_pr_url
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_secrets"
down_revision = "0010_run_pr_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("hint", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_secret_owner_name"),
    )
    op.create_index("ix_secrets_owner_id", "secrets", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_secrets_owner_id", table_name="secrets")
    op.drop_table("secrets")
