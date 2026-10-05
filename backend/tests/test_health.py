from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    res = TestClient(app).get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["database"] in ("ok", "error")
    assert body["version"]


def test_unauthenticated_error_envelope() -> None:
    res = TestClient(app).get("/api/v1/projects")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_validation_error_envelope() -> None:
    res = TestClient(app).post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["errors"]
