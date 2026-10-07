"""Worker register, deployments and access cards (spec 2-access-permits §3.1, §3.2, §4.1, §4.2,
§5.1 WK-1…WK-12, §5.12 P2-x, LC-9, LC-10)."""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    AccessCardReissueReason,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    DeploymentStatus,
    InductionStatus,
    QrKind,
    QrTokenStatus,
    UnmaskReason,
    ValidityStatus,
    WorkerPersonType,
    WorkerStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, ContractorStatus, EntityType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner, ExportPurpose
from app.core.text import like_pattern, search_blob
from app.models import (
    Adp,
    AirportPass,
    Attachment,
    CredentialEvent,
    Deployment,
    GateCheck,
    InductionCourse,
    InductionRecord,
    Offence,
    PassApplication,
    Project,
    ProjectEngagement,
    Site,
    User,
    WapCrew,
    Worker,
    WorkerIdHistory,
)
from app.schemas.common import has_arabic
from app.schemas.hse_common import ApiWarning
from app.schemas.workers import (
    AccessCardRead,
    AccessCardReissueRequest,
    AccessCardSummary,
    CredentialBadge,
    DeploymentCreate,
    DeploymentFields,
    DeploymentPage,
    DeploymentRead,
    DeploymentTransitionRequest,
    DeploymentUpdate,
    InductionBadge,
    UnmaskRequest,
    WorkerCreate,
    WorkerDataReport,
    WorkerDataReportRequest,
    WorkerDeploymentSummary,
    WorkerIdLookup,
    WorkerIdNumberRead,
    WorkerListItem,
    WorkerLookupResult,
    WorkerPage,
    WorkerRead,
    WorkerTransitionRequest,
    WorkerUpdate,
)
from app.services import audit, projects
from app.services.access import common, lifecycle
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import (
    Grant,
    Principal,
    deny,
    engagement_descendants,
    forbidden_error,
)

C = Capability

# ---- scope ---------------------------------------------------------------------------------------


def dep_clause(p: Principal, cap: Capability) -> ColumnElement[bool]:
    """SQL filter: deployments covered by the caller's grants for `cap` (WK-11)."""
    grants = p.project_grants(cap)
    if grants is None:
        return true()
    parts = []
    for pid, g in grants.items():
        cond = [Deployment.project_id == pid]
        if g.site_ids is not None:
            cond.append(Deployment.site_ids.overlap(list(g.site_ids)))
        if g.engagement_ids is not None:
            cond.append(Deployment.engagement_id.in_(list(g.engagement_ids) or [uuid.UUID(int=0)]))
        parts.append(and_(*cond))
    return or_(*parts) if parts else false()


def dep_covered(p: Principal, d: Deployment, cap: Capability) -> Grant | None:
    g = p.grant(d.project_id, cap)
    return g if common.grant_covers(g, d.site_ids, d.engagement_id) else None


def _project_wide(p: Principal, cap: Capability) -> bool:
    grants = p.project_grants(cap)
    return grants is None or any(g.engagement_ids is None for g in grants.values())


def can_see(db: Session, p: Principal, w: Worker, cap: Capability = C.worker_view) -> bool:
    if p.is_manager:
        return True
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
    if not deps:
        return _project_wide(p, cap)
    return any(dep_covered(p, d, cap) for d in deps)


def get_worker(
    db: Session, p: Principal, worker_id: uuid.UUID, cap: Capability = C.worker_view
) -> Worker:
    w = db.get(Worker, worker_id)
    if w is None:
        raise not_found("Worker")
    if not p.has_any(cap):
        raise forbidden_error()
    if not can_see(db, p, w, cap):
        raise deny(db, p, EntityType.worker, worker_id, None, "Worker")
    return w


def get_deployment(
    db: Session, p: Principal, deployment_id: uuid.UUID, cap: Capability = C.worker_view
) -> Deployment:
    d = db.get(Deployment, deployment_id)
    if d is None:
        raise not_found("Deployment")
    if dep_covered(p, d, cap) is None:
        if p.grant(d.project_id, cap) is None and p.can_see_project(d.project_id):
            raise forbidden_error()
        raise deny(db, p, EntityType.worker_deployment, deployment_id, d.project_id, "Deployment")
    return d


# ---- reads ---------------------------------------------------------------------------------------


def photo_id(db: Session, worker_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(Attachment.id)
        .where(
            Attachment.owner_type == AttachmentOwner.worker_photo, Attachment.owner_id == worker_id
        )
        .order_by(Attachment.created_at.desc())
        .limit(1)
    )


