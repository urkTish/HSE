"""PTW appointments (spec 3-ptw §3.4, §4.7, PR-1…PR-9, §7 expiry alerts)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookSubjectType
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.ptw_enums import (
    PERMIT_TERMINAL,
    AppointmentDiscipline,
    AppointmentFunction,
    AppointmentStatus,
    PermitType,
)
from app.kpi.periods import add_months
from app.models import Permit, PermitCrew, PtwAppointment, Site, Worker, Zone
from app.schemas.hse_common import ApiWarning
from app.schemas.ptw_appointments import (
    AppointmentCreate,
    AppointmentPage,
    AppointmentRead,
    AppointmentTransition,
    AppointmentUpdate,
)
from app.services import audit, notify, projects
from app.services.access import common as acommon
from app.services.access import eligibility
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, user_roles
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common
from app.services.ptw import reference as ref

C = Capability
F = AppointmentFunction
DISC = AppointmentDiscipline
ISOLATION_DISCIPLINES = {DISC.electrical_lv, DISC.electrical_hv, DISC.mechanical_process}
USER_ONLY = {F.issuer, F.area_authority, F.isolation_authority}
AREA_ROLES = {Role.hse_officer, Role.site_engineer, Role.permit_issuer}
ALERT_DAYS = (30, 14, 7, 0)


def _days_left(a: PtwAppointment) -> int:
    return (a.valid_to - today()).days


def live_permits(db: Session, a: PtwAppointment) -> list[Permit]:
    stmt = select(Permit).where(
        Permit.project_id == a.project_id, Permit.status.not_in(list(PERMIT_TERMINAL))
    )
    if a.function == F.issuer and a.holder_user_id:
        stmt = stmt.where(Permit.issuer_user_id == a.holder_user_id)
    elif a.function == F.area_authority and a.holder_user_id:
        stmt = stmt.where(Permit.area_authority_user_id == a.holder_user_id)
    else:
        crew_permits = select(PermitCrew.permit_id).where(PermitCrew.appointment_id == a.id)
        stmt = stmt.where(Permit.id.in_(crew_permits))
    return list(db.scalars(stmt.order_by(Permit.permit_no)))


def to_read(
    db: Session,
    p: Principal | None,
    a: PtwAppointment,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> AppointmentRead:
    refs = refs or Refs(db)
    names = acommon.can_see_names(p, a.project_id)
    w = db.get(Worker, a.holder_worker_id) if a.holder_worker_id else None
    appointed = refs.user(a.appointed_by_user_id)
    assert appointed is not None  # noqa: S101
    return AppointmentRead(
        id=a.id,
        project_id=a.project_id,
        appointment_no=a.appointment_no,
        function=a.function,
        discipline=a.discipline,
        holder_user=refs.user(a.holder_user_id),
        holder_worker=acommon.worker_ref(w, names) if w else None,
        permit_types=[PermitType(t) for t in a.permit_types],
        sites=[refs.site(s) for s in a.site_ids],
        zones=[z for z in (refs.zone(z) for z in a.zone_ids or []) if z],
        basis=a.basis,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        days_left=_days_left(a),
        status=a.status,
        status_reason=a.status_reason,
        appointed_by=appointed,
        live_permits=[common.permit_ref(x) for x in live_permits(db, a)],
        warnings=warnings or [],
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def appointment_ref(db: Session, p: Principal | None, a: PtwAppointment | None) -> Any:
    from app.schemas.ptw_common import AppointmentRef  # noqa: PLC0415

    if a is None:
        return None
    en = ar = None
    if a.holder_user_id:
        u = Refs(db).user(a.holder_user_id)
        en, ar = (u.full_name_en, u.full_name_ar) if u else (None, None)
    elif a.holder_worker_id and acommon.can_see_names(p, a.project_id):
        w = db.get(Worker, a.holder_worker_id)
        en, ar = (w.full_name_en, w.full_name_ar) if w else (None, None)
    return AppointmentRef(
        id=a.id,
        appointment_no=a.appointment_no,
        function=a.function,
        discipline=a.discipline,
        holder_name_en=en,
        holder_name_ar=ar,
        valid_to=a.valid_to,
        status=a.status,
    )


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if (
        p.grant(project_id, C.permit_view) is None
        and p.grant(project_id, C.ptw_appointment_manage) is None
    ):
        raise forbidden_error()


def get_row(db: Session, p: Principal, appointment_id: uuid.UUID) -> PtwAppointment:
    a = db.get(PtwAppointment, appointment_id)
    if a is None:
        raise not_found("Appointment")
    projects.get_visible(db, p, a.project_id)
    _view(p, a.project_id)
    return a


def read(db: Session, p: Principal, appointment_id: uuid.UUID) -> AppointmentRead:
    return to_read(db, p, get_row(db, p, appointment_id))


def list_appointments(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    functions: list[AppointmentFunction] | None,
    discipline: AppointmentDiscipline | None,
    statuses: list[AppointmentStatus] | None,
    holder_user_id: uuid.UUID | None,
    holder_worker_id: uuid.UUID | None,
    site_id: uuid.UUID | None,
    zone_id: uuid.UUID | None,
    expiring_within_days: int | None,
    q: str | None,
) -> AppointmentPage:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    stmt = select(PtwAppointment).where(PtwAppointment.project_id == project.id)
    if functions:
        stmt = stmt.where(PtwAppointment.function.in_(functions))
    if discipline:
        stmt = stmt.where(PtwAppointment.discipline == discipline)
    if statuses:
        stmt = stmt.where(PtwAppointment.status.in_(statuses))
    if holder_user_id:
        stmt = stmt.where(PtwAppointment.holder_user_id == holder_user_id)
    if holder_worker_id:
        stmt = stmt.where(PtwAppointment.holder_worker_id == holder_worker_id)
    if site_id:
        stmt = stmt.where(PtwAppointment.site_ids.contains([site_id]))
    if zone_id:
        stmt = stmt.where(
            or_(PtwAppointment.zone_ids == [], PtwAppointment.zone_ids.contains([zone_id]))
        )
    if expiring_within_days is not None:
        stmt = stmt.where(
            PtwAppointment.status == AppointmentStatus.active,
            PtwAppointment.valid_to <= today() + timedelta(days=expiring_within_days),
        )
    if q:
        stmt = stmt.where(PtwAppointment.appointment_no.ilike(f"%{q.strip()}%"))
    rows, total = paginate(db, stmt.order_by(PtwAppointment.seq), page, size)
    refs = Refs(db)
    return AppointmentPage(
        items=[to_read(db, p, a, refs) for a in rows], total=total, page=page, page_size=size
    )


# ---- writes --------------------------------------------------------------------------------------


def _require_manage(p: Principal, project_id: uuid.UUID, function: AppointmentFunction) -> None:
    p.require(project_id, C.ptw_appointment_manage)
    if function == F.issuer and not p.is_manager:
        raise ApiError(
            403,
            ErrorCode.ISSUER_APPOINTMENT_MANAGER_ONLY,
            "Issuer appointments are made by the HSE Manager only (PR-2).",
            "تعيينات مُصدِري التصاريح يجريها مدير السلامة فقط.",
        )


def _check_scope(
    db: Session, project_id: uuid.UUID, site_ids: list[uuid.UUID], zone_ids: list[uuid.UUID]
) -> None:
    for sid in site_ids:
        s = db.get(Site, sid)
        if s is None or s.project_id != project_id:
            raise validation_error("site_ids", "Every site must belong to the project.")
    for zid in zone_ids:
        z = db.get(Zone, zid)
        if z is None or z.site_id not in site_ids:
            raise validation_error("zone_ids", "Every zone must belong to one of the sites.")


def _check_validity(db: Session, project_id: uuid.UUID, vf: date, vt: date) -> None:
    months = common.settings(db, project_id).appointment_max_months
    if vt < vf:
        raise validation_error("valid_to", "valid_to must be on or after valid_from.")
    if vt > add_months(vf, months):
        raise validation_error(
            "valid_to", f"An appointment may last at most {months} months (PR-7)."
        )


def _hook_warnings(db: Session, a: PtwAppointment) -> list[ApiWarning]:
    """PR-9 / HK3-2 appointment hooks (issuer PTW-ISSUER, isolation authority LOTO-AUTHORITY)."""
    hooks_ = ref.APPOINTMENT_HOOKS.get(a.function, ())
    if not hooks_:
        return []
    worker_id = a.holder_worker_id
    if worker_id is None and a.holder_user_id:
        worker_id = db.scalar(select(Worker.id).where(Worker.user_id == a.holder_user_id))
    s = acommon.settings(db, a.project_id)
    out = []
    for kind, code in hooks_:
        it = eligibility.hook_item(
            db, HookSubjectType.worker, worker_id or a.id, kind, code, now(), s
        )
        if it.status.value in ("warn", "not_met", "not_evaluated", "expiring"):
            en, ar = it.message or ("Requirement not met", "متطلب غير مستوفى")
            out.append(
                ApiWarning(code="HOOK_NOT_AVAILABLE", message=f"{code}: {en}", message_ar=ar)
            )
    return out


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: AppointmentCreate
) -> AppointmentRead:
    project = projects.get_visible(db, p, project_id)
    _require_manage(p, project.id, body.function)
    if (body.holder_user_id is None) == (body.holder_worker_id is None):
        raise validation_error("holder_user_id", "Give exactly one holder (user or worker).")
    if body.function in USER_ONLY and body.holder_user_id is None:
        raise validation_error(
            "holder_user_id", f"A {body.function.value} appointment needs a user holder."
        )
    if body.function == F.isolation_authority:
        if body.discipline not in ISOLATION_DISCIPLINES:
            raise validation_error(
                "discipline", "Isolation authorities need an LV/HV/mechanical discipline."
            )
    elif body.function == F.authorised_person:
        if body.discipline is None or body.discipline in {DISC.mechanical_process}:
            raise validation_error("discipline", "Authorised persons need a discipline.")
    elif body.discipline is not None:
        raise validation_error(
            "discipline", "Only isolation and authorised-person appointments carry a discipline."
        )
    if body.function == F.area_authority and body.holder_user_id:
        roles = user_roles(db, body.holder_user_id, project.id)
        if not roles & AREA_ROLES:
            raise validation_error(
                "holder_user_id",
                "Area authorities must be HSE Officers, site engineers or permit issuers on "
                "the project (PR-3).",
            )
    if body.holder_worker_id and db.get(Worker, body.holder_worker_id) is None:
        raise validation_error("holder_worker_id", "Unknown worker.")
    _check_scope(db, project.id, body.site_ids, body.zone_ids)
    _check_validity(db, project.id, body.valid_from, body.valid_to)
    seq = (
        db.scalar(
            select(PtwAppointment.seq)
            .where(PtwAppointment.project_id == project.id)
            .order_by(PtwAppointment.seq.desc())
            .limit(1)
        )
        or 0
    ) + 1
    a = PtwAppointment(
        id=uuid.uuid4(),
        project_id=project.id,
        seq=seq,
        appointment_no=f"APT-{project.code}-{seq:04d}",
        function=body.function,
        discipline=body.discipline,
        holder_user_id=body.holder_user_id,
        holder_worker_id=body.holder_worker_id,
        permit_types=[t.value for t in body.permit_types],
        site_ids=list(body.site_ids),
        zone_ids=list(body.zone_ids),
        basis=body.basis.strip(),
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        appointed_by_user_id=p.user.id,
        status=AppointmentStatus.active,
        alerts_sent=[],
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.ptw_appointment,
        entity_id=a.id,
        project_id=project.id,
        after=_snap(a),
    )
    from app.services.hse_common import id_warnings  # noqa: PLC0415

    return to_read(db, p, a, warnings=_hook_warnings(db, a) + id_warnings(basis=a.basis))


def _snap(a: PtwAppointment) -> dict[str, Any]:
    return acommon.jsonable(
        {
            "appointment_no": a.appointment_no,
            "function": a.function.value,
            "discipline": a.discipline.value if a.discipline else None,
            "permit_types": list(a.permit_types),
            "site_ids": list(a.site_ids),
            "zone_ids": list(a.zone_ids or []),
            "basis": a.basis,
            "valid_from": a.valid_from,
            "valid_to": a.valid_to,
            "status": a.status.value,
        }
    )


def update(
    db: Session, p: Principal, appointment_id: uuid.UUID, body: AppointmentUpdate
) -> AppointmentRead:
    a = get_row(db, p, appointment_id)
    _require_manage(p, a.project_id, a.function)
    if a.status in (AppointmentStatus.revoked, AppointmentStatus.expired):
        raise invalid_transition("appointment", a.status, "update")
    before = _snap(a)
    ch = body.changes()
    if "permit_types" in ch:
        ch["permit_types"] = [getattr(t, "value", t) for t in ch["permit_types"]]
    sites = ch.get("site_ids", a.site_ids)
    zones = ch.get("zone_ids", a.zone_ids or [])
    _check_scope(db, a.project_id, sites, zones)
    _check_validity(db, a.project_id, a.valid_from, ch.get("valid_to", a.valid_to))
    for k, v in ch.items():
        setattr(a, k, v)
    a.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _snap(a))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.ptw_appointment,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
        _reevaluate(db, a)
    return to_read(db, p, a)


TRANSITIONS = {
    AppointmentStatus.active: {AppointmentStatus.suspended, AppointmentStatus.revoked},
    AppointmentStatus.suspended: {AppointmentStatus.active, AppointmentStatus.revoked},
}


def transition(
    db: Session, p: Principal, appointment_id: uuid.UUID, body: AppointmentTransition
) -> AppointmentRead:
    a = get_row(db, p, appointment_id)
    _require_manage(p, a.project_id, a.function)
    to = body.to_status
    if to not in TRANSITIONS.get(a.status, set()):
        raise invalid_transition("appointment", a.status, to)
    if to in (AppointmentStatus.suspended, AppointmentStatus.revoked) and not body.reason:
        raise validation_error("reason", "A reason of at least 10 characters is required.")
    if to == AppointmentStatus.active and a.valid_to < today():
        raise validation_error("to_status", "The appointment has passed its valid_to date.")
    before = a.status
    a.status = to
    a.status_reason = body.reason
    a.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(a.project_id),
        entity_type=EntityType.ptw_appointment,
        entity_id=a.id,
        project_id=a.project_id,
        before={"status": before.value},
        after={"status": to.value},
        details={"reason": body.reason},
    )
    _reevaluate(db, a)
    return to_read(db, p, a)


def _reevaluate(db: Session, a: PtwAppointment) -> None:
    """PR-8: every non-terminal permit where the holder acts is re-evaluated."""
    from app.services.ptw import evaluation  # noqa: PLC0415

    for x in live_permits(db, a):
        evaluation.refresh(db, x)


# ---- job -----------------------------------------------------------------------------------------


def daily_job(db: Session, at: datetime | None = None) -> int:
    """§4.7 expiry (today > valid_to) and §7 alerts 30 / 14 / 7 / 0 days before valid_to."""
    at = at or now()
    day = acommon.local_day(at)
    n = 0
    for a in db.scalars(
        select(PtwAppointment).where(
            PtwAppointment.status.in_([AppointmentStatus.active, AppointmentStatus.suspended])
        )
    ):
        if day > a.valid_to:
            a.status = AppointmentStatus.expired
            audit.record(
                db,
                AuditAction.status_change,
                audit.SYSTEM,
                entity_type=EntityType.ptw_appointment,
                entity_id=a.id,
                project_id=a.project_id,
                before={"status": "active"},
                after={"status": "expired"},
            )
            _reevaluate(db, a)
            n += 1
            continue
        left = (a.valid_to - day).days
        for d in ALERT_DAYS:
            key = f"expiry_{d}"
            if left <= d and key not in (a.alerts_sent or []):
                users = {a.appointed_by_user_id}
                if a.holder_user_id:
                    users.add(a.holder_user_id)
                if a.function == F.issuer:
                    users.update(notify.managers(db))
                notify.notify(
                    db,
                    users,
                    NotificationKind.ptw_appointment_expiry,
                    f"{a.appointment_no} ({a.function.value}) expires on {a.valid_to} ({left} d)",
                    f"ينتهي التعيين {a.appointment_no} في {a.valid_to} ({left} يوم)",
                    None,
                    None,
                    EntityType.ptw_appointment,
                    a.id,
                    a.project_id,
                )
                a.alerts_sent = [
                    *(a.alerts_sent or []),
                    *[f"expiry_{x}" for x in ALERT_DAYS if x >= d],
                ]
                n += 1
                break
    db.flush()
    return n
