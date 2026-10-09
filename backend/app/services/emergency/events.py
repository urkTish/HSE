"""Real emergency events (spec 6c-emergency-drills §3.13, §4.6, EV-1…EV-7, PE-1, §6.7):
declaration with live alerts, the muster and suspensions, timeline, All Clear, void, review with
the incident link (EV-4), and the Phase 2 `aircraft_emergency` link (EV-6). Events never satisfy
programme lines (DP-6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import (
    EventAction,
    EventStatus,
    EventType,
    MusterSource,
    MusterStatus,
    ResponseType,
)
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.ptw_enums import StatusReason
from app.models import EmergencyEvent, Incident, Muster, OpsEvent
from app.schemas.emergency import (
    EventCreate,
    EventPage,
    EventRead,
    EventReviewInput,
    EventTimes,
    EventTransition,
    EventUpdate,
)
from app.services.common import invalid_transition, paginate
from app.services.emergency import common as ec
from app.services.emergency import muster as mu
from app.services.emergency import reference as ref
from app.services.hse_common import make_ref
from app.services.permissions import Principal, forbidden_error

C = Capability
ES = EventStatus
LATE = timedelta(minutes=15)
BACKDATE = timedelta(hours=24)


def times(e: EmergencyEvent) -> EventTimes:
    ext: dict[str, str | None] = {}
    for x in e.external_services or []:
        ext[x["agency"]] = ec.mstr(
            ec.minutes(ec.dt(x.get("called_at")), ec.dt(x.get("arrived_at")))
        )
    return EventTimes(
        first_response_min=ec.mstr(ec.minutes(e.raised_at, e.first_responder_at)),
        total_min=ec.mstr(ec.minutes(e.raised_at, e.all_clear_at)),
        external_arrival_min=ext,
    )


def event_read(db: Session, e: EmergencyEvent) -> EventRead:
    m = db.get(Muster, e.muster_id) if e.muster_id else None
    inc = db.get(Incident, e.incident_id) if e.incident_id else None
    return EventRead(
        id=e.id,
        event_no=e.event_no,
        project_id=e.project_id,
        event_type=e.event_type,
        site_id=e.site_id,
        site_code=ec.site_code(db, e.site_id) or "",
        zone_ids=list(e.zone_ids or []),
        zone_codes=ec.codes(db, e.zone_ids or []),
        location_en=e.location_en,
        raised_at=e.raised_at,
        declared_by=ec.user_ref(db, e.declared_by_user_id) if e.declared_by_user_id else None,
        response_type=e.response_type,
        muster_id=e.muster_id,
        muster_no=m.muster_no if m else None,
        first_responder_at=e.first_responder_at,
        external_services=list(e.external_services or []),
        casualties_count=e.casualties_count,
        incident_id=e.incident_id,
        incident_ref=inc.ref if inc else None,
        ops_event_id=e.ops_event_id,
        all_clear_at=e.all_clear_at,
        all_clear_by=ec.user_ref(db, e.all_clear_by_user_id) if e.all_clear_by_user_id else None,
        review=dict(e.review) if e.review else None,
        times=times(e),
        late_entry=e.late_entry,
        status=e.status,
        status_reason=e.status_reason,
    )


def _event(db: Session, p: Principal, event_id: uuid.UUID) -> EmergencyEvent:
    e = db.get(EmergencyEvent, event_id)
    if e is None or not p.can_see_project(e.project_id):
        raise not_found("Emergency event")
    ec.need(p, e.project_id, C.emergency_view, write=False)
    return e


def list_events(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    event_type: list[EventType] | None,
    status: list[EventStatus] | None,
    page: int,
    size: int,
) -> EventPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    q = select(EmergencyEvent).where(EmergencyEvent.project_id == project_id)
    if event_type:
        q = q.where(EmergencyEvent.event_type.in_(event_type))
    if status:
        q = q.where(EmergencyEvent.status.in_(status))
    rows, total = paginate(db, q.order_by(EmergencyEvent.raised_at.desc()), page, size)
    return EventPage(
        items=[event_read(db, e) for e in rows], total=total, page=page, page_size=size
    )


def read_event(db: Session, p: Principal, event_id: uuid.UUID) -> EventRead:
    return event_read(db, _event(db, p, event_id))


# ---- declaration (EV-1…EV-3, PE-1) ---------------------------------------------------------------


def _incident(db: Session, project_id: uuid.UUID, incident_id: uuid.UUID | None) -> None:
    if incident_id is None:
        return
    inc = db.get(Incident, incident_id)
    if inc is None or inc.project_id != project_id:
        raise validation_error("incident_id", "Choose an incident of the project.")


def _alert(db: Session, e: EmergencyEvent) -> int:
    """EV-2: within 60 s to the HSE Manager, HSE Officers, site engineers, Contractor HSE Reps
    on the site and the rostered coordinators. Never a casualty's name."""
    if not ec.once(db, f"ev2:{e.id}"):
        return 0
    site = ec.site_code(db, e.site_id) or ""
    zones = ", ".join(ec.codes(db, e.zone_ids or []))
    aps = ", ".join(a.ap_code for a in ec.active_aps(db, e.project_id, e.site_id))
    t_en, t_ar = ref.EVENT_TYPES[e.event_type]
    r_en, r_ar = ref.RESPONSES[e.response_type]
    users = (
        ec.managers(db)
        | ec.officers(db, e.project_id)
        | ec.site_engineers(db, e.project_id, e.site_id)
        | ec.site_reps(db, e.project_id, e.site_id)
        | ec.coordinators(db, e.project_id, e.site_id, e.raised_at)
    )
    return ec.send(
        db, users, NotificationKind.emergency_event,
        f"EMERGENCY {e.event_no}: {t_en} at {site} [{zones}] — {r_en}; assembly point {aps}",
        f"طوارئ {e.event_no}: {t_ar} في {site} [{zones}] — {r_ar}؛ نقطة التجمع {aps}",
        e.project_id, EntityType.emergency_event, e.id, email=True,
    )  # fmt: skip


