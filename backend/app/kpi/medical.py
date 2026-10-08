"""Occupational health KPIs K-89…K-96 (spec 6a-occupational-health §6.3–§6.6, MK-1…MK-3).

Requirement-based KPIs (K-89…K-92, K-96) come from the medical requirement engine
(`services/med/requirements`) so the KPI page, the gap register and the readiness view agree
(MK-1). Holds and referrals (K-93…K-95) are snapshotted per project on first use. Every request
works on a copy bound to its own session (`with_db`), as the training facts do."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import WorkerPersonType
from app.core.clock import now
from app.core.hse_enums import KpiKind, KpiMetric
from app.core.med_enums import FitnessRequirementState, HoldReason, HoldStatus, ReferralStatus
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.models import Deployment, FitnessHold, FitnessReferral, Worker

UUID = uuid.UUID
M = KpiMetric
RS = FitnessRequirementState
K92_DAYS = 30


@dataclass(frozen=True, slots=True)
class HoldFact:
    project: UUID
    eng: UUID | None
    trade: str | None
    sites: frozenset[UUID]
    contractor: bool
    reason: str
    started_at: datetime
    released_at: datetime | None
    cancelled_at: datetime | None
    cancelled: bool
    work_during_hold: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class RefFact:
    project: UUID
    eng: UUID | None
    trade: str | None
    sites: frozenset[UUID]
    raised_at: datetime
    due_at: datetime
    assessed_at: datetime | None
    cancelled: bool


@dataclass
class MedFacts:
    pids: list[UUID]
    holds: list[HoldFact] = field(default_factory=list)
    referrals: list[RefFact] = field(default_factory=list)
    referral_hours: dict[UUID, int] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    pe_cache: dict[tuple[Any, ...], Any] = field(default_factory=dict)
    db: Session | None = None

    def with_db(self, db: Session) -> MedFacts:
        out = copy.copy(self)
        out.db = db
        return out

    def peval(self, pid: UUID, d: date) -> Any:
        from app.services.med import requirements as rq  # noqa: PLC0415

        key = (pid, d)
        pe = self.pe_cache.get(key)
        if pe is None:
            assert self.db is not None  # noqa: S101
            pe = self.pe_cache[key] = rq.evaluate_project(self.db, pid, d)
        return pe


def load_med(db: Session, pids: list[UUID], _shared: Any = None) -> MedFacts:
    from app.services.med import common  # noqa: PLC0415

    mf = MedFacts(pids=list(pids), db=db)
    mf.categories = {c: fc.category.value for c, fc in common.codes(db).items()}
    for pid in pids:
        mf.referral_hours[pid] = common.settings(db, pid).referral_assessment_hours
    holds = list(db.scalars(select(FitnessHold).where(FitnessHold.project_id.in_(pids))))
    refs = list(db.scalars(select(FitnessReferral).where(FitnessReferral.project_id.in_(pids))))
    wids = {h.worker_id for h in holds} | {r.worker_id for r in refs}
    deps: dict[tuple[UUID, UUID], Deployment] = {}
    contractor: set[UUID] = set()
    if wids:
        for dep in db.scalars(
            select(Deployment).where(
                Deployment.worker_id.in_(wids), Deployment.project_id.in_(pids)
            )
        ):
            deps[(dep.worker_id, dep.project_id)] = dep
        contractor = set(
            db.scalars(
                select(Worker.id).where(
                    Worker.id.in_(wids),
                    Worker.person_type == WorkerPersonType.contractor_worker,
                )
            )
        )

    def where(wid: UUID, pid: UUID) -> tuple[str | None, frozenset[UUID]]:
        dep = deps.get((wid, pid))
        if dep is None:
            return None, frozenset()
        return dep.trade.value, frozenset(dep.site_ids or [])

    for h in holds:
        trade, sites = where(h.worker_id, h.project_id)
        mf.holds.append(
            HoldFact(
                project=h.project_id,
                eng=h.engagement_id,
                trade=trade,
                sites=sites,
                contractor=h.worker_id in contractor,
                reason=h.reason.value,
                started_at=h.started_at,
                released_at=h.released_at,
                cancelled_at=h.cancelled_at,
                cancelled=h.status == HoldStatus.cancelled,
                work_during_hold=tuple(
                    datetime.fromisoformat(x["at"]) for x in h.work_during_hold or []
                ),
            )
        )
    for r in refs:
        trade, sites = where(r.worker_id, r.project_id)
        mf.referrals.append(
            RefFact(
                project=r.project_id,
                eng=r.engagement_id,
                trade=trade,
                sites=sites,
                raised_at=r.raised_at,
                due_at=r.due_at,
                assessed_at=r.assessed_at,
                cancelled=r.status == ReferralStatus.cancelled,
            )
        )
    return mf


# ---- requirement statistics ---------------------------------------------------------------------


@dataclass
class ReqStats:
    """Counted requirements (K-89…K-91), K-92 lines and K-96 workers at one date."""

    reqs: list[Any] = field(default_factory=list)  # counted rq.Req, filtered
    k92: int = 0
    k96: int = 0
    k96_engs: list[UUID | None] = field(default_factory=list)
    k96_trades: list[str] = field(default_factory=list)

    @property
    def met(self) -> int:
        return sum(1 for r in self.reqs if r.state in (RS.met, RS.expiring))

    @property
    def gaps(self) -> list[Any]:
        return [r for r in self.reqs if r.state == RS.gap]

    def workers(self) -> tuple[int, int]:
        """(deployments with ≥ 1 counted requirement, of those with ≥ 1 gap)."""
        per: dict[UUID, bool] = {}
        for r in self.reqs:
            per[r.dep.id] = per.get(r.dep.id, False) or r.state == RS.gap
        return len(per), sum(per.values())


def mfacts(e: Engine) -> MedFacts | None:
    mf = getattr(e.facts, "med", None)
    return mf if isinstance(mf, MedFacts) else None


def day(e: Engine, a: Agg) -> date:
    return min(e.as_of, a.window.end)


def instant(d: date) -> datetime:
    from app.services.med import common  # noqa: PLC0415

    return min(common.day_end_utc(d), now())


def _sites_ok(e: Engine, sites: frozenset[UUID] | list[UUID] | None) -> bool:
    want = e.flt.sites
    return want is None or bool(set(sites or ()) & want)


def _trade_ok(e: Engine, trade: str | None) -> bool:
    trades = getattr(e, "trades", None)
    return trades is None or trade in trades


def code_keep(e: Engine, mf: MedFacts) -> Callable[[str], bool]:
    codes = getattr(e, "med_codes", None)
    cats = getattr(e, "med_categories", None)

    def ok(code: str) -> bool:
        if codes is not None and code not in codes:
            return False
        return cats is None or mf.categories.get(code) in cats

    return ok


def _dep_ok(e: Engine, dep: Deployment) -> bool:
    return (
        e.flt.eng_ok(dep.engagement_id)
        and _sites_ok(e, dep.site_ids)
        and _trade_ok(e, dep.trade.value)
    )


def req_stats(e: Engine, d: date) -> ReqStats:
    cache: dict[date, ReqStats] = e.__dict__.setdefault("_med_req", {})
    if d in cache:
        return cache[d]
    from app.services.med import engine as meng  # noqa: PLC0415
    from app.services.med import reference as mref  # noqa: PLC0415

    out = ReqStats()
    mf = mfacts(e)
    if mf is not None and not e.flt.zone_filtered:
        ok_code = code_keep(e, mf)
        window_end = d + timedelta(days=K92_DAYS)
        at = instant(d)
        for pid in mf.pids:
            pe = mf.peval(pid, d)
            lines: set[tuple[UUID, str]] = set()
            for r in pe.reqs:
                if not r.counted or not ok_code(r.code) or not _dep_ok(e, r.dep):
                    continue
                out.reqs.append(r)
                chk = r.check
                if (
                    r.state in (RS.met, RS.expiring)
                    and chk is not None
                    and chk.row is not None
                    and chk.valid_until is not None
                    and d <= chk.valid_until <= window_end
                ):
                    lines.add((chk.row.line.id, r.code))
            out.k92 += len({x[0] for x in lines})
            f = pe.f
            for dep in f.deps:
                w = f.workers.get(dep.worker_id)
                if w is None or w.person_type != WorkerPersonType.contractor_worker:
                    continue
                if not _dep_ok(e, dep):
                    continue
                wf = f.facts.get(dep.worker_id)
                if wf is None:
                    continue
                if any(
                    mref.review_required(x["code"]) and ok_code(row.line.code)
                    for row, x in meng.restrictions_in_force(f.ctx, wf, at)
                ):
                    out.k96 += 1
                    out.k96_engs.append(dep.engagement_id)
                    out.k96_trades.append(dep.trade.value)
    cache[d] = out
    return out


# ---- holds and referrals ------------------------------------------------------------------------


def _fact_ok(e: Engine, x: HoldFact | RefFact) -> bool:
    return e.flt.eng_ok(x.eng) and _sites_ok(e, x.sites) and _trade_ok(e, x.trade)


def active_holds(e: Engine, d: date) -> tuple[list[HoldFact], list[HoldFact]]:
    """K-93: (Active holds of contractor_worker deployments at d, of those overdue)."""
    mf = mfacts(e)
    if mf is None or e.flt.zone_filtered:
        return [], []
    at = instant(d)
    act = [
        h
        for h in mf.holds
        if h.contractor
        and _fact_ok(e, h)
        and h.started_at <= at
        and (h.released_at is None or h.released_at > at)
        and not (h.cancelled and (h.cancelled_at is None or h.cancelled_at <= at))
    ]
    late = [
        h
        for h in act
        if h.reason in (HoldReason.referral.value, HoldReason.manual.value)
        and at > h.started_at + timedelta(hours=mf.referral_hours.get(h.project, 24))
    ]
    return act, late


def released_holds(e: Engine, a: Agg) -> list[HoldFact]:
    from app.services.med import common  # noqa: PLC0415

    mf = mfacts(e)
    if mf is None or e.flt.zone_filtered:
        return []
    start, end = a.window.start, day(e, a)
    return [
        h
        for h in mf.holds
        if h.released_at is not None
        and not h.cancelled
        and start <= common.local_day(h.released_at) <= end
        and _fact_ok(e, h)
    ]


def counted_referrals(e: Engine, a: Agg) -> list[RefFact]:
    from app.services.med import common  # noqa: PLC0415

    mf = mfacts(e)
    if mf is None or e.flt.zone_filtered:
        return []
    start, end = a.window.start, day(e, a)
    closes = instant(end)
    return [
        r
        for r in mf.referrals
        if not r.cancelled
        and start <= common.local_day(r.raised_at) <= end
        and r.due_at <= closes
        and _fact_ok(e, r)
    ]


def on_time(r: RefFact) -> bool:
    return r.assessed_at is not None and r.assessed_at <= r.due_at


# ---- engine metrics ------------------------------------------------------------------------------


def _k89(e: Engine, a: Agg) -> Result:
    s = req_stats(e, day(e, a))
    return e._pct(M.K89, s.met, len(s.reqs))


def _k90(e: Engine, a: Agg) -> Result:
    n, bad = req_stats(e, day(e, a)).workers()
    return e._pct(M.K90, n - bad, n)


def _k91(e: Engine, a: Agg) -> Result:
    s = req_stats(e, day(e, a))
    gaps = s.gaps
    _n, workers = s.workers()
    res = e._count(M.K91, len(gaps))
    res.components = [
        Component("workers", "Workers with a gap", "عمال لديهم فجوة", Decimal(workers),
                  KpiKind.count_),
        Component("hook_gaps", "Gaps on hook codes", "فجوات في رموز المتطلبات",
                  Decimal(sum(1 for r in gaps if r.hook_code)), KpiKind.count_),
    ]  # fmt: skip
    return res


def _k92(e: Engine, a: Agg) -> Result:
    return e._count(M.K92, req_stats(e, day(e, a)).k92)


def _k93(e: Engine, a: Agg) -> Result:
    act, late = active_holds(e, day(e, a))
    res = e._count(M.K93, len(act))
    res.components = [
        Component("overdue", "Past the referral assessment window",
                  "تجاوزت مهلة تقييم الإحالة", Decimal(len(late)), KpiKind.count_),
    ]  # fmt: skip
    return res


def _k94(e: Engine, a: Agg) -> Result:
    rows = released_holds(e, a)
    return e._pct(M.K94, sum(1 for h in rows if not h.work_during_hold), len(rows))


def _k95(e: Engine, a: Agg) -> Result:
    rows = counted_referrals(e, a)
    return e._pct(M.K95, sum(1 for r in rows if on_time(r)), len(rows))


def _k96(e: Engine, a: Agg) -> Result:
    return e._count(M.K96, req_stats(e, day(e, a)).k96)


def e15_inputs(e: Engine, a: Agg) -> dict[str, int]:
    """E15 inputs in the window: work-during-hold detections on released or still-Active holds
    (counts by hold only; never identities or reasons)."""
    from app.services.med import common  # noqa: PLC0415

    mf = mfacts(e)
    if mf is None:
        return {"released": 0, "breaches": 0}
    start, end = a.window.start, day(e, a)
    rel = released_holds(e, a)
    n = sum(1 for h in rel if h.work_during_hold)
    at = instant(end)
    for h in mf.holds:
        if h.cancelled or not _fact_ok(e, h) or h in rel:
            continue
        if h.released_at is not None and h.released_at <= at:
            continue
        if any(start <= common.local_day(x) <= end for x in h.work_during_hold):
            n += 1
    return {"released": len(rel), "breaches": n}


engine_mod._DISPATCH.update(
    {
        M.K89: _k89,
        M.K90: _k90,
        M.K91: _k91,
        M.K92: _k92,
        M.K93: _k93,
        M.K94: _k94,
        M.K95: _k95,
        M.K96: _k96,
    }
)
