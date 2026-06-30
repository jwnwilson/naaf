def test_create_and_get_project(client):
    created = client.post("/projects/", json={"name": "naaf"}).json()
    assert created["success"] is True
    pid = created["data"]["id"]

    got = client.get(f"/projects/{pid}").json()
    assert got["data"]["name"] == "naaf"


def test_list_projects_has_meta(client):
    client.post("/projects/", json={"name": "a"})
    client.post("/projects/", json={"name": "b"})
    body = client.get("/projects/").json()
    assert body["meta"]["total"] == 2
    assert len(body["data"]) == 2


def test_patch_project(client):
    pid = client.post("/projects/", json={"name": "old"}).json()["data"]["id"]
    body = client.patch(f"/projects/{pid}", json={"name": "new"}).json()
    assert body["data"]["name"] == "new"


def test_delete_project(client):
    pid = client.post("/projects/", json={"name": "x"}).json()["data"]["id"]
    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get(f"/projects/{pid}").status_code == 404


def test_get_missing_project_is_enveloped_404(client):
    resp = client.get("/projects/" + "0" * 32)
    assert resp.status_code == 404
    assert resp.json()["success"] is False
