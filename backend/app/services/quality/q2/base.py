"""Helpers shared by every Q2 service (spec 8-quality Part C): record scope with the
responsible-person scope N (Q-ROL-04), list conditions in SQL, transitions with audit, sign-offs
through the matrix (Q-RPM-03…08) and the attachment count used by evidence rules."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType, entity_type_value, step_def
from app.models import Attachment, Project, User
from app.models.quality import QSignoff
from app.services import audit
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import rpm, signoff
from app.services.quality import settings as qs

C = Capability
S = CapabilityScope
RT = QRecordType


def project_of(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    return project


def signed_by(db: Session, rt: QRecordType, rid: uuid.UUID, uid: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(QSignoff.id).where(
                QSignoff.record_type == rt.value,
                QSignoff.record_id == rid,
                QSignoff.signed_by_user_id == uid,
            )
        )
        is not None
    )


def can_view(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    caps: Iterable[Capability],
    site_id: uuid.UUID | None,
    eng_id: uuid.UUID | None,
    *,
    rt: QRecordType | None = None,
    rid: uuid.UUID | None = None,
    pending: Callable[[], list[tuple[str, rpm.Ctx]]] | None = None,
    own: Iterable[uuid.UUID | None] = (),
) -> bool:
    """238 (or a record capability) covering the record's site and contractor; scope N only for
    records where the user resolves for a pending step or has signed (Q-ROL-04)."""
    if not p.can_see_project(project_id):
        return False
    if p.user.id in {u for u in own if u}:
        return True
    n_grant = False
    for cap in (C.quality_view, *caps):
        g = p.grant(project_id, cap)
        if g is None:
            continue
        if g.scope == S.responsible:
            n_grant = True
            continue
        if qc.covers(g, site_id, eng_id):
            return True
    if not n_grant or rt is None or rid is None:
        return False
    if signed_by(db, rt, rid, p.user.id):
        return True
    project = project_of(db, project_id)
    for step, ctx in pending() if pending else []:
        if rpm.resolves(db, p, project, rt, step, ctx, record_id=rid, can_act=False):
            return True
    return False


def scope_cond(
    p: Principal,
    project_id: uuid.UUID,
    caps: Iterable[Capability],
    site_col: Any,
    eng_col: Any,
    n_ids: Callable[[], list[uuid.UUID]] | None = None,
    id_col: Any = None,
) -> Any:
    """SQL condition of the records the user may list (Q-ROL-02 engagement narrowing, Phase 0
    rule 11 sites; scope N through `n_ids`)."""
    if p.is_manager:
        return true()
    ors: list[Any] = []
    has_n = False
    for cap in (C.quality_view, *caps):
        g = p.grant(project_id, cap)
        if g is None:
            continue
        if g.scope == S.responsible:
            has_n = True
            continue
        conds: list[Any] = []
        if g.site_ids is not None and site_col is not None:
            conds.append(site_col.in_(list(g.site_ids)) if g.site_ids else false())
        if g.engagement_ids is not None and eng_col is not None:
            engs = list(g.engagement_ids)
            conds.append(eng_col.in_(engs) if engs else false())
        if not conds:
            return true()
        ors.append(and_(*conds))
    if has_n and n_ids is not None and id_col is not None:
        ids = n_ids()
        if ids:
            ors.append(id_col.in_(ids))
    return or_(*ors) if ors else false()


def require_view(
    db: Session,
    p: Principal,
    ok: bool,
    et: EntityType,
    rid: uuid.UUID,
    pid: uuid.UUID | None,
    what: str,
) -> None:
    if not ok:
        raise deny(db, p, et, rid, pid, what)


def require_list(p: Principal, project_id: uuid.UUID, *caps: Capability) -> None:
    if p.is_manager:
        return
    if not any(p.grant(project_id, c) is not None for c in (C.quality_view, *caps)):
        raise forbidden_error()


def et(rt: QRecordType) -> EntityType:
    return EntityType(entity_type_value(rt))


def audit_create(db: Session, p: Principal, rt: QRecordType, row: Any, **after: Any) -> None:
    audit.record(
        db,
        AuditAction.create,
        p.actor(row.project_id),
        entity_type=et(rt),
        entity_id=row.id,
        project_id=row.project_id,
        after={k: str(v) for k, v in after.items()},
    )


def audit_update(
    db: Session,
    p: Principal,
    rt: QRecordType,
    row: Any,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    b, a = audit.diff(before, after)
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(row.project_id),
            entity_type=et(rt),
            entity_id=row.id,
            project_id=row.project_id,
            before=b,
            after=a,
        )


def set_status(
    db: Session, p: Principal | None, rt: QRecordType, row: Any, to: Any, **details: Any
) -> None:
    old = row.status
    row.status = to
    if p is not None and hasattr(row, "updated_by_user_id"):
        row.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(row.project_id) if p else audit.SYSTEM,
        entity_type=et(rt),
        entity_id=row.id,
        project_id=row.project_id,
        details={
            "from": getattr(old, "value", str(old)),
            "to": getattr(to, "value", str(to)),
            **{k: str(v) for k, v in details.items() if v is not None},
        },
    )


def invalid(what: str, status: Any, action: str) -> Any:
    st = getattr(status, "value", str(status))
    return qc.err(
        409,
        ErrorCode.INVALID_TRANSITION,
        f"{what} in status {st} cannot be {action}.",
        "لا يمكن تنفيذ هذا الإجراء في الحالة الحالية للسجل.",
        record_status=st,
    )


def sign(
    db: Session,
    p: Principal,
    project: Project,
    rt: QRecordType,
    rid: uuid.UUID,
    step: str,
    decision: str,
    comment: str | None,
    ctx: rpm.Ctx,
    *,
    paper: dict[str, Any] | None = None,
    qualifier: str | None = None,
) -> QSignoff:
    """One responsible-person sign-off (in-app after `check_signer`, or paper, Q-RPM-08)."""
    qc.writable(project, p)
    if paper:
        sd = step_def(rt, step)
        if sd is not None and p.grant(project.id, sd.capability) is not None:
            # the paper recorder still may not be the requester (Q-RPM-06)
            rule = rpm.effective_rule(db, project.id, rt, step, qualifier=qualifier, record_id=rid)
            if rule is not None and not rule.self_approval_allowed and p.user.id in ctx.requesters:
                raise qc.err(
                    422,
                    ErrorCode.SOD_CONFLICT,
                    "You created or recorded this record; another person must record the sign-off.",
                    "أنت من أنشأ السجل؛ يجب أن يسجّل شخص آخر التوقيع.",
                )
        return signoff.sign_paper(
            db, p, project, rt, rid, step, decision, comment, paper, ctx, qualifier=qualifier
        )
    # Q-RPM-06 first: the user who entered the result being decided never signs it, whether or
    # not they would resolve (AC-Q2-08)
    first = rpm.effective_rule(db, project.id, rt, step, qualifier=qualifier, record_id=rid)
    if first is not None and not first.self_approval_allowed and p.user.id in ctx.requesters:
        raise qc.err(
            422,
            ErrorCode.SOD_CONFLICT,
            "You created, requested or recorded this record, so another responsible person "
            "must sign this step (Q-RPM-06).",
            "أنت من أنشأ السجل أو طلبه أو سجّل نتيجته؛ يجب أن يوقّع شخص مسؤول آخر هذه الخطوة.",
        )
    rule, capacity = rpm.check_signer(
        db, p, project, rt, step, ctx, qualifier=qualifier, record_id=rid
    )
    return signoff.sign(db, p, project, rt, rid, step, decision, comment, rule, capacity)


def resolvers(
    db: Session, project: Project, rt: QRecordType, step: str, ctx: rpm.Ctx, rid: uuid.UUID | None
) -> list[uuid.UUID]:
    res = rpm.resolve(db, project, rt, step, ctx, record_id=rid)
    return [u for u in res.users if u not in ctx.requesters]


def attachment_count(
    db: Session, owner: AttachmentOwner, owner_id: uuid.UUID, after: datetime | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.owner_type == owner, Attachment.owner_id == owner_id)
    )
    stmt = stmt.where(Attachment.superseded_at.is_(None))
    if after is not None:
        stmt = stmt.where(Attachment.created_at > after)
    return int(db.scalar(stmt) or 0)


def user_ref(db: Session, uid: uuid.UUID | None, hide: bool = False) -> dict[str, Any] | None:
    if uid is None or hide:
        return None
    u = db.get(User, uid)
    if u is None:
        return None
    return {"id": u.id, "full_name_en": u.full_name_en, "full_name_ar": u.full_name_ar}


def setting(db: Session, project_id: uuid.UUID, key: str) -> Any:
    return qs.value(db, project_id, key)


def day_start(project: Project, d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=ZoneInfo(qc.tz(project)))


def day_end(project: Project, d: date) -> datetime:
    return day_start(project, d) + timedelta(days=1)


def local_day(project: Project, at: datetime) -> date:
    return at.astimezone(ZoneInfo(qc.tz(project))).date()


def add_months(d: date, n: int) -> date:
    """Calendar months with a month-end clamp (6d §6.4)."""
    from app.kpi.periods import add_months as am  # noqa: PLC0415

    return am(d, n)


def project_member(db: Session, project: Project, uid: uuid.UUID) -> bool:
    """An active role on the project (or the organisation-wide HSE Manager)."""
    day = qc.project_day(project)
    return any(a.user_id == uid for a in qc._assignments(db, project.id, day))


def read_only(p: Principal, project_id: uuid.UUID) -> bool:
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    return read_only_viewer(p, project_id)


def quality_engineers(db: Session, project: Project) -> list[uuid.UUID]:
    from app.core.enums import Role  # noqa: PLC0415

    return [a.user_id for a in qc.role_holders(db, project, Role.quality_engineer)]


def main_engagement(db: Session, project_id: uuid.UUID) -> uuid.UUID | None:
    """The project's first tier-1 engagement: the NCR's responsible party when the source has none
    (an instrument owned by the project, D-343); the NCR owner may change it."""
    from app.models import ProjectEngagement  # noqa: PLC0415

    return db.scalar(
        select(ProjectEngagement.id)
        .where(ProjectEngagement.project_id == project_id)
        .order_by(ProjectEngagement.tier, ProjectEngagement.id)
        .limit(1)
    )


def main_site(db: Session, project_id: uuid.UUID) -> uuid.UUID | None:
    """The project's first site, for an NCR whose source names none (D-343)."""
    from app.models import Site  # noqa: PLC0415

    return db.scalar(
        select(Site.id).where(Site.project_id == project_id).order_by(Site.code).limit(1)
    )


