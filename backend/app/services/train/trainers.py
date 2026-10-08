"""Trainer authorisations (spec 5-training §3.3, §4.2, TA-1…TA-6) and the TA-2 / TA-3 trainer
checks used by sessions."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.train_enums import (
    CourseCategory,
    SessionStatus,
    TrainerAuthorisationAction,
    TrainerAuthorisationStatus,
    TrainerRole,
    TrainingProviderKind,
)
from app.models import (
    TrainerAuthorisation,
    TrainingCourse,
    TrainingSession,
    User,
    Worker,
)
from app.schemas.trainer_authorisations import (
    TrainerAuthorisationCreate,
    TrainerAuthorisationPage,
    TrainerAuthorisationRead,
    TrainerAuthorisationTransition,
    TrainerAuthorisationUpdate,
)
from app.services.cert import common as cc
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, active_assignments, forbidden_error
from app.services.train import common
from app.services.train import hook as thook
from app.services.train import providers as tprov
from app.services.train import reference as ref
from app.services.train import validity as tval

C = common.C
TS = TrainerAuthorisationStatus
TA = TrainerAuthorisationAction
EVIDENCE_CATS = ref.EVIDENCE_CATEGORIES


def _iso(x: Any) -> date | None:
    if x is None:
        return None
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def active_on(a: TrainerAuthorisation, d: date) -> bool:
    if not (a.valid_from <= d <= a.valid_to):
        return False
    if a.status in (TS.withdrawn, TS.expired) and (a.ended_on is None or a.ended_on <= d):
        return False
    for per in a.suspension_periods or []:
        f, t = _iso(per.get("from")), _iso(per.get("to"))
        if f is not None and f <= d and (t is None or d < t):
            return False
    return not (a.status == TS.suspended and not (a.suspension_periods or []))


def authorisation_for(
    db: Session,
    project_id: uuid.UUID,
    provider_id: uuid.UUID,
    course_code: str,
    role: TrainerRole,
    user_id: uuid.UUID | None,
    worker_id: uuid.UUID | None,
    days: list[date],
) -> TrainerAuthorisation | None:
    """TA-2: an authorisation Active on every day for the course and role."""
    q = select(TrainerAuthorisation).where(
        TrainerAuthorisation.project_id == project_id,
        TrainerAuthorisation.provider_id == provider_id,
    )
    if user_id is not None:
        q = q.where(TrainerAuthorisation.trainer_user_id == user_id)
    elif worker_id is not None:
        q = q.where(TrainerAuthorisation.trainer_worker_id == worker_id)
    else:
        return None
    for a in db.scalars(q):
        if course_code not in (a.course_codes or []) or role.value not in (a.roles or []):
            continue
        if all(active_on(a, d) for d in days):
            return a
    return None


def trainer_worker(
    db: Session, user_id: uuid.UUID | None, worker_id: uuid.UUID | None
) -> Worker | None:
    if worker_id is not None:
        return db.get(Worker, worker_id)
    if user_id is not None:
        return db.scalar(select(Worker).where(Worker.user_id == user_id))
    return None


def trained(
    db: Session,
    project_id: uuid.UUID,
    c: TrainingCourse,
    user_id: uuid.UUID | None,
    worker_id: uuid.UUID | None,
    days: list[date],
) -> bool:
    """TA-3: an in-force record of the course (or a satisfying one) on every day, for courses
    with a validity (not professional qualifications)."""
    if c.category == CourseCategory.professional_qualification or c.validity_months is None:
        return True
    w = trainer_worker(db, user_id, worker_id)
    if w is None:
        return False
    recs = thook.worker_records(db, w.id)
    ctx = thook.eval_ctx(db, project_id)
    sat = common.satisfiers(db, c.code)
    return all(tval.best(recs, sat, d, ctx).met for d in days)


# ---- reads ---------------------------------------------------------------------------------------


def _get(db: Session, auth_id: uuid.UUID) -> TrainerAuthorisation:
    a = db.get(TrainerAuthorisation, auth_id)
    if a is None:
        raise not_found("Trainer authorisation")
    return a


def _affected(db: Session, a: TrainerAuthorisation) -> int:
    n = 0
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.project_id == a.project_id,
            TrainingSession.provider_id == a.provider_id,
            TrainingSession.status.in_([SessionStatus.scheduled, SessionStatus.draft]),
        )
    ):
        uses = (a.trainer_user_id and a.trainer_user_id in (s.trainer_user_ids or [])) or (
            a.trainer_worker_id and a.trainer_worker_id in (s.trainer_worker_ids or [])
        )
        if not uses:
            continue
        days = [date.fromisoformat(x["date"]) for x in s.days]
        if s.course_code not in (a.course_codes or []) or not all(active_on(a, d) for d in days):
            n += 1
    return n


def read(db: Session, p: Principal, a: TrainerAuthorisation) -> TrainerAuthorisationRead:
    refs = Refs(db)
    pv = common.provider_or_404(db, a.provider_id)
    w = db.get(Worker, a.trainer_worker_id) if a.trainer_worker_id else None
    show = common.names(p, a.project_id)
    auth = refs.user(a.authorised_by_user_id)
    assert auth is not None  # noqa: S101
    return TrainerAuthorisationRead(
        id=a.id,
        authorisation_no=a.authorisation_no,
        project_id=a.project_id,
        trainer_user=refs.user(a.trainer_user_id),
        trainer_worker=common.worker_ref(w, show) if w else None,
        provider=common.provider_ref(pv, p, a.project_id),
        course_codes=list(a.course_codes or []),
        roles=[TrainerRole(r) for r in a.roles or []],
        basis=a.basis,
        evidence_attachment_ids=list(a.evidence_attachment_ids or []),
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        days_left=(a.valid_to - today()).days,
        status=a.status,
        status_reason=a.status_reason if common.is_hse(p, a.project_id) else None,
        authorised_by=auth,
        authorised_at=a.authorised_at,
        scheduled_sessions_affected=_affected(db, a),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def list_authorisations(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[TrainerAuthorisationStatus] | None,
    course_code: str | None,
    role: TrainerRole | None,
    provider_id: uuid.UUID | None,
    expiring_days: int | None,
) -> TrainerAuthorisationPage:
    common.visible_project(db, p, project_id)
    if (
        p.grant(project_id, C.training_record_view) is None
        and p.grant(project_id, C.trainer_authorise) is None
    ):
        raise forbidden_error()
    stmt = (
        select(TrainerAuthorisation)
        .where(TrainerAuthorisation.project_id == project_id)
        .order_by(TrainerAuthorisation.seq)
    )
    if status:
        stmt = stmt.where(TrainerAuthorisation.status.in_(status))
    if course_code:
        stmt = stmt.where(TrainerAuthorisation.course_codes.any(course_code))  # type: ignore[arg-type]
    if role:
        stmt = stmt.where(TrainerAuthorisation.roles.any(role.value))  # type: ignore[arg-type]
    if provider_id:
        stmt = stmt.where(TrainerAuthorisation.provider_id == provider_id)
    if expiring_days is not None:
        d = today()
        stmt = stmt.where(
            TrainerAuthorisation.valid_to >= d,
            TrainerAuthorisation.valid_to <= d + timedelta(days=expiring_days),
        )
    rows, total = paginate(db, stmt, page, page_size)
    return TrainerAuthorisationPage(
        items=[read(db, p, a) for a in rows], total=total, page=page, page_size=page_size
    )


def get_authorisation(db: Session, p: Principal, auth_id: uuid.UUID) -> TrainerAuthorisationRead:
    a = _get(db, auth_id)
    if not p.can_see_project(a.project_id) or (
        p.grant(a.project_id, C.training_record_view) is None
        and p.grant(a.project_id, C.trainer_authorise) is None
    ):
        raise not_found("Trainer authorisation")
    return read(db, p, a)


# ---- create / update ---------------------------------------------------------------------------


def _is_contractor_rep(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    return any(
        a.role == Role.contractor_hse_rep and a.project_id == project_id
        for a in active_assignments(db, user_id, today())
    )


def _not_authorised(en: str, ar: str) -> ApiError:
    return ApiError(422, ErrorCode.TRAINER_NOT_AUTHORISED, en, ar)


def _check(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    a: TrainerAuthorisation,
) -> None:
    s = common.settings(db, project_id)
    if (a.trainer_user_id is None) == (a.trainer_worker_id is None):
        raise validation_error("trainer_user_id", "Name exactly one trainer (user or worker).")
    if a.trainer_user_id is not None and a.trainer_user_id == p.user.id:
        raise common.sod("The authoriser cannot authorise themselves.")
    if a.trainer_worker_id is not None:
        w = common.active_worker(db, a.trainer_worker_id, "trainer_worker_id")
        if w.user_id is not None and w.user_id == p.user.id:
            raise common.sod("The authoriser cannot authorise themselves.")
    elif a.trainer_user_id is not None and db.get(User, a.trainer_user_id) is None:
        raise validation_error("trainer_user_id", "Unknown user.")
    pv = common.provider_or_404(db, a.provider_id)
    if pv.kind == TrainingProviderKind.external:
        raise validation_error("provider_id", "External trainers are named on the session (TA-5).")
    if a.valid_to < a.valid_from:
        raise validation_error("valid_to", "Must be on or after valid_from.")
    limit = common.add_months(a.valid_from, s.trainer_authorisation_max_months) - timedelta(days=1)
    if a.valid_to > limit:
        raise ApiError(
            422,
            ErrorCode.AUTHORISATION_TOO_LONG,
            f"An authorisation may run at most {s.trainer_authorisation_max_months} months "
            f"(to {limit.isoformat()}).",
            f"لا تتجاوز مدة التفويض {s.trainer_authorisation_max_months} شهراً.",
            meta={"max_valid_to": limit.isoformat()},
        )
    rep = a.trainer_user_id is not None and _is_contractor_rep(db, a.trainer_user_id, project_id)
    needs_evidence = False
    for code in a.course_codes or []:
        c = common.course(db, code)
        if c is None or not c.active or c.category == CourseCategory.induction_link:
            raise validation_error("course_codes", f"Unknown or inactive course {code}.")
        if rep:
            u = db.get(User, a.trainer_user_id)
            own = u is not None and u.employer_contractor_id == pv.contractor_id
            if (
                pv.kind != TrainingProviderKind.contractor_internal
                or not own
                or not c.contractor_delivery_allowed
            ):
                raise _not_authorised(
                    f"A Contractor HSE Rep may train only courses open to contractor delivery "
                    f"under their own training unit ({code}).",
                    "يجوز لممثل السلامة لدى المقاول التدريب فقط على الدورات المسموح بها لوحدة "
                    "التدريب التابعة لمقاوله.",
                )
        acc = tprov.acceptable(db, pv, c, a.valid_from)
        if (
            not acc.ok
            and acc.reason is not None
            and acc.reason.value not in ("PROVIDER_NOT_APPROVED",)
        ):
            raise tprov.unacceptable_error(acc)
        if c.category in EVIDENCE_CATS:
            needs_evidence = True
    if needs_evidence and not a.evidence_attachment_ids:
        raise ApiError(
            422,
            ErrorCode.TRAINER_EVIDENCE_REQUIRED,
            "Attach evidence for high-risk, PTW-role or emergency courses.",
            "أرفق المستندات للدورات عالية الخطورة أو أدوار التصاريح أو الطوارئ.",
        )


def _next_seq(db: Session, project_id: uuid.UUID) -> int:
    db.execute(select(func.pg_advisory_xact_lock(5_000_002)))
    return (
        int(
            db.scalar(
                select(func.coalesce(func.max(TrainerAuthorisation.seq), 0)).where(
                    TrainerAuthorisation.project_id == project_id
                )
            )
            or 0
        )
        + 1
    )


def create_authorisation(
    db: Session, p: Principal, project_id: uuid.UUID, body: TrainerAuthorisationCreate
) -> TrainerAuthorisationRead:
    proj = common.visible_project(db, p, project_id)
    p.require(project_id, C.trainer_authorise)
    a = TrainerAuthorisation(
        id=uuid.uuid4(),
        project_id=project_id,
        trainer_user_id=body.trainer_user_id,
        trainer_worker_id=body.trainer_worker_id,
        provider_id=body.provider_id,
        course_codes=list(dict.fromkeys(body.course_codes)),
        roles=[r.value for r in body.roles],
        basis=body.basis,
        evidence_attachment_ids=list(body.evidence_attachment_ids),
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        status=TS.active,
        suspension_periods=[],
        authorised_by_user_id=p.user.id,
        authorised_at=now(),
    )
    _check(db, p, project_id, a)
    a.seq = _next_seq(db, project_id)
    a.authorisation_no = f"TA-{proj.code}-{a.seq:04d}"
    cc.stamp(a, p, create=True)
    db.add(a)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.trainer_authorisation, a, project_id)
    return read(db, p, a)


def update_authorisation(
    db: Session, p: Principal, auth_id: uuid.UUID, body: TrainerAuthorisationUpdate
) -> TrainerAuthorisationRead:
    a = _get(db, auth_id)
    p.require(a.project_id, C.trainer_authorise)
    if a.status != TS.active:
        raise invalid_transition("Trainer authorisation", a.status, "edited")
    before = cc.snap(a)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "roles":
            v = [getattr(r, "value", r) for r in v]  # noqa: PLW2901
        setattr(a, k, v)
    _check(db, p, a.project_id, a)
    cc.stamp(a, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.trainer_authorisation, a, a.project_id, before)
    return read(db, p, a)


def transition(
    db: Session, p: Principal, auth_id: uuid.UUID, body: TrainerAuthorisationTransition
) -> TrainerAuthorisationRead:
    a = _get(db, auth_id)
    p.require(a.project_id, C.trainer_authorise)
    before = cc.snap(a)
    d = today()
    if body.action == TA.suspend:
        if a.status != TS.active:
            raise invalid_transition("Trainer authorisation", a.status, TS.suspended)
        a.status_reason = common.reason(body.reason, 10)
        a.status = TS.suspended
        a.suspension_periods = [*(a.suspension_periods or []), {"from": d.isoformat(), "to": None}]
    elif body.action == TA.reinstate:
        if a.status != TS.suspended:
            raise invalid_transition("Trainer authorisation", a.status, TS.active)
        a.status = TS.active
        a.status_reason = body.reason
        a.suspension_periods = [
            {**x, "to": d.isoformat()} if x.get("to") is None else x
            for x in a.suspension_periods or []
        ]
    else:
        if a.status not in (TS.active, TS.suspended):
            raise invalid_transition("Trainer authorisation", a.status, TS.withdrawn)
        a.status_reason = common.reason(body.reason, 10)
        a.status = TS.withdrawn
        a.ended_on = d
    cc.stamp(a, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.trainer_authorisation,
        a,
        a.project_id,
        before,
        {"action": body.action.value},
    )
    if a.status != TS.active:
        flag_sessions(db, a)
    return read(db, p, a)


def flag_sessions(db: Session, a: TrainerAuthorisation) -> int:
    """§7: Scheduled sessions whose trainer is no longer authorised → HSE Officers alerted."""
    from app.core.enums import NotificationKind  # noqa: PLC0415
    from app.services.cert import alerts  # noqa: PLC0415

    n = _affected(db, a)
    if n:
        alerts.send(
            db,
            alerts.officers(db, a.project_id),
            NotificationKind.trainer_authorisation_lapsed_sessions,
            f"{a.authorisation_no}: {n} scheduled session(s) no longer have an authorised trainer",
            f"{a.authorisation_no}: {n} جلسة مجدولة لم يعد مدربها مفوضاً",
            EntityType.trainer_authorisation,
            a.id,
            a.project_id,
            email=True,
        )
    return n
