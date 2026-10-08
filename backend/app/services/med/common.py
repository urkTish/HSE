"""Helpers shared by the Phase 6a services (spec 6a-occupational-health): the catalogue (seeded
on first use), project settings, access tiers (OH-2), scope checks and small utilities."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import DeploymentStatus, HookKind, WorkerStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.med_enums import FitnessTier
from app.models import (
    Deployment,
    FitnessCode,
    MedicalExaminer,
    MedicalProvider,
    MedicalSettings,
    Project,
    Worker,
)
from app.schemas.medical import ExaminerRef, FitnessCodeRef, MedicalProviderRef
from app.services import audit
from app.services.access import common as acommon
from app.services.med import reference as ref
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
T = FitnessTier
TIER_CAPS = (
    (3, C.fitness_clinical_view),
    (2, C.fitness_functional_view),
    (1, C.fitness_status_view),
)
TIER_OF = {1: T.status, 2: T.functional, 3: T.clinical_admin}

# ---- catalogue ----------------------------------------------------------------------------------


def ensure_catalogue(db: Session) -> None:
    if db.info.get("med_catalogue_ok"):
        return
    have = set(db.scalars(select(FitnessCode.code)))
    added = False
    for code, en, ar, cat, months, exc, kinds, tests in ref.CATALOGUE:
        if code in have:
            continue
        db.add(
            FitnessCode(
                id=uuid.uuid4(),
                code=code,
                name_en=en,
                name_ar=ar,
                category=cat,
                validity_months=months,
                examiner_classes=list(exc),
                provider_kinds=list(kinds),
                typical_tests=list(tests),
                extra_negated_by=[],
                active=True,
                seeded=True,
            )
        )
        added = True
    if added:
        db.flush()
    db.info["med_catalogue_ok"] = True


def codes(db: Session) -> dict[str, FitnessCode]:
    cache: dict[str, FitnessCode] | None = db.info.get("med_codes")
    if cache is None:
        ensure_catalogue(db)
        cache = {c.code: c for c in db.scalars(select(FitnessCode))}
        db.info["med_codes"] = cache
    return cache


def code(db: Session, c: str) -> FitnessCode | None:
    return codes(db).get(c)


def code_ref(db: Session, c: str) -> FitnessCodeRef:
    fc = code(db, c)
    if fc is None:
        from app.core.med_enums import FitnessCategory  # noqa: PLC0415

        return FitnessCodeRef(code=c, name_en=c, name_ar=c, category=FitnessCategory.task)
    return FitnessCodeRef(
        code=fc.code, name_en=fc.name_en, name_ar=fc.name_ar, category=fc.category
    )


def negated_by(fc: FitnessCode) -> list[str]:
    """RC codes that negate the code: list RC `negates` plus MC-3 additions."""
    out = [r.value for r, v in ref.RESTRICTIONS.items() if fc.code in v[3]]
    return out + [x for x in fc.extra_negated_by or [] if x not in out]


def negates_code(db: Session, restriction: str, c: str) -> bool:
    fc = code(db, c)
    if fc is not None and restriction in (fc.extra_negated_by or []):
        return True
    return c in ref.negates(restriction)


def clear_cache(db: Session) -> None:
    for k in ("med_codes", "med_settings", "med_providers", "med_examiners", "med_wf"):
        db.info.pop(k, None)


# ---- settings -----------------------------------------------------------------------------------


def settings(db: Session, project_id: uuid.UUID) -> MedicalSettings:
    cache: dict[uuid.UUID, MedicalSettings] = db.info.setdefault("med_settings", {})
    s = cache.get(project_id) or db.get(MedicalSettings, project_id)
    if s is None:
        s = MedicalSettings(project_id=project_id)
        for col in MedicalSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                setattr(s, col.key, arg(None) if callable(arg) else arg)
        s.fitness_validity_months = {}
        s.medical_hook_critical_codes = list(ref.DEFAULT_CRITICAL)
        s.rtw_hold_case_categories = list(ref.RTW_CATEGORIES)
        s.heat_illness_natures = list(ref.HEAT_NATURES)
        s.exposure_group_trade_defaults = {k: list(v) for k, v in ref.EG_TRADE_DEFAULTS.items()}
        s.alert_schedule_long_days = list(ref.ALERT_SCHEDULE_LONG)
        db.add(s)
        db.flush()
    cache[project_id] = s
    return s


def critical_codes(s: MedicalSettings | None) -> set[str]:
    if s is None:
        return set(ref.DEFAULT_CRITICAL)
    return set(s.medical_hook_critical_codes or ref.DEFAULT_CRITICAL)


def override_months(s: MedicalSettings | None, c: str) -> int | None:
    if s is None:
        return None
    v = (s.fitness_validity_months or {}).get(c)
    return int(v) if v is not None else None


def registered(db: Session, project_id: uuid.UUID | None) -> bool:
    """6a registered its `medical_fitness` provider on the project (HK6-1)."""
    if project_id is None:
        return False
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    cache: dict[Any, Any] = db.info.setdefault("hook_states", {})
    key = ("registered", project_id, HookKind.medical_fitness)
    if key not in cache:
        cache[key] = cpolicy.state(db, project_id, HookKind.medical_fitness) is not None
    return bool(cache[key])


# ---- tiers and scope (OH-2) ---------------------------------------------------------------------


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


def tier(p: Principal | None, project_id: uuid.UUID, dep: Deployment | None) -> int:
    """0 = none; 1 status (155); 2 functional (156); 3 clinical-administrative (157)."""
    if p is None:
        return 3
    for n, cap in TIER_CAPS:
        if covers_dep(p.grant(project_id, cap), dep):
            return n
    return 0


def project_tier(p: Principal | None, project_id: uuid.UUID) -> int:
    """The caller's best tier on the project regardless of scope (registers filter rows)."""
    if p is None:
        return 3
    for n, cap in TIER_CAPS:
        if p.grant(project_id, cap) is not None:
            return n
    return 0


