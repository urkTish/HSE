"""NOTAM works clearances and obstacle/crane clearances (spec 2-access-permits §3.14, §3.15,
§4.6, §4.7, §5.7 NT-1…NT-7, OB-1…OB-9, §6.4 heights)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    ClearanceReason,
    NotamStatus,
    NotamType,
    ObstacleCondition,
    ObstacleDecision,
    ObstacleEquipmentType,
    ObstacleStatus,
    WapStatus,
    WorksImpact,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role, ZoneType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import NotamRequest, ObstacleClearance, Project, Vehicle, Wap, Zone
from app.schemas.airside_works import (
    HeightFigures,
    NotamReplaceRequest,
    NotamRequestCreate,
    NotamRequestPage,
    NotamRequestRead,
    NotamRequestUpdate,
    NotamTransitionRequest,
    ObstacleCreate,
    ObstacleDecisionRequest,
    ObstacleFields,
    ObstaclePage,
    ObstaclePreviewRequest,
    ObstacleRead,
    ObstacleTransitionRequest,
    ObstacleUpdate,
)
from app.schemas.hse_common import ApiWarning
from app.services import attachments, audit, notify, projects
from app.services.access import common
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq
from app.services.permissions import Principal, forbidden_error

C = Capability
NS = NotamStatus
OS = ObstacleStatus
APPROVED = (OS.approved, OS.approved_with_conditions)
OPERATOR_TYPES = {
    ObstacleEquipmentType.mobile_crane,
    ObstacleEquipmentType.tower_crane,
    ObstacleEquipmentType.crawler_crane,
    ObstacleEquipmentType.piling_rig,
    ObstacleEquipmentType.drilling_rig,
    ObstacleEquipmentType.concrete_pump_boom,
}
ZERO = Decimal("0.00")


# ---- NOTAM helpers -------------------------------------------------------------------------------


def in_effect(n: NotamRequest, at: datetime) -> bool:
    return (
        n.status == NS.issued
        and n.effective_from_utc is not None
        and n.effective_to_utc is not None
        and n.effective_from_utc <= at <= n.effective_to_utc
    )


def covers(n: NotamRequest, start: datetime, end: datetime) -> bool:
    """NT-4: [start, end) within the issued effective window."""
    return (
        n.status == NS.issued
        and n.effective_from_utc is not None
        and n.effective_to_utc is not None
        and n.effective_from_utc <= start
        and end <= n.effective_to_utc
    )


def covers_day(n: NotamRequest, d: date) -> bool:
    """OB-7: an Issued NTM whose effective window overlaps the local day."""
    lo = common.local_midnight_utc(d)
    hi = common.local_midnight_utc(d + timedelta(days=1))
    return (
        n.status == NS.issued
        and n.effective_from_utc is not None
        and n.effective_to_utc is not None
        and n.effective_from_utc < hi
        and n.effective_to_utc > lo
    )


def required_lead_days(n: NotamRequest, s: Any) -> int:
    """NT-2."""
    impact = set(n.works_impact or [])
    long_runway = WorksImpact.runway_closure.value in impact and (
        n.requested_end_utc - n.requested_start_utc > timedelta(hours=24)
    )
    if WorksImpact.declared_distances_change.value in impact or long_runway:
        return int(s.airac_lead_days)
    return int(s.notam_request_lead_days)


def _linked_waps(db: Session, ntm_id: uuid.UUID) -> list[Wap]:
    return list(
        db.scalars(
            select(Wap).where(Wap.linked_ntm_ids.contains([ntm_id]), Wap.revision_of_id.is_(None))
        )
    )


def notam_read(
    db: Session, p: Principal | None, n: NotamRequest, refs: Refs | None = None
) -> NotamRequestRead:
    refs = refs or Refs(db)
    s = common.settings(db, n.project_id)
    succ = db.scalar(select(NotamRequest.id).where(NotamRequest.replaces_ntm_id == n.id))
    return NotamRequestRead(
        id=n.id,
        ntm_no=n.ntm_no,
        project_id=n.project_id,
        zones=[z for z in (refs.zone(x) for x in n.zone_ids or []) if z is not None],
        engagement=refs.eng(n.engagement_id),
        works_impact=[WorksImpact(x) for x in n.works_impact or []],
        description_en=n.description_en,
        description_ar=n.description_ar,
        requested_start_utc=n.requested_start_utc,
        requested_end_utc=n.requested_end_utc,
        schedule_text=n.schedule_text,
        required_lead_days=required_lead_days(n, s),
        submitted_to_ops_at=n.submitted_to_ops_at,
        late_request=n.late_request,
        late_justification=n.late_justification,
        notam_number=n.notam_number,
        notam_type=n.notam_type,
        effective_from_utc=n.effective_from_utc,
        effective_to_utc=n.effective_to_utc,
        effective_from_notam=common.notam_format(n.effective_from_utc),
        effective_to_notam=common.notam_format(n.effective_to_utc),
        item_e_text=n.item_e_text,
        replaces_ntm_id=n.replaces_ntm_id,
        replaced_by_ntm_id=succ,
        in_effect=in_effect(n, now()),
        linked_wap_ids=[w.id for w in _linked_waps(db, n.id)],
        requested_by=refs.user(n.requested_by_user_id) or attachments.UNKNOWN,
        status=n.status,
        created_at=n.created_at,
        updated_at=n.updated_at,
    )


def _view(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, C.access_works_view)
    if g is None:
        raise forbidden_error()
    return g


def _visible_row(p: Principal, project_id: uuid.UUID, eng: uuid.UUID | None) -> bool:
    g = p.grant(project_id, C.access_works_view)
    if g is None:
        return False
    return g.engagement_ids is None or (eng is not None and eng in g.engagement_ids)


def get_notam_row(db: Session, p: Principal, ntm_id: uuid.UUID) -> NotamRequest:
    n = db.get(NotamRequest, ntm_id)
    if n is None:
        raise not_found("NOTAM request")
    _view(db, p, n.project_id)
    if not _visible_row(p, n.project_id, n.engagement_id):
        raise forbidden_error("This record is outside your scope.")
    return n


def read_notam(db: Session, p: Principal, ntm_id: uuid.UUID) -> NotamRequestRead:
    return notam_read(db, p, get_notam_row(db, p, ntm_id))


def list_notams(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[NotamStatus] | None,
    zone_id: uuid.UUID | None,
    works_impact: WorksImpact | None,
    in_effect_now: bool | None,
    late_request: bool | None,
    not_issued_within_hours: int | None,
    date_from: date | None,
    date_to: date | None,
) -> NotamRequestPage:
    project = projects.get_visible(db, p, project_id)
    common.require_airport(project)
    g = _view(db, p, project.id)
    stmt = select(NotamRequest).where(NotamRequest.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(NotamRequest.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(NotamRequest.status.in_(statuses))
    if zone_id:
        stmt = stmt.where(NotamRequest.zone_ids.contains([zone_id]))
    if works_impact:
        stmt = stmt.where(NotamRequest.works_impact.contains([works_impact.value]))
    at = now()
    if in_effect_now is not None:
        cond: ColumnElement[bool] = (
            (NotamRequest.status == NS.issued)
            & (NotamRequest.effective_from_utc <= at)
            & (NotamRequest.effective_to_utc >= at)
        )
        stmt = stmt.where(cond if in_effect_now else ~cond)
    if late_request is not None:
        stmt = stmt.where(NotamRequest.late_request.is_(late_request))
    if not_issued_within_hours is not None:
        stmt = stmt.where(
            NotamRequest.status.in_([NS.submitted_to_ops, NS.requested_from_ais]),
            NotamRequest.requested_start_utc <= at + timedelta(hours=not_issued_within_hours),
        )
    if date_from:
        stmt = stmt.where(NotamRequest.requested_end_utc >= common.local_midnight_utc(date_from))
    if date_to:
        stmt = stmt.where(
            NotamRequest.requested_start_utc
            < common.local_midnight_utc(date_to + timedelta(days=1))
        )
    stmt = stmt.order_by(NotamRequest.requested_start_utc.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(zones=[z for n in rows for z in n.zone_ids or []])
    return NotamRequestPage(
        items=[notam_read(db, p, n, refs) for n in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _check_notam_zones(db: Session, project_id: uuid.UUID, zone_ids: list[uuid.UUID]) -> list[Zone]:
    zones = []
    for zid in dict.fromkeys(zone_ids):
        z = db.get(Zone, zid)
        if z is None or z.project_id != project_id or not z.notam_required_for_works:
            raise validation_error(
                "zone_ids", "Choose airside zones that require a NOTAM for works."
            )
        zones.append(z)
    return zones


def _notam_snapshot(n: NotamRequest) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(n, k)
            for k in (
                "ntm_no", "zone_ids", "works_impact", "requested_start_utc", "requested_end_utc",
                "schedule_text", "submitted_to_ops_at", "late_request", "notam_number",
                "notam_type", "effective_from_utc", "effective_to_utc", "status",
            )
        }
    )  # fmt: skip


def create_notam(
    db: Session, p: Principal, project_id: uuid.UUID, body: NotamRequestCreate
) -> NotamRequestRead:
    project = projects.get_visible(db, p, project_id)
    common.require_airport(project)
    zones = _check_notam_zones(db, project.id, body.zone_ids)
    common.require_cap(p, project.id, C.notam_edit, [z.site_id for z in zones], body.engagement_id)
    if body.requested_end_utc <= body.requested_start_utc:
        raise validation_error("requested_end_utc", "The end must be after the start.")
    year = today().year
    seq = next_seq(db, NotamRequest, project.id, year)
    n = NotamRequest(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        ntm_no=make_ref("NTM", project.code, year, seq, 4),
        project_id=project.id,
        zone_ids=[z.id for z in zones],
        engagement_id=body.engagement_id,
        works_impact=[w.value for w in dict.fromkeys(body.works_impact)],
        description_en=body.description_en,
        description_ar=body.description_ar,
        requested_start_utc=body.requested_start_utc,
        requested_end_utc=body.requested_end_utc,
        schedule_text=body.schedule_text,
        requested_by_user_id=p.user.id,
        status=NS.draft,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(n)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.notam_request,
        entity_id=n.id,
        project_id=project.id,
        after=_notam_snapshot(n),
    )
    return notam_read(db, p, n)


def update_notam(
    db: Session, p: Principal, ntm_id: uuid.UUID, body: NotamRequestUpdate
) -> NotamRequestRead:
    n = get_notam_row(db, p, ntm_id)
    common.require_cap(p, n.project_id, C.notam_edit, None, n.engagement_id)
    if n.status != NS.draft:
        raise invalid_transition("NOTAM request", n.status, "edited")
    before = _notam_snapshot(n)
    ch = body.changes()
    if "zone_ids" in ch:
        n.zone_ids = [z.id for z in _check_notam_zones(db, n.project_id, ch.pop("zone_ids"))]
    if "works_impact" in ch:
        n.works_impact = [getattr(w, "value", w) for w in dict.fromkeys(ch.pop("works_impact"))]
    for k, v in ch.items():
        setattr(n, k, v)
    if n.requested_end_utc <= n.requested_start_utc:
        raise validation_error("requested_end_utc", "The end must be after the start.")
    n.updated_at = now()
    n.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _notam_snapshot(n))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(n.project_id),
            entity_type=EntityType.notam_request,
            entity_id=n.id,
            project_id=n.project_id,
            before=bf,
            after=af,
        )
    return notam_read(db, p, n)


def _ntm_ended(db: Session, n: NotamRequest) -> None:
    """NT-5 / OB-7 cascades (WAP blockers and suspensions, obstacle clearances)."""
    from app.services.access import waps  # noqa: PLC0415 (waps imports this module)

    for w in _linked_waps(db, n.id):
        waps.refresh(db, w)
    for o in db.scalars(
        select(ObstacleClearance).where(ObstacleClearance.linked_ntm_ids.contains([n.id]))
    ):
        evaluate_obstacle(db, o, today())


def _notify_ntm(db: Session, n: NotamRequest, kind: NotificationKind, en: str, ar: str) -> None:
    users = {n.requested_by_user_id}
    users.update(contractor_reps(db, n.project_id, n.engagement_id))
    users.update(notify.users_with_role(db, Role.hse_officer, [n.project_id]))
    notify.notify(
        db, users, kind, f"{n.ntm_no}: {en}", f"{n.ntm_no}: {ar}", None, None,
        EntityType.notam_request, n.id, n.project_id,
    )  # fmt: skip


def transition_notam(
    db: Session, p: Principal, ntm_id: uuid.UUID, body: NotamTransitionRequest
) -> NotamRequestRead:
    n = get_notam_row(db, p, ntm_id)
    frm, to = n.status, body.to_status
    before = _notam_snapshot(n)
    at = now()
    warnings: list[ApiWarning] = []

    def need(cap: Capability) -> None:
        common.require_cap(p, n.project_id, cap, None, n.engagement_id)

    if frm == NS.draft and to == NS.submitted_to_ops:
        need(C.notam_edit)
        s = common.settings(db, n.project_id)
        lead = required_lead_days(n, s)
        late = at > n.requested_start_utc - timedelta(days=lead)
        if late:
            if not body.late_justification:
                raise ApiError(
                    422,
                    ErrorCode.LATE_JUSTIFICATION_REQUIRED,
                    f"Less than {lead} days before the start: give a late justification (NT-2).",
                    f"المهلة أقل من {lead} يوماً: يلزم تبرير التأخير.",
                    meta={"required_lead_days": lead},
                )
            n.late_justification = body.late_justification
            warnings.append(
                ApiWarning(
                    code="LATE_REQUEST",
                    message=f"Submitted with less than {lead} days lead (K-59).",
                    message_ar="قُدّم الطلب بمهلة أقل من المطلوب.",
                )
            )
        n.late_request = late
        n.submitted_to_ops_at = at
    elif frm == NS.submitted_to_ops and to == NS.requested_from_ais:
        need(C.notam_process)
    elif frm == NS.requested_from_ais and to == NS.issued:
        need(C.notam_process)
        _issue_fields(db, n, body.notam_number, body.effective_from_utc, body.effective_to_utc)
        n.notam_type = body.notam_type or NotamType.N
        n.item_e_text = body.item_e_text
    elif frm in (NS.submitted_to_ops, NS.requested_from_ais) and to == NS.rejected:
        need(C.notam_process)
        n.status_reason = common.reason_text(body.reason)
    elif frm == NS.issued and to == NS.cancelled:
        need(C.notam_process)
        n.status_reason = common.reason_text(body.reason)
        n.notam_type = n.notam_type  # the NOTAMC is recorded as the cancellation itself
    elif to == NS.replaced:
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "Use POST /notam-requests/{id}/replace.",
            "استخدم إجراء الاستبدال.",
        )
    else:
        raise invalid_transition("NOTAM request", frm, to)
    n.status = to
    n.updated_at = at
    n.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(n.project_id),
        entity_type=EntityType.notam_request,
        entity_id=n.id,
        project_id=n.project_id,
        before=before,
        after=_notam_snapshot(n),
    )
    if to in (NS.issued, NS.cancelled):
        _ntm_ended(db, n)  # issue lifts blockers; cancel suspends (NT-5)
    if to == NS.cancelled and _linked_waps(db, n.id):
        _notify_ntm(
            db, n, NotificationKind.notam_ended_with_waps,
            "cancelled: linked work-area permits suspended", "أُلغي: تم إيقاف التصاريح المرتبطة",
        )  # fmt: skip
    out = notam_read(db, p, n)
    out.warnings = warnings
    return out


def _issue_fields(
    db: Session,
    n: NotamRequest,
    number: str | None,
    start: datetime | None,
    end: datetime | None,
) -> None:
    if not number or start is None or end is None:
        raise validation_error(
            "notam_number", "notam_number and the effective from/to times are required."
        )
    if end <= start:
        raise validation_error("effective_to_utc", "The end must be after the start.")
    if db.scalar(
        select(NotamRequest.id).where(
            NotamRequest.project_id == n.project_id,
            NotamRequest.notam_number == number,
            NotamRequest.id != n.id,
        )
    ):
        raise duplicate("notam_number", "This NOTAM number is already recorded (NT-7).")
    n.notam_number = number
    n.effective_from_utc = start
    n.effective_to_utc = end


def replace_notam(
    db: Session, p: Principal, ntm_id: uuid.UUID, body: NotamReplaceRequest
) -> NotamRequestRead:
    """NOTAMR: new Issued record replacing an Issued one; auto-linked to its WAPs (NT-5)."""
    old = get_notam_row(db, p, ntm_id)
    common.require_cap(p, old.project_id, C.notam_process, None, old.engagement_id)
    if old.status != NS.issued:
        raise invalid_transition("NOTAM request", old.status, NS.replaced)
    project = db.get(Project, old.project_id)
    assert project is not None  # noqa: S101
    year = today().year
    seq = next_seq(db, NotamRequest, project.id, year)
    n = NotamRequest(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        ntm_no=make_ref("NTM", project.code, year, seq, 4),
        project_id=project.id,
        zone_ids=list(old.zone_ids),
        engagement_id=old.engagement_id,
        works_impact=list(old.works_impact),
        description_en=old.description_en,
        description_ar=old.description_ar,
        requested_start_utc=body.effective_from_utc,
        requested_end_utc=body.effective_to_utc,
        schedule_text=body.schedule_text or old.schedule_text,
        submitted_to_ops_at=now(),
        notam_type=NotamType.R,
        item_e_text=body.item_e_text,
        replaces_ntm_id=old.id,
        requested_by_user_id=p.user.id,
        status=NS.issued,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(n)
    _issue_fields(db, n, body.notam_number, body.effective_from_utc, body.effective_to_utc)
    db.flush()
    old.status = NS.replaced
    old.updated_at = now()
    for w in _linked_waps(db, old.id):
        w.linked_ntm_ids = [*w.linked_ntm_ids, n.id]
    for o in db.scalars(
        select(ObstacleClearance).where(ObstacleClearance.linked_ntm_ids.contains([old.id]))
    ):
        o.linked_ntm_ids = [*o.linked_ntm_ids, n.id]
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.notam_request,
        entity_id=n.id,
        project_id=project.id,
        after=_notam_snapshot(n),
        details={"replaces": old.ntm_no},
    )
    _ntm_ended(db, old)
    return notam_read(db, p, n)


def expire_notams(db: Session, at: datetime | None = None) -> int:
    """§4.6 job (every 5 min): Issued → Expired when now > effective_to; NT-5 cascade."""
    at = at or now()
    n_done = 0
    for n in db.scalars(
        select(NotamRequest).where(
            NotamRequest.status == NS.issued, NotamRequest.effective_to_utc < at
        )
    ):
        n.status = NS.expired
        n.updated_at = at
        n_done += 1
        db.flush()
        audit.record(
            db,
            AuditAction.status_change,
            entity_type=EntityType.notam_request,
            entity_id=n.id,
            project_id=n.project_id,
            before={"status": "issued"},
            after={"status": "expired"},
        )
        _ntm_ended(db, n)
        active = [
            w for w in _linked_waps(db, n.id) if w.status in (WapStatus.active, WapStatus.suspended)
        ]
        if active:
            _notify_ntm(
                db, n, NotificationKind.notam_ended_with_waps,
                "expired with linked work-area permits", "انتهى مع وجود تصاريح مرتبطة",
            )  # fmt: skip
    return n_done


# ---- obstacle heights (§6.4, OB-3) ---------------------------------------------------------------


@dataclass
class Heights:
    top: Decimal
    ols: Decimal | None
    margin: Decimal | None
    penetration: Decimal
    reasons: list[ClearanceReason]


def compute(
    project: Project,
    zone: Zone | None,
    equipment_type: ObstacleEquipmentType,
    ground: Decimal,
    height: Decimal,
    ols: Decimal | None,
    s: Any,
) -> Heights:
    top = ground + height
    zl = zone.ols_height_limit_m_amsl if zone else None
    limit = ols if ols is not None else (Decimal(str(zl)) if zl is not None else None)
    margin = (limit - top) if limit is not None else None
    pen = max(ZERO, -margin) if margin is not None else ZERO
    reasons: list[ClearanceReason] = []
    zmax = zone.max_equipment_height_m_agl if zone else None
    if zmax is not None and height > Decimal(str(zmax)):
        reasons.append(ClearanceReason.zone_height_exceeded)
    if limit is not None and top > limit:
        reasons.append(ClearanceReason.ols_penetration)
    if limit is not None and limit - s.ols_buffer_m < top <= limit:
        reasons.append(ClearanceReason.within_ols_buffer)
    if not project.is_airport and height >= s.obstacle_height_threshold_m:
        reasons.append(ClearanceReason.height_threshold)
    if (
        project.is_airport
        and equipment_type in OPERATOR_TYPES
        and zone is not None
        and zone.zone_type == ZoneType.airside
    ):
        reasons.append(ClearanceReason.operator_requires)
    return Heights(common.q2(top), limit, margin, common.q2(pen), reasons)


def _ft(v: Decimal | None) -> Decimal | None:
    return None if v is None else common.to_ft(v)


def figures(h: Heights, height: Decimal, zone: Zone | None) -> HeightFigures:
    return HeightFigures(
        top_elevation_m_amsl=common.q2(h.top),
        top_elevation_ft_amsl=common.to_ft(h.top),
        ols_limit_m_amsl=common.q2(h.ols) if h.ols is not None else None,
        margin_m=common.q2(h.margin) if h.margin is not None else None,
        margin_ft=_ft(h.margin),
        penetration_m=common.q2(h.penetration),
        penetration_ft=common.to_ft(h.penetration),
        max_height_m_agl=common.q2(height),
        max_height_ft_agl=common.to_ft(height),
        zone_max_equipment_height_m_agl=zone.max_equipment_height_m_agl if zone else None,
        clearance_reasons=h.reasons,
        clearance_required=bool(h.reasons),
    )


def active_on(o: ObstacleClearance, d: date) -> bool:
    return (
        o.status in APPROVED
        and o.valid_from is not None
        and o.valid_to is not None
        and o.valid_from <= d <= o.valid_to
    )


def obstacle_read(
    db: Session, p: Principal | None, o: ObstacleClearance, refs: Refs | None = None
) -> ObstacleRead:
    refs = refs or Refs(db)
    project = db.get(Project, o.project_id)
    zone = db.get(Zone, o.zone_id) if o.zone_id else None
    assert project is not None  # noqa: S101
    s = common.settings(db, o.project_id)
    h = compute(
        project, zone, o.equipment_type, o.ground_elevation_m_amsl, o.max_height_m_agl,
        o.ols_limit_m_amsl, s,
    )  # fmt: skip
    v = db.get(Vehicle, o.vehicle_id) if o.vehicle_id else None
    return ObstacleRead(
        id=o.id,
        obs_no=o.obs_no,
        project_id=o.project_id,
        zone=refs.zone(o.zone_id),
        engagement=refs.eng(o.engagement_id),
        vehicle=common.vehicle_ref(v) if v else None,
        equipment_desc=o.equipment_desc,
        equipment_type=o.equipment_type,
        location_lat=o.location_lat,
        location_lng=o.location_lng,
        location_desc=o.location_desc,
        ground_elevation_m_amsl=o.ground_elevation_m_amsl,
        ols_surface=o.ols_surface,
        ols_source_ref=o.ols_source_ref,
        heights=figures(h, o.max_height_m_agl, zone),
        requested_from=o.requested_from,
        requested_to=o.requested_to,
        submitted_at=o.submitted_at,
        late_request=o.late_request,
        late_justification=o.late_justification,
        authority_ref=o.authority_ref,
        decision=o.decision,
        approved_max_height_m_agl=o.approved_max_height_m_agl,
        approved_max_height_ft_agl=_ft(o.approved_max_height_m_agl),
        approved_top_m_amsl=o.approved_top_m_amsl,
        conditions=[ObstacleCondition(c) for c in o.conditions or []],
        conditions_text=o.conditions_text,
        valid_from=o.valid_from,
        valid_to=o.valid_to,
        linked_ntm_ids=list(o.linked_ntm_ids or []),
        active_today=active_on(o, today()),
        system_suspended=o.system_suspended,
        requested_by=refs.user(o.requested_by_user_id) or attachments.UNKNOWN,
        status=o.status,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def get_obstacle_row(db: Session, p: Principal, obs_id: uuid.UUID) -> ObstacleClearance:
    o = db.get(ObstacleClearance, obs_id)
    if o is None:
        raise not_found("Obstacle clearance")
    _view(db, p, o.project_id)
    if not _visible_row(p, o.project_id, o.engagement_id):
        raise forbidden_error("This record is outside your scope.")
    return o


def read_obstacle(db: Session, p: Principal, obs_id: uuid.UUID) -> ObstacleRead:
    return obstacle_read(db, p, get_obstacle_row(db, p, obs_id))


def list_obstacles(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[ObstacleStatus] | None,
    zone_id: uuid.UUID | None,
    reason: ClearanceReason | None,
    active_on_day: date | None,
    expiring_within_days: int | None,
) -> ObstaclePage:
    project = projects.get_visible(db, p, project_id)
    g = _view(db, p, project.id)
    stmt = select(ObstacleClearance).where(ObstacleClearance.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(ObstacleClearance.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(ObstacleClearance.status.in_(statuses))
    if zone_id:
        stmt = stmt.where(ObstacleClearance.zone_id == zone_id)
    if reason:
        stmt = stmt.where(ObstacleClearance.clearance_reasons.contains([reason.value]))
    if active_on_day:
        stmt = stmt.where(
            ObstacleClearance.status.in_(APPROVED),
            ObstacleClearance.valid_from <= active_on_day,
            ObstacleClearance.valid_to >= active_on_day,
        )
    if expiring_within_days is not None:
        day = today()
        stmt = stmt.where(
            ObstacleClearance.status.in_(APPROVED),
            ObstacleClearance.valid_to >= day,
            ObstacleClearance.valid_to <= day + timedelta(days=expiring_within_days),
        )
    stmt = stmt.order_by(ObstacleClearance.requested_from.desc(), ObstacleClearance.seq.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(zones=[o.zone_id for o in rows])
    return ObstaclePage(
        items=[obstacle_read(db, p, o, refs) for o in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _validate_obstacle(
    db: Session, project: Project, body: ObstacleFields | ObstacleClearance
) -> tuple[Zone | None, Vehicle | None]:
    zone = db.get(Zone, body.zone_id) if body.zone_id else None
    if body.zone_id and (zone is None or zone.project_id != project.id):
        raise validation_error("zone_id", "Unknown zone on this project.")
    if project.is_airport:
        if zone is None:
            raise validation_error("zone_id", "A zone is required on airport projects (OB-1).")
        if body.ols_surface is None:
            raise validation_error("ols_surface", "Required on airport projects (OB-1).")
    v = db.get(Vehicle, body.vehicle_id) if body.vehicle_id else None
    if body.vehicle_id and (v is None or v.project_id != project.id):
        raise validation_error("vehicle_id", "Unknown vehicle on this project.")
    if v is None and not body.equipment_desc:
        raise validation_error("equipment_desc", "Give a vehicle or an equipment description.")
    if v is not None and body.max_height_m_agl < v.max_working_height_m_agl:
        raise validation_error(
            "max_height_m_agl", "Must be ≥ the vehicle's maximum working height (OB-2)."
        )
    if (
        body.ols_limit_m_amsl is not None
        and zone is not None
        and zone.ols_height_limit_m_amsl is not None
        and body.ols_limit_m_amsl != zone.ols_height_limit_m_amsl
        and not body.ols_source_ref
    ):
        raise validation_error("ols_source_ref", "Give the OLS drawing reference.")
    if body.requested_to < body.requested_from:
        raise validation_error("requested_to", "Must be on or after requested_from.")
    if not (Decimal(16) <= Decimal(body.location_lat) <= Decimal(33)) or not (
        Decimal(34) <= Decimal(body.location_lng) <= Decimal(56)
    ):
        raise validation_error("location_lat", "The location must be inside Saudi Arabia.")
    return zone, v


def preview(db: Session, p: Principal, body: ObstaclePreviewRequest) -> HeightFigures:
    project = projects.get_visible(db, p, body.project_id)
    _view(db, p, project.id)
    zone, _ = _validate_obstacle(db, project, body)
    s = common.settings(db, project.id)
    h = compute(
        project, zone, body.equipment_type, body.ground_elevation_m_amsl, body.max_height_m_agl,
        body.ols_limit_m_amsl, s,
    )  # fmt: skip
    return figures(h, body.max_height_m_agl, zone)


def _obs_snapshot(o: ObstacleClearance) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(o, k)
            for k in (
                "obs_no", "zone_id", "vehicle_id", "equipment_type", "max_height_m_agl",
                "ground_elevation_m_amsl", "ols_limit_m_amsl", "top_elevation_m_amsl",
                "penetration_m", "clearance_reasons", "requested_from", "requested_to",
                "decision", "approved_max_height_m_agl", "conditions", "valid_from", "valid_to",
                "linked_ntm_ids", "status",
            )
        }
    )  # fmt: skip


def _recompute(db: Session, project: Project, o: ObstacleClearance, zone: Zone | None) -> None:
    s = common.settings(db, project.id)
    h = compute(
        project, zone, o.equipment_type, o.ground_elevation_m_amsl, o.max_height_m_agl,
        o.ols_limit_m_amsl, s,
    )  # fmt: skip
    o.top_elevation_m_amsl = h.top
    o.penetration_m = h.penetration
    o.clearance_reasons = [r.value for r in h.reasons]


def create_obstacle(
    db: Session, p: Principal, project_id: uuid.UUID, body: ObstacleCreate
) -> ObstacleRead:
    project = projects.get_visible(db, p, project_id)
    zone, _ = _validate_obstacle(db, project, body)
    common.require_cap(
        p, project.id, C.obstacle_edit, [zone.site_id] if zone else None, body.engagement_id
    )
    year = today().year
    seq = next_seq(db, ObstacleClearance, project.id, year)
    data = body.model_dump(exclude={"equipment_item_id"})  # Phase 4 stage 2 persists it (CF-4)
    o = ObstacleClearance(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        obs_no=make_ref("OBS", project.code, year, seq, 4),
        project_id=project.id,
        requested_by_user_id=p.user.id,
        status=OS.draft,
        conditions=[],
        linked_ntm_ids=[],
        alerts_sent=[],
        created_by_user_id=p.user.id,
        **data,
    )
    _recompute(db, project, o, zone)
    db.add(o)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.obstacle_clearance,
        entity_id=o.id,
        project_id=project.id,
        after=_obs_snapshot(o),
    )
    out = obstacle_read(db, p, o)
    if not o.clearance_reasons:
        out.warnings = [
            ApiWarning(
                code="CLEARANCE_NOT_REQUIRED",
                message="No OB-3 reason applies: a clearance is not required.",
                message_ar="لا يلزم الحصول على موافقة.",
            )
        ]
    return out


def update_obstacle(
    db: Session, p: Principal, obs_id: uuid.UUID, body: ObstacleUpdate
) -> ObstacleRead:
    o = get_obstacle_row(db, p, obs_id)
    common.require_cap(p, o.project_id, C.obstacle_edit, None, o.engagement_id)
    if o.status != OS.draft:
        raise invalid_transition("Obstacle clearance", o.status, "edited")
    project = db.get(Project, o.project_id)
    assert project is not None  # noqa: S101
    before = _obs_snapshot(o)
    for k, v in body.changes().items():
        if k == "equipment_item_id":  # Phase 4 stage 2 persists it (CF-4)
            continue
        setattr(o, k, v)
    zone, _ = _validate_obstacle(db, project, o)
    _recompute(db, project, o, zone)
    o.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _obs_snapshot(o))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(o.project_id),
            entity_type=EntityType.obstacle_clearance,
            entity_id=o.id,
            project_id=o.project_id,
            before=bf,
            after=af,
        )
    return obstacle_read(db, p, o)


def _approved_status(o: ObstacleClearance) -> ObstacleStatus:
    return (
        OS.approved_with_conditions
        if o.decision == ObstacleDecision.approved_with_conditions
        else OS.approved
    )


def _dependent_waps(db: Session, o: ObstacleClearance) -> None:
    from app.services.access import waps  # noqa: PLC0415

    for w in db.scalars(
        select(Wap).where(Wap.linked_obs_ids.contains([o.id]), Wap.revision_of_id.is_(None))
    ):
        waps.refresh(db, w)


def transition_obstacle(
    db: Session, p: Principal, obs_id: uuid.UUID, body: ObstacleTransitionRequest
) -> ObstacleRead:
    o = get_obstacle_row(db, p, obs_id)
    frm, to = o.status, body.to_status
    before = _obs_snapshot(o)
    at = now()
    if frm == OS.draft and to == OS.submitted:
        common.require_cap(p, o.project_id, C.obstacle_edit, None, o.engagement_id)
        s = common.settings(db, o.project_id)
        late = today() > o.requested_from - timedelta(days=s.obstacle_clearance_lead_days)
        if late and not body.late_justification:
            raise ApiError(
                422,
                ErrorCode.LATE_JUSTIFICATION_REQUIRED,
                f"Less than {s.obstacle_clearance_lead_days} days before the start: give a "
                "late justification (OB-5).",
                "المهلة أقل من المطلوب: يلزم تبرير التأخير.",
            )
        o.late_request = late
        o.late_justification = body.late_justification if late else None
        o.submitted_at = at
        o.authority_ref = body.authority_ref or o.authority_ref
    elif frm in APPROVED and to == OS.suspended:
        common.require_cap(p, o.project_id, C.obstacle_decide, None, o.engagement_id)
        o.status_reason = common.reason_text(body.reason)
        o.system_suspended = False
    elif frm == OS.suspended and to in APPROVED:
        common.require_cap(p, o.project_id, C.obstacle_decide, None, o.engagement_id)
        o.status_reason = common.reason_text(body.reason)
        o.system_suspended = False
        to = _approved_status(o)
    elif frm in (*APPROVED, OS.suspended) and to == OS.withdrawn:
        own = o.requested_by_user_id == p.user.id
        if own:
            common.require_cap(p, o.project_id, C.obstacle_edit, None, o.engagement_id)
        else:
            common.require_cap(p, o.project_id, C.obstacle_decide, None, o.engagement_id)
        o.status_reason = common.reason_text(body.reason)
    elif to in (OS.approved, OS.approved_with_conditions, OS.rejected):
        raise ApiError(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "Use POST /obstacle-clearances/{id}/decision.",
            "استخدم إجراء القرار.",
        )
    else:
        raise invalid_transition("Obstacle clearance", frm, to)
    o.status = to
    o.updated_at = at
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.obstacle_clearance,
        entity_id=o.id,
        project_id=o.project_id,
        before=before,
        after=_obs_snapshot(o),
    )
    if to in (OS.suspended, OS.withdrawn, *APPROVED):
        _dependent_waps(db, o)
    return obstacle_read(db, p, o)


def decide(
    db: Session, p: Principal, obs_id: uuid.UUID, body: ObstacleDecisionRequest
) -> ObstacleRead:
    o = get_obstacle_row(db, p, obs_id)
    common.require_cap(p, o.project_id, C.obstacle_decide, None, o.engagement_id)
    if o.status != OS.submitted:
        raise invalid_transition("Obstacle clearance", o.status, body.decision.value)
    before = _obs_snapshot(o)
    conds = list(dict.fromkeys(c.value for c in body.conditions))
    if body.decision != ObstacleDecision.rejected:
        if ClearanceReason.ols_penetration.value in (o.clearance_reasons or []) and (
            ObstacleCondition.notam_required.value not in conds
            or ObstacleCondition.obstruction_light.value not in conds
            or not (body.authority_ref or o.authority_ref)
        ):
            raise ApiError(
                422,
                ErrorCode.OB_CONDITIONS_REQUIRED,
                "An OLS penetration needs conditions notam_required and obstruction_light and "
                "an authority reference (OB-4).",
                "اختراق سطح العوائق يتطلب شرطي NOTAM والإنارة ومرجع الجهة.",
            )
        if ObstacleCondition.notam_required.value in conds and not body.linked_ntm_ids:
            raise validation_error("linked_ntm_ids", "Link the NOTAM request(s) (OB-7).")
        for nid in body.linked_ntm_ids:
            n = db.get(NotamRequest, nid)
            if n is None or n.project_id != o.project_id:
                raise validation_error("linked_ntm_ids", "Unknown NOTAM request.")
        vf = body.valid_from or o.requested_from
        vt = body.valid_to or o.requested_to
        if vf < o.requested_from or vt > o.requested_to or vt < vf:
            raise validation_error(
                "valid_from", "The validity must be within the requested window."
            )
        amh = body.approved_max_height_m_agl or o.max_height_m_agl
        if amh > o.max_height_m_agl:
            raise validation_error("approved_max_height_m_agl", "Must be ≤ the requested height.")
        o.approved_max_height_m_agl = amh
        o.approved_top_m_amsl = body.approved_top_m_amsl or common.q2(
            o.ground_elevation_m_amsl + amh
        )
        o.valid_from, o.valid_to = vf, vt
        o.linked_ntm_ids = list(dict.fromkeys(body.linked_ntm_ids))
        o.status = (
            OS.approved_with_conditions
            if body.decision == ObstacleDecision.approved_with_conditions or conds
            else OS.approved
        )
        o.decision = (
            ObstacleDecision.approved_with_conditions
            if o.status == OS.approved_with_conditions
            else ObstacleDecision.approved
        )
    else:
        o.decision = ObstacleDecision.rejected
        o.status = OS.rejected
    o.conditions = conds
    o.conditions_text = body.conditions_text
    o.authority_ref = body.authority_ref or o.authority_ref
    o.decided_at = now()
    o.updated_at = now()
    db.flush()
    if o.status in APPROVED:
        evaluate_obstacle(db, o, today())
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.obstacle_clearance,
        entity_id=o.id,
        project_id=o.project_id,
        before=before,
        after=_obs_snapshot(o),
    )
    notify.notify(
        db,
        {o.requested_by_user_id, *contractor_reps(db, o.project_id, o.engagement_id)},
        NotificationKind.obstacle_clearance_update,
        f"{o.obs_no}: {o.status.value.replace('_', ' ')}",
        f"{o.obs_no}: تم تسجيل القرار",
        None,
        None,
        EntityType.obstacle_clearance,
        o.id,
        o.project_id,
    )
    _dependent_waps(db, o)
    return obstacle_read(db, p, o)


def evaluate_obstacle(db: Session, o: ObstacleClearance, day: date) -> bool:
    """OB-7 (system suspension when notam_required and the day is not covered by an Issued
    linked NTM; lifted automatically) and §4.7 expiry. Returns True when the state changed."""
    changed = False
    if o.status in (*APPROVED, OS.suspended) and o.valid_to is not None and day > o.valid_to:
        o.status = OS.expired
        o.system_suspended = False
        changed = True
    elif ObstacleCondition.notam_required.value in (o.conditions or []) and o.valid_from:
        if day >= o.valid_from:
            ntms = [db.get(NotamRequest, i) for i in o.linked_ntm_ids or []]
            covered = any(n is not None and covers_day(n, day) for n in ntms)
            if not covered and o.status in APPROVED:
                o.status = OS.suspended
                o.system_suspended = True
                o.status_reason = "Linked NOTAM not issued for the day (OB-7)"
                changed = True
            elif covered and o.status == OS.suspended and o.system_suspended:
                o.status = _approved_status(o)
                o.system_suspended = False
                o.status_reason = None
                changed = True
    if changed:
        o.updated_at = now()
        db.flush()
        _dependent_waps(db, o)
    return changed


def obstacle_job(db: Session, day: date | None = None) -> int:
    day = day or today()
    n = 0
    for o in db.scalars(
        select(ObstacleClearance).where(ObstacleClearance.status.in_([*APPROVED, OS.suspended]))
    ):
        n += evaluate_obstacle(db, o, day)
    return n
