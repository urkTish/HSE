"""Temperature mapping studies (spec 8-quality §D.5, Q-MAP-01…06): design checks (loggers
calibrated on the start and end dates, duration, interval, logger count), logger file imports with
the study as target, evaluation (per logger min / max / mean and % in range outside the declared
test windows; hot and cold spots), approval through the matrix (`mapping_study.approve`) that
makes the zone mapped until `valid_until`, and the validity alerts."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.quality.common import QCalStatus, QMteStatus, QRecordType
from app.core.quality.q3 import (
    QLoadState,
    QMappingPurpose,
    QMappingState,
    QMappingStatus,
    QReadingTarget,
    QSeason,
    QStorageClass,
)
from app.models import Project, Zone
from app.models.quality import QMteItem
from app.models.quality.q3 import QMappingStudy, QReading, QStorageZone
from app.schemas.hse_common import ApiWarning
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b

C = Capability
RT = QRecordType.mapping_study
ST = QMappingStatus
OK_CAL = frozenset({QCalStatus.calibrated, QCalStatus.due_soon})


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    import calendar  # noqa: PLC0415

    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def ctx(m: QMappingStudy) -> rpm.Ctx:
    z = None
    return rpm.Ctx(site_id=z, requesters=qc.ids(m.created_by_user_id))


def get_study(db: Session, p: Principal, sid: uuid.UUID) -> tuple[QMappingStudy, Project]:
    m = db.get(QMappingStudy, sid)
    if m is None or not p.can_see_project(m.project_id):
        raise b.not_found(db, p, RT, sid, m.project_id if m else None)
    project = qc.get_project(db, p, m.project_id)
    z = db.get(QStorageZone, m.zone_id)
    if not b.can_view(
        db,
        p,
        project,
        RT,
        m.id,
        z.site_id if z else None,
        lambda: [("approve", ctx(m), None)] if m.status == ST.evaluated else [],
    ):
        raise b.not_found(db, p, RT, sid, project.id)
    return m, project


def _span(m: QMappingStudy) -> tuple[datetime | None, datetime | None]:
    return (m.actual_start or m.planned_start, m.actual_end or m.planned_end)


def design_problems(
    db: Session, project: Project, m: QMappingStudy
) -> tuple[list[str], list[ApiWarning]]:
    """Q-MAP-01 (calibration on both dates) and Q-MAP-02 (duration, interval, loggers)."""
    start, end = _span(m)
    warnings: list[ApiWarning] = []
    cal_bad: list[str] = []
    for lg in m.loggers or []:
        it = db.get(QMteItem, uuid.UUID(str(lg["mte_id"])))
        if it is None or it.project_id != project.id:
            raise qc.field_err(
                "loggers",
                "A logger is not registered on this project.",
                "مسجل غير مسجل في المشروع.",
            )
        # Q-MAP-01 is about the study dates: a logger overdue today may still have been in
        # calibration then (with Q2 installed `overdue` is a live status), so only the due date
        # decides, plus inactive / out-of-service instruments.
        bad = it.status != QMteStatus.active or it.cal_status == QCalStatus.out_of_service
        if it.cal_due_on is None and it.cal_status == QCalStatus.overdue:
            bad = True  # never calibrated
        for d in (start, end):
            if d is not None and it.cal_due_on is not None and it.cal_due_on < b.local_day(d):
                bad = True
        if bad:
            cal_bad.append(it.mte_no)
        elif it.cal_status not in OK_CAL and it.cal_due_on is None:
            warnings.append(
                qc.warning(
                    "MTE_NOT_CALIBRATED",
                    f"{it.mte_no}: calibration status unknown; confirm it before the study.",
                    f"{it.mte_no}: حالة المعايرة غير معروفة.",
                    "loggers",
                )
            )
    if cal_bad:
        raise qc.err(
            422,
            ErrorCode.MAPPING_LOGGER_NOT_CALIBRATED,
            f"Loggers not calibrated on the study start and end dates: {', '.join(cal_bad)} "
            "(Q-MAP-01).",
            f"مسجلات غير معايرة في تاريخي بداية الدراسة ونهايتها: {', '.join(cal_bad)}.",
            loggers=cal_bad,
        )
    short: list[str] = []
    min_h = int(b.setting(db, project.id, "mapping_min_hours"))
    max_iv = int(b.setting(db, project.id, "mapping_max_interval_minutes"))
    min_lg = int(b.setting(db, project.id, "mapping_min_loggers"))
    if start and end and (end - start) < timedelta(hours=min_h):
        short.append(f"duration {(end - start) / timedelta(hours=1):.0f} h < {min_h} h")
    if m.interval_minutes > max_iv:
        short.append(f"interval {m.interval_minutes} min > {max_iv} min")
    if len(m.loggers or []) < min_lg:
        short.append(f"{len(m.loggers or [])} loggers < {min_lg}")
    return short, warnings


def _design(db: Session, project: Project, m: QMappingStudy) -> list[ApiWarning]:
    short, warnings = design_problems(db, project, m)
    if short:
        raise qc.err(
            422,
            ErrorCode.MAPPING_DESIGN_INSUFFICIENT,
            "The study design is insufficient: " + "; ".join(short) + " (Q-MAP-02).",
            "تصميم الدراسة غير كافٍ: " + "؛ ".join(short),
            problems=short,
        )
    if m.lead_user_id is not None:
        v = reg.competence_check(
            db, m.lead_user_id, "MAPPING-LEAD", b.local_day(_span(m)[0] or now())
        )
        if v.met is False:
            if b.setting(db, project.id, "competence_policy") == "block":
                raise qc.err(422, ErrorCode.COMPETENCE_NOT_MET, v.detail_en, v.detail_ar)
            warnings.append(
                qc.warning(ErrorCode.COMPETENCE_NOT_MET, v.detail_en, v.detail_ar, "lead_user_id")
            )
    return warnings


FIELDS = (
    "purpose",
    "season",
    "load_state",
    "planned_start",
    "planned_end",
    "interval_minutes",
    "lead_user_id",
)


def _apply(m: QMappingStudy, body: dict[str, Any]) -> None:
    for k in FIELDS:
        if k in body and body[k] is not None:
            v = body[k]
            if k == "purpose":
                v = QMappingPurpose(v)
            elif k == "season":
                v = QSeason(v)
            elif k == "load_state":
                v = QLoadState(v)
            setattr(m, k, v)
    if "loggers" in body and body["loggers"] is not None:
        codes = [str(x["position_code"]).strip().upper() for x in body["loggers"]]
        if len(set(codes)) != len(codes):
            raise qc.field_err(
                "loggers", "Each logger needs its own position code.", "لكل مسجل رمز موقع خاص."
            )
        m.loggers = [
            {
                "mte_id": str(x["mte_id"]),
                "position_code": str(x["position_code"]).strip().upper(),
                "description": x.get("description"),
            }
            for x in body["loggers"]
        ]
    if "test_windows" in body and body["test_windows"] is not None:
        m.test_windows = [
            {"kind": w["kind"], "from": _iso(w["from"]), "to": _iso(w["to"])}
            for w in body["test_windows"]
        ]


def _iso(v: Any) -> str:
    return v.isoformat() if isinstance(v, datetime) else str(v)


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.storage_manage)
    z = db.get(QStorageZone, body["zone_id"])
    if z is None or z.project_id != project.id:
        raise qc.field_err(
            "zone_id",
            "The zone has no storage settings on this project.",
            "المنطقة بلا إعدادات تخزين.",
        )
    b.require_site(g, z.site_id)
    m = QMappingStudy(
        id=uuid.uuid4(),
        project_id=project.id,
        zone_id=z.zone_id,
        purpose=QMappingPurpose(body["purpose"]),
        loggers=[],
        test_windows=[],
        recommended_positions=[],
        status=ST.draft,
        created_by_user_id=p.user.id,
    )
    _apply(m, body)
    warnings = _design(db, project, m)
    db.add(m)
    db.flush()
    b.audit_create(db, p, project, RT, m.id, zone=str(z.zone_id))
    return {**read(db, p, m), "warnings": b.warn_dump(warnings)}


def update(db: Session, p: Principal, sid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    m, project = get_study(db, p, sid)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    if m.status not in (ST.draft, ST.data_loaded, ST.evaluated):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "An approved or rejected study cannot change.",
            "لا يمكن تعديل دراسة معتمدة أو مرفوضة.",
        )
    _apply(m, body)
    warnings = _design(db, project, m)
    if m.status == ST.evaluated:
        m.status = ST.data_loaded
    m.updated_by_user_id = p.user.id
    _ = g
    return {**read(db, p, m), "warnings": b.warn_dump(warnings)}


def on_data(db: Session, m: QMappingStudy) -> None:
    """Readings imported with the study as target (Q-MAP-03)."""
    span = (
        db.execute(
            select(QReading.measured_at)
            .where(
                QReading.target_type == QReadingTarget.mapping_study,
                QReading.target_id == m.id,
                QReading.voided.is_(False),
            )
            .order_by(QReading.measured_at)
        )
        .scalars()
        .all()
    )
    if not span:
        if m.status == ST.data_loaded:
            m.status = ST.draft
        return
    m.actual_start, m.actual_end = span[0], span[-1]
    if m.status in (ST.draft, ST.evaluated):
        m.status = ST.data_loaded


def _in_window(m: QMappingStudy, at: datetime) -> bool:
    for w in m.test_windows or []:
        if datetime.fromisoformat(w["from"]) <= at < datetime.fromisoformat(w["to"]):
            return True
    return False


def _channel_map(db: Session, m: QMappingStudy) -> dict[str, str]:
    out: dict[str, str] = {}
    for lg in m.loggers or []:
        out[lg["position_code"]] = lg["position_code"]
        it = db.get(QMteItem, uuid.UUID(lg["mte_id"]))
        if it is not None:
            if it.serial_no:
                out[it.serial_no] = lg["position_code"]
            out[it.mte_no] = lg["position_code"]
    return out


def evaluate(db: Session, p: Principal, sid: uuid.UUID) -> dict[str, Any]:
    """Data Loaded → Evaluated: results per logger; pass ⇔ every logger stays within the zone
    range outside the test windows."""
    m, project = get_study(db, p, sid)
    _, g = b.project_for_progress(db, p, project.id, C.storage_manage)
    if m.status not in (ST.data_loaded, ST.evaluated):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Import the logger files first.",
            "استورد ملفات المسجلات أولاً.",
        )
    _design(db, project, m)
    z = db.get(QStorageZone, m.zone_id)
    assert z is not None  # noqa: S101
    cmap = _channel_map(db, m)
    per: dict[str, list[tuple[datetime, Decimal]]] = {}
    for at, ch, v in db.execute(
        select(QReading.measured_at, QReading.channel, QReading.temperature_c).where(
            QReading.target_type == QReadingTarget.mapping_study,
            QReading.target_id == m.id,
            QReading.voided.is_(False),
        )
    ):
        if v is None:
            continue
        per.setdefault(cmap.get(ch, ch), []).append((at, v))
    results = []
    passed = True
    zone_min: Decimal | None = None
    zone_max: Decimal | None = None
    for lg in m.loggers or []:
        rows = sorted(per.get(lg["position_code"], []))
        counted = [(at, v) for at, v in rows if not _in_window(m, at)]
        if not rows:
            results.append(
                {"position_code": lg["position_code"], "mte_id": lg["mte_id"], "readings": 0}
            )
            passed = False
            continue
        vals = [v for _, v in counted] or [v for _, v in rows]
        inr = [
            v
            for v in vals
            if (z.temp_min is None or v >= z.temp_min) and (z.temp_max is None or v <= z.temp_max)
        ]
        ok = len(inr) == len(vals)
        passed = passed and ok
        lo, hi = min(vals), max(vals)
        zone_min = lo if zone_min is None else min(zone_min, lo)
        zone_max = hi if zone_max is None else max(zone_max, hi)
        results.append(
            {
                "position_code": lg["position_code"],
                "mte_id": lg["mte_id"],
                "description": lg.get("description"),
                "readings": len(rows),
                "readings_in_test_windows": len(rows) - len(counted),
                "min_c": lo,
                "max_c": hi,
                "mean_c": (sum(vals, Decimal(0)) / len(vals)).quantize(
                    Decimal("0.01"), ROUND_HALF_UP
                ),
                "pct_in_range": (Decimal(len(inr)) * 100 / len(vals)).quantize(
                    Decimal("0.1"), ROUND_HALF_UP
                ),
                "in_range": ok,
            }
        )
    with_data = [r for r in results if r.get("readings")]
    hot = max(with_data, key=lambda r: r["max_c"]) if with_data else None
    cold = min(with_data, key=lambda r: r["min_c"]) if with_data else None
    m.results = {
        "loggers": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in results
        ],
        "zone_min_c": str(zone_min) if zone_min is not None else None,
        "zone_max_c": str(zone_max) if zone_max is not None else None,
        "hot_spot": hot["position_code"] if hot else None,
        "cold_spot": cold["position_code"] if cold else None,
        "evaluated_at": now().isoformat(),
    }
    m.passed = passed and bool(with_data)
    rec: list[dict[str, Any]] = []
    if hot:
        rec.append(
            {
                "position": "hot_spot",
                "position_code": hot["position_code"],
                "description": hot.get("description"),
            }
        )
    if cold:
        rec.append(
            {
                "position": "cold_spot",
                "position_code": cold["position_code"],
                "description": cold.get("description"),
            }
        )
    m.recommended_positions = rec
    m.status = ST.evaluated
    m.map_no = m.map_no or b.number(db, project, RT)
    _ = g
    return read(db, p, m)


def approve(db: Session, p: Principal, sid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Evaluated → Approved (266 + RPM `mapping_study.approve`) or Rejected (`returned`)."""
    m, project = get_study(db, p, sid)
    project, _ = b.project_for_progress(db, p, project.id, C.storage_manage, allow_n=True)
    if m.status != ST.evaluated:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Evaluate the study first.", "قيّم الدراسة أولاً."
        )
    decision = body.get("decision") or "approved"
    if decision == "approved" and not m.passed:
        raise qc.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "A failed study cannot be approved; reject it and repeat.",
            "لا يمكن اعتماد دراسة غير ناجحة.",
        )
    s = b.sign(
        db, p, project, RT, m.id, "approve", ctx(m), decision=decision, comment=body.get("comment")
    )
    z = db.get(QStorageZone, m.zone_id)
    assert z is not None  # noqa: S101
    if decision == "returned":
        m.status = ST.rejected
        m.reject_reason = (body.get("comment") or "").strip() or None
        b.audit_status(db, p, project, RT, m.id, ST.evaluated, ST.rejected, signoff=str(s.id))
        return read(db, p, m)
    day = body.get("approved_on") or qc.project_day(project)
    months = int(b.setting(db, project.id, "mapping_validity_months"))
    m.status = ST.approved
    m.approved_at = now()
    m.approved_on = day
    m.valid_until = add_months(day, months) - timedelta(days=1)
    m.map_no = m.map_no or b.number(db, project, RT)
    apply_approval(z, m)
    b.audit_status(
        db, p, project, RT, m.id, ST.evaluated, ST.approved, valid_until=str(m.valid_until)
    )
    return read(db, p, m)


