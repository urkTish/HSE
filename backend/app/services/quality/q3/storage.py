"""Storage zones, monitoring points, logger assignments and readings (spec 8-quality §D.3,
Q-STO-01…07): class defaults, audited range changes that require re-mapping (Q-MAP-06), manual
readings with the probe's M&TE (Q-STO-02), coverage / gaps / time out of range (Q-STO-04 / -05),
the zone profile chart (C48) and mean kinetic temperature (Q-EXC-12)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode
from app.core.quality.common import QRecordType
from app.core.quality.q3 import (
    MKT_CLASSES,
    STORAGE_CLASSES,
    QExcursionStatus,
    QMappingState,
    QReadingSource,
    QReadingTarget,
    QStorageClass,
    QZoneRole,
)
from app.models import Project, Site, Zone
from app.models.quality.q3 import (
    QExcursion,
    QMonitoringGap,
    QMonitoringPoint,
    QReading,
    QStorageZone,
    QZoneDay,
)
from app.services import audit
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import mte as mte_svc
from app.services.quality.q3 import base as b
from app.services.quality.q3 import engine as eng

C = Capability
RT = QRecordType


# ---- zones --------------------------------------------------------------------------------------


def limits(z: QStorageZone) -> eng.Limits:
    return eng.Limits(z.temp_min, z.temp_max)


def humidity_limits(z: QStorageZone) -> eng.Limits:
    return eng.Limits(z.humidity_min, z.humidity_max)


def bands(z: QStorageZone) -> eng.Bands:
    return eng.Bands(z.alarm_delay_minutes, z.d1, z.d2, z.t1, z.t2)


def zone_row(db: Session, p: Principal, zone_id: uuid.UUID) -> tuple[QStorageZone, Project]:
    z = db.get(QStorageZone, zone_id)
    if z is None or not p.can_see_project(z.project_id):
        raise b.not_found(db, p, RT.excursion, zone_id, z.project_id if z else None)
    project = qc.get_project(db, p, z.project_id)
    g = p.grant(project.id, C.quality_view)
    if g is None or (g.scope.value != "responsible" and not g.covers_site(z.site_id)):
        raise b.not_found(db, p, RT.excursion, zone_id, project.id)
    return z, project


def points_of(db: Session, zone_id: uuid.UUID, active: bool = True) -> list[QMonitoringPoint]:
    q = select(QMonitoringPoint).where(QMonitoringPoint.zone_id == zone_id)
    if active:
        q = q.where(QMonitoringPoint.active.is_(True))
    return list(db.scalars(q.order_by(QMonitoringPoint.code)))


def zone_grid(
    db: Session, z: QStorageZone, t0: datetime, t1: datetime, *, humidity: bool = False
) -> eng.Grid:
    pts = points_of(db, z.zone_id)
    ids = [x.id for x in pts]
    factor = b.dsetting(db, z.project_id, "reading_gap_factor")
    rows: list[eng.Reading] = []
    if ids:
        # a reading before t0 still covers the first minutes of the window
        look = t0 - timedelta(minutes=max(x.interval_minutes for x in pts) * float(factor) + 1)
        for r in db.execute(
            select(
                QReading.target_id,
                QReading.measured_at,
                QReading.humidity_pct if humidity else QReading.temperature_c,
                QReading.id,
                QReading.probe_fault,
            ).where(
                QReading.target_type == QReadingTarget.point,
                QReading.target_id.in_(ids),
                QReading.voided.is_(False),
                QReading.measured_at >= look,
                QReading.measured_at < t1,
            )
        ):
            rows.append(eng.Reading(r[0], r[1], r[2], r[3], r[4]))
    lim = humidity_limits(z) if humidity else limits(z)
    return eng.grid(rows, {x.id: x.interval_minutes for x in pts}, factor, lim, t0, t1)


def defaults_for(sc: QStorageClass) -> dict[str, Any]:
    d = STORAGE_CLASSES[sc]
    return {
        "temp_min": d.temp_min,
        "temp_max": d.temp_max,
        "alarm_delay_minutes": d.alarm_delay,
        "d1": d.d1,
        "d2": d.d2,
        "t1": d.t1,
        "t2": d.t2,
        "humidity_max": d.humidity_max,
    }


RANGE_KEYS = ("temp_min", "temp_max", "humidity_min", "humidity_max")
EDIT_KEYS = (
    *RANGE_KEYS,
    "setpoint",
    "alarm_delay_minutes",
    "d1",
    "d2",
    "t1",
    "t2",
    "interval_minutes",
    "role",
    "active",
)


def _check_zone(z: QStorageZone) -> None:
    if z.temp_min is not None and z.temp_max is not None and z.temp_min >= z.temp_max:
        raise qc.field_err(
            "temp_min",
            "The minimum must be below the maximum.",
            "يجب أن يكون الحد الأدنى أقل من الأعلى.",
        )
    if z.d1 <= 0 or z.d2 < z.d1 or z.t1 <= 0 or z.t2 < z.t1 or z.alarm_delay_minutes < 0:
        raise qc.field_err(
            "d1",
            "Bands must be positive and d1 ≤ d2, t1 ≤ t2.",
            "يجب أن تكون الحدود موجبة ومتصاعدة.",
        )
    if z.interval_minutes < 1 or z.interval_minutes > 240:
        raise qc.field_err(
            "interval_minutes", "Interval 1–240 minutes.", "الفاصل بين 1 و240 دقيقة."
        )


def create_zone(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT.mapping_study, C.storage_manage)
    zone = b.zone_of(db, project, body["zone_id"])
    b.require_site(g, zone.site_id)
    if db.get(QStorageZone, zone.id) is not None:
        raise qc.field_err(
            "zone_id", "This zone already has storage settings.", "لهذه المنطقة إعدادات تخزين."
        )
    sc = QStorageClass(body["storage_class"])
    vals = defaults_for(sc)
    t = now()
    z = QStorageZone(
        zone_id=zone.id,
        project_id=project.id,
        site_id=zone.site_id,
        storage_class=sc,
        role=QZoneRole(body.get("role") or "storage"),
        setpoint=body.get("setpoint"),
        interval_minutes=body.get("interval_minutes") or 15,
        mapping_state=QMappingState.not_mapped,
        change_notes=[],
        alerts_sent=[],
        created_at=t,
        updated_at=t,
        **vals,
    )
    for k in EDIT_KEYS:
        if body.get(k) is not None and k not in ("role",):
            setattr(z, k, body[k])
    _check_zone(z)
    db.add(z)
    db.flush()
    b.audit_create(db, p, project, RT.mapping_study, z.zone_id, storage_class=sc.value)
    return zone_read(db, p, z)


def update_zone(
    db: Session, p: Principal, zone_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    z, project = zone_row(db, p, zone_id)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    b.require_site(g, z.site_id)
    before = {k: getattr(z, k) for k in EDIT_KEYS}
    if body.get("storage_class") and body["storage_class"] != z.storage_class:
        z.storage_class = QStorageClass(body["storage_class"])
        for k, v in defaults_for(z.storage_class).items():
            setattr(z, k, v)
    for k in EDIT_KEYS:
        if k in body and body[k] is not None:
            setattr(z, k, QZoneRole(body[k]) if k == "role" else body[k])
    _check_zone(z)
    after = {k: getattr(z, k) for k in EDIT_KEYS}
    changed = {k for k in EDIT_KEYS if before[k] != after[k]}
    if changed & set(RANGE_KEYS[:2]):
        # Q-STO-01 / Q-MAP-06: a range change requires a new study of purpose after_change
        z.mapping_state = QMappingState.remap_required
        z.remap_reason = "range_change"
    if changed & set(RANGE_KEYS):
        invalidate_days(db, z.zone_id)  # coverage and TOR follow the new limits (D-351)
    z.updated_at = now()
    if changed:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_mapping_study,
            entity_id=z.zone_id,
            project_id=project.id,
            before={k: str(before[k]) for k in changed},
            after={k: str(after[k]) for k in changed},
            details={"storage_zone": True},
        )
    return zone_read(db, p, z)


def change_note(
    db: Session, p: Principal, zone_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Q-MAP-06: a layout or HVAC change note sets `remap_required`."""
    z, project = zone_row(db, p, zone_id)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    b.require_site(g, z.site_id)
    kind = body.get("kind")
    if kind not in ("layout", "hvac"):
        raise qc.field_err("kind", "Kind is layout or hvac.", "النوع: تخطيط أو تكييف.")
    note = qc.reason(body.get("note"), 20, "note")
    z.change_notes = [
        *z.change_notes,
        {"kind": kind, "note": note, "by": str(p.user.id), "at": now().isoformat()},
    ]
    z.mapping_state = QMappingState.remap_required
    z.remap_reason = f"{kind}_change"
    z.updated_at = now()
    b.audit_status(db, p, project, RT.mapping_study, z.zone_id, None, "remap_required", kind=kind)
    return zone_read(db, p, z)


