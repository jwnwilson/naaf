from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client(session_factory, key: str | None = None) -> TestClient:
    secret_key = key if key is not None else Fernet.generate_key().decode()
    settings = Settings(secret_key=secret_key)
    return TestClient(create_app(settings=settings, session_factory=session_factory))


def test_set_then_list_masks_the_value(session_factory):
    c = _client(session_factory)
    r = c.put("/secrets/anthropic_api_key", json={"value": "sk-ant-abcd1234"})
    assert r.status_code == 200
    assert r.json()["data"] == {"name": "anthropic_api_key", "isSet": True, "hint": "1234"}
    body = c.get("/secrets")
    row = next(s for s in body.json()["data"] if s["name"] == "anthropic_api_key")
    assert row["isSet"] is True and row["hint"] == "1234"
    assert "sk-ant-abcd1234" not in body.text  # value never leaves the server


def test_unset_secret_lists_as_not_set(session_factory):
    c = _client(session_factory)
    rows = {s["name"]: s for s in c.get("/secrets").json()["data"]}
    assert rows["github_token"]["isSet"] is False
    assert rows["github_token"]["hint"] == ""


def test_unknown_name_is_422(session_factory):
    c = _client(session_factory)
    assert c.put("/secrets/aws_key", json={"value": "x"}).status_code == 422


def test_blank_value_is_422(session_factory):
    c = _client(session_factory)
    assert c.put("/secrets/github_token", json={"value": "   "}).status_code == 422


def test_delete_clears_the_secret(session_factory):
    c = _client(session_factory)
    c.put("/secrets/github_token", json={"value": "ghp_zzzz9999"})
    c.delete("/secrets/github_token")
    rows = {s["name"]: s for s in c.get("/secrets").json()["data"]}
    assert rows["github_token"]["isSet"] is False


def test_missing_encryption_key_fails_closed(session_factory):
    c = _client(session_factory, key="")
    assert c.put("/secrets/github_token", json={"value": "ghp_x"}).status_code == 500