def _badges(db: Session, d: Deployment) -> tuple[list[InductionBadge], list[CredentialBadge]]:
    inds: dict[str, InductionBadge] = {}
    for r, code in db.execute(
        select(InductionRecord, InductionCourse.code)
        .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
        .where(InductionRecord.worker_id == d.worker_id, InductionRecord.project_id == d.project_id)
        .order_by(InductionRecord.delivered_at)
    ):
        inds[code] = InductionBadge(
            course_code=code, status=r.status, valid_until=lifecycle.induction_valid_until(r)
        )
    creds: list[CredentialBadge] = []
    for ps in db.scalars(
        select(AirportPass)
        .where(AirportPass.worker_id == d.worker_id, AirportPass.project_id == d.project_id)
        .order_by(AirportPass.issued_on.desc())
    ):
        creds.append(
            CredentialBadge(
                kind="airport_pass",
                id=ps.id,
                number=ps.pass_no,
                validity_status=ps.validity_status,
                effective_valid_until=ps.effective_valid_until,
                detail=f"{ps.pass_category} · {ps.card_colour.value} · {', '.join(ps.area_codes)}",
            )
        )
    for a in db.scalars(
        select(Adp).where(Adp.worker_id == d.worker_id, Adp.project_id == d.project_id)
    ):
        creds.append(
            CredentialBadge(
                kind="adp",
                id=a.id,
                number=a.adp_no or "—",
                validity_status=a.validity_status,
                effective_valid_until=a.effective_valid_until,
                detail=a.category.value,
            )
        )
    return sorted(inds.values(), key=lambda b: b.course_code), creds


