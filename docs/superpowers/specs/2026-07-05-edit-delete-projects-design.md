# Edit & Delete Projects — Design

**Date:** 2026-07-05
**Status:** Approved — ready for implementation plan

## Problem

Projects can be created but never edited or removed. The user wants to:

1. Edit an existing project's details — including a **description** field that does not exist yet.
2. Delete a project (with all its work items, runs, threads, etc.).
3. Reach both actions from a small **edit affordance on each sidebar project row**, opening a
   modal that reuses the create-project modal's look and fields.

## What already exists

- **Backend routes are done.** `routes/projects.py` already has `PATCH /projects/{id}` and
  `DELETE /projects/{id}`. `ProjectUpdateIn` accepts `name` and `repoUrl`.
- **The modal pattern is established.** `CreateModalProvider` already renders create/edit modals
  keyed by a discriminated `State` union, exposed via the `useCreateModal()` context — this is
  exactly how `EditWorkItemModal` is wired (`openEditWorkItem`). We follow that pattern.
- **Delete is incomplete.** The current `DELETE` calls `uow.projects.delete(id)`, which deletes a
  single row. A project with work items would violate the un-cascaded
  `work_items.project_id → projects.id` FK (and orphan many un-FK'd rows). Only empty projects can
  be deleted today; the existing test only covers the empty case.

## Decisions

| Decision | Choice |
|---|---|
| Editable fields | Name, Repo URL, **and a new real `description` field** |
| Delete guard | **Inline confirm** inside the edit modal (reveal a confirm row, no separate dialog) |
| Delete on a populated project | **Cascade-delete everything** under the project |
| Cascade mechanism | **App-level, in one UnitOfWork transaction** — not DB `ON DELETE CASCADE` |
| Modal structure | Separate `EditProjectModal` (mirrors `EditWorkItemModal`), sharing a `ProjectFormFields` component with the create modal (DRY) |

### Why app-level cascade, not DB `ON DELETE CASCADE`

Several descendant tables reference their parent by a **plain string with no foreign key**, so a
DB-level cascade physically cannot reach them:

- `runs.project_id` — `String`, indexed, **no FK**
- `run_events.run_id`, `notifications.run_id`, `bus_messages.run_id`, `messages.run_id` — no FK
- `messages.thread_id` — a work-item id **or** `project:<projectId>` (40 chars); no FK
- `agent_events.scope` — `thread:<threadId>` or `run:<runId>`; no FK

Because those must be cleaned up in application code regardless, doing the *entire* cascade
app-level keeps it in one explicit, unit-testable place and avoids an FK-altering Alembic migration
(painful under SQLite, which requires a batch table rebuild). The only new migration is the
additive `description` column.

## Architecture

### 1. Backend — `description` field

Thread a new `description` (default `""`) through the stack the same way `repo_url` already flows:

- `domain/project.py` — `Project.description: str = ""`
- `adapters/database/orm.py` — `ProjectRow.description` (`String`, `default=""`, `nullable=False`,
  `server_default=""`)
- **Alembic** `0015_project_description` — add column with `server_default=''`
- `interactors/api/schemas.py` — `CreateProject.description` / `UpdateProject.description`
- `interactors/api/contract.py` — `ProjectOut.description`, `ProjectCreateIn.description = ""`,
  `ProjectUpdateIn.description: str | None = None`
- `routes/projects.py` — pass `description` into `CreateProject`/`UpdateProject`, and include it in
  every `ProjectOut` (create/read/list/update)

### 2. Backend — cascade delete

New method `SqlUnitOfWork.delete_project_cascade(project_id: str)`, run inside the request's UoW
transaction, executing in dependency order. It needs a bulk **`delete_where(**filters)`** operation
on the repositories/port (added alongside the existing single-id `delete`); un-FK'd tables that
have no repository get a small targeted delete helper.

Order:

1. Collect `work_item_ids` = work items with `project_id == P`; `run_ids` = runs with
   `project_id == P`.
2. Delete run-keyed rows: `run_events`, `notifications`, `bus_messages`, `messages` (by `run_id`),
   `agent_events` (scope `run:<runId>`).
3. Delete work-item-keyed rows: `attachments`, `messages` (thread == work-item id),
   `agent_events` (scope `thread:<wiId>`).
4. Delete project-thread rows: `messages` (thread == `project:<P>`),
   `agent_events` (scope `thread:project:<P>`).
5. Delete `runs` (by `project_id`), then `work_items` (by `project_id`), then the `project`.

`routes/projects.py::delete_project` calls `uow.delete_project_cascade(id.hex)` instead of
`uow.projects.delete(...)`. Response stays `204`.

> Owner scoping is preserved: every repository query already applies the required `owner_id`
> filter, so the cascade only ever touches the caller's own rows.

### 3. Frontend

- **`PencilIcon`** — new icon in `components/ui/icons` (+ export in `icons/index.ts`).
- **Hooks** (`lib/api/hooks`):
  - `useUpdateProject(id)` — `apiPatch<Project>('/projects/${id}', body)`; invalidates
    `queryKeys.projects()`.
  - `useDeleteProject(id)` — `apiDelete('/projects/${id}')`; invalidates `queryKeys.projects()`;
    on success, if the deleted project is the one selected in the URL, navigate away
    (e.g. to `/projects`).
  - Export both from `hooks/index.ts`; add `ProjectUpdate` type.
- **`ProjectFormFields`** — extracted component rendering Name / Repo URL / Description
  (`FormField` + `TextInput`/`Textarea`), consumed by both modals. `CreateProjectModal` adopts it
  and thereby gains the Description field.
- **`EditProjectModal`** (`modules/create/`, mirrors `EditWorkItemModal`):
  - Prefills from the passed `Project`; **Save** calls `useUpdateProject`.
  - Footer **Delete** button toggles an inline confirm row: *"Delete this project and all its work
    items? This can't be undone."* → **Cancel** / **Confirm delete** (calls `useDeleteProject`,
    then `onClose`). Mutation errors surface inline like the other modals.
