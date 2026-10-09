"""6c-emergency-drills §9 ACs 1-10 (ERP, assembly points, contacts, settings)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.emergency_jobs import emergency_alerts
from app.models import EmergencyContact
from tests.conftest import Api
from tests.emer_helpers import API, ap, erp, err, notified, project, site, tick, zone

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")


def ok(res: Any, status: int = 200) -> dict[str, Any]:
    assert res.status_code == status, res.text
    return res.json()  # type: ignore[no-any-return]


def new_rev(c: Any, db: Session, pcode: str = "ANIA-EXP") -> dict[str, Any]:
    return ok(c.post(f"{API}/projects/{project(db, pcode).id}/erps", json={}), 201)


def submit(c: Any, eid: str) -> dict[str, Any]:
    return ok(c.post(f"{API}/erps/{eid}/transitions", json={"action": "submit"}))


ACCEPT = {"client_acceptance_ref": "ANIA-CL-ERP-TEST-04", "accepted_on": "2026-10-05"}


def test_AC1_AC5_approve_sod_and_frequency(api: Api, db: Session) -> None:
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    r4 = new_rev(noura, db)
    assert r4["erp_no"] == "ERP-ANIA-EXP-r4" and r4["status"] == "draft"
    sc = r4["scenarios"]
    fire = next(i for i, s in enumerate(sc) if s["scenario_code"] == "SC-FIRE")
    bad = [dict(s) for s in sc]
    bad[fire] = {**bad[fire], "drill_frequency_months": 9}
    res = noura.patch(f"{API}/erps/{r4['id']}", json={"scenarios": _inputs(bad), **ACCEPT})
    assert res.status_code == 422 and err(res) == "DRILL_FREQUENCY_TOO_LOW"
    bad[fire]["drill_frequency_months"] = 3
    ok(noura.patch(f"{API}/erps/{r4['id']}", json={"scenarios": _inputs(bad), **ACCEPT}))
    submit(noura, r4["id"])
    res = noura.post(f"{API}/erps/{r4['id']}/transitions", json={"action": "approve"})
    assert res.status_code == 403
    done = ok(faisal.post(f"{API}/erps/{r4['id']}/transitions", json={"action": "approve"}))
    assert done["status"] == "approved" and done["review_due_on"] == "2027-10-05"
    db.expire_all()
    assert erp(db, "ERP-ANIA-EXP-r3").status.value == "superseded"
    prog = ok(faisal.get(f"{API}/projects/{project(db, 'ANIA-EXP').id}/drill-programme"))
    land = [ln for ln in prog["lines"] if ln["site_code"] == "S-LAND"
            and ln["drill_type"] == "evacuation_full" and ln["shift_requirement"] == "any"
            and ln["announcement_requirement"] == "any" and ln["source"] != "repeat"]  # fmt: skip
    assert land and all(ln["frequency_months"] == 3 for ln in land), land
    # Faisal prepares r5 himself → SOD_CONFLICT
    r5 = new_rev(faisal, db)
    ok(faisal.patch(f"{API}/erps/{r5['id']}", json=ACCEPT))
    submit(faisal, r5["id"])
    res = faisal.post(f"{API}/erps/{r5['id']}/transitions", json={"action": "approve"})
    assert res.status_code == 422 and err(res) == "SOD_CONFLICT"


def _inputs(sc: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("scenario_code", "scenario_type", "site_ids", "alarm_signal_en", "alarm_signal_ar",
            "response_type", "response_summary_en", "response_summary_ar", "agencies",
            "drill_type", "drill_frequency_months", "rescue_plan_refs", "no_such_work")  # fmt: skip
    return [{k: s[k] for k in keys if k in s} for s in sc]


def test_AC2_AC3_incomplete_and_last_ap(api: Api, db: Session) -> None:
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    r4 = new_rev(noura, db)
    sc = [s for s in r4["scenarios"] if s["scenario_type"] != "height_rescue"]
    ok(noura.patch(f"{API}/erps/{r4['id']}", json={"scenarios": _inputs(sc), **ACCEPT}))
    arff = db.scalar(select(EmergencyContact).where(
        EmergencyContact.project_id == project(db, "ANIA-EXP").id,
        EmergencyContact.agency == "airport_arff"))  # fmt: skip
    assert arff is not None
    ok(noura.patch(f"{API}/emergency-contacts/{arff.id}", json={"active": False}))
    # AC3: Z-LAY1 served by no active AP
    for code in ("AP-SLAND-01", "AP-SLAND-02"):
        a = ap(db, code)
        a.zones_served = [z for z in a.zones_served if z != zone(db, "Z-LAY1").id]
    db.commit()
    submit(noura, r4["id"])
    res = faisal.post(f"{API}/erps/{r4['id']}/transitions", json={"action": "approve"})
    assert res.status_code == 422 and err(res) == "ERP_INCOMPLETE"
    missing = res.json()["detail"]["meta"]["missing"]
    assert {"scenario:height_rescue", "contact:airport_arff", "zone:Z-LAY1"} <= set(missing)


def test_AC3_deactivate_last_ap(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    ok(
        noura.patch(
            f"{API}/assembly-points/{ap(db, 'AP-SLAND-01').id}", json={"status": "inactive"}
        )
    )
    res = noura.patch(f"{API}/assembly-points/{ap(db, 'AP-SLAND-02').id}",
                      json={"status": "inactive"})  # fmt: skip
    assert res.status_code == 422 and err(res) == "ZONE_WITHOUT_ASSEMBLY_POINT"
    assert "Z-LAY1" in res.json()["detail"]["meta"]["zones"]


@pytest.mark.parametrize("zcode", ["Z-APR-21", "Z-ILS33R"])
def test_AC4_ap_restricted(api: Api, db: Session, zcode: str) -> None:
    body = {"ap_code": "AP-SAIR-09", "site_id": str(site(db, "S-AIR").id),
            "zone_id": str(zone(db, zcode).id), "location_en": "x", "location_ar": "x",
            "capacity_persons": 100, "zones_served": [str(zone(db, "Z-TWB").id)],
            "kind": "alternate"}  # fmt: skip
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/assembly-points", json=body
    )
    assert res.status_code == 422 and err(res) == "ASSEMBLY_POINT_IN_RESTRICTED_AREA"


def test_AC6_rescue_plan_ref(api: Api, db: Session) -> None:
    """ANIA-EXP has CSE permits issued in the last 90 days (Phase 3 seed)."""
    noura = api.as_("noura.qahtani")
    r4 = new_rev(noura, db)
    sc = [dict(s) for s in r4["scenarios"]]
    for s in sc:
        if s["scenario_type"] == "confined_space_rescue":
            s["rescue_plan_refs"], s["no_such_work"] = [], False
    res = noura.patch(f"{API}/erps/{r4['id']}", json={"scenarios": _inputs(sc)})
    assert res.status_code == 422 and err(res) == "RESCUE_PLAN_REF_REQUIRED"


def test_AC7_overdue_erp(api: Api, db: Session) -> None:
    pid = project(db, "RBT-52").id
    lina = api.as_("lina.haddad")
    erps = ok(lina.get(f"{API}/projects/{pid}/erps"))["items"]
    assert any(e["erp_no"] == "ERP-RBT-52-r2" and e["status"] == "approved" for e in erps)
    panel = ok(lina.get(f"{API}/projects/{pid}/emergency-action-panel"))
    assert "erp_overdue" in {i["kind"] for i in panel["items"]}
    t = tick(2026, 10, 6, 7, 5)
    emergency_alerts(db, t)
    db.commit()
    got = notified(db, "emergency_erp_review", t)
    assert {"lina.haddad", "faisal.harbi"} <= set(got), got


def test_AC8_plan_deficiency_and_new_revision(api: Api, db: Session) -> None:
    from app.services.emergency import common as ec

    e = erp(db, "ERP-ANIA-EXP-r3")
    t = tick(2026, 10, 6, 10, 1)
    ec.add_review_trigger(db, e.project_id, "drill_finding", "DRL-TEST")
    db.commit()
    db.refresh(e)
    assert e.review_required
    assert "faisal.harbi" in notified(db, "emergency_erp_review", t)
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    r4 = new_rev(noura, db)
    ok(noura.patch(f"{API}/erps/{r4['id']}", json=ACCEPT))
    submit(noura, r4["id"])
    done = ok(faisal.post(f"{API}/erps/{r4['id']}/transitions", json={"action": "approve"}))
    assert done["review_required"] is False


def test_AC9_AC10_settings(api: Api, db: Session) -> None:
    url = f"{API}/projects/{project(db, 'ANIA-EXP').id}/emergency-settings"
    faisal = api.as_("faisal.harbi")
    assert faisal.patch(url, json={"first_aider_ratio": 60}).status_code == 422
    res = faisal.patch(url, json={"drill_minimums": {"evacuation_full": 9}})
    assert res.status_code == 422 and err(res) == "SETTING_LOOSENING"
    got = ok(faisal.patch(url, json={"first_aider_ratio": 40,
                                     "drill_minimums": {"evacuation_full": 4}}))  # fmt: skip
    assert got["first_aider_ratio"] == 40 and got["drill_minimums"]["evacuation_full"] == 4
    assert api.as_("noura.qahtani").patch(url, json={"first_aider_ratio": 30}).status_code == 403
    rbt = f"{API}/projects/{project(db, 'RBT-52').id}/emergency-settings"
    res = faisal.patch(rbt, json={"emergency_ptw_enforcement_from": str(date(2026, 10, 6))})
    assert res.status_code == 422 and err(res) == "ERP_NOT_APPROVED"
