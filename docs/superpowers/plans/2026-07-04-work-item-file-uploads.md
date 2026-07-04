# Work-item File Uploads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human attach text/image files to a work item and have the agent read those files during a run, backed by a swappable storage abstraction (local disk now, S3 later).

**Architecture:** A new app-agnostic `storage` workspace lib (bytes-over-keys port + `LocalStorage`/`S3Storage`). The server owns the `work-item/<uuid>/<filename>` key convention, an `attachments` DB table (metadata) + storage (bytes), multipart upload/list/download/delete endpoints, and — at run provision — materializes a work item's attachments into the cloned workspace so existing agent file tools reach them. A Detail-screen panel drives upload/list/delete with an overwrite-confirm guard.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 + Alembic (SQLite in tests), pydantic v2, pydantic-settings, `uv` workspace; React + Vite + Tailwind + React Query + MSW; pytest + Vitest.

**Reference spec:** `docs/superpowers/specs/2026-07-04-work-item-file-uploads-design.md`

## Global Constraints

- Python ≥ 3.12; package manager `uv`; env prefix `naaf_`.
- Immutability: pydantic entities updated via `model_copy(update={...})`, never mutated.
- API envelope: every response is `{success, data, error}` (+ `meta`); use `crud_router.ok`.
- Owner scoping: every owned row carries `owner_id`; the UnitOfWork stamps it via `required_filters`. Every attachment route loads the work item through the owner-scoped repo first (cross-owner ⇒ `RecordNotFound` ⇒ 404).
- Entity IDs are 32-char UUID hex (`domain.base.new_id`).
- Key convention (identical local & S3): `work-item/<work_item_id>/<filename>`.
- Storage port is **bytes-oriented** (`put_bytes`/`get_bytes`), not text.
- Limits: max upload `naaf_max_attachment_bytes` default `10_485_760` (10 MB) ⇒ 413; content-type allowlist (text + image) ⇒ 415; duplicate filename ⇒ 409 unless `overwrite=true`.
- TDD: write the failing test first; AAA structure; descriptive names. 80% coverage gate (`make coverage`), `make lint` green before PR.
- Commit format: `<type>: <description>`.
- Run backend tests from `projects/server` with `uv run pytest`; lib tests live in `libs/storage/tests`. Run UI tests from `projects/ui` with `pnpm test`.

## File Structure

**New — `storage` lib**
- `libs/storage/pyproject.toml` — workspace package `storage`, optional `s3` extra (`boto3`).
- `libs/storage/src/storage/__init__.py` — public exports.
- `libs/storage/src/storage/exceptions.py` — `StorageError`, `StorageNotFound`.
- `libs/storage/src/storage/ports.py` — `Storage` ABC.
- `libs/storage/src/storage/local.py` — `LocalStorage`.
- `libs/storage/src/storage/s3.py` — `S3Storage` (lazy boto3).
- `libs/storage/tests/test_local_storage.py`, `libs/storage/tests/test_s3_storage.py`.

**New — server**
- `projects/server/src/domain/attachments/__init__.py`
- `projects/server/src/domain/attachments/attachment.py` — `Attachment` entity.
- `projects/server/src/domain/attachments/validation.py` — filename/size/content-type rules.
- `projects/server/src/adapters/storage/__init__.py`
- `projects/server/src/adapters/storage/keys.py` — `attachment_key`, `attachment_prefix`.
- `projects/server/src/adapters/storage/factory.py` — `build_storage(settings)`.
- `projects/server/src/adapters/database/migrations/versions/0011_attachments.py`
- `projects/server/src/interactors/api/routes/attachments.py` — upload/list/download/delete.
- Tests: `projects/server/tests/...` per task.

**Modified — server**
- `projects/server/pyproject.toml` — add `storage` workspace dep + `python-multipart`.
- `pyproject.toml` (root) — workspace `members`, `[tool.uv.sources]`, coverage `source`, `testpaths`.
- `src/adapters/database/orm.py` — `AttachmentRow`.
- `src/adapters/database/repositories.py` — `AttachmentRepository`.
- `src/adapters/database/uow.py` — `uow.attachments`.
- `src/interactors/api/settings.py` — storage settings.
- `src/interactors/api/deps.py` — `get_storage`.
- `src/interactors/api/app.py` — build + attach storage to `app.state`.
- `src/interactors/api/contract.py` — `AttachmentOut`.
- `src/interactors/api/routes/work_items.py` — populate `WorkItemOut.attachments`.
- `src/interactors/api/routes/__init__.py` — register attachments router.
- `src/domain/agent/context.py` — `WorkItemBrief.attachments`.
- `src/domain/agent/prompts.py` — attachments block.
- `src/interactors/worker/handlers.py` — `HandlerContext.storage`, materialize at provision, attachments in `build_stage_context`.
- `src/interactors/worker/subscription_runner.py` — build storage into ctx.
- `docker-compose.yml` — bind-mount attachments root into worker.

**Modified — UI**
- `projects/ui/src/lib/api/client.ts` — `apiUpload` helper.
- `projects/ui/src/lib/api/hooks/useAttachments.ts`, `useUploadAttachment.ts`, `useDeleteAttachment.ts`.
- `projects/ui/src/lib/api/queryKeys.ts` — `attachments` key.
- `projects/ui/src/modules/detail/AttachmentsPanel.tsx` (+ test).
- `projects/ui/src/modules/detail/DetailScreen.tsx` — render panel in the Attachments tab.
- `projects/ui/src/lib/api/mocks/db.ts`, `mocks/handlers.ts`, `mocks/fixtures/*` — attachments store + handlers + seed.

---

### Task 1: `storage` workspace lib — port + LocalStorage

**Files:**
- Create: `libs/storage/pyproject.toml`
- Create: `libs/storage/src/storage/__init__.py`
- Create: `libs/storage/src/storage/exceptions.py`
- Create: `libs/storage/src/storage/ports.py`
- Create: `libs/storage/src/storage/local.py`
- Create: `libs/storage/tests/test_local_storage.py`
- Modify: `pyproject.toml` (root) — workspace registration

**Interfaces:**
- Produces: `storage.Storage` (ABC with `put_bytes(key, data, content_type=None)`, `get_bytes(key) -> bytes`, `list(prefix) -> list[str]`, `delete(key)`, `exists(key) -> bool`, `local_path(key) -> str`), `storage.LocalStorage(root: str)`, `storage.StorageError`, `storage.StorageNotFound`.

- [ ] **Step 1: Write the failing test**

Create `libs/storage/tests/test_local_storage.py`:

```python
import pytest

from storage import LocalStorage, StorageNotFound


def test_put_then_get_round_trips_bytes(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/hello.txt", b"hi there")
    assert store.get_bytes("work-item/abc/hello.txt") == b"hi there"


def test_exists_reflects_presence(tmp_path):
    store = LocalStorage(str(tmp_path))
    assert store.exists("work-item/abc/x.png") is False
    store.put_bytes("work-item/abc/x.png", b"\x89PNG")
    assert store.exists("work-item/abc/x.png") is True


def test_list_returns_keys_under_prefix(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/a.txt", b"a")
    store.put_bytes("work-item/abc/b.txt", b"b")
    store.put_bytes("work-item/other/c.txt", b"c")
    assert sorted(store.list("work-item/abc/")) == ["work-item/abc/a.txt", "work-item/abc/b.txt"]


def test_delete_removes_key(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/a.txt", b"a")
    store.delete("work-item/abc/a.txt")
    assert store.exists("work-item/abc/a.txt") is False


def test_get_missing_raises_storage_not_found(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(StorageNotFound):
        store.get_bytes("work-item/abc/missing.txt")


def test_key_escaping_the_root_is_rejected(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError):
        store.put_bytes("../escape.txt", b"nope")
```

