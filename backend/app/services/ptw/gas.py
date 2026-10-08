# ruff: noqa: E501
"""Gas detectors, bump tests and gas tests (spec 3-ptw §3.9, §3.10, §4.6, GT-1…GT-9, §6.2,
§6.3, §6.10, §7 calibration alerts)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.ptw_enums import (
    PERMIT_LIVE,
    PERMIT_TERMINAL,
    AppointmentFunction,
    BumpTestResult,
    DetectorStatus,
    GasFailCode,
    GasLimitProfile,
    GasReadingPoint,
    GasSensor,
    GasStatus,
    GasTestResult,
    GasTestType,
    PermitStatus,
    PermitType,
    QuarantineReason,
    SignaturePurpose,
    StatusReason,
)
from app.models import (
    BumpTest,
    GasDetector,
    GasTest,
    Permit,
    PermitShift,
    ProjectEngagement,
    PtwAppointment,
    Worker,
)
from app.schemas.gas import (
    AppliedLimits,
    BumpTestCreate,
    BumpTestList,
    BumpTestRead,
    CalibrationInput,
    DetectorCreate,
    DetectorPage,
    DetectorRead,
    DetectorRetireInput,
    DetectorUpdate,
    GasEvaluation,
    GasReadingInput,
    GasReadingRead,
    GasTestCreate,
    GasTestList,
    GasTestPage,
    GasTestPreview,
    GasTestRead,
    GasTestSupersede,
    OtherReading,
)
from app.schemas.ptw_common import DetectorRef
from app.schemas.ptw_config import GasLimitSet, OtherGasLimit
from app.services import attachments, audit, notify, projects
from app.services.access import common as acommon
from app.services.common import duplicate, paginate
from app.services.hse_common import Refs, contractor_reps
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common, rules
from app.services.ptw.appointments import appointment_ref

C = Capability
BACKDATE_MINUTES = 60
FUTURE_TOLERANCE = timedelta(minutes=2)
CAL_ALERT_DAYS = (30, 14, 7, 0)
CSE_POINTS = {GasReadingPoint.top.value, GasReadingPoint.middle.value, GasReadingPoint.bottom.value}
GAS_TEST_PERMIT_STATUSES = {
    PermitStatus.approved,
    PermitStatus.issued,
    PermitStatus.active,
    PermitStatus.suspended,
}


def short_code(db: Session, project_id: uuid.UUID) -> str:
    """`ANIA-EXP` → `ANIA`, `RBT-52` → `RBT` (detector and lock numbers)."""
    return common.project_code(db, project_id).split("-")[0]


# ---- detectors -----------------------------------------------------------------------------------


def due_on(db: Session, project_id: uuid.UUID, calibrated: date, cert_due: date | None) -> date:
    s = common.settings(db, project_id)
    d = calibrated + timedelta(days=s.detector_calibration_interval_days)
    return min(d, cert_due) if cert_due else d


def _bump_read(db: Session, b: BumpTest, refs: Refs, names: bool) -> BumpTestRead:
    w = db.get(Worker, b.tested_by_worker_id) if b.tested_by_worker_id else None
    return BumpTestRead(
        id=b.id,
        detector_id=b.detector_id,
        tested_at=b.tested_at,
        result=b.result,
        sensors_responded=[GasSensor(s) for s in b.sensors_responded],
        tested_by_user=refs.user(b.tested_by_user_id),
        tested_by_worker=acommon.worker_ref(w, names) if w else None,
        gas_cylinder_lot=b.gas_cylinder_lot,
        gas_cylinder_expiry=b.gas_cylinder_expiry,
        valid_for_date=acommon.local_day(b.tested_at),
    )


def _last_bump(db: Session, detector_id: uuid.UUID) -> BumpTest | None:
    return db.scalars(
        select(BumpTest)
        .where(BumpTest.detector_id == detector_id)
        .order_by(BumpTest.tested_at.desc())
        .limit(1)
    ).first()


def _detector_permits(db: Session, d: GasDetector) -> list[Permit]:
    since = now() - timedelta(days=1)
    ids = select(GasTest.permit_id).where(GasTest.detector_id == d.id, GasTest.tested_at >= since)
    rows = list(
        db.scalars(
            select(Permit)
            .where(Permit.id.in_(ids), Permit.status.in_(list(PERMIT_LIVE)))
            .order_by(Permit.permit_no)
        )
    )
    monitor = [
        x
        for x in db.scalars(
            select(Permit).where(
                Permit.project_id == d.project_id, Permit.status.in_(list(PERMIT_LIVE))
            )
        )
        if str((x.sections or {}).get("confined_space", {}).get("continuous_monitor_detector_id"))
        == str(d.id)
    ]
    out = {x.id: x for x in [*rows, *monitor]}
    return sorted(out.values(), key=lambda x: x.permit_no)


def detector_read(
    db: Session, p: Principal | None, d: GasDetector, refs: Refs | None = None
) -> DetectorRead:
    refs = refs or Refs(db)
    names = acommon.can_see_names(p, d.project_id)
    last = _last_bump(db, d.id)
    day = today()
    return DetectorRead(
        id=d.id,
        project_id=d.project_id,
        detector_no=d.detector_no,
        engagement=refs.eng_required(d.engagement_id),
        make_model=d.make_model,
        serial=d.serial,
        sensors=[GasSensor(s) for s in d.sensors],
        lel_reference_gas=d.lel_reference_gas,
        calibrated_on=d.calibrated_on,
        calibration_cert_ref=d.calibration_cert_ref,
        certificate_due_on=d.certificate_due_on,
        calibration_due_on=d.calibration_due_on,
        calibration_days_left=(d.calibration_due_on - day).days,
        status=d.status,
        quarantine_reason=d.quarantine_reason,
        quarantined_at=d.quarantined_at,
        last_bump_test=_bump_read(db, last, refs, names) if last else None,
        bump_tested_today=bool(
            last
            and last.result == BumpTestResult.pass_
            and acommon.local_day(last.tested_at) == day
        ),
        live_permits=[common.permit_ref(x) for x in _detector_permits(db, d)],
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def detector_ref(d: GasDetector) -> DetectorRef:
    return DetectorRef(
        id=d.id, detector_no=d.detector_no, status=d.status, calibration_due_on=d.calibration_due_on
    )


def _view(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    return common.view_grant(db, p, project_id)


def _get_detector(db: Session, p: Principal, detector_id: uuid.UUID) -> GasDetector:
    d = db.get(GasDetector, detector_id)
    if d is None:
        raise not_found("Gas detector")
    g = _view(db, p, d.project_id)
    if not acommon.grant_covers(g, None, d.engagement_id) and g.engagement_ids is not None:
        # contractor scope: own tree's detectors, plus any detector used on a visible permit
        raise forbidden_error("This detector is outside your scope.")
    return d


def list_detectors(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    statuses: list[DetectorStatus] | None,
    engagement_id: uuid.UUID | None,
    due_within: int | None,
    q: str | None,
) -> DetectorPage:
    g = _view(db, p, project_id)
    stmt = select(GasDetector).where(GasDetector.project_id == project_id)
    if g.engagement_ids is not None:
        stmt = stmt.where(GasDetector.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(GasDetector.status.in_(statuses))
    if engagement_id:
        stmt = stmt.where(GasDetector.engagement_id == engagement_id)
    if due_within is not None:
        stmt = stmt.where(GasDetector.calibration_due_on <= today() + timedelta(days=due_within))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                GasDetector.detector_no.ilike(like),
                GasDetector.serial.ilike(like),
                GasDetector.make_model.ilike(like),
            )
        )
    rows, total = paginate(db, stmt.order_by(GasDetector.detector_no), page, size)
    refs = Refs(db).load(engs=[r.engagement_id for r in rows])
    return DetectorPage(
        items=[detector_read(db, p, r, refs) for r in rows], total=total, page=page, page_size=size
    )


def _audit(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    et: EntityType,
    eid: uuid.UUID,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(project_id) if p else audit.SYSTEM,
        entity_type=et,
        entity_id=eid,
        project_id=project_id,
        before=before,
        after=after,
        details=details,
    )


def _check_sensors(sensors: list[GasSensor], lel_gas: Any) -> None:
    if GasSensor.lel in sensors and lel_gas is None:
        raise validation_error("lel_reference_gas", "Give the LEL reference gas.")


def create_detector(
    db: Session, p: Principal, project_id: uuid.UUID, body: DetectorCreate
) -> DetectorRead:
    projects.get_visible(db, p, project_id)
    acommon.require_cap(p, project_id, C.gas_detector_manage, None, body.engagement_id)
    e = db.get(ProjectEngagement, body.engagement_id)
    if e is None or e.project_id != project_id:
        raise validation_error("engagement_id", "Engagement is not on this project.")
    if body.calibrated_on > today():
        raise validation_error("calibrated_on", "The calibration date cannot be in the future.")
    _check_sensors(body.sensors, body.lel_reference_gas)
    if db.scalar(
        select(GasDetector.id).where(
            GasDetector.project_id == project_id, GasDetector.serial == body.serial
        )
    ):
        raise duplicate("serial", "A detector with this serial is already registered.")
    seq = (
        db.scalar(select(func.max(GasDetector.seq)).where(GasDetector.project_id == project_id))
        or 0
    ) + 1
    due = due_on(db, project_id, body.calibrated_on, body.certificate_due_on)
    overdue = due < today()
    d = GasDetector(
        id=uuid.uuid4(),
        project_id=project_id,
        seq=seq,
        detector_no=f"GD-{short_code(db, project_id)}-{seq:03d}",
        engagement_id=body.engagement_id,
        make_model=body.make_model,
        serial=body.serial,
        sensors=[s.value for s in body.sensors],
        lel_reference_gas=body.lel_reference_gas,
        calibrated_on=body.calibrated_on,
        calibration_cert_ref=body.calibration_cert_ref,
        certificate_due_on=body.certificate_due_on,
        calibration_due_on=due,
        status=DetectorStatus.quarantined if overdue else DetectorStatus.in_service,
        quarantine_reason=QuarantineReason.calibration_overdue if overdue else None,
        quarantined_at=now() if overdue else None,
        alerts_sent=[],
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    _audit(
        db,
        p,
        project_id,
        EntityType.gas_detector,
        d.id,
        AuditAction.create,
        None,
        {"detector_no": d.detector_no, "status": d.status.value},
    )
    return detector_read(db, p, d)


def read_detector(db: Session, p: Principal, detector_id: uuid.UUID) -> DetectorRead:
    return detector_read(db, p, _get_detector(db, p, detector_id))


def _manage(p: Principal, d: GasDetector) -> None:
    acommon.require_cap(p, d.project_id, C.gas_detector_manage, None, d.engagement_id)


def update_detector(
    db: Session, p: Principal, detector_id: uuid.UUID, body: DetectorUpdate
) -> DetectorRead:
    d = _get_detector(db, p, detector_id)
    _manage(p, d)
    if d.status == DetectorStatus.retired:
        raise validation_error("status", "A retired detector cannot be edited.")
    ch = body.changes()
    before = {"make_model": d.make_model, "sensors": list(d.sensors)}
    if "make_model" in ch and body.make_model:
        d.make_model = body.make_model
    if "sensors" in ch and body.sensors:
        d.sensors = [s.value for s in body.sensors]
    if "lel_reference_gas" in ch:
        d.lel_reference_gas = body.lel_reference_gas
    _check_sensors([GasSensor(s) for s in d.sensors], d.lel_reference_gas)
    d.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        d.project_id,
        EntityType.gas_detector,
        d.id,
        AuditAction.update,
        before,
        {"make_model": d.make_model, "sensors": list(d.sensors)},
    )
    return detector_read(db, p, d)


def record_calibration(
    db: Session, p: Principal, detector_id: uuid.UUID, body: CalibrationInput
) -> DetectorRead:
    d = _get_detector(db, p, detector_id)
    _manage(p, d)
    if d.status == DetectorStatus.retired:
        raise validation_error("status", "A retired detector cannot be calibrated.")
    if body.calibrated_on > today():
        raise validation_error("calibrated_on", "The calibration date cannot be in the future.")
    before = {
        "status": d.status.value,
        "calibrated_on": str(d.calibrated_on),
        "calibration_due_on": str(d.calibration_due_on),
    }
    d.calibrated_on = body.calibrated_on
    d.calibration_cert_ref = body.calibration_cert_ref
    d.certificate_due_on = body.certificate_due_on
    d.calibration_due_on = due_on(db, d.project_id, body.calibrated_on, body.certificate_due_on)
    d.alerts_sent = []
    if d.calibration_due_on >= today() and (
        d.status == DetectorStatus.quarantined
        and d.quarantine_reason == QuarantineReason.calibration_overdue
    ):
        d.status = DetectorStatus.in_service
        d.quarantine_reason = None
        d.quarantined_at = None
    d.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        d.project_id,
        EntityType.gas_detector,
        d.id,
        AuditAction.update,
        before,
        {
            "status": d.status.value,
            "calibrated_on": str(d.calibrated_on),
            "calibration_due_on": str(d.calibration_due_on),
        },
        {"calibration": True},
    )
    return detector_read(db, p, d)


def list_bumps(
    db: Session,
    p: Principal,
    detector_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BumpTestList:
    d = _get_detector(db, p, detector_id)
    refs = Refs(db)
    names = acommon.can_see_names(p, d.project_id)
    stmt = select(BumpTest).where(BumpTest.detector_id == d.id)
    if date_from:
        stmt = stmt.where(BumpTest.tested_at >= acommon.local_midnight_utc(date_from))
    if date_to:
        stmt = stmt.where(
            BumpTest.tested_at < acommon.local_midnight_utc(date_to + timedelta(days=1))
        )
    rows = db.scalars(stmt.order_by(BumpTest.tested_at.desc()))
    return BumpTestList(items=[_bump_read(db, b, refs, names) for b in rows])


def record_bump(
    db: Session, p: Principal, detector_id: uuid.UUID, body: BumpTestCreate
) -> BumpTestRead:
    d = _get_detector(db, p, detector_id)
    acommon.require_cap(p, d.project_id, C.gas_test_record, None, None)
    if d.status == DetectorStatus.retired:
        raise common.err(
            ErrorCode.DETECTOR_NOT_IN_SERVICE,
            f"{d.detector_no} is retired.",
            f"الجهاز {d.detector_no} مستبعد.",
        )
    if body.tested_at > now() + FUTURE_TOLERANCE:
        raise validation_error("tested_at", "The bump test time cannot be in the future.")
    if body.gas_cylinder_expiry <= acommon.local_day(body.tested_at):
        raise validation_error("gas_cylinder_expiry", "The test gas cylinder has expired.")
    responded = {s.value for s in body.sensors_responded}
    if body.result == BumpTestResult.pass_ and responded != set(d.sensors):
        raise validation_error(
            "sensors_responded", "A pass needs every sensor of the detector to respond."
        )
    if body.tested_by_worker_id and db.get(Worker, body.tested_by_worker_id) is None:
        raise validation_error("tested_by_worker_id", "Worker not found.")
    b = BumpTest(
        id=uuid.uuid4(),
        detector_id=d.id,
        tested_at=body.tested_at,
        result=body.result,
        sensors_responded=sorted(responded),
        tested_by_user_id=None
        if body.tested_by_worker_id
        else (body.tested_by_user_id or p.user.id),
        tested_by_worker_id=body.tested_by_worker_id,
        gas_cylinder_lot=body.gas_cylinder_lot,
        gas_cylinder_expiry=body.gas_cylinder_expiry,
    )
    db.add(b)
    before = d.status
    if body.result == BumpTestResult.fail:
        quarantine(db, d, QuarantineReason.bump_test_failed)
    elif (
        d.status == DetectorStatus.quarantined
        and d.quarantine_reason == QuarantineReason.bump_test_failed
        and acommon.local_day(body.tested_at) >= d.calibrated_on
        and d.calibration_due_on >= today()
        and _calibrated_after_quarantine(d)
    ):
        d.status = DetectorStatus.in_service
        d.quarantine_reason = None
        d.quarantined_at = None
    db.flush()
    _audit(
        db,
        p,
        d.project_id,
        EntityType.gas_detector,
        d.id,
        AuditAction.update,
        {"status": before.value},
        {"status": d.status.value},
        {"bump_test": body.result.value, "tested_at": body.tested_at.isoformat()},
    )
    return _bump_read(db, b, Refs(db), acommon.can_see_names(p, d.project_id))


def _calibrated_after_quarantine(d: GasDetector) -> bool:
    return d.quarantined_at is None or d.calibrated_on >= acommon.local_day(d.quarantined_at)


def quarantine(db: Session, d: GasDetector, reason: QuarantineReason) -> None:
    if d.status == DetectorStatus.retired:
        return
    d.status = DetectorStatus.quarantined
    d.quarantine_reason = reason
    d.quarantined_at = now()
    users = set(contractor_reps(db, d.project_id, d.engagement_id)) | set(
        common.officers(db, d.project_id)
    )
    if users:
        en = (
            "failed bump test"
            if reason == QuarantineReason.bump_test_failed
            else "calibration overdue"
        )
        ar = (
            "فشل اختبار الاستجابة"
            if reason == QuarantineReason.bump_test_failed
            else "تأخر المعايرة"
        )
        notify.notify(
            db,
            users,
            NotificationKind.gas_detector_quarantined,
            f"{d.detector_no} quarantined: {en}",
            f"تم عزل الجهاز {d.detector_no}: {ar}",
            None,
            None,
            EntityType.gas_detector,
            d.id,
            d.project_id,
        )


def retire(
    db: Session, p: Principal, detector_id: uuid.UUID, body: DetectorRetireInput
) -> DetectorRead:
    d = _get_detector(db, p, detector_id)
    _manage(p, d)
    if d.status == DetectorStatus.retired:
        raise validation_error("status", "The detector is already retired.")
    before = d.status
    d.status = DetectorStatus.retired
    d.retired_reason = body.reason
    d.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        d.project_id,
        EntityType.gas_detector,
        d.id,
        AuditAction.status_change,
        {"status": before.value},
        {"status": "retired"},
        {"reason": body.reason},
    )
    return detector_read(db, p, d)


def daily_job(db: Session, at: datetime | None = None) -> int:
    """§4.6 job 00:05: calibration_due_on < today → Quarantined; §7 alerts 30/14/7/0 days."""
    at = at or now()
    day = acommon.local_day(at)
    n = 0
    for d in db.scalars(select(GasDetector).where(GasDetector.status != DetectorStatus.retired)):
        if d.calibration_due_on < day and d.status == DetectorStatus.in_service:
            quarantine(db, d, QuarantineReason.calibration_overdue)
            d.quarantined_at = at
            _audit(
                db,
                None,
                d.project_id,
                EntityType.gas_detector,
                d.id,
                AuditAction.status_change,
                {"status": "in_service"},
                {"status": "quarantined", "reason": "calibration_overdue"},
            )
            n += 1
        left = (d.calibration_due_on - day).days
        for k in CAL_ALERT_DAYS:
            key = f"cal_{k}"
            if 0 <= left <= k and key not in (d.alerts_sent or []):
                # one alert per threshold, the most specific first time it is crossed
                d.alerts_sent = [
                    *(d.alerts_sent or []),
                    *[f"cal_{x}" for x in CAL_ALERT_DAYS if x >= k],
                ]
                users = set(contractor_reps(db, d.project_id, d.engagement_id))
                if k <= 7:
                    users |= set(common.officers(db, d.project_id))
                if users:
                    notify.notify(
                        db,
                        users,
                        NotificationKind.gas_detector_calibration_due,
                        f"{d.detector_no} calibration due {d.calibration_due_on.isoformat()} ({left} days)",
                        f"معايرة الجهاز {d.detector_no} مستحقة في {d.calibration_due_on.isoformat()} ({left} يوم)",
                        None,
                        None,
                        EntityType.gas_detector,
                        d.id,
                        d.project_id,
                    )
                break
    db.flush()
    return n


# ---- gas tests: evaluation -----------------------------------------------------------------------


def _limits_read(lim: rules.Limits) -> AppliedLimits:
    j = lim.as_json()
    return AppliedLimits(
        profiles=[GasLimitProfile(x) for x in lim.profiles],
        limits=GasLimitSet(
            o2_min_pct=j["o2_min_pct"],
            o2_max_pct=j["o2_max_pct"],
            lel_below_pct=j["lel_below_pct"],
            h2s_below_ppm=j["h2s_below_ppm"],
            co_below_ppm=j["co_below_ppm"],
        ),
        other_toxics=[OtherGasLimit.model_validate(o) for o in lim.other],
    )


def _reading_json(r: GasReadingInput) -> dict[str, Any]:
    return {
        "point": r.point.value,
        "o2_pct": None if r.o2_pct is None else str(r.o2_pct),
        "lel_pct": None if r.lel_pct is None else str(r.lel_pct),
        "h2s_ppm": None if r.h2s_ppm is None else str(r.h2s_ppm),
        "co_ppm": None if r.co_ppm is None else str(r.co_ppm),
        "other": [{"gas": o.gas, "value": str(o.value), "unit": o.unit} for o in r.other],
    }


def _reading_read(r: dict[str, Any], lim: rules.Limits) -> GasReadingRead:
    return GasReadingRead(
        point=GasReadingPoint(r["point"]),
        o2_pct=rules.dec(r.get("o2_pct")),
        lel_pct=rules.dec(r.get("lel_pct")),
        h2s_ppm=rules.dec(r.get("h2s_ppm")),
        co_ppm=rules.dec(r.get("co_ppm")),
        other=[OtherReading.model_validate(o) for o in r.get("other") or []],
        fail_codes=rules.evaluate_readings([r], lim),
    )


def _worst(readings: list[dict[str, Any]], lim: rules.Limits) -> GasReadingRead:
    def vals(k: str) -> list[Any]:
        return [rules.dec(r.get(k)) for r in readings if r.get(k) is not None]

    o2 = vals("o2_pct")
    worst_o2 = None
    if o2:
        mid = (lim.o2_min + lim.o2_max) / 2
        worst_o2 = max(o2, key=lambda v: abs(v - mid))
    w: dict[str, Any] = {
        "point": readings[0]["point"]
        if len(readings) == 1
        else GasReadingPoint.at_work_point.value,
        "o2_pct": worst_o2,
        "lel_pct": max(vals("lel_pct"), default=None),
        "h2s_ppm": max(vals("h2s_ppm"), default=None),
        "co_ppm": max(vals("co_ppm"), default=None),
        "other": [],
    }
    return _reading_read(w, lim)


@dataclass
class Check:
    code: ErrorCode
    en: str
    ar: str
    field: str | None = None


def _checks(
    db: Session,
    permit: Permit,
    test_type: GasTestType,
    tested_at: datetime | None,
    detector: GasDetector | None,
    readings: list[dict[str, Any]],
    at: datetime,
) -> list[Check]:
    out: list[Check] = []
    types = list(permit.work_types)
    if tested_at is not None:
        if tested_at > at + FUTURE_TOLERANCE:
            out.append(
                Check(
                    ErrorCode.VALIDATION_ERROR,
                    "tested_at is in the future.",
                    "وقت الفحص في المستقبل.",
                    "tested_at",
                )
            )
        elif tested_at < at - timedelta(minutes=BACKDATE_MINUTES):
            out.append(
                Check(
                    ErrorCode.BACKDATED_TEST,
                    f"Tests cannot be recorded more than {BACKDATE_MINUTES} min after they were taken.",
                    f"لا يمكن تسجيل الفحص بعد أكثر من {BACKDATE_MINUTES} دقيقة من إجرائه.",
                    "tested_at",
                )
            )
    if detector is not None:
        test_day = acommon.local_day(tested_at or at)
        if detector.project_id != permit.project_id:
            out.append(
                Check(
                    ErrorCode.VALIDATION_ERROR,
                    "Detector not on this project.",
                    "الجهاز ليس في هذا المشروع.",
                    "detector_id",
                )
            )
        elif detector.calibration_due_on < test_day or (
            detector.status == DetectorStatus.quarantined
            and detector.quarantine_reason == QuarantineReason.calibration_overdue
        ):
            out.append(
                Check(
                    ErrorCode.DETECTOR_CALIBRATION_OVERDUE,
                    f"{detector.detector_no} calibration was due {detector.calibration_due_on.isoformat()}.",
                    f"معايرة الجهاز {detector.detector_no} كانت مستحقة في {detector.calibration_due_on.isoformat()}.",
                    "detector_id",
                )
            )
        elif detector.status != DetectorStatus.in_service:
            out.append(
                Check(
                    ErrorCode.DETECTOR_NOT_IN_SERVICE,
                    f"{detector.detector_no} is {detector.status.value}.",
                    f"الجهاز {detector.detector_no} غير صالح للاستخدام.",
                    "detector_id",
                )
            )
        else:
            t = tested_at or at
            bump = db.scalar(
                select(BumpTest.id).where(
                    BumpTest.detector_id == detector.id,
                    BumpTest.result == BumpTestResult.pass_,
                    BumpTest.tested_at <= t,
                    BumpTest.tested_at >= acommon.local_midnight_utc(test_day),
                )
            )
            if bump is None:
                out.append(
                    Check(
                        ErrorCode.BUMP_TEST_MISSING,
                        f"{detector.detector_no} has no passing bump test today before the test.",
                        f"لا يوجد اختبار استجابة ناجح للجهاز {detector.detector_no} اليوم قبل الفحص.",
                        "detector_id",
                    )
                )
        missing = [s for s in rules.required_sensors(types) if s not in detector.sensors]
        if missing:
            out.append(
                Check(
                    ErrorCode.DETECTOR_SENSOR_MISSING,
                    f"{detector.detector_no} lacks sensors: {', '.join(missing)}.",
                    f"الجهاز {detector.detector_no} يفتقد الحساسات: {', '.join(missing)}.",
                    "detector_id",
                )
            )
    if PermitType.confined_space.value in types and test_type in (
        GasTestType.pre_entry,
        GasTestType.pre_issue,
    ):
        points = {r["point"] for r in readings}
        if not points >= CSE_POINTS:
            out.append(
                Check(
                    ErrorCode.CSE_POINTS_REQUIRED,
                    "Confined-space pre-entry tests need top, middle and bottom readings (CS-2).",
                    "فحص ما قبل الدخول يتطلب قراءات أعلى ووسط وأسفل المكان.",
                    "readings",
                )
            )
    return out


def preview(db: Session, p: Principal, permit_id: uuid.UUID, body: GasTestPreview) -> GasEvaluation:
    from app.services.ptw import facts  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    f = facts.compute(db, permit)
    readings = [_reading_json(r) for r in body.readings]
    det = db.get(GasDetector, body.detector_id) if body.detector_id else None
    errs = _checks(db, permit, body.test_type, body.tested_at, det, readings, now())
    fails = rules.evaluate_readings(readings, f.limits)
    return GasEvaluation(
        result=GasTestResult.fail if fails else GasTestResult.pass_,
        fail_codes=fails,
        worst=_worst(readings, f.limits),
        applicable_limits=_limits_read(f.limits),
        errors=[c.code.value for c in errs],
    )


# ---- gas tests: record ---------------------------------------------------------------------------


def _test_read(
    db: Session, p: Principal | None, t: GasTest, refs: Refs | None = None
) -> GasTestRead:
    refs = refs or Refs(db)
    permit = db.get(Permit, t.permit_id)
    assert permit is not None  # noqa: S101
    a = db.get(PtwAppointment, t.tester_appointment_id)
    det = db.get(GasDetector, t.detector_id)
    assert det is not None  # noqa: S101
    shift = db.get(PermitShift, t.shift_id) if t.shift_id else None
    lim_json = t.applicable_limits
    lim = rules.Limits(
        o2_min=rules.dec(lim_json["o2_min_pct"]),  # type: ignore[arg-type]
        o2_max=rules.dec(lim_json["o2_max_pct"]),  # type: ignore[arg-type]
        lel_below=rules.dec(lim_json["lel_below_pct"]),  # type: ignore[arg-type]
        h2s_below=rules.dec(lim_json["h2s_below_ppm"]),  # type: ignore[arg-type]
        co_below=rules.dec(lim_json["co_below_ppm"]),  # type: ignore[arg-type]
        profiles=tuple(lim_json.get("profiles") or ["general"]),
        other=tuple(lim_json.get("other_toxics") or []),
    )
    recorded = refs.user(t.recorded_by_user_id)
    assert recorded is not None  # noqa: S101
    names = acommon.can_see_names(p, t.project_id)
    return GasTestRead(
        id=t.id,
        test_no=t.test_no,
        permit=common.permit_ref(permit),
        shift_no=shift.shift_no if shift else None,
        test_type=t.test_type,
        tested_at=t.tested_at,
        tester=appointment_ref(db, p, a),
        recorded_by=recorded,
        tester_signature_attachment_id=t.tester_signature_attachment_id if names else None,
        detector=detector_ref(det),
        readings=[_reading_read(r, lim) for r in t.readings],
        internal_temp_c=t.internal_temp_c,
        applicable_limits=_limits_read(lim),
        result=t.result,
        fail_codes=[GasFailCode(c) for c in t.fail_codes],
        valid_for_start_until=t.valid_for_start_until,
        next_due_at=t.next_due_at,
        superseded=t.superseded,
        superseded_reason=t.superseded_reason,
        note=t.note,
        created_at=t.created_at,
    )


def _tester(
    db: Session, permit: Permit, appointment_id: uuid.UUID, gas_types: list[str], at: datetime
) -> PtwAppointment:
    a = db.get(PtwAppointment, appointment_id)
    types = gas_types or list(permit.work_types)
    if (
        a is None
        or a.project_id != permit.project_id
        or a.function != AppointmentFunction.gas_tester
        or not common.appointment_covers(
            a, types, permit.site_id, permit.zone_ids, [acommon.local_day(at)]
        )
    ):
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "The tester needs an Active gas_tester appointment covering this zone and permit type (GT-2).",
            "يجب أن يحمل الفاحص تعييناً سارياً كفاحص غاز يغطي المنطقة ونوع التصريح.",
            field="tester_appointment_id",
        )
    return a


def _is_self(db: Session, p: Principal, a: PtwAppointment) -> bool:
    if a.holder_user_id == p.user.id:
        return True
    if a.holder_worker_id:
        w = db.get(Worker, a.holder_worker_id)
        return bool(w and w.user_id == p.user.id)
    return False


def _signature_bytes(b64: str) -> bytes:
    from app.services.access.inductions import _signature  # noqa: PLC0415

    try:
        return _signature(b64)
    except ApiError as exc:
        raise validation_error(
            "tester_signature_png_base64", "The signature must be a PNG image."
        ) from exc


def next_test_no(db: Session, permit: Permit) -> tuple[int, str]:
    seq = (db.scalar(select(func.max(GasTest.seq)).where(GasTest.permit_id == permit.id)) or 0) + 1
    return seq, f"GT-{permit.permit_no}-{seq:02d}"


def record(db: Session, p: Principal, permit_id: uuid.UUID, body: GasTestCreate) -> GasTestRead:
    from app.services.ptw import facts  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    acommon.require_cap(
        p, permit.project_id, C.gas_test_record, [permit.site_id], permit.engagement_id
    )
    if permit.status not in GAS_TEST_PERMIT_STATUSES:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "Gas tests are recorded on Approved, Issued, Active or Suspended permits.",
            "تسجل فحوص الغاز على التصاريح المعتمدة أو الصادرة أو السارية أو الموقوفة.",
            status=409,
        )
    at = now()
    f = facts.compute(db, permit)
    a = _tester(db, permit, body.tester_appointment_id, f.gas_types, body.tested_at)
    det = db.get(GasDetector, body.detector_id)
    if det is None:
        raise validation_error("detector_id", "Detector not found.")
    readings = [_reading_json(r) for r in body.readings]
    errs = _checks(db, permit, body.test_type, body.tested_at, det, readings, at)
    if errs:
        e = errs[0]
        raise common.err(e.code, e.en, e.ar, field=e.field)
    if PermitType.confined_space.value in permit.work_types and body.internal_temp_c is None:
        raise validation_error(
            "internal_temp_c", "Record the internal temperature at every CSE test (GT-9)."
        )
    self_test = _is_self(db, p, a)
    if not self_test and not body.tester_signature_png_base64:
        raise common.err(
            ErrorCode.TESTER_SIGNATURE_REQUIRED,
            "The gas tester must sign on this device.",
            "يجب أن يوقّع فاحص الغاز على هذا الجهاز.",
            field="tester_signature_png_base64",
        )
    fails = rules.evaluate_readings(readings, f.limits)
    s = f.settings
    seq, no = next_test_no(db, permit)
    t = GasTest(
        id=uuid.uuid4(),
        project_id=permit.project_id,
        permit_id=permit.id,
        shift_id=permit.current_shift_id,
        seq=seq,
        test_no=no,
        test_type=body.test_type,
        tested_at=body.tested_at,
        tester_appointment_id=a.id,
        recorded_by_user_id=p.user.id,
        detector_id=det.id,
        readings=readings,
        internal_temp_c=body.internal_temp_c,
        applicable_limits=f.limits.as_json(),
        result=GasTestResult.fail if fails else GasTestResult.pass_,
        fail_codes=[c.value for c in fails],
        valid_for_start_until=body.tested_at + timedelta(minutes=s.gas_pre_start_validity_minutes),
        next_due_at=(
            body.tested_at + timedelta(minutes=f.interval) if not fails and f.interval else None
        ),
        note=body.note,
    )
    db.add(t)
    db.flush()
    if not self_test and body.tester_signature_png_base64:
        att = attachments.store(
            db,
            AttachmentOwner.gas_test_signature,
            t.id,
            permit.project_id,
            f"{no}-signature.png",
            _signature_bytes(body.tester_signature_png_base64),
            "image/png",
            p.user.id,
        )
        t.tester_signature_attachment_id = att.id
    common.sign(
        db,
        permit,
        SignaturePurpose.gas_test,
        "gas_tester",
        user_id=a.holder_user_id if self_test else None,
        worker_id=None if a.holder_user_id else a.holder_worker_id,
        appointment_id=a.id,
        entity_id=t.id,
        co_device=None if self_test else p.user.id,
        at=at,
    )
    _audit(
        db,
        p,
        permit.project_id,
        EntityType.gas_test,
        t.id,
        AuditAction.create,
        None,
        {"test_no": no, "result": t.result.value, "fail_codes": t.fail_codes},
    )
    if fails:
        _on_fail(db, permit, t, StatusReason.gas_test_failed)
    else:
        from app.services.ptw import evaluation  # noqa: PLC0415

        evaluation.refresh(db, permit)
    return _test_read(db, p, t)


def _on_fail(db: Session, permit: Permit, t: GasTest, reason: StatusReason) -> None:
    """GT-6 / GT-7: immediate suspension of an Issued/Active permit and alerts."""
    from app.services.ptw import evaluation, lifecycle  # noqa: PLC0415

    if permit.status in (PermitStatus.issued, PermitStatus.active):
        lifecycle.auto_suspend(db, permit, reason, t.test_no, t.test_no)
    cse = PermitType.confined_space.value in permit.work_types
    users = common.permit_people(db, permit, reps=True, officer=True, manager=cse)
    codes = ", ".join(t.fail_codes) or reason.value
    common.tell(
        db,
        permit,
        users,
        NotificationKind.gas_test_failed,
        f"Gas test {t.test_no} failed ({codes})",
        f"فشل فحص الغاز {t.test_no} ({codes})",
    )
    evaluation.refresh(db, permit)


def list_for_permit(db: Session, p: Principal, permit_id: uuid.UUID) -> GasTestList:
    permit = common.get_permit(db, p, permit_id)
    rows = db.scalars(
        select(GasTest).where(GasTest.permit_id == permit.id).order_by(GasTest.tested_at.desc())
    )
    refs = Refs(db)
    return GasTestList(items=[_test_read(db, p, t, refs) for t in rows])


def list_project(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    permit_id: uuid.UUID | None,
    detector_id: uuid.UUID | None,
    test_types: list[GasTestType] | None,
    result: GasTestResult | None,
    date_from: date | None,
    date_to: date | None,
) -> GasTestPage:
    g = _view(db, p, project_id)
    stmt = (
        select(GasTest)
        .join(Permit, Permit.id == GasTest.permit_id)
        .where(GasTest.project_id == project_id)
    )
    if g.site_ids is not None:
        stmt = stmt.where(Permit.site_id.in_(list(g.site_ids)))
    if g.engagement_ids is not None:
        stmt = stmt.where(Permit.engagement_id.in_(list(g.engagement_ids)))
    if permit_id:
        stmt = stmt.where(GasTest.permit_id == permit_id)
    if detector_id:
        stmt = stmt.where(GasTest.detector_id == detector_id)
    if test_types:
        stmt = stmt.where(GasTest.test_type.in_(test_types))
    if result:
        stmt = stmt.where(GasTest.result == result)
    if date_from:
        stmt = stmt.where(GasTest.tested_at >= acommon.local_midnight_utc(date_from))
    if date_to:
        stmt = stmt.where(
            GasTest.tested_at < acommon.local_midnight_utc(date_to + timedelta(days=1))
        )
    rows, total = paginate(db, stmt.order_by(GasTest.tested_at.desc()), page, size)
    refs = Refs(db)
    return GasTestPage(
        items=[_test_read(db, p, t, refs) for t in rows], total=total, page=page, page_size=size
    )


def _get_test(db: Session, p: Principal, gas_test_id: uuid.UUID) -> GasTest:
    t = db.get(GasTest, gas_test_id)
    if t is None:
        raise not_found("Gas test")
    common.get_permit(db, p, t.permit_id)
    return t


def read_test(db: Session, p: Principal, gas_test_id: uuid.UUID) -> GasTestRead:
    return _test_read(db, p, _get_test(db, p, gas_test_id))


def supersede(
    db: Session, p: Principal, gas_test_id: uuid.UUID, body: GasTestSupersede
) -> GasTestRead:
    t = _get_test(db, p, gas_test_id)
    permit = db.get(Permit, t.permit_id)
    assert permit is not None  # noqa: S101
    acommon.require_cap(
        p, permit.project_id, C.gas_test_record, [permit.site_id], permit.engagement_id
    )
    if t.superseded:
        raise validation_error("gas_test_id", "The test is already superseded.")
    if permit.status in PERMIT_TERMINAL:
        raise common.err(
            ErrorCode.PERMIT_READ_ONLY, "The permit is closed.", "التصريح مغلق.", status=409
        )
    t.superseded = True
    t.superseded_reason = body.reason
    db.flush()
    _audit(
        db,
        p,
        permit.project_id,
        EntityType.gas_test,
        t.id,
        AuditAction.update,
        {"superseded": False},
        {"superseded": True},
        {"reason": body.reason},
    )
    from app.services.ptw import evaluation  # noqa: PLC0415

    evaluation.refresh(db, permit)
    return _test_read(db, p, t)


# ---- permit gas state (GT-3, GT-4, §6.3) ---------------------------------------------------------


def tests_of(db: Session, permit_id: uuid.UUID) -> list[GasTest]:
    return list(
        db.scalars(
            select(GasTest)
            .where(GasTest.permit_id == permit_id, GasTest.superseded.is_(False))
            .order_by(GasTest.tested_at)
        )
    )


@dataclass
class GasState:
    required: bool
    latest: GasTest | None
    latest_pass: GasTest | None
    next_due_at: datetime | None
    status: GasStatus


def state(
    db: Session, permit: Permit, interval: int | None, required: bool, at: datetime
) -> GasState:
    rows = [t for t in tests_of(db, permit.id) if t.tested_at <= at + FUTURE_TOLERANCE]
    latest = rows[-1] if rows else None
    passes = [t for t in rows if t.result == GasTestResult.pass_]
    lp = passes[-1] if passes else None
    due = lp.tested_at + timedelta(minutes=interval) if lp and interval else None
    if not required:
        st = GasStatus.not_required
    elif latest is None:
        st = GasStatus.missing
    elif latest.result == GasTestResult.fail:
        st = GasStatus.failed
    elif due and at >= due:
        st = GasStatus.overdue
    elif due and at >= due - timedelta(minutes=10):
        st = GasStatus.due_soon
    else:
        st = GasStatus.valid
    return GasState(required, latest, lp, due, st)


def valid_for_start(
    db: Session,
    permit: Permit,
    at: datetime,
    validity_minutes: int,
    *,
    after: datetime | None = None,
) -> GasTest | None:
    """A passing, non-superseded test with tested_at ≥ at − validity (and ≥ `after`)."""
    lo = at - timedelta(minutes=validity_minutes)
    if after and after > lo:
        lo = after
    for t in reversed(tests_of(db, permit.id)):
        if t.tested_at > at + FUTURE_TOLERANCE:
            continue
        if t.tested_at < lo:
            break
        if t.result == GasTestResult.pass_:
            return t
    return None


def failed_since(db: Session, permit: Permit, since: datetime | None) -> GasTest | None:
    rows = tests_of(db, permit.id)
    if not rows or rows[-1].result != GasTestResult.fail:
        return None
    t = rows[-1]
    return t if since is None or t.tested_at >= since else None


def shift_compliant(
    db: Session,
    permit: Permit,
    shift: PermitShift,
    interval: int | None,
    validity: int,
    break_minutes: int,
    end: datetime,
    ended_by_overdue: bool,
) -> bool:
    """§6.3 K-66: start test valid at started_at; the latest passing test < interval old at
    every instant of work (Active, not paused); every restart after a stop ≥ break preceded by a
    passing test within start validity. A shift ended by a retest-overdue suspension is not
    compliant (work reached the due time without a test; DECISIONS)."""
    if ended_by_overdue:
        return False
    passes = sorted(t.tested_at for t in tests_of(db, permit.id) if t.result == GasTestResult.pass_)

    def latest_before(t: datetime) -> datetime | None:
        c = [x for x in passes if x <= t]
        return c[-1] if c else None

    start = shift.started_at
    first = latest_before(start)
    if first is None or start - first > timedelta(minutes=validity):
        return False
    work: list[tuple[datetime, datetime]] = []
    cur = start
    for ps in sorted(shift.pauses or [], key=lambda x: x["from"]):
        pf = datetime.fromisoformat(ps["from"])
        pt = datetime.fromisoformat(ps["to"]) if ps.get("to") else end
        if pf > cur:
            work.append((cur, min(pf, end)))
        if (pt - pf) >= timedelta(minutes=break_minutes) and pt < end:
            lb = latest_before(pt)
            if (
                lb is None
                or pt - lb > timedelta(minutes=validity)
                or lb < pf - timedelta(minutes=validity)
            ):
                return False
        cur = max(cur, pt)
    if cur < end:
        work.append((cur, end))
    if not interval:
        return True
    limit = timedelta(minutes=interval)
    for a, b in work:
        lb = latest_before(a)
        if lb is None or a - lb > limit:
            return False
        for x in [x for x in passes if a < x < b]:
            if x - lb > limit:
                return False
            lb = x
        if b - lb > limit:
            return False
    return True