def deployment_read(
    db: Session,
    p: Principal | None,
    d: Deployment,
    refs: Refs | None = None,
    *,
    names: bool | None = None,
) -> DeploymentRead:
    refs = refs or Refs(db)
    w = db.get(Worker, d.worker_id)
    assert w is not None  # noqa: S101
    show = common.can_see_names(p, d.project_id) if names is None else names
    inds, creds = _badges(db, d)
    tok = common.latest_qr(db, d.id)
    return DeploymentRead(
        id=d.id,
        worker_id=w.id,
        worker_no=w.worker_no,
        full_name_en=w.full_name_en if show else None,
        full_name_ar=w.full_name_ar if show else None,
        project_id=d.project_id,
        engagement=refs.eng(d.engagement_id),
        employee_no=d.employee_no,
        trade=d.trade,
        sites=[refs.site(s) for s in d.site_ids or []],
        mobilised_on=d.mobilised_on,
        planned_demob_on=d.planned_demob_on,
        demobilised_on=d.demobilised_on,
        status=d.status,
        access_card=AccessCardSummary(
            issued_on=d.access_card_issued_on,
            reissue_count=d.reissue_count,
            token_status=tok.status if tok else None,
        ),
        inductions=inds,
        credentials=creds,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _summary(db: Session, d: Deployment, refs: Refs) -> WorkerDeploymentSummary:
    code = db.scalar(select(Project.code).where(Project.id == d.project_id)) or ""
    return WorkerDeploymentSummary(
        id=d.id,
        project_id=d.project_id,
        project_code=code,
        engagement=refs.eng(d.engagement_id),
        trade=d.trade,
        status=d.status,
        mobilised_on=d.mobilised_on,
        demobilised_on=d.demobilised_on,
    )


def worker_read(
    db: Session, p: Principal, w: Worker, warnings: list[ApiWarning] | None = None
) -> WorkerRead:
    refs = Refs(db)
    deps = [
        d
        for d in db.scalars(
            select(Deployment).where(Deployment.worker_id == w.id).order_by(Deployment.mobilised_on)
        )
        if p.is_manager or dep_covered(p, d, C.worker_view)
    ]
    anonymised = w.status == WorkerStatus.anonymised
    return WorkerRead(
        id=w.id,
        worker_no=w.worker_no,
        person_type=w.person_type,
        full_name_en=w.full_name_en,
        full_name_ar=w.full_name_ar,
        id_type=None if anonymised else w.id_type,
        id_number_masked=None if anonymised else w.id_number_masked,
        passport_country=w.passport_country,
        id_expiry_date=w.id_expiry_date,
        id_expired=bool(w.id_expiry_date and w.id_expiry_date < today()),
        nationality=w.nationality,
        adult_attestation=w.adult_attestation,
        primary_language=w.primary_language,
        user=refs.user(w.user_id),
        photo_attachment_id=None if anonymised else photo_id(db, w.id),
        status=w.status,
        ban_reason=w.ban_reason,
        deployments=[_summary(db, d, refs) for d in deps],
        warnings=warnings or [],
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


def _list_item(
    db: Session, p: Principal, w: Worker, dep: Deployment | None, refs: Refs
) -> WorkerListItem:
    return WorkerListItem(
        id=w.id,
        worker_no=w.worker_no,
        person_type=w.person_type,
        full_name_en=w.full_name_en,
        full_name_ar=w.full_name_ar,
        id_type=w.id_type,
        id_number_masked=w.id_number_masked,
        id_expiry_date=w.id_expiry_date,
        nationality=w.nationality,
        status=w.status,
        has_photo=photo_id(db, w.id) is not None,
        deployment=deployment_read(db, p, dep, refs) if dep else None,
    )


def list_workers(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    project_id: uuid.UUID | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    site_ids: list[uuid.UUID] | None,
    statuses: list[WorkerStatus] | None,
    deployment_statuses: list[DeploymentStatus] | None,
    person_type: Any,
    trade: Any,
    q: str | None,
    sort: str,
) -> WorkerPage:
    if not p.has_any(C.worker_view):
        raise forbidden_error()
    if project_id is not None:
        projects.get_visible(db, p, project_id)
    dep_filter: list[ColumnElement[bool]] = [dep_clause(p, C.worker_view)]
    if project_id:
        dep_filter.append(Deployment.project_id == project_id)
    if engagement_ids:
        engs: set[uuid.UUID] = set()
        for e in engagement_ids:
            engs |= engagement_descendants(db, e) if include_subcontractors else {e}
        dep_filter.append(Deployment.engagement_id.in_(engs))
    if site_ids:
        dep_filter.append(Deployment.site_ids.overlap(site_ids))
    if deployment_statuses:
        dep_filter.append(Deployment.status.in_(deployment_statuses))
    if trade:
        dep_filter.append(Deployment.trade == trade)
    has_dep = select(Deployment.worker_id).where(*dep_filter)
    stmt = select(Worker)
    narrowed = project_id or engagement_ids or site_ids or deployment_statuses or trade
    if not p.is_manager or narrowed:
        cond: ColumnElement[bool] = Worker.id.in_(has_dep)
        if not narrowed and _project_wide(p, C.worker_view):
            orphan = ~select(Deployment.id).where(Deployment.worker_id == Worker.id).exists()
            cond = or_(cond, orphan)
        stmt = stmt.where(cond)
    if statuses:
        stmt = stmt.where(Worker.status.in_(statuses))
    if person_type:
        stmt = stmt.where(Worker.person_type == person_type)
    if q:
        stmt = stmt.where(Worker.search_text.like(like_pattern(q)))
    key = {"worker_no": Worker.seq, "name": Worker.full_name_en}[sort.lstrip("-")]
    stmt = stmt.order_by(key.desc() if sort.startswith("-") else key)
    items, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    out = []
    for w in items:
        dep = None
        if project_id:
            dep = db.scalar(
                select(Deployment)
                .where(Deployment.worker_id == w.id, Deployment.project_id == project_id)
                .order_by(Deployment.created_at.desc())
                .limit(1)
            )
        out.append(_list_item(db, p, w, dep, refs))
    return WorkerPage(items=out, total=total, page=page, page_size=page_size)


def read_worker(db: Session, p: Principal, worker_id: uuid.UUID) -> WorkerRead:
    return worker_read(db, p, get_worker(db, p, worker_id))


# ---- create / update -----------------------------------------------------------------------------


def _snapshot(w: Worker) -> dict[str, Any]:
    """Audit view (masked ID only, WK-4/WK-9)."""
    return {
        "worker_no": w.worker_no,
        "person_type": w.person_type,
        "full_name_en": w.full_name_en,
        "full_name_ar": w.full_name_ar,
        "id_type": w.id_type,
        "id_number_masked": w.id_number_masked,
        "passport_country": w.passport_country,
        "id_expiry_date": w.id_expiry_date,
        "nationality": w.nationality,
        "primary_language": w.primary_language,
        "status": w.status,
    }


def _exists_error(db: Session, p: Principal, existing: Worker) -> ApiError:
    if can_see(db, p, existing):
        return ApiError(
            409,
            ErrorCode.WORKER_EXISTS,
            f"A worker with this ID already exists ({existing.worker_no}).",
            f"يوجد عامل مسجل بهذه الهوية ({existing.worker_no}).",
            meta={"worker_id": str(existing.id), "worker_no": existing.worker_no},
        )
    return ApiError(
        409,
        ErrorCode.WORKER_EXISTS_OUT_OF_SCOPE,
        "A worker with this ID is already registered by another organisation. Ask the HSE "
        "Officer to add a deployment.",
        "العامل مسجل مسبقاً لدى جهة أخرى. اطلب من مسؤول السلامة إضافة تعيين.",
    )


def _set_search(w: Worker) -> None:
    w.search_text = search_blob(w.worker_no, w.full_name_en, w.full_name_ar)


def _next_worker_no(db: Session) -> tuple[int, str]:
    db.execute(select(func.pg_advisory_xact_lock(0x574B5252)))  # "WKRR"
    seq = int(db.scalar(select(func.max(Worker.seq))) or 0) + 1
    return seq, f"WKR-{seq:06d}"


def create_worker(db: Session, p: Principal, body: WorkerCreate) -> WorkerRead:
    p.ensure_writer()
    if body.deployment is not None:
        project = projects.get_visible(db, p, body.deployment.project_id)
        common.require_cap(
            p, project.id, C.worker_edit, body.deployment.site_ids, body.deployment.engagement_id
        )
    elif not _project_wide(p, C.worker_edit) or not p.has_any(C.worker_edit):
        if p.has_any(C.worker_edit):
            raise forbidden_error("Contractor HSE Reps register workers with a deployment (WK-11).")
        raise forbidden_error()
    if not body.adult_attestation:
        raise ApiError(
            422,
            ErrorCode.ADULT_ATTESTATION_REQUIRED,
            "Confirm that the worker is 18 or older.",
            "يجب الإقرار بأن عمر العامل 18 سنة أو أكثر.",
        )
    if body.id_expiry_date <= today():
        raise validation_error("id_expiry_date", "The ID must not be expired.")
    if not has_arabic(body.full_name_ar):
        raise validation_error("full_name_ar", "Enter the Arabic name in Arabic script.")
    number = common.check_id(body.id_type, body.id_number, body.passport_country)
    bidx = common.blind_index(body.id_type, number, body.passport_country)
    existing = db.scalar(select(Worker).where(Worker.id_number_bidx == bidx))
    if existing is not None:
        raise _exists_error(db, p, existing)
    seq, no = _next_worker_no(db)
    w = Worker(
        id=uuid.uuid4(),
        seq=seq,
        worker_no=no,
        person_type=body.person_type,
        full_name_en=body.full_name_en,
        full_name_ar=body.full_name_ar,
        id_expiry_date=body.id_expiry_date,
        nationality=body.nationality,
        adult_attestation=True,
        primary_language=body.primary_language,
        user_id=body.user_id,
        status=WorkerStatus.active,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
        seed_fake=False,
    )
    common.set_worker_id(w, body.id_type, number, body.passport_country)
    _set_search(w)
    db.add(w)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(body.deployment.project_id if body.deployment else None),
        entity_type=EntityType.worker,
        entity_id=w.id,
        after=_snapshot(w),
    )
    if body.deployment is not None:
        dep = body.deployment
        _create_deployment(db, p, dep.project_id, w, dep)
    return worker_read(db, p, w)


def lookup(db: Session, p: Principal, body: WorkerIdLookup) -> WorkerLookupResult:
    """WK-3: exact match through the blind index; only workers in scope."""
    if not p.has_any(C.worker_view):
        raise forbidden_error()
    bidx = common.blind_index(body.id_type, body.id_number, body.passport_country)
    w = db.scalar(select(Worker).where(Worker.id_number_bidx == bidx))
    if w is None or not can_see(db, p, w):
        return WorkerLookupResult(items=[])
    return WorkerLookupResult(items=[_list_item(db, p, w, None, Refs(db))])


def _can_edit(db: Session, p: Principal, w: Worker) -> None:
    p.ensure_writer()
    if p.is_manager:
        return
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
    if not deps and _project_wide(p, C.worker_edit) and p.has_any(C.worker_edit):
        return
    if not any(dep_covered(p, d, C.worker_edit) for d in deps):
        raise forbidden_error()


def update_worker(
    db: Session, p: Principal, worker_id: uuid.UUID, body: WorkerUpdate
) -> WorkerRead:
    w = get_worker(db, p, worker_id)
    _can_edit(db, p, w)
    if w.status == WorkerStatus.anonymised:
        raise invalid_transition("Worker", w.status, "edited")
    before = _snapshot(w)
    ch = body.changes()
    warnings: list[ApiWarning] = []
    if "id_type" in ch or "id_number" in ch or "passport_country" in ch:
        id_type = ch.get("id_type", w.id_type)
        if id_type is None:
            raise validation_error("id_type", "ID type is required.")
        number = ch.get("id_number")
        if number is None:
            raise validation_error("id_number", "Send the full ID number with an ID change.")
        country = ch.get("passport_country", w.passport_country)
        n = common.check_id(id_type, number, country)
        bidx = common.blind_index(id_type, n, country)
        if bidx != w.id_number_bidx:
            other = db.scalar(select(Worker).where(Worker.id_number_bidx == bidx))
            if other is not None and other.id != w.id:
                raise _exists_error(db, p, other)
            if w.id_number_enc and w.id_type:
                db.add(
                    WorkerIdHistory(
                        id=uuid.uuid4(),
                        worker_id=w.id,
                        id_type=w.id_type,
                        id_number_enc=w.id_number_enc,
                        id_number_masked=w.id_number_masked or "",
                        passport_country=w.passport_country,
                        replaced_at=now(),
                        replaced_by_user_id=p.user.id,
                    )
                )
            common.set_worker_id(w, id_type, n, country)
    for k in ("full_name_en", "full_name_ar", "nationality", "primary_language", "user_id"):
        if k in ch:
            setattr(w, k, ch[k])
    if "full_name_ar" in ch and not has_arabic(w.full_name_ar):
        raise validation_error("full_name_ar", "Enter the Arabic name in Arabic script.")
    expiry_changed = "id_expiry_date" in ch and ch["id_expiry_date"] != w.id_expiry_date
    if "id_expiry_date" in ch:
        w.id_expiry_date = ch["id_expiry_date"]
        if w.id_expiry_date and w.id_expiry_date <= today():
            warnings.append(
                ApiWarning(
                    code=ErrorCode.ID_EXPIRED.value,
                    message="The ID expiry date is in the past; access is blocked (WK-7).",
                    message_ar="تاريخ انتهاء الهوية في الماضي؛ الدخول محظور.",
                    field="id_expiry_date",
                )
            )
    _set_search(w)
    w.updated_by_user_id = p.user.id
    w.updated_at = now()
    db.flush()
    if expiry_changed:
        lifecycle.refresh_worker(db, w.id)
    bf, af = audit.diff(before, _snapshot(w))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(None),
            entity_type=EntityType.worker,
            entity_id=w.id,
            before=bf,
            after=af,
        )
    return worker_read(db, p, w, warnings)


