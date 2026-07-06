import pytest
from naaf_db.engine import build_engine
from naaf_db.errors import RecordNotFound
from naaf_db.repository import SqlRepository
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
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


class WidgetRepo(SqlRepository[Widget]):
    orm_model = WidgetRow
    dto = Widget


@pytest.fixture
def session():
    engine = build_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_create_read_roundtrip_with_owner_scope(session):
    repo = WidgetRepo(session, required_filters={"owner_id": "u1"})
    created = repo.create(Widget(id="w1", owner_id="", name="a"))
    session.flush()
    assert created.owner_id == "u1"
    assert repo.read("w1").name == "a"


def test_read_missing_raises_record_not_found(session):
    repo = WidgetRepo(session, required_filters={"owner_id": "u1"})
    with pytest.raises(RecordNotFound):
        repo.read("nope")


def test_owner_scope_hides_other_owners_rows(session):
    WidgetRepo(session, required_filters={"owner_id": "u1"}).create(
        Widget(id="w1", owner_id="", name="a")
    )
    session.flush()
    with pytest.raises(RecordNotFound):
        WidgetRepo(session, required_filters={"owner_id": "u2"}).read("w1")
