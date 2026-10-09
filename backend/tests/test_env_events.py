# ruff: noqa: E501
"""Phase 6e airside post-storm checks, spills, water and complaints (6e §9 AC 34-47)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.env_jobs import env_daily, env_minute
from app.models import (
    CorrectiveAction,
    EnvComplaint,
    Incident,
    OpsEvent,
)
from app.schemas.env import (
    ComplaintCreate,
    SpillCreate,
    SpillTransition,
    WaterCreate,
)
from app.services import incidents
from app.services.emergency import assets
from app.services.env import board, spills, water
from tests.conftest import Api
from tests.env_helpers import (
    API,
    D,
    P,
    area,
    eng,
    expect,
    kit,
    kpi,
    kpis,
    local,
    notified,
    project,
    tick,
    zone,
)
from tests.field_helpers import body as fbody
from tests.field_helpers import stop_fields, submit


def _site(db: Session, code: str) -> uuid.UUID:
    from app.models import Site

    s = db.scalar(select(Site.id).where(Site.code == code))
    assert s is not None
    return s


def _storm(db: Session, end_h: int) -> OpsEvent:
    """A dust_sandstorm ops event on S-AIR ending today at end_h (cloned from OPS-0008)."""
    src = db.scalar(select(OpsEvent).where(OpsEvent.ops_no == "OPS-ANIA-EXP-2026-0008"))
    assert src is not None
    ev = OpsEvent(
        id=uuid.uuid4(), ops_no="OPS-ANIA-EXP-2026-0099", year=2026, seq=99, project_id=src.project_id,
        site_id=src.site_id, type=src.type, zone_ids=src.zone_ids,
        default_zone_ids=src.default_zone_ids, source=src.source, source_ref="TEST",
        started_at=local(2026, 10, 6, end_h - 2), ended_at=local(2026, 10, 6, end_h),
        declared_by_user_id=src.declared_by_user_id,
    )  # fmt: skip
    db.add(ev)
    db.flush()
    return ev


def test_post_storm_met(env_seed: None, db: Session) -> None:
    """AC 34 (a): ending 14:00 → due 18:00; a WSA inspection at 15:30 on S-AIR meets it."""
    tick(2026, 10, 6, 15, 35)
    _storm(db, 14)
    submit(db, "noura.qahtani", fbody(db, "WSA", site="S-AIR", zone_code="Z-APR-21",
                                      eng_code="RAWABI", completed=local(2026, 10, 6, 15, 30)))  # fmt: skip
    pid = project(db, "ANIA-EXP").id
    t = [x for x in board.post_storm_tasks(db, pid, local(2026, 10, 6, 0))
         if x.ops_no.endswith("0099")]  # fmt: skip
    assert len(t) == 1 and t[0].due_at == local(2026, 10, 6, 18) and t[0].met


def test_post_storm_unmet(env_seed: None, db: Session) -> None:
    """AC 34 (b): none done → Noura and Omar alerted at 18:00; the action panel lists it."""
    tick(2026, 10, 6, 14, 5)
    _storm(db, 14)
    pid = project(db, "ANIA-EXP").id
    since = tick(2026, 10, 6, 18, 1)
    env_minute(db)
    got = notified(db, "post_storm_check", since)
    assert {"noura.qahtani", "omar.siddiqui"} <= set(got), got
    panel = board.action_panel(db, P(db, "noura.qahtani"), pid)
    assert any("0099" in r.ref or "0099" in r.label_en for r in panel.items), panel


def test_dsn_stop_rule(env_seed: None, clock: None, db: Session) -> None:
    """AC 35: DSN-02 non-compliant on Z-TWB → STOP_RECORD_REQUIRED, then CA critical (inspection)."""
    b = fbody(db, "DSN", nc={"DSN-02"}, site="S-AIR", zone_code="Z-TWB", eng_code="GULFPAVE")
    expect("STOP_RECORD_REQUIRED", lambda: submit(db, "noura.qahtani", b))
    db.rollback()
    r = submit(db, "noura.qahtani", fbody(db, "DSN", nc={"DSN-02"}, site="S-AIR",
                                          zone_code="Z-TWB", eng_code="GULFPAVE", stop=stop_fields()))  # fmt: skip
    cas = db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_type == "inspection",
                                                    CorrectiveAction.priority == "critical",
                                                    CorrectiveAction.created_date == date(2026, 10, 6)))  # fmt: skip
    assert r.result.value == "fail" and len(list(cas)) >= 1


EV7 = [
    # quantity, contained, reached, zone, reportable
    ("40", True, "none", "Z-APR-21", True),
    ("8", True, "none", "Z-LAY1", False),
    ("8", True, "none", "Z-APR-21", True),
    ("15", True, "drain", "Z-MSCP", True),
    ("25", True, "none", "Z-PIERB", True),
    ("5", False, "none", "Z-LAY1", True),
]


def test_ev7_classification(env_seed: None, clock: None, db: Session) -> None:
    """AC 36."""
    pid = project(db, "ANIA-EXP").id
    got = [spills.reportable(db, pid, D(q), r, c, zone(db, z)) for q, c, r, z, _ in EV7]  # type: ignore[arg-type]
    assert got == [x[4] for x in EV7]


def _spill(db: Session, q: str, z: str, site: str, **kw: Any) -> SpillCreate:
    data = {"client_uuid": str(uuid.uuid4()), "occurred_at": local(2026, 10, 6, 9, 30),
            "site_id": _site(db, site), "zone_id": zone(db, z).id,
            "responsible_engagement_id": eng(db, "ANIA-EXP", "GULFPAVE" if site == "S-AIR" else "NAJD").id,
            "substance": "diesel", "source": "refuelling", "quantity_l": D(q), "surface": "paved",
            "contained": True, "reached": "none"}  # fmt: skip
    data.update(kw)
    return SpillCreate.model_validate(data)


FIELDS = {"actual_severity": 2, "potential_severity": 3, "activity": "paving_asphalt",
          "shift": "day", "description": "Diesel spill at the bowser", "immediate_actions": "Kit used"}  # fmt: skip


def test_spill_incident_kpis_and_notifications(
    env_seed: None, clock: None, api: Api, db: Session
) -> None:
    """AC 37, 41, 43: EV7 (a) creates a Reported environmental incident (K-16 + 1) needing
    airport_operator; (b) no incident, K-124 + 1; (d) needs ncec 24 h; same client_uuid twice →
    one spill and one incident; September seed incidents unchanged."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    f = api.as_("faisal.harbi")
    oct_ = {"start": "2026-10-01", "end": "2026-10-31"}
    k124 = int(kpi(kpis(f, pid, **oct_), "K124")["value"])
    n_inc = len(db.scalars(select(Incident.id).where(Incident.project_id == pid)).all())
    a = _spill(db, "40", "Z-APR-21", "S-AIR", incident_fields=FIELDS)
    s = spills.create_spill(db, p, pid, a)
    again = spills.create_spill(db, p, pid, a)
    assert again.id == s.id
    inc = db.get(Incident, s.incident_id)
    assert (
        inc is not None
        and inc.status.value == "reported"
        and inc.incident_types == ["environmental"]
    )
    assert (inc.env_category.value if inc.env_category else None, inc.env_substance) == (
        "spill",
        "diesel",
    )
    assert (D(inc.env_quantity_l or 0), inc.env_contained, inc.env_reached.value if inc.env_reached else None,
            inc.zone_id) == (D(40), True, "none", zone(db, "Z-APR-21").id)  # fmt: skip
    assert {r.body.value for r in incidents.required_notifications(inc, [])} >= {"airport_operator"}
    spills.create_spill(db, p, pid, _spill(db, "8", "Z-LAY1", "S-LAND"))
    d = spills.create_spill(db, p, pid, _spill(db, "15", "Z-MSCP", "S-LAND", reached="drain",
                                                substance="hydraulic_oil", incident_fields=FIELDS))  # fmt: skip
    dinc = db.get(Incident, d.incident_id)
    assert dinc is not None
    ncec = [r for r in incidents.required_notifications(dinc, []) if r.body.value == "ncec"]
    assert len(ncec) == 1 and ncec[0].due_at == dinc.occurred_at + timedelta(hours=24)
    assert len(db.scalars(select(Incident.id).where(Incident.project_id == pid)).all()) == n_inc + 2
    db.commit()
    assert int(kpi(kpis(f, pid, **oct_), "K124")["value"]) == k124 + 3
    sept = db.scalar(select(Incident).where(Incident.ref == "INC-ANIA-EXP-2026-0288"))
    assert sept is not None
    assert not [
        r
        for r in incidents.required_notifications(sept, [])
        if r.body.value in ("ncec", "airport_operator")
    ]
    k16 = f.get(f"{API}/kpi/metrics", params={"project_id": str(pid), "period": "custom",
                                              "start": "2026-09-01", "end": "2026-09-30", "metric": "K-16"})  # fmt: skip
    assert k16.status_code == 200, k16.text
    assert k16.json()["kpis"][0]["value"] == "1"


