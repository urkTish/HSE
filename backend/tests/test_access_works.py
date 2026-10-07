"""Spec 2-access-permits §9 AC41-AC53 (NOTAM, obstacle clearances, WAPs, ops suspension), X4."""

from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app import access_jobs
from app.core.access_enums import (
    CredentialReason,
    CrewMemberStatus,
    ObstacleStatus,
    WapStatus,
)
from app.core.clock import frozen, set_now
from app.core.enums import EmployerType, NotificationKind, Role, UserStatus
from app.models import RoleAssignment, User, Wap, WapCrew
from tests.access_helpers import (
    API,
    notam,
    notifications,
    obstacle,
    riyadh,
    utc,
    wap,
    worker,
)
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")
ALL_DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def preview(api: Api, ids: Ids, height: str, zone: str = "Z-TWB") -> dict[str, Any]:
    res = api.as_("noura.qahtani").post(
        f"{API}/obstacle-clearances/preview",
        json={"project_id": ids.project("ANIA-EXP"), "zone_id": ids.zone(zone),
              "equipment_type": "mobile_crane", "equipment_desc": "50 t mobile crane TEST",
              "location_lat": "24.5", "location_lng": "46.6",
              "location_desc": "TWB TEST", "ground_elevation_m_amsl": "612.40",
              "max_height_m_agl": height, "ols_surface": "inner_horizontal",
              "ols_limit_m_amsl": "642.50", "requested_from": "2026-11-01",
              "requested_to": "2026-11-05"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out.get("heights", out)


def test_P2AC41_late_notam_request_counts_against_k59(api: Api, ids: Ids, db: Session) -> None:
    n = notam(db, "2026-0014")
    assert n.late_request is True
    res = api.as_("faisal.harbi").get(
        f"{API}/kpi/metrics/K-59",
        params={"project_id": ids.project("ANIA-EXP"), "period": "month", "anchor": "2026-10-01",
                "as_of": "2026-10-06"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    k = res.json()["kpi"]
    assert float(k["denominator"]) >= 1
    assert float(k["numerator"]) <= float(k["denominator"]) - 1


def test_P2AC42_X4c_penetration_and_conditions(api: Api, ids: Ids, db: Session) -> None:
    o = obstacle(db, "2026-0009")
    assert str(o.top_elevation_m_amsl) == "647.40"
    assert str(o.penetration_m) == "4.90"
    h = preview(api, ids, "35.00")
    assert h["top_elevation_m_amsl"] == "647.40"
    assert h["penetration_m"] == "4.90" and h["penetration_ft"] == "16.08"
    assert "ols_penetration" in h["clearance_reasons"]
    n = api.as_("noura.qahtani")
    res = n.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/obstacle-clearances",
        json={"zone_id": ids.zone("Z-TWB"), "engagement_id": ids.engagement("RAWABI"),
              "equipment_type": "mobile_crane", "equipment_desc": "50 t mobile crane TEST",
              "location_lat": "24.5", "location_lng": "46.6",
              "location_desc": "TWB TEST", "ground_elevation_m_amsl": "612.40",
              "max_height_m_agl": "35.00", "ols_surface": "inner_horizontal",
              "ols_limit_m_amsl": "642.50", "requested_from": "2026-11-20",
              "requested_to": "2026-11-25"},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    oid = res.json()["id"]
    res = n.post(f"{API}/obstacle-clearances/{oid}/transitions", json={"to_status": "submitted"})
    assert res.status_code == 200, res.text
    res = n.post(
        f"{API}/obstacle-clearances/{oid}/decision",
        json={"decision": "approved_with_conditions", "authority_ref": "GACA-OBS-TEST-0099",
              "conditions": ["lower_at_night"], "valid_from": "2026-11-20",
              "valid_to": "2026-11-25", "linked_ntm_ids": []},
    )  # fmt: skip
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "OB_CONDITIONS_REQUIRED"


def test_P2AC43_X4a_obs0004(db: Session, api: Api) -> None:
    o = obstacle(db, "2026-0004")
    res = api.as_("noura.qahtani").get(f"{API}/obstacle-clearances/{o.id}")
    assert res.status_code == 200, res.text
    h = res.json()["heights"]
    assert h["top_elevation_m_amsl"] == "644.40"
    assert h["margin_m"] == "10.60" and h["margin_ft"] == "34.78"
    assert h["clearance_reasons"] == ["zone_height_exceeded", "operator_requires"]


def test_P2AC44_X4bd_buffer(api: Api, ids: Ids) -> None:
    h25 = preview(api, ids, "25.00")
    assert h25["margin_m"] == "5.10" and h25["margin_ft"] == "16.73"
    assert "within_ols_buffer" not in h25["clearance_reasons"]
    h30 = preview(api, ids, "30.00")
    assert h30["top_elevation_m_amsl"] == "642.40"
    assert "within_ols_buffer" in h30["clearance_reasons"]


def run_jobs(db: Session, at: Any, daily: bool = False) -> None:
    db.expire_all()
    with frozen(at):
        if daily:
            access_jobs.access_daily(db)
        access_jobs.access_minute(db)
        db.commit()
    db.expire_all()


def test_P2AC45_AC46_obs_suspends_then_notam_issue_activates_wap(api: Api, db: Session) -> None:
    run_jobs(db, riyadh(2026, 10, 8, 0, 5), daily=True)
    o = obstacle(db, "2026-0007")
    assert o.status == ObstacleStatus.suspended and o.system_suspended
    w = wap(db, "2026-0035")
    assert w.status == WapStatus.approved
    codes = {b["code"] for b in w.blockers}
    assert {"NOTAM_NOT_ISSUED", "OBS_NOT_ACTIVE"} <= codes
    run_jobs(db, riyadh(2026, 10, 8, 7, 0))
    assert notifications(db, NotificationKind.wap_blocked, w.id)
    set_now(riyadh(2026, 10, 8, 6, 30))
    n = notam(db, "2026-0014")
    res = api.as_("noura.qahtani").post(
        f"{API}/notam-requests/{n.id}/transitions",
        json={"to_status": "issued", "notam_number": "A1009/26", "notam_type": "N",
              "effective_from_utc": "2026-10-08T04:00:00Z",
              "effective_to_utc": "2026-10-12T13:00:00Z",
              "item_e_text": "ILS RWY 33R NOT AVBL DUE WIP"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    run_jobs(db, riyadh(2026, 10, 8, 7, 1), daily=True)
    assert obstacle(db, "2026-0007").status != ObstacleStatus.suspended
    assert wap(db, "2026-0035").status == WapStatus.active


def wap_body(ids: Ids, db: Session, **over: Any) -> dict[str, Any]:
    tariq = worker(db, "Tariq Mahmood")
    body: dict[str, Any] = {
        "site_id": ids.site("S-AIR"),
        "zone_ids": [ids.zone("Z-APR-21")],
        "engagement_id": ids.engagement("GULFPAVE"),
        "supervisor_worker_id": str(tariq.id),
        "scope_en": "Joint sealing on stand 23 TEST",
        "scope_ar": "أعمال اختبار",
        "valid_from": "2026-10-07",
        "valid_to": "2026-10-10",
        "windows": [{"start_local": "06:00", "end_local": "18:00", "weekdays": ALL_DAYS}],
        "crew": [{"worker_id": str(tariq.id), "crew_role": "supervisor"}],
    }
    body.update(over)
    return body


def submitted_wap(api: Api, ids: Ids, db: Session) -> str:
    a = api.as_("ahmed.zahrani")
    res = a.post(f"{API}/projects/{ids.project('ANIA-EXP')}/waps", json=wap_body(ids, db))
    assert res.status_code == 201, res.text
    wid = res.json()["id"]
    res = a.post(f"{API}/waps/{wid}/transitions", json={"to_status": "submitted"})
    assert res.status_code == 200, res.text
    return str(wid)


def rawabi_issuer(db: Session, ids: Ids) -> None:
    import uuid

    from app.core.clock import now
    from app.core.config import get_settings
    from app.core.security import hash_password
    from tests.conftest import PASSWORD

    u = User(
        id=uuid.uuid4(),
        email="rawabi.issuer@example.com",
        full_name_en="Rawabi Issuer TEST",
        full_name_ar="مصدر تصاريح",
        employer_type=EmployerType.contractor,
        employer_contractor_id=uuid.UUID(ids.contractor("RAWABI")),
        preferred_language="en",
        status=UserStatus.active,
        password_hash=hash_password(PASSWORD),
        privacy_notice_version=get_settings().privacy_notice_version,
        search_text="rawabi issuer",
        activated_at=now(),
    )
    db.add(u)
    db.flush()
    db.add(
        RoleAssignment(
            id=uuid.uuid4(),
            user_id=u.id,
            role=Role.permit_issuer,
            project_id=uuid.UUID(ids.project("ANIA-EXP")),
            site_ids=[],
            valid_from=now().date(),
        )
    )
    db.commit()


def test_P2AC47_segregation_of_duties(api: Api, ids: Ids, db: Session) -> None:
    rawabi_issuer(db, ids)
    wid = submitted_wap(api, ids, db)
    res = api.as_("rawabi.issuer").post(
        f"{API}/waps/{wid}/transitions", json={"to_status": "approved"}
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "SOD_CONFLICT"
    own = submitted_wap(api, ids, db)
    db.execute(
        update(Wap).where(Wap.id == own).values(requested_by_user_id=ids.user("khalid.otaibi"))
    )
    db.commit()
    k = api.as_("khalid.otaibi")
    res = k.post(f"{API}/waps/{own}/transitions", json={"to_status": "approved"})
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "SOD_CONFLICT"
    res = k.post(f"{API}/waps/{wid}/transitions", json={"to_status": "approved"})
    assert res.status_code == 200, res.text


def test_P2AC48_wap_max_days(api: Api, ids: Ids, db: Session) -> None:
    res = api.as_("ahmed.zahrani").post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/waps",
        json=wap_body(ids, db, valid_from="2026-10-07", valid_to="2026-11-06"),
    )
    assert res.status_code == 422, res.text


def test_P2AC49_suspended_contractor_cannot_request_wap(api: Api, ids: Ids, db: Session) -> None:
    body = wap_body(
        ids, db, site_id=ids.site("S-TWR"), zone_ids=[ids.zone("Z-TC01")],
        engagement_id=ids.engagement("DLIFT"),
        supervisor_worker_id=str(worker(db, "Bikash Rai").id),
        crew=[{"worker_id": str(worker(db, "Bikash Rai").id), "crew_role": "supervisor"}],
    )  # fmt: skip
    res = api.as_("faisal.harbi").post(f"{API}/projects/{ids.project('RBT-52')}/waps", json=body)
    assert res.status_code == 403, res.text
    assert res.json()["detail"]["code"] == "CONTRACTOR_SUSPENDED"


def test_P2AC50_lvp_suspends_manoeuvring_wap_and_fod_handback(
    api: Api, ids: Ids, db: Session
) -> None:
    set_now(riyadh(2026, 10, 6, 23, 30))
    k = api.as_("khalid.otaibi")
    res = k.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/ops-events",
        json={"type": "lvp", "site_id": ids.site("S-AIR"), "zone_ids": [], "source": "aocc",
              "source_ref": "AOCC-LOG-TEST-301"},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    eid = res.json()["id"]
    run_jobs(db, riyadh(2026, 10, 6, 23, 31))
    w31, w33 = wap(db, "2026-0031"), wap(db, "2026-0033")
    assert w31.status == WapStatus.suspended
    assert w31.suspension_reason == CredentialReason.ops_suspension
    assert w33.status == WapStatus.active
    assert k.post(f"{API}/ops-events/{eid}/end", json={}).status_code == 200
    run_jobs(db, riyadh(2026, 10, 6, 23, 45))
    assert wap(db, "2026-0031").status == WapStatus.suspended
    url = f"{API}/waps/{w31.id}/transitions"
    res = k.post(url, json={"to_status": "active", "reason": "LVP ended, works resume"})
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "FOD_HANDBACK_REQUIRED"
    set_now(riyadh(2026, 10, 6, 23, 50))
    res = k.post(
        url,
        json={"to_status": "active", "reason": "LVP ended, works resume",
              "fod_check": {"checked_by_user_id": ids.user("khalid.otaibi"),
                            "checked_at": "2026-10-06T20:44:00Z", "result": "clear"}},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"


def test_P2AC51_crew_member_excluded_at_window_start(db: Session) -> None:
    run_jobs(db, riyadh(2026, 10, 14, 0, 5), daily=True)
    run_jobs(db, riyadh(2026, 10, 14, 23, 0))
    w = wap(db, "2026-0031")
    abdul = worker(db, "Abdul Karim Mia")
    crew = db.query(WapCrew).filter(WapCrew.wap_id == w.id, WapCrew.worker_id == abdul.id).one()
    assert crew.status == CrewMemberStatus.excluded
    assert "INDUCTION_EXPIRED" in crew.exclusion_reasons
    assert w.status == WapStatus.active
    assert notifications(db, NotificationKind.wap_crew_excluded, w.id)


def test_P2AC52_cancelled_notam_suspends_wap(api: Api, db: Session) -> None:
    n = notam(db, "2026-0012")
    res = api.as_("noura.qahtani").post(
        f"{API}/notam-requests/{n.id}/transitions",
        json={"to_status": "cancelled", "reason": "Works finished early TEST"},
    )
    assert res.status_code == 200, res.text
    run_jobs(db, utc(2026, 10, 6, 9, 1))
    w = wap(db, "2026-0031")
    assert w.status == WapStatus.suspended
    assert w.suspension_reason == CredentialReason.dependency_invalid


def test_P2AC53_viewer_sees_crew_count_not_names(api: Api, db: Session) -> None:
    w = wap(db, "2026-0031")
    res = api.as_("sarah.mitchell").get(f"{API}/waps/{w.id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["crew_count"] == 9
    for name in ("Tariq", "Rajesh", "Abdul Karim", "WKR-0000"):
        assert name not in res.text
