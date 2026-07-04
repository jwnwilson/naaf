# Work-item file uploads — design

> Status: approved for planning · 2026-07-04
> Feature: attach files to a work item (epic/feature/task) so agents can read and use
> them during a run.

## Goal

Let a human attach files to any work item and have the agent access those files while it
works the item. Two file classes are in scope: **text/docs** (md, txt, code, CSV, JSON —
read directly as text) and **images** (png, jpg, screenshots, mockups — land on disk for
filesystem/`bash` access and future vision support). PDFs, office docs, and heavy binaries
are out of scope for this round.

The design is **local-first with a clean path to cloud**: a storage abstraction with a
default `LocalStorage` adapter (files under `~/.naaf`) and an `S3Storage` adapter written
now but not the active backend. The on-disk/object key structure is identical for both
backends, so switching to S3 later requires no changes to callers, the worker, or the
agent.

## Key decisions (from brainstorming)

- **File classes:** text/docs + images only.
- **Storage:** a `storage` workspace lib (port + Local/S3 adapters), `LocalStorage`
  default rooted at `~/.naaf`. Bytes-oriented port (not text) so images round-trip.
- **Consistent key structure everywhere:** `work-item/<uuid>/<filename>` — identical for
  local disk and S3.
- **Metadata:** a DB `attachments` table **and** the folder (table is the queryable
  source; bytes live in storage). Table and folder are kept in sync by ordering writes.
- **Agent access:** the attachments root is bind-mounted into the worker container; at
  provision the work item's attachment folder is made available inside the run workspace
  so existing `read_file`/`grep`/`bash` tools reach it. No new agent tools.
- **Scope:** full stack — backend + worker + UI. `S3Storage` shipped as code; MinIO/compose
  service **not** stood up this round.
- **Overwrite:** duplicate filename is an explicit, safe-defaulted overwrite — 409 unless
  `overwrite=true`; the UI warns before overwriting.

## 1. Architecture — `storage` workspace lib

A new **app-agnostic workspace lib**, mirroring `libs/crud_router`. It knows nothing about
work items — just bytes addressed by string keys — so it is reusable later for run
artifacts, memory snapshots, etc.

```
libs/storage/
  pyproject.toml            # name = "storage"; [project.optional-dependencies] s3 = ["boto3"]
  src/storage/
    __init__.py             # exports Storage, LocalStorage, S3Storage, StorageConfig
    ports.py                # Storage ABC
    local.py                # LocalStorage(root)
    s3.py                   # S3Storage(bucket, region) — imports boto3 lazily
    exceptions.py           # StorageError, StorageNotFound
  tests/test_storage.py
```

### Port (bytes-oriented)

```python
class Storage(ABC):
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...          # raises StorageNotFound
    def list(self, prefix: str) -> list[str]: ...        # keys under prefix
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> str: ...           # on-disk path for the mount
```

- `LocalStorage(root)`: writes `root/<key>`, `mkdir -p` parents, path-escape guard on
  `key` (no `..` escaping the root). `local_path` returns the real path.
- `S3Storage(bucket, region)`: `boto3` imported lazily so the default install stays lean.
  `put_bytes`→`put_object`, `get_bytes`→`get_object` (translating `NoSuchKey`→
  `StorageNotFound`), `list`→`list_objects_v2`, `delete`→`delete_object`. `local_path`
  is only meaningful after a sync-down (a deferred cloud concern; documented, not used
  this round).

### Wiring in the server

- **Key convention lives in the server**, not the lib:
  `adapters/storage/keys.py` → `attachment_key(work_item_id, filename) ->
  "work-item/{work_item_id}/{filename}"` and `attachment_prefix(work_item_id)`.
- **Adapter selection lives in the server**: `adapters/storage/factory.py` →
  `build_storage(settings) -> Storage`, choosing `LocalStorage(attachments_root)` or
  `S3Storage(...)` from `naaf_storage_backend`.
- Injected into the API via `deps.get_storage` and into the worker `HandlerContext`.

### Workspace registration (root `pyproject.toml`)

- `[tool.uv.workspace] members` += `libs/storage`
- `[tool.uv.sources]` += `storage = { workspace = true }`
- coverage `source` += `storage`
- `testpaths` += `libs/storage/tests`
- Server `pyproject.toml` dependency: `storage = { workspace = true }`

## 2. Data model — `attachments` table (migration `0011`)

New domain entity + ORM row + repository, owner-scoped like every other owned row.

`Attachment(Entity)` — `domain/attachments/attachment.py`:

| field | notes |
|---|---|
| `id` | uuid hex (from `Entity`) |
| `owner_id` | owner scoping (from `Entity`) |
| `work_item_id` | the owning work item's id |
| `filename` | leaf of the storage key; **unique per work item** |
| `content_type` | from upload, or inferred from extension |
| `size` | byte length |
| `created_at` / `updated_at` | from `Entity`; `updated_at` bumped on overwrite |

- `storage_key` is **derived** (`work-item/{work_item_id}/{filename}`), not stored.
- `AttachmentRow` in `adapters/database/orm.py` (`__tablename__ = "attachments"`), columns
  mirroring the entity; index on `(owner_id, work_item_id)`.
