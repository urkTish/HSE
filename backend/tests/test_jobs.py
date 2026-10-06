"""Spec 1-dashboard §7 scheduled alerts, D-11 automatic month lock — AC36 and job smoke tests."""

import uuid
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import hse_jobs
from app.core.clock import now
from app.core.enums import NotificationKind
from app.models import CorrectiveAction, Notification, Observation, PeriodLock, Project
from tests.conftest import Api, Ids
from tests.hse_helpers import API, create_ca, reported_incident


def _recipients(db: Session, kind: NotificationKind, entity_id: str) -> set[str]:
    rows = db.scalars(
        select(Notification.user_id).where(
            Notification.kind == kind, Notification.entity_id == uuid.UUID(entity_id)
        )
    )
    return {str(u) for u in rows}


def test_AC36_high_risk_observation_without_ca_alerts(api: Api, ids: Ids, db: Session) -> None:
    res = api.as_("omar.siddiqui").post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/observations",
        json={
            "site_id": ids.site("S-AIR"),
            "observed_at": "2026-10-04T08:10:00Z",
            "observed_engagement_id": ids.engagement("GULFPAVE"),
            "obs_type": "unsafe_condition",
            "category": "airside_fod_control",
            "risk_rating": "high",
            "description": "Loose aggregate on TWB shoulder",
            "immediate_action": "Area coned off",
            "closed_on_spot": False,
        },
    )
    assert res.status_code == 201, res.text
    oid = res.json()["id"]
    assert hse_jobs.high_risk_observations(db)["alerted"] == 0  # not 24 h yet
    db.execute(
        update(Observation)
        .where(Observation.id == uuid.UUID(oid))
        .values(created_at=now() - timedelta(hours=25))
    )
    assert hse_jobs.high_risk_observations(db)["alerted"] == 1
    who = _recipients(db, NotificationKind.high_risk_observation_without_ca, oid)
    assert ids.user("noura.qahtani") in who  # HSE Officer
    assert ids.user("ahmed.zahrani") in who  # Contractor HSE Rep (RAWABI tree has GULFPAVE)
    assert hse_jobs.high_risk_observations(db)["alerted"] == 0  # sent once


def test_ca_overdue_escalates_once_per_day(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    ca = create_ca(n, ids, "incident", inc["id"])
    late = date.today() - timedelta(days=8)
    db.execute(
        update(CorrectiveAction)
        .where(CorrectiveAction.id == uuid.UUID(ca["id"]))
        .values(due_date=late, original_due_date=late)
    )
    first = hse_jobs.ca_alerts(db)
    assert first["overdue"] >= 1
    who = _recipients(db, NotificationKind.ca_overdue, ca["id"])
    assert ids.user("ramesh.kumar") in who  # owner
    assert ids.user("noura.qahtani") in who  # officer at ≥ 7 days
    assert ids.user("faisal.harbi") not in who  # manager only at ≥ 30 days
    again = hse_jobs.ca_alerts(db)
    assert again["overdue"] == 0  # once per day


def test_month_auto_lock_on_lock_day(db: Session) -> None:
    project = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    assert project is not None
    res = hse_jobs.month_auto_lock(db, date(2026, 10, 9))
    assert "ANIA-EXP:2026-09" not in res["locked"]  # before month_lock_day (10)
    res = hse_jobs.month_auto_lock(db, date(2026, 10, 10))
    assert "ANIA-EXP:2026-09" in res["locked"]
    row = db.get(PeriodLock, (project.id, date(2026, 9, 1)))
    assert row is not None and row.locked
    assert "ANIA-EXP:2026-09" not in hse_jobs.month_auto_lock(db, date(2026, 10, 11))["locked"]


def test_all_phase1_jobs_run(db: Session) -> None:
    for name, job in hse_jobs.PHASE1_JOBS.items():
        out = job(db)
        assert isinstance(out, dict), name
    db.rollback()
