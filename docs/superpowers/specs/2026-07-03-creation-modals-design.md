# Design: Project & Work-Item Creation Modals

**Date:** 2026-07-03
**Status:** Approved (brainstorming) → pending implementation plan
**Scope:** UI-only. Wire up creation of Projects and Work Items (Epic / Feature / Task)
from the board UI. No backend changes.

## Problem

The board UI can read Projects and Work Items but cannot create them. The Topbar
**New** button exists but is wired to a no-op (`onNew={() => {}}` in `AppShell`). Users
have no way to create a Project or a work item (Epic / Feature / Task) from the app.

The backend already supports creation:

- `POST /projects` — body `{ name, repoUrl }` (repoUrl optional, defaults to `""`).
- `POST /projects/{project_id}/work-items` — body `WorkItemCreateIn`:
  `{ type: epic|feature|task, title, status=todo, priority=medium, epicId?, featureId?, spec? }`,
  with server-side hierarchy validation (invalid parent → HTTP 409).

MSW mocks already handle both POSTs (`src/lib/api/mocks/handlers.ts`).

Design reference: **Create Work Item modal (screen H)** in
`docs/design/README.md` / `docs/design/NAAF Hi-Fi.dc.html`:

- Modal overlaid on a ghosted Board background.
- Three type tabs: Epic / Feature / Task (fields adapt per type).
- Footer: **Create [type]** · **Create & add another** · Cancel.

## Decisions (from brainstorming)

1. **Two modals**, matching design H: one *Create Project* modal, and one *Create Work
   Item* modal with Epic/Feature/Task type tabs.
2. **Ship supported fields only.** The design's *Assign Agent* and *Label* fields are
   omitted — `POST work-items` does not accept them, and there is no label model. No
   backend work in this change (YAGNI).
3. **Triggers:** Topbar New (context-aware), board column `+` buttons, and empty-state CTAs.
4. **Modal state via a small React context** (`CreateModalProvider`), not URL params.

## Architecture

Hand-rolled Modal primitive (no dialog library is installed; deps are React 18,
react-router-dom, @tanstack/react-query only). Recreate the hi-fi look using the
existing Tailwind design tokens, consistent with the current `components/ui` primitives.

### New design-system primitives — `src/components/ui/`

- **`Modal.tsx`** — overlay + centered surface panel. Responsibilities: dimmed/ghosted
  backdrop, header/body/footer slots, close on Esc, overlay click, and Cancel; sets
  initial focus on open. Purely presentational — no knowledge of what it contains.
- **Form primitives** (small, focused files): `FormField.tsx` (label + control slot +
  optional error text), `TextInput.tsx`, `Select.tsx`, `Textarea.tsx`. Keep the modal
  forms DRY and each file small.

Each primitive is exported from `components/ui/index.ts` and unit-tested.

### Feature slice — `src/modules/create/`

- **`CreateModalProvider.tsx`** — React context provider. Owns open-state and seed
  values; renders whichever modal is active. Exposes:
  - `openCreateProject()`
  - `openCreateWorkItem({ projectId, status? })`
  - `close()`
  Rendered once, wrapping the app content in `AppShell`.
- **`useCreateModal.ts`** — hook to consume the context from any trigger.
- **`CreateProjectModal.tsx`** — fields: **Name** (required), **Repo URL** (optional).
  Footer: Create / Cancel.
- **`CreateWorkItemModal.tsx`** — Epic / Feature / Task **type tabs**. Fields adapt:
  | Type    | Fields |
  | ------- | ------ |
  | Epic    | Status, Priority, Spec/Description |
  | Feature | Status, Priority, **Parent Epic**, Spec/Description |
  | Task    | Status, Priority, **Parent Epic**, **Parent Feature**, Spec/Description |
  Parent dropdowns are populated from `useProjectWorkItems(projectId)`, filtered by kind.
  Selecting a Parent Feature implies its Parent Epic (kept consistent).
  Footer: **Create [type]** · **Create & add another** · Cancel.

### New API hooks — `src/lib/api/hooks/`

Follow the existing mutation pattern (`useResolveGate`, `useSendMessage`): `useMutation`
+ `apiPost` + `invalidateQueries`.

