"""Training providers and accreditations (spec 5-training §3.2, §4.1, PV-1…PV-8): the register,
the PV-3 acceptability test used by sessions, records and imports, and the PV-6 blacklist
cascade."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.text import like_pattern, normalize
from app.core.train_enums import (
    AccreditationBodyCode,
    ProviderBlacklistScope,
    ProviderUnacceptableReason,
    SessionStatus,
    TrainingProviderAction,
    TrainingProviderKind,
    TrainingProviderStatus,
    TrainingRecordStatus,
    TrainingStatusReason,
)
from app.models import (
    Contractor,
    Deployment,
    ProjectEngagement,
    TrainingCourse,
    TrainingNomination,
    TrainingProvider,
    TrainingProviderAccreditation,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from app.schemas.training_courses import (
    AcceptabilityItem,
    ProviderAcceptability,
    ProviderAccreditationCreate,
    ProviderAccreditationRead,
    ProviderAccreditationUpdate,
    ProviderCreate,
    ProviderImpact,
    ProviderImpactHolder,
    ProviderListItem,
    ProviderPage,
    ProviderRead,
    ProviderTransitionRequest,
    ProviderUpdate,
    RegisterCheckInput,
)
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error
from app.services.train import common

C = common.C
S = TrainingProviderStatus
A = TrainingProviderAction
U = ProviderUnacceptableReason
K = TrainingProviderKind
RS = TrainingRecordStatus

# ---- acceptability (PV-3) -----------------------------------------------------------------------


def _iso(x: Any) -> date | None:
    if x is None:
        return None
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def suspended_on(pv: TrainingProvider, d: date) -> bool:
    for per in pv.suspension_periods or []:
        a, b = _iso(per.get("from")), _iso(per.get("to"))
        if a is not None and a <= d and (b is None or d < b):
            return True
    return False


def counts_on(a: TrainingProviderAccreditation, d: date) -> bool:
    """PV-2."""
    return a.register_checked_at is not None and a.valid_from <= d <= a.valid_until


def accreditations(db: Session, provider_id: uuid.UUID) -> list[TrainingProviderAccreditation]:
    return list(
        db.scalars(
            select(TrainingProviderAccreditation)
            .where(TrainingProviderAccreditation.provider_id == provider_id)
            .order_by(TrainingProviderAccreditation.valid_until)
        )
    )


def tree_engagements(db: Session, pv: TrainingProvider, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Engagements of the provider's contractor (and descendants) on the project."""
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


@dataclass
class Acceptability:
    ok: bool
    reason: ProviderUnacceptableReason | None = None
    not_own_tree: list[uuid.UUID] = field(default_factory=list)


def acceptable(
    db: Session,
    pv: TrainingProvider,
    c: TrainingCourse,
    d: date,
    project_id: uuid.UUID | None = None,
    worker_ids: Iterable[uuid.UUID] = (),
) -> Acceptability:
    """PV-3 (a)–(c) on date d."""
    if pv.status == S.blacklisted:
        return Acceptability(False, U.PROVIDER_BLACKLISTED)
    if pv.status in (S.draft, S.pending_approval) or pv.approved_at is None:
        return Acceptability(False, U.PROVIDER_NOT_APPROVED)
    if suspended_on(pv, d) or (pv.status == S.suspended and not (pv.suspension_periods or [])):
        return Acceptability(False, U.PROVIDER_SUSPENDED)
    # (c) kind rules are checked before (b): an internal / contractor unit never holds the
    # accreditation, and the kind is the actionable reason (AC17; DECISIONS)
    if pv.kind == K.internal and not c.internal_allowed:
        return Acceptability(False, U.INTERNAL_NOT_ALLOWED)
    if pv.kind == K.contractor_internal and not c.contractor_delivery_allowed:
        return Acceptability(False, U.CONTRACTOR_DELIVERY_NOT_ALLOWED)
    bodies = set(c.accreditation_bodies_required or [])
    if bodies:
        accs = [a for a in accreditations(db, pv.id) if a.accreditation_body in bodies]
        counted = [a for a in accs if counts_on(a, d)]
        if not counted:
            return Acceptability(False, U.ACCREDITATION_INVALID)
        if not any(c.code in (a.scope_course_codes or []) for a in counted):
            return Acceptability(False, U.ACCREDITATION_SCOPE)
    if pv.kind == K.contractor_internal:
        wids = list(worker_ids)
        if wids:
            bad = _not_own_tree(db, pv, project_id, wids)
            if bad:
                return Acceptability(False, U.NOT_OWN_TREE, bad)
    return Acceptability(True)