def revoke_all(
    db: Session,
    w: Worker,
    reason: CredentialReason,
    actor: uuid.UUID | None,
    engagement_ids: set[uuid.UUID] | None = None,
) -> None:
    """LC-8 / LC-9: every credential of the worker on every project (LC-8: only those held
    through the given engagements)."""
    at = now()

    def mine(eid: uuid.UUID | None) -> bool:
        return engagement_ids is None or eid in engagement_ids

    for ps in db.scalars(select(AirportPass).where(AirportPass.worker_id == w.id)):
        if mine(ps.engagement_id):
            lifecycle.revoke(db, ps, reason, None, actor, at=at)
    for a in db.scalars(select(Adp).where(Adp.worker_id == w.id)):
        if mine(a.engagement_id):
            lifecycle.revoke(db, a, reason, None, actor, at=at)
    for r in db.scalars(
        select(InductionRecord).where(
            InductionRecord.worker_id == w.id,
            InductionRecord.status.in_([InductionStatus.valid, InductionStatus.suspended]),
        )
    ):
        if mine(r.engagement_id):
            lifecycle.revoke(db, r, reason, None, actor, at=at)
    for d in db.scalars(select(Deployment).where(Deployment.worker_id == w.id)):
        if mine(d.engagement_id) and common.active_qr(db, d.id) is not None:
            lifecycle.revoke(db, d, reason, None, actor, at=at)
    if engagement_ids is None:
        for c in db.scalars(
            select(WapCrew).where(WapCrew.worker_id == w.id, WapCrew.removed_at.is_(None))
        ):
            c.removed_at = at


