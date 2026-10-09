"""Spills (spec 6e-environmental §3.13, §4.6, SPL-1…SPL-7, AIR-5, ASP-3 (b)): reportable rule,
Phase 1 incident link (SPL-3), 6c spill kits marked used (SPL-5), cleanup waste on close (SPL-6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import AssetType
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.env_enums import (
    ConsignmentStatus,
    SpillAction,
    SpillStatus,
    SpillSurface,
    StorageAreaType,
    WasteClass,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import (
    AttachmentOwner,
    EnvCategory,
    EnvReached,
    IncidentStatus,
    IncidentType,
)
from app.models import (
    EmergencyAsset,
    Incident,
    Spill,
    WasteConsignment,
    WasteStorageArea,
    Zone,
)
from app.schemas.env import SpillCreate, SpillPage, SpillRead, SpillTransition
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal

C = Capability
ET = EntityType
NK = NotificationKind
SS = SpillStatus
D = Decimal


def reportable(
    db: Session, project_id: uuid.UUID, qty: Decimal, reached: EnvReached, contained: bool,
    zone: Zone | None,
) -> bool:  # fmt: skip
    """SPL-2 / AIR-5."""
    c = ec.cfg(db, project_id)
    return (
        D(qty) >= c.dec("spill_reportable_l")
        or reached in (EnvReached.drain, EnvReached.water_body)
        or not contained
        or (ec.is_airside(zone) and bool(c["airside_spill_always_reportable"]))
    )


def spill_read(db: Session, p: Principal | None, s: Spill) -> SpillRead:
    hide = p is not None and ec.is_viewer(p, s.project_id)
    z = db.get(Zone, s.zone_id) if s.zone_id else None
    inc = db.get(Incident, s.incident_id) if s.incident_id else None
    return SpillRead(
        id=s.id, spill_no=s.spill_no, client_uuid=s.client_uuid, project_id=s.project_id,
        occurred_at=s.occurred_at, site_id=s.site_id, zone_id=s.zone_id,
        zone_code=z.code if z else None, responsible_engagement_id=s.responsible_engagement_id,
        responsible_code=ec.eng_code(db, s.responsible_engagement_id), substance=s.substance,
        source=s.source, quantity_l=str(ec.q1(s.quantity_l)), surface=s.surface,
        contained=s.contained, reached=s.reached,
        spill_kit_asset_ids=list(s.spill_kit_asset_ids or []), reportable=s.reportable,
        incident_id=s.incident_id, incident_ref=inc.ref if inc else None,
        cleanup_completed_at=s.cleanup_completed_at,
        cleanup_consignment_ids=list(s.cleanup_consignment_ids or []),
        cleanup_storage_area_id=s.cleanup_storage_area_id,
        absorbed_and_binned=s.absorbed_and_binned,
        photo_ids=None if hide else list(s.photo_ids or []), status=s.status,
        void_reason=s.void_reason,
    )  # fmt: skip


def _spill(db: Session, p: Principal, sid: uuid.UUID) -> Spill:
    s = db.get(Spill, sid)
    if s is None or not p.can_see_project(s.project_id):
        raise not_found("Spill")
    g = ec.need(p, s.project_id, C.env_view, write=False)
    if not ec.scope_ok(g, s.site_id, s.responsible_engagement_id):
        raise not_found("Spill")
    return s


def list_spills(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: list[SpillStatus] | None,
    reportable_: bool | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    size: int,
) -> SpillPage:
    g = ec.view_grant(db, p, project_id)
    q = select(Spill).where(Spill.project_id == project_id)
    if status:
        q = q.where(Spill.status.in_(status))
    if reportable_ is not None:
        q = q.where(Spill.reportable.is_(reportable_))
    if date_from:
        q = q.where(Spill.occurred_date >= date_from)
    if date_to:
        q = q.where(Spill.occurred_date <= date_to)
    rows = [
        s
        for s in db.scalars(q.order_by(Spill.occurred_at.desc()))
        if ec.scope_ok(g, s.site_id, s.responsible_engagement_id)
    ]
    return ec.paged(SpillPage, rows, page, size, lambda s: spill_read(db, p, s))


def _kits(db: Session, project_id: uuid.UUID, body: SpillCreate) -> list[EmergencyAsset]:
    from app.services.emergency import assets  # noqa: PLC0415

    out: list[EmergencyAsset] = []
    for i, aid in enumerate(body.spill_kit_asset_ids):
        a = db.get(EmergencyAsset, aid)
        if a is None or a.project_id != project_id or a.asset_type != AssetType.spill_kit:
            raise validation_error(f"spill_kit_asset_ids[{i}]", "Pick a spill kit of the project.")
        out.append(a)
    for i, pl in enumerate(body.spill_kit_payloads):
        try:
            a = assets._by_sticker(db, project_id, pl)
        except ApiError as e:
            raise validation_error(f"spill_kit_payloads[{i}]", "Scan a spill-kit sticker.") from e
        if a.asset_type != AssetType.spill_kit:
            raise validation_error(f"spill_kit_payloads[{i}]", "This sticker is not a spill kit.")
        out.append(a)
    return list({a.id: a for a in out}.values())


def _link_incident(db: Session, project_id: uuid.UUID, iid: uuid.UUID, body: SpillCreate) -> None:
    """SPL-3: an existing environmental incident of the project, same site, within ± 24 h."""
    inc = db.get(Incident, iid)
    ok = (
        inc is not None
        and inc.project_id == project_id
        and inc.status != IncidentStatus.voided
        and IncidentType.environmental.value in (inc.incident_types or [])
        and inc.site_id == body.site_id
        and abs(inc.occurred_at - body.occurred_at) <= timedelta(hours=24)
    )
    if not ok:
        raise ec.code_err(
            ErrorCode.INCIDENT_NOT_ENVIRONMENTAL,
            "Link an environmental incident on the same site within 24 hours.",
            "اربط حادثة بيئية في نفس الموقع خلال 24 ساعة.", "incident_id",
        )  # fmt: skip


def _new_incident(
    db: Session, p: Principal, project_id: uuid.UUID, body: SpillCreate
) -> Incident:
    """SPL-3: a Phase 1 incident, Reported, with spill facts only (P6e-4)."""
    from app.services import incidents  # noqa: PLC0415

    f = body.incident_fields
    assert f is not None  # noqa: S101
    pr = ec.project(db, None, project_id)
    d = ec.local_day(body.occurred_at)
    seq = ec.next_seq(db, Incident, project_id, d.year)
    label = rf.SS_LABELS[body.substance][0]
    inc = Incident(
        id=uuid.uuid4(), project_id=project_id, ref=ec.ref("INC", pr.code, d.year, seq, 4),
        year=d.year, seq=seq, site_id=body.site_id, zone_id=body.zone_id,
        responsible_engagement_id=body.responsible_engagement_id, occurred_at=body.occurred_at,
        occurred_date=d, reported_at=now(), reported_by_user_id=p.user.id, shift=f.shift,
        incident_types=[IncidentType.environmental.value],
        primary_type=IncidentType.environmental,
        title=f"Spill: {label} {ec.q1(body.quantity_l)} L"[:150], description=f.description,
        immediate_actions=f.immediate_actions, activity=f.activity, work_related=True,
        actual_severity=f.actual_severity, potential_severity=f.potential_severity,
        env_category=EnvCategory.spill, env_substance=body.substance.value,
        env_quantity_l=body.quantity_l, env_contained=body.contained, env_reached=body.reached,
        status=IncidentStatus.reported, created_by_user_id=p.user.id, airside_flags=[],
        alerts_sent=[],
    )  # fmt: skip
    db.add(inc)
    db.flush()
    from app.services import audit  # noqa: PLC0415

    audit.record(
        db, AuditAction.create, p.actor(project_id), entity_type=ET.incident, entity_id=inc.id,
        project_id=project_id, after=incidents.snapshot(inc),
    )  # fmt: skip
    incidents._report_alerts(db, incidents.bundle(db, inc))
    return inc


def create_spill(db: Session, p: Principal, project_id: uuid.UUID, body: SpillCreate) -> SpillRead:
    pr = ec.project(db, p, project_id)
    old = db.scalar(
        select(Spill).where(Spill.project_id == project_id, Spill.client_uuid == body.client_uuid)
    )
    if old is not None:
        return spill_read(db, p, old)  # SPL-1 idempotent
    ec.site_of(db, project_id, body.site_id)
    zone = ec.zone_of(db, body.site_id, body.zone_id)
    ec.eng_of_project(db, project_id, body.responsible_engagement_id)
    ec.require(p, project_id, C.spill_record, body.site_id, body.responsible_engagement_id)
    t = now()
    if body.occurred_at > t + timedelta(minutes=2) or body.occurred_at < t - timedelta(hours=72):
        raise validation_error("occurred_at", "The spill time must be within the last 72 hours.")
    rep = reportable(db, project_id, body.quantity_l, body.reached, body.contained, zone)
    kits = _kits(db, project_id, body)
    inc_id: uuid.UUID | None = None
    if body.incident_id is not None:
        _link_incident(db, project_id, body.incident_id, body)
        inc_id = body.incident_id
    elif rep:
        if body.incident_fields is None:
            raise ec.code_err(
                ErrorCode.INCIDENT_FIELDS_REQUIRED,
                "A reportable spill needs the incident fields (severity, activity, shift, "
                "description, immediate actions) or a linked environmental incident.",
                "الانسكاب واجب الإبلاغ يتطلب بيانات الحادثة أو ربط حادثة بيئية.",
                "incident_fields",
            )
        inc_id = _new_incident(db, p, project_id, body).id
    d = ec.local_day(body.occurred_at)
    seq = ec.next_seq(db, Spill, project_id, d.year)
    s = Spill(
        id=uuid.uuid4(), spill_no=ec.ref("SPL", pr.code, d.year, seq, 4), year=d.year, seq=seq,
        client_uuid=body.client_uuid, project_id=project_id, occurred_at=body.occurred_at,
        occurred_date=d, site_id=body.site_id, zone_id=body.zone_id,
        responsible_engagement_id=body.responsible_engagement_id, substance=body.substance,
        source=body.source, quantity_l=body.quantity_l, surface=body.surface,
        contained=body.contained, reached=body.reached,
        spill_kit_asset_ids=[a.id for a in kits], reportable=rep, incident_id=inc_id,
        recorded_by_user_id=p.user.id, status=SS.reported, created_by_user_id=p.user.id,
        photo_ids=[], cleanup_consignment_ids=[],
    )  # fmt: skip
    db.add(s)
    for a in kits:
        a.used_at = body.occurred_at  # SPL-5 / 6c v1.2 USED_REPLENISH
    db.flush()
    if body.photos:
        s.photo_ids = ec.store_photos(
            db, AttachmentOwner.env_photo, s.id, project_id, body.photos, p.user.id, "photos"
        )
    if rep:
        _alert(db, s)
        from app.services.env import register  # noqa: PLC0415

        register.flag_aspects(
            db, project_id, s.site_id, {"fuel_spill_risk", "hazardous_material_storage"},
            s.spill_no,
        )  # fmt: skip
    db.flush()
    ec.record(db, p, AuditAction.create, ET.spill, s, project_id)
    return spill_read(db, p, s)


def _alert(db: Session, s: Spill) -> None:
    pid = s.project_id
    users = (
        ec.officers(db, pid)
        | ec.managers(db)
        | ec.site_engineers(db, pid, s.site_id)
        | ec.reps(db, pid, s.responsible_engagement_id)
    )
    if ec.once(db, f"env:spill:{s.id}"):
        ec.send(
            db, users, NK.env_spill_reportable,
            f"Reportable spill {s.spill_no}: {rf.SS_LABELS[s.substance][0]} "
            f"{ec.q1(s.quantity_l)} L.",
            f"انسكاب واجب الإبلاغ {s.spill_no}: {rf.SS_LABELS[s.substance][1]} "
            f"{ec.q1(s.quantity_l)} لتر.",
            pid, ET.spill, s.id, email=True,
        )  # fmt: skip


def read_spill(db: Session, p: Principal, sid: uuid.UUID) -> SpillRead:
    return spill_read(db, p, _spill(db, p, sid))


def _cleanup_tracked(db: Session, s: Spill, body: SpillTransition) -> bool:
    """SPL-6."""
    ids = body.cleanup_consignment_ids or list(s.cleanup_consignment_ids or [])
    for cid in ids:
        c = db.get(WasteConsignment, cid)
        if c is None or c.project_id != s.project_id:
            raise validation_error("cleanup_consignment_ids", "Unknown consignment.")
        if c.status in (ConsignmentStatus.voided, ConsignmentStatus.rejected):
            continue
        if c.stream_code in rf.CLEANUP_STREAMS or rf.stream_class(c.stream_code) == (
            WasteClass.hazardous
        ):
            s.cleanup_consignment_ids = list(ids)
            return True
    aid = body.cleanup_storage_area_id or s.cleanup_storage_area_id
    if aid is not None:
        a = db.get(WasteStorageArea, aid)
        if a is None or a.project_id != s.project_id:
            raise validation_error("cleanup_storage_area_id", "Unknown storage area.")
        if a.type == StorageAreaType.hazardous_store and a.status.value == "active":
            s.cleanup_storage_area_id = aid
            return True
    if (
        body.absorbed_and_binned
        and D(s.quantity_l) < 1
        and s.surface == SpillSurface.paved
        and not s.reportable
    ):
        s.absorbed_and_binned = True
        return True
    return False


def transition_spill(
    db: Session, p: Principal, sid: uuid.UUID, body: SpillTransition
) -> SpillRead:
    s = _spill(db, p, sid)
    pid = s.project_id
    if s.status in (SS.closed, SS.voided):
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, f"The spill is {s.status.value}.",
                       "لا يمكن تغيير حالة الانسكاب.")  # fmt: skip
    if body.action == SpillAction.void:
        p.require(pid, C.env_void)
        s.void_reason = ec.reason(body.reason, 20)
        s.status = SS.voided
    elif body.action == SpillAction.clean_up:
        ec.require(p, pid, C.spill_record, s.site_id, s.responsible_engagement_id)
        if s.status != SS.reported:
            raise ApiError(409, ErrorCode.INVALID_TRANSITION, "Already cleaned up.",
                           "تم التنظيف مسبقاً.")  # fmt: skip
        s.cleanup_completed_at = _cleanup_at(body.cleanup_completed_at, s.occurred_at)
        _cleanup_tracked(db, s, body)
        s.status = SS.cleaned_up
    else:
        p.require(pid, C.env_review)
        if body.cleanup_completed_at is not None:
            s.cleanup_completed_at = _cleanup_at(body.cleanup_completed_at, s.occurred_at)
        if s.cleanup_completed_at is None or not _cleanup_tracked(db, s, body):
            raise ec.code_err(
                ErrorCode.CLEANUP_WASTE_UNTRACKED,
                "Give the cleanup time and the cleanup waste (a hazardous consignment or an active "
                "hazardous store).",
                "حدد وقت انتهاء التنظيف ووجهة نفايات التنظيف.", "cleanup_storage_area_id",
            )  # fmt: skip
        s.status = SS.closed
        s.closed_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.spill, s, pid)
    return spill_read(db, p, s)


def _cleanup_at(at: datetime | None, occurred: datetime) -> datetime:
    if at is None:
        raise validation_error("cleanup_completed_at", "Give the cleanup completion time.")
    if at < occurred or at > now() + timedelta(minutes=2):
        raise validation_error("cleanup_completed_at", "Cleanup ends after the spill, not later "
                               "than now.")  # fmt: skip
    return at
