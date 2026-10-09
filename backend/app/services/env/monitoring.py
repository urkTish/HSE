"""Instruments and `env_monitor` devices, station ingest and derived averages, monitoring points
with tighten-only limits, readings and background declarations (spec 6e-environmental §3.7–§3.11,
§6.2, MON-1…MON-4, LIM-1…LIM-3, EXD-3, WAT-3)."""

from __future__ import annotations

import math
import secrets
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import OpsEventType
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.env_enums import (
    Averaging,
    InstrumentAction,
    InstrumentKind,
    InstrumentStatus,
    LimitSource,
    NoiseArea,
    NoisePeriod,
    Parameter,
    PermitType,
    PointKind,
    PointSource,
    ProviderKind,
    ReadingResult,
    ReadingSource,
    RecordState,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.security import decode_jwt, token_digest
from app.models import (
    BackgroundDeclaration,
    EnvExceedance,
    EnvInstrument,
    EnvMonitorDevice,
    EnvPoint,
    EnvProvider,
    EnvReading,
    OpsEvent,
    Zone,
)
from app.schemas.env import (
    BackgroundCreate,
    BackgroundPage,
    BackgroundRead,
    EnvDeviceCreate,
    EnvDeviceRead,
    EnvStationSessionInput,
    EnvStationSessionRead,
    EnvVoid,
    InstrumentCreate,
    InstrumentPage,
    InstrumentRead,
    InstrumentTransition,
    InstrumentUpdate,
    PointCreate,
    PointPage,
    PointRead,
    PointUpdate,
    ReadingCreate,
    ReadingPage,
    ReadingRead,
    Requirement,
    RequirementRead,
    StationPush,
    StationPushResult,
)
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal

C = Capability
ET = EntityType
NK = NotificationKind
D = Decimal
AV = Averaging
IS = InstrumentStatus
Q15 = timedelta(minutes=15)
SLM_KINDS = frozenset({InstrumentKind.sound_level_meter, InstrumentKind.noise_station})


def _conflict(en: str, ar: str = "لا يمكن تنفيذ هذا الإجراء في الحالة الحالية.") -> ApiError:
    return ApiError(409, ErrorCode.INVALID_TRANSITION, en, ar)


# ---- instruments (§3.7, MON-1) -------------------------------------------------------------------


def instrument_read(x: EnvInstrument) -> InstrumentRead:
    return InstrumentRead(
        id=x.id, project_id=x.project_id, instrument_no=x.instrument_no, kind=x.kind,
        make_model=x.make_model, serial_no=x.serial_no, standard_class=x.standard_class,
        calibration_valid_until=x.calibration_valid_until,
        calibration_cert_ref=x.calibration_cert_ref, status=x.status,
        status_reason=x.status_reason,
    )  # fmt: skip


def _instrument(db: Session, p: Principal, iid: uuid.UUID) -> EnvInstrument:
    x = db.get(EnvInstrument, iid)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Instrument")
    ec.need(p, x.project_id, C.env_view, write=False)
    return x


def list_instruments(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int
) -> InstrumentPage:
    ec.view_grant(db, p, project_id)
    rows = list(
        db.scalars(
            select(EnvInstrument)
            .where(EnvInstrument.project_id == project_id)
            .order_by(EnvInstrument.instrument_no)
        )
    )
    return ec.paged(InstrumentPage, rows, page, size, instrument_read)


def _cal_future(d: date) -> None:
    if d <= ec.local_day():
        raise ec.code_err(
            ErrorCode.INSTRUMENT_CALIBRATION_EXPIRED,
            "Calibration must be valid beyond today (MON-1).",
            "يجب أن تكون معايرة الجهاز سارية بعد اليوم.", "calibration_valid_until",
        )  # fmt: skip


def create_instrument(
    db: Session, p: Principal, project_id: uuid.UUID, body: InstrumentCreate
) -> InstrumentRead:
    pr = ec.project(db, p, project_id)
    p.require(project_id, C.env_monitoring_manage)
    _cal_future(body.calibration_valid_until)
    if body.kind in SLM_KINDS and body.standard_class not in ("1", "2"):
        raise validation_error(
            "standard_class", "Sound level meters need IEC 61672-1 class 1 or 2."
        )
    if db.scalar(
        select(EnvInstrument.id).where(
            EnvInstrument.project_id == project_id, EnvInstrument.serial_no == body.serial_no
        )
    ):
        raise ApiError(409, ErrorCode.DUPLICATE_VALUE, "This serial number exists.",
                       "الرقم التسلسلي مستخدم.")  # fmt: skip
    n = int(
        db.scalar(
            select(func.count(EnvInstrument.id)).where(EnvInstrument.project_id == project_id)
        )
        or 0
    )
    x = EnvInstrument(
        id=uuid.uuid4(), project_id=project_id, instrument_no=f"EMI-{pr.code}-{n + 1:02d}",
        status=IS.active, created_by_user_id=p.user.id, **body.model_dump(),
    )  # fmt: skip
    db.add(x)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_instrument, x, project_id)
    return instrument_read(x)