def transition_worker(
    db: Session, p: Principal, worker_id: uuid.UUID, body: WorkerTransitionRequest
) -> WorkerRead:
    w = get_worker(db, p, worker_id)
    p.ensure_writer()
    if not p.has_any(C.worker_ban):
        raise forbidden_error()
    before = _snapshot(w)
    if (
        w.status in (WorkerStatus.active, WorkerStatus.inactive)
        and body.to_status == WorkerStatus.banned
    ):
        w.status = WorkerStatus.banned
        w.ban_reason = body.reason
        revoke_all(db, w, CredentialReason.worker_banned, p.user.id)
    elif w.status == WorkerStatus.banned and body.to_status == WorkerStatus.active:
        w.status = WorkerStatus.active
        w.ban_reason = None
    else:
        raise invalid_transition("Worker", w.status, body.to_status)
    w.updated_by_user_id = p.user.id
    w.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(None),
        entity_type=EntityType.worker,
        entity_id=w.id,
        before={"status": before["status"]},
        after={"status": w.status},
        details={"reason": body.reason},
    )
    return worker_read(db, p, w)


def unmask(
    db: Session, p: Principal, worker_id: uuid.UUID, body: UnmaskRequest
) -> WorkerIdNumberRead:
    w = get_worker(db, p, worker_id)
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
    ok = p.is_manager or any(dep_covered(p, d, C.worker_unmask_id) for d in deps)
    if (
        not ok
        and not deps
        and _project_wide(p, C.worker_unmask_id)
        and p.has_any(C.worker_unmask_id)
    ):
        ok = True
    if not ok:
        raise forbidden_error("Revealing ID numbers needs capability 48.")
    if body.reason == UnmaskReason.other and not (body.reason_text or "").strip():
        raise validation_error("reason_text", "Describe the reason.")
    if w.id_number_enc is None or w.id_type is None:
        raise not_found("ID number")
    number = crypto.decrypt(w.id_number_enc)
    pid = deps[0].project_id if deps else None
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(pid),
        entity_type=EntityType.worker,
        entity_id=w.id,
        project_id=pid,
        fields_read=["id_number"],
        details={"reason": body.reason.value, "reason_text": body.reason_text},
    )
    return WorkerIdNumberRead(
        worker_id=w.id,
        id_type=w.id_type,
        id_number=number,
        passport_country=w.passport_country,
        revealed_at=now(),
    )


