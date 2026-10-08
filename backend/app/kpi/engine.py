"""The KPI engine (spec 1-dashboard §5.6, §6). Pure: facts in, exact decimals out.

``Engine(facts, filter, as_of, config)`` filters the role-scoped facts once, then
``aggregate(window)`` builds every base count/sum for a window (cached) and
``result(metric, agg)`` turns them into a metric value with numerator, denominator,
components and warnings. Nothing is rounded here (K-R8); ``app.kpi.fmt`` rounds for output.
"""

import bisect
import itertools
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TypeVar

from app.core.enums import EntityType
from app.core.hse_enums import (
    HIGHER_CONTROLS,
    CaseCategory,
    ControlLevel,
    KpiKind,
    KpiMetric,
    KpiWarning,
    NullReason,
    ObservationType,
    OverdueBucket,
    PermanentDisability,
)
from app.kpi.cases import day_counts, lost_days_charged
from app.kpi.catalogue import CATALOGUE, PHASE2_METRICS, PHASE3_METRICS
from app.kpi.facts import (
    CaseFact,
    EventFact,
    Facts,
    Filter,
    ObsFact,
    WfFact,
)
from app.kpi.periods import Window

M = KpiMetric
C = CaseCategory
HUNDRED = Decimal(100)
ZERO = Decimal(0)
T = TypeVar("T")

CONTROL_LABELS = {
    ControlLevel.elimination: ("Elimination", "إزالة"),
    ControlLevel.substitution: ("Substitution", "استبدال"),
    ControlLevel.engineering: ("Engineering", "هندسي"),
    ControlLevel.administrative: ("Administrative", "إداري"),
    ControlLevel.ppe: ("PPE", "معدات الوقاية"),
}
OBS_LABELS = {
    ObservationType.safe_behaviour: ("Safe behaviour", "سلوك آمن"),
    ObservationType.safe_condition: ("Safe condition", "وضع آمن"),
    ObservationType.unsafe_act: ("Unsafe act", "تصرف غير آمن"),
    ObservationType.unsafe_condition: ("Unsafe condition", "وضع غير آمن"),
}
BUCKETS = (
    (OverdueBucket.d1_7, 1, 7),
    (OverdueBucket.d8_30, 8, 30),
    (OverdueBucket.d31_60, 31, 60),
    (OverdueBucket.d60_plus, 61, 10**9),
)

Source = tuple[EntityType, list[uuid.UUID]]


def bucket_of(days_overdue: int) -> OverdueBucket:
    for b, lo, hi in BUCKETS:
        if lo <= days_overdue <= hi:
            return b
    return OverdueBucket.d1_7


@dataclass(frozen=True)
class EngineConfig:
    ltifr_base: int = 1_000_000
    rate_base: int = 200_000
    low_exposure_hours: int = 200_000


# ---- aggregates ----------------------------------------------------------------------------------


@dataclass
class Agg:
    window: Window
    as_of: date
    # exposure
    mh: Decimal = ZERO
    mh_tier: dict[int, Decimal] = field(default_factory=lambda: {1: ZERO, 2: ZERO, 3: ZERO})
    unzoned_mh: Decimal = ZERO
    hc_total: int = 0
    hc_dates: int = 0
    hc_peak: int = 0
    tbt: int = 0
    tbt_att: int = 0
    ind: int = 0
    trn: Decimal = ZERO
    # cases (eligible per I-4)
    cats: dict[CaseCategory, int] = field(default_factory=lambda: dict.fromkeys(C, 0))
    perm: int = 0
    lost_days: int = 0
    rt_days: int = 0
    provisional: int = 0
    capped: int = 0
    # events
    nm: int = 0
    do: int = 0
    pd: int = 0
    env: int = 0
    pd_cost: Decimal = ZERO
    hipo: int = 0
    late: int = 0
    # observations
    obs: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ObservationType, 0))
    unsafe_closed: int = 0
    # inspections
    d_insp: int = 0
    on_time: int = 0
    late_insp: int = 0
    missed: int = 0
    done: int = 0
    # corrective actions
    raised: int = 0
    closed: int = 0
    k41_den: int = 0
    k41_num: int = 0
    overdue: int = 0
    buckets: dict[OverdueBucket, int] = field(
        default_factory=lambda: dict.fromkeys(OverdueBucket, 0)
    )
    ver_overdue: int = 0
    controls: dict[ControlLevel, int] = field(
        default_factory=lambda: dict.fromkeys(ControlLevel, 0)
    )
    # meetings
    planned_meetings: int = 0
    held_meetings: int = 0
    invited: int = 0
    attended: int = 0
    # completeness
    expected: int = 0
    reported: int = 0

    @property
    def tri(self) -> int:
        c = self.cats
        return c[C.FAT] + c[C.LTI] + c[C.RWC] + c[C.JTC] + c[C.MTC]

    @property
    def lti(self) -> int:
        return self.cats[C.FAT] + self.cats[C.LTI]

    @property
    def dart(self) -> int:
        return self.cats[C.LTI] + self.cats[C.RWC] + self.cats[C.JTC]

    @property
    def obs_total(self) -> int:
        return sum(self.obs.values())

    @property
    def obs_safe(self) -> int:
        return self.obs[ObservationType.safe_behaviour] + self.obs[ObservationType.safe_condition]

    @property
    def obs_unsafe(self) -> int:
        return self.obs[ObservationType.unsafe_act] + self.obs[ObservationType.unsafe_condition]