- **`useCreateProject.ts`** → `apiPost('/projects', { name, repoUrl })`; on success
  invalidate `queryKeys.projects()`.
- **`useCreateWorkItem.ts`** → `apiPost('/projects/${projectId}/work-items', body)` where
  `body = { type, title, status, priority, epicId?, featureId?, spec? }`; on success
  invalidate the project's work-items query (`["work-items", "project", projectId]`) and
  the board query.

Both hooks are exported from `lib/api/hooks/index.ts`.

### Wiring

- **`AppShell.tsx`** wraps its content in `CreateModalProvider`. There is no dedicated
  projects-list screen — `/projects` is the board — so the trigger placement is explicit
  rather than route-inferred:
  - **Topbar New** → *Create Work Item* seeded with the board's currently resolved
    `projectId` (the board's primary action is adding items, matching design H).
  - **Create Project** → a `+` affordance in the **Sidebar** projects section, plus the
    no-projects empty state (see below). This keeps project creation next to where
    projects are listed.
- **Board column headers** (`BoardView`) get a `+` button → `openCreateWorkItem({
  projectId, status })` seeded with that column's status.
- **Empty states** (board/list with no items, or no projects) get a CTA button that opens
  the relevant modal.

### Behavior & conventions

- **Immutability:** controlled forms via `setForm(f => ({ ...f, ...changes }))`; never
  mutate state objects (project convention).
- **Validation:** submit disabled until required fields are valid (Name for project;
  Title for work item). Parent selects validated client-side against the hierarchy so we
  don't rely solely on the 409.
- **Error handling (explicit):** surface API errors inline in the modal footer/body,
  including 409 invalid-hierarchy; do not silently swallow. Submit button shows a pending
  state during the mutation.
- **Create & add another:** submits, keeps the modal open, resets Title + Spec but
  preserves the selected type and parents for fast repeated entry.
- **On success (Create):** close the modal; query invalidation refreshes board/list.
- No toast system exists in the app → no toasts (YAGNI); feedback is close + refreshed list.

## Testing (TDD, 80% gate)

- **Modal primitive:** renders children; closes on Esc, overlay click, and Cancel; sets
  initial focus.
- **Form primitives:** render label/error; propagate change events immutably.
- **`useCreateProject` / `useCreateWorkItem`:** POST the correct body; invalidate the
  correct query keys on success; expose error state on failure.
- **`CreateProjectModal`:** submit disabled until Name present; submits `{name, repoUrl}`;
  closes on success.
- **`CreateWorkItemModal`:** tab switching shows the correct adaptive fields; parent
  dropdowns list only valid kinds; per-type submit body is correct; *Create & add another*
  resets title/spec and preserves type/parents.
- **Wiring:** Topbar New opens the right modal; board column `+` seeds status; empty-state
  CTA opens the modal.
- MSW already mocks both POST endpoints — reuse for integration-level tests.

## Out of scope

- Assign Agent and Label at creation (needs backend + possibly a new domain field).
- Editing/deleting via modal (separate change).
- Backend changes of any kind.

## Files (anticipated)

New:
- `src/components/ui/Modal.tsx` (+ test)
- `src/components/ui/FormField.tsx`, `TextInput.tsx`, `Select.tsx`, `Textarea.tsx` (+ tests)
- `src/modules/create/CreateModalProvider.tsx` (+ test)
- `src/modules/create/useCreateModal.ts`
- `src/modules/create/CreateProjectModal.tsx` (+ test)
- `src/modules/create/CreateWorkItemModal.tsx` (+ test)
- `src/lib/api/hooks/useCreateProject.ts` (+ test)
- `src/lib/api/hooks/useCreateWorkItem.ts` (+ test)

Modified:
- `src/app/AppShell.tsx` (provider + Topbar `onNew` → Create Work Item)
- `src/app/Sidebar.tsx` (Create Project `+` affordance)
- `src/modules/board/BoardView.tsx` (column `+` triggers, empty-state CTA)
- `src/modules/board/ListView.tsx` (empty-state CTA, if applicable)
- `src/components/ui/index.ts`, `src/lib/api/hooks/index.ts` (exports)
