"""6c-emergency-drills §9 ACs 54-59 (Phase 3 integration PE-1…PE-6, 3-ptw v1.4 §11.4)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.emergency_enums import AssetStatus, AssetType
from app.models import EmergencyAsset, Permit
from app.schemas.permits import ShiftStartFields
from app.services.emergency import ptw as eptw
from app.services.ptw import evaluation
from tests.conftest import Api
from tests.emer_helpers import API, expect, local, project, team, zone
from tests.ptw_helpers import GOOD_GAS, fx, gas_test, hw_fx, permit, resume, world
from tests.test_emer_drills import act, ok, plan

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")


def codes(p: Permit, db: Session, at: Any = None) -> tuple[list[str], list[str]]:
    res = evaluation.evaluate(db, p, evaluation.Ctx(at=at or now(), start=True))
    return [b["code"] for b in res.blockers], [w["code"] for w in res.warnings]


def reason(p: Permit) -> str:
    return str(getattr(p.status_reason, "value", p.status_reason))


def test_AC54_drill_suspend_and_receiver_resume(api: Api, db: Session) -> None:
    n = world(db)
    fahad = api.as_("fahad.mutairi")
    d = ok(plan(fahad, db), 201)
    ok(act(fahad, d["id"], "start"))
    p = permit(db, "PTW-ANIA-EXP-2026-0413")
    db.refresh(p)
    assert p.status.value == "suspended" and reason(p) == "emergency_drill"
    body = ShiftStartFields.model_validate({"crew_present": n.crew_present(p),
                                            "ambient_temp_c": "30.0"})  # fmt: skip
    expect("TRANSITION_CONDITION_NOT_MET",
           lambda: eptw.drill_resume(db, n.p("faris.anazi"), p.id, body), 409)  # fmt: skip
    db.rollback()
    # conduct the drill (counts, timings) then wait past the gas break
    from tests.emer_helpers import drill as get_drill

    x = get_drill(db, d["drill_no"])
    m = x.muster_id
    noura = api.as_("noura.qahtani")
    from tests.emer_helpers import eng

    set_now(now() + timedelta(minutes=5))
    ok(fahad.patch(f"{API}/drills/{d['id']}", json={"timeline": {
        "evacuation_complete_at": now().isoformat()}}))  # fmt: skip
    rows = [{"engagement_id": str(eng(db, "ANIA-EXP", "RAWABI").id), "expected": 5,
             "accounted": 5}]  # fmt: skip
    ok(noura.put(f"{API}/musters/{m}/counts", json={"rows": rows}))
    ok(fahad.patch(f"{API}/drills/{d['id']}", json={"timeline": {
        "all_clear_at": now().isoformat()}}))  # fmt: skip
    ok(act(fahad, d["id"], "conduct"))
    set_now(now() + timedelta(minutes=70))
    db.expire_all()
    p = permit(db, "PTW-ANIA-EXP-2026-0413")
    expect("GAS_TEST_EXPIRED",
           lambda: eptw.drill_resume(db, n.p("faris.anazi"), p.id, body), 422)  # fmt: skip
    db.rollback()
    t = now()
    gas_test(n, p, t, "pre_entry", GOOD_GAS)
    set_now(t + timedelta(minutes=1))
    eptw.drill_resume(db, n.p("faris.anazi"), p.id, body)
    db.commit()
    db.refresh(p)
    assert p.status.value == "active"


def test_AC55_event_resume(api: Api, db: Session) -> None:
    n = world(db)
    from tests.test_emer_events import declare

    ev = ok(declare(api.as_("fahad.mutairi"), db, "S-LAND",
                    zone_ids=[str(zone(db, "Z-LAY1").id)]), 201)  # fmt: skip
    p = permit(db, "PTW-ANIA-EXP-2026-0412")
    db.refresh(p)
    assert reason(p) == "emergency"
    body = ShiftStartFields.model_validate({"crew_present": n.crew_present(p)})
    expect("INVALID_TRANSITION",
           lambda: eptw.drill_resume(db, n.p("ramesh.kumar"), p.id, body), 422)  # fmt: skip
    db.rollback()
    t = now() + timedelta(minutes=5)
    expect("TRANSITION_CONDITION_NOT_MET",
           lambda: resume(n, p, "khalid.otaibi", "ramesh.kumar", t), 409)  # fmt: skip
    db.rollback()
    set_now(t)
    ok(api.as_("fahad.mutairi").post(f"{API}/emergency-events/{ev['id']}/transitions",
                                     json={"action": "all_clear"}))  # fmt: skip
    resume(n, p, "khalid.otaibi", "ramesh.kumar", t + timedelta(minutes=1))
    assert p.status.value == "active"


def test_AC56_rescue_blockers(db: Session) -> None:
    p = permit(db, "PTW-ANIA-EXP-2026-0413")
    b, _ = codes(p, db)
    assert not {"RESCUE_DRILL_OVERDUE", "RESCUE_TEAM_NOT_REGISTERED"} & set(b)
    b, _ = codes(p, db, local(2026, 10, 20, 9))
    assert "RESCUE_DRILL_OVERDUE" in b
    t = team(db, "RT-ANIA-CSE-01")
    t.status = t.status.__class__("inactive")
    db.flush()
    b, _ = codes(p, db)
    assert "RESCUE_TEAM_NOT_REGISTERED" in b
    rbt = permit(db, "PTW-RBT-52-2026-0287")
    b, w = codes(rbt, db, local(2026, 10, 20, 9))
    assert not {"RESCUE_DRILL_OVERDUE", "RESCUE_TEAM_NOT_REGISTERED"} & set(b)
    assert "HEIGHT_RESCUE_NOT_READY" not in w  # RBT-52: enforcement null


WAH = {
    "work_type": "work_at_height", "max_fall_height_m": "8.00", "access_method": ["mewp"],
    "fall_protection": "arrest_srl", "srl_required_clearance_m": "2.40", "anchor_rating_kn": "22.2",
    "available_clearance_m": "4.00", "drop_zone_controlled": True, "tool_tethering": True,
}  # fmt: skip


def test_AC57_height_rescue_warning(db: Session) -> None:
    n = world(db)
    p = fx(n, zones=("Z-LAY1",), types=("work_at_height",), sections=[WAH])
    _, w = codes(p, db)
    assert "HEIGHT_RESCUE_NOT_READY" not in w  # RT-ANIA-WAH-01 covers S-LAND and is current
    t = team(db, "RT-ANIA-WAH-01")
    t.status = t.status.__class__("inactive")
    db.flush()
    b, w = codes(p, db)
    assert "HEIGHT_RESCUE_NOT_READY" in w and "HEIGHT_RESCUE_NOT_READY" not in b


def test_AC58_no_ready_extinguisher(db: Session) -> None:
    n = world(db)
    p = hw_fx(n, zone="Z-LAY1")
    _, w = codes(p, db)
    assert "NO_READY_EXTINGUISHER" not in w
    for a in db.scalars(select(EmergencyAsset).where(
            EmergencyAsset.zone_id == zone(db, "Z-LAY1").id,
            EmergencyAsset.asset_type == AssetType.fire_extinguisher)):  # fmt: skip
        a.status, a.status_changed_on = AssetStatus.out_of_service, None
    db.flush()
    _, w = codes(p, db)
    assert "NO_READY_EXTINGUISHER" in w


def test_AC59_emergency_info(api: Api, db: Session) -> None:
    c = api.as_("ramesh.kumar")
    url = f"{API}/projects/{project(db, 'ANIA-EXP').id}/emergency-info"
    pier = ok(c.get(url, params={"zone_ids": [str(zone(db, "Z-PIERB").id)]}))
    assert pier["assembly_point_code"] == "AP-SLAND-01"
    assert {"+966110000911", "998", "997"} <= set(pier["numbers"])
    assert "+966110009998" not in pier["numbers"]
    twb = ok(c.get(url, params={"zone_ids": [str(zone(db, "Z-TWB").id)]}))
    assert "+966110009998" in twb["numbers"] and "Airport ARFF" in twb["text"]