@dataclass
class Component:
    key: str
    label_en: str
    label_ar: str
    value: Decimal | None
    kind: KpiKind
    decimals: int = 0
    share: Decimal | None = None


@dataclass
class Result:
    metric: KpiMetric
    value: Decimal | None
    numerator: Decimal | int | None = None
    denominator: Decimal | int | None = None
    null_reason: NullReason | None = None
    base: int | None = None
    components: list[Component] = field(default_factory=list)
    warnings: list[KpiWarning] = field(default_factory=list)
    one_case_changes_rate_by: Decimal | None = None


@dataclass(frozen=True)
class LtiFree:
    as_of: date
    days: int
    man_hours: Decimal
    basis: str  # since_last_lti | since_start
    last_lti_date: date | None
    last_lti_case: CaseFact | None
    run_start: date
    longest_days: int
    longest_start: date | None
    longest_end: date | None


def _share(part: Decimal | int, total: Decimal | int) -> Decimal | None:
    return Decimal(part) / Decimal(total) * HUNDRED if total else None


def _slice(items: Sequence[T], keys: list[date], w: Window) -> Sequence[T]:
    lo = bisect.bisect_left(keys, w.start)
    hi = bisect.bisect_right(keys, w.end)
    return items[lo:hi]


class Engine:
    def __init__(
        self,
        facts: Facts,
        flt: Filter,
        as_of: date,
        config: EngineConfig | None = None,
    ) -> None:
        self.facts = facts
        self.flt = flt
        self.as_of = as_of
        self.config = config or EngineConfig()
        zones = facts.zones
        f = flt
        base_wf = [r for r in facts.wf if f.site_ok(r.site) and f.eng_ok(r.eng)]
        self.reported_cells: set[tuple[uuid.UUID, uuid.UUID, date]] = {
            (r.eng, r.site, r.d) for r in base_wf if r.reported
        }
        if f.zone_filtered:
            self.wf = [r for r in base_wf if f.zone_ok(r.zone, zones)]
            zone_sites = (
                {zones[z].site for z in f.zones if z in zones} if f.zones is not None else None
            )
            self.unzoned = [
                r
                for r in base_wf
                if r.zone is None and (zone_sites is None or r.site in zone_sites)
            ]
        else:
            self.wf = base_wf
            self.unzoned = []

        def keep(site: uuid.UUID, zone: uuid.UUID | None, eng: uuid.UUID | None) -> bool:
            return f.site_ok(site) and f.zone_ok(zone, zones) and f.eng_ok(eng)

        self.all_cases = [c for c in facts.cases if keep(c.site, c.zone, c.eng)]
        self.cases = [c for c in self.all_cases if c.eligible]
        self.events = [e for e in facts.events if keep(e.site, e.zone, e.eng)]
        self.obs = [o for o in facts.obs if keep(o.site, o.zone, o.eng)]
        self.insp = [i for i in facts.insp if keep(i.site, i.zone, i.eng)]
        self.cas = [
            a
            for a in facts.cas
            if keep(a.site, a.zone, a.eng) and not (a.cancelled and a.cancelled <= as_of)
        ]
        self.meetings = [m for m in facts.meetings if f.eng_ok(m.eng)]
        self.inds = [
            i
            for i in facts.inds
            if f.eng_ok(i.eng)
            and (f.site_ok(i.site) if i.site is not None else f.sites is None)
            and not f.zone_filtered
        ]
        self._ind_keys = [i.d for i in self.inds]
        self._wf_keys = [r.d for r in self.wf]
        self._unz_keys = [r.d for r in self.unzoned]
        self._case_keys = [c.d for c in self.cases]
        self._event_keys = [e.d for e in self.events]
        self._obs_keys = [o.d for o in self.obs]
        self._cache: dict[Window, Agg] = {}

    # ---- windows --------------------------------------------------------------------------
    def wf_in(self, w: Window) -> Sequence[WfFact]:
        return _slice(self.wf, self._wf_keys, w)

    def cases_in(self, w: Window) -> Sequence[CaseFact]:
        return _slice(self.cases, self._case_keys, w)

    def all_cases_in(self, w: Window) -> list[CaseFact]:
        return [c for c in self.all_cases if w.contains(c.d)]

    def events_in(self, w: Window) -> Sequence[EventFact]:
        return _slice(self.events, self._event_keys, w)

    def obs_in(self, w: Window) -> Sequence[ObsFact]:
        return _slice(self.obs, self._obs_keys, w)

    def case_counts(self, c: CaseFact) -> tuple[int, int, bool]:
        """(lost days charged, restricted + transfer days, capped) at as_of."""
        counts = day_counts(c.dates, self.as_of, c.cap)
        lost = lost_days_charged(c.category, counts, c.fatal, c.permanent, c.fatality_charge)
        return lost, counts.restricted_days + counts.transfer_days, counts.capped

    def aggregate(self, w: Window) -> Agg:
        if w in self._cache:
            return self._cache[w]
        a = Agg(window=w, as_of=self.as_of)
        as_of = self.as_of
        eval_day = min(as_of, w.end)
        engs = self.facts.engagements
        # exposure
        per_day: dict[date, int] = defaultdict(int)
        for r in self.wf_in(w):
            a.mh += r.mh
            e = engs.get(r.eng)
            tier = min(e.tier, 3) if e else 1
            a.mh_tier[tier] = a.mh_tier.get(tier, ZERO) + r.mh
            a.hc_total += r.hc
            per_day[r.d] += r.hc
            a.tbt += r.tbt
            a.tbt_att += r.tbt_att
            a.ind += r.ind
            a.trn += r.trn
        a.ind += len(_slice(self.inds, self._ind_keys, w))
        a.hc_dates = sum(1 for v in per_day.values() if v > 0)
        a.hc_peak = max(per_day.values(), default=0)
        for r in _slice(self.unzoned, self._unz_keys, w):
            a.unzoned_mh += r.mh
        # cases
        for c in self.cases_in(w):
            if c.d > as_of:
                continue
            a.cats[c.category] += 1
            if c.permanent != PermanentDisability.none:
                a.perm += 1
            if c.provisional:
                a.provisional += 1
            lost, rt, capped = self.case_counts(c)
            a.lost_days += lost
            a.rt_days += rt
            a.capped += int(capped)
        # events
        for ev in self.events_in(w):
            if ev.d > as_of:
                continue
            a.nm += "near_miss" in ev.types
            a.do += "dangerous_occurrence" in ev.types
            if "property_damage" in ev.types:
                a.pd += 1
                a.pd_cost += ev.pd_cost
            a.env += "environmental" in ev.types
            a.hipo += ev.hipo
            a.late += ev.late
        # observations
        for o in self.obs_in(w):
            if o.d > as_of:
                continue
            a.obs[o.obs_type] = a.obs.get(o.obs_type, 0) + o.n
            if not o.safe and o.closed_date is not None and o.closed_date <= as_of:
                a.unsafe_closed += o.n
        # inspections
        for i in self.insp:
            done_on = i.completed if i.completed and i.completed <= as_of else None
            if done_on and w.contains(done_on):
                a.done += 1
            if i.planned is None or i.cancelled or not w.contains(i.planned):
                continue
            due_by = i.planned + timedelta(days=i.grace)
            if done_on is None and not due_by < as_of:
                continue  # not yet missable (W7)
            a.d_insp += 1
            if done_on is None:
                a.missed += 1
            elif done_on <= due_by:
                a.on_time += 1
            else:
                a.late_insp += 1
        # corrective actions (cancelled ones already excluded, CA-8)
        for ca in self.cas:
            if w.contains(ca.created) and ca.created <= as_of:
                a.raised += 1
                a.controls[ca.control] += 1
            verified = ca.verified if ca.verified and ca.verified <= as_of else None
            completed = ca.completed if ca.completed and ca.completed <= as_of else None
            if verified and w.contains(verified):
                a.closed += 1
            if w.contains(ca.due) and ca.due <= as_of:
                a.k41_den += 1
                if verified and completed and completed <= ca.due:
                    a.k41_num += 1
            # state at the evaluation day
            if ca.created > eval_day:
                continue
            done_at = ca.completed is not None and ca.completed <= eval_day
            closed_at = ca.verified is not None and ca.verified <= eval_day
            if not done_at and not closed_at and eval_day > ca.due:
                a.overdue += 1
                a.buckets[bucket_of((eval_day - ca.due).days)] += 1
            elif (
                done_at
                and not closed_at
                and ca.completed is not None
                and eval_day > ca.completed + timedelta(days=3)
            ):
                a.ver_overdue += 1
        # meetings
        for m in self.meetings:
            if not w.contains(m.planned):
                continue
            a.planned_meetings += 1
            if m.held is not None and m.held <= as_of:
                a.held_meetings += 1
                a.invited += m.invited
                a.attended += m.attended or 0
        # completeness (K-45)
        a.expected, a.reported = self.completeness(w)
        self._cache[w] = a
        return a

    # ---- completeness -----------------------------------------------------------------------
    def expected_cells(self, w: Window) -> Iterable[tuple[uuid.UUID, uuid.UUID, date]]:
        """Engagement × site × day cells expected to have a return (K-45)."""
        last_allowed = self.as_of - timedelta(days=1)
        for e in self.facts.engagements.values():
            if not self.flt.eng_ok(e.id):
                continue
            first = max(w.start, e.mobilisation)
            last = min(w.end, last_allowed, e.demobilisation or w.end)
            if last < first:
                continue
            for s in sorted(e.site_ids):
                if not self.flt.site_ok(s):
                    continue
                d = first
                while d <= last:
                    yield e.id, s, d
                    d += timedelta(days=1)

    def completeness(self, w: Window) -> tuple[int, int]:
        expected = reported = 0
        for cell in self.expected_cells(w):
            expected += 1
            reported += cell in self.reported_cells
        return expected, reported

    def missing_cells(self, w: Window) -> list[tuple[uuid.UUID, uuid.UUID, date]]:
        return [c for c in self.expected_cells(w) if c not in self.reported_cells]

    # ---- LTI-free (§6.4) --------------------------------------------------------------------
    def run_start(self) -> date:
        start = self.facts.project_start or date(2000, 1, 1)
        if self.flt.engs is not None:
            mobs = [
                e.mobilisation for e in self.facts.engagements.values() if e.id in self.flt.engs
            ]
            if mobs:
                start = max(start, min(mobs))
        return start

    def lti_free(self) -> LtiFree:
        as_of = self.as_of
        ltis = sorted(
            (c for c in self.cases if c.category in (C.FAT, C.LTI) and c.d <= as_of),
            key=lambda c: (c.d, c.incident_ref, c.person_no),
        )
        start = self.run_start()
        if ltis:
            last = ltis[-1]
            days = (as_of - last.d).days
            w = Window(last.d + timedelta(days=1), as_of)
            basis = "since_last_lti"
            run_start = last.d + timedelta(days=1)
        else:
            last = None
            days = (as_of - start).days + 1
            w = Window(start, as_of)
            basis = "since_start"
            run_start = start
        mh = sum((r.mh for r in self.wf_in(w)), ZERO) if w.start <= w.end else ZERO
        # longest run (informational, §6.4.6)
        dates = sorted({c.d for c in ltis})
        runs: list[tuple[int, date | None, date | None]] = []
        if dates:
            runs.append(((dates[0] - start).days, start, dates[0]))
            for prev, nxt in itertools.pairwise(dates):
                runs.append(((nxt - prev).days, prev, nxt))
            runs.append(((as_of - dates[-1]).days, dates[-1], as_of))
        else:
            runs.append((days, start, as_of))
        longest = max(runs, key=lambda r: r[0])
        return LtiFree(
            as_of=as_of,
            days=days,
            man_hours=mh,
            basis=basis,
            last_lti_date=last.d if last else None,
            last_lti_case=last,
            run_start=run_start,
            longest_days=longest[0],
            longest_start=longest[1],
            longest_end=longest[2],
        )

    # ---- metric values ------------------------------------------------------------------------
    def _rate(self, metric: KpiMetric, count: int | Decimal, a: Agg, base: int) -> Result:
        res = Result(metric, None, count, a.mh, base=base)
        if a.mh <= 0:
            res.null_reason = (
                NullReason.NO_ZONE_EXPOSURE if self.flt.zone_filtered else NullReason.NO_EXPOSURE
            )
            return res
        res.value = Decimal(count) * Decimal(base) / a.mh
        if self.flt.zone_filtered and a.unzoned_mh > 0:
            res.warnings.append(KpiWarning.PARTIAL_EXPOSURE)
        if a.mh < self.config.low_exposure_hours:
            res.warnings.append(KpiWarning.LOW_EXPOSURE)
            res.one_case_changes_rate_by = Decimal(base) / a.mh
        return res

    def _pct(
        self,
        metric: KpiMetric,
        num: int | Decimal,
        den: int | Decimal,
        reason: NullReason = NullReason.NO_DENOMINATOR,
    ) -> Result:
        res = Result(metric, _share(num, den), num, den)
        if res.value is None:
            res.null_reason = reason
        return res

    def _count(self, metric: KpiMetric, n: int | Decimal) -> Result:
        return Result(metric, Decimal(n), n)

    def result(self, metric: KpiMetric, a: Agg) -> Result:
        fn = _DISPATCH[metric]
        res = fn(self, a)
        if a.provisional and metric in CASE_METRICS:
            res.warnings.append(KpiWarning.PROVISIONAL_CASES)
        if metric in (M.K17, M.K18, M.K23) and a.capped:
            res.warnings.append(KpiWarning.CAPPED_CASES)
        return res

    def results(self, metrics: Iterable[KpiMetric], w: Window) -> list[Result]:
        a = self.aggregate(w)
        return [self.result(m, a) for m in metrics]

    # ---- drill-down sources -------------------------------------------------------------------
    def sources(self, metric: KpiMetric, w: Window) -> tuple[Source | None, Source | None]:
        """(numerator records, denominator records) behind a metric for a window."""
        as_of = self.as_of
        wf_ids = [i for r in self.wf_in(w) for i in r.ids]
        mh = (EntityType.workforce_return, wf_ids)

        def cases(pred: Callable[[CaseFact], bool]) -> tuple[EntityType, list[uuid.UUID]]:
            ids = [c.id for c in self.cases_in(w) if c.d <= as_of and pred(c)]
            return EntityType.injury_case, ids

        def events(t: str) -> tuple[EntityType, list[uuid.UUID]]:
            ids = [e.id for e in self.events_in(w) if e.d <= as_of and t in e.types]
            return EntityType.incident, ids

        cats: dict[KpiMetric, set[CaseCategory]] = {
            M.K05: {C.FAT}, M.K06: {C.FAT, C.LTI}, M.K07: {C.RWC}, M.K08: {C.JTC},
            M.K09: {C.MTC}, M.K10: {C.FAT, C.LTI, C.RWC, C.JTC, C.MTC},
            M.K11: {C.LTI, C.RWC, C.JTC}, M.K12: {C.FAC}, M.K17: {C.FAT, C.LTI},
        }  # fmt: skip
        rate_of = {
            M.K20: M.K06, M.K21: M.K10, M.K22: M.K11, M.K23: M.K17, M.K24: M.K12,
            M.K25: M.K13, M.K26a: M.K14, M.K26b: M.K15, M.K26c: M.K16, M.K32: M.K30,
        }  # fmt: skip
        ev = {
            M.K13: "near_miss", M.K14: "dangerous_occurrence", M.K15: "property_damage",
            M.K16: "environmental",
        }  # fmt: skip
        if metric in rate_of:
            num, _ = self.sources(rate_of[metric], w)
            return num, mh
        if metric in cats:
            return cases(lambda c: c.category in cats[metric]), None
        if metric == M.K05b:
            return cases(lambda c: c.permanent != PermanentDisability.none), None
        if metric == M.K18:
            return cases(lambda c: self.case_counts(c)[1] > 0), None
        if metric in ev:
            return events(ev[metric]), None
        if metric == M.K44:
            return (EntityType.incident, [e.id for e in self.events_in(w) if e.hipo]), None
        if metric == M.K47:
            return (EntityType.incident, [e.id for e in self.events_in(w) if e.late]), None
        if metric == M.K27:
            n, _ = self.sources(M.K13, w)
            d1, _ = self.sources(M.K10, w)
            d2, _ = self.sources(M.K12, w)
            assert d1 is not None and d2 is not None  # noqa: S101
            return n, (EntityType.injury_case, d1[1] + d2[1])
        if metric in (M.K01, M.K02, M.K03, M.K04, M.K36, M.K37, M.K38, M.K45):
            return mh, None
        if metric in (M.K28, M.K29):
            lf = self.lti_free()
            ids = [lf.last_lti_case.id] if lf.last_lti_case else []
            return (EntityType.injury_case, ids), None
        if metric in (M.K30, M.K31, M.K33):
            obs = [i for o in self.obs_in(w) if o.d <= as_of for i in o.ids]
            return (EntityType.observation, obs), None
        if metric in (M.K34, M.K35):
            ids = [
                i.id for i in self.insp if i.planned and not i.cancelled and w.contains(i.planned)
            ]
            return (EntityType.inspection, ids), None
        if metric == M.K35b:
            ids = [i.id for i in self.insp if i.completed and w.contains(i.completed)]
            return (EntityType.inspection, ids), None
        if metric in (M.K40, M.K43):
            ids = [ca.id for ca in self.cas if w.contains(ca.created)]
            return (EntityType.corrective_action, ids), None
        if metric == M.K41:
            den_ids = [ca.id for ca in self.cas if w.contains(ca.due) and ca.due <= as_of]
            num_ids = [
                ca.id
                for ca in self.cas
                if ca.id in set(den_ids)
                and ca.verified
                and ca.verified <= as_of
                and ca.completed
                and ca.completed <= ca.due
            ]
            return (EntityType.corrective_action, num_ids), (EntityType.corrective_action, den_ids)
        if metric in (M.K42, M.K42b):
            e = min(as_of, w.end)
            ids = []
            for ca in self.cas:
                if ca.created > e:
                    continue
                done_at = ca.completed is not None and ca.completed <= e
                closed_at = ca.verified is not None and ca.verified <= e
                if metric == M.K42 and not done_at and not closed_at and e > ca.due:
                    ids.append(ca.id)
                if (
                    metric == M.K42b
                    and done_at
                    and not closed_at
                    and ca.completed is not None
                    and e > ca.completed + timedelta(days=3)
                ):
                    ids.append(ca.id)
            return (EntityType.corrective_action, ids), None
        if metric == M.K39:
            ids = [m.id for m in self.meetings if w.contains(m.planned)]
            return (EntityType.hse_meeting, ids), None
        return None, None