def apply_approval(z: QStorageZone, m: QMappingStudy) -> None:
    """Q-MAP-04 / -06: the zone is mapped until valid_until; a required re-mapping is cleared only
    by an `after_change` study."""
    if (
        z.mapping_state == QMappingState.remap_required
        and m.purpose != QMappingPurpose.after_change
    ):
        return
    z.mapping_state = QMappingState.mapped
    z.mapped_until = m.valid_until
    z.remap_reason = None
    z.updated_at = now()


def validity_alerts(db: Session, at: datetime) -> int:
    """Q-MAP-05: alerts at 60 / 30 / 0 days before the zone's mapped_until; an expired mapping
    makes the zone not mapped."""
    n = 0
    for z in db.scalars(
        select(QStorageZone).where(
            QStorageZone.active.is_(True), QStorageZone.mapped_until.is_not(None)
        )
    ):
        project = db.get(Project, z.project_id)
        if project is None or z.mapped_until is None:
            continue
        today = qc.project_day(project, at)
        left = (z.mapped_until - today).days
        if left < 0 and z.mapping_state == QMappingState.mapped:
            z.mapping_state = QMappingState.not_mapped
        zone = db.get(Zone, z.zone_id)
        for th in (0, 30, 60):
            if not (th - 30 < left <= th):
                continue
            users = b.holders(db, project, C.storage_manage, z.site_id) | set(
                b.resolvers(db, project, RT, "approve", rpm.Ctx(site_id=z.site_id))
            )
            n += b.send(
                db,
                project,
                users,
                f"map:{z.zone_id}:{z.mapped_until}:{th}",
                f"{zone.code if zone else ''}: temperature mapping valid until {z.mapped_until} "
                f"({th} days)",
                f"{zone.code if zone else ''}: دراسة التوزيع الحراري صالحة حتى {z.mapped_until}",
                body_en="Plan the periodic study.",
                body_ar="خطط للدراسة الدورية.",
                path=f"/quality/storage/{z.zone_id}",
            )
            break
    return n


