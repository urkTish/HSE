"""Q3 measurements for Q2's out-of-tolerance review (spec 8-quality Q-CAL-04, D-370).

A logger or probe found out of tolerance must list "readings of monitoring points to which the
logger was assigned in the period". A point logs every 15 minutes, so one item per reading would
bury the reviewer; Q3 reports one item per monitoring point and local day: the reading of that day
closest to a limit of the zone range (the one whose margin decides the proposal), with the number
of readings in the ref. Readings count for a logger while it was assigned to the point (imported
readings carry no instrument) and for a probe when the reading names it (manual readings).

The logger-assignment and manual-reading rows that Q3 writes to `q_mte_usage` (record id = the
monitoring point) are covered by these items, so `covered` tells Q2 to skip them."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.quality.common import QRecordType
from app.core.quality.q3 import QReadingTarget
from app.models import Project
from app.models.quality import QMteItem, QMteUsage
from app.models.quality.q3 import QMonitoringPoint, QReading, QStorageZone
from app.services.quality.q2 import base as b2

RECORD_TYPE = "monitoring_point"
_POINT_USAGE_TYPES = (QRecordType.mapping_study.value, QRecordType.excursion.value)


def _iso(v: Any) -> datetime | None:
    if not v:
        return None
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def _margin(v: Decimal, lo: Decimal | None, hi: Decimal | None) -> Decimal | None:
    ms = [abs(v - x) for x in (lo, hi) if x is not None]
    return min(ms) if ms else None


def items(db: Session, m: QMteItem, period_from: date, period_to: date) -> list[dict[str, Any]]:
    """`OOT_SOURCES` provider: one item per monitoring point and day measured with `m`."""
    project = db.get(Project, m.project_id)
    if project is None:
        return []
    a = b2.day_start(project, period_from)
    z_ = b2.day_end(project, period_to)
    mid = str(m.id)
    points = db.scalars(
        select(QMonitoringPoint).where(QMonitoringPoint.project_id == project.id)
    ).all()
    out: list[dict[str, Any]] = []
    for pt in points:
        windows = []
        for lg in pt.loggers or []:
            if str(lg.get("mte_id")) != mid:
                continue
            f = max(_iso(lg.get("from")) or a, a)
            t = min(_iso(lg.get("to")) or z_, z_)
            if f < t:
                windows.append(and_(QReading.measured_at >= f, QReading.measured_at < t))
        cond = QReading.mte_id == m.id
        if windows:
            cond = or_(cond, and_(QReading.mte_id.is_(None), or_(*windows)))
        rows = db.execute(
            select(QReading.measured_at, QReading.temperature_c)
            .where(
                QReading.target_type == QReadingTarget.point,
                QReading.target_id == pt.id,
                QReading.voided.is_(False),
                QReading.temperature_c.is_not(None),
                QReading.measured_at >= a,
                QReading.measured_at < z_,
                cond,
            )
            .order_by(QReading.measured_at)
        ).all()
        if not rows:
            continue
        zone = db.get(QStorageZone, pt.zone_id)
        lo = zone.temp_min if zone is not None else None
        hi = zone.temp_max if zone is not None else None
        days: dict[date, list[Any]] = {}
        for at, temp in rows:
            d = b2.local_day(project, at)
            day = days.setdefault(d, [None, None, None, 0])
            day[3] += 1
            mg = _margin(temp, lo, hi) if temp is not None else None
            if day[0] is None or (mg is not None and (day[2] is None or mg < day[2])):
                day[0], day[1], day[2] = at, temp, mg
        for d, (at, temp, _mg, n) in sorted(days.items()):
            out.append(
                {
                    "record_type": RECORD_TYPE,
                    "record_id": pt.id,
                    "ref": f"{pt.code} · {d.isoformat()} · {n} readings"[:60],
                    "used_at": at,
                    "value": temp,
                    "limit_low": lo,
                    "limit_high": hi,
                }
            )
    return out


def covered(db: Session, u: QMteUsage) -> bool:
    """`OOT_USAGE_COVERED` provider: Q3's own usage rows of a monitoring point."""
    return u.record_type in _POINT_USAGE_TYPES and db.get(QMonitoringPoint, u.record_id) is not None


def register() -> None:
    from app.services.quality.q2 import calibration  # noqa: PLC0415

    if items not in calibration.OOT_SOURCES:
        calibration.OOT_SOURCES.append(items)
    if covered not in calibration.OOT_USAGE_COVERED:
        calibration.OOT_USAGE_COVERED.append(covered)