def _not_own_tree(
    db: Session, pv: TrainingProvider, project_id: uuid.UUID | None, worker_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    bad: list[uuid.UUID] = []
    trees: dict[uuid.UUID, set[uuid.UUID]] = {}
    for wid in worker_ids:
        deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == wid)))
        if project_id is not None:
            deps = [x for x in deps if x.project_id == project_id]
        ok = False
        for dep in deps:
            if dep.project_id not in trees:
                trees[dep.project_id] = tree_engagements(db, pv, dep.project_id)
            if dep.engagement_id is not None and dep.engagement_id in trees[dep.project_id]:
                ok = True
                break
        if not ok:
            bad.append(wid)
    return bad


UNACCEPTABLE_TEXT: dict[ProviderUnacceptableReason, tuple[str, str]] = {
    U.PROVIDER_NOT_APPROVED: ("The provider is not approved.", "الجهة غير معتمدة."),
    U.PROVIDER_SUSPENDED: ("The provider is suspended.", "الجهة موقوفة."),
    U.PROVIDER_BLACKLISTED: ("The provider is blacklisted.", "الجهة محظورة."),
    U.ACCREDITATION_INVALID: (
        "The provider holds no valid, register-checked accreditation required for this course.",
        "لا تملك الجهة اعتماداً سارياً ومتحققاً منه مطلوباً لهذه الدورة.",
    ),
    U.ACCREDITATION_SCOPE: (
        "The provider's accreditation does not cover this course.",
        "اعتماد الجهة لا يشمل هذه الدورة.",
    ),
    U.INTERNAL_NOT_ALLOWED: (
        "This course cannot be delivered internally.",
        "لا يجوز تقديم هذه الدورة داخلياً.",
    ),
    U.CONTRACTOR_DELIVERY_NOT_ALLOWED: (
        "This course cannot be delivered by a contractor's training unit.",
        "لا يجوز أن تقدم وحدة تدريب المقاول هذه الدورة.",
    ),
    U.NOT_OWN_TREE: (
        "A contractor's training unit may train only workers of its own contractor tree.",
        "لا يجوز لوحدة تدريب المقاول تدريب عمال من خارج شجرة المقاول.",
    ),
}


def unacceptable_error(a: Acceptability, on: date | None = None) -> ApiError:
    assert a.reason is not None  # noqa: S101
    en, ar = UNACCEPTABLE_TEXT[a.reason]
    meta: dict[str, Any] = {"reason": a.reason.value}
    if on is not None:
        meta["on_date"] = on.isoformat()
    if a.not_own_tree:
        meta["worker_ids"] = [str(x) for x in a.not_own_tree]
    return ApiError(422, ErrorCode.PROVIDER_NOT_ACCEPTABLE, en, ar, meta=meta)


def require_acceptable(
    db: Session,
    pv: TrainingProvider,
    c: TrainingCourse,
    days: Iterable[date],
    project_id: uuid.UUID | None = None,
    worker_ids: Iterable[uuid.UUID] = (),
) -> None:
    wids = list(worker_ids)
    for d in days:
        a = acceptable(db, pv, c, d, project_id, wids)
        if not a.ok:
            raise unacceptable_error(a, d)


# ---- reads ---------------------------------------------------------------------------------------


def get(db: Session, provider_id: uuid.UUID) -> TrainingProvider:
    return common.provider_or_404(db, provider_id)


def _hse_view(p: Principal) -> bool:
    return p.is_manager or common.is_hse(p) or not _contractor_view(p)


def _contractor_view(p: Principal) -> bool:
    if p.is_manager:
        return False
    roles = {r for s in p.projects.values() for r in s.roles}
    return bool(roles) and roles <= common.CONTRACTOR_ROLES


