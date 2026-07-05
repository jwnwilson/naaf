"""project description column

Revision ID: 0016_project_description
Revises: 0015_run_cost
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_project_description"
down_revision = "0015_run_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("description", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("projects", "description")