def update_instrument(
    db: Session, p: Principal, iid: uuid.UUID, body: InstrumentUpdate
) -> InstrumentRead:
    x = _instrument(db, p, iid)
    p.require(x.project_id, C.env_monitoring_manage)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(x, k, v)
    x.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_instrument, x, x.project_id)
    return instrument_read(x)


def transition_instrument(
    db: Session, p: Principal, iid: uuid.UUID, body: InstrumentTransition
) -> InstrumentRead:
    x = _instrument(db, p, iid)
    p.require(x.project_id, C.env_monitoring_manage)
    if x.status == IS.retired:
        raise _conflict("A retired instrument cannot change.")
    if body.action == InstrumentAction.activate:
        _cal_future(x.calibration_valid_until)
        x.status, x.status_reason = IS.active, None
    elif body.action == InstrumentAction.quarantine:
        x.status, x.status_reason = IS.quarantined, ec.reason(body.reason, 5)
    else:
        x.status, x.status_reason = IS.retired, body.reason
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_instrument, x, x.project_id)
    return instrument_read(x)


# ---- env_monitor devices and station sessions (§11.3, MON-2) -------------------------------------


def device_read(d: EnvMonitorDevice, token: str | None = None) -> EnvDeviceRead:
    return EnvDeviceRead(
        id=d.id, instrument_id=d.instrument_id, device_id=d.device_id, label=d.label,
        registered_at=d.registered_at, last_seen_at=d.last_seen_at, revoked_at=d.revoked_at,
        device_token=token,
    )  # fmt: skip


def register_device(
    db: Session, p: Principal, iid: uuid.UUID, body: EnvDeviceCreate
) -> EnvDeviceRead:
    x = _instrument(db, p, iid)
    p.require(x.project_id, C.env_monitoring_manage)
    if x.kind not in rf.STATION_KINDS or x.status != IS.active:
        raise validation_error("device_id", "Only an active station instrument takes a device.")
    token = secrets.token_urlsafe(32)
    d = EnvMonitorDevice(
        id=uuid.uuid4(), project_id=x.project_id, instrument_id=x.id, device_id=body.device_id,
        label=body.label, token_hash=token_digest(token), registered_at=now(),
        registered_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(d)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_monitor_device, d, x.project_id)
    return device_read(d, token)


def revoke_device(db: Session, p: Principal, iid: uuid.UUID, device_pk: uuid.UUID) -> EnvDeviceRead:
    x = _instrument(db, p, iid)
    p.require(x.project_id, C.env_monitoring_manage)
    d = db.get(EnvMonitorDevice, device_pk)
    if d is None or d.instrument_id != x.id:
        raise not_found("Device")
    if d.revoked_at is not None:
        raise _conflict("The device is already revoked.")
    d.revoked_at = now()
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_monitor_device, d, x.project_id)
    return device_read(d)


def _unauth() -> ApiError:
    return ApiError(
        401, ErrorCode.GATE_DEVICE_REVOKED,
        "This monitoring device is not registered or was revoked.",
        "جهاز الرصد غير مسجل أو تم إلغاؤه.",
    )  # fmt: skip


def _station_point(db: Session, instrument_id: uuid.UUID) -> EnvPoint | None:
    return db.scalar(
        select(EnvPoint).where(
            EnvPoint.instrument_id == instrument_id,
            EnvPoint.source_kind == PointSource.station,
            EnvPoint.active.is_(True),
        )
    )


def station_session(db: Session, body: EnvStationSessionInput) -> EnvStationSessionRead:
    d = db.scalar(
        select(EnvMonitorDevice).where(
            EnvMonitorDevice.token_hash == token_digest(body.device_token)
        )
    )
    if d is None or d.revoked_at is not None:
        raise _unauth()
    ins = db.get(EnvInstrument, d.instrument_id)
    if ins is None:
        raise _unauth()
    at = now()
    d.last_seen_at = at
    s = get_settings()
    claims = {"sub": str(d.id), "sid": str(uuid.uuid4()), "typ": "gate", "kind": "env_monitor",
              "exp": at + timedelta(days=30)}  # fmt: skip
    token = jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm)
    pt = _station_point(db, ins.id)
    db.flush()
    return EnvStationSessionRead(
        access_token=token,
        instrument_no=ins.instrument_no,
        point_code=pt.point_code if pt else None,
    )


def ingest(db: Session, token: str | None, body: StationPush) -> StationPushResult:
    claims = decode_jwt(token) if token else None
    if not claims or claims.get("kind") != "env_monitor":
        raise _unauth()
    try:
        dpk = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise _unauth() from exc
    d = db.get(EnvMonitorDevice, dpk)
    if d is None or d.revoked_at is not None:
        raise _unauth()
    ins = db.get(EnvInstrument, d.instrument_id)
    pt = _station_point(db, d.instrument_id)
    if pt is None or ins is None:
        raise validation_error("values", "The station is not linked to an active point.")
    t = now()
    d.last_seen_at = t
    acc = dup = 0
    for i, v in enumerate(body.values):
        if v.window_start + Q15 > t + timedelta(minutes=2):
            raise validation_error(f"values[{i}].window_start", "The window has not ended.")
        _range(v.parameter, v.value, f"values[{i}].value")
        exists = db.scalar(
            select(EnvReading.id).where(
                EnvReading.device_pk == d.id, EnvReading.parameter == v.parameter,
                EnvReading.averaging == AV.min15, EnvReading.window_start == v.window_start,
            )
        )  # fmt: skip
        if exists:
            dup += 1
            continue
        _calibrated(ins, v.window_start + Q15, f"values[{i}].window_start")
        make_reading(
            db, pt, v.parameter, AV.min15, v.window_start, v.window_start + Q15, v.value,
            ReadingSource.station, instrument_id=ins.id, device_pk=d.id,
        )  # fmt: skip
        acc += 1
    n = derive(db, pt, t)
    return StationPushResult(accepted=acc, duplicates=dup, derived=n)


