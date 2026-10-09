"""Waste streams, storage areas and consignments (spec 6e-environmental §3.4–§3.6, §4.3,
WST-1…WST-5, CON-1…CON-9, AIR-2, AIR-3, §6.3)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import ValidityStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.env_enums import (
    AreaStatus,
    ConsignmentAction,
    ConsignmentStatus,
    PermitType,
    ProviderKind,
    QuantityUnit,
    WasteClass,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner, CaSourceType
from app.models import (
    Attachment,
    Avp,
    ChecklistResponse,
    EnvProvider,
    FieldFinding,
    Vehicle,
    WasteConsignment,
    WasteStorageArea,
    WasteStream,
    Zone,
)
from app.schemas.env import (
    Accumulation,
    AreaCreate,
    AreaPage,
    AreaRead,
    AreaUpdate,
    ConsignmentCreate,
    ConsignmentPage,
    ConsignmentRead,
    ConsignmentTransition,
    ConsignmentUpdate,
    HazDeadline,
    InspectionAnswerRow,
    ReceiptInput,
    StreamList,
    StreamRead,
    StreamUpsert,
)
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal, forbidden_error

C = Capability
ET = EntityType
NK = NotificationKind
CS = ConsignmentStatus
D = Decimal


# ---- streams (§3.4, WST-1) -----------------------------------------------------------------------


def stream_rows(db: Session, project_id: uuid.UUID) -> dict[str, WasteStream]:
    return {
        s.stream_code: s
        for s in db.scalars(select(WasteStream).where(WasteStream.project_id == project_id))
    }


def density_of(db: Session, project_id: uuid.UUID, code: str) -> Decimal:
    row = stream_rows(db, project_id).get(code)
    return D(row.density) if row else rf.WS[code][4]


def _stream_read(code: str, row: WasteStream | None) -> StreamRead:
    en, ar, wc, route, dens, wild = rf.WS[code]
    unit = "m3 only" if wc == WasteClass.liquid_sewage else (
        "kg/L" if code in rf.LIQUID_KG_L else "t/m3"
    )  # fmt: skip
    return StreamRead(
        stream_code=code, label_en=en, label_ar=ar, waste_class=wc,
        default_route=row.default_route if row else route,
        density=str(D(row.density if row else dens).quantize(D("0.01"))), density_unit=unit,
        wildlife_attractant=wild, excluded_from_tonnage=wc == WasteClass.liquid_sewage,
        active=bool(row and row.active),
    )  # fmt: skip


def list_streams(db: Session, p: Principal, project_id: uuid.UUID) -> StreamList:
    ec.view_grant(db, p, project_id)
    rows = stream_rows(db, project_id)
    return StreamList(items=[_stream_read(c, rows.get(c)) for c in rf.WS])


def upsert_stream(
    db: Session, p: Principal, project_id: uuid.UUID, code: str, body: StreamUpsert
) -> StreamRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.waste_area_manage)
    if code not in rf.WS:
        raise not_found("Waste stream")
    row = stream_rows(db, project_id).get(code)
    if row is None:
        row = WasteStream(
            id=uuid.uuid4(), project_id=project_id, stream_code=code,
            default_route=rf.WS[code][3], density=rf.WS[code][4], created_by_user_id=p.user.id,
        )  # fmt: skip
        db.add(row)
        action = AuditAction.create
    else:
        action = AuditAction.update
    if body.default_route is not None:
        row.default_route = body.default_route
    if body.density is not None:
        row.density = body.density
    row.active = body.active
    row.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, action, ET.waste_stream, row, project_id)
    return _stream_read(code, row)


# ---- storage areas (§3.5, WST-2…WST-5, AIR-2) ----------------------------------------------------


def _zone_code(db: Session, zone_id: uuid.UUID | None) -> str | None:
    z = db.get(Zone, zone_id) if zone_id else None
    return z.code if z else None


def haz_deadlines(db: Session, a: WasteStorageArea, today: date | None = None) -> list[HazDeadline]:
    """§6.6."""
    d0 = today or ec.local_day()
    days = int(ec.cfg(db, a.project_id)["haz_storage_max_days"])
    out = []
    for x in a.accumulation or []:
        if not x.get("started_on"):
            continue
        st = date.fromisoformat(x["started_on"])
        dl = st + timedelta(days=days)
        out.append(
            HazDeadline(
                stream_code=x["stream_code"], started_on=st, deadline=dl,
                days_left=(dl - d0).days, overdue=d0 > dl,
            )
        )  # fmt: skip
    return out


def _answers(db: Session, a: WasteStorageArea) -> list[InspectionAnswerRow]:
    """WST-4: the last 6d WSA / ENV answers in the area's zone (non-compliant first)."""
    q = select(ChecklistResponse).where(
        ChecklistResponse.project_id == a.project_id,
        ChecklistResponse.template_code.in_(("WSA", "ENV")),
        ChecklistResponse.submitted.is_(True),
        ChecklistResponse.voided.is_(False),
    )
    q = (
        q.where(ChecklistResponse.zone_id == a.zone_id)
        if a.zone_id
        else q.where(ChecklistResponse.site_id == a.site_id)
    )
    rs = list(db.scalars(q.order_by(ChecklistResponse.completed_at.desc()).limit(3)))
    cas = {
        (f.response_id, f.item_code): f.ca_id
        for f in db.scalars(
            select(FieldFinding).where(
                FieldFinding.response_id.in_([r.id for r in rs]), FieldFinding.voided.is_(False)
            )
        )
    }
    rows = [
        InspectionAnswerRow(
            inspection_id=r.inspection_id, template_code=r.template_code, item_code=x["item_code"],
            compliant=x.get("compliant") is not False, completed_date=r.completed_date,
            ca_id=cas.get((r.id, x["item_code"])),
        )
        for r in rs
        for x in r.answers or []
        if x.get("applicable")
    ]  # fmt: skip
    rows.sort(key=lambda r: (r.compliant, -(r.completed_date or date.min).toordinal()))
    return rows[:30]


