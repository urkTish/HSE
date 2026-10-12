"""7b.1 Site vehicles & plant (spec 7b-fleet-driver §3.1, §4.1, SV-1…SV-4): the Phase 2 vehicle
with the 7b columns, document expiry, derived readiness, verification, defect-hold clearance and
withdrawal. 7b never edits Phase 4 status (SV-3, BD7b-2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import CredentialReason, PlateType, VehicleStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.site_vehicle_enums import (
    SEATED_CLASSES,
    SITE_SCOPES,
    USE_CLASS_GROUP,
    SiteVehAuthStatus,
    SiteVehDocsFilter,
    SiteVehDriverGroup,
    SiteVehJourneyStatus,
    SiteVehReadiness,
    SiteVehUseClass,
    SiteVehWarning,
)
from app.models import (
    Avp,
    CorrectiveAction,
    DriverAuthorisation,
    EquipmentItem,
    JourneyPlan,
    Vehicle,
    VehicleCheck,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.site_vehicle import (
    SiteVehClearHold,
    SiteVehCreate,
    SiteVehDocRead,
    SiteVehHoldRead,
    SiteVehPage,
    SiteVehPhase4Read,
    SiteVehRead,
    SiteVehSummary,
    SiteVehTodayCheck,
    SiteVehUpdate,
    SiteVehVehicleRef,
    SiteVehWithdraw,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.access import lifecycle
from app.services.access import vehicles as pveh
from app.services.cert import reference as cref
from app.services.common import invalid_transition
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.site_vehicle import common as c
from app.services.site_vehicle.reference import WARNING

C = Capability
R = SiteVehReadiness
EXPIRING_DAYS = 30
SNAP = ("site_scope", "use_class", "driver_group", "seats", "operating_card_no",
        "operating_card_expiry", "istimara_expiry", "insurance_policy_no", "insurance_expiry",
        "mvpi_expiry", "idle_from", "idle_to", "fleet_no", "make_model", "status",
        "withdrawn_on", "docs_verified_at")  # fmt: skip
DOC_FIELDS = {"istimara_expiry", "insurance_expiry", "mvpi_expiry", "operating_card_expiry"}


def warn(code: SiteVehWarning, fld: str | None = None) -> ApiWarning:
    en, ar = WARNING[code]
    return ApiWarning(code=code.value, message=en, message_ar=ar, field=fld)


def vehicle_ref(v: Vehicle) -> SiteVehVehicleRef:
    return SiteVehVehicleRef(
        id=v.id,
        vehicle_no=v.vehicle_no,
        fleet_no=v.fleet_no,
        make_model=v.make_model,
        use_class=v.use_class,
        driver_group=v.driver_group,
    )


def snap(v: Vehicle) -> dict[str, Any]:
    return {k: getattr(v, k) for k in SNAP}


# ---- reading -------------------------------------------------------------------------------------


@dataclass
class Ctx:
    """Prefetched data for a page of vehicles."""

    day: date
    items: dict[uuid.UUID, EquipmentItem] = field(default_factory=dict)
    holds: dict[uuid.UUID, list[VehicleCheck]] = field(default_factory=dict)
    today: dict[uuid.UUID, VehicleCheck] = field(default_factory=dict)

    @classmethod
    def load(cls, db: Session, vs: list[Vehicle], day: date | None = None) -> Ctx:
        d = day or c.local_day()
        ids = [v.id for v in vs]
        today: dict[uuid.UUID, VehicleCheck] = {}
        if ids:
            for ch in db.scalars(
                select(VehicleCheck)
                .where(VehicleCheck.vehicle_id.in_(ids), VehicleCheck.check_date == d)
                .order_by(VehicleCheck.completed_at)
            ):
                today[ch.vehicle_id] = ch  # the latest check of the day
        return cls(d, c.phase4_items(db, ids), c.hold_checks(db, ids), today)

    def readiness(self, v: Vehicle) -> tuple[SiteVehReadiness, list[str]]:
        return c.readiness_on(v, self.day, self.items.get(v.id), self.holds.get(v.id, []))


def doc_reads(v: Vehicle, day: date) -> list[SiteVehDocRead]:
    out = []
    for k, d in c.documents(v):
        left = (d - day).days
        state = "expired" if left < 0 else ("expiring" if left <= EXPIRING_DAYS else "valid")
        out.append(SiteVehDocRead(kind=k, expiry=d, days_left=left, state=state))
    return out


def required_on(cf: c.Cfg, v: Vehicle, d: date) -> bool:
    """PU-1 / §6.2: a required vehicle-day."""
    return (
        cf.live
        and cf.live_from is not None
        and d >= cf.live_from
        and c.is_site(v)
        and v.driver_group in cf.required_groups
        and cf.working_day(d)
        and not c.idle_on(v, d)
        and not c.withdrawn_on(v, d)
    )


def site_vehicle_read(
    db: Session, p: Principal | None, v: Vehicle, ctx: Ctx | None = None, refs: Refs | None = None
) -> SiteVehRead:
    ctx = ctx or Ctx.load(db, [v])
    refs = refs or Refs(db)
    show_plate = p is None or c.names_visible(p, v.project_id)
    r, reasons = ctx.readiness(v)
    item = ctx.items.get(v.id)
    hold = c.hold_on(ctx.holds.get(v.id, []), ctx.day)
    hold_read = None
    if hold is not None:
        ca = db.scalar(
            select(CorrectiveAction).where(
                CorrectiveAction.source_id == hold.id,
                CorrectiveAction.source_type == "site_vehicle",
            )
        )
        hold_read = SiteVehHoldRead(
            check_id=hold.id,
            check_no=hold.check_no,
            set_on=hold.check_date,
            failed_items=list(hold.failed_items or []),
            ca_id=ca.id if ca else None,
            ca_ref=ca.ref if ca else None,
        )
    tc = ctx.today.get(v.id)
    warnings = []
    if c.is_site(v) and v.docs_verified_at is None and v.plate_type != PlateType.none:
        warnings.append(warn(SiteVehWarning.VEHICLE_DOCS_UNVERIFIED))
    return SiteVehRead(
        id=v.id,
        vehicle_no=v.vehicle_no,
        project_id=v.project_id,
        engagement=refs.eng_required(v.engagement_id),
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
        site_scope=v.site_scope,
        use_class=v.use_class,
        driver_group=v.driver_group,
        seats=v.seats,
        operating_card_no=v.operating_card_no,
        operating_card_expiry=v.operating_card_expiry,
        istimara_expiry=v.istimara_expiry,
        insurance_policy_no=v.insurance_policy_no,
        insurance_expiry=v.insurance_expiry,
        mvpi_expiry=v.mvpi_expiry,
        documents=doc_reads(v, ctx.day),
        docs_verified=v.docs_verified_at is not None,
        docs_verified_by=refs.user(v.docs_verified_by_user_id),
        docs_verified_at=v.docs_verified_at,
        idle_from=v.idle_from,
        idle_to=v.idle_to,
        status=v.status,
        withdrawn_on=v.withdrawn_on,
        readiness=r,
        readiness_reasons=reasons,
        phase4=SiteVehPhase4Read(
            equipment_id=item.id,
            equipment_no=item.equipment_no,
            service_status=item.service_status,
            operator_code=operator_code(item),
        )
        if item
        else None,
        hold=hold_read,
        today_check=SiteVehTodayCheck(check_id=tc.id, check_no=tc.check_no, passed=tc.passed)
        if tc
        else None,
        pre_use_required_today=required_on(c.cfg(db, v.project_id), v, ctx.day),
        warnings=warnings,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def operator_code(item: EquipmentItem | None) -> str | None:
    if item is None:
        return None
    e = cref.EQC.get(item.category)
    return e.operator_code if e else None


def _visible_engs(db: Session, p: Principal, project_id: uuid.UUID) -> set[uuid.UUID] | None:
    return c.register_engs(p, project_id)


def can_see(db: Session, p: Principal, v: Vehicle) -> bool:
    g = c.view_grant(p, v.project_id)
    engs = _visible_engs(db, p, v.project_id)
    if engs is not None and v.engagement_id not in engs:
        return False
    return c.covers_eng(db, g, v.engagement_id)


def get_row(db: Session, p: Principal, vehicle_id: uuid.UUID) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if v is None or not c.is_site(v) or not p.can_see_project(v.project_id):
        raise not_found("Site vehicle")
    c.require_live(db, v.project_id)
    if not can_see(db, p, v):
        raise not_found("Site vehicle")
    return v


def read_vehicle(db: Session, p: Principal, vehicle_id: uuid.UUID) -> SiteVehRead:
    return site_vehicle_read(db, p, get_row(db, p, vehicle_id))


def visible_vehicles(db: Session, p: Principal, project_id: uuid.UUID) -> list[Vehicle]:
    g = c.view_grant(p, project_id)
    engs = _visible_engs(db, p, project_id)
    stmt = c.site_vehicle_query(project_id)
    if engs is not None:
        stmt = stmt.where(Vehicle.engagement_id.in_(list(engs)))
    rows = list(db.scalars(stmt.order_by(Vehicle.seq)))
    return [v for v in rows if c.covers_eng(db, g, v.engagement_id)]


def list_vehicles(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    readiness: list[SiteVehReadiness] | None,
    engagement_ids: list[uuid.UUID] | None,
    use_classes: list[SiteVehUseClass] | None,
    groups: list[SiteVehDriverGroup] | None,
    docs: SiteVehDocsFilter | None,
    phase4_linked: bool | None,
    q: str | None,
    page: int,
    page_size: int,
) -> SiteVehPage:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    vs = visible_vehicles(db, p, project_id)
    ctx = Ctx.load(db, vs)
    day = ctx.day
    out = []
    for v in vs:
        if engagement_ids and v.engagement_id not in engagement_ids:
            continue
        if use_classes and v.use_class not in use_classes:
            continue
        if groups and v.driver_group not in groups:
            continue
        if phase4_linked is not None and (v.id in ctx.items) != phase4_linked:
            continue
        if readiness and ctx.readiness(v)[0] not in readiness:
            continue
        if docs == SiteVehDocsFilter.expired and not any(d < day for _, d in c.documents(v)):
            continue
        if docs == SiteVehDocsFilter.expiring_30d and not any(
            day <= d <= day + timedelta(days=EXPIRING_DAYS) for _, d in c.documents(v)
        ):
            continue
        if docs == SiteVehDocsFilter.unverified and (
            v.docs_verified_at is not None or v.plate_type == PlateType.none
        ):
            continue
        if q:
            s = q.strip().lower()
            hay = [v.vehicle_no, v.fleet_no, v.make_model]
            if c.names_visible(p, project_id) and v.plate_digits:
                hay.append(v.plate_digits)
            if not any(s in (h or "").lower() for h in hay):
                continue
        out.append(v)
    total = len(out)
    rows = out[(page - 1) * page_size : page * page_size]
    refs = Refs(db).load(
        engs=[v.engagement_id for v in rows], users=[v.docs_verified_by_user_id for v in rows]
    )
    return SiteVehPage(
        items=[site_vehicle_read(db, p, v, ctx, refs) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def summary(db: Session, p: Principal, project_id: uuid.UUID) -> SiteVehSummary:
    """Aggregates (233 including the Viewer / Client)."""
    c.project(db, p, project_id)
    g = c.view_grant(p, project_id, registers=False)
    cf = c.require_live(db, project_id)
    viewer = c.is_viewer(p, project_id)
    vs = (
        list(db.scalars(c.site_vehicle_query(project_id)))
        if viewer
        else visible_vehicles(db, p, project_id)
    )
    ctx = Ctx.load(db, vs)
    day = ctx.day
    by: dict[str, int] = {r.value: 0 for r in R}
    for v in vs:
        by[ctx.readiness(v)[0].value] += 1
    req = [v for v in vs if required_on(cf, v, day)]
    done = sum(1 for v in req if v.id in ctx.today)
    auths = [
        a
        for a in db.scalars(
            select(DriverAuthorisation).where(
                DriverAuthorisation.project_id == project_id,
                DriverAuthorisation.status == SiteVehAuthStatus.active,
            )
        )
        if viewer or c.covers_eng(db, g, a.engagement_id)
    ]
    plans = [
        j
        for j in db.scalars(
            select(JourneyPlan).where(
                JourneyPlan.project_id == project_id,
                JourneyPlan.status == SiteVehJourneyStatus.planned,
            )
        )
        if viewer or c.covers_any(db, g, [j.engagement_id, j.driver_engagement_id])
    ]
    lim = day + timedelta(days=EXPIRING_DAYS)
    return SiteVehSummary(
        project_id=project_id,
        as_of=day,
        live=cf.live,
        site_vehicles=len(vs),
        by_readiness=by,
        docs_expired=sum(1 for v in vs if any(d < day for _, d in c.documents(v))),
        docs_expiring_30d=sum(1 for v in vs if any(day <= d <= lim for _, d in c.documents(v))),
        docs_unverified=sum(
            1 for v in vs if v.docs_verified_at is None and v.plate_type != PlateType.none
        ),
        pre_use_required_today=len(req),
        pre_use_done_today=done,
        active_authorisations=len(auths),
        authorisations_expiring_30d=sum(
            1
            for a in auths
            if a.effective_valid_until is not None and a.effective_valid_until <= lim
        ),
        journeys_planned=len(plans),
        journeys_overdue=sum(1 for j in plans if overdue(j)),
    )


def overdue(j: JourneyPlan) -> bool:
    """§4.3 display flag: Planned and now > planned_arrive + 60 min."""
    return j.status == SiteVehJourneyStatus.planned and now() > j.planned_arrive + timedelta(
        minutes=60
    )


# ---- writing -------------------------------------------------------------------------------------


def _write_grant(db: Session, p: Principal, project_id: uuid.UUID, eng: uuid.UUID) -> None:
    g = p.require(project_id, C.site_vehicle_manage)
    if not c.covers_eng(db, g, eng):
        raise forbidden_error("This vehicle is outside your scope.")


def _validate_site(v: Vehicle) -> None:
    """§3.1 rules on the 7b fields."""
    if v.site_scope not in SITE_SCOPES:
        return
    if v.use_class is None:
        raise validation_error("use_class", "Required for site vehicles (list SU).")
    v.driver_group = USE_CLASS_GROUP[v.use_class]
    if v.use_class in SEATED_CLASSES:
        if v.seats is None or not 2 <= v.seats <= 60:
            raise validation_error("seats", "Seats 2–60 are required for crew buses and pickups.")
    elif v.seats is not None and not 1 <= v.seats <= 60:
        raise validation_error("seats", "1–60.")
    if c.operating_card_required(v) and (not v.operating_card_no or not v.operating_card_expiry):
        raise c.err(
            422,
            ErrorCode.OPERATING_CARD_REQUIRED,
            "An operating card (number and expiry) is required for crew buses, tippers and "
            "heavy goods vehicles on public roads (TGA).",
            "بطاقة التشغيل (الرقم وتاريخ الانتهاء) مطلوبة للحافلات والقلابات ومركبات النقل الثقيل.",
            "operating_card_no",
        )
    if v.idle_from and v.idle_to and v.idle_to < v.idle_from:
        raise validation_error("idle_to", "Must be on or after idle_from.")


def create_vehicle(
    db: Session, p: Principal, project_id: uuid.UUID, body: SiteVehCreate
) -> SiteVehRead:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    if body.site_scope not in SITE_SCOPES:
        raise validation_error("site_scope", "site or both (airside_only is Phase 2 only).")
    _write_grant(db, p, project_id, body.engagement_id)
    pveh._check_engagement(db, project_id, body.engagement_id)
    db.execute(select(func.pg_advisory_xact_lock(0x56454849)))
    seq = int(db.scalar(select(func.max(Vehicle.seq)).where(Vehicle.project_id == project_id)) or 0)
    seq += 1
    data = body.model_dump()
    data["year_built"] = data.pop("year")
    data["travel_height_m"] = data["travel_height_m"] or Decimal("2.00")
    data["max_working_height_m_agl"] = data["max_working_height_m_agl"] or data["travel_height_m"]
    v = Vehicle(
        id=uuid.uuid4(),
        seq=seq,
        vehicle_no=f"VEH-{seq:04d}",
        project_id=project_id,
        status=VehicleStatus.active,
        created_by_user_id=p.user.id,
        **data,
    )
    v.plate_letters_en = v.plate_letters_en.upper() if v.plate_letters_en else None
    v.serial_or_vin = v.serial_or_vin.strip().upper()
    pveh._validate_vehicle(db, v)
    _validate_site(v)
    db.add(v)
    db.flush()
    c.refresh(db, v)
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.vehicle,
        entity_id=v.id,
        project_id=project_id,
        after=audit.jsonable({**pveh._veh_snapshot(v), **snap(v)}),
    )
    return site_vehicle_read(db, p, v)


def update_vehicle(
    db: Session, p: Principal, vehicle_id: uuid.UUID, body: SiteVehUpdate
) -> SiteVehRead:
    v = db.get(Vehicle, vehicle_id)
    if v is None or not p.can_see_project(v.project_id):
        raise not_found("Vehicle")
    c.require_live(db, v.project_id)
    _write_grant(db, p, v.project_id, v.engagement_id)
    if v.status == VehicleStatus.withdrawn:
        raise invalid_transition("Vehicle", v.status, "edited")
    before = snap(v)
    ch = body.changes()
    for k, val in ch.items():
        setattr(v, k, val)
    if DOC_FIELDS & set(ch):
        v.docs_verified_at = None  # SV-4: changed dates need a new verification
        v.docs_verified_by_user_id = None
    pveh._validate_vehicle(db, v, check_vin=False)
    _validate_site(v)
    v.updated_by_user_id = p.user.id
    v.updated_at = now()
    db.flush()
    c.refresh(db, v)
    bf, af = audit.diff(before, snap(v))
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
    return site_vehicle_read(db, p, v)


def verify_documents(db: Session, p: Principal, vehicle_id: uuid.UUID) -> SiteVehRead:
    """SV-4: the HSE Officer (or Manager) verifies the document scans; reps cannot."""
    v = get_row(db, p, vehicle_id)
    _write_grant(db, p, v.project_id, v.engagement_id)
    if c.is_rep_only(p, v.project_id):
        raise forbidden_error("Contractor HSE Reps cannot verify documents (SV-4).")
    v.docs_verified_at = now()
    v.docs_verified_by_user_id = p.user.id
    v.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(v.project_id),
        entity_type=EntityType.vehicle,
        entity_id=v.id,
        project_id=v.project_id,
        after={"docs_verified_at": v.docs_verified_at.isoformat()},
        details={"action": "verify_documents"},
    )
    return site_vehicle_read(db, p, v)


def clear_hold(
    db: Session, p: Principal, vehicle_id: uuid.UUID, body: SiteVehClearHold
) -> SiteVehRead:
    """§4.1 defect_hold is cleared by 234 with a repair note and a passing check completed
    after the hold (409 VEHICLE_DEFECT_HOLD otherwise)."""
    v = get_row(db, p, vehicle_id)
    _write_grant(db, p, v.project_id, v.engagement_id)
    hold = c.active_hold(db, v.id)
    if hold is None:
        raise invalid_transition("Vehicle", "no defect hold", "cleared")
    passing = db.scalar(
        select(VehicleCheck)
        .where(
            VehicleCheck.vehicle_id == v.id,
            VehicleCheck.passed.is_(True),
            VehicleCheck.completed_at > hold.completed_at,
        )
        .order_by(VehicleCheck.completed_at.desc())
        .limit(1)
    )
    if passing is None:
        raise c.err(
            409,
            ErrorCode.VEHICLE_DEFECT_HOLD,
            "Record a passing pre-use check after the repair before clearing the defect hold.",
            "سجّل فحصاً يومياً ناجحاً بعد الإصلاح قبل رفع الإيقاف.",
            hold_check_no=hold.check_no,
        )
    hold.hold_cleared_at = now()
    hold.hold_cleared_by_user_id = p.user.id
    hold.hold_repair_note = body.repair_note
    hold.hold_cleared_by_check_id = passing.id
    db.flush()
    c.refresh(db, v)
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(v.project_id),
        entity_type=EntityType.vehicle_check,
        entity_id=hold.id,
        project_id=v.project_id,
        before={"hold": "set"},
        after={"hold": "cleared", "passing_check": passing.check_no},
        details={"repair_note": body.repair_note},
    )
    users = c.rep_users(db, v.project_id, v.engagement_id) | c.officer_users(db, v.project_id)
    c.send(
        db,
        users,
        NotificationKind.vehicle_defect_hold,
        f"Defect hold cleared on {v.vehicle_no} ({v.fleet_no}).",
        f"تم رفع إيقاف العيب عن المركبة {v.vehicle_no}.",
        v.project_id,
        EntityType.vehicle,
        v.id,
    )
    return site_vehicle_read(db, p, v)


def withdraw(
    db: Session, p: Principal, vehicle_id: uuid.UUID, body: SiteVehWithdraw
) -> SiteVehRead:
    v = get_row(db, p, vehicle_id)
    _write_grant(db, p, v.project_id, v.engagement_id)
    if v.status == VehicleStatus.withdrawn:
        raise invalid_transition("Vehicle", v.status, VehicleStatus.withdrawn)
    before = v.status
    # Phase 2 withdrawal semantics: any AVP of the vehicle is revoked
    s = acommon.settings(db, v.project_id)
    for a in db.scalars(select(Avp).where(Avp.vehicle_id == v.id)):
        lifecycle.revoke(db, a, CredentialReason.other, body.reason, p.user.id, s)
    v.status = VehicleStatus.withdrawn
    v.withdrawn_on = body.withdrawn_on or c.local_day()
    v.updated_at = now()
    db.flush()
    c.refresh(db, v)
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(v.project_id),
        entity_type=EntityType.vehicle,
        entity_id=v.id,
        project_id=v.project_id,
        before={"status": before.value},
        after={"status": v.status.value, "withdrawn_on": v.withdrawn_on.isoformat()},
        details={"reason": body.reason},
    )
    return site_vehicle_read(db, p, v)
