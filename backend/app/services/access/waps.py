"""Work-area access permits (WAP) and operational suspension events (spec 2-access-permits
§3.16, §3.17, §4.8, §5.8 WA-1…WA-19, §6.7) and the Phase 3 read `active_waps` (§8.5)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    AreaCategory,
    CredentialAction,
    CredentialReason,
    CrewMemberStatus,
    CrewRole,
    EligibilityContext,
    FodCheckResult,
    GateReasonCode,
    NotamStatus,
    ObstacleStatus,
    OpsEventType,
    QrKind,
    QrTokenStatus,
    ValidityStatus,
    WapBlocker,
    WapStatus,
    WorksImpact,
)
from app.core.clock import now, today
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    NotificationKind,
    Role,
    ZoneStatus,
)
from app.core.errors import ApiError, ErrorCode, field_error, not_found, validation_error
from app.models import (
    Avp,
    NotamRequest,
    ObstacleClearance,
    OpsEvent,
    User,
    Vehicle,
    Wap,
    WapCrew,
    WapVehicle,
    Worker,
    Zone,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.waps import (
    CrewInput,
    CrewMemberRead,
    FodCheckInput,
    FodCheckRead,
    OpsEventCreate,
    OpsEventEnd,
    OpsEventPage,
    OpsEventRead,
    OpsEventUpdate,
    WapBlockerRead,
    WapBoardResponse,
    WapBoardZone,
    WapCreate,
    WapPage,
    WapPrintRead,
    WapRead,
    WapRevisionCreate,
    WapTransitionRequest,
    WapUpdate,
    WapVehicleInput,
    WapVehicleRead,
    WapWindowInstance,
    WapWindowRead,
)
from app.services import attachments, audit, notify, projects
from app.services.access import common, eligibility, lifecycle, profiles, windows
from app.services.access.reasons import BLOCKER_TEXT
from app.services.access.works import covers as ntm_covers
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
WS = WapStatus
B = WapBlocker
G = GateReasonCode
LIVE = (WS.approved, WS.active, WS.suspended)
OPEN = (WS.draft, WS.submitted, *LIVE)
OBS_OK = (ObstacleStatus.approved, ObstacleStatus.approved_with_conditions)
OBS_DEAD = (ObstacleStatus.rejected, ObstacleStatus.withdrawn)

BLOCKER_REASON = {
    B.CONTRACTOR_SUSPENDED: CredentialReason.contractor_suspended,
    B.OPS_SUSPENSION_ACTIVE: CredentialReason.ops_suspension,
}
LVP_TYPES = (OpsEventType.lvp, OpsEventType.dust_sandstorm)
# WA-11 + Appendix A (Tariq is "WAP-0031 supervisor & escort"): a supervisor may escort.
ESCORT_ROLES = (CrewRole.escort, CrewRole.supervisor)


# ---- small lookups -------------------------------------------------------------------------------


def _zones(db: Session, w: Wap) -> list[Zone]:
    return [z for z in (db.get(Zone, i) for i in w.zone_ids or []) if z is not None]


def base_of(w: Wap) -> uuid.UUID:
    return w.revision_of_id or w.id


def crew_rows(db: Session, w: Wap, include_removed: bool = False) -> list[WapCrew]:
    stmt = select(WapCrew).where(WapCrew.wap_id == base_of(w))
    if not include_removed:
        stmt = stmt.where(WapCrew.removed_at.is_(None))
    rows = list(db.scalars(stmt))
    workers = {
        x.id: x
        for x in db.scalars(select(Worker).where(Worker.id.in_([r.worker_id for r in rows])))
    }
    return sorted(
        rows, key=lambda r: workers[r.worker_id].worker_no if r.worker_id in workers else ""
    )


def vehicle_rows(db: Session, w: Wap, include_removed: bool = False) -> list[WapVehicle]:
    stmt = select(WapVehicle).where(WapVehicle.wap_id == base_of(w))
    if not include_removed:
        stmt = stmt.where(WapVehicle.removed_at.is_(None))
    return list(db.scalars(stmt))


def pending_revision(db: Session, w: Wap) -> Wap | None:
    return db.scalar(
        select(Wap).where(Wap.revision_of_id == w.id, Wap.status == WS.submitted).limit(1)
    )


def active_ops(db: Session, zone_ids: list[uuid.UUID], at: datetime) -> list[OpsEvent]:
    if not zone_ids:
        return []
    return list(
        db.scalars(
            select(OpsEvent).where(
                OpsEvent.zone_ids.overlap(zone_ids),
                OpsEvent.started_at <= at,
                or_(OpsEvent.ended_at.is_(None), OpsEvent.ended_at > at),
            )
        )
    )


def remaining_instances(w: Wap, at: datetime) -> list[windows.Instance]:
    d = common.local_day(at)
    return [
        i
        for i in windows.instances(
            windows.parse(w.windows), w.valid_from, w.valid_to, d - timedelta(days=1), w.valid_to
        )
        if i.end_utc > at
    ]


def _remaining_days(w: Wap, at: datetime) -> list[date]:
    d = max(common.local_day(at), w.valid_from)
    out = []
    while d <= w.valid_to:
        out.append(d)
        d += timedelta(days=1)
    return out


# ---- crew and vehicle evaluation (WA-10, WA-11, WA-12) ------------------------------------------


@dataclass
class _Member:
    row: WapCrew
    reasons: list[GateReasonCode]
    escorted: bool


def _avp_status(db: Session, vehicle_id: uuid.UUID, need: str, d: date) -> GateReasonCode | None:
    avps = list(
        db.scalars(
            select(Avp).where(
                Avp.vehicle_id == vehicle_id,
                Avp.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
            )
        )
    )
    valid = [a for a in avps if lifecycle.live_valid(a, d)]
    if any(any(profiles.covers(x, need) for x in a.areas or []) for a in valid):
        return None
    if valid:
        return G.AVP_AREA
    if any(a.validity_status == ValidityStatus.suspended for a in avps):
        return G.AVP_SUSPENDED
    return G.AVP_MISSING


def evaluate_crew(
    db: Session, w: Wap, at: datetime | None = None, notify_changes: bool = True
) -> None:
    """WA-10/11/12: evaluate every crew member and vehicle; auto-exclude / re-include."""
    at = at or now()
    d = common.local_day(at)
    zones = _zones(db, w)
    s = common.settings(db, w.project_id)
    profs = {z.id: profiles.ensure(db, z) for z in zones}
    rows = crew_rows(db, w)
    members: dict[uuid.UUID, _Member] = {}
    for r in rows:
        worker = db.get(Worker, r.worker_id)
        if worker is None:
            continue
        reasons: list[GateReasonCode] = []
        escorted = False
        for z in zones:
            ev = eligibility.evaluate(
                db, worker, z, at, EligibilityContext.wap,
                escort_ok=True, crew_role=r.crew_role.value, with_wap=False,
            )  # fmt: skip
            escorted = escorted or ev.escort_required
            reasons += [x for x in ev.deny_except_escort() if x not in reasons]
            need = profs[z.id].adp_category_required
            if r.crew_role == CrewRole.driver and need is not None:
                it, _ = eligibility.adp_item(db, worker.id, w.project_id, need.value, d)
                if it.reason and it.reason not in reasons and it.status.value == "not_met":
                    reasons.append(it.reason)
        members[r.worker_id] = _Member(r, reasons, escorted)
    # WA-11 escorts
    per_escort: dict[uuid.UUID, int] = {}
    ratio = min(
        [
            profs[z.id].escort_ratio_max or profiles.setting_ratio(s, profiles.area_category(z))
            for z in zones
        ]
        or [s.escort_ratio_max_other]
    )
    for m in members.values():
        if not m.escorted:
            continue
        esc = members.get(m.row.escort_worker_id) if m.row.escort_worker_id else None
        if esc is None or esc.row.crew_role not in ESCORT_ROLES:
            m.reasons.append(G.ESCORT_REQUIRED)
            continue
        if (
            esc.escorted
            or esc.reasons
            or not _escort_qualified(db, w, esc.row.worker_id, zones, profs, d)
        ):
            m.reasons.append(G.ESCORT_INVALID)
            continue
        per_escort[esc.row.worker_id] = per_escort.get(esc.row.worker_id, 0) + 1
        if per_escort[esc.row.worker_id] > ratio:
            m.reasons.append(G.ESCORT_RATIO_EXCEEDED)
    excluded_now: list[WapCrew] = []
    for m in members.values():
        r = m.row
        r.escorted = m.escorted
        r.eligible_now = not m.reasons
        r.evaluated_at = at
        r.exclusion_reasons = [x.value for x in m.reasons]
        if r.crew_role == CrewRole.supervisor:
            r.status = CrewMemberStatus.included  # blocker SUPERVISOR_INELIGIBLE instead
            continue
        if m.reasons and r.status != CrewMemberStatus.excluded:
            r.status = CrewMemberStatus.excluded
            excluded_now.append(r)
        elif not m.reasons and r.status == CrewMemberStatus.excluded:
            r.status = CrewMemberStatus.included
    _evaluate_vehicles(db, w, zones, profs, s, d)
    db.flush()
    if excluded_now and notify_changes and w.status not in (WS.draft,):
        users = {w.requested_by_user_id, *contractor_reps(db, w.project_id, w.engagement_id)}
        nos = ", ".join(
            x.worker_no for x in (db.get(Worker, r.worker_id) for r in excluded_now) if x
        )
        notify.notify(
            db, users, NotificationKind.wap_crew_excluded,
            f"{w.wap_no}: crew excluded ({nos})", f"{w.wap_no}: استبعاد من الطاقم ({nos})",
            None, None, EntityType.wap, w.id, w.project_id,
        )  # fmt: skip


def _escort_qualified(
    db: Session,
    w: Wap,
    worker_id: uuid.UUID,
    zones: list[Zone],
    profs: dict[uuid.UUID, Any],
    d: date,
) -> bool:
    for z in zones:
        area = profs[z.id].airport_pass_area_code
        if area:
            _it, ps = eligibility.pass_item(db, worker_id, w.project_id, area, d)
            if ps is None or ps.escorted:
                return False
        if profiles.area_category(z) == AreaCategory.manoeuvring:
            _it, adp = eligibility.adp_item(db, worker_id, w.project_id, "manoeuvring", d)
            if adp is None:
                return False
    return True


def _evaluate_vehicles(
    db: Session, w: Wap, zones: list[Zone], profs: dict[uuid.UUID, Any], s: Any, d: date
) -> None:
    rows = vehicle_rows(db, w)
    own: dict[uuid.UUID, list[GateReasonCode]] = {}
    for r in rows:
        reasons: list[GateReasonCode] = []
        for z in zones:
            need = profs[z.id].avp_area_required
            if need is None:
                continue
            code = _avp_status(db, r.vehicle_id, need.value, d)
            if code is not None and code not in reasons:
                reasons.append(code)
        own[r.vehicle_id] = reasons
    escorted_count: dict[uuid.UUID, int] = {}
    cats = [profs[z.id].avp_area_required for z in zones if profs[z.id].avp_area_required]
    ratio = (
        s.vehicle_escort_ratio_max_manoeuvring
        if AreaCategory.manoeuvring in cats
        else s.vehicle_escort_ratio_max_apron
    )
    for r in rows:
        reasons = own[r.vehicle_id]
        if reasons and r.escort_vehicle_id is not None and own.get(r.escort_vehicle_id) == []:
            escorted_count[r.escort_vehicle_id] = escorted_count.get(r.escort_vehicle_id, 0) + 1
            reasons = (
                [G.ESCORT_RATIO_EXCEEDED] if escorted_count[r.escort_vehicle_id] > ratio else []
            )
        v = db.get(Vehicle, r.vehicle_id)
        if v is not None and v.status.value != "active" and G.AVP_MISSING not in reasons:
            reasons.append(G.AVP_MISSING)
        r.exclusion_reasons = [x.value for x in reasons]
        r.status = CrewMemberStatus.excluded if reasons else CrewMemberStatus.included


# ---- blockers (WA-13) ----------------------------------------------------------------------------


def _blk(code: WapBlocker, ref: str | None = None) -> dict[str, Any]:
    return {"code": code.value, "ref": ref}


def compute_blockers(db: Session, w: Wap, at: datetime | None = None) -> list[dict[str, Any]]:
    at = at or now()
    zones = _zones(db, w)
    out: list[dict[str, Any]] = []

    def add(code: WapBlocker, ref: str | None = None) -> None:
        if all(b["code"] != code.value for b in out):
            out.append(_blk(code, ref))

    ntms = [n for n in (db.get(NotamRequest, i) for i in w.linked_ntm_ids or []) if n]
    inst = remaining_instances(w, at)
    for z in zones:
        prof = profiles.ensure(db, z)
        if z.notam_required_for_works:
            mine = [n for n in ntms if z.id in (n.zone_ids or [])] or ntms
            issued = [n for n in mine if n.status == NotamStatus.issued]
            if not issued:
                add(B.NOTAM_NOT_ISSUED, mine[0].ntm_no if mine else None)
            else:
                for i in inst:
                    if not any(ntm_covers(n, i.start_utc, i.end_utc) for n in issued):
                        add(B.NOTAM_NOT_COVERING_WINDOW, f"{i.local_date.isoformat()} {i.label}")
                        break
        if prof.ils_outage_notam_required and not any(
            WorksImpact.ils_outage.value in (n.works_impact or [])
            and n.status not in (NotamStatus.rejected, NotamStatus.cancelled, NotamStatus.expired)
            for n in ntms
        ):
            add(B.ILS_OUTAGE_NOTAM_REQUIRED, z.code)
        if z.in_movement_area and not w.works_safety_plan_ref:
            add(B.WSP_REQUIRED, z.code)
    _height_blockers(db, w, zones, at, add)
    crew = crew_rows(db, w)
    sup = [c for c in crew if c.worker_id == w.supervisor_worker_id]
    if sup and sup[0].eligible_now is False:
        add(B.SUPERVISOR_INELIGIBLE)
    evaluated = [c for c in crew if c.evaluated_at is not None]
    if evaluated and not any(
        c.status == CrewMemberStatus.included and c.eligible_now for c in evaluated
    ):
        add(B.NO_ELIGIBLE_CREW)
    con = common.engagement_contractor(db, w.engagement_id)
    if con is not None and con.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        add(B.CONTRACTOR_SUSPENDED, con.short_code)
    ops = active_ops(db, list(w.zone_ids or []), at)
    if ops:
        add(B.OPS_SUSPENSION_ACTIVE, ops[0].ops_no)
    return out


def _height_blockers(db: Session, w: Wap, zones: list[Zone], at: datetime, add: Any) -> None:
    """WA-8 / OB-6 / VP-7."""
    obs = [o for o in (db.get(ObstacleClearance, i) for i in w.linked_obs_ids or []) if o]
    days = _remaining_days(w, at)
    d0 = common.local_day(at)
    for o in obs:
        if o.status == ObstacleStatus.suspended:
            add(B.OBS_NOT_ACTIVE, o.obs_no)
    for r in vehicle_rows(db, w):
        v = db.get(Vehicle, r.vehicle_id)
        if v is None:
            continue
        h = (
            r.height_limited_to_m
            if r.height_limited_to_m is not None
            else v.max_working_height_m_agl
        )
        for z in zones:
            zmax = z.max_equipment_height_m_agl
            if zmax is None or Decimal(h) <= Decimal(str(zmax)):
                continue
            cands = [
                o for o in obs
                if o.vehicle_id == v.id and o.zone_id == z.id and o.status not in OBS_DEAD
            ]  # fmt: skip
            good = [
                o
                for o in cands
                if o.approved_max_height_m_agl is not None
                and Decimal(h) <= o.approved_max_height_m_agl
                and o.valid_from is not None
                and o.valid_to is not None
                and all(o.valid_from <= d <= o.valid_to for d in days)
                and o.status in (*OBS_OK, ObstacleStatus.suspended)
            ]
            if not good:
                add(B.HEIGHT_CLEARANCE_REQUIRED, v.vehicle_no)
            elif w.valid_from <= d0 and not any(
                o.status in OBS_OK and o.valid_from is not None and o.valid_from <= d0 for o in good
            ):
                add(B.OBS_NOT_ACTIVE, good[0].obs_no)


# ---- status reactions ----------------------------------------------------------------------------


def _wap_users(db: Session, w: Wap, officers: bool = False) -> set[uuid.UUID]:
    users = {w.requested_by_user_id, *contractor_reps(db, w.project_id, w.engagement_id)}
    if w.approved_by_user_id:
        users.add(w.approved_by_user_id)
    if officers:
        users.update(notify.users_with_role(db, Role.hse_officer, [w.project_id]))
    return users


def _audit_status(
    db: Session, w: Wap, frm: WapStatus, actor: Any = None, reason: str | None = None
) -> None:
    audit.record(
        db,
        AuditAction.status_change,
        *([actor] if actor is not None else []),
        entity_type=EntityType.wap,
        entity_id=w.id,
        project_id=w.project_id,
        before={"status": frm.value},
        after={"status": w.status.value, **({"reason": reason} if reason else {})},
    )


def _suspend(
    db: Session,
    w: Wap,
    reason: CredentialReason,
    text: str | None,
    actor_id: uuid.UUID | None = None,
    audit_actor: Any = None,
) -> None:
    frm = w.status
    w.status = WS.suspended
    w.suspension_reason = reason
    w.status_reason = text
    w.updated_at = now()
    action = CredentialAction.suspend_confirmed if actor_id else CredentialAction.auto_suspended
    lifecycle.event(db, w, action, reason, text, actor_id)
    db.flush()
    _audit_status(db, w, frm, audit_actor, text or reason.value)
    notify.notify(
        db, _wap_users(db, w, officers=True), NotificationKind.wap_suspended,
        f"{w.wap_no}: suspended ({reason.value})", f"{w.wap_no}: تم إيقاف التصريح",
        text, text, EntityType.wap, w.id, w.project_id,
    )  # fmt: skip


def _activate(db: Session, w: Wap, at: datetime) -> None:
    frm = w.status
    w.status = WS.active
    w.activated_at = w.activated_at or at
    w.suspension_reason = None
    w.updated_at = at
    if common.active_qr(db, w.id) is None:
        common.issue_qr(db, QrKind.WP, w.project_id, w.id, w.wap_no)
    db.flush()
    _audit_status(db, w, frm)


def _end(db: Session, w: Wap, to: WapStatus, at: datetime) -> None:
    w.status = to
    if to == WS.closed:
        w.closed_at = at
    w.updated_at = at
    common.end_qr(db, w.id, QrTokenStatus.revoked)
    db.flush()


def _blocked_alert(db: Session, w: Wap, key: str) -> None:
    if key in (w.alerts_sent or []):
        return
    w.alerts_sent = [*(w.alerts_sent or []), key]
    codes = ", ".join(b["code"] for b in w.blockers or [])
    notify.notify(
        db, _wap_users(db, w), NotificationKind.wap_blocked,
        f"{w.wap_no}: approved but blocked ({codes})", f"{w.wap_no}: معتمد لكنه معطل ({codes})",
        None, None, EntityType.wap, w.id, w.project_id,
    )  # fmt: skip


def refresh(db: Session, w: Wap, at: datetime | None = None, evaluate: bool = False) -> None:
    """Recompute blockers; activate an Approved WAP inside validity without blockers and
    suspend an Active WAP that gained a blocker (WA-13, NT-5, OB-7, WA-3, WA-15)."""
    at = at or now()
    if evaluate:
        evaluate_crew(db, w, at)
    w.blockers = compute_blockers(db, w, at)
    if w.revision_of_id is not None:
        db.flush()
        return
    d = common.local_day(at)
    codes = [WapBlocker(b["code"]) for b in w.blockers]
    if w.status == WS.active and codes:
        reason = next(
            (BLOCKER_REASON[c] for c in codes if c in BLOCKER_REASON),
            CredentialReason.dependency_invalid,
        )
        _suspend(db, w, reason, ", ".join(c.value for c in codes))
    elif w.status == WS.approved and w.valid_from <= d <= w.valid_to:
        if not codes:
            _activate(db, w, at)
        else:
            _blocked_alert(db, w, f"blocked:{d.isoformat()}")
    db.flush()


# ---- reads ---------------------------------------------------------------------------------------


def _window_reads(w: Wap) -> list[WapWindowRead]:
    return [
        WapWindowRead(
            start_local=x.start,
            end_local=x.end,
            weekdays=[k for k, v in windows.PY_WEEKDAY.items() if v in x.weekdays],
            crosses_midnight=x.crosses_midnight,
        )
        for x in windows.parse(w.windows)
    ]


def _inst(i: windows.Instance | None) -> WapWindowInstance | None:
    if i is None:
        return None
    return WapWindowInstance(local_date=i.local_date, start_utc=i.start_utc, end_utc=i.end_utc)


def _fod_read(db: Session, refs: Refs, f: dict[str, Any] | None) -> FodCheckRead | None:
    if not f:
        return None
    wk = (
        db.get(Worker, uuid.UUID(f["checked_by_worker_id"]))
        if f.get("checked_by_worker_id")
        else None
    )
    return FodCheckRead(
        checked_by_worker=common.worker_ref(wk, True) if wk else None,
        checked_by_user=refs.user(uuid.UUID(f["checked_by_user_id"]))
        if f.get("checked_by_user_id")
        else None,
        checked_at=datetime.fromisoformat(f["checked_at"]),
        result=FodCheckResult(f["result"]),
    )


def _blocker_reads(blockers: list[dict[str, Any]]) -> list[WapBlockerRead]:
    out = []
    for b in blockers:
        code = WapBlocker(b["code"])
        en, ar = BLOCKER_TEXT[code]
        out.append(WapBlockerRead(code=code, detail_en=en, detail_ar=ar, ref=b.get("ref")))
    return out


def wap_read(
    db: Session,
    p: Principal | None,
    w: Wap,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
    live: bool = True,
) -> WapRead:
    refs = refs or Refs(db)
    names = common.can_see_names(p, w.project_id)
    at = now()
    blockers = compute_blockers(db, w, at) if live and w.status in OPEN else (w.blockers or [])
    defs = windows.parse(w.windows)
    crew = crew_rows(db, w)
    vehicles = vehicle_rows(db, w)
    sup = db.get(Worker, w.supervisor_worker_id)
    crew_reads: list[CrewMemberRead] = []
    veh_reads: list[WapVehicleRead] = []
    if names:
        for c in crew:
            wk = db.get(Worker, c.worker_id)
            if wk is None:
                continue
            crew_reads.append(
                CrewMemberRead(
                    worker=common.worker_ref(wk, True),
                    crew_role=c.crew_role,
                    escort_worker_id=c.escort_worker_id,
                    status=c.status,
                    exclusion_reasons=[GateReasonCode(x) for x in c.exclusion_reasons or []],
                    escorted=c.escorted,
                    eligible_now=c.eligible_now,
                    evaluated_at=c.evaluated_at,
                )
            )
        for r in vehicles:
            v = db.get(Vehicle, r.vehicle_id)
            if v is None:
                continue
            avp = db.scalar(
                select(Avp.avp_no).where(
                    Avp.vehicle_id == v.id,
                    Avp.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
                )
            )
            veh_reads.append(
                WapVehicleRead(
                    vehicle=common.vehicle_ref(v),
                    escort_vehicle_id=r.escort_vehicle_id,
                    height_limited_to_m=r.height_limited_to_m,
                    avp_no=avp,
                    status=r.status,
                    exclusion_reasons=[GateReasonCode(x) for x in r.exclusion_reasons or []],
                )
            )
    pend = pending_revision(db, w) if w.revision_of_id is None else None
    return WapRead(
        id=w.id,
        wap_no=w.wap_no,
        revision_no=w.revision_no,
        revision_of_id=w.revision_of_id,
        pending_revision_id=pend.id if pend else None,
        project_id=w.project_id,
        site=refs.site(w.site_id),
        zones=[z for z in (refs.zone(x) for x in w.zone_ids or []) if z is not None],
        engagement=refs.eng_required(w.engagement_id),
        requested_by=refs.user(w.requested_by_user_id) or attachments.UNKNOWN,
        supervisor=common.worker_ref(sup, True) if sup and names else None,
        scope_en=w.scope_en,
        scope_ar=w.scope_ar,
        works_safety_plan_ref=w.works_safety_plan_ref,
        valid_from=w.valid_from,
        valid_to=w.valid_to,
        windows=_window_reads(w),
        current_window=_inst(windows.current(defs, w.valid_from, w.valid_to, at)),
        next_window=_inst(windows.upcoming(defs, w.valid_from, w.valid_to, at)),
        crew_count=len(crew),
        vehicle_count=len(vehicles),
        crew=crew_reads,
        vehicles=veh_reads,
        operator_permit_ref=w.operator_permit_ref,
        linked_ntm_ids=list(w.linked_ntm_ids or []),
        linked_obs_ids=list(w.linked_obs_ids or []),
        fod_handback_required=w.fod_handback_required,
        fod_check=_fod_read(db, refs, w.fod_check),
        conditions_en=w.conditions_en,
        conditions_ar=w.conditions_ar,
        approved_by=refs.user(w.approved_by_user_id),
        approved_at=w.approved_at,
        blockers=_blocker_reads(blockers),
        suspension_reason=w.suspension_reason,
        status=w.status,
        warnings=warnings or [],
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


def _view(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, C.access_works_view)
    if g is None:
        raise forbidden_error()
    return g


def get_wap_row(db: Session, p: Principal, wap_id: uuid.UUID) -> Wap:
    w = db.get(Wap, wap_id)
    if w is None:
        raise not_found("Work-area permit")
    g = _view(db, p, w.project_id)
    if not common.grant_covers(g, [w.site_id], w.engagement_id):
        raise forbidden_error("This record is outside your scope.")
    return w


def read_wap(db: Session, p: Principal, wap_id: uuid.UUID) -> WapRead:
    return wap_read(db, p, get_wap_row(db, p, wap_id))


def list_waps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[WapStatus] | None = None,
    site_id: uuid.UUID | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    active_on: date | None = None,
    blocked: bool | None = None,
    blocker: WapBlocker | None = None,
    worker_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    q: str | None = None,
) -> WapPage:
    project = projects.get_visible(db, p, project_id)
    g = _view(db, p, project.id)
    stmt = select(Wap).where(Wap.project_id == project.id, Wap.revision_of_id.is_(None))
    if g.engagement_ids is not None:
        stmt = stmt.where(Wap.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        stmt = stmt.where(Wap.site_id.in_(list(g.site_ids)))
    if statuses:
        stmt = stmt.where(Wap.status.in_(statuses))
    if site_id:
        stmt = stmt.where(Wap.site_id == site_id)
    if zone_ids:
        stmt = stmt.where(Wap.zone_ids.overlap(zone_ids))
    if engagement_ids:
        engs = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                engs.update(engagement_descendants(db, e))
        stmt = stmt.where(Wap.engagement_id.in_(list(engs)))
    if active_on:
        stmt = stmt.where(
            Wap.valid_from <= active_on, Wap.valid_to >= active_on, Wap.status.in_(LIVE)
        )
    if blocked:
        d = today()
        stmt = stmt.where(Wap.status == WS.approved, Wap.valid_from <= d, Wap.valid_to >= d)
    if worker_id:
        stmt = stmt.where(
            Wap.id.in_(
                select(WapCrew.wap_id).where(
                    WapCrew.worker_id == worker_id, WapCrew.removed_at.is_(None)
                )
            )
        )
    if vehicle_id:
        stmt = stmt.where(
            Wap.id.in_(
                select(WapVehicle.wap_id).where(
                    WapVehicle.vehicle_id == vehicle_id, WapVehicle.removed_at.is_(None)
                )
            )
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Wap.wap_no.ilike(like), Wap.scope_en.ilike(like), Wap.scope_ar.ilike(like))
        )
    stmt = stmt.order_by(Wap.valid_from.desc(), Wap.wap_no.desc())
    rows: list[Wap] | Any
    if blocker is not None:
        rows = [
            w
            for w in db.scalars(stmt)
            if w.status in OPEN and any(b["code"] == blocker.value for b in compute_blockers(db, w))
        ]
        total = len(rows)
        rows = rows[(page - 1) * page_size : page * page_size]
    else:
        rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(
        sites=[w.site_id for w in rows],
        zones=[z for w in rows for z in w.zone_ids or []],
        engs=[w.engagement_id for w in rows],
        users=[u for w in rows for u in (w.requested_by_user_id, w.approved_by_user_id)],
    )
    return WapPage(
        items=[wap_read(db, p, w, refs) for w in rows], total=total, page=page, page_size=page_size
    )


# ---- validation ----------------------------------------------------------------------------------


def _check_zones(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[Zone]:
    out = []
    for zid in dict.fromkeys(ids):
        z = db.get(Zone, zid)
        if z is None or z.project_id != project_id:
            raise validation_error("zone_ids", "Choose zones of this project.")
        if z.site_id != site_id:
            raise validation_error("zone_ids", "All zones must belong to the WAP's site (WA-2).")
        if z.status != ZoneStatus.active:
            raise validation_error("zone_ids", f"Zone {z.code} is archived.")
        out.append(z)
    return out


def _crew_invalid(msg: str, msg_ar: str, field: str = "crew") -> ApiError:
    return ApiError(
        422, ErrorCode.CREW_INVALID, msg, msg_ar, errors=[field_error(field, msg, "CREW_INVALID")]
    )


def _check_member(db: Session, w: Wap, c: CrewInput, field: str) -> Worker:
    wk = db.get(Worker, c.worker_id)
    if wk is None:
        raise validation_error(f"{field}.worker_id", "Unknown worker.")
    dep = eligibility.current_deployment(db, wk.id, w.project_id)
    if dep is None:
        raise _crew_invalid(
            f"{wk.worker_no} is not deployed on this project.",
            f"العامل {wk.worker_no} غير معيّن في هذا المشروع.", f"{field}.worker_id",
        )  # fmt: skip
    if dep.engagement_id not in common.engagement_ancestors(db, w.engagement_id):
        raise _crew_invalid(
            f"{wk.worker_no} is not employed by the WAP's contractor or its parent (WA-2).",
            f"العامل {wk.worker_no} لا يتبع مقاول التصريح.", f"{field}.worker_id",
        )  # fmt: skip
    if w.site_id not in (dep.site_ids or []):
        raise _crew_invalid(
            f"{wk.worker_no}'s deployment does not cover the WAP's site (WA-2).",
            f"تعيين العامل {wk.worker_no} لا يشمل موقع التصريح.", f"{field}.worker_id",
        )  # fmt: skip
    return wk


def _check_crew(db: Session, w: Wap, crew: list[CrewInput]) -> None:
    ids = [c.worker_id for c in crew]
    if len(set(ids)) != len(ids):
        raise _crew_invalid("A worker is listed twice.", "تم إدراج عامل مرتين.")
    for i, c in enumerate(crew):
        _check_member(db, w, c, f"crew.{i}")
        if c.escort_worker_id is not None:
            esc = next((x for x in crew if x.worker_id == c.escort_worker_id), None)
            if esc is None or esc.crew_role not in ESCORT_ROLES or esc.worker_id == c.worker_id:
                raise _crew_invalid(
                    "The escort must be a crew member with role escort or supervisor (WA-11).",
                    "يجب أن يكون المرافق عضوًا في الطاقم بدور مرافق.", f"crew.{i}.escort_worker_id",
                )  # fmt: skip
    sup = next((c for c in crew if c.worker_id == w.supervisor_worker_id), None)
    if sup is None or sup.crew_role != CrewRole.supervisor:
        raise _crew_invalid(
            "The supervisor must be listed in the crew with role supervisor.",
            "يجب إدراج المشرف في الطاقم بدور مشرف.", "supervisor_worker_id",
        )  # fmt: skip


def _check_vehicle(db: Session, w: Wap, v_in: WapVehicleInput, field: str) -> Vehicle:
    v = db.get(Vehicle, v_in.vehicle_id)
    if v is None or v.project_id != w.project_id:
        raise validation_error(f"{field}.vehicle_id", "Choose a vehicle of this project.")
    if (
        v_in.height_limited_to_m is not None
        and v_in.height_limited_to_m > v.max_working_height_m_agl
    ):
        raise validation_error(
            f"{field}.height_limited_to_m",
            "The limited height cannot exceed the vehicle's maximum working height.",
        )
    return v


def _check_vehicles(db: Session, w: Wap, vehicles: list[WapVehicleInput]) -> None:
    ids = [v.vehicle_id for v in vehicles]
    if len(set(ids)) != len(ids):
        raise validation_error("vehicles", "A vehicle is listed twice.")
    for i, v in enumerate(vehicles):
        _check_vehicle(db, w, v, f"vehicles.{i}")
        if v.escort_vehicle_id is not None and (
            v.escort_vehicle_id not in ids or v.escort_vehicle_id == v.vehicle_id
        ):
            raise validation_error(
                f"vehicles.{i}.escort_vehicle_id", "The escort vehicle must be listed on the WAP."
            )


def _check_links(db: Session, w: Wap, ntm_ids: list[uuid.UUID], obs_ids: list[uuid.UUID]) -> None:
    for i, nid in enumerate(ntm_ids):
        n = db.get(NotamRequest, nid)
        if n is None or n.project_id != w.project_id:
            raise validation_error(f"linked_ntm_ids.{i}", "Unknown NOTAM record.")
    for i, oid in enumerate(obs_ids):
        o = db.get(ObstacleClearance, oid)
        if o is None or o.project_id != w.project_id:
            raise validation_error(f"linked_obs_ids.{i}", "Unknown obstacle clearance.")
        if o.status in OBS_DEAD:
            raise ApiError(
                422, ErrorCode.CLEARANCE_NOT_LINKABLE,
                f"{o.obs_no} is {o.status.value} and cannot be linked (OB-8).",
                f"لا يمكن ربط {o.obs_no} لأنه مرفوض أو مسحوب.",
                errors=[field_error(f"linked_obs_ids.{i}", "Not linkable.", "NOT_LINKABLE")],
            )  # fmt: skip


def _contractor_ok(db: Session, engagement_id: uuid.UUID) -> None:
    con = common.engagement_contractor(db, engagement_id)
    if con is not None and con.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        raise ApiError(
            403, ErrorCode.CONTRACTOR_SUSPENDED,
            f"{con.short_code} is {con.status.value}; WAPs cannot be submitted (WA-3).",
            f"المقاول {con.short_code} موقوف أو محظور.",
        )  # fmt: skip


def _check_dates(db: Session, w: Wap, submit: bool) -> None:
    s = common.settings(db, w.project_id)
    if w.valid_to < w.valid_from:
        raise validation_error("valid_to", "valid_to must be on or after valid_from.")
    if (w.valid_to - w.valid_from).days + 1 > s.wap_max_days:
        raise ApiError(
            422, ErrorCode.WAP_DURATION_EXCEEDED,
            f"A WAP may cover at most {s.wap_max_days} days (WA-5).",
            f"لا يتجاوز التصريح {s.wap_max_days} يومًا.",
            errors=[field_error("valid_to", "Too long.", "WAP_DURATION_EXCEEDED")],
            meta={"wap_max_days": s.wap_max_days},
        )  # fmt: skip
    if submit and w.valid_from < today():
        raise validation_error(
            "valid_from", "valid_from cannot be in the past at submission (WA-5)."
        )


def _check_wsp(db: Session, w: Wap) -> None:
    if any(z.in_movement_area for z in _zones(db, w)) and not w.works_safety_plan_ref:
        raise ApiError(
            422, ErrorCode.WSP_REQUIRED,
            "A works safety plan reference is required for movement-area zones (WA-6).",
            "يلزم مرجع خطة سلامة الأعمال لمناطق الحركة.",
            errors=[field_error("works_safety_plan_ref", "Required.", "WSP_REQUIRED")],
        )  # fmt: skip


def _snapshot(w: Wap) -> dict[str, Any]:
    return common.jsonable(
        {
            k: getattr(w, k)
            for k in (
                "wap_no", "revision_no", "zone_ids", "engagement_id", "supervisor_worker_id",
                "works_safety_plan_ref", "valid_from", "valid_to", "windows", "linked_ntm_ids",
                "linked_obs_ids", "operator_permit_ref", "status",
            )
        }
    )  # fmt: skip


def _set_crew(db: Session, w: Wap, crew: list[CrewInput]) -> None:
    for r in crew_rows(db, w, include_removed=True):
        db.delete(r)
    db.flush()
    for c in crew:
        db.add(
            WapCrew(
                id=uuid.uuid4(), wap_id=w.id, worker_id=c.worker_id, crew_role=c.crew_role,
                escort_worker_id=c.escort_worker_id, status=CrewMemberStatus.included,
                exclusion_reasons=[], escorted=False,
            )
        )  # fmt: skip


def _set_vehicles(db: Session, w: Wap, vehicles: list[WapVehicleInput]) -> None:
    for r in vehicle_rows(db, w, include_removed=True):
        db.delete(r)
    db.flush()
    for v in vehicles:
        db.add(
            WapVehicle(
                id=uuid.uuid4(), wap_id=w.id, vehicle_id=v.vehicle_id,
                escort_vehicle_id=v.escort_vehicle_id, height_limited_to_m=v.height_limited_to_m,
                status=CrewMemberStatus.included, exclusion_reasons=[],
            )
        )  # fmt: skip


def _derive(db: Session, w: Wap, zones: list[Zone]) -> None:
    w.fod_handback_required = any(bool(z.fod_control_required) for z in zones)
    if not w.works_safety_plan_ref:
        w.works_safety_plan_ref = next(
            (z.works_safety_plan_ref for z in zones if z.works_safety_plan_ref), None
        )


# ---- create / update -----------------------------------------------------------------------------


def create_wap(db: Session, p: Principal, project_id: uuid.UUID, body: WapCreate) -> WapRead:
    project = projects.get_visible(db, p, project_id)
    zones = _check_zones(db, project.id, body.site_id, body.zone_ids)
    common.require_cap(p, project.id, C.wap_edit, [body.site_id], body.engagement_id)
    eng = Refs(db).eng(body.engagement_id)
    if eng is None:
        raise validation_error("engagement_id", "Unknown engagement.")
    _contractor_ok(db, body.engagement_id)
    year = today().year
    seq = next_seq(db, Wap, project.id, year)
    w = Wap(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        wap_no=make_ref("WAP", project.code, year, seq, 4),
        revision_no=0,
        project_id=project.id,
        site_id=body.site_id,
        zone_ids=[z.id for z in zones],
        engagement_id=body.engagement_id,
        requested_by_user_id=p.user.id,
        supervisor_worker_id=body.supervisor_worker_id,
        scope_en=body.scope_en,
        scope_ar=body.scope_ar,
        works_safety_plan_ref=body.works_safety_plan_ref,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        windows=windows.dump(body.windows),
        operator_permit_ref=body.operator_permit_ref,
        linked_ntm_ids=list(dict.fromkeys(body.linked_ntm_ids)),
        linked_obs_ids=list(dict.fromkeys(body.linked_obs_ids)),
        conditions_en=body.conditions_en,
        conditions_ar=body.conditions_ar,
        blockers=[],
        alerts_sent=[],
        status=WS.draft,
        created_by_user_id=p.user.id,
    )
    _derive(db, w, zones)
    _check_dates(db, w, submit=False)
    _check_crew(db, w, body.crew)
    _check_vehicles(db, w, body.vehicles)
    _check_links(db, w, w.linked_ntm_ids, w.linked_obs_ids)
    db.add(w)
    db.flush()
    _set_crew(db, w, body.crew)
    _set_vehicles(db, w, body.vehicles)
    db.flush()
    w.blockers = compute_blockers(db, w)
    audit.record(
        db, AuditAction.create, p.actor(project.id), entity_type=EntityType.wap, entity_id=w.id,
        project_id=project.id, after=_snapshot(w),
    )  # fmt: skip
    return wap_read(db, p, w)


def update_wap(db: Session, p: Principal, wap_id: uuid.UUID, body: WapUpdate) -> WapRead:
    w = get_wap_row(db, p, wap_id)
    common.require_cap(p, w.project_id, C.wap_edit, [w.site_id], w.engagement_id)
    if w.status != WS.draft or w.revision_of_id is not None:
        raise invalid_transition("WAP", w.status, "edited")
    before = _snapshot(w)
    ch = body.changes()
    zones = _zones(db, w)
    if "zone_ids" in ch:
        zones = _check_zones(db, w.project_id, w.site_id, ch.pop("zone_ids"))
        w.zone_ids = [z.id for z in zones]
    crew = ch.pop("crew", None)
    vehicles = ch.pop("vehicles", None)
    if "windows" in ch:
        w.windows = windows.dump(body.windows or [])
        ch.pop("windows")
    for k in ("linked_ntm_ids", "linked_obs_ids"):
        if k in ch:
            setattr(w, k, list(dict.fromkeys(ch.pop(k))))
    for k, v in ch.items():
        setattr(w, k, v)
    _derive(db, w, zones)
    _check_dates(db, w, submit=False)
    if crew is not None:
        _check_crew(db, w, body.crew or [])
        _set_crew(db, w, body.crew or [])
    elif "supervisor_worker_id" in ch:
        cur = [
            CrewInput(
                worker_id=c.worker_id, crew_role=c.crew_role, escort_worker_id=c.escort_worker_id
            )
            for c in crew_rows(db, w)
        ]
        _check_crew(db, w, cur)
    if vehicles is not None:
        _check_vehicles(db, w, body.vehicles or [])
        _set_vehicles(db, w, body.vehicles or [])
    _check_links(db, w, w.linked_ntm_ids, w.linked_obs_ids)
    w.updated_at = now()
    w.updated_by_user_id = p.user.id
    db.flush()
    w.blockers = compute_blockers(db, w)
    bf, af = audit.diff(before, _snapshot(w))
    if af or crew is not None or vehicles is not None:
        audit.record(
            db, AuditAction.update, p.actor(w.project_id), entity_type=EntityType.wap,
            entity_id=w.id, project_id=w.project_id, before=bf,
            after={**af, **({"crew": len(crew)} if crew is not None else {})},
        )  # fmt: skip
    return wap_read(db, p, w)


# ---- transitions ---------------------------------------------------------------------------------


def _sod(db: Session, p: Principal, w: Wap) -> None:
    """WA-4."""
    if p.user.id == w.requested_by_user_id:
        raise ApiError(
            422, ErrorCode.SOD_CONFLICT, "The approver must differ from the requester (WA-4).",
            "يجب أن يختلف المعتمِد عن مقدم الطلب.",
        )  # fmt: skip
    u = db.get(User, p.user.id)
    emp = getattr(u, "employer_contractor_id", None)
    if emp is not None:
        for e in common.engagement_ancestors(db, w.engagement_id):
            con = common.engagement_contractor(db, e)
            if con is not None and con.id == emp:
                raise ApiError(
                    422, ErrorCode.SOD_CONFLICT,
                    "The approver cannot be employed by the WAP's contractor or its parent (WA-4).",
                    "لا يجوز أن يكون المعتمِد موظفًا لدى المقاول أو المقاول الرئيسي.",
                )  # fmt: skip


def _fod(db: Session, p: Principal, w: Wap, f: FodCheckInput | None) -> None:
    """WA-17."""
    if not w.fod_handback_required:
        return
    if f is None or f.result != FodCheckResult.clear or f.checked_at > now():
        raise ApiError(
            422, ErrorCode.FOD_HANDBACK_REQUIRED,
            "A clear FOD check (checked_at ≤ now) is required (WA-17).",
            "يلزم فحص الأجسام الغريبة بنتيجة سليمة.",
            errors=[field_error("fod_check", "Required.", "FOD_HANDBACK_REQUIRED")],
        )  # fmt: skip
    w.fod_check = {
        "checked_by_worker_id": str(f.checked_by_worker_id) if f.checked_by_worker_id else None,
        "checked_by_user_id": str(
            f.checked_by_user_id or (None if f.checked_by_worker_id else p.user.id)
        )
        if (f.checked_by_user_id or not f.checked_by_worker_id)
        else None,
        "checked_at": f.checked_at.isoformat(),
        "result": f.result.value,
    }


def _need_reason(body: WapTransitionRequest) -> str:
    if not body.reason or not body.reason.strip():
        raise validation_error("reason", "A reason is required.")
    return body.reason.strip()


def _merge_revision(db: Session, rev: Wap, base: Wap, p: Principal) -> None:
    before = _snapshot(base)
    for k in ("zone_ids", "valid_from", "valid_to", "windows", "linked_ntm_ids", "linked_obs_ids"):
        setattr(base, k, getattr(rev, k))
    base.fod_handback_required = rev.fod_handback_required
    base.works_safety_plan_ref = rev.works_safety_plan_ref
    base.revision_no = rev.revision_no
    base.updated_at = now()
    base.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _snapshot(base))
    audit.record(
        db, AuditAction.update, p.actor(base.project_id), entity_type=EntityType.wap,
        entity_id=base.id, project_id=base.project_id, before=bf, after=af,
        details={"revision_id": str(rev.id), "reason": rev.revision_reason},
    )  # fmt: skip


def transition_wap(
    db: Session, p: Principal, wap_id: uuid.UUID, body: WapTransitionRequest
) -> WapRead:
    w = get_wap_row(db, p, wap_id)
    frm, to = w.status, body.to_status
    at = now()
    warnings: list[ApiWarning] = []

    def need(cap: Capability) -> None:
        common.require_cap(p, w.project_id, cap, [w.site_id], w.engagement_id)

    def users_notify(en: str, ar: str, users: set[uuid.UUID]) -> None:
        notify.notify(
            db, users, NotificationKind.wap_update, f"{w.wap_no}: {en}", f"{w.wap_no}: {ar}",
            body.reason, body.reason, EntityType.wap, w.id, w.project_id,
        )  # fmt: skip

    reason_text: str | None = None
    if w.revision_of_id is not None:
        base = db.get(Wap, w.revision_of_id)
        assert base is not None  # noqa: S101
        if frm != WS.submitted or to not in (WS.approved, WS.rejected, WS.cancelled):
            raise invalid_transition("WAP revision", frm, to)
        if to == WS.approved:
            need(C.wap_approve)
            _sod(db, p, w)
            w.status = WS.approved
            w.approved_by_user_id = p.user.id
            w.approved_at = at
            _merge_revision(db, w, base, p)
            refresh(db, base, at, evaluate=True)
        elif to == WS.rejected:
            need(C.wap_approve)
            reason_text = _need_reason(body)
            w.status = WS.rejected
        else:
            need(C.wap_close)
            w.status = WS.cancelled
        w.status_reason = reason_text or body.reason
        w.updated_at = at
        db.flush()
        _audit_status(db, w, frm, p.actor(w.project_id), body.reason)
        users_notify(f"revision {to.value}", "تم تحديث المراجعة", {w.requested_by_user_id})
        return wap_read(db, p, w)

    if frm == WS.draft and to == WS.submitted:
        need(C.wap_edit)
        _contractor_ok(db, w.engagement_id)
        _check_dates(db, w, submit=True)
        _check_wsp(db, w)
        crew = crew_rows(db, w)
        _check_crew(
            db,
            w,
            [
                CrewInput(
                    worker_id=c.worker_id,
                    crew_role=c.crew_role,
                    escort_worker_id=c.escort_worker_id,
                )
                for c in crew
            ],
        )
        w.status = WS.submitted
        w.submitted_at = at
        evaluate_crew(db, w, at)
        users_notify(
            "submitted for approval", "مقدم للاعتماد",
            set(notify.users_with_role(db, Role.hse_officer, [w.project_id]))
            | set(notify.users_with_role(db, Role.hse_manager, [w.project_id])),
        )  # fmt: skip
    elif frm == WS.submitted and to == WS.draft:
        need(C.wap_approve)
        reason_text = _need_reason(body)
        w.status = WS.draft
        users_notify("returned", "أعيد للتعديل", {w.requested_by_user_id})
    elif frm == WS.submitted and to == WS.approved:
        need(C.wap_approve)
        _sod(db, p, w)
        w.status = WS.approved
        w.approved_by_user_id = p.user.id
        w.approved_at = at
        evaluate_crew(db, w, at)
        users_notify("approved", "تم الاعتماد", {w.requested_by_user_id})
    elif frm == WS.submitted and to == WS.rejected:
        need(C.wap_approve)
        reason_text = _need_reason(body)
        w.status = WS.rejected
        users_notify("rejected", "تم الرفض", {w.requested_by_user_id})
    elif frm == WS.active and to == WS.suspended:
        need(C.wap_suspend)
        if body.reason_code is None:
            raise validation_error("reason_code", "A reason code is required.")
        reason_text = _need_reason(body)
        _suspend(db, w, body.reason_code, reason_text, p.user.id, p.actor(w.project_id))
        return wap_read(db, p, w)
    elif frm == WS.suspended and to == WS.active:
        need(C.wap_approve)
        if not w.valid_from <= common.local_day(at) <= w.valid_to:
            raise invalid_transition("WAP", frm, to)
        evaluate_crew(db, w, at)
        blockers = compute_blockers(db, w, at)
        w.blockers = blockers
        if blockers:
            raise ApiError(
                422, ErrorCode.WAP_BLOCKED, "The WAP has blockers (WA-13).",
                "التصريح لديه معوقات.", meta={"blockers": [b["code"] for b in blockers]},
            )  # fmt: skip
        _fod(db, p, w, body.fod_check)
        w.status = WS.active
        w.suspension_reason = None
        lifecycle.event(
            db, w, CredentialAction.reinstated, CredentialReason.other, body.reason, p.user.id, at
        )
        users_notify("resumed", "تم الاستئناف", _wap_users(db, w))
    elif frm in (WS.active, WS.suspended) and to == WS.closed:
        need(C.wap_close)
        _fod(db, p, w, body.fod_check)
        _end(db, w, WS.closed, at)
    elif frm in (WS.draft, WS.submitted, WS.approved) and to == WS.cancelled:
        need(C.wap_close)
        reason_text = _need_reason(body)
        _end(db, w, WS.cancelled, at)
    else:
        raise invalid_transition("WAP", frm, to)
    w.status_reason = reason_text
    w.updated_at = at
    w.updated_by_user_id = p.user.id
    db.flush()
    _audit_status(db, w, frm, p.actor(w.project_id), reason_text)
    if w.status in (WS.approved, WS.submitted):
        refresh(db, w, at)
        if w.status == WS.approved and w.blockers:
            warnings.append(
                ApiWarning(
                    code="WAP_BLOCKED",
                    message="Approved with blockers; it activates once they clear.",
                    message_ar="تم الاعتماد مع وجود معوقات؛ يسري عند زوالها.",
                )
            )
    return wap_read(db, p, w, warnings=warnings)


# ---- revisions, crew, vehicles -------------------------------------------------------------------


def create_revision(
    db: Session, p: Principal, wap_id: uuid.UUID, body: WapRevisionCreate
) -> WapRead:
    w = get_wap_row(db, p, wap_id)
    common.require_cap(p, w.project_id, C.wap_edit, [w.site_id], w.engagement_id)
    if w.revision_of_id is not None or w.status not in LIVE:
        raise invalid_transition("WAP", w.status, "revised")
    if pending_revision(db, w) is not None:
        raise duplicate("revision", "A revision is already awaiting approval.")
    zones = _check_zones(db, w.project_id, w.site_id, body.zone_ids or list(w.zone_ids))
    rev = Wap(
        id=uuid.uuid4(),
        year=w.year,
        seq=w.seq,
        wap_no=w.wap_no,
        revision_no=max(
            [w.revision_no, *db.scalars(select(Wap.revision_no).where(Wap.revision_of_id == w.id))]
        )
        + 1,
        revision_of_id=w.id,
        revision_reason=body.reason,
        project_id=w.project_id,
        site_id=w.site_id,
        zone_ids=[z.id for z in zones],
        engagement_id=w.engagement_id,
        requested_by_user_id=p.user.id,
        supervisor_worker_id=w.supervisor_worker_id,
        scope_en=w.scope_en,
        scope_ar=w.scope_ar,
        works_safety_plan_ref=w.works_safety_plan_ref,
        valid_from=body.valid_from or w.valid_from,
        valid_to=body.valid_to or w.valid_to,
        windows=windows.dump(body.windows) if body.windows else list(w.windows),
        operator_permit_ref=w.operator_permit_ref,
        linked_ntm_ids=list(dict.fromkeys(body.linked_ntm_ids))
        if body.linked_ntm_ids is not None
        else list(w.linked_ntm_ids),
        linked_obs_ids=list(dict.fromkeys(body.linked_obs_ids))
        if body.linked_obs_ids is not None
        else list(w.linked_obs_ids),
        conditions_en=w.conditions_en,
        conditions_ar=w.conditions_ar,
        blockers=[],
        alerts_sent=[],
        submitted_at=now(),
        status=WS.submitted,
        created_by_user_id=p.user.id,
    )
    _derive(db, rev, zones)
    _check_dates(db, rev, submit=body.valid_from is not None and body.valid_from != w.valid_from)
    _check_links(db, rev, rev.linked_ntm_ids, rev.linked_obs_ids)
    _check_wsp(db, rev)
    db.add(rev)
    db.flush()
    rev.blockers = compute_blockers(db, rev)
    audit.record(
        db, AuditAction.create, p.actor(w.project_id), entity_type=EntityType.wap,
        entity_id=rev.id, project_id=w.project_id, after=_snapshot(rev),
        details={"revision_of": str(w.id), "reason": body.reason},
    )  # fmt: skip
    return wap_read(db, p, rev)


def _editable(db: Session, p: Principal, wap_id: uuid.UUID) -> Wap:
    w = get_wap_row(db, p, wap_id)
    common.require_cap(p, w.project_id, C.wap_edit, [w.site_id], w.engagement_id)
    if w.revision_of_id is not None or w.status not in OPEN:
        raise invalid_transition("WAP", w.status, "changed")
    return w


def _after_change(db: Session, p: Principal, w: Wap, what: dict[str, Any]) -> WapRead:
    w.updated_at = now()
    w.updated_by_user_id = p.user.id
    db.flush()
    if w.status in (WS.draft,):
        w.blockers = compute_blockers(db, w)
    else:
        refresh(db, w, evaluate=True)
    audit.record(
        db, AuditAction.update, p.actor(w.project_id), entity_type=EntityType.wap,
        entity_id=w.id, project_id=w.project_id, after=common.jsonable(what),
    )  # fmt: skip
    return wap_read(db, p, w)


def add_crew(db: Session, p: Principal, wap_id: uuid.UUID, body: CrewInput) -> WapRead:
    w = _editable(db, p, wap_id)
    current = crew_rows(db, w)
    if any(c.worker_id == body.worker_id for c in current):
        raise duplicate("worker_id", "This worker is already on the crew.")
    _check_member(db, w, body, "worker_id")
    if body.escort_worker_id is not None and not any(
        c.worker_id == body.escort_worker_id and c.crew_role in ESCORT_ROLES for c in current
    ):
        raise _crew_invalid(
            "The escort must be a crew member with role escort or supervisor (WA-11).",
            "يجب أن يكون المرافق عضوًا في الطاقم بدور مرافق.", "escort_worker_id",
        )  # fmt: skip
    old = db.scalar(
        select(WapCrew).where(WapCrew.wap_id == w.id, WapCrew.worker_id == body.worker_id)
    )
    if old is not None:
        db.delete(old)
        db.flush()
    db.add(
        WapCrew(
            id=uuid.uuid4(), wap_id=w.id, worker_id=body.worker_id, crew_role=body.crew_role,
            escort_worker_id=body.escort_worker_id, status=CrewMemberStatus.included,
            exclusion_reasons=[], escorted=False,
        )
    )  # fmt: skip
    return _after_change(db, p, w, {"crew_added": body.worker_id})


def remove_crew(db: Session, p: Principal, wap_id: uuid.UUID, worker_id: uuid.UUID) -> WapRead:
    w = _editable(db, p, wap_id)
    row = next((c for c in crew_rows(db, w) if c.worker_id == worker_id), None)
    if row is None:
        raise not_found("Crew member")
    if worker_id == w.supervisor_worker_id:
        raise _crew_invalid(
            "The supervisor cannot be removed.", "لا يمكن إزالة المشرف.", "worker_id"
        )
    if any(c.escort_worker_id == worker_id for c in crew_rows(db, w)):
        raise _crew_invalid(
            "Reassign the escorted members first.", "أعد تعيين المرافَقين أولًا.", "worker_id"
        )
    row.removed_at = now()
    row.status = CrewMemberStatus.removed
    return _after_change(db, p, w, {"crew_removed": worker_id})


def add_vehicle(db: Session, p: Principal, wap_id: uuid.UUID, body: WapVehicleInput) -> WapRead:
    w = _editable(db, p, wap_id)
    current = vehicle_rows(db, w)
    if any(v.vehicle_id == body.vehicle_id for v in current):
        raise duplicate("vehicle_id", "This vehicle is already listed.")
    _check_vehicle(db, w, body, "vehicle_id")
    if body.escort_vehicle_id is not None and not any(
        v.vehicle_id == body.escort_vehicle_id for v in current
    ):
        raise validation_error("escort_vehicle_id", "The escort vehicle must be listed on the WAP.")
    old = db.scalar(
        select(WapVehicle).where(
            WapVehicle.wap_id == w.id, WapVehicle.vehicle_id == body.vehicle_id
        )
    )
    if old is not None:
        db.delete(old)
        db.flush()
    db.add(
        WapVehicle(
            id=uuid.uuid4(), wap_id=w.id, vehicle_id=body.vehicle_id,
            escort_vehicle_id=body.escort_vehicle_id, height_limited_to_m=body.height_limited_to_m,
            status=CrewMemberStatus.included, exclusion_reasons=[],
        )
    )  # fmt: skip
    return _after_change(db, p, w, {"vehicle_added": body.vehicle_id})


def remove_vehicle(db: Session, p: Principal, wap_id: uuid.UUID, vehicle_id: uuid.UUID) -> WapRead:
    w = _editable(db, p, wap_id)
    rows = vehicle_rows(db, w)
    row = next((v for v in rows if v.vehicle_id == vehicle_id), None)
    if row is None:
        raise not_found("WAP vehicle")
    if any(v.escort_vehicle_id == vehicle_id for v in rows):
        raise validation_error("vehicle_id", "This vehicle escorts another listed vehicle.")
    row.removed_at = now()
    row.status = CrewMemberStatus.removed
    return _after_change(db, p, w, {"vehicle_removed": vehicle_id})


def print_wap(db: Session, p: Principal, wap_id: uuid.UUID) -> WapPrintRead:
    w = get_wap_row(db, p, wap_id)
    if w.revision_of_id is not None or w.status not in LIVE:
        raise invalid_transition("WAP", w.status, "printed")
    t = common.active_qr(db, w.id) or common.issue_qr(db, QrKind.WP, w.project_id, w.id, w.wap_no)
    return WapPrintRead(
        wap_id=w.id,
        wap_no=w.wap_no,
        qr_payload=common.payload(t),
        printed_ref=t.printed_ref,
        token_status=t.status,
        wap=wap_read(db, p, w),
    )


def board(
    db: Session, p: Principal, project_id: uuid.UUID, on: date | None, site_id: uuid.UUID | None
) -> WapBoardResponse:
    project = projects.get_visible(db, p, project_id)
    g = _view(db, p, project.id)
    d = on or today()
    stmt = select(Wap).where(
        Wap.project_id == project.id,
        Wap.revision_of_id.is_(None),
        Wap.status.in_(LIVE),
        Wap.valid_from <= d,
        Wap.valid_to >= d,
    )
    if site_id:
        stmt = stmt.where(Wap.site_id == site_id)
    rows = [
        w
        for w in db.scalars(stmt.order_by(Wap.wap_no))
        if common.grant_covers(g, [w.site_id], w.engagement_id)
    ]
    refs = Refs(db).load(
        sites=[w.site_id for w in rows], zones=[z for w in rows for z in w.zone_ids or []],
        engs=[w.engagement_id for w in rows],
    )  # fmt: skip
    reads = {w.id: wap_read(db, p, w, refs) for w in rows}
    zone_ids = list(dict.fromkeys(z for w in rows for z in w.zone_ids or []))
    at = now() if d == today() else common.local_midnight_utc(d) + timedelta(hours=12)
    out = []
    for zid in zone_ids:
        zr = refs.zone(zid)
        if zr is None:
            continue
        out.append(
            WapBoardZone(
                zone=zr,
                waps=[reads[w.id] for w in rows if zid in (w.zone_ids or [])],
                ops_suspension_active=bool(active_ops(db, [zid], at)),
            )
        )
    out.sort(key=lambda z: z.zone.code)
    return WapBoardResponse(project_id=project.id, date=d, zones=out)


# ---- operational suspension events (WA-15, WA-16) ------------------------------------------------


def ops_read(db: Session, e: OpsEvent, refs: Refs | None = None) -> OpsEventRead:
    refs = refs or Refs(db)
    at = now()
    return OpsEventRead(
        id=e.id,
        ops_no=e.ops_no,
        project_id=e.project_id,
        site=refs.site(e.site_id),
        type=e.type,
        zones=[z for z in (refs.zone(x) for x in e.zone_ids or []) if z is not None],
        default_zone_ids=list(e.default_zone_ids or []),
        source=e.source,
        source_ref=e.source_ref,
        started_at=e.started_at,
        ended_at=e.ended_at,
        active=e.started_at <= at and (e.ended_at is None or e.ended_at > at),
        declared_by=refs.user(e.declared_by_user_id) or attachments.UNKNOWN,
        notes=e.notes,
        suspended_wap_ids=list(e.suspended_wap_ids or []),
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


def get_ops_row(db: Session, p: Principal, event_id: uuid.UUID) -> OpsEvent:
    e = db.get(OpsEvent, event_id)
    if e is None:
        raise not_found("Operational suspension event")
    g = _view(db, p, e.project_id)
    if g.site_ids is not None and e.site_id not in g.site_ids:
        raise forbidden_error("This record is outside your scope.")
    return e


def read_ops(db: Session, p: Principal, event_id: uuid.UUID) -> OpsEventRead:
    return ops_read(db, get_ops_row(db, p, event_id))


def list_ops(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    active: bool | None = None,
    types: list[OpsEventType] | None = None,
    site_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OpsEventPage:
    project = projects.get_visible(db, p, project_id)
    g = _view(db, p, project.id)
    stmt = select(OpsEvent).where(OpsEvent.project_id == project.id)
    if g.site_ids is not None:
        stmt = stmt.where(OpsEvent.site_id.in_(list(g.site_ids)))
    at = now()
    if active is not None:
        cond = (OpsEvent.started_at <= at) & or_(
            OpsEvent.ended_at.is_(None), OpsEvent.ended_at > at
        )
        stmt = stmt.where(cond if active else ~cond)
    if types:
        stmt = stmt.where(OpsEvent.type.in_(types))
    if site_id:
        stmt = stmt.where(OpsEvent.site_id == site_id)
    if date_from:
        stmt = stmt.where(
            or_(
                OpsEvent.ended_at.is_(None),
                OpsEvent.ended_at >= common.local_midnight_utc(date_from),
            )
        )
    if date_to:
        stmt = stmt.where(
            OpsEvent.started_at < common.local_midnight_utc(date_to + timedelta(days=1))
        )
    rows, total = paginate(db, stmt.order_by(OpsEvent.started_at.desc()), page, page_size)
    refs = Refs(db).load(
        sites=[e.site_id for e in rows], zones=[z for e in rows for z in e.zone_ids or []],
        users=[e.declared_by_user_id for e in rows],
    )  # fmt: skip
    return OpsEventPage(
        items=[ops_read(db, e, refs) for e in rows], total=total, page=page, page_size=page_size
    )


def _default_zones(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, t: OpsEventType
) -> list[uuid.UUID]:
    if t not in LVP_TYPES:
        return []
    out = []
    for z in db.scalars(
        select(Zone).where(
            Zone.site_id == site_id, Zone.project_id == project_id, Zone.status == ZoneStatus.active
        )
    ):
        if profiles.ensure(db, z).lvp_withdrawal_required:
            out.append(z.id)
    return out


def apply_ops(db: Session, e: OpsEvent, at: datetime | None = None) -> int:
    """WA-15: suspend every Active WAP with a zone in the event's zones (idempotent)."""
    at = at or now()
    if e.started_at > at or (e.ended_at is not None and e.ended_at <= at):
        return 0
    from app.services.cert import scaffolds  # noqa: PLC0415 (Phase 4 SF-5, once per event)

    scaffolds.ops_event_trigger(db, e)
    n = 0
    for w in db.scalars(
        select(Wap).where(
            Wap.project_id == e.project_id,
            Wap.revision_of_id.is_(None),
            Wap.status == WS.active,
            Wap.zone_ids.overlap(list(e.zone_ids or [])),
        )
    ):
        w.blockers = compute_blockers(db, w, at)
        _suspend(db, w, CredentialReason.ops_suspension, f"{e.ops_no} ({e.type.value})")
        if w.id not in (e.suspended_wap_ids or []):
            e.suspended_wap_ids = [*(e.suspended_wap_ids or []), w.id]
        n += 1
    db.flush()
    return n