def accreditation_read(db: Session, a: TrainingProviderAccreditation) -> ProviderAccreditationRead:
    refs = Refs(db)
    d = today()
    return ProviderAccreditationRead(
        id=a.id,
        provider_id=a.provider_id,
        accreditation_body=AccreditationBodyCode(a.accreditation_body),
        accreditation_no=a.accreditation_no,
        scope_course_codes=list(a.scope_course_codes or []),
        valid_from=a.valid_from,
        valid_until=a.valid_until,
        days_left=(a.valid_until - d).days,
        certificate_attachment_id=a.certificate_attachment_id,
        register_checked_at=a.register_checked_at,
        register_checked_by=refs.user(a.register_checked_by_user_id),
        counts=counts_on(a, d),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def suspended_from(pv: TrainingProvider) -> date | None:
    open_ = [p for p in pv.suspension_periods or [] if p.get("to") is None]
    return _iso(open_[-1]["from"]) if open_ else None


def provider_read(db: Session, p: Principal, pv: TrainingProvider) -> ProviderRead:
    hse = _hse_view(p)
    contact = p.has_any(C.training_provider_edit)
    refs = Refs(db)
    contractor = db.get(Contractor, pv.contractor_id) if pv.contractor_id else None
    return ProviderRead(
        id=pv.id,
        provider_code=pv.provider_code,
        legal_name_en=pv.legal_name_en,
        legal_name_ar=pv.legal_name_ar,
        kind=pv.kind,
        contractor_id=pv.contractor_id,
        contractor_short_code=contractor.short_code if contractor else None,
        country=pv.country,
        cr_number=pv.cr_number,
        foreign_reg_no=pv.foreign_reg_no,
        verification_portal_url=pv.verification_portal_url,
        verification_domains=list(pv.verification_domains or []),
        verification_email=pv.verification_email,
        verification_phone=pv.verification_phone,
        contact_name=pv.contact_name if contact else None,
        contact_mobile=pv.contact_mobile if contact else None,
        status=pv.status if hse else None,
        accepted_for_use=common.provider_accepted(pv),
        status_reason=pv.status_reason if hse else None,
        suspended_from=suspended_from(pv) if hse else None,
        blacklist_scope=pv.blacklist_scope if hse else None,
        blacklist_from=pv.blacklist_from if hse else None,
        accreditations=[accreditation_read(db, a) for a in accreditations(db, pv.id)],
        approved_by=refs.user(pv.approved_by_user_id),
        approved_at=pv.approved_at,
        created_at=pv.created_at,
        updated_at=pv.updated_at,
    )


def _view(p: Principal) -> None:
    if not p.has_any(C.training_catalogue_view):
        raise forbidden_error()


def list_providers(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    q: str | None,
    status: list[TrainingProviderStatus] | None,
    kind: list[TrainingProviderKind] | None,
    course_code: str | None,
    accreditation_body: list[AccreditationBodyCode] | None,
    accreditation_expiring_days: int | None,
) -> ProviderPage:
    _view(p)
    hse = _hse_view(p)
    stmt = select(TrainingProvider).order_by(TrainingProvider.provider_code)
    if q:
        pat = like_pattern(normalize(q))
        stmt = stmt.where(
            or_(
                TrainingProvider.provider_code.ilike(like_pattern(q)),
                TrainingProvider.name_norm_en.ilike(pat),
                TrainingProvider.name_norm_ar.ilike(pat),
            )
        )
    if status and hse:
        stmt = stmt.where(TrainingProvider.status.in_(status))
    if kind:
        stmt = stmt.where(TrainingProvider.kind.in_(kind))
    d = today()
    if course_code or accreditation_body or accreditation_expiring_days is not None:
        ids: set[uuid.UUID] = set()
        for a in db.scalars(select(TrainingProviderAccreditation)):
            if course_code and course_code not in (a.scope_course_codes or []):
                continue
            if accreditation_body and a.accreditation_body not in {
                b.value for b in accreditation_body
            }:
                continue
            if accreditation_expiring_days is not None and not (
                d <= a.valid_until <= d + timedelta(days=accreditation_expiring_days)
            ):
                continue
            ids.add(a.provider_id)
        if course_code and not accreditation_body and accreditation_expiring_days is None:
            c = common.course(db, course_code)
            if c is not None and not c.accreditation_bodies_required:
                kinds = []
                if c.internal_allowed:
                    kinds.append(K.internal)
                if c.contractor_delivery_allowed:
                    kinds.append(K.contractor_internal)
                kinds.append(K.external)
                ids |= set(
                    db.scalars(select(TrainingProvider.id).where(TrainingProvider.kind.in_(kinds)))
                )
        stmt = stmt.where(TrainingProvider.id.in_(ids or {uuid.UUID(int=0)}))
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for pv in rows:
        accs = accreditations(db, pv.id)
        counted = [a for a in accs if counts_on(a, d)]
        contractor = db.get(Contractor, pv.contractor_id) if pv.contractor_id else None
        items.append(
            ProviderListItem(
                id=pv.id,
                provider_code=pv.provider_code,
                legal_name_en=pv.legal_name_en,
                legal_name_ar=pv.legal_name_ar,
                kind=pv.kind,
                contractor_short_code=contractor.short_code if contractor else None,
                status=pv.status if hse else None,
                accepted_for_use=common.provider_accepted(pv),
                accredited_course_codes=sorted({x for a in counted for x in a.scope_course_codes}),
                next_accreditation_expiry=min(
                    (a.valid_until for a in accs if a.valid_until >= d), default=None
                ),
            )
        )
    return ProviderPage(items=items, total=total, page=page, page_size=page_size)


def get_provider(db: Session, p: Principal, provider_id: uuid.UUID) -> ProviderRead:
    _view(p)
    return provider_read(db, p, get(db, provider_id))


# ---- create / update -----------------------------------------------------------------------------


def _edit(p: Principal) -> None:
    p.require_any(C.training_provider_edit)


def _decide(p: Principal) -> None:
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return (urlparse(url).hostname or "").lower() or None


def _domain_ok(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _validate(db: Session, pv: TrainingProvider) -> None:
    if pv.kind == K.contractor_internal:
        if pv.contractor_id is None or db.get(Contractor, pv.contractor_id) is None:
            raise validation_error("contractor_id", "Required for a contractor training unit.")
    elif pv.contractor_id is not None:
        raise validation_error("contractor_id", "Only for kind contractor_internal.")
    domains = [d.lower() for d in pv.verification_domains or []]
    pv.verification_domains = domains
    if pv.kind == K.external:
        if not pv.country:
            raise validation_error("country", "Required for an external provider.")
        if pv.country == "SA" and not pv.cr_number:
            raise validation_error("cr_number", "Required for a Saudi provider.")
        if not domains:
            raise validation_error("verification_domains", "Give at least one domain.")
    host = _host(pv.verification_portal_url)
    if pv.verification_portal_url:
        if not pv.verification_portal_url.startswith("https://") or host is None:
            raise validation_error("verification_portal_url", "Use an https URL.")
        if not _domain_ok(host, domains):
            raise validation_error(
                "verification_portal_url", "The portal host must be one of the domains."
            )
    if pv.verification_email:
        dom = pv.verification_email.rsplit("@", 1)[-1].lower()
        if "@" not in pv.verification_email or not _domain_ok(dom, domains):
            raise validation_error(
                "verification_email", "The email domain must be one of the domains."
            )


def _names(db: Session, pv: TrainingProvider) -> None:
    pv.name_norm_en = normalize(pv.legal_name_en)
    pv.name_norm_ar = normalize(pv.legal_name_ar)
    for col, field_ in (("name_norm_en", "legal_name_en"), ("name_norm_ar", "legal_name_ar")):
        other = db.scalar(
            select(TrainingProvider.id).where(
                getattr(TrainingProvider, col) == getattr(pv, col), TrainingProvider.id != pv.id
            )
        )
        if other is not None:
            raise duplicate(field_, "A provider with this name exists.")


def create_provider(db: Session, p: Principal, body: ProviderCreate) -> ProviderRead:
    _edit(p)
    if db.scalar(
        select(TrainingProvider.id).where(TrainingProvider.provider_code == body.provider_code)
    ):
        raise duplicate("provider_code", "This provider code exists.")
    pv = TrainingProvider(
        id=uuid.uuid4(),
        status=S.draft,
        suspension_periods=[],
        **body.model_dump(),
    )
    _validate(db, pv)
    _names(db, pv)
    cc.stamp(pv, p, create=True)
    db.add(pv)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_provider, pv, None)
    return provider_read(db, p, pv)


def update_provider(
    db: Session, p: Principal, provider_id: uuid.UUID, body: ProviderUpdate
) -> ProviderRead:
    _edit(p)
    pv = get(db, provider_id)
    before = cc.snap(pv)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(pv, k, v)
    _validate(db, pv)
    _names(db, pv)
    cc.stamp(pv, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.training_provider, pv, None, before)
    return provider_read(db, p, pv)


# ---- transitions ---------------------------------------------------------------------------------

ALLOWED: dict[
    TrainingProviderAction, tuple[set[TrainingProviderStatus], TrainingProviderStatus]
] = {
    A.submit: ({S.draft}, S.pending_approval),
    A.approve: ({S.pending_approval}, S.approved),
    A.return_: ({S.pending_approval}, S.draft),
    A.suspend: ({S.approved}, S.suspended),
    A.reinstate: ({S.suspended}, S.approved),
    A.blacklist: ({S.approved, S.suspended}, S.blacklisted),
    A.lift_blacklist: ({S.blacklisted}, S.suspended),
}


def _open(d: date) -> dict[str, Any]:
    return {"from": d.isoformat(), "to": None}


def _close_periods(periods: list[dict[str, Any]], d: date) -> list[dict[str, Any]]:
    return [{**x, "to": d.isoformat()} if x.get("to") is None else x for x in periods]


def transition(
    db: Session, p: Principal, provider_id: uuid.UUID, body: ProviderTransitionRequest
) -> ProviderRead:
    pv = get(db, provider_id)
    srcs, dst = ALLOWED[body.action]
    if pv.status not in srcs:
        raise invalid_transition("Training provider", pv.status, dst)
    if body.action == A.submit:
        _edit(p)
    else:
        _decide(p)
    before = cc.snap(pv)
    d = today()
    details: dict[str, Any] = {"action": body.action.value, "from": pv.status.value}
    if body.action == A.submit:
        if pv.kind == K.external and not any(
            a.register_checked_at is not None for a in accreditations(db, pv.id)
        ):
            raise ApiError(
                422,
                ErrorCode.PROVIDER_ACCREDITATION_REQUIRED,
                "Record at least one accreditation checked on the register.",
                "سجّل اعتماداً واحداً على الأقل متحققاً منه في السجل.",
            )
        pv.submitted_by_user_id = p.user.id
        pv.status_reason = None
    elif body.action == A.approve:
        pv.approved_by_user_id = p.user.id
        pv.approved_at = now()
        pv.status_reason = None
    elif body.action == A.return_:
        pv.status_reason = common.reason(body.reason, 10)
    elif body.action == A.suspend:
        pv.status_reason = common.reason(body.reason, 10)
        on = body.effective_on or d
        pv.suspension_periods = [
            *(pv.suspension_periods or []),
            {"from": on.isoformat(), "to": None},
        ]
    elif body.action == A.reinstate:
        pv.status_reason = common.reason(body.reason, 10)
        pv.suspension_periods = _close_periods(pv.suspension_periods or [], d)
    elif body.action == A.blacklist:
        r = common.reason(body.reason, 20)
        if body.blacklist_scope is None or (
            body.blacklist_scope == ProviderBlacklistScope.issued_from
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
            if body.blacklist_scope == ProviderBlacklistScope.issued_from
            else None
        )
        pv.blacklisted_on = d
        details["blacklist_scope"] = body.blacklist_scope.value
    elif body.action == A.lift_blacklist:
        pv.status_reason = common.reason(body.reason, 10)
        pv.blacklist_scope = None
        pv.blacklist_from = None
        pv.suspension_periods = [
            *(pv.suspension_periods or []),
            {"from": d.isoformat(), "to": None},
        ]
    pv.status = dst
    cc.stamp(pv, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_provider, pv, None, before, details
    )
    from app.services.cert import events  # noqa: PLC0415

    if body.action == A.blacklist:
        res = blacklist_cascade(db, pv, p)
        details["records_revoked"] = res
    if dst in (S.suspended, S.blacklisted, S.approved):
        events.publish(db, "training.provider_changed", worker_ids=_holder_ids(db, pv))
        if dst in (S.suspended, S.blacklisted):
            _alert_status(db, pv)
    return provider_read(db, p, pv)


def _holder_ids(db: Session, pv: TrainingProvider) -> set[uuid.UUID]:
    return set(
        db.scalars(select(TrainingRecord.worker_id).where(TrainingRecord.provider_id == pv.id))
    )


def blacklist_cascade(db: Session, pv: TrainingProvider, p: Principal | None) -> int:
    """PV-6: revoke records in scope (Accepted / Suspended → Revoked; Draft / Submitted →
    Rejected), publish `training.record_changed`."""
    from app.services.cert import events  # noqa: PLC0415

    d = today()
    at = now()
    n = 0
    workers: set[uuid.UUID] = set()
    for r in db.scalars(select(TrainingRecord).where(TrainingRecord.provider_id == pv.id)):
        if pv.blacklist_scope == ProviderBlacklistScope.issued_from and (
            pv.blacklist_from is None or r.completed_on < pv.blacklist_from
        ):
            continue
        if r.status in (RS.accepted, RS.suspended):
            new = RS.revoked
        elif r.status in (RS.draft, RS.submitted):
            new = RS.rejected
        else:
            continue
        before = cc.snap(r, exclude=("theory_score_pct",))
        r.status = new
        r.status_reason = TrainingStatusReason.provider_blacklisted
        r.status_changed_at = at
        r.ended_on = d
        n += 1
        workers.add(r.worker_id)
        cc.record(
            db,
            p,
            AuditAction.status_change,
            EntityType.training_record,
            r,
            r.project_id,
            before,
            {"cascade": "provider_blacklisted", "provider": pv.provider_code},
            after=cc.snap(r, exclude=("theory_score_pct",)),
        )
    db.flush()
    if workers:
        events.publish(db, "training.record_changed", worker_ids=workers)
        _alert_holders(db, pv, workers)
    return n


def _projects_of(db: Session, worker_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for dep in db.scalars(select(Deployment).where(Deployment.worker_id.in_(list(worker_ids)))):
        if dep.status.value != "demobilised":
            out.setdefault(dep.project_id, set()).add(dep.worker_id)
    return out


def _alert_holders(db: Session, pv: TrainingProvider, workers: set[uuid.UUID]) -> None:
    for pid, ws in _projects_of(db, workers).items():
        alerts.send(
            db,
            alerts.officers(db, pid),
            NotificationKind.training_provider_status,
            f"Provider {pv.provider_code} blacklisted: {len(ws)} holders need re-training",
            f"الجهة {pv.provider_code} محظورة: {len(ws)} من حاملي السجلات بحاجة لإعادة التدريب",
            EntityType.training_provider,
            pv.id,
            pid,
            email=True,
        )


def _alert_status(db: Session, pv: TrainingProvider) -> None:
    from app.models import Project  # noqa: PLC0415

    for pid in db.scalars(select(Project.id)):
        alerts.send(
            db,
            alerts.officers(db, pid),
            NotificationKind.training_provider_status,
            f"Training provider {pv.provider_code} is {pv.status.value}",
            f"جهة التدريب {pv.provider_code} أصبحت {pv.status.value}",
            EntityType.training_provider,
            pv.id,
            pid,
        )


def impact(db: Session, p: Principal, provider_id: uuid.UUID) -> ProviderImpact:
    _view(p)
    if not (p.is_manager or common.is_hse(p)):
        raise forbidden_error()
    pv = get(db, provider_id)
    holders: list[ProviderImpactHolder] = []
    revoked = 0
    for r in db.scalars(
        select(TrainingRecord)
        .where(TrainingRecord.provider_id == pv.id)
        .order_by(TrainingRecord.record_no)
    ):
        if r.status_reason == TrainingStatusReason.provider_blacklisted:
            revoked += 1
        elif not (
            pv.status in (S.suspended, S.blacklisted)
            and r.status in (RS.accepted, RS.submitted, RS.revoked)
        ):
            continue
        w = db.get(Worker, r.worker_id)
        if w is None:
            continue
        pids = common.worker_projects(db, w.id)
        show = any(common.names(p, pid) for pid in pids) or p.is_manager
        holders.append(
            ProviderImpactHolder(
                worker_id=w.id,
                worker_no=w.worker_no,
                full_name_en=w.full_name_en if show else None,
                full_name_ar=w.full_name_ar if show else None,
                course_code=r.course_code,
                record_no=r.record_no,
                completed_on=r.completed_on,
                project_ids=pids,
            )
        )
    sessions: list[uuid.UUID] = []
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.provider_id == pv.id,
            TrainingSession.status.in_([SessionStatus.draft, SessionStatus.scheduled]),
        )
    ):
        c = common.course(db, s.course_code)
        if c is None:
            continue
        days = [date.fromisoformat(x["date"]) for x in s.days]
        if any(not acceptable(db, pv, c, x).ok for x in days):
            sessions.append(s.id)
    return ProviderImpact(
        provider_id=pv.id,
        provider_code=pv.provider_code,
        records_revoked=revoked,
        holders=holders,
        sessions_not_allowed=sessions,
    )