def open_event(
    db: Session,
    project_id: uuid.UUID,
    event_type: EventType,
    site_id: uuid.UUID,
    zone_ids: list[uuid.UUID],
    raised_at: datetime,
    response: ResponseType,
    by: uuid.UUID | None,
    at: datetime,
    **extra: Any,
) -> EmergencyEvent:
    year = ec.local_day(raised_at).year
    seq = ec.next_seq(db, EmergencyEvent, project_id, year)
    e = EmergencyEvent(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        event_no=make_ref("EMV", ec.pcode(db, project_id), year, seq, 3),
        project_id=project_id,
        event_type=event_type,
        site_id=site_id,
        zone_ids=list(zone_ids),
        raised_at=raised_at,
        declared_by_user_id=by,
        response_type=response,
        external_services=[],
        casualties_count=extra.pop("casualties_count", 0),
        late_entry=raised_at < at - LATE,
        status=ES.active,
        alerts_sent=[],
        created_by_user_id=by,
        **extra,
    )
    db.add(e)
    db.flush()
    if response in ref.MUSTER_RESPONSES:
        zones = list(zone_ids) if response == ResponseType.zone_evacuation else None
        m = mu.open_muster(
            db, project_id, MusterSource.event, e.id, site_id, zones, raised_at, e.late_entry, by
        )
        e.muster_id = m.id
        if not e.late_entry:
            from app.services.emergency import ptw as eptw  # noqa: PLC0415

            sz = None if response == ResponseType.site_evacuation else list(zone_ids)
            eptw.suspend_for(
                db, project_id, site_id, sz, StatusReason.emergency, e.event_no, raised_at
            )
    db.flush()
    if not e.late_entry:
        _alert(db, e)
    return e