CASE_METRICS = frozenset(
    {M.K05, M.K05b, M.K06, M.K07, M.K08, M.K09, M.K10, M.K11, M.K12, M.K17, M.K18,
     M.K20, M.K21, M.K22, M.K23, M.K24, M.K27, M.K28, M.K29}
)  # fmt: skip


def _k01(e: Engine, a: Agg) -> Result:
    return Result(M.K01, a.mh, a.mh)


def _k02(e: Engine, a: Agg) -> Result:
    direct = a.mh_tier.get(1, ZERO)
    sub = a.mh - direct
    res = e._pct(M.K02, direct, a.mh, NullReason.NO_EXPOSURE)
    res.components = [
        Component("direct", "Direct (tier 1)", "مباشر (المستوى 1)", direct, KpiKind.hours, 0,
                  _share(direct, a.mh)),
        Component("subcontractor", "Subcontractor (tier ≥ 2)", "مقاول باطن (المستوى 2 فأعلى)",
                  sub, KpiKind.hours, 0, _share(sub, a.mh)),
    ] + [
        Component(f"tier_{t}", f"Tier {t}", f"المستوى {t}", a.mh_tier.get(t, ZERO),
                  KpiKind.hours, 0, _share(a.mh_tier.get(t, ZERO), a.mh))
        for t in (1, 2, 3)
    ]  # fmt: skip
    return res


