# Edit Work Item (title · priority · spec) — Design

> Feature **B** of the "dogfood NAAF on itself" effort (sequencing: **B → A+C → D**).
> Quick, self-contained UI win: let a user edit a work item's description from the board UI.

## Problem

A work item's `spec` (its markdown description), `title`, and `priority` are **display-only**
in the UI. The Detail screen's Spec tab renders `item.spec` through `ReactMarkdown` with an
"agent-editable" badge but offers **no human-edit affordance** (`modules/detail/SpecTab.tsx`).
There is no `useUpdateWorkItem` mutation hook, and the generic `apiPatch` helper in
`lib/api/client.ts` is defined but never called. A user cannot refine a description they (or an
agent) wrote.

## Goal

Add an **Edit** affordance on the Detail screen that opens a modal to edit a work item's
`title`, `priority`, and `spec`, persisting via the existing PATCH endpoint. Status stays on the
transition flow — this modal never changes it.

## Non-goals (YAGNI)

- No inline editing on the Detail screen (an edit **modal** was chosen for consistency and speed).
- No status editing here — status changes go through `POST /work-items/{id}/transition`.
- No optimistic concurrency / conflict resolution. The spec is flagged "agent-editable"; if an
  agent and a human edit concurrently it is **last-write-wins**, acceptable for a single-user
  local tool and explicitly out of scope to solve now.
- No editing of parent (epic/feature), assignee, or token limit.

## Backend — no change required

`PATCH /work-items/{id}` already exists and already does exactly what we need:

- Route: `interactors/api/routes/work_items.py` — `@router.patch("/{id}")`,
  `update_work_item(id, body: WorkItemUpdateIn, uow)`. It forwards only the fields present in the
  request (`model_fields_set`): `title`, `priority`, and `spec` (→ domain `body`), and guards
  against nulling the NOT-NULL body column when `spec` is absent.
- Contract: `WorkItemUpdateIn` (`interactors/api/contract.py`) → `UpdateWorkItem`
  (`interactors/api/schemas.py`) → `uow.work_items.update(id, ...)` (generic `SqlRepository.update`,
  partial via `model_dump(exclude_unset=True)`).

This feature is therefore **UI-only** on the server side.

## Frontend — four focused pieces

1. **`useUpdateWorkItem` hook** (`lib/api/hooks/useUpdateWorkItem.ts`)
   - `apiPatch<WorkItem>('/work-items/{id}', body)` where `body` is `{ title?, priority?, spec? }`.
   - On success, invalidate the same query keys `useCreateWorkItem` invalidates — the work-item
     detail query, the board query, and the work-items list — so the Detail screen and board
     refresh. First real consumer of the existing `apiPatch` helper.

2. **`EditWorkItemModal`** (`modules/create/EditWorkItemModal.tsx`)
   - A **new, focused** modal that reuses the shared form **primitives**
     (`FormField` / `TextInput` / `Select` / `Textarea`), pre-filled from the passed-in item.
   - Fields: **Title** (`TextInput`), **Priority** (`Select`, reusing the create modal's priority
     option list), **Spec** (`Textarea`, markdown).
   - Submit button reads **Save** (or "Saving…" while pending); a **Cancel** secondary button
     closes it. On success, close the modal.
   - Deliberately **not** folded into `CreateWorkItemModal` — that modal carries epic/feature/task
     type tabs, parent pickers, and a "create & add another" action that don't apply to edit.
     Keeping them separate keeps both files small and single-purpose (many-small-files).

3. **Provider wiring** (`modules/create/CreateModalProvider.tsx` + `useCreateModal.ts`)
   - Extend the modal state with an `edit-work-item` kind that carries the target work item.
   - Add `openEditWorkItem(item)` to the `useCreateModal` API.
   - Render `<EditWorkItemModal item={…} />` when `state.kind === "edit-work-item"`.
   - The provider name stays `CreateModalProvider`; renaming it is out of scope.

4. **"Edit" button** (`modules/detail/DetailScreen.tsx`)
   - An **Edit** button in the Detail screen header → `openEditWorkItem(item)`.

## Mock-mode parity

Add a `PATCH /work-items/{id}` MSW handler + a `db.updateWorkItem` in the mock store (mirroring
how the creation-modals work added `db.addProject`/`db.addWorkItem`), so edits persist in mock
mode too. Live mode passes straight through to the real backend.

## Data flow

```
Detail "Edit" button
  → openEditWorkItem(item)            (useCreateModal)
  → CreateModalProvider renders EditWorkItemModal (pre-filled)
  → user edits title/priority/spec, clicks Save
  → useUpdateWorkItem → apiPatch PATCH /work-items/{id} { title?, priority?, spec? }
  → (live) backend update_work_item  |  (mock) db.updateWorkItem
  → invalidate work-item detail + board + work-items queries
  → modal closes; Detail + board reflect the change
```

## Error handling

- Empty title is invalid → the Save button is disabled (mirror the create modal's required-field
  handling); the backend also treats an absent field as "no change."
- A failed PATCH surfaces an error state in the modal (reuse the create modal's mutation-error
  display) and keeps the modal open so edits aren't lost.

## Testing

- **`useUpdateWorkItem`** — fires PATCH to the right URL with the edited body; invalidates the
  expected query keys on success.
- **`EditWorkItemModal`** — renders pre-filled from the item, edits a field, submits PATCH, closes
  on success; Save disabled when title is emptied. Follows the existing `CreateWorkItemModal`
  test pattern (MSW-backed).
- Keep the 80% coverage gate green (`make coverage` covers the server; the UI has its own suite).

## Files touched (summary)

| File | Change |
|------|--------|
| `projects/ui/src/lib/api/hooks/useUpdateWorkItem.ts` | **new** mutation hook |
| `projects/ui/src/lib/api/hooks/index.ts` | export the hook |
| `projects/ui/src/modules/create/EditWorkItemModal.tsx` | **new** modal |
| `projects/ui/src/modules/create/CreateModalProvider.tsx` | add `edit-work-item` kind + render |
| `projects/ui/src/modules/create/useCreateModal.ts` | add `openEditWorkItem` |
| `projects/ui/src/modules/detail/DetailScreen.tsx` | add **Edit** button |
| `projects/ui/src/lib/api/mocks/handlers.ts` | add `PATCH /work-items/{id}` handler |
| `projects/ui/src/lib/api/mocks/db.ts` (mock store) | add `updateWorkItem` |
| tests for the hook + modal | **new** |

Server side: **no change.**