def live_status(db: Session, z: QStorageZone, at: datetime | None = None) -> str:
    """Zone list colour (§D.10): excursion · gap · not_mapped · in_range."""
    t = b.floor_minute(at or now())
    live = db.scalar(
        select(QExcursion.id).where(
            QExcursion.zone_id == z.zone_id,
            QExcursion.transient.is_(False),
            QExcursion.ended_at.is_(None),
            QExcursion.status.in_([QExcursionStatus.detected, QExcursionStatus.under_assessment]),
        )
    )
    if live is not None:
        return "excursion"
    gmin = int(b.setting(db, z.project_id, "monitoring_gap_alert_minutes"))
    gr = zone_grid(db, z, t - timedelta(minutes=gmin), t)
    if gr.n and gr.mon.count(1) == 0:
        return "gap"
    project = db.get(Project, z.project_id)
    stale = bool(project and z.mapped_until and z.mapped_until < qc.project_day(project))
    if z.mapping_state != QMappingState.mapped or stale:
        return "not_mapped"
    return "in_range"


def zone_read(
    db: Session, p: Principal | None, z: QStorageZone, *, status: bool = False
) -> dict[str, Any]:
    zone = db.get(Zone, z.zone_id)
    pts = points_of(db, z.zone_id, active=False)
    out: dict[str, Any] = {
        "zone_id": z.zone_id,
        "project_id": z.project_id,
        "site": b.site_ref(db, z.site_id),
        "code": zone.code if zone else "",
        "name_en": zone.name_en if zone else "",
        "name_ar": zone.name_ar if zone else "",
        "storage_class": z.storage_class,
        "role": z.role,
        "temp_min": z.temp_min,
        "temp_max": z.temp_max,
        "setpoint": z.setpoint,
        "humidity_min": z.humidity_min,
        "humidity_max": z.humidity_max,
        "alarm_delay_minutes": z.alarm_delay_minutes,
        "d1": z.d1,
        "d2": z.d2,
        "t1": z.t1,
        "t2": z.t2,
        "interval_minutes": z.interval_minutes,
        "mapping_state": z.mapping_state,
        "mapped_until": z.mapped_until,
        "remap_reason": z.remap_reason,
        "change_notes": z.change_notes,
        "dispatch_override_allowed": STORAGE_CLASSES[z.storage_class].dispatch_override_allowed,
        "active": z.active,
        "points": [point_read(db, x) for x in pts],
    }
    if status:
        out["live_status"] = live_status(db, z)
    return out


