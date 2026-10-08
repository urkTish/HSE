# ruff: noqa: E501
"""Permit lifecycle (spec 3-ptw §4.1, §4.2, §5.1, §5.9, §5.9a): request → review → HSE review →
approve → issue → start, shift end / stop work / automatic suspension (SH-2), revalidation and
resume, receiver acceptance, closure, cancellation and the post-expiry check.

Every signing transition needs step-up re-authentication (PT-15) and stores a signature. Blocked
transitions answer 422 with code = the first blocker (DECISIONS #57)."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind, QrTokenStatus
from app.core.clock import now
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    NotificationKind,
    Role,
)
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import CaStatus
from app.core.ptw_enums import (
    CANCEL_REASONS,
    MANUAL_SUSPEND_REASONS,
    PERMIT_TERMINAL,
    ROUTINE_REASONS,
    AppointmentFunction,
    CrewLineStatus,
    ExemptionKind,
    Exposure,
    JsaStatus,
    PermitBlocker,
    PermitStatus,
    PermitType,
    ShiftEndType,
    SignaturePurpose,
    SimopsCheckTrigger,
    StatusReason,
    VoltageClass,
    WorkCondition,
)
from app.models import (
    Contractor,
    CorrectiveAction,
    Permit,
    PermitRecord,
    PermitShift,
    PermitSuspension,
    ProjectEngagement,
    PtwAppointment,
    PtwAudit,
    User,
)
from app.schemas.permits import (
    ApproveInput,
    AreaReviewInput,
    CancelInput,
    CloseInput,
    ClosureRequestInput,
    EndShiftInput,
    GasAlarmInput,
    HseReviewInput,
    IssueInput,
    PermitRead,
    PostExpiryCheckInput,
    ReceiverAcceptanceInput,
    ReceiverAcceptanceRead,
    RequestInput,
    ResumeInput,
    ReturnInput,
    RevalidateInput,
    ShiftStartFields,
    StartInput,
    SuspendInput,
    WindReadingInput,
)
from app.schemas.ptw_common import CoSignature
from app.services import audit, auth
from app.services.access import common as acommon
from app.services.hse_common import user_roles
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import checks, common, evaluation, rules
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

C = Capability
T = PermitType
S = PermitStatus
B = PermitBlocker

REQUEST_CODES = {B.JSA_MISSING, B.DOCUMENT_MISSING, B.ROLE_MISSING}
AREA_ROLES = {Role.hse_officer, Role.site_engineer, Role.permit_issuer}
REVALIDATE_REASONS = {StatusReason.shift_end, StatusReason.shift_lapsed}


# ---- small helpers -------------------------------------------------------------------------------


def _view(db: Session, p: Principal, permit: Permit) -> PermitRead:
    from app.services.ptw import views  # noqa: PLC0415

    return views.permit_read(db, p, permit)


def _audit(
    db: Session,
    p: Principal | None,
    permit: Permit,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(permit.project_id) if p else audit.SYSTEM,
        entity_type=EntityType.permit,
        entity_id=permit.id,
        project_id=permit.project_id,
        before=before,
        after=after,
        details=details,
    )


def _set_status(
    db: Session,
    p: Principal | None,
    permit: Permit,
    new: PermitStatus,
    *,
    reason: StatusReason | None = None,
    detail: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    before = {"status": permit.status.value}
    permit.status = new
    permit.status_reason = reason
    permit.status_detail = detail
    after: dict[str, Any] = {"status": new.value}
    if reason:
        after["status_reason"] = reason.value
    _audit(db, p, permit, AuditAction.status_change, before, after, details)


def invalid(permit: Permit, action: str) -> ApiError:
    return common.err(
        ErrorCode.INVALID_TRANSITION,
        f"{permit.permit_no} is {permit.status.value}: {action} is not possible.",
        f"التصريح {permit.permit_no} في حالة {permit.status.value}: لا يمكن تنفيذ الإجراء.",
        status=409,
    )


def _need(permit: Permit, action: str, *allowed: PermitStatus) -> None:
    if permit.status in PERMIT_TERMINAL:
        raise common.err(
            ErrorCode.PERMIT_READ_ONLY,
            f"{permit.permit_no} is {permit.status.value} and read-only (CL-7).",
            "التصريح مغلق للقراءة فقط.",
            status=409,
        )
    if permit.status not in allowed:
        raise invalid(permit, action)


def sod(en: str, ar: str = "تعارض في فصل المهام.") -> ApiError:
    return common.err(ErrorCode.SOD_CONFLICT, en, ar)


def _cap(p: Principal, permit: Permit, cap: Capability) -> None:
    acommon.require_cap(p, permit.project_id, cap, [permit.site_id], permit.engagement_id)


def _cap_site(p: Principal, permit: Permit, cap: Capability) -> None:
    """Capabilities held by client-side roles scoped to sites (no engagement scope)."""
    acommon.require_cap(p, permit.project_id, cap, [permit.site_id], None)


def _receiver_only(p: Principal, permit: Permit, what: str) -> None:
    if p.user.id != permit.receiver_user_id:
        raise forbidden_error(f"Only the named receiver {what} (capability 84).")


def _contractor_ok(db: Session, permit: Permit) -> None:
    """PT-6 on create / request / approve / issue / revalidate / resume."""
    con = acommon.engagement_contractor(db, permit.engagement_id)
    if con is not None:
        contractor_status_ok(con)


def contractor_status_ok(con: Contractor) -> None:
    """PT-6: suspended / blacklisted contractors block forward transitions."""
    if con.status == ContractorStatus.blacklisted:
        raise common.err(
            ErrorCode.CONTRACTOR_BLACKLISTED,
            f"{con.short_code} is blacklisted: its permits may only be closed or cancelled (PT-6).",
            f"المقاول {con.short_code} محظور: تصاريحه تُغلق أو تُلغى فقط.",
        )
    if con.status == ContractorStatus.suspended:
        raise common.err(
            ErrorCode.CONTRACTOR_SUSPENDED,
            f"{con.short_code} is suspended (PT-6).",
            f"المقاول {con.short_code} موقوف.",
        )


def employer_in_tree(db: Session, user: User | None, permit: Permit) -> bool:
    """PR-5 (b): the user is employed by the permit's contractor or an ancestor's contractor."""
    if user is None or user.employer_contractor_id is None:
        return False
    for eid in acommon.engagement_ancestors(db, permit.engagement_id):
        e = db.get(ProjectEngagement, eid)
        if e is not None and e.contractor_id == user.employer_contractor_id:
            return True
    return False


def issuer_sod(db: Session, permit: Permit, user_id: uuid.UUID) -> None:
    """PR-5 (a) (b) (c) (d) for the issuer."""
    if user_id == permit.receiver_user_id:
        raise sod(
            "The issuer cannot be the receiver (PR-5 a).", "لا يمكن أن يكون المُصدِر هو المستلم."
        )
    if employer_in_tree(db, db.get(User, user_id), permit):
        raise sod(
            "The issuer cannot be employed by the permit's contractor or its parent (PR-5 b).",
            "لا يمكن أن يكون المُصدِر من موظفي المقاول المنفذ أو المقاول الرئيسي.",
        )
    if user_id == permit.area_authority_user_id:
        raise sod(
            "The issuer cannot be the area authority (PR-5 c).",
            "لا يمكن أن يكون المُصدِر مسؤول المنطقة.",
        )
    if user_id == permit.hse_reviewer_user_id:
        raise sod(
            "The issuer cannot be the HSE reviewer (PR-5 d).",
            "لا يمكن أن يكون المُصدِر مراجع السلامة.",
        )


def require_issuer(db: Session, p: Principal, permit: Permit, at: datetime) -> PtwAppointment:
    """Capability 87 + an Active issuer appointment for every type and the site (PR-2), plus the
    issuer SoD rules. Any appointed issuer of the project may sign (PR-8)."""
    _cap_site(p, permit, C.permit_issue)
    if not p.is_manager and Role.permit_issuer not in user_roles(db, p.user.id, permit.project_id):
        raise forbidden_error("Only a permit issuer signs this step (PR-2).")
    issuer_sod(db, permit, p.user.id)
    a = evaluation.issuer_appointment(db, permit, p.user.id, evaluation.appointment_day(permit, at))
    if a is None:
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "You have no Active issuer appointment covering every work type and the site (PR-2).",
            "لا يوجد لديك تعيين مُصدِر ساري يغطي كل أنواع العمل والموقع.",
        )
    return a


def blocked(rows: list[dict[str, Any]]) -> ApiError:
    return common.blocked_error(rows)


def _refresh(db: Session, permit: Permit, at: datetime | None = None, simops: bool = False) -> None:
    evaluation.refresh(db, permit, run_simops=simops, at=at)


def _simops(db: Session, permit: Permit, trigger: SimopsCheckTrigger, at: datetime) -> None:
    from app.services.ptw import simops  # noqa: PLC0415

    simops.check(db, permit, trigger, at=at)


# ---- shifts --------------------------------------------------------------------------------------


def planned_end(db: Session, permit: Permit, at: datetime) -> datetime:
    """§3.13 / §6.5: min(started_at + ptw_shift_max_hours, end of the current window instance,
    valid_to_at)."""
    s = common.settings(db, permit.project_id)
    ends = [at + timedelta(hours=s.ptw_shift_max_hours), permit.valid_to_at]
    inst = common.current_instance(permit, at)
    if inst is not None:
        ends.append(inst[1])
    return min(ends)


def shifts_of(db: Session, permit_id: uuid.UUID) -> list[PermitShift]:
    return list(
        db.scalars(
            select(PermitShift)
            .where(PermitShift.permit_id == permit_id)
            .order_by(PermitShift.shift_no)
        )
    )


def open_shift(
    db: Session,
    permit: Permit,
    at: datetime,
    *,
    receiver_id: uuid.UUID,
    issuer_id: uuid.UUID,
    crew: list[uuid.UUID],
    ambient: Decimal | None,
    gas_test_id: uuid.UUID | None,
    end: datetime | None = None,
) -> PermitShift:
    n = db.scalar(select(func.max(PermitShift.shift_no)).where(PermitShift.permit_id == permit.id))
    f = facts_mod.compute(db, permit)
    s = PermitShift(
        id=uuid.uuid4(),
        permit_id=permit.id,
        project_id=permit.project_id,
        shift_no=int(n or 0) + 1,
        started_at=at,
        planned_end_at=end or planned_end(db, permit, at),
        receiver_user_id=receiver_id,
        issuer_user_id=issuer_id,
        gas_test_id=gas_test_id,
        ambient_temp_c=ambient,
        crew_present=list(crew),
        briefed=list(crew),
        pauses=[],
        gas_required=f.gas_required,
        alerts_sent=[],
    )
    db.add(s)
    db.flush()
    permit.current_shift_id = s.id
    from app.services.ptw import jsa  # noqa: PLC0415

    jsa.record_briefing(db, jsa.current_for_permit(db, permit), s.id, s.shift_no, crew, receiver_id)
    audit.record(
        db,
        AuditAction.create,
        audit.SYSTEM,
        entity_type=EntityType.permit_shift,
        entity_id=s.id,
        project_id=permit.project_id,
        after={
            "permit_no": permit.permit_no,
            "shift_no": s.shift_no,
            "planned_end_at": s.planned_end_at.isoformat(),
        },
    )
    return s


def close_shift(
    db: Session,
    permit: Permit,
    shift: PermitShift | None,
    at: datetime,
    end_type: ShiftEndType,
    *,
    overdue: bool = False,
) -> None:
    """Ends an open shift and fixes the K-66 flags (gas_required / gas_compliant)."""
    if shift is None or shift.ended_at is not None:
        return
    from app.services.ptw import gas  # noqa: PLC0415

    pauses = []
    for ps in shift.pauses or []:
        pauses.append(ps if ps.get("to") else {**ps, "to": at.isoformat()})
    shift.pauses = pauses
    end = max(at, shift.started_at)
    shift.ended_at = end
    shift.end_type = end_type
    f = facts_mod.compute(db, permit)
    shift.gas_required = f.gas_required
    if f.gas_required:
        s = f.settings
        shift.gas_compliant = gas.shift_compliant(
            db,
            permit,
            shift,
            f.interval,
            s.gas_pre_start_validity_minutes,
            s.gas_break_retest_minutes,
            end,
            overdue,
        )
    else:
        shift.gas_compliant = None
    audit.record(
        db,
        AuditAction.update,
        audit.SYSTEM,
        entity_type=EntityType.permit_shift,
        entity_id=shift.id,
        project_id=permit.project_id,
        after={
            "ended_at": end.isoformat(),
            "end_type": end_type.value,
            "gas_compliant": shift.gas_compliant,
        },
    )


def current_shift(db: Session, permit: Permit) -> PermitShift | None:
    return evaluation.current_shift(db, permit)


def open_pause(shift: PermitShift | None) -> dict[str, Any] | None:
    if shift is None:
        return None
    for ps in shift.pauses or []:
        if not ps.get("to"):
            return ps
    return None


def persons_inside(db: Session, permit_id: uuid.UUID) -> list[PermitRecord]:
    return [r for r in evaluation.records(db, permit_id, "entry_log") if r.out_at is None]


def entrants_inside_error(db: Session, permit: Permit) -> None:
    inside = persons_inside(db, permit.id)
    if inside:
        raise common.err(
            ErrorCode.ENTRANTS_INSIDE,
            f"The entry log shows {len(inside)} person(s) inside the confined space (CS-7).",
            f"سجل الدخول يظهر {len(inside)} شخص داخل المكان المحصور.",
            meta={"persons_inside": len(inside)},
        )


# ---- suspension (SH-1, SH-2) ---------------------------------------------------------------------


def suspend_now(
    db: Session,
    permit: Permit,
    reason: StatusReason,
    detail: str | None,
    *,
    by: Principal | None = None,
    source_ref: str | None = None,
    at: datetime | None = None,
    end_type: ShiftEndType = ShiftEndType.suspended,
) -> PermitSuspension:
    at = at or now()
    routine = reason in ROUTINE_REASONS
    shift = current_shift(db, permit)
    close_shift(db, permit, shift, at, end_type, overdue=reason == StatusReason.gas_retest_overdue)
    sp = PermitSuspension(
        id=uuid.uuid4(),
        permit_id=permit.id,
        project_id=permit.project_id,
        suspended_at=at,
        reason=reason,
        routine=routine,
        raised_by_user_id=by.user.id if by else None,
        detail=(detail or "")[:500] or None,
        auto_source_ref=(source_ref or "")[:60] or None,
    )
    db.add(sp)
    _set_status(
        db, by, permit, S.suspended, reason=reason, detail=detail, details={"auto": by is None}
    )
    permit.receiver_acceptance = None
    db.flush()
    rtext = ref.REASON_TEXT[reason]
    if reason == StatusReason.midday_ban:
        users = common.permit_people(db, permit)
        kind = NotificationKind.midday_ban
    elif routine:
        users = common.permit_people(db, permit)
        kind = NotificationKind.permit_suspended
    else:
        cse = T.confined_space.value in permit.work_types
        gas_reason = reason in (
            StatusReason.gas_test_failed,
            StatusReason.gas_alarm,
            StatusReason.gas_retest_overdue,
        )
        users = common.permit_people(
            db, permit, reps=True, officer=True, manager=cse and gas_reason
        )
        kind = NotificationKind.gas_test_failed if gas_reason else NotificationKind.permit_suspended
    common.tell(
        db,
        permit,
        users,
        kind,
        f"Suspended: {rtext[0]}" + (f" ({detail})" if detail else ""),
        f"تم الإيقاف: {rtext[1]}" + (f" ({detail})" if detail else ""),
    )
    return sp


def auto_suspend(
    db: Session,
    permit: Permit,
    reason: StatusReason,
    detail: str | None,
    source_ref: str | None,
    at: datetime | None = None,
) -> PermitSuspension | None:
    """SH-2 automatic suspension of an Issued/Active permit (system; within the request or the
    minute job)."""
    if permit.status not in (S.issued, S.active):
        return None
    return suspend_now(db, permit, reason, detail, source_ref=source_ref, at=at)


def back_to_reviewed(db: Session, p: Principal | None, permit: Permit, why: str) -> None:
    """JS-10 / PT-9: an Approved or Issued permit returns to Reviewed (approval must be repeated)."""
    if permit.status not in (S.approved, S.issued):
        return
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    permit.approved_at = None
    permit.issued_at = None
    permit.receiver_acceptance = None
    _set_status(db, p, permit, S.reviewed, details={"why": why})
    common.tell(
        db,
        permit,
        common.permit_people(db, permit),
        NotificationKind.permit_update,
        f"Returned to Reviewed: {why}",
        f"أعيد إلى حالة تمت المراجعة: {why}",
    )


def back_to_requested(db: Session, p: Principal | None, permit: Permit, why: str) -> None:
    """PT-13: a change of zones, location, types, windows, validity, equipment or key-role crew
    after Approve returns the permit to Requested and clears the reviews."""
    if permit.status not in (S.reviewed, S.approved, S.issued, S.suspended):
        return
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    permit.area_review = None
    permit.hse_review = None
    permit.reviewed_at = None
    permit.approved_at = None
    permit.issued_at = None
    permit.receiver_acceptance = None
    if permit.status == S.suspended:
        sp = evaluation.open_suspension(db, permit)
        if sp is not None:
            sp.resumed_at = now()
            sp.cause_cleared_text = f"Returned to Requested: {why}"[:500]
    _set_status(db, p, permit, S.requested, details={"why": why})
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, area=True),
        NotificationKind.permit_update,
        f"Returned to Requested for re-review: {why}",
        f"أعيد إلى حالة مطلوب لإعادة المراجعة: {why}",
    )


# ---- receiver acceptance (PT-15) -----------------------------------------------------------------


def record_receiver_acceptance(
    db: Session, p: Principal, permit_id: uuid.UUID, body: ReceiverAcceptanceInput
) -> ReceiverAcceptanceRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_receive)
    _receiver_only(p, permit, "accepts the permit")
    need = S.approved if body.purpose.value == "issue" else S.suspended
    _need(permit, f"receiver acceptance ({body.purpose.value})", need)
    common.require_reauth(db, p, permit.project_id)
    at = now()
    minutes = common.settings(db, permit.project_id).step_up_reauth_minutes
    s = common.sign(
        db, permit, SignaturePurpose.accept, "permit_receiver", user_id=p.user.id, at=at
    )
    until = at + timedelta(minutes=minutes)
    permit.receiver_acceptance = {
        "purpose": body.purpose.value,
        "signed_at": at.isoformat(),
        "valid_until": until.isoformat(),
        "signature_id": str(s.id),
        "user_id": str(p.user.id),
    }
    _audit(db, p, permit, AuditAction.update, None, {"receiver_acceptance": body.purpose.value})
    return ReceiverAcceptanceRead(purpose=body.purpose, signed_at=at, valid_until=until)


def _receiver_accepts(
    db: Session,
    p: Principal,
    permit: Permit,
    cosign: CoSignature | None,
    purpose: str,
    at: datetime,
    receiver_id: uuid.UUID | None = None,
) -> None:
    """The receiver accepts in the same step: a co-signature on this device or a receiver
    acceptance made on their own device within step_up_reauth_minutes."""
    rid = receiver_id or permit.receiver_user_id
    if cosign is not None:
        u = auth.check_cosigner(db, cosign.user_id, cosign.password)
        if u.id != rid:
            raise common.err(
                ErrorCode.COSIGNER_INVALID,
                "The co-signer must be the permit's receiver.",
                "يجب أن يكون الموقّع المشارك مستلم التصريح.",
                status=401,
            )
        common.sign(
            db,
            permit,
            SignaturePurpose.accept,
            "permit_receiver",
            user_id=u.id,
            co_device=p.user.id,
            at=at,
        )
        return
    ra = permit.receiver_acceptance or {}
    if (
        ra.get("purpose") == purpose
        and ra.get("user_id") == str(rid)
        and datetime.fromisoformat(ra["valid_until"]) >= at
    ):
        permit.receiver_acceptance = None
        return
    raise common.err(
        ErrorCode.TRANSITION_CONDITION_NOT_MET,
        "The receiver must accept: co-sign on this device or record an acceptance on their own device first.",
        "يجب أن يقبل المستلم: توقيع مشارك على هذا الجهاز أو تسجيل القبول من جهازه أولاً.",
        meta={"receiver_acceptance_required": True},
    )


# ---- request / return / reviews ------------------------------------------------------------------


def request(db: Session, p: Principal, permit_id: uuid.UUID, body: RequestInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_receive)
    _need(permit, "request", S.draft)
    _receiver_only(p, permit, "requests the permit")
    common.require_reauth(db, p, permit.project_id)
    at = now()
    _contractor_ok(db, permit)
    checks.for_request(db, permit, at)
    res = evaluation.evaluate(db, permit, evaluation.Ctx(at=at, evaluate_crew=False))
    rows = [b for b in res.blockers if B(b["code"]) in REQUEST_CODES]
    if rows:
        raise blocked(rows)
    permit.requested_at = at
    permit.first_requested_at = permit.first_requested_at or at
    permit.returned_comment = None
    _set_status(
        db, p, permit, S.requested, details={"comment": body.comment} if body.comment else None
    )
    common.sign(db, permit, SignaturePurpose.request, "permit_receiver", user_id=p.user.id, at=at)
    _simops(db, permit, SimopsCheckTrigger.request, at)
    _refresh(db, permit, at)
    common.tell(
        db,
        permit,
        [permit.area_authority_user_id] if permit.area_authority_user_id else [],
        NotificationKind.permit_requested,
        "Permit requested — area review needed",
        "تم طلب التصريح — مطلوب مراجعة مسؤول المنطقة",
    )
    return _view(db, p, permit)


def return_(db: Session, p: Principal, permit_id: uuid.UUID, body: ReturnInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _need(permit, "return", S.requested, S.reviewed)
    pid = permit.project_id
    ok = p.grant(pid, C.permit_issue) is not None
    if permit.status == S.requested:
        ok = ok or (
            p.grant(pid, C.permit_area_review) is not None
            and p.user.id == permit.area_authority_user_id
        )
    else:
        ok = ok or p.grant(pid, C.permit_hse_review) is not None
    if not ok:
        raise forbidden_error(
            "Only the area authority, an HSE reviewer or an issuer may return the permit."
        )
    p.ensure_writer()
    acommon.require_cap(
        p,
        pid,
        C.permit_issue
        if p.grant(pid, C.permit_issue)
        else (C.permit_area_review if permit.status == S.requested else C.permit_hse_review),
        [permit.site_id],
        None,
    )
    permit.returned_comment = body.comment
    permit.area_review = None
    permit.hse_review = None
    permit.reviewed_at = None
    _set_status(db, p, permit, S.draft, details={"comment": body.comment})
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, issuer=False, reps=True),
        NotificationKind.permit_update,
        f"Returned: {body.comment}",
        f"أعيد التصريح: {body.comment}",
    )
    _refresh(db, permit)
    return _view(db, p, permit)


def area_review(
    db: Session, p: Principal, permit_id: uuid.UUID, body: AreaReviewInput
) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_area_review)
    _need(permit, "review", S.requested)
    if p.user.id != permit.area_authority_user_id:
        raise forbidden_error("Only the named area authority reviews the permit (capability 85).")
    if p.user.id == permit.receiver_user_id:
        raise sod(
            "The area authority cannot be the receiver (PR-5 c).",
            "لا يمكن أن يكون مسؤول المنطقة هو المستلم.",
        )
    if p.user.id == permit.issuer_user_id:
        raise sod(
            "The area authority cannot be the issuer (PR-5 c).",
            "لا يمكن أن يكون مسؤول المنطقة هو المُصدِر.",
        )
    at = now()
    checks.area_authority_ok(db, permit, p.user.id, at)
    f = facts_mod.compute(db, permit)
    if f.airside and not body.wap_no_confirmed:
        raise validation_error(
            "wap_no_confirmed", "Airside zones: confirm the WAP number checked (PR-6)."
        )
    common.require_reauth(db, p, permit.project_id)
    permit.area_review = {
        "by_user_id": str(p.user.id),
        "at": at.isoformat(),
        "area_conditions_known": True,
        "simops_reviewed": True,
        "special_area_hazards": body.special_area_hazards,
        "wap_no_confirmed": body.wap_no_confirmed,
    }
    permit.reviewed_at = at
    _set_status(db, p, permit, S.reviewed)
    common.sign(db, permit, SignaturePurpose.review, "area_authority", user_id=p.user.id, at=at)
    _simops(db, permit, SimopsCheckTrigger.review, at)
    _refresh(db, permit, at)
    if permit.high_risk:
        users = [u for u in (permit.hse_reviewer_user_id, permit.issuer_user_id) if u]
        if not permit.hse_reviewer_user_id:
            users += common.officers(db, permit.project_id)
        common.tell(
            db,
            permit,
            users,
            NotificationKind.permit_reviewed,
            "High-risk permit reviewed — HSE review needed",
            "تمت مراجعة تصريح عالي الخطورة — مطلوب مراجعة السلامة",
        )
    return _view(db, p, permit)


def hse_review(db: Session, p: Principal, permit_id: uuid.UUID, body: HseReviewInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_hse_review)
    _need(permit, "HSE review", S.requested, S.reviewed)
    if permit.hse_reviewer_user_id and permit.hse_reviewer_user_id != p.user.id:
        raise forbidden_error("Only the named HSE reviewer reviews this permit.")
    if p.user.id in (permit.receiver_user_id, permit.issuer_user_id):
        raise sod(
            "The HSE reviewer cannot be the receiver or the issuer (PR-5 d).",
            "لا يمكن أن يكون مراجع السلامة هو المستلم أو المُصدِر.",
        )
    if not permit.high_risk and not facts_mod.compute(db, permit).high_risk_reasons:
        raise common.err(
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "The permit is not high-risk: no HSE review is needed (PT-9).",
            "التصريح ليس عالي الخطورة: لا حاجة لمراجعة السلامة.",
            status=409,
        )
    if body.decision == "returned" and (not body.comment or len(body.comment.strip()) < 10):
        raise validation_error("comment", "Give the reason for returning (at least 10 characters).")
    common.require_reauth(db, p, permit.project_id)
    at = now()
    permit.hse_reviewer_user_id = p.user.id
    if body.decision == "accepted":
        permit.hse_review = {
            "decision": "accepted",
            "by_user_id": str(p.user.id),
            "at": at.isoformat(),
            "comment": body.comment,
        }
        common.sign(
            db, permit, SignaturePurpose.hse_review, "hse_reviewer", user_id=p.user.id, at=at
        )
        _audit(db, p, permit, AuditAction.update, None, {"hse_review": "accepted"})
        if permit.issuer_user_id:
            common.tell(
                db,
                permit,
                [permit.issuer_user_id],
                NotificationKind.permit_reviewed,
                "HSE review accepted",
                "تم قبول مراجعة السلامة",
            )
    else:
        permit.hse_review = None
        permit.returned_comment = body.comment
        permit.area_review = None
        permit.reviewed_at = None
        _set_status(
            db, p, permit, S.draft, details={"hse_review": "returned", "comment": body.comment}
        )
        common.tell(
            db,
            permit,
            common.permit_people(db, permit, issuer=False, reps=True),
            NotificationKind.permit_update,
            f"Returned by HSE review: {body.comment}",
            f"أعيد من مراجعة السلامة: {body.comment}",
        )
    _refresh(db, permit, at)
    return _view(db, p, permit)


def exemption_needed(db: Session, permit: Permit, f: facts_mod.Facts) -> None:
    """EL-3 energized LV and LF-3 capacity > 90 % need a granted exemption (capability 102)."""
    if f.has(T.electrical_isolation):
        el = f.sec(T.electrical_isolation)
        if el.get("work_condition") == WorkCondition.energized.value:
            vc = rules.voltage_class(int(el.get("system_voltage_v") or 0), bool(el.get("dc")))
            if (
                vc != VoltageClass.hv
                and evaluation.exemption(db, permit, ExemptionKind.energized_work) is None
            ):
                raise common.err(
                    ErrorCode.EXEMPTION_REQUIRED,
                    "Energized work needs the HSE Manager's approval (EL-3).",
                    "العمل المكهرب يتطلب موافقة مدير الصحة والسلامة.",
                    meta={"kind": ExemptionKind.energized_work.value},
                )
    if (
        f.lift is not None
        and f.lift.capacity_pct > 90
        and evaluation.exemption(db, permit, ExemptionKind.lift_capacity_over_90) is None
    ):
        raise common.err(
            ErrorCode.EXEMPTION_REQUIRED,
            f"Lift at {f.lift.capacity_display} % of capacity needs the HSE Manager's approval (LF-3).",
            f"الرفع بنسبة {f.lift.capacity_display} % يتطلب موافقة مدير الصحة والسلامة.",
            meta={"kind": ExemptionKind.lift_capacity_over_90.value},
        )


def approve(db: Session, p: Principal, permit_id: uuid.UUID, body: ApproveInput) -> PermitRead:
    from app.services.ptw import jsa  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    _need(permit, "approve", S.reviewed)
    common.require_reauth(db, p, permit.project_id)
    at = now()
    appt = require_issuer(db, p, permit, at)
    _contractor_ok(db, permit)
    _simops(db, permit, SimopsCheckTrigger.approve, at)
    prev_issuer = permit.issuer_user_id
    permit.issuer_user_id = p.user.id
    res = evaluation.evaluate(db, permit, evaluation.Ctx(at=at))
    rows = res.approve_rows()
    if rows:
        permit.issuer_user_id = prev_issuer
        raise blocked(rows)
    exemption_needed(db, permit, res.facts)
    j = jsa.current_for_permit(db, permit)
    if j is not None and j.status == JsaStatus.submitted:
        jsa.approve(db, p, j, p.user.id)
    permit.approved_at = at
    _set_status(
        db, p, permit, S.approved, details={"comment": body.comment} if body.comment else None
    )
    common.sign(
        db,
        permit,
        SignaturePurpose.approve,
        "issuer",
        user_id=p.user.id,
        appointment_id=appt.id,
        at=at,
    )
    _refresh(db, permit, at)
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, issuer=False, reps=True),
        NotificationKind.permit_update,
        "Permit approved",
        "تم اعتماد التصريح",
    )
    return _view(db, p, permit)


# ---- issue / start -------------------------------------------------------------------------------


def receiver_limit(db: Session, permit: Permit) -> None:
    """PT-5: at most max_active_permits_per_receiver permits in Issued/Active."""
    limit = common.settings(db, permit.project_id).max_active_permits_per_receiver
    n = db.scalar(
        select(func.count())
        .select_from(Permit)
        .where(
            Permit.receiver_user_id == permit.receiver_user_id,
            Permit.status.in_([S.issued, S.active]),
            Permit.id != permit.id,
        )
    )
    if int(n or 0) >= limit:
        raise common.err(
            ErrorCode.RECEIVER_LIMIT,
            f"The receiver already holds {n} Issued/Active permits (limit {limit}, PT-5).",
            f"المستلم لديه {n} تصاريح صادرة/سارية (الحد {limit}).",
            meta={"limit": limit, "count": int(n or 0)},
        )


def _wind(body_w: WindReadingInput | None) -> Decimal | None:
    return Decimal(str(body_w.speed_ms)) if body_w is not None else None


def save_wind(
    db: Session, p: Principal | None, permit: Permit, w: WindReadingInput | None
) -> PermitRecord | None:
    if w is None:
        return None
    r = PermitRecord(
        id=uuid.uuid4(),
        permit_id=permit.id,
        kind="wind",
        at=w.measured_at,
        data={"speed_ms": str(w.speed_ms), "source": w.source.value, "source_ref": w.source_ref},
        recorded_by_user_id=p.user.id if p else None,
    )
    db.add(r)
    db.flush()
    return r


def copy_obs_conditions(db: Session, permit: Permit) -> None:
    """LF-9: conditions of the linked obstacle clearances are copied into the permit."""
    from app.models import ObstacleClearance  # noqa: PLC0415

    out = list(permit.copied_conditions or [])
    for oid in permit.linked_obs_ids or []:
        o = db.get(ObstacleClearance, oid)
        if o is None:
            continue
        for c in o.conditions or []:
            line = f"{o.obs_no}: {c}"
            if line not in out:
                out.append(line)
    permit.copied_conditions = out


def issue(db: Session, p: Principal, permit_id: uuid.UUID, body: IssueInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    _need(permit, "issue", S.approved)
    common.require_reauth(db, p, permit.project_id)
    at = now()
    appt = require_issuer(db, p, permit, at)
    _contractor_ok(db, permit)
    f = facts_mod.compute(db, permit)
    if f.has(T.lifting) and body.wind_reading is None:
        raise validation_error(
            "wind_reading", "A wind reading is required at Issue for lifting (LF-6)."
        )
    receiver_limit(db, permit)
    checks.key_roles_busy(db, permit)
    _simops(db, permit, SimopsCheckTrigger.issue, at)
    prev_issuer = permit.issuer_user_id
    permit.issuer_user_id = p.user.id
    res = evaluation.evaluate(
        db, permit, evaluation.Ctx(at=at, start=True, wind_ms=_wind(body.wind_reading))
    )
    if res.blockers:
        permit.issuer_user_id = prev_issuer
        raise blocked(res.blockers)
    exemption_needed(db, permit, res.facts)
    _receiver_accepts(db, p, permit, body.receiver_cosign, "issue", at)
    if body.conditions_en is not None:
        permit.conditions_en = body.conditions_en
    if body.conditions_ar is not None:
        permit.conditions_ar = body.conditions_ar
    copy_obs_conditions(db, permit)
    save_wind(db, p, permit, body.wind_reading)
    permit.issued_at = at
    permit.first_issued_at = permit.first_issued_at or at
    _set_status(db, p, permit, S.issued, details={"site_visit_confirmed": True})
    common.sign(
        db,
        permit,
        SignaturePurpose.issue,
        "issuer",
        user_id=p.user.id,
        appointment_id=appt.id,
        at=at,
    )
    if acommon.active_qr(db, permit.id) is None:
        acommon.issue_qr(db, QrKind.PT, permit.project_id, permit.id, permit.permit_no)
    evaluation.store(permit, res)
    _refresh(db, permit, at)
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, issuer=False, reps=True),
        NotificationKind.permit_update,
        "Permit issued — start work within the issue-to-start time",
        "تم إصدار التصريح — ابدأ العمل خلال المهلة المحددة",
    )
    return _view(db, p, permit)


@dataclass
class ShiftCheck:
    at: datetime
    planned_end: datetime
    crew: list[uuid.UUID]
    gas_test_id: uuid.UUID | None
    result: evaluation.Result


def excavation_inspected(db: Session, permit: Permit, at: datetime) -> bool:
    """EX-6: a `safe` competent-person inspection for this shift — after the previous shift
    ended, within ptw_shift_max_hours before `at`, and no later `unsafe` result."""
    rows = [
        r
        for r in evaluation.records(db, permit.id, "excavation_inspection")
        if r.at <= at + timedelta(minutes=5)
    ]
    if not rows:
        return False
    last = rows[-1]
    if last.data.get("result") != "safe":
        return False
    s = common.settings(db, permit.project_id)
    if last.at < at - timedelta(hours=s.ptw_shift_max_hours):
        return False
    ended = [x.ended_at for x in shifts_of(db, permit.id) if x.ended_at is not None]
    return not (ended and last.at < max(ended))


def heat_controls_missing(db: Session, permit: Permit, f: facts_mod.Facts) -> bool:
    """HT-6: CSE internal temperature (latest gas test) ≥ cse_heat_control_temp_c needs heat
    controls on the permit."""
    if not f.has(T.confined_space):
        return False
    from app.services.ptw import gas  # noqa: PLC0415

    temps = [
        t.internal_temp_c for t in gas.tests_of(db, permit.id) if t.internal_temp_c is not None
    ]
    if not temps or Decimal(str(temps[-1])) < f.settings.cse_heat_control_temp_c:
        return False
    hc = f.sec(T.confined_space).get("heat_controls") or {}
    return not (
        hc.get("forced_cool_air_ventilation")
        and hc.get("water_at_entry")
        and hc.get("stay_time_max_minutes")
    )


def shift_checks(
    db: Session,
    permit: Permit,
    body: ShiftStartFields,
    at: datetime,
    *,
    gas_after: datetime | None = None,
    window: bool = True,
    gas_start: bool = False,
) -> ShiftCheck:
    """Start / revalidate / resume / handover checks (DECISIONS: OUTSIDE_WINDOW first, then the
    blockers, then INSPECTION_REQUIRED and the other errors)."""
    from app.services.ptw import gas  # noqa: PLC0415

    if window and (at >= permit.valid_to_at or common.current_instance(permit, at) is None):
        nxt = common.next_instance(permit, at)
        fb = facts_mod.compute(db, permit)
        ban = evaluation.in_ban_now(fb, at)
        if (
            ban is not None
            and evaluation.exemption(db, permit, ExemptionKind.midday_ban, ban) is None
        ):
            # Y5: inside the ban hours the ban is the reason, even between split windows.
            raise common.err(
                ErrorCode.MIDDAY_BAN,
                "The midday ban is in force: outdoor work may restart when it ends (HT-1).",
                "حظر العمل وقت الظهيرة ساري: يُستأنف العمل الخارجي بعد انتهائه.",
                meta={"next_window_start": nxt[0].isoformat() if nxt else None},
            )
        raise common.err(
            ErrorCode.OUTSIDE_WINDOW,
            "Now is outside the permit's work windows (PT-12)."
            + (
                f" Next window starts {acommon.local(nxt[0]).strftime('%Y-%m-%d %H:%M')}."
                if nxt
                else ""
            ),
            "الوقت الحالي خارج فترات العمل المسموحة للتصريح.",
            meta={"next_window_start": nxt[0].isoformat() if nxt else None},
        )
    f = facts_mod.compute(db, permit)
    if (
        permit.exposure in (Exposure.outdoor_direct_sun, Exposure.outdoor_shaded)
        and body.ambient_temp_c is None
    ):
        raise validation_error(
            "ambient_temp_c", "Record the ambient temperature for outdoor work (HT-5)."
        )
    if f.has(T.lifting) and body.wind_reading is None:
        raise validation_error("wind_reading", "A wind reading is required for lifting (LF-6).")
    lines = {x.worker_id: x for x in evaluation.crew_lines(db, permit.id)}
    ids: list[uuid.UUID] = []
    for i, c in enumerate(body.crew_present):
        if c.worker_id not in lines:
            raise validation_error(
                f"crew_present.{i}.worker_id", "This worker is not on the permit's crew."
            )
        if c.worker_id in ids:
            raise validation_error(f"crew_present.{i}.worker_id", "A worker is listed twice.")
        ids.append(c.worker_id)
    end = planned_end(db, permit, at)
    res = evaluation.evaluate(
        db,
        permit,
        evaluation.Ctx(
            at=at,
            start=True,
            crew_present=ids,
            wind_ms=_wind(body.wind_reading),
            shift_end=end,
            gas_after=gas_after,
        ),
    )
    rows = list(res.blockers)
    gt = None
    if f.gas_required:
        gt = gas.valid_for_start(
            db, permit, at, f.settings.gas_pre_start_validity_minutes, after=gas_after
        )
        if gas_start and gt is None:
            rows.append(common.blocker_json(B.GAS_TEST_EXPIRED))
    if rows:
        raise blocked(rows)
    unbriefed = [c.worker_id for c in body.crew_present if not c.briefed]
    if unbriefed:
        raise common.err(
            ErrorCode.CREW_NOT_BRIEFED,
            f"{len(unbriefed)} worker(s) in crew present are not briefed for this shift (SH-4).",
            f"{len(unbriefed)} من الطاقم الحاضر لم يتلقوا التوعية لهذه الوردية.",
            meta={"worker_ids": [str(w) for w in unbriefed]},
        )
    for i, wid in enumerate(ids):
        x = lines[wid]
        db.refresh(x)
        if x.status == CrewLineStatus.excluded:
            raise common.err(
                ErrorCode.VALIDATION_ERROR,
                f"{evaluation.worker_no(db, wid)} is excluded ({x.excluded_reason}) and cannot be present.",
                "عضو الطاقم مستبعد ولا يمكن إدراجه ضمن الحاضرين.",
                field=f"crew_present.{i}.worker_id",
            )
    if f.has(T.excavation) and not excavation_inspected(db, permit, at):
        raise common.err(
            ErrorCode.INSPECTION_REQUIRED,
            "Record today's competent-person excavation inspection before the shift starts (EX-6).",
            "سجّل فحص الحفرية من الشخص الكفء قبل بدء الوردية.",
        )
    if heat_controls_missing(db, permit, f):
        raise common.err(
            ErrorCode.HEAT_CONTROLS_REQUIRED,
            "Internal temperature needs heat controls on the permit before entry (HT-6).",
            "درجة الحرارة الداخلية تتطلب ضوابط إجهاد حراري قبل الدخول.",
        )
    return ShiftCheck(
        at=at, planned_end=end, crew=ids, gas_test_id=gt.id if gt else None, result=res
    )


def start(db: Session, p: Principal, permit_id: uuid.UUID, body: StartInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_receive)
    _need(permit, "start", S.issued)
    _receiver_only(p, permit, "starts work")
    at = now()
    s = common.settings(db, permit.project_id)
    assert permit.issued_at is not None  # noqa: S101
    if at > permit.issued_at + timedelta(minutes=s.issue_to_start_max_minutes):
        raise common.err(
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            f"Work was not started within {s.issue_to_start_max_minutes} min of issue; the permit must be issued again.",
            "لم يبدأ العمل خلال المهلة بعد الإصدار؛ يجب إصدار التصريح مجدداً.",
            status=409,
        )
    _simops(db, permit, SimopsCheckTrigger.start, at)
    chk = shift_checks(db, permit, body, at)
    save_wind(db, p, permit, body.wind_reading)
    assert permit.issuer_user_id is not None  # noqa: S101
    open_shift(
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
    permit.started_at = permit.started_at or at
    _set_status(db, p, permit, S.active)
    evaluation.store(permit, chk.result)
    _refresh(db, permit, at)
    return _view(db, p, permit)


# ---- end shift / suspend / gas alarm --------------------------------------------------------------


def end_shift(db: Session, p: Principal, permit_id: uuid.UUID, body: EndShiftInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_receive)
    _need(permit, "end shift", S.active)
    sh = current_shift(db, permit)
    if p.user.id not in (permit.receiver_user_id, sh.receiver_user_id if sh else None):
        raise forbidden_error("Only the shift's receiver ends the shift (capability 84).")
    entrants_inside_error(db, permit)
    suspend_now(
        db, permit, StatusReason.shift_end, body.note, by=p, end_type=ShiftEndType.shift_end
    )
    _refresh(db, permit)
    return _view(db, p, permit)


def suspend(db: Session, p: Principal, permit_id: uuid.UUID, body: SuspendInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_suspend)
    _need(permit, "stop work", S.issued, S.active)
    if body.reason not in MANUAL_SUSPEND_REASONS:
        raise validation_error(
            "reason", "Choose stop_work, weather, emergency, gas_alarm, isolation_breach or other."
        )
    suspend_now(db, permit, body.reason, body.detail, by=p)
    _refresh(db, permit)
    return _view(db, p, permit)


def gas_alarm(db: Session, p: Principal, permit_id: uuid.UUID, body: GasAlarmInput) -> PermitRead:
    """GT-7: a continuous-monitor alarm suspends the permit (gas_alarm) like a failed test."""
    permit = common.get_permit(db, p, permit_id)
    if p.grant(permit.project_id, C.permit_receive) is None:
        _cap(p, permit, C.permit_suspend)
    else:
        _cap(p, permit, C.permit_receive)
    _need(permit, "gas alarm", S.issued, S.active)
    suspend_now(db, permit, StatusReason.gas_alarm, body.detail or "Continuous monitor alarm", by=p)
    _refresh(db, permit)
    return _view(db, p, permit)


# ---- revalidate / resume -------------------------------------------------------------------------


def _audit_ca_in_progress(db: Session, sp: PermitSuspension) -> bool:
    """SH-3: after audit_critical the linked CA must be at least In Progress."""
    if not sp.auto_source_ref:
        return True
    a = db.scalar(select(PtwAudit).where(PtwAudit.audit_no == sp.auto_source_ref))
    if a is None:
        return True
    cas = list(db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == a.id)))
    if not cas:
        return False
    return all(c.status not in (CaStatus.open,) for c in cas)


def _start_after_suspension(
    db: Session,
    p: Principal,
    permit: Permit,
    body: RevalidateInput | ResumeInput,
    purpose: SignaturePurpose,
    trigger: SimopsCheckTrigger,
    cause: str | None,
) -> PermitRead:
    at = now()
    appt = require_issuer(db, p, permit, at)
    _contractor_ok(db, permit)
    sp = evaluation.open_suspension(db, permit)
    s = common.settings(db, permit.project_id)
    gas_after = None
    if sp is not None and at - sp.suspended_at >= timedelta(minutes=s.gas_break_retest_minutes):
        gas_after = sp.suspended_at
    _simops(db, permit, trigger, at)
    chk = shift_checks(db, permit, body, at, gas_after=gas_after, gas_start=True)
    _receiver_accepts(db, p, permit, body.receiver_cosign, purpose.value, at)
    save_wind(db, p, permit, body.wind_reading)
    if sp is not None:
        sp.resumed_at = at
        sp.resumed_by_user_id = p.user.id
        sp.resume_gas_test_id = chk.gas_test_id
        sp.cause_cleared_text = cause
    permit.issuer_user_id = p.user.id
    open_shift(
        db,
        permit,
        at,
        receiver_id=permit.receiver_user_id,
        issuer_id=p.user.id,
        crew=chk.crew,
        ambient=body.ambient_temp_c,
        gas_test_id=chk.gas_test_id,
        end=chk.planned_end,
    )
    _set_status(
        db, p, permit, S.active, details={"site_visit_confirmed": True, purpose.value: True}
    )
    common.sign(db, permit, purpose, "issuer", user_id=p.user.id, appointment_id=appt.id, at=at)
    evaluation.store(permit, chk.result)
    _refresh(db, permit, at)
    return _view(db, p, permit)


def revalidate(
    db: Session, p: Principal, permit_id: uuid.UUID, body: RevalidateInput
) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    _need(permit, "revalidate", S.suspended)
    if permit.status_reason not in REVALIDATE_REASONS:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "Revalidation follows a shift end or shift lapse; use Resume for other suspensions.",
            "إعادة التفعيل بعد نهاية الوردية فقط؛ استخدم الاستئناف لغيرها.",
            status=409,
        )
    if T.radiography.value in permit.work_types:
        raise common.err(
            ErrorCode.REVALIDATION_NOT_ALLOWED,
            "Radiography permits cannot be revalidated: a new permit is needed (SH-7).",
            "لا يمكن إعادة تفعيل تصاريح التصوير الإشعاعي: يلزم تصريح جديد.",
        )
    common.require_reauth(db, p, permit.project_id)
    return _start_after_suspension(
        db, p, permit, body, SignaturePurpose.revalidate, SimopsCheckTrigger.revalidate, None
    )


def resume(db: Session, p: Principal, permit_id: uuid.UUID, body: ResumeInput) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    _need(permit, "resume", S.suspended)
    reason = permit.status_reason
    if reason in REVALIDATE_REASONS:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "After a shift end or lapse the permit is revalidated, not resumed (SH-7).",
            "بعد نهاية الوردية يُعاد تفعيل التصريح وليس استئنافه.",
            status=409,
        )
    con = acommon.engagement_contractor(db, permit.engagement_id)
    if reason == StatusReason.contractor_blacklisted or (
        con is not None and con.status == ContractorStatus.blacklisted
    ):
        _contractor_ok(db, permit)
    routine = reason in ROUTINE_REASONS
    cause = (body.cause_cleared_text or "").strip()
    if not routine and len(cause) < 20:
        raise common.err(
            ErrorCode.CAUSE_NOT_CLEARED,
            "Record how the cause of the suspension was cleared (at least 20 characters, SH-3).",
            "سجّل كيف تمت إزالة سبب الإيقاف (20 حرفاً على الأقل).",
            field="cause_cleared_text",
        )
    sp = evaluation.open_suspension(db, permit)
    if (
        reason == StatusReason.audit_critical
        and sp is not None
        and not _audit_ca_in_progress(db, sp)
    ):
        raise common.err(
            ErrorCode.CAUSE_NOT_CLEARED,
            "The corrective action of the critical audit finding must be at least In Progress (SH-3).",
            "يجب أن يكون الإجراء التصحيحي للمخالفة الحرجة قيد التنفيذ على الأقل.",
        )
    common.require_reauth(db, p, permit.project_id)
    return _start_after_suspension(
        db, p, permit, body, SignaturePurpose.resume, SimopsCheckTrigger.resume, cause or None
    )


# ---- closure (CL-1, CL-2) ------------------------------------------------------------------------


def _locks_of_permit(db: Session, permit: Permit) -> list[Any]:
    from app.services.ptw import isolations  # noqa: PLC0415

    crew = {x.worker_id for x in evaluation.crew_lines(db, permit.id, include_removed=True)}
    out = []
    for c in isolations.certs_of(db, permit):
        for e in isolations.active_personal_locks(db, c.lockbox_id):
            if e.permit_id == permit.id or (e.permit_id is None and e.worker_id in crew):
                out.append(e)
    return out


def fire_watch_until(permit: Permit) -> datetime | None:
    hw = (permit.sections or {}).get(T.hot_work.value) or {}
    v = hw.get("fire_watch_until")
    return datetime.fromisoformat(v) if v else None


def fod_ok(db: Session, permit: Permit, f: facts_mod.Facts) -> bool:
    from app.models import Wap  # noqa: PLC0415

    if (permit.fod_check or {}).get("result") == "clear":
        return True
    w = evaluation.linked_wap(db, permit, f, now())
    if w is not None and (w.fod_check or {}).get("result") == "clear":
        fc = w.fod_check or {}
        at = fc.get("checked_at")
        return not (at and permit.started_at and datetime.fromisoformat(at) < permit.started_at)
    _ = Wap
    return False


def request_closure(
    db: Session, p: Principal, permit_id: uuid.UUID, body: ClosureRequestInput
) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_receive)
    _need(permit, "request closure", S.issued, S.active, S.suspended)
    _receiver_only(p, permit, "requests closure")
    if body.work_status.value == "incomplete_area_safe" and not body.remaining_work:
        raise validation_error(
            "remaining_work", "Describe what remains and how the area was made safe (CL-1)."
        )
    gaps = evaluation.checklist_gaps(db, permit, "closure")
    if gaps:
        raise common.err(
            ErrorCode.CHECKLIST_INCOMPLETE,
            "Answer the closure checklist first: " + ", ".join(gaps),
            "أكمل قائمة الإغلاق أولاً: " + ", ".join(gaps),
            meta={"items": gaps},
        )
    entrants_inside_error(db, permit)
    items: list[str] = []
    if _locks_of_permit(db, permit):
        items.append("X-04 personal locks still applied")
    if T.hot_work.value in permit.work_types and not fire_watch_until(permit):
        items.append("hot_work_ended_at not recorded")
    if items:
        raise common.err(
            ErrorCode.CLOSURE_INCOMPLETE,
            "Closure incomplete: " + "; ".join(items),
            "الإغلاق غير مكتمل: " + "; ".join(items),
            meta={"items": items},
        )
    at = now()
    close_shift(db, permit, current_shift(db, permit), at, ShiftEndType.closed)
    permit.closure_request = {
        "requested_by_user_id": str(p.user.id),
        "requested_at": at.isoformat(),
        "work_status": body.work_status.value,
        "remaining_work": body.remaining_work,
    }
    _audit(db, p, permit, AuditAction.update, None, {"closure_request": body.work_status.value})
    common.tell(
        db,
        permit,
        [permit.issuer_user_id] if permit.issuer_user_id else [],
        NotificationKind.permit_update,
        "Closure requested — issuer site inspection needed",
        "تم طلب الإغلاق — مطلوب فحص المُصدِر للموقع",
    )
    _refresh(db, permit, at)
    return _view(db, p, permit)


def close(db: Session, p: Principal, permit_id: uuid.UUID, body: CloseInput) -> PermitRead:
    from app.services.ptw import isolations, simops  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    _need(permit, "close", S.issued, S.active, S.suspended)
    common.require_reauth(db, p, permit.project_id)
    at = now()
    appt = require_issuer(db, p, permit, at)
    if permit.closure_request is None:
        raise common.err(
            ErrorCode.CLOSURE_INCOMPLETE,
            "The receiver has not requested closure (CL-1).",
            "لم يطلب المستلم الإغلاق بعد.",
            meta={"items": ["closure request"]},
        )
    fw = fire_watch_until(permit)
    if fw is not None and at < fw:
        raise common.err(
            ErrorCode.FIRE_WATCH_RUNNING,
            f"The fire watch runs until {acommon.local(fw).strftime('%H:%M')} (HW-4).",
            f"مراقبة الحريق مستمرة حتى {acommon.local(fw).strftime('%H:%M')}.",
            meta={"fire_watch_until": fw.isoformat()},
        )
    entrants_inside_error(db, permit)
    f = facts_mod.compute(db, permit)
    if f.movement_area and (
        not fod_ok(db, permit, f) or not f.sec(T.airside_works).get("ops_handback_ref")
    ):
        raise common.err(
            ErrorCode.FOD_HANDBACK_REQUIRED,
            "A FOD check 'clear' and the operations hand-back reference are required before closure (AW-8).",
            "مطلوب فحص أجسام غريبة بنتيجة سليمة ومرجع التسليم للعمليات قبل الإغلاق.",
        )
    items: list[str] = []
    gaps = evaluation.checklist_gaps(db, permit, "closure")
    items += gaps
    if f.has(T.radiography):
        sr = permit.source_return or {}
        if not sr or Decimal(str(sr.get("survey_usv_h", "0"))) > 2 * Decimal(
            str(sr.get("background_usv_h", "0"))
        ):
            items.append("X-11 source returned and verified")
    if _locks_of_permit(db, permit):
        items.append("X-04 personal locks still applied")
    if items:
        raise common.err(
            ErrorCode.CLOSURE_INCOMPLETE,
            "Closure incomplete: " + "; ".join(items),
            "الإغلاق غير مكتمل: " + "; ".join(items),
            meta={"items": items},
        )
    close_shift(db, permit, current_shift(db, permit), at, ShiftEndType.closed)
    sp = evaluation.open_suspension(db, permit)
    if sp is not None:
        sp.resumed_at = at
        sp.cause_cleared_text = "Closed"
    permit.closed_at = at
    permit.ended_at = at
    _set_status(db, p, permit, S.closed, details={"site_visit_confirmed": True, "note": body.note})
    common.sign(
        db,
        permit,
        SignaturePurpose.close,
        "issuer",
        user_id=p.user.id,
        appointment_id=appt.id,
        at=at,
    )
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    simops.close_for(db, permit, at)
    still = [
        c.iso_no
        for c in isolations.certs_of(db, permit)
        if c.status.value in ("isolated", "verified", "deisolation_requested")
    ]
    if still:
        permit.warnings = [
            {"code": "ISOLATIONS_STILL_APPLIED", "detail": ", ".join(still), "ref": still[0]}
        ]
    else:
        permit.warnings = []
    permit.blockers = []
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, reps=True),
        NotificationKind.permit_update,
        "Permit closed",
        "تم إغلاق التصريح",
    )
    return _view(db, p, permit)


# ---- cancel / post-expiry ------------------------------------------------------------------------


def cancel(db: Session, p: Principal, permit_id: uuid.UUID, body: CancelInput) -> PermitRead:
    from app.services.ptw import simops  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    _cap(p, permit, C.permit_cancel)
    allowed = [S.draft, S.requested, S.reviewed, S.approved, S.issued]
    if permit.status == S.suspended and permit.status_reason == StatusReason.contractor_blacklisted:
        allowed.append(S.suspended)
    _need(permit, "cancel", *allowed)
    roles = user_roles(db, p.user.id, permit.project_id)
    client_side = p.is_manager or bool(roles & {Role.hse_officer, Role.permit_issuer})
    if not client_side and (
        p.user.id != permit.receiver_user_id or permit.status not in (S.draft, S.requested)
    ):
        raise forbidden_error(
            "A receiver may cancel only their own Draft or Requested permit (capability 89 C1)."
        )
    if body.reason not in CANCEL_REASONS:
        raise validation_error(
            "reason",
            "Choose rejected, not_required, duplicate, contractor_suspended, contractor_blacklisted or other.",
        )
    if permit.status in (S.issued, S.suspended) and not body.site_visit_confirmed:
        raise validation_error(
            "site_visit_confirmed", "Confirm the site visit: the area is left safe (PT-14)."
        )
    common.require_reauth(db, p, permit.project_id)
    at = now()
    close_shift(db, permit, current_shift(db, permit), at, ShiftEndType.closed)
    sp = evaluation.open_suspension(db, permit)
    if sp is not None:
        sp.resumed_at = at
        sp.cause_cleared_text = "Cancelled"
    permit.ended_at = at
    _set_status(db, p, permit, S.cancelled, reason=body.reason, detail=body.detail)
    common.sign(db, permit, SignaturePurpose.cancel, "canceller", user_id=p.user.id, at=at)
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    simops.close_for(db, permit, at)
    permit.blockers = []
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, reps=True),
        NotificationKind.permit_update,
        f"Permit cancelled ({body.reason.value})",
        f"تم إلغاء التصريح ({ref.REASON_TEXT[body.reason][1]})",
    )
    return _view(db, p, permit)


def post_expiry_check(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PostExpiryCheckInput
) -> PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _cap_site(p, permit, C.permit_issue)
    if permit.status != S.expired:
        raise invalid(permit, "post-expiry check")
    if permit.post_expiry_check is not None:
        raise common.err(
            ErrorCode.DUPLICATE_VALUE,
            "The post-expiry check is already recorded.",
            "تم تسجيل الفحص بالفعل.",
            status=409,
        )
    if not common.appointments_of(
        db, permit.project_id, AppointmentFunction.issuer, user_id=p.user.id
    ):
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "Only an appointed issuer of the project records the post-expiry check (CL-6).",
            "فحص ما بعد الانتهاء يسجله مُصدِر معيّن في المشروع فقط.",
        )
    if not body.area_safe:
        ca = db.get(CorrectiveAction, body.ca_id) if body.ca_id else None
        if ca is None or ca.project_id != permit.project_id:
            raise common.err(
                ErrorCode.CA_REQUIRED,
                "Area not safe: raise a corrective action first and give its id (CL-6).",
                "المنطقة غير آمنة: أنشئ إجراءً تصحيحياً أولاً.",
                field="ca_id",
            )
    at = now()
    permit.post_expiry_check = {
        "checked_by_user_id": str(p.user.id),
        "checked_at": at.isoformat(),
        "site_visit_confirmed": True,
        "area_safe": body.area_safe,
        "area_note": body.area_note,
        "entrants_zero": body.entrants_zero,
        "personal_locks_removed": body.personal_locks_removed,
        "fire_watch_status": body.fire_watch_status,
        "ca_id": str(body.ca_id) if body.ca_id else None,
    }
    permit.warnings = [
        w for w in permit.warnings or [] if w.get("code") != "POST_EXPIRY_CHECK_PENDING"
    ]
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"post_expiry_check": {"area_safe": body.area_safe}},
    )
    return _view(db, p, permit)


# ---- job transitions -----------------------------------------------------------------------------


def lapse_issue(db: Session, permit: Permit, at: datetime) -> None:
    """Issued → Approved when not started within issue_to_start_max_minutes."""
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    permit.issued_at = None
    permit.receiver_acceptance = None
    _set_status(db, None, permit, S.approved, details={"issue_lapsed": True})
    common.tell(
        db,
        permit,
        common.permit_people(db, permit),
        NotificationKind.permit_issue_lapsed,
        "Issue lapsed: work not started in time — issue again",
        "انقضى الإصدار: لم يبدأ العمل في الوقت المحدد — يلزم إصدار جديد",
    )


def lapse_shift(db: Session, permit: Permit, shift: PermitShift, at: datetime) -> None:
    """SH-5: a shift reaching planned_end_at without end-shift, accepted handover or closure."""
    end = min(at, shift.planned_end_at)
    if permit.status == S.active:
        suspend_now(
            db,
            permit,
            StatusReason.shift_lapsed,
            f"Shift {shift.shift_no} reached its planned end without hand-over or end-shift",
            at=end,
            end_type=ShiftEndType.lapsed,
        )
    else:
        close_shift(db, permit, shift, end, ShiftEndType.lapsed)
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, reps=True, officer=True),
        NotificationKind.shift_lapsed,
        f"Shift {shift.shift_no} lapsed without hand-over",
        f"انقضت الوردية {shift.shift_no} دون تسليم",
    )


def expire(db: Session, permit: Permit, at: datetime) -> None:
    """§4.1 / CL-5: Approved/Issued/Active/Suspended past valid_to_at → Expired."""
    from app.services.ptw import simops  # noqa: PLC0415

    sh = current_shift(db, permit)
    if sh is not None:
        close_shift(
            db, permit, sh, min(at, max(permit.valid_to_at, sh.started_at)), ShiftEndType.expired
        )
    sp = evaluation.open_suspension(db, permit)
    if sp is not None:
        sp.resumed_at = at
        sp.cause_cleared_text = "Expired"
    needs_check = (
        permit.status in (S.issued, S.active, S.suspended) or permit.started_at is not None
    )
    permit.ended_at = at
    acommon.end_qr(db, permit.id, QrTokenStatus.revoked)
    _set_status(db, None, permit, S.expired)
    simops.close_for(db, permit, at)
    permit.blockers = []
    if needs_check:
        permit.warnings = [{"code": "POST_EXPIRY_CHECK_PENDING", "detail": None, "ref": None}]
    else:
        permit.warnings = []
        permit.post_expiry_check = {"not_required": True, "checked_at": at.isoformat()}
    common.tell(
        db,
        permit,
        common.permit_people(db, permit, officer=True),
        NotificationKind.permit_expired,
        "Permit expired — post-expiry check pending" if needs_check else "Permit expired",
        "انتهى التصريح — فحص ما بعد الانتهاء معلق" if needs_check else "انتهى التصريح",
    )


def post_expiry_pending(permit: Permit) -> bool:
    return permit.status == S.expired and permit.post_expiry_check is None
