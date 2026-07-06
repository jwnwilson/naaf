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
def client(session_factory, async_session_factory, tmp_path):
    app = create_app(
        settings=Settings(attachments_root=str(tmp_path / "attachments")),
        session_factory=session_factory,
        async_session_factory=async_session_factory,
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
def second_work_item_id(client) -> str:
    """A second work item under the SAME owner as seeded_work_item_id.

    An epic is used because it is a valid root (a task would need a feature
    parent); the guard test only needs a distinct owned work item id.
    """
    proj = client.post("/projects/", json={"name": "test-project-2"}).json()["data"]
    pid = proj["id"]
    epic = client.post(
        f"/projects/{pid}/work-items", json={"type": "epic", "title": "E2"}
    ).json()["data"]
    return epic["id"]


@pytest.fixture
def client_other_owner(session_factory, async_session_factory, tmp_path):
    """A TestClient owned by 'other-user' — cannot access dev-user's work items."""
    app = create_app(
        settings=Settings(
            dev_owner_id="other-user",
            attachments_root=str(tmp_path / "attachments-other"),
        ),
        session_factory=session_factory,
        async_session_factory=async_session_factory,
    )
    return TestClient(app)


@pytest.fixture
def running_backend_run(client, session_factory):
    """Seed an enabled backend AgentDefinition + a running Run via direct UoW access.

    Returns a dict with ``work_item_id`` — the task the run is attached to.
    """
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.run import Run, RunStatus, Stage, StageState, StageStatus
    from domain.team import AgentDefinition, AgentRole, Team

    # Create a real project + task via the API to avoid FK surprises.
    proj = client.post("/projects/", json={"name": "run-project"}).json()["data"]
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
    work_item_id = task["id"]

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="", name="RunTeam"))
        uow.agent_definitions.create(
            AgentDefinition(
                owner_id="",
                team_id=team.id,
                role=AgentRole.BACKEND,
                enabled=True,
            )
        )
        uow.runs.create(
            Run(
                owner_id="",
                work_item_id=work_item_id,
                project_id=pid,
                autonomy_level="gated_all",
                status=RunStatus.RUNNING,
                current_stage=Stage.IMPLEMENT,
                stages=[
                    StageState(
                        stage=Stage.IMPLEMENT,
                        status=StageStatus.RUNNING,
                        role="engineer",
                    )
                ],
            )
        )

    return {"work_item_id": work_item_id}