def declare(db: Session, p: Principal, project_id: uuid.UUID, body: EventCreate) -> EventRead:
    ec.project(db, p, project_id)
    g = ec.need(p, project_id, C.emergency_declare)
    ec.site_or_422(db, project_id, body.site_id)
    if not ec.site_in_scope(db, g, project_id, body.site_id):
        raise forbidden_error()
    ec.zones_of_site(db, body.site_id, body.zone_ids)
    at = now()
    raised = body.raised_at or at
    if raised > at + timedelta(minutes=2):
        raise validation_error("raised_at", "The event time cannot be in the future.")
    if raised < at - BACKDATE:
        raise validation_error("raised_at", "An event may be back-dated by at most 24 hours.")
    _incident(db, project_id, body.incident_id)
    e = open_event(
        db, project_id, body.event_type, body.site_id, list(dict.fromkeys(body.zone_ids)),
        raised, body.response_type, p.user.id, at,
        location_en=body.location_en, casualties_count=body.casualties_count,
        incident_id=body.incident_id, notes=body.notes,
    )  # fmt: skip
    ec.record(db, p, AuditAction.create, EntityType.emergency_event, e, project_id)
    return event_read(db, e)


# ---- timeline (EV-7) -----------------------------------------------------------------------------


def update_event(db: Session, p: Principal, event_id: uuid.UUID, body: EventUpdate) -> EventRead:
    e = _event(db, p, event_id)
    g = ec.need(p, e.project_id, C.emergency_declare)
    if not ec.site_in_scope(db, g, e.project_id, e.site_id):
        raise forbidden_error()
    if e.status not in (ES.active, ES.all_clear):
        raise invalid_transition("Emergency event", e.status, "updated")
    ch = body.model_dump(exclude_unset=True)
    before = {k: str(getattr(e, k)) for k in ch if hasattr(e, k)}
    if body.first_responder_at is not None and body.first_responder_at < e.raised_at:
        raise ec.err(
            422, ErrorCode.TIMELINE_ORDER, "The first responder cannot arrive before the event.",
            "لا يمكن وصول المسعف قبل الحدث.", field="first_responder_at",
        )  # fmt: skip
    if body.external_services is not None:
        rows = []
        for i, x in enumerate(body.external_services):
            if (x.called_at and x.called_at < e.raised_at) or (
                x.called_at and x.arrived_at and x.arrived_at < x.called_at
            ):
                raise ec.err(
                    422, ErrorCode.TIMELINE_ORDER,
                    "External services: arrived ≥ called ≥ raised.",
                    "الجهات الخارجية: الوصول بعد الاتصال بعد البلاغ.",
                    field=f"external_services.{i}",
                )  # fmt: skip
            rows.append(
                {
                    "agency": x.agency.value,
                    "called_at": x.called_at.isoformat() if x.called_at else None,
                    "arrived_at": x.arrived_at.isoformat() if x.arrived_at else None,
                    "reference": x.reference,
                }
            )
        e.external_services = rows
    if "incident_id" in ch:
        _incident(db, e.project_id, body.incident_id)
    for k in ("first_responder_at", "casualties_count", "incident_id", "location_en", "notes"):
        if k in ch:
            setattr(e, k, ch[k])
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_event, e.id, e.project_id, before,
        {k: str(getattr(e, k)) for k in ch if hasattr(e, k)},
    )  # fmt: skip
    return event_read(db, e)


# ---- All Clear / void (§4.6) ---------------------------------------------------------------------


def all_clear(db: Session, e: EmergencyEvent, at: datetime, by: uuid.UUID | None) -> None:
    e.all_clear_at = at
    e.all_clear_by_user_id = by
    e.status = ES.all_clear
    m = db.get(Muster, e.muster_id) if e.muster_id else None
    if m is not None:
        mu.sync_exits(db, m, at)
        mu.reconcile(db, m)
        mu.close(db, m, at)
    db.flush()


