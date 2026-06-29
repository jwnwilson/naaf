from dataclasses import dataclass, field

from crud_router import CrudRouter, Envelope
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class Thing(BaseModel):
    id: str
    name: str


class CreateThing(BaseModel):
    name: str


class UpdateThing(BaseModel):
    name: str | None = None


@dataclass
class Paginated:
    results: list
    total: int
    page_size: int
    page_number: int


@dataclass
class FakeRepo:
    store: dict = field(default_factory=dict)

    def create(self, dto):
        thing = Thing(id="t1", name=dto.name)
        self.store[thing.id] = thing
        return thing

    def read(self, id):
        from crud_router.errors import NotFound
        if id not in self.store:
            raise NotFound("missing")
        return self.store[id]

    def read_multi(self, filters, page_size, page_number, order_by):
        items = list(self.store.values())
        return Paginated(items, len(items), page_size, page_number)

    def update(self, id, dto):
        cur = self.store[id]
        self.store[id] = cur.model_copy(update={"name": dto.name})
        return self.store[id]

    def delete(self, id):
        self.store.pop(id, None)


class FakeUow:
    def __init__(self):
        self.things = FakeRepo()


def _client():
    uow = FakeUow()
    app = FastAPI()
    app.include_router(CrudRouter(
        db_dependency=lambda: uow,
        repository="things",
        response_dto=Thing,
        create_schema=CreateThing,
        update_schema=UpdateThing,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/things",
    ))
    return TestClient(app)


def test_create_returns_enveloped_201():
    client = _client()
    resp = client.post("/things/", json={"name": "a"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "a"
    assert body["error"] is None


def test_list_includes_pagination_meta():
    client = _client()
    client.post("/things/", json={"name": "a"})
    resp = client.get("/things/")
    body = resp.json()
    assert body["success"] is True
    assert body["meta"]["total"] == 1
    assert isinstance(body["data"], list)


def test_envelope_model_defaults():
    env = Envelope[str](data="x")
    assert env.success is True
    assert env.error is None
