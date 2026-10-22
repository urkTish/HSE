"""First-time setup: organisation, first project, first administrator (D-306)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine
from app.main import app
from app.models import Installation, Project, RoleAssignment, User
from tests.conftest import Api

PW = "Trial-Setup#2026x"


def _body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "organisation_name_en": "Gulf Airports Construction Co.",
        "organisation_name_ar": "شركة إنشاءات مطارات الخليج",
        "project": {
            "code": "TRIAL-1",
            "name_en": "Terminal 3 expansion",
            "name_ar": "توسعة المبنى 3",
            "project_type": "airport",
            "client_name_en": "Airport Authority",
            "client_name_ar": "هيئة المطار",
            "city": "Riyadh",
            "start_date": "2026-10-01",
            "airport_iata": "RUH",
        },
        "admin": {
            "email": "Admin.First@Example.com",
            "full_name_en": "First Admin",
            "full_name_ar": "المسؤول الأول",
            "preferred_language": "ar",
            "password": PW,
        },
        "privacy_notice_version": get_settings().privacy_notice_version,
    }
    body.update(over)
    return body


def _empty_install() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def test_setup_is_locked_on_a_seeded_install(api: Api) -> None:
    c = TestClient(app)
    assert c.get("/api/v1/setup").json()["needed"] is False
    res = c.post("/api/v1/setup", json=_body())
    assert res.status_code == 409 and res.json()["detail"]["code"] == "SETUP_ALREADY_DONE"


def test_setup_creates_org_project_admin_and_signs_in(db: Session) -> None:
    _empty_install()
    c = TestClient(app)
    st = c.get("/api/v1/setup").json()
    assert st["needed"] is True and st["token_required"] is False
    weak = c.post("/api/v1/setup", json=_body(admin={**_body()["admin"], "password": "short"}))
    assert weak.status_code == 422
    no_ar = c.post("/api/v1/setup", json=_body(organisation_name_ar="Gulf"))
    assert no_ar.status_code == 422
    old_notice = c.post("/api/v1/setup", json=_body(privacy_notice_version="PN-0.1"))
    assert old_notice.status_code == 409
    assert c.get("/api/v1/setup").json()["needed"] is True  # nothing half-created
    res = c.post("/api/v1/setup", json=_body())
    assert res.status_code == 201, res.text
    body = res.json()
    assert "hse_session=" in res.headers["set-cookie"]
    me = body["user"]
    assert me["email"] == "admin.first@example.com" and me["is_hse_manager"] is True
    assert me["privacy_ack_required"] is False and me["display_language"] == "ar"
    c.headers["Authorization"] = f"Bearer {body['access_token']}"
    projects = c.get("/api/v1/projects").json()["items"]
    assert [p["code"] for p in projects] == ["TRIAL-1"]
    st2 = c.get("/api/v1/setup").json()
    assert st2["needed"] is False
    assert st2["organisation_name_ar"] == "شركة إنشاءات مطارات الخليج"
    again = TestClient(app).post("/api/v1/setup", json=_body())
    assert again.status_code == 409
    login = TestClient(app).post(
        "/api/v1/auth/login", json={"email": "admin.first@example.com", "password": PW}
    )
    assert login.status_code == 200
    db.expire_all()
    assert db.get(Installation, 1) is not None
    assert db.scalar(select(Project.code)) == "TRIAL-1"
    user = db.scalar(select(User).where(User.email == "admin.first@example.com"))
    assert user is not None
    roles = db.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == user.id)).all()
    assert [r.value for r in roles] == ["hse_manager"]


def test_setup_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _empty_install()
    monkeypatch.setattr(get_settings(), "setup_token", "deploy-code-123")
    c = TestClient(app)
    assert c.get("/api/v1/setup").json()["token_required"] is True
    assert c.post("/api/v1/setup", json=_body()).status_code == 403
    assert c.post("/api/v1/setup", json=_body(setup_token="wrong")).status_code == 403
    res = c.post("/api/v1/setup", json=_body(setup_token="deploy-code-123"))
    assert res.status_code == 201, res.text
