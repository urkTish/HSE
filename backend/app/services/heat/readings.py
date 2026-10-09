"""WBGT readings: manual entry (WB-1…WB-4), weather-station sessions and ingest (HS-4), CSV import
(WB-4) and voids (WB-5). The zone state is derived on read (`state`), so a reading or a void
changes it at once; live readings feed the heat alerts (HA-1, HA-2, HA-5)."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import jwt
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.heat_enums import (
    HeatLogStatus,
    InstrumentStatus,
    PointSourceKind,
    ReadingSource,
    RecordStatus,
)
from app.core.security import decode_jwt, token_digest
from app.models import (
    HeatIllnessEntry,
    HeatInstrument,
    HeatStationDevice,
    MonitoringPoint,
    Project,
    WbgtReading,
)
from app.schemas.heat import (
    ReadingComponents,
    ReadingCreate,
    ReadingImportResult,
    ReadingImportRow,
    ReadingPage,
    ReadingRead,
    StationReadingCreate,
    StationSessionInput,
    StationSessionRead,
    VoidInput,
)
from app.schemas.hse_common import ApiWarning
from app.services.common import paginate
from app.services.heat import common as hc
from app.services.permissions import Principal

C = Capability
D = Decimal
RANGES = {
    "ta_c": (D(0), D(60)),
    "tnwb_c": (D(0), D(45)),
    "tg_c": (D(0), D(90)),
    "rh_pct": (D(0), D(100)),
    "wbgt_entered_c": (D(10), D(45)),
}
LATE = timedelta(minutes=15)


def _out_of_range(name: str) -> ApiError:
    lo, hi = RANGES[name]
    return hc.err(
        422,
        ErrorCode.VALUE_OUT_OF_RANGE,
        f"{name} must be between {lo} and {hi}.",
        "القيمة خارج النطاق المسموح.",
        field=name,
    )


def reading_read(
    db: Session, r: WbgtReading, warnings: list[ApiWarning] | None = None
) -> ReadingRead:
    pt = db.get(MonitoringPoint, r.point_id)
    ins = db.get(HeatInstrument, r.instrument_id)
    return ReadingRead(
        id=r.id,
        reading_no=r.reading_no,
        point_id=r.point_id,
        point_code=pt.point_code if pt else "?",
        measured_at=r.measured_at,
        source=r.source,
        instrument_no=ins.instrument_no if ins else "?",
        ta_c=hc.dstr(r.ta_c),
        tnwb_c=hc.dstr(r.tnwb_c),
        tg_c=hc.dstr(r.tg_c),
        rh_pct=r.rh_pct,
        wbgt_entered_c=hc.dstr(r.wbgt_entered_c),
        wbgt_c=str(hc.q1(D(r.wbgt_c))),
        regime_cells=dict(r.regime_cells or {}),
        late_entry=r.late_entry,
        status=r.status,
        void_reason=r.void_reason,
        recorded_by=hc.user_ref(db, r.recorded_by_user_id),
        created_at=r.created_at,
        warnings=warnings or [],
    )


# ---- the core write ------------------------------------------------------------------------------


@dataclass
class Made:
    reading: WbgtReading
    warnings: list[ApiWarning] = field(default_factory=list)
    duplicate: bool = False


def compute_wbgt(
    c: ReadingComponents, solar: bool, tolerance: Decimal
) -> tuple[D, list[ApiWarning]]:
    """§6.1, WB-2, WB-3."""
    for name, (lo, hi) in RANGES.items():
        v = getattr(c, name)
        if v is not None and not lo <= D(v) <= hi:
            raise _out_of_range(name)
    comp = hc.wbgt(c.tnwb_c, c.tg_c, c.ta_c, solar)
    warns: list[ApiWarning] = []
    if comp is None:
        if c.wbgt_entered_c is None:
            raise hc.err(
                422,
                ErrorCode.WBGT_REQUIRED,
                "Give the WBGT, or the natural wet-bulb and globe temperatures (WB-3).",
                "أدخل مؤشر WBGT أو درجتي الحرارة الرطبة الطبيعية والكرة.",
                field="wbgt_entered_c",
            )
        return hc.q1(D(c.wbgt_entered_c)), warns
    if c.wbgt_entered_c is not None and abs(D(c.wbgt_entered_c) - comp) > tolerance:
        warns.append(
            ApiWarning(
                code=ErrorCode.WBGT_COMPONENT_MISMATCH.value,
                message=f"The entered WBGT differs from the computed {hc.q1(comp)}; the "
                "computed value is used.",
                message_ar="المؤشر المُدخل يختلف عن المحسوب؛ تم اعتماد المحسوب.",
                field="wbgt_entered_c",
            )
        )
    out = hc.q1(comp)
    if not D(10) <= out <= D(45):
        raise _out_of_range("wbgt_entered_c")
    return out, warns


def _check_instrument(x: HeatInstrument | None, project_id: uuid.UUID, at: datetime) -> None:
    if x is None or x.project_id != project_id:
        raise validation_error("instrument_id", "Unknown instrument for this project.")
    if x.calibration_valid_until < hc.local_day(at):
        raise hc.err(
            422,
            ErrorCode.INSTRUMENT_CALIBRATION_EXPIRED,
            f"{x.instrument_no} was not calibrated on the reading date.",
            "الجهاز غير معاير في تاريخ القراءة.",
            field="instrument_id",
        )
    if x.status != InstrumentStatus.active:
        raise hc.err(
            422,
            ErrorCode.INSTRUMENT_NOT_COMPLIANT,
            f"{x.instrument_no} is not active.",
            "الجهاز غير فعال.",
            field="instrument_id",
        )


def _next_no(db: Session, project_id: uuid.UUID, d: Any) -> tuple[int, str]:
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    cur = db.scalar(
        select(func.max(WbgtReading.seq)).where(
            WbgtReading.project_id == project_id, WbgtReading.local_date == d
        )
    )
    seq = int(cur or 0) + 1
    return seq, f"WBG-{hc.pcode(db, project_id)}-{d.strftime('%Y%m%d')}-{seq:04d}"


def make(
    db: Session,
    pt: MonitoringPoint,
    ins: HeatInstrument,
    c: ReadingComponents,
    measured_at: datetime,
    source: ReadingSource,
    user_id: uuid.UUID | None = None,
    device_pk: uuid.UUID | None = None,
    permit_id: uuid.UUID | None = None,
    alert: bool = True,
) -> Made:
    cfg = hc.cfg(db, pt.project_id)
    _check_instrument(ins, pt.project_id, measured_at)
    w, warns = compute_wbgt(c, pt.solar_load, cfg.dec("wbgt_component_tolerance_c"))
    at = now()
    d = hc.local_day(measured_at)
    seq, no = _next_no(db, pt.project_id, d)
    from app.services.heat import state  # noqa: PLC0415

    before = state.point_state(db, pt, measured_at, cfg) if alert else None
    r = WbgtReading(
        id=uuid.uuid4(),
        reading_no=no,
        project_id=pt.project_id,
        local_date=d,
        seq=seq,
        point_id=pt.id,
        permit_id=permit_id,
        measured_at=measured_at,
        source=source,
        instrument_id=ins.id,
        device_pk=device_pk,
        ta_c=c.ta_c,
        tnwb_c=c.tnwb_c,
        tg_c=c.tg_c,
        rh_pct=c.rh_pct,
        wbgt_entered_c=c.wbgt_entered_c,
        wbgt_c=w,
        regime_cells=hc.cells(hc.table(db), cfg.offset, w),
        recorded_by_user_id=user_id,
        late_entry=source == ReadingSource.import_ or measured_at < at - LATE,
        status=RecordStatus.valid,
        created_at=at,
    )
    db.add(r)
    db.flush()
    if alert and before is not None and not r.late_entry:
        from app.services.heat import alerts  # noqa: PLC0415

        alerts.on_reading(db, pt, before, measured_at)
    return Made(r, warns)


# ---- manual --------------------------------------------------------------------------------------


def _point_for(db: Session, project_id: uuid.UUID, body: ReadingCreate) -> MonitoringPoint:
    pt: MonitoringPoint | None = None
    if body.point_id is not None:
        pt = db.get(MonitoringPoint, body.point_id)
    elif body.zone_id is not None:
        pt = hc.covering(db, project_id).get(body.zone_id)
        if pt is None:
            raise validation_error(
                "zone_id", "The zone has no monitoring point; ask the HSE Officer to add one."
            )
    if pt is None or pt.project_id != project_id:
        raise validation_error("point_id", "Unknown monitoring point.")
    if not pt.active:
        raise validation_error("point_id", "The monitoring point is not active.")
    return pt


def create_manual(
    db: Session, p: Principal, project_id: uuid.UUID, body: ReadingCreate
) -> ReadingRead:
    hc.project(db, p, project_id)
    g = p.require(project_id, C.heat_reading_record)
    pt = _point_for(db, project_id, body)
    if not hc.site_in_scope(db, g, project_id, pt.site_id):
        raise not_found("Monitoring point")
    cfg = hc.cfg(db, project_id)
    at = now()
    if body.measured_at > at + timedelta(minutes=2):
        raise validation_error("measured_at", "The reading time cannot be in the future.")
    if body.measured_at < at - timedelta(hours=int(cfg["reading_backdate_max_hours"])):
        raise hc.err(
            422,
            ErrorCode.BACKDATED_READING,
            f"Manual readings may be back-dated up to {cfg['reading_backdate_max_hours']} h.",
            "لا يمكن إدخال قراءة يدوية أقدم من الحد المسموح.",
            field="measured_at",
        )
    ins = db.get(HeatInstrument, body.instrument_id)
    m = make(
        db,
        pt,
        ins,  # type: ignore[arg-type]
        body,
        body.measured_at,
        ReadingSource.manual,
        user_id=p.user.id,
        permit_id=body.permit_id,
    )
    hc.record(db, p, AuditAction.create, EntityType.wbgt_reading, m.reading, project_id)
    return reading_read(db, m.reading, m.warnings)


def list_readings(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    point_id: uuid.UUID | None,
    from_at: datetime | None,
    to_at: datetime | None,
    status: RecordStatus | None,
) -> ReadingPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = select(WbgtReading).where(WbgtReading.project_id == project_id)
    if point_id:
        stmt = stmt.where(WbgtReading.point_id == point_id)
    if from_at:
        stmt = stmt.where(WbgtReading.measured_at >= from_at)
    if to_at:
        stmt = stmt.where(WbgtReading.measured_at <= to_at)
    if status:
        stmt = stmt.where(WbgtReading.status == status)
    stmt = stmt.order_by(WbgtReading.measured_at.desc(), WbgtReading.reading_no.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return ReadingPage(
        items=[reading_read(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


def void(db: Session, p: Principal, reading_id: uuid.UUID, body: VoidInput) -> ReadingRead:
    r = db.get(WbgtReading, reading_id)
    if r is None or not p.can_see_project(r.project_id):
        raise not_found("WBGT reading")
    p.require(r.project_id, C.heat_void)
    why = hc.reason(body.reason, 20)
    if r.status != RecordStatus.valid:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("WBGT reading", r.status, RecordStatus.voided)
    before = {"status": r.status.value}
    r.status, r.void_reason = RecordStatus.voided, why
    r.voided_at, r.voided_by_user_id = now(), p.user.id
    db.flush()
    hc.record(db, p, AuditAction.status_change, EntityType.wbgt_reading, r, r.project_id, before)
    # HI-3: a context that used the reading is flagged, not recomputed
    for e in db.scalars(
        select(HeatIllnessEntry).where(
            HeatIllnessEntry.project_id == r.project_id,
            HeatIllnessEntry.status != HeatLogStatus.voided,
        )
    ):
        if (e.context or {}).get("reading_no") == r.reading_no:
            e.context = {**e.context, "reading_voided": True}
    db.flush()
    return reading_read(db, r)


# ---- weather station -----------------------------------------------------------------------------


def _unauth() -> ApiError:
    return ApiError(
        401,
        ErrorCode.GATE_DEVICE_REVOKED,
        "This weather-station device is not registered or was revoked.",
        "جهاز محطة الطقس غير مسجل أو تم إلغاؤه.",
    )


def _station_point(db: Session, d: HeatStationDevice) -> MonitoringPoint | None:
    return db.scalar(
        select(MonitoringPoint).where(
            MonitoringPoint.instrument_id == d.instrument_id,
            MonitoringPoint.source_kind == PointSourceKind.station,
            MonitoringPoint.active.is_(True),
        )
    )


def station_session(db: Session, body: StationSessionInput) -> StationSessionRead:
    d = db.scalar(
        select(HeatStationDevice).where(
            HeatStationDevice.token_hash == token_digest(body.device_token)
        )
    )
    if d is None or d.revoked_at is not None:
        raise _unauth()
    ins = db.get(HeatInstrument, d.instrument_id)
    if ins is None:
        raise _unauth()
    at = now()
    d.last_seen_at = at
    s = get_settings()
    token = jwt.encode(
        {
            "sub": str(d.id),
            "sid": str(uuid.uuid4()),
            "typ": "gate",
            "kind": "weather_station",
            "exp": at + timedelta(days=30),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    pt = _station_point(db, d)
    db.flush()
    return StationSessionRead(
        access_token=token,
        instrument_no=ins.instrument_no,
        point_code=pt.point_code if pt else None,
    )


def ingest(db: Session, token: str | None, body: StationReadingCreate) -> ReadingRead:
    claims = decode_jwt(token) if token else None
    if not claims or claims.get("kind") != "weather_station":
        raise _unauth()
    try:
        dpk = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise _unauth() from exc
    d = db.get(HeatStationDevice, dpk)
    if d is None or d.revoked_at is not None:
        raise _unauth()
    pt = _station_point(db, d)
    if pt is None:
        raise validation_error("measured_at", "The station is not linked to an active point.")
    if body.measured_at > now() + timedelta(minutes=2):
        raise validation_error("measured_at", "The reading time cannot be in the future.")
    d.last_seen_at = now()
    old = db.scalar(
        select(WbgtReading).where(
            WbgtReading.device_pk == d.id, WbgtReading.measured_at == body.measured_at
        )
    )
    if old is not None:
        return reading_read(db, old)  # WB-1 idempotent
    ins = db.get(HeatInstrument, d.instrument_id)
    m = make(db, pt, ins, body, body.measured_at, ReadingSource.station, device_pk=d.id)  # type: ignore[arg-type]
    return reading_read(db, m.reading, m.warnings)


# ---- import (WB-4) -------------------------------------------------------------------------------

COLS = ("point_code", "measured_at", "instrument_no", "ta_c", "tnwb_c", "tg_c", "rh_pct", "wbgt_c")


def _dec(v: str | None) -> Decimal | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return D(v)
    except InvalidOperation as exc:
        raise ValueError(v) from exc


def import_csv(
    db: Session, p: Principal, project_id: uuid.UUID, file: UploadFile, dry_run: bool
) -> ReadingImportResult:
    hc.project(db, p, project_id)
    p.require(project_id, C.heat_register_manage)
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise validation_error("file", "The file is larger than 5 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise validation_error("file", "Use a UTF-8 .csv file.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or any(c not in reader.fieldnames for c in COLS[:3]):
        raise validation_error("file", "Use the wbgt_readings template: " + ", ".join(COLS))
    pts = {x.point_code: x for x in hc.points(db, project_id)}
    ins = {
        x.instrument_no: x
        for x in db.scalars(select(HeatInstrument).where(HeatInstrument.project_id == project_id))
    }
    rows: list[ReadingImportRow] = []
    created = 0
    for i, row in enumerate(reader, start=2):
        try:
            pt = pts.get((row.get("point_code") or "").strip())
            if pt is None:
                raise validation_error("point_code", "Unknown point.")
            at = datetime.fromisoformat((row.get("measured_at") or "").strip())
            if at.tzinfo is None:
                raise validation_error("measured_at", "Give the time with its UTC offset.")
            if at > now():
                raise validation_error("measured_at", "The reading time cannot be in the future.")
            x = ins.get((row.get("instrument_no") or "").strip())
            comps = ReadingComponents(
                ta_c=_dec(row.get("ta_c")),
                tnwb_c=_dec(row.get("tnwb_c")),
                tg_c=_dec(row.get("tg_c")),
                rh_pct=int(row["rh_pct"]) if (row.get("rh_pct") or "").strip() else None,
                wbgt_entered_c=_dec(row.get("wbgt_c")),
            )
            _check_instrument(x, project_id, at)
            cfg = hc.cfg(db, project_id)
            compute_wbgt(comps, pt.solar_load, cfg.dec("wbgt_component_tolerance_c"))
            if not dry_run:
                assert x is not None  # noqa: S101
                make(db, pt, x, comps, at, ReadingSource.import_, user_id=p.user.id, alert=False)
                created += 1
            rows.append(ReadingImportRow(row=i, ok=True))
        except ApiError as e:
            rows.append(ReadingImportRow(row=i, ok=False, code=e.code.value, message=e.message))
        except (ValueError, KeyError) as e:
            rows.append(ReadingImportRow(row=i, ok=False, code="VALIDATION_ERROR", message=str(e)))
    if created:
        hc.audit_change(
            db, p, EntityType.wbgt_reading, None, project_id, None, {"imported": created}
        )
    return ReadingImportResult(
        dry_run=dry_run,
        rows_total=len(rows),
        rows_ok=sum(1 for r in rows if r.ok),
        created=created,
        rows=rows,
    )
