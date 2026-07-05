# Edit & Delete Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user edit a project (name, repo URL, and a new description field) and delete a project — including all its descendants — from an Edit Project modal reached via a pencil affordance on each sidebar project row.

**Architecture:** Backend already exposes `PATCH`/`DELETE /projects/{id}`. We (1) add a real `description` field through the domain/ORM/API stack with an additive Alembic migration, (2) make `DELETE` cascade to every descendant via an app-level `SqlUnitOfWork.delete_project_cascade` (the FK-less run/event/message/notification tables can't be reached by DB `ON DELETE CASCADE`), and (3) build the frontend: an `EditProjectModal` (reusing a shared `ProjectFormFields`) with inline-confirm delete, two React Query hooks, a `PencilIcon`, and sidebar wiring through the existing `CreateModalProvider`.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · pytest · React · TypeScript · TanStack Query · Vite · Tailwind · Vitest · MSW.

## Global Constraints

- Immutability: Pydantic models updated via `model_copy(update={...})`, never mutated; React state via new objects.
- API envelope: every response is `{success, data, error}` (+ `meta`).
- Owner scoping: every repository query carries the UoW's required `owner_id` filter.
- Entity IDs are 32-char UUID hex strings.
- TDD: write the failing test first; AAA structure; descriptive behavior names.
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore/perf/ci).
- Gates before PR: `make coverage` (80%) and `make lint` (ruff + mypy) green for backend; `pnpm lint` (eslint + tsc) and `pnpm test` green for UI.
- Backend commands run from repo root; UI commands run from `projects/ui`.
- Migration head is `0015_run_cost`; the new migration is `0016_project_description`.

---

## File Structure

**Backend**
- Modify `projects/server/src/domain/project.py` — add `description`.
- Modify `projects/server/src/adapters/database/orm.py` — `ProjectRow.description`.
- Create `projects/server/src/adapters/database/migrations/versions/0016_project_description.py`.
- Modify `projects/server/src/interactors/api/schemas.py` — `CreateProject`/`UpdateProject`.
- Modify `projects/server/src/interactors/api/contract.py` — `ProjectOut`/`ProjectCreateIn`/`ProjectUpdateIn`.
- Modify `projects/server/src/interactors/api/routes/projects.py` — `_project_out` helper, thread `description`, cascade delete.
- Modify `projects/server/src/adapters/database/repository.py` — `delete_where`.
- Modify `projects/server/src/adapters/database/repositories.py` — `BusMessageRepository.delete_by_run_ids`.
- Modify `projects/server/src/adapters/database/uow.py` — `delete_project_cascade`.
- Tests: `projects/server/tests/api/test_projects_api.py`, `projects/server/tests/adapters/test_uow.py`.

**Frontend** (under `projects/ui`)
- Create `src/components/ui/icons/PencilIcon.tsx`; modify `icons/index.ts`, `icons/icons.test.tsx`.
- Modify `openapi/naaf-api.yaml`; regenerate `src/lib/api/schema.d.ts`.
- Create `src/lib/api/hooks/useUpdateProject.ts`, `src/lib/api/hooks/useDeleteProject.ts` (+ tests); modify `src/lib/api/hooks/index.ts`.
- Create `src/modules/create/ProjectFormFields.tsx`; modify `src/modules/create/CreateProjectModal.tsx` (+ its test).
- Create `src/modules/create/EditProjectModal.tsx` (+ test); modify `src/components/ui/Button.tsx` (+ nothing else) to add a `danger` variant.
- Modify `src/modules/create/useCreateModal.ts`, `src/modules/create/CreateModalProvider.tsx` (+ its test).
- Modify `src/app/Sidebar.tsx` (+ its test).
- Modify `src/lib/api/mocks/db.ts`, `src/lib/api/mocks/handlers.ts` (+ `handlers.test.ts`), `src/lib/api/mocks/fixtures/index.ts`.

---

## Task 1: Backend `description` field end-to-end

**Files:**
- Modify: `projects/server/src/domain/project.py`
- Modify: `projects/server/src/adapters/database/orm.py:30-36`
- Create: `projects/server/src/adapters/database/migrations/versions/0016_project_description.py`
- Modify: `projects/server/src/interactors/api/schemas.py:7-20`
- Modify: `projects/server/src/interactors/api/contract.py:98-120`
- Modify: `projects/server/src/interactors/api/routes/projects.py`
- Test: `projects/server/tests/api/test_projects_api.py`

**Interfaces:**
- Produces: `Project.description: str`, `ProjectOut.description: str`, `ProjectCreateIn.description: str = ""`, `ProjectUpdateIn.description: str | None = None`, and a `_project_out(p, uow) -> ProjectOut` helper in the route module.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/api/test_projects_api.py`:

```python
def test_project_description_defaults_empty_and_round_trips(client):
    created = client.post("/projects/", json={"name": "p"}).json()["data"]
    assert created["description"] == ""
    pid = created["id"]

    patched = client.patch(f"/projects/{pid}", json={"description": "ship the PR"}).json()["data"]
    assert patched["description"] == "ship the PR"

    got = client.get(f"/projects/{pid}").json()["data"]
    assert got["description"] == "ship the PR"

    listed = client.get("/projects/").json()["data"]
    assert any(p["id"] == pid and p["description"] == "ship the PR" for p in listed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py::test_project_description_defaults_empty_and_round_trips -v`
Expected: FAIL — response has no `description` key (KeyError) / `ProjectOut` validation error.

- [ ] **Step 3: Add `description` to the domain model**

In `projects/server/src/domain/project.py`, add the field to `Project`:

```python
class Project(Entity):
    owner_id: str
    name: str
    description: str = ""
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL
```

- [ ] **Step 4: Add the ORM column**

In `projects/server/src/adapters/database/orm.py`, inside `ProjectRow` (after `name`):

```python
    description: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
```

- [ ] **Step 5: Create the Alembic migration**

Create `projects/server/src/adapters/database/migrations/versions/0016_project_description.py`:

```python
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
```

- [ ] **Step 6: Thread `description` through the API schemas**

In `projects/server/src/interactors/api/schemas.py`, add to `CreateProject` (after `name`) and `UpdateProject`:

```python
class CreateProject(BaseModel):
    name: str
    description: str = ""
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    description: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel | None = None
```

- [ ] **Step 7: Thread `description` through the contract**

In `projects/server/src/interactors/api/contract.py`, add `description` to the three project models (keep existing fields):

```python
class ProjectOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    description: str
    repoUrl: str
    itemCount: int
    createdAt: str
    updatedAt: str


class ProjectCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    description: str = ""
    repoUrl: str = ""


class ProjectUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str | None = None
    description: str | None = None
    repoUrl: str | None = None
```

- [ ] **Step 8: DRY the route with a `_project_out` helper and thread `description`**

In `projects/server/src/interactors/api/routes/projects.py`, add the helper below `_item_count`, and replace the four inline `ProjectOut(...)` constructions with it:

```python
def _project_out(p, uow: SqlUnitOfWork) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        repoUrl=p.repo_url or "",
        itemCount=_item_count(p.id, uow),
        createdAt=iso(p.created_at),
        updatedAt=iso(p.updated_at),
    )