def tier_enum(n: int) -> FitnessTier:
    return TIER_OF[max(1, min(3, n))]


def is_oh(p: Principal, project_id: uuid.UUID | None) -> bool:
    if project_id is None:
        return any(Role.oh_practitioner in s.roles for s in p.projects.values())
    s = p.projects.get(project_id)
    return s is not None and Role.oh_practitioner in s.roles


def unsuppressed(p: Principal | None, project_id: uuid.UUID | None = None) -> bool:
    """MK-3: the HSE Manager and OH Practitioners see small cells."""
    if p is None:
        return True
    return p.is_manager or is_oh(p, project_id)


def visible_project(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None or not p.can_see_project(project_id):
        raise not_found("Project")
    return x


def need(p: Principal, project_id: uuid.UUID, cap: Capability, write: bool = True) -> Grant:
    if write:
        return p.require(project_id, cap)
    g = p.grant(project_id, cap)
    if g is None:
        raise forbidden_error()
    return g


def sensitive_read(
    db: Session,
    p: Principal | None,
    entity_type: EntityType,
    entity_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    fields: list[str],
) -> None:
    if p is None or not fields:
        return
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(project_id),
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        fields_read=sorted(set(fields)),
    )


# ---- workers and deployments --------------------------------------------------------------------


def worker(db: Session, worker_id: uuid.UUID) -> Worker:
    w = db.get(Worker, worker_id)
    if w is None:
        raise not_found("Worker")
    return w


def deployment(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID) -> Deployment | None:
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


def open_deployment(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID) -> Deployment:
    """FA-1: a non-demobilised deployment on the project (pre-placement may precede
    mobilisation)."""
    w = worker(db, worker_id)
    if w.status == WorkerStatus.anonymised:
        raise validation_error("worker_id", "This worker record is anonymised.")
    dep = deployment(db, worker_id, project_id)
    if dep is None or dep.status == DeploymentStatus.demobilised:
        raise validation_error("worker_id", "The worker has no open deployment on this project.")
    return dep


def mobilised_on(dep: Deployment, d: date) -> bool:
    if dep.status == DeploymentStatus.pending_induction:
        return False
    if dep.mobilised_on is None or dep.mobilised_on > d:
        return False
    return dep.demobilised_on is None or dep.demobilised_on > d


