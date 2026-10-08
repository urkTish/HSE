"""Corrective actions (spec 1-dashboard §3.8, §4.5, rules CA-1…CA-8, §6.6)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import (
    AttachmentOwner,
    CaPriority,
    CaSourceType,
    CaStatus,
    ControlLevel,
    ExtensionStatus,
    ObservationStatus,
    OverdueBucket,
)
from app.kpi.engine import BUCKETS, bucket_of
from app.models import (
    AiAnswerRecord,
    Attachment,
    CaExtension,
    CorrectiveAction,
    Incident,
    Inspection,
    Observation,
    Project,
    RoleAssignment,
    User,
)
from app.schemas.actions import (
    CaCreate,
    CaExtensionCreate,
    CaExtensionDecision,
    CaExtensionRead,
    CaInline,
    CaPage,
    CaRead,
    CaSourceRef,
    CaTransitionRequest,
    CaUpdate,
)
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.incidents import LinkedCaSummary
from app.services import audit, hse_settings, notify, projects
from app.services.common import ensure_open, invalid_transition, paginate, require_reason
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    covers,
    id_warnings,
    make_ref,
    next_seq,
    project_today,
    user_roles,
)
from app.services.permissions import Principal, deny, engagement_descendants, forbidden_error

ST = CaStatus
OPEN = (ST.open, ST.in_progress)
LIVE = (ST.open, ST.in_progress, ST.pending_verification)
HIGH = (CaPriority.critical, CaPriority.high)
UNKNOWN = UserRef(id=uuid.UUID(int=0), full_name_en="—")
PRIORITY_ORDER = {
    CaPriority.critical: 0,
    CaPriority.high: 1,
    CaPriority.medium: 2,
    CaPriority.low: 3,
}


# ---- derived flags (§6.6, K-42/K-42b) ------------------------------------------------------------


def overdue_at(ca: CorrectiveAction, day: date) -> bool:
    """Same definition as the KPI engine (K-42): not completed or closed by `day`, day > due."""
    if ca.status == ST.cancelled or ca.created_date > day:
        return False
    done = ca.completed_date is not None and ca.completed_date <= day
    closed = ca.verified_date is not None and ca.verified_date <= day
    return not done and not closed and day > ca.due_date


def verification_overdue_at(ca: CorrectiveAction, day: date) -> bool:
    if ca.status == ST.cancelled or ca.completed_date is None or ca.completed_date > day:
        return False
    closed = ca.verified_date is not None and ca.verified_date <= day
    return not closed and day > ca.completed_date + timedelta(days=3)


def overdue_sql(day: date) -> Any:
    C = CorrectiveAction  # noqa: N806
    return and_(
        C.status != ST.cancelled,
        C.created_date <= day,
        or_(C.completed_date.is_(None), C.completed_date > day),
        or_(C.verified_date.is_(None), C.verified_date > day),
        C.due_date < day,
    )


def verification_overdue_sql(day: date) -> Any:
    C = CorrectiveAction  # noqa: N806
    return and_(
        C.status != ST.cancelled,
        C.completed_date.is_not(None),
        C.completed_date + 3 < day,
        or_(C.verified_date.is_(None), C.verified_date > day),
    )


def summaries(
    db: Session, source_type: CaSourceType, ids: Sequence[uuid.UUID], day: date
) -> dict[uuid.UUID, list[LinkedCaSummary]]:
    out: dict[uuid.UUID, list[LinkedCaSummary]] = defaultdict(list)
    if not ids:
        return out
    for ca in db.scalars(
        select(CorrectiveAction)
        .where(CorrectiveAction.source_type == source_type, CorrectiveAction.source_id.in_(ids))
        .order_by(CorrectiveAction.seq)
    ):
        assert ca.source_id is not None  # noqa: S101
        out[ca.source_id].append(
            LinkedCaSummary(
                id=ca.id,
                ref=ca.ref,
                title=ca.title,
                status=ca.status,
                control_level=ca.control_level,
                due_date=ca.due_date,
                overdue=overdue_at(ca, day),
            )
        )
    return out


# ---- visibility ----------------------------------------------------------------------------------


def can_view(p: Principal, ca: CorrectiveAction) -> bool:
    if p.user.id in (ca.owner_id, ca.verifier_id, ca.created_by_user_id):
        return True
    return covers(
        p.grant(ca.project_id, Capability.incident_view), ca.site_id, ca.responsible_engagement_id
    )


def get_ca(db: Session, p: Principal, ca_id: uuid.UUID) -> CorrectiveAction:
    ca = db.get(CorrectiveAction, ca_id)
    if ca is None or not can_view(p, ca):
        raise deny(db, p, EntityType.corrective_action, ca_id, ca.project_id if ca else None, "CA")
    return ca


def scoped_query(p: Principal, project: Project) -> Select[Any]:
    C = CorrectiveAction  # noqa: N806
    stmt = select(C).where(C.project_id == project.id)
    uid = p.user.id
    own = or_(C.owner_id == uid, C.verifier_id == uid, C.created_by_user_id == uid)
    g = p.grant(project.id, Capability.incident_view)
    if g is None:
        return stmt.where(own)
    conds: list[Any] = []
    if g.site_ids is not None:
        conds.append(C.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        conds.append(C.responsible_engagement_id.in_(engs) if engs else false())
    if conds:
        stmt = stmt.where(or_(and_(*conds), own))
    return stmt


# ---- read ----------------------------------------------------------------------------------------


def _source_ref(db: Session, ca: CorrectiveAction) -> CaSourceRef:
    ref = None
    model: Any = {
        CaSourceType.incident: Incident,
        CaSourceType.observation: Observation,
        CaSourceType.inspection: Inspection,
    }.get(ca.source_type)
    if model is not None and ca.source_id:
        row = db.get(model, ca.source_id)
        ref = row.ref if row else None
    elif ca.source_type == CaSourceType.ai_recommendation:
        ref = ca.ai_recommendation_id or (str(ca.source_id) if ca.source_id else None)
    elif ca.source_type == CaSourceType.ptw_audit and ca.source_id:
        from app.models import PtwAudit  # noqa: PLC0415

        pa = db.get(PtwAudit, ca.source_id)
        ref = pa.audit_no if pa else None
    return CaSourceRef(type=ca.source_type, id=ca.source_id, ref=ref)


def allowed(p: Principal, ca: CorrectiveAction) -> list[CaStatus]:
    out = []
    for to in CaStatus:
        try:
            _authorise(p, ca, to)
        except ApiError:
            continue
        out.append(to)
    return out


def to_read(
    db: Session,
    p: Principal,
    ca: CorrectiveAction,
    warnings: list[ApiWarning] | None = None,
    day: date | None = None,
) -> CaRead:
    exts = list(
        db.scalars(
            select(CaExtension).where(CaExtension.ca_id == ca.id).order_by(CaExtension.requested_at)
        )
    )
    refs = Refs(db).load(
        sites=[ca.site_id],
        zones=[ca.zone_id],
        engs=[ca.responsible_engagement_id],
        users=[ca.owner_id, ca.verifier_id]
        + [e.requested_by_user_id for e in exts]
        + [e.decided_by_user_id for e in exts],
    )
    if day is None:
        project = db.get(Project, ca.project_id)
        assert project is not None  # noqa: S101
        day = project_today(project)
    od = overdue_at(ca, day)
    days = (day - ca.due_date).days if od else None
    evidence = db.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.owner_type == AttachmentOwner.corrective_action_evidence,
            Attachment.owner_id == ca.id,
        )
    )
    return CaRead(
        id=ca.id,
        ref=ca.ref,
        project_id=ca.project_id,
        source=_source_ref(db, ca),
        site=refs.site(ca.site_id),
        zone=refs.zone(ca.zone_id),
        responsible_engagement=refs.eng_required(ca.responsible_engagement_id),
        title=ca.title,
        description=ca.description,
        control_level=ca.control_level,
        priority=ca.priority,
        owner=refs.user(ca.owner_id) or UNKNOWN,
        verifier=refs.user(ca.verifier_id) or UNKNOWN,
        due_date=ca.due_date,
        original_due_date=ca.original_due_date,
        extensions=[
            CaExtensionRead(
                id=e.id,
                new_due_date=e.new_due_date,
                previous_due_date=e.previous_due_date,
                reason=e.reason,
                status=e.status,
                requested_by=refs.user(e.requested_by_user_id) or UNKNOWN,
                requested_at=e.requested_at,
                decided_by=refs.user(e.decided_by_user_id),
                decided_at=e.decided_at,
                decision_comment=e.decision_comment,
            )
            for e in exts
        ],
        status=ca.status,
        completed_at=ca.completed_at,
        evidence_text=ca.evidence_text,
        evidence_attachment_count=int(evidence or 0),
        verified_at=ca.verified_at,
        verification_comment=ca.verification_comment,
        cancel_reason=ca.cancel_reason,
        overdue=od,
        days_overdue=days,
        overdue_bucket=bucket_of(days) if days is not None else None,
        verification_overdue=verification_overdue_at(ca, day),
        allowed_transitions=allowed(p, ca),
        warnings=warnings or [],
        created_at=ca.created_at,
        updated_at=ca.updated_at,
    )


def read(db: Session, p: Principal, ca_id: uuid.UUID) -> CaRead:
    return to_read(db, p, get_ca(db, p, ca_id))


# ---- validation ----------------------------------------------------------------------------------


def _check_people(
    db: Session,
    project: Project,
    owner_id: uuid.UUID,
    verifier_id: uuid.UUID,
    priority: CaPriority,
    engagement_id: uuid.UUID,
) -> None:
    owner = db.get(User, owner_id)
    if owner is None or not user_roles(db, owner_id, project.id):
        raise validation_error("owner_id", "The owner must be an active user on this project.")
    if verifier_id == owner_id:
        raise ApiError(
            422,
            ErrorCode.VERIFIER_IS_OWNER,
            "The verifier cannot be the owner of the action (CA-5).",
            "لا يمكن أن يكون المُحقِّق هو المسؤول عن التنفيذ.",
        )
    roles = user_roles(db, verifier_id, project.id)
    allowed_roles = {Role.hse_officer, Role.hse_manager}
    if priority not in HIGH:
        allowed_roles |= {Role.site_engineer, Role.contractor_hse_rep}
    ok = bool(roles & allowed_roles)
    if ok and not roles & {Role.hse_officer, Role.hse_manager, Role.site_engineer}:
        # contractor HSE rep: only within their contractor tree (C scope)
        ok = _rep_covers(db, verifier_id, project.id, engagement_id)
    if not ok:
        raise ApiError(
            422,
            ErrorCode.VERIFIER_ROLE_NOT_ALLOWED,
            "Critical/high actions are verified by an HSE Officer or the HSE Manager; medium/low "
            "also by a Site Engineer or the responsible Contractor HSE Rep (CA-5).",
            "دور المُحقِّق غير مسموح لهذه الأولوية.",
        )


def _rep_covers(db: Session, user_id: uuid.UUID, project_id: uuid.UUID, eng: uuid.UUID) -> bool:
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.project_id == project_id,
            RoleAssignment.role == Role.contractor_hse_rep,
            RoleAssignment.revoked_at.is_(None),
        )
    ):
        if a.contractor_engagement_id and eng in engagement_descendants(
            db, a.contractor_engagement_id
        ):
            return True
    return False


def _resolve_source(
    db: Session, project: Project, source_type: CaSourceType, source_id: uuid.UUID | None
) -> Any:
    if source_type == CaSourceType.other:
        return None
    if source_id is None:
        raise validation_error("source_id", "The source is required.")
    if source_type == CaSourceType.ptw_audit:
        from app.services.ptw import audits  # noqa: PLC0415

        return audits.ca_source(db, project.id, source_id)
    model: Any = {
        CaSourceType.incident: Incident,
        CaSourceType.observation: Observation,
        CaSourceType.inspection: Inspection,
        CaSourceType.ai_recommendation: AiAnswerRecord,
    }[source_type]
    row = db.get(model, source_id)
    if row is None or getattr(row, "project_id", project.id) != project.id:
        raise validation_error("source_id", "The source record is not on this project.")
    return row


def new_ca(
    db: Session,
    p: Principal,
    project: Project,
    inline: CaInline,
    source_type: CaSourceType,
    source: Any,
    *,
    site_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    ai_recommendation_id: str | None = None,
) -> tuple[CorrectiveAction, list[ApiWarning]]:
    """Create one CA (also used inline by inspections). Caller has checked capability 34."""
    site = site_id or getattr(source, "site_id", None)
    if site is None:
        raise validation_error("site_id", "The site is required.")
    zone = zone_id if zone_id is not None else getattr(source, "zone_id", None)
    check_site_zone(db, project, site, zone)
    eng_id = (
        inline.responsible_engagement_id
        or getattr(source, "responsible_engagement_id", None)
        or getattr(source, "observed_engagement_id", None)
        or getattr(source, "engagement_id", None)
    )
    if eng_id is None:
        raise validation_error(
            "responsible_engagement_id", "The responsible contractor is required."
        )
    check_engagement(db, project, eng_id, "responsible_engagement_id")
    _check_people(db, project, inline.owner_id, inline.verifier_id, inline.priority, eng_id)
    s = hse_settings.get(db, project.id)
    created = project_today(project)
    default_due = created + timedelta(days=hse_settings.ca_due_days(s, inline.priority))
    due = inline.due_date or default_due
    if due < created:
        raise validation_error("due_date", "The due date cannot be before today.")
    if due > default_due:
        raise ApiError(
            422,
            ErrorCode.DUE_DATE_TOO_LATE,
            f"The latest due date for {inline.priority.value} priority is "
            f"{default_due.isoformat()}; request an extension instead (CA-2).",
            "تاريخ الاستحقاق متأخر عن الافتراضي؛ اطلب تمديداً.",
        )
    year = created.year
    seq = next_seq(db, CorrectiveAction, project.id, year)
    ca = CorrectiveAction(
        project_id=project.id,
        ref=make_ref("CA", project.code, year, seq, 5),
        year=year,
        seq=seq,
        source_type=source_type,
        source_id=getattr(source, "id", None),
        ai_recommendation_id=ai_recommendation_id,
        site_id=site,
        zone_id=zone,
        responsible_engagement_id=eng_id,
        title=inline.title,
        description=inline.description,
        control_level=inline.control_level,
        priority=inline.priority,
        owner_id=inline.owner_id,
        verifier_id=inline.verifier_id,
        created_date=created,
        due_date=due,
        original_due_date=due,
        status=ST.open,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(ca)
    db.flush()
    warnings = id_warnings(title=ca.title, description=ca.description)
    if source_type == CaSourceType.incident and source is not None:
        others = list(
            db.scalars(
                select(CorrectiveAction).where(
                    CorrectiveAction.source_type == CaSourceType.incident,
                    CorrectiveAction.source_id == source.id,
                    CorrectiveAction.status != ST.cancelled,
                )
            )
        )
        if (source.potential_severity or 0) >= 3 and all(
            x.control_level == ControlLevel.ppe for x in others
        ):
            warnings.append(
                ApiWarning(
                    code="PPE_ONLY_CONTROL",
                    message="PPE is the lowest control — record why higher controls are not "
                    "reasonably practicable (CA-6).",
                    message_ar="معدات الوقاية هي أدنى مستويات التحكم — سجّل سبب عدم إمكانية "
                    "تطبيق ضوابط أعلى.",
                    field="control_level",
                )
            )
    if (
        source_type == CaSourceType.observation
        and source is not None
        and source.status == ObservationStatus.open
    ):
        source.status = ObservationStatus.action_raised
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=project.id,
        after=_snapshot(ca),
    )
    _notify_owner(db, ca)
    return ca, warnings


def _notify_owner(db: Session, ca: CorrectiveAction) -> None:
    notify.notify(
        db,
        [ca.owner_id],
        NotificationKind.ca_assigned,
        f"{ca.ref} assigned to you (due {ca.due_date.isoformat()})",
        f"تم إسناد {ca.ref} إليك (الاستحقاق {ca.due_date.isoformat()})",
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=ca.project_id,
    )


def _snapshot(ca: CorrectiveAction) -> dict[str, Any]:
    keys = (
        "title",
        "control_level",
        "priority",
        "owner_id",
        "verifier_id",
        "zone_id",
        "due_date",
        "status",
        "completed_at",
        "verified_at",
        "cancel_reason",
    )
    return {k: getattr(ca, k) for k in keys}


# ---- API operations ------------------------------------------------------------------------------


def create(db: Session, p: Principal, project_id: uuid.UUID, body: CaCreate) -> CaRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    g = p.require(project.id, Capability.ca_create)
    if body.source_type == CaSourceType.ai_recommendation and not body.ai_recommendation_id:
        raise validation_error("ai_recommendation_id", "Give the recommendation id (CA-7).")
    source = _resolve_source(db, project, body.source_type, body.source_id)
    site = body.site_id or getattr(source, "site_id", None)
    eng = (
        body.responsible_engagement_id
        or getattr(source, "responsible_engagement_id", None)
        or getattr(source, "observed_engagement_id", None)
        or getattr(source, "engagement_id", None)
    )
    if not covers(g, site, eng):
        raise forbidden_error("This site or contractor is outside your scope.")
    ca, warnings = new_ca(
        db,
        p,
        project,
        body,
        body.source_type,
        source,
        site_id=body.site_id,
        zone_id=body.zone_id,
        ai_recommendation_id=body.ai_recommendation_id,
    )
    return to_read(db, p, ca, warnings)


def _staff(p: Principal, ca: CorrectiveAction) -> bool:
    return covers(p.grant(ca.project_id, Capability.ca_approve_extension), ca.site_id, None)


def update(db: Session, p: Principal, ca_id: uuid.UUID, body: CaUpdate) -> CaRead:
    ca = get_ca(db, p, ca_id)
    project = db.get(Project, ca.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    if ca.status not in OPEN:
        raise invalid_transition("Corrective action", ca.status, "edited")
    staff = _staff(p, ca)
    if not staff and p.user.id != ca.owner_id:
        raise forbidden_error()
    ch = body.changes()
    if {"owner_id", "verifier_id", "priority"} & set(ch) and not staff:
        raise forbidden_error("Only HSE staff may change the owner, verifier or priority.")
    before = _snapshot(ca)
    old_owner = ca.owner_id
    for k in ("title", "description", "control_level", "priority", "owner_id", "verifier_id"):
        if k in ch:
            setattr(ca, k, ch[k])
    if "zone_id" in ch:
        check_site_zone(db, project, ca.site_id, ch["zone_id"])
        ca.zone_id = ch["zone_id"]
    if {"owner_id", "verifier_id", "priority"} & set(ch):
        _check_people(
            db, project, ca.owner_id, ca.verifier_id, ca.priority, ca.responsible_engagement_id
        )
    ca.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snapshot(ca))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(ca.project_id),
            entity_type=EntityType.corrective_action,
            entity_id=ca.id,
            project_id=ca.project_id,
            before=bf,
            after=af,
        )
    if ca.owner_id != old_owner:
        _notify_owner(db, ca)
    return to_read(db, p, ca, id_warnings(title=ca.title, description=ca.description))


def _authorise(p: Principal, ca: CorrectiveAction, to: CaStatus) -> None:
    src = ca.status
    uid = p.user.id
    edges: dict[tuple[CaStatus, CaStatus], bool] = {
        (ST.open, ST.in_progress): uid == ca.owner_id,
        (ST.open, ST.pending_verification): uid == ca.owner_id,
        (ST.in_progress, ST.pending_verification): uid == ca.owner_id,
        (ST.pending_verification, ST.closed): uid == ca.verifier_id or p.is_manager,
        (ST.pending_verification, ST.in_progress): uid == ca.verifier_id or p.is_manager,
        (ST.open, ST.cancelled): _staff(p, ca),
        (ST.in_progress, ST.cancelled): _staff(p, ca),
        (ST.closed, ST.in_progress): p.is_manager,
    }
    ok = edges.get((src, to))
    if ok is None:
        raise invalid_transition("Corrective action", src, to)
    p.ensure_writer()
    if src == ST.pending_verification and uid == ca.owner_id:
        raise ApiError(
            403,
            ErrorCode.VERIFIER_IS_OWNER,
            "You own this action; another person must verify it (CA-5).",
            "أنت المسؤول عن التنفيذ؛ يجب أن يتحقق منه شخص آخر.",
        )
    if not ok:
        raise forbidden_error()


def _evidence_count(db: Session, ca: CorrectiveAction) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(
                Attachment.owner_type == AttachmentOwner.corrective_action_evidence,
                Attachment.owner_id == ca.id,
            )
        )
        or 0
    )


def settle_source(db: Session, ca: CorrectiveAction) -> None:
    """When the last CA of a source is Closed/Cancelled: incident Actions Pending → Closed
    (AC25), observation Action Raised → Closed (§4.3)."""
    from app.services import incidents  # noqa: PLC0415

    if ca.source_id is None:
        return
    if ca.source_type == CaSourceType.incident:
        incidents.settle_after_ca(db, ca.source_id)
    elif ca.source_type == CaSourceType.observation:
        obs = db.get(Observation, ca.source_id)
        if obs is None or obs.status != ObservationStatus.action_raised:
            return
        live = db.scalar(
            select(func.count())
            .select_from(CorrectiveAction)
            .where(
                CorrectiveAction.source_type == CaSourceType.observation,
                CorrectiveAction.source_id == obs.id,
                CorrectiveAction.status.in_(LIVE),
            )
        )
        if not live:
            obs.status = ObservationStatus.closed
            obs.closed_at = now()
            obs.closed_date = ca.verified_date or ca.cancelled_date or ca.created_date
            obs.closure_comment = f"All corrective actions settled ({ca.ref})."
            audit.record(
                db,
                AuditAction.status_change,
                audit.SYSTEM,
                entity_type=EntityType.observation,
                entity_id=obs.id,
                project_id=obs.project_id,
                before={"status": ObservationStatus.action_raised},
                after={"status": ObservationStatus.closed},
            )


def transition(db: Session, p: Principal, ca_id: uuid.UUID, body: CaTransitionRequest) -> CaRead:
    ca = get_ca(db, p, ca_id)
    project = db.get(Project, ca.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    to = body.to_status
    _authorise(p, ca, to)
    src = ca.status
    day = project_today(project)
    details: dict[str, Any] = {"from": src.value, "to": to.value}
    if to == ST.in_progress and src == ST.open:
        pass
    elif to == ST.pending_verification:
        text = (body.evidence_text or ca.evidence_text or "").strip()
        if len(text) < 20 and _evidence_count(db, ca) == 0:
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_REQUIRED,
                "Add evidence: at least 20 characters of text or one file (CA-4).",
                "أضف دليل الإنجاز: نص لا يقل عن 20 حرفاً أو ملف واحد.",
            )
        if body.evidence_text:
            ca.evidence_text = body.evidence_text.strip()
        ca.completed_at = now()
        ca.completed_date = day
        notify.notify(
            db,
            [ca.verifier_id],
            NotificationKind.ca_pending_verification,
            f"{ca.ref} is ready for your verification",
            f"{ca.ref} جاهز للتحقق",
            entity_type=EntityType.corrective_action,
            entity_id=ca.id,
            project_id=ca.project_id,
        )
    elif src == ST.pending_verification and to == ST.closed:
        ca.verified_at = now()
        ca.verified_date = day
        ca.verification_comment = body.comment
    elif src == ST.pending_verification and to == ST.in_progress:
        ca.verification_comment = require_reason(body.comment, "reject the completion")
        ca.completed_at = None
        ca.completed_date = None
    elif to == ST.cancelled:
        ca.cancel_reason = require_reason(body.reason, "cancel the action")
        ca.cancelled_date = day
    elif src == ST.closed and to == ST.in_progress:
        details["reason"] = require_reason(body.reason, "reopen the action")
        ca.verified_at = None
        ca.verified_date = None
        ca.completed_at = None
        ca.completed_date = None
    ca.status = to
    ca.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(ca.project_id),
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=ca.project_id,
        before={"status": src},
        after={"status": to},
        details=details,
    )
    if to in (ST.closed, ST.cancelled):
        settle_source(db, ca)
    return to_read(db, p, ca)


def request_extension(
    db: Session, p: Principal, ca_id: uuid.UUID, body: CaExtensionCreate
) -> CaRead:
    ca = get_ca(db, p, ca_id)
    project = db.get(Project, ca.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    if p.user.id != ca.owner_id:
        raise forbidden_error("Only the owner may request an extension.")
    if ca.status not in OPEN:
        raise invalid_transition("Corrective action", ca.status, "extended")
    exts = list(db.scalars(select(CaExtension).where(CaExtension.ca_id == ca.id)))
    s = hse_settings.get(db, ca.project_id)
    if sum(1 for e in exts if e.status == ExtensionStatus.approved) >= s.ca_max_extensions:
        raise ApiError(
            409,
            ErrorCode.EXTENSION_LIMIT_REACHED,
            f"This action already has {s.ca_max_extensions} approved extensions (CA-3).",
            "تم بلوغ الحد الأقصى للتمديدات.",
        )
    if any(e.status == ExtensionStatus.requested for e in exts):
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "An extension request is already waiting for a decision.",
            "يوجد طلب تمديد بانتظار القرار.",
        )
    if body.new_due_date <= ca.due_date:
        raise validation_error("new_due_date", "The new due date must be after the current one.")
    ext = CaExtension(
        ca_id=ca.id,
        new_due_date=body.new_due_date,
        previous_due_date=ca.due_date,
        reason=body.reason,
        status=ExtensionStatus.requested,
        requested_by_user_id=p.user.id,
        requested_at=now(),
    )
    db.add(ext)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(ca.project_id),
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=ca.project_id,
        details={"extension_requested": body.new_due_date.isoformat(), "reason": body.reason},
    )
    return to_read(db, p, ca)


def decide_extension(
    db: Session, p: Principal, ca_id: uuid.UUID, ext_id: uuid.UUID, body: CaExtensionDecision
) -> CaRead:
    ca = get_ca(db, p, ca_id)
    project = db.get(Project, ca.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(ca.project_id, Capability.ca_approve_extension)
    if not _staff(p, ca) or p.user.id == ca.owner_id:
        raise forbidden_error("Extensions are decided by HSE staff other than the owner (CA-3).")
    ext = db.get(CaExtension, ext_id)
    if ext is None or ext.ca_id != ca.id:
        raise not_found("Extension")
    if ext.status != ExtensionStatus.requested:
        raise invalid_transition("Extension", ext.status, "decided")
    if body.approve:
        s = hse_settings.get(db, ca.project_id)
        approved = db.scalar(
            select(func.count())
            .select_from(CaExtension)
            .where(CaExtension.ca_id == ca.id, CaExtension.status == ExtensionStatus.approved)
        )
        if (approved or 0) >= s.ca_max_extensions:
            raise ApiError(
                409,
                ErrorCode.EXTENSION_LIMIT_REACHED,
                "The extension limit is reached (CA-3).",
                "تم بلوغ الحد الأقصى للتمديدات.",
            )
        ext.status = ExtensionStatus.approved
        before = ca.due_date
        ca.due_date = ext.new_due_date
        ca.alerts_sent = []
    else:
        ext.status = ExtensionStatus.rejected
        before = ca.due_date
    ext.decided_by_user_id = p.user.id
    ext.decided_at = now()
    ext.decision_comment = body.comment
    ca.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(ca.project_id),
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=ca.project_id,
        before={"due_date": before},
        after={"due_date": ca.due_date},
        details={"extension": str(ext.id), "approved": body.approve},
    )
    return to_read(db, p, ca)


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[CaStatus] | None = None,
    overdue: bool | None = None,
    overdue_bucket: OverdueBucket | None = None,
    verification_overdue: bool | None = None,
    priorities: list[CaPriority] | None = None,
    control_levels: list[ControlLevel] | None = None,
    source_type: CaSourceType | None = None,
    source_id: uuid.UUID | None = None,
    site_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    owner_is_me: bool = False,
    verifier_is_me: bool = False,
    due_from: date | None = None,
    due_to: date | None = None,
    as_of: date | None = None,
    q: str | None = None,
    sort: str = "due_date",
) -> CaPage:
    project = projects.get_visible(db, p, project_id)
    C = CorrectiveAction  # noqa: N806
    day = as_of or project_today(project)
    stmt = scoped_query(p, project)
    if statuses:
        stmt = stmt.where(C.status.in_(statuses))
    if overdue is not None:
        stmt = stmt.where(overdue_sql(day) if overdue else ~overdue_sql(day))
    if overdue_bucket is not None:
        lo, hi = next((lo, hi) for b, lo, hi in BUCKETS if b == overdue_bucket)
        stmt = stmt.where(
            overdue_sql(day),
            C.due_date <= day - timedelta(days=lo),
            C.due_date >= day - timedelta(days=min(hi, 100_000)),
        )
    if verification_overdue is not None:
        cond = verification_overdue_sql(day)
        stmt = stmt.where(cond if verification_overdue else ~cond)
    if priorities:
        stmt = stmt.where(C.priority.in_(priorities))
    if control_levels:
        stmt = stmt.where(C.control_level.in_(control_levels))
    if source_type:
        stmt = stmt.where(C.source_type == source_type)
    if source_id:
        stmt = stmt.where(C.source_id == source_id)
    if site_ids:
        stmt = stmt.where(C.site_id.in_(site_ids))
    if engagement_ids:
        engs: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                engs |= engagement_descendants(db, e)
        stmt = stmt.where(C.responsible_engagement_id.in_(engs))
    if owner_is_me:
        stmt = stmt.where(C.owner_id == p.user.id)
    if verifier_is_me:
        stmt = stmt.where(C.verifier_id == p.user.id)
    if due_from:
        stmt = stmt.where(C.due_date >= due_from)
    if due_to:
        stmt = stmt.where(C.due_date <= due_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(C.ref.ilike(like), C.title.ilike(like)))
    order: Any = {
        "due_date": C.due_date.asc(),
        "-due_date": C.due_date.desc(),
        "created_at": C.created_at.asc(),
        "-created_at": C.created_at.desc(),
        "priority": C.priority.asc(),
    }[sort]
    stmt = stmt.order_by(order, C.ref)
    items, total = paginate(db, stmt, page, page_size)
    return CaPage(
        items=[to_read(db, p, ca, day=day) for ca in items],
        total=total,
        page=page,
        page_size=page_size,
    )