```

Then:
- `create_project`: `p = uow.projects.create(CreateProject(name=body.name, description=body.description, repo_url=body.repoUrl))` → `return ok(_project_out(p, uow))`
- `read_project`: `return ok(_project_out(uow.projects.read(id.hex), uow))`
- `list_projects`: `results = [_project_out(p, uow) for p in page.results]`
- `update_project`: `p = uow.projects.update(id.hex, UpdateProject(name=body.name, description=body.description, repo_url=body.repoUrl))` → `return ok(_project_out(p, uow))`

- [ ] **Step 9: Run the test to verify it passes**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py -v`
Expected: PASS (new test + existing `test_patch_project`, `test_create_and_get_project`, etc.).

- [ ] **Step 10: Verify migration applies and lint is clean**

Run: `cd projects/server && uv run alembic upgrade head && cd ../.. && uv run ruff check projects/server/src && uv run mypy projects/server/src`
Expected: `alembic` reaches `0016_project_description`; ruff and mypy report no errors.

- [ ] **Step 11: Commit**

```bash
git add projects/server/src/domain/project.py projects/server/src/adapters/database/orm.py \
  projects/server/src/adapters/database/migrations/versions/0016_project_description.py \
  projects/server/src/interactors/api/schemas.py projects/server/src/interactors/api/contract.py \
  projects/server/src/interactors/api/routes/projects.py projects/server/tests/api/test_projects_api.py
git commit -m "feat: add editable project description field"
```

---

## Task 2: Bulk `delete_where` on repositories

**Files:**
- Modify: `projects/server/src/adapters/database/repository.py`
- Modify: `projects/server/src/adapters/database/repositories.py`
- Test: `projects/server/tests/adapters/test_uow.py`