# ---- limits (§3.9, LIM-1…LIM-3, PRM-5) -----------------------------------------------------------

Lib = tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, str, str]


def lib(param: Parameter, avg: Averaging, period: NoisePeriod, na: NoiseArea | None) -> Lib | None:
    """The DL row (NA for noise) a requirement is prefilled from."""
    if param == Parameter.laeq:
        if na is None or avg not in (AV.h1, AV.measurement) or period == NoisePeriod.any:
            return None
        lim = rf.NA[na][2] if period == NoisePeriod.day else rf.NA[na][3]
        return (lim - 3, lim, None, None, "ncec", f"NA-{na.value}-{period.value}")
    return rf.DL.get((param, avg))


def _dec(v: Any) -> Decimal | None:
    return None if v is None else D(str(v))


def _s(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def _loose(field: str) -> ApiError:
    return ec.code_err(
        ErrorCode.LIMIT_LOOSENING,
        "Limits may only be tightened below the library value (LIM-2).",
        "لا يمكن تخفيف الحدود عن قيمة المكتبة.", field,
    )  # fmt: skip


def build_requirements(reqs: list[Requirement], na: NoiseArea | None) -> list[dict[str, Any]]:
    """LIM-1 prefill (noise rows per period, LIM-3) and LIM-2 tighten-only check."""
    rows: list[Requirement] = []
    for r in reqs:
        if r.parameter == Parameter.laeq and r.period == NoisePeriod.any:
            if na is None:
                raise validation_error("noise_area_category", "Noise points need a list NA area.")
            rows += [
                r.model_copy(update={"period": per}) for per in (NoisePeriod.day, NoisePeriod.night)
            ]
        else:
            rows.append(r)
    out = []
    for i, r in enumerate(rows):
        lb = lib(r.parameter, r.averaging, r.period, na)
        al, li, lo, hi = r.alert_value, r.limit_value, r.limit_min, r.limit_max
        src, ref = r.limit_source, r.library_ref
        if lb is not None:
            al = lb[0] if al is None else al
            li = lb[1] if li is None else li
            lo = lb[2] if lo is None else lo
            hi = lb[3] if hi is None else hi
            src = src or LimitSource(lb[4])
            ref = ref or lb[5]
            f = f"requirements[{i}]"
            if lb[0] is not None and al is not None and al > lb[0]:
                raise _loose(f + ".alert_value")
            if lb[1] is not None and li is not None and li > lb[1]:
                raise _loose(f + ".limit_value")
            if (lb[2] is not None and lo is not None and lo < lb[2]) or (
                lb[3] is not None and hi is not None and hi > lb[3]
            ):
                raise _loose(f + ".limit_min")
        out.append({
            "parameter": r.parameter.value, "averaging": r.averaging.value,
            "schedule": r.schedule.value, "period": r.period.value, "alert_value": _s(al),
            "limit_value": _s(li), "limit_min": _s(lo), "limit_max": _s(hi),
            "limit_source": src.value if src else None, "library_ref": ref,
        })  # fmt: skip
    return out


def _conditions(db: Session, pt: EnvPoint) -> list[dict[str, Any]]:
    out = []
    for pm in ec.project_permits(db, pt.project_id):
        if pm.manual_status is not None and pm.manual_status.value == "cancelled":
            continue
        for c in pm.conditions or []:
            if c.get("point_id") == str(pt.id) and c.get("limit_value") is not None:
                out.append(c)
    return out


def effective(
    db: Session, pt: EnvPoint, req: dict[str, Any]
) -> tuple[Decimal | None, LimitSource | None, str | None]:
    """PRM-5 / LIM-2: a lower permit-condition limit replaces the row limit."""
    lim = _dec(req.get("limit_value"))
    src = LimitSource(req["limit_source"]) if req.get("limit_source") else None
    code = None
    for c in _conditions(db, pt):
        if c.get("parameter") not in (None, req["parameter"]):
            continue
        if c.get("averaging") not in (None, req["averaging"]):
            continue
        v = D(str(c["limit_value"]))
        if lim is None or v < lim:
            lim, src, code = v, LimitSource.permit_condition, c.get("code")
    return lim, src, code


def find_requirement(
    pt: EnvPoint, param: Parameter, avg: Averaging, period: NoisePeriod
) -> dict[str, Any] | None:
    rows = [r for r in pt.requirements or [] if r["parameter"] == param.value]
    for want in (avg, AV.h1) if avg == AV.measurement else (avg,):
        for r in rows:
            if r["averaging"] == want.value and r["period"] in (period.value, "any"):
                return r
    return None


def evaluate(
    db: Session, pt: EnvPoint, param: Parameter, avg: Averaging, period: NoisePeriod,
    value: Decimal,
) -> tuple[ReadingResult, Decimal | None]:  # fmt: skip
    """§6.2 result (unrounded comparison)."""
    if avg == AV.min15:
        return ReadingResult.no_limit, None
    r = find_requirement(pt, param, avg, period)
    if r is None:
        return ReadingResult.no_limit, None
    if param == Parameter.ph:
        lo, hi = _dec(r.get("limit_min")), _dec(r.get("limit_max"))
        if lo is None and hi is None:
            return ReadingResult.no_limit, None
        if lo is not None and value < lo:
            return ReadingResult.exceedance, lo
        if hi is not None and value > hi:
            return ReadingResult.exceedance, hi
        return ReadingResult.ok, hi
    lim, _src, _code = effective(db, pt, r)
    al = _dec(r.get("alert_value"))
    if lim is None:
        return ReadingResult.no_limit, None
    if value > lim:
        return ReadingResult.exceedance, lim
    if al is not None and value >= al:
        return ReadingResult.alert, lim
    return ReadingResult.ok, lim


# ---- points (§3.8) -------------------------------------------------------------------------------


def point_read(db: Session, pt: EnvPoint) -> PointRead:
    z = db.get(Zone, pt.zone_id) if pt.zone_id else None
    reqs = []
    for r in pt.requirements or []:
        lim, src, code = effective(db, pt, r)
        reqs.append(
            RequirementRead(
                **{k: v for k, v in r.items() if k in Requirement.model_fields},
                effective_limit=ec.s1(lim) if r["parameter"] != "ph" else None,
                effective_source=src, condition_code=code,
            )
        )  # fmt: skip
    return PointRead(
        id=pt.id, project_id=pt.project_id, point_code=pt.point_code, site_id=pt.site_id,
        zone_id=pt.zone_id, zone_code=z.code if z else None, airside=airside(db, pt),
        kind=pt.kind, noise_area_category=pt.noise_area_category, source_kind=pt.source_kind,
        instrument_id=pt.instrument_id, permit_id=pt.permit_id, requirements=reqs,
        active=pt.active,
    )  # fmt: skip


def airside(db: Session, pt: EnvPoint) -> bool:
    z = db.get(Zone, pt.zone_id) if pt.zone_id else None
    return pt.kind == PointKind.airside or ec.is_airside(z)


def _point(db: Session, p: Principal, point_id: uuid.UUID) -> EnvPoint:
    pt = db.get(EnvPoint, point_id)
    if pt is None or not p.can_see_project(pt.project_id):
        raise not_found("Monitoring point")
    g = ec.need(p, pt.project_id, C.env_view, write=False)
    if not g.covers_site(pt.site_id):
        raise not_found("Monitoring point")
    return pt


def list_points(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int
) -> PointPage:
    g = ec.view_grant(db, p, project_id)
    rows = [
        x
        for x in db.scalars(
            select(EnvPoint).where(EnvPoint.project_id == project_id).order_by(EnvPoint.point_code)
        )
        if g.covers_site(x.site_id)
    ]
    return ec.paged(PointPage, rows, page, size, lambda x: point_read(db, x))


def _check_point(db: Session, pt: EnvPoint) -> None:
    if pt.source_kind == PointSource.station:
        ins = db.get(EnvInstrument, pt.instrument_id) if pt.instrument_id else None
        if ins is None or ins.project_id != pt.project_id or ins.kind not in rf.STATION_KINDS:
            raise validation_error("instrument_id", "Station points need a station instrument.")
    elif pt.instrument_id is not None:
        ins = db.get(EnvInstrument, pt.instrument_id)
        if ins is None or ins.project_id != pt.project_id:
            raise validation_error("instrument_id", "Unknown instrument.")
    if pt.permit_id is not None:
        pm = next((x for x in ec.project_permits(db, pt.project_id) if x.id == pt.permit_id), None)
        if pm is None:
            raise validation_error("permit_id", "Unknown project permit.")


def create_point(db: Session, p: Principal, project_id: uuid.UUID, body: PointCreate) -> PointRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.env_monitoring_manage)
    ec.site_of(db, project_id, body.site_id)
    ec.zone_of(db, body.site_id, body.zone_id)
    if db.scalar(
        select(EnvPoint.id).where(
            EnvPoint.project_id == project_id, EnvPoint.point_code == body.point_code
        )
    ):
        raise ApiError(409, ErrorCode.DUPLICATE_VALUE, "This point code exists.", "الرمز مستخدم.")
    data = body.model_dump(exclude={"requirements"})
    pt = EnvPoint(
        id=uuid.uuid4(), project_id=project_id, created_by_user_id=p.user.id,
        requirements=build_requirements(body.requirements, body.noise_area_category), **data,
    )  # fmt: skip
    _check_point(db, pt)
    db.add(pt)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_point, pt, project_id)
    return point_read(db, pt)


