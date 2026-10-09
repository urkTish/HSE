"""6b-heat-stress §9 ACs 29-37 (acclimatisation plans; HS4) on fabricated gate entries."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    DeploymentStatus,
    GateDirection,
    GateResult,
    GateSubjectKind,
    WorkerPersonType,
)
from app.core.heat_enums import PlanStatus, PlanType
from app.models import AcclimatisationPlan, Deployment, Gate, GateCheck, Worker
from app.services.heat import common as hc
from app.services.heat import plans
from tests.conftest import Api
from tests.heat_helpers import API, err, local, notified, project, tick, worker

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")


def fresh(db: Session, n: int = 1, skip: int = 0) -> list[Deployment]:
    """ANIA labourer deployments whose worker has no gate entry and no plan."""
    pid = project(db, "ANIA-EXP").id
    seen = set(db.scalars(select(GateCheck.worker_id).where(GateCheck.worker_id.is_not(None))))
    seen |= set(db.scalars(select(AcclimatisationPlan.worker_id)))
    out = []
    for dep in db.scalars(
        select(Deployment)
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(
            Deployment.project_id == pid,
            Deployment.status == DeploymentStatus.mobilised,
            Worker.person_type == WorkerPersonType.contractor_worker,
            Worker.seq >= 1000,
        )
        .order_by(Worker.seq)
    ):
        if dep.trade.value == "labourer" and dep.worker_id not in seen:
            out.append(dep)
    assert len(out) >= n + skip
    return out[skip : skip + n]


def gate_in(db: Session, dep: Deployment, d: date) -> None:
    g = db.scalar(select(Gate).where(Gate.project_id == dep.project_id))
    assert g is not None
    db.add(
        GateCheck(
            id=uuid.uuid4(),
            occurred_at=local(d.year, d.month, d.day, 6, 30),
            local_date=d,
            project_id=dep.project_id,
            site_id=g.site_id,
            gate_id=g.id,
            direction=GateDirection.in_,
            subject_kind=GateSubjectKind.person,
            worker_id=dep.worker_id,
            deployment_id=dep.id,
            engagement_id=dep.engagement_id,
            result=GateResult.GRANTED,
            reason_codes=[],
        )
    )
    db.flush()


def work(db: Session, dep: Deployment, ds: list[date]) -> None:
    for d in ds:
        tick(d.year, d.month, d.day, 7)
        gate_in(db, dep, d)
        plans.on_worked_day(db, dep, d)
    db.commit()


def plans_of(db: Session, dep: Deployment) -> list[AcclimatisationPlan]:
    db.expire_all()
    return list(
        db.scalars(
            select(AcclimatisationPlan)
            .where(AcclimatisationPlan.deployment_id == dep.id)
            .order_by(AcclimatisationPlan.created_at, AcclimatisationPlan.seq)
        )
    )


def D(m: int, d: int) -> date:
    return date(2027, m, d)


def test_AC29_hs4a_new_worker(db: Session) -> None:
    (dep,) = fresh(db)
    work(db, dep, [D(6, 2), D(6, 3), D(6, 5), D(6, 6), D(6, 7)])
    (pl,) = plans_of(db, dep)
    assert pl.plan_type == PlanType.new_worker
    got = [(x["work_date"], x["max_pct"], x["max_minutes"]) for x in pl.days]
    assert got == [("2027-06-02", 20, 120), ("2027-06-03", 40, 240), ("2027-06-05", 60, 360),
                   ("2027-06-06", 80, 480), ("2027-06-07", 100, 600)]  # fmt: skip
    assert pl.status == PlanStatus.active
    tick(2027, 6, 8, 0, 7)
    plans.run_daily(db, dep.project_id, D(6, 8))
    db.commit()
    (pl,) = plans_of(db, dep)
    assert pl.status == PlanStatus.completed and pl.completed_on == D(6, 7)


def test_AC30_AC31_hs4b_hs4c(db: Session) -> None:
    a, b = fresh(db, 2)
    work(db, a, [D(6, 2), D(6, 3), D(6, 8)])
    first, second = plans_of(db, a)
    assert first.status == PlanStatus.interrupted
    assert second.plan_type == PlanType.new_worker and second.trigger_date == D(6, 8)
    assert (second.days[0]["work_date"], second.days[0]["max_pct"]) == ("2027-06-08", 20)
    for i in range(15):  # acclimatised: worked 06-16 … 06-30 (no plan: inserted directly)
        gate_in(db, b, D(6, 16) + timedelta(days=i))
    db.commit()
    work(db, b, [D(7, 8)])
    (pl,) = plans_of(db, b)
    assert pl.plan_type == PlanType.returner
    assert (pl.days[0]["work_date"], pl.days[0]["max_pct"]) == ("2027-07-08", 50)
    assert [x["max_pct"] for x in pl.days] == [50, 60, 80, 100]


def test_AC32_prior_experience(api: Api, db: Session) -> None:
    (dep,) = fresh(db)
    work(db, dep, [D(6, 2)])
    (pl,) = plans_of(db, dep)
    tick(2027, 6, 2, 12)
    ahmed = api.as_("ahmed.zahrani")
    url = f"{API}/acclimatisation-plans/{pl.id}/prior-experience"
    assert ahmed.post(url, json={"text": "12 chars xxx"}).status_code == 422
    res = ahmed.post(url, json={"text": "Five summers on Riyadh road projects"})
    assert res.status_code == 200, res.text
    assert [d["max_pct"] for d in res.json()["days"]] == [50, 60, 80, 100]
    (dep2,) = fresh(db, 1, skip=1)
    work(db, dep2, [D(6, 2), D(6, 3), D(6, 5)])
    (pl2,) = plans_of(db, dep2)
    res = api.as_("ahmed.zahrani").post(
        f"{API}/acclimatisation-plans/{pl2.id}/prior-experience",
        json={"text": "Five summers on Riyadh road projects"},
    )
    assert res.status_code == 422 and err(res) == "TOO_LATE_TO_CHANGE", res.text


def test_AC33_AC34_ganesh_plan(api: Api, db: Session) -> None:
    pl = db.scalar(
        select(AcclimatisationPlan).where(AcclimatisationPlan.plan_no == "ACP-ANIA-EXP-2026-00412")
    )
    assert pl is not None and pl.status == PlanStatus.waiting_restriction
    tick(2026, 10, 8, 0, 7)
    plans.run_daily(db, pl.project_id, date(2026, 10, 8))
    db.commit()
    db.refresh(pl)
    assert pl.status == PlanStatus.waiting_restriction
    # P6b-3 below 6a tier 2: Sanjay (receiver, tier 1). Ahmed holds 156 for his tree in the 6a
    # matrix (DECISIONS: AC34 names him; the matrix wins).
    res = api.as_("sanjay.verma").get(f"{API}/acclimatisation-plans/{pl.id}")
    assert res.status_code == 200, res.text
    low = res.json()
    assert (low["plan_type"], low["trigger"]["kind"]) == ("returner", "absence")
    assert low["trigger"].get("ref") is None
    noura = api.as_("noura.qahtani").get(f"{API}/acclimatisation-plans/{pl.id}").json()
    assert noura["plan_type"] == "post_heat_illness"
    assert noura["trigger"]["ref"] == "MFH-ANIA-EXP-2026-00019"
    assert worker(db, "WKR-000033").id == pl.worker_id


def test_AC35_unconfirmed(db: Session) -> None:
    (dep,) = fresh(db)
    work(db, dep, [D(6, 2), D(6, 3)])
    pid = dep.project_id
    since = local(2027, 6, 1)
    tick(2027, 6, 4, 23, 59)
    plans.unconfirmed_alerts(db, pid, local(2027, 6, 4, 23, 59))
    tick(2027, 6, 5, 0, 0)
    plans.unconfirmed_alerts(db, pid, local(2027, 6, 5, 0, 0))
    db.commit()
    got = notified(db, "heat_plan_unconfirmed", since)
    assert sum("day 2" in t for t in got["ahmed.zahrani"]) == 1
    assert not any("day 2" in t for t in got.get("noura.qahtani", []))
    plans.unconfirmed_alerts(db, pid, local(2027, 6, 6, 0, 0))
    db.commit()
    assert any("day 2" in t for t in notified(db, "heat_plan_unconfirmed", since)["noura.qahtani"])


def test_AC36_AC37_season_end_and_period_start(db: Session) -> None:
    a, b, c = fresh(db, 3)
    pid = a.project_id
    tick(2027, 9, 30, 9)
    pl = plans.create(db, a, PlanType.new_worker, {"kind": "mobilisation"}, D(9, 30))
    db.commit()
    tick(2027, 10, 1, 0, 7)
    plans.run_daily(db, pid, D(10, 1))
    db.commit()
    db.refresh(pl)
    assert (pl.status, pl.status_reason) == (PlanStatus.cancelled, "season_ended")
    g = db.scalar(
        select(AcclimatisationPlan).where(AcclimatisationPlan.plan_no == "ACP-ANIA-EXP-2026-00412")
    )
    assert g is not None and g.status == PlanStatus.waiting_restriction
    for i in range(9):
        gate_in(db, b, D(4, 17) + timedelta(days=i))
    for i in range(4):
        gate_in(db, c, D(4, 17) + timedelta(days=i))
    db.commit()
    hc.clear_cache(db)
    tick(2028 - 1, 5, 1, 0, 7)
    plans.period_start(db, pid, D(5, 1))
    db.commit()
    assert [p.plan_type for p in plans_of(db, b) if p.trigger_date == D(5, 1)] == []
    (ps,) = [p for p in plans_of(db, c) if p.trigger_date == D(5, 1)]
    assert ps.plan_type == PlanType.period_start and ps.days[0]["max_pct"] == 50
