"""Fitness holds, referrals and return to work (spec 6a-occupational-health §3.7, §3.8, §4.4,
§4.5, FH-1…FH-8, RF-1…RF-7, RW-1…RW-4).

Holds are created by the system (injury cases FH-1a, referrals with removal FH-1b) or manually
(FH-1c); they are released only by an accepted assessment (FH-3) and cancelled with a reason
(FH-4). Work during a hold (FH-8) is detected at gate entries, permit shift starts and from the
Phase 1 rtw_date."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import GateDirection, GateResult
from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.med_enums import (
    AssessmentType,
    FitnessOutcome,
    HoldCancelCode,
    HoldReason,
    HoldSourceType,
    HoldStatus,
    ReferralReason,
    ReferralStatus,
    WorkDuringHoldType,
)
from app.models import (
    FitnessAssessment,
    FitnessHold,
    FitnessLine,
    FitnessReferral,
    Incident,
    InjuryCase,
    Project,
    Worker,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.medical import (
    FitnessHoldCancel,
    FitnessHoldCreate,
    FitnessHoldPage,
    FitnessHoldRead,
    FitnessReferralCancel,
    FitnessReferralCreate,
    FitnessReferralPage,
    FitnessReferralRead,
    WorkDuringHoldRead,
)
from app.services.cert import common as cc
from app.services.common import invalid_transition, paginate
from app.services.hse_common import id_warnings, make_ref, next_seq
from app.services.med import alerts, common
from app.services.med import reference as ref
from app.services.permissions import Principal, deny, forbidden_error

C = common.C
HS = HoldStatus
RS = ReferralStatus
K = NotificationKind
SKIP = ("reason_text_enc", "cancel_reason_enc", "note_enc")
LIVE_GATE = (GateResult.GRANTED, GateResult.GRANTED_WITH_WARNING)

# ---- helpers -------------------------------------------------------------------------------------


def _pcode(db: Session, project_id: uuid.UUID) -> str:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return pr.code


def _publish(db: Session, worker_id: uuid.UUID) -> None:
    from app.services.cert import events  # noqa: PLC0415

    common.clear_cache(db)
    events.publish(db, "medical.hold_changed", worker_ids=[worker_id])


def hold_hours(h: FitnessHold, at: datetime | None = None) -> str:
    end = h.released_at or h.cancelled_at or at or now()
    hrs = Decimal((end - h.started_at).total_seconds()) / Decimal(3600)
    return str(hrs.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def can_cancel(p: Principal, project_id: uuid.UUID) -> bool:
    """Row 159: HSE Officers may place holds only; OH Practitioners and the Manager cancel."""
    return p.grant(project_id, C.fitness_hold_manage) is not None and (
        p.is_manager or common.is_oh(p, project_id)
    )


def _hold_visible(db: Session, p: Principal, h: FitnessHold) -> int:
    t = common.tier(p, h.project_id, common.deployment(db, h.worker_id, h.project_id))
    if t < 2:
        raise deny(db, p, EntityType.fitness_hold, h.id, h.project_id, "Fitness hold")
    return t


def hold_read(db: Session, p: Principal | None, h: FitnessHold, tier: int) -> FitnessHoldRead:
    w = db.get(Worker, h.worker_id)
    assert w is not None  # noqa: S101
    out = FitnessHoldRead(
        id=h.id,
        tier=common.tier_enum(tier),
        hold_no=h.hold_no,
        worker=common.worker_ref(w, common.names(p, h.project_id)),
        project_id=h.project_id,
        status=h.status,
        started_at=h.started_at,
        released_at=h.released_at,
        cancelled_at=h.cancelled_at,
        hold_hours=hold_hours(h),
        compliant=(not h.work_during_hold) if h.status == HS.released else None,
        work_during_hold=[
            WorkDuringHoldRead(
                event_type=WorkDuringHoldType(x["event_type"]),
                ref=x.get("ref"),
                at=datetime.fromisoformat(x["at"]),
            )
            for x in h.work_during_hold or []
        ],
    )
    if tier >= 3:
        out.reason = h.reason
        out.source_type = h.source_type
        out.source_ref = h.source_ref
        out.reason_text = common.dec(h.reason_text_enc)
        if h.release_assessment_id:
            a = db.get(FitnessAssessment, h.release_assessment_id)
            out.release_assessment_no = a.assessment_no if a else None
        out.cancel_code = h.cancel_code
        out.cancel_reason = common.dec(h.cancel_reason_enc)
    return out


# ---- creation (FH-1) -----------------------------------------------------------------------------


def create_hold(
    db: Session,
    p: Principal | None,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    reason: HoldReason,
    source_type: HoldSourceType,
    source_id: uuid.UUID | None,
    source_ref: str | None,
    text: str | None = None,
    at: datetime | None = None,
) -> FitnessHold:
    at = at or now()
    y = common.local_day(at).year
    seq = next_seq(db, FitnessHold, project_id, y)
    dep = common.deployment(db, worker_id, project_id)
    h = FitnessHold(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        hold_no=make_ref("MFH", _pcode(db, project_id), y, seq, 5),
        worker_id=worker_id,
        project_id=project_id,
        engagement_id=dep.engagement_id if dep else None,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
        source_ref=source_ref,
        reason_text_enc=common.enc(text),
        started_at=at,  # FH-5: never back-dated
        status=HS.active,
        work_during_hold=[],
        alerts_sent=[],
    )
    cc.stamp(h, p, create=True)
    db.add(h)
    db.flush()
    common.record(db, p, AuditAction.create, EntityType.fitness_hold, h, project_id)
    _publish(db, worker_id)
    _alert_created(db, h)
    return h


def _alert_created(db: Session, h: FitnessHold) -> None:
    n = alerts.wno(db, h.worker_id)
    en, ar = ref.REMOVED
    alerts.send(
        db,
        alerts.oh(db, h.project_id),
        K.fitness_hold_created,
        f"{en}: {n} ({h.hold_no}, {ref.HOLD_LABELS[h.reason][0]})",
        f"{ar}: {n} ({h.hold_no}، {ref.HOLD_LABELS[h.reason][1]})",
        h.project_id,
        EntityType.fitness_hold,
        h.id,
    )
    users = alerts.reps(db, h.project_id, h.engagement_id) | _live_receivers(db, h)
    alerts.send(
        db,
        users,
        K.fitness_hold_created,
        f"{en}: {n} ({h.hold_no})",
        f"{ar}: {n} ({h.hold_no})",
        h.project_id,
        EntityType.fitness_hold,
        h.id,
    )


def _live_receivers(db: Session, h: FitnessHold) -> set[uuid.UUID]:
    from app.core.ptw_enums import PermitStatus  # noqa: PLC0415
    from app.models import Permit, PermitCrew  # noqa: PLC0415

    live = (PermitStatus.issued, PermitStatus.active, PermitStatus.suspended)
    rows = db.scalars(
        select(Permit.receiver_user_id)
        .join(PermitCrew, PermitCrew.permit_id == Permit.id)
        .where(PermitCrew.worker_id == h.worker_id, Permit.status.in_(live))
    )
    return {x for x in rows if x is not None}


def create_manual(
    db: Session, p: Principal, project_id: uuid.UUID, body: FitnessHoldCreate
) -> FitnessHoldRead:
    common.visible_project(db, p, project_id)
    g = p.require(project_id, C.fitness_hold_manage)
    dep = common.open_deployment(db, body.worker_id, project_id)
    if not common.covers_dep(g, dep):
        raise forbidden_error()
    text = common.reason(body.reason_text, 20, "reason_text")
    h = create_hold(
        db,
        p,
        body.worker_id,
        project_id,
        HoldReason.manual,
        HoldSourceType.manual,
        None,
        None,
        text,
    )
    out = hold_read(db, p, h, common.tier(p, project_id, dep))
    return out


# ---- reads ---------------------------------------------------------------------------------------


def list_holds(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[HoldStatus] | None,
    worker_id: uuid.UUID | None,
    with_work_during_hold: bool | None,
) -> FitnessHoldPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.fitness_functional_view)
    if g is None:
        raise forbidden_error()
    stmt = (
        select(FitnessHold)
        .where(FitnessHold.project_id == project_id)
        .order_by(FitnessHold.started_at.desc())
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(FitnessHold.engagement_id.in_(g.engagement_ids or {uuid.UUID(int=0)}))
    if status:
        stmt = stmt.where(FitnessHold.status.in_(status))
    if worker_id is not None:
        stmt = stmt.where(FitnessHold.worker_id == worker_id)
    if with_work_during_hold is not None:
        cond = FitnessHold.work_during_hold != []
        stmt = stmt.where(cond if with_work_during_hold else ~cond)
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for h in rows:
        t = common.tier(p, project_id, common.deployment(db, h.worker_id, project_id))
        if t >= 2:
            items.append(hold_read(db, p, h, t))
    common.sensitive_read(db, p, EntityType.fitness_hold, None, project_id, ["hold"])
    return FitnessHoldPage(items=items, total=total, page=page, page_size=page_size)


def read_hold(db: Session, p: Principal, hold_id: uuid.UUID) -> FitnessHoldRead:
    h = db.get(FitnessHold, hold_id)
    if h is None:
        raise deny(db, p, EntityType.fitness_hold, hold_id, None, "Fitness hold")
    t = _hold_visible(db, p, h)
    fields = ["hold"] + (["hold_reason"] if t >= 3 else [])
    common.sensitive_read(db, p, EntityType.fitness_hold, h.id, h.project_id, fields)
    return hold_read(db, p, h, t)


# ---- cancel / release (FH-3, FH-4) ---------------------------------------------------------------


def _cancel(
    db: Session,
    p: Principal | None,
    h: FitnessHold,
    at: datetime,
    code: HoldCancelCode | None,
    text: str | None,
) -> None:
    before = common.snap(h)
    h.status = HS.cancelled
    h.cancelled_at = at
    h.cancel_code = code
    h.cancel_reason_enc = common.enc(text)
    h.cancelled_by_user_id = p.user.id if p else None
    db.flush()
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.fitness_hold,
        h,
        h.project_id,
        before,
        {"to": "cancelled", "code": code.value if code else None},
    )
    _publish(db, h.worker_id)


def cancel_hold(
    db: Session, p: Principal, hold_id: uuid.UUID, body: FitnessHoldCancel
) -> FitnessHoldRead:
    h = db.get(FitnessHold, hold_id)
    if h is None:
        raise deny(db, p, EntityType.fitness_hold, hold_id, None, "Fitness hold")
    t = _hold_visible(db, p, h)
    p.ensure_writer()
    if not can_cancel(p, h.project_id):
        raise forbidden_error()
    if h.status != HS.active:
        raise invalid_transition("Fitness hold", h.status, HS.cancelled)
    _cancel(db, p, h, now(), None, common.reason(body.reason, 20))
    return hold_read(db, p, h, t)


def release_hold(db: Session, p: Principal, hold_id: uuid.UUID) -> FitnessHoldRead:
    h = db.get(FitnessHold, hold_id)
    if h is None:
        raise deny(db, p, EntityType.fitness_hold, hold_id, None, "Fitness hold")
    _hold_visible(db, p, h)
    raise ApiError(
        422,
        ErrorCode.HOLD_RELEASE_REQUIRES_ASSESSMENT,
        "A hold is released only by an accepted fitness assessment (FH-3).",
        "يُرفع الإيقاف فقط بتقييم لياقة مقبول.",
    )


def on_assessment_accepted(db: Session, a: FitnessAssessment) -> None:
    """FH-3 release and RF-4 referral assessed."""
    lines = {
        ln.code: ln
        for ln in db.scalars(select(FitnessLine).where(FitnessLine.assessment_id == a.id))
    }
    gen = lines.get(ref.GEN)
    at = a.accepted_at or now()
    ref_row = db.get(FitnessReferral, a.related_referral_id) if a.related_referral_id else None
    if (
        a.assessment_type == AssessmentType.referral
        and ref_row is not None
        and ref_row.status == RS.open
        and ref_row.worker_id == a.worker_id
    ):
        ref_row.status = RS.assessed
        ref_row.assessment_id = a.id
        ref_row.assessed_at = at
    hold_ids = {a.related_hold_id} if a.related_hold_id else set()
    if ref_row is not None and ref_row.hold_id is not None:
        hold_ids.add(ref_row.hold_id)
    for hid in hold_ids:
        h = db.get(FitnessHold, hid)
        if h is None or h.status != HS.active or h.worker_id != a.worker_id or gen is None:
            continue
        ok_type = (
            a.assessment_type == AssessmentType.return_to_work
            and h.reason
            in (HoldReason.rtw_after_injury, HoldReason.heat_illness, HoldReason.manual)
        ) or (
            a.assessment_type == AssessmentType.referral
            and h.reason in (HoldReason.referral, HoldReason.manual)
        )
        if not ok_type or a.examined_on < common.local_day(h.started_at):
            continue
        before = common.snap(h)
        h.status = HS.released
        h.released_at = at
        h.release_assessment_id = a.id
        _rtw_check(db, h)
        db.flush()
        common.record(
            db,
            None,
            AuditAction.status_change,
            EntityType.fitness_hold,
            h,
            h.project_id,
            before,
            {"to": "released", "assessment": a.assessment_no},
        )
        if (
            h.reason == HoldReason.rtw_after_injury
            and gen.outcome == FitnessOutcome.fit_with_restrictions
        ):
            _restricted_days_prompt(db, h)
        _publish(db, h.worker_id)
        from app.services.heat import plans as heat_plans  # noqa: PLC0415

        heat_plans.on_hold_released(db, h)  # 6b AP-1c
    from app.services.heat import plans as heat_plans  # noqa: PLC0415

    heat_plans.on_assessment(db, a.worker_id)  # 6b AP-6
    db.flush()


def _restricted_days_prompt(db: Session, h: FitnessHold) -> None:
    """RW-3: prompt only; the case is never changed."""
    c = db.get(InjuryCase, h.source_id) if h.source_id else None
    if c is None:
        return
    inc = db.get(Incident, c.incident_id)
    case_no = f"{inc.ref}-P{c.person_no}" if inc else h.source_ref or ""
    users = set(alerts.officers(db, h.project_id))
    alerts.send(
        db,
        users,
        K.fitness_restricted_days_prompt,
        f"Check whether restricted-work days apply to case {case_no} (OSHA 1904.7(b)(4))",
        f"تحقق من أيام العمل المقيد للحالة {case_no}",
        h.project_id,
        EntityType.injury_case,
        c.id,
        email=False,
    )


# ---- injury cases (FH-1a, FH-4, RW-2, FH-8c) -----------------------------------------------------


def _case_ref(db: Session, c: InjuryCase) -> str:
    inc = db.get(Incident, c.incident_id)
    return f"{inc.ref}-P{c.person_no}" if inc else str(c.id)[:8]


def _case_hold(db: Session, c: InjuryCase) -> FitnessHold | None:
    return db.scalar(
        select(FitnessHold).where(
            FitnessHold.source_type == HoldSourceType.injury_case, FitnessHold.source_id == c.id
        )
    )


def _trigger(db: Session, c: InjuryCase) -> HoldReason | None:
    s = common.settings(db, c.project_id)
    heat = c.nature.value in (s.heat_illness_natures or [])
    if heat:
        return HoldReason.heat_illness
    if c.category.value in (s.rtw_hold_case_categories or []):
        return HoldReason.rtw_after_injury
    return None


def on_case(db: Session, c: InjuryCase, p: Principal | None = None) -> list[ApiWarning]:
    """Called after an injury case is created / changed / confirmed (Phase 1 §11.2)."""
    s = common.settings(db, c.project_id)
    if s.medical_register_from is None:
        return []
    inc = db.get(Incident, c.incident_id)
    voided = inc is not None and inc.status.value == "voided"
    draft = inc is None or inc.status.value == "draft"
    h = _case_hold(db, c)
    at = now()
    if h is not None and h.status == HS.active:
        if voided or c.worker_id is None or c.worker_id != h.worker_id:
            _cancel(db, p, h, at, HoldCancelCode.source_voided, None)
        elif _trigger(db, c) is None:
            _cancel(db, p, h, at, HoldCancelCode.source_reclassified, None)
    if h is None and not voided and not draft and c.worker_id is not None:
        reason = _trigger(db, c)
        if reason is not None and common.deployment(db, c.worker_id, c.project_id) is not None:
            h = create_hold(
                db,
                p,
                c.worker_id,
                c.project_id,
                reason,
                HoldSourceType.injury_case,
                c.id,
                _case_ref(db, c),
                at=at,
            )
    warnings: list[ApiWarning] = []
    if (
        h is not None
        and c.rtw_date is not None
        and h.status != HS.cancelled
        and (
            h.status == HS.active
            or (h.released_at is not None and c.rtw_date < common.local_day(h.released_at))
        )
    ):
        warnings.append(
            ApiWarning(
                code=ErrorCode.RTW_BEFORE_CLEARANCE.value,
                message="The return-to-work date is before the worker was cleared by the "
                "occupational health practitioner.",
                message_ar="تاريخ العودة للعمل يسبق اعتماد لياقة العامل.",
                field="rtw_date",
            )
        )
        if _rtw_check(db, h):
            alerts.send(
                db,
                alerts.oh(db, h.project_id) | alerts.managers(db),
                K.fitness_rtw_before_clearance,
                f"Return to work recorded before clearance: {alerts.wno(db, h.worker_id)} "
                f"({h.hold_no})",
                f"عودة للعمل قبل الاعتماد: {alerts.wno(db, h.worker_id)}",
                h.project_id,
                EntityType.fitness_hold,
                h.id,
            )
    return warnings


def _rtw_check(db: Session, h: FitnessHold) -> bool:
    """FH-8c: rtw_date < local date of released_at (or the hold still active) → append once."""
    if h.source_type != HoldSourceType.injury_case or h.source_id is None:
        return False
    c = db.get(InjuryCase, h.source_id)
    if c is None or c.rtw_date is None:
        return False
    if h.released_at is not None and c.rtw_date >= common.local_day(h.released_at):
        return False
    if any(
        x["event_type"] == WorkDuringHoldType.rtw_before_clearance.value
        for x in h.work_during_hold or []
    ):
        return False
    at = common.noon(c.rtw_date)
    h.work_during_hold = [
        *(h.work_during_hold or []),
        {
            "event_type": WorkDuringHoldType.rtw_before_clearance.value,
            "ref": h.source_ref,
            "at": at.isoformat(),
        },
    ]
    db.flush()
    return True


def on_incident_status(db: Session, inc: Incident, p: Principal | None = None) -> None:
    from app.services.heat import log as heat_log  # noqa: PLC0415

    for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id)):
        on_case(db, c, p)
        heat_log.on_case(db, c)  # 6b HI-1 / §4.4


# ---- work during hold (FH-8) ---------------------------------------------------------------------


def _active_holds(db: Session, worker_id: uuid.UUID, at: datetime) -> list[FitnessHold]:
    return [
        h
        for h in db.scalars(
            select(FitnessHold).where(
                FitnessHold.worker_id == worker_id, FitnessHold.status == HS.active
            )
        )
        if h.started_at <= at
    ]


def _detect(
    db: Session, worker_id: uuid.UUID, kind: WorkDuringHoldType, ref_: str | None, at: datetime
) -> None:
    for h in _active_holds(db, worker_id, at):
        h.work_during_hold = [
            *(h.work_during_hold or []),
            {"event_type": kind.value, "ref": ref_, "at": at.isoformat()},
        ]
        db.flush()
        n = alerts.wno(db, worker_id)
        alerts.send(
            db,
            alerts.oh(db, h.project_id) | alerts.managers(db) | alerts.officers(db, h.project_id),
            K.fitness_work_during_hold,
            f"Work during a fitness hold detected: {n} ({h.hold_no})",
            f"تم رصد عمل أثناء إيقاف اللياقة: {n} ({h.hold_no})",
            h.project_id,
            EntityType.fitness_hold,
            h.id,
        )


def detect_gate(db: Session, row: Any) -> None:
    """FH-8a: an `in` check GRANTED / GRANTED_WITH_WARNING, or admitted despite denial."""
    if row.worker_id is None or row.direction != GateDirection.in_ or not row.final:
        return
    if row.result in LIVE_GATE or row.admitted_despite_denial:
        from app.models import Gate  # noqa: PLC0415

        g = db.get(Gate, row.gate_id)
        ref_ = g.gate_code if g is not None else row.subject_ref
        _detect(db, row.worker_id, WorkDuringHoldType.gate_entry, ref_, row.occurred_at)
        from app.services.heat import plans as heat_plans  # noqa: PLC0415

        heat_plans.on_gate(db, row)  # 6b AP-4 worked day


def detect_crew(db: Session, permit_no: str, worker_ids: list[uuid.UUID], at: datetime) -> None:
    """FH-8b: the worker is in crew_present of a permit shift started during the hold."""
    for wid in worker_ids:
        _detect(db, wid, WorkDuringHoldType.crew_present, permit_no, at)


# ---- referrals (RF) ------------------------------------------------------------------------------


def _ref_visible(db: Session, p: Principal, r: FitnessReferral) -> int:
    t = common.tier(p, r.project_id, common.deployment(db, r.worker_id, r.project_id))
    if t < 2 and r.raised_by_user_id != p.user.id:
        raise deny(db, p, EntityType.fitness_referral, r.id, r.project_id, "Fitness referral")
    return max(t, 1)


def referral_read(
    db: Session, p: Principal | None, r: FitnessReferral, tier: int
) -> FitnessReferralRead:
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    at = now()
    h = db.get(FitnessHold, r.hold_id) if r.hold_id else None
    a = db.get(FitnessAssessment, r.assessment_id) if r.assessment_id else None
    out = FitnessReferralRead(
        id=r.id,
        tier=common.tier_enum(tier),
        referral_no=r.referral_no,
        worker=common.worker_ref(w, common.names(p, r.project_id)),
        project_id=r.project_id,
        status=r.status,
        remove_from_work=r.remove_from_work,
        raised_by=common.user_ref(db, r.raised_by_user_id),
        raised_at=r.raised_at,
        due_at=r.due_at,
        overdue=r.status == RS.open and at > r.due_at,
        assessed_at=r.assessed_at,
        on_time=(r.assessed_at <= r.due_at) if r.assessed_at else None,
    )
    if tier >= 2:
        out.hold_no = h.hold_no if h else None
        out.assessment_no = a.assessment_no if a else None
    if tier >= 3:
        out.reason = r.reason
        out.note = common.dec(r.note_enc)
        out.cancel_reason = common.dec(r.cancel_reason_enc)
    return out


def create_referral(
    db: Session, p: Principal, project_id: uuid.UUID, body: FitnessReferralCreate
) -> FitnessReferralRead:
    common.visible_project(db, p, project_id)
    g = p.require(project_id, C.fitness_referral_raise)
    w = common.worker(db, body.worker_id)
    dep = common.deployment(db, body.worker_id, project_id)
    if dep is None or not common.mobilised_on(dep, common.local_day()):
        raise validation_error("worker_id", "The worker is not mobilised on this project.")
    if not common.covers_dep(g, dep):
        raise forbidden_error("You may refer only workers in your scope (RF-2).")
    r = raise_referral(db, p, w.id, project_id, body.reason, body.note, body.remove_from_work)
    out = referral_read(db, p, r, max(1, common.tier(p, project_id, dep)))
    out.warnings = id_warnings(note=body.note)
    if body.reason == ReferralReason.heat_illness_episode:
        out.incident_draft_link = (
            f"/projects/{project_id}/incidents/new?type=injury_illness&illness=true"
            f"&worker_id={w.id}&referral={r.referral_no}"
        )
        out.warnings.append(
            ApiWarning(
                code=ErrorCode.INCIDENT_RECORD_EXPECTED.value,
                message="Record the heat-illness episode as a Phase 1 incident.",
                message_ar="سجّل نوبة الإجهاد الحراري كحادثة.",
                field="reason",
            )
        )
    return out


def raise_referral(
    db: Session,
    p: Principal | None,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    reason: ReferralReason,
    note: str | None,
    remove: bool,
    at: datetime | None = None,
    source_cert_id: uuid.UUID | None = None,
) -> FitnessReferral:
    at = at or now()
    s = common.settings(db, project_id)
    y = common.local_day(at).year
    seq = next_seq(db, FitnessReferral, project_id, y)
    dep = common.deployment(db, worker_id, project_id)
    r = FitnessReferral(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        referral_no=make_ref("MFR", _pcode(db, project_id), y, seq, 5),
        worker_id=worker_id,
        project_id=project_id,
        engagement_id=dep.engagement_id if dep else None,
        reason=reason,
        note_enc=common.enc(note),
        remove_from_work=remove,
        raised_by_user_id=p.user.id if p else None,
        raised_at=at,
        due_at=at + timedelta(hours=s.referral_assessment_hours),
        status=RS.open,
        source_cert_id=source_cert_id,
        alerts_sent=[],
    )
    cc.stamp(r, p, create=True)
    db.add(r)
    db.flush()
    common.record(db, p, AuditAction.create, EntityType.fitness_referral, r, project_id)
    if remove:
        h = create_hold(
            db,
            p,
            worker_id,
            project_id,
            HoldReason.referral,
            HoldSourceType.referral,
            r.id,
            r.referral_no,
            at=at,
        )
        r.hold_id = h.id
        db.flush()
    from app.services.heat import log as heat_log  # noqa: PLC0415

    heat_log.on_referral(db, r)  # 6b HI-2
    n = alerts.wno(db, worker_id)
    alerts.send(
        db,
        alerts.oh(db, project_id),
        K.fitness_referral_raised,
        f"Fitness referral {r.referral_no} for {n}, assess by {common.local_day(r.due_at)}",
        f"إحالة لياقة {r.referral_no} للعامل {n}",
        project_id,
        EntityType.fitness_referral,
        r.id,
    )
    return r


def list_referrals(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[ReferralStatus] | None,
    overdue: bool | None,
    worker_id: uuid.UUID | None,
) -> FitnessReferralPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.fitness_functional_view)
    stmt = (
        select(FitnessReferral)
        .where(FitnessReferral.project_id == project_id)
        .order_by(FitnessReferral.raised_at.desc())
    )
    if g is None:
        if p.grant(project_id, C.fitness_referral_raise) is None:
            raise forbidden_error()
        stmt = stmt.where(FitnessReferral.raised_by_user_id == p.user.id)
    elif g.engagement_ids is not None:
        stmt = stmt.where(
            or_(
                FitnessReferral.engagement_id.in_(g.engagement_ids or {uuid.UUID(int=0)}),
                FitnessReferral.raised_by_user_id == p.user.id,
            )
        )
    if status:
        stmt = stmt.where(FitnessReferral.status.in_(status))
    if overdue is not None:
        cond = (FitnessReferral.status == RS.open) & (FitnessReferral.due_at < now())
        stmt = stmt.where(cond if overdue else ~cond)
    if worker_id is not None:
        stmt = stmt.where(FitnessReferral.worker_id == worker_id)
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for r in rows:
        t = common.tier(p, project_id, common.deployment(db, r.worker_id, project_id))
        items.append(referral_read(db, p, r, max(1, t)))
    return FitnessReferralPage(items=items, total=total, page=page, page_size=page_size)


def read_referral(db: Session, p: Principal, referral_id: uuid.UUID) -> FitnessReferralRead:
    r = db.get(FitnessReferral, referral_id)
    if r is None:
        raise deny(db, p, EntityType.fitness_referral, referral_id, None, "Fitness referral")
    t = _ref_visible(db, p, r)
    if t >= 2:
        fields = ["referral"] + (["referral_reason", "referral_note"] if t >= 3 else [])
        common.sensitive_read(db, p, EntityType.fitness_referral, r.id, r.project_id, fields)
    return referral_read(db, p, r, t)


def cancel_referral(
    db: Session, p: Principal, referral_id: uuid.UUID, body: FitnessReferralCancel
) -> FitnessReferralRead:
    r = db.get(FitnessReferral, referral_id)
    if r is None:
        raise deny(db, p, EntityType.fitness_referral, referral_id, None, "Fitness referral")
    t = _ref_visible(db, p, r)
    p.ensure_writer()
    if r.status != RS.open:
        raise invalid_transition("Fitness referral", r.status, RS.cancelled)
    at = now()
    own = r.raised_by_user_id == p.user.id and not r.remove_from_work and at < r.due_at
    if not (own or can_cancel(p, r.project_id)):
        raise forbidden_error()
    text = common.reason(body.reason, 20)
    before = common.snap(r)
    r.status = RS.cancelled
    r.cancelled_at = at
    r.cancel_reason_enc = common.enc(text)
    r.cancelled_by_user_id = p.user.id
    db.flush()
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.fitness_referral,
        r,
        r.project_id,
        before,
        {"to": "cancelled"},
    )
    if r.hold_id:
        h = db.get(FitnessHold, r.hold_id)
        if h is not None and h.status == HS.active:
            _cancel(db, p, h, at, None, text)
    return referral_read(db, p, r, t)