def read_point(db: Session, p: Principal, point_id: uuid.UUID) -> PointRead:
    return point_read(db, _point(db, p, point_id))


def update_point(db: Session, p: Principal, point_id: uuid.UUID, body: PointUpdate) -> PointRead:
    pt = _point(db, p, point_id)
    p.require(pt.project_id, C.env_monitoring_manage)
    before = {"requirements": list(pt.requirements or [])}
    data = body.model_dump(exclude_unset=True, exclude={"requirements"})
    if "zone_id" in data:
        ec.zone_of(db, pt.site_id, data["zone_id"])
    for k, v in data.items():
        setattr(pt, k, v)
    if body.requirements is not None:
        pt.requirements = build_requirements(body.requirements, pt.noise_area_category)
    _check_point(db, pt)
    pt.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_point, pt, pt.project_id, before)
    return point_read(db, pt)


# ---- readings (§3.10, §6.2, MON-3) ---------------------------------------------------------------


def _range(param: Parameter, value: Decimal, field: str) -> None:
    lo, hi = rf.PA[param][3], rf.PA[param][4]
    if value < lo or value > hi:
        raise ec.code_err(
            ErrorCode.VALUE_OUT_OF_RANGE, f"{rf.PA[param][0]} must be between {lo} and {hi}.",
            f"يجب أن تكون القيمة بين {lo} و {hi}.", field,
        )  # fmt: skip


