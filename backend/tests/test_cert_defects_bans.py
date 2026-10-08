"""4-third-party-cert §9 ACs 74-84 (defects, service status, blacklisting and bans)."""

from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EquipmentDefect, Notification, User
from tests.cert_helpers import (
    API,
    dep,
    ecert,
    err_code,
    item,
    project,
    riyadh,
    tpi,
    worker,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")


def defect(db: Session, no: str) -> EquipmentDefect:
    d = db.scalar(select(EquipmentDefect).where(EquipmentDefect.defect_no == no))
    assert d is not None, no
    return d


def raise_defect(api: Api, db: Session, who: str, tag: str, cat: str, **kw: Any) -> Any:
    body = {"equipment_id": str(item(db, tag).id), "source": "site_inspection", "category": cat,
            "description_en": "Test defect found on inspection", "physical_tag_applied": True, **kw}  # fmt: skip
    return api.as_(who).post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/defects", json=body)


def notified(db: Session, email: str, like: str) -> bool:
    uid = db.scalar(select(User.id).where(User.email == email))
    q = select(Notification.id).where(Notification.user_id == uid, Notification.title_en.like(like))
    return db.scalar(q) is not None


def test_P4AC74_Z5a_b_defect_due_alerts_and_overdue(db: Session) -> None:
    from app.cert_jobs import cert_alerts, cert_daily
    from app.core.clock import set_now

    d = defect(db, "DEF-ANIA-EXP-2026-0005")
    assert d.tpi_due_date == date(2026, 10, 31) and d.due_date == date(2026, 10, 24)

    def count(day: int) -> int:
        set_now(riyadh(2026, 10, day, 7))
        cert_alerts(db)
        db.flush()
        n = db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.title_en.like("Defect DEF-ANIA-EXP-2026-0005%"))
        )  # fmt: skip
        return int(n or 0)

    n16 = count(16)
    n17 = count(17)
    assert n17 > n16
    assert count(20) == n17
    n21 = count(21)
    assert n21 > n17
    n24 = count(24)
    assert n24 > n21
    it = db.get(type(item(db, "RW-MC-03")), d.equipment_id)
    assert it is not None and it.service_status.value != "out_of_service"
    set_now(datetime(2026, 10, 24, 21, 5, tzinfo=riyadh(2026, 1, 1).tzinfo))  # 2026-10-25 00:05
    cert_daily(db)
    db.flush()
    db.refresh(it)
    assert (it.service_status.value, it.service_status_reason.value) == (  # type: ignore[union-attr]
        "out_of_service",
        "defect_b_overdue",
    )


def test_P4AC75_Z5c_b_defect_default_due(api: Api, db: Session) -> None:
    res = raise_defect(api, db, "noura.qahtani", "FX-FL-A018", "B")
    assert res.status_code in (200, 201), res.text
    assert res.json()["due_date"] == "2026-10-20"