def _ops_notify(db: Session, e: OpsEvent, started: bool) -> None:
    users = set(notify.users_with_role(db, Role.hse_officer, [e.project_id]))
    for w in db.scalars(
        select(Wap).where(
            Wap.project_id == e.project_id,
            Wap.revision_of_id.is_(None),
            Wap.status.in_(LIVE),
            Wap.zone_ids.overlap(list(e.zone_ids or [])),
        )
    ):
        users |= _wap_users(db, w)
    en = "started" if started else "ended"
    ar = "بدأ" if started else "انتهى"
    notify.notify(
        db, users, NotificationKind.ops_suspension,
        f"{e.ops_no}: operational suspension {en} ({e.type.value})",
        f"{e.ops_no}: إيقاف تشغيلي {ar}",
        e.notes, e.notes, EntityType.ops_event, e.id, e.project_id,
    )  # fmt: skip


def create_ops(
    db: Session, p: Principal, project_id: uuid.UUID, body: OpsEventCreate
) -> OpsEventRead:
    project = projects.get_visible(db, p, project_id)
    common.require_cap(p, project.id, C.wap_suspend, [body.site_id], None)
    extra = _check_zones(db, project.id, body.site_id, body.zone_ids) if body.zone_ids else []
    defaults = _default_zones(db, project.id, body.site_id, body.type)
    zone_ids = list(dict.fromkeys([*defaults, *(z.id for z in extra)]))
    if not zone_ids:
        raise validation_error("zone_ids", "Choose at least one zone.")
    at = now()
    year = today().year
    seq = next_seq(db, OpsEvent, project.id, year)
    e = OpsEvent(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        ops_no=make_ref("OPS", project.code, year, seq, 4),
        project_id=project.id,
        site_id=body.site_id,
        type=body.type,
        zone_ids=zone_ids,
        default_zone_ids=defaults,
        source=body.source,
        source_ref=body.source_ref,
        started_at=body.started_at or at,
        declared_by_user_id=p.user.id,
        notes=body.notes,
        suspended_wap_ids=[],
        created_by_user_id=p.user.id,
    )
    db.add(e)
    db.flush()
    audit.record(
        db, AuditAction.create, p.actor(project.id), entity_type=EntityType.ops_event,
        entity_id=e.id, project_id=project.id,
        after=common.jsonable(
            {"ops_no": e.ops_no, "type": e.type, "zone_ids": zone_ids, "started_at": e.started_at}
        ),
    )  # fmt: skip
    apply_ops(db, e, at)
    if e.started_at <= at:
        _ops_notify(db, e, True)
    return ops_read(db, e)


