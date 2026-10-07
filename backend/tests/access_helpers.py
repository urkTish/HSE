"""Lookups and clock helpers for Phase 2 tests (Appendix A world, "today" = 2026-10-06)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Adp,
    AirportPass,
    Avp,
    Deployment,
    Gate,
    InductionCourse,
    InductionRecord,
    Notification,
    NotamRequest,
    ObstacleClearance,
    Project,
    Vehicle,
    Wap,
    Worker,
)

API = "/api/v1"
RIYADH = ZoneInfo("Asia/Riyadh")
TODAY = date(2026, 10, 6)


def riyadh(y: int, m: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    """A local Asia/Riyadh wall-clock time as an aware UTC datetime."""
    return datetime(y, m, d, h, mi, s, tzinfo=RIYADH).astimezone(UTC)


def utc(y: int, m: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=UTC)


NOON = riyadh(2026, 10, 6, 12)


def project_id(db: Session, code: str) -> uuid.UUID:
    pid = db.scalar(select(Project.id).where(Project.code == code))
    assert pid is not None, code
    return pid


def worker(db: Session, name: str) -> Worker:
    w = db.scalar(select(Worker).where(Worker.full_name_en == name))
    assert w is not None, name
    return w


def deployment(db: Session, name: str) -> Deployment:
    w = worker(db, name)
    d = db.scalar(
        select(Deployment)
        .where(Deployment.worker_id == w.id)
        .order_by(Deployment.mobilised_on.desc())
        .limit(1)
    )
    assert d is not None, name
    return d


def induction(db: Session, name: str, code: str, status: Any = None) -> InductionRecord:
    w = worker(db, name)
    q = (
        select(InductionRecord)
        .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
        .where(InductionRecord.worker_id == w.id, InductionCourse.code == code)
        .order_by(InductionRecord.delivered_on.desc())
    )
    if status is not None:
        q = q.where(InductionRecord.status == status)
    r = db.scalars(q).first()
    assert r is not None, (name, code)
    return r


def airport_pass(db: Session, name: str) -> AirportPass:
    w = worker(db, name)
    ps = db.scalars(
        select(AirportPass)
        .where(AirportPass.worker_id == w.id)
        .order_by(AirportPass.issued_on.desc())
    ).first()
    assert ps is not None, name
    return ps


def adp(db: Session, name: str) -> Adp:
    w = worker(db, name)
    a = db.scalars(select(Adp).where(Adp.worker_id == w.id).order_by(Adp.created_at.desc())).first()
    assert a is not None, name
    return a


def vehicle(db: Session, no: str) -> Vehicle:
    v = db.scalar(select(Vehicle).where(Vehicle.vehicle_no == no))
    assert v is not None, no
    return v


def avp(db: Session, vehicle_no: str) -> Avp:
    v = vehicle(db, vehicle_no)
    a = db.scalars(select(Avp).where(Avp.vehicle_id == v.id).order_by(Avp.created_at.desc())).first()
    assert a is not None, vehicle_no
    return a


def wap(db: Session, no_suffix: str) -> Wap:
    w = db.scalar(
        select(Wap).where(Wap.wap_no.like(f"%{no_suffix}"), Wap.revision_of_id.is_(None))
    )
    assert w is not None, no_suffix
    return w


def notam(db: Session, no_suffix: str) -> NotamRequest:
    n = db.scalar(select(NotamRequest).where(NotamRequest.ntm_no.like(f"%{no_suffix}")))
    assert n is not None, no_suffix
    return n


def obstacle(db: Session, no_suffix: str) -> ObstacleClearance:
    o = db.scalar(select(ObstacleClearance).where(ObstacleClearance.obs_no.like(f"%{no_suffix}")))
    assert o is not None, no_suffix
    return o


def gate(db: Session, code: str) -> Gate:
    g = db.scalar(select(Gate).where(Gate.gate_code == code))
    assert g is not None, code
    return g


def notifications(db: Session, kind: Any, entity_id: uuid.UUID | None = None) -> list[Notification]:
    q = select(Notification).where(Notification.kind == kind)
    if entity_id is not None:
        q = q.where(Notification.entity_id == entity_id)
    return list(db.scalars(q))


def days(n: int) -> timedelta:
    return timedelta(days=n)