def area_read(db: Session, a: WasteStorageArea, detail: bool = False) -> AreaRead:
    last: list[str] = []
    answers: list[InspectionAnswerRow] = []
    if detail:
        answers = _answers(db, a)
        last = list(
            db.scalars(
                select(WasteConsignment.consignment_no)
                .where(WasteConsignment.storage_area_id == a.id)
                .order_by(WasteConsignment.dispatched_at.desc())
                .limit(5)
            )
        )
    return AreaRead(
        id=a.id, project_id=a.project_id, area_code=a.area_code, site_id=a.site_id,
        zone_id=a.zone_id, zone_code=_zone_code(db, a.zone_id), type=a.type,
        accepted_streams=list(a.accepted_streams or []), capacity_m3=str(ec.q1(a.capacity_m3)),
        secondary_containment_pct=a.secondary_containment_pct, covered=a.covered,
        lidded_secured=a.lidded_secured, signage_bilingual=a.signage_bilingual,
        accumulation=[
            Accumulation(stream_code=x["stream_code"],
                         started_on=date.fromisoformat(x["started_on"]) if x.get("started_on")
                         else None)
            for x in a.accumulation or []
        ],
        haz_deadlines=haz_deadlines(db, a), status=a.status, inspection_answers=answers,
        last_consignments=last,
    )  # fmt: skip