**Interfaces:**
- Consumes: `SqlRepository` (Task 0 baseline), `BusMessageRepository`.
- Produces: `SqlRepository.delete_where(**filters) -> int` (supports plain-equality and `__in` filters, always AND-ed with the UoW's `required_filters`); `BusMessageRepository.delete_by_run_ids(run_ids: list[str]) -> None`.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/adapters/test_uow.py`:

```python
def test_delete_where_respects_owner_and_in_filter(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.api.schemas import CreateProject

    a = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a.transaction():
        p1 = a.projects.create(CreateProject(name="p1"))
        p2 = a.projects.create(CreateProject(name="p2"))

    other = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with other.transaction():
        pb = other.projects.create(CreateProject(name="pb"))

    a2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "a"})
    with a2.transaction():
        removed = a2.projects.delete_where(id__in=[p1.id, p2.id, pb.id])
        assert removed == 2  # pb belongs to owner "b" and is filtered out

    b2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "b"})
    with b2.transaction():
        assert b2.projects.read(pb.id).id == pb.id  # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py::test_delete_where_respects_owner_and_in_filter -v`
Expected: FAIL — `AttributeError: 'ProjectRepository' object has no attribute 'delete_where'`.

- [ ] **Step 3: Implement `delete_where` on `SqlRepository`**

In `projects/server/src/adapters/database/repository.py`, update the import line and add the method at the end of the class:

```python
from sqlalchemy import Delete, Select, asc, delete as sql_delete, desc, func, select
```

```python
    def delete_where(self, **filters: Any) -> int:
        """Bulk-delete rows matching required_filters AND the given filters.

        Supports plain equality and the ``<field>__in`` suffix (the only shapes
        the project cascade needs). Returns the number of rows deleted.
        """
        stmt: Delete = sql_delete(self.orm_model)
        for key, value in {**self.required_filters, **filters}.items():
            if key.endswith("__in"):
                stmt = stmt.where(getattr(self.orm_model, key[:-4]).in_(value))
            else:
                stmt = stmt.where(getattr(self.orm_model, key) == value)
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)
```

- [ ] **Step 4: Add `delete_by_run_ids` to `BusMessageRepository`**

In `projects/server/src/adapters/database/repositories.py`, update the import line and add the method to `BusMessageRepository`:

```python
from sqlalchemy import delete as sql_delete, func, select
```

```python
    def delete_by_run_ids(self, run_ids: list[str]) -> None:
        if not run_ids:
            return
        self.session.execute(sql_delete(BusMessageRow).where(BusMessageRow.run_id.in_(run_ids)))
        self.session.flush()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py::test_delete_where_respects_owner_and_in_filter -v`
Expected: PASS.

- [ ] **Step 6: Lint**

Run: `uv run ruff check projects/server/src && uv run mypy projects/server/src`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add projects/server/src/adapters/database/repository.py \
  projects/server/src/adapters/database/repositories.py \
  projects/server/tests/adapters/test_uow.py
git commit -m "feat: add owner-scoped bulk delete_where to repositories"
```

---

## Task 3: Cascade delete + wire into the route

**Files:**
- Modify: `projects/server/src/adapters/database/uow.py`
- Modify: `projects/server/src/interactors/api/routes/projects.py`
- Test: `projects/server/tests/adapters/test_uow.py`, `projects/server/tests/api/test_projects_api.py`

**Interfaces:**
- Consumes: `delete_where` / `delete_by_run_ids` (Task 2); scope format `stream_scope` (`thread:<id>` / `run:<id>`) and project thread id `project:<projectId>`.
- Produces: `SqlUnitOfWork.delete_project_cascade(project_id: str) -> None`.

- [ ] **Step 1: Write the failing cascade test**

Add to `projects/server/tests/adapters/test_uow.py`:

```python
def test_delete_project_cascade_removes_all_descendants(session_factory):
    from sqlalchemy import func, select

    from adapters.database.orm import BusMessageRow
    from adapters.database.uow import SqlUnitOfWork
    from domain.agent.events import EVENT_TEXT, AgentEvent
    from domain.attachments.attachment import Attachment
    from domain.errors import RecordNotFound
    from domain.messaging.message import Message
    from domain.notifications.notification import Notification, NotificationType
    from domain.runs.events import EventType, RunEvent
    from domain.runs.messages import AgentMessage, MessageType
    from domain.runs.run import Run
    from domain.work_item import WorkItem, WorkItemKind
    from interactors.api.schemas import CreateProject

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p = uow.projects.create(CreateProject(name="p"))
        wi = uow.work_items.create(
            WorkItem(owner_id="u1", project_id=p.id, kind=WorkItemKind.TASK, title="t")
        )
        run = uow.runs.create(
            Run(owner_id="u1", work_item_id=wi.id, project_id=p.id, autonomy_level="gated_all")
        )
        uow.run_events.create(RunEvent(owner_id="u1", run_id=run.id, type=EventType.LOG))
        uow.notifications.create(
            Notification(owner_id="u1", run_id=run.id, type=NotificationType.RUN_SUCCEEDED,
                         title="done", source_seq=1)
        )
        uow.bus_messages.publish(
            AgentMessage(owner_id="u1", run_id=run.id, recipient="run:x:lead",
                         role="lead", type=MessageType.START)
        )
        uow.attachments.create(
            Attachment(owner_id="u1", work_item_id=wi.id, filename="a.txt",
                       content_type="text/plain", size=1)
        )
        uow.messages.create(Message(owner_id="u1", thread_id=wi.id, content="hi"))
        uow.messages.create(Message(owner_id="u1", thread_id=f"project:{p.id}", content="proj"))
        uow.agent_events.create(AgentEvent(owner_id="u1", scope=f"run:{run.id}", kind=EVENT_TEXT))
        uow.agent_events.create(AgentEvent(owner_id="u1", scope=f"thread:{wi.id}", kind=EVENT_TEXT))
        uow.agent_events.create(
            AgentEvent(owner_id="u1", scope=f"thread:project:{p.id}", kind=EVENT_TEXT)
        )

    act = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with act.transaction():
        act.delete_project_cascade(p.id)

    check = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with check.transaction():
        assert check.work_items.read_multi(page_size=0).total == 0
        assert check.runs.read_multi(page_size=0).total == 0
        assert check.run_events.read_multi(page_size=0).total == 0
        assert check.notifications.read_multi(page_size=0).total == 0
        assert check.attachments.read_multi(page_size=0).total == 0
        assert check.messages.read_multi(page_size=0).total == 0
        assert check.agent_events.read_multi(page_size=0).total == 0
        bus_total = check.session.execute(
            select(func.count()).select_from(BusMessageRow)
        ).scalar_one()
        assert bus_total == 0
        with pytest.raises(RecordNotFound):
            check.projects.read(p.id)
```

Ensure `import pytest` is present at the top of the test file (add it if missing).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py::test_delete_project_cascade_removes_all_descendants -v`
Expected: FAIL — `AttributeError: 'SqlUnitOfWork' object has no attribute 'delete_project_cascade'`.

- [ ] **Step 3: Implement `delete_project_cascade`**

In `projects/server/src/adapters/database/uow.py`, add the method to `SqlUnitOfWork` (after the repository properties):

```python
    def delete_project_cascade(self, project_id: str) -> None:
        """Delete a project and every descendant, in dependency order, within
        this transaction. Un-FK'd tables (runs/events/notifications/bus_messages/
        messages/agent_events) are cleaned up explicitly because a DB-level
        ON DELETE CASCADE cannot reach them."""
        wi_ids = [
            w.id
            for w in self.work_items.read_multi(
                filters={"project_id": project_id}, page_size=0
            ).results
        ]
        run_ids = [
            r.id
            for r in self.runs.read_multi(
                filters={"project_id": project_id}, page_size=0
            ).results
        ]

        if run_ids:
            self.run_events.delete_where(run_id__in=run_ids)
            self.notifications.delete_where(run_id__in=run_ids)
            self.bus_messages.delete_by_run_ids(run_ids)

        scopes = (
            [f"run:{rid}" for rid in run_ids]
            + [f"thread:{wid}" for wid in wi_ids]
            + [f"thread:project:{project_id}"]
        )
        self.agent_events.delete_where(scope__in=scopes)

        thread_ids = [*wi_ids, f"project:{project_id}"]
        self.messages.delete_where(thread_id__in=thread_ids)

        if wi_ids:
            self.attachments.delete_where(work_item_id__in=wi_ids)

        self.runs.delete_where(project_id=project_id)
        self.work_items.delete_where(project_id=project_id)
        self.projects.delete(project_id)
```

- [ ] **Step 4: Run the cascade test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py::test_delete_project_cascade_removes_all_descendants -v`
Expected: PASS.

- [ ] **Step 5: Add a route test for deleting a populated project**

Add to `projects/server/tests/api/test_projects_api.py`:

```python
def test_delete_project_with_work_item_cascades(client):
    pid = client.post("/projects/", json={"name": "p"}).json()["data"]["id"]
    client.post(f"/projects/{pid}/work-items", json={"kind": "task", "title": "t"})

    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get(f"/projects/{pid}").status_code == 404
    assert client.get(f"/work-items?project={pid}").json()["data"] == []
```

- [ ] **Step 6: Run it to verify it fails, then wire the route**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py::test_delete_project_with_work_item_cascades -v`
Expected: FAIL — the current route calls `uow.projects.delete`, which raises an FK/integrity error on Postgres (and leaves the work item on SQLite).

In `projects/server/src/interactors/api/routes/projects.py`, change `delete_project`:

```python
@router.delete("/{id}", status_code=204, response_class=Response)
def delete_project(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.delete_project_cascade(id.hex)
    return Response(status_code=204)
```

(A missing project still raises `RecordNotFound` from `projects.delete` inside the cascade → enveloped 404, preserving `test_get_missing_project_is_enveloped_404` behavior for delete.)

- [ ] **Step 7: Run the full project + uow suites**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py projects/server/tests/adapters/test_uow.py -v`
Expected: PASS (including the existing `test_delete_project` empty-project case).

- [ ] **Step 8: Lint**

Run: `uv run ruff check projects/server/src && uv run mypy projects/server/src`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add projects/server/src/adapters/database/uow.py \
  projects/server/src/interactors/api/routes/projects.py \
  projects/server/tests/adapters/test_uow.py projects/server/tests/api/test_projects_api.py
git commit -m "feat: cascade-delete project descendants on delete"
```

---

## Task 4: `PencilIcon`

**Files:**
- Create: `projects/ui/src/components/ui/icons/PencilIcon.tsx`
- Modify: `projects/ui/src/components/ui/icons/index.ts`
- Test: `projects/ui/src/components/ui/icons/icons.test.tsx`

**Interfaces:**
- Produces: `PencilIcon` (exported from `components/ui/icons` and re-exported by `components/ui`).

- [ ] **Step 1: Add `PencilIcon` to the icon-set test**

In `projects/ui/src/components/ui/icons/icons.test.tsx`, add `"PencilIcon"` to the `names` array:

```tsx
  const names = [
    "DashboardIcon", "InboxIcon", "ProjectsIcon", "AgentsIcon", "SettingsIcon",
    "SearchIcon", "GitRepoIcon", "ListIcon", "GridIcon", "PlusIcon",
    "ChevronDownIcon", "ChevronRightIcon", "CheckIcon", "DocumentIcon", "PencilIcon",
  ] as const;
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `projects/ui`): `pnpm test src/components/ui/icons/icons.test.tsx`
Expected: FAIL — `Icons.PencilIcon` is `undefined`, not a function.

- [ ] **Step 3: Create the icon**

Create `projects/ui/src/components/ui/icons/PencilIcon.tsx`:

```tsx
import type { IconProps } from "./types";

export function PencilIcon({ size = 11, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 11 11" fill="none" className={className}>
      <path
        d="M7.4 1.6l2 2L4 9l-2.4.6L2.2 7.2 7.4 1.6z"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      <path d="M6.6 2.4l2 2" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}
```

- [ ] **Step 4: Export it**

In `projects/ui/src/components/ui/icons/index.ts`, add:

```ts
export { PencilIcon } from "./PencilIcon";
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm test src/components/ui/icons/icons.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/components/ui/icons/PencilIcon.tsx \
  projects/ui/src/components/ui/icons/index.ts \
  projects/ui/src/components/ui/icons/icons.test.tsx
git commit -m "feat: add PencilIcon"
```

---

## Task 5: Project schema types + update/delete hooks

**Files:**
- Modify: `projects/ui/openapi/naaf-api.yaml:684-706`
- Regenerate: `projects/ui/src/lib/api/schema.d.ts`
- Create: `projects/ui/src/lib/api/hooks/useUpdateProject.ts`, `projects/ui/src/lib/api/hooks/useDeleteProject.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts`
- Test: `projects/ui/src/lib/api/hooks/useUpdateProject.test.tsx`, `projects/ui/src/lib/api/hooks/useDeleteProject.test.tsx`

**Interfaces:**
- Produces: `useUpdateProject(id: string)` (mutates `ProjectUpdate`, returns `Project`); `useDeleteProject(id: string)` (mutates `void`); types `ProjectUpdate`, `Project`. Both invalidate `queryKeys.projects()`.

- [ ] **Step 1: Add `description` to the OpenAPI schemas**

In `projects/ui/openapi/naaf-api.yaml`, add `description` (optional — not in `required`) to the three project schemas:

```yaml
    Project:
      type: object
      required: [id, name, repoUrl, itemCount, createdAt, updatedAt]
      properties:
        id: { type: string }
        name: { type: string }
        description: { type: string }
        repoUrl: { type: string }
        itemCount: { type: integer }
        createdAt: { type: string, format: date-time }
        updatedAt: { type: string, format: date-time }

    ProjectCreate:
      type: object
      required: [name, repoUrl]
      properties:
        name: { type: string }
        description: { type: string }
        repoUrl: { type: string }

    ProjectUpdate:
      type: object
      properties:
        name: { type: string }
        description: { type: string }
        repoUrl: { type: string }
```

- [ ] **Step 2: Regenerate the typed schema**

Run (from `projects/ui`): `pnpm gen:api`
Expected: `src/lib/api/schema.d.ts` regenerates; `git diff` shows `description?: string` added to `Project`, `ProjectCreate`, `ProjectUpdate`.

- [ ] **Step 3: Write the failing hook tests**

Create `projects/ui/src/lib/api/hooks/useUpdateProject.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useUpdateProject } from "./useUpdateProject";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("patches a project and resolves with the updated project", async () => {
  server.use(
    http.patch("/api/projects/p1", async ({ request }) => {
      const body = (await request.json()) as { description?: string };
      return HttpResponse.json({
        success: true, error: null,
        data: { id: "p1", name: "P", description: body.description ?? "", repoUrl: "", itemCount: 0, createdAt: "", updatedAt: "" },
      });
    }),
  );
  const { result } = renderHook(() => useUpdateProject("p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ description: "new desc" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.description).toBe("new desc");
});
```

Create `projects/ui/src/lib/api/hooks/useDeleteProject.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useDeleteProject } from "./useDeleteProject";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("deletes a project and resolves", async () => {
  server.use(
    http.delete("/api/projects/p1", () =>
      HttpResponse.json({ success: true, error: null, data: null }),
    ),
  );
  const { result } = renderHook(() => useDeleteProject("p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync();
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pnpm test src/lib/api/hooks/useUpdateProject.test.tsx src/lib/api/hooks/useDeleteProject.test.tsx`
Expected: FAIL — modules `./useUpdateProject` / `./useDeleteProject` do not exist.

- [ ] **Step 5: Create the hooks**

Create `projects/ui/src/lib/api/hooks/useUpdateProject.ts`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPatch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ProjectUpdate = components["schemas"]["ProjectUpdate"];
export type Project = components["schemas"]["Project"];

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdate) => apiPatch<Project>(`/projects/${id}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
```

Create `projects/ui/src/lib/api/hooks/useDeleteProject.ts`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete } from "../client";
import { queryKeys } from "../queryKeys";

export function useDeleteProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete(`/projects/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
```

- [ ] **Step 6: Export the hooks**

In `projects/ui/src/lib/api/hooks/index.ts`, add:

```ts
export { useUpdateProject } from "./useUpdateProject";
export type { ProjectUpdate } from "./useUpdateProject";
export { useDeleteProject } from "./useDeleteProject";
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pnpm test src/lib/api/hooks/useUpdateProject.test.tsx src/lib/api/hooks/useDeleteProject.test.tsx`
Expected: PASS.

- [ ] **Step 8: Typecheck**

Run: `pnpm lint`
Expected: eslint + `tsc --noEmit` clean.

- [ ] **Step 9: Commit**

```bash
git add projects/ui/openapi/naaf-api.yaml projects/ui/src/lib/api/schema.d.ts \
  projects/ui/src/lib/api/hooks/useUpdateProject.ts projects/ui/src/lib/api/hooks/useDeleteProject.ts \
  projects/ui/src/lib/api/hooks/useUpdateProject.test.tsx projects/ui/src/lib/api/hooks/useDeleteProject.test.tsx \
  projects/ui/src/lib/api/hooks/index.ts
git commit -m "feat: project description type + update/delete hooks"
```

---

## Task 6: Shared `ProjectFormFields` + Description in create modal

**Files:**
- Create: `projects/ui/src/modules/create/ProjectFormFields.tsx`
- Modify: `projects/ui/src/modules/create/CreateProjectModal.tsx`
- Test: `projects/ui/src/modules/create/CreateProjectModal.test.tsx`

**Interfaces:**
- Produces: `ProjectFormValues` (`{ name: string; repoUrl: string; description: string }`) and `ProjectFormFields({ values, onChange })` where `onChange(patch: Partial<ProjectFormValues>)`.

- [ ] **Step 1: Add a failing test for the Description field in create**

Add to `projects/ui/src/modules/create/CreateProjectModal.test.tsx`:

```tsx
test("submits the description with the new project", async () => {
  let received: { name: string; description?: string } | null = null;
  server.use(
    http.post("/api/projects", async ({ request }) => {
      received = (await request.json()) as { name: string; description?: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: received.name, description: received.description ?? "", repoUrl: "", itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  renderModal();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  await userEvent.type(screen.getByLabelText(/description/i), "our repo");
  await userEvent.click(screen.getByRole("button", { name: /create project/i }));
  await waitFor(() => expect(received?.description).toBe("our repo"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/modules/create/CreateProjectModal.test.tsx`
Expected: FAIL — no field labelled "Description" exists yet.

- [ ] **Step 3: Create `ProjectFormFields`**

Create `projects/ui/src/modules/create/ProjectFormFields.tsx`:

```tsx
import { FormField, Textarea, TextInput } from "../../components/ui";

export interface ProjectFormValues {
  name: string;
  repoUrl: string;
  description: string;
}

interface Props {
  values: ProjectFormValues;
  onChange: (patch: Partial<ProjectFormValues>) => void;
}

export function ProjectFormFields({ values, onChange }: Props) {
  return (
    <>
      <FormField label="Name">
        <TextInput
          aria-label="Name"
          value={values.name}
          onChange={(e) => onChange({ name: e.target.value })}
          autoFocus
        />
      </FormField>
      <FormField label="Repo URL">
        <TextInput
          aria-label="Repo URL"
          value={values.repoUrl}
          placeholder="https://github.com/org/repo"
          onChange={(e) => onChange({ repoUrl: e.target.value })}
        />
      </FormField>
      <FormField label="Description">
        <Textarea
          aria-label="Description"
          value={values.description}
          onChange={(e) => onChange({ description: e.target.value })}
        />
      </FormField>
    </>
  );
}
```

- [ ] **Step 4: Adopt it in `CreateProjectModal`**

Replace the body of `projects/ui/src/modules/create/CreateProjectModal.tsx` with:

```tsx
import { useState } from "react";
import { Button, Modal } from "../../components/ui";
import { useCreateProject } from "../../lib/api/hooks";
import { ProjectFormFields, type ProjectFormValues } from "./ProjectFormFields";

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<ProjectFormValues>({ name: "", repoUrl: "", description: "" });
  const mutation = useCreateProject();
  const canSubmit = form.name.trim().length > 0 && !mutation.isPending;

  async function submit() {
    try {
      await mutation.mutateAsync({
        name: form.name.trim(),
        repoUrl: form.repoUrl.trim(),
        description: form.description.trim(),
      });
    } catch {
      return; // error is surfaced via mutation.isError
    }
    onClose();
  }

  return (
    <Modal
      title="Create Project"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(); }}>
            {mutation.isPending ? "Creating…" : "Create Project"}
          </Button>
        </>
      }
    >
      <ProjectFormFields values={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))} />
      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{mutation.error instanceof Error ? mutation.error.message : String(mutation.error)}</p>
      )}
    </Modal>
  );
}
```

- [ ] **Step 5: Run the create-modal tests to verify they pass**

Run: `pnpm test src/modules/create/CreateProjectModal.test.tsx`
Expected: PASS (new description test + existing "submit disabled until name" / "creates and closes").

- [ ] **Step 6: Typecheck**

Run: `pnpm lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/modules/create/ProjectFormFields.tsx \
  projects/ui/src/modules/create/CreateProjectModal.tsx \
  projects/ui/src/modules/create/CreateProjectModal.test.tsx
git commit -m "feat: shared ProjectFormFields with description field"
```

---

## Task 7: `EditProjectModal` with inline-confirm delete

**Files:**
- Modify: `projects/ui/src/components/ui/Button.tsx`
- Create: `projects/ui/src/modules/create/EditProjectModal.tsx`
- Test: `projects/ui/src/modules/create/EditProjectModal.test.tsx`

**Interfaces:**
- Consumes: `ProjectFormFields` (Task 6), `useUpdateProject`/`useDeleteProject` (Task 5), `Project` type, react-router `useNavigate`/`useSearchParams`.
- Produces: `EditProjectModal({ project: Project, onClose: () => void })`; `Button` gains a `danger` variant.

- [ ] **Step 1: Add a `danger` variant to `Button`**

In `projects/ui/src/components/ui/Button.tsx`, extend the variant union and map:

```tsx
type Variant = "primary" | "secondary" | "tertiary" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white",
  secondary: "border border-[rgba(255,255,255,0.12)] text-text-3",
  tertiary: "border border-border text-text-4",
  danger: "bg-[#e5686b] text-white",
};
```

- [ ] **Step 2: Write the failing modal tests**

Create `projects/ui/src/modules/create/EditProjectModal.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { EditProjectModal } from "./EditProjectModal";
import type { components } from "../../lib/api/schema";

const project = {
  id: "p1", name: "Acme", description: "old desc", repoUrl: "https://x/y",
  itemCount: 3, createdAt: "", updatedAt: "",
} as components["schemas"]["Project"];

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <EditProjectModal project={project} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose };
}

test("prefills fields from the project", () => {
  renderModal();
  expect((screen.getByLabelText(/name/i) as HTMLInputElement).value).toBe("Acme");
  expect((screen.getByLabelText(/description/i) as HTMLTextAreaElement).value).toBe("old desc");
});

test("saves edits and closes", async () => {
  let received: { description?: string } | null = null;
  server.use(
    http.patch("/api/projects/p1", async ({ request }) => {
      received = (await request.json()) as { description?: string };
      return HttpResponse.json({ success: true, error: null, data: { ...project, description: received.description ?? "" } });
    }),
  );
  const { onClose } = renderModal();
  const desc = screen.getByLabelText(/description/i);
  await userEvent.clear(desc);
  await userEvent.type(desc, "ship it");
  await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(received?.description).toBe("ship it");
});

test("delete is gated behind an inline confirm", async () => {
  const deleteCalled = vi.fn();
  server.use(
    http.delete("/api/projects/p1", () => {
      deleteCalled();
      return HttpResponse.json({ success: true, error: null, data: null });
    }),
  );
  const { onClose } = renderModal();

  await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
  expect(screen.getByText(/can't be undone/i)).toBeInTheDocument();
  expect(deleteCalled).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  expect(screen.queryByText(/can't be undone/i)).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
  await userEvent.click(screen.getByRole("button", { name: /confirm delete/i }));
  await waitFor(() => expect(deleteCalled).toHaveBeenCalledOnce());
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pnpm test src/modules/create/EditProjectModal.test.tsx`
Expected: FAIL — module `./EditProjectModal` does not exist.

- [ ] **Step 4: Create the modal**

Create `projects/ui/src/modules/create/EditProjectModal.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Modal } from "../../components/ui";
import { useDeleteProject, useUpdateProject, type Project } from "../../lib/api/hooks";
import { ProjectFormFields, type ProjectFormValues } from "./ProjectFormFields";

export function EditProjectModal({ project, onClose }: { project: Project; onClose: () => void }) {
  const [form, setForm] = useState<ProjectFormValues>({
    name: project.name,
    repoUrl: project.repoUrl,
    description: project.description ?? "",
  });
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const update = useUpdateProject(project.id);
  const remove = useDeleteProject(project.id);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const canSubmit = form.name.trim().length > 0 && !update.isPending;
  const err = update.error ?? remove.error;

  async function save() {
    try {
      await update.mutateAsync({
        name: form.name.trim(),
        repoUrl: form.repoUrl.trim(),
        description: form.description.trim(),
      });
    } catch {
      return;
    }
    onClose();
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync();
    } catch {
      return;
    }
    if (searchParams.get("project") === project.id) navigate("/projects");
    onClose();
  }

  return (
    <Modal
      title="Edit Project"
      onClose={onClose}
      footer={
        confirmingDelete ? (
          <>
            <Button variant="secondary" onClick={() => setConfirmingDelete(false)}>Cancel</Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => { void confirmDelete(); }}>
              {remove.isPending ? "Deleting…" : "Confirm delete"}
            </Button>
          </>
        ) : (
          <>
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete</Button>
            <div className="flex-1" />
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!canSubmit} onClick={() => { void save(); }}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        )
      }
    >
      {confirmingDelete ? (
        <p className="text-[12px] text-text-1">
          Delete <strong>{project.name}</strong> and all its work items, runs, and threads? This can't be undone.
        </p>
      ) : (
        <ProjectFormFields values={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))} />
      )}
      {err && (
        <p className="text-[10.5px] text-[#e5686b]">{err instanceof Error ? err.message : String(err)}</p>
      )}
    </Modal>
  );
}
```

- [ ] **Step 5: Run the modal tests to verify they pass**

Run: `pnpm test src/modules/create/EditProjectModal.test.tsx`
Expected: PASS (prefill, save, gated delete).

- [ ] **Step 6: Typecheck**

Run: `pnpm lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/components/ui/Button.tsx \
  projects/ui/src/modules/create/EditProjectModal.tsx \
  projects/ui/src/modules/create/EditProjectModal.test.tsx
git commit -m "feat: EditProjectModal with inline-confirm delete"
```

---

## Task 8: Wire `openEditProject` into the modal provider

**Files:**
- Modify: `projects/ui/src/modules/create/useCreateModal.ts`
- Modify: `projects/ui/src/modules/create/CreateModalProvider.tsx`
- Test: `projects/ui/src/modules/create/CreateModalProvider.test.tsx`

**Interfaces:**
- Consumes: `EditProjectModal` (Task 7), `Project` type.
- Produces: `useCreateModal().openEditProject(project: Project)`; provider `State` gains `{ kind: "edit-project"; project: Project }`.

- [ ] **Step 1: Add a failing provider test**

In `projects/ui/src/modules/create/CreateModalProvider.test.tsx`: import `MemoryRouter`, wrap the render in it (so `EditProjectModal`'s router hooks resolve), add an editable `Project`, an "open edit project" button to `Harness`, and a test.

At the top, add:

```tsx
import { MemoryRouter } from "react-router-dom";

const editProject = {
  id: "p1", name: "Acme", description: "", repoUrl: "", itemCount: 0, createdAt: "", updatedAt: "",
} as components["schemas"]["Project"];
```

Update `Harness` to also expose the new opener:

```tsx
function Harness() {
  const { openCreateProject, openCreateWorkItem, openEditWorkItem, openEditProject } = useCreateModal();
  return (
    <>
      <button onClick={() => openCreateProject()}>open project</button>
      <button onClick={() => openCreateWorkItem({ projectId: "p1" })}>open item</button>
      <button onClick={() => openEditWorkItem(editItem)}>open edit</button>
      <button onClick={() => openEditProject(editProject)}>open edit project</button>
    </>
  );
}
```

Wrap the provider in `renderProvider` with `MemoryRouter`:

```tsx
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CreateModalProvider>
          <Harness />
        </CreateModalProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
```

Add the test:

```tsx
test("opens the Edit Project modal pre-filled", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open edit project"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Edit Project");
  expect((screen.getByLabelText(/name/i) as HTMLInputElement).value).toBe("Acme");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/modules/create/CreateModalProvider.test.tsx`
Expected: FAIL — `openEditProject` is `undefined`.

- [ ] **Step 3: Add `openEditProject` to the context type**

In `projects/ui/src/modules/create/useCreateModal.ts`, import `Project` and extend the interface:

```tsx
import { createContext, useContext } from "react";
import type { Project } from "../../lib/api/hooks/useProjects";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";

export interface CreateModalContextValue {
  openCreateProject: () => void;
  openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) => void;
  openEditWorkItem: (item: WorkItem) => void;
  openEditProject: (project: Project) => void;
  close: () => void;
}
```

(Leave `CreateModalContext`, `useCreateModal` unchanged below.)

- [ ] **Step 4: Handle the new state in the provider**

In `projects/ui/src/modules/create/CreateModalProvider.tsx`: import `Project` and `EditProjectModal`, extend `State`, add the setter, render the modal.

```tsx
import { useMemo, useState, type ReactNode } from "react";
import type { Project } from "../../lib/api/hooks/useProjects";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";
import { CreateProjectModal } from "./CreateProjectModal";
import { CreateWorkItemModal } from "./CreateWorkItemModal";
import { EditProjectModal } from "./EditProjectModal";
import { EditWorkItemModal } from "./EditWorkItemModal";
import { CreateModalContext } from "./useCreateModal";

type State =
  | { kind: "none" }
  | { kind: "project" }
  | { kind: "work-item"; projectId: string; status?: WorkItem["status"] }
  | { kind: "edit-work-item"; item: WorkItem }
  | { kind: "edit-project"; project: Project };

export function CreateModalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "none" });

  const value = useMemo(
    () => ({
      openCreateProject: () => setState({ kind: "project" }),
      openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) =>
        setState({ kind: "work-item", projectId: o.projectId, status: o.status }),
      openEditWorkItem: (item: WorkItem) => setState({ kind: "edit-work-item", item }),
      openEditProject: (project: Project) => setState({ kind: "edit-project", project }),
      close: () => setState({ kind: "none" }),
    }),
    [],
  );

  return (
    <CreateModalContext.Provider value={value}>
      {children}
      {state.kind === "project" && <CreateProjectModal onClose={value.close} />}
      {state.kind === "work-item" && (
        <CreateWorkItemModal projectId={state.projectId} initialStatus={state.status} onClose={value.close} />
      )}
      {state.kind === "edit-work-item" && (
        <EditWorkItemModal item={state.item} onClose={value.close} />
      )}
      {state.kind === "edit-project" && (
        <EditProjectModal project={state.project} onClose={value.close} />
      )}
    </CreateModalContext.Provider>
  );
}
```

- [ ] **Step 5: Run the provider tests to verify they pass**

Run: `pnpm test src/modules/create/CreateModalProvider.test.tsx`
Expected: PASS (all existing tests + the new Edit Project test).

- [ ] **Step 6: Typecheck**

Run: `pnpm lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/modules/create/useCreateModal.ts \
  projects/ui/src/modules/create/CreateModalProvider.tsx \
  projects/ui/src/modules/create/CreateModalProvider.test.tsx
