from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_with_status_ok():
    res = client.get("/health")

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"status"}
    assert body["status"] == "ok"


def test_health_does_not_require_a_query():
    res = client.get("/health")

    assert res.json() == {"status": "ok"}