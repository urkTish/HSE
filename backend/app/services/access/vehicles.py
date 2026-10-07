"""Vehicles / mobile plant and airside vehicle permits (spec 2-access-permits §3.12, §3.13,
§5.6 VP-1…VP-8)."""

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    AreaCategory,
    AvpChecklistItem,
    ChecklistOutcome,
    CredentialAction,
    CredentialReason,
    CustodyStatus,
    HookKind,
    HookSubjectType,
    InspectionResult,
    PlateType,
    QrKind,
    QrTokenStatus,
    RequirementStatus,
    ValidityStatus,
    VehicleStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, ContractorStatus, EntityType, ZoneType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.text import like_pattern
from app.kpi.periods import add_months
from app.models import Avp, ProjectEngagement, Vehicle, Zone
from app.schemas.airside_driving import (
    AvpCreate,
    AvpIssueRequest,
    AvpPage,
    AvpRead,
    AvpStickerRead,
    AvpStickerReissueRequest,
    AvpUpdate,
    VehicleCreate,
    VehiclePage,
    VehicleRead,
    VehicleTransitionRequest,
    VehicleUpdate,
)
from app.schemas.hse_common import ApiWarning
from app.services import audit, projects
from app.services.access import common, credentials, eligibility, lifecycle, profiles
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
LIVE = (ValidityStatus.active, ValidityStatus.suspended)
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
NO_NA = {
    AvpChecklistItem.amber_beacon,
    AvpChecklistItem.company_marking,
    AvpChecklistItem.fire_extinguisher,
    AvpChecklistItem.tyres_brakes,
    AvpChecklistItem.lights,
}
MANOEUVRING_ITEMS = {AvpChecklistItem.radio_fitted, AvpChecklistItem.chequered_flag_or_marking}
INSPECTION_MAX_AGE_DAYS = 14
HEIGHT_MARKING_M = Decimal("3.00")


