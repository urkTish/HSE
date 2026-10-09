# ruff: noqa: E501
"""6c-emergency-drills §9 ACs 36-47 (drills, musters, evaluation) and 8 (plan_deficiency)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.emergency_enums import MusterMode, MusterSource
from app.emergency_jobs import emergency_alerts
from app.models import CorrectiveAction, Deployment, GateCheck
from app.services.emergency import muster as mu
from app.services.emergency import programme as pg
from tests.conftest import Api
from tests.emer_helpers import (
    API,
    ap,
    drill,
    eng,
    erp,
    err,
    local,
    muster_of,
    notified,
    project,
    site,
    team,
    tick,
    uid,
)

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")


def ok(res: Any, status: int = 200) -> dict[str, Any]:
    assert res.status_code == status, res.text
    return res.json()  # type: ignore[no-any-return]


def plan(c: Any, db: Session, **kw: Any) -> Any:
    body: dict[str, Any] = {
        "drill_type": "evacuation_full", "scenario_code": "SC-FIRE",
        "site_id": str(site(db, "S-LAND").id), "planned_at": (now() + timedelta(hours=1)).isoformat(),
        "shift": "day", "announced": True, "conductor_user_id": str(uid(db, "fahad.mutairi")),
        "evaluator_user_ids": [str(uid(db, "noura.qahtani"))], **kw,
    }  # fmt: skip
    return c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/drills", json=body)


def act(c: Any, did: str, action: str, **kw: Any) -> Any:
    return c.post(f"{API}/drills/{did}/transitions", json={"action": action, **kw})


def listed(c: Any, db: Session) -> set[str]:
    res = c.get(f"{API}/projects/{project(db, 'ANIA-EXP').id}/drills", params={"page_size": 100})
    return {d["drill_no"] for d in ok(res)["items"]}


def run_land_drill(api: Api, db: Session, **kw: Any) -> dict[str, Any]:
    """Plan, start, count (RAWABI 10/10), time and conduct a S-LAND evacuation drill."""
    fahad, noura = api.as_("fahad.mutairi"), api.as_("noura.qahtani")
    d = ok(plan(fahad, db, **kw), 201)
    ok(act(fahad, d["id"], "start"))
    set_now(now() + timedelta(minutes=5))
    ok(fahad.patch(f"{API}/drills/{d['id']}", json={"timeline": {
        "evacuation_complete_at": now().isoformat()}}))  # fmt: skip
    set_now(now() + timedelta(minutes=5))
    m = drill(db, d["drill_no"]).muster_id
    rows = [{"engagement_id": str(eng(db, "ANIA-EXP", "RAWABI").id), "expected": 10,
             "accounted": 10}]  # fmt: skip
    ok(noura.put(f"{API}/musters/{m}/counts", json={"rows": rows}))
    set_now(now() + timedelta(minutes=2))
    ok(fahad.patch(f"{API}/drills/{d['id']}", json={"timeline": {
        "all_clear_at": now().isoformat()}}))  # fmt: skip
    return ok(act(fahad, d["id"], "conduct"))


def test_AC36_unannounced_visibility(api: Api, db: Session) -> None:
    fahad = api.as_("fahad.mutairi")
    d = ok(plan(fahad, db, announced=False), 201)
    no = d["drill_no"]
    for who in ("ahmed.zahrani", "ramesh.kumar"):
        assert no not in listed(api.as_(who), db), who
        assert api.as_(who).get(f"{API}/drills/{d['id']}").status_code == 404
    for who in ("fahad.mutairi", "noura.qahtani", "faisal.harbi"):
        assert no in listed(api.as_(who), db), who
    ok(act(fahad, d["id"], "start"))
    assert no in listed(api.as_("ahmed.zahrani"), db)
    assert no in listed(api.as_("sarah.mitchell"), db)


def test_AC37_conductor_only_evaluator(api: Api, db: Session) -> None:
    res = plan(api.as_("fahad.mutairi"), db, evaluator_user_ids=[str(uid(db, "fahad.mutairi"))])
    assert res.status_code == 422 and err(res) == "SOD_CONFLICT"


def test_AC38_timeline_order(api: Api, db: Session) -> None:
    fahad = api.as_("fahad.mutairi")
    d = ok(plan(fahad, db), 201)
    ok(act(fahad, d["id"], "start"))
    early = (now() - timedelta(minutes=1)).isoformat()
    res = fahad.patch(f"{API}/drills/{d['id']}",
                      json={"timeline": {"evacuation_complete_at": early}})  # fmt: skip
    assert res.status_code == 422 and err(res) == "TIMELINE_ORDER"


def test_AC39_ed3(api: Api, db: Session) -> None:
    d = ok(api.as_("noura.qahtani").get(f"{API}/drills/{drill(db, 'DRL-ANIA-EXP-2026-031').id}"))
    assert (d["measures"]["evac_min"], d["measures"]["headcount_min"]) == ("8.7", "24.2")
    assert d["result"] == "unsatisfactory"
    crit = [f for f in d["evaluation"]["findings"] if f["severity"] == "critical"]
    assert any(f["category"] == "behaviour" and f.get("auto") and f.get("ca_ref") for f in crit)
    rep = [x for x in pg.lines(db, project(db, "ANIA-EXP").id, date(2026, 10, 6))
           if x.source.value == "repeat"]  # fmt: skip
    assert [x.due_by for x in rep] == [date(2026, 10, 17)]


def test_AC40_ed4(api: Api, db: Session) -> None:
    x = drill(db, "DRL-ANIA-EXP-2026-034")
    d = ok(api.as_("noura.qahtani").get(f"{API}/drills/{x.id}"))
    assert (d["measures"]["evac_min"], d["measures"]["headcount_min"]) == ("6.3", "17.5")
    assert d["result"] == "satisfactory"
    m = muster_of(db, x)
    assert m.mode == MusterMode.roll
    # roll = the G-AAP3 `in` rows of the Phase 2 world (DECISIONS: 434, not 486)
    assert len(mu.entries(db, m)) == 434
    assert m.headcount_complete_at == local(2026, 9, 24, 23, 17, 30)


def test_AC41_extra_scan_no_gate_row(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    air = site(db, "S-AIR").id
    at = local(2026, 9, 30, 23, 30)
    set_now(at)
    x = drill(db, "DRL-ANIA-EXP-2026-034")
    m = mu.open_muster(db, pid, MusterSource.drill, x.id, air, None, at, False, None)
    assert m.mode == MusterMode.roll and mu.entries(db, m)
    on_roll = {e.deployment_id for e in mu.entries(db, m)}
    dep = next(d for d in db.scalars(select(Deployment).where(
        Deployment.project_id == pid, Deployment.status == "mobilised")) if d.id not in on_roll)  # fmt: skip
    n_gate = db.scalar(select(func.count()).select_from(GateCheck))
    e = mu.account(db, m, dep, ap(db, "AP-SAIR-01").id, None)
    assert e.extra and e.state.value == "accounted" and m.extras == 1
    assert db.scalar(select(func.count()).select_from(GateCheck)) == n_gate


def test_AC42_muster_reader_bound(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    noura = api.as_("noura.qahtani")
    reg = ok(noura.post(f"{API}/projects/{pid}/muster-devices", json={
        "ap_id": str(ap(db, "AP-SAIR-01").id), "device_id": "MR-TEST-01",
        "label": "AP-SAIR-01 reader"}), 201)  # fmt: skip
    sess = ok(api.anon.post(f"{API}/emergency/muster-session",
                            json={"device_token": reg["device_token"]}))  # fmt: skip
    hdr = {"Authorization": f"Bearer {sess['access_token']}"}
    res = api.anon.get(f"{API}/projects/{pid}/drills", headers=hdr)
    assert res.status_code in (401, 403), res.text
    res = api.anon.post(f"{API}/emergency/muster-scan", headers=hdr,
                        json={"payload": "HSE2:AC:XXXXXXXXXXXX",
                              "ap_id": str(ap(db, "AP-SLAND-01").id)})  # fmt: skip
    assert res.status_code == 403, res.text


def test_AC43_late_entry(api: Api, db: Session) -> None:
    fahad = api.as_("fahad.mutairi")
    d = ok(plan(fahad, db, planned_at=(now() - timedelta(hours=1)).isoformat()), 201)
    t = now()
    got = ok(act(fahad, d["id"], "start", alarm_at=(now() - timedelta(minutes=30)).isoformat()))
    assert got["late_entry"] is True
    db.expire_all()
    assert muster_of(db, drill(db, d["drill_no"])).mode == MusterMode.count_
    from app.models import Permit

    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0413"))
    assert p is not None and p.status.value == "active"
    assert not notified(db, "emergency_unaccounted", t)


def test_AC44_AC8_evaluation_findings(api: Api, db: Session) -> None:
    d = run_land_drill(api, db)
    noura = api.as_("noura.qahtani")
    crit = [{"criterion": c, "answer": "pass"} for c in
            ("DC01", "DC02", "DC03", "DC04", "DC05", "DC06", "DC07", "DC08", "DC11", "DC12")]  # fmt: skip
    crit[3]["answer"] = "fail"  # DC04
    t = now()
    body = {"criteria": crit, "findings": [
        {"category": "communication", "severity": "minor", "description_en": "Radio noise"},
        {"category": "plan_deficiency", "severity": "major", "description_en": "AP map outdated"},
    ]}  # fmt: skip
    ev = ok(noura.post(f"{API}/drills/{d['id']}/evaluation", json=body))
    fs = ev["evaluation"]["findings"]
    dc04 = next(f for f in fs if f.get("ref") == "DC04")
    assert dc04["severity"] == "critical" and dc04["ca_ref"]
    ca = db.scalar(select(CorrectiveAction).where(CorrectiveAction.ref == dc04["ca_ref"]))
    assert ca is not None and getattr(ca.priority, "value", ca.priority) == "critical"
    minor = next(f for f in fs if f["severity"] == "minor")
    assert minor.get("ca_id") is None
    db.expire_all()
    assert erp(db, "ERP-ANIA-EXP-r3").review_required  # ER-8
    assert "faisal.harbi" in notified(db, "emergency_erp_review", t)


def test_AC45_dr8_equipment_finding(api: Api, db: Session) -> None:
    from app.core.cert_enums import ServiceStatus
    from app.models import EquipmentItem

    t = team(db, "RT-ANIA-CSE-01")
    (item_id,) = t.equipment_item_ids
    it = db.get(EquipmentItem, item_id)
    assert it is not None
    it.service_status = ServiceStatus.out_of_service
    db.commit()
    fahad = api.as_("fahad.mutairi")
    d = ok(plan(fahad, db, drill_type="cse_rescue", scenario_code="SC-CSE", team_id=str(t.id),
                site_id=None, rescue_plan_ref="RP-CSE-TEST-01"), 201)  # fmt: skip
    got = ok(act(fahad, d["id"], "start"))
    auto = got["evaluation"]["auto_findings"]
    assert any(f["category"] == "equipment" and f["severity"] == "major" for f in auto)


def test_AC46_evaluation_overdue(db: Session) -> None:
    x = drill(db, "DRL-ANIA-EXP-2026-034")
    x.status, x.evaluation, x.result = x.status.__class__("conducted"), None, None
    x.conducted_at = local(2026, 10, 1, 10)
    x.timeline = {**x.timeline, "alarm_at": local(2026, 10, 1, 10).isoformat()}
    db.commit()
    t1 = tick(2026, 10, 4, 7, 5)
    emergency_alerts(db, t1)
    db.commit()
    got = notified(db, "emergency_evaluation_overdue", t1)
    assert "noura.qahtani" in got and "faisal.harbi" not in got
    t2 = tick(2026, 10, 6, 7, 5)
    emergency_alerts(db, t2)
    db.commit()
    assert "faisal.harbi" in notified(db, "emergency_evaluation_overdue", t2)


def test_AC47_void(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    land = site(db, "S-LAND").id
    x = drill(db, "DRL-ANIA-EXP-2026-031")
    cas = [f["ca_id"] for f in x.evaluation["findings"] if f.get("ca_id")]
    res = act(api.as_("faisal.harbi"), str(x.id), "void",
              reason="Recorded against the wrong site by mistake")  # fmt: skip
    assert ok(res)["status"] == "voided"
    db.expire_all()
    ln = next(ln for ln in pg.lines(db, pid, date(2026, 10, 6))
              if ln.site_id == land and ln.drill_type.value == "evacuation_full"
              and ln.shift_req.value == "any" and ln.ann_req.value == "any")  # fmt: skip
    assert ln.due_by == date(2026, 9, 17) and ln.status.value == "overdue"
    for ca_id in cas:
        ca = db.get(CorrectiveAction, ca_id)
        assert ca is not None and getattr(ca.status, "value", ca.status) != "closed"