git commit -m "feat: wire openEditProject through the modal provider"
```

---

## Task 9: Sidebar edit affordance

**Files:**
- Modify: `projects/ui/src/app/Sidebar.tsx`
- Test: `projects/ui/src/app/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `useCreateModal().openEditProject` (Task 8), `PencilIcon` (Task 4).

- [ ] **Step 1: Add a failing sidebar test**

Add to the `describe("Sidebar", ...)` block in `projects/ui/src/app/Sidebar.test.tsx`:

```tsx
  it("a project's edit pencil opens the Edit Project modal", async () => {
    renderSidebar();
    const editButtons = await screen.findAllByRole("button", { name: /edit project/i });
    await userEvent.click(editButtons[0]);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Edit Project");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/app/Sidebar.test.tsx`
Expected: FAIL — no button named "Edit project" is rendered.

- [ ] **Step 3: Add the pencil affordance to `ProjectRow`**

In `projects/ui/src/app/Sidebar.tsx`, add `PencilIcon` to the icon import and replace the `ProjectRow` component:

```tsx
function ProjectRow({ project }: { project: Project }) {
  const { openEditProject } = useCreateModal();
  return (
    <div className="group relative">
      <NavLink
        to={`/projects?project=${project.id}`}
        className={({ isActive }) =>
          [
            "flex items-center gap-[6px] rounded-[5px] px-[7px] py-[5px] text-[11.5px] transition-colors",
            isActive
              ? "bg-[rgba(124,108,240,0.08)] text-accent-text"
              : "text-[#42454e] hover:text-[#8a8d96]",
          ].join(" ")
        }
      >
        {({ isActive }) => (
          <>
            <GitRepoIcon size={11} className="shrink-0" />
            <span className="flex-1 truncate">{project.name}</span>
            <span
              className={`font-mono text-[9px] transition-opacity group-hover:opacity-0 ${isActive ? "text-accent" : "text-[#4a4d56]"}`}
            >
              {project.itemCount}
            </span>
          </>
        )}
      </NavLink>
      <button
        type="button"
        aria-label="Edit project"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          openEditProject(project);
        }}
        className="absolute right-[7px] top-1/2 -translate-y-1/2 text-[#4a4d56] opacity-0 transition-opacity hover:text-[#8a8d96] group-hover:opacity-100"
      >
        <PencilIcon size={11} />
      </button>
    </div>
  );
}
```