def test_P4AC76_Z5d_accessory_a_defect_cannot_be_repaired(api: Api, db: Session) -> None:
    res = raise_defect(api, db, "noura.qahtani", "FX-ACC-A055", "A")
    assert res.status_code in (200, 201), res.text
    did = res.json()["id"]
    res = api.as_("noura.qahtani").post(
        f"{API}/defects/{did}/rectification",
        json={"description": "Re-spliced the sling eye", "done_by_text": "Rigging loft",
              "done_at": "2026-10-06T06:30:00Z"},
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "ACCESSORY_REPAIR_NOT_ALLOWED", res.text
    w = defect(db, "DEF-ANIA-EXP-2026-0004")
    assert w.equipment_id == item(db, "WRS-NJ-0117").id
    assert item(db, "WRS-NJ-0117").service_status.value == "retired"


def test_P4AC77_return_to_service_sod_and_tpi_reinspection(api: Api, db: Session) -> None:
    d = defect(db, "DEF-ANIA-EXP-2026-0007")
    assert d.equipment_id == item(db, "RW-MEWP-07").id
    res = api.as_("ahmed.zahrani").post(
        f"{API}/defects/{d.id}/rectification",
        json={"description": "Replaced the platform overload sensor", "done_by_text": "RAWABI workshop",
              "done_at": "2026-10-06T06:00:00Z"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    res = api.as_("ahmed.zahrani").post(
        f"{API}/equipment/{d.equipment_id}/return-to-service", json={"note": "Repaired and tested"}
    )
    assert res.status_code in (403, 422), res.text
    if res.status_code == 422:
        assert err_code(res) == "SOD_CONFLICT"
    res = api.as_("noura.qahtani").post(
        f"{API}/defects/{d.id}/close",
        json={"method": "hse_verification", "note": "Checked on site"},
    )
    assert res.status_code == 422 and err_code(res) == "TPI_REINSPECTION_REQUIRED", res.text


def test_P4AC78_manual_tag_out_never_blocked(api: Api, db: Session) -> None:
    it = item(db, "GP-EX-05")
    res = api.as_("fahad.mutairi").post(
        f"{API}/equipment/{it.id}/tag-out",
        json={"project_id": str(project(db, "ANIA-EXP").id), "reason": "boom cylinder weeping",
              "physical_tag_applied": True},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    assert res.json()["service_status"] == "out_of_service"
    db.expire_all()
    from app.services.cert import alerts

    d = dep(db, "GP-EX-05")
    reps = alerts.reps(db, d.project_id, d.engagement_id)  # GULFPAVE's Contractor HSE Rep(s)
    assert reps
    for uid in reps | alerts.officers(db, d.project_id):
        assert db.scalar(select(Notification.id).where(
            Notification.user_id == uid, Notification.title_en.like("%tagged out%"))), uid  # fmt: skip
    assert notified(db, "noura.qahtani@example.com", "%tagged out%")


def test_P4AC79_incident_prompt_changes_nothing(api: Api, db: Session) -> None:
    from app.core.hse_enums import Agency
    from app.models import CorrectiveAction, Incident, InjuryCase

    case = db.scalar(select(InjuryCase).limit(1))
    assert case is not None
    case.agency = Agency.mewp
    db.commit()
    inc = db.get(Incident, case.incident_id)
    assert inc is not None
    before = (inc.updated_at, db.scalar(select(func.count()).select_from(CorrectiveAction)))
    res = api.as_("noura.qahtani").get(f"{API}/incidents/{inc.id}/defect-prompt")
    if res.status_code == 404:  # the incident is on another project: use the manager
        res = api.as_("faisal.harbi").get(f"{API}/incidents/{inc.id}/defect-prompt")
    assert res.status_code == 200, res.text
    assert res.json()["prompt"] is True and res.json()["agency"] == "mewp"
    db.expire_all()
    inc = db.get(Incident, case.incident_id)
    assert inc is not None
    assert (inc.updated_at, db.scalar(select(func.count()).select_from(CorrectiveAction))) == before


def test_P4AC80_blacklisting_is_manager_only_with_reason(api: Api, db: Session) -> None:
    it = item(db, "FX-FL-A018")
    url = f"{API}/equipment/{it.id}/blacklist"
    ok_text = "Forged load test certificate found (test)."
    res = api.as_("noura.qahtani").post(url, json={"reason_code": "other", "reason_text": ok_text})
    assert res.status_code == 403, res.text
    res = api.as_("faisal.harbi").post(
        url, json={"reason_code": "other", "reason_text": "too short"}
    )
    assert res.status_code == 422, res.text


def test_P4AC81_blacklisted_item_cascade_and_k78(api: Api, db: Session) -> None:
    from app.models import QrToken

    it = item(db, "SH-TH-02")
    assert it.service_status.value == "blacklisted"
    d = dep(db, "SH-TH-02")
    assert d.status.value == "demobilised"
    toks = db.scalars(select(QrToken).where(QrToken.subject_id == d.id)).all()
    assert toks and all(t.status.value == "revoked" for t in toks)
    res = api.as_("faisal.harbi").get(
        f"{API}/kpi/certification",
        params={
            "project_id": str(project(db, "ANIA-EXP").id),
            "period": "month",
            "anchor": "2026-09-15",
        },
    )
    assert res.status_code == 200, res.text
    k78 = next(m for m in res.json()["metrics"] if m["metric"] == "K-78")
    assert {c["key"]: c["value"] for c in k78["components"]}["equipment"] == "1"


def test_P4AC82_banned_holder_and_bl5_message(api: Api, db: Session) -> None:
    w = worker(db, "WKR-000022")
    status = w.status
    body = {"worker_id": str(w.id), "cert_type": "SCAFFOLDER", "tpi_id": str(tpi(db, "DSPC").id),
            "cert_no": "DSPC-SC-TEST-26-1010", "issued_on": "2026-10-01",
            "name_as_printed": w.full_name_en, "id_on_card": {"shown": False}}  # fmt: skip
    res = api.as_("ahmed.zahrani").post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/personnel-certificates", json=body
    )
    assert res.status_code == 422 and err_code(res) == "HOLDER_BANNED", res.text
    assert "Certification not accepted on this organisation" in res.text
    view = api.as_("ahmed.zahrani").get(f"{API}/workers/{w.id}/certificates")
    assert view.status_code == 200, view.text
    assert view.json()["banned"] is True and "reason" not in str(view.json().get("ban_message_en"))
    db.expire_all()
    assert worker(db, "WKR-000022").status == status


def test_P4AC83_tpi_blacklist_revokes_and_quarantine_history(api: Api, db: Session) -> None:
    c = ecert(db, "QC-EQ-TEST-26-0042")
    assert c.status.value == "revoked"
    assert c.status_reason is not None and c.status_reason.value == "tpi_blacklisted"
    it = item(db, "GP-FL-03")
    res = api.as_("faisal.harbi").get(f"{API}/equipment/{it.id}/status-events")
    assert res.status_code == 200, res.text
    evs = [(e["to_status"], e["occurred_at"][:10]) for e in res.json()["items"]]
    assert ("quarantined", "2026-09-20") in evs and ("in_service", "2026-09-23") in evs


def test_P4AC84_lifting_tpi_blacklist_suspends(api: Api, db: Session) -> None:
    t = tpi(db, "QUICKCERT")
    res = api.as_("faisal.harbi").post(
        f"{API}/tpis/{t.id}/transitions",
        json={"to_status": "suspended", "reason": "Lift blacklist after review (test)."},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "suspended"
    db.expire_all()
    assert ecert(db, "QC-EQ-TEST-26-0042").status.value == "revoked"
