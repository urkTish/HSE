# ruff: noqa: E501
"""Phase 3 scheduled jobs (3-ptw §4.1, §4.2, §5.9, §5.11, §7).

`ptw_minute` (every minute): issue lapse, handover / shift lapse, gas retest due and overdue,
midday-ban pre-warning and 12:00 suspension, expiry (waits for the fire watch), fire watch
ended, request / not-issued / shift-end / valid-to / post-expiry alerts, and the PT-16
recompute of live permits (which auto-suspends on new blockers, SH-2).
`ptw_daily` (00:15): appointment, detector, isolation, JSA template and audit-lock jobs and the daily crew
eligibility refresh of Approved and live permits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import NotificationKind
from app.core.ptw_enums import (
    PERMIT_LIVE,
    CrewLineStatus,
    ExemptionKind,
    Exposure,
    HandoverStatus,
    PermitStatus,
    PermitWarningCode,
    PtwCrewRole,
    StatusReason,
)
from app.models import Permit, PermitCrew, PermitHandover, PermitShift, Worker
from app.services.access import common as acommon
from app.services.ptw import common, evaluation, lifecycle, rules
from app.services.ptw import facts as facts_mod

S = PermitStatus


def _mark(row: Any, key: str) -> bool:
    """True the first time `key` is seen on row.alerts_sent (and records it)."""
    sent = list(row.alerts_sent or [])
    if key in sent:
        return False
    row.alerts_sent = [*sent, key]
    return True


def _hm(at: datetime) -> str:
    return acommon.local(at).strftime("%H:%M")


def _permits(db: Session, *statuses: PermitStatus) -> list[Permit]:
    return list(
        db.scalars(
            select(Permit).where(Permit.status.in_(list(statuses))).order_by(Permit.permit_no)
        )
    )


# ---- lifecycle timers ----------------------------------------------------------------------------


def _issue_lapses(db: Session, at: datetime) -> int:
    n = 0
    for permit in _permits(db, S.issued):
        if permit.issued_at is None:
            continue
        s = common.settings(db, permit.project_id)
        if at > permit.issued_at + timedelta(minutes=s.issue_to_start_max_minutes):
            lifecycle.lapse_issue(db, permit, at)
            n += 1
    return n


def _shift_lapses(db: Session, at: datetime) -> int:
    n = 0
    for h in db.scalars(
        select(PermitHandover).where(
            PermitHandover.status == HandoverStatus.initiated, PermitHandover.deadline_at <= at
        )
    ):
        from app.services.ptw import fieldwork  # noqa: PLC0415

        fieldwork.lapse_handover(db, h, at)
    for permit in _permits(db, S.active):
        sh = lifecycle.current_shift(db, permit)
        if sh is not None and sh.ended_at is None and sh.planned_end_at <= at:
            lifecycle.lapse_shift(db, permit, sh, at)
            n += 1
    return n


def _expiries(db: Session, at: datetime) -> int:
    n = 0
    for permit in _permits(db, S.approved, S.issued, S.active, S.suspended):
        if at <= permit.valid_to_at:
            continue
        fw = lifecycle.fire_watch_until(permit)
        if fw is not None and fw > at:
            continue  # HW-5: expiry waits for the fire watch
        lifecycle.expire(db, permit, at)
        n += 1
    return n


# ---- gas (GT-4) ----------------------------------------------------------------------------------


def _gas_testers(db: Session, permit: Permit) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for line in db.scalars(
        select(PermitCrew).where(
            PermitCrew.permit_id == permit.id,
            PermitCrew.crew_role == PtwCrewRole.gas_tester,
            PermitCrew.status == CrewLineStatus.listed,
        )
    ):
        w = db.get(Worker, line.worker_id)
        if w is not None and w.user_id is not None:
            out.add(w.user_id)
    return out


def _gas(db: Session, at: datetime) -> dict[str, int]:
    from app.services.ptw import gas  # noqa: PLC0415

    due_alerts = overdue = 0
    for permit in _permits(db, S.active):
        f = facts_mod.compute(db, permit)
        if not f.gas_required or f.interval is None:
            continue
        sh = lifecycle.current_shift(db, permit)
        if sh is None or lifecycle.open_pause(sh) is not None:
            continue  # no test falls due during a pause (GT-4)
        st = gas.state(db, permit, f.interval, True, at)
        due = st.next_due_at
        if due is None:
            continue
        if at >= due:
            lifecycle.auto_suspend(
                db,
                permit,
                StatusReason.gas_retest_overdue,
                f"No passing gas test by {_hm(due)}",
                st.latest_pass.test_no if st.latest_pass else None,
                at=max(due, sh.started_at),
            )
            overdue += 1
            continue
        users = {permit.receiver_user_id} | _gas_testers(db, permit)
        if at >= due - timedelta(minutes=10) and _mark(sh, f"gas_due10:{due.isoformat()}"):
            common.tell(
                db,
                permit,
                users,
                NotificationKind.gas_retest_due,
                f"Gas re-test due at {_hm(due)}",
                f"إعادة فحص الغاز مستحقة الساعة {_hm(due)}",
            )
            due_alerts += 1
    return {"gas_due_alerts": due_alerts, "gas_overdue": overdue}


# ---- midday ban (HT-3) ---------------------------------------------------------------------------


def _midday(db: Session, at: datetime) -> dict[str, int]:
    warned = suspended = 0
    day = acommon.local_day(at)
    for permit in _permits(db, S.active, S.issued):
        if permit.exposure != Exposure.outdoor_direct_sun:
            continue
        if evaluation.exemption(db, permit, ExemptionKind.midday_ban, day) is not None:
            continue
        st = common.settings(db, permit.project_id)
        if not rules.in_season(
            day, st.midday_ban_period["start_mmdd"], st.midday_ban_period["end_mmdd"]
        ):
            continue
        bs, be = rules.ban_interval(day, st.midday_ban_hours)
        if bs <= at < be:
            if permit.status == S.active:
                lifecycle.suspend_now(
                    db, permit, StatusReason.midday_ban, None, at=at, source_ref=None
                )
                suspended += 1
            continue
        pre = bs - timedelta(minutes=st.midday_ban_prewarn_minutes)
        if (
            permit.status == S.active
            and pre <= at < bs
            and _mark(permit, f"midday_pre:{day.isoformat()}")
        ):
            common.tell(
                db,
                permit,
                common.permit_people(db, permit),
                NotificationKind.midday_ban,
                f"Midday ban from {_hm(bs)}: stop outdoor work",
                f"حظر العمل وقت الظهيرة يبدأ الساعة {_hm(bs)}: أوقف العمل الخارجي",
            )
            warned += 1
    return {"midday_prewarned": warned, "midday_suspended": suspended}


# ---- alerts (§7) ---------------------------------------------------------------------------------


def _alerts(db: Session, at: datetime) -> int:
    n = 0
    # Requested: reminder at 4 h, HSE Officer at 8 h
    for permit in _permits(db, S.requested):
        if permit.requested_at is None:
            continue
        age = at - permit.requested_at
        if age >= timedelta(hours=4) and _mark(permit, f"req4:{permit.requested_at.isoformat()}"):
            common.tell(
                db,
                permit,
                [permit.area_authority_user_id] if permit.area_authority_user_id else [],
                NotificationKind.permit_review_reminder,
                "Permit waiting for your area review for 4 h",
                "التصريح بانتظار مراجعتك منذ 4 ساعات",
            )
            n += 1
        if age >= timedelta(hours=8) and _mark(permit, f"req8:{permit.requested_at.isoformat()}"):
            common.tell(
                db,
                permit,
                common.officers(db, permit.project_id),
                NotificationKind.permit_review_reminder,
                "Permit still not reviewed after 8 h",
                "التصريح لم تتم مراجعته بعد 8 ساعات",
            )
            n += 1
    # Approved but not issued at window start + 60 min
    for permit in _permits(db, S.approved):
        inst = common.current_instance(permit, at)
        if inst is None or at < inst[0] + timedelta(minutes=60):
            continue
        if _mark(permit, f"not_issued:{inst[0].isoformat()}"):
            common.tell(
                db,
                permit,
                common.permit_people(db, permit),
                NotificationKind.permit_not_issued,
                f"Approved permit not issued 60 min after the window start ({_hm(inst[0])})",
                "التصريح المعتمد لم يصدر بعد 60 دقيقة من بداية الفترة",
            )
            n += 1
    # Shift end approaching (−60 / −15) and fire watch ended
    for permit in _permits(db, S.active, S.suspended):
        sh = lifecycle.current_shift(db, permit)
        if permit.status == S.active and sh is not None and sh.ended_at is None:
            for mins in (60, 15):
                if sh.planned_end_at - timedelta(minutes=mins) <= at < sh.planned_end_at and _mark(
                    sh, f"end{mins}"
                ):
                    common.tell(
                        db,
                        permit,
                        {sh.receiver_user_id, sh.issuer_user_id},
                        NotificationKind.shift_end_approaching,
                        f"Shift {sh.shift_no} ends at {_hm(sh.planned_end_at)}: end it or hand over",
                        f"الوردية {sh.shift_no} تنتهي الساعة {_hm(sh.planned_end_at)}",
                    )
                    n += 1
                    break
        fw = lifecycle.fire_watch_until(permit)
        if fw is not None and fw <= at and _mark(permit, "fire_watch_ended"):
            common.tell(
                db,
                permit,
                common.permit_people(db, permit),
                NotificationKind.fire_watch_ended,
                "Fire watch ended: the permit may be closed",
                "انتهت مراقبة الحريق: يمكن إغلاق التصريح",
            )
            n += 1
    # valid_to approaching
    for permit in _permits(db, *PERMIT_LIVE):
        dur = permit.valid_to_at - permit.valid_from_at
        marks = (72, 24, 0) if dur > timedelta(hours=24) else (2,)
        for h in marks:
            if (
                permit.valid_to_at - timedelta(hours=h)
                <= at
                < permit.valid_to_at + timedelta(minutes=1)
            ):
                if _mark(permit, f"vt{h}"):
                    common.tell(
                        db,
                        permit,
                        common.permit_people(db, permit),
                        NotificationKind.permit_ending,
                        f"Permit valid until {acommon.local(permit.valid_to_at).strftime('%Y-%m-%d %H:%M')}",
                        "اقتراب انتهاء صلاحية التصريح",
                    )
                    n += 1
                break
    # post-expiry check pending at 24 h (CL-6)
    for permit in _permits(db, S.expired):
        if not lifecycle.post_expiry_pending(permit) or permit.ended_at is None:
            continue
        if at >= permit.ended_at + timedelta(hours=24) and _mark(permit, "pec24"):
            common.tell(
                db,
                permit,
                common.officers(db, permit.project_id),
                NotificationKind.post_expiry_check_pending,
                "Post-expiry check still pending after 24 h",
                "فحص ما بعد الانتهاء ما زال معلقاً بعد 24 ساعة",
            )
            n += 1
    return n


def _recompute(db: Session, at: datetime) -> int:
    n = 0
    for permit in _permits(db, S.issued, S.active, S.suspended):
        if evaluation.refresh(db, permit, run_simops=False, at=at) is not None:
            n += 1
    return n


def ptw_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    at = at or now()
    # The 12:00 midday-ban suspension runs before shift lapses: a shift whose window ends at
    # the ban start ends `suspended`, not `lapsed` (Y5, DECISIONS #74).
    out: dict[str, Any] = {"issue_lapsed": _issue_lapses(db, at)}
    out.update(_midday(db, at))
    out["shift_lapsed"] = _shift_lapses(db, at)
    out["expired"] = _expiries(db, at)
    out.update(_gas(db, at))
    out["alerts"] = _alerts(db, at)
    out["recomputed"] = _recompute(db, at)
    db.flush()
    return out


# ---- daily ---------------------------------------------------------------------------------------


def _crew_refresh(db: Session, at: datetime) -> dict[str, int]:
    refreshed = warned = 0
    for permit in _permits(db, S.approved, S.issued, S.active, S.suspended):
        res = evaluation.refresh(db, permit, run_simops=False, at=at, evaluate_crew=True)
        if res is None:
            continue
        refreshed += 1
        if any(w["code"] == PermitWarningCode.EXPIRING_7D.value for w in res.warnings) and _mark(
            permit, f"crew7:{acommon.local_day(at).isoformat()}"
        ):
            common.tell(
                db,
                permit,
                common.permit_people(db, permit, issuer=False, reps=True),
                NotificationKind.crew_eligibility_expiring,
                "A crew requirement expires within 7 days",
                "متطلب لأحد أفراد الطاقم ينتهي خلال 7 أيام",
            )
            warned += 1
    return {"crew_refreshed": refreshed, "crew_expiring_alerts": warned}


def ptw_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.ptw import appointments, audits, gas, isolations, jsa  # noqa: PLC0415

    at = at or now()
    out: dict[str, Any] = {
        "appointments": appointments.daily_job(db, at),
        "detectors": gas.daily_job(db, at),
        "isolations": isolations.daily_job(db, at),
        "jsa_templates": jsa.daily_job(db, at),
        "audits_locked": audits.daily_job(db, at),
    }
    out.update(_crew_refresh(db, at))
    db.flush()
    return out


PHASE3_JOBS = {
    "ptw_minute": ptw_minute,
    "ptw_daily": ptw_daily,
}

_ = PermitShift