- [ ] **Step 2: Register the workspace package so tests can import it**

Create `libs/storage/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "storage"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7"]

[project.optional-dependencies]
s3 = ["boto3>=1.34"]

[tool.hatch.build.targets.wheel]
packages = ["src/storage"]
```

Edit the root `pyproject.toml`. Add `"libs/storage"` to `[tool.uv.workspace] members`, add `storage = { workspace = true }` to `[tool.uv.sources]`, add `"storage"` to the coverage `source` list, and add `"libs/storage/tests"` to `testpaths`. Example resulting fragments:

```toml
[tool.uv.workspace]
members = ["projects/server", "libs/crud_router", "libs/storage"]

[tool.uv.sources]
naaf-server = { workspace = true }
naaf-crud-router = { workspace = true }
storage = { workspace = true }
```

```toml
testpaths = ["projects/server/tests", "libs/crud_router/tests", "libs/storage/tests"]
```

```toml
source = ["domain", "adapters", "interactors", "crud_router", "storage"]
```

Then create the package files.

`libs/storage/src/storage/exceptions.py`:

```python
class StorageError(Exception):
    """Base error for the storage lib."""


class StorageNotFound(StorageError):
    """Raised when a requested key does not exist."""
```

`libs/storage/src/storage/ports.py`:

```python
from abc import ABC, abstractmethod


class Storage(ABC):
    """A blob store addressed by string keys. Backend-agnostic (local disk / S3)."""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def list(self, prefix: str) -> list[str]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def local_path(self, key: str) -> str: ...
```

`libs/storage/src/storage/local.py`:

```python
from pathlib import Path

from .exceptions import StorageNotFound
from .ports import Storage


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError(f"key escapes storage root: {key!r}")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageNotFound(key)
        return path.read_bytes()

    def list(self, prefix: str) -> list[str]:
        base = self._resolve(prefix)
        if not base.is_dir():
            return []
        return [
            str(p.relative_to(self._root)) for p in sorted(base.rglob("*")) if p.is_file()
        ]

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def local_path(self, key: str) -> str:
        return str(self._resolve(key))
```

`libs/storage/src/storage/__init__.py`:

```python
from .exceptions import StorageError, StorageNotFound
from .local import LocalStorage
from .ports import Storage

__all__ = ["Storage", "LocalStorage", "StorageError", "StorageNotFound"]
```

- [ ] **Step 3: Sync the workspace and run the test to verify it passes**

Run:
```bash
cd /Users/noel/projects/naaf && uv sync
uv run pytest libs/storage/tests/test_local_storage.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add libs/storage pyproject.toml
git commit -m "feat: storage lib with bytes-oriented port and LocalStorage adapter"
```

---

### Task 2: `S3Storage` adapter (lazy boto3)

**Files:**
- Create: `libs/storage/src/storage/s3.py`
- Modify: `libs/storage/src/storage/__init__.py`
- Create: `libs/storage/tests/test_s3_storage.py`

**Interfaces:**
- Consumes: `storage.Storage`, `storage.StorageNotFound` (Task 1).
- Produces: `storage.S3Storage(bucket: str, region: str, prefix: str = "")`.

- [ ] **Step 1: Write the failing test**

Create `libs/storage/tests/test_s3_storage.py`:

```python
import importlib.util

import pytest

boto3_missing = importlib.util.find_spec("boto3") is None
pytestmark = pytest.mark.skipif(boto3_missing, reason="boto3 (s3 extra) not installed")


def test_s3_storage_is_importable_and_constructs():
    from storage import S3Storage

    store = S3Storage(bucket="naaf-test", region="eu-west-1")
    assert store.local_path("work-item/abc/x.txt").endswith("work-item/abc/x.txt")


def test_get_missing_maps_to_storage_not_found(monkeypatch):
    import botocore.exceptions

    from storage import S3Storage, StorageNotFound

    store = S3Storage(bucket="naaf-test", region="eu-west-1")

    class _FakeClient:
        def get_object(self, **_):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )

    monkeypatch.setattr(store, "_client", _FakeClient())
    with pytest.raises(StorageNotFound):
        store.get_bytes("work-item/abc/missing.txt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/noel/projects/naaf && uv run pytest libs/storage/tests/test_s3_storage.py -v`
Expected: FAIL with `ImportError`/`cannot import name 'S3Storage'` (or SKIP if boto3 absent — if skipped, install the extra first: `uv sync --extra s3` from the lib is not wired; instead add boto3 for this test run with `uv pip install boto3` inside the project venv, then re-run).

- [ ] **Step 3: Write minimal implementation**

Create `libs/storage/src/storage/s3.py`:

```python
from .exceptions import StorageError, StorageNotFound
from .ports import Storage


class S3Storage(Storage):
    """S3-backed blob store. boto3 is imported lazily so the base install stays lean.

    `local_path` returns a path under a scratch dir; it is only meaningful after a
    sync-down (a cloud-deployment concern) and is not used by the local default.
    """

    def __init__(self, bucket: str, region: str, prefix: str = "") -> None:
        self._bucket = bucket
        self._region = region
        self._prefix = prefix.rstrip("/")
        self.__client = None

    @property
    def _client(self):
        if self.__client is None:
            import boto3

            self.__client = boto3.client("s3", region_name=self._region)
        return self.__client

    @_client.setter
    def _client(self, value) -> None:
        self.__client = value

    def _full(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=self._full(key), Body=data, **extra)

    def get_bytes(self, key: str) -> bytes:
        import botocore.exceptions

        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=self._full(key))
        except botocore.exceptions.ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise StorageNotFound(key) from err
            raise StorageError(str(err)) from err
        return resp["Body"].read()

    def list(self, prefix: str) -> list[str]:
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._full(prefix))
        keys = [obj["Key"] for obj in resp.get("Contents", [])]
        if self._prefix:
            keys = [k[len(self._prefix) + 1 :] for k in keys]
        return sorted(keys)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._full(key))

    def exists(self, key: str) -> bool:
        import botocore.exceptions

        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full(key))
            return True
        except botocore.exceptions.ClientError:
            return False

    def local_path(self, key: str) -> str:
        return f"/tmp/naaf-s3-cache/{self._full(key)}"
```

Update `libs/storage/src/storage/__init__.py`:

```python
from .exceptions import StorageError, StorageNotFound
from .local import LocalStorage
from .ports import Storage
from .s3 import S3Storage

__all__ = ["Storage", "LocalStorage", "S3Storage", "StorageError", "StorageNotFound"]
```