def _calibrated(ins: EnvInstrument, window_end: datetime, field: str) -> None:
    d = ec.local_day(window_end - timedelta(seconds=1))
    if ins.status == IS.retired or ins.calibration_valid_until < d:
        raise ec.code_err(
            ErrorCode.INSTRUMENT_CALIBRATION_EXPIRED,
            f"{ins.instrument_no} calibration ended {ins.calibration_valid_until.isoformat()}.",
            f"انتهت معايرة الجهاز {ins.instrument_no}.", field,
        )  # fmt: skip


def reading_day(window_end: datetime) -> date:
    """EK-1: local date of window_end (an end at local midnight belongs to the day it closes)."""
    return ec.local_day(window_end - timedelta(seconds=1))


def _next_reading_seq(db: Session, project_id: uuid.UUID, d: date) -> int:
    cache: dict[tuple[uuid.UUID, date], int] = db.info.setdefault("env_rseq", {})
    k = (project_id, d)
    if k not in cache:
        cache[k] = int(
            db.scalar(
                select(func.max(EnvReading.seq)).where(
                    EnvReading.project_id == project_id, EnvReading.day == d
                )
            )
            or 0
        )
    cache[k] += 1
    return cache[k]


def _events(db: Session, project_id: uuid.UUID) -> list[OpsEvent]:
    cache: dict[uuid.UUID, list[OpsEvent]] = db.info.setdefault("env_ops", {})
    if project_id not in cache:
        types = [OpsEventType(t) for t in ec.cfg(db, project_id)["background_ops_event_types"]]
        cache[project_id] = list(
            db.scalars(
                select(OpsEvent).where(OpsEvent.project_id == project_id, OpsEvent.type.in_(types))
            )
        )
    return cache[project_id]


def background_ref(db: Session, pt: EnvPoint, ws: datetime, we: datetime) -> str | None:
    """EXD-3: an ops event of a background type covering the point's zone (or its site), or a
    background declaration covering the site, overlapping the window."""
    for ev in _events(db, pt.project_id):
        if ev.started_at >= we or (ev.ended_at is not None and ev.ended_at <= ws):
            continue
        covers = pt.zone_id in (ev.zone_ids or []) if pt.zone_id else ev.site_id == pt.site_id
        if covers:
            return ev.ops_no
    bd = db.scalar(
        select(BackgroundDeclaration)
        .where(
            BackgroundDeclaration.project_id == pt.project_id,
            BackgroundDeclaration.site_ids.any(pt.site_id),  # type: ignore[arg-type]
            BackgroundDeclaration.from_at < we,
            BackgroundDeclaration.to_at > ws,
        )
        .order_by(BackgroundDeclaration.from_at)
    )
    return bd.declaration_no if bd else None


