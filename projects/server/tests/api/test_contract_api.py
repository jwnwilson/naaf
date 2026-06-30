def test_project_create_emits_camelcase_contract(client):
    body = client.post("/projects/", json={"name": "naaf", "repoUrl": "git@x/y"}).json()
    assert body["success"] is True
    d = body["data"]
    assert d["name"] == "naaf" and d["repoUrl"] == "git@x/y"
    assert "itemCount" in d and "createdAt" in d
    assert "owner_id" not in d and "autonomy_level" not in d


def test_work_item_nested_create_and_list_by_project(client):
    pid = client.post("/projects/", json={"name": "p"}).json()["data"]["id"]
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "Auth", "priority": "high"}).json()["data"]
    assert epic["type"] == "epic" and epic["priority"] == "high"
    assert epic["projectId"] == pid and "kind" not in epic and "body" not in epic
    listed = client.get(f"/work-items?project={pid}").json()
    assert listed["data"][0]["type"] == "epic"


def test_transition_uses_5_set(client):
    pid = client.post("/projects/", json={"name": "p"}).json()["data"]["id"]
    resp = client.post(f"/projects/{pid}/work-items", json={"type": "epic", "title": "x"})
    wid = resp.json()["data"]["id"]
    out = client.post(f"/work-items/{wid}/transition", json={"status": "in_progress"}).json()
    assert out["data"]["status"] == "in_progress"


def test_agent_definition_contract_shape(client, session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.team import AgentDefinition, AgentRole

    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        aid = uow.agent_definitions.create(
            AgentDefinition(
                owner_id="dev-user", team_id=t, role=AgentRole.LEAD,
                model_alias="claude-opus-4",
            )
        ).id
    a = client.get(f"/agent-definitions/{aid}").json()["data"]
    assert a["model"] == "claude-opus-4" and a["enabled"] is True and a["tokenLimit"] == 200000
    assert "model_alias" not in a
