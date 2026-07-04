# Inbox thread → work-item link

**Date:** 2026-07-04
**Status:** Draft (awaiting review)

## Problem

Each inbox conversation is a thread over a work item. The conversation header
(`ConversationPane` → `TaskBanner`) already shows the work item's title, but:

- The title is plain text — there is no way to jump from a conversation to the
  work item it belongs to.
- The banner's most prominent element is a truncated raw hex id
  (`workItemId.slice(0, 8)`), not the human-readable name.

Users reading a thread in the inbox should be able to click the work-item name
to open that work item.

## Goal

Show the work-item name at the top of an inbox thread as a **link to the
work-item detail screen**.

Non-goals: redesigning the thread header, changing the message list, or altering
project-chat behaviour beyond giving it a sensible link target.

## Constraints & findings

- The work-item detail route is `/projects/:projectId/items/:itemId`
  (`app/routes.tsx`). It requires **both** a project id and an item id.
- The thread API (`ThreadOut` / `ThreadView`) currently carries `workItemId` and
  `title` but **not** `projectId`. This is the core gap.
- `WorkItem.project_id` exists on the domain model, so the project id is
  available server-side.
- Project-level threads (`id = "project:<id>"`, the "chat with lead"
  conversation) have `work_item_id = ""` — there is no work item to open.
- The codebase already links to work items via a React-Router `<Link>`:
  `to={`/projects/${item.projectId}/items/${item.id}`}` in
  `board/KanbanCard.tsx` and `board/ListRow.tsx`. Reuse this pattern.

## Approach

Thread the project id through the existing DTO chain, then turn the existing
banner `<div>` into a `<Link>`.

### 1. Backend — surface `projectId` on threads

- `domain/messaging/thread.py`: add `project_id: str` to `ThreadView`.
  - `thread_from_work_item` → `project_id=item.project_id`.
  - `thread_from_project` → `project_id=project.id` (with `work_item_id=""`).
- `interactors/api/contract.py`: add `projectId: str` to `ThreadOut`.
- `interactors/api/routes/threads.py`: map `projectId=view.project_id` in
  `_thread_out`. `ThreadDetailOut` inherits it via `_thread_out(...).model_dump()`.

### 2. Frontend — make the banner a link

`modules/inbox/ConversationPane.tsx` — `TaskBanner`:

- Work-item thread → `<Link to={`/projects/${projectId}/items/${workItemId}`}>`
  wrapping the title.
- Project thread (no `workItemId`) → `<Link to={`/projects?project=${projectId}`}>`
  (the board for that project), showing the project name.
- Guard: if `projectId` is missing, render the title as plain text (no broken
  link).
- Promote the readable title to the primary link label; keep an unobtrusive
  hover affordance consistent with existing links.

### 3. Mock + contract plumbing

- Regenerate `lib/api/schema.d.ts` from the backend OpenAPI so
  `Thread.projectId` exists.
- `lib/api/mocks/db.ts`: populate `projectId` in `findThread` / `threadDetail`
  by looking up the work item's `projectId` (already present in the mock db).
- `openapi/contract.test.ts`: extend as needed for the new field.

### 4. Tests (TDD — write first)

- Backend:
  - `thread_from_work_item` sets `project_id` from the work item.
  - `thread_from_project` sets `project_id` from the project.
  - Threads route test asserts `projectId` appears in the response envelope.
- Frontend:
  - `ConversationPane.test.tsx`: banner renders an anchor whose `href` is
    `/projects/{projectId}/items/{workItemId}` for a work-item thread.
  - Banner links to `/projects?project={projectId}` for a project thread.

## Edge cases

| Case | Behaviour |
|------|-----------|
| Work-item thread | Title links to the detail screen |
| Project-level thread (no work item) | Project name links to the board |
| `projectId` missing/empty | Title rendered as plain text, no link |

## Testing & gates

- `make coverage` (80% gate) and `make lint` green before PR.
- UI unit tests for the banner in both mock and live shapes.