def make_reading(
    db: Session,
    pt: EnvPoint,
    param: Parameter,
    avg: Averaging,
    ws: datetime,
    we: datetime,
    value: Decimal,
    source: ReadingSource,
    instrument_id: uuid.UUID | None = None,
    device_pk: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    lab_provider_id: uuid.UUID | None = None,
    lab_report_ref: str | None = None,
    field_cal: bool | None = None,
    created_at: datetime | None = None,
    process: bool = True,
    seed: bool = False,
) -> EnvReading:
    """Stores a reading with its day, period (LIM-3), result (§6.2), background flag (EXD-3) and
    late flag, then runs the exceedance rules (EXD-1, EXD-2, EXD-6)."""
    from app.services.env import exceedances  # noqa: PLC0415

    c = ec.cfg(db, pt.project_id)
    day = reading_day(we)
    period = c.period_of(ec.to_local(ws)) if param == Parameter.laeq else NoisePeriod.any
    result, limit = evaluate(db, pt, param, avg, period, value)
    bg = background_ref(db, pt, ws, we) if param in rf.DUST_PARAMS and avg != AV.min15 else None
    at = created_at or now()
    late_after = timedelta(hours=2) if source == ReadingSource.station else timedelta(minutes=15)
    late = source not in (ReadingSource.derived,) and at - we > late_after
    seq = _next_reading_seq(db, pt.project_id, day)
    code = ec.pcode(db, pt.project_id)
    r = EnvReading(
        id=uuid.uuid4(), reading_no=f"ENR-{code}-{day:%Y%m%d}-{seq:05d}", project_id=pt.project_id,
        day=day, seq=seq, point_id=pt.id, parameter=param, averaging=avg, period=period,
        window_start=ws, window_end=we, source=source, value=value, instrument_id=instrument_id,
        device_pk=device_pk, lab_provider_id=lab_provider_id, lab_report_ref=lab_report_ref,
        field_calibration_checked=field_cal, background=bg is not None, background_ref=bg,
        result=result, limit_value=limit, late_entry=late, recorded_by_user_id=user_id,
        photo_ids=[], warnings=[], status=RecordState.valid, created_at=at, updated_at=at,
        created_by_user_id=user_id, seed_fake=seed,
    )  # fmt: skip
    if pt.kind == PointKind.discharge and avg != AV.min15:
        pm = next((x for x in ec.project_permits(db, pt.project_id) if x.id == pt.permit_id), None)
        if not ec.permit_valid_on(db, pm, day):
            r.warnings = ["PERMIT_NOT_VALID"]
            if process:
                discharge_alert(db, pt, day)
    db.add(r)
    db.flush()
    if process:
        exceedances.on_reading(db, r, pt)
    return r


def discharge_alert(db: Session, pt: EnvPoint, day: date) -> None:
    """WAT-3: once per day to the HSE Officers and the HSE Manager."""
    if ec.once(db, f"env:discharge_permit:{pt.id}:{day.isoformat()}"):
        ec.send(
            db, ec.officers(db, pt.project_id) | ec.managers(db), NK.discharge_permit_invalid,
            f"{pt.point_code}: discharge on {day.isoformat()} without a valid permit.",
            f"{pt.point_code}: تصريف بتاريخ {day.isoformat()} دون تصريح ساري.",
            pt.project_id, ET.env_point, pt.id, email=True,
        )  # fmt: skip


def mean(param: Parameter, vals: list[Decimal]) -> Decimal:
    """§6.2: arithmetic mean; laeq energy mean."""
    if param == Parameter.laeq:
        s = sum(10 ** (float(v) / 10) for v in vals) / len(vals)
        return D(str(round(10 * math.log10(s), 6)))
    return sum(vals, D(0)) / len(vals)


def derive(db: Session, pt: EnvPoint, upto: datetime, lookback_h: int = 50) -> int:
    """MON-2 / §6.2: `1h` values from ≥ data_capture_pct of the 15-min values, `24h` (local day)
    from the derived hours, as soon as the window closes."""
    cap = ec.cfg(db, pt.project_id).dec("data_capture_pct")
    since = upto - timedelta(hours=lookback_h)
    rows = list(
        db.scalars(
            select(EnvReading).where(
                EnvReading.point_id == pt.id,
                EnvReading.status == RecordState.valid,
                EnvReading.averaging.in_([AV.min15, AV.h1, AV.h24]),
                EnvReading.window_start >= since - timedelta(hours=24),
            )
        )
    )
    have = {(r.parameter, r.averaging, r.window_start) for r in rows}
    n = 0
    hours: dict[tuple[Parameter, datetime], list[Decimal]] = {}
    for r in rows:
        if r.averaging == AV.min15 and r.window_start >= since:
            h = r.window_start.replace(minute=0, second=0, microsecond=0)
            hours.setdefault((r.parameter, h), []).append(D(r.value))
    for (param, h), vals in sorted(hours.items(), key=lambda x: x[0][1]):
        if (param, AV.h1, h) in have or h + timedelta(hours=1) > upto:
            continue
        if D(len(vals)) / 4 * 100 >= cap:
            r = make_reading(db, pt, param, AV.h1, h, h + timedelta(hours=1), mean(param, vals),
                             ReadingSource.derived)  # fmt: skip
            rows.append(r)
            have.add((param, AV.h1, h))
            n += 1
    days: dict[tuple[Parameter, date], list[Decimal]] = {}
    for r in rows:
        if r.averaging == AV.h1:
            days.setdefault((r.parameter, reading_day(r.window_end)), []).append(D(r.value))
    for (param, d), vals in days.items():
        s0 = ec.day_start(d)
        s1 = ec.day_start(d + timedelta(days=1))
        if (param, AV.h24, s0) in have or s1 > upto or s0 < since - timedelta(hours=24):
            continue
        if D(len(vals)) / 24 * 100 >= cap:
            make_reading(db, pt, param, AV.h24, s0, s1, mean(param, vals), ReadingSource.derived)
            n += 1
    return n