def data_report(
    db: Session, p: Principal, worker_id: uuid.UUID, body: WorkerDataReportRequest
) -> WorkerDataReport:
    """P2-11 (capability 79)."""
    w = get_worker(db, p, worker_id)
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
    if not (p.is_manager or any(dep_covered(p, d, C.export_access_identity) for d in deps)):
        raise forbidden_error("The data report needs capability 79.")
    if body.purpose == ExportPurpose.other and not (body.purpose_text or "").strip():
        raise ApiError(
            422,
            ErrorCode.EXPORT_PURPOSE_REQUIRED,
            "Describe the purpose.",
            "يرجى توضيح الغرض.",
        )

    def rows(model: Any, *where: Any) -> list[dict[str, object]]:
        out = []
        for r in db.scalars(select(model).where(*where)):
            d: dict[str, object] = {}
            for col in model.__table__.columns:
                if col.key.endswith("_enc") or col.key in ("id_number_bidx", "search_text"):
                    continue
                v = getattr(r, col.key)
                d[col.key] = v if isinstance(v, int | bool | str | float) or v is None else str(v)
            out.append(d)
        return out

    gate_count = db.scalar(
        select(func.count()).select_from(GateCheck).where(GateCheck.worker_id == w.id)
    )
    dep_ids = [d.id for d in deps]
    cred_ids = (
        dep_ids
        + list(db.scalars(select(InductionRecord.id).where(InductionRecord.worker_id == w.id)))
        + list(db.scalars(select(AirportPass.id).where(AirportPass.worker_id == w.id)))
        + list(db.scalars(select(Adp.id).where(Adp.worker_id == w.id)))
    )
    sections = {
        "deployments": rows(Deployment, Deployment.worker_id == w.id),
        "inductions": rows(InductionRecord, InductionRecord.worker_id == w.id),
        "pass_applications": rows(PassApplication, PassApplication.worker_id == w.id),
        "airport_passes": rows(AirportPass, AirportPass.worker_id == w.id),
        "adps": rows(Adp, Adp.worker_id == w.id),
        "offences": rows(Offence, Offence.worker_id == w.id),
        "wap_crew": rows(WapCrew, WapCrew.worker_id == w.id),
        "gate_log": [{"count": int(gate_count or 0)}],
        "credential_events": rows(CredentialEvent, CredentialEvent.credential_id.in_(cred_ids)),
    }
    audit.record(
        db,
        AuditAction.export,
        p.actor(deps[0].project_id if deps else None),
        entity_type=EntityType.worker,
        entity_id=w.id,
        details={"report": "worker_data_report", "purpose": body.purpose.value,
                 "purpose_text": body.purpose_text},
    )  # fmt: skip
    return WorkerDataReport(worker=worker_read(db, p, w), generated_at=now(), sections=sections)


# ---- deployments ---------------------------------------------------------------------------------


def _validate_deployment(
    db: Session,
    project: Project,
    w: Worker,
    eng_id: uuid.UUID | None,
    site_ids: list[uuid.UUID],
    mobilised_on: date,
    planned: date | None,
) -> ProjectEngagement | None:
    eng = None
    if w.person_type == WorkerPersonType.contractor_worker and eng_id is None:
        raise validation_error("engagement_id", "Contractor workers need an engagement.")
    if eng_id is not None:
        eng = db.get(ProjectEngagement, eng_id)
        if eng is None or eng.project_id != project.id:
            raise validation_error("engagement_id", "The engagement is not on this project.")
        if eng.contractor.status != ContractorStatus.approved:
            if eng.contractor.status == ContractorStatus.suspended:
                raise ApiError(
                    403,
                    ErrorCode.CONTRACTOR_SUSPENDED,
                    "The contractor is suspended.",
                    "المقاول موقوف.",
                )
            raise ApiError(
                422,
                ErrorCode.CONTRACTOR_NOT_APPROVED,
                "The contractor is not approved.",
                "المقاول غير معتمد.",
            )
        allowed = set(eng.site_ids or [])
        if mobilised_on < eng.mobilisation_date:
            raise validation_error("mobilised_on", "Before the engagement's mobilisation date.")
        if planned and eng.demobilisation_date and planned > eng.demobilisation_date:
            raise validation_error("planned_demob_on", "After the engagement's demobilisation.")
    else:
        allowed = set(db.scalars(select(Site.id).where(Site.project_id == project.id)))
    if not set(site_ids) <= allowed:
        raise validation_error("site_ids", "Sites must be within the engagement's sites.")
    if planned and planned < mobilised_on:
        raise validation_error("planned_demob_on", "Must be on or after mobilised_on.")
    return eng


