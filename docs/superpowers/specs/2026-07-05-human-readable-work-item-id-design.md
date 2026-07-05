# Human-readable work item IDs + parent lineage names

**Date:** 2026-07-05
**Status:** Approved design, ready for implementation plan

## Problem

Work items are identified in the UI by their raw 32-char UUID hex (`item.id`),
shown in the "ID" column of both the board's `KanbanCard` and the `ListRow`. That
value is impossible to say out loud or type, so there is no practical way to refer
to a specific work item — when talking to an agent, in conversation, or from memory.

Separately, the board and list surfaces do not show a work item's place in the
hierarchy. The `KanbanCard`/`ListRow` render `epicId` (a hex string) as a tag, and
the parent **feature** name is not shown at all. A user scanning the board cannot
tell which epic/feature a task belongs to.

## Goals

1. Give every work item a short, stable, human-readable key that can be referred to
   by (e.g. `NAAF-42`), displayed across the board, list, detail, and thread header.
2. Show a work item's parent **epic name** and parent **feature name** on the
   listing and board pages.

## Non-goals (YAGNI — deferred)

- Jump-to / search-by-key (typing `NAAF-42` to open an item, key-based routing).
- Editable project key UI (create/edit form field, live uniqueness validation).
- Per-kind numbering (`E-1`, `F-1`, `T-1`). One sequence per project, shared across
  kinds.
- Surfacing the raw UUID on the board/list cards — it stays reachable via the URL and
  the detail screen; the readable key replaces it on the cards.

## Design decisions (locked)

| Decision | Choice |
|---|---|
| Key format | Per-project sequential, JIRA-style: `{PROJECT_KEY}-{seq}` |
| Numbering scope | One counter per project, shared across epic/feature/task |
| Project prefix | Auto-derived from name, stored immutably on the project |
| Lookup scope | Display-only (no search/jump this cut) |
| Lineage display | Breadcrumb `Epic › Feature`, truncated |

## Architecture

Two new pieces of persisted state; the composed key string is computed, not stored.

### `Project.key` (new, immutable)

- New column `projects.key` (`String(8)`, not null after backfill).
- Derived **once at project creation** from the project name:
  - Take the name's alphanumeric characters, uppercase them, keep the first 4.
  - Fallback to `PROJ` when the name has no alphanumerics.
  - Enforce uniqueness per owner: if the derived key already exists for that owner,
    append the smallest integer suffix that makes it unique (`ACME`, `ACME2`, `ACME3`).
- Immutable: never recomputed on rename, so existing keys stay stable.

### `WorkItem.seq` (new)

- New column `work_items.seq` (`Integer`, not null after backfill).
- A per-project running counter assigned **at create time** as
  `max(seq) + 1 WHERE project_id = <project>`.
- Guarded by `UniqueConstraint(project_id, seq)` — this mirrors the existing
  `RunEventRepository` / `AgentEventRepository` sequence pattern (see
  `adapters/database/repositories.py`). The implementation reuses that exact shape;
  no new mechanism is introduced.

### Computed key

The human-readable key `"NAAF-42"` is computed in the API layer as
`f"{project.key}-{item.seq}"`. It is **not** stored, keeping a single source of truth
(project key + item seq).

## Data flow

### Lineage resolution (already ~90% present)

`_resolve_lineage(item, uow)` in `routes/work_items.py` already walks the parent chain
(≤2 reads) and reads the epic/feature rows to return `(epic_id, feature_id)`. It
discards the titles. Extend it to also return `epic_name` / `feature_name` — no extra
queries.

### Key resolution

The item-read, list, and board routes already load or can load the owning project (the
list and board are project-scoped; the single-item read has `item.project_id`). Load
`project.key` and compose the key alongside the lineage. For the unfiltered
`GET /work-items` list, cache project keys by `project_id` within the request to avoid
an N+1 (a small dict built as projects are first seen).

### API contract (`WorkItemOut`)

Add three fields; existing fields unchanged:

- `key: str` — e.g. `"NAAF-42"`.
- `epicName: str | None`.
- `featureName: str | None`.

`epicId` / `featureId` remain. Request schemas (`WorkItemCreateIn`,
`WorkItemUpdateIn`) are **unchanged**.

## Migration `0015`

1. Add `projects.key` (nullable to start). Backfill: for each project, derive the key
   from its name using the same rule as creation, applying the per-owner collision
   suffix over already-assigned keys. Then enforce not-null.