- **Modal wiring:**
  - `useCreateModal.ts` — add `openEditProject: (project: Project) => void` to the context.
  - `CreateModalProvider.tsx` — add `{ kind: "edit-project"; project: Project }` to `State`, the
    `openEditProject` setter, and render `<EditProjectModal project={...} onClose={close} />`.
- **Sidebar `ProjectRow`:** wrap in a `group relative` container; keep the `NavLink` for
  navigation and overlay a pencil button that is `opacity-0 group-hover:opacity-100`, with
  `aria-label="Edit project"`, calling
  `e.preventDefault(); e.stopPropagation(); openEditProject(project)` so it never triggers
  navigation. It sits at the row's right edge (alongside/over the item count).
- **OpenAPI types:** regenerate `lib/api/schema.ts` so `Project`, `ProjectCreate`, `ProjectUpdate`
  carry `description`.

## Data flow

```
Sidebar ProjectRow ─ pencil click ─▶ openEditProject(project)
        │                                   │
        │                          CreateModalProvider state = { edit-project, project }
        ▼                                   ▼
   (NavLink nav unaffected)          <EditProjectModal>
                                        ├─ Save    ─▶ useUpdateProject ─▶ PATCH /projects/{id}
                                        └─ Delete ─▶ inline confirm ─▶ useDeleteProject
                                                                        └─▶ DELETE /projects/{id}
                                                                              └─▶ delete_project_cascade
```

## Error handling

- **Modal:** mutation `isError` renders an inline red message (same pattern as `CreateProjectModal`
  / `EditWorkItemModal`); the modal stays open so the user can retry or cancel.
- **Delete navigation:** if the active project is deleted, redirect to `/projects` to avoid a board
  view pointing at a now-missing project.
- **Cascade:** runs entirely within the UoW transaction — any failure rolls back, leaving the
  project and its descendants intact (no partial deletion).
- **Validation:** Name required (non-empty) to enable Save, matching create.

## Testing

**Backend**
- `description` round-trips: present in create response, editable via `PATCH`, returned by
  `GET` and list.
- `delete_project_cascade` removes a project that has a work item + attachment + run + run events +
  notification + bus message + work-item-thread messages + project-thread messages + agent events,
  and leaves **no orphaned rows** in any of those tables. (This is the central new test — today's
  suite only deletes empty projects.)
- Deleting an empty project still returns `204` and then `404` on read (existing behavior intact).

**Frontend**
- `EditProjectModal`: prefills fields; Save calls the update hook with edited values and closes.
- Delete is gated: the Delete button reveals the confirm row; only **Confirm delete** invokes the
  delete hook; **Cancel** hides the row without deleting.
- Sidebar: the pencil is present per row, does not navigate, and opens the edit modal.
- `CreateProjectModal` still creates a project with the new Description field included.

## Out of scope (YAGNI)

- No DB `ON DELETE CASCADE` migration (see rationale above).
- No soft-delete / archive / undo — hard delete only.
- No editing of `team_id` / `autonomy_level` from this modal.
- No bulk project actions.
```