- `AttachmentRepository` in `adapters/database/repositories.py` (subclasses `SqlRepository`);
  registered on the UnitOfWork as `uow.attachments`.
- Migration `0011_attachments`, `down_revision = "0010_run_pr_url"`.

### Sync ordering (table ↔ folder)

- **Upload:** `storage.put_bytes(key, data)` **then** insert/patch the row.
- **Delete:** delete the row **then** `storage.delete(key)`.
- **Overwrite:** `put_bytes` (replaces bytes) **then** patch the existing row's
  `size`/`content_type`/`updated_at` (no new row).

## 3. API — multipart upload / list / download / delete

First `UploadFile` endpoints in the codebase, on the existing `/work-items` router. Every
route **loads the work item first through the owner-scoped repo** (404 if not the owner's),
then operates on its attachment folder. All responses use the standard `Envelope`.

- `POST /work-items/{id}/attachments` — `multipart/form-data`, `overwrite: bool = false`.
  - Validate size against `naaf_max_attachment_bytes` (default 10 MB) → 413.
  - Validate content-type against a **text + image allowlist** → 415.
  - If filename exists and `overwrite` is false → **409 Conflict**.
  - If `overwrite` is true → replace bytes + patch row.
  - Returns `AttachmentOut`.
- `GET /work-items/{id}/attachments` — list rows → `AttachmentOut[]`.
- `GET /work-items/{id}/attachments/{attId}` — `StreamingResponse` of the bytes with the
  stored `content_type`.
- `DELETE /work-items/{id}/attachments/{attId}` — 204/envelope.

New contract model `AttachmentOut` (`id, filename, contentType, size, url, createdAt`,
`url` = the download route). The existing `WorkItemOut.attachments` placeholder
(`contract.py`, hardcoded `[]` in `work_items.py`) is populated from the table.

## 4. Worker mount + agent access

- **Setting** `naaf_attachments_root` (default `~/.naaf`); `LocalStorage` roots there.
- **docker-compose worker** gets the attachments root **bind-mounted** at a fixed container
  path (`~/.naaf` → `/attachments`, with `naaf_attachments_root: /attachments`). Files the
  API writes at `<root>/work-item/<uuid>/…` are visible to the worker at the same key.
- **Agent access at provision** (`handlers._provision`): after the repo clone, the worker
  materializes the work item's attachment folder into a stable path **inside the run
  workspace** — `<clone>/.naaf/attachments/` (symlink or copy from
  `<attachments_root>/work-item/<uuid>/`). This keeps the agent-facing path inside the
  sandboxed clone, so `read_file`/`grep`/`bash` reach the files with the existing
  path-escape guard intact. For S3 later, provision syncs the prefix down to that same
  path — **agent code is unchanged**.
- **Prompt wiring:**
  - `WorkItemBrief` (`domain/agent/context.py`) gains `attachments: list[str]`.
  - `build_stage_context` (`interactors/worker/handlers.py`) loads the attachment
    filenames for the work item.
  - `stage_instruction` (`domain/agent/prompts.py`) appends an **"## Attachments"** block
    listing filenames and the folder path (`.naaf/attachments/`), telling the agent to
    read them as needed. Text files are read via `read_file`; images sit on disk (vision
    consumption is a **future enhancement**, called out explicitly — not wired now).

## 5. UI — Detail-screen attachments

A new **Attachments** section in `src/modules/detail/` (`AttachmentsPanel.tsx`), following
the existing module + hook + MSW conventions.

- File-picker / drag-drop upload; list rows (filename · size · type) with a download link
  and a delete action (confirm dialog).
- **Overwrite guard:** before uploading, the panel checks the current attachment list. On a
  filename collision it shows a **confirm dialog** ("`<name>` already exists — overwrite
  it?"). Only on confirm does it re-POST with `overwrite=true`. No collision → direct
  upload.
- New hooks in `src/lib/api/hooks/`: `useAttachments`, `useUploadAttachment`,
  `useDeleteAttachment` — invalidating the work-item + attachments queries (mirrors
  `useUpdateWorkItem`).
- MSW mocks: an attachments store in `db`, `liveHandlers` for the four endpoints, and a
  seed fixture, so the flow is demoable offline like the other dogfooding features.

## 6. Testing (TDD, 80% gate)

- **Lib (`libs/storage/tests`):** `LocalStorage` round-trip (put/get/list/delete/exists),
  key-escape safety, `StorageNotFound` on missing key; `S3Storage` test skipped when
  `boto3` is absent.
- **Server:** upload/list/download/delete endpoints — owner-scoping, duplicate-filename
  409, `overwrite=true` replace path, size (413) and content-type (415) rejection,
  cross-owner 404; `AttachmentRepository`; `build_stage_context` includes attachments;
  `stage_instruction` renders the "## Attachments" block; migration up/down.
- **UI:** `AttachmentsPanel` render / upload / overwrite-confirm / delete against MSW; hook
  tests.

## Out of scope / deferred

- MinIO/compose S3 service and actually running on S3 (adapter ships as code only).
- S3 prefix sync-down at provision (documented; local uses the bind mount).
- Vision/image understanding by the agent (images land on disk; no base64-into-prompt).
- PDFs, office docs, archives, and large-binary handling.
