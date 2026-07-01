"""Run API tests (TDD — written before implementation).

Covers: start, list, get, events, gate endpoints.
"""


def _project_and_item(client):
    """Create a project + root epic (epics need no parent) and return (pid, wid)."""
    pid = client.post("/projects/", json={"name": "P"}).json()["data"]["id"]
    wid = client.post(
        f"/projects/{pid}/work-items", json={"type": "epic", "title": "T"}
    ).json()["data"]["id"]
    return pid, wid


# ---------------------------------------------------------------------------
# POST /work-items/{id}/runs
# ---------------------------------------------------------------------------


def test_start_run_returns_camelcase_run(client):
    """Starting a run creates a queued Run with camelCase fields, no owner_id leak."""
    _, wid = _project_and_item(client)
    body = client.post(f"/work-items/{wid}/runs").json()
    d = body["data"]
    assert body["success"] is True
    assert d["workItemId"] == wid
    assert d["status"] == "queued"
    assert "createdAt" in d
    assert "owner_id" not in d


def test_start_run_transitions_work_item_to_in_progress(client):
    """Starting a run moves the work item status to in_progress."""
    _, wid = _project_and_item(client)
    client.post(f"/work-items/{wid}/runs")
    wi = client.get(f"/work-items/{wid}").json()["data"]
    assert wi["status"] == "in_progress"


def test_start_run_returns_201(client):
    _, wid = _project_and_item(client)
    resp = client.post(f"/work-items/{wid}/runs")
    assert resp.status_code == 201


def test_start_run_missing_work_item_is_404(client):
    """Starting a run against a missing work item returns a 404 envelope."""
    resp = client.post(f"/work-items/{'0' * 32}/runs")
    assert resp.status_code == 404
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# GET /runs  and  GET /runs/{id}
# ---------------------------------------------------------------------------


def test_list_and_get_run(client):
    """List includes the started run; get by id returns the same run."""
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]

    listed = client.get(f"/runs?work_item={wid}").json()["data"]
    assert any(r["id"] == rid for r in listed)

    got = client.get(f"/runs/{rid}").json()["data"]
    assert got["id"] == rid
    assert got["workItemId"] == wid


def test_list_runs_project_filter(client):
    """Runs can be filtered by project."""
    pid, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    listed = client.get(f"/runs?project={pid}").json()["data"]
    assert any(r["id"] == rid for r in listed)


def test_get_missing_run_is_404(client):
    resp = client.get(f"/runs/{'0' * 32}")
    assert resp.status_code == 404
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# GET /runs/{id}/events
# ---------------------------------------------------------------------------


def test_list_events_returns_empty_for_new_run(client):
    """A freshly-started run has no events (worker hasn't processed it)."""
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    body = client.get(f"/runs/{rid}/events").json()
    assert body["success"] is True
    assert body["data"] == []


def test_list_events_missing_run_is_404(client):
    resp = client.get(f"/runs/{'0' * 32}/events")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /runs/{id}/gate
# ---------------------------------------------------------------------------


def test_gate_endpoint_requires_pending_gate(client):
    """Posting gate decision on a run with no pending gate returns 409."""
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    resp = client.post(f"/runs/{rid}/gate", json={"decision": "approve"})
    assert resp.status_code == 409
    assert resp.json()["success"] is False


def test_gate_endpoint_rejects_invalid_decision(client):
    """An invalid decision value is rejected with 422 before reaching the logic."""
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    resp = client.post(f"/runs/{rid}/gate", json={"decision": "maybe"})
    assert resp.status_code == 422
