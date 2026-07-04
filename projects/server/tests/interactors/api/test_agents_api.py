"""Tests for GET /agents — live-agent roster endpoint."""
from adapters.database.uow import SqlUnitOfWork
from domain.team import AgentDefinition, AgentRole, Team


def test_agents_endpoint_returns_roster_all_idle_without_runs(client):
    # The dev seed / a fresh DB may have no definitions; assert envelope + list shape.
    resp = client.get("/agents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert all(row["status"] in ("running", "idle") for row in body["data"])


def test_agents_reflects_a_running_backend(client, running_backend_run):
    # running_backend_run fixture: an enabled backend AgentDefinition + a run whose
    # current stage is IMPLEMENT (engineer). See conftest note below.
    rows = client.get("/agents").json()["data"]
    backend = next((r for r in rows if r["role"] == "backend"), None)
    assert backend is not None
    assert backend["status"] == "running"
    assert backend["currentStage"] == "implement"
    assert backend["workItemId"] == running_backend_run["work_item_id"]


def test_agents_is_owner_scoped(
    client_other_owner, session_factory, running_backend_run
):
    # Give other-user their OWN enabled backend roster row, so the assertion is
    # non-vacuous: it proves dev-user's running backend run does not leak across.
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "other-user"})
    with uow.transaction() as u:
        team = u.teams.create(Team(owner_id="", name="OtherTeam"))
        u.agent_definitions.create(
            AgentDefinition(
                owner_id="",
                team_id=team.id,
                role=AgentRole.BACKEND,
                enabled=True,
            )
        )

    rows = client_other_owner.get("/agents").json()["data"]
    backend = next((r for r in rows if r["role"] == "backend"), None)
    assert backend is not None and backend["status"] == "idle"
    assert backend["workItemId"] is None
