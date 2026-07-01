"""runs

Revision ID: 0003_runs
Revises: 0002_contract_fields
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_runs"
down_revision = "0002_contract_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("work_item_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("autonomy_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_stage", sa.String(length=16), nullable=True),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("pending_gate", sa.JSON(), nullable=True),
        sa.Column("resolved_gates", sa.JSON(), nullable=False),
        sa.Column("verify_attempts", sa.Integer(), nullable=False),
        sa.Column("max_verify_loops", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_owner_id"), "runs", ["owner_id"], unique=False)
    op.create_index(op.f("ix_runs_work_item_id"), "runs", ["work_item_id"], unique=False)
    op.create_index(op.f("ix_runs_project_id"), "runs", ["project_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq"),
    )
    op.create_index(op.f("ix_run_events_owner_id"), "run_events", ["owner_id"], unique=False)
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"], unique=False)

    op.create_table(
        "bus_messages",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bus_messages_owner_id"), "bus_messages", ["owner_id"], unique=False)
    op.create_index(op.f("ix_bus_messages_run_id"), "bus_messages", ["run_id"], unique=False)
    op.create_index(op.f("ix_bus_messages_recipient"), "bus_messages", ["recipient"], unique=False)
    op.create_index(op.f("ix_bus_messages_status"), "bus_messages", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bus_messages_status"), table_name="bus_messages")
    op.drop_index(op.f("ix_bus_messages_recipient"), table_name="bus_messages")
    op.drop_index(op.f("ix_bus_messages_run_id"), table_name="bus_messages")
    op.drop_index(op.f("ix_bus_messages_owner_id"), table_name="bus_messages")
    op.drop_table("bus_messages")

    op.drop_index(op.f("ix_run_events_run_id"), table_name="run_events")
    op.drop_index(op.f("ix_run_events_owner_id"), table_name="run_events")
    op.drop_table("run_events")

    op.drop_index(op.f("ix_runs_project_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_work_item_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_owner_id"), table_name="runs")
    op.drop_table("runs")