2. Add `work_items.seq` (nullable to start) and the `UniqueConstraint(project_id, seq)`.
   Backfill: for each project, order its items by `(created_at, id)` and assign
   `1..N`. Then enforce not-null.
3. Downgrade drops the constraint and both columns.

`interactors/cli/seed.py` is updated so seeded projects/items exercise the derivation
and sequence paths (the demo project's items get `1..N`).

## Frontend (display-only)

`projects/ui/src/lib/api/schema.ts` is regenerated from the OpenAPI spec to pick up
`key`, `epicName`, `featureName` on the `WorkItem` schema.

- **`LineageBreadcrumb`** (new shared component): given `epicName` / `featureName`,
  renders `Epic › Feature`, truncated with ellipsis. Renders only the parts that
  exist — a feature shows just its epic; an epic renders nothing. Used by board, list,
  and detail so the three surfaces stay consistent.
- **`KanbanCard`**: replace `item.id` in the top row with `item.key`; replace the
  `epicId` hex `<Tag>` with `LineageBreadcrumb`.
- **`ListRow`**: show `item.key` in the ID column (the `w-[62px]` slot); replace the
  `epicId` `<Tag>` with `LineageBreadcrumb`. The `ID` column header in `ListView`
  stays labelled "ID".
- **Detail screen header** and **inbox thread header**: show `item.key` next to the
  title.

> Note: in the UI's live-API mode, `GET /projects/:id/board` is still MSW-mocked
> (only that one route). `ListView` uses `useProjectWorkItems` → `GET /work-items`,
> which is live. The board `KanbanCard` renders from whichever source feeds it; the
> mock fixtures for the board must also carry `key`/`epicName`/`featureName` so the
> mocked board renders correctly.

## Error handling & edge cases

- **Legacy rows without a key/seq**: eliminated by the migration backfill; every
  project ends with a key and every item with a seq, so the API never composes a
  partial key.
- **Kind with no parent lineage**: an epic has no epic/feature parent → both names are
  `null` → the breadcrumb renders nothing. A feature has only an epic → feature name is
  `null`. This is handled by the "render only parts that exist" rule.
- **Key collisions across owners**: uniqueness is scoped per owner, matching the
  owner-scoping invariant; keys need not be globally unique.
- **Concurrency on `seq`**: single-user local tool; the `UniqueConstraint(project_id,
  seq)` is the backstop, exactly as the existing event-sequence repositories rely on.

## Testing

- **Domain/derivation unit tests**: key derivation (normal name, hyphens/spaces,
  no-alphanumeric fallback, truncation to 4, collision suffixing).
- **Repository test**: `WorkItemRepository.create` assigns monotonically increasing
  per-project `seq`; two projects number independently from 1.
- **API tests**: `WorkItemOut` includes `key` = `{project.key}-{seq}`; `epicName` /
  `featureName` populate correctly for a task (both), a feature (epic only), an epic
  (neither).
- **Migration test**: extend the existing migration test coverage — upgrade backfills
  keys/seqs for pre-existing rows; unique constraint present.
- **Seed test** (if present): seeded project has a key; items have contiguous seqs.
- **Frontend**: `LineageBreadcrumb` renders full chain / epic-only / nothing;
  `KanbanCard` and `ListRow` show `item.key` and the breadcrumb. Update any existing
  card/row snapshot or fixture expectations.

Coverage stays at/above the 80% gate.

## Files touched (map)

Backend:
- `domain/project.py` — add `key`.
- `domain/work_item.py` — add `seq`.
- `domain/` new helper for key derivation (e.g. `domain/project.py` function or a
  small `project_key.py`), pure, unit-tested.
- `adapters/database/orm.py` — `projects.key`, `work_items.seq` + unique constraint.
- `adapters/database/repositories.py` — `WorkItemRepository.create` seq assignment;
  `ProjectRepository.create` key derivation (or derive in the route).
- `adapters/database/migrations/versions/0015_*.py` — new migration.
- `interactors/api/contract.py` — `WorkItemOut` gets `key`, `epicName`, `featureName`.
- `interactors/api/routes/work_items.py` — `_resolve_lineage` returns names;
  `_work_item_out` composes `key`; project-key lookup/cache.
- `interactors/cli/seed.py` — exercise derivation.

Frontend:
- `lib/api/schema.ts` — regenerate.
- `modules/board/LineageBreadcrumb.tsx` — new.
- `modules/board/KanbanCard.tsx`, `modules/board/ListRow.tsx` — use key + breadcrumb.
- Detail screen header + inbox thread header — show key.
- MSW board fixtures — carry the new fields.
