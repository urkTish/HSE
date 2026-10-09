"""Helpers for Phase 6b tests (6b-heat-stress Appendix A world, clock 2026-10-06 10:00 Riyadh).
Tests use the ``heat_seed`` fixture (Phase 0-6a template + the 6b seed, cloned per test) and
``clock``."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import (
    Contractor,
    HeatInstrument,
    MonitoringPoint,
    Notification,
    ProjectEngagement,
    RestStation,
    User,
    WbgtReading,
    Zone,
)
from tests.cert_helpers import API, CLOCK, P, expect, project, worker
from tests.train_helpers import kpi

__all__ = [
    "API",
    "CLOCK",
    "P",
    "eng",
    "err",
    "expect",
    "instrument",
    "kpi",
    "local",
    "notified",
    "point",
    "project",
    "reading",
    "station",
    "tick",
    "uid",
    "worker",
    "zone",
]


def local(y: int, m: int, d: int, h: int = 10, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=UTC) - timedelta(hours=3)


def tick(y: int, m: int, d: int, h: int = 10, mi: int = 0, s: int = 0) -> datetime:
    t = local(y, m, d, h, mi, s)
    set_now(t)
    return t


def zone(db: Session, code: str) -> Zone:
    z = db.scalar(select(Zone).where(Zone.code == code))
    assert z is not None, code
    return z


def point(db: Session, code: str) -> MonitoringPoint:
    p = db.scalar(select(MonitoringPoint).where(MonitoringPoint.point_code == code))
    assert p is not None, code
    return p


def instrument(db: Session, no: str) -> HeatInstrument:
    x = db.scalar(select(HeatInstrument).where(HeatInstrument.instrument_no == no))
    assert x is not None, no
    return x


def station(db: Session, code: str) -> RestStation:
    x = db.scalar(select(RestStation).where(RestStation.station_code == code))
    assert x is not None, code
    return x


def reading(db: Session, no: str) -> WbgtReading:
    x = db.scalar(select(WbgtReading).where(WbgtReading.reading_no == no))
    assert x is not None, no
    return x


def eng(db: Session, pcode: str, short: str) -> ProjectEngagement:
    e = db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(
            ProjectEngagement.project_id == project(db, pcode).id, Contractor.short_code == short
        )
    )
    assert e is not None, short
    return e


def uid(db: Session, who: str) -> uuid.UUID:
    u = db.scalar(select(User).where(User.email == f"{who}@example.com"))
    assert u is not None, who
    return u.id


def notified(db: Session, kind: str, since: datetime | None = None) -> dict[str, list[str]]:
    """username → titles of notifications of `kind` (optionally created at/after `since`)."""
    stmt = select(Notification, User.email).join(User, User.id == Notification.user_id)
    out: dict[str, list[str]] = {}
    for n, email in db.execute(stmt):
        k = getattr(n.kind, "value", n.kind)
        if k != kind or (since is not None and n.created_at < since):
            continue
        out.setdefault(email.split("@")[0], []).append(_title(n))
    return out


def _title(n: Any) -> str:
    for attr in ("title_en", "title", "message_en", "body_en"):
        v = getattr(n, attr, None)
        if v:
            return str(v)
    return ""


def day(d: date) -> str:
    return d.isoformat()


def err(res: Any) -> str:
    body = res.json()
    d = body.get("detail", body)
    return str(d.get("code") if isinstance(d, dict) else d)