def _k03_value(a: Agg) -> Decimal | None:
    return Decimal(a.hc_total) / Decimal(a.hc_dates) if a.hc_dates else None


def _k03(e: Engine, a: Agg) -> Result:
    res = Result(M.K03, _k03_value(a), a.hc_total, a.hc_dates)
    if res.value is None:
        res.null_reason = NullReason.NO_EXPOSURE
    return res


def _k04(e: Engine, a: Agg) -> Result:
    return e._count(M.K04, a.hc_peak)


def _k15(e: Engine, a: Agg) -> Result:
    res = e._count(M.K15, a.pd)
    res.components = [
        Component(
            "cost_sar",
            "Estimated cost (SAR)",
            "التكلفة التقديرية (ريال)",
            a.pd_cost,
            KpiKind.hours,
            2,
        )
    ]
    return res


def _k27(e: Engine, a: Agg) -> Result:
    den = a.tri + a.cats[C.FAC]
    res = Result(M.K27, Decimal(a.nm) / Decimal(den) if den else None, a.nm, den)
    if den == 0:
        res.null_reason = NullReason.NO_DENOMINATOR
    return res


def _k28(e: Engine, a: Agg) -> Result:
    lf = e.lti_free()
    return Result(M.K28, Decimal(lf.days), lf.days)


