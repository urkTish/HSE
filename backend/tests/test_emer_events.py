# ruff: noqa: E501
"""6c-emergency-drills §9 ACs 48-53 (emergency events, EV-1…EV-7)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.emergency_enums import MusterMode
from app.models import EmergencyEvent, Permit
from app.services.emergency import muster as mu
from tests.conftest import Api
from tests.emer_helpers import API, err, event, local, muster_of, notified, project, site, zone

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")


def ok(res: Any, status: int = 200) -> dict[str, Any]:
    assert res.status_code == status, res.text
    return res.json()  # type: ignore[no-any-return]


def declare(c: Any, db: Session, site_code: str = "S-AIR", **kw: Any) -> Any:
    body: dict[str, Any] = {"event_type": "fire_explosion", "site_id": str(site(db, site_code).id),
                            "zone_ids": [str(zone(db, "Z-APR-21").id)],
                            "response_type": "site_evacuation", **kw}  # fmt: skip
    return c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/emergency-events", json=body)


def test_AC48_AC49_site_evacuation(api: Api, db: Session) -> None:
    t = local(2026, 9, 30, 23, 30)  # gate rows exist up to 2026-09-30 night (Phase 2 world)
    set_now(t)
    omar = api.as_("omar.siddiqui")
    ev = ok(declare(omar, db), 201)
    got = notified(db, "emergency_event", t)
    assert {"faisal.harbi", "noura.qahtani", "omar.siddiqui", "ahmed.zahrani"} <= set(got), got
    assert any(x.startswith(f"EMERGENCY {ev['event_no']}") for x in got["faisal.harbi"])
    db.expire_all()
    e = event(db, ev["event_no"])
    m = muster_of(db, e)
    assert m.mode == MusterMode.roll and mu.entries(db, m)
    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0408"))
    assert p is not None  # Suspended before; now the open suspension source is the event
    land = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0413"))
    assert land is not None and land.status.value == "active"  # other site untouched
    # MU-8: leave 3 entries open, account the rest, then the 20-minute timer
    es = mu.entries(db, m)
    for x in es[3:]:
        x.state = x.state.__class__("accounted")
        x.at = t + timedelta(minutes=5)
    db.flush()
    t20 = t + timedelta(minutes=20)
    assert mu.headcount_timer(db, m, t20) > 0
    assert mu.headcount_timer(db, m, t20 + timedelta(minutes=1)) == 0
    db.commit()
    alerts = notified(db, "emergency_unaccounted", t)
    assert any("3 persons unaccounted" in x for x in alerts["faisal.harbi"]), alerts
    set_now(t20 + timedelta(minutes=1))
    noura = api.as_("noura.qahtani")
    ok(noura.post(f"{API}/musters/{m.id}/entries/{es[0].id}/resolve",
                  json={"reason": "found_on_site", "note": "Found in the stores container"}))  # fmt: skip
    after = notified(db, "emergency_unaccounted", t20 + timedelta(seconds=30))
    assert any("found on site" in x for x in after["faisal.harbi"]), after


def test_AC48_issued_permits_suspended(api: Api, db: Session) -> None:
    ok(declare(api.as_("fahad.mutairi"), db, "S-LAND",
               zone_ids=[str(zone(db, "Z-MSCP").id)]), 201)  # fmt: skip
    db.expire_all()
    for no in ("PTW-ANIA-EXP-2026-0405", "PTW-ANIA-EXP-2026-0412", "PTW-ANIA-EXP-2026-0413"):
        p = db.scalar(select(Permit).where(Permit.permit_no == no))
        assert p is not None and p.status.value == "suspended", no
        assert getattr(p.status_reason, "value", p.status_reason) == "emergency"


def test_AC50_AC53_review_rules(api: Api, db: Session) -> None:
    omar, noura = api.as_("omar.siddiqui"), api.as_("noura.qahtani")
    ev = ok(declare(omar, db, response_type="local_response"), 201)
    res = declare(api.as_("sarah.mitchell"), db)
    assert res.status_code == 403
    set_now(now() + timedelta(minutes=10))
    ok(omar.post(f"{API}/emergency-events/{ev['id']}/transitions", json={"action": "all_clear"}))
    body = {"what_worked": "Quick alarm", "issues": "AP signage"}
    assert omar.post(f"{API}/emergency-events/{ev['id']}/review", json=body).status_code == 403
    res = noura.post(f"{API}/emergency-events/{ev['id']}/review", json=body)
    assert res.status_code == 422 and err(res) == "INCIDENT_LINK_REQUIRED"
    fa = ok(declare(omar, db, event_type="false_alarm", response_type="local_response"), 201)
    ok(omar.post(f"{API}/emergency-events/{fa['id']}/transitions", json={"action": "all_clear"}))
    assert ok(noura.post(f"{API}/emergency-events/{fa['id']}/review", json=body))["status"] == (
        "reviewed"
    )


def test_AC51_ed8(api: Api, db: Session) -> None:
    e = ok(api.as_("noura.qahtani").get(
        f"{API}/emergency-events/{event(db, 'EMV-ANIA-EXP-2026-004').id}"))  # fmt: skip
    assert e["times"]["first_response_min"] == "3.0" and e["times"]["total_min"] == "28.0"
    assert e["times"]["external_arrival_min"]["red_crescent"] == "13.0"
    assert e["muster_id"] is None and e["casualties_count"] == 1 and e["incident_ref"]
    assert "Ganesh" not in str(e)


def test_AC52_ops_aircraft_emergency(api: Api, db: Session) -> None:
    set_now(local(2026, 10, 6, 23, 30))
    k = api.as_("khalid.otaibi")
    zs = [str(zone(db, "Z-TWB").id), str(zone(db, "Z-ILS33R").id)]
    ops = ok(k.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/ops-events", json={
        "type": "aircraft_emergency", "site_id": str(site(db, "S-AIR").id), "zone_ids": zs,
        "source": "aocc", "source_ref": "AOCC-LOG-TEST-501"}), 201)  # fmt: skip
    e = db.scalar(select(EmergencyEvent).where(EmergencyEvent.ops_event_id == ops["id"]))
    assert e is not None and e.event_type.value == "airport_aep_activation"
    assert {str(z) for z in e.zone_ids} >= set(zs)
    assert e.response_type.value == "zone_evacuation"
    set_now(now() + timedelta(minutes=20))
    ok(k.post(f"{API}/ops-events/{ops['id']}/end", json={}))
    db.expire_all()
    assert event(db, e.event_no).status.value == "all_clear"