def _check_area(db: Session, a: WasteStorageArea) -> None:
    """WST-2, AIR-2."""
    c = ec.cfg(db, a.project_id)
    for s in a.accepted_streams or []:
        if s not in rf.WS:
            raise validation_error("accepted_streams", f"Unknown stream {s}.")
        if rf.stream_class(s) == WasteClass.hazardous and a.type not in rf.HAZ_STORES:
            raise ec.code_err(
                ErrorCode.STREAM_NOT_ACCEPTED,
                f"Hazardous stream {s} only in a hazardous or liquid store.",
                f"النفايات الخطرة {s} تُخزن فقط في مخزن نفايات خطرة أو مخزن سوائل.",
                "accepted_streams",
            )
    if a.type in rf.HAZ_STORES and (a.secondary_containment_pct or 0) < int(
        c["containment_min_pct"]
    ):
        raise ec.code_err(
            ErrorCode.CONTAINMENT_INSUFFICIENT,
            f"Secondary containment must be at least {c['containment_min_pct']} %.",
            f"يجب ألا يقل الاحتواء الثانوي عن {c['containment_min_pct']} %.",
            "secondary_containment_pct",
        )
    z = db.get(Zone, a.zone_id) if a.zone_id else None
    msg = (
        "Airside storage must be a lidded, secured sealed bin station or hazardous / liquid store.",
        "يجب أن تكون منطقة التخزين في الجانب الجوي محكمة الإغلاق ومن النوع المسموح.",
    )
    if ec.is_airside(z) and (a.type not in rf.AIRSIDE_OK or not a.lidded_secured):
        raise ec.code_err(ErrorCode.AIRSIDE_STORAGE_NOT_SECURED, *msg, "type")
    wild = any(rf.WS[s][5] for s in a.accepted_streams or [])
    if (
        wild
        and ec.is_airport(db, a.project_id)
        and (a.type not in rf.ATTRACTANT_OK or not a.lidded_secured)
    ):
        raise ec.code_err(
            ErrorCode.AIRSIDE_STORAGE_NOT_SECURED,
            "Wildlife-attracting waste only in a lidded sealed bin station or compactor.",
            "نفايات جاذبة للحياة البرية تُخزن فقط في محطة حاويات محكمة أو كابسة مغلقة.",
            "accepted_streams",
        )
    for x in a.accumulation or []:
        if x["stream_code"] not in (a.accepted_streams or []):
            raise validation_error("accumulation", "Accumulation is for accepted streams only.")


def _acc(items: list[Accumulation] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for x in items:
        d = x if isinstance(x, dict) else x.model_dump()
        st = d.get("started_on")
        out.append({"stream_code": d["stream_code"],
                    "started_on": st.isoformat() if isinstance(st, date) else st})  # fmt: skip
    return out


def _area(db: Session, p: Principal, area_id: uuid.UUID) -> WasteStorageArea:
    a = db.get(WasteStorageArea, area_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Storage area")
    g = ec.need(p, a.project_id, C.env_view, write=False)
    if not g.covers_site(a.site_id):
        raise not_found("Storage area")
    return a


def list_areas(
    db: Session, p: Principal, project_id: uuid.UUID, site_id: uuid.UUID | None, page: int,
    size: int,
) -> AreaPage:  # fmt: skip
    g = ec.view_grant(db, p, project_id)
    rows = [
        a
        for a in db.scalars(
            select(WasteStorageArea)
            .where(WasteStorageArea.project_id == project_id)
            .order_by(WasteStorageArea.area_code)
        )
        if g.covers_site(a.site_id) and (site_id is None or a.site_id == site_id)
    ]
    return ec.paged(AreaPage, rows, page, size, lambda a: area_read(db, a))


def create_area(db: Session, p: Principal, project_id: uuid.UUID, body: AreaCreate) -> AreaRead:
    ec.project(db, p, project_id)
    ec.site_of(db, project_id, body.site_id)
    ec.zone_of(db, body.site_id, body.zone_id)
    ec.require(p, project_id, C.waste_area_manage, body.site_id, check_eng=False)
    if db.scalar(
        select(WasteStorageArea.id).where(
            WasteStorageArea.project_id == project_id, WasteStorageArea.area_code == body.area_code
        )
    ):
        raise ApiError(409, ErrorCode.DUPLICATE_VALUE, "This area code exists.", "الرمز مستخدم.")
    data = body.model_dump()
    data["accumulation"] = _acc(body.accumulation)
    a = WasteStorageArea(
        id=uuid.uuid4(), project_id=project_id, status=AreaStatus.active,
        created_by_user_id=p.user.id, **data,
    )  # fmt: skip
    _check_area(db, a)
    db.add(a)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.waste_storage_area, a, project_id)
    return area_read(db, a, True)


def read_area(db: Session, p: Principal, area_id: uuid.UUID) -> AreaRead:
    return area_read(db, _area(db, p, area_id), True)


def update_area(db: Session, p: Principal, area_id: uuid.UUID, body: AreaUpdate) -> AreaRead:
    a = _area(db, p, area_id)
    ec.require(p, a.project_id, C.waste_area_manage, a.site_id, check_eng=False)
    data = body.model_dump(exclude_unset=True)
    if "zone_id" in data:
        ec.zone_of(db, a.site_id, data["zone_id"])
    if data.get("accumulation") is not None:
        data["accumulation"] = _acc(data["accumulation"])
    for k, v in data.items():
        setattr(a, k, v)
    _check_area(db, a)
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.waste_storage_area, a, a.project_id)
    return area_read(db, a, True)