def update_ops(
    db: Session, p: Principal, event_id: uuid.UUID, body: OpsEventUpdate
) -> OpsEventRead:
    e = get_ops_row(db, p, event_id)
    common.require_cap(p, e.project_id, C.wap_suspend, [e.site_id], None)
    if e.ended_at is not None:
        raise invalid_transition("Operational suspension", "ended", "edited")
    ch = body.changes()
    before = {"zone_ids": [str(z) for z in e.zone_ids], "notes": e.notes}
    if "zone_ids" in ch:
        new = list(dict.fromkeys(ch["zone_ids"] or []))
        missing = [z for z in e.default_zone_ids or [] if z not in new]
        if missing:
            raise ApiError(
                422, ErrorCode.OPS_ZONES_LOCKED,
                "Default zones of an LVP / dust event cannot be removed (WA-16).",
                "لا يمكن إزالة المناطق الافتراضية.",
                errors=[field_error("zone_ids", "Locked.", "OPS_ZONES_LOCKED")],
            )  # fmt: skip
        _check_zones(db, e.project_id, e.site_id, new)
        e.zone_ids = new
    if "notes" in ch:
        e.notes = ch["notes"]
    e.updated_at = now()
    e.updated_by_user_id = p.user.id
    db.flush()
    apply_ops(db, e)
    audit.record(
        db, AuditAction.update, p.actor(e.project_id), entity_type=EntityType.ops_event,
        entity_id=e.id, project_id=e.project_id, before=before,
        after={"zone_ids": [str(z) for z in e.zone_ids], "notes": e.notes},
    )  # fmt: skip
    return ops_read(db, e)