Add `PencilIcon` to the existing `import { ... } from "../components/ui/icons";` block.

- [ ] **Step 4: Run the sidebar tests to verify they pass**

Run: `pnpm test src/app/Sidebar.test.tsx`
Expected: PASS (new pencil test + existing nav/project-list/budget tests).

- [ ] **Step 5: Typecheck**

Run: `pnpm lint`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/app/Sidebar.tsx projects/ui/src/app/Sidebar.test.tsx
git commit -m "feat: add edit pencil to sidebar project rows"
```

---

## Task 10: Mock layer — persist edit/delete + description

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/db.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts:44-96`
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts`
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts`

**Interfaces:**
- Consumes: mock `db` singleton.
- Produces: `db.updateProject(id, patch)`, `db.removeProject(id)`; PATCH/DELETE handlers that persist; create/patch responses include `description`.

- [ ] **Step 1: Add a failing handlers test**

Add to `projects/ui/src/lib/api/mocks/handlers.test.ts`:

```ts
test("PATCH then DELETE a project persists in the mock db", async () => {
  const created = await apiPost<ProjectRow>("/projects", { name: "Temp", repoUrl: "", description: "d0" });
  await apiPatch<ProjectRow>(`/projects/${created.id}`, { description: "d1" });
  const afterPatch = await apiList<ProjectRow>("/projects");
  expect(afterPatch.results.find((p) => p.id === created.id)?.description).toBe("d1");

  await apiDelete(`/projects/${created.id}`);
  const afterDelete = await apiList<ProjectRow>("/projects");
  expect(afterDelete.results.some((p) => p.id === created.id)).toBe(false);
});
```