def _k29(e: Engine, a: Agg) -> Result:
    lf = e.lti_free()
    return Result(M.K29, lf.man_hours, lf.man_hours)


def _k30(e: Engine, a: Agg) -> Result:
    res = e._count(M.K30, a.obs_total)
    res.components = [
        Component("safe", "Safe", "آمنة", Decimal(a.obs_safe), KpiKind.count_, 0,
                  _share(a.obs_safe, a.obs_total)),
        Component("unsafe", "Unsafe", "غير آمنة", Decimal(a.obs_unsafe), KpiKind.count_, 0,
                  _share(a.obs_unsafe, a.obs_total)),
    ] + [
        Component(t.value, OBS_LABELS[t][0], OBS_LABELS[t][1], Decimal(a.obs.get(t, 0)),
                  KpiKind.count_, 0, _share(a.obs.get(t, 0), a.obs_total))
        for t in ObservationType
    ]  # fmt: skip
    return res


def _k36(e: Engine, a: Agg) -> Result:
    res = e._count(M.K36, a.tbt)
    res.components = [
        Component("attendees", "Attendees", "الحضور", Decimal(a.tbt_att), KpiKind.count_)
    ]
    return res


def _k37(e: Engine, a: Agg) -> Result:
    hc = _k03_value(a)
    res = Result(M.K37, a.trn / hc if hc else None, a.trn, hc)
    if hc is None:
        res.null_reason = NullReason.NO_EXPOSURE
    return res


