"""Permanent project delete for named administrators, and free-text project codes (D-265)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEntry, Project, RoleAssignment, Site
from tests.conftest import Api, Ids

BODY = {
    "name_en": "Free code project",
    "name_ar": "مشروع تجريبي",
    "project_type": "building_highrise",
    "client_name_en": "Client",
    "client_name_ar": "العميل",
    "city": "Riyadh",
    "start_date": "2026-01-01",
}


def test_project_code_is_free_text(api: Api) -> None:
    mgr = api.as_("faisal.harbi")
    res = mgr.post("/api/v1/projects", json={**BODY, "code": "  Tower b 2 "})
    assert res.status_code == 201, res.text
    assert res.json()["code"] == "Tower b 2"
    assert mgr.post("/api/v1/projects", json={**BODY, "code": "x" * 13}).status_code == 422
    assert mgr.post("/api/v1/projects", json={**BODY, "code": "   "}).status_code == 422


def test_delete_needs_a_named_administrator(
    api: Api, ids: Ids, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "project_delete_emails", "someone.else@example.com")
    mgr = api.as_("faisal.harbi")
    assert mgr.get("/api/v1/auth/me").json()["can_delete_projects"] is False
    res = mgr.post(
        f"/api/v1/projects/{ids.project('RBT-52')}/delete", json={"confirm_code": "RBT-52"}
    )
    assert res.status_code == 403


@pytest.mark.usefixtures("hse_seed")
def test_delete_removes_the_project_and_its_data(
    api: Api, ids: Ids, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "project_delete_emails", " Faisal.Harbi@example.com ")
    mgr = api.as_("faisal.harbi")
    assert mgr.get("/api/v1/auth/me").json()["can_delete_projects"] is True
    pid, keep = ids.project("RBT-52"), ids.project("ANIA-EXP")
    keep_sites = db.scalar(select(func.count()).select_from(Site).where(Site.project_id == keep))

    wrong = mgr.post(f"/api/v1/projects/{pid}/delete", json={"confirm_code": "rbt-52"})
    assert wrong.status_code == 422

    res = mgr.post(f"/api/v1/projects/{pid}/delete", json={"confirm_code": "RBT-52"})
    assert res.status_code == 200, res.text
    assert res.json()["code"] == "RBT-52" and res.json()["rows_deleted"] > 1

    db.expire_all()
    assert db.get(Project, pid) is None
    assert not db.scalar(select(func.count()).select_from(Site).where(Site.project_id == pid))
    assert not db.scalar(
        select(func.count()).select_from(RoleAssignment).where(RoleAssignment.project_id == pid)
    )
    assert db.scalar(select(func.count()).select_from(Site).where(Site.project_id == keep)) == (
        keep_sites
    )
    entry = db.scalar(
        select(AuditEntry).where(AuditEntry.entity_id == pid).order_by(AuditEntry.seq.desc())
    )
    assert entry is not None and entry.details and entry.details["deleted"] is True
    assert mgr.get(f"/api/v1/projects/{pid}").status_code == 404
    assert mgr.get(f"/api/v1/projects/{keep}").status_code == 200
    chain = mgr.post("/api/v1/audit-log/verify")
    assert chain.status_code == 200 and chain.json()["ok"] is True, chain.text