def reading_read(db: Session, p: Principal | None, r: EnvReading) -> ReadingRead:
    pt = db.get(EnvPoint, r.point_id)
    hide = p is not None and ec.is_viewer(p, r.project_id)
    unit = rf.unit_of(r.parameter)
    return ReadingRead(
        id=r.id, reading_no=r.reading_no, project_id=r.project_id, point_id=r.point_id,
        point_code=pt.point_code if pt else "?", parameter=r.parameter, averaging=r.averaging,
        period=r.period, window_start=r.window_start, window_end=r.window_end, source=r.source,
        value=str(ec.q1(r.value)), display=f"{ec.q1(r.value)} {unit}".strip(),
        instrument_id=r.instrument_id, lab_provider_id=r.lab_provider_id,
        lab_report_ref=r.lab_report_ref, field_calibration_checked=r.field_calibration_checked,
        background=r.background, background_ref=r.background_ref, result=r.result,
        limit_value=ec.s1(r.limit_value), late_entry=r.late_entry, exceedance_id=r.exceedance_id,
        photo_ids=None if hide else list(r.photo_ids or []), status=r.status,
        void_reason=r.void_reason, warnings=ec.warnings_of(r.warnings),
    )  # fmt: skip


def _reading(db: Session, p: Principal, rid: uuid.UUID) -> tuple[EnvReading, EnvPoint]:
    r = db.get(EnvReading, rid)
    if r is None or not p.can_see_project(r.project_id):
        raise not_found("Reading")
    pt = _point(db, p, r.point_id)
    return r, pt


