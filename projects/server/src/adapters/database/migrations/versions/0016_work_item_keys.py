"""human-readable work item keys: projects.key + work_items.seq

Revision ID: 0016_work_item_keys
Revises: 0015_run_cost
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0016_work_item_keys"
down_revision = "0015_run_cost"
branch_labels = None
depends_on = None


def _derive(name: str, taken: set[str]) -> str:
    # Intentional verbatim copy of domain.project.derive_project_key — migrations
    # must be self-contained and frozen against future domain-logic changes.
    base = re.sub(r"[^A-Za-z0-9]", "", name or "").upper()[:4] or "PROJ"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def upgrade() -> None:
    op.add_column("projects", sa.Column("key", sa.String(length=8), nullable=True))
    op.add_column("work_items", sa.Column("seq", sa.Integer(), nullable=True))

    conn = op.get_bind()
    projects = conn.execute(
        sa.text("SELECT id, owner_id, name FROM projects ORDER BY created_at, id")
    ).fetchall()
    taken_by_owner: dict[str, set[str]] = {}
    for pid, owner_id, name in projects:
        taken = taken_by_owner.setdefault(owner_id, set())
        key = _derive(name, taken)
        taken.add(key)
        conn.execute(
            sa.text("UPDATE projects SET key = :k WHERE id = :id"),
            {"k": key, "id": pid},
        )

    for pid, _owner_id, _name in projects:
        items = conn.execute(
            sa.text(
                "SELECT id FROM work_items WHERE project_id = :pid "
                "ORDER BY created_at, id"
            ),
            {"pid": pid},
        ).fetchall()
        for i, (wid,) in enumerate(items, start=1):
            conn.execute(
                sa.text("UPDATE work_items SET seq = :s WHERE id = :id"),
                {"s": i, "id": wid},
            )

    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("work_items", recreate=recreate) as batch:
        batch.create_unique_constraint("uq_work_item_project_seq", ["project_id", "seq"])

    op.create_index("uq_project_owner_key", "projects", ["owner_id", "key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_project_owner_key", table_name="projects")

    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("work_items", recreate=recreate) as batch:
        batch.drop_constraint("uq_work_item_project_seq", type_="unique")
    op.drop_column("work_items", "seq")
    op.drop_column("projects", "key")
