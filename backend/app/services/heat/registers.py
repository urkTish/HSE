"""Heat instruments and weather-station devices (§3.1, §4.1, HS-2, HS-4), monitoring points
(§3.2, HS-3) and rest stations (§3.7, RS-1)."""

from __future__ import annotations

import secrets
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.heat_enums import InstrumentAction, InstrumentKind, InstrumentStatus, PointSourceKind
from app.core.security import token_digest
from app.models import (
    HeatInstrument,
    HeatStationDevice,
    MonitoringPoint,
    RestStation,
    Site,
    Zone,
)
from app.schemas.heat import (
    InstrumentCreate,
    InstrumentPage,
    InstrumentRead,
    InstrumentTransition,
    PointCreate,
    PointPage,
    PointRead,
    PointUpdate,
    RestStationCreate,
    RestStationPage,
    RestStationRead,
    RestStationUpdate,
    StationDeviceCreate,
    StationDeviceRead,
    StationDeviceRegistered,
)
from app.services.common import duplicate, invalid_transition, paginate
from app.services.heat import common as hc
from app.services.permissions import Principal

C = Capability
IS = InstrumentStatus


def _calibration_expired() -> Any:
    return hc.err(
        422,
        ErrorCode.INSTRUMENT_CALIBRATION_EXPIRED,
        "The instrument calibration has expired.",
        "انتهت صلاحية معايرة الجهاز.",
        field="calibration_valid_until",
    )


# ---- instruments ---------------------------------------------------------------------------------


def device_read(d: HeatStationDevice) -> StationDeviceRead:
    return StationDeviceRead(
        id=d.id,
        device_id=d.device_id,
        label=d.label,
        registered_at=d.registered_at,
        last_seen_at=d.last_seen_at,
        revoked_at=d.revoked_at,
    )


def instrument_read(db: Session, x: HeatInstrument) -> InstrumentRead:
    devs = db.scalars(
        select(HeatStationDevice)
        .where(HeatStationDevice.instrument_id == x.id)
        .order_by(HeatStationDevice.registered_at)
    )
    pts = db.scalars(
        select(MonitoringPoint.point_code)
        .where(MonitoringPoint.instrument_id == x.id)
        .order_by(MonitoringPoint.point_code)
    )
    return InstrumentRead(
        id=x.id,
        instrument_no=x.instrument_no,
        project_id=x.project_id,
        kind=x.kind,
        make_model=x.make_model,
        serial_no=x.serial_no,
        iso7243_compliant=x.iso7243_compliant,
        calibration_valid_until=x.calibration_valid_until,
        calibration_cert_ref=x.calibration_cert_ref,
        status=x.status,
        status_reason=x.status_reason,
        devices=[device_read(d) for d in devs],
        point_codes=list(pts),
    )


