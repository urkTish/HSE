"""Spec 2-access-permits §9 AC32-AC40 (ADPs, offences, vehicles, AVPs), X3 and X5."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app import access_jobs
from app.core.access_enums import CredentialReason, LimitingFactor, ValidityStatus
from app.core.clock import frozen, set_now
from app.core.enums import NotificationKind
from app.services.access import driving, lifecycle
from tests.access_helpers import (
    API,
    NOON,
    adp,
    airport_pass,
    avp,
    deployment,
    notifications,
    project_id,
    riyadh,
    vehicle,
    worker,
)
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def adp_body(db: Session, name: str, category: str) -> dict[str, object]:
    return {
        "deployment_id": str(deployment(db, name).id),
        "category": category,
        "vehicle_classes": ["light"],
        "licence_issuer": "ksa",
        "licence_class": "private",
        "licence_expiry_date": "2029-01-01",
    }


def issue_adp(api: Api, ids: Ids, db: Session, name: str, category: str, rtf: bool) -> object:
    n = api.as_("noura.qahtani")
    res = n.post(f"{API}/projects/{ids.project('ANIA-EXP')}/adps", json=adp_body(db, name, category))
    assert res.status_code == 201, res.text
    aid = res.json()["id"]
    res = n.patch(
        f"{API}/adps/{aid}",
        json={"theory_test_date": "2026-10-01", "theory_score_pct": "92",
              "practical_test_date": "2026-10-02", "practical_result": "passed",
              "practical_examiner": "Examiner TEST", "practical_included_manoeuvring": True,
              "rtf_competence": rtf},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    return n.post(
        f"{API}/adps/{aid}/issue",
        json={"adp_no": "ADP-OEXX-26-TEST-01", "issued_on": "2026-10-06",
              "own_valid_until": "2028-10-05"},
    )  # fmt: skip


def test_P2AC32_escorted_pass_cannot_hold_adp(api: Api, ids: Ids, db: Session) -> None:
    res = issue_adp(api, ids, db, "Abdul Karim Mia", "apron", True)
    assert res.status_code == 422, res.text  # type: ignore[attr-defined]
    assert res.json()["detail"]["code"] == "ADP_PASS_REQUIRED"  # type: ignore[attr-defined]


def test_P2AC33_manoeuvring_needs_rtf(api: Api, ids: Ids, db: Session) -> None:
    res = issue_adp(api, ids, db, "Noura Al-Qahtani", "manoeuvring", False)
    assert res.status_code == 422, res.text  # type: ignore[attr-defined]
    assert res.json()["detail"]["code"] == "RTF_REQUIRED"  # type: ignore[attr-defined]


def test_P2AC34_X5_points_suspension_period(api: Api, db: Session) -> None:
    a = adp(db, "Jomar Santos")
    assert a.validity_status == ValidityStatus.suspended
    reasons = {s.reason_code for s in lifecycle.open_suspensions(db, a)}
    assert reasons == {CredentialReason.points_threshold}
    assert lifecycle.open_suspensions(db, a)[0].suspension_end == date(2026, 10, 13)
    body = {"reason_code": "points_threshold", "reason_text": "Suspension period served in full"}
    set_now(riyadh(2026, 10, 13, 10))
    res = api.as_("noura.qahtani").post(f"{API}/credentials/adp/{a.id}/reinstate", json=body)
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "SUSPENSION_PERIOD_RUNNING"
    set_now(riyadh(2026, 10, 14, 10))
    res = api.as_("noura.qahtani").post(f"{API}/credentials/adp/{a.id}/reinstate", json=body)
    assert res.status_code == 200, res.text
    db.expire_all()
    assert adp(db, "Jomar Santos").validity_status == ValidityStatus.active


def test_P2AC35_X5_points_window(db: Session) -> None:
    w = worker(db, "Jomar Santos")
    pid = project_id(db, "ANIA-EXP")
    assert driving.points_12m(db, w.id, pid, date(2026, 9, 14), 365)[0] == 12
    assert driving.points_12m(db, w.id, pid, date(2026, 11, 20), 365)[0] == 9


def test_P2AC36_off05_suspends_alerts_manager_and_second_revokes(
    api: Api, ids: Ids, db: Session
) -> None:
    w = worker(db, "Saad Al-Dosari")
    n = api.as_("noura.qahtani")

    def off(at: str) -> list[str]:
        res = n.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/airside-offences",
            json={"worker_id": str(w.id), "offence_code": "OFF-05", "offence_at": at,
                  "zone_id": ids.zone("Z-APR-21")},
        )  # fmt: skip
        assert res.status_code == 201, res.text
        actions: list[str] = res.json()["resulting_actions"]
        return actions

    assert "adp_suspended_violation" in off("2026-10-05T08:00:00Z")
    db.expire_all()
    a = adp(db, "Saad Al-Dosari")
    assert a.validity_status == ValidityStatus.suspended
    who = {str(x.user_id) for x in notifications(db, NotificationKind.adp_suspended, a.id)}
    assert ids.user("faisal.harbi") in who
    assert "adp_revoked" in off("2026-10-06T07:00:00Z")
    db.expire_all()
    assert adp(db, "Saad Al-Dosari").validity_status == ValidityStatus.revoked


def test_P2AC37_pass_suspension_cascades_to_adp(api: Api, db: Session) -> None:
    ps = airport_pass(db, "Rajesh Nair")
    n = api.as_("noura.qahtani")
    res = n.post(
        f"{API}/credentials/airport_pass/{ps.id}/suspend",
        json={"reason_code": "security_request", "reason_text": "Security office request TEST"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    a = adp(db, "Rajesh Nair")
    assert a.validity_status == ValidityStatus.suspended
    assert {s.reason_code for s in lifecycle.open_suspensions(db, a)} == {
        CredentialReason.dependency_invalid
    }
    res = n.post(
        f"{API}/credentials/airport_pass/{ps.id}/reinstate",
        json={"reason_code": "security_request", "reason_text": "Security office cleared TEST"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    assert adp(db, "Rajesh Nair").validity_status == ValidityStatus.active


def test_P2AC38_X3_avp_insurance_dependency(api: Api, ids: Ids, db: Session) -> None:
    a = avp(db, "VEH-0002")
    assert a.effective_valid_until == date(2026, 10, 20)
    assert a.limiting_factor == LimitingFactor.insurance_expiry
    with frozen(NOON):
        access_jobs.credential_alerts(db)
        db.commit()
    rows = notifications(db, NotificationKind.avp_expiry, a.id)
    assert rows and "(14 days" in rows[0].title_en
    with frozen(riyadh(2026, 10, 21, 0, 5)):
        access_jobs.access_daily(db)
        db.commit()
    db.expire_all()
    a = avp(db, "VEH-0002")
    assert a.validity_status == ValidityStatus.suspended
    assert {s.reason_code for s in lifecycle.open_suspensions(db, a)} == {
        CredentialReason.vehicle_document_expired
    }
    set_now(riyadh(2026, 10, 21, 9))
    res = api.as_("noura.qahtani").patch(
        f"{API}/vehicles/{vehicle(db, 'VEH-0002').id}", json={"insurance_expiry": "2027-10-20"}
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    a = avp(db, "VEH-0002")
    assert a.validity_status == ValidityStatus.active
    assert a.effective_valid_until == date(2027, 1, 15)  # MVPI now limits


def test_P2AC39_checklist_na_not_allowed(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    res = n.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/avps",
        json={"vehicle_id": str(vehicle(db, "VEH-0004").id), "areas": ["apron"]},
    )
    assert res.status_code == 201, res.text
    aid = res.json()["id"]
    checklist = {k: "pass" for k in (
        "amber_beacon", "company_marking", "chequered_flag_or_marking", "radio_fitted",
        "fire_extinguisher", "spill_kit", "fod_bin", "tyres_brakes", "reverse_alarm", "lights",
        "no_loose_items", "height_marking")}  # fmt: skip
    checklist["amber_beacon"] = "n.a."
    res = n.patch(
        f"{API}/avps/{aid}",
        json={"inspection_date": "2026-10-05", "inspector": "Inspector TEST",
              "inspection_result": "passed", "checklist": checklist},
    )  # fmt: skip
    if res.status_code == 200:
        res = n.post(
            f"{API}/avps/{aid}/issue",
            json={"avp_no": "AVP-OEXX-26-TEST-1", "sticker_no": "STK-TEST-1",
                  "issued_on": "2026-10-06", "own_valid_until": "2027-10-05"},
        )  # fmt: skip
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "AVP_PRECONDITION"
    assert "amber_beacon" in res.text


def test_P2AC40_duplicate_plate_rejected(api: Api, ids: Ids) -> None:
    body = {
        "engagement_id": ids.engagement("RAWABI"),
        "owner_type": "company",
        "category": "pickup",
        "plate_type": "private",
        "plate_letters_ar": "ح ط ر",
        "plate_letters_en": "JTR",
        "plate_digits": "9012",
        "fleet_no": "RW-LV-99",
        "serial_or_vin": "TESTVXN0000000099",
        "make_model": "Pickup TEST",
        "year": 2022,
        "colour": "white",
        "travel_height_m": "1.90",
        "max_working_height_m_agl": "1.90",
        "istimara_expiry": "2027-06-30",
        "insurance_policy_no": "POL-TEST-99",
        "insurance_expiry": "2027-06-30",
        "mvpi_expiry": "2027-06-30",
    }
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/vehicles", json=body
    )
    assert res.status_code == 409, res.text