def test_spill_links(env_seed: None, clock: None, db: Session) -> None:
    """AC 38: link to an environmental incident within 24 h; injury-only → 422; no fields → 422."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    first = spills.create_spill(db, p, pid, _spill(db, "40", "Z-APR-21", "S-AIR", incident_fields=FIELDS,
                                                   occurred_at=local(2026, 10, 5, 23, 30)))  # fmt: skip
    n = len(db.scalars(select(Incident.id)).all())
    linked = spills.create_spill(
        db, p, pid, _spill(db, "30", "Z-APR-21", "S-AIR", incident_id=first.incident_id)
    )
    assert (
        linked.incident_id == first.incident_id and len(db.scalars(select(Incident.id)).all()) == n
    )
    injury = db.scalar(select(Incident).where(Incident.project_id == pid,
                                              ~Incident.incident_types.any("environmental")))  # type: ignore[arg-type]  # fmt: skip
    assert injury is not None
    injury.site_id, injury.occurred_at = _site(db, "S-AIR"), local(2026, 10, 6, 8)
    db.flush()
    expect("INCIDENT_NOT_ENVIRONMENTAL", lambda: spills.create_spill(
        db, p, pid, _spill(db, "30", "Z-APR-21", "S-AIR", incident_id=injury.id)))  # fmt: skip
    expect(
        "INCIDENT_FIELDS_REQUIRED",
        lambda: spills.create_spill(db, p, pid, _spill(db, "30", "Z-APR-21", "S-AIR")),
    )


def test_spill_kit_used_and_closure(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 39-40, 42: a used kit is not ready until a passing check; closing needs tracked cleanup
    waste; Fahad cannot close (210); a hazardous store without a kit is listed (SPL-7)."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    f = api.as_("faisal.harbi")
    oct_ = {"start": "2026-10-01", "end": "2026-10-31"}
    before = kpi(kpis(f, pid, **oct_), "K125")["numerator"]
    k = kit(db, "SK-SLAND-04")
    s = spills.create_spill(db, p, pid, _spill(db, "40", "Z-LAY1", "S-LAND", incident_fields=FIELDS,
                                               spill_kit_asset_ids=[str(k.id)]))  # fmt: skip
    r = assets.readiness(db, k, date(2026, 10, 6))
    assert "USED_REPLENISH" in [x.value for x in r.reasons]
    db.commit()
    assert int(kpi(kpis(f, pid, **oct_), "K125")["numerator"]) == int(before) - 1
    spills.transition_spill(db, p, s.id, SpillTransition(action="clean_up",
                                                          cleanup_completed_at=local(2026, 10, 6, 9, 50)))  # fmt: skip
    expect(
        "CLEANUP_WASTE_UNTRACKED",
        lambda: spills.transition_spill(db, p, s.id, SpillTransition(action="close")),
    )
    with pytest.raises(ApiError) as ei:
        spills.transition_spill(db, P(db, "fahad.mutairi"), s.id, SpillTransition(
            action="close", cleanup_storage_area_id=area(db, "HWS-SLAND-01").id))  # fmt: skip
    assert ei.value.status_code == 403
    out = spills.transition_spill(db, p, s.id, SpillTransition(
        action="close", cleanup_storage_area_id=area(db, "HWS-SLAND-01").id))  # fmt: skip
    assert out.status == "closed"
    # SPL-7: no in-service kit in Z-LAY1 → HWS-SLAND-01 listed
    assert not [x for x in board.kit_gaps(db, pid) if x.startswith("HWS-SLAND-01")]
    from app.models import EmergencyAsset

    for a in db.scalars(select(EmergencyAsset).where(EmergencyAsset.asset_type == "spill_kit",
                                                     EmergencyAsset.zone_id == zone(db, "Z-LAY1").id)):  # fmt: skip
        a.status = "out_of_service"
    db.flush()
    assert [x for x in board.kit_gaps(db, pid) if x.startswith("HWS-SLAND-01")]
    panel = board.action_panel(db, p, pid)
    assert any("HWS-SLAND-01" in (r.ref + r.label_en) for r in panel.items)


def test_water(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 44: K-126 6,960 m³, 8.00 L/h, 62.5 %; duplicate entry → 422."""
    pid = project(db, "ANIA-EXP").id
    k = kpi(kpis(api.as_("faisal.harbi"), pid), "K126")
    comps = {c["key"]: c["display"] for c in k["components"]}
    assert (k["display"], comps["l_per_mh"], comps["treated_pct"]) == ("6,960", "8.00", "62.5 %")
    expect("DUPLICATE_WATER_ENTRY", lambda: water.create_water(db, P(db, "noura.qahtani"), pid, WaterCreate(
        site_id=_site(db, "S-AIR"), month="2026-09", source="tanker", volume_m3=D("10"))))  # fmt: skip