def _k39(e: Engine, a: Agg) -> Result:
    res = e._pct(M.K39, a.attended, a.invited)
    res.components = [
        Component("held_pct", "Meetings held vs planned", "الاجتماعات المنعقدة من المخطط",
                  _share(a.held_meetings, a.planned_meetings), KpiKind.percentage, 1),
        Component("held", "Held", "منعقدة", Decimal(a.held_meetings), KpiKind.count_),
        Component("planned", "Planned", "مخططة", Decimal(a.planned_meetings), KpiKind.count_),
    ]  # fmt: skip
    return res


def _k40(e: Engine, a: Agg) -> Result:
    res = e._count(M.K40, a.raised)
    res.components = [Component("closed", "Closed", "مغلقة", Decimal(a.closed), KpiKind.count_)]
    return res


def _k42(e: Engine, a: Agg) -> Result:
    res = e._count(M.K42, a.overdue)
    res.components = [
        Component(b.value, f"{b.value} days", f"{b.value} يوم", Decimal(a.buckets[b]),
                  KpiKind.count_, 0, _share(a.buckets[b], a.overdue))
        for b, _, _ in BUCKETS
    ]  # fmt: skip
    return res


def _k43(e: Engine, a: Agg) -> Result:
    higher = sum(a.controls[c] for c in HIGHER_CONTROLS)
    res = e._pct(M.K43, higher, a.raised)
    res.components = [
        Component(c.value, *CONTROL_LABELS[c], Decimal(a.controls[c]), KpiKind.count_, 0,
                  _share(a.controls[c], a.raised))
        for c in ControlLevel
    ]  # fmt: skip
    return res