# ---- consignments (§3.6, §4.3, CON) --------------------------------------------------------------


def estimated_t(code: str, quantity: Decimal, unit: QuantityUnit, density: Decimal) -> Decimal:
    """§6.3 (sewage is counted in m³ only → 0 t)."""
    if rf.stream_class(code) == WasteClass.liquid_sewage:
        return D(0)
    if unit == QuantityUnit.t:
        return D(quantity)
    if unit == QuantityUnit.m3:
        return D(quantity) * D(density)
    return D(quantity) * D(density) / 1000


def tonnes(c: WasteConsignment) -> Decimal | None:
    """§6.3: received_net_t when a receipt is recorded, else estimated_t; None for sewage."""
    if rf.stream_class(c.stream_code) == WasteClass.liquid_sewage:
        return None
    return D(c.received_net_t) if c.received_net_t is not None else D(c.estimated_t)


def overdue(c: WasteConsignment, today: date | None = None) -> bool:
    return c.status == CS.dispatched and (today or ec.local_day()) > c.due_on


def _code(db: Session, pid: uuid.UUID | None) -> str:
    pv = db.get(EnvProvider, pid) if pid else None
    return pv.provider_code if pv else "?"


def consignment_read(db: Session, p: Principal, c: WasteConsignment) -> ConsignmentRead:
    hide = ec.is_viewer(p, c.project_id)
    t = tonnes(c)
    return ConsignmentRead(
        id=c.id, project_id=c.project_id, consignment_no=c.consignment_no,
        stream_code=c.stream_code, waste_class=rf.stream_class(c.stream_code),
        storage_area_id=c.storage_area_id, site_id=c.site_id,
        generator_engagement_id=c.generator_engagement_id,
        generator_code=ec.eng_code(db, c.generator_engagement_id), quantity=str(ec.s3(c.quantity)),
        unit=c.unit, estimated_t=str(ec.s3(c.estimated_t)),
        tonnes=ec.s1(t), provisional=t is not None and c.received_net_t is None,
        route=c.route, transporter_id=c.transporter_id,
        transporter_code=_code(db, c.transporter_id),
        transporter_licence_id=c.transporter_licence_id,
        facility_provider_id=c.facility_provider_id,
        facility_provider_code=_code(db, c.facility_provider_id), facility_code=c.facility_code,
        facility_licence_id=c.facility_licence_id,
        vehicle_plate=None if hide else c.vehicle_plate,
        driver_name=None if hide else c.driver_name,
        driver_mobile=None if hide else c.driver_mobile,
        mwan_manifest_ref=c.mwan_manifest_ref, dispatched_at=c.dispatched_at, due_on=c.due_on,
        overdue=overdue(c), received_at=c.received_at, received_net_t=ec.s3(c.received_net_t),
        ticket_ref=c.ticket_ref, ticket_file_id=c.ticket_file_id,
        receipt_recorded_at=c.receipt_recorded_at, discrepancy_pct=ec.s1(c.discrepancy_pct),
        discrepancy_reason=c.discrepancy_reason, rejection_reason=c.rejection_reason,
        redispatch_of_id=c.redispatch_of_id, ca_id=c.ca_id, status=c.status,
        status_reason=c.status_reason, warnings=ec.warnings_of(c.warnings),
    )  # fmt: skip


