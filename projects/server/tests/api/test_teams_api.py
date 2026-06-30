from adapters.database.uow import SqlUnitOfWork
from domain.team import AgentDefinition, AgentRole


def _insert_agent_definition(session_factory, team_id: str, **overrides) -> str:
    """Insert an AgentDefinition directly (the contract has no POST route)."""
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        agent = uow.agent_definitions.create(
            AgentDefinition(owner_id="dev-user", team_id=team_id, **overrides)
        )
        return agent.id


def test_create_team_emits_contract_shape(client):
    team = client.post("/teams/", json={"name": "Default"}).json()["data"]
    assert team["name"] == "Default"
    assert "owner_id" not in team


def test_agent_definition_contract_shape(client, session_factory):
    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    aid = _insert_agent_definition(
        session_factory,
        t,
        role=AgentRole.LEAD,
        model_alias="claude-opus-4",
        persona_prompt="be helpful",
    )
    a = client.get(f"/agent-definitions/{aid}").json()["data"]
    assert a["model"] == "claude-opus-4"
    assert a["enabled"] is True
    assert a["tokenLimit"] == 200000
    assert a["systemPrompt"] == "be helpful"
    assert "model_alias" not in a


def test_list_agent_definitions_filtered_by_team(client, session_factory):
    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    _insert_agent_definition(session_factory, t, role=AgentRole.LEAD, model_alias="m1")
    _insert_agent_definition(session_factory, t, role=AgentRole.QA, model_alias="m2")
    body = client.get(f'/agent-definitions/?filters={{"team_id":"{t}"}}').json()
    assert body["meta"]["total"] == 2