def transition(db: Session, p: Principal, event_id: uuid.UUID, body: EventTransition) -> EventRead:
    e = _event(db, p, event_id)
    before = {"status": e.status.value}
    at = now()
    if body.action == EventAction.all_clear:
        g = ec.need(p, e.project_id, C.emergency_all_clear)
        if not ec.site_in_scope(db, g, e.project_id, e.site_id):
            raise forbidden_error()
        if e.status != ES.active:
            raise invalid_transition("Emergency event", e.status, ES.all_clear)
        when = body.at or at
        if when < e.raised_at or when > at + timedelta(minutes=2):
            raise validation_error("at", "All Clear is between the event time and now.")
        all_clear(db, e, when, p.user.id)
    else:
        p.require(e.project_id, C.emergency_void)
        if e.status not in (ES.active, ES.all_clear):
            raise invalid_transition("Emergency event", e.status, ES.voided)
        e.status_reason = ec.reason(body.reason, 20)
        e.status = ES.voided
        m = db.get(Muster, e.muster_id) if e.muster_id else None
        if m is not None and m.status != MusterStatus.voided:
            m.status = MusterStatus.voided
            m.closed_at = m.closed_at or at
        db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_event, e.id, e.project_id, before,
        {"status": e.status.value, "reason": e.status_reason},
    )  # fmt: skip
    return event_read(db, e)


# ---- review (EV-4, EV-5) -------------------------------------------------------------------------


def review(db: Session, p: Principal, event_id: uuid.UUID, body: EventReviewInput) -> EventRead:
    e = _event(db, p, event_id)
    p.require(e.project_id, C.emergency_all_clear)
    if not ec.is_hse(p, e.project_id):
        raise forbidden_error("Events are reviewed by the HSE Manager or an HSE Officer (EV-5).")
    if e.status != ES.all_clear:
        raise invalid_transition("Emergency event", e.status, ES.reviewed)
    if e.event_type in ref.INCIDENT_REQUIRED and e.incident_id is None:
        raise ec.err(
            422,
            ErrorCode.INCIDENT_LINK_REQUIRED,
            f"{e.event_no}: link the Phase 1 incident before the review (EV-4).",
            "اربط الحادثة قبل مراجعة الحدث.",
            field="incident_id",
        )
    at = now()
    ca_ids: list[str] = []
    if body.create_ca:
        ca = ec.make_ca(
            db, e.project_id, e.id, e.site_id, (e.zone_ids or [])[0] if e.zone_ids else None, None,
            body.ca_title or f"{e.event_no}: review actions",
            body.issues, ec.local_day(at) + timedelta(days=14), p.user.id,
        )  # fmt: skip
        ca_ids.append(str(ca.id))
    if body.erp_update_needed:
        ec.add_review_trigger(db, e.project_id, "event_review", e.event_no)
    e.review = {
        "what_worked": body.what_worked,
        "issues": body.issues,
        "erp_update_needed": body.erp_update_needed,
        "ca_ids": ca_ids,
        "reviewed_by": str(p.user.id),
        "reviewed_at": at.isoformat(),
    }
    e.status = ES.reviewed
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_event, e.id, e.project_id, {"status": "all_clear"},
        {"status": "reviewed"},
    )  # fmt: skip
    return event_read(db, e)


# ---- EV-6: Phase 2 aircraft_emergency ------------------------------------------------------------


def from_ops(db: Session, ops: OpsEvent) -> EmergencyEvent | None:
    if not ec.enabled(db, ops.project_id):
        return None
    zmap = ec.zone_map(db, ops.project_id)
    movement = any(bool(getattr(zmap.get(z), "in_movement_area", False)) for z in ops.zone_ids)
    resp = ResponseType.zone_evacuation if movement else ResponseType.none
    at = now()
    return open_event(
        db, ops.project_id, EventType.airport_aep_activation, ops.site_id,
        list(ops.zone_ids or []), min(ops.started_at, at), resp, ops.declared_by_user_id, at,
        ops_event_id=ops.id, location_en=f"Phase 2 {ops.ops_no}",
    )  # fmt: skip


def end_ops(db: Session, ops: OpsEvent, at: datetime) -> None:
    for e in db.scalars(
        select(EmergencyEvent).where(
            EmergencyEvent.ops_event_id == ops.id, EmergencyEvent.status == ES.active
        )
    ):
        all_clear(db, e, at, None)