Note: `__init__` importing `s3` must not import boto3 at module load — it doesn't, because `s3.py` imports boto3 only inside methods.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/noel/projects/naaf
uv run python -c "from storage import S3Storage, LocalStorage; print('ok')"
uv run pytest libs/storage/tests -v
```
Expected: `ok` prints (proves `S3Storage` imports without boto3 installed); LocalStorage tests PASS; S3 tests PASS or SKIP depending on boto3 presence.

- [ ] **Step 5: Commit**

```bash
git add libs/storage
git commit -m "feat: add S3Storage adapter with lazy boto3 import"
```

---

### Task 3: `Attachment` entity, ORM, repository, migration

**Files:**
- Create: `projects/server/src/domain/attachments/__init__.py`
- Create: `projects/server/src/domain/attachments/attachment.py`
- Modify: `projects/server/src/adapters/database/orm.py`
- Modify: `projects/server/src/adapters/database/repositories.py`
- Modify: `projects/server/src/adapters/database/uow.py`
- Create: `projects/server/src/adapters/database/migrations/versions/0011_attachments.py`
- Create: `projects/server/tests/adapters/test_attachment_repository.py`

**Interfaces:**
- Produces: `domain.attachments.attachment.Attachment` (fields `id, owner_id, work_item_id, filename, content_type, size, created_at, updated_at`); `uow.attachments` (an `AttachmentRepository`, owner-scoped, standard CRUD + `read_multi`).

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/adapters/test_attachment_repository.py`:

```python
from domain.attachments.attachment import Attachment


def test_create_and_read_attachment_round_trips(uow):
    with uow.transaction() as u:
        created = u.attachments.create(
            Attachment(
                owner_id="",
                work_item_id="wi123",
                filename="mockup.png",
                content_type="image/png",
                size=42,
            )
        )
    with uow.transaction() as u:
        got = u.attachments.read(created.id)
    assert got.work_item_id == "wi123"
    assert got.filename == "mockup.png"
    assert got.content_type == "image/png"
    assert got.size == 42
    assert got.owner_id == "dev-user"  # stamped by required_filters


def test_list_by_work_item_filters(uow):
    with uow.transaction() as u:
        u.attachments.create(Attachment(owner_id="", work_item_id="wiA", filename="a.txt", content_type="text/plain", size=1))
        u.attachments.create(Attachment(owner_id="", work_item_id="wiB", filename="b.txt", content_type="text/plain", size=1))
    with uow.transaction() as u:
        page = u.attachments.read_multi(filters={"work_item_id": "wiA"})
    assert [a.filename for a in page.results] == ["a.txt"]
```

Note: reuse the existing `uow` fixture (owner-scoped to `dev-user`). If a repo-level `uow` fixture doesn't exist in `tests/adapters/`, check `projects/server/tests/conftest.py` for the shared owner-scoped `SqlUnitOfWork` fixture and use that name.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/test_attachment_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.attachments` / `uow has no attribute 'attachments'`.

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/attachments/__init__.py` (empty).

Create `projects/server/src/domain/attachments/attachment.py`:

```python
from domain.base import Entity


class Attachment(Entity):
    """A file attached to a work item. Bytes live in storage under
    work-item/<work_item_id>/<filename>; this row is the queryable metadata."""

    owner_id: str
    work_item_id: str
    filename: str
    content_type: str
    size: int