def acceptability(
    db: Session,
    p: Principal,
    provider_id: uuid.UUID,
    course_code: str,
    on_dates: list[date],
    project_id: uuid.UUID | None,
    worker_ids: list[uuid.UUID] | None,
) -> ProviderAcceptability:
    _view(p)
    pv = get(db, provider_id)
    c = common.course_or_404(db, course_code)
    items = []
    for d in on_dates:
        a = acceptable(db, pv, c, d, project_id, worker_ids or [])
        items.append(
            AcceptabilityItem(
                on_date=d, acceptable=a.ok, reason=a.reason, worker_ids_not_own_tree=a.not_own_tree
            )
        )
    return ProviderAcceptability(provider_id=pv.id, course=common.course_ref(c), items=items)


# ---- accreditations ------------------------------------------------------------------------------


def _acc(db: Session, acc_id: uuid.UUID) -> TrainingProviderAccreditation:
    a = db.get(TrainingProviderAccreditation, acc_id)
    if a is None:
        raise not_found("Accreditation")
    return a


def _check_acc(db: Session, a: TrainingProviderAccreditation) -> None:
    if a.valid_until <= a.valid_from:
        raise validation_error("valid_until", "Must be after valid_from.")
    allc = common.courses(db)
    for x in a.scope_course_codes or []:
        if x not in allc:
            raise validation_error("scope_course_codes", f"Unknown course code {x}.")
    other = db.scalar(
        select(TrainingProviderAccreditation.id).where(
            TrainingProviderAccreditation.accreditation_body == a.accreditation_body,
            TrainingProviderAccreditation.accreditation_no == a.accreditation_no,
            TrainingProviderAccreditation.id != a.id,
        )
    )
    if other is not None:
        raise duplicate("accreditation_no", "This accreditation number exists for the body.")


