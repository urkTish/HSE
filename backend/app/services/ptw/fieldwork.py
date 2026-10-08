# ruff: noqa: E501
"""Phase 3 field work on live permits: pauses (SH-9), handovers (SH-6), field records (HW-4,
CS-7, LF-6/WH-7, EX-6, RG-3/RG-5, AW-8) and exemptions (PT-17)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ErrorCode, validation_error
from app.core.ptw_enums import (
    PERMIT_TERMINAL,
    AppointmentDiscipline,
    AppointmentFunction,
    CrewLineStatus,
    EntryDirection,
    ExcavationInspectionResult,
    ExemptionKind,
    ExemptionStatus,
    Exposure,
    HandoverStatus,
    PermitStatus,
    PermitType,
    PtwCrewRole,
    ShiftEndType,
    SignaturePurpose,
    StatusReason,
    VoltageClass,
    WorkCondition,
)
from app.models import (
    Permit,
    PermitCrew,
    PermitExemption,
    PermitHandover,
    PermitRecord,
    PtwAppointment,
    User,
    Worker,
)
from app.schemas import permits as sch
from app.services import audit, auth, notify
from app.services.access import common as acommon
from app.services.hse_common import Refs, user_roles
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import checks, common, evaluation, lifecycle, rules, views
from app.services.ptw import facts as facts_mod

C = Capability
T = PermitType
S = PermitStatus

PAUSE_MAX = timedelta(hours=2)
HANDOVER_LEAD = timedelta(minutes=60)
ONE_HANDOVER = {T.hot_work.value, T.confined_space.value}
FUTURE_SLACK = timedelta(minutes=5)


def _audit(
    db: Session,
    p: Principal | None,
    permit: Permit,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    entity_type: EntityType = EntityType.permit,
    entity_id: uuid.UUID | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(permit.project_id) if p else audit.SYSTEM,
        entity_type=entity_type,
        entity_id=entity_id or permit.id,
        project_id=permit.project_id,
        before=before,
        after=after,
    )


def _not_future(at: datetime, field: str) -> None:
    if at > now() + FUTURE_SLACK:
        raise validation_error(field, "The time cannot be in the future.")


def _need_type(permit: Permit, t: PermitType, what: str) -> None:
    if t.value not in (permit.work_types or []):
        raise common.err(
            ErrorCode.VALIDATION_ERROR,
            f"{what} applies to {t.value} permits only.",
            "هذا السجل لا ينطبق على نوع هذا التصريح.",
        )


def _field_cap(p: Principal, permit: Permit) -> None:
    """Field records: the receiver side (84) or the issuer side (87) in scope."""
    pid = permit.project_id
    if p.grant(pid, C.permit_receive) is not None:
        acommon.require_cap(p, pid, C.permit_receive, [permit.site_id], permit.engagement_id)
    else:
        acommon.require_cap(p, pid, C.permit_issue, [permit.site_id], None)


def _live(permit: Permit, what: str, *allowed: PermitStatus) -> None:
    lifecycle._need(permit, what, *(allowed or (S.issued, S.active, S.suspended)))


def _shift_receiver(db: Session, p: Principal, permit: Permit, what: str) -> Any:
    lifecycle._cap(p, permit, C.permit_receive)
    sh = lifecycle.current_shift(db, permit)
    if p.user.id not in (permit.receiver_user_id, sh.receiver_user_id if sh else None):
        raise forbidden_error(f"Only the shift's receiver {what} (capability 84).")
    return sh


def _set_section(permit: Permit, t: PermitType, values: dict[str, Any]) -> None:
    secs = dict(permit.sections or {})
    cur = dict(secs.get(t.value) or {})
    cur.update(values)
    secs[t.value] = cur
    permit.sections = secs


# ---- pauses (SH-9) -------------------------------------------------------------------------------


def start_pause(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.PauseStartInput
) -> sch.PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _live(permit, "pause", S.active)
    sh = _shift_receiver(db, p, permit, "records a pause")
    if sh is None:
        raise lifecycle.invalid(permit, "pause")
    if lifecycle.open_pause(sh) is not None:
        raise common.err(
            ErrorCode.PAUSE_NOT_ALLOWED,
            "A pause is already open on this shift.",
            "يوجد توقف مفتوح بالفعل في هذه الوردية.",
            status=409,
        )
    at = now()
    if at >= sh.planned_end_at:
        raise common.err(
            ErrorCode.PAUSE_NOT_ALLOWED,
            "The shift has reached its planned end: end the shift or hand over instead (SH-9).",
            "بلغت الوردية نهايتها: أنهِ الوردية أو سلّمها بدلاً من التوقف.",
        )
    if T.confined_space.value in permit.work_types:
        lifecycle.entrants_inside_error(db, permit)
    sh.pauses = [
        *(sh.pauses or []),
        {
            "from": at.isoformat(),
            "to": None,
            "reason": body.reason.value,
            "note": body.note,
        },
    ]
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"pause_started": at.isoformat(), "reason": body.reason.value},
        entity_type=EntityType.permit_shift,
        entity_id=sh.id,
    )
    lifecycle._refresh(db, permit, at)
    return lifecycle._view(db, p, permit)


def end_pause(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.PauseEndInput
) -> sch.PermitRead:
    from app.services.ptw import gas  # noqa: PLC0415

    permit = common.get_permit(db, p, permit_id)
    _live(permit, "end pause", S.active)
    sh = _shift_receiver(db, p, permit, "ends a pause")
    ps = lifecycle.open_pause(sh)
    if sh is None or ps is None:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "There is no open pause on the current shift.",
            "لا يوجد توقف مفتوح في الوردية الحالية.",
            status=409,
        )
    at = now()
    started = datetime.fromisoformat(ps["from"])
    if at - started > PAUSE_MAX or at >= sh.planned_end_at:
        raise common.err(
            ErrorCode.PAUSE_NOT_ALLOWED,
            "The pause lasted more than 2 h or reached the shift end: end the shift or suspend the permit instead (SH-9).",
            "تجاوز التوقف ساعتين أو بلغ نهاية الوردية: أنهِ الوردية أو أوقف التصريح.",
            meta={"paused_since": started.isoformat()},
        )
    f = facts_mod.compute(db, permit)
    s = f.settings
    if f.gas_required:
        long_pause = at - started >= timedelta(minutes=s.gas_break_retest_minutes)
        st = gas.state(db, permit, f.interval, True, at)
        due = st.next_due_at is not None and at >= st.next_due_at
        if (long_pause or due) and gas.valid_for_start(
            db, permit, at, s.gas_pre_start_validity_minutes, after=started if long_pause else None
        ) is None:
            raise common.err(
                ErrorCode.GAS_TEST_EXPIRED,
                f"The pause lasted ≥ {s.gas_break_retest_minutes} min: record a passing post-break gas test before work restarts (GT-4)."
                if long_pause
                else "The periodic gas test fell due during the pause: record a passing test before work restarts (GT-4).",
                "سجّل فحص غاز ناجح قبل استئناف العمل بعد التوقف.",
            )
    pauses = []
    for x in sh.pauses or []:
        y = x
        if x.get("from") == ps["from"] and not x.get("to"):
            y = {**x, "to": at.isoformat()}
            if body.note:
                y["note"] = ((x.get("note") or "") + " " + body.note).strip()[:300]
        pauses.append(y)
    sh.pauses = pauses
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"pause_ended": at.isoformat()},
        entity_type=EntityType.permit_shift,
        entity_id=sh.id,
    )
    lifecycle._refresh(db, permit, at)
    return lifecycle._view(db, p, permit)


# ---- handovers (SH-6) ----------------------------------------------------------------------------


def _handover(db: Session, p: Principal, handover_id: uuid.UUID) -> tuple[PermitHandover, Permit]:
    h = db.get(PermitHandover, handover_id)
    if h is None:
        raise common.err(
            ErrorCode.NOT_FOUND, "Handover not found.", "التسليم غير موجود.", status=404
        )
    permit = common.get_permit(db, p, h.permit_id)
    return h, permit


def handovers_count(db: Session, permit_id: uuid.UUID) -> int:
    return sum(1 for h in views.handovers_of(db, permit_id) if h.status == HandoverStatus.accepted)


def list_handovers(db: Session, p: Principal, permit_id: uuid.UUID) -> sch.HandoverList:
    permit = common.get_permit(db, p, permit_id)
    refs = Refs(db)
    return sch.HandoverList(
        items=[views.handover_read(db, h, refs) for h in views.handovers_of(db, permit.id)]
    )


def _issuer_ok(db: Session, permit: Permit, user_id: uuid.UUID, at: datetime) -> None:
    if Role.permit_issuer not in user_roles(db, user_id, permit.project_id):
        raise validation_error("to_issuer_user_id", "The incoming issuer must be a permit issuer.")
    if (
        evaluation.issuer_appointment(db, permit, user_id, evaluation.appointment_day(permit, at))
        is None
    ):
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "The incoming issuer has no Active issuer appointment covering every work type and the site (PR-2).",
            "لا يوجد لدى المُصدِر المستلم تعيين ساري يغطي كل أنواع العمل والموقع.",
            field="to_issuer_user_id",
        )


def _incoming_sod(
    db: Session, permit: Permit, receiver_id: uuid.UUID, issuer_id: uuid.UUID
) -> None:
    """PR-5 for the incoming pair, evaluated as if the incoming receiver held the permit."""
    old = permit.receiver_user_id
    permit.receiver_user_id = receiver_id
    try:
        lifecycle.issuer_sod(db, permit, issuer_id)
        if receiver_id in (permit.area_authority_user_id, permit.hse_reviewer_user_id):
            raise lifecycle.sod(
                "The incoming receiver cannot be the area authority or HSE reviewer (PR-5).",
            )
    finally:
        permit.receiver_user_id = old


def create_handover(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.HandoverCreate
) -> sch.HandoverRead:
    permit = common.get_permit(db, p, permit_id)
    _live(permit, "handover", S.active)
    sh = _shift_receiver(db, p, permit, "initiates a handover")
    if sh is None:
        raise lifecycle.invalid(permit, "handover")
    at = now()
    if at < sh.planned_end_at - HANDOVER_LEAD:
        raise common.err(
            ErrorCode.HANDOVER_TOO_EARLY,
            f"A handover may be initiated at most 60 min before the shift's planned end ({acommon.local(sh.planned_end_at).strftime('%H:%M')}).",
            "يمكن بدء التسليم قبل 60 دقيقة كحد أقصى من نهاية الوردية.",
            meta={"earliest_at": (sh.planned_end_at - HANDOVER_LEAD).isoformat()},
        )
    if at >= sh.planned_end_at:
        raise lifecycle.invalid(permit, "handover after the shift's planned end")
    if ONE_HANDOVER & set(permit.work_types) and handovers_count(db, permit.id) >= 1:
        raise common.err(
            ErrorCode.HANDOVER_LIMIT,
            "Hot work and confined-space permits allow at most one handover (§3.1, SH-6).",
            "تصاريح الأعمال الساخنة والأماكن المحصورة تسمح بتسليم واحد فقط.",
        )
    if any(h.status == HandoverStatus.initiated for h in views.handovers_of(db, permit.id)):
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "A handover is already awaiting acceptance.",
            "يوجد تسليم بانتظار القبول.",
            status=409,
        )
    lifecycle.entrants_inside_error(db, permit)
    checks.receiver_ok(db, permit, body.to_receiver_user_id, "to_receiver_user_id")
    _issuer_ok(db, permit, body.to_issuer_user_id, at)
    _incoming_sod(db, permit, body.to_receiver_user_id, body.to_issuer_user_id)
    h = PermitHandover(
        id=uuid.uuid4(),
        permit_id=permit.id,
        from_shift_id=sh.id,
        from_receiver_user_id=sh.receiver_user_id,
        to_receiver_user_id=body.to_receiver_user_id,
        to_issuer_user_id=body.to_issuer_user_id,
        initiated_at=at,
        deadline_at=sh.planned_end_at,
        status=HandoverStatus.initiated,
        notes_en=body.notes_en,
        notes_ar=body.notes_ar,
    )
    db.add(h)
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.create,
        None,
        {
            "permit_no": permit.permit_no,
            "shift_no": sh.shift_no,
            "to_receiver_user_id": str(body.to_receiver_user_id),
            "to_issuer_user_id": str(body.to_issuer_user_id),
        },
        entity_type=EntityType.permit_handover,
        entity_id=h.id,
    )
    common.tell(
        db,
        permit,
        {body.to_receiver_user_id, body.to_issuer_user_id},
        NotificationKind.permit_update,
        f"Handover of {permit.permit_no} awaits your acceptance before {acommon.local(sh.planned_end_at).strftime('%H:%M')}",
        f"تسليم التصريح {permit.permit_no} بانتظار قبولك",
    )
    return views.handover_read(db, h, Refs(db))


def lapse_handover(db: Session, h: PermitHandover, at: datetime) -> None:
    permit = db.get(Permit, h.permit_id)
    h.status = HandoverStatus.lapsed
    if permit is not None:
        _audit(
            db,
            None,
            permit,
            AuditAction.status_change,
            {"status": "initiated"},
            {"status": "lapsed"},
            entity_type=EntityType.permit_handover,
            entity_id=h.id,
        )


def accept_handover(
    db: Session, p: Principal, handover_id: uuid.UUID, body: sch.HandoverAcceptInput
) -> sch.PermitRead:
    h, permit = _handover(db, p, handover_id)
    _live(permit, "accept handover", S.active)
    if h.status != HandoverStatus.initiated:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            f"This handover is {h.status.value}.",
            "هذا التسليم ليس بانتظار القبول.",
            status=409,
        )
    at = now()
    if at >= h.deadline_at:
        lapse_handover(db, h, at)
        raise common.err(
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "The handover was not accepted before the shift's planned end (SH-6).",
            "لم يُقبل التسليم قبل نهاية الوردية.",
            status=409,
        )
    uid = p.user.id
    if uid == h.to_receiver_user_id:
        lifecycle._cap(p, permit, C.permit_receive)
        mine, other, other_label = "receiver", h.to_issuer_user_id, "issuer"
    elif uid == h.to_issuer_user_id:
        lifecycle._cap_site(p, permit, C.permit_issue)
        mine, other, other_label = "issuer", h.to_receiver_user_id, "receiver"
    else:
        raise forbidden_error(
            "Only the incoming receiver or the incoming issuer accepts a handover."
        )
    common.require_reauth(db, p, permit.project_id)
    _issuer_ok(db, permit, h.to_issuer_user_id, at)
    checks.receiver_ok(db, permit, h.to_receiver_user_id, "to_receiver_user_id")
    _incoming_sod(db, permit, h.to_receiver_user_id, h.to_issuer_user_id)
    co: User | None = None
    if body.cosign is not None:
        co = auth.check_cosigner(db, body.cosign.user_id, body.cosign.password)
        if co.id != other:
            raise common.err(
                ErrorCode.COSIGNER_INVALID,
                f"The co-signer must be the incoming {other_label}.",
                "الموقّع المشارك يجب أن يكون الطرف المستلم الآخر.",
                status=401,
            )
    signed = {
        "receiver": h.receiver_signed_at is not None,
        "issuer": h.issuer_signed_at is not None,
    }
    signed[mine] = True
    if co is not None:
        signed[other_label] = True
    if signed["receiver"] and signed["issuer"]:
        # the full SH-6 checks with the incoming pair in place
        old_r, old_i = permit.receiver_user_id, permit.issuer_user_id
        permit.receiver_user_id, permit.issuer_user_id = h.to_receiver_user_id, h.to_issuer_user_id
        try:
            if old_r != h.to_receiver_user_id:
                lifecycle.receiver_limit(db, permit)
            chk = lifecycle.shift_checks(db, permit, body, at, gas_start=True)
        except Exception:
            permit.receiver_user_id, permit.issuer_user_id = old_r, old_i
            raise
    _sign_handover(db, permit, h, mine, uid, None, at)
    if co is not None:
        _sign_handover(db, permit, h, other_label, co.id, uid, at)
    if not (h.receiver_signed_at and h.issuer_signed_at):
        _audit(
            db,
            p,
            permit,
            AuditAction.update,
            None,
            {f"{mine}_signed_at": at.isoformat()},
            entity_type=EntityType.permit_handover,
            entity_id=h.id,
        )
        return lifecycle._view(db, p, permit)
    lifecycle.save_wind(db, p, permit, body.wind_reading)
    old_shift = lifecycle.current_shift(db, permit)
    lifecycle.close_shift(db, permit, old_shift, at, ShiftEndType.handover)
    lifecycle.open_shift(
        db,
        permit,
        at,
        receiver_id=h.to_receiver_user_id,
        issuer_id=h.to_issuer_user_id,
        crew=chk.crew,
        ambient=body.ambient_temp_c,
        gas_test_id=chk.gas_test_id,
        end=chk.planned_end,
    )
    h.status = HandoverStatus.accepted
    h.accepted_at = at
    _audit(
        db,
        p,
        permit,
        AuditAction.status_change,
        {"status": "initiated"},
        {"status": "accepted"},
        entity_type=EntityType.permit_handover,
        entity_id=h.id,
    )
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        {"receiver_user_id": str(old_r), "issuer_user_id": str(old_i) if old_i else None},
        {
            "receiver_user_id": str(h.to_receiver_user_id),
            "issuer_user_id": str(h.to_issuer_user_id),
            "handover": True,
        },
    )
    evaluation.store(permit, chk.result)
    lifecycle._refresh(db, permit, at)
    common.tell(
        db,
        permit,
        {h.from_receiver_user_id, old_i, h.to_receiver_user_id, h.to_issuer_user_id} - {None},  # type: ignore[arg-type]
        NotificationKind.permit_update,
        f"Handover of {permit.permit_no} accepted",
        f"تم قبول تسليم التصريح {permit.permit_no}",
    )
    return lifecycle._view(db, p, permit)


def _sign_handover(
    db: Session,
    permit: Permit,
    h: PermitHandover,
    side: str,
    user_id: uuid.UUID,
    device_of: uuid.UUID | None,
    at: datetime,
) -> None:
    label = "permit_receiver" if side == "receiver" else "permit_issuer"
    appt = None
    if side == "issuer":
        a = evaluation.issuer_appointment(
            db, permit, user_id, evaluation.appointment_day(permit, at)
        )
        appt = a.id if a else None
    common.sign(
        db,
        permit,
        SignaturePurpose.handover_accept,
        label,
        user_id=user_id,
        appointment_id=appt,
        entity_id=h.id,
        co_device=device_of,
        at=at,
    )
    if side == "receiver":
        h.receiver_signed_at = at
    else:
        h.issuer_signed_at = at


# ---- field records -------------------------------------------------------------------------------


def record_hot_work_end(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.HotWorkEndInput
) -> sch.PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.hot_work, "hot_work_ended_at")
    _live(permit, "record hot work end", S.active, S.suspended)
    lifecycle._cap(p, permit, C.permit_receive)
    if p.user.id != permit.receiver_user_id:
        sh = lifecycle.current_shift(db, permit)
        if sh is None or sh.receiver_user_id != p.user.id:
            raise forbidden_error("Only the receiver records the end of hot work (HW-4).")
    _not_future(body.ended_at, "ended_at")
    if permit.started_at and body.ended_at < permit.started_at:
        raise validation_error("ended_at", "Hot work cannot end before the permit started.")
    if lifecycle.fire_watch_until(permit) is not None:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "The end of hot work is already recorded.",
            "تم تسجيل انتهاء العمل الساخن مسبقاً.",
            status=409,
        )
    s = common.settings(db, permit.project_id)
    fw = body.ended_at + timedelta(minutes=s.fire_watch_post_minutes)
    _set_section(
        permit,
        T.hot_work,
        {"hot_work_ended_at": body.ended_at.isoformat(), "fire_watch_until": fw.isoformat()},
    )
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"hot_work_ended_at": body.ended_at.isoformat(), "fire_watch_until": fw.isoformat()},
    )
    lifecycle._refresh(db, permit)
    return lifecycle._view(db, p, permit)


def record_entry(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.EntryLogInput
) -> sch.EntryLogRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.confined_space, "The entry log")
    lifecycle._cap(p, permit, C.permit_receive)
    _not_future(body.at, "at")
    names = views.names_ok(p, permit.project_id)
    if body.direction == EntryDirection.in_:
        _live(permit, "entry", S.active)
        sh = lifecycle.current_shift(db, permit)
        if lifecycle.open_pause(sh) is not None:
            raise common.err(
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "Work is paused: nobody may enter the confined space during a pause.",
                "العمل متوقف مؤقتاً: لا يُسمح بالدخول أثناء التوقف.",
            )
        line = db.scalar(
            select(PermitCrew).where(
                PermitCrew.permit_id == permit.id,
                PermitCrew.worker_id == body.worker_id,
                PermitCrew.crew_role == PtwCrewRole.entrant,
                PermitCrew.status == CrewLineStatus.listed,
            )
        )
        if line is None:
            raise validation_error(
                "worker_id", "Only an eligible entrant listed on the permit may enter (CS-7)."
            )
        if sh is not None and body.worker_id not in (sh.crew_present or []):
            raise validation_error("worker_id", "The entrant is not in this shift's crew present.")
        if any(r.worker_id == body.worker_id for r in lifecycle.persons_inside(db, permit.id)):
            raise validation_error("worker_id", "The entry log already shows this entrant inside.")
        r = PermitRecord(
            id=uuid.uuid4(),
            permit_id=permit.id,
            kind="entry_log",
            at=body.at,
            worker_id=body.worker_id,
            data={},
            recorded_by_user_id=p.user.id,
        )
        db.add(r)
    else:
        lifecycle._need(permit, "exit", S.issued, S.active, S.suspended)
        open_rows = [
            x for x in lifecycle.persons_inside(db, permit.id) if x.worker_id == body.worker_id
        ]
        if not open_rows:
            raise validation_error("worker_id", "The entry log does not show this person inside.")
        r = open_rows[-1]
        if body.at < r.at:
            raise validation_error("at", "The exit time is before the entry time.")
        r.out_at = body.at
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {
            "entry_log": body.direction.value,
            "worker_id": str(body.worker_id),
            "at": body.at.isoformat(),
        },
    )
    return sch.EntryLogRead(
        id=r.id,
        worker=views._worker(db, r.worker_id, names),
        in_at=r.at,
        out_at=r.out_at,
    )


def record_wind(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.WindReadingInput
) -> sch.WindReadingRead:
    permit = common.get_permit(db, p, permit_id)
    if not ({T.lifting.value, T.work_at_height.value} & set(permit.work_types)):
        raise common.err(
            ErrorCode.VALIDATION_ERROR,
            "Wind readings apply to lifting and work-at-height permits only.",
            "قراءات الرياح تنطبق على تصاريح الرفع والعمل على ارتفاع فقط.",
        )
    _live(permit, "wind reading", S.approved, S.issued, S.active, S.suspended)
    _field_cap(p, permit)
    _not_future(body.measured_at, "measured_at")
    r = lifecycle.save_wind(db, p, permit, body)
    assert r is not None  # noqa: S101
    f = facts_mod.compute(db, permit)
    lim = evaluation.wind_limit(f) if f.has(T.lifting) else rules.WAH_WIND_LIMIT_MS
    speed = Decimal(str(body.speed_ms))
    _audit(db, p, permit, AuditAction.update, None, {"wind_ms": str(speed), "limit_ms": str(lim)})
    if (
        not f.has(T.lifting)
        and permit.status in (S.issued, S.active)
        and permit.exposure in (Exposure.outdoor_direct_sun, Exposure.outdoor_shaded)
        and speed > rules.WAH_WIND_LIMIT_MS
    ):
        lifecycle.suspend_now(
            db,
            permit,
            StatusReason.weather,
            f"Wind {speed} m/s > {rules.WAH_WIND_LIMIT_MS} m/s (WH-7)",
            source_ref=body.source_ref,
        )
    lifecycle._refresh(db, permit)
    return sch.WindReadingRead(
        id=r.id,
        measured_at=r.at,
        speed_ms=speed,
        source=body.source,
        source_ref=body.source_ref,
        limit_ms=lim,
        within_limit=speed <= lim,
        recorded_by=Refs(db).user(p.user.id),
    )


def record_excavation_inspection(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.ExcavationInspectionInput
) -> sch.ExcavationInspectionRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.excavation, "An excavation inspection")
    _live(permit, "excavation inspection", S.approved, S.issued, S.active, S.suspended)
    _field_cap(p, permit)
    _not_future(body.inspected_at, "inspected_at")
    a = db.get(PtwAppointment, body.appointment_id)
    day = acommon.local_day(body.inspected_at)
    if (
        a is None
        or a.project_id != permit.project_id
        or a.function != AppointmentFunction.authorised_person
        or a.discipline != AppointmentDiscipline.excavation_competent_person
        or not common.appointment_covers(
            a, [T.excavation.value], permit.site_id, list(permit.zone_ids or []), [day]
        )
    ):
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "The inspection needs an Active excavation competent-person appointment covering the site (EX-6).",
            "يتطلب الفحص تعيين شخص كفء للحفريات ساري ويغطي الموقع.",
            field="appointment_id",
        )
    r = PermitRecord(
        id=uuid.uuid4(),
        permit_id=permit.id,
        kind="excavation_inspection",
        at=body.inspected_at,
        data={
            "appointment_id": str(a.id),
            "result": body.result.value,
            "after_rain_or_event": body.after_rain_or_event,
            "note": body.note,
        },
        recorded_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"excavation_inspection": body.result.value, "appointment_no": a.appointment_no},
    )
    if body.result == ExcavationInspectionResult.unsafe and permit.status in (S.issued, S.active):
        lifecycle.suspend_now(
            db,
            permit,
            StatusReason.other,
            "Excavation inspection unsafe (EX-6)" + (f": {body.note}" if body.note else ""),
            by=p,
            source_ref=a.appointment_no,
        )
    lifecycle._refresh(db, permit)
    return views.inspection_read(db, p, r, Refs(db), permit.receiver_user_id)


def record_barrier_survey(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.BarrierSurveyInput
) -> sch.BarrierSurveyRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.radiography, "A barrier survey")
    _live(permit, "barrier survey", S.approved, S.issued, S.active, S.suspended)
    _field_cap(p, permit)
    _not_future(body.measured_at, "measured_at")
    r = PermitRecord(
        id=uuid.uuid4(),
        permit_id=permit.id,
        kind="barrier_survey",
        at=body.measured_at,
        data={"max_usv_h": str(body.max_usv_h), "meter_tag": body.meter_tag},
        recorded_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    lim = common.settings(db, permit.project_id).rg_barrier_limit_usv_h
    _audit(db, p, permit, AuditAction.update, None, {"barrier_survey_usv_h": str(body.max_usv_h)})
    lifecycle._refresh(db, permit)
    return views.survey_read(r, Decimal(str(lim)), Refs(db), permit.receiver_user_id)


def record_source_return(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.SourceReturnInput
) -> sch.PermitRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.radiography, "Source return")
    _live(permit, "source return", S.active, S.suspended)
    _field_cap(p, permit)
    _not_future(body.at, "at")
    before = permit.source_return
    permit.source_return = acommon.jsonable(body.model_dump())
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        {"source_return": before},
        {"source_return": permit.source_return},
    )
    lifecycle._refresh(db, permit)
    return lifecycle._view(db, p, permit)


def record_fod_check(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.PermitFodCheckInput
) -> sch.PermitFodCheckRead:
    permit = common.get_permit(db, p, permit_id)
    _need_type(permit, T.airside_works, "A FOD check")
    _live(permit, "FOD check", S.active, S.suspended)
    _field_cap(p, permit)
    _not_future(body.checked_at, "checked_at")
    if (body.checked_by_worker_id is None) == (body.checked_by_user_id is None):
        raise validation_error(
            "checked_by_worker_id", "Give exactly one of checked_by_worker_id / checked_by_user_id."
        )
    if body.checked_by_worker_id is not None:
        if db.get(Worker, body.checked_by_worker_id) is None:
            raise validation_error("checked_by_worker_id", "Unknown worker.")
        if not checks.in_tree(db, permit, body.checked_by_worker_id):
            raise validation_error(
                "checked_by_worker_id",
                "The worker must be deployed on the permit's contractor tree.",
            )
    elif db.get(User, body.checked_by_user_id) is None:
        raise validation_error("checked_by_user_id", "Unknown user.")
    permit.fod_check = acommon.jsonable(body.model_dump())
    _audit(db, p, permit, AuditAction.update, None, {"fod_check": body.result.value})
    lifecycle._refresh(db, permit)
    out = views.fod_read(
        db, permit.fod_check, "permit", views.names_ok(p, permit.project_id), Refs(db)
    )
    assert out is not None  # noqa: S101
    return out


# ---- exemptions (PT-17) --------------------------------------------------------------------------


def _exemption_applicable(db: Session, permit: Permit, body: sch.ExemptionCreate) -> None:
    f = facts_mod.compute(db, permit)
    k = body.kind
    if k == ExemptionKind.midday_ban:
        if body.midday_reason is None:
            raise validation_error("midday_reason", "A midday-ban exemption needs a reason (HT-4).")
        if not body.heat_controls_text:
            raise validation_error(
                "heat_controls_text", "Describe the heat controls (≥ 30 characters, HT-4)."
            )
        if body.valid_from is None or body.valid_to is None:
            raise validation_error(
                "valid_from", "A midday-ban exemption needs a date range (HT-4)."
            )
        if body.valid_to < body.valid_from:
            raise validation_error("valid_to", "The end date is before the start date.")
        return
    if body.valid_from and body.valid_to and body.valid_to < body.valid_from:
        raise validation_error("valid_to", "The end date is before the start date.")
    need = {
        ExemptionKind.energized_work: T.electrical_isolation,
        ExemptionKind.fire_impairment: T.hot_work,
        ExemptionKind.lift_capacity_over_90: T.lifting,
    }[k]
    if not f.has(need):
        raise validation_error("kind", f"This exemption applies to {need.value} permits only.")
    sec = f.sec(need)
    if k == ExemptionKind.energized_work:
        if sec.get("work_condition") != WorkCondition.energized.value:
            raise validation_error("kind", "The electrical section is not energized work (EL-3).")
        if sec.get("voltage_class") == VoltageClass.hv.value:
            raise common.err(
                ErrorCode.ENERGIZED_HV_PROHIBITED,
                "Energized HV work is prohibited; no exemption is possible (EL-3).",
                "العمل على جهد عالٍ مكهرب محظور ولا يمكن استثناؤه.",
            )
    if k == ExemptionKind.fire_impairment and not sec.get("fire_system_impairment"):
        raise validation_error(
            "kind", "The hot-work section declares no fire-system impairment (HW-8)."
        )


def request_exemption(
    db: Session, p: Principal, permit_id: uuid.UUID, body: sch.ExemptionCreate
) -> sch.ExemptionRead:
    permit = common.get_permit(db, p, permit_id)
    if permit.status in PERMIT_TERMINAL:
        raise lifecycle.invalid(permit, "exemption request")
    granter = p.grant(permit.project_id, C.ptw_exemption_grant) is not None or p.is_manager
    if not granter:
        from app.services.ptw import permits  # noqa: PLC0415

        permits._prep(p, permit)
    _exemption_applicable(db, permit, body)
    for e in views.exemptions_of(db, permit.id):
        if (
            e.kind == body.kind
            and e.status in (ExemptionStatus.requested, ExemptionStatus.granted)
            and (
                body.kind != ExemptionKind.midday_ban
                or e.valid_from is None
                or e.valid_to is None
                or body.valid_from is None
                or body.valid_to is None
                or (e.valid_from <= body.valid_to and body.valid_from <= e.valid_to)
            )
        ):
            raise common.err(
                ErrorCode.DUPLICATE_VALUE,
                f"An exemption of this kind is already {e.status.value} for this permit.",
                "يوجد استثناء من هذا النوع لهذا التصريح.",
                status=409,
            )
    at = now()
    e = PermitExemption(
        id=uuid.uuid4(),
        permit_id=permit.id,
        project_id=permit.project_id,
        kind=body.kind,
        status=ExemptionStatus.requested,
        midday_reason=body.midday_reason,
        reason_text=body.reason_text,
        heat_controls_text=body.heat_controls_text,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        requested_by_user_id=p.user.id,
        requested_at=at,
    )
    db.add(e)
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.create,
        None,
        acommon.jsonable({"permit_no": permit.permit_no, **body.model_dump()}),
        entity_type=EntityType.permit_exemption,
        entity_id=e.id,
    )
    if granter:
        common.require_reauth(db, p, permit.project_id)
        _decide(db, p, permit, e, ExemptionStatus.granted, None, at)
    else:
        common.tell(
            db,
            permit,
            notify.managers(db),
            NotificationKind.ptw_exemption,
            f"Exemption requested on {permit.permit_no}: {body.kind.value}",
            f"طلب استثناء على التصريح {permit.permit_no}",
        )
    return views.exemption_read(e, Refs(db))


def _decide(
    db: Session,
    p: Principal,
    permit: Permit,
    e: PermitExemption,
    status: ExemptionStatus,
    note: str | None,
    at: datetime,
) -> None:
    e.status = status
    e.decided_by_user_id = p.user.id
    e.decided_at = at
    e.decision_note = note
    _audit(
        db,
        p,
        permit,
        AuditAction.status_change,
        {"status": "requested"},
        {"status": status.value},
        entity_type=EntityType.permit_exemption,
        entity_id=e.id,
    )
    users = {e.requested_by_user_id, permit.receiver_user_id}
    if permit.issuer_user_id:
        users.add(permit.issuer_user_id)
    if status == ExemptionStatus.granted:
        users.update(common.officers(db, permit.project_id))
    common.tell(
        db,
        permit,
        users,
        NotificationKind.ptw_exemption,
        f"Exemption {status.value} on {permit.permit_no}: {e.kind.value}",
        f"الاستثناء على التصريح {permit.permit_no}: {'مُنح' if status == ExemptionStatus.granted else 'رُفض'}",
    )
    lifecycle._refresh(db, permit, at)


def decide_exemption(
    db: Session, p: Principal, exemption_id: uuid.UUID, body: sch.ExemptionDecision
) -> sch.ExemptionRead:
    e = db.get(PermitExemption, exemption_id)
    if e is None:
        raise common.err(
            ErrorCode.NOT_FOUND, "Exemption not found.", "الاستثناء غير موجود.", status=404
        )
    permit = common.get_permit(db, p, e.permit_id)
    acommon.require_cap(p, permit.project_id, C.ptw_exemption_grant, [permit.site_id], None)
    if e.status != ExemptionStatus.requested:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            f"This exemption is already {e.status.value}.",
            "تم البت في هذا الاستثناء مسبقاً.",
            status=409,
        )
    if permit.status in PERMIT_TERMINAL:
        raise lifecycle.invalid(permit, "exemption decision")
    common.require_reauth(db, p, permit.project_id)
    _decide(db, p, permit, e, ExemptionStatus(body.decision), body.note, now())
    return views.exemption_read(e, Refs(db))
