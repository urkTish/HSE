"""Medical providers (clinics) and examiner registrations (spec 6a-occupational-health §3.2,
§3.3, §4.1, §4.2, MP-1…MP-6, EX-1…EX-5): the registers, the MP-3 acceptability and EX-2
qualification tests used by assessments and imports, and the MP-6 blacklist cascade."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.cert_enums import VerificationStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.med_enums import (
    AssessmentStatus,
    ExaminerAction,
    ExaminerClass,
    ExaminerStatus,
    MedicalBlacklistScope,
    MedicalProviderAction,
    MedicalProviderKind,
    MedicalProviderStatus,
)
from app.core.med_enums import MedicalProviderUnacceptableReason as U
from app.core.text import like_pattern, normalize
from app.models import (
    Contractor,
    Deployment,
    FitnessAssessment,
    FitnessCode,
    MedicalExaminer,
    MedicalProvider,
    ProjectEngagement,
    RoleAssignment,
)
from app.schemas.access_common import WorkerRef
from app.schemas.hse_common import UserRef
from app.schemas.medical import (
    ExaminerCreate,
    ExaminerPage,
    ExaminerRead,
    ExaminerTransition,
    ExaminerUpdate,
    MedicalProviderCreate,
    MedicalProviderPage,
    MedicalProviderRead,
    MedicalProviderTransition,
    MedicalProviderUpdate,
)
from app.services.cert import common as cc
from app.services.common import duplicate, invalid_transition, paginate
from app.services.med import alerts, common
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = common.C
S = MedicalProviderStatus
A = MedicalProviderAction
K = MedicalProviderKind
ES = ExaminerStatus

# ---- MP-3 acceptability / EX-2 qualification ----------------------------------------------------

UNACCEPTABLE_TEXT: dict[U, tuple[str, str]] = {
    U.PROVIDER_NOT_APPROVED: ("The clinic is not approved.", "العيادة غير معتمدة."),
    U.PROVIDER_SUSPENDED: ("The clinic is suspended.", "العيادة موقوفة."),
    U.PROVIDER_BLACKLISTED: ("The clinic is blacklisted.", "العيادة محظورة."),
    U.LICENCE_INVALID: ("The clinic's MOH licence is not valid.", "ترخيص العيادة غير ساري."),
    U.PROVIDER_KIND_NOT_ALLOWED: (
        "This kind of clinic may not certify this fitness code.",
        "لا يسمح لهذا النوع من العيادات باعتماد رمز اللياقة هذا.",
    ),
    U.NOT_PROJECT_CLINIC: (
        "The site clinic does not serve this project.",
        "عيادة الموقع لا تخدم هذا المشروع.",
    ),
    U.NOT_OWN_TREE: (
        "A contractor clinic may certify only workers of its own contractor tree.",
        "يحق لعيادة المقاول اعتماد عمال شجرة المقاول فقط.",
    ),
}


def _iso(x: Any) -> date | None:
    return date.fromisoformat(x) if isinstance(x, str) and x else None


def suspended_on(pv: MedicalProvider, d: date) -> bool:
    for per in pv.suspension_periods or []:
        f, t = _iso(per.get("from")), _iso(per.get("to"))
        if f is not None and f <= d and (t is None or d < t):
            return True
    return False


def _tree(db: Session, pv: MedicalProvider, project_id: uuid.UUID) -> set[uuid.UUID]:
    if pv.contractor_id is None:
        return set()
    out: set[uuid.UUID] = set()
    for e in db.scalars(
        select(ProjectEngagement).where(
            ProjectEngagement.project_id == project_id,
            ProjectEngagement.contractor_id == pv.contractor_id,
        )
    ):
        out |= engagement_descendants(db, e.id)
    return out


def unacceptable(
    db: Session,
    pv: MedicalProvider,
    fc: FitnessCode,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    d: date,
) -> U | None:
    """MP-3 on examined_on d; None when acceptable."""
    if (
        pv.blacklisted_on is not None
        and pv.status == S.blacklisted
        and (
            pv.blacklist_scope != MedicalBlacklistScope.issued_from
            or (pv.blacklist_from is not None and d >= pv.blacklist_from)
        )
    ):
        return U.PROVIDER_BLACKLISTED
    if suspended_on(pv, d):
        return U.PROVIDER_SUSPENDED
    if pv.status not in (S.approved, S.suspended, S.blacklisted) or (
        pv.approved_on is not None and pv.approved_on > d
    ):
        return U.PROVIDER_NOT_APPROVED
    if pv.licence_valid_until < d:
        return U.LICENCE_INVALID
    if pv.kind.value not in (fc.provider_kinds or []):
        return U.PROVIDER_KIND_NOT_ALLOWED
    if pv.kind == K.site_clinic and project_id not in (pv.project_ids or []):
        return U.NOT_PROJECT_CLINIC
    if pv.kind == K.contractor_clinic:
        dep = common.deployment(db, worker_id, project_id)
        if dep is None or dep.engagement_id not in _tree(db, pv, project_id):
            return U.NOT_OWN_TREE
    return None


def unacceptable_error(reason: U, code: str | None = None) -> ApiError:
    en, ar = UNACCEPTABLE_TEXT[reason]
    meta: dict[str, Any] = {"reason": reason.value}
    if code:
        meta["code"] = code
    return ApiError(422, ErrorCode.MEDICAL_PROVIDER_NOT_ACCEPTABLE, en, ar, meta=meta)


def examiner_problem(
    x: MedicalExaminer, pv: MedicalProvider, fc: FitnessCode, d: date
) -> ErrorCode | None:
    """EX-2 / EX-3 on examined_on d."""
    if x.classification == ExaminerClass.nurse:
        return ErrorCode.EXAMINER_NOT_QUALIFIED
    if x.licence_checked_at is None or x.licence_valid_until < d:
        return ErrorCode.EXAMINER_LICENCE_INVALID
    if x.status in (ES.withdrawn, ES.suspended) or (
        x.status == ES.expired and d > x.licence_valid_until
    ):
        return ErrorCode.EXAMINER_LICENCE_INVALID
    if pv.id not in (x.provider_ids or []):
        return ErrorCode.EXAMINER_LICENCE_INVALID
    if x.classification.value not in (fc.examiner_classes or []):
        return ErrorCode.EXAMINER_NOT_QUALIFIED
    return None


def examiner_error(code: ErrorCode, line_code: str | None = None) -> ApiError:
    if code == ErrorCode.EXAMINER_NOT_QUALIFIED:
        en, ar = (
            "The examiner's classification may not sign this fitness code.",
            "تصنيف الفاحص لا يسمح بتوقيع رمز اللياقة هذا.",
        )
    else:
        en, ar = (
            "The examiner's registration is not valid on the examination date for this clinic.",
            "تسجيل الفاحص غير ساري في تاريخ الفحص لهذه العيادة.",
        )
    return ApiError(422, code, en, ar, meta={"code": line_code} if line_code else None)


# ---- reads ---------------------------------------------------------------------------------------


def _view(p: Principal) -> None:
    if not (p.has_any(C.fitness_catalogue_view) or p.has_any(C.medical_provider_edit)):
        raise forbidden_error()


def _user_ref(db: Session, uid: uuid.UUID | None) -> UserRef | None:
    ref: UserRef | None = common.user_ref(db, uid)
    return ref


def _actions(p: Principal, pv: MedicalProvider) -> list[A]:
    ro = bool(p.projects) and all(s.read_only for s in p.projects.values())
    edit = p.has_any(C.medical_provider_edit) and not ro
    out: list[A] = []
    for a, (srcs, _dst) in ALLOWED.items():
        if pv.status not in srcs:
            continue
        if (a == A.submit and edit) or (a != A.submit and p.is_manager and not ro):
            out.append(a)
    return out


def provider_read(db: Session, p: Principal, pv: MedicalProvider) -> MedicalProviderRead:
    return MedicalProviderRead(
        id=pv.id,
        provider_code=pv.provider_code,
        legal_name_en=pv.legal_name_en,
        legal_name_ar=pv.legal_name_ar,
        kind=pv.kind,
        project_ids=list(pv.project_ids or []),
        contractor_id=pv.contractor_id,
        moh_licence_no=pv.moh_licence_no,
        licence_valid_until=pv.licence_valid_until,
        licence_checked_at=pv.licence_checked_at,
        licence_checked_by=_user_ref(db, pv.licence_checked_by_user_id),
        verification_domains=list(pv.verification_domains or []),
        verification_email=pv.verification_email,
        verification_phone=pv.verification_phone,
        verification_portal_url=pv.verification_portal_url,
        status=pv.status,
        status_reason=pv.status_reason,
        approved_on=pv.approved_on,
        blacklist_scope=pv.blacklist_scope,
        blacklist_from=pv.blacklist_from,
        allowed_actions=_actions(p, pv),
    )


def list_providers(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    q: str | None,
    kind: list[MedicalProviderKind] | None,
    status: list[MedicalProviderStatus] | None,
    project_id: uuid.UUID | None,
) -> MedicalProviderPage:
    _view(p)
    stmt = select(MedicalProvider).order_by(MedicalProvider.provider_code)
    if q:
        pat = like_pattern(normalize(q))
        stmt = stmt.where(
            or_(
                MedicalProvider.provider_code.ilike(like_pattern(q)),
                MedicalProvider.name_norm_en.ilike(pat),
                MedicalProvider.name_norm_ar.ilike(pat),
            )
        )
    if kind:
        stmt = stmt.where(MedicalProvider.kind.in_(kind))
    if status:
        stmt = stmt.where(MedicalProvider.status.in_(status))
    if project_id is not None:
        stmt = stmt.where(
            or_(
                MedicalProvider.kind != K.site_clinic,
                MedicalProvider.project_ids.any(project_id),  # type: ignore[arg-type]
            )
        )
    rows, total = paginate(db, stmt, page, page_size)
    return MedicalProviderPage(
        items=[provider_read(db, p, x) for x in rows], total=total, page=page, page_size=page_size
    )


def get_provider(db: Session, p: Principal, provider_id: uuid.UUID) -> MedicalProviderRead:
    _view(p)
    return provider_read(db, p, common.provider_or_404(db, provider_id))


# ---- create / update -----------------------------------------------------------------------------


def _edit(p: Principal) -> None:
    p.require_any(C.medical_provider_edit)


def _decide(p: Principal) -> None:
    p.ensure_writer()
    if not p.has_any(C.medical_provider_decide):
        raise forbidden_error()


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return (urlparse(url).hostname or "").lower() or None


def domain_ok(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _validate(db: Session, pv: MedicalProvider) -> None:
    if pv.kind == K.site_clinic:
        if not pv.project_ids:
            raise validation_error("project_ids", "A site clinic must name its projects.")
    elif pv.project_ids:
        raise validation_error("project_ids", "Only a site clinic names projects.")
    if pv.kind == K.contractor_clinic:
        if pv.contractor_id is None or db.get(Contractor, pv.contractor_id) is None:
            raise validation_error("contractor_id", "Required for a contractor clinic.")
    elif pv.contractor_id is not None:
        raise validation_error("contractor_id", "Only for a contractor clinic.")
    domains = [d.lower().strip() for d in pv.verification_domains or []]
    pv.verification_domains = domains
    if pv.kind != K.site_clinic and not domains:
        raise validation_error("verification_domains", "Give at least one domain.")
    host = _host(pv.verification_portal_url)
    if pv.verification_portal_url:
        if not pv.verification_portal_url.startswith("https://") or host is None:
            raise validation_error("verification_portal_url", "Use an https URL.")
        if not domain_ok(host, domains):
            raise validation_error(
                "verification_portal_url", "The portal host must be one of the domains."
            )
    if pv.verification_email:
        dom = pv.verification_email.rsplit("@", 1)[-1].lower()
        if "@" not in pv.verification_email or not domain_ok(dom, domains):
            raise validation_error(
                "verification_email", "The email domain must be one of the domains."
            )


def _names(db: Session, pv: MedicalProvider) -> None:
    pv.name_norm_en = normalize(pv.legal_name_en)
    pv.name_norm_ar = normalize(pv.legal_name_ar)
    for col, field_ in (("name_norm_en", "legal_name_en"), ("name_norm_ar", "legal_name_ar")):
        other = db.scalar(
            select(MedicalProvider.id).where(
                getattr(MedicalProvider, col) == getattr(pv, col), MedicalProvider.id != pv.id
            )
        )
        if other is not None:
            raise duplicate(field_, "A clinic with this name exists.")
    other = db.scalar(
        select(MedicalProvider.id).where(
            MedicalProvider.moh_licence_no == pv.moh_licence_no, MedicalProvider.id != pv.id
        )
    )
    if other is not None:
        raise duplicate("moh_licence_no", "This MOH licence is registered to another clinic.")


def create_provider(db: Session, p: Principal, body: MedicalProviderCreate) -> MedicalProviderRead:
    _edit(p)
    if db.scalar(
        select(MedicalProvider.id).where(MedicalProvider.provider_code == body.provider_code)
    ):
        raise duplicate("provider_code", "This clinic code exists.")
    data = body.model_dump()
    pv = MedicalProvider(
        id=uuid.uuid4(), status=S.draft, suspension_periods=[], alerts_sent=[], **data
    )
    if pv.licence_checked_at is not None:
        pv.licence_checked_by_user_id = p.user.id
    _validate(db, pv)
    _names(db, pv)
    cc.stamp(pv, p, create=True)
    db.add(pv)
    db.flush()
    common.clear_cache(db)
    common.record(db, p, AuditAction.create, EntityType.medical_provider, pv, None)
    return provider_read(db, p, pv)


def update_provider(
    db: Session, p: Principal, provider_id: uuid.UUID, body: MedicalProviderUpdate
) -> MedicalProviderRead:
    _edit(p)
    pv = common.provider_or_404(db, provider_id)
    before = common.snap(pv)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(pv, k, v)
    if "licence_checked_at" in data:
        pv.licence_checked_by_user_id = p.user.id if pv.licence_checked_at else None
    _validate(db, pv)
    _names(db, pv)
    cc.stamp(pv, p)
    db.flush()
    common.clear_cache(db)
    common.record(db, p, AuditAction.update, EntityType.medical_provider, pv, None, before)
    return provider_read(db, p, pv)


# ---- transitions (§4.1) --------------------------------------------------------------------------

ALLOWED: dict[MedicalProviderAction, tuple[set[MedicalProviderStatus], MedicalProviderStatus]] = {
    A.submit: ({S.draft}, S.pending_approval),
    A.approve: ({S.pending_approval}, S.approved),
    A.return_: ({S.pending_approval}, S.draft),
    A.suspend: ({S.approved}, S.suspended),
    A.reinstate: ({S.suspended}, S.approved),
    A.blacklist: ({S.approved, S.suspended}, S.blacklisted),
    A.lift_blacklist: ({S.blacklisted}, S.suspended),
}


def _close(periods: list[dict[str, Any]], d: date) -> list[dict[str, Any]]:
    return [{**x, "to": d.isoformat()} if x.get("to") is None else x for x in periods]


def _licence_required() -> ApiError:
    return ApiError(
        422,
        ErrorCode.LICENCE_CHECK_REQUIRED,
        "Record that the MOH licence was checked, with a licence valid today (MP-2).",
        "سجّل التحقق من ترخيص وزارة الصحة مع ترخيص ساري اليوم.",
    )


def suspend(db: Session, pv: MedicalProvider, p: Principal | None, reason: str, on: date) -> None:
    pv.status = S.suspended
    pv.status_reason = reason
    pv.suspension_periods = [*(pv.suspension_periods or []), {"from": on.isoformat(), "to": None}]


def transition_provider(
    db: Session, p: Principal, provider_id: uuid.UUID, body: MedicalProviderTransition
) -> MedicalProviderRead:
    pv = common.provider_or_404(db, provider_id)
    srcs, dst = ALLOWED[body.action]
    if body.action == A.submit:
        _edit(p)
    else:
        _decide(p)
    if pv.status not in srcs:
        raise invalid_transition("Medical provider", pv.status, dst)
    before = common.snap(pv)
    d = today()
    details: dict[str, Any] = {"action": body.action.value, "from": pv.status.value}
    if body.action == A.submit:
        if pv.licence_checked_at is None or not pv.moh_licence_no:
            raise _licence_required()
        pv.status_reason = None
    elif body.action == A.approve:
        if pv.licence_checked_at is None or pv.licence_valid_until < d:
            raise _licence_required()
        pv.approved_on = pv.approved_on or d
        pv.status_reason = None
    elif body.action == A.return_:
        pv.status_reason = common.reason(body.reason, 10)
    elif body.action == A.suspend:
        suspend(db, pv, p, common.reason(body.reason, 10), d)
    elif body.action == A.reinstate:
        pv.status_reason = None
        pv.suspension_periods = _close(pv.suspension_periods or [], d)
    elif body.action == A.blacklist:
        r = common.reason(body.reason, 20)
        if body.blacklist_scope is None or (
            body.blacklist_scope == MedicalBlacklistScope.issued_from
            and body.blacklist_from is None
        ):
            raise ApiError(
                422,
                ErrorCode.PROVIDER_BLACKLIST_SCOPE_REQUIRED,
                "Choose the blacklist scope (and the date for issued_from).",
                "اختر نطاق الحظر (والتاريخ عند الاختيار من تاريخ).",
            )
        pv.status_reason = r
        pv.blacklist_scope = body.blacklist_scope
        pv.blacklist_from = (
            body.blacklist_from
            if body.blacklist_scope == MedicalBlacklistScope.issued_from
            else None
        )
        pv.blacklisted_on = d
        details["blacklist_scope"] = body.blacklist_scope.value
    elif body.action == A.lift_blacklist:
        pv.status_reason = common.reason(body.reason, 10)
        pv.blacklist_scope = None
        pv.blacklist_from = None
        pv.blacklisted_on = None
        pv.suspension_periods = [
            *(pv.suspension_periods or []),
            {"from": d.isoformat(), "to": None},
        ]
    pv.status = dst
    cc.stamp(pv, p)
    db.flush()
    common.clear_cache(db)
    if body.action == A.blacklist:
        details["assessments_revoked"] = blacklist_cascade(db, pv, p)
    common.record(
        db, p, AuditAction.status_change, EntityType.medical_provider, pv, None, before, details
    )
    if dst in (S.suspended, S.blacklisted, S.approved):
        _publish(db, pv)
        if dst in (S.suspended, S.blacklisted):
            alert_status(db, pv)
    return provider_read(db, p, pv)


def _holders(db: Session, pv: MedicalProvider) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(FitnessAssessment.worker_id).where(FitnessAssessment.provider_id == pv.id)
        )
    )


def _publish(db: Session, pv: MedicalProvider) -> None:
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "medical.provider_changed", worker_ids=_holders(db, pv))


def blacklist_cascade(db: Session, pv: MedicalProvider, p: Principal | None) -> int:
    """MP-6: revoke the assessments in scope (Accepted → Revoked; Draft / Submitted / Awaiting
    → Rejected), refresh line states and send the OH Practitioners the affected list."""
    from app.services.med import assessments  # noqa: PLC0415

    at = now()
    n = 0
    per_project: dict[uuid.UUID, set[uuid.UUID]] = {}
    for a in db.scalars(select(FitnessAssessment).where(FitnessAssessment.provider_id == pv.id)):
        if pv.blacklist_scope == MedicalBlacklistScope.issued_from and (
            pv.blacklist_from is None or a.examined_on < pv.blacklist_from
        ):
            continue
        if a.status == AssessmentStatus.accepted:
            assessments.revoke_system(db, a, p, "provider_blacklisted", at)
        elif a.status in (
            AssessmentStatus.draft,
            AssessmentStatus.submitted,
            AssessmentStatus.awaiting_signoff,
        ):
            assessments.set_status(db, a, AssessmentStatus.rejected, at)
        else:
            continue
        n += 1
        per_project.setdefault(a.project_id, set()).add(a.worker_id)
    db.flush()
    for pid, ws in per_project.items():
        for wid in ws:
            from app.services.med import engine  # noqa: PLC0415

            engine.refresh_states(db, wid)
        listing = ", ".join(sorted(alerts.wno(db, w) for w in ws))
        alerts.send(
            db,
            alerts.oh(db, pid),
            NotificationKind.medical_reexamination_list,
            f"Clinic {pv.provider_code} blacklisted: re-examine {len(ws)} workers ({listing})",
            f"العيادة {pv.provider_code} محظورة: إعادة فحص {len(ws)} عمال ({listing})",
            pid,
            EntityType.medical_provider,
            pv.id,
        )
    if per_project:
        from app.services.cert import events  # noqa: PLC0415

        events.publish(
            db, "medical.fitness_changed", worker_ids={w for ws in per_project.values() for w in ws}
        )
    return n


def affected(db: Session, p: Principal, provider_id: uuid.UUID) -> list[WorkerRef]:
    """Workers whose assessments were revoked by the blacklist (OH Practitioners, Manager)."""
    pv = common.provider_or_404(db, provider_id)
    if not (p.is_manager or common.is_oh(p, None)):
        raise forbidden_error()
    ids = set(
        db.scalars(
            select(FitnessAssessment.worker_id).where(
                FitnessAssessment.provider_id == pv.id,
                FitnessAssessment.revoke_code == "provider_blacklisted",
            )
        )
    )
    from app.models import Worker  # noqa: PLC0415

    out = []
    for w in db.scalars(select(Worker).where(Worker.id.in_(ids or {uuid.UUID(int=0)}))):
        out.append(common.worker_ref(w, True))
    return sorted(out, key=lambda r: r.worker_no)


def _projects(db: Session, pv: MedicalProvider) -> list[uuid.UUID]:
    from app.models import Project  # noqa: PLC0415

    if pv.kind == K.site_clinic:
        return list(pv.project_ids or [])
    return list(db.scalars(select(Project.id)))


def alert_status(db: Session, pv: MedicalProvider) -> None:
    """Provider suspended / blacklisted: OH Practitioners and HSE Officers (no reason)."""
    from app.services.cert.alerts import officers  # noqa: PLC0415

    for pid in _projects(db, pv):
        alerts.send(
            db,
            alerts.oh(db, pid) | set(officers(db, pid)),
            NotificationKind.medical_provider_status,
            f"Clinic {pv.provider_code} is {pv.status.value}",
            f"العيادة {pv.provider_code} أصبحت {pv.status.value}",
            pid,
            EntityType.medical_provider,
            pv.id,
        )


# ---- examiners (§3.3, §4.2) ----------------------------------------------------------------------


def examiner_read(db: Session, p: Principal, x: MedicalExaminer) -> ExaminerRead:
    lic = p.has_any(C.medical_provider_edit)
    out = ExaminerRead(
        id=x.id,
        examiner_no=x.examiner_no,
        full_name_en=x.full_name_en,
        full_name_ar=x.full_name_ar,
        classification=x.classification,
        provider_ids=list(x.provider_ids or []),
        user=_user_ref(db, x.user_id),
        status=x.status,
    )
    if lic:
        out.scfhs_licence_no = x.scfhs_licence_no
        out.licence_valid_until = x.licence_valid_until
        out.licence_checked_at = x.licence_checked_at
        out.status_reason = x.status_reason
    return out


def list_examiners(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    q: str | None,
    provider_id: uuid.UUID | None,
    status: list[ExaminerStatus] | None,
) -> ExaminerPage:
    _view(p)
    stmt = select(MedicalExaminer).order_by(MedicalExaminer.examiner_no)
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(
                MedicalExaminer.examiner_no.ilike(pat),
                MedicalExaminer.full_name_en.ilike(pat),
                MedicalExaminer.full_name_ar.ilike(pat),
            )
        )
    if provider_id is not None:
        stmt = stmt.where(MedicalExaminer.provider_ids.any(provider_id))  # type: ignore[arg-type]
    if status:
        stmt = stmt.where(MedicalExaminer.status.in_(status))
    rows, total = paginate(db, stmt, page, page_size)
    return ExaminerPage(
        items=[examiner_read(db, p, x) for x in rows], total=total, page=page, page_size=page_size
    )


def get_examiner(db: Session, p: Principal, examiner_id: uuid.UUID) -> ExaminerRead:
    _view(p)
    return examiner_read(db, p, common.examiner_or_404(db, examiner_id))


def _check_providers(db: Session, ids: list[uuid.UUID]) -> None:
    for pid in ids:
        pv = db.get(MedicalProvider, pid)
        if pv is None or pv.status not in (S.approved, S.suspended):
            raise validation_error("provider_ids", "Every clinic must be approved.")


def _check_user(db: Session, x: MedicalExaminer) -> None:
    if x.user_id is None:
        return
    is_oh = db.scalar(
        select(func.count())
        .select_from(RoleAssignment)
        .where(
            RoleAssignment.user_id == x.user_id,
            RoleAssignment.role == Role.oh_practitioner,
            RoleAssignment.revoked_at.is_(None),
        )
    )
    if not is_oh:
        raise validation_error("user_id", "Link only an Occupational Health Practitioner user.")
    other = db.scalar(
        select(MedicalExaminer.id).where(
            MedicalExaminer.user_id == x.user_id, MedicalExaminer.id != x.id
        )
    )
    if other is not None:
        raise duplicate("user_id", "This user is linked to another examiner.")


def create_examiner(db: Session, p: Principal, body: ExaminerCreate) -> ExaminerRead:
    _edit(p)
    if body.licence_valid_until <= today():
        raise validation_error("licence_valid_until", "The licence must be valid after today.")
    if db.scalar(
        select(MedicalExaminer.id).where(MedicalExaminer.scfhs_licence_no == body.scfhs_licence_no)
    ):
        raise duplicate("scfhs_licence_no", "This SCFHS licence is registered.")
    _check_providers(db, body.provider_ids)
    seq = (db.scalar(select(func.max(MedicalExaminer.seq))) or 0) + 1
    x = MedicalExaminer(
        id=uuid.uuid4(),
        seq=seq,
        examiner_no=f"EXR-{seq:04d}",
        status=ES.active,
        licence_checked_by_user_id=p.user.id,
        alerts_sent=[],
        **body.model_dump(),
    )
    _check_user(db, x)
    cc.stamp(x, p, create=True)
    db.add(x)
    db.flush()
    common.record(db, p, AuditAction.create, EntityType.medical_examiner, x, None)
    return examiner_read(db, p, x)


def update_examiner(
    db: Session, p: Principal, examiner_id: uuid.UUID, body: ExaminerUpdate
) -> ExaminerRead:
    _edit(p)
    x = common.examiner_or_404(db, examiner_id)
    if x.status in (ES.withdrawn, ES.expired):
        raise invalid_transition("Examiner", x.status, x.status)
    before = common.snap(x)
    data = body.model_dump(exclude_unset=True)
    if "provider_ids" in data:
        _check_providers(db, data["provider_ids"] or [])
    for k, v in data.items():
        setattr(x, k, v)
    _check_user(db, x)
    cc.stamp(x, p)
    db.flush()
    common.record(db, p, AuditAction.update, EntityType.medical_examiner, x, None, before)
    return examiner_read(db, p, x)


EX_ALLOWED: dict[ExaminerAction, tuple[set[ExaminerStatus], ExaminerStatus]] = {
    ExaminerAction.suspend: ({ES.active}, ES.suspended),
    ExaminerAction.reinstate: ({ES.suspended}, ES.active),
    ExaminerAction.withdraw: ({ES.active, ES.suspended}, ES.withdrawn),
}


def transition_examiner(
    db: Session, p: Principal, examiner_id: uuid.UUID, body: ExaminerTransition
) -> ExaminerRead:
    _decide(p)
    x = common.examiner_or_404(db, examiner_id)
    srcs, dst = EX_ALLOWED[body.action]
    if x.status not in srcs:
        raise invalid_transition("Examiner", x.status, dst)
    before = common.snap(x)
    x.status_reason = common.reason(body.reason, 10)
    x.status = dst
    cc.stamp(x, p)
    db.flush()
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.medical_examiner,
        x,
        None,
        before,
        {"action": body.action.value},
    )
    return examiner_read(db, p, x)


def linked_examiner(db: Session, user_id: uuid.UUID) -> MedicalExaminer | None:
    return db.scalar(select(MedicalExaminer).where(MedicalExaminer.user_id == user_id))


def verification_ok(a: FitnessAssessment) -> bool:
    return a.verification_status == VerificationStatus.verified


def deployments_of(db: Session, worker_id: uuid.UUID) -> list[Deployment]:
    return list(db.scalars(select(Deployment).where(Deployment.worker_id == worker_id)))
