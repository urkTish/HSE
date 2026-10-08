"""5-training §9 ACs 14, 19, 34, 39, 89, 90 (provider alerts and blacklist scope, matrix
dating, due dates, refresher plan, gap panel)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.train_enums import TrainingRecordStatus
from app.models import (
    Deployment,
    Notification,
    TrainingProviderAccreditation,
    TrainingRecord,
)
from tests.conftest import Api
from tests.train_helpers import API, project, provider, worker

RS = TrainingRecordStatus
pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def test_P5AC14_accreditation_alert_schedule(db: Session) -> None:
    from app.train_jobs import _accreditation_expiry

    pv = provider(db, "HAYAT")
    acc = db.scalars(
        select(TrainingProviderAccreditation).where(
            TrainingProviderAccreditation.provider_id == pv.id,
            TrainingProviderAccreditation.valid_until == date(2027, 6, 30),
        )
    ).first()
    assert acc is not None
    fired = []
    d = date(2027, 5, 25)
    while d <= date(2027, 7, 1):
        _accreditation_expiry(db, d)
        db.flush()
        n = db.scalars(select(Notification.id).where(Notification.entity_id == acc.id)).first()
        if n is not None:
            fired.append(d)
            db.execute(delete(Notification).where(Notification.entity_id == acc.id))
        d += timedelta(days=1)
    assert fired == [date(2027, 5, 31), date(2027, 6, 16), date(2027, 6, 23), date(2027, 6, 30)]


def test_P5AC19_blacklist_issued_from(api: Api, db: Session) -> None:
    pv = provider(db, "ASTA")
    recs = db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.provider_id == pv.id,
            TrainingRecord.status == TrainingRecordStatus.accepted,
        )
    ).all()
    cut = date(2025, 3, 1)
    assert any(r.completed_on < cut for r in recs) and any(r.completed_on >= cut for r in recs)
    res = api.as_("faisal.harbi").post(
        f"{API}/training-providers/{pv.id}/transitions",
        json={"action": "blacklist", "blacklist_scope": "issued_from",
              "blacklist_from": cut.isoformat(),
              "reason": "Cards issued without attendance from March 2025 (test)"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    db.expire_all()
    for r in recs:
        db.refresh(r)
        want = (
            TrainingRecordStatus.revoked if r.completed_on >= cut else TrainingRecordStatus.accepted
        )
        assert r.status == want, (r.record_no, r.completed_on, r.status)


def test_P5AC34_effective_from_ignored(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    body = {"applies_to_kind": "trade", "applies_to_values": ["painter"],
            "requirement": {"course_code": "SCAFF-AWR"}, "level": "mandatory",
            "due_within_days": 14, "effective_from": "2026-09-01"}  # fmt: skip
    res = api.as_("noura.qahtani").post(f"{API}/projects/{pid}/training-matrix/lines", json=body)
    assert res.status_code in (200, 201), res.text
    assert res.json()["effective_from"] == "2026-10-06", res.json()


def test_P5AC39_due_then_gap(api: Api, db: Session) -> None:
    w = worker(db, "WKR-003291")  # labourer
    pid = project(db, "ANIA-EXP").id
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == w.id,
                                             Deployment.project_id == pid))  # fmt: skip
    assert dep is not None and dep.status == DeploymentStatus.mobilised
    dep.mobilised_on = date(2026, 9, 28)
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.worker_id == w.id, TrainingRecord.course_code == "HEAT-AWR"
        )
    ):
        r.status = TrainingRecordStatus.revoked  # no HEAT-AWR in force
    db.commit()
    c = api.as_("noura.qahtani")

    def heat(as_of: str) -> dict[str, object]:
        res = c.get(f"{API}/deployments/{dep.id}/training-requirements", params={"as_of": as_of})
        assert res.status_code == 200, res.text
        return next(r for r in res.json()["requirements"]
                    if r["requirement"]["course_code"] == "HEAT-AWR")  # fmt: skip

    r = heat("2026-10-04")
    assert r["due_date"] == "2026-10-05" and r["state"] == "due", r
    assert heat("2026-10-05")["state"] == "gap"


def test_P5AC89_heat_season_planning(db: Session) -> None:
    from app.services.train import gaps

    pid = project(db, "ANIA-EXP").id
    assert gaps.due_from(db, pid, "HEAT-AWR", date(2027, 5, 19)) == date(2027, 3, 20)
    # a record expiring after the season is planned on the plain 60-day rule
    assert gaps.due_from(db, pid, "HEAT-AWR", date(2027, 11, 30)) == date(2027, 10, 1)


def test_P5AC90_gap_on_live_permit(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    c = api.as_("faisal.harbi")
    res = c.get(f"{API}/dashboard/action-panel", params={"project_id": str(pid)})
    assert res.status_code == 200, res.text
    items = {i["key"]: i for i in res.json()["items"]}
    assert items["training_hook_gaps_on_live_work"]["count"] >= 1, items
    res = c.get(f"{API}/projects/{pid}/training-gaps",
                params={"course_code": "CSE-ATTENDANT", "page_size": 200})  # fmt: skip
    assert res.status_code == 200, res.text
    biju = [g for g in res.json()["items"] if g["worker"]["worker_no"] == "WKR-000017"]
    assert biju, res.json()["items"]
    assert "PTW-ANIA-EXP-2026-0413" in str(biju[0]["live_permits"]), biju[0]
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == worker(db, "WKR-000017").id,
                                             Deployment.project_id == pid))  # fmt: skip
    assert dep is not None and dep.status == DeploymentStatus.mobilised  # GP-8