```

Add to `projects/server/src/adapters/database/orm.py` (after `WorkItemRow`):

```python
class AttachmentRow(_Timestamped, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_owner_wi", "owner_id", "work_item_id"),
        UniqueConstraint("owner_id", "work_item_id", "filename", name="uq_attachment_name"),
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
```

Add to `projects/server/src/adapters/database/repositories.py` — import `AttachmentRow` in the orm import block and the `Attachment` domain import at top, then:

```python
from domain.attachments.attachment import Attachment
...
class AttachmentRepository(SqlRepository[Attachment]):
    orm_model = AttachmentRow
    dto = Attachment
```

Add to `projects/server/src/adapters/database/uow.py` — import `AttachmentRepository` and add the property:

```python
    @property
    def attachments(self) -> AttachmentRepository:
        return self._repo("attachments", AttachmentRepository)
```

Create the migration `projects/server/src/adapters/database/migrations/versions/0011_attachments.py`:

```python
"""attachments table

Revision ID: 0011_attachments
Revises: 0010_run_pr_url
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_attachments"
down_revision = "0010_run_pr_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("work_item_id", sa.String(length=32), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
    )
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"])
    op.create_index("ix_attachments_work_item_id", "attachments", ["work_item_id"])
    op.create_index("ix_attachments_owner_wi", "attachments", ["owner_id", "work_item_id"])
    op.create_unique_constraint(
        "uq_attachment_name", "attachments", ["owner_id", "work_item_id", "filename"]
    )


def downgrade() -> None:
    op.drop_table("attachments")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/test_attachment_repository.py -v`
Expected: both tests PASS. (Tests build tables from ORM metadata; the migration is exercised in Task 5's app-level tests / real DB.)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/attachments projects/server/src/adapters/database projects/server/tests/adapters/test_attachment_repository.py
git commit -m "feat: Attachment entity, ORM row, repository, and migration 0011"
```

---

### Task 4: Storage settings, keys, factory, validation, `get_storage`

**Files:**
- Modify: `projects/server/src/interactors/api/settings.py`
- Create: `projects/server/src/adapters/storage/__init__.py`
- Create: `projects/server/src/adapters/storage/keys.py`
- Create: `projects/server/src/adapters/storage/factory.py`
- Create: `projects/server/src/domain/attachments/validation.py`
- Modify: `projects/server/src/interactors/api/deps.py`
- Modify: `projects/server/src/interactors/api/app.py`
- Modify: `projects/server/pyproject.toml`
- Create: `projects/server/tests/adapters/test_storage_factory.py`
- Create: `projects/server/tests/domain/test_attachment_validation.py`

**Interfaces:**
- Consumes: `storage.Storage`, `storage.LocalStorage`, `storage.S3Storage` (Tasks 1–2); `Settings` (existing).
- Produces:
  - `adapters.storage.keys.attachment_key(work_item_id, filename) -> str`, `attachment_prefix(work_item_id) -> str`.
  - `adapters.storage.factory.build_storage(settings) -> Storage`.
  - `domain.attachments.validation.ALLOWED_CONTENT_TYPES: set[str]`, `validate_filename(name) -> str`, `is_allowed_content_type(ct) -> bool`.
  - `interactors.api.deps.get_storage(request) -> Storage`.
  - Settings fields: `attachments_root` (default `~/.naaf`), `storage_backend` (`"local"`), `s3_bucket`, `s3_region`, `max_attachment_bytes` (default `10_485_760`).

- [ ] **Step 1: Write the failing tests**

Create `projects/server/tests/domain/test_attachment_validation.py`:

```python
import pytest

from domain.attachments.validation import (
    is_allowed_content_type,
    validate_filename,
)


def test_allows_text_and_image_types():
    assert is_allowed_content_type("text/markdown") is True
    assert is_allowed_content_type("image/png") is True


def test_rejects_disallowed_types():
    assert is_allowed_content_type("application/x-msdownload") is False


def test_validate_filename_returns_clean_leaf():
    assert validate_filename("mockup.png") == "mockup.png"


@pytest.mark.parametrize("bad", ["../escape.txt", "a/b.txt", "", "  ", "/etc/passwd"])
def test_validate_filename_rejects_paths_and_empty(bad):
    with pytest.raises(ValueError):
        validate_filename(bad)
```

Create `projects/server/tests/adapters/test_storage_factory.py`:

```python
from adapters.storage.factory import build_storage
from adapters.storage.keys import attachment_key, attachment_prefix
from interactors.api.settings import Settings
from storage import LocalStorage


def test_key_convention():
    assert attachment_key("wi123", "a.png") == "work-item/wi123/a.png"
    assert attachment_prefix("wi123") == "work-item/wi123/"


def test_build_storage_defaults_to_local(tmp_path):
    settings = Settings(attachments_root=str(tmp_path))
    store = build_storage(settings)
    assert isinstance(store, LocalStorage)
    store.put_bytes(attachment_key("wi1", "x.txt"), b"y")
    assert store.get_bytes("work-item/wi1/x.txt") == b"y"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/server && uv run pytest tests/domain/test_attachment_validation.py tests/adapters/test_storage_factory.py -v`
Expected: FAIL — modules `domain.attachments.validation` / `adapters.storage.*` do not exist.

- [ ] **Step 3: Write minimal implementation**

Add to `projects/server/src/interactors/api/settings.py` (new fields, keep existing):

```python
    workspace_root: str = "/tmp/naaf-workspaces"
    attachments_root: str = "~/.naaf"
    storage_backend: str = "local"          # "local" | "s3"
    s3_bucket: str = ""
    s3_region: str = ""
    max_attachment_bytes: int = 10_485_760  # 10 MB
```

Create `projects/server/src/adapters/storage/__init__.py` (empty).

Create `projects/server/src/adapters/storage/keys.py`:

```python
def attachment_key(work_item_id: str, filename: str) -> str:
    return f"work-item/{work_item_id}/{filename}"


def attachment_prefix(work_item_id: str) -> str:
    return f"work-item/{work_item_id}/"
```

Create `projects/server/src/adapters/storage/factory.py`:

```python
import os

from interactors.api.settings import Settings
from storage import LocalStorage, S3Storage, Storage


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(bucket=settings.s3_bucket, region=settings.s3_region)
    root = os.path.expanduser(settings.attachments_root)
    return LocalStorage(root)
```

Create `projects/server/src/domain/attachments/validation.py`:

```python
ALLOWED_CONTENT_TYPES: set[str] = {
    # text / docs
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "text/xml",
    # images
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def is_allowed_content_type(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() in ALLOWED_CONTENT_TYPES


def validate_filename(name: str) -> str:
    """Return a safe single-segment filename or raise ValueError."""
    cleaned = (name or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or cleaned in (".", ".."):
        raise ValueError(f"invalid filename: {name!r}")
    return cleaned
```

Add to `projects/server/src/interactors/api/deps.py`:

```python
from storage import Storage
...
def get_storage(request: Request) -> Storage:
    return request.app.state.storage
```

Modify `projects/server/src/interactors/api/app.py` — build storage and attach to state:

```python
from adapters.storage.factory import build_storage
...
    app = FastAPI(title="NAAF Control Plane")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.storage = build_storage(settings)
```

Modify `projects/server/pyproject.toml` — add to `dependencies`: `"storage"` and `"python-multipart>=0.0.9"`; add under `[tool.uv.sources]`: `storage = { workspace = true }`.

- [ ] **Step 4: Run tests + sync**

Run:
```bash
cd /Users/noel/projects/naaf && uv sync
cd projects/server && uv run pytest tests/domain/test_attachment_validation.py tests/adapters/test_storage_factory.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/noel/projects/naaf
git add projects/server/src/interactors/api/settings.py projects/server/src/adapters/storage projects/server/src/domain/attachments/validation.py projects/server/src/interactors/api/deps.py projects/server/src/interactors/api/app.py projects/server/pyproject.toml projects/server/tests
git commit -m "feat: storage settings, key convention, factory, validation, get_storage dep"
```

---

### Task 5: Attachment API — upload / list / download / delete

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py`
- Create: `projects/server/src/interactors/api/routes/attachments.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Modify: `projects/server/src/interactors/api/routes/work_items.py`
- Create: `projects/server/tests/interactors/api/test_attachments_api.py`

**Interfaces:**
- Consumes: `uow.attachments` + `uow.work_items` (Task 3), `get_storage` (Task 4), `attachment_key`/`attachment_prefix` (Task 4), validation helpers (Task 4).
- Produces: `AttachmentOut` contract model; routes:
  - `POST /work-items/{id}/attachments` (multipart `file`, form `overwrite: bool=false`) → `Envelope[AttachmentOut]`
  - `GET /work-items/{id}/attachments` → `Envelope[list[AttachmentOut]]`
  - `GET /work-items/{id}/attachments/{attId}` → `StreamingResponse`
  - `DELETE /work-items/{id}/attachments/{attId}` → `Envelope[dict]`

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/interactors/api/test_attachments_api.py`:

```python
import io


def _upload(client, wi_id, name="notes.md", data=b"# hi", ct="text/markdown", overwrite=False):
    return client.post(
        f"/work-items/{wi_id}/attachments",
        files={"file": (name, io.BytesIO(data), ct)},
        data={"overwrite": str(overwrite).lower()},
    )


def test_upload_then_list_and_download(client, seeded_work_item_id):
    up = _upload(client, seeded_work_item_id)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["success"] is True
    att = body["data"]
    assert att["filename"] == "notes.md"
    assert att["contentType"] == "text/markdown"
    assert att["size"] == 4

    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert [a["filename"] for a in listed] == ["notes.md"]

    dl = client.get(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.content == b"# hi"


def test_duplicate_filename_conflicts_without_overwrite(client, seeded_work_item_id):
    _upload(client, seeded_work_item_id)
    dup = _upload(client, seeded_work_item_id)
    assert dup.status_code == 409


def test_overwrite_replaces_bytes_and_keeps_single_row(client, seeded_work_item_id):
    _upload(client, seeded_work_item_id, data=b"one")
    up2 = _upload(client, seeded_work_item_id, data=b"two-longer", overwrite=True)
    assert up2.status_code == 200
    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert len(listed) == 1
    assert listed[0]["size"] == len(b"two-longer")


def test_rejects_disallowed_content_type(client, seeded_work_item_id):
    r = _upload(client, seeded_work_item_id, name="a.exe", ct="application/x-msdownload")
    assert r.status_code == 415


def test_rejects_oversize_upload(client, seeded_work_item_id, monkeypatch):
    from interactors.api import routes  # noqa: F401
    big = b"x" * (10_485_760 + 1)
    r = _upload(client, seeded_work_item_id, name="big.txt", data=big, ct="text/plain")
    assert r.status_code == 413


def test_delete_removes_attachment(client, seeded_work_item_id):
    att = _upload(client, seeded_work_item_id).json()["data"]
    d = client.delete(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert d.status_code == 200
    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert listed == []


def test_upload_to_other_owners_item_is_404(client_other_owner, seeded_work_item_id):
    r = _upload(client_other_owner, seeded_work_item_id)
    assert r.status_code == 404
```

Note: reuse the existing API test fixtures. Check `projects/server/tests/interactors/api/conftest.py` for the `client` (TestClient with a temp DB + dev auth) and work-item-seeding fixtures; if `seeded_work_item_id` / `client_other_owner` don't exist, add them to that conftest following the existing project/work-item seeding pattern (create a project + a task work item, return its id; `client_other_owner` overrides `get_owner_id` to a different owner). The app's storage must point at a temp dir — set `naaf_attachments_root` to a tmp path in the test app factory fixture (or override `app.state.storage`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_attachments_api.py -v`
Expected: FAIL — routes/`AttachmentOut` not present (404s / import errors).

- [ ] **Step 3: Write minimal implementation**

Add `AttachmentOut` to `projects/server/src/interactors/api/contract.py`:

```python
class AttachmentOut(BaseModel):
    id: str
    filename: str
    contentType: str
    size: int
    url: str
    createdAt: str
```

Create `projects/server/src/interactors/api/routes/attachments.py`:

```python
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from adapters.storage.keys import attachment_key, attachment_prefix
from crud_router import Envelope, ok
from domain.attachments.attachment import Attachment
from domain.attachments.validation import is_allowed_content_type, validate_filename
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse
from storage import Storage, StorageNotFound

from interactors.api.contract import AttachmentOut, iso
from interactors.api.deps import get_storage, get_uow

router = APIRouter(prefix="/work-items/{work_item_id}/attachments", tags=["attachments"])


def _out(att: Attachment, work_item_id: str) -> AttachmentOut:
    return AttachmentOut(
        id=att.id,
        filename=att.filename,
        contentType=att.content_type,
        size=att.size,
        url=f"/work-items/{work_item_id}/attachments/{att.id}",
        createdAt=iso(att.created_at),
    )


def _require_item(uow: SqlUnitOfWork, work_item_id: str) -> None:
    uow.work_items.read(work_item_id)  # RecordNotFound -> 404 via exception handler


def _find_by_name(uow: SqlUnitOfWork, work_item_id: str, filename: str) -> Attachment | None:
    page = uow.work_items and uow.attachments.read_multi(
        filters={"work_item_id": work_item_id, "filename": filename}
    )
    return page.results[0] if page.results else None


@router.post("", response_model=Envelope[AttachmentOut])
async def upload_attachment(
    work_item_id: UUID,
    file: UploadFile = File(...),  # noqa: B008
    overwrite: bool = Form(False),  # noqa: B008
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)

    filename = validate_filename(file.filename or "")
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip()
    if not is_allowed_content_type(content_type):
        raise HTTPException(status_code=415, detail=f"unsupported file type: {content_type}")

    data = await file.read()
    if len(data) > uow_max_bytes(uow):
        raise HTTPException(status_code=413, detail="file too large")

    existing = _find_by_name(uow, wid, filename)
    if existing and not overwrite:
        raise HTTPException(status_code=409, detail=f"{filename} already exists")

    storage.put_bytes(attachment_key(wid, filename), data, content_type)
    if existing:
        att = uow.attachments.update(
            existing.id,
            existing.model_copy(update={"content_type": content_type, "size": len(data)}),
        )
    else:
        att = uow.attachments.create(
            Attachment(
                owner_id="", work_item_id=wid, filename=filename,
                content_type=content_type, size=len(data),
            )
        )
    return ok(_out(att, wid))


@router.get("", response_model=Envelope[list[AttachmentOut]])
def list_attachments(
    work_item_id: UUID, uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    page = uow.attachments.read_multi(
        filters={"work_item_id": wid}, order_by="created_at"
    )
    return ok([_out(a, wid) for a in page.results])


@router.get("/{attachment_id}")
def download_attachment(
    work_item_id: UUID,
    attachment_id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    att = uow.attachments.read(attachment_id.hex)
    try:
        data = storage.get_bytes(attachment_key(wid, att.filename))
    except StorageNotFound as err:
        raise HTTPException(status_code=404, detail="file bytes missing") from err
    return StreamingResponse(
        iter([data]),
        media_type=att.content_type,
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'},
    )


@router.delete("/{attachment_id}", response_model=Envelope[dict])
def delete_attachment(
    work_item_id: UUID,
    attachment_id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    att = uow.attachments.read(attachment_id.hex)
    uow.attachments.delete(att.id)
    storage.delete(attachment_key(wid, att.filename))
    return ok({"deleted": att.id})
```

Replace the `uow_max_bytes(uow)` helper reference above with the settings value — the cleanest wiring is to read it off the app settings via a dependency. Add this small dep to `interactors/api/deps.py`:

```python
def get_max_attachment_bytes(request: Request) -> int:
    return request.app.state.settings.max_attachment_bytes
```

Then in `attachments.py` replace the `overwrite`/size handling: add `max_bytes: int = Depends(get_max_attachment_bytes)` to `upload_attachment`'s signature and use `if len(data) > max_bytes:`. Remove the `uow_max_bytes` placeholder call and the `_find_by_name` `uow.work_items and` guard (use the direct `read_multi`):

```python
def _find_by_name(uow: SqlUnitOfWork, work_item_id: str, filename: str) -> Attachment | None:
    page = uow.attachments.read_multi(filters={"work_item_id": work_item_id, "filename": filename})
    return page.results[0] if page.results else None
```

Register the router in `projects/server/src/interactors/api/routes/__init__.py`:

```python
from interactors.api.routes.attachments import router as attachments_router
...
    app.include_router(attachments_router)
```

Populate `WorkItemOut.attachments` in `projects/server/src/interactors/api/routes/work_items.py` — change `_work_item_out` to accept the attachment list and map it. Simplest: in `read_work_item` (and any single-item builder), after reading the item, fetch attachments and pass their `AttachmentOut` dicts. Update `_work_item_out` signature:

```python
def _work_item_out(
    item: WorkItem, epic_id: str | None, feature_id: str | None,
    attachments: list | None = None,
) -> WorkItemOut:
    return WorkItemOut(
        ...
        attachments=attachments or [],
        ...
    )
```

And in `read_work_item`:

```python
from adapters.storage.keys import attachment_key  # not needed; use route url form
from interactors.api.contract import AttachmentOut
...
@router.get("/{id}", response_model=Envelope[WorkItemOut])
def read_work_item(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    item = uow.work_items.read(id.hex)
    atts = uow.attachments.read_multi(filters={"work_item_id": item.id}, order_by="created_at").results
    att_out = [
        AttachmentOut(
            id=a.id, filename=a.filename, contentType=a.content_type, size=a.size,
            url=f"/work-items/{item.id}/attachments/{a.id}", createdAt=iso(a.created_at),
        ).model_dump()
        for a in atts
    ]
    return ok(_work_item_out(item, *_resolve_lineage(item, uow), attachments=att_out))
```

Leave the list-endpoint `_work_item_out` callers passing no attachments (defaults to `[]`) to avoid N+1 on the board/list.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_attachments_api.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Run the full backend suite + lint**

Run:
```bash
cd projects/server && uv run pytest -q
cd /Users/noel/projects/naaf && make lint
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api projects/server/tests/interactors/api/test_attachments_api.py
git commit -m "feat: attachment upload/list/download/delete API + populate WorkItemOut.attachments"
```

---

### Task 6: Agent access — materialize at provision + prompt wiring + worker mount

**Files:**
- Modify: `projects/server/src/domain/agent/context.py`
- Modify: `projects/server/src/domain/agent/prompts.py`
- Modify: `projects/server/src/interactors/worker/handlers.py`
- Modify: `projects/server/src/interactors/worker/subscription_runner.py`
- Modify: `docker-compose.yml`
- Create: `projects/server/tests/domain/test_attachments_prompt.py`
- Create: `projects/server/tests/interactors/worker/test_provision_attachments.py`

**Interfaces:**
- Consumes: `Storage` (Task 1), `attachment_prefix` (Task 4), `HandlerContext` (existing).
- Produces: `WorkItemBrief.attachments: list[str]`; `HandlerContext.storage`; a `materialize_attachments(storage, work_item_id, workspace_path)` helper that writes `<workspace>/.naaf/attachments/<filename>` for each stored key.

- [ ] **Step 1: Write the failing tests**

Create `projects/server/tests/domain/test_attachments_prompt.py`:

```python
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.prompts import stage_instruction
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def _ctx(attachments):
    return StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/x",
        work_item=WorkItemBrief(title="T", body="B", attachments=attachments),
        agent=AgentDefinition(owner_id="o", team_id="", role=AgentRole.BACKEND),
    )


def test_instruction_lists_attachments_when_present():
    text = stage_instruction(_ctx(["mockup.png", "notes.md"]))
    assert "## Attachments" in text
    assert ".naaf/attachments/" in text
    assert "mockup.png" in text and "notes.md" in text


def test_instruction_omits_section_when_no_attachments():
    text = stage_instruction(_ctx([]))
    assert "## Attachments" not in text
```

Create `projects/server/tests/interactors/worker/test_provision_attachments.py`:

```python
from pathlib import Path

from adapters.storage.keys import attachment_key
from interactors.worker.handlers import materialize_attachments
from storage import LocalStorage


def test_materialize_writes_attachments_into_workspace(tmp_path):
    root = tmp_path / "store"
    store = LocalStorage(str(root))
    store.put_bytes(attachment_key("wi1", "a.txt"), b"alpha")
    store.put_bytes(attachment_key("wi1", "b.png"), b"\x89PNG")

    workspace = tmp_path / "clone"
    workspace.mkdir()

    names = materialize_attachments(store, "wi1", str(workspace))

    dest = workspace / ".naaf" / "attachments"
    assert (dest / "a.txt").read_bytes() == b"alpha"
    assert (dest / "b.png").read_bytes() == b"\x89PNG"
    assert sorted(names) == ["a.txt", "b.png"]


def test_materialize_no_attachments_returns_empty(tmp_path):
    store = LocalStorage(str(tmp_path / "store"))
    workspace = tmp_path / "clone"
    workspace.mkdir()
    assert materialize_attachments(store, "wiX", str(workspace)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/server && uv run pytest tests/domain/test_attachments_prompt.py tests/interactors/worker/test_provision_attachments.py -v`
Expected: FAIL — `WorkItemBrief` has no `attachments`; `materialize_attachments` undefined.

- [ ] **Step 3: Write minimal implementation**

Add `attachments` to `projects/server/src/domain/agent/context.py`:

```python
class WorkItemBrief(BaseModel):
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
```

Update `stage_instruction` in `projects/server/src/domain/agent/prompts.py`:

```python
def stage_instruction(ctx: StageContext) -> str:
    wi = ctx.work_item
    criteria = "\n".join(f"- {c}" for c in wi.acceptance_criteria) or "- (none given)"
    attachments_block = ""
    if wi.attachments:
        files = "\n".join(f"- {name}" for name in wi.attachments)
        attachments_block = (
            "\n\n## Attachments\n"
            "The following files are available in `.naaf/attachments/` in your workspace. "
            "Read the ones relevant to the ticket:\n"
            f"{files}"
        )
    return (
        f"# Ticket: {wi.title}\n\n{wi.body}\n\n"
        f"## Acceptance criteria\n{criteria}"
        f"{attachments_block}\n\n"
        f"## Your task ({ctx.stage.value})\n{_STAGE_INSTRUCTIONS[ctx.stage]}"
    )
```

In `projects/server/src/interactors/worker/handlers.py`:

Add import at top:
```python
from pathlib import Path

from adapters.storage.keys import attachment_prefix
from storage import Storage
```

Add `storage` to `HandlerContext`:
```python
    storage: Storage | None = None  # blob store for work-item attachments
```

Add the helper (module-level, near `_provision`):
```python
def materialize_attachments(storage: "Storage", work_item_id: str, workspace_path: str) -> list[str]:
    """Copy a work item's attachments from storage into <workspace>/.naaf/attachments/.
    Returns the filenames written. Backend-agnostic: works for local disk and S3."""
    dest = Path(workspace_path) / ".naaf" / "attachments"
    names: list[str] = []
    for key in storage.list(attachment_prefix(work_item_id)):
        filename = key.rsplit("/", 1)[-1]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / filename).write_bytes(storage.get_bytes(key))
        names.append(filename)
    return names
```

Call it in `_provision` after a successful clone — replace the success `return` block:
```python
    if ctx.storage is not None:
        try:
            materialize_attachments(ctx.storage, run.work_item_id, path)
        except Exception as exc:  # attachment sync must not crash provision
            emit(ctx, run, EventType.LOG, stage=Stage.PROVISION, role="lead",
                 payload={"message": f"attachment sync skipped: {exc}"})
    return StageOutcome(
        events=[
            AgentEvent(message=f"cloned {repo}"),
            AgentEvent(message=f"branch agent/{run.id} at {path}"),
        ],
        result=StageResult(passed=True, summary=f"provisioned {path}"),
    )
```

Populate attachments in `build_stage_context` — inside the `try` after building `brief`, list from storage:
```python
        names = []
        if ctx.storage is not None:
            names = [
                k.rsplit("/", 1)[-1]
                for k in ctx.storage.list(attachment_prefix(run.work_item_id))
            ]
        brief = WorkItemBrief(
            title=getattr(wi, "title", ""),
            body=getattr(wi, "body", ""),
            acceptance_criteria=[
                ac.text for ac in (getattr(wi, "acceptance_criteria", None) or [])
            ],
            attachments=names,
        )
```

Wire storage into the worker ctx in `projects/server/src/interactors/worker/subscription_runner.py` — build once near `_s = _Settings()` and pass into `HandlerContext`:
```python
    from adapters.storage.factory import build_storage
    _storage = build_storage(_s)
    ...
        return HandlerContext(
            ...
            workspace_root=_s.workspace_root,
            role_aliases=_s.role_model_aliases,
            storage=_storage,
            chat_responder=chat_responder,
            lead_orchestrator=lead_orchestrator,
        )
```

Bind-mount the attachments root into the worker in `docker-compose.yml` (under the `worker` service):
```yaml
    environment:
      ...
      naaf_workspace_root: /workspaces
      naaf_attachments_root: /attachments
      ...
    volumes:
      - naaf_workspaces:/workspaces
      - ${naaf_attachments_host:-~/.naaf}:/attachments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/domain/test_attachments_prompt.py tests/interactors/worker/test_provision_attachments.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full backend suite + lint**

Run:
```bash
cd projects/server && uv run pytest -q
cd /Users/noel/projects/naaf && make lint
```
Expected: green (fix any `HandlerContext` construction sites in existing tests that now need no change — `storage` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/domain/agent projects/server/src/interactors/worker docker-compose.yml projects/server/tests/domain/test_attachments_prompt.py projects/server/tests/interactors/worker/test_provision_attachments.py
git commit -m "feat: materialize work-item attachments into agent workspace + prompt wiring"
```

---

### Task 7: UI — upload client helper + hooks

**Files:**
- Modify: `projects/ui/src/lib/api/client.ts`
- Modify: `projects/ui/src/lib/api/queryKeys.ts`
- Create: `projects/ui/src/lib/api/hooks/useAttachments.ts`
- Create: `projects/ui/src/lib/api/hooks/useUploadAttachment.ts`
- Create: `projects/ui/src/lib/api/hooks/useDeleteAttachment.ts`
- Create: `projects/ui/src/lib/api/hooks/useAttachments.test.tsx`

**Interfaces:**
- Consumes: `apiFetch`/`request` (existing), MSW handlers (Task 8 — but hook tests can register a local MSW handler or rely on Task 8 order; implement Task 8 first if running strictly TDD against mocks, or use `server.use(...)` inline).
- Produces:
  - `apiUpload<T>(path, formData) -> Promise<T>` (POST multipart, no JSON content-type).
  - `Attachment` type `{ id: string; filename: string; contentType: string; size: number; url: string; createdAt: string }`.
  - `useAttachments(workItemId)`, `useUploadAttachment(workItemId)`, `useDeleteAttachment(workItemId)`.
  - `queryKeys.attachments(workItemId)`.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/lib/api/hooks/useAttachments.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { renderHook, waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { withQueryClient } from "../../../test/withQueryClient";
import { useAttachments } from "./useAttachments";

describe("useAttachments", () => {
  it("lists attachments for a work item", async () => {
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({
          success: true,
          data: [
            { id: "a1", filename: "notes.md", contentType: "text/markdown", size: 4, url: "/x", createdAt: "2026-07-04T00:00:00Z" },
          ],
          error: null,
        }),
      ),
    );
    const { result } = renderHook(() => useAttachments("wi1"), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.data?.[0].filename).toBe("notes.md");
  });
});
```

Note: use the project's existing React Query test wrapper. If `withQueryClient` doesn't exist at that path, find the wrapper used by `useUpdateWorkItem.test.tsx` and reuse it verbatim.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- useAttachments`
Expected: FAIL — `useAttachments` module not found.

- [ ] **Step 3: Write minimal implementation**

Add `apiUpload` to `projects/ui/src/lib/api/client.ts` (after `apiPost`):

```ts
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  // No content-type header: the browser sets the multipart boundary itself.
  return apiFetch<T>(path, { method: "POST", body: form, headers: {} });
}
```

Because `request` spreads a default `content-type: application/json`, override it: change the `apiUpload` to strip it. Update `request`'s header build to let an explicit `content-type: undefined` remove it — simplest is a dedicated path in `apiUpload`:

```ts
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  const raw = await res.text().catch(() => "");
  const body = JSON.parse(raw) as { success: boolean; data: T; error: string | null };
  if (!res.ok || !body.success) {
    throw new ApiError(body.error ?? `upload failed (${res.status})`, res.status);
  }
  return body.data;
}
```

Add to `projects/ui/src/lib/api/queryKeys.ts`:

```ts
  attachments: (workItemId: string) => ["attachments", workItemId] as const,
```

Create `projects/ui/src/lib/api/hooks/useAttachments.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export type Attachment = {
  id: string;
  filename: string;
  contentType: string;
  size: number;
  url: string;
  createdAt: string;
};

export function useAttachments(workItemId: string) {
  return useQuery({
    queryKey: queryKeys.attachments(workItemId),
    queryFn: () => apiFetch<Attachment[]>(`/work-items/${workItemId}/attachments`),
    enabled: Boolean(workItemId),
  });
}
```

Create `projects/ui/src/lib/api/hooks/useUploadAttachment.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiUpload } from "../client";
import { queryKeys } from "../queryKeys";
import type { Attachment } from "./useAttachments";

export function useUploadAttachment(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, overwrite }: { file: File; overwrite: boolean }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("overwrite", String(overwrite));
      return apiUpload<Attachment>(`/work-items/${workItemId}/attachments`, form);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.attachments(workItemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(workItemId) });
    },
  });
}
```

Create `projects/ui/src/lib/api/hooks/useDeleteAttachment.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export function useDeleteAttachment(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      apiFetch<{ deleted: string }>(
        `/work-items/${workItemId}/attachments/${attachmentId}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.attachments(workItemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(workItemId) });
    },
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test -- useAttachments`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api
git commit -m "feat: UI attachment hooks + multipart upload client helper"
```

---

### Task 8: UI — AttachmentsPanel + Detail wiring + MSW mocks

**Files:**
- Create: `projects/ui/src/modules/detail/AttachmentsPanel.tsx`
- Create: `projects/ui/src/modules/detail/AttachmentsPanel.test.tsx`
- Modify: `projects/ui/src/modules/detail/DetailScreen.tsx`
- Modify: `projects/ui/src/lib/api/mocks/db.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`
- Modify: `projects/ui/src/lib/api/mocks/fixtures/*` (seed attachments — follow existing fixture file layout)

**Interfaces:**
- Consumes: `useAttachments`, `useUploadAttachment`, `useDeleteAttachment` (Task 7).
- Produces: `AttachmentsPanel({ workItemId }: { workItemId: string })`; MSW `liveHandlers` for the four attachment endpoints; a `db` attachments store (`listAttachments`, `addAttachment`, `deleteAttachment`).

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/modules/detail/AttachmentsPanel.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../lib/api/mocks/server";
import { withQueryClient } from "../../test/withQueryClient";
import { AttachmentsPanel } from "./AttachmentsPanel";

const att = (filename: string) => ({
  id: `id-${filename}`, filename, contentType: "text/markdown", size: 3,
  url: `/work-items/wi1/attachments/id-${filename}`, createdAt: "2026-07-04T00:00:00Z",
});

describe("AttachmentsPanel", () => {
  it("renders the attachment list", async () => {
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({ success: true, data: [att("notes.md")], error: null }),
      ),
    );
    render(<AttachmentsPanel workItemId="wi1" />, { wrapper: withQueryClient() });
    await waitFor(() => expect(screen.getByText("notes.md")).toBeInTheDocument());
  });

  it("warns before overwriting an existing file", async () => {
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({ success: true, data: [att("notes.md")], error: null }),
      ),
    );
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AttachmentsPanel workItemId="wi1" />, { wrapper: withQueryClient() });
    await waitFor(() => expect(screen.getByText("notes.md")).toBeInTheDocument());

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["new"], "notes.md", { type: "text/markdown" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringContaining("notes.md"),
    ));
    confirmSpy.mockRestore();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- AttachmentsPanel`
Expected: FAIL — `AttachmentsPanel` not found.

- [ ] **Step 3: Write minimal implementation**

Create `projects/ui/src/modules/detail/AttachmentsPanel.tsx`:

```tsx
import { useRef } from "react";
import { useAttachments } from "../../lib/api/hooks/useAttachments";
import { useUploadAttachment } from "../../lib/api/hooks/useUploadAttachment";
import { useDeleteAttachment } from "../../lib/api/hooks/useDeleteAttachment";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentsPanel({ workItemId }: { workItemId: string }) {
  const { data: attachments = [], isLoading } = useAttachments(workItemId);
  const upload = useUploadAttachment(workItemId);
  const remove = useDeleteAttachment(workItemId);
  const inputRef = useRef<HTMLInputElement>(null);

  const onPick = (file: File | undefined) => {
    if (!file) return;
    const exists = attachments.some((a) => a.filename === file.name);
    if (exists && !window.confirm(`${file.name} already exists — overwrite it?`)) return;
    upload.mutate({ file, overwrite: exists });
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] text-[#8b8f9a]">Attachments</span>
        <label className="cursor-pointer font-mono text-[11px] text-[#bab7f6]">
          + Upload
          <input
            ref={inputRef}
            data-testid="attachment-input"
            type="file"
            className="hidden"
            onChange={(e) => onPick(e.target.files?.[0])}
          />
        </label>
      </div>

      {isLoading && <span className="font-mono text-[11px] text-[#42454e]">Loading…</span>}
      {!isLoading && attachments.length === 0 && (
        <span className="font-mono text-[11px] text-[#42454e]">No attachments</span>
      )}

      <ul className="flex flex-col gap-1">
        {attachments.map((a) => (
          <li key={a.id} className="flex items-center justify-between rounded px-2 py-1 hover:bg-white/5">
            <a href={`/api${a.url}`} target="_blank" rel="noreferrer"
               className="font-mono text-[11.5px] text-[#d6d3f0]">{a.filename}</a>
            <span className="flex items-center gap-3">
              <span className="font-mono text-[10px] text-[#42454e]">{formatSize(a.size)}</span>
              <button type="button" onClick={() => remove.mutate(a.id)}
                      className="font-mono text-[10px] text-[#e06c75]">delete</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

Wire it into `projects/ui/src/modules/detail/DetailScreen.tsx` — replace the Attachments tab body:

```tsx
import { AttachmentsPanel } from "./AttachmentsPanel";
...
        {activeTab === "Attachments" && <AttachmentsPanel workItemId={itemId ?? ""} />}
```

Add a `db` attachments store in `projects/ui/src/lib/api/mocks/db.ts` — a `let attachments` array seeded from `seed.attachments` (add an empty `attachments: []` to the seed fixture if absent), a getter, and:

```ts
  listAttachments: (workItemId: string) =>
    attachments.filter((a) => a.workItemId === workItemId),
  addAttachment: (a: MockAttachment) => { attachments = [...attachments, a]; return a; },
  deleteAttachment: (id: string) => { attachments = attachments.filter((a) => a.id !== id); },
```

(Type `MockAttachment` = `Attachment & { workItemId: string }`. Follow the existing store shape/reset handling — include `attachments` in `db.reset()`.)

Add `liveHandlers` in `projects/ui/src/lib/api/mocks/handlers.ts` for the four endpoints, returning the envelope shape, e.g.:

```ts
http.get("/api/work-items/:id/attachments", ({ params }) =>
  HttpResponse.json({ success: true, data: db.listAttachments(params.id as string), error: null }),
),
http.post("/api/work-items/:id/attachments", async ({ params, request }) => {
  const form = await request.formData();
  const file = form.get("file") as File;
  const created = db.addAttachment({
    id: `att-${file.name}`, workItemId: params.id as string, filename: file.name,
    contentType: file.type || "application/octet-stream", size: file.size,
    url: `/work-items/${params.id}/attachments/att-${file.name}`,
    createdAt: new Date().toISOString(),
  });
  return HttpResponse.json({ success: true, data: created, error: null });
}),
http.delete("/api/work-items/:id/attachments/:attId", ({ params }) => {
  db.deleteAttachment(params.attId as string);
  return HttpResponse.json({ success: true, data: { deleted: params.attId }, error: null });
}),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm test -- AttachmentsPanel useAttachments`
Expected: PASS.

- [ ] **Step 5: Run full UI suite + lint/build**

Run:
```bash
cd projects/ui && pnpm test && pnpm lint && pnpm build
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/modules/detail projects/ui/src/lib/api/mocks
git commit -m "feat: Detail-screen attachments panel with overwrite guard + MSW mocks"
```

---

### Task 9: Coverage gate, docs, and PR

**Files:**
- Modify: `docs/project-history.md` (status entry)
- Modify: `CLAUDE.md` (attachments note under A-series, optional)

- [ ] **Step 1: Run the full gates**

Run:
```bash
cd /Users/noel/projects/naaf
make coverage   # 80% gate
make lint
cd projects/ui && pnpm test && pnpm build
```
Expected: coverage ≥ 80%, lint clean, UI green. If backend coverage dips below 80%, add targeted tests for any uncovered branch in `attachments.py` (e.g. the download `StorageNotFound` path, the overwrite update path).

- [ ] **Step 2: Update project history**

Add a dated status entry to `docs/project-history.md` summarizing: work-item file uploads shipped — `storage` lib (Local/S3), `attachments` table + API, agent access via workspace materialization + prompt block, Detail-screen panel with overwrite guard. Link the spec and this plan.

- [ ] **Step 3: Commit docs**

```bash
git add docs/project-history.md CLAUDE.md
git commit -m "docs: record work-item file uploads feature"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/work-item-file-uploads
gh pr create --title "feat: file uploads on work items so agents can use attached files" \
  --body "$(cat <<'EOF'
## Summary
- New `storage` workspace lib: bytes-oriented port + `LocalStorage` (default, `~/.naaf`) and `S3Storage` (lazy boto3) adapters, consistent `work-item/<uuid>/<filename>` keys.
- `attachments` table (migration 0011) + owner-scoped repository; multipart upload/list/download/delete API with size (413), content-type allowlist (415), and duplicate-filename (409 unless `overwrite`) validation.
- Agents access attachments: provision materializes them into `<workspace>/.naaf/attachments/`; the stage prompt lists them. Worker gets the attachments root bind-mounted.
- Detail-screen Attachments panel: upload (with overwrite-confirm guard), list, download, delete; MSW mocks for offline demo.

## Test plan
- [ ] `make coverage` ≥ 80%
- [ ] `make lint` clean
- [ ] `cd projects/ui && pnpm test && pnpm build` green
- [ ] Manual: `make dev`, attach a `.md` + `.png` to a task, start a run, confirm the agent sees `.naaf/attachments/` in its prompt and can read the text file.
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- §1 storage lib (port + Local + S3, workspace registration) → Tasks 1, 2, and root pyproject edits in Task 1/4. ✓
- §1 key convention in server + factory + get_storage → Task 4. ✓
- §2 attachments table + repository + migration + sync ordering → Task 3 (schema) + Task 5 (ordering: put→insert, delete row→delete bytes, overwrite→put→update). ✓
- §3 upload/list/download/delete, overwrite, 409/413/415, owner-scoping, populate WorkItemOut.attachments, python-multipart → Tasks 4–5. ✓
- §4 mount, materialize at provision, WorkItemBrief.attachments, build_stage_context, stage_instruction block, S3 unchanged agent code → Task 6. ✓
- §5 Detail panel, overwrite guard, hooks, MSW → Tasks 7–8. ✓
- §6 testing across lib/server/UI → each task's TDD steps + Task 9 gate. ✓
- Out-of-scope items (MinIO/compose, S3 sync-down at provision, vision, PDFs) → not implemented; S3Storage ships as code only. ✓

**2. Placeholder scan:** Task 5 originally referenced a `uow_max_bytes(uow)` helper — resolved inline in the same step by switching to a `get_max_attachment_bytes` dependency and instructing removal of the placeholder call. No `TBD`/`TODO`/"add error handling" left.

**3. Type consistency:** `Storage` port methods (`put_bytes`/`get_bytes`/`list`/`delete`/`exists`/`local_path`) are identical across lib, factory, routes, and worker. `Attachment` fields (`work_item_id`, `content_type`, `size`) match ORM columns and `AttachmentOut` mapping (`contentType`, camelCase). `attachment_key`/`attachment_prefix` signatures consistent. UI `Attachment` type matches `AttachmentOut` JSON. `materialize_attachments(storage, work_item_id, workspace_path) -> list[str]` used consistently in Task 6 test and impl.
