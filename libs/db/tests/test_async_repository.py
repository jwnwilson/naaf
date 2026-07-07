import pytest
from naaf_db.async_repository import AsyncSqlRepository
from naaf_db.engine import build_async_engine
from naaf_db.errors import RecordNotFound
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class WidgetRow(Base):
    __tablename__ = "widgets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class Widget(BaseModel):
    id: str
    owner_id: str
    name: str


class AsyncWidgetRepo(AsyncSqlRepository[Widget]):
    orm_model = WidgetRow
    dto = Widget


@pytest.fixture
async def factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_create_read_and_owner_scope(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        await repo.create(Widget(id="w1", owner_id="", name="a"))
        await session.flush()
        got = await repo.read("w1")
        assert got.owner_id == "u1" and got.name == "a"


@pytest.mark.asyncio
async def test_async_read_missing_raises(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        with pytest.raises(RecordNotFound):
            await repo.read("nope")


@pytest.mark.asyncio
async def test_async_read_multi_filters_and_orders(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        for i in (2, 1, 3):
            await repo.create(Widget(id=f"w{i}", owner_id="", name=str(i)))
        await session.flush()
        page = await repo.read_multi(filters={"name__gte": "2"}, order_by="name")
        assert [w.name for w in page.results] == ["2", "3"]
        assert page.total == 2


@pytest.mark.asyncio
async def test_async_update_changes_fields(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        created = await repo.create(Widget(id="w1", owner_id="", name="old"))
        await session.flush()
        updated = await repo.update(created.id, Widget(id="w1", owner_id="u1", name="new"))
        assert updated.name == "new"


@pytest.mark.asyncio
async def test_async_delete_then_read_raises(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        created = await repo.create(Widget(id="w1", owner_id="", name="x"))
        await session.flush()
        await repo.delete(created.id)
        with pytest.raises(RecordNotFound):
            await repo.read(created.id)


@pytest.mark.asyncio
async def test_async_delete_where_respects_owner_and_in_filter(factory):
    async with factory() as session:
        repo_a = AsyncWidgetRepo(session, required_filters={"owner_id": "a"})
        repo_b = AsyncWidgetRepo(session, required_filters={"owner_id": "b"})
        w1 = await repo_a.create(Widget(id="w1", owner_id="", name="p1"))
        w2 = await repo_a.create(Widget(id="w2", owner_id="", name="p2"))
        wb = await repo_b.create(Widget(id="w3", owner_id="", name="pb"))
        await session.flush()

        removed = await repo_a.delete_where(id__in=[w1.id, w2.id, wb.id])
        assert removed == 2  # wb belongs to owner "b" and is filtered out

        assert (await repo_b.read(wb.id)).id == wb.id  # untouched