def _create_deployment(
    db: Session, p: Principal, project_id: uuid.UUID, w: Worker, body: DeploymentFields
) -> Deployment:
    project = projects.get_visible(db, p, project_id)
    common.require_cap(p, project.id, C.worker_edit, body.site_ids, body.engagement_id)
    if w.status == WorkerStatus.banned:
        raise ApiError(409, ErrorCode.WORKER_BANNED, "The worker is banned.", "العامل محظور.")
    _validate_deployment(
        db, project, w, body.engagement_id, body.site_ids, body.mobilised_on, body.planned_demob_on
    )
    if db.scalar(
        select(Deployment.id).where(
            Deployment.worker_id == w.id,
            Deployment.project_id == project.id,
            Deployment.status != DeploymentStatus.demobilised,
        )
    ):
        raise ApiError(
            409,
            ErrorCode.DEPLOYMENT_EXISTS,
            "The worker already has an open deployment on this project. Demobilise it first.",
            "للعامل تعيين قائم في هذا المشروع. يجب إنهاؤه أولاً.",
        )
    if body.employee_no and db.scalar(
        select(Deployment.id).where(
            Deployment.engagement_id == body.engagement_id,
            Deployment.employee_no == body.employee_no,
            Deployment.status != DeploymentStatus.demobilised,
        )
    ):
        raise validation_error("employee_no", "Employee number already used in this engagement.")
    d = Deployment(
        id=uuid.uuid4(),
        worker_id=w.id,
        project_id=project.id,
        engagement_id=body.engagement_id,
        employee_no=body.employee_no,
        trade=body.trade,
        site_ids=list(body.site_ids),
        mobilised_on=body.mobilised_on,
        planned_demob_on=body.planned_demob_on,
        status=DeploymentStatus.pending_induction,
        reissue_count=0,
        passport_alerts_sent=[],
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
        seed_fake=False,
    )
    db.add(d)
    if w.status == WorkerStatus.inactive:
        w.status = WorkerStatus.active
        w.inactive_since = None
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.worker_deployment,
        entity_id=d.id,
        project_id=project.id,
        after=_dep_snapshot(d),
    )
    return d


def _dep_snapshot(d: Deployment) -> dict[str, Any]:
    return {
        "engagement_id": d.engagement_id,
        "employee_no": d.employee_no,
        "trade": d.trade,
        "site_ids": [str(s) for s in d.site_ids or []],
        "mobilised_on": d.mobilised_on,
        "planned_demob_on": d.planned_demob_on,
        "demobilised_on": d.demobilised_on,
        "status": d.status,
    }


def create_deployment(
    db: Session, p: Principal, project_id: uuid.UUID, body: DeploymentCreate
) -> DeploymentRead:
    p.ensure_writer()
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise not_found("Worker")
    d = _create_deployment(db, p, project_id, w, body)
    return deployment_read(db, p, d)


def list_deployments(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    site_ids: list[uuid.UUID] | None,
    statuses: list[DeploymentStatus] | None,
    trade: Any,
    q: str | None,
) -> DeploymentPage:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(Deployment)
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(Deployment.project_id == project.id, dep_clause(p, C.worker_view))
    )
    if engagement_ids:
        engs: set[uuid.UUID] = set()
        for e in engagement_ids:
            engs |= engagement_descendants(db, e) if include_subcontractors else {e}
        stmt = stmt.where(Deployment.engagement_id.in_(engs))
    if site_ids:
        stmt = stmt.where(Deployment.site_ids.overlap(site_ids))
    if statuses:
        stmt = stmt.where(Deployment.status.in_(statuses))
    if trade:
        stmt = stmt.where(Deployment.trade == trade)
    if q:
        stmt = stmt.where(Worker.search_text.like(like_pattern(q)))
    stmt = stmt.order_by(Worker.seq, Deployment.created_at)
    items, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    return DeploymentPage(
        items=[deployment_read(db, p, d, refs) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


def read_deployment(db: Session, p: Principal, deployment_id: uuid.UUID) -> DeploymentRead:
    return deployment_read(db, p, get_deployment(db, p, deployment_id))


def update_deployment(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: DeploymentUpdate
) -> DeploymentRead:
    d = get_deployment(db, p, deployment_id)
    common.require_cap(p, d.project_id, C.worker_edit, d.site_ids, d.engagement_id)
    if d.status == DeploymentStatus.demobilised:
        raise invalid_transition("Deployment", d.status, "edited")
    project = db.get(Project, d.project_id)
    w = db.get(Worker, d.worker_id)
    assert project is not None and w is not None  # noqa: S101
    before = _dep_snapshot(d)
    ch = body.changes()
    for k, v in ch.items():
        setattr(d, k, v)
    _validate_deployment(
        db, project, w, d.engagement_id, list(d.site_ids), d.mobilised_on, d.planned_demob_on
    )
    d.updated_by_user_id = p.user.id
    d.updated_at = now()
    db.flush()
    if "planned_demob_on" in ch:
        lifecycle.refresh_worker(db, w.id)
    bf, af = audit.diff(before, _dep_snapshot(d))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(d.project_id),
            entity_type=EntityType.worker_deployment,
            entity_id=d.id,
            project_id=d.project_id,
            before=bf,
            after=af,
        )
    return deployment_read(db, p, d)


def demobilise(
    db: Session,
    d: Deployment,
    on: date,
    reason: CredentialReason,
    actor: uuid.UUID | None,
) -> None:
    """LC-10: pass and ADP revoked (`demobilised`), custody return due from the demobilisation
    date, access-card token revoked, WAP crew entries removed."""
    d.status = DeploymentStatus.demobilised
    d.demobilised_on = on
    s = common.settings(db, d.project_id)
    at = now()
    for ps in db.scalars(
        select(AirportPass).where(
            AirportPass.deployment_id == d.id,
            AirportPass.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
        )
    ):
        lifecycle.revoke(db, ps, reason, None, actor, s, at)
        ps.return_due_on = on + timedelta(days=s.pass_return_days)
    for a in db.scalars(
        select(Adp).where(
            Adp.deployment_id == d.id,
            Adp.validity_status.in_(
                [ValidityStatus.active, ValidityStatus.suspended, ValidityStatus.pending]
            ),
        )
    ):
        lifecycle.revoke(db, a, reason, None, actor, s, at)
        if a.custody_status is not None:
            a.return_due_on = on + timedelta(days=s.pass_return_days)
    if common.active_qr(db, d.id) is not None:
        lifecycle.revoke(db, d, reason, None, actor, s, at)
    for c in db.scalars(
        select(WapCrew).where(WapCrew.worker_id == d.worker_id, WapCrew.removed_at.is_(None))
    ):
        c.removed_at = at
    d.updated_at = at
    db.flush()


def transition_deployment(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: DeploymentTransitionRequest
) -> DeploymentRead:
    d = get_deployment(db, p, deployment_id)
    common.require_cap(p, d.project_id, C.worker_edit, d.site_ids, d.engagement_id)
    if body.to_status != DeploymentStatus.demobilised or d.status == DeploymentStatus.demobilised:
        raise invalid_transition("Deployment", d.status, body.to_status)
    before = d.status
    on = body.demobilised_on or today()
    if on < d.mobilised_on:
        raise validation_error("demobilised_on", "Before the mobilisation date.")
    demobilise(db, d, on, CredentialReason.demobilised, p.user.id)
    d.updated_by_user_id = p.user.id
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(d.project_id),
        entity_type=EntityType.worker_deployment,
        entity_id=d.id,
        project_id=d.project_id,
        before={"status": before},
        after={"status": d.status, "demobilised_on": on},
        details={"reason": body.reason},
    )
    return deployment_read(db, p, d)