def end_ops(db: Session, p: Principal, event_id: uuid.UUID, body: OpsEventEnd) -> OpsEventRead:
    e = get_ops_row(db, p, event_id)
    common.require_cap(p, e.project_id, C.wap_suspend, [e.site_id], None)
    if e.ended_at is not None:
        raise invalid_transition("Operational suspension", "ended", "ended")
    at = body.ended_at or now()
    if at < e.started_at:
        raise validation_error("ended_at", "The end must be after the start.")
    e.ended_at = at
    e.updated_at = now()
    e.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db, AuditAction.status_change, p.actor(e.project_id), entity_type=EntityType.ops_event,
        entity_id=e.id, project_id=e.project_id, before={"active": True},
        after={"active": False, "ended_at": at.isoformat()},
    )  # fmt: skip
    _ops_notify(db, e, False)
    return ops_read(db, e)


# ---- jobs ----------------------------------------------------------------------------------------


def ops_job(db: Session, at: datetime | None = None) -> int:
    """WA-15 within 60 s for events whose start was in the future when declared."""
    at = at or now()
    n = 0
    for e in db.scalars(
        select(OpsEvent).where(
            OpsEvent.started_at <= at, or_(OpsEvent.ended_at.is_(None), OpsEvent.ended_at > at)
        )
    ):
        n += apply_ops(db, e, at)
    return n


