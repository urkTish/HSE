"""Stop-work orders (spec 6d-field-assurance §3.9, §4.3, FND-7…FND-9): register, release (196) once
the linked CA is being worked, void (201), and the Phase 3 resume guard (3-ptw v1.5 SH-3)."""

from __future__ import annotations

import uuid

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import StopOrderStatus
from app.core.hse_enums import AttachmentOwner, CaStatus
from app.core.ptw_enums import StatusReason
from app.models import ChecklistResponse, Inspection, Permit, StopWorkOrder
from app.schemas.field import (
    FieldVoid,
    PermitBrief,
    StopWorkPage,
    StopWorkRead,
    StopWorkRelease,
)
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.field import common as fc
from app.services.hse_common import Refs
from app.services.permissions import Principal

C = Capability
SO = StopOrderStatus
RELEASE_CA = (CaStatus.in_progress, CaStatus.pending_verification, CaStatus.closed)


def order_read(db: Session, p: Principal | None, o: StopWorkOrder) -> StopWorkRead:
    from app.models import Attachment  # noqa: PLC0415

    refs = Refs(db).load(
        sites=[o.site_id], zones=[o.zone_id], engs=[o.engagement_id], users=[o.released_by_user_id]
    )
    r = db.get(ChecklistResponse, o.response_id)
    ins = db.get(Inspection, r.inspection_id) if r and r.inspection_id else None
    ca_ref, ca_status = fc.ca_info(db, o.ca_id)
    viewer = p is not None and fc.is_viewer(p, o.project_id)
    photos = (
        []
        if viewer
        else list(
            db.scalars(
                select(Attachment.id)
                .where(
                    Attachment.owner_type == AttachmentOwner.stop_work_photo,
                    Attachment.owner_id == o.id,
                )
                .order_by(Attachment.created_at)
            )
        )
    )
    permits = [db.get(Permit, x) for x in o.permit_ids or []]
    return StopWorkRead(
        id=o.id,
        order_no=o.order_no,
        response_id=o.response_id,
        inspection_ref=ins.ref if ins else None,
        item_code=o.item_code,
        site=refs.site(o.site_id),
        zone=refs.zone(o.zone_id),
        engagement=refs.eng(o.engagement_id),
        activity_en=o.activity_en,
        activity_ar=o.activity_ar,
        instructed_role=o.instructed_role,
        instructed_at=o.instructed_at,
        raised_at=o.raised_at,
        received_at=o.received_at,
        recorded_offline=o.recorded_offline,
        permits=[PermitBrief(id=pm.id, permit_no=pm.permit_no) for pm in permits if pm],
        ca_id=o.ca_id,
        ca_ref=ca_ref,
        ca_status=ca_status,
        released_by=refs.user(o.released_by_user_id),
        released_at=o.released_at,
        release_note=o.release_note,
        release_photo_ids=photos,
        status=o.status,
        status_reason=o.status_reason,
    )


def _get(db: Session, p: Principal, order_id: uuid.UUID) -> StopWorkOrder:
    o = db.get(StopWorkOrder, order_id)
    if o is None or not p.can_see_project(o.project_id):
        raise not_found("Stop-work order")
    g = p.grant(o.project_id, C.field_view)
    if not fc.in_scope(g, o.site_id, o.engagement_id):
        raise not_found("Stop-work order")
    return o


def list_orders(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[StopOrderStatus] | None,
    site_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> StopWorkPage:
    fc.project(db, p, project_id)
    g = fc.view_grant(p, project_id)
    SW = StopWorkOrder  # noqa: N806
    stmt = select(SW).where(SW.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(SW.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        stmt = stmt.where(SW.engagement_id.in_(engs) if engs else false())
    if statuses:
        stmt = stmt.where(SW.status.in_(statuses))
    if site_id:
        stmt = stmt.where(SW.site_id == site_id)
    items, total = paginate(db, stmt.order_by(SW.raised_at.desc()), page, page_size)
    return StopWorkPage(
        items=[order_read(db, p, o) for o in items], total=total, page=page, page_size=page_size
    )


def read_order(db: Session, p: Principal, order_id: uuid.UUID) -> StopWorkRead:
    return order_read(db, p, _get(db, p, order_id))


def release_order(
    db: Session, p: Principal, order_id: uuid.UUID, body: StopWorkRelease
) -> StopWorkRead:
    """FND-8 (196): the linked CA In Progress, Pending Verification or Closed; note ≥ 20; ≥ 1
    photo. Named permits stay suspended until the issuer resumes (SH-3)."""
    o = _get(db, p, order_id)
    proj = fc.project(db, p, o.project_id)
    ensure_open(proj)
    g = p.require(o.project_id, C.stop_work_release)
    if not g.covers_site(o.site_id):
        from app.services.permissions import forbidden_error  # noqa: PLC0415

        raise forbidden_error()
    if o.status != SO.active:
        raise invalid_transition("Stop-work order", o.status, SO.released)
    _ref, ca_status = fc.ca_info(db, o.ca_id)
    if ca_status not in RELEASE_CA:
        raise fc.err(
            422,
            ErrorCode.STOP_RELEASE_CA_REQUIRED,
            "Release only when the corrective action is In Progress or later (FND-8).",
            "يُرفع الإيقاف فقط بعد بدء تنفيذ الإجراء التصحيحي.",
            field="ca",
        )
    note = fc.reason(body.release_note, 20, "release_note")
    if not body.photos:
        raise validation_error("photos", "Attach at least one photo of the corrected condition.")
    before = {"status": o.status.value}
    fc.store_photos(db, AttachmentOwner.stop_work_photo, o.id, o.project_id, body.photos,
                    p.user.id, "photos")  # fmt: skip
    o.status = SO.released
    o.released_by_user_id = p.user.id
    o.released_at = now()
    o.release_note = note
    o.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.stop_work_order, o, o.project_id,
              before=before)  # fmt: skip
    return order_read(db, p, o)


def void_order(db: Session, p: Principal, order_id: uuid.UUID, body: FieldVoid) -> StopWorkRead:
    o = _get(db, p, order_id)
    proj = fc.project(db, p, o.project_id)
    ensure_open(proj)
    p.require(o.project_id, C.field_void)
    why = fc.reason(body.reason, 20)
    if o.status != SO.active:
        raise invalid_transition("Stop-work order", o.status, SO.voided)
    before = {"status": o.status.value}
    o.status = SO.voided
    o.status_reason = why
    o.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.stop_work_order, o, o.project_id,
              before=before, details={"reason": why})  # fmt: skip
    return order_read(db, p, o)


def resume_guard(db: Session, permit: Permit) -> None:
    """3-ptw v1.5 SH-3: a `stop_work` suspension cannot be resumed while the order is Active."""
    if permit.status_reason != StatusReason.stop_work:
        return
    from app.services.ptw import evaluation  # noqa: PLC0415

    sp = evaluation.open_suspension(db, permit)
    ref = sp.auto_source_ref if sp is not None else None
    if not ref:
        return
    o = db.scalar(select(StopWorkOrder).where(StopWorkOrder.order_no == ref))
    if o is not None and o.status == SO.active:
        raise fc.err(
            422,
            ErrorCode.STOP_WORK_ACTIVE,
            f"Stop-work order {o.order_no} is still Active: release it first (FND-9).",
            f"أمر إيقاف العمل {o.order_no} ما زال سارياً.",
        )