def _consignment(db: Session, p: Principal, cid: uuid.UUID) -> WasteConsignment:
    c = db.get(WasteConsignment, cid)
    if c is None or not p.can_see_project(c.project_id):
        raise not_found("Consignment")
    g = ec.need(p, c.project_id, C.env_view, write=False)
    if not ec.scope_ok(g, c.site_id, c.generator_engagement_id):
        raise not_found("Consignment")
    return c


def list_consignments(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: list[ConsignmentStatus] | None,
    stream_code: str | None,
    provider_id: uuid.UUID | None,
    overdue_: bool | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    size: int,
) -> ConsignmentPage:
    g = ec.view_grant(db, p, project_id)
    q = select(WasteConsignment).where(WasteConsignment.project_id == project_id)
    if status:
        q = q.where(WasteConsignment.status.in_(status))
    if stream_code:
        q = q.where(WasteConsignment.stream_code == stream_code)
    if provider_id:
        q = q.where(
            (WasteConsignment.transporter_id == provider_id)
            | (WasteConsignment.facility_provider_id == provider_id)
        )
    if date_from:
        q = q.where(WasteConsignment.dispatched_date >= date_from)
    if date_to:
        q = q.where(WasteConsignment.dispatched_date <= date_to)
    rows = [
        c
        for c in db.scalars(q.order_by(WasteConsignment.dispatched_at.desc()))
        if ec.scope_ok(g, c.site_id, c.generator_engagement_id)
        and (overdue_ is None or overdue(c) == overdue_)
    ]
    return ec.paged(ConsignmentPage, rows, page, size, lambda c: consignment_read(db, p, c))


def _norm_plate(s: str) -> str:
    return "".join(ch for ch in s.upper().replace("(TEST)", "") if ch.isalnum())


def avp_found(db: Session, project_id: uuid.UUID, plate: str, d: date) -> bool:
    """AIR-3: a Phase 2 vehicle with this plate and an Active AVP on d."""
    want = _norm_plate(plate)
    for v, a in db.execute(
        select(Vehicle, Avp)
        .join(Avp, Avp.vehicle_id == Vehicle.id)
        .where(Avp.project_id == project_id, Avp.validity_status == ValidityStatus.active)
    ):
        digits, letters = v.plate_digits or "", (v.plate_letters_en or "").upper()
        if want not in (digits + letters, letters + digits) or not digits:
            continue
        if (a.issued_on is None or a.issued_on <= d) and (
            a.effective_valid_until is None or d <= a.effective_valid_until
        ):
            return True
    return False


def producer_check(db: Session, project_id: uuid.UUID, d: date) -> None:
    """PRM-4 / CON-3."""
    for code, pms in ec.requirements(db, project_id).items():
        if not any(pm.permit_type == PermitType.mwan_producer_registration for pm in pms):
            continue
        if ec.applicable(pms, d) and not ec.requirement_in_force(db, project_id, code, d):
            raise ec.code_err(
                ErrorCode.PRODUCER_REGISTRATION_INVALID,
                f"The MWAN producer registration is not in force on {d.isoformat()}; "
                "no consignment can be dispatched.",
                f"تسجيل منتج النفايات غير ساري بتاريخ {d.isoformat()}؛ لا يمكن إرسال النفايات.",
            )


