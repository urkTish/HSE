"""Phase 3 integration (spec 6c-emergency-drills §5.9 PE-1…PE-5, 3-ptw v1.4 §11.4): event and
drill suspensions, the receiver's resume after a drill, the rescue readiness blockers and the
height-rescue / extinguisher warnings. PE-3…PE-5 apply only from
`emergency_ptw_enforcement_from` (§11.4 item 6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import ActiveStatus, DrillStatus, EventStatus, TeamType
from app.core.errors import ErrorCode
from app.core.ptw_enums import (
    CrewLineStatus,
    PermitBlocker,
    PermitStatus,
    PermitWarningCode,
    PtwCrewRole,
    StatusReason,
)
from app.core.ptw_enums import PermitType as T
from app.models import Drill, EmergencyEvent, Permit, PermitSuspension, RescueTeam, Worker
from app.schemas.permits import PermitRead
from app.services.emergency import common as ec

B = PermitBlocker
W = PermitWarningCode
LIVE = (PermitStatus.issued, PermitStatus.active)


def applies(db: Session, project_id: uuid.UUID, at: datetime) -> bool:
    d = ec.local_day(at)
    return ec.enabled(db, project_id, d) and ec.cfg(db, project_id).enforced_on(d)


# ---- PE-1 / PE-2 suspensions ---------------------------------------------------------------------


def suspend_for(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_ids: list[uuid.UUID] | None,
    reason: StatusReason,
    source_ref: str,
    at: datetime,
) -> int:
    """Suspend every Issued / Active permit of the site whose zones intersect the evacuated zones
    (site evacuation: every zone of the site)."""
    from app.services.ptw import lifecycle  # noqa: PLC0415

    zs = set(zone_ids or [])
    n = 0
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == project_id,
            Permit.site_id == site_id,
            Permit.status.in_(LIVE),
        )
    ):
        if zs and not zs & set(pm.zone_ids or []):
            continue
        if lifecycle.auto_suspend(db, pm, reason, source_ref, source_ref, at) is not None:
            n += 1
    return n


def _source(db: Session, permit: Permit) -> tuple[PermitSuspension | None, str | None]:
    from app.services.ptw import evaluation  # noqa: PLC0415

    sp = evaluation.open_suspension(db, permit)
    return sp, sp.auto_source_ref if sp is not None else None


def emergency_resume_guard(db: Session, permit: Permit) -> None:
    """PE-1: a permit suspended `emergency` is resumed by the issuer only after All Clear."""
    if permit.status_reason != StatusReason.emergency:
        return
    _sp, ref_ = _source(db, permit)
    if not ref_:
        return
    ev = db.scalar(select(EmergencyEvent).where(EmergencyEvent.event_no == ref_))
    if ev is not None and ev.status == EventStatus.active:
        raise ec.err(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            f"{ev.event_no} is still Active: resume after All Clear (PE-1).",
            f"الحدث {ev.event_no} ما زال نشطاً: الاستئناف بعد انتهاء الحالة.",
        )


def drill_resume(db: Session, p: Any, permit_id: uuid.UUID, body: Any) -> PermitRead:
    """PE-2: the receiver resumes a permit suspended `emergency_drill` once the drill is
    Conducted; no issuer cause text; GT-4 where gas testing applies (via the shift checks)."""
    from app.core.ptw_enums import SignaturePurpose, SimopsCheckTrigger  # noqa: PLC0415
    from app.services.ptw import common as pcommon  # noqa: PLC0415
    from app.services.ptw import evaluation, lifecycle  # noqa: PLC0415

    permit = pcommon.get_permit(db, p, permit_id)
    lifecycle._need(permit, "resume", PermitStatus.suspended)
    if permit.status_reason != StatusReason.emergency_drill:
        raise pcommon.err(
            ErrorCode.INVALID_TRANSITION,
            "Only a permit suspended for an emergency drill is resumed by the receiver (PE-2).",
            "يستأنف المستلم فقط التصريح الموقوف لتمرين طوارئ.",
            status=422,
        )
    lifecycle._receiver_only(p, permit, "resumes after an emergency drill")
    sp, ref_ = _source(db, permit)
    d = db.scalar(select(Drill).where(Drill.drill_no == ref_)) if ref_ else None
    if d is not None and d.status == DrillStatus.in_progress:
        raise pcommon.err(
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            f"{d.drill_no} is still in progress: resume after it is Conducted (PE-2).",
            f"التمرين {d.drill_no} ما زال جارياً.",
            status=409,
        )
    at = now()
    s = pcommon.settings(db, permit.project_id)
    gas_after = None
    if sp is not None and at - sp.suspended_at >= timedelta(minutes=s.gas_break_retest_minutes):
        gas_after = sp.suspended_at
    lifecycle._simops(db, permit, SimopsCheckTrigger.resume, at)
    chk = lifecycle.shift_checks(db, permit, body, at, gas_after=gas_after, gas_start=True)
    lifecycle.save_wind(db, p, permit, body.wind_reading)
    if sp is not None:
        sp.resumed_at = at
        sp.resumed_by_user_id = p.user.id
        sp.resume_gas_test_id = chk.gas_test_id
    assert permit.issuer_user_id is not None  # noqa: S101
    lifecycle.open_shift(
        db,
        permit,
        at,
        receiver_id=permit.receiver_user_id,
        issuer_id=permit.issuer_user_id,
        crew=chk.crew,
        ambient=body.ambient_temp_c,
        gas_test_id=chk.gas_test_id,
        end=chk.planned_end,
    )
    lifecycle._set_status(db, p, permit, PermitStatus.active, details={"drill_resume": True})
    pcommon.sign(db, permit, SignaturePurpose.resume, "receiver", user_id=p.user.id, at=at)
    evaluation.store(permit, chk.result)
    lifecycle._refresh(db, permit, at)
    return lifecycle._view(db, p, permit)


# ---- PE-3 / PE-4 / PE-5 (called from ptw.evaluation.evaluate) ------------------------------------


def _teams(db: Session, project_id: uuid.UUID, team_type: TeamType) -> list[RescueTeam]:
    return list(
        db.scalars(
            select(RescueTeam).where(
                RescueTeam.project_id == project_id,
                RescueTeam.team_type == team_type,
                RescueTeam.status == ActiveStatus.active,
            )
        )
    )


def check(db: Session, permit: Permit, ctx: Any, res: Any, lines: list[Any]) -> None:
    if not ctx.start or not applies(db, permit.project_id, ctx.at):
        return
    from app.services.emergency import assets, org  # noqa: PLC0415
    from app.services.med import common as mcommon  # noqa: PLC0415
    from app.services.ptw import rules  # noqa: PLC0415

    d = ec.local_day(ctx.at)
    types = set(permit.work_types or [])
    if T.confined_space.value in types:
        for line in lines:
            if line.crew_role != PtwCrewRole.rescue_lead or line.status == CrewLineStatus.excluded:
                continue
            w = db.get(Worker, line.worker_id)
            wno = w.worker_no if w else None
            dep = mcommon.deployment(db, line.worker_id, permit.project_id)
            t = (
                org.team_for_lead(db, permit.project_id, dep.id, TeamType.confined_space)
                if dep is not None
                else None
            )
            if t is None:
                res.add(B.RESCUE_TEAM_NOT_REGISTERED, wno, wno)
                continue
            r = org.readiness(db, t, d)
            if not r.current:
                reasons = [x.value for x in r.reasons]
                res.add(
                    B.RESCUE_DRILL_OVERDUE,
                    f"{t.team_code}: {', '.join(reasons)}",
                    t.team_code,
                    reasons=reasons,
                )
    if T.work_at_height.value in types and rules.wah_arrest(res.facts.sec(T.work_at_height)):
        ok = any(
            permit.site_id in (t.site_ids or []) and org.readiness(db, t, d).current
            for t in _teams(db, permit.project_id, TeamType.height)
        )
        if not ok:
            res.warn(W.HEIGHT_RESCUE_NOT_READY, ec.site_code(db, permit.site_id))
    if T.hot_work.value in types:
        zmap = ec.zone_map(db, permit.project_id)
        for z in permit.zone_ids or []:
            if not assets.ready_extinguisher_in(db, permit.project_id, z, ctx.at):
                code = zmap[z].code if z in zmap else None
                res.warn(W.NO_READY_EXTINGUISHER, code, code)
