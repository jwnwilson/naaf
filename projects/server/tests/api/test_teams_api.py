def test_create_team_and_agent_definition(client):
    team = client.post("/teams/", json={"name": "Default"}).json()["data"]
    assert team["owner_id"] == "dev-user"

    agent = client.post("/agent-definitions/", json={
        "team_id": team["id"], "role": "lead"
    }).json()["data"]
    assert agent["role"] == "lead"
    assert agent["runtime_adapter"] == "claude_code"
    assert agent["capability_grants"] == []


def test_list_agent_definitions_filtered_by_team(client):
    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    client.post("/agent-definitions/", json={"team_id": t, "role": "lead"})
    client.post("/agent-definitions/", json={"team_id": t, "role": "qa"})
    body = client.get(f'/agent-definitions/?filters={{"team_id":"{t}"}}').json()
    assert body["meta"]["total"] == 2
