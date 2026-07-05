# Human-readable Work Item IDs + Parent Lineage Names — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every work item a short, stable, human-readable key (`NAAF-42`) shown across board / list / detail, and show each item's parent epic name and feature name on the board and list.

**Architecture:** Two new persisted fields — `Project.key` (auto-derived once from the name, immutable) and `WorkItem.seq` (per-project running counter, assigned at create via `max(seq)+1`, mirroring the existing `RunEventRepository`/`AgentEventRepository` sequence pattern). The composed key string (`{project.key}-{seq}`) is **computed** in the API, never stored. The API's existing `_resolve_lineage` already reads the parent chain — it's extended to also return the epic/feature titles. The frontend is display-only.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Alembic, Pydantic v2, pytest. React 18 + Vite + Tailwind, TanStack Query, openapi-typescript, Vitest. `uv` for Python, `pnpm` for UI.

## Global Constraints

- Backend runs from `projects/server`; UI from `projects/ui`.
- Tests build the schema with `Base.metadata.create_all` (`tests/conftest.py`), so ORM column DDL + unique constraints take effect in all unit/API tests. The Alembic migration is exercised only by `tests/adapters/test_migrations.py` and real Postgres.
- Immutability: Pydantic models update via `model_copy(update={...})`, never mutated.
- API envelope: every response is `{success, data, error}`; owned rows carry `owner_id`; the UnitOfWork applies it as a required filter.
- IDs are UUID hex (32 chars). The new `key` is a separate human-facing string; it does **not** replace `id` in routing or persistence.
- Commit format: `<type>: <description>`. Commit after each task. 80% coverage gate; `make coverage` and `make lint` (backend) / `pnpm lint` (UI) must stay green.
- UI OpenAPI types are generated from the hand-maintained `projects/ui/openapi/naaf-api.yaml` via `pnpm gen:api` (output `src/lib/api/schema.d.ts`, imported as `../../lib/api/schema`).

## Deferred (out of scope, do not build)

- Jump-to / search-by-key, key-based routing.
- Editable project-key UI.
- Per-kind numbering.
- **Inbox thread header key** — the thread payload (`ConversationPane`/`TaskBanner`) does not carry the work item, so showing the key there needs threads-route plumbing. Left for a follow-up; note this when finishing.

---

## Task 1: `derive_project_key` pure helper

Derive a project key from a name, unique against already-taken keys.

**Files:**
- Modify: `projects/server/src/domain/project.py`
- Test: `projects/server/tests/domain/test_project_key.py` (create)

**Interfaces:**
- Produces: `derive_project_key(name: str, taken: set[str] = frozenset()) -> str`

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/domain/test_project_key.py`:

```python
from domain.project import derive_project_key


def test_derives_first_four_alnum_uppercased():
    assert derive_project_key("naaf") == "NAAF"
    assert derive_project_key("Acme Web App") == "ACME"
    assert derive_project_key("my-tool") == "MYTO"


def test_strips_non_alphanumerics_before_truncating():
    assert derive_project_key("A.B-C_D_E") == "ABCD"


def test_falls_back_to_proj_when_no_alphanumerics():
    assert derive_project_key("!!!") == "PROJ"
    assert derive_project_key("") == "PROJ"


def test_suffixes_on_collision():
    assert derive_project_key("Acme", {"ACME"}) == "ACME2"
    assert derive_project_key("Acme", {"ACME", "ACME2"}) == "ACME3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/test_project_key.py -v`
Expected: FAIL — `ImportError: cannot import name 'derive_project_key'`.

- [ ] **Step 3: Write minimal implementation**

Add to `projects/server/src/domain/project.py` (top-level, after imports):

```python
import re


def derive_project_key(name: str, taken: set[str] = frozenset()) -> str:
    """A short uppercase key from the project name, unique against `taken`."""
    base = re.sub(r"[^A-Za-z0-9]", "", name or "").upper()[:4] or "PROJ"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"
```

Also add the field to the `Project` model:

```python
class Project(Entity):
    owner_id: str
    name: str
    key: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/test_project_key.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/project.py projects/server/tests/domain/test_project_key.py
git commit -m "feat: derive_project_key helper + Project.key field"
```

---

## Task 2: Persist `key` and `seq` (ORM + repositories)

Add `projects.key` and `work_items.seq` columns, a `(project_id, seq)` unique constraint, and the create-time assignment in both repositories. Because tests use `create_all`, this task is fully testable via repository tests.

**Files:**
- Modify: `projects/server/src/domain/work_item.py` (add `seq`)
- Modify: `projects/server/src/adapters/database/orm.py` (columns + constraint)
- Modify: `projects/server/src/adapters/database/repositories.py` (create overrides)
- Test: `projects/server/tests/adapters/test_repository.py` (add tests)

