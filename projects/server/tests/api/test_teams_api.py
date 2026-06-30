def test_create_team_and_agent_definition(client):
    team = client.post("/teams/", json={"name": "Default"}).json()["data"]
    assert team["name"] == "Default"

    agent = client.post("/agent-definitions/", json={
        "teamId": team["id"], "role": "lead", "model": "claude-opus-4"
    }).json()["data"]
    assert agent["role"] == "lead"
    assert agent["model"] == "claude-opus-4"
    assert agent["enabled"] is True
    assert agent["tokenLimit"] == 200000


def test_list_agent_definitions_filtered_by_team(client):
    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    client.post("/agent-definitions/", json={"teamId": t, "role": "lead", "model": "m1"})
    client.post("/agent-definitions/", json={"teamId": t, "role": "qa", "model": "m2"})
    body = client.get(f'/agent-definitions/?filters={{"team_id":"{t}"}}').json()
    assert body["meta"]["total"] == 2