def create_accreditation(
    db: Session, p: Principal, provider_id: uuid.UUID, body: ProviderAccreditationCreate
) -> ProviderAccreditationRead:
    _edit(p)
    pv = get(db, provider_id)
    data = body.model_dump()
    data["accreditation_body"] = body.accreditation_body.value
    a = TrainingProviderAccreditation(id=uuid.uuid4(), provider_id=pv.id, alerts_sent=[], **data)
    _check_acc(db, a)
    cc.stamp(a, p, create=True)
    db.add(a)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_provider_accreditation, a, None)
    return accreditation_read(db, a)


def update_accreditation(
    db: Session, p: Principal, acc_id: uuid.UUID, body: ProviderAccreditationUpdate
) -> ProviderAccreditationRead:
    _edit(p)
    a = _acc(db, acc_id)
    before = cc.snap(a)
    data = body.model_dump(exclude_unset=True)
    material = False
    for k, v0 in data.items():
        v = getattr(v0, "value", v0) if k == "accreditation_body" else v0
        if k in ("accreditation_body", "accreditation_no", "scope_course_codes", "valid_from",
                 "valid_until") and getattr(a, k) != v:  # fmt: skip
            material = True
        setattr(a, k, v)
    if material:
        a.register_checked_at = None
        a.register_checked_by_user_id = None
    _check_acc(db, a)
    cc.stamp(a, p)
    db.flush()
    cc.record(
        db, p, AuditAction.update, EntityType.training_provider_accreditation, a, None, before
    )
    return accreditation_read(db, a)


def register_check(
    db: Session, p: Principal, acc_id: uuid.UUID, body: RegisterCheckInput
) -> ProviderAccreditationRead:
    _edit(p)
    a = _acc(db, acc_id)
    before = cc.snap(a)
    a.register_checked_at = body.checked_at or now()
    a.register_checked_by_user_id = p.user.id
    a.register_check_note = body.note
    cc.stamp(a, p)
    db.flush()
    cc.record(
        db, p, AuditAction.update, EntityType.training_provider_accreditation, a, None, before
    )
    return accreditation_read(db, a)


def nominee_ids(db: Session, session_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(TrainingNomination.worker_id).where(
                TrainingNomination.session_id == session_id,
                TrainingNomination.withdrawn_at.is_(None),
            )
        )
    )