def list_readings(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    point_id: uuid.UUID | None,
    parameter: Parameter | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    size: int,
) -> ReadingPage:
    g = ec.view_grant(db, p, project_id)
    pts = {
        x.id
        for x in db.scalars(select(EnvPoint).where(EnvPoint.project_id == project_id))
        if g.covers_site(x.site_id)
    }
    q = select(EnvReading).where(
        EnvReading.project_id == project_id, EnvReading.point_id.in_(pts or [uuid.uuid4()])
    )
    if point_id:
        q = q.where(EnvReading.point_id == point_id)
    if parameter:
        q = q.where(EnvReading.parameter == parameter)
    if date_from:
        q = q.where(EnvReading.day >= date_from)
    if date_to:
        q = q.where(EnvReading.day <= date_to)
    total = int(db.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = list(
        db.scalars(
            q.order_by(EnvReading.window_end.desc(), EnvReading.reading_no.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    return ReadingPage(
        items=[reading_read(db, p, r) for r in rows], total=total, page=page, page_size=size
    )


def create_reading(
    db: Session, p: Principal, project_id: uuid.UUID, body: ReadingCreate
) -> ReadingRead:
    ec.project(db, p, project_id)
    pt = db.get(EnvPoint, body.point_id)
    if pt is None or pt.project_id != project_id or not pt.active:
        raise validation_error("point_id", "Unknown or inactive monitoring point.")
    ec.require(p, project_id, C.env_reading_record, pt.site_id, check_eng=False)
    if body.averaging == AV.min15 or not any(
        r["parameter"] == body.parameter.value
        and (r["averaging"] == body.averaging.value
             or (body.averaging == AV.measurement and r["averaging"] == "1h"))
        for r in pt.requirements or []
    ):  # fmt: skip
        raise validation_error("parameter", "Not a requirement of this point.")
    t = now()
    if body.window_end <= body.window_start:
        raise validation_error("window_end", "The window end must be after its start.")
    if body.window_end > t + timedelta(minutes=2):
        raise validation_error("window_end", "The window cannot end in the future.")
    _range(body.parameter, body.value, "value")
    ins: EnvInstrument | None = None
    if body.lab_provider_id is not None:
        source = ReadingSource.lab
        _lab(db, body.lab_provider_id, reading_day(body.window_end))
        if not body.lab_report_ref:
            raise validation_error("lab_report_ref", "Give the lab report reference.")
    else:
        source = ReadingSource.manual
        if body.window_end < t - timedelta(hours=72):
            raise ec.code_err(
                ErrorCode.BACKDATED_READING, "Manual readings may be back-dated up to 72 hours.",
                "يمكن إدخال القراءات اليدوية بأثر رجعي حتى 72 ساعة فقط.", "window_end",
            )  # fmt: skip
        if pt.source_kind != PointSource.visual and body.parameter != Parameter.visual_dust:
            iid = body.instrument_id or pt.instrument_id
            ins = db.get(EnvInstrument, iid) if iid else None
            if ins is None or ins.project_id != project_id:
                raise validation_error("instrument_id", "Name the instrument used.")
            _calibrated(ins, body.window_end, "instrument_id")
            if ins.status != IS.active:
                raise validation_error("instrument_id", "The instrument is not active.")
            if body.parameter == Parameter.laeq:
                if body.field_calibration_checked is not True:
                    raise ec.code_err(
                        ErrorCode.FIELD_CALIBRATION_REQUIRED,
                        "Confirm the field calibration check before a noise measurement.",
                        "أكد فحص المعايرة الميدانية قبل قياس الضوضاء.",
                        "field_calibration_checked",
                    )
                if body.window_end - body.window_start < Q15:
                    raise validation_error("window_end", "Noise measurements last ≥ 15 minutes.")
    r = make_reading(
        db, pt, body.parameter, body.averaging, body.window_start, body.window_end, body.value,
        source, instrument_id=ins.id if ins else None, user_id=p.user.id,
        lab_provider_id=body.lab_provider_id, lab_report_ref=body.lab_report_ref,
        field_cal=body.field_calibration_checked,
    )  # fmt: skip
    if body.photos:
        r.photo_ids = ec.store_photos(
            db, AttachmentOwner.env_photo, r.id, project_id, body.photos, p.user.id, "photos"
        )
    db.flush()
    ec.record(db, p, AuditAction.create, ET.env_reading, r, project_id)
    return reading_read(db, p, r)


def _lab(db: Session, provider_id: uuid.UUID, d: date) -> EnvProvider:
    pv = ec.provider_ok(db.get(EnvProvider, provider_id), "lab_provider_id")
    if ProviderKind.environmental_lab.value not in (pv.kinds or []):
        raise validation_error("lab_provider_id", "Name an environmental laboratory.")
    if not any(
        x.permit_type == PermitType.lab_accreditation and ec.in_force(x, d)
        for x in ec.licences(db, pv.id)
    ):
        raise ec.code_err(
            ErrorCode.PROVIDER_LICENCE_INVALID,
            f"{pv.provider_code} has no accreditation in force on {d.isoformat()}.",
            f"لا يوجد اعتماد ساري لدى {pv.provider_code}.", "lab_provider_id",
        )  # fmt: skip
    return pv


def read_reading(db: Session, p: Principal, rid: uuid.UUID) -> ReadingRead:
    return reading_read(db, p, _reading(db, p, rid)[0])


def void_reading(db: Session, p: Principal, rid: uuid.UUID, body: EnvVoid) -> ReadingRead:
    r, _pt = _reading(db, p, rid)
    p.require(r.project_id, C.env_void)
    if r.status == RecordState.voided:
        raise _conflict("The reading is already voided.")
    r.void_reason = ec.reason(body.reason, 20)
    r.status = RecordState.voided
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.env_reading, r, r.project_id)
    return reading_read(db, p, r)


# ---- background declarations (§3.11) -------------------------------------------------------------


def background_read(b: BackgroundDeclaration) -> BackgroundRead:
    return BackgroundRead(
        id=b.id, declaration_no=b.declaration_no, project_id=b.project_id,
        site_ids=list(b.site_ids or []), from_at=b.from_at, to_at=b.to_at, source=b.source,
        source_ref=b.source_ref,
    )  # fmt: skip


def list_backgrounds(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int
) -> BackgroundPage:
    ec.view_grant(db, p, project_id)
    rows = list(
        db.scalars(
            select(BackgroundDeclaration)
            .where(BackgroundDeclaration.project_id == project_id)
            .order_by(BackgroundDeclaration.from_at.desc())
        )
    )
    return ec.paged(BackgroundPage, rows, page, size, background_read)


def create_background(
    db: Session, p: Principal, project_id: uuid.UUID, body: BackgroundCreate
) -> BackgroundRead:
    pr = ec.project(db, p, project_id)
    p.require(project_id, C.env_monitoring_manage)
    for s in body.site_ids:
        ec.site_of(db, project_id, s)
    if body.to_at <= body.from_at or body.to_at - body.from_at > timedelta(hours=72):
        raise validation_error("to_at", "A declaration lasts up to 72 hours.")
    y = ec.local_day(body.from_at).year
    seq = ec.next_seq(db, BackgroundDeclaration, project_id, y)
    b = BackgroundDeclaration(
        id=uuid.uuid4(), declaration_no=f"BGD-{pr.code}-{y}-{seq:03d}", year=y, seq=seq,
        project_id=project_id, site_ids=list(body.site_ids), from_at=body.from_at,
        to_at=body.to_at, source=body.source, source_ref=body.source_ref,
        declared_by_user_id=p.user.id, created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(b)
    db.flush()
    reflag(db, project_id, b)
    ec.record(db, p, AuditAction.create, ET.background_declaration, b, project_id)
    return background_read(b)


def reflag(db: Session, project_id: uuid.UUID, b: BackgroundDeclaration) -> None:
    """EXD-3 for readings already stored: flag dust readings in the window (the reading is never
    altered otherwise, EXD-4) and suggest background_natural on their open exceedances."""
    pts = {
        x.id: x
        for x in db.scalars(select(EnvPoint).where(EnvPoint.project_id == project_id))
        if x.site_id in (b.site_ids or [])
    }
    if not pts:
        return
    for r in db.scalars(
        select(EnvReading).where(
            EnvReading.point_id.in_(list(pts)),
            EnvReading.parameter.in_(list(rf.DUST_PARAMS)),
            EnvReading.averaging != AV.min15,
            EnvReading.window_start < b.to_at,
            EnvReading.window_end > b.from_at,
            EnvReading.background.is_(False),
        )
    ):
        r.background, r.background_ref = True, b.declaration_no
        x = db.get(EnvExceedance, r.exceedance_id) if r.exceedance_id else None
        if x is not None and x.cause is None:
            from app.core.env_enums import ExceedanceCause  # noqa: PLC0415

            x.suggested_cause, x.background_ref = (
                ExceedanceCause.background_natural,
                b.declaration_no,
            )
    db.flush()
