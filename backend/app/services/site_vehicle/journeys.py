"""7b.4 Journey plan — minimal form, **prototype** (spec 7b-fleet-driver §3.4, §4.3, JM-1, JM-2).
No check-ins, no escalation, no driving-time engine; "Overdue" is a list flag only and sends no
notification."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import VehicleStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, UserStatus
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.site_vehicle_enums import (
    NOT_READY_FOR_JOURNEY,
    SiteVehJourneyStatus,
    SiteVehWarning,
)
from app.models import JourneyPlan, User, Vehicle, Worker
from app.schemas.hse_common import ApiWarning
from app.schemas.site_vehicle import (
    SiteVehJourneyArrive,
    SiteVehJourneyCancel,
    SiteVehJourneyCreate,
    SiteVehJourneyHint,
    SiteVehJourneyHintInput,
    SiteVehJourneyPage,
    SiteVehJourneyRead,
)
from app.services.access.common import at_local
from app.services.common import invalid_transition
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.site_vehicle import checks as sc
from app.services.site_vehicle import common as c
from app.services.site_vehicle import vehicles as sv
from app.services.site_vehicle.reference import WARNING

C = Capability
J = SiteVehJourneyStatus


# ---- JM-1 hint -----------------------------------------------------------------------------------


def hint_reasons(cf: c.Cfg, km: int, depart: datetime, arrive: datetime) -> list[str]:
    out = []
    if km >= int(cf["journey_hint_km"]):
        out.append("distance")
    n_from, n_to = cf.night
    d0 = c.local_day(depart) - timedelta(days=1)
    d1 = c.local_day(arrive)
    d = d0
    while d <= d1:
        start = at_local(d, n_from)
        end = at_local(d + timedelta(days=1) if n_to <= n_from else d, n_to)
        if depart < end and arrive > start:
            out.append("night")
            break
        d += timedelta(days=1)
    return out


def hint(
    db: Session, p: Principal, project_id: uuid.UUID, body: SiteVehJourneyHintInput
) -> SiteVehJourneyHint:
    c.project(db, p, project_id)
    cf = c.require_live(db, project_id)
    c.view_grant(p, project_id)
    reasons = hint_reasons(cf, body.distance_km, body.planned_depart, body.planned_arrive)
    en, ar = WARNING[SiteVehWarning.JOURNEY_PLAN_RECOMMENDED]
    return SiteVehJourneyHint(
        recommended=bool(reasons),
        reasons=reasons,
        message_en=en if reasons else None,
        message_ar=ar if reasons else None,
    )


# ---- reading -------------------------------------------------------------------------------------


def plan_read(
    db: Session,
    p: Principal | None,
    j: JourneyPlan,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> SiteVehJourneyRead:
    refs = refs or Refs(db)
    v = db.get(Vehicle, j.vehicle_id)
    w = db.get(Worker, j.driver_worker_id)
    assert v is not None and w is not None  # noqa: S101
    names = p is None or c.names_visible(p, j.project_id)
    return SiteVehJourneyRead(
        id=j.id,
        plan_no=j.plan_no,
        project_id=j.project_id,
        vehicle=sv.vehicle_ref(v),
        engagement=refs.eng(j.engagement_id),
        driver=c.worker_ref(w, names),
        driver_group=j.driver_group,
        driver_authorised=j.driver_authorised,
        passengers=j.passengers,
        origin=j.origin,
        destination=j.destination,
        distance_km=j.distance_km,
        planned_depart=j.planned_depart,
        planned_arrive=j.planned_arrive,
        contact=refs.user(j.contact_user_id) if names else None,
        notes=j.notes,
        hint_recommended=j.hint_recommended,
        status=j.status,
        overdue=sv.overdue(j),
        arrived_at=j.arrived_at,
        cancelled_reason=j.cancelled_reason,
        warnings=warnings if warnings is not None else [ApiWarning(**x) for x in j.warnings or []],
        created_at=j.created_at,
        updated_at=j.updated_at,
    )


def _visible(db: Session, p: Principal, j: JourneyPlan) -> bool:
    g = c.view_grant(p, j.project_id)
    return c.covers_any(db, g, [j.engagement_id, j.driver_engagement_id])


def _get(db: Session, p: Principal, plan_id: uuid.UUID) -> JourneyPlan:
    j = db.get(JourneyPlan, plan_id)
    if j is None or not p.can_see_project(j.project_id):
        raise not_found("Journey plan")
    c.require_live(db, j.project_id)
    if not _visible(db, p, j):
        raise not_found("Journey plan")
    return j


def read_plan(db: Session, p: Principal, plan_id: uuid.UUID) -> SiteVehJourneyRead:
    return plan_read(db, p, _get(db, p, plan_id))


def list_plans(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[SiteVehJourneyStatus] | None,
    overdue: bool | None,
    date_from: date | None,
    date_to: date | None,
    vehicle_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> SiteVehJourneyPage:
    c.project(db, p, project_id)
    c.require_live(db, project_id)
    c.view_grant(p, project_id)
    stmt = select(JourneyPlan).where(JourneyPlan.project_id == project_id)
    if statuses:
        stmt = stmt.where(JourneyPlan.status.in_(statuses))
    if date_from:
        stmt = stmt.where(JourneyPlan.depart_date >= date_from)
    if date_to:
        stmt = stmt.where(JourneyPlan.depart_date <= date_to)
    if vehicle_id:
        stmt = stmt.where(JourneyPlan.vehicle_id == vehicle_id)
    rows = [j for j in db.scalars(stmt.order_by(JourneyPlan.planned_depart.desc()))
            if _visible(db, p, j)]  # fmt: skip
    if overdue is not None:
        rows = [j for j in rows if sv.overdue(j) == overdue]
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    refs = Refs(db).load(
        engs=[j.engagement_id for j in rows], users=[j.contact_user_id for j in rows]
    )
    return SiteVehJourneyPage(
        items=[plan_read(db, p, j, refs) for j in rows], total=total, page=page, page_size=page_size
    )


# ---- writing -------------------------------------------------------------------------------------


def next_plan_no(db: Session, project_id: uuid.UUID, year: int) -> tuple[int, str]:
    c.lock_project(db, project_id)
    n = int(
        db.scalar(
            select(func.max(JourneyPlan.seq)).where(
                JourneyPlan.project_id == project_id, JourneyPlan.year == year
            )
        )
        or 0
    )
    return n + 1, f"JP-{c.pcode(db, project_id)}-{year}-{n + 1:04d}"


def create_plan(
    db: Session, p: Principal, project_id: uuid.UUID, body: SiteVehJourneyCreate
) -> SiteVehJourneyRead:
    c.project(db, p, project_id)
    cf = c.require_live(db, project_id)
    g = p.require(project_id, C.pre_use_record)
    v = db.get(Vehicle, body.vehicle_id)
    if v is None or v.project_id != project_id or not c.is_site(v):
        raise validation_error("vehicle_id", "Not a site vehicle of this project.")
    dep = sc.driver_deployment(db, project_id, body.driver_worker_id)
    if not c.covers_any(db, g, [v.engagement_id, dep.engagement_id]):
        raise forbidden_error("This vehicle and driver are outside your scope.")
    if body.planned_arrive <= body.planned_depart:
        raise c.err(
            422,
            ErrorCode.JOURNEY_TIMES_INVALID,
            "The planned arrival must be after the departure.",
            "يجب أن يكون وقت الوصول المخطط بعد وقت المغادرة.",
            "planned_arrive",
        )
    d = c.local_day(body.planned_depart)
    r, reasons = c.readiness(db, v, max(d, c.local_day()))
    if r in NOT_READY_FOR_JOURNEY or v.status == VehicleStatus.withdrawn:
        raise c.err(
            409,
            ErrorCode.VEHICLE_NOT_READY,
            f"The vehicle is not ready ({r.value}).",
            "المركبة غير جاهزة.",
            None,
            readiness=r.value,
            reasons=reasons,
        )
    if v.seats is not None and body.passengers > v.seats - 1:
        raise c.err(
            422,
            ErrorCode.PASSENGERS_EXCEED_SEATS,
            f"At most {v.seats - 1} passengers (seats − 1).",
            "عدد الركاب يتجاوز المقاعد المتاحة.",
            "passengers",
            max=v.seats - 1,
        )
    contact = db.get(User, body.contact_user_id)
    if contact is None or contact.status != UserStatus.active:
        raise validation_error("contact_user_id", "Unknown or inactive user.")
    w = db.get(Worker, body.driver_worker_id)
    if w is not None and w.user_id == contact.id:
        raise c.err(
            422,
            ErrorCode.JOURNEY_CONTACT_IS_DRIVER,
            "The contact person cannot be the driver.",
            "لا يمكن أن تكون جهة الاتصال هي السائق.",
            "contact_user_id",
        )
    auth, warns = sc.driver_check(db, cf, project_id, body.driver_worker_id, v, d)
    reasons_hint = hint_reasons(cf, body.distance_km, body.planned_depart, body.planned_arrive)
    if reasons_hint:
        warns.append(sv.warn(SiteVehWarning.JOURNEY_PLAN_RECOMMENDED))
    year = d.year
    seq, no = next_plan_no(db, project_id, year)
    j = JourneyPlan(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        seq=seq,
        plan_no=no,
        vehicle_id=v.id,
        engagement_id=v.engagement_id,
        driver_worker_id=body.driver_worker_id,
        driver_engagement_id=dep.engagement_id,
        driver_group=v.driver_group,
        driver_authorised=auth is not None,
        authorisation_id=auth.id if auth else None,
        passengers=body.passengers,
        origin=body.origin,
        destination=body.destination,
        distance_km=body.distance_km,
        planned_depart=body.planned_depart,
        planned_arrive=body.planned_arrive,
        depart_date=d,
        contact_user_id=contact.id,
        notes=body.notes,
        hint_recommended=bool(reasons_hint),
        status=J.planned,
        warnings=[x.model_dump() for x in warns],
        created_by_user_id=p.user.id,
    )
    db.add(j)
    db.flush()
    c.record(db, p, AuditAction.create, EntityType.journey_plan, j, project_id)
    return plan_read(db, p, j, warnings=warns)


def _write(db: Session, p: Principal, plan_id: uuid.UUID) -> JourneyPlan:
    j = _get(db, p, plan_id)
    g = p.require(j.project_id, C.pre_use_record)
    if not c.covers_any(db, g, [j.engagement_id, j.driver_engagement_id]):
        raise forbidden_error()
    return j


def arrive(
    db: Session, p: Principal, plan_id: uuid.UUID, body: SiteVehJourneyArrive
) -> SiteVehJourneyRead:
    j = _write(db, p, plan_id)
    if j.status != J.planned:
        raise invalid_transition("Journey plan", j.status, J.arrived)
    at = body.arrived_at or now()
    if at > now() or at < j.planned_depart:
        raise validation_error("arrived_at", "Between the departure and now.")
    before = {"status": j.status.value}
    j.status = J.arrived
    j.arrived_at = at
    j.updated_at = now()
    j.updated_by_user_id = p.user.id
    db.flush()
    c.record(db, p, AuditAction.status_change, EntityType.journey_plan, j, j.project_id, before)
    return plan_read(db, p, j)


def cancel(
    db: Session, p: Principal, plan_id: uuid.UUID, body: SiteVehJourneyCancel
) -> SiteVehJourneyRead:
    j = _write(db, p, plan_id)
    if j.status != J.planned:
        raise invalid_transition("Journey plan", j.status, J.cancelled)
    before = {"status": j.status.value}
    j.status = J.cancelled
    j.cancelled_reason = body.reason
    j.updated_at = now()
    j.updated_by_user_id = p.user.id
    db.flush()
    c.record(db, p, AuditAction.status_change, EntityType.journey_plan, j, j.project_id, before)
    return plan_read(db, p, j)