def pharma_unmapped(db: Session, project: Project) -> list[QStorageZone]:
    today = qc.project_day(project)
    return [
        z
        for z in db.scalars(
            select(QStorageZone).where(
                QStorageZone.project_id == project.id,
                QStorageZone.storage_class == QStorageClass.pharma_2_8,
                QStorageZone.active.is_(True),
            )
        )
        if z.mapping_state != QMappingState.mapped
        or (z.mapped_until is not None and z.mapped_until < today)
    ]


def read(db: Session, p: Principal, m: QMappingStudy) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    z = db.get(QStorageZone, m.zone_id)
    zone = db.get(Zone, m.zone_id)
    project = db.get(Project, m.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, m.project_id)
    return {
        "id": m.id,
        "project_id": m.project_id,
        "map_no": m.map_no,
        "zone": {
            "zone_id": m.zone_id,
            "code": zone.code if zone else "",
            "name_en": zone.name_en if zone else "",
            "name_ar": zone.name_ar if zone else "",
            "storage_class": z.storage_class if z else None,
            "temp_min": z.temp_min if z else None,
            "temp_max": z.temp_max if z else None,
        },
        "purpose": m.purpose,
        "season": m.season,
        "load_state": m.load_state,
        "planned_start": m.planned_start,
        "planned_end": m.planned_end,
        "actual_start": m.actual_start,
        "actual_end": m.actual_end,
        "interval_minutes": m.interval_minutes,
        "loggers": [
            {**lg, "mte": b.mte_ref(db, uuid.UUID(lg["mte_id"]))} for lg in m.loggers or []
        ],
        "test_windows": m.test_windows,
        "lead": b.user_ref(db, m.lead_user_id, hide),
        "results": m.results,
        "passed": m.passed,
        "recommended_positions": m.recommended_positions,
        "report_attachment_id": m.report_attachment_id,
        "status": m.status,
        "approved_on": m.approved_on,
        "valid_until": m.valid_until,
        "reject_reason": m.reject_reason,
        "can_approve": m.status == ST.evaluated
        and b.resolves(db, p, project, RT, m.id, "approve", ctx(m)),
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, m.id)
        ],
    }


