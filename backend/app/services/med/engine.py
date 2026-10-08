"""Line validity (§6.1), the governing line and the in-force predicate (§6.2), and the
`medical_fitness` hook check HK6-6. Pure functions over pre-loaded rows, so the hook provider,
the requirement engine and the KPIs share one implementation (MK-1).

Everything is evaluated at an instant `at` from timestamps (accepted_at, verified_at,
revoked_at, hold start / release), so a past as_of (KPIs as of 2026-09-30) sees the register as
it was then."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookProviderStatus, WorkerStatus
from app.core.cert_enums import HookReasonCode, VerificationStatus
from app.core.med_enums import (
    AssessmentStatus,
    FitnessLimitingFactor,
    FitnessOutcome,
    HoldStatus,
    MedicalBlacklistScope,
    RestrictionCode,
)
from app.models import (
    FitnessAssessment,
    FitnessCode,
    FitnessHold,
    FitnessLine,
    MedicalProvider,
    MedicalSettings,
    Worker,
)
from app.services.access import common as acommon
from app.services.med import common
from app.services.med import reference as ref

P = HookProviderStatus
R = HookReasonCode
LF = FitnessLimitingFactor
EXPIRING_HOOK_DAYS = 7
EXPIRING_KPI_DAYS = 30
TIE_ORDER = [LF.restriction_review, LF.printed_next_due, LF.code_validity, LF.project_override]


# ---- §6.1 validity -------------------------------------------------------------------------------


def restriction_end(outcome: FitnessOutcome, restrictions: Iterable[dict[str, Any]],
                    review_date: date | None) -> date | None:  # fmt: skip
    if outcome != FitnessOutcome.fit_with_restrictions or review_date is None:
        return None
    if any(ref.review_required(r["code"]) for r in restrictions):
        return review_date
    return None


def validity(
    examined_on: date,
    outcome: FitnessOutcome,
    months: int,
    printed_next_due: date | None,
    r_end: date | None,
    override_months: int | None = None,
) -> tuple[date | None, FitnessLimitingFactor | None]:
    """(valid_until, limiting_factor); unfit outcomes have none."""
    if outcome in ref.UNFIT:
        return None, None
    terms: list[tuple[date, FitnessLimitingFactor]] = [
        (common.add_months(examined_on, months) - timedelta(days=1), LF.code_validity)
    ]
    if printed_next_due is not None:
        terms.append((printed_next_due, LF.printed_next_due))
    if r_end is not None:
        terms.append((r_end, LF.restriction_review))
    if override_months is not None and override_months < months:
        terms.append(
            (
                common.add_months(examined_on, override_months) - timedelta(days=1),
                LF.project_override,
            )
        )
    lo = min(t[0] for t in terms)
    factor = min((f for d, f in terms if d == lo), key=TIE_ORDER.index)
    return lo, factor


def stored_validity(
    fc: FitnessCode, examined_on: date, outcome: FitnessOutcome, restrictions: list[dict[str, Any]],
    review_date: date | None, printed: date | None,
) -> tuple[date | None, FitnessLimitingFactor | None]:  # fmt: skip
    r_end = restriction_end(outcome, restrictions, review_date)
    return validity(examined_on, outcome, fc.validity_months, printed, r_end)


# ---- context and loaded rows ---------------------------------------------------------------------


@dataclass
class Ctx:
    codes: dict[str, FitnessCode]
    providers: dict[uuid.UUID, MedicalProvider]
    settings: MedicalSettings | None
    critical: set[str]

    def months(self, c: str) -> int:
        fc = self.codes.get(c)
        return fc.validity_months if fc is not None else 12


def ctx_for(db: Session, project_id: uuid.UUID | None) -> Ctx:
    s = common.settings(db, project_id) if project_id is not None else None
    return Ctx(common.codes(db), common.providers(db), s, common.critical_codes(s))


@dataclass
class Row:
    line: FitnessLine
    a: FitnessAssessment


@dataclass
class WorkerFacts:
    worker: Worker | None
    lines: dict[str, list[Row]] = field(default_factory=lambda: defaultdict(list))
    holds: list[FitnessHold] = field(default_factory=list)
    pending: set[str] = field(default_factory=set)  # codes with Submitted / Awaiting Sign-off


def _chunks(ids: list[uuid.UUID], n: int = 5000) -> Iterable[list[uuid.UUID]]:
    for i in range(0, len(ids), n):
        yield ids[i : i + n]


def load(db: Session, worker_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, WorkerFacts]:
    wids = list(set(worker_ids))
    out: dict[uuid.UUID, WorkerFacts] = {}
    for chunk in _chunks(wids):
        for w in db.scalars(select(Worker).where(Worker.id.in_(chunk))):
            out[w.id] = WorkerFacts(w)
        rows = db.execute(
            select(FitnessLine, FitnessAssessment)
            .join(FitnessAssessment, FitnessAssessment.id == FitnessLine.assessment_id)
            .where(FitnessLine.worker_id.in_(chunk))
        ).all()
        for ln, a in rows:
            wf = out.setdefault(ln.worker_id, WorkerFacts(None))
            wf.lines[ln.code].append(Row(ln, a))
        for h in db.scalars(select(FitnessHold).where(FitnessHold.worker_id.in_(chunk))):
            out.setdefault(h.worker_id, WorkerFacts(None)).holds.append(h)
    return out


def load_one(db: Session, worker_id: uuid.UUID) -> WorkerFacts:
    return load(db, [worker_id]).get(worker_id) or WorkerFacts(db.get(Worker, worker_id))


# ---- §6.2 governing line and in force ------------------------------------------------------------


def accepted_at(a: FitnessAssessment, at: datetime) -> bool:
    """Accepted at `at` and not revoked by then (rejected / draft never count)."""
    if a.accepted_at is None or a.accepted_at > at or a.historic:
        return False
    return not (a.revoked_at is not None and a.revoked_at <= at)


def governing(rows: list[Row], at: datetime) -> Row | None:
    d = acommon.local_day(at)
    cands = [r for r in rows if accepted_at(r.a, at) and r.a.examined_on <= d]
    if not cands:
        return None
    return max(cands, key=lambda r: (r.a.examined_on, r.a.accepted_at or at))


def verified(c: Ctx, r: Row, at: datetime) -> bool:
    """FV-1: verified, or inside the unverified-acceptance window for a non-critical code."""
    a = r.a
    if a.verification_status == VerificationStatus.verified and (
        a.verified_at is None or a.verified_at <= at
    ):
        return True
    if a.verification_status in (VerificationStatus.failed, VerificationStatus.unable_to_verify):
        return False
    hours = c.settings.unverified_fitness_acceptance_hours if c.settings is not None else 0
    if hours <= 0 or r.line.code in c.critical or a.accepted_at is None:
        return False
    return at < a.accepted_at + timedelta(hours=hours)


def blacklisted(c: Ctx, r: Row, d: date) -> bool:
    pv = c.providers.get(r.a.provider_id)
    if pv is None or pv.blacklisted_on is None or pv.blacklisted_on > d:
        return False
    if pv.blacklist_scope == MedicalBlacklistScope.issued_from and pv.blacklist_from is not None:
        return r.a.examined_on >= pv.blacklist_from
    return True


def effective_until(c: Ctx, r: Row) -> tuple[date | None, FitnessLimitingFactor | None]:
    ln = r.line
    if ln.valid_until is None:
        return None, None
    ov = common.override_months(c.settings, ln.code)
    if ov is None or ov >= c.months(ln.code):
        return ln.valid_until, ln.limiting_factor
    alt = common.add_months(r.a.examined_on, ov) - timedelta(days=1)
    if alt < ln.valid_until:
        return alt, LF.project_override
    return ln.valid_until, ln.limiting_factor


def in_force(c: Ctx, r: Row, at: datetime, gov: Row | None = None) -> bool:
    d = acommon.local_day(at)
    if gov is None or gov.line.id != r.line.id:
        return False
    if r.line.outcome not in ref.FIT or not verified(c, r, at) or blacklisted(c, r, d):
        return False
    vu, _ = effective_until(c, r)
    return r.a.examined_on <= d and vu is not None and d <= vu


def restrictions_in_force(
    c: Ctx, wf: WorkerFacts, at: datetime
) -> list[tuple[Row, dict[str, Any]]]:
    out: list[tuple[Row, dict[str, Any]]] = []
    for rows in wf.lines.values():
        gov = governing(rows, at)
        if gov is not None and in_force(c, gov, at, gov):
            out.extend((gov, x) for x in gov.line.restrictions or [])
    return out


def active_holds(wf: WorkerFacts, at: datetime) -> list[FitnessHold]:
    out = []
    for h in wf.holds:
        if h.started_at > at:
            continue
        if h.released_at is not None and h.released_at <= at:
            continue
        if h.cancelled_at is not None and h.cancelled_at <= at:
            continue
        if h.status == HoldStatus.cancelled and h.cancelled_at is None:
            continue
        out.append(h)
    return out


# ---- HK6-6 ---------------------------------------------------------------------------------------


@dataclass
class Check:
    status: HookProviderStatus
    reason: HookReasonCode | None = None
    hard_stop: bool = False
    valid_until: date | None = None
    ref: str | None = None
    conditions: tuple[dict[str, Any], ...] = ()
    row: Row | None = None
    restriction: str | None = None
    factor: FitnessLimitingFactor | None = None

    @property
    def ok(self) -> bool:
        return self.status in (P.met, P.expiring)


def _cond(x: dict[str, Any]) -> dict[str, Any]:
    en, ar = ref.RESTRICTIONS[RestrictionCode(x["code"])][:2]
    out: dict[str, Any] = {"code": x["code"], "text_en": en, "text_ar": ar}
    if x.get("value") is not None:
        out["value"] = x["value"]
    return out


def _latest_failed(rows: list[Row], at: datetime) -> HookReasonCode | None:
    """No line in force while the latest line was Revoked or failed verification (HK6-3)."""
    d = acommon.local_day(at)
    cands = []
    for r in rows:
        a = r.a
        if a.historic or a.examined_on > d:
            continue
        if a.revoked_at is not None and a.revoked_at <= at:
            cands.append((a.examined_on, a.revoked_at, r))
        elif a.accepted_at is not None and a.accepted_at <= at:
            cands.append((a.examined_on, a.accepted_at, r))
        elif (
            a.status == AssessmentStatus.rejected
            and a.status_changed_at is not None
            and a.status_changed_at <= at
            and a.verification_status == VerificationStatus.failed
        ):
            cands.append((a.examined_on, a.status_changed_at, r))
    if not cands:
        return None
    _e, _t, r = max(cands, key=lambda x: (x[0], x[1]))
    a = r.a
    if a.revoked_at is not None and a.revoked_at <= at:
        if (
            a.verification_status == VerificationStatus.failed
            or a.revoke_code == "verification_failed"
        ):
            return R.MEDICAL_VERIFICATION_FAILED
        return R.MEDICAL_REVOKED
    if a.status == AssessmentStatus.rejected and a.verification_status == VerificationStatus.failed:
        return R.MEDICAL_VERIFICATION_FAILED
    return None


def _pending(rows: list[Row], at: datetime) -> bool:
    for r in rows:
        a = r.a
        if a.status in (AssessmentStatus.submitted, AssessmentStatus.awaiting_signoff):
            t = a.submitted_at or a.created_at
            if t is None or t <= at:
                return True
    return False


def check(c: Ctx, wf: WorkerFacts | None, code: str, at: datetime) -> Check:
    d = acommon.local_day(at)
    w = wf.worker if wf is not None else None
    if w is None or w.status == WorkerStatus.anonymised:
        return Check(P.not_met, R.WORKER_UNKNOWN)
    assert wf is not None  # noqa: S101
    if c.codes.get(code) is None:
        return Check(P.unknown_code, R.UNKNOWN_CODE)
    holds = active_holds(wf, at)
    if holds:
        h = min(holds, key=lambda x: x.started_at)
        return Check(P.not_met, R.MEDICAL_HOLD, True, ref=h.hold_no)
    gen = governing(wf.lines.get(ref.GEN, []), at)
    if gen is not None and gen.line.outcome in ref.UNFIT:
        return Check(P.not_met, R.MEDICAL_UNFIT, True, ref=gen.a.assessment_no, row=gen)
    rows = wf.lines.get(code, [])
    gov = governing(rows, at)
    if gov is None:
        if _pending(rows, at):
            return Check(P.not_met, R.MEDICAL_PENDING_REVIEW)
        failed = _latest_failed(rows, at)
        if failed is not None:
            return Check(P.not_met, failed, True)
        return Check(P.not_met, R.MEDICAL_MISSING)
    no = gov.a.assessment_no
    if gov.line.outcome in ref.UNFIT:
        return Check(P.not_met, R.MEDICAL_UNFIT, True, ref=no, row=gov)
    if blacklisted(c, gov, d):
        return Check(P.not_met, R.MEDICAL_REVOKED, True, ref=no, row=gov)
    if not verified(c, gov, at):
        if gov.a.verification_status == VerificationStatus.failed:
            return Check(P.not_met, R.MEDICAL_VERIFICATION_FAILED, True, ref=no, row=gov)
        return Check(P.not_met, R.MEDICAL_UNVERIFIED, ref=no, row=gov)
    in_f = restrictions_in_force(c, wf, at)
    for _r, x in in_f:
        if common_negates(c, x["code"], code):
            return Check(
                P.not_met, R.RESTRICTION_CONFLICT, True, ref=no, row=gov, restriction=x["code"]
            )
    vu, factor = effective_until(c, gov)
    if vu is None or d > vu:
        reason = R.MEDICAL_REVIEW_DUE if factor == LF.restriction_review else R.MEDICAL_EXPIRED
        return Check(P.not_met, reason, valid_until=vu, ref=no, row=gov, factor=factor)
    conds = tuple(_cond(x) for _r, x in in_f if not common_negates(c, x["code"], code))
    st = P.met if vu > d + timedelta(days=EXPIRING_HOOK_DAYS) else P.expiring
    return Check(st, None, valid_until=vu, ref=no, conditions=conds, row=gov, factor=factor)


def common_negates(c: Ctx, restriction: str, code: str) -> bool:
    fc = c.codes.get(code)
    if fc is not None and restriction in (fc.extra_negated_by or []):
        return True
    return code in ref.negates(restriction)


# ---- line states (§4.3) --------------------------------------------------------------------------


def refresh_states(db: Session, worker_id: uuid.UUID, codes: Iterable[str] | None = None) -> None:
    """Recompute stored `line_state` for the worker's codes: governing / superseded for Accepted
    lines, revoked / rejected for terminal assessments, pending otherwise."""
    from app.core.clock import now  # noqa: PLC0415
    from app.core.med_enums import FitnessLineState  # noqa: PLC0415

    ls = FitnessLineState

    wf = load_one(db, worker_id)
    at = now()
    wanted = set(codes) if codes is not None else set(wf.lines)
    for code, rows in wf.lines.items():
        if code not in wanted:
            continue
        gov = governing(rows, at)
        for r in rows:
            a = r.a
            if a.status == AssessmentStatus.revoked:
                st = ls.revoked
            elif a.status == AssessmentStatus.rejected:
                st = ls.rejected
            elif a.status == AssessmentStatus.accepted and not a.historic:
                st = ls.governing if gov is not None and gov.line.id == r.line.id else ls.superseded
            elif a.status == AssessmentStatus.accepted:
                st = ls.superseded
            else:
                st = ls.pending
            if r.line.line_state != st:
                r.line.line_state = st
    db.flush()