**Interfaces:**
- Consumes: `derive_project_key` (Task 1).
- Produces: `WorkItem.seq: int | None`; `Project.key` populated by `ProjectRepository.create`; monotonic per-project `seq` by `WorkItemRepository.create`.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/adapters/test_repository.py` (append; reuse the file's existing `session_factory` fixture / imports — check the top of the file for how repositories/UoW are constructed and follow that exact pattern):

```python
def test_project_create_derives_unique_key(session_factory):
    from domain.project import Project
    from adapters.database.uow import SqlUnitOfWork

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        a = uow.projects.create(Project(owner_id="u1", name="Acme"))
        b = uow.projects.create(Project(owner_id="u1", name="Acme"))
    assert a.key == "ACME"
    assert b.key == "ACME2"


def test_work_item_seq_is_per_project_monotonic(session_factory):
    from domain.project import Project
    from domain.work_item import WorkItem, WorkItemKind
    from adapters.database.uow import SqlUnitOfWork

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p1 = uow.projects.create(Project(owner_id="u1", name="One"))
        p2 = uow.projects.create(Project(owner_id="u1", name="Two"))
        i1 = uow.work_items.create(
            WorkItem(owner_id="u1", project_id=p1.id, kind=WorkItemKind.EPIC, title="a")
        )
        i2 = uow.work_items.create(
            WorkItem(owner_id="u1", project_id=p1.id, kind=WorkItemKind.TASK, title="b")
        )
        j1 = uow.work_items.create(
            WorkItem(owner_id="u1", project_id=p2.id, kind=WorkItemKind.EPIC, title="c")
        )
    assert (i1.seq, i2.seq) == (1, 2)
    assert j1.seq == 1  # numbering restarts per project
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/test_repository.py -k "derives_unique_key or per_project_monotonic" -v`
Expected: FAIL — `AttributeError`/`TypeError` (no `key`/`seq`, no override behavior).

- [ ] **Step 3: Write minimal implementation**

In `projects/server/src/domain/work_item.py`, add `seq` to `WorkItem`:

```python
class WorkItem(Entity):
    owner_id: str
    project_id: str
    parent_id: str | None = None
    kind: WorkItemKind
    title: str
    body: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.TODO
    priority: Priority = Priority.MEDIUM
    seq: int | None = None
