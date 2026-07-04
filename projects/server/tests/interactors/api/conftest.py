"""Fixtures for attachment API tests.

Overrides the top-level `client` fixture so storage is routed to a temp dir
instead of ~/.naaf. Also provides:
  - seeded_work_item_id: a real task work item created via the API
  - client_other_owner: a TestClient scoped to a different owner ("other-user")
"""
import pytest
from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings


@pytest.fixture
def client(session_factory, tmp_path):
    app = create_app(
        settings=Settings(attachments_root=str(tmp_path / "attachments")),
        session_factory=session_factory,
    )
    return TestClient(app)


@pytest.fixture
def seeded_work_item_id(client) -> str:
    """Create a project + task work item and return the task's id."""
    proj = client.post("/projects/", json={"name": "test-project"}).json()["data"]
    pid = proj["id"]
    epic = client.post(
        f"/projects/{pid}/work-items", json={"type": "epic", "title": "E"}
    ).json()["data"]
    feat = client.post(
        f"/projects/{pid}/work-items",
        json={"type": "feature", "title": "F", "epicId": epic["id"]},
    ).json()["data"]
    task = client.post(
        f"/projects/{pid}/work-items",
        json={"type": "task", "title": "T", "featureId": feat["id"]},
    ).json()["data"]
    return task["id"]


@pytest.fixture
def client_other_owner(session_factory, tmp_path):
    """A TestClient owned by 'other-user' — cannot access dev-user's work items."""
    app = create_app(
        settings=Settings(
            dev_owner_id="other-user",
            attachments_root=str(tmp_path / "attachments-other"),
        ),
        session_factory=session_factory,
    )
    return TestClient(app)
