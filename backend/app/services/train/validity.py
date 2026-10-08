"""Record validity (§6.1, strictest wins), the in-force predicate (§6.6) and the best record
satisfying a code (CC-6, HK5-3). Pure functions over loaded rows so that the hook provider,
the requirement engine and the KPIs share one implementation."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.core.cert_enums import HookReasonCode, VerificationStatus
from app.core.train_enums import (
    ProviderBlacklistScope,
    TrainingLimitingFactor,
    TrainingProviderStatus,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
)
from app.models import TrainingCourse, TrainingProvider, TrainingRecord, TrainingSettings
from app.services.access import common as acommon

R = HookReasonCode
LF = TrainingLimitingFactor
S = TrainingRecordStatus
HARD = frozenset({R.TRAINING_REVOKED, R.TRAINING_SUSPENDED, R.TRAINING_VERIFICATION_FAILED})
# statuses that may have been in force at some date (§6.6 with as_of in the past)
LIVE = frozenset({S.accepted, S.expired, S.superseded})


def add_months(d: date, months: int) -> date:
    from app.kpi.periods import add_months as _am  # noqa: PLC0415

    return _am(d, months)


def course_end(completed_on: date, months: int | None) -> date | None:
    if months is None:
        return None
    return add_months(completed_on, months) - timedelta(days=1)


def stored_validity(
    c: TrainingCourse | None, completed_on: date, printed_expiry: date | None
) -> tuple[date | None, TrainingLimitingFactor]:
    """§6.1 org default: min(printed_expiry, completed_on + catalogue validity − 1 day);
    printed_expiry wins a tie."""
    ce = course_end(completed_on, c.validity_months if c is not None else None)
    if printed_expiry is None and ce is None:
        return None, LF.none
    if ce is None or (printed_expiry is not None and printed_expiry <= ce):
        return printed_expiry, LF.printed_expiry
    return ce, LF.course_validity


def override_months(c: TrainingCourse | None, s: TrainingSettings | None) -> int | None:
    if c is None or s is None:
        return None
    ov = (s.course_validity_months or {}).get(c.code)
    return int(ov) if ov is not None else None


@dataclass(frozen=True)
class Eff:
    valid_until: date | None
    limiting: TrainingLimitingFactor
    course_end: date | None


def effective(r: TrainingRecord, c: TrainingCourse | None, s: TrainingSettings | None) -> Eff:
    """§6.1 effective on a project: min(stored valid_until, completed_on + override − 1)."""
    months = c.validity_months if c is not None else None
    ov = override_months(c, s)
    vu, lf = r.valid_until, r.limiting_factor
    ce = course_end(r.completed_on, months)
    if ov is not None:
        ov_end = course_end(r.completed_on, ov)
        if ov_end is not None and (months is None or ov < months):
            ce = ov_end
        if ov_end is not None and (vu is None or ov_end < vu):
            vu, lf = ov_end, LF.project_override
    return Eff(vu, lf, ce)


@dataclass
class EvalCtx:
    """What the predicate needs besides the record: courses, the project's settings (override,
    critical codes, unverified window) and providers (blacklist scope)."""

    courses: dict[str, TrainingCourse]
    settings: TrainingSettings | None = None
    providers: dict[uuid.UUID, TrainingProvider] = field(default_factory=dict)

    @property
    def critical(self) -> set[str]:
        from app.services.train import reference as ref  # noqa: PLC0415

        if self.settings is None:
            return set(ref.DEFAULT_CRITICAL)
        return set(self.settings.training_hook_critical_codes or ref.DEFAULT_CRITICAL)

    @property
    def unverified_hours(self) -> int:
        return self.settings.unverified_training_acceptance_hours if self.settings else 0


@dataclass(frozen=True)
class Verdict:
    in_force: bool
    reason: HookReasonCode | None
    eff: Eff
    unverified_until: datetime | None = None

    @property
    def hard(self) -> bool:
        return self.reason in HARD


def blacklisted_for(pv: TrainingProvider | None, r: TrainingRecord) -> bool:
    if pv is None or pv.status != TrainingProviderStatus.blacklisted:
        return False
    if pv.blacklist_scope == ProviderBlacklistScope.issued_from and pv.blacklist_from:
        return r.completed_on >= pv.blacklist_from
    return True


def in_force_since(r: TrainingRecord) -> datetime | None:
    return r.in_force_from or r.verified_at or r.reviewed_at


def evaluate(r: TrainingRecord, d: date, ctx: EvalCtx, at: datetime | None = None) -> Verdict:
    """§6.6 at local date d (`at` = the moment for the unverified window; default end of d)."""
    c = ctx.courses.get(r.course_code)
    eff = effective(r, c, ctx.settings)
    if r.status == S.revoked:
        return Verdict(False, R.TRAINING_REVOKED, eff)
    if r.status == S.suspended:
        return Verdict(False, R.TRAINING_SUSPENDED, eff)
    if r.verification_status == VerificationStatus.failed or (
        r.status == S.rejected and r.status_reason == TrainingStatusReason.verification_failed
    ):
        return Verdict(False, R.TRAINING_VERIFICATION_FAILED, eff)
    if blacklisted_for(ctx.providers.get(r.provider_id), r):
        return Verdict(False, R.TRAINING_REVOKED, eff)
    if r.status == S.submitted:
        return Verdict(False, R.TRAINING_PENDING_REVIEW, eff)
    if r.status not in LIVE or r.completed_on > d:
        return Verdict(False, R.TRAINING_MISSING, eff)
    if r.historic:
        return Verdict(False, R.TRAINING_EXPIRED, eff)
    if r.superseded_on is not None and r.superseded_on <= d:
        return Verdict(False, R.TRAINING_EXPIRED, eff)
    window: datetime | None = None
    if r.verification_status != VerificationStatus.verified:
        hours = ctx.unverified_hours
        if (
            r.source == TrainingRecordSource.session
            or hours <= 0
            or r.course_code in ctx.critical
            or r.reviewed_at is None
        ):
            return Verdict(False, R.TRAINING_UNVERIFIED, eff)
        window = r.reviewed_at + timedelta(hours=hours)
        moment = at or acommon.local_midnight_utc(d + timedelta(days=1))
        if moment >= window:
            return Verdict(False, R.TRAINING_UNVERIFIED, eff, window)
    since = in_force_since(r)
    if since is not None and acommon.local_day(since) > d:
        return Verdict(False, R.TRAINING_PENDING_REVIEW, eff, window)
    if eff.valid_until is not None and d > eff.valid_until:
        return Verdict(False, R.TRAINING_EXPIRED, eff, window)
    return Verdict(True, None, eff, window)


_PRIORITY = (R.TRAINING_PENDING_REVIEW, R.TRAINING_UNVERIFIED, R.TRAINING_EXPIRED)


@dataclass(frozen=True)
class Best:
    record: TrainingRecord | None
    verdict: Verdict | None
    reason: HookReasonCode | None  # when not met
    hard: bool = False

    @property
    def met(self) -> bool:
        return self.verdict is not None and self.verdict.in_force

    @property
    def valid_until(self) -> date | None:
        return self.verdict.eff.valid_until if self.verdict else None


def _rank(vu: date | None) -> date:
    return vu or date.max


def best(
    records: Iterable[TrainingRecord],
    codes: Iterable[str],
    d: date,
    ctx: EvalCtx,
    at: datetime | None = None,
) -> Best:
    """CC-6 best in-force record whose course is one of `codes` (the code and its satisfiers);
    the longest effective validity wins. Not met: HK5-3 hard stop when the latest record
    (completed_on, then created) is revoked / suspended / failed verification."""
    wanted = set(codes)
    cands = [r for r in records if r.course_code in wanted and not r.anonymised]
    top: tuple[TrainingRecord, Verdict] | None = None
    verdicts: list[tuple[TrainingRecord, Verdict]] = []
    for r in cands:
        v = evaluate(r, d, ctx, at)
        verdicts.append((r, v))
        if v.in_force and (top is None or _rank(v.eff.valid_until) > _rank(top[1].eff.valid_until)):
            top = (r, v)
    if top is not None:
        return Best(top[0], top[1], None)
    real = [(r, v) for r, v in verdicts if r.status != S.draft and r.completed_on <= d]
    if not real:
        return Best(None, None, R.TRAINING_MISSING)
    latest = max(real, key=lambda x: (x[0].completed_on, x[0].seq or 0))
    if latest[1].hard:
        return Best(latest[0], latest[1], latest[1].reason, True)
    for want in _PRIORITY:
        for r, v in sorted(real, key=lambda x: x[0].completed_on, reverse=True):
            if v.reason == want and not v.hard:
                return Best(r, v, want)
    return Best(latest[0], latest[1], R.TRAINING_MISSING)
