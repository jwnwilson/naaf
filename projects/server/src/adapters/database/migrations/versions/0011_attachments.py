"""attachments table

Revision ID: 0011_attachments
Revises: 0010_run_pr_url
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_attachments"
down_revision = "0010_run_pr_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("work_item_id", sa.String(length=32), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id", "work_item_id", "filename", name="uq_attachment_name"),
    )
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"])
    op.create_index("ix_attachments_work_item_id", "attachments", ["work_item_id"])
    op.create_index("ix_attachments_owner_wi", "attachments", ["owner_id", "work_item_id"])


def downgrade() -> None:
    op.drop_table("attachments")
