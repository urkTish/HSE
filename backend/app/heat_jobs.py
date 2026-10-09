"""Phase 6b scheduled jobs (6b-heat-stress §4, §7).

`heat_minute` (every 60 s): zone heat state is derived on read, so the minute job re-evaluates
Active outdoor permits (HEAT_STOP suspension within 60 s, §11.4), sends "work may resume" (HA-2),
overdue readings (HA-4), the non-permit ban pre-warning (HA-6) and plan-day confirmation alerts.
`heat_daily` (00:07): instrument quarantine on calibration expiry (HS-2), acclimatisation plans
(period start, advance, interruptions, catch-up), exemption expiry, coverage gaps (daily in the
controls period) and overdue reviews.
`heat_alerts` (07:04): calibration expiry 30 / 14 / 7 / 0, welfare checks missing yesterday,
exemption ending tomorrow, heat-illness reviews overdue.

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind
from app.core.heat_enums import InstrumentStatus
from app.models import HeatInstrument, HeatSettings
from app.services.cert.alerts import long_step

NK = NotificationKind
LONG = (30, 14, 7, 0)


def _projects(db: Session) -> list[Any]:
    return list(
        db.scalars(
            select(HeatSettings.project_id).where(HeatSettings.heat_register_from.is_not(None))
        )
    )


def heat_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.heat import alerts, plans  # noqa: PLC0415
    from app.services.heat import common as hc  # noqa: PLC0415
    from app.services.heat import ptw as heat_ptw  # noqa: PLC0415

    at = at or now()
    out = {"permits": 0, "resume": 0, "overdue": 0, "prewarn": 0, "unconfirmed": 0}
    for pid in _projects(db):
        if not hc.cfg(db, pid).active_on(hc.local_day(at)):
            continue
        out["permits"] += heat_ptw.refresh_outdoor(db, pid, at)
        out["resume"] += alerts.resume_check(db, pid, at, timedelta(minutes=1))
        out["overdue"] += alerts.overdue(db, pid, at)
        out["prewarn"] += alerts.prewarn(db, pid, at)
        out["unconfirmed"] += plans.unconfirmed_alerts(db, pid, at)
    db.flush()
    return out


def _coverage_gap_alert(db: Session, pid: Any, at: datetime) -> int:
    from app.services.heat import common as hc  # noqa: PLC0415
    from app.services.heat import config  # noqa: PLC0415

    cfg = hc.cfg(db, pid)
    d = hc.local_day(at)
    gaps = config.coverage_gaps(db, pid)
    if not gaps or not cfg.in_controls(d) or not hc.once(db, f"heat:gap:{pid}:{d.isoformat()}"):
        return 0
    return hc.send(
        db,
        hc.officers(db, pid) | hc.managers(db),
        NK.heat_coverage_gap,
        "Required zones without an active monitoring point: " + ", ".join(gaps),
        "مناطق مطلوبة بلا نقطة قياس فعالة: " + ", ".join(gaps),
        pid,
    )


def heat_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.heat import ban, plans, registers  # noqa: PLC0415
    from app.services.heat import common as hc  # noqa: PLC0415
    from app.services.heat import log as heat_log  # noqa: PLC0415

    at = at or now()
    d = hc.local_day(at)
    out = {"quarantined": registers.quarantine_expired(db, d), "expired": 0, "gaps": 0}
    for pid in _projects(db):
        if not hc.cfg(db, pid).active_on(d):
            continue
        plans.run_daily(db, pid, d)
        out["expired"] += ban.expire(db, pid, d)
        out["gaps"] += _coverage_gap_alert(db, pid, at)
        heat_log.overdue_alerts(db, pid, at)
    db.flush()
    return out


def heat_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.heat import ban, welfare  # noqa: PLC0415
    from app.services.heat import common as hc  # noqa: PLC0415
    from app.services.heat import log as heat_log  # noqa: PLC0415

    at = at or now()
    d = hc.local_day(at)
    out = {"calibration": 0, "welfare_missing": 0}
    pids = set(_projects(db))
    for x in db.scalars(
        select(HeatInstrument).where(
            HeatInstrument.status == InstrumentStatus.active,
            HeatInstrument.project_id.in_(pids),
        )
    ):
        step = long_step(db, f"heat:cal:{x.id}", x.calibration_valid_until, d, LONG)
        if step is None:
            continue
        out["calibration"] += hc.send(
            db,
            hc.officers(db, x.project_id),
            NK.heat_calibration_expiry,
            f"Calibration of {x.instrument_no} ends on {x.calibration_valid_until} ({step} days)",
            f"تنتهي معايرة {x.instrument_no} في {x.calibration_valid_until}",
            x.project_id,
            EntityType.heat_instrument,
            x.id,
            email=True,
        )
    for pid in pids:
        if not hc.cfg(db, pid).active_on(d):
            continue
        out["welfare_missing"] += welfare.missing_yesterday(db, pid, d - timedelta(days=1))
        ban.expire(db, pid, d)
        heat_log.overdue_alerts(db, pid, at)
    db.flush()
    return out


PHASE6B_JOBS = {
    "heat_minute": heat_minute,
    "heat_daily": heat_daily,
    "heat_alerts": heat_alerts,
}
