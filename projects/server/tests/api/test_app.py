from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings


def test_health_is_enveloped_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "data": {"status": "ok"}, "error": None, "meta": None}


def test_health_returns_json_content_type(client):
    resp = client.get("/health")
    assert resp.headers["content-type"].startswith("application/json")


def test_health_rejects_non_get_methods(client):
    assert client.post("/health").status_code == 405


def test_health_bypasses_auth(session_factory, async_session_factory):
    # Arrange — an auth mode the owner-scoping dependency cannot resolve
    app = create_app(
        settings=Settings(auth_mode="auth0"),
        session_factory=session_factory,
        async_session_factory=async_session_factory,
    )

    # Act — no credentials supplied
    resp = TestClient(app).get("/health")

    # Assert — liveness probes must answer without authentication
    assert resp.status_code == 200
    assert resp.json()["data"] == {"status": "ok"}
