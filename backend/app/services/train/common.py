"""Helpers shared by the Phase 5 services (spec 5-training): the catalogue (built-ins created on
first use), scope checks on deployments, refs, settings and numbering."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, WorkerPersonType, WorkerStatus
from app.core.clock import now, today
from app.core.enums import Capability, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.train_enums import (
    CourseCategory,
    TrainingProviderKind,
    TrainingProviderStatus,
)
from app.models import (
    Deployment,
    HseSettings,
    Project,
    TrainingCourse,
    TrainingProvider,
    TrainingRecord,
    TrainingSession,
    TrainingSettings,
    Worker,
)
from app.schemas.training_common import (
    CourseRef,
    TrainingProviderRef,
    TrainingRecordRef,
    TrainingSessionRef,
)
from app.services.access import common as acommon
from app.services.permissions import Grant, Principal, forbidden_error
from app.services.train import reference as ref

C = Capability
CONTRACTOR_ROLES = frozenset({Role.contractor_hse_rep, Role.permit_receiver})
LIVE_DEP = (DeploymentStatus.mobilised, DeploymentStatus.pending_induction)

# ---- catalogue ----------------------------------------------------------------------------------


def ensure_catalogue(db: Session) -> None:
    """The §3.15 catalogue rows exist (created once, then edited by the HSE Manager)."""
    if db.info.get("train_catalogue_ok"):
        return
    have = set(db.scalars(select(TrainingCourse.code)))
    added = False
    for c in ref.CATALOGUE:
        if c.code in have:
            continue
        db.add(
            TrainingCourse(
                id=uuid.uuid4(),
                code=c.code,
                name_en=c.name_en,
                name_ar=c.name_ar,
                category=c.category,
                induction_type=c.induction_type,
                induction_project_codes={},
                validity_months=c.validity,
                min_duration_hours=Decimal(c.hours) if c.hours else None,
                max_class_size=c.max_class_size,
                delivery_modes=[m.value for m in c.delivery_modes],
                theory_required=c.theory if c.category != CourseCategory.induction_link else False,
                pass_mark_pct=80
                if c.theory and c.category != CourseCategory.induction_link
                else None,
                practical_required=c.practical,
                prerequisite_codes=list(c.prereq),
                satisfies=list(c.satisfies),
                renewal_course_code=c.renewal,
                renews_only=c.renews_only,
                internal_allowed=c.internal and not c.bodies,
                contractor_delivery_allowed=c.contractor and not c.bodies,
                accreditation_bodies_required=[b.value for b in c.bodies],
                languages_offered=[x.value for x in c.languages],
                active=True,
                seeded=True,
                seed_fake=False,
            )
        )
        added = True
    if added:
        db.flush()
        _link_inductions(db)
    db.info["train_catalogue_ok"] = True


def _link_inductions(db: Session) -> None:
    """CC-7 zone_specific links: project id → Phase 2 course code (by project code)."""
    for c in ref.CATALOGUE:
        if not c.induction_codes:
            continue
        row = db.scalar(select(TrainingCourse).where(TrainingCourse.code == c.code))
        if row is None:
            continue
        codes = dict(row.induction_project_codes or {})
        for pcode, icode in c.induction_codes.items():
            pid = db.scalar(select(Project.id).where(Project.code == pcode))
            if pid is not None:
                codes[str(pid)] = icode
        row.induction_project_codes = codes
    db.flush()


def courses(db: Session) -> dict[str, TrainingCourse]:
    ensure_catalogue(db)
    cache: dict[str, TrainingCourse] | None = db.info.get("train_courses")
    if cache is None:
        cache = {c.code: c for c in db.scalars(select(TrainingCourse))}
        db.info["train_courses"] = cache
    return cache


def clear_cache(db: Session) -> None:
    for k in ("train_courses", "train_satisfiers", "train_hook_codes", "train_settings"):
        db.info.pop(k, None)


def course(db: Session, code: str) -> TrainingCourse | None:
    return courses(db).get(code)


def course_or_404(db: Session, code: str) -> TrainingCourse:
    c = course(db, code)
    if c is None:
        raise not_found("Course")
    return c


def satisfiers(db: Session, code: str) -> list[str]:
    """CC-6: the code itself and every course whose `satisfies` lists it (one level)."""
    cache: dict[str, list[str]] = db.info.setdefault("train_satisfiers", {})
    if code not in cache:
        out = [code]
        for c in courses(db).values():
            if code in (c.satisfies or []) and c.code not in out:
                out.append(c.code)
        cache[code] = out
    return cache[code]


def course_ref(c: TrainingCourse) -> CourseRef:
    return CourseRef(code=c.code, name_en=c.name_en, name_ar=c.name_ar, category=c.category)


def course_ref_code(db: Session, code: str) -> CourseRef:
    c = course(db, code)
    if c is None:
        return CourseRef(code=code, name_en=code, name_ar=code, category=CourseCategory.awareness)
    return course_ref(c)


# ---- settings -----------------------------------------------------------------------------------


def settings(db: Session, project_id: uuid.UUID) -> TrainingSettings:
    cache: dict[uuid.UUID, TrainingSettings] = db.info.setdefault("train_settings", {})
    s = cache.get(project_id) or db.get(TrainingSettings, project_id)
    if s is None:
        s = TrainingSettings(project_id=project_id)
        for col in TrainingSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                setattr(s, col.key, arg(None) if callable(arg) else arg)
        s.course_validity_months = {}
        s.language_block_categories = [c.value for c in ref.DEFAULT_LANGUAGE_BLOCK]
        s.training_hook_critical_codes = list(ref.DEFAULT_CRITICAL)
        s.alert_schedule_long_days = list(ref.ALERT_SCHEDULE_LONG)
        db.add(s)
        db.flush()
    cache[project_id] = s
    return s


def critical_codes(s: TrainingSettings) -> set[str]:
    return set(s.training_hook_critical_codes or ref.DEFAULT_CRITICAL)


def register_from(db: Session, project_id: uuid.UUID) -> date | None:
    hs = db.get(HseSettings, project_id)
    return hs.training_register_from if hs else None


def effective_validity_months(
    c: TrainingCourse, s: TrainingSettings | None
) -> tuple[int | None, bool]:
    """§6.1 validity_months(course, project) and whether the project override limits it."""
    base = c.validity_months
    ov = (s.course_validity_months or {}).get(c.code) if s is not None else None
    if ov is None:
        return base, False
    ov = int(ov)
    if base is None or ov < base:
        return ov, True
    return base, False


def effective_pass_mark(c: TrainingCourse, s: TrainingSettings) -> int:
    return max(c.pass_mark_pct or 0, s.training_pass_mark_pct)


# ---- roles and scope ----------------------------------------------------------------------------


def roles_on(p: Principal, project_id: uuid.UUID | None) -> set[Role]:
    if p.is_manager:
        return {Role.hse_manager}
    scope = p.projects.get(project_id) if project_id else None
    return scope.roles if scope else set()


def is_hse(p: Principal, project_id: uuid.UUID | None = None) -> bool:
    """P5-4: HSE Manager / HSE Officer (on the project; anywhere when project_id is None)."""
    if p.is_manager:
        return True
    if project_id is None:
        return any(Role.hse_officer in s.roles for s in p.projects.values())
    return Role.hse_officer in roles_on(p, project_id)


def contractor_only(p: Principal, project_id: uuid.UUID | None) -> bool:
    roles = roles_on(p, project_id)
    return bool(roles) and roles <= CONTRACTOR_ROLES


def viewer_only(p: Principal, project_id: uuid.UUID | None) -> bool:
    return roles_on(p, project_id) == {Role.viewer_client}


def covers_dep(g: Grant | None, dep: Deployment | None) -> bool:
    if g is None:
        return False
    if g.engagement_ids is None and g.site_ids is None:
        return True
    if dep is None:
        return False
    if g.engagement_ids is not None and dep.engagement_id not in g.engagement_ids:
        return False
    return g.site_ids is None or bool(set(dep.site_ids or []) & set(g.site_ids))


def need(p: Principal, project_id: uuid.UUID, cap: Capability, write: bool = True) -> Grant:
    if write:
        return p.require(project_id, cap)
    g = p.grant(project_id, cap)
    if g is None:
        raise forbidden_error()
    return g


def project(db: Session, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None:
        raise not_found("Project")
    return x


def visible_project(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None or not p.can_see_project(project_id):
        raise not_found("Project")
    return x


# ---- workers and deployments --------------------------------------------------------------------


def worker(db: Session, worker_id: uuid.UUID) -> Worker:
    w = db.get(Worker, worker_id)
    if w is None:
        raise not_found("Worker")
    return w


def active_worker(db: Session, worker_id: uuid.UUID, field: str = "worker_id") -> Worker:
    w = worker(db, worker_id)
    if w.status == WorkerStatus.anonymised:
        raise validation_error(field, "This worker record is anonymised.")
    return w


def deployment(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID) -> Deployment | None:
    """The open deployment on the project, else the latest one."""
    rows = list(
        db.scalars(
            select(Deployment)
            .where(Deployment.worker_id == worker_id, Deployment.project_id == project_id)
            .order_by(Deployment.created_at.desc())
        )
    )
    for d in rows:
        if d.status != DeploymentStatus.demobilised:
            return d
    return rows[0] if rows else None


def deployment_on(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, d: date
) -> Deployment | None:
    for dep in db.scalars(
        select(Deployment).where(
            Deployment.worker_id == worker_id, Deployment.project_id == project_id
        )
    ):
        if dep.mobilised_on <= d and (dep.demobilised_on is None or dep.demobilised_on > d):
            return dep
    return None


def mobilised_on(dep: Deployment, d: date) -> bool:
    """Deployment Mobilised at local date d (end of day)."""
    if dep.status == DeploymentStatus.pending_induction:
        return False
    if dep.mobilised_on > d:
        return False
    return dep.demobilised_on is None or dep.demobilised_on > d


def worker_projects(db: Session, worker_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Deployment.project_id).where(
                Deployment.worker_id == worker_id, Deployment.status != DeploymentStatus.demobilised
            )
        )
    )


def is_contractor_worker(w: Worker) -> bool:
    return w.person_type == WorkerPersonType.contractor_worker


def can_see_worker(
    db: Session, p: Principal, w: Worker, cap: Capability = C.training_record_view
) -> bool:
    """A worker's training is visible when the caller holds `cap` on a project where the worker
    has a deployment covered by the grant (TR-16, C scope for contractor roles)."""
    if p.is_manager:
        return True
    for dep in db.scalars(select(Deployment).where(Deployment.worker_id == w.id)):
        if covers_dep(p.grant(dep.project_id, cap), dep):
            return True
    return False


def names(p: Principal | None, project_id: uuid.UUID | None) -> bool:
    return acommon.can_see_names(p, project_id)


def worker_ref(w: Worker, show: bool) -> Any:
    return acommon.worker_ref(w, show)


# ---- providers ----------------------------------------------------------------------------------


def provider_or_404(db: Session, provider_id: uuid.UUID) -> TrainingProvider:
    x = db.get(TrainingProvider, provider_id)
    if x is None:
        raise not_found("Training provider")
    return x


def provider_accepted(pv: TrainingProvider) -> bool:
    return pv.status == TrainingProviderStatus.approved


def provider_ref(
    pv: TrainingProvider, p: Principal | None = None, project_id: uuid.UUID | None = None
) -> TrainingProviderRef:
    hse = p is None or is_hse(p, project_id) or not contractor_only(p, project_id)
    return TrainingProviderRef(
        id=pv.id,
        provider_code=pv.provider_code,
        legal_name_en=pv.legal_name_en,
        legal_name_ar=pv.legal_name_ar,
        kind=pv.kind,
        status=pv.status if hse else None,
        accepted_for_use=provider_accepted(pv),
    )


def is_internalish(pv: TrainingProvider) -> bool:
    return pv.kind in (TrainingProviderKind.internal, TrainingProviderKind.contractor_internal)


# ---- refs ---------------------------------------------------------------------------------------


def session_ref(s: TrainingSession) -> TrainingSessionRef:
    return TrainingSessionRef(
        id=s.id,
        session_no=s.session_no,
        course_code=s.course_code,
        status=s.status,
        first_day=s.first_day,
        last_day=s.last_day,
    )


def record_ref(r: TrainingRecord, valid_until: date | None = None) -> TrainingRecordRef:
    return TrainingRecordRef(
        id=r.id,
        record_no=r.record_no,
        course_code=r.course_code,
        status=r.status,
        valid_until=valid_until if valid_until is not None else r.valid_until,
    )


# ---- numbering ----------------------------------------------------------------------------------


def next_record_seq(db: Session) -> int:
    db.execute(select(func.pg_advisory_xact_lock(5_000_001)))
    return int(db.scalar(select(func.coalesce(func.max(TrainingRecord.seq), 0))) or 0) + 1


def record_no(seq: int) -> str:
    return f"TRR-{seq:06d}"


# ---- misc ---------------------------------------------------------------------------------------


def add_months(d: date, months: int) -> date:
    from app.kpi.periods import add_months as _am  # noqa: PLC0415

    return _am(d, months)


def local_day(at: datetime | None = None) -> date:
    return acommon.local_day(at or now())


def day_end_utc(d: date) -> datetime:
    return acommon.local_midnight_utc(d + timedelta(days=1)) - timedelta(microseconds=1)


def reason(text: str | None, minimum: int, field: str = "reason") -> str:
    if not text or len(text.strip()) < minimum:
        raise validation_error(field, f"Give a reason of at least {minimum} characters.")
    return text.strip()


def ids(xs: Iterable[uuid.UUID | None]) -> list[uuid.UUID]:
    return [x for x in xs if x is not None]


def sod(msg: str = "The same person cannot perform both steps.") -> ApiError:
    return ApiError(422, ErrorCode.SOD_CONFLICT, msg, "تعارض في الفصل بين المهام.")


def today_local() -> date:
    return today()