def test_complaints(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 46-47: due dates, alerts, nearby readings, contact visibility, retention."""
    since = tick(2026, 10, 6, 10)
    lina = P(db, "lina.haddad")
    pid = project(db, "RBT-52").id
    auth = water.create_complaint(db, lina, pid, ComplaintCreate(
        received_at=local(2026, 10, 6, 9), channel="via_authority", category="dust",
        site_id=_site(db, "S-TWR"), description="Authority forwarded a dust complaint", anonymous=True))  # fmt: skip
    assert auth.response_due_on == date(2026, 10, 9)
    assert "faisal.harbi" in notified(db, "env_complaint", since)
    ph = water.create_complaint(db, lina, pid, ComplaintCreate(
        received_at=local(2026, 10, 6, 9, 30), channel="phone",
        category="noise", site_id=_site(db, "S-TWR"), description="Noise at night",
        complainant_name="Test Person", complainant_contact="+966500000111"))  # fmt: skip
    assert ph.response_due_on == date(2026, 10, 13)
    old = db.scalar(select(EnvComplaint).where(EnvComplaint.complaint_no == "ECP-RBT-52-2026-004"))
    assert old is not None
    near = water.nearby_readings(db, lina, old.id)
    pts = {r.point_code for r in near.items}
    assert "N-STWR-01" in pts
    db.commit()
    seen = {}
    for who in ("lina.haddad", "sarah.mitchell", "yousef.ghamdi"):
        r = api.as_(who).get(f"{API}/env-complaints/{old.id}")
        assert r.status_code == 200, (who, r.text)
        seen[who] = (r.json()["complainant_contact"], r.json()["contact_note"])
    assert seen["lina.haddad"][0] == "+966500000999"
    assert seen["sarah.mitchell"] == (None, "Contact held by the HSE team")
    assert seen["yousef.ghamdi"] == (None, "Contact held by the HSE team")
    tick(2027, 9, 21, 0, 11)
    env_daily(db)
    db.refresh(old)
    assert old.complainant_contact is None and old.contact_deleted_at is not None
    assert old.status.value == "closed"
