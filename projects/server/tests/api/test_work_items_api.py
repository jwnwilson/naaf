def _project(client) -> str:
    return client.post("/projects/", json={"name": "naaf"}).json()["data"]["id"]


def test_nested_create_epic_then_feature_then_task(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "Auth"}).json()["data"]
    assert epic["projectId"] == pid

    feat = client.post(f"/projects/{pid}/work-items",
                       json={"type": "feature", "title": "Login", "epicId": epic["id"]})
    assert feat.status_code == 201
    fid = feat.json()["data"]["id"]

    task = client.post(f"/projects/{pid}/work-items",
                       json={"type": "task", "title": "Form", "featureId": fid})
    assert task.status_code == 201


def test_feature_without_epic_parent_is_409(client):
    pid = _project(client)
    resp = client.post(f"/projects/{pid}/work-items",
                       json={"type": "feature", "title": "x"})
    assert resp.status_code == 409
    assert resp.json()["success"] is False


def test_transition_todo_to_in_progress(client):
    pid = _project(client)
    wid = client.post(f"/projects/{pid}/work-items",
                      json={"type": "epic", "title": "x"}).json()["data"]["id"]
    body = client.post(f"/work-items/{wid}/transition",
                       json={"status": "in_progress"}).json()
    assert body["data"]["status"] == "in_progress"


def test_illegal_transition_is_409(client):
    pid = _project(client)
    wid = client.post(f"/projects/{pid}/work-items",
                      json={"type": "epic", "title": "x"}).json()["data"]["id"]
    resp = client.post(f"/work-items/{wid}/transition", json={"status": "done"})
    assert resp.status_code == 409


def test_create_work_item_under_missing_project_is_404(client):
    resp = client.post("/projects/" + "0" * 32 + "/work-items",
                       json={"type": "epic", "title": "x"})
    assert resp.status_code == 404
    assert resp.json()["success"] is False


def test_board_returns_nested_tree(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "E"}).json()["data"]
    client.post(f"/projects/{pid}/work-items",
                json={"type": "feature", "title": "F", "epicId": epic["id"]})
    board = client.get(f"/projects/{pid}/board").json()
    assert board["success"] is True
    assert len(board["data"]) == 1
    assert board["data"][0]["item"]["id"] == epic["id"]
    assert board["data"][0]["children"][0]["item"]["title"] == "F"
