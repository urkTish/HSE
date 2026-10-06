"""HSE meetings (spec 1-dashboard §3.9; feeds K-39). Recorded by HSE staff (the plan-manage
capability 33, held by the HSE Officer and Manager); visible with the register scope (31)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import validation_error
from app.core.hse_enums import AttachmentOwner, MeetingType
from app.models import Attachment, HseMeeting, Project
from app.schemas.meetings import HseMeetingCreate, HseMeetingPage, HseMeetingRead, HseMeetingUpdate
from app.services import audit, projects
from app.services.common import ensure_open, paginate
from app.services.hse_common import Refs, check_engagement
from app.services.permissions import Principal, deny, forbidden_error

FIELDS = (
    "engagement_id",
    "meeting_type",
    "title",
    "planned_date",
    "held_date",
    "invited_count",
    "attended_count",
)


def _read(db: Session, m: HseMeeting) -> HseMeetingRead:
    refs = Refs(db).load(engs=[m.engagement_id])
    minutes = db.scalar(
        select(
            exists().where(
                Attachment.owner_type == AttachmentOwner.hse_meeting_minutes,
                Attachment.owner_id == m.id,
            )
        )
    )
    return HseMeetingRead(
        id=m.id,
        project_id=m.project_id,
        engagement=refs.eng(m.engagement_id),
        meeting_type=m.meeting_type,
        title=m.title,
        planned_date=m.planned_date,
        held_date=m.held_date,
        invited_count=m.invited_count,
        attended_count=m.attended_count,
        has_minutes=bool(minutes),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _get(db: Session, p: Principal, meeting_id: uuid.UUID) -> HseMeeting:
    m = db.get(HseMeeting, meeting_id)
    if m is None or p.grant(m.project_id, Capability.incident_view) is None:
        raise deny(
            db, p, EntityType.hse_meeting, meeting_id, m.project_id if m else None, "Meeting"
        )
    return m


def _check(m: HseMeeting) -> None:
    if m.attended_count is not None and m.attended_count > m.invited_count:
        raise validation_error("attended_count", "attended_count must be ≤ invited_count")
    if m.held_date is not None and m.attended_count is None:
        raise validation_error("attended_count", "attended_count is required once held")


def _snap(m: HseMeeting) -> dict[str, Any]:
    return {k: getattr(m, k) for k in FIELDS}


def read(db: Session, p: Principal, meeting_id: uuid.UUID) -> HseMeetingRead:
    return _read(db, _get(db, p, meeting_id))


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: HseMeetingCreate
) -> HseMeetingRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    p.require(project.id, Capability.inspection_plan_manage)
    if body.engagement_id:
        check_engagement(db, project, body.engagement_id)
    m = HseMeeting(project_id=project.id, **body.model_dump())
    db.add(m)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.hse_meeting,
        entity_id=m.id,
        project_id=project.id,
        after=_snap(m),
    )
    return _read(db, m)


def update(
    db: Session, p: Principal, meeting_id: uuid.UUID, body: HseMeetingUpdate
) -> HseMeetingRead:
    m = _get(db, p, meeting_id)
    project = db.get(Project, m.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(project.id, Capability.inspection_plan_manage)
    ch = body.changes()
    if ch.get("engagement_id"):
        check_engagement(db, project, ch["engagement_id"])
    before = _snap(m)
    for k, v in ch.items():
        setattr(m, k, v)
    _check(m)
    m.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snap(m))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.hse_meeting,
            entity_id=m.id,
            project_id=project.id,
            before=bf,
            after=af,
        )
    return _read(db, m)


def delete(db: Session, p: Principal, meeting_id: uuid.UUID) -> None:
    m = _get(db, p, meeting_id)
    project = db.get(Project, m.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(project.id, Capability.inspection_plan_manage)
    audit.record(
        db,
        AuditAction.archive,
        p.actor(project.id),
        entity_type=EntityType.hse_meeting,
        entity_id=m.id,
        project_id=project.id,
        before=_snap(m),
        details={"deleted": True},
    )
    db.delete(m)
    db.flush()


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    meeting_type: MeetingType | None,
    date_from: date | None,
    date_to: date | None,
) -> HseMeetingPage:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, Capability.incident_view) is None:
        raise forbidden_error()
    M = HseMeeting  # noqa: N806
    stmt = select(M).where(M.project_id == project.id)
    if meeting_type:
        stmt = stmt.where(M.meeting_type == meeting_type)
    if date_from:
        stmt = stmt.where(M.planned_date >= date_from)
    if date_to:
        stmt = stmt.where(M.planned_date <= date_to)
    items, total = paginate(db, stmt.order_by(M.planned_date.desc()), page, page_size)
    return HseMeetingPage(
        items=[_read(db, m) for m in items], total=total, page=page, page_size=page_size
    )