Ensure the test file imports `apiPatch`, `apiDelete`, `apiList` from `"../client"` (add any missing names to the existing import), and that `ProjectRow` is the type already used in this file (`components["schemas"]["Project"]`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/lib/api/mocks/handlers.test.ts`
Expected: FAIL — the patch/delete handlers don't mutate `db`, so the description isn't persisted and the project isn't removed.

- [ ] **Step 3: Add `updateProject` / `removeProject` to the mock db**

In `projects/ui/src/lib/api/mocks/db.ts`, add these methods to the `db` object (near the existing `addProject` / `updateWorkItem`):

```ts
  updateProject: (id: string, patch: Partial<Project>): Project | null => {
    let updated: Project | null = null;
    projects = projects.map((p) => {
      if (p.id !== id) return p;
      updated = { ...p, ...patch, updatedAt: new Date().toISOString() };
      return updated;
    });
    return updated;
  },
  removeProject: (id: string): boolean => {
    const before = projects.length;
    projects = projects.filter((p) => p.id !== id);
    return projects.length < before;
  },
```

- [ ] **Step 4: Make the handlers persist and carry `description`**

In `projects/ui/src/lib/api/mocks/handlers.ts`, update the create body type and the PATCH/DELETE handlers:

```ts
  http.post(`${BASE}/projects`, async ({ request }) => {
    const body = (await request.json()) as { name: string; repoUrl: string; description?: string };
    const created = {
      id: `proj-${Date.now()}`,
      name: body.name,
      description: body.description ?? "",
      repoUrl: body.repoUrl,
      itemCount: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    db.addProject(created);
    return HttpResponse.json(
      { success: true, data: created, error: null, meta: null },
      { status: 201 },
    );
  }),
```

```ts
  http.patch(`${BASE}/projects/:id`, async ({ params, request }) => {
    const body = (await request.json()) as Partial<{ name: string; repoUrl: string; description: string }>;
    const updated = db.updateProject(params.id as string, body);
    return updated ? ok(updated) : notFound();
  }),

  http.delete(`${BASE}/projects/:id`, ({ params }) => {
    return db.removeProject(params.id as string) ? ok(null) : notFound();
  }),
```

- [ ] **Step 5: Add `description` to the seed fixtures**

In `projects/ui/src/lib/api/mocks/fixtures/index.ts`, add a `description` to each seeded project object (there are two), e.g. `description: "Core control-plane service"` and `description: "React board UI"` — pick short, plausible strings matching each project's name.

- [ ] **Step 6: Run the mock tests to verify they pass**

Run: `pnpm test src/lib/api/mocks/handlers.test.ts`
Expected: PASS.

- [ ] **Step 7: Full UI gate**

Run: `pnpm lint && pnpm test`
Expected: eslint + tsc clean; all Vitest suites pass.

- [ ] **Step 8: Commit**

```bash
git add projects/ui/src/lib/api/mocks/db.ts projects/ui/src/lib/api/mocks/handlers.ts \
  projects/ui/src/lib/api/mocks/handlers.test.ts projects/ui/src/lib/api/mocks/fixtures/index.ts
git commit -m "feat: mock persist project edit/delete + description"
```

---

## Final verification (before PR)

- [ ] **Backend gates:** `make coverage` (≥80%) and `make lint` (ruff + mypy) green.
- [ ] **UI gates:** from `projects/ui`, `pnpm lint` and `pnpm test` green.
- [ ] **Manual smoke (optional, live mode):** run `make dev`, hover a sidebar project → pencil appears → open modal → edit the description → Save (row persists) → reopen → Delete → Confirm delete → project disappears and, if it was the open project, the board navigates to `/projects`.
- [ ] **Push + PR:** `git push -u origin feat/edit-delete-projects` then `gh pr create` with a focused title (`feat: edit & delete projects`), summary, and the test plan above. Keep the worktree alive for review iteration.

---

## Self-Review Notes

- **Spec coverage:** description field (Tasks 1, 5, 6) · PATCH edit (Tasks 1, 5, 7) · cascade delete + no-orphans test (Tasks 2, 3) · inline-confirm delete (Task 7) · sidebar pencil affordance (Tasks 4, 9) · shared ProjectFormFields (Task 6) · provider wiring mirroring EditWorkItem (Task 8) · delete-navigation for the active project (Task 7) · mock persistence for fully-mocked UI (Task 10). All spec sections map to a task.
- **Type consistency:** `ProjectFormValues` (`{name, repoUrl, description}`) is defined in Task 6 and consumed unchanged in Task 7; `openEditProject(project: Project)` is declared in Task 8's context type and called in Tasks 8/9; `delete_where(**filters)` / `delete_by_run_ids(run_ids)` defined in Task 2 are the exact names used in Task 3; migration `0016_project_description` chains from `0015_run_cost`.
- **No placeholders:** every code and test step contains complete, runnable content.
