# ruff: noqa: E501
"""6c-emergency-drills §9 ACs 11-17 (roster and coverage) and 19-22 (rescue teams)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import ServiceStatus
from app.core.emergency_enums import CoverageState, DrillStatus, EmergencyRole, TeamReason
from app.emergency_jobs import live_coverage
from app.models import (
    Contractor,
    Deployment,
    Drill,
    EquipmentItem,
    ProjectEngagement,
    RosterAssignment,
    TrainingRecord,
    Worker,
)
from app.services.emergency import common as ec
from app.services.emergency import org
from app.services.train import matrix
from tests.conftest import Api
from tests.emer_helpers import API, err, local, notified, project, site, team, zone

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")

Z1, Z2, Z3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def calc(hc: int, fa: int, wardens: list[list[uuid.UUID]], zw: list[uuid.UUID] | None = None,
         req: list[uuid.UUID] | None = None) -> ec.CovResult:  # fmt: skip
    zw = zw if zw is not None else [Z1, Z2]
    return ec.coverage_calc(hc, zw, req if req is not None else zw, fa, wardens, True, 50, 50)


def test_AC11_AC12_ed1() -> None:
    w = [[Z1]] * 7 + [[Z2]] * 5
    r = calc(520, 10, w)
    assert (r.rfa, r.rw, r.fa, r.state, r.reasons) == (11, 11, 10, CoverageState.short,
                                                       ["first_aider"])  # fmt: skip
    assert calc(500, 10, w).state == CoverageState.covered
    assert calc(0, 0, []).state == CoverageState.not_required
    assert (calc(1, 1, [[Z1], [Z2]]).rfa, calc(1, 1, [[Z1], [Z2]]).rw) == (1, 2)
    assert calc(100, 0, []).rfa == 2
    assert calc(101, 0, []).rfa == 3


def test_AC15_zone_without_warden() -> None:
    zs = [Z1, Z2, Z3]
    r = calc(300, 6, [[Z1], [Z2]] * 3, zs)
    assert r.wardens == 6 and r.rw == 6 and r.state == CoverageState.short
    assert r.reasons == ["zone"] and r.zones_without == [Z3]


def test_AC13_ed2_waleed_not_qualified(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    body = (
        api.as_("noura.qahtani")
        .get(
            f"{API}/projects/{pid}/emergency-coverage",
            params={
                "date_from": "2026-09-14",
                "site_id": str(site(db, "S-LAND").id),
                "shift": "day",
            },
        )
        .json()
    )
    (row,) = body["rows"]
    waleed = db.scalar(select(Worker).where(Worker.full_name_en == "Waleed Saleh"))
    assert waleed is not None and waleed.worker_no in row["rostered_not_qualified"]
    assert row["first_aiders_counted"] >= row["first_aiders_required"]  # ED2 FA side holds


def test_AC14_presence(db: Session) -> None:
    """EO-4: S-LAND (excluded gate, DECISIONS) counts the rostered; S-AIR needs a gate `in`."""
    pid = project(db, "ANIA-EXP").id
    land, air = site(db, "S-LAND").id, site(db, "S-AIR").id
    assert not ec.has_gates(db, pid, land) and ec.has_gates(db, pid, air)
    d = date(2026, 9, 14)
    # a qualified S-LAND warden with no gate `in` on S-AIR, also rostered on S-AIR day
    a = next(x for x in ec.roster(db, pid, land, d, EmergencyRole.fire_warden)
             if x.deployment_id not in ec.present_map(db, pid, air, d, d).get(d, set()))  # fmt: skip
    before = ec.coverage_days(db, pid, d, d, air, ec.DrillShift.day)[0].result.wardens
    db.add(RosterAssignment(id=uuid.uuid4(), assignment_no="EOR-ANIA-EXP-99999",
                            project_id=pid, seq=99999, role=EmergencyRole.fire_warden,
                            deployment_id=a.deployment_id, site_id=air,
                            zone_ids=[zone(db, "Z-TWB").id], shift="day",
                            valid_from=date(2026, 9, 1)))  # fmt: skip
    db.flush()
    db.info.pop("em_present", None)
    assert ec.coverage_days(db, pid, d, d, air, ec.DrillShift.day)[0].result.wardens == before
    land_days = ec.coverage_days(db, pid, d, d, land, ec.DrillShift.day)
    assert land_days[0].result.wardens > 0


def _dep(db: Session, pcode: str, short: str, without_role: str | None = None) -> Deployment:
    pid = project(db, pcode).id
    q = (
        select(Deployment)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(Deployment.project_id == pid, Contractor.short_code == short,
               Deployment.status == "mobilised")
        .order_by(Deployment.id)
    )  # fmt: skip
    for d in db.scalars(q):
        pr = matrix.profile_row(db, d)
        if without_role is None or without_role not in (pr.matrix_roles or [] if pr else []):
            return d
    raise AssertionError(short)


def test_AC16_roster_matrix_role(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    d = _dep(db, "ANIA-EXP", "NAJD", "first_aider")
    body = {"role": "first_aider", "deployment_id": str(d.id), "site_id": str(d.site_ids[0]),
            "shift": "day", "valid_from": "2026-10-06"}  # fmt: skip
    res = ahmed.post(f"{API}/projects/{d.project_id}/emergency-roster", json=body)
    assert res.status_code == 201, res.text
    assert res.json()["matrix_role_added"] is True
    db.expire_all()
    pr = matrix.profile_row(db, d)
    assert pr is not None and "first_aider" in pr.matrix_roles
    # QIMMA is only on RBT-52, a project Ahmed cannot see: 404 (DECISIONS; the AC says 403)
    q = _dep(db, "RBT-52", "QIMMA")
    res = ahmed.post(f"{API}/projects/{q.project_id}/emergency-roster",
                     json={**body, "deployment_id": str(q.id), "site_id": str(q.site_ids[0])})  # fmt: skip
    assert res.status_code == 404, res.text


def test_AC17_live_shortfall_once(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    at = local(2026, 10, 6, 7, 0)
    for a in ec.roster(db, pid, site(db, "S-LAND").id, date(2026, 10, 6),
                       EmergencyRole.first_aider)[5:]:  # fmt: skip
        a.valid_to = date(2026, 10, 5)  # live shortfall on S-LAND
    db.flush()
    assert live_coverage(db, pid, at) >= 1
    db.commit()
    got = notified(db, "emergency_coverage_short", at - timedelta(minutes=1))
    assert {"fahad.mutairi", "nasser.shahrani", "ahmed.zahrani", "noura.qahtani"} <= set(got), got
    assert any("S-LAND" in t for t in got["fahad.mutairi"])
    assert live_coverage(db, pid, at + timedelta(minutes=1)) == 0


# ---- rescue teams --------------------------------------------------------------------------------


def _rd(db: Session, code: str, d: date) -> org.Readiness:
    db.expire_all()
    return org.readiness(db, team(db, code), d)


def test_AC19_AC20_currency(db: Session) -> None:
    assert _rd(db, "RT-ANIA-CSE-01", date(2026, 10, 6)).current
    r = _rd(db, "RT-ANIA-CSE-01", date(2026, 10, 20))
    assert r.reasons == [TeamReason.RESCUE_DRILL_OVERDUE] and r.current_until == date(2026, 10, 19)
    t = team(db, "RT-ANIA-CSE-01")
    last = db.scalar(select(Drill).where(Drill.team_id == t.id,
                                         Drill.status == DrillStatus.evaluated))  # fmt: skip
    assert last is not None
    last.conducted_at = local(2026, 10, 15, 9)
    db.commit()
    assert _rd(db, "RT-ANIA-CSE-01", date(2026, 11, 2)).current
    assert TeamReason.TEAM_UNDERSTRENGTH in _rd(db, "RT-ANIA-CSE-01", date(2026, 11, 3)).reasons


def test_AC21_first_aider_and_equipment(db: Session) -> None:
    t = team(db, "RT-ANIA-CSE-01")
    people = [t.lead_deployment_id, *t.member_deployment_ids]
    wids = list(ec.dep_worker(db, people).values())
    for r in db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id.in_(wids),
                                                     TrainingRecord.course_code == "FIRST-AID")):  # fmt: skip
        r.valid_until = date(2026, 10, 1)
    db.commit()
    assert TeamReason.NO_FIRST_AIDER in _rd(db, "RT-ANIA-CSE-01", date(2026, 10, 6)).reasons
    (item_id,) = t.equipment_item_ids
    item = db.get(EquipmentItem, item_id)
    assert item is not None
    item.service_status = ServiceStatus.out_of_service
    db.commit()
    assert TeamReason.RESCUE_EQUIPMENT_NOT_READY in _rd(db, "RT-ANIA-CSE-01",
                                                        date(2026, 10, 6)).reasons  # fmt: skip


def test_AC22_already_in_team_and_understrength(api: Api, db: Session) -> None:
    t = team(db, "RT-ANIA-CSE-01")
    pid = t.project_id
    c = api.as_("noura.qahtani")
    others = [d.id for d in db.scalars(select(Deployment).where(
        Deployment.project_id == pid, Deployment.status == "mobilised",
        Deployment.id.not_in([t.lead_deployment_id, *t.member_deployment_ids])).limit(2))]  # fmt: skip
    body: dict[str, Any] = {"team_code": "RT-ANIA-CSE-02", "team_type": "confined_space",
                            "site_ids": [str(site(db, "S-LAND").id)],
                            "lead_deployment_id": str(others[0]),
                            "member_deployment_ids": [str(t.lead_deployment_id)]}  # fmt: skip
    res = c.post(f"{API}/projects/{pid}/rescue-teams", json=body)
    assert res.status_code == 422 and err(res) == "ALREADY_IN_TEAM"
    body["member_deployment_ids"] = [str(others[1])]
    res = c.post(f"{API}/projects/{pid}/rescue-teams", json=body)
    assert res.status_code == 201, res.text
    assert "TEAM_UNDERSTRENGTH" in res.json()["readiness"]["reasons"]