def wap_job(db: Session, at: datetime | None = None) -> int:
    """Activation at valid_from (WA-13), window-start re-evaluation (WA-10), close at
    valid_to + 1 and expiry of never-activated WAPs (§4.8). Returns the number of changes."""
    at = at or now()
    d = common.local_day(at)
    n = 0
    for w in list(
        db.scalars(select(Wap).where(Wap.revision_of_id.is_(None), Wap.status.in_(LIVE)))
    ):
        frm = w.status
        if w.valid_to < d:
            _end(db, w, WS.expired if frm == WS.approved else WS.closed, at)
            _audit_status(db, w, frm, None, "valid_to passed")
            n += 1
            continue
        if w.valid_from > d:
            continue
        inst = windows.current(windows.parse(w.windows), w.valid_from, w.valid_to, at)
        key = f"win:{inst.start_utc.isoformat()}" if inst else f"day:{d.isoformat()}"
        if key in (w.alerts_sent or []):
            continue
        w.alerts_sent = [*(w.alerts_sent or []), key][-40:]
        refresh(db, w, at, evaluate=True)
        if w.status == WS.approved and w.blockers and inst is not None:
            _blocked_alert(db, w, f"blocked:{key}")
        n += int(w.status != frm)
    db.flush()
    return n


def refresh_for_worker(db: Session, worker_id: uuid.UUID) -> None:
    for w in db.scalars(
        select(Wap)
        .join(WapCrew, WapCrew.wap_id == Wap.id)
        .where(WapCrew.worker_id == worker_id, WapCrew.removed_at.is_(None), Wap.status.in_(OPEN))
    ):
        refresh(db, w, evaluate=w.status != WS.draft)


def refresh_for_engagements(db: Session, engagement_ids: list[uuid.UUID]) -> None:
    """WA-3: contractor suspended → Active WAPs suspended (`contractor_suspended`)."""
    for w in db.scalars(
        select(Wap).where(
            Wap.engagement_id.in_(engagement_ids),
            Wap.revision_of_id.is_(None),
            Wap.status.in_(LIVE),
        )
    ):
        refresh(db, w)


# ---- Phase 3 read (§8.5) -------------------------------------------------------------------------


def active_at(
    db: Session, zone_id: uuid.UUID, engagement_id: uuid.UUID | None, at: datetime
) -> list[Wap]:
    stmt = select(Wap).where(
        Wap.revision_of_id.is_(None), Wap.status == WS.active, Wap.zone_ids.contains([zone_id])
    )
    if engagement_id is not None:
        stmt = stmt.where(Wap.engagement_id.in_(common.engagement_ancestors(db, engagement_id)))
    d = common.local_day(at)
    return [w for w in db.scalars(stmt.order_by(Wap.wap_no)) if w.valid_from <= d <= w.valid_to]