def list_zones(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    rows = db.scalars(select(QStorageZone).where(QStorageZone.project_id == project.id))
    out = []
    for z in rows:
        if g.scope.value != "responsible" and not g.covers_site(z.site_id):
            continue
        out.append(zone_read(db, p, z, status=True))
    return sorted(out, key=lambda r: r["code"])


# ---- points and loggers -------------------------------------------------------------------------


def point_read(db: Session, pt: QMonitoringPoint) -> dict[str, Any]:
    return {
        "id": pt.id,
        "zone_id": pt.zone_id,
        "code": pt.code,
        "position": pt.position,
        "position_note": pt.position_note,
        "interval_minutes": pt.interval_minutes,
        "loggers": [
            {**lg, "mte": b.mte_ref(db, uuid.UUID(lg["mte_id"]))} for lg in pt.loggers or []
        ],
        "active": pt.active,
    }


def create_point(
    db: Session, p: Principal, zone_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    z, project = zone_row(db, p, zone_id)
    _, g = b.project_for_create(db, p, project.id, RT.mapping_study, C.storage_manage)
    b.require_site(g, z.site_id)
    code = body["code"].strip().upper()
    if db.scalar(
        select(QMonitoringPoint.id).where(
            QMonitoringPoint.project_id == project.id, QMonitoringPoint.code == code
        )
    ):
        raise qc.field_err("code", "This point code is already used.", "رمز النقطة مستخدم.")
    pt = QMonitoringPoint(
        project_id=project.id,
        zone_id=z.zone_id,
        code=code,
        position=body.get("position") or "general",
        position_note=body.get("position_note"),
        interval_minutes=body.get("interval_minutes") or z.interval_minutes,
        loggers=[],
        active=True,
        created_by_user_id=p.user.id,
    )
    db.add(pt)
    db.flush()
    invalidate_days(db, z.zone_id)
    return point_read(db, pt)


def point_row(
    db: Session, p: Principal, point_id: uuid.UUID
) -> tuple[QMonitoringPoint, QStorageZone, Project]:
    pt = db.get(QMonitoringPoint, point_id)
    if pt is None:
        raise b.not_found(db, p, RT.excursion, point_id, None)
    z, project = zone_row(db, p, pt.zone_id)
    return pt, z, project


def update_point(
    db: Session, p: Principal, point_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    pt, z, project = point_row(db, p, point_id)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    b.require_site(g, z.site_id)
    before = (pt.interval_minutes, pt.active)
    for k in ("position", "position_note", "interval_minutes", "active"):
        if k in body and body[k] is not None:
            setattr(pt, k, body[k])
    if (pt.interval_minutes, pt.active) != before:
        db.flush()
        invalidate_days(db, z.zone_id)  # which points cover a minute changed (D-351)
    pt.updated_by_user_id = p.user.id
    return point_read(db, pt)


def assign_logger(
    db: Session, p: Principal, point_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Q-STO-03: a logger assignment records M&TE usage for its period; an overdue or
    out-of-service logger warns or blocks per `mte_use_policy` (Q-SHR-04)."""
    pt, z, project = point_row(db, p, point_id)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    b.require_site(g, z.site_id)
    m = b.mte_of(db, project, body["mte_id"])
    start: datetime = body.get("from") or now()
    loggers = []
    for lg in pt.loggers or []:
        loggers.append({**lg, "to": start.isoformat()} if lg.get("to") is None else lg)
    _, warnings = mte_svc.record_usage(
        db, project, m.id, RT.mapping_study, pt.id, p.user.id, start, f"logger at {pt.code}"
    )
    loggers.append({"mte_id": str(m.id), "from": start.isoformat(), "to": None})
    pt.loggers = loggers
    return {**point_read(db, pt), "warnings": b.warn_dump(warnings)}


def point_for_serial(
    db: Session, project_id: uuid.UUID, serial: str, at: datetime
) -> QMonitoringPoint | None:
    """The point a logger (by serial) was assigned to at `at` (logger files name the serial)."""
    from app.models.quality import QMteItem  # noqa: PLC0415

    m = db.scalar(
        select(QMteItem).where(QMteItem.project_id == project_id, QMteItem.serial_no == serial)
    )
    if m is None:
        return None
    for pt in db.scalars(select(QMonitoringPoint).where(QMonitoringPoint.project_id == project_id)):
        for lg in pt.loggers or []:
            if lg["mte_id"] != str(m.id):
                continue
            f = datetime.fromisoformat(lg["from"])
            t = datetime.fromisoformat(lg["to"]) if lg.get("to") else None
            if f <= at and (t is None or at < t):
                return pt
    return None


# ---- manual readings (Q-STO-02) ------------------------------------------------------------------


def manual_reading(
    db: Session, p: Principal, point_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    from app.services.quality.q3 import excursions  # noqa: PLC0415

    pt, z, project = point_row(db, p, point_id)
    _, g = b.project_for_create(db, p, project.id, RT.excursion, C.reading_record)
    b.require_site(g, z.site_id)
    at: datetime = body["measured_at"]
    t = now()
    if at > t + timedelta(minutes=5):
        raise qc.err(
            422,
            ErrorCode.CLOCK_SKEW,
            "The reading time is in the future; check the device clock.",
            "وقت القراءة في المستقبل؛ تحقق من ساعة الجهاز.",
        )
    max_age = int(b.setting(db, project.id, "manual_reading_max_age_hours"))
    if at < t - timedelta(hours=max_age):
        raise qc.err(
            422,
            ErrorCode.READING_TOO_OLD,
            f"Manual readings older than {max_age} h cannot be entered; import the logger file.",
            f"لا يمكن إدخال قراءة يدوية أقدم من {max_age} ساعة؛ استورد ملف المسجل.",
        )
    if body.get("temperature_c") is None and body.get("humidity_pct") is None:
        raise qc.field_err(
            "temperature_c", "Enter a temperature or a humidity.", "أدخل الحرارة أو الرطوبة."
        )
    mte_id = body.get("mte_id")
    if mte_id is None:
        raise qc.err(
            422, ErrorCode.MTE_REQUIRED, "Scan or pick the probe used.", "اختر المجس المستخدم."
        )
    b.mte_of(db, project, mte_id)
    exists = db.scalar(
        select(QReading.id).where(
            QReading.target_type == QReadingTarget.point,
            QReading.target_id == pt.id,
            QReading.channel == "",
            QReading.measured_at == at,
            QReading.voided.is_(False),
        )
    )
    if exists is not None:
        raise qc.field_err(
            "measured_at", "A reading at this time already exists.", "توجد قراءة في هذا الوقت."
        )
    r = QReading(
        project_id=project.id,
        target_type=QReadingTarget.point,
        target_id=pt.id,
        channel="",
        measured_at=at,
        temperature_c=body.get("temperature_c"),
        humidity_pct=body.get("humidity_pct"),
        source=QReadingSource.manual,
        mte_id=mte_id,
        entered_by_user_id=p.user.id,
        probe_fault=False,
        voided=False,
        created_at=t,
    )
    db.add(r)
    db.flush()
    _, warnings = mte_svc.record_usage(
        db, project, mte_id, RT.excursion, pt.id, p.user.id, at, f"reading {r.id}"
    )
    found = excursions.detect_zone(
        db, project, z, at - timedelta(hours=1), at + timedelta(minutes=1), p.user.id, manual=True
    )
    return {
        "reading": reading_read(r),
        "excursions": [excursions.brief(x) for x in found],
        "warnings": b.warn_dump(warnings),
    }


def annotate(db: Session, p: Principal, reading_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """Q-STO-07: corrections are annotations; the value never changes."""
    r = db.get(QReading, reading_id)
    if r is None or not p.can_see_project(r.project_id):
        raise b.not_found(db, p, RT.excursion, uuid.UUID(int=reading_id), None)
    project, _ = b.project_for_progress(db, p, r.project_id, C.reading_record)
    text = qc.reason(body.get("text"), 5, "text")
    r.annotation = {"text": text, "by": str(p.user.id), "at": now().isoformat()}
    _ = project
    return reading_read(r)


def reading_read(r: QReading) -> dict[str, Any]:
    return {
        "id": r.id,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "channel": r.channel,
        "measured_at": r.measured_at,
        "temperature_c": r.temperature_c,
        "humidity_pct": r.humidity_pct,
        "source": r.source,
        "batch_id": r.batch_id,
        "mte_id": r.mte_id,
        "annotation": r.annotation,
        "probe_fault": r.probe_fault,
    }


# ---- zone report: profile chart, coverage, TOR, MKT ---------------------------------------------


def zone_report(
    db: Session, p: Principal, zone_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    """C48 profile chart data plus coverage %, TOR %, gaps and MKT for a period."""
    z, _project = zone_row(db, p, zone_id)
    if end <= start or end - start > timedelta(days=62):
        raise qc.field_err(
            "end", "Choose a period of up to 62 days.", "اختر فترة لا تتجاوز 62 يوماً."
        )
    gr = zone_grid(db, z, start, end)
    period, mon, out = eng.coverage(gr)
    pts = points_of(db, z.zone_id, active=False)
    series = []
    for pt in pts:
        rows = db.execute(
            select(
                QReading.measured_at,
                QReading.temperature_c,
                QReading.humidity_pct,
                QReading.probe_fault,
            )
            .where(
                QReading.target_type == QReadingTarget.point,
                QReading.target_id == pt.id,
                QReading.voided.is_(False),
                QReading.measured_at >= start,
                QReading.measured_at < end,
            )
            .order_by(QReading.measured_at)
        ).all()
        step = max(1, len(rows) // 1500)  # keep the chart light
        series.append(
            {
                "point_id": pt.id,
                "code": pt.code,
                "values": [{"t": r[0], "c": r[1], "rh": r[2], "fault": r[3]} for r in rows[::step]],
                "mkt": point_mkt(db, z, pt, start, end),
            }
        )
    excs = db.scalars(
        select(QExcursion)
        .where(
            QExcursion.zone_id == z.zone_id,
            QExcursion.started_at < end,
            (QExcursion.ended_at.is_(None)) | (QExcursion.ended_at > start),
            QExcursion.status != QExcursionStatus.voided,
        )
        .order_by(QExcursion.started_at)
    )
    return {
        "zone": zone_read(db, p, z),
        "start": start,
        "end": end,
        "period_minutes": period,
        "monitored_minutes": mon,
        "out_minutes": out,
        "coverage_pct": b.q1(Decimal(mon) * 100 / period) if period else None,
        "tor_pct": b.q2(Decimal(out) * 100 / mon) if mon else None,
        "gaps": gap_rows(db, z, start, end),
        "series": series,
        "excursions": [
            {
                "id": x.id,
                "exc_no": x.exc_no,
                "transient": x.transient,
                "started_at": x.started_at,
                "ended_at": x.ended_at,
                "severity": x.severity,
                "status": x.status,
            }
            for x in excs
        ],
    }


def point_mkt(
    db: Session, z: QStorageZone, pt: QMonitoringPoint, start: datetime, end: datetime
) -> dict[str, Any] | None:
    if z.storage_class not in MKT_CLASSES:
        return None
    rows = db.execute(
        select(QReading.measured_at, QReading.temperature_c).where(
            QReading.target_type == QReadingTarget.point,
            QReading.target_id == pt.id,
            QReading.voided.is_(False),
            QReading.probe_fault.is_(False),
            QReading.measured_at >= start,
            QReading.measured_at < end,
        )
    ).all()
    value = eng.mkt(eng.hourly_means((b.local(r[0]), r[1]) for r in rows))
    if value is None:
        return None
    above = z.temp_max is not None and value > z.temp_max
    return {
        "mkt_c": value,
        "warning": "MKT_ABOVE_RANGE" if above else None,
    }


def month_tor(db: Session, z: QStorageZone, year: int, month: int) -> tuple[int, int, int]:
    """(period, monitored, out) minutes of a zone in a Riyadh calendar month (K-162 inputs);
    dismissed excursions' readings carry `probe_fault` and are never out (Q-EXC-11). Summed from
    the day summaries (D-351)."""
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    days = zone_days(db, z, first, nxt - timedelta(days=1))
    return (
        sum(v[0] for v in days.values()),
        sum(v[1] for v in days.values()),
        sum(v[2] for v in days.values()),
    )


# ---- day summaries (D-351) ----------------------------------------------------------------------

Coverage = tuple[int, int, int]


def _compute_days(db: Session, z: QStorageZone, d_from: date, d_to: date) -> dict[date, Coverage]:
    """(period, monitored, out) for each local day in [d_from, d_to] from one grid; the grid runs
    a little past the last day so its last reading's coverage is the same as in a longer grid."""
    a, e = b.day_start(d_from), b.day_start(d_to + timedelta(days=1))
    pts = points_of(db, z.zone_id)
    factor = b.dsetting(db, z.project_id, "reading_gap_factor")
    ahead = timedelta(minutes=int(max([x.interval_minutes for x in pts] or [15]) * factor) + 1)
    gr = zone_grid(db, z, a, e + ahead)
    out: dict[date, Coverage] = {}
    d = d_from
    while d <= d_to:
        i0 = gr.index(b.day_start(d))
        i1 = gr.index(b.day_start(d + timedelta(days=1)))
        out[d] = eng.coverage(gr, i0, i1)
        d += timedelta(days=1)
    return out


def invalidate_days(db: Session, zone_id: uuid.UUID) -> None:
    """A change of the zone's limits or of its points' intervals / active flags changes every
    day's coverage and TOR: the summaries are dropped and recomputed on first use (D-351)."""
    db.execute(delete(QZoneDay).where(QZoneDay.zone_id == zone_id))


def refresh_days(db: Session, z: QStorageZone, d_from: date, d_to: date) -> None:
    """Recompute the stored summaries of the days the new data touched; days not over yet are
    never stored (they are computed when asked)."""
    today = b.local_day(now())
    d_to = min(d_to, today - timedelta(days=1))
    db.execute(
        delete(QZoneDay).where(
            QZoneDay.zone_id == z.zone_id, QZoneDay.day >= d_from, QZoneDay.day <= d_to
        )
    )
    if d_to < d_from:
        return
    t = now()
    for d, (period, mon, out) in _compute_days(db, z, d_from, d_to).items():
        db.add(
            QZoneDay(
                zone_id=z.zone_id,
                day=d,
                project_id=z.project_id,
                period_minutes=period,
                monitored_minutes=mon,
                out_minutes=out,
                computed_at=t,
            )
        )
    db.flush()


def zone_days(db: Session, z: QStorageZone, d_from: date, d_to: date) -> dict[date, Coverage]:
    """Day summaries of [d_from, d_to]: stored ones as they are, missing past days computed and
    stored, today and later days computed only."""
    have = {
        r.day: (r.period_minutes, r.monitored_minutes, r.out_minutes)
        for r in db.scalars(
            select(QZoneDay).where(
                QZoneDay.zone_id == z.zone_id, QZoneDay.day >= d_from, QZoneDay.day <= d_to
            )
        )
    }
    missing = []
    d = d_from
    while d <= d_to:
        if d not in have:
            missing.append(d)
        d += timedelta(days=1)
    if missing:
        today = b.local_day(now())
        got = _compute_days(db, z, missing[0], missing[-1])
        t = now()
        for d in missing:
            have[d] = got[d]
            if d < today:
                period, mon, out = got[d]
                db.add(
                    QZoneDay(
                        zone_id=z.zone_id,
                        day=d,
                        project_id=z.project_id,
                        period_minutes=period,
                        monitored_minutes=mon,
                        out_minutes=out,
                        computed_at=t,
                    )
                )
        db.flush()
    return have


# ---- monitoring gaps (Q-STO-04) ----------------------------------------------------------------


def sync_gaps(
    db: Session,
    project: Project,
    z: QStorageZone,
    gr: eng.Grid,
    *,
    notify: bool = True,
) -> list[QMonitoringGap]:
    """Keep the "monitoring gap" entries of the grid's window in step with the readings and alert
    the 266 holders of the zone's site once per new gap (push and in-app, no e-mail). Only gaps
    with monitored minutes on both sides inside the window count: the minutes after the last
    reading are not a gap yet, and the start of a window is not the start of the data."""
    gmin = int(b.setting(db, project.id, "monitoring_gap_alert_minutes"))
    t0, t1 = gr.t0, gr.at(gr.n)
    found = {gr.at(a): (gr.at(e), e - a) for a, e in eng.gaps(gr, gmin) if a > 0 and e < gr.n}
    rows = {
        g.started_at: g
        for g in db.scalars(
            select(QMonitoringGap).where(
                QMonitoringGap.zone_id == z.zone_id,
                QMonitoringGap.started_at >= t0,
                QMonitoringGap.started_at < t1,
            )
        )
    }
    for at, g in rows.items():
        # only a stored gap the window sees whole (with monitored minutes around it, as `found`
        # needs) can have vanished; one that touches or passes the window's edges is not judged
        # by a smaller window
        if at not in found and at > t0 and g.ended_at < t1:
            db.delete(g)
    new: list[QMonitoringGap] = []
    for at, (end, minutes) in found.items():
        old = rows.get(at)
        if old is not None:
            old.ended_at, old.minutes = end, minutes
            continue
        g = QMonitoringGap(
            project_id=project.id,
            site_id=z.site_id,
            zone_id=z.zone_id,
            started_at=at,
            ended_at=end,
            minutes=minutes,
            created_at=now(),
        )
        db.add(g)
        new.append(g)
    db.flush()
    if notify and new:
        zone = db.get(Zone, z.zone_id)
        code = zone.code if zone else ""
        users = b.holders(db, project, C.storage_manage, z.site_id)
        for g in new:
            sent = b.send(
                db,
                project,
                users,
                f"gap:{z.zone_id}:{g.started_at.isoformat()}",
                f"Monitoring gap in {code}: {g.minutes} min without readings",
                f"انقطاع مراقبة في {code}: {g.minutes} دقيقة بلا قراءات",
                body_en=f"No reading covered {code} from {b.local(g.started_at):%Y-%m-%d %H:%M} "
                f"to {b.local(g.ended_at):%H:%M}. Check the loggers.",
                body_ar=f"لم تغطِّ أي قراءة {code} من {b.local(g.started_at):%Y-%m-%d %H:%M} "
                f"إلى {b.local(g.ended_at):%H:%M}. افحص المسجلات.",
                path=f"/quality/storage/{z.zone_id}",
                email=False,
            )
            if sent:
                g.notified_at = now()
    return new


def gap_rows(db: Session, z: QStorageZone, start: datetime, end: datetime) -> list[dict[str, Any]]:
    return [
        {"from": g.started_at, "to": g.ended_at, "minutes": g.minutes}
        for g in db.scalars(
            select(QMonitoringGap)
            .where(
                QMonitoringGap.zone_id == z.zone_id,
                QMonitoringGap.started_at < end,
                QMonitoringGap.ended_at > start,
            )
            .order_by(QMonitoringGap.started_at)
        )
    ]


def zone_for_code(db: Session, project_id: uuid.UUID, code: str | None) -> QStorageZone | None:
    if not code:
        return None
    zid = db.scalar(
        select(Zone.id)
        .join(Site, Site.id == Zone.site_id)
        .where(Site.project_id == project_id, Zone.code == code)
    )
    return db.get(QStorageZone, zid) if zid else None


_ = (date, forbidden_error)