def _k45(e: Engine, a: Agg) -> Result:
    return e._pct(M.K45, a.reported, a.expected)


def _k46(e: Engine, a: Agg) -> Result:
    return Result(M.K46, None, null_reason=NullReason.NOT_AVAILABLE_YET)


def _not_yet(metric: KpiMetric) -> Callable[[Engine, Agg], Result]:
    def fn(e: Engine, a: Agg) -> Result:
        return Result(metric, None, null_reason=NullReason.NOT_AVAILABLE_YET)

    return fn


def _rate_fn(
    metric: KpiMetric, count: Callable[[Agg], int], ltifr: bool = False
) -> Callable[[Engine, Agg], Result]:
    def fn(e: Engine, a: Agg) -> Result:
        return e._rate(metric, count(a), a, e.config.ltifr_base if ltifr else e.config.rate_base)

    return fn


def _count_fn(metric: KpiMetric, count: Callable[[Agg], int]) -> Callable[[Engine, Agg], Result]:
    def fn(e: Engine, a: Agg) -> Result:
        return e._count(metric, count(a))

    return fn


def _pct_fn(
    metric: KpiMetric, num: Callable[[Agg], int], den: Callable[[Agg], int]
) -> Callable[[Engine, Agg], Result]:
    def fn(e: Engine, a: Agg) -> Result:
        return e._pct(metric, num(a), den(a))

    return fn


