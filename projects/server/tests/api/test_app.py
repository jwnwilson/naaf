def test_health_is_enveloped_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "data": {"status": "ok"}, "error": None, "meta": None}
