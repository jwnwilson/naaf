def _project(client) -> str:
    return client.post("/projects/", json={"name": "naaf"}).json()["data"]["id"]


def test_work_item_out_exposes_key_and_lineage_names(client):
    # project
    proj = client.post("/projects", json={"name": "NAAF Test"}).json()["data"]
    pid = proj["id"]

    def create(kind, title, parent_field=None, parent_id=None):
        body = {"type": kind, "title": title, "status": "todo", "priority": "medium"}
        if parent_field:
            body[parent_field] = parent_id
        return client.post(f"/projects/{pid}/work-items", json=body).json()["data"]

    epic = create("epic", "Auth")
    feature = create("feature", "Login flow", "epicId", epic["id"])
    task = create("task", "Fix login bug", "featureId", feature["id"])

    # key = <project.key>-<seq>; NAAF Test -> NAAF, epic is seq 1
    assert epic["key"] == "NAAF-1"
    assert feature["key"] == "NAAF-2"
    assert task["key"] == "NAAF-3"

    # lineage names
    assert epic["epicName"] is None and epic["featureName"] is None
    assert feature["epicName"] == "Auth" and feature["featureName"] is None
    assert task["epicName"] == "Auth" and task["featureName"] == "Login flow"


def test_list_work_items_includes_key(client):
    proj = client.post("/projects", json={"name": "Acme"}).json()["data"]
    pid = proj["id"]
    client.post(
        f"/projects/{pid}/work-items",
        json={"type": "epic", "title": "E", "status": "todo", "priority": "medium"},
    )
    items = client.get("/work-items", params={"project": pid}).json()["data"]
    assert items[0]["key"] == "ACME-1"


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


def test_patch_task_returns_lineage(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "E"}).json()["data"]
    feat = client.post(f"/projects/{pid}/work-items",
                       json={"type": "feature", "title": "F", "epicId": epic["id"]}).json()["data"]
    task = client.post(f"/projects/{pid}/work-items",
                       json={"type": "task", "title": "T", "featureId": feat["id"]}).json()["data"]

    patched = client.patch(f"/work-items/{task['id']}",
                           json={"title": "T2"}).json()["data"]
    assert patched["title"] == "T2"
    assert patched["epicId"] == epic["id"]  # grandparent
    assert patched["featureId"] == feat["id"]  # parent


def test_list_by_epic_filter_has_correct_total(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "E"}).json()["data"]
    other = client.post(f"/projects/{pid}/work-items",
                        json={"type": "epic", "title": "Other"}).json()["data"]
    client.post(f"/projects/{pid}/work-items",
                json={"type": "feature", "title": "F1", "epicId": epic["id"]})
    client.post(f"/projects/{pid}/work-items",
                json={"type": "feature", "title": "F2", "epicId": epic["id"]})
    client.post(f"/projects/{pid}/work-items",
                json={"type": "feature", "title": "F3", "epicId": other["id"]})

    body = client.get(f"/work-items?epic={epic['id']}").json()
    assert body["meta"]["total"] == len(body["data"]) == 2
    assert all(item["epicId"] == epic["id"] for item in body["data"])


def test_nested_create_task_with_both_ids_uses_feature_as_parent(client):
    """When both epicId and featureId are sent, featureId wins (most specific)."""
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"type": "epic", "title": "E"}).json()["data"]
    feat = client.post(f"/projects/{pid}/work-items",
                       json={"type": "feature", "title": "F", "epicId": epic["id"]}).json()["data"]

    # Send BOTH ids — task should be parented to the feature, not the epic
    resp = client.post(f"/projects/{pid}/work-items",
                       json={"type": "task", "title": "T",
                             "epicId": epic["id"], "featureId": feat["id"]})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["featureId"] == feat["id"]   # parent is the feature (most specific)
    assert data["epicId"] == epic["id"]      # grandparent is the epic


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