def names(p: Principal | None, project_id: uuid.UUID | None) -> bool:
    return acommon.can_see_names(p, project_id)


def worker_ref(w: Worker, show: bool) -> Any:
    return acommon.worker_ref(w, show)


# ---- providers and examiners --------------------------------------------------------------------


def provider_or_404(db: Session, provider_id: uuid.UUID) -> MedicalProvider:
    x = db.get(MedicalProvider, provider_id)
    if x is None:
        raise not_found("Medical provider")
    return x


def examiner_or_404(db: Session, examiner_id: uuid.UUID) -> MedicalExaminer:
    x = db.get(MedicalExaminer, examiner_id)
    if x is None:
        raise not_found("Examiner")
    return x


def providers(db: Session) -> dict[uuid.UUID, MedicalProvider]:
    cache: dict[uuid.UUID, MedicalProvider] | None = db.info.get("med_providers")
    if cache is None:
        cache = {x.id: x for x in db.scalars(select(MedicalProvider))}
        db.info["med_providers"] = cache
    return cache


def provider_ref(pv: MedicalProvider) -> MedicalProviderRef:
    return MedicalProviderRef(
        id=pv.id,
        provider_code=pv.provider_code,
        legal_name_en=pv.legal_name_en,
        legal_name_ar=pv.legal_name_ar,
        kind=pv.kind,
    )


def examiner_ref(x: MedicalExaminer) -> ExaminerRef:
    return ExaminerRef(
        id=x.id,
        examiner_no=x.examiner_no,
        full_name_en=x.full_name_en,
        full_name_ar=x.full_name_ar,
        classification=x.classification,
    )


# ---- misc ---------------------------------------------------------------------------------------


def add_months(d: date, months: int) -> date:
    from app.kpi.periods import add_months as _am  # noqa: PLC0415

    return _am(d, months)


def local_day(at: datetime | None = None) -> date:
    return acommon.local_day(at or now())


def day_end_utc(d: date) -> datetime:
    return acommon.local_midnight_utc(d + timedelta(days=1)) - timedelta(microseconds=1)


def noon(d: date) -> datetime:
    return acommon.local_midnight_utc(d) + timedelta(hours=12)


def reason(text: str | None, minimum: int, field: str = "reason") -> str:
    if not text or len(text.strip()) < minimum:
        raise validation_error(field, f"Give a reason of at least {minimum} characters.")
    return text.strip()


def enc(text: str | None) -> bytes | None:
    return crypto.encrypt(text) if text else None


def dec(blob: bytes | None) -> str | None:
    return crypto.decrypt(blob) if blob else None


def ids(xs: Iterable[uuid.UUID | None]) -> list[uuid.UUID]:
    return [x for x in xs if x is not None]


def err(status: int, code: ErrorCode, en: str, ar: str, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def sod(msg: str = "The same person cannot perform both steps.") -> ApiError:
    return ApiError(422, ErrorCode.SOD_CONFLICT, msg, "تعارض في الفصل بين المهام.")


def today_local() -> date:
    return today()


def oh_users(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    from app.services.hse_common import project_role_users  # noqa: PLC0415

    return project_role_users(db, project_id, Role.oh_practitioner)


def user_ref(db: Session, uid: uuid.UUID | None) -> Any:
    from app.models import User  # noqa: PLC0415
    from app.schemas.hse_common import UserRef  # noqa: PLC0415

    if uid is None:
        return None
    u = db.get(User, uid)
    if u is None:
        return None
    return UserRef(id=u.id, full_name_en=u.full_name_en, full_name_ar=u.full_name_ar)


def snap(obj: Any) -> dict[str, Any]:
    """Audit snapshot without encrypted columns (sensitive free text never enters the audit)."""
    from app.services.cert import common as cc  # noqa: PLC0415

    skip = [c.key for c in obj.__table__.columns if c.key.endswith("_enc")]
    return cc.snap(obj, exclude=skip)


def record(
    db: Session,
    p: Principal | None,
    action: AuditAction,
    entity_type: EntityType,
    obj: Any,
    project_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    from app.services.cert import common as cc  # noqa: PLC0415

    cc.record(db, p, action, entity_type, obj, project_id, before, details, after=snap(obj))