def list_studies(
    db: Session, p: Principal, project_id: uuid.UUID, zone_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    q = select(QMappingStudy).where(QMappingStudy.project_id == project.id)
    if zone_id:
        q = q.where(QMappingStudy.zone_id == zone_id)
    out = []
    for m in db.scalars(q.order_by(QMappingStudy.created_at.desc())):
        z = db.get(QStorageZone, m.zone_id)
        if g.scope.value == "responsible":
            if not b.can_view(
                db,
                p,
                project,
                RT,
                m.id,
                z.site_id if z else None,
                lambda m=m: [("approve", ctx(m), None)] if m.status == ST.evaluated else [],
            ):
                continue
        elif z is not None and not g.covers_site(z.site_id):
            continue
        zone = db.get(Zone, m.zone_id)
        out.append(
            {
                "id": m.id,
                "map_no": m.map_no,
                "zone_code": zone.code if zone else "",
                "purpose": m.purpose,
                "season": m.season,
                "status": m.status,
                "passed": m.passed,
                "loggers": len(m.loggers or []),
                "planned_start": m.planned_start,
                "planned_end": m.planned_end,
                "valid_until": m.valid_until,
            }
        )
    return out


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    for m in db.scalars(
        select(QMappingStudy).where(
            QMappingStudy.project_id == project.id,
            QMappingStudy.status == ST.evaluated,
            QMappingStudy.passed.is_(True),
        )
    ):
        z = db.get(QStorageZone, m.zone_id)
        zone = db.get(Zone, m.zone_id)
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT,
                    m.id,
                    project.id,
                    m.map_no or "MAP",
                    f"Mapping study {zone.code if zone else ''}",
                    "approve",
                    m.updated_at,
                    f"/quality/mapping/{m.id}",
                    "Q3",
                ),
                None,
                z.site_id if z else None,
                None,
                qc.ids(m.created_by_user_id),
            )
        )
    return out
