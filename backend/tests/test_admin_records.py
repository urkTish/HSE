"""Administrator delete of any record, traceable in the deleted-items register (D-271)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Site, Zone
from tests.conftest import Api, Ids


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch, api: Api):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "project_delete_emails", "faisal.harbi@example.com")
    return api.as_("faisal.harbi")


def test_delete_a_zone_is_traceable(admin, ids: Ids, db: Session) -> None:  # type: ignore[no-untyped-def]
    types = admin.get("/api/v1/admin/deletable-types").json()["entity_types"]
    assert "zone" in types and "user" not in types
    zone_id = ids.zone("Z-PIERB")
    res = admin.post(
        "/api/v1/admin/records/delete",
        json={"entity_type": "zone", "entity_id": zone_id, "reason": "created by mistake"},
    )
    assert res.status_code == 200, res.text
    assert db.scalar(select(Zone.id).where(Zone.id == zone_id)) is None
    rec_id = res.json()["id"]
    page = admin.get("/api/v1/admin/deleted-records").json()
    assert page["items"][0]["id"] == rec_id and page["items"][0]["reason"] == "created by mistake"
    detail = admin.get(f"/api/v1/admin/deleted-records/{rec_id}").json()
    assert detail["rows"]["zones"][0]["id"] == zone_id
    assert admin.post("/api/v1/audit-log/verify").json()["ok"] is True


def test_only_the_administrator_deletes(api: Api, ids: Ids, db: Session) -> None:
    mgr = api.as_("faisal.harbi")  # HSE Manager but not in PROJECT_DELETE_EMAILS
    site_id = ids.site("S-TWR")
    res = mgr.post(
        "/api/v1/admin/records/delete",
        json={"entity_type": "site", "entity_id": site_id, "reason": "x"},
    )
    assert res.status_code == 403
    assert db.scalar(select(Site.id).where(Site.id == site_id)) is not None
    assert mgr.get("/api/v1/admin/deleted-records").status_code == 403


def test_unknown_type_and_users_are_refused(admin, ids: Ids) -> None:  # type: ignore[no-untyped-def]
    for kind, rid in (("user", ids.user("noura.qahtani")), ("nonsense", ids.site("S-TWR"))):
        res = admin.post(
            "/api/v1/admin/records/delete",
            json={"entity_type": kind, "entity_id": rid, "reason": "x"},
        )
        assert res.status_code == 422