_DISPATCH: dict[KpiMetric, Callable[[Engine, Agg], Result]] = {
    M.K01: _k01,
    M.K02: _k02,
    M.K03: _k03,
    M.K04: _k04,
    M.K05: _count_fn(M.K05, lambda a: a.cats[C.FAT]),
    M.K05b: _count_fn(M.K05b, lambda a: a.perm),
    M.K06: _count_fn(M.K06, lambda a: a.lti),
    M.K07: _count_fn(M.K07, lambda a: a.cats[C.RWC]),
    M.K08: _count_fn(M.K08, lambda a: a.cats[C.JTC]),
    M.K09: _count_fn(M.K09, lambda a: a.cats[C.MTC]),
    M.K10: _count_fn(M.K10, lambda a: a.tri),
    M.K11: _count_fn(M.K11, lambda a: a.dart),
    M.K12: _count_fn(M.K12, lambda a: a.cats[C.FAC]),
    M.K13: _count_fn(M.K13, lambda a: a.nm),
    M.K14: _count_fn(M.K14, lambda a: a.do),
    M.K15: _k15,
    M.K16: _count_fn(M.K16, lambda a: a.env),
    M.K17: _count_fn(M.K17, lambda a: a.lost_days),
    M.K18: _count_fn(M.K18, lambda a: a.rt_days),
    M.K20: _rate_fn(M.K20, lambda a: a.lti, ltifr=True),
    M.K21: _rate_fn(M.K21, lambda a: a.tri),
    M.K22: _rate_fn(M.K22, lambda a: a.dart),
    M.K23: _rate_fn(M.K23, lambda a: a.lost_days),
    M.K24: _rate_fn(M.K24, lambda a: a.cats[C.FAC]),
    M.K25: _rate_fn(M.K25, lambda a: a.nm),
    M.K26a: _rate_fn(M.K26a, lambda a: a.do),
    M.K26b: _rate_fn(M.K26b, lambda a: a.pd),
    M.K26c: _rate_fn(M.K26c, lambda a: a.env),
    M.K27: _k27,
    M.K28: _k28,
    M.K29: _k29,
    M.K30: _k30,
    M.K31: _pct_fn(M.K31, lambda a: a.obs_safe, lambda a: a.obs_total),
    M.K32: _rate_fn(M.K32, lambda a: a.obs_total),
    M.K33: _pct_fn(M.K33, lambda a: a.unsafe_closed, lambda a: a.obs_unsafe),
    M.K34: _pct_fn(M.K34, lambda a: a.on_time, lambda a: a.d_insp),
    M.K35: _pct_fn(M.K35, lambda a: a.on_time + a.late_insp, lambda a: a.d_insp),
    M.K35b: _count_fn(M.K35b, lambda a: a.done),
    M.K36: _k36,
    M.K37: _k37,
    M.K38: _count_fn(M.K38, lambda a: a.ind),
    M.K39: _k39,
    M.K40: _k40,
    M.K41: _pct_fn(M.K41, lambda a: a.k41_num, lambda a: a.k41_den),
    M.K42: _k42,
    M.K42b: _count_fn(M.K42b, lambda a: a.ver_overdue),
    M.K43: _k43,
    M.K44: _count_fn(M.K44, lambda a: a.hipo),
    M.K45: _k45,
    M.K46: _k46,
    M.K47: _count_fn(M.K47, lambda a: a.late),
    **{m: _not_yet(m) for m in PHASE2_METRICS},  # replaced by app.kpi.access
    **{m: _not_yet(m) for m in PHASE3_METRICS},  # Phase 3 stage 2: app.kpi.ptw
}
import app.kpi.access  # noqa: E402  (registers K-48…K-60 into _DISPATCH)
import app.kpi.ptw  # noqa: E402, F401  (registers K-46, K-46b, K-61…K-71 into _DISPATCH)

assert set(_DISPATCH) == set(KpiMetric) == set(CATALOGUE)  # noqa: S101
