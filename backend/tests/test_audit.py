"""Audit log — AC1 (entry), AC30-AC32, rules 35-40."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Role
from app.jobs import purge_audit, verify_audit_chain
from app.models import AuditEntry
from app.services import audit
from app.services.audit import AuditActor
from tests.conftest import Api, Ids
from tests.hse_helpers import add_case, create_ca, create_incident


def _some_entries(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    c.patch(f"/api/v1/zones/{ids.zone('Z-PIERB')}", json={"name_en": "Pier B Steel"})
    api.as_("yousef.ghamdi").get(f"/api/v1/projects/{ids.project('ANIA-EXP')}")


def test_AC30_update_and_delete_blocked(api: Api, ids: Ids, db: Session) -> None:
    _some_entries(api, ids)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_log SET after = '{}'::jsonb"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AuditEntry))


def test_AC30_tampering_detected_by_chain_job(api: Api, ids: Ids, db: Session) -> None:
    _some_entries(api, ids)
    assert verify_audit_chain(db)["ok"] is True
    db.commit()
    target = db.scalars(select(AuditEntry).where(AuditEntry.action == AuditAction.update)).first()
    assert target is not None
    # A DBA bypassing the trigger edits the `after` field directly
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
    db.execute(
        text("""UPDATE audit_log SET after = '{"name_en": "forged"}'::jsonb WHERE id = :i"""),
        {"i": target.id},
    )
    db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))
    db.commit()
    db.expire_all()
    result = verify_audit_chain(db)
    db.commit()
    assert result["ok"] is False and result["first_break_seq"] == target.seq
    res = api.as_("faisal.harbi").post("/api/v1/audit-log/verify")
    assert res.status_code == 200 and res.json()["ok"] is False
    notes = api.as_("faisal.harbi").get("/api/v1/notifications").json()["items"]
    assert any(n["kind"] == "audit_chain_break" for n in notes)


def test_AC30_deleted_entry_detected(api: Api, ids: Ids, db: Session) -> None:
    _some_entries(api, ids)
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
    db.execute(text("DELETE FROM audit_log WHERE seq = 2"))
    db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))
    db.commit()
    assert audit.verify_chain(db).ok is False


def test_AC31_officer_view_scoped_without_ip(api: Api, ids: Ids, db: Session) -> None:
    _some_entries(api, ids)
    api.as_("faisal.harbi").patch(
        f"/api/v1/projects/{ids.project('RBT-52')}/settings", json={"show_hijri": True}
    )
    c = api.as_("noura.qahtani")
    res = c.get("/api/v1/audit-log")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items
    pid = ids.project("ANIA-EXP")
    for e in items:
        assert e["project_id"] == pid
        assert "ip_address" not in e and "user_agent" not in e and "hash" not in e
        if e["action"] in ("login_success", "login_failed", "logout"):
            assert e["actor_user_id"] == ids.user("noura.qahtani")
    viewed = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.audit_log_viewed)
    ).all()
    assert len(viewed) == 1 and str(viewed[0].actor_user_id) == ids.user("noura.qahtani")
    full = api.as_("faisal.harbi").get("/api/v1/audit-log").json()["items"]
    assert any("ip_address" in e for e in full)
    assert {e["project_id"] for e in full} > {pid}


def test_rule38_others_cannot_read_audit_log(api: Api) -> None:
    for who in ("omar.siddiqui", "sarah.mitchell", "ahmed.zahrani"):
        assert api.as_(who).get("/api/v1/audit-log").status_code == 403


def test_rule38_change_history_for_visible_records(api: Api, ids: Ids) -> None:
    _some_entries(api, ids)
    zid = ids.zone("Z-PIERB")
    sarah = api.as_("sarah.mitchell").get(f"/api/v1/history/zone/{zid}")
    assert sarah.status_code == 200 and sarah.json()["total"] == 1
    assert "ip_address" not in sarah.json()["items"][0]
    # Omar (S-AIR only) cannot see a S-LAND zone's history
    assert api.as_("omar.siddiqui").get(f"/api/v1/history/zone/{zid}").status_code == 404


def test_AC32_retention_purge(api: Api, ids: Ids, db: Session) -> None:
    pid = ids.project("ANIA-EXP")
    old = now() - timedelta(days=366 * 6)
    for i in range(3):
        audit.record(
            db,
            AuditAction.update,
            AuditActor(None, Role.hse_officer),
            project_id=__import__("uuid").UUID(pid),
            details={"i": i},
            occurred_at=old + timedelta(days=i),
        )
    db.commit()
    _some_entries(api, ids)
    total_before = db.scalar(select(func.count()).select_from(AuditEntry))
    result = purge_audit(db)
    db.commit()
    assert result["purged"] == 3
    purges = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.retention_purge)
    ).all()
    assert len(purges) == 1
    details = purges[0].details or {}
    assert details["count"] == 3
    assert details["from"].startswith(old.date().isoformat())
    assert details["to"].startswith((old + timedelta(days=2)).date().isoformat())
    assert db.scalar(select(func.count()).select_from(AuditEntry)) == total_before - 3 + 1
    # The chain stays verifiable across the purged gap
    assert audit.verify_chain(db).ok is True


def test_rule39_export_of_audit_log_logged(api: Api) -> None:
    c = api.as_("faisal.harbi")
    res = c.get("/api/v1/exports/audit_log", params={"format": "csv"})
    assert res.status_code == 200
    entries = c.get("/api/v1/audit-log", params={"action": "export"}).json()["items"]
    assert entries and entries[0]["details"]["dataset"] == "audit_log"


def test_rule35_create_update_status_logged(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("noura.qahtani")
    res = c.post(
        f"/api/v1/projects/{ids.project('ANIA-EXP')}/sites",
        json={"code": "S-NEW", "name_en": "New", "name_ar": "جديد", "site_side": "landside"},
    )
    sid = res.json()["id"]
    c.post(f"/api/v1/sites/{sid}/transitions", json={"to_status": "inactive"})
    actions = [
        e.action
        for e in db.scalars(
            select(AuditEntry).where(AuditEntry.entity_id == sid).order_by(AuditEntry.seq)
        )
    ]
    assert actions == [AuditAction.create, AuditAction.archive]


def test_phase1_entity_history(api: Api, ids: Ids) -> None:
    noura = api.as_("noura.qahtani")
    inc = create_incident(noura, ids)
    case = add_case(noura, ids, inc["id"])
    ca = create_ca(noura, ids, "incident", inc["id"])
    for kind, eid in (
        ("incident", inc["id"]),
        ("injury_case", case["id"]),
        ("corrective_action", ca["id"]),
    ):
        res = noura.get(f"/api/v1/history/{kind}/{eid}")
        assert res.status_code == 200, (kind, res.text)
        assert res.json()["total"] >= 1, kind
    # Yousef (RBT-52 only) gets 404 for ANIA-EXP records, no hint
    yousef = api.as_("yousef.ghamdi")
    assert yousef.get(f"/api/v1/history/incident/{inc['id']}").status_code == 404
    assert yousef.get(f"/api/v1/history/injury_case/{case['id']}").status_code == 404
