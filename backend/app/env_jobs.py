"""Phase 6e scheduled jobs (6e-environmental §4, §7, P6e-2).

`env_minute` (every 60 s): station aggregates (MON-2: `1h` / `24h` derived as windows close, with
the exceedance rules), post-storm checks unmet at due (AIR-4).
`env_daily` (00:11, after `field_daily`): instruments quarantined at calibration expiry (MON-1),
background exceedances auto-reviewed and exceedances closed with their CA (EXD-3, §4.5), hazardous
storage overdue → one CA (WST-5), complainant data retention (P6e-2), settings cache reset.
`env_alerts` (07:08): permit and licence expiry (PRM-3), instrument calibration (MON-1),
consignments overdue (CON-6), hazardous storage reminders (WST-5), exceedance reviews due
(EXD-5), complaints due (CPL-1), aspect reviews (ASP-3).

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind, ProjectStatus
from app.core.env_enums import (
    AreaStatus,
    AspectStatus,
    ComplaintStatus,
    ConsignmentStatus,
    InstrumentStatus,
    PointSource,
)
from app.core.hse_enums import CaSourceType
from app.models import (
    EnvAspect,
    EnvComplaint,
    EnvInstrument,
    EnvPermit,
    EnvPoint,
    Project,
    WasteConsignment,
    WasteStorageArea,
)

NK = NotificationKind
ET = EntityType


def _projects(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(Project.id).where(Project.status != ProjectStatus.closed)))


def env_minute(db: Session) -> dict[str, Any]:
    from app.services.env import board, monitoring  # noqa: PLC0415
    from app.services.env import common as ec  # noqa: PLC0415

    t = now()
    derived = alerts = 0
    for pt in db.scalars(
        select(EnvPoint).where(
            EnvPoint.source_kind == PointSource.station, EnvPoint.active.is_(True)
        )
    ):
        derived += monitoring.derive(db, pt, t)
    for pid in _projects(db):
        for x in board.post_storm_tasks(db, pid, t - timedelta(hours=48), t):
            if x.overdue and ec.once(db, f"env:storm:{x.ops_no}:{x.site_id}"):
                alerts += ec.send(
                    db, ec.officers(db, pid) | ec.site_engineers(db, pid, x.site_id),
                    NK.post_storm_check,
                    f"Post-storm storage check not done on {x.site_code} after {x.ops_no}.",
                    f"لم يُنفذ فحص التخزين بعد العاصفة في {x.site_code} ({x.ops_no}).",
                    pid, ET.waste_storage_area, None,
                )  # fmt: skip
    db.flush()
    return {"derived": derived, "storm_alerts": alerts}


def env_daily(db: Session) -> dict[str, Any]:
    from app.services.env import common as ec  # noqa: PLC0415
    from app.services.env import exceedances, waste, water  # noqa: PLC0415

    ec.clear_cache(db)
    today = ec.local_day()
    quarantined = cas = purged = 0
    for x in db.scalars(
        select(EnvInstrument).where(
            EnvInstrument.status == InstrumentStatus.active,
            EnvInstrument.calibration_valid_until < today,
        )
    ):
        x.status, x.status_reason = InstrumentStatus.quarantined, "Calibration expired (MON-1)."
        quarantined += 1
    for pid in _projects(db):
        exceedances.daily(db, pid, today)
        pr = db.get(Project, pid)
        assert pr is not None  # noqa: S101
        for a in db.scalars(
            select(WasteStorageArea).where(
                WasteStorageArea.project_id == pid, WasteStorageArea.status == AreaStatus.active
            )
        ):
            for h in waste.haz_deadlines(db, a, today):
                key = f"env:haz_ca:{a.id}:{h.stream_code}:{h.started_on.isoformat()}"
                if h.overdue and ec.once(db, key):
                    ec.make_ca(
                        db, pr, CaSourceType.environmental, a.id, a.site_id, a.zone_id, None,
                        "major", f"Hazardous storage time exceeded: {a.area_code} {h.stream_code}",
                        f"{h.stream_code} stored in {a.area_code} since "
                        f"{h.started_on.isoformat()}; deadline {h.deadline.isoformat()} "
                        "passed (WST-5). Dispatch the waste.",
                        None, None, None,
                    )  # fmt: skip
                    cas += 1
        purged += water.retention(db, pid, today)
    db.flush()
    return {"quarantined": quarantined, "haz_cas": cas, "contacts_deleted": purged}


def _renewed(db: Session, pm: EnvPermit) -> bool:
    """PRM-3: a renewal of the same requirement that is (or will be) in force the day after."""
    from app.services.env import common as ec  # noqa: PLC0415

    if pm.valid_to is None or pm.project_id is None or not pm.requirement_code:
        return False
    nxt = pm.valid_to + timedelta(days=1)
    return any(
        o.id != pm.id and o.requirement_code == pm.requirement_code and ec.in_force(o, nxt)
        for o in ec.project_permits(db, pm.project_id)
    )


def _permit_alerts(db: Session, pid: uuid.UUID, today: date) -> int:
    from app.services.env import board  # noqa: PLC0415
    from app.services.env import common as ec  # noqa: PLC0415

    c = ec.cfg(db, pid)
    n = 0
    users = ec.officers(db, pid) | ec.managers(db)
    for pm in ec.project_permits(db, pid):
        if pm.valid_to is None or pm.manual_status is not None or _renewed(db, pm):
            continue
        left = (pm.valid_to - today).days
        steps = [int(x) for x in c["permit_alert_days"]] + [-1]
        if left in steps and ec.once(db, f"env:permit:{pm.id}:{left}"):
            en = (
                f"{pm.record_no} expired on {pm.valid_to.isoformat()} with no renewal."
                if left < 0
                else f"{pm.record_no} expires on {pm.valid_to.isoformat()} ({left} days)."
            )
            n += ec.send(db, users, NK.env_permit_expiry, en,
                         f"{pm.record_no} ينتهي بتاريخ {pm.valid_to.isoformat()}.", pid,
                         ET.env_permit, pm.id, email=True)  # fmt: skip
    days = [int(x) for x in c["provider_licence_alert_days"]]
    for prov in board.used_providers(db, pid, today):
        for lic in ec.licences(db, prov):
            if lic.valid_to is None or lic.manual_status is not None:
                continue
            left = (lic.valid_to - today).days
            if left in days and ec.once(db, f"env:licence:{lic.id}:{pid}:{left}"):
                n += ec.send(
                    db, ec.officers(db, pid), NK.env_permit_expiry,
                    f"Provider licence {lic.record_no} expires on {lic.valid_to.isoformat()}.",
                    f"ترخيص مقدم الخدمة {lic.record_no} ينتهي بتاريخ {lic.valid_to.isoformat()}.",
                    pid, ET.env_permit, lic.id, email=True,
                )  # fmt: skip
    return n


def env_alerts(db: Session) -> dict[str, Any]:
    from app.services.env import common as ec  # noqa: PLC0415
    from app.services.env import exceedances, waste  # noqa: PLC0415

    ec.clear_cache(db)
    today = ec.local_day()
    n = 0
    for pid in _projects(db):
        offs = ec.officers(db, pid)
        n += _permit_alerts(db, pid, today)
        for x in db.scalars(
            select(EnvInstrument).where(
                EnvInstrument.project_id == pid, EnvInstrument.status != InstrumentStatus.retired
            )
        ):
            left = (x.calibration_valid_until - today).days
            if left in (30, 14, 7, 0) and ec.once(db, f"env:cal:{x.id}:{left}"):
                n += ec.send(db, offs, NK.env_instrument_calibration,
                             f"{x.instrument_no} calibration ends "
                             f"{x.calibration_valid_until.isoformat()}.",
                             f"تنتهي معايرة {x.instrument_no}.", pid, ET.env_instrument, x.id,
                             email=True)  # fmt: skip
        for c in db.scalars(
            select(WasteConsignment).where(
                WasteConsignment.project_id == pid,
                WasteConsignment.status == ConsignmentStatus.dispatched,
                WasteConsignment.due_on < today,
            )
        ):
            late = (today - c.due_on).days - 1
            if late % 7 == 0 and ec.once(db, f"env:con_overdue:{c.id}:{today.isoformat()}"):
                users = offs | ec.reps(db, pid, c.generator_engagement_id)
                if c.dispatched_by_user_id:
                    users.add(c.dispatched_by_user_id)
                n += ec.send(db, users, NK.consignment_overdue,
                             f"{c.consignment_no}: no receipt proof (due {c.due_on.isoformat()}).",
                             f"{c.consignment_no}: لم يُسجل إثبات الاستلام.", pid,
                             ET.waste_consignment, c.id, email=True)  # fmt: skip
        for a in db.scalars(
            select(WasteStorageArea).where(
                WasteStorageArea.project_id == pid, WasteStorageArea.status == AreaStatus.active
            )
        ):
            for h in waste.haz_deadlines(db, a, today):
                if h.days_left in (14, 0, -1):
                    key = f"env:haz:{a.id}:{h.stream_code}:{h.started_on}:{h.days_left}"
                    if ec.once(db, key):
                        n += ec.send(
                            db, offs | ec.site_engineers(db, pid, a.site_id),
                            NK.haz_storage_deadline,
                            f"{a.area_code} {h.stream_code}: storage deadline "
                            f"{h.deadline.isoformat()} ({h.days_left} days left).",
                            f"{a.area_code}: مهلة تخزين النفايات الخطرة {h.deadline.isoformat()}.",
                            pid, ET.waste_storage_area, a.id, email=True,
                        )  # fmt: skip
        n += exceedances.review_alerts(db, pid, today)
        for cp in db.scalars(
            select(EnvComplaint).where(
                EnvComplaint.project_id == pid, EnvComplaint.status == ComplaintStatus.open
            )
        ):
            step = (today - cp.response_due_on).days
            if step in (-1, 1) and ec.once(db, f"env:cpl:{cp.id}:{step}"):
                n += ec.send(db, offs, NK.env_complaint,
                             f"Complaint {cp.complaint_no} reply due "
                             f"{cp.response_due_on.isoformat()}.",
                             f"موعد الرد على الشكوى {cp.complaint_no}.", pid, ET.env_complaint,
                             cp.id, email=True)  # fmt: skip
        for asp in db.scalars(
            select(EnvAspect).where(
                EnvAspect.project_id == pid, EnvAspect.status == AspectStatus.active
            )
        ):
            if asp.review_due_on is None:
                continue
            left = (asp.review_due_on - today).days
            if left in (30, 0) and ec.once(db, f"env:asp:{asp.id}:{asp.review_due_on}:{left}"):
                n += ec.send(
                    db,
                    offs,
                    NK.aspect_review,
                    f"{asp.aspect_no} annual review due {asp.review_due_on.isoformat()}.",
                    f"مراجعة {asp.aspect_no} مستحقة.",
                    pid,
                    ET.env_aspect,
                    asp.id,
                )
    db.flush()
    return {"alerts": n}


PHASE6E_JOBS = {
    "env_minute": env_minute,
    "env_daily": env_daily,
    "env_alerts": env_alerts,
}
