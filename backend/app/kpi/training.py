"""Training KPIs K-82…K-88, the K-37 register source, E12/E13 and T17 (spec 5-training §6.8).

Everything here is computed from the requirement engine (`services/train/requirements`) and the
session / record tables; the frontend only formats (TK-1)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.hse_enums import KpiKind, KpiMetric, KpiWarning, NullReason, Severity
from app.core.train_enums import RequirementState, TrainingHoursSource
from app.kpi import engine as engine_mod
from app.kpi import fmt
from app.kpi.engine import ZERO, Agg, Component, Engine, Result
from app.kpi.train_facts import AssessFact, HourFact, TrainFacts
from app.schemas.kpi import Banner
from app.services.train import reference as tref
from app.services.train import requirements as treq

RS = RequirementState
K85_DAYS = 30


@dataclass
class ReqKpis:
    """Requirement-based KPIs (K-82…K-85, K-88) at one date for one population."""

    counted: int = 0
    met: int = 0
    gap: int = 0
    workers: int = 0
    workers_gap: int = 0
    hook_gaps: int = 0
    k85: int = 0
    k88: int = 0
    gaps_by_code: Counter[str] = field(default_factory=Counter)
    hook_gaps_by_code: Counter[str] = field(default_factory=Counter)
    by_course: dict[str, list[int]] = field(default_factory=dict)  # code → [met, counted]
    by_trade: dict[str, list[int]] = field(default_factory=dict)
    by_engagement: dict[uuid.UUID | None, list[int]] = field(default_factory=dict)
    k85_by_course: Counter[str] = field(default_factory=Counter)
    workers_by_trade: dict[str, list[int]] = field(default_factory=dict)  # [ok, all]
    workers_by_engagement: dict[uuid.UUID | None, list[int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "counted": self.counted,
            "met": self.met,
            "gap": self.gap,
            "workers": self.workers,
            "workers_gap": self.workers_gap,
            "hook_gaps": self.hook_gaps,
            "k85": self.k85,
            "k88": self.k88,
            "gaps_by_code": dict(self.gaps_by_code),
            "hook_gaps_by_code": dict(self.hook_gaps_by_code),
        }


def _code_key(r: treq.Req) -> str:
    return r.course_code or r.key


def compute(
    pe: treq.ProjectEval,
    d: date,
    trade: str | None = None,
    course_codes: set[str] | None = None,
    keep: Callable[[treq.Req], bool] | None = None,
) -> ReqKpis:
    out = ReqKpis()
    hook_codes = pe.f.hook_codes
    per_dep: dict[uuid.UUID, list[treq.Req]] = {}
    k85: dict[uuid.UUID, tuple[str, bool]] = {}
    window_end = d + timedelta(days=K85_DAYS)
    for r in pe.reqs:
        if not r.counted:
            continue
        if trade is not None and r.dep.trade.value != trade:
            continue
        if course_codes is not None and not (set(r.codes) & course_codes):
            continue
        if keep is not None and not keep(r):
            continue
        per_dep.setdefault(r.dep.id, []).append(r)
        code = _code_key(r)
        ok = r.state in (RS.met, RS.expiring)
        out.counted += 1
        bc = out.by_course.setdefault(code, [0, 0])
        bt = out.by_trade.setdefault(r.dep.trade.value, [0, 0])
        be = out.by_engagement.setdefault(r.dep.engagement_id, [0, 0])
        for b in (bc, bt, be):
            b[1] += 1
        if ok:
            out.met += 1
            for b in (bc, bt, be):
                b[0] += 1
            vu = r.valid_until
            if r.record is not None and vu is not None and d <= vu <= window_end:
                in_time = r.booked is not None and r.booked.last_day <= vu
                prev = k85.get(r.record.id)
                k85[r.record.id] = (r.record.course_code, in_time or (prev is not None and prev[1]))
        else:
            out.gap += 1
            out.gaps_by_code[code] += 1
            if any(c in hook_codes and c in tref.HOOK_CODES_TODAY for c in r.codes):
                out.hook_gaps += 1
                out.hook_gaps_by_code[code] += 1
    for reqs in per_dep.values():
        dep = reqs[0].dep
        bad = any(r.state == RS.gap for r in reqs)
        out.workers += 1
        out.workers_gap += int(bad)
        for key, store in (
            (dep.trade.value, out.workers_by_trade),
            (dep.engagement_id, out.workers_by_engagement),
        ):
            b = store.setdefault(key, [0, 0])  # type: ignore[arg-type]
            b[1] += 1
            b[0] += int(not bad)
    out.k85 = len(k85)
    out.k88 = sum(1 for _c, t in k85.values() if t)
    out.k85_by_course = Counter(c for c, _t in k85.values())
    return out


def requirement_kpis(
    db: Session,
    project_id: uuid.UUID,
    d: date,
    engagement_ids: set[uuid.UUID] | None = None,
) -> dict[str, Any]:
    pe = treq.evaluate_project(db, project_id, d, engagement_ids=engagement_ids, bookings=True)
    return compute(pe, d).as_dict()


def merge(into: ReqKpis, x: ReqKpis) -> ReqKpis:
    for k in ("counted", "met", "gap", "workers", "workers_gap", "hook_gaps", "k85", "k88"):
        setattr(into, k, getattr(into, k) + getattr(x, k))
    into.gaps_by_code.update(x.gaps_by_code)
    into.hook_gaps_by_code.update(x.hook_gaps_by_code)
    into.k85_by_course.update(x.k85_by_course)
    pairs: list[tuple[dict[Any, list[int]], dict[Any, list[int]]]] = [
        (x.by_course, into.by_course),
        (x.by_trade, into.by_trade),
        (x.by_engagement, into.by_engagement),
        (x.workers_by_trade, into.workers_by_trade),
        (x.workers_by_engagement, into.workers_by_engagement),
    ]
    for src, dst in pairs:
        for key, (a, b) in src.items():
            cur = dst.setdefault(key, [0, 0])
            cur[0] += a
            cur[1] += b
    return into


# ---- engine metrics (registered into app.kpi.engine._DISPATCH) -----------------------------------

M = KpiMetric
HUNDRED = Decimal(100)
FIVE = Decimal(5)


def tfacts(e: Engine) -> TrainFacts | None:
    tf = getattr(e.facts, "train", None)
    return tf if isinstance(tf, TrainFacts) else None


def day(e: Engine, a: Agg) -> date:
    return min(e.as_of, a.window.end)


def _sites_ok(e: Engine, sites: frozenset[uuid.UUID] | Iterable[uuid.UUID] | None) -> bool:
    want = e.flt.sites
    if want is None:
        return True
    return bool(set(sites or ()) & want)


def _course_ok(e: Engine, codes: Iterable[str], category: str | None = None) -> bool:
    want = getattr(e, "course_codes", None)
    cats = getattr(e, "course_categories", None)
    cs = set(codes)
    if want is not None and not (cs & want):
        return False
    if cats is not None:
        if category is not None:
            return category in cats
        tf = tfacts(e)
        known = tf.courses if tf is not None else {}
        return any(c in known and known[c].category.value in cats for c in cs)
    return True


def _req_keep(e: Engine) -> Callable[[treq.Req], bool]:
    trades = getattr(e, "trades", None)

    def keep(r: treq.Req) -> bool:
        if not e.flt.eng_ok(r.dep.engagement_id) or not _sites_ok(e, r.dep.site_ids):
            return False
        if trades is not None and r.dep.trade.value not in trades:
            return False
        return _course_ok(e, r.codes)

    return keep


def req_kpis(e: Engine, a: Agg) -> ReqKpis:
    d = day(e, a)
    cache: dict[date, ReqKpis] = e.__dict__.setdefault("_train_req", {})
    if d in cache:
        return cache[d]
    tf = tfacts(e)
    out = ReqKpis()
    if tf is not None:
        keep = _req_keep(e)
        for pid in tf.pids:
            merge(out, compute(tf.peval(pid, d), d, keep=keep))
    cache[d] = out
    return out


def hour_rows(e: Engine, a: Agg) -> list[HourFact]:
    """Register hours (TH-1…TH-3) of the window's days ≥ training_register_from (to the
    evaluation day), filtered; staff and voided rows included (callers split them)."""
    tf = tfacts(e)
    if tf is None or not e.facts.train_from:
        return []
    start, end = a.window.start, day(e, a)
    if e.flt.zone_filtered:
        return []
    out = []
    for h in tf.hours:
        if h.d < start or h.d > end:
            continue
        rf = e.facts.train_from.get(h.project)
        if rf is None or h.d < rf:
            continue
        if not e.flt.eng_ok(h.eng) and not h.staff:
            continue
        if h.staff and e.flt.engs is not None:
            continue
        if not _sites_ok(e, h.sites) or not _course_ok(e, (h.course,), h.category):
            continue
        out.append(h)
    return out


def _voided_by(h: HourFact | AssessFact, d: date) -> bool:
    return h.voided is not None and h.voided <= d


def register_hours(e: Engine, a: Agg) -> Decimal:
    """K-37 register part: contractor hours, not voided on or before as_of (TH-9)."""
    return sum(
        (h.hours for h in hour_rows(e, a) if not h.staff and not _voided_by(h, e.as_of)),
        ZERO,
    )


def k37_source(e: Engine, a: Agg) -> TrainingHoursSource:
    tf_from = e.facts.train_from
    start, end = a.window.start, a.window.end
    tf = tfacts(e)
    pids = set(tf.pids if tf is not None else []) or set(tf_from)
    if not tf_from:
        return TrainingHoursSource.daily_returns
    reg = [tf_from.get(pid) for pid in pids] if pids else list(tf_from.values())
    if all(x is not None and x <= start for x in reg):
        return TrainingHoursSource.register
    if all(x is None or x > end for x in reg):
        return TrainingHoursSource.daily_returns
    return TrainingHoursSource.mixed


def _k37(e: Engine, a: Agg) -> Result:
    hc = engine_mod._k03_value(a)
    reg = register_hours(e, a) if e.facts.train_from else ZERO
    num = a.trn + reg
    res = Result(M.K37, num / hc if hc else None, num, hc)
    if hc is None:
        res.null_reason = NullReason.NO_EXPOSURE
    if not e.facts.train_from:
        res.data_source = TrainingHoursSource.daily_returns
        return res
    res.data_source = k37_source(e, a)
    if a.trn_reg > 0 and reg >= 0:
        pct = abs(reg - a.trn_reg) / a.trn_reg * HUNDRED
        if pct > FIVE:
            shown = fmt.dec_str(pct, 1) or ""
            res.notes.append(
                Banner(
                    code=KpiWarning.TRAINING_REGISTER_DIFFERS,
                    severity=Severity.info,
                    message_en=f"Daily returns differ from the training register by {shown} % "
                    "for register days",
                    message_ar=f"تختلف التقارير اليومية عن سجل التدريب بنسبة {shown} % لأيام السجل",
                    params={"pct": shown},
                )
            )
    tf = tfacts(e)
    if tf is not None:
        n = sum(
            1
            for pid, last in tf.open_sessions
            if pid in e.facts.train_from and a.window.start <= last <= day(e, a)
        )
        if n:
            res.notes.append(
                Banner(
                    code=KpiWarning.SESSIONS_NOT_CLOSED,
                    severity=Severity.info,
                    message_en=f"{n} sessions not closed",
                    message_ar=f"{n} جلسات غير مغلقة",
                    params={"count": str(n)},
                )
            )
    return res


def _k82(e: Engine, a: Agg) -> Result:
    r = req_kpis(e, a)
    return e._pct(M.K82, r.met, r.counted)


def _k83(e: Engine, a: Agg) -> Result:
    r = req_kpis(e, a)
    return e._pct(M.K83, r.workers - r.workers_gap, r.workers)


def _k84(e: Engine, a: Agg) -> Result:
    r = req_kpis(e, a)
    res = e._count(M.K84, r.gap)
    res.components = [
        Component("workers", "Workers with a gap", "عمال لديهم فجوة", Decimal(r.workers_gap),
                  KpiKind.count_),
        Component("hook_gaps", "Gaps on hook codes", "فجوات في رموز المتطلبات",
                  Decimal(r.hook_gaps), KpiKind.count_),
    ]  # fmt: skip
    return res


def _k85(e: Engine, a: Agg) -> Result:
    return e._count(M.K85, req_kpis(e, a).k85)


def _k86(e: Engine, a: Agg) -> Result:
    rows = hour_rows(e, a)
    contractor = sum((h.hours for h in rows if not h.staff), ZERO)
    voided = sum((h.hours for h in rows if not h.staff and _voided_by(h, e.as_of)), ZERO)
    staff = sum((h.hours for h in rows if h.staff and not _voided_by(h, e.as_of)), ZERO)
    res = Result(M.K86, contractor, contractor, None)
    res.components = [
        Component("voided", "Voided-session hours", "ساعات جلسات ملغاة", voided, KpiKind.hours, 2),
        Component("staff", "Client/PMC staff hours", "ساعات موظفي العميل/الإدارة", staff,
                  KpiKind.hours, 2),
    ]  # fmt: skip
    return res


def assess_rows(e: Engine, a: Agg) -> list[AssessFact]:
    tf = tfacts(e)
    if tf is None:
        return []
    start, end = a.window.start, day(e, a)
    return [
        x
        for x in tf.assess
        if start <= x.d <= end
        and not _voided_by(x, e.as_of)
        and e.flt.eng_ok(x.eng)
        and _sites_ok(e, x.sites)
        and _course_ok(e, (x.course,), x.category)
    ]


def _k87(e: Engine, a: Agg) -> Result:
    rows = assess_rows(e, a)
    return e._pct(M.K87, sum(1 for x in rows if x.passed), len(rows))


def _k88(e: Engine, a: Agg) -> Result:
    r = req_kpis(e, a)
    return e._pct(M.K88, r.k88, r.k85)


def failures(e: Engine, a: Agg) -> tuple[int, int]:
    """E13 inputs in the window: failed verifications and voided sessions (tree-filtered)."""
    tf = tfacts(e)
    if tf is None:
        return 0, 0
    ver = void = 0
    for f in tf.fails:
        if not (a.window.start <= f.d <= a.window.end):
            continue
        if e.flt.engs is not None and not (f.engs & e.flt.engs):
            continue
        if f.kind == "void":
            void += 1
        else:
            ver += 1
    return ver, void


engine_mod._DISPATCH.update(
    {
        M.K37: _k37,
        M.K82: _k82,
        M.K83: _k83,
        M.K84: _k84,
        M.K85: _k85,
        M.K86: _k86,
        M.K87: _k87,
        M.K88: _k88,
    }
)