```

In `projects/server/src/adapters/database/orm.py`, add `key` to `ProjectRow`:

```python
class ProjectRow(_Timestamped, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str | None] = mapped_column(String(8), nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    repo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(32), default="gated_all", nullable=False)
```

And add `seq` + a unique constraint to `WorkItemRow`:

```python
class WorkItemRow(_Timestamped, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("project_id", "seq", name="uq_work_item_project_seq"),
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True, nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(String, default="", nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="todo", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

(`UniqueConstraint` and `Integer` are already imported in `orm.py`.)

In `projects/server/src/adapters/database/repositories.py`, replace the two empty repository bodies. Add the import for the key helper at the top with the other domain imports:

```python
from domain.project import Project, derive_project_key
```

Then:

```python
class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project

    def create(self, dto: Project) -> Project:  # type: ignore[override]
        if not dto.key:
            q = select(ProjectRow.key).where(ProjectRow.key.isnot(None))
            for key, value in self.required_filters.items():
                q = q.where(getattr(ProjectRow, key) == value)
            taken = {row[0] for row in self.session.execute(q).all()}
            dto = dto.model_copy(update={"key": derive_project_key(dto.name, taken)})
        return super().create(dto)


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem

    def create(self, dto: WorkItem) -> WorkItem:  # type: ignore[override]
        q = select(func.coalesce(func.max(WorkItemRow.seq), 0) + 1).where(
            WorkItemRow.project_id == dto.project_id
        )
        for key, value in self.required_filters.items():
            q = q.where(getattr(WorkItemRow, key) == value)
        next_seq = self.session.execute(q).scalar_one()
        return super().create(dto.model_copy(update={"seq": next_seq}))
```

(`select` and `func` are already imported in `repositories.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/test_repository.py -k "derives_unique_key or per_project_monotonic" -v`
Expected: PASS (2 tests).

Then run the whole adapters suite to catch fallout:
Run: `cd projects/server && uv run pytest tests/adapters -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/work_item.py projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/repositories.py projects/server/tests/adapters/test_repository.py
git commit -m "feat: persist Project.key + per-project WorkItem.seq"
```

---

## Task 3: Alembic migration `0015` + backfill test

Add the columns + unique constraint to existing databases and backfill keys/seqs for pre-existing rows.

**Files:**
- Create: `projects/server/src/adapters/database/migrations/versions/0015_work_item_keys.py`
- Test: `projects/server/tests/adapters/test_migrations.py` (add a test)

**Interfaces:**
- Consumes: schema at revision `0014_agent_events`.
- Produces: `projects.key` + `work_items.seq` columns and `uq_work_item_project_seq` on upgraded DBs.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/adapters/test_migrations.py`:

```python
def test_migration_backfills_work_item_keys_and_seq(tmp_path):
    import os
    import sqlite3
    import subprocess
    from pathlib import Path

    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "0014_agent_events"],
        cwd=server, env=env, check=True,
    )
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projects (id, owner_id, name, autonomy_level, created_at, updated_at) "
        "VALUES ('p1','u1','Demo Project','gated_all','2026-01-01','2026-01-01')"
    )
    con.execute(
        "INSERT INTO work_items (id, owner_id, project_id, kind, title, body, "
        "acceptance_criteria, status, priority, created_at, updated_at) VALUES "
        "('w1','u1','p1','epic','A','','[]','todo','medium','2026-01-01','2026-01-01')"
    )
    con.execute(
        "INSERT INTO work_items (id, owner_id, project_id, kind, title, body, "
        "acceptance_criteria, status, priority, created_at, updated_at) VALUES "
        "('w2','u1','p1','task','B','','[]','todo','medium','2026-01-02','2026-01-02')"
    )
    con.commit()
    con.close()

    r = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(db)
    key = con.execute("SELECT key FROM projects WHERE id='p1'").fetchone()[0]
    seqs = dict(con.execute("SELECT id, seq FROM work_items WHERE project_id='p1'").fetchall())
    con.close()
    assert key == "DEMO"
    assert seqs == {"w1": 1, "w2": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/test_migrations.py -k backfills_work_item -v`
Expected: FAIL — `alembic upgrade head` errors (no `0015` revision / `key` column absent).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/adapters/database/migrations/versions/0015_work_item_keys.py`:

```python
"""human-readable work item keys: projects.key + work_items.seq

Revision ID: 0015_work_item_keys
Revises: 0014_agent_events
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0015_work_item_keys"
down_revision = "0014_agent_events"
branch_labels = None
depends_on = None


def _derive(name: str, taken: set[str]) -> str:
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

    with op.batch_alter_table("work_items") as batch:
        batch.create_unique_constraint("uq_work_item_project_seq", ["project_id", "seq"])


def downgrade() -> None:
    with op.batch_alter_table("work_items") as batch:
        batch.drop_constraint("uq_work_item_project_seq", type_="unique")
    op.drop_column("work_items", "seq")
    op.drop_column("projects", "key")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/test_migrations.py -v`
Expected: PASS (all migration tests, including the new one and the pre-existing `test_alembic_upgrade_head_on_sqlite`).

> If the `batch_alter_table` step errors on SQLite because of the self-referential `work_items.parent_id` FK, add `recreate="always"` to `op.batch_alter_table("work_items", recreate="always")` and re-run. Do not remove the constraint — it is the `seq` uniqueness backstop.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/migrations/versions/0015_work_item_keys.py projects/server/tests/adapters/test_migrations.py
git commit -m "feat: migration 0015 — backfill project keys + work item seq"
```

---

## Task 4: API — expose `key`, `epicName`, `featureName`

Extend `_resolve_lineage` to return parent titles, add the three fields to `WorkItemOut`, and compose the key from the owning project.

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py` (`WorkItemOut`)
- Modify: `projects/server/src/interactors/api/routes/work_items.py`
- Test: `projects/server/tests/api/test_work_items_api.py` (add tests)

**Interfaces:**
- Consumes: `WorkItem.seq` (Task 2), `Project.key` (Task 2).
- Produces: `WorkItemOut.key: str`, `.epicName: str | None`, `.featureName: str | None`.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/api/test_work_items_api.py` (use the existing `client` fixture and the file's existing helpers for creating projects/items — mirror how other tests in this file POST `/projects/{id}/work-items`; the snippet below assumes a helper that returns the created item's JSON `data`):

```python
def test_work_item_out_exposes_key_and_lineage_names(client):
    # project
    proj = client.post("/projects", json={"name": "NAAF Test"}).json()["data"]
    pid = proj["id"]

    def create(kind, title, parent_field=None, parent_id=None):
        body = {"type": kind, "title": title, "status": "todo", "priority": "medium"}
        if parent_field:
            body[parent_field] = parent_id
        return client.post(f"/projects/{pid}/work-items", json=body).json()["data"]

    epic = create("epic", "Auth")
    feature = create("feature", "Login flow", "epicId", epic["id"])
    task = create("task", "Fix login bug", "featureId", feature["id"])

    # key = <project.key>-<seq>; NAAF Test -> NAAF, epic is seq 1
    assert epic["key"] == "NAAF-1"
    assert feature["key"] == "NAAF-2"
    assert task["key"] == "NAAF-3"

    # lineage names
    assert epic["epicName"] is None and epic["featureName"] is None
    assert feature["epicName"] == "Auth" and feature["featureName"] is None
    assert task["epicName"] == "Auth" and task["featureName"] == "Login flow"


def test_list_work_items_includes_key(client):
    proj = client.post("/projects", json={"name": "Acme"}).json()["data"]
    pid = proj["id"]
    client.post(
        f"/projects/{pid}/work-items",
        json={"type": "epic", "title": "E", "status": "todo", "priority": "medium"},
    )
    items = client.get("/work-items", params={"project": pid}).json()["data"]
    assert items[0]["key"] == "ACME-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_work_items_api.py -k "exposes_key or list_work_items_includes_key" -v`
Expected: FAIL — `KeyError: 'key'` / `epicName` missing.

- [ ] **Step 3: Write minimal implementation**

In `projects/server/src/interactors/api/contract.py`, add the three fields to `WorkItemOut` (keep `id` first; `key` required):

```python
class WorkItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    key: str
    type: str  # WorkItemKind value
    title: str
    status: str  # WorkItemStatus value
    priority: str  # Priority value
    assignedAgent: Any | None = None
    epicId: str | None = None
    epicName: str | None = None
    featureId: str | None = None
    featureName: str | None = None
    projectId: str
    tokenUsageThisRun: int | None = None
    tokenUsageAllRuns: int | None = None
    tokenLimit: int | None = None
    spec: str | None = None
    attachments: list[Any] | None = None
    createdAt: str
    updatedAt: str
```

In `projects/server/src/interactors/api/routes/work_items.py`, replace the lineage/out helpers and update every caller. First, the helpers (near the top, after imports):

```python
from typing import NamedTuple


class Lineage(NamedTuple):
    epic_id: str | None = None
    epic_name: str | None = None
    feature_id: str | None = None
    feature_name: str | None = None


def _resolve_lineage(item: WorkItem, uow: SqlUnitOfWork) -> Lineage:
    """Return the epic/feature ids + names by walking the parent chain (≤2 reads)."""
    if item.parent_id is None:
        return Lineage()
    parent = uow.work_items.read(item.parent_id)
    if parent.kind == WorkItemKind.EPIC:
        return Lineage(epic_id=parent.id, epic_name=parent.title)
    if parent.kind == WorkItemKind.FEATURE:
        epic_id: str | None = None
        epic_name: str | None = None
        if parent.parent_id:
            epic = uow.work_items.read(parent.parent_id)
            epic_id, epic_name = epic.id, epic.title
        return Lineage(epic_id, epic_name, parent.id, parent.title)
    return Lineage()


def _compose_key(item: WorkItem, project_key: str | None) -> str:
    """Human-readable key, e.g. 'NAAF-42'. Falls back to the raw id if unset."""
    if project_key and item.seq is not None:
        return f"{project_key}-{item.seq}"
    return item.id


def _work_item_out(
    item: WorkItem,
    lineage: Lineage,
    project_key: str | None,
    attachments: list | None = None,
) -> WorkItemOut:
    return WorkItemOut(
        id=item.id,
        key=_compose_key(item, project_key),
        type=item.kind.value,
        title=item.title,
        status=item.status.value,
        priority=item.priority.value,
        assignedAgent=None,
        epicId=lineage.epic_id,
        epicName=lineage.epic_name,
        featureId=lineage.feature_id,
        featureName=lineage.feature_name,
        projectId=item.project_id,
        tokenUsageThisRun=None,
        tokenUsageAllRuns=None,
        tokenLimit=None,
        spec=item.body or None,
        attachments=attachments or [],
        createdAt=iso(item.created_at),
        updatedAt=iso(item.updated_at),
    )
```

Now update each caller (the `_work_item_out` signature changed from `(item, epic_id, feature_id, ...)` to `(item, lineage, project_key, ...)`):

`read_work_item` (fetch the project for its key):

```python
@router.get("/{id}", response_model=Envelope[WorkItemOut])
def read_work_item(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    item = uow.work_items.read(id.hex)
    project = uow.projects.read(item.project_id)
    atts = uow.attachments.read_multi(
        filters={"work_item_id": item.id}, order_by="created_at"
    ).results
    att_out = [
        AttachmentOut(
            id=a.id,
            filename=a.filename,
            contentType=a.content_type,
            size=a.size,
            url=f"/work-items/{item.id}/attachments/{a.id}",
            createdAt=iso(a.created_at),
        ).model_dump()
        for a in atts
    ]
    return ok(_work_item_out(item, _resolve_lineage(item, uow), project.key, attachments=att_out))
```

`update_work_item` — replace the final return:

```python
    updated = uow.work_items.update(id.hex, UpdateWorkItem(**data))  # type: ignore[arg-type]
    project = uow.projects.read(updated.project_id)
    return ok(_work_item_out(updated, _resolve_lineage(updated, uow), project.key))
```

`list_work_items` — cache project keys and pass through:

```python
    results = []
    project_keys: dict[str, str | None] = {}
    for item in page.results:
        lineage = _resolve_lineage(item, uow)
        if epic and lineage.epic_id != epic:
            continue
        if item.project_id not in project_keys:
            project_keys[item.project_id] = uow.projects.read(item.project_id).key
        results.append(_work_item_out(item, lineage, project_keys[item.project_id]))
```

`transition_work_item` — replace the final return:

```python
    saved = uow.work_items.update(id.hex, current.model_copy(update={"status": new_status}))
    project = uow.projects.read(saved.project_id)
    return ok(_work_item_out(saved, _resolve_lineage(saved, uow), project.key))
```

`create_work_item` — capture the project already being read for validation:

```python
    project = uow.projects.read(project_id)  # owner-scoped: missing or foreign project → 404
    parent_id = body.featureId or body.epicId or None
    parent = uow.work_items.read(parent_id) if parent_id else None
    validate_hierarchy(body.type, parent)
    if parent is not None and parent.project_id != project_id:
        raise InvalidHierarchy("parent must belong to the same project")
    item = WorkItem(
        owner_id="",  # stamped by repo from required_filters
        project_id=project_id,
        parent_id=parent_id,
        kind=body.type,
        title=body.title,
        body=body.spec or "",
        priority=body.priority,
        status=body.status,
    )
    saved = uow.work_items.create(item)
    return ok(_work_item_out(saved, _resolve_lineage(saved, uow), project.key))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_work_items_api.py tests/api/test_contract_api.py -v`
Expected: PASS. If `test_contract_api.py` asserts an exact `WorkItemOut` field set, update its expected keys to include `key`, `epicName`, `featureName`.

Then the full backend suite + gates:
Run: `cd projects/server && make coverage && make lint`
Expected: PASS, coverage ≥ 80%.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/work_items.py projects/server/tests/api/test_work_items_api.py projects/server/tests/api/test_contract_api.py
git commit -m "feat: expose work item key + epic/feature names on WorkItemOut"
```

---

## Task 5: Seed a real epic → feature → task hierarchy

So the live board/list surfaces show lineage breadcrumbs against seeded data (seeded keys/seqs already flow automatically from Task 2).

**Files:**
- Modify: `projects/server/src/interactors/cli/seed.py`
- Test: `projects/server/tests/cli/test_seed.py` (add/adjust)

**Interfaces:**
- Consumes: `WorkItemRepository.create` / `ProjectRepository.create` (Task 2).
- Produces: seeded demo project whose tasks have an epic + feature parent.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/cli/test_seed.py` (follow the file's existing setup for calling `seed_demo` with a `session_factory` + `owner_id`):

```python
def test_seed_demo_creates_hierarchy_with_keys(session_factory):
    from interactors.cli.seed import seed_demo
    from adapters.database.uow import SqlUnitOfWork

    seed_demo(session_factory, owner_id="u1")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.read_multi(filters={"name": "Demo Project"}).results[0]
        items = uow.work_items.read_multi(
            filters={"project_id": project.id}, page_size=0, order_by="seq"
        ).results

    assert project.key == "DEMO"
    assert {i.seq for i in items} == set(range(1, len(items) + 1))
    # at least one task hangs under a feature under an epic
    by_id = {i.id: i for i in items}
    tasks = [i for i in items if i.kind.value == "task"]
    assert any(
        (feat := by_id.get(t.parent_id)) is not None
        and feat.kind.value == "feature"
        and by_id.get(feat.parent_id) is not None
        and by_id[feat.parent_id].kind.value == "epic"
        for t in tasks
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/cli/test_seed.py -k hierarchy_with_keys -v`
Expected: FAIL — seeded items are currently flat (tasks have no parent).

- [ ] **Step 3: Write minimal implementation**

Rewrite `seed_demo`'s item creation in `projects/server/src/interactors/cli/seed.py` to build an epic → feature → tasks tree. Replace the `_DEMO_ITEMS` list and the creation loop:

```python
DEMO_EPIC = (WorkItemKind.EPIC, "Core Infrastructure", WorkItemStatus.DONE, Priority.HIGH)
DEMO_FEATURE = (WorkItemKind.FEATURE, "CI & Auth", WorkItemStatus.IN_PROGRESS, Priority.HIGH)
# tasks hang under the feature
_DEMO_TASKS: list[tuple[str, WorkItemStatus, Priority]] = [
    ("Set up CI pipeline", WorkItemStatus.IN_REVIEW, Priority.HIGH),
    ("Implement authentication", WorkItemStatus.IN_PROGRESS, Priority.URGENT),
    ("Design database schema", WorkItemStatus.TODO, Priority.MEDIUM),
    ("Write API documentation", WorkItemStatus.BACKLOG, Priority.LOW),
    ("Add end-to-end tests", WorkItemStatus.BACKLOG, Priority.MEDIUM),
]
```

And the body of `seed_demo` after the project is created:

```python
        kind, title, status, priority = DEMO_EPIC
        epic = uow.work_items.create(
            WorkItem(owner_id=owner_id, project_id=project.id, kind=kind,
                     title=title, status=status, priority=priority)
        )
        kind, title, status, priority = DEMO_FEATURE
        feature = uow.work_items.create(
            WorkItem(owner_id=owner_id, project_id=project.id, parent_id=epic.id,
                     kind=kind, title=title, status=status, priority=priority)
        )
        for title, status, priority in _DEMO_TASKS:
            uow.work_items.create(
                WorkItem(owner_id=owner_id, project_id=project.id, parent_id=feature.id,
                         kind=WorkItemKind.TASK, title=title, status=status, priority=priority)
            )
        return project.id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/cli/test_seed.py -v`
Expected: PASS. Fix any other assertion in `test_seed.py` that assumed the old flat item count.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/cli/seed.py projects/server/tests/cli/test_seed.py
git commit -m "feat: seed demo project with epic/feature/task hierarchy"
```

---

## Task 6: UI types — OpenAPI schema + fixtures

Add the three fields to the OpenAPI spec, regenerate the TS types, and enrich the MSW fixtures so the mocked board/list still type-check and render.

**Files:**
- Modify: `projects/ui/openapi/naaf-api.yaml` (`WorkItem` schema)
- Modify: `projects/ui/src/lib/api/schema.d.ts` (regenerated — do not hand-edit)
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts`

**Interfaces:**
- Produces: `components["schemas"]["WorkItem"]` gains required `key: string` and nullable `epicName`, `featureName`.

- [ ] **Step 1: Edit the OpenAPI spec**

In `projects/ui/openapi/naaf-api.yaml`, update the `WorkItem` schema: add `key` to `required`, and add the three properties:

```yaml
    WorkItem:
      type: object
      required: [id, key, type, title, status, priority, projectId, createdAt, updatedAt]
      properties:
        id: { type: string }
        key: { type: string }
        type: { type: string, enum: [epic, feature, task] }
        title: { type: string }
        status:
          type: string
          enum: [backlog, todo, in_progress, in_review, done]
        priority: { type: string, enum: [low, medium, high, urgent] }
        assignedAgent: { $ref: "#/components/schemas/Agent", nullable: true }
        epicId: { type: string, nullable: true }
        epicName: { type: string, nullable: true }
        featureId: { type: string, nullable: true }
        featureName: { type: string, nullable: true }
        projectId: { type: string }
        tokenUsageThisRun: { type: integer, nullable: true }
        tokenUsageAllRuns: { type: integer, nullable: true }
        tokenLimit: { type: integer, nullable: true }
        spec: { type: string, nullable: true }
        attachments:
          type: array
          items: { $ref: "#/components/schemas/Attachment" }
          nullable: true
        createdAt: { type: string, format: date-time }
        updatedAt: { type: string, format: date-time }
```

- [ ] **Step 2: Regenerate the types**

Run: `cd projects/ui && pnpm gen:api`
Expected: `src/lib/api/schema.d.ts` updated; `git diff` shows `key`, `epicName`, `featureName` on the `WorkItem` schema.

- [ ] **Step 3: Verify the fixtures now fail type-check**

Run: `cd projects/ui && pnpm exec tsc --noEmit`
Expected: FAIL — the `workItems` fixture array is missing the now-required `key`.

- [ ] **Step 4: Enrich the fixtures**

In `projects/ui/src/lib/api/mocks/fixtures/index.ts`, remove the explicit `: WorkItem[]` annotation from the literal (rename to `baseWorkItems`) and derive the three fields once, so we don't hand-edit ~15 entries:

```typescript
// was: const workItems: WorkItem[] = [ ... ];
const baseWorkItems = [
  // ...the existing array of work item objects, unchanged...
];

const byId = new Map(baseWorkItems.map((w) => [w.id, w] as const));
const workItems: WorkItem[] = baseWorkItems.map((w, i) => ({
  ...w,
  key: `DEMO-${i + 1}`,
  epicName: w.epicId ? byId.get(w.epicId)?.title ?? null : null,
  featureName: w.featureId ? byId.get(w.featureId)?.title ?? null : null,
})) as WorkItem[];
```

Keep the downstream `export`/usage of `workItems` unchanged.

- [ ] **Step 5: Verify type-check + tests pass**

Run: `cd projects/ui && pnpm exec tsc --noEmit && pnpm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/openapi/naaf-api.yaml projects/ui/src/lib/api/schema.d.ts projects/ui/src/lib/api/mocks/fixtures/index.ts
git commit -m "feat: add key + epic/feature names to WorkItem API type + fixtures"
```

---

## Task 7: `LineageBreadcrumb` + board card + list row

Show the readable key and the `Epic › Feature` breadcrumb on the board and list.

**Files:**
- Create: `projects/ui/src/modules/board/LineageBreadcrumb.tsx`
- Create: `projects/ui/src/modules/board/LineageBreadcrumb.test.tsx`
- Modify: `projects/ui/src/modules/board/KanbanCard.tsx`
- Modify: `projects/ui/src/modules/board/ListRow.tsx`
- Test: `projects/ui/src/modules/board/KanbanCard.test.tsx`, `ListRow.test.tsx`

**Interfaces:**
- Consumes: `WorkItem.key`, `.epicName`, `.featureName` (Task 6).
- Produces: `LineageBreadcrumb({ item })` component.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/modules/board/LineageBreadcrumb.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LineageBreadcrumb } from "./LineageBreadcrumb";

describe("LineageBreadcrumb", () => {
  it("renders epic › feature when both present", () => {
    render(<LineageBreadcrumb item={{ epicName: "Auth", featureName: "Login flow" }} />);
    expect(screen.getByText("Auth › Login flow")).toBeInTheDocument();
  });

  it("renders only the epic when feature is absent", () => {
    render(<LineageBreadcrumb item={{ epicName: "Auth", featureName: null }} />);
    expect(screen.getByText("Auth")).toBeInTheDocument();
  });

  it("renders nothing when there is no lineage", () => {
    const { container } = render(
      <LineageBreadcrumb item={{ epicName: null, featureName: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- LineageBreadcrumb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `projects/ui/src/modules/board/LineageBreadcrumb.tsx`:

```tsx
import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];

export function LineageBreadcrumb({
  item,
}: {
  item: Pick<WorkItem, "epicName" | "featureName">;
}) {
  const parts = [item.epicName, item.featureName].filter(Boolean) as string[];
  if (parts.length === 0) return null;
  const label = parts.join(" › ");
  return (
    <span className="min-w-0 truncate font-mono text-[9px] text-text-6" title={label}>
      {label}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test -- LineageBreadcrumb`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire into KanbanCard and ListRow**

In `projects/ui/src/modules/board/KanbanCard.tsx`: import the component, remove the now-unused `Tag` import, show the key, and replace the epicId tag.

```tsx
import { Link } from "react-router-dom";
import { Avatar } from "../../components/ui";
import { LineageBreadcrumb } from "./LineageBreadcrumb";
import type { WorkItem } from "./groupByStatus";
```

Row 1 key span:

```tsx
        <span className="font-mono text-[9.5px] text-text-6">{item.key}</span>
```

Row 3 (replace the `epicId` Tag with the breadcrumb):

```tsx
      {/* Row 3: lineage + token count */}
      <div className="flex items-center gap-[6px] min-w-0">
        <LineageBreadcrumb item={item} />
        {item.tokenUsageThisRun != null && (
          <span className={`font-mono text-[9px] ${isInProgress ? "text-accent" : "text-text-6"}`}>
            {(item.tokenUsageThisRun / 1000).toFixed(1)}k
          </span>
        )}
      </div>
```

In `projects/ui/src/modules/board/ListRow.tsx`: import `LineageBreadcrumb`, drop `Tag` from the imports, show the key, and replace the epicId tag.

```tsx
import { Link } from "react-router-dom";
import { Avatar, PriorityBars, StatusCircle } from "../../components/ui";
import { LineageBreadcrumb } from "./LineageBreadcrumb";
import type { WorkItem } from "./groupByStatus";
```

Key span:

```tsx
      <span className="w-[62px] shrink-0 font-mono text-[10.5px] text-text-6">{item.key}</span>
```

Replace `{item.epicId != null && <Tag>{item.epicId}</Tag>}` with:

```tsx
      <LineageBreadcrumb item={item} />
```

- [ ] **Step 6: Update the card/row tests**

In `projects/ui/src/modules/board/KanbanCard.test.tsx` and `ListRow.test.tsx`, make the test fixtures include `key`, `epicName`, `featureName`, and assert the key + breadcrumb render (and that the raw `id` no longer needs to). Example assertion to add:

```tsx
expect(screen.getByText("NAAF-3")).toBeInTheDocument();
expect(screen.getByText("Auth › Login flow")).toBeInTheDocument();
```

(Set `key: "NAAF-3"`, `epicName: "Auth"`, `featureName: "Login flow"` on the item passed to the component. If these tests build their item from the shared fixtures, they already carry the fields from Task 6.)

- [ ] **Step 7: Run tests + lint**

Run: `cd projects/ui && pnpm test && pnpm lint`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add projects/ui/src/modules/board/LineageBreadcrumb.tsx projects/ui/src/modules/board/LineageBreadcrumb.test.tsx projects/ui/src/modules/board/KanbanCard.tsx projects/ui/src/modules/board/ListRow.tsx projects/ui/src/modules/board/KanbanCard.test.tsx projects/ui/src/modules/board/ListRow.test.tsx
git commit -m "feat: show work item key + epic/feature breadcrumb on board and list"
```

---

## Task 8: Detail screen — key + lineage names

Surface the key and replace the raw-hex breadcrumb/tags on the detail screen.

**Files:**
- Modify: `projects/ui/src/modules/detail/ItemHeader.tsx`
- Modify: `projects/ui/src/modules/detail/Breadcrumb.tsx`
- Test: `projects/ui/src/modules/detail/ItemHeader.test.tsx`, `Breadcrumb.test.tsx`

**Interfaces:**
- Consumes: `WorkItem.key`, `.epicName`, `.featureName` (Task 6).

- [ ] **Step 1: Write the failing test**

In `projects/ui/src/modules/detail/ItemHeader.test.tsx`, add an assertion that the key chip and epic/feature names render (extend the existing item fixture with `key`, `epicName`, `featureName`):

```tsx
it("shows the key and lineage names", () => {
  render(<ItemHeader item={{ ...baseItem, key: "NAAF-3", epicName: "Auth", featureName: "Login flow" }} />);
  expect(screen.getByText("NAAF-3")).toBeInTheDocument();
  expect(screen.getByText("Auth")).toBeInTheDocument();
  expect(screen.getByText("Login flow")).toBeInTheDocument();
});
```

In `projects/ui/src/modules/detail/Breadcrumb.test.tsx`, assert the breadcrumb ends with the key and uses names (extend the fixture the same way):

```tsx
it("renders epic/feature names and the key", () => {
  render(<Breadcrumb item={{ ...baseItem, key: "NAAF-3", epicName: "Auth", featureName: "Login flow" }} />);
  expect(screen.getByText("Auth")).toBeInTheDocument();
  expect(screen.getByText("Login flow")).toBeInTheDocument();
  expect(screen.getByText("NAAF-3")).toBeInTheDocument();
});
```

(If the test files don't already define a `baseItem`, build one inline with the required `WorkItem` fields — mirror the existing item objects already used in these two test files.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- ItemHeader Breadcrumb`
Expected: FAIL — key/names not rendered.

- [ ] **Step 3: Write minimal implementation**

In `projects/ui/src/modules/detail/ItemHeader.tsx`, add a key chip first in the metadata row and swap the `epicId` tag for name tags:

```tsx
      {/* Metadata row */}
      <div className="flex flex-wrap items-center gap-[6px]">
        <span className={CHIP_CLASS}>{item.key}</span>
        <span className={CHIP_CLASS}>{item.status}</span>
        <span className={CHIP_CLASS}>{item.priority}</span>
        {item.assignedAgent && (
          <span className={CHIP_CLASS}>{item.assignedAgent.id}</span>
        )}
        {item.epicName && <Tag tone="accent">{item.epicName}</Tag>}
        {item.featureName && <Tag>{item.featureName}</Tag>}
      </div>
```

In `projects/ui/src/modules/detail/Breadcrumb.tsx`, build segments from names + key instead of raw hex ids (drop the `projectId` and `id` hex segments — the key already encodes the project):

```tsx
export function Breadcrumb({ item }: { item: WorkItem }) {
  const segments: { label: string; emphasized?: boolean }[] = [];

  if (item.epicName) {
    segments.push({ label: item.epicName });
  }
  if (item.featureName) {
    segments.push({ label: item.featureName });
  }
  segments.push({ label: item.key, emphasized: true });

  return (
    <div className="flex h-[34px] items-center gap-[6px] px-[16px] text-[11px] text-text-5">
      {segments.map((seg, i) => (
        <span key={seg.label} className="flex items-center gap-[6px]">
          {i > 0 && <Chevron />}
          <span className={seg.emphasized ? "text-text-3" : undefined}>
            {seg.label}
          </span>
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run tests + lint**

Run: `cd projects/ui && pnpm test -- ItemHeader Breadcrumb && pnpm lint`
Expected: PASS. Then the full UI suite: `cd projects/ui && pnpm test`
Expected: PASS. Fix any detail-module snapshot/test that still expects the old hex breadcrumb.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/detail/ItemHeader.tsx projects/ui/src/modules/detail/Breadcrumb.tsx projects/ui/src/modules/detail/ItemHeader.test.tsx projects/ui/src/modules/detail/Breadcrumb.test.tsx
git commit -m "feat: show work item key + lineage names on detail screen"
```

---

## Final verification (before PR)

- [ ] Backend gates: `cd projects/server && make coverage && make lint` → green, ≥80%.
- [ ] UI gates: `cd projects/ui && pnpm lint && pnpm test` → green.
- [ ] Manual smoke (optional but recommended — use the project `verify`/`run` skill): start the stack, confirm the board card and list row show `DEMO-N` + `Core Infrastructure › CI & Auth`, and the detail header shows the key.
- [ ] Push + open PR: `git push -u origin feat/work-item-key` then `gh pr create` with a `feat:` title, summary, and this plan's test coverage as the test plan.

## Self-review notes (author)

- **Spec coverage:** key format (Task 1/2/4), project prefix auto-derived + stored (Task 1/2), per-project seq (Task 2), migration + backfill (Task 3), lineage names in API (Task 4), board + list breadcrumb (Task 7), detail key display (Task 8), seed exercises derivation (Task 5), MSW fixtures carry fields (Task 6). **Inbox thread header is deferred** — divergence from spec, called out in "Deferred".
- **Type consistency:** `Lineage` NamedTuple + `_work_item_out(item, lineage, project_key, attachments=None)` used identically across all five route callers; `derive_project_key(name, taken)` signature identical in domain + migration; `LineageBreadcrumb({ item })` takes `Pick<WorkItem,"epicName"|"featureName">` and is called with the full `WorkItem` (structurally compatible).
- **No placeholders:** every code step shows complete code.