def list_instruments(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, page_size: int
) -> InstrumentPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = (
        select(HeatInstrument)
        .where(HeatInstrument.project_id == project_id)
        .order_by(HeatInstrument.instrument_no)
    )
    rows, total = paginate(db, stmt, page, page_size)
    return InstrumentPage(
        items=[instrument_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def _check_activation(compliant: bool, valid_until: date) -> None:
    if not compliant:
        raise hc.err(
            422,
            ErrorCode.INSTRUMENT_NOT_COMPLIANT,
            "The instrument must meet ISO 7243 to be activated (HS-2).",
            "يجب أن يكون الجهاز مطابقاً لـ ISO 7243.",
            field="iso7243_compliant",
        )
    if valid_until <= hc.local_day():
        raise _calibration_expired()


def create_instrument(
    db: Session, p: Principal, project_id: uuid.UUID, body: InstrumentCreate
) -> InstrumentRead:
    pr = hc.project(db, p, project_id)
    p.require(project_id, C.heat_register_manage)
    _check_activation(body.iso7243_compliant, body.calibration_valid_until)
    if db.scalar(
        select(HeatInstrument.id).where(
            HeatInstrument.project_id == project_id, HeatInstrument.serial_no == body.serial_no
        )
    ):
        raise duplicate("serial_no", "This serial number is already registered on the project.")
    seq = (
        int(
            db.scalar(
                select(func.max(HeatInstrument.seq)).where(HeatInstrument.project_id == project_id)
            )
            or 0
        )
        + 1
    )
    x = HeatInstrument(
        id=uuid.uuid4(),
        instrument_no=f"HSM-{pr.code}-{seq:02d}",
        project_id=project_id,
        seq=seq,
        status=IS.active,
        created_by_user_id=p.user.id,
        **body.model_dump(),
    )
    db.add(x)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.heat_instrument, x, project_id)
    return instrument_read(db, x)


def _instrument(db: Session, p: Principal, instrument_id: uuid.UUID) -> HeatInstrument:
    x = db.get(HeatInstrument, instrument_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Heat instrument")
    if p.grant(x.project_id, C.heat_view) is None:
        raise not_found("Heat instrument")
    return x


def read_instrument(db: Session, p: Principal, instrument_id: uuid.UUID) -> InstrumentRead:
    return instrument_read(db, _instrument(db, p, instrument_id))


def transition_instrument(
    db: Session, p: Principal, instrument_id: uuid.UUID, body: InstrumentTransition
) -> InstrumentRead:
    x = _instrument(db, p, instrument_id)
    p.require(x.project_id, C.heat_register_manage)
    before = {"status": x.status.value}
    if x.status == IS.retired:
        raise invalid_transition("Heat instrument", x.status, body.action)
    if body.action == InstrumentAction.activate:
        if x.status != IS.quarantined:
            raise invalid_transition("Heat instrument", x.status, IS.active)
        if body.calibration_valid_until is None or not body.calibration_cert_ref:
            raise validation_error(
                "calibration_valid_until", "Give the new calibration date and certificate."
            )
        _check_activation(x.iso7243_compliant, body.calibration_valid_until)
        x.calibration_valid_until = body.calibration_valid_until
        x.calibration_cert_ref = body.calibration_cert_ref
        x.status, x.status_reason = IS.active, None
    elif body.action == InstrumentAction.quarantine:
        if x.status != IS.active:
            raise invalid_transition("Heat instrument", x.status, IS.quarantined)
        x.status, x.status_reason = IS.quarantined, hc.reason(body.reason, 10)
    else:
        x.status, x.status_reason = IS.retired, body.reason
    x.updated_by_user_id = p.user.id
    db.flush()
    hc.record(db, p, AuditAction.status_change, EntityType.heat_instrument, x, x.project_id, before)
    return instrument_read(db, x)


def quarantine_expired(db: Session, d: date) -> int:
    """HS-2 / §4.1: the daily job quarantines instruments whose calibration ended before d."""
    n = 0
    for x in db.scalars(
        select(HeatInstrument).where(
            HeatInstrument.status == IS.active, HeatInstrument.calibration_valid_until < d
        )
    ):
        before = {"status": x.status.value}
        x.status, x.status_reason = IS.quarantined, "calibration_expired"
        hc.record(
            db, None, AuditAction.status_change, EntityType.heat_instrument, x, x.project_id, before
        )
        n += 1
    db.flush()
    return n


def register_device(
    db: Session, p: Principal, instrument_id: uuid.UUID, body: StationDeviceCreate
) -> StationDeviceRegistered:
    x = _instrument(db, p, instrument_id)
    p.require(x.project_id, C.heat_register_manage)
    if x.kind != InstrumentKind.fixed_station or x.status != IS.active:
        raise validation_error("device_id", "Only an active fixed station takes a device (HS-4).")
    token = secrets.token_urlsafe(32)
    d = HeatStationDevice(
        id=uuid.uuid4(),
        project_id=x.project_id,
        instrument_id=x.id,
        device_id=body.device_id,
        label=body.label,
        token_hash=token_digest(token),
        registered_at=now(),
        registered_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    hc.audit_change(
        db, p, EntityType.heat_instrument, x.id, x.project_id, None, {"device": body.device_id}
    )
    return StationDeviceRegistered(device=device_read(d), device_token=token)


def revoke_device(
    db: Session, p: Principal, instrument_id: uuid.UUID, device_pk: uuid.UUID
) -> StationDeviceRead:
    x = _instrument(db, p, instrument_id)
    p.require(x.project_id, C.heat_register_manage)
    d = db.get(HeatStationDevice, device_pk)
    if d is None or d.instrument_id != x.id:
        raise not_found("Station device")
    if d.revoked_at is not None:
        raise invalid_transition("Station device", "registered", "revoked")
    d.revoked_at = now()
    db.flush()
    hc.audit_change(
        db,
        p,
        EntityType.heat_instrument,
        x.id,
        x.project_id,
        {"device": d.device_id},
        {"device": d.device_id, "revoked": True},
    )
    return device_read(d)


# ---- monitoring points ---------------------------------------------------------------------------


def _codes(db: Session, ids: list[uuid.UUID]) -> list[str]:
    zs = {z.id: z.code for z in db.scalars(select(Zone).where(Zone.id.in_(ids)))} if ids else {}
    return [zs.get(i, "?") for i in ids]


def point_read(db: Session, pt: MonitoringPoint) -> PointRead:
    ins = db.get(HeatInstrument, pt.instrument_id) if pt.instrument_id else None
    return PointRead(
        id=pt.id,
        point_code=pt.point_code,
        project_id=pt.project_id,
        site_id=pt.site_id,
        zone_ids=list(pt.zone_ids or []),
        zone_codes=_codes(db, list(pt.zone_ids or [])),
        source_kind=pt.source_kind,
        instrument_id=pt.instrument_id,
        instrument_no=ins.instrument_no if ins else None,
        solar_load=pt.solar_load,
        active=pt.active,
    )


def list_points(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, page_size: int
) -> PointPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = (
        select(MonitoringPoint)
        .where(MonitoringPoint.project_id == project_id)
        .order_by(MonitoringPoint.point_code)
    )
    rows, total = paginate(db, stmt, page, page_size)
    return PointPage(
        items=[point_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def _site_zones(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, zone_ids: list[uuid.UUID]
) -> Site:
    site = db.get(Site, site_id)
    if site is None or site.project_id != project_id:
        raise validation_error("site_id", "The site does not belong to this project.")
    for z in zone_ids:
        zone = db.get(Zone, z)
        if zone is None or zone.site_id != site_id:
            raise validation_error("zone_ids", "Every zone must belong to the site.")
    return site


def _check_cover(
    db: Session, project_id: uuid.UUID, zone_ids: list[uuid.UUID], own: uuid.UUID | None
) -> None:
    cov = hc.covering(db, project_id)
    taken = [z for z in zone_ids if z in cov and cov[z].id != own]
    if taken:
        codes = _codes(db, taken)
        raise hc.err(
            422,
            ErrorCode.ZONE_ALREADY_COVERED,
            "A zone is already covered by another active point: " + ", ".join(codes),
            "المنطقة مغطاة بنقطة قياس أخرى: " + "، ".join(codes),
            field="zone_ids",
            zones=codes,
        )


def _check_station(db: Session, project_id: uuid.UUID, instrument_id: uuid.UUID | None) -> None:
    x = db.get(HeatInstrument, instrument_id) if instrument_id else None
    if (
        x is None
        or x.project_id != project_id
        or x.kind != InstrumentKind.fixed_station
        or x.status != IS.active
    ):
        raise validation_error("instrument_id", "A station point needs an active fixed station.")


def create_point(db: Session, p: Principal, project_id: uuid.UUID, body: PointCreate) -> PointRead:
    hc.project(db, p, project_id)
    p.require(project_id, C.heat_register_manage)
    _site_zones(db, project_id, body.site_id, body.zone_ids)
    if db.scalar(
        select(MonitoringPoint.id).where(
            MonitoringPoint.project_id == project_id,
            MonitoringPoint.point_code == body.point_code,
        )
    ):
        raise duplicate("point_code", "This point code is already used on the project.")
    _check_cover(db, project_id, body.zone_ids, None)
    if body.source_kind == PointSourceKind.station:
        _check_station(db, project_id, body.instrument_id)
    pt = MonitoringPoint(
        id=uuid.uuid4(),
        project_id=project_id,
        point_code=body.point_code,
        site_id=body.site_id,
        zone_ids=list(body.zone_ids),
        source_kind=body.source_kind,
        instrument_id=body.instrument_id if body.source_kind == PointSourceKind.station else None,
        solar_load=body.solar_load,
        active=True,
        created_by_user_id=p.user.id,
    )
    db.add(pt)
    db.flush()
    hc.clear_cache(db)
    hc.record(db, p, AuditAction.create, EntityType.monitoring_point, pt, project_id)
    return point_read(db, pt)


def update_point(db: Session, p: Principal, point_id: uuid.UUID, body: PointUpdate) -> PointRead:
    pt = db.get(MonitoringPoint, point_id)
    if pt is None or not p.can_see_project(pt.project_id):
        raise not_found("Monitoring point")
    p.require(pt.project_id, C.heat_register_manage)
    data = body.model_dump(exclude_unset=True)
    before = {"zone_ids": [str(z) for z in pt.zone_ids or []], "active": pt.active}
    zones = data.get("zone_ids", pt.zone_ids)
    active = data.get("active", pt.active)
    if "zone_ids" in data:
        _site_zones(db, pt.project_id, pt.site_id, zones)
    if active:
        _check_cover(db, pt.project_id, list(zones), pt.id)
    if "instrument_id" in data and pt.source_kind == PointSourceKind.station:
        _check_station(db, pt.project_id, data["instrument_id"])
    for k, v in data.items():
        setattr(pt, k, list(v) if k == "zone_ids" else v)
    pt.updated_by_user_id = p.user.id
    db.flush()
    hc.clear_cache(db)
    hc.record(db, p, AuditAction.update, EntityType.monitoring_point, pt, pt.project_id, before)
    return point_read(db, pt)


# ---- rest stations -------------------------------------------------------------------------------


def station_read(db: Session, s: RestStation) -> RestStationRead:
    return RestStationRead(
        id=s.id,
        station_code=s.station_code,
        project_id=s.project_id,
        site_id=s.site_id,
        zone_ids=list(s.zone_ids or []),
        zone_codes=_codes(db, list(s.zone_ids or [])),
        station_type=s.station_type,
        capacity_persons=s.capacity_persons,
        cooling=s.cooling,
        active=s.active,
    )


def list_stations(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, page_size: int
) -> RestStationPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = (
        select(RestStation)
        .where(RestStation.project_id == project_id)
        .order_by(RestStation.station_code)
    )
    rows, total = paginate(db, stmt, page, page_size)
    return RestStationPage(
        items=[station_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def create_station(
    db: Session, p: Principal, project_id: uuid.UUID, body: RestStationCreate
) -> RestStationRead:
    hc.project(db, p, project_id)
    p.require(project_id, C.heat_register_manage)
    _site_zones(db, project_id, body.site_id, body.zone_ids)
    if db.scalar(
        select(RestStation.id).where(
            RestStation.project_id == project_id, RestStation.station_code == body.station_code
        )
    ):
        raise duplicate("station_code", "This station code is already used on the project.")
    s = RestStation(
        id=uuid.uuid4(),
        project_id=project_id,
        active=True,
        created_by_user_id=p.user.id,
        **{**body.model_dump(), "zone_ids": list(body.zone_ids)},
    )
    db.add(s)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.rest_station, s, project_id)
    return station_read(db, s)


def update_station(
    db: Session, p: Principal, station_id: uuid.UUID, body: RestStationUpdate
) -> RestStationRead:
    s = db.get(RestStation, station_id)
    if s is None or not p.can_see_project(s.project_id):
        raise not_found("Rest station")
    p.require(s.project_id, C.heat_register_manage)
    data = body.model_dump(exclude_unset=True)
    if "zone_ids" in data:
        _site_zones(db, s.project_id, s.site_id, data["zone_ids"])
    before = {"active": s.active, "capacity_persons": s.capacity_persons}
    for k, v in data.items():
        setattr(s, k, list(v) if k == "zone_ids" else v)
    s.updated_by_user_id = p.user.id
    db.flush()
    hc.record(db, p, AuditAction.update, EntityType.rest_station, s, s.project_id, before)
    return station_read(db, s)