def licence_checks(
    db: Session, code: str, route: Any, tr: EnvProvider, fac: EnvProvider, fcode: str | None,
    d: date,
) -> tuple[uuid.UUID, uuid.UUID]:  # fmt: skip
    """CON-2 (no override)."""
    wc = rf.stream_class(code)
    if wc == WasteClass.liquid_sewage and ProviderKind.sewage_tanker.value not in (tr.kinds or []):
        raise ec.code_err(
            ErrorCode.LICENCE_SCOPE_MISMATCH,
            f"Sewage needs a sewage tanker; {tr.provider_code} is not one.",
            f"نقل الصرف الصحي يتطلب صهريج صرف صحي؛ {tr.provider_code} ليس كذلك.",
            "transporter_id",
        )
    tl = ec.licence_for(db, tr, d, frozenset({"collection_transport"}), wc.value, "transporter_id")
    types = (
        frozenset({PermitType.facility_authorisation}) if wc == WasteClass.liquid_sewage else None
    )
    fl = ec.licence_for(
        db, fac, d, rf.ROUTE_ACTIVITY[route], wc.value, "facility_provider_id", types, fcode
    )
    return tl.id, fl.id


def create_consignment(
    db: Session, p: Principal, project_id: uuid.UUID, body: ConsignmentCreate
) -> ConsignmentRead:
    pr = ec.project(db, p, project_id)
    code = body.stream_code
    stream = stream_rows(db, project_id).get(code)
    if code not in rf.WS or stream is None or not stream.active:
        raise validation_error("stream_code", "Activate this waste stream on the project first.")
    area = db.get(WasteStorageArea, body.storage_area_id) if body.storage_area_id else None
    if body.storage_area_id and (area is None or area.project_id != project_id):
        raise validation_error("storage_area_id", "Unknown storage area.")
    if area is not None and code not in (area.accepted_streams or []):
        raise ec.code_err(
            ErrorCode.STREAM_NOT_ACCEPTED, "The storage area does not accept this stream.",
            "منطقة التخزين لا تقبل هذا المسار.", "storage_area_id",
        )  # fmt: skip
    site_id = body.site_id or (area.site_id if area else None)
    if site_id is None:
        raise validation_error("site_id", "Give the site or the storage area.")
    ec.site_of(db, project_id, site_id)
    ec.eng_of_project(db, project_id, body.generator_engagement_id)
    ec.require(p, project_id, C.consignment_record, site_id, body.generator_engagement_id)
    t = now()
    at = body.dispatched_at
    if at > t + timedelta(minutes=5) or at < t - timedelta(hours=72):
        raise validation_error(
            "dispatched_at", "Dispatch time must be within the last 72 hours (CON-1).",
            msg_ar="يجب أن يكون وقت الإرسال خلال آخر 72 ساعة.",
        )  # fmt: skip
    d = ec.local_day(body.dispatched_at)
    producer_check(db, project_id, d)
    tr = ec.provider_ok(db.get(EnvProvider, body.transporter_id), "transporter_id")
    fac = ec.provider_ok(db.get(EnvProvider, body.facility_provider_id), "facility_provider_id")
    route = body.route or stream.default_route
    tl, fl = licence_checks(db, code, route, tr, fac, body.facility_code, d)
    c = ec.cfg(db, project_id)
    wc = rf.stream_class(code)
    if wc.value in (c["mwan_manifest_required_for"] or []) and not body.mwan_manifest_ref:
        raise ec.code_err(
            ErrorCode.MANIFEST_REF_REQUIRED, "The MWAN manifest reference is required.",
            "رقم بيان النقل (موان) مطلوب.", "mwan_manifest_ref",
        )  # fmt: skip
    if body.redispatch_of_id is not None:
        prev = db.get(WasteConsignment, body.redispatch_of_id)
        if prev is None or prev.project_id != project_id or prev.status != CS.rejected:
            raise validation_error("redispatch_of_id", "Name a rejected consignment.")
    warnings: list[str] = []
    zone = db.get(Zone, area.zone_id) if area and area.zone_id else None
    if ec.is_airside(zone) and not avp_found(db, project_id, body.vehicle_plate, d):
        warnings.append("AVP_NOT_FOUND")
    seq = ec.next_seq(db, WasteConsignment, project_id, d.year)
    con = WasteConsignment(
        id=uuid.uuid4(), consignment_no=ec.ref("WCN", pr.code, d.year, seq, 5), year=d.year,
        seq=seq, project_id=project_id, stream_code=code, storage_area_id=body.storage_area_id,
        site_id=site_id, generator_engagement_id=body.generator_engagement_id,
        quantity=body.quantity, unit=body.unit,
        estimated_t=estimated_t(code, body.quantity, body.unit, D(stream.density)), route=route,
        transporter_id=tr.id, transporter_licence_id=tl, facility_provider_id=fac.id,
        facility_code=body.facility_code, facility_licence_id=fl,
        vehicle_plate=body.vehicle_plate, driver_name=body.driver_name,
        driver_mobile=body.driver_mobile, mwan_manifest_ref=body.mwan_manifest_ref,
        dispatched_at=body.dispatched_at, dispatched_date=d, dispatched_by_user_id=p.user.id,
        due_on=d + timedelta(days=int(c["manifest_return_days"])),
        redispatch_of_id=body.redispatch_of_id, warnings=warnings, status=CS.dispatched,
        created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(con)
    if area is not None and any(
        x["stream_code"] == code and x.get("started_on") for x in area.accumulation or []
    ):
        # WST-5: a dispatch of the stream from the area clears started_on (full removal)
        area.accumulation = [
            {**x, "started_on": None} if x["stream_code"] == code else x
            for x in area.accumulation or []
        ]
    db.flush()
    ec.record(db, p, AuditAction.create, ET.waste_consignment, con, project_id)
    return consignment_read(db, p, con)


def read_consignment(db: Session, p: Principal, cid: uuid.UUID) -> ConsignmentRead:
    return consignment_read(db, p, _consignment(db, p, cid))


def _closed(c: WasteConsignment) -> None:
    if c.status == CS.closed:
        raise ApiError(
            409, ErrorCode.CONSIGNMENT_CLOSED, "A closed consignment cannot be changed.",
            "لا يمكن تعديل إشعار نقل مغلق.",
        )  # fmt: skip
    if c.status == CS.voided:
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, "The consignment is voided.",
                       "الإشعار ملغى.")  # fmt: skip


