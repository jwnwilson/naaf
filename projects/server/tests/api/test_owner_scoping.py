from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings


def test_other_owner_cannot_read_project(session_factory):
    app_u1 = create_app(settings=Settings(dev_owner_id="u1"), session_factory=session_factory)
    app_u2 = create_app(settings=Settings(dev_owner_id="u2"), session_factory=session_factory)
    pid = TestClient(app_u1).post("/projects/", json={"name": "secret"}).json()["data"]["id"]
    # u2 shares the DB but is scoped out -> 404
    assert TestClient(app_u2).get(f"/projects/{pid}").status_code == 404
