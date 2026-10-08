"""Phase 5 project settings, enabling training hooks (HK5-1), the training hook readiness report
(HK5-9) and the training hours report (spec 5-training §3.16, §4.7, TH-1…TH-9, §8.4)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, WorkerPersonType
from app.core.cert_enums import HookCodePolicy, HookReasonCode, HookStage
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.ptw_enums import PERMIT_TERMINAL
from app.core.train_enums import (
    CourseCategory,
    SessionStatus,
    TrainingHoursSource,
    TrainingRecordStatus,
)
from app.models import (
    HseSettings,
    Permit,
    PermitCrew,
    TrainingNomination,
    TrainingRecord,
    TrainingSession,
    Worker,
    WorkforceReturn,
)
from app.schemas.cert_config import (
    HookPolicyRead,
    HookReadinessReport,
    ReadinessAffected,
    ReadinessCode,
    ReadinessSubject,
)
from app.schemas.training_config import (
    TrainingHooksEnableRequest,
    TrainingHoursReport,
    TrainingHoursRow,
    TrainingSettingsRead,
    TrainingSettingsUpdate,
)
from app.services.access import common as acommon
from app.services.cert import common as cc
from app.services.common import invalid_transition
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error
from app.services.train import common
from app.services.train import reference as ref

C = common.C
TWO = Decimal("0.01")
FIELDS = (
    "course_validity_months",
    "training_pass_mark_pct",
    "training_max_attempts_30d",
    "unverified_training_acceptance_hours",
    "training_verification_due_days",
    "session_close_deadline_days",
    "session_backdate_max_days",
    "session_day_max_net_hours",
    "trainer_authorisation_max_months",
    "refresher_planning_days",
    "refresher_max_lapse_days",
    "matrix_line_max_due_days",
    "language_block_categories",
    "training_hook_transition_days",
    "training_hook_critical_transition_days",
    "training_hook_critical_codes",
    "training_matrix_warning_pct",
    "training_scan_retention_years",
    "alert_schedule_long_days",
)


# ---- settings (§3.16) ---------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> TrainingSettingsRead:
    from app.services.cert import policy  # noqa: PLC0415

    s = common.settings(db, project_id)
    refs = Refs(db)
    data: dict[str, Any] = {k: getattr(s, k) for k in FIELDS}
    data["course_validity_months"] = {
        k: int(v) for k, v in (s.course_validity_months or {}).items()
    }
    data["language_block_categories"] = [
        CourseCategory(x) for x in (s.language_block_categories or [])
    ]
    data["training_hook_critical_codes"] = list(common.critical_codes(s))
    data["alert_schedule_long_days"] = list(s.alert_schedule_long_days or ref.ALERT_SCHEDULE_LONG)
    return TrainingSettingsRead(
        project_id=project_id,
        training_register_from=common.register_from(db, project_id),
        training_hooks_enabled=policy.state(db, project_id, HookKind.training_course) is not None,
        updated_by=refs.user(s.updated_by_user_id),
        updated_at=s.updated_at,
        **data,
    )


def get_settings(db: Session, p: Principal, project_id: uuid.UUID) -> TrainingSettingsRead:
    common.visible_project(db, p, project_id)
    if p.grant(project_id, C.training_catalogue_view) is None:
        raise forbidden_error()
    return settings_read(db, project_id)


def _manager(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    common.visible_project(db, p, project_id)
    p.ensure_writer()
    if not p.is_manager:  # capability 145 is the HSE Manager's
        raise forbidden_error()


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: TrainingSettingsUpdate
) -> TrainingSettingsRead:
    _manager(db, p, project_id)
    s = common.settings(db, project_id)
    before = cc.snap(s)
    data = body.model_dump(exclude_unset=True)
    for k, v in list(data.items()):
        if v is None:
            raise validation_error(k, "Cannot be null.")
    if "course_validity_months" in data:
        out: dict[str, int] = {}
        for code, months in data.pop("course_validity_months").items():
            c = common.course(db, code)
            if c is None or not c.active:
                raise validation_error("course_validity_months", f"Unknown course {code}.")
            top = c.validity_months
            if int(months) < 1 or (top is not None and int(months) > top):
                raise validation_error(
                    "course_validity_months",
                    f"{code}: 1 … {top or 'any'} months (shorten only).",
                )
            out[code] = int(months)
        s.course_validity_months = out
    if "language_block_categories" in data:
        new = {getattr(x, "value", x) for x in data.pop("language_block_categories")}
        if not set(s.language_block_categories or []) <= new:
            raise validation_error("language_block_categories", "Categories may only be added.")
        s.language_block_categories = sorted(new)
    if "training_hook_critical_codes" in data:
        new = set(data.pop("training_hook_critical_codes"))
        if not common.critical_codes(s) <= new:
            raise validation_error("training_hook_critical_codes", "Codes may only be added.")
        for code in new:
            if common.course(db, code) is None:
                raise validation_error("training_hook_critical_codes", f"Unknown course {code}.")
        s.training_hook_critical_codes = sorted(new)
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    common.clear_cache(db)
    cc.record(
        db, p, AuditAction.settings_changed, EntityType.training_settings, s, project_id, before
    )
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "training.record_changed", project_id=project_id, project_wide=True)
    return settings_read(db, project_id)


# ---- HK5-1 --------------------------------------------------------------------------------------


def enable_hooks(
    db: Session, p: Principal, project_id: uuid.UUID, body: TrainingHooksEnableRequest
) -> HookPolicyRead:
    from app.services.cert import events, policy  # noqa: PLC0415

    _manager(db, p, project_id)
    rf = common.register_from(db, project_id)
    if rf is None or rf > today():
        raise ApiError(
            422,
            ErrorCode.TRAINING_REGISTER_NOT_LIVE,
            "Set training_register_from (≤ today) before enabling training hooks.",
            "حدد تاريخ بدء سجل التدريب (حتى اليوم) قبل تفعيل متطلبات التدريب.",
        )
    if policy.state(db, project_id, HookKind.training_course) is not None:
        raise invalid_transition("Hook policy", "transition", "transition")
    on = body.registered_on or today()
    if on > today():
        raise validation_error("registered_on", "Cannot be in the future.")
    policy.enable_project(
        db, project_id, on, p.actor(project_id), kinds=(HookKind.training_course,)
    )
    policy._alert_change(
        db, project_id, "Training requirement checks enabled", "تم تفعيل فحوص متطلبات التدريب"
    )
    events.publish(db, "hook_policy.changed", project_id=project_id)
    return policy.policy_read(db, project_id)


# ---- HK5-9 readiness ----------------------------------------------------------------------------


def _pct(n: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(n) * 100 / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def readiness(
    db: Session, p: Principal, project_id: uuid.UUID, on_date: date | None = None
) -> HookReadinessReport:
    """Per hook code: subjects requiring it (crew roles, appointments, credentials, zones — the
    enforcement lines of the requirement engine), met / expiring, not-met list, and the live
    permits the block will affect. Never prevents the switch."""
    from app.services.cert import policy  # noqa: PLC0415
    from app.services.ptw.common import permit_ref  # noqa: PLC0415
    from app.services.train import requirements as reqs  # noqa: PLC0415

    common.visible_project(db, p, project_id)
    if p.grant(project_id, C.training_kpi_view) is None:
        raise forbidden_error()
    d = on_date or today()
    kind = HookKind.training_course
    st = policy.state(db, project_id, kind)
    cfg = policy.cfg(db, project_id, kind)
    at = acommon.local_midnight_utc(d) + timedelta(hours=12)
    stage = policy.current_stage(st, cfg, at) if st is not None else HookStage.warn
    s = common.settings(db, project_id)
    crit = common.critical_codes(s)
    names = common.names(p, project_id)
    pe = reqs.evaluate_project(db, project_id, d, enforcement=True, mobilised_only=True)
    per_code: dict[str, dict[uuid.UUID, Any]] = defaultdict(dict)
    for r in pe.reqs:
        if not r.hook_code:
            continue
        for code in r.codes:
            if code in pe.f.hook_codes:
                cur = per_code[code].get(r.dep.worker_id)
                if cur is None or r.state.value in ("met", "expiring", "exempt"):
                    per_code[code][r.dep.worker_id] = r
    failing: set[uuid.UUID] = set()
    codes = []
    for code in policy.codes_of(db, kind):
        subj = per_code.get(code, {})
        ok = 0
        not_met = []
        for wid, r in sorted(subj.items(), key=lambda kv: str(kv[0])):
            if r.state.value in ("met", "expiring", "exempt"):
                ok += 1
                continue
            failing.add(wid)
            w = pe.f.workers.get(wid) or db.get(Worker, wid)
            reason = r.reason or HookReasonCode.TRAINING_MISSING
            not_met.append(
                ReadinessSubject(
                    subject_type="worker",
                    subject_id=wid,
                    ref=w.worker_no if w else str(wid),
                    label=w.full_name_en if (w and names) else None,
                    reason_code=reason,
                    hard_stop=reason
                    in (
                        HookReasonCode.TRAINING_REVOKED,
                        HookReasonCode.TRAINING_SUSPENDED,
                        HookReasonCode.TRAINING_VERIFICATION_FAILED,
                    ),
                )
            )
        value = _pct(ok, len(subj))
        codes.append(
            ReadinessCode(
                code=code,
                critical=code in crit,
                policy=policy.code_policy(st, cfg, code, at)
                if st is not None
                else HookCodePolicy.warn,
                block_from=policy.block_from(st, cfg, code) if st is not None else None,
                required=len(subj),
                in_force=ok,
                readiness_pct=value,
                readiness_display=f"{value} %" if value is not None else "—",
                not_met=not_met,
            )
        )
    permits = []
    if failing:
        for pm in db.scalars(
            select(Permit).where(
                Permit.project_id == project_id, Permit.status.notin_(list(PERMIT_TERMINAL))
            )
        ):
            crew = {
                c.worker_id
                for c in db.scalars(select(PermitCrew).where(PermitCrew.permit_id == pm.id))
            }
            if crew & failing:
                permits.append(permit_ref(pm))
    nxt = d
    if st is not None:
        dates = [
            x
            for x, done in (
                (st.critical_block_from, st.critical_switched_at),
                (st.general_block_from, st.general_switched_at),
            )
            if done is None and x >= d
        ]
        nxt = min(dates) if dates else d
    from app.services.train import gaps  # noqa: PLC0415

    _permits, waps = gaps.live_work(db, project_id, failing)
    return HookReadinessReport(
        project_id=project_id,
        kind=kind,
        as_of=d,
        stage=stage,
        codes=codes,
        affected=[
            ReadinessAffected(
                on_date=nxt,
                permits=permits,
                wap_nos=sorted({x for v in waps.values() for x in v}),
                gate_codes=[],
            )
        ],
    )


# ---- training hours report (§8.4, TH-6, TH-7) ---------------------------------------------------


def _month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


_Key = tuple[str, uuid.UUID | None]


def _keys(month: str, eid: uuid.UUID | None) -> list[tuple[str, uuid.UUID | None]]:
    return [(month, None)] + ([(month, eid)] if eid is not None else [])


def _dec(x: Decimal) -> Decimal:
    return x.quantize(TWO)


def hours_report(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    date_from: date,
    date_to: date,
    engagement_id: uuid.UUID | None = None,
    include_subcontractors: bool = True,
) -> TrainingHoursReport:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_kpi_view)
    if g is None:
        raise forbidden_error()
    if date_to < date_from or (date_to - date_from).days > 366:
        raise validation_error("date_to", "date_to ≥ date_from, at most one year.")
    engs: set[uuid.UUID] | None = None
    if engagement_id is not None:
        engs = {engagement_id}
        if include_subcontractors:
            engs |= engagement_descendants(db, engagement_id)
    if g.engagement_ids is not None:
        engs = set(g.engagement_ids) if engs is None else engs & set(g.engagement_ids)
    hs = db.get(HseSettings, project_id)
    rf = hs.training_register_from if hs else None
    today_ = today()

    def eng_ok(e: uuid.UUID | None) -> bool:
        return engs is None or (e is not None and e in engs)

    def reg_day(d: date) -> bool:
        return rf is not None and d >= rf

    reg: dict[_Key, Decimal] = defaultdict(Decimal)
    staff: dict[_Key, Decimal] = defaultdict(Decimal)
    voided: dict[_Key, Decimal] = defaultdict(Decimal)
    cats: dict[_Key, dict[CourseCategory, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    dr: dict[_Key, Decimal] = defaultdict(Decimal)
    dr_reg: dict[_Key, Decimal] = defaultdict(Decimal)
    open_: dict[str, int] = defaultdict(int)
    courses = common.courses(db)
    for n, s, ptype in db.execute(
        select(TrainingNomination, TrainingSession, Worker.person_type)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .join(Worker, Worker.id == TrainingNomination.worker_id)
        .where(
            TrainingSession.project_id == project_id,
            TrainingSession.status.in_([SessionStatus.closed, SessionStatus.voided]),
            TrainingSession.last_day >= date_from,
            TrainingSession.first_day <= date_to,
        )
    ):
        if s.closed_at is None or ptype == WorkerPersonType.visitor:
            continue
        is_void = s.voided_at is not None and acommon.local_day(s.voided_at) <= today_
        c = courses.get(s.course_code)
        for i, day in enumerate(s.days or []):
            d = date.fromisoformat(day["date"])
            if not (date_from <= d <= date_to) or not reg_day(d):
                continue
            h = Decimal(int((n.minutes_by_day or {}).get(str(i + 1), 0))) / Decimal(60)
            if h <= 0:
                continue
            if not eng_ok(n.engagement_id):
                continue
            for key in _keys(_month(d), n.engagement_id):
                if ptype == WorkerPersonType.client_pmc_staff:
                    if not is_void:
                        staff[key] += h
                    continue
                if is_void:
                    voided[key] += h
                    continue
                reg[key] += h
                if c is not None:
                    cats[key][c.category] += h
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.sponsoring_project_id == project_id,
            TrainingRecord.project_sponsored.is_(True),
            TrainingRecord.status.in_(
                [
                    TrainingRecordStatus.accepted,
                    TrainingRecordStatus.superseded,
                    TrainingRecordStatus.expired,
                ]
            ),
            TrainingRecord.completed_on >= date_from,
            TrainingRecord.completed_on <= date_to,
        )
    ):
        if r.verification_status.value != "verified" or not reg_day(r.completed_on):
            continue
        if not eng_ok(r.engagement_id):
            continue
        h = r.hours or Decimal(0)
        c = courses.get(r.course_code)
        for key in _keys(_month(r.completed_on), r.engagement_id):
            reg[key] += h
            if c is not None:
                cats[key][c.category] += h
    W = WorkforceReturn  # noqa: N806
    from app.kpi.data import COUNTED_RETURN  # noqa: PLC0415

    for eid, d, h in db.execute(
        select(W.engagement_id, W.work_date, func.sum(W.training_hours))
        .where(
            W.project_id == project_id,
            W.work_date >= date_from,
            W.work_date <= date_to,
            W.status.in_(COUNTED_RETURN),
        )
        .group_by(W.engagement_id, W.work_date)
    ):
        if not eng_ok(eid) or not h:
            continue
        for key in _keys(_month(d), eid):
            dr[key] += Decimal(h)
            if reg_day(d):
                dr_reg[key] += Decimal(h)
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.project_id == project_id,
            TrainingSession.status == SessionStatus.delivered,
            TrainingSession.last_day >= date_from,
            TrainingSession.last_day <= date_to,
        )
    ):
        open_[_month(s.last_day)] += 1
    months = []
    m = date(date_from.year, date_from.month, 1)
    while m <= date_to:
        months.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    keys = {k for dct in (reg, staff, voided, dr) for k in dct}
    refs = Refs(db)
    rows = []
    for ms in months:
        mk = _month(ms)
        me = date(ms.year + (ms.month == 12), ms.month % 12 + 1, 1) - timedelta(days=1)
        lo, hi = max(ms, date_from), min(me, date_to)
        n_days = (hi - lo).days + 1
        reg_days = 0 if rf is None else max(0, (hi - max(lo, rf)).days + 1)
        if rf is None or rf > hi:
            src = TrainingHoursSource.daily_returns
        elif rf <= lo:
            src = TrainingHoursSource.register
        else:
            src = TrainingHoursSource.mixed
        engs_here: list[uuid.UUID | None] = sorted(
            {k[1] for k in keys if k[0] == mk and k[1] is not None}, key=str
        )
        for row_eng in [None, *engs_here]:
            key = (mk, row_eng)
            basis = dr_reg[key]
            pct = abs(reg[key] - basis) / basis * 100 if basis > 0 and reg_days else None
            rows.append(
                TrainingHoursRow(
                    month=mk,
                    engagement=refs.eng(row_eng) if row_eng is not None else None,
                    source=src,
                    register_days=min(reg_days, n_days),
                    register_hours=_dec(reg[key]),
                    daily_return_hours=_dec(dr[key]),
                    daily_return_hours_register_days=_dec(basis),
                    k37_numerator=_dec(dr[key] - basis + reg[key]),
                    staff_hours=_dec(staff[key]),
                    voided_hours=_dec(voided[key]),
                    reconciliation_pct=pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if pct is not None
                    else None,
                    reconciliation_note=pct is not None and pct > 5,
                    sessions_not_closed=open_[mk] if row_eng is None else 0,
                    by_category={k: _dec(v) for k, v in cats[key].items()},
                )
            )
    return TrainingHoursReport(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        training_register_from=rf,
        rows=rows,
    )