def update_consignment(
    db: Session, p: Principal, cid: uuid.UUID, body: ConsignmentUpdate
) -> ConsignmentRead:
    c = _consignment(db, p, cid)
    _closed(c)
    ec.require(p, c.project_id, C.consignment_record, c.site_id, c.generator_engagement_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.waste_consignment, c, c.project_id)
    return consignment_read(db, p, c)


def discrepancy(c: WasteConsignment) -> Decimal | None:
    """CON-7 (unrounded)."""
    if c.received_net_t is None or not c.estimated_t:
        return None
    return abs(D(c.received_net_t) - D(c.estimated_t)) / D(c.estimated_t) * 100


def record_receipt(
    db: Session, p: Principal, cid: uuid.UUID, body: ReceiptInput
) -> ConsignmentRead:
    c = _consignment(db, p, cid)
    _closed(c)
    g = p.grant(c.project_id, C.consignment_record) or p.grant(c.project_id, C.consignment_close)
    if g is None or not ec.scope_ok(g, c.site_id, c.generator_engagement_id):
        raise forbidden_error("This consignment is outside your scope.")
    if c.status != CS.dispatched:
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, "Only a dispatched load is received.",
                       "يُسجل الاستلام للإشعارات المرسلة فقط.")  # fmt: skip
    if body.received_at < c.dispatched_at:
        raise validation_error("received_at", "Receipt cannot be before dispatch.")
    att = db.get(Attachment, body.ticket_file_id)
    if att is None or att.owner_type != AttachmentOwner.consignment_ticket or att.owner_id != c.id:
        raise validation_error("ticket_file_id", "Attach the weighbridge ticket to this load.")
    c.received_at = body.received_at
    c.received_net_t = body.received_net_t
    c.ticket_ref = body.ticket_ref
    c.ticket_file_id = body.ticket_file_id
    c.receipt_recorded_at = now()
    x = discrepancy(c)
    c.discrepancy_pct = None if x is None else x.quantize(D("0.01"))
    c.status = CS.received
    c.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.waste_consignment, c, c.project_id)
    return consignment_read(db, p, c)


