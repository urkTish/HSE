"""Phase 3 read models: live board (§8.4), readiness preview, print (PT-20), closed-permit
pack, shift / suspension lists, project suspension log and incident permit suggestions."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind, QrTokenStatus
from app.core.clock import now
from app.core.enums import AuditAction, EntityType
from app.core.errors import ApiError
from app.core.ptw_enums import (
    PERMIT_TERMINAL,
    ChecklistKind,
    CrewLineStatus,
    PermitAction,
    PermitBlocker,
    PermitStatus,
    PermitType,
    StatusReason,
)
from app.models import (
    AuditEntry,
    GasTest,
    IsolationPoint,
    Lock,
    NotamRequest,
    Permit,
    PermitSuspension,
    Worker,
)
from app.schemas import permits as sch
from app.services.access import common as acommon
from app.services.access.works import in_effect
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal
from app.services.ptw import checks, common, evaluation, lifecycle, views
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

T = PermitType
S = PermitStatus
A = PermitAction
B = PermitBlocker

BOARD_STATUSES = (S.issued, S.active, S.suspended)
START_ACTIONS = {A.issue, A.start, A.revalidate, A.resume, A.handover}
SIGNING_ACTIONS = {
    A.request,
    A.review,
    A.hse_review,
    A.approve,
    A.issue,
    A.revalidate,
    A.resume,
    A.close,
    A.cancel,
    A.handover,
}
ACTION_STATUSES: dict[PermitAction, tuple[PermitStatus, ...]] = {
    A.request: (S.draft,),
    A.return_: (S.requested, S.reviewed),
    A.review: (S.requested,),
    A.hse_review: (S.reviewed,),
    A.approve: (S.reviewed,),
    A.issue: (S.approved,),
    A.start: (S.issued,),
    A.end_shift: (S.active,),
    A.suspend: (S.issued, S.active),
    A.revalidate: (S.suspended,),
    A.resume: (S.suspended,),
    A.request_closure: (S.issued, S.active, S.suspended),
    A.close: (S.issued, S.active, S.suspended),
    A.cancel: (S.draft, S.requested, S.reviewed, S.approved, S.issued, S.suspended),
    A.handover: (S.active,),
    A.lapse_issue: (S.issued,),
    A.expire: (S.approved, S.issued, S.active, S.suspended),
}


def _scope(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    return common.view_grant(db, p, project_id)


def _in_scope(g: Any, permit: Permit) -> bool:
    return acommon.grant_covers(g, [permit.site_id], permit.engagement_id)


# ---- live board ----------------------------------------------------------------------------------


def _window_today(permit: Permit, at: datetime) -> str | None:
    inst = common.current_instance(permit, at) or common.next_instance(permit, at)
    if inst is None:
        return None
    a, b = acommon.local(inst[0]), acommon.local(inst[1])
    if a.date() != acommon.local(at).date():
        return None
    return f"{a.strftime('%H:%M')}–{b.strftime('%H:%M')}"


def board_permit(db: Session, permit: Permit, at: datetime) -> sch.BoardPermit:
    from app.services.ptw import simops  # noqa: PLC0415

    f = facts_mod.compute(db, permit)
    refs = Refs(db)
    shift = evaluation.current_shift(db, permit)
    g = views.gas_state(db, permit, f, at)
    chips = [
        f"{c.rule_code} {c.result.value} {c.status.value}"
        for c in simops.conflicts_of(db, permit.id)
        if c.status.value == "open"
    ]
    waps = views.wap_links(db, permit, f)
    wap_chip = f"{waps[0].wap_no} {waps[0].status.value}" if waps else None
    notam_chip = None
    if waps:
        for nid in waps[0].linked_ntm_ids or []:
            n = db.get(NotamRequest, nid)
            if n is not None:
                notam_chip = f"{n.ntm_no} {'in effect' if in_effect(n, at) else 'not in effect'}"
                break
    eng = refs.eng_required(permit.engagement_id)
    return sch.BoardPermit(
        id=permit.id,
        permit_no=permit.permit_no,
        display_no=common.display_no(permit),
        title=permit.title,
        work_types=[T(t) for t in permit.work_types],
        primary_type=permit.primary_type,
        high_risk=permit.high_risk,
        status=permit.status,
        status_reason=permit.status_reason,
        engagement_code=eng.short_code,
        window_today=_window_today(permit, at),
        in_window_now=common.current_instance(permit, at) is not None,
        shift_no=shift.shift_no if shift else None,
        shift_planned_end_at=shift.planned_end_at if shift else None,
        crew_count=len(evaluation.crew_lines(db, permit.id)),
        crew_present_count=len(shift.crew_present or []) if shift else None,
        gas_status=g.status,
        gas_next_due_at=g.next_due_at,
        simops_chips=chips,
        wap_chip=wap_chip,
        notam_chip=notam_chip,
        blockers=[
            b["code"]
            for b in sorted(permit.blockers or [], key=lambda b: ref.BLOCKER_ORDER[B(b["code"])])
        ],
        persons_inside=len(lifecycle.persons_inside(db, permit.id))
        if T.confined_space.value in permit.work_types
        else None,
        fire_watch_until=lifecycle.fire_watch_until(permit),
    )


def board(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    work_types: list[PermitType] | None = None,
    include_planned_hours: int = 12,
) -> sch.PtwBoardResponse:
    g = _scope(db, p, project_id)
    at = now()
    horizon = at + timedelta(hours=include_planned_hours)
    stmt = select(Permit).where(
        Permit.project_id == project_id,
        Permit.status.in_([*BOARD_STATUSES, S.approved]),
    )
    if site_id:
        stmt = stmt.where(Permit.site_id == site_id)
    if zone_ids:
        stmt = stmt.where(Permit.zone_ids.overlap(list(zone_ids)))
    if work_types:
        stmt = stmt.where(Permit.work_types.overlap([t.value for t in work_types]))
    rows: list[Permit] = []
    for permit in db.scalars(stmt.order_by(Permit.permit_no)):
        if not _in_scope(g, permit):
            continue
        if permit.status == S.approved:
            # planned: an Approved permit whose next window starts within the horizon
            nxt = common.current_instance(permit, at) or common.next_instance(permit, at)
            if include_planned_hours == 0 or nxt is None or nxt[0] > horizon:
                continue
        rows.append(permit)
    counts: dict[PermitStatus, int] = dict.fromkeys(BOARD_STATUSES, 0)
    refs = Refs(db)
    zones: dict[uuid.UUID, list[sch.BoardPermit]] = {}
    for permit in rows:
        if permit.status in counts:
            counts[permit.status] += 1
        item = board_permit(db, permit, at)
        for z in permit.zone_ids or []:
            if zone_ids and z not in zone_ids:
                continue
            zones.setdefault(z, []).append(item)
    out = []
    for zid, items in zones.items():
        zr = refs.zone(zid)
        if zr is not None:
            out.append(sch.BoardZone(zone=zr, permits=items))
    out.sort(key=lambda b: b.zone.code)
    return sch.PtwBoardResponse(project_id=project_id, at=at, zones=out, counts=counts)


# ---- readiness -----------------------------------------------------------------------------------


def _code(fn: Any) -> str | None:
    try:
        fn()
    except ApiError as e:
        return e.code.value
    return None


def readiness(
    db: Session, p: Principal, permit_id: uuid.UUID, action: PermitAction
) -> sch.PermitReadiness:
    permit = common.get_permit(db, p, permit_id)
    at = now()
    errors: list[str] = []
    if permit.status in PERMIT_TERMINAL:
        errors.append("PERMIT_READ_ONLY")
    elif permit.status not in ACTION_STATUSES.get(action, ()):
        errors.append("INVALID_TRANSITION")
    elif action not in views.allowed_actions(db, p, permit) and action not in (
        A.lapse_issue,
        A.expire,
    ):
        errors.append("FORBIDDEN")
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(permit.warnings or [])
    if not errors or errors == ["FORBIDDEN"]:
        nested = db.begin_nested()
        try:
            prev_issuer = permit.issuer_user_id
            if action in (A.approve, A.issue) and prev_issuer is None:
                permit.issuer_user_id = p.user.id
            ctx = evaluation.Ctx(
                at=at, start=action in START_ACTIONS, evaluate_crew=action != A.request
            )
            res = evaluation.evaluate(db, permit, ctx)
            warnings = res.warnings
            if action == A.request:
                blockers = [b for b in res.blockers if B(b["code"]) in lifecycle.REQUEST_CODES]
                c = _code(lambda: checks.for_request(db, permit, at))
                if c:
                    errors.append(c)
            elif action == A.approve:
                blockers = res.approve_rows()
            elif action in START_ACTIONS:
                blockers = list(res.blockers)
            if action in (A.approve, A.issue, A.request, A.revalidate, A.resume):
                c = _code(lambda: lifecycle._contractor_ok(db, permit))
                if c:
                    errors.append(c)
            if action == A.issue:
                for fn in (
                    lambda: lifecycle.receiver_limit(db, permit),
                    lambda: checks.key_roles_busy(db, permit),
                ):
                    c = _code(fn)
                    if c:
                        errors.append(c)
            if action in (A.start, A.revalidate, A.resume, A.handover) and (
                at >= permit.valid_to_at or common.current_instance(permit, at) is None
            ):
                errors.append("OUTSIDE_WINDOW")
            if action == A.start and permit.issued_at is not None:
                s = common.settings(db, permit.project_id)
                if at > permit.issued_at + timedelta(minutes=s.issue_to_start_max_minutes):
                    errors.append("TRANSITION_CONDITION_NOT_MET")
            if action == A.revalidate and permit.status_reason not in lifecycle.REVALIDATE_REASONS:
                errors.append("REVALIDATION_NOT_ALLOWED")
            if action == A.close:
                fw = lifecycle.fire_watch_until(permit)
                if fw is not None and fw > at:
                    errors.append("FIRE_WATCH_RUNNING")
            if action in (A.end_shift, A.close, A.handover) and lifecycle.persons_inside(
                db, permit.id
            ):
                errors.append("ENTRANTS_INSIDE")
        finally:
            nested.rollback()
            db.refresh(permit)
    if action in SIGNING_ACTIONS:
        c = _code(lambda: common.require_reauth(db, p, permit.project_id))
        if c:
            errors.append(c)
    seen: list[str] = []
    for e in errors:
        if e not in seen:
            seen.append(e)
    blockers.sort(key=lambda b: ref.BLOCKER_ORDER[B(b["code"])])
    return sch.PermitReadiness(
        action=action,
        allowed=not blockers and not seen,
        blockers=common.blocker_reads(blockers),
        warnings=common.warning_reads(warnings),
        errors=seen,
    )


# ---- print (PT-20) and closure pack -------------------------------------------------------------


def _qr_payload(db: Session, permit: Permit) -> str:
    t = acommon.active_qr(db, permit.id) or acommon.latest_qr(db, permit.id)
    if t is None or t.kind != QrKind.PT:
        t = acommon.issue_qr(db, QrKind.PT, permit.project_id, permit.id, permit.permit_no)
        if permit.status in PERMIT_TERMINAL:
            t.status = QrTokenStatus.revoked
            t.ended_at = now()
    return acommon.payload(t)


def _latest_gas(db: Session, permit: Permit) -> Any:
    return db.scalar(
        select(GasTest)
        .where(GasTest.permit_id == permit.id, GasTest.superseded.is_(False))
        .order_by(GasTest.tested_at.desc())
        .limit(1)
    )


def _print(db: Session, p: Principal, permit: Permit) -> dict[str, Any]:
    from app.services.ptw import isolations  # noqa: PLC0415

    refs = Refs(db)
    names = views.names_ok(p, permit.project_id)
    zones = [z for z in (refs.zone(z) for z in permit.zone_ids or []) if z is not None]
    crew = []
    for x in evaluation.crew_lines(db, permit.id):
        if x.status == CrewLineStatus.removed:
            continue
        w = db.get(Worker, x.worker_id)
        show = names and w is not None and w.anonymised_at is None
        crew.append(
            sch.PrintCrewLine(
                name_en=w.full_name_en if show and w else None,
                name_ar=w.full_name_ar if show and w else None,
                worker_no=w.worker_no if names and w else None,
                crew_role=x.crew_role,
            )
        )
    isos = []
    for c in isolations.certs_of(db, permit):
        for pt in db.scalars(
            select(IsolationPoint)
            .where(IsolationPoint.certificate_id == c.id)
            .order_by(IsolationPoint.point_no)
        ):
            lk = db.get(Lock, pt.isolation_lock_id) if pt.isolation_lock_id else None
            isos.append(
                sch.PrintIsolationLine(
                    iso_no=c.iso_no,
                    point_no=pt.point_no,
                    device_tag=pt.device_tag,
                    lock_no=lk.lock_no if lk else None,
                    tag_no=pt.tag_no,
                )
            )
    conds = [c for c in (permit.conditions_en, permit.conditions_ar) if c]
    conds += [str(c) for c in permit.copied_conditions or []]
    shift = evaluation.current_shift(db, permit)
    location = permit.location_desc
    if permit.grid_x_m is not None and permit.grid_y_m is not None:
        location += f" · ({permit.grid_x_m}, {permit.grid_y_m})"
    if permit.level_code:
        location += f" · {permit.level_code}"
    receiver = common.user_name(db, permit.receiver_user_id) or ""
    return {
        "permit_no": permit.permit_no,
        "display_no": common.display_no(permit),
        "project_code": common.project_code(db, permit.project_id),
        "status": permit.status,
        "work_types": [T(t) for t in permit.work_types],
        "location": location,
        "zones": [f"{z.code} {z.name_en}" for z in zones],
        "valid_from_at": permit.valid_from_at,
        "valid_to_at": permit.valid_to_at,
        "windows": common.window_reads(permit),
        "current_shift_no": shift.shift_no if shift else None,
        "receiver_name": receiver,
        "issuer_name": common.user_name(db, permit.issuer_user_id),
        "area_authority_name": common.user_name(db, permit.area_authority_user_id),
        "crew": crew,
        "latest_gas_test": views.gas_brief(_latest_gas(db, permit)),
        "isolations": isos,
        "key_conditions": conds,
        "emergency_info": permit.emergency_info or "",
        "qr_payload": _qr_payload(db, permit),
        "printed_ref": permit.permit_no,
        "generated_at": now(),
        "audit_hash": common.permit_hash(permit),
    }


def print_view(db: Session, p: Principal, permit_id: uuid.UUID) -> sch.PermitPrintRead:
    permit = common.get_permit(db, p, permit_id)
    return sch.PermitPrintRead(**_print(db, p, permit))


def closure_pack(db: Session, p: Principal, permit_id: uuid.UUID) -> sch.ClosurePackRead:
    permit = common.get_permit(db, p, permit_id)
    refs = Refs(db)
    names = views.names_ok(p, permit.project_id)
    base = _print(db, p, permit)
    tests = db.scalars(
        select(GasTest).where(GasTest.permit_id == permit.id).order_by(GasTest.tested_at)
    )
    return sch.ClosurePackRead(
        **base,
        shifts=[
            views.shift_read(db, p, s, refs, names) for s in lifecycle.shifts_of(db, permit.id)
        ],
        suspensions=[views.suspension_read(sp, refs) for sp in views.suspensions_of(db, permit.id)],
        gas_tests=[b for b in (views.gas_brief(t) for t in tests) if b is not None],
        signatures=[
            views.signature_read(db, s, refs, names) for s in views.signatures_of(db, permit)
        ],
        closure_checklist=views.checklist_read(db, permit, ChecklistKind.closure, refs),
        closed_at=permit.closed_at,
    )


# ---- shifts / suspensions ------------------------------------------------------------------------


def list_shifts(db: Session, p: Principal, permit_id: uuid.UUID) -> sch.ShiftList:
    permit = common.get_permit(db, p, permit_id)
    refs = Refs(db)
    names = views.names_ok(p, permit.project_id)
    return sch.ShiftList(
        items=[views.shift_read(db, p, s, refs, names) for s in lifecycle.shifts_of(db, permit.id)]
    )


def list_suspensions(db: Session, p: Principal, permit_id: uuid.UUID) -> sch.SuspensionList:
    permit = common.get_permit(db, p, permit_id)
    refs = Refs(db)
    return sch.SuspensionList(
        items=[views.suspension_read(sp, refs) for sp in views.suspensions_of(db, permit.id)]
    )


def project_suspensions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    reasons: list[StatusReason] | None = None,
    work_types: list[PermitType] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    open_only: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> sch.SuspensionPage:
    g = _scope(db, p, project_id)
    stmt = (
        select(PermitSuspension)
        .join(Permit, Permit.id == PermitSuspension.permit_id)
        .where(PermitSuspension.project_id == project_id)
    )
    if reasons:
        stmt = stmt.where(PermitSuspension.reason.in_(list(reasons)))
    if work_types:
        stmt = stmt.where(Permit.work_types.overlap([t.value for t in work_types]))
    if engagement_ids:
        stmt = stmt.where(Permit.engagement_id.in_(list(engagement_ids)))
    if zone_ids:
        stmt = stmt.where(Permit.zone_ids.overlap(list(zone_ids)))
    if open_only:
        stmt = stmt.where(PermitSuspension.resumed_at.is_(None))
    if date_from:
        stmt = stmt.where(PermitSuspension.suspended_at >= acommon.local_midnight_utc(date_from))
    if date_to:
        stmt = stmt.where(
            PermitSuspension.suspended_at < acommon.local_midnight_utc(date_to) + timedelta(days=1)
        )
    if g.site_ids is not None:
        stmt = stmt.where(Permit.site_id.in_(list(g.site_ids)))
    if g.engagement_ids is not None:
        stmt = stmt.where(Permit.engagement_id.in_(list(g.engagement_ids)))
    stmt = stmt.order_by(PermitSuspension.suspended_at.desc(), PermitSuspension.id)
    items, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    out = []
    for sp in items:
        permit = db.get(Permit, sp.permit_id)
        assert permit is not None  # noqa: S101
        base = views.suspension_read(sp, refs).model_dump()
        out.append(
            sch.SuspensionLogItem(
                **base,
                permit=common.permit_ref(permit),
                engagement=refs.eng_required(permit.engagement_id),
                zone_codes=[z.code for z in (refs.zone(z) for z in permit.zone_ids or []) if z],
            )
        )
    return sch.SuspensionPage(items=out, total=total, page=page, page_size=page_size)


# ---- incident suggestions (1-dashboard v1.2) -----------------------------------------------------


def status_at(db: Session, permit: Permit, at: datetime) -> PermitStatus | None:
    row = db.scalar(
        select(AuditEntry)
        .where(
            AuditEntry.entity_type == EntityType.permit,
            AuditEntry.entity_id == permit.id,
            AuditEntry.action == AuditAction.status_change,
            AuditEntry.occurred_at <= at,
        )
        .order_by(AuditEntry.occurred_at.desc(), AuditEntry.seq.desc())
        .limit(1)
    )
    if row is not None and row.after and row.after.get("status"):
        return PermitStatus(row.after["status"])
    # no trail (seeded history): derive from the stored timestamps
    first = permit.first_issued_at or permit.issued_at
    if first is None or first > at:
        return None
    end = permit.closed_at or permit.ended_at
    if end is not None and end <= at:
        return permit.status
    for sp in views.suspensions_of(db, permit.id):
        if sp.suspended_at <= at and (sp.resumed_at is None or sp.resumed_at > at):
            return S.suspended
    if permit.started_at is not None and permit.started_at <= at:
        return S.active
    return S.issued


def incident_suggestions(
    db: Session, p: Principal, incident_id: uuid.UUID
) -> sch.IncidentPermitSuggestions:
    from app.services import incidents  # noqa: PLC0415

    inc = incidents.get_incident(db, p, incident_id)
    g = _scope(db, p, inc.project_id)
    stmt = select(Permit).where(
        Permit.project_id == inc.project_id,
        Permit.site_id == inc.site_id,
        Permit.valid_from_at <= inc.occurred_at,
        Permit.status != S.draft,
    )
    if inc.zone_id is not None:
        stmt = stmt.where(Permit.zone_ids.contains([inc.zone_id]))
    refs = Refs(db)
    out = []
    for permit in db.scalars(stmt.order_by(Permit.permit_no)):
        if not _in_scope(g, permit):
            continue
        st = status_at(db, permit, inc.occurred_at)
        if st not in BOARD_STATUSES:
            continue
        assert st is not None  # noqa: S101
        out.append(
            sch.IncidentPermitSuggestion(
                permit=common.permit_ref(permit),
                zones=[z for z in (refs.zone(z) for z in permit.zone_ids or []) if z is not None],
                status_at_occurrence=st,
            )
        )
    return sch.IncidentPermitSuggestions(items=out)