def auto_ncr(
    db: Session,
    project: Project,
    source_type: Any,
    source_id: uuid.UUID,
    *,
    raised_by: uuid.UUID | None,
    owner_id: uuid.UUID,
    classification: Any,
    category: Any,
    title: str | None = None,
    evidence: tuple[tuple[AttachmentOwner, uuid.UUID], ...] = (),
) -> Any:
    """— → Open by the System like `ncr.core.auto_raise`, with the source's files (lab report,
    certificates, NDT report) copied as NCR evidence first, so a critical NCR meets Q-NCR-03."""
    from app.core.quality.common import (  # noqa: PLC0415
        NCR_SOURCE_DEFS,
        QDetectionStage,
        QLinkKind,
        QNcrStatus,
    )
    from app.models.quality import QNcr  # noqa: PLC0415
    from app.services import attachments  # noqa: PLC0415
    from app.services.quality import ensure_registered, links  # noqa: PLC0415
    from app.services.quality import registry as reg  # noqa: PLC0415
    from app.services.quality.ncr import core  # noqa: PLC0415

    ensure_registered()
    info = reg.NCR_SOURCES[source_type].resolve(db, project, source_id)
    n = QNcr(
        id=uuid.uuid4(),
        project_id=project.id,
        profile=qc.require_profile(db, project),
        source_type=source_type,
        source_id=source_id,
        source_ref=info.ref,
        item_key=info.item_key,
        site_id=info.site_id or main_site(db, project.id),
        zone_id=info.zone_id,
        system_id=info.system_id,
        location_ref=info.location_ref,
        title=(title or info.title or info.ref or source_type.value)[:150],
        requirement_en=info.requirement_en or "See the source record.",
        requirement_ar=info.requirement_ar,
        finding_en=info.finding_en or info.title or "See the source record.",
        finding_ar=info.finding_ar,
        category=category,
        detection_stage=info.detection_stage or QDetectionStage.in_process,
        classification=classification or info.proposed_class or NCR_SOURCE_DEFS[source_type][1],
        responsible_engagement_id=info.engagement_id or main_engagement(db, project.id),
        supplier_id=info.supplier_id,
        customer_id=info.customer_id,
        quantity=info.quantity,
        unit=info.unit,
        lot_refs=list(info.lot_refs),
        raised_by_user_id=raised_by,
        owner_id=owner_id,
        status=QNcrStatus.draft,
        alerts_sent=[],
        created_by_user_id=raised_by,
    )
    db.add(n)
    db.flush()
    for owner, oid in evidence:
        for a in list(
            db.scalars(
                select(Attachment).where(
                    Attachment.owner_type == owner,
                    Attachment.owner_id == oid,
                    Attachment.superseded_at.is_(None),
                )
            )
        ):
            attachments.store(
                db,
                AttachmentOwner.q_ncr_evidence,
                n.id,
                project.id,
                a.file_name,
                attachments.read_content(a),
                a.content_type,
                raised_by or a.uploaded_by_user_id,
                shrink=False,
                generated=True,
            )
    if info.record_type is not None:
        links.add(
            db,
            project.id,
            RT.ncr,
            n.id,
            info.record_type,
            source_id,
            QLinkKind.raised_from,
            raised_by,
        )
    core._do_open(db, None, project, n)
    return n