# ---- access card ---------------------------------------------------------------------------------


def printed_ref(db: Session, d: Deployment) -> str:
    w = db.get(Worker, d.worker_id)
    code = db.scalar(select(Project.code).where(Project.id == d.project_id))
    return f"{w.worker_no if w else ''} / {code}"


def mobilise(db: Session, d: Deployment, on: date) -> None:
    """IN-1: pending_induction → mobilised on the first passed general_site induction; the
    access-card token is issued."""
    if d.status != DeploymentStatus.pending_induction:
        return
    d.status = DeploymentStatus.mobilised
    d.inducted_on = on
    d.access_card_issued_on = on
    common.issue_qr(db, QrKind.AC, d.project_id, d.id, printed_ref(db, d))


def _card(db: Session, d: Deployment) -> AccessCardRead:
    tok = common.active_qr(db, d.id)
    if d.status != DeploymentStatus.mobilised or tok is None or d.access_card_issued_on is None:
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "The access card is issued after the general site induction is passed.",
            "تصدر بطاقة الدخول بعد اجتياز التعريف العام بالموقع.",
        )
    w = db.get(Worker, d.worker_id)
    assert w is not None  # noqa: S101
    eng = Refs(db).eng(d.engagement_id)
    return AccessCardRead(
        deployment_id=d.id,
        worker_no=w.worker_no,
        full_name_en=w.full_name_en,
        full_name_ar=w.full_name_ar,
        employer_short_code=eng.short_code if eng else None,
        photo_attachment_id=photo_id(db, w.id),
        qr_payload=common.payload(tok),
        printed_ref=tok.printed_ref,
        issued_on=d.access_card_issued_on,
        reissue_count=d.reissue_count,
        token_status=tok.status,
    )


def access_card(db: Session, p: Principal, deployment_id: uuid.UUID) -> AccessCardRead:
    d = get_deployment(db, p, deployment_id)
    common.require_cap(p, d.project_id, C.worker_edit, d.site_ids, d.engagement_id, write=False)
    return _card(db, d)


def reissue_card(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: AccessCardReissueRequest
) -> AccessCardRead:
    d = get_deployment(db, p, deployment_id)
    common.require_cap(p, d.project_id, C.worker_edit, d.site_ids, d.engagement_id)
    if d.status != DeploymentStatus.mobilised:
        raise invalid_transition("Access card", d.status, "reissued")
    lost = body.reason == AccessCardReissueReason.lost
    common.end_qr(db, d.id, QrTokenStatus.rotated, lost=lost)
    common.issue_qr(db, QrKind.AC, d.project_id, d.id, printed_ref(db, d))
    d.reissue_count += 1
    d.access_card_issued_on = today()
    lifecycle.event(
        db,
        d,
        CredentialAction.token_rotated,
        CredentialReason.lost_stolen if lost else CredentialReason.superseded,
        body.reason_text,
        p.user.id,
    )
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(d.project_id),
        entity_type=EntityType.worker_deployment,
        entity_id=d.id,
        project_id=d.project_id,
        details={"access_card": "reissued", "reason": body.reason.value},
    )
    return _card(db, d)


def user_by_id(db: Session, uid: uuid.UUID | None) -> User | None:
    return db.get(User, uid) if uid else None


__all__ = ["CredentialKind"]