def transition_consignment(
    db: Session, p: Principal, cid: uuid.UUID, body: ConsignmentTransition
) -> ConsignmentRead:
    c = _consignment(db, p, cid)
    _closed(c)
    pid = c.project_id
    a = body.action
    if a == ConsignmentAction.void:
        p.require(pid, C.env_void)
        c.status_reason = ec.reason(body.reason, 20)
        c.status = CS.voided
    elif a == ConsignmentAction.close:
        p.require(pid, C.consignment_close)
        if c.status != CS.received:
            raise ApiError(409, ErrorCode.INVALID_TRANSITION, "Record the receipt first.",
                           "سجّل الاستلام أولاً.")  # fmt: skip
        x = discrepancy(c)
        if x is not None and x > ec.cfg(db, pid).dec("weight_discrepancy_pct"):
            if not body.discrepancy_reason or len(body.discrepancy_reason.strip()) < 20:
                raise ec.code_err(
                    ErrorCode.DISCREPANCY_REASON_REQUIRED,
                    f"Weight discrepancy {ec.s1(x)} % — give a reason of at least 20 characters.",
                    f"فرق الوزن {ec.s1(x)} % — اذكر سبباً لا يقل عن 20 حرفاً.",
                    "discrepancy_reason",
                )
            c.discrepancy_reason = body.discrepancy_reason.strip()
        c.status = CS.closed
        c.closed_at = now()
    else:
        p.require(pid, C.consignment_close)
        if c.status != CS.dispatched:
            raise ApiError(409, ErrorCode.INVALID_TRANSITION, "Only a dispatched load is rejected.",
                           "يُرفض الإشعار المرسل فقط.")  # fmt: skip
        c.rejection_reason = ec.reason(body.reason, 10)
        c.status = CS.rejected
        pr = ec.project(db, None, pid)
        ca = ec.make_ca(
            db, pr, CaSourceType.environmental, c.id, c.site_id or _any_site(db, pid), None,
            c.generator_engagement_id, "major",
            f"Rejected waste load {c.consignment_no}",
            f"{c.consignment_no} ({c.stream_code}) was refused by the facility: "
            f"{c.rejection_reason}. The waste must leave again on a new consignment.",
            None, None, p.user.id,
        )  # fmt: skip
        c.ca_id = ca.id
        ec.send(
            db, ec.officers(db, pid) | ec.reps(db, pid, c.generator_engagement_id),
            NK.consignment_rejected,
            f"{c.consignment_no} was rejected by the facility; {ca.ref} raised.",
            f"رفضت المنشأة الإشعار {c.consignment_no}؛ تم إنشاء {ca.ref}.",
            pid, ET.waste_consignment, c.id, email=True,
        )  # fmt: skip
    c.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.waste_consignment, c, pid)
    return consignment_read(db, p, c)


def _any_site(db: Session, project_id: uuid.UUID) -> uuid.UUID:
    from app.models import Site  # noqa: PLC0415

    s = db.scalar(select(Site.id).where(Site.project_id == project_id).order_by(Site.code))
    assert s is not None  # noqa: S101
    return s