def _airport(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    project = projects.get_visible(db, p, project_id)
    common.require_airport(project)
    return project


def _norm_letters(s: str | None) -> str | None:
    return re.sub(r"\s+", "", s) if s else None


# ---- vehicles ------------------------------------------------------------------------------------


def documents(v: Vehicle) -> list[date]:
    return [d for d in (v.istimara_expiry, v.insurance_expiry, v.mvpi_expiry) if d is not None]


def vehicle_read(
    db: Session,
    p: Principal | None,
    v: Vehicle,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> VehicleRead:
    refs = refs or Refs(db)
    show_plate = p is None or p.grant(v.project_id, C.worker_view) is not None
    docs = documents(v)
    day = today()
    active = db.scalar(
        select(Avp.id).where(Avp.vehicle_id == v.id, Avp.validity_status.in_(LIVE)).limit(1)
    )
    eng = refs.eng_required(v.engagement_id)
    return VehicleRead(
        id=v.id,
        vehicle_no=v.vehicle_no,
        project_id=v.project_id,
        engagement=eng,
        owner_type=v.owner_type,
        category=v.category,
        plate_type=v.plate_type,
        plate_letters_ar=v.plate_letters_ar if show_plate else None,
        plate_letters_en=v.plate_letters_en if show_plate else None,
        plate_digits=v.plate_digits if show_plate else None,
        fleet_no=v.fleet_no,
        serial_or_vin=v.serial_or_vin,
        make_model=v.make_model,
        year=v.year_built,
        colour=v.colour,
        travel_height_m=v.travel_height_m,
        max_working_height_m_agl=v.max_working_height_m_agl,
        max_working_height_ft=common.to_ft(v.max_working_height_m_agl),
        istimara_expiry=v.istimara_expiry,
        insurance_policy_no=v.insurance_policy_no,
        insurance_expiry=v.insurance_expiry,
        mvpi_expiry=v.mvpi_expiry,
        documents_valid=all(d >= day for d in docs),
        earliest_document_expiry=min(docs) if docs else None,
        status=v.status,
        active_avp_id=active,
        warnings=warnings or [],
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def get_vehicle_row(db: Session, p: Principal, vehicle_id: uuid.UUID) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if v is None:
        raise not_found("Vehicle")
    projects.get_visible(db, p, v.project_id)
    g = p.grant(v.project_id, C.access_works_view) or p.grant(v.project_id, C.worker_view)
    if not common.grant_covers(g, None, v.engagement_id):
        raise forbidden_error("This vehicle is outside your scope.")
    return v


def read_vehicle(db: Session, p: Principal, vehicle_id: uuid.UUID) -> VehicleRead:
    return vehicle_read(db, p, get_vehicle_row(db, p, vehicle_id))


def _view_grant(p: Principal, project_id: uuid.UUID) -> Any:
    g = p.grant(project_id, C.access_works_view) or p.grant(project_id, C.worker_view)
    if g is None:
        raise forbidden_error()
    return g


def list_vehicles(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[VehicleStatus] | None,
    categories: list[Any] | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    documents_expiring_within_days: int | None,
    q: str | None,
) -> VehiclePage:
    project = _airport(db, p, project_id)
    g = _view_grant(p, project.id)
    stmt = select(Vehicle).where(Vehicle.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(Vehicle.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(Vehicle.status.in_(statuses))
    if categories:
        stmt = stmt.where(Vehicle.category.in_(categories))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(Vehicle.engagement_id.in_(ids))
    if documents_expiring_within_days is not None:
        lim = today() + timedelta(days=documents_expiring_within_days)
        stmt = stmt.where(
            or_(
                Vehicle.istimara_expiry <= lim,
                Vehicle.insurance_expiry <= lim,
                Vehicle.mvpi_expiry <= lim,
            )
        )
    if q:
        pat = like_pattern(q)
        conds: list[ColumnElement[bool]] = [
            Vehicle.vehicle_no.ilike(pat),
            Vehicle.fleet_no.ilike(pat),
            Vehicle.make_model.ilike(pat),
        ]
        if p.grant(project.id, C.worker_view) is not None:
            conds.append(Vehicle.plate_digits.ilike(pat))
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(Vehicle.seq)
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(engs=[v.engagement_id for v in rows])
    return VehiclePage(
        items=[vehicle_read(db, p, v, refs) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _validate_vehicle(db: Session, v: Vehicle, check_vin: bool = True) -> None:
    """check_vin=False on updates that leave the VIN unchanged (stored rows are not re-judged)."""
    plated = v.plate_type != PlateType.none
    if plated:
        if not v.plate_letters_ar or not v.plate_digits:
            raise validation_error("plate_letters_ar", "Plate letters and digits are required.")
        if len(_norm_letters(v.plate_letters_ar) or "") != 3:
            raise validation_error("plate_letters_ar", "Saudi plates have 3 letters.")
        if v.istimara_expiry is None:
            raise validation_error("istimara_expiry", "Required for plated vehicles.")
        if v.mvpi_expiry is None:
            raise validation_error("mvpi_expiry", "Required for plated vehicles (Fahas).")
        if check_vin and not VIN_RE.match(v.serial_or_vin):
            raise validation_error("serial_or_vin", "Not a valid 17-character VIN.")
    else:
        v.plate_letters_ar = v.plate_letters_en = v.plate_digits = None
    if not Decimal("0.5") <= v.travel_height_m <= Decimal(20):
        raise validation_error("travel_height_m", "0.5-20 m.")
    if v.max_working_height_m_agl < v.travel_height_m:
        raise validation_error("max_working_height_m_agl", "Must be ≥ the travel height (OB-2).")
    if v.year_built > today().year + 1:
        raise validation_error("year", "Year cannot be in the future.")
    if plated:
        clash = db.scalar(
            select(Vehicle.vehicle_no).where(
                func.regexp_replace(Vehicle.plate_letters_ar, r"\s", "", "g")
                == _norm_letters(v.plate_letters_ar),
                Vehicle.plate_digits == v.plate_digits,
                Vehicle.status != VehicleStatus.withdrawn,
                Vehicle.id != v.id,
            )
        )
        if clash:
            raise duplicate("plate_digits", "A vehicle with this plate is already registered.")
    if db.scalar(
        select(Vehicle.id).where(
            Vehicle.project_id == v.project_id,
            Vehicle.serial_or_vin == v.serial_or_vin,
            Vehicle.id != v.id,
        )
    ):
        raise duplicate("serial_or_vin", "This serial/VIN is already registered on the project.")


def _veh_snapshot(v: Vehicle) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(v, k)
            for k in (
                "vehicle_no", "engagement_id", "owner_type", "category", "plate_type",
                "plate_letters_ar", "plate_digits", "fleet_no", "serial_or_vin", "make_model",
                "year_built", "colour", "travel_height_m", "max_working_height_m_agl",
                "istimara_expiry", "insurance_policy_no", "insurance_expiry", "mvpi_expiry",
                "status",
            )
        }
    )  # fmt: skip


def _check_engagement(db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
    e = db.get(ProjectEngagement, engagement_id)
    if e is None or e.project_id != project_id:
        raise validation_error("engagement_id", "Unknown engagement on this project.")
    if e.contractor.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        raise ApiError(
            403,
            ErrorCode.CONTRACTOR_SUSPENDED,
            "The contractor is suspended.",
            "المقاول موقوف.",
        )


def create_vehicle(
    db: Session, p: Principal, project_id: uuid.UUID, body: VehicleCreate
) -> VehicleRead:
    project = _airport(db, p, project_id)
    common.require_cap(p, project.id, C.vehicle_edit, None, body.engagement_id)
    _check_engagement(db, project.id, body.engagement_id)
    db.execute(select(func.pg_advisory_xact_lock(0x56454849)))
    seq = (
        int(db.scalar(select(func.max(Vehicle.seq)).where(Vehicle.project_id == project.id)) or 0)
        + 1
    )
    data = body.model_dump()
    data["year_built"] = data.pop("year")
    v = Vehicle(
        id=uuid.uuid4(),
        seq=seq,
        vehicle_no=f"VEH-{seq:04d}",
        project_id=project.id,
        status=VehicleStatus.active,
        created_by_user_id=p.user.id,
        **data,
    )
    v.plate_letters_en = v.plate_letters_en.upper() if v.plate_letters_en else None
    v.serial_or_vin = v.serial_or_vin.strip().upper()
    _validate_vehicle(db, v)
    db.add(v)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.vehicle,
        entity_id=v.id,
        project_id=project.id,
        after=_veh_snapshot(v),
    )
    return vehicle_read(db, p, v)


def update_vehicle(
    db: Session, p: Principal, vehicle_id: uuid.UUID, body: VehicleUpdate
) -> VehicleRead:
    v = get_vehicle_row(db, p, vehicle_id)
    common.require_cap(p, v.project_id, C.vehicle_edit, None, v.engagement_id)
    if v.status == VehicleStatus.withdrawn:
        raise invalid_transition("Vehicle", v.status, "edited")
    before = _veh_snapshot(v)
    ch = body.changes()
    if "year" in ch:
        ch["year_built"] = ch.pop("year")
    for k, val in ch.items():
        setattr(v, k, val)
    v.serial_or_vin = v.serial_or_vin.strip().upper()
    _validate_vehicle(db, v, check_vin="serial_or_vin" in ch)
    v.updated_by_user_id = p.user.id
    v.updated_at = now()
    db.flush()
    if {"istimara_expiry", "insurance_expiry", "mvpi_expiry"} & set(ch):
        lifecycle.refresh_vehicle(db, v.id)  # LC-2 / VP-5
    bf, af = audit.diff(before, _veh_snapshot(v))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(v.project_id),
            entity_type=EntityType.vehicle,
            entity_id=v.id,
            project_id=v.project_id,
            before=bf,
            after=af,
        )
    return vehicle_read(db, p, v)


VEHICLE_MOVES = {
    (VehicleStatus.active, VehicleStatus.off_site),
    (VehicleStatus.off_site, VehicleStatus.active),
    (VehicleStatus.active, VehicleStatus.withdrawn),
    (VehicleStatus.off_site, VehicleStatus.withdrawn),
}


def transition_vehicle(
    db: Session, p: Principal, vehicle_id: uuid.UUID, body: VehicleTransitionRequest
) -> VehicleRead:
    v = get_vehicle_row(db, p, vehicle_id)
    common.require_cap(p, v.project_id, C.vehicle_edit, None, v.engagement_id)
    if (v.status, body.to_status) not in VEHICLE_MOVES:
        raise invalid_transition("Vehicle", v.status, body.to_status)
    before = v.status
    v.status = body.to_status
    if body.to_status == VehicleStatus.withdrawn:
        s = common.settings(db, v.project_id)
        for a in db.scalars(select(Avp).where(Avp.vehicle_id == v.id)):
            lifecycle.revoke(
                db, a, CredentialReason.other, body.reason or "Vehicle withdrawn", p.user.id, s
            )
    v.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(v.project_id),
        entity_type=EntityType.vehicle,
        entity_id=v.id,
        project_id=v.project_id,
        before={"status": before.value},
        after={"status": v.status.value},
        details={"reason": body.reason} if body.reason else None,
    )
    return vehicle_read(db, p, v)


# ---- AVPs ----------------------------------------------------------------------------------------


def checklist_problems(a: Avp, v: Vehicle) -> list[AvpChecklistItem]:
    """VP-3 / VP-4 items blocking issue."""
    cl = {AvpChecklistItem(k): ChecklistOutcome(x) for k, x in (a.checklist or {}).items()}
    out: list[AvpChecklistItem] = []
    manoeuvring = AreaCategory.manoeuvring.value in (a.areas or [])
    for item in AvpChecklistItem:
        res = cl.get(item)
        must_pass = (item in MANOEUVRING_ITEMS and manoeuvring) or (
            item == AvpChecklistItem.height_marking
            and v.max_working_height_m_agl > HEIGHT_MARKING_M
        )
        if (
            res is None
            or res == ChecklistOutcome.fail
            or (res == ChecklistOutcome.na and (item in NO_NA or must_pass))
        ):
            out.append(item)
    return out


def _hook_items(db: Session, a: Avp, v: Vehicle) -> list[eligibility.Item]:
    s = common.settings(db, a.project_id)
    reqs = (s.hook_requirements_by_vehicle_category or {}).get(v.category.value, [])
    return [
        eligibility.hook_item(
            db, HookSubjectType.vehicle, v.id, HookKind(h["kind"]), h["code"], now(), s
        )
        for h in reqs
    ]


def avp_read(db: Session, p: Principal | None, a: Avp, refs: Refs | None = None) -> AvpRead:
    refs = refs or Refs(db)
    v = db.get(Vehicle, a.vehicle_id)
    assert v is not None  # noqa: S101
    tok = common.latest_qr(db, a.id)
    hooks_ = _hook_items(db, a, v)
    return AvpRead(
        id=a.id,
        avp_no=a.avp_no,
        project_id=a.project_id,
        vehicle=common.vehicle_ref(v),
        engagement=refs.eng_required(a.engagement_id),
        areas=[AreaCategory(x) for x in a.areas or []],
        inspection_date=a.inspection_date,
        inspector=a.inspector,
        inspection_result=a.inspection_result,
        checklist={
            AvpChecklistItem(k): ChecklistOutcome(x) for k, x in (a.checklist or {}).items()
        },
        checklist_problems=checklist_problems(a, v),
        sticker_no=a.sticker_no,
        sticker_token_status=tok.status if tok else None,
        issued_on=a.issued_on,
        own_valid_until=a.own_valid_until,
        validity=credentials.validity_block(db, a, refs),
        hook_warnings=[
            f"{h.code}: {h.status.value}" for h in hooks_ if h.status != RequirementStatus.met
        ],
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def get_avp_row(db: Session, p: Principal, avp_id: uuid.UUID) -> Avp:
    a = db.get(Avp, avp_id)
    if a is None:
        raise not_found("AVP")
    projects.get_visible(db, p, a.project_id)
    g = p.grant(a.project_id, C.access_works_view) or p.grant(a.project_id, C.worker_view)
    if not common.grant_covers(g, None, a.engagement_id):
        raise forbidden_error("This AVP is outside your scope.")
    return a


def read_avp(db: Session, p: Principal, avp_id: uuid.UUID) -> AvpRead:
    return avp_read(db, p, get_avp_row(db, p, avp_id))


def list_avps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    validity_statuses: list[ValidityStatus] | None,
    area: AreaCategory | None,
    vehicle_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    expiring_within_days: int | None,
) -> AvpPage:
    project = _airport(db, p, project_id)
    g = _view_grant(p, project.id)
    stmt = select(Avp).where(Avp.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(Avp.engagement_id.in_(list(g.engagement_ids)))
    if validity_statuses:
        stmt = stmt.where(Avp.validity_status.in_(validity_statuses))
    if area:
        stmt = stmt.where(Avp.areas.contains([area.value]))
    if vehicle_id:
        stmt = stmt.where(Avp.vehicle_id == vehicle_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(Avp.engagement_id.in_(ids))
    if expiring_within_days is not None:
        stmt = stmt.where(
            Avp.validity_status.in_(LIVE),
            Avp.effective_valid_until <= today() + timedelta(days=expiring_within_days),
        )
    stmt = stmt.order_by(Avp.created_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(engs=[a.engagement_id for a in rows])
    return AvpPage(
        items=[avp_read(db, p, a, refs) for a in rows], total=total, page=page, page_size=page_size
    )


def _check_areas(db: Session, engagement_id: uuid.UUID, areas: list[AreaCategory]) -> None:
    """VP-2: areas must exist in airside zones of the engagement's sites."""
    e = db.get(ProjectEngagement, engagement_id)
    sites = list(e.site_ids or []) if e else []
    have = {
        profiles.area_category(z)
        for z in db.scalars(
            select(Zone).where(Zone.site_id.in_(sites), Zone.zone_type == ZoneType.airside)
        )
    }
    for a in areas:
        if a not in have:
            raise validation_error("areas", f"No {a.value} zone in the contractor's airside sites.")


def _avp_snapshot(a: Avp) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(a, k)
            for k in (
                "avp_no", "areas", "inspection_date", "inspector", "inspection_result",
                "checklist", "sticker_no", "issued_on", "own_valid_until", "validity_status",
            )
        }
    )  # fmt: skip


def create_avp(db: Session, p: Principal, project_id: uuid.UUID, body: AvpCreate) -> AvpRead:
    project = _airport(db, p, project_id)
    v = db.get(Vehicle, body.vehicle_id)
    if v is None or v.project_id != project.id:
        raise validation_error("vehicle_id", "Unknown vehicle on this project.")
    common.require_cap(p, project.id, C.vehicle_edit, None, v.engagement_id)
    if v.status != VehicleStatus.active:
        raise validation_error("vehicle_id", "The vehicle is not active.")
    _check_engagement(db, project.id, v.engagement_id)
    existing = db.scalar(
        select(Avp).where(
            Avp.vehicle_id == v.id, Avp.validity_status.in_([*LIVE, ValidityStatus.pending])
        )
    )
    if existing is not None:
        raise ApiError(
            409,
            ErrorCode.AVP_EXISTS,
            "The vehicle already has an AVP or application (VP-2).",
            "للمركبة تصريح أو طلب قائم.",
            meta={"id": str(existing.id)},
        )
    areas = list(dict.fromkeys(body.areas))
    _check_areas(db, v.engagement_id, areas)
    a = Avp(
        id=uuid.uuid4(),
        project_id=project.id,
        vehicle_id=v.id,
        engagement_id=v.engagement_id,
        areas=[x.value for x in areas],
        checklist={},
        validity_status=ValidityStatus.pending,
        created_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.avp,
        entity_id=a.id,
        project_id=project.id,
        after=_avp_snapshot(a),
    )
    return avp_read(db, p, a)


INSPECTION_FIELDS = {"inspection_date", "inspector", "inspection_result", "checklist"}


def update_avp(db: Session, p: Principal, avp_id: uuid.UUID, body: AvpUpdate) -> AvpRead:
    a = get_avp_row(db, p, avp_id)
    ch = body.changes()
    if set(ch) & INSPECTION_FIELDS:
        common.require_cap(p, a.project_id, C.avp_issue, None, a.engagement_id)
    if "areas" in ch:
        common.require_cap(p, a.project_id, C.vehicle_edit, None, a.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        raise invalid_transition("AVP", a.validity_status, "edited")
    before = _avp_snapshot(a)
    if "areas" in ch:
        areas = [AreaCategory(x) for x in dict.fromkeys(ch["areas"])]
        _check_areas(db, a.engagement_id, areas)
        a.areas = [x.value for x in areas]
    if "checklist" in ch:
        a.checklist = {
            str(getattr(k, "value", k)): str(getattr(x, "value", x))
            for k, x in (ch["checklist"] or {}).items()
        }
    for k in ("inspection_date", "inspector", "inspection_result"):
        if k in ch:
            setattr(a, k, ch[k])
    if a.inspection_date and a.inspection_date > today():
        raise validation_error("inspection_date", "The inspection date cannot be in the future.")
    a.updated_at = now()
    a.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _avp_snapshot(a))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.avp,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
    return avp_read(db, p, a)


def _precondition(problems: list[str]) -> ApiError:
    return ApiError(
        422,
        ErrorCode.AVP_PRECONDITION,
        "The AVP cannot be issued: " + "; ".join(problems) + " (VP-3/VP-4).",
        "لا يمكن إصدار تصريح المركبة: الشروط غير مستوفاة.",
        meta={"problems": problems},
    )


def issue_avp(db: Session, p: Principal, avp_id: uuid.UUID, body: AvpIssueRequest) -> AvpRead:
    a = get_avp_row(db, p, avp_id)
    common.require_cap(p, a.project_id, C.avp_issue, None, a.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        raise invalid_transition("AVP", a.validity_status, ValidityStatus.active)
    v = db.get(Vehicle, a.vehicle_id)
    assert v is not None  # noqa: S101
    s = common.settings(db, a.project_id)
    day = today()
    if body.issued_on > day:
        raise validation_error("issued_on", "issued_on cannot be in the future.")
    problems: list[str] = []
    if a.inspection_result != InspectionResult.passed or a.inspection_date is None:
        problems.append("inspection not passed")
    elif not (
        body.issued_on - timedelta(days=INSPECTION_MAX_AGE_DAYS)
        <= a.inspection_date
        <= body.issued_on
    ):
        problems.append(f"inspection older than {INSPECTION_MAX_AGE_DAYS} days")
    for name, d in (
        ("istimara", v.istimara_expiry),
        ("insurance", v.insurance_expiry),
        ("mvpi", v.mvpi_expiry),
    ):
        if d is not None and d <= day:
            problems.append(f"{name} expired")
    items = checklist_problems(a, v)
    if items:
        problems.append("checklist: " + ", ".join(i.value for i in items))
    for h in _hook_items(db, a, v):
        if h.status in (RequirementStatus.not_met, RequirementStatus.not_evaluated):
            problems.append(f"hook {h.code} not met")
    if problems:
        raise _precondition(problems)
    limit = add_months(body.issued_on, s.avp_validity_months)
    if body.own_valid_until > limit or body.own_valid_until <= body.issued_on:
        raise validation_error("own_valid_until", f"Must be after issue and ≤ {limit.isoformat()}.")
    if db.scalar(select(Avp.id).where(Avp.project_id == a.project_id, Avp.avp_no == body.avp_no)):
        raise duplicate("avp_no", "This AVP number already exists on the project.")
    before = _avp_snapshot(a)
    a.avp_no = body.avp_no
    a.sticker_no = body.sticker_no
    a.issued_on = body.issued_on
    a.own_valid_until = body.own_valid_until
    a.validity_status = ValidityStatus.active
    a.custody_status = CustodyStatus.held
    common.issue_qr(db, QrKind.VS, a.project_id, a.id, body.sticker_no)
    lifecycle.evaluate_avp(db, a)
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.avp,
        entity_id=a.id,
        project_id=a.project_id,
        before=before,
        after=_avp_snapshot(a),
    )
    return avp_read(db, p, a)


def withdraw_avp(db: Session, p: Principal, avp_id: uuid.UUID) -> AvpRead:
    a = get_avp_row(db, p, avp_id)
    common.require_cap(p, a.project_id, C.vehicle_edit, None, a.engagement_id)
    if a.validity_status != ValidityStatus.pending:
        raise invalid_transition("AVP", a.validity_status, ValidityStatus.withdrawn)
    a.validity_status = ValidityStatus.withdrawn
    a.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.avp,
        entity_id=a.id,
        project_id=a.project_id,
        before={"validity_status": "pending"},
        after={"validity_status": "withdrawn"},
    )
    return avp_read(db, p, a)


def _sticker(db: Session, a: Avp) -> AvpStickerRead:
    tok = common.active_qr(db, a.id)
    v = db.get(Vehicle, a.vehicle_id)
    assert v is not None  # noqa: S101
    if tok is None or a.avp_no is None or a.sticker_no is None:
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "The sticker is available for issued AVPs only.",
            "الملصق متاح للتصاريح الصادرة فقط.",
        )
    return AvpStickerRead(
        avp_id=a.id,
        avp_no=a.avp_no,
        sticker_no=a.sticker_no,
        vehicle_no=v.vehicle_no,
        fleet_no=v.fleet_no,
        qr_payload=common.payload(tok),
        printed_ref=tok.printed_ref,
        token_status=tok.status,
    )


def sticker(db: Session, p: Principal, avp_id: uuid.UUID) -> AvpStickerRead:
    a = get_avp_row(db, p, avp_id)
    common.require_cap(p, a.project_id, C.vehicle_edit, None, a.engagement_id, write=False)
    return _sticker(db, a)


def reissue_sticker(
    db: Session, p: Principal, avp_id: uuid.UUID, body: AvpStickerReissueRequest
) -> AvpStickerRead:
    a = get_avp_row(db, p, avp_id)
    common.require_cap(p, a.project_id, C.avp_issue, None, a.engagement_id)
    if a.validity_status not in LIVE or a.sticker_no is None:
        raise invalid_transition("AVP", a.validity_status, "sticker reissued")
    common.end_qr(db, a.id, QrTokenStatus.rotated)
    common.issue_qr(db, QrKind.VS, a.project_id, a.id, a.sticker_no)
    lifecycle.event(
        db, a, CredentialAction.token_rotated, CredentialReason.superseded, body.reason, p.user.id
    )
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(a.project_id),
        entity_type=EntityType.avp,
        entity_id=a.id,
        project_id=a.project_id,
        details={"sticker": "reissued"},
    )
    return _sticker(db, a)
