"""Occupational health KPI page (GET /kpi/occupational-health, 6a §6.6, MK-1…MK-5).

Engine values only; aggregates only. Codes, categories, contractor short codes, trades, months
and gap reasons are the only keys; never names, worker_no, outcomes, restrictions, hold or
referral reasons per person, examiners or clinics (MK-4). Cells and the headline person counts
of K-91 workers, K-93 and K-96 of 1–4 are shown as "<5" except to the HSE Manager and OH
Practitioners (MK-3)."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.hse_enums import KpiMetric
from app.core.med_enums import FitnessCategory, MedicalKpiGroupBy
from app.kpi import fmt, present, service
from app.kpi import medical as km
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.facts import Filter
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.schemas.kpi import KpiValue
from app.schemas.medical import MedicalBreakdown, MedicalBreakdownRow, MedicalKpiResponse
from app.services.med import common as mcommon

M = KpiMetric
G = MedicalKpiGroupBy
MEDICAL_METRICS = [M.K89, M.K90, M.K91, M.K92, M.K93, M.K94, M.K95, M.K96]
REQ_METRICS = [M.K89, M.K90, M.K91, M.K92, M.K96]
PERSON_COUNTS = {M.K91, M.K93, M.K96}
SMALL = "<5"
CATEGORY_LABELS = {
    FitnessCategory.general.value: ("General fitness", "اللياقة العامة"),
    FitnessCategory.task.value: ("Task-specific fitness", "لياقة خاصة بالمهمة"),
    FitnessCategory.surveillance.value: ("Health surveillance", "المراقبة الصحية"),
}


def _vals(xs: Any) -> frozenset[str] | None:
    out = frozenset(getattr(x, "value", x) for x in xs or [])
    return out or None


def med_engine(
    scope: Scope, codes: list[str], categories: list[FitnessCategory], e: Engine | None = None
) -> Engine:
    e = e or scope.engine
    e.trades = _vals(getattr(scope.query, "trades", []))  # type: ignore[attr-defined]
    e.med_codes = _vals(codes)  # type: ignore[attr-defined]
    e.med_categories = _vals(categories)  # type: ignore[attr-defined]
    return e


def small_ok(scope: Scope) -> bool:
    """MK-3: only the HSE Manager and OH Practitioners see exact counts of 1–4."""
    return scope.p.is_manager or all(mcommon.is_oh(scope.p, x.id) for x in scope.projects)


def _small(n: str | None) -> bool:
    if n is None:
        return False
    try:
        return 0 < Decimal(n) < 5
    except ArithmeticError:
        return False


def _suppress_value(v: KpiValue) -> KpiValue:
    if v.metric in PERSON_COUNTS:
        if v.metric != M.K91 and _small(v.value):
            v.value, v.display, v.numerator = None, SMALL, None
            v.comparisons = []
        for c in v.components:
            if _small(c.value):
                c.value, c.display = None, SMALL
    return v


def _row(
    metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window, hide: bool
) -> MedicalBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    num, den = fmt.exact(r.numerator), fmt.exact(r.denominator)
    persons = num if r.denominator is None else den
    if hide and _small(persons):
        return MedicalBreakdownRow(
            key=key, label_en=en, label_ar=ar, value=None, display=SMALL, suppressed=True
        )
    return MedicalBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=num,
        denominator=den,
    )


def _sub(scope: Scope, base: Engine, flt: Filter, **attrs: frozenset[str] | None) -> Engine:
    e = scope.sub_engine(flt)
    for k in ("trades", "med_codes", "med_categories"):
        setattr(e, k, getattr(base, k, None))
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


def _tier2(scope: Scope) -> bool:
    return all(
        scope.p.grant(x.id, Capability.fitness_functional_view) is not None for x in scope.projects
    )


def _breakdowns(
    scope: Scope, e: Engine, metrics: list[KpiMetric], group_by: list[MedicalKpiGroupBy]
) -> list[MedicalBreakdown]:
    w = scope.window
    a = e.aggregate(w)
    hide = not small_ok(scope)
    out: list[MedicalBreakdown] = []
    stats = km.req_stats(e, km.day(e, a))
    mf = km.mfacts(e)
    names = (
        {c: (fc.name_en, fc.name_ar) for c, fc in mcommon.codes(mf.db).items()}
        if (mf is not None and mf.db is not None)
        else {}
    )
    req_metrics = [m for m in metrics if m in REQ_METRICS]
    for g in dict.fromkeys(group_by):
        if g == G.code:
            codes = sorted({r.code for r in stats.reqs})
            for m in req_metrics:
                rows = [
                    _row(m, c, names.get(c, (c, c))[0], names.get(c, (c, c))[1],
                         _sub(scope, e, scope.flt, med_codes=frozenset({c})), w, hide)
                    for c in codes
                ]  # fmt: skip
                out.append(MedicalBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.code_category:
            cats = sorted({mf.categories.get(r.code, "") for r in stats.reqs} if mf else set())
            for m in req_metrics:
                rows = [
                    _row(m, c, *CATEGORY_LABELS.get(c, (c, c)),
                         _sub(scope, e, scope.flt, med_categories=frozenset({c})), w, hide)
                    for c in cats
                ]  # fmt: skip
                out.append(MedicalBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.trade:
            trades = sorted({r.dep.trade.value for r in stats.reqs})
            for m in req_metrics:
                rows = [
                    _row(m, t, t, t, _sub(scope, e, scope.flt, trades=frozenset({t})), w, hide)
                    for t in trades
                ]
                out.append(MedicalBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            tops = sorted(
                (
                    x
                    for x in scope.facts.engagements.values()
                    if x.tier == 1 and (scope.flt.engs is None or x.id in scope.flt.engs)
                ),
                key=lambda x: x.code,
            )
            for m in metrics:
                rows = [
                    _row(
                        m,
                        top.code,
                        top.name_en,
                        top.name_ar,
                        _sub(
                            scope,
                            e,
                            scope.narrowed_filter(engs=frozenset(scope.facts.descendants(top.id))),
                        ),
                        w,
                        hide,
                    )
                    for top in tops
                ]
                out.append(MedicalBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw, hide))
                out.append(MedicalBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.gap_reason and _tier2(scope):
            by = Counter(r.reason.value if r.reason else "MEDICAL_MISSING" for r in stats.gaps)
            rows = []
            for k, n in sorted(by.items()):
                sup = hide and 0 < n < 5
                rows.append(
                    MedicalBreakdownRow(
                        key=k,
                        label_en=k,
                        label_ar=k,
                        value=None if sup else str(n),
                        display=SMALL if sup else fmt.number(Decimal(n), 0),
                        numerator=None if sup else str(n),
                        suppressed=sup,
                    )
                )
            out.append(MedicalBreakdown(metric=M.K91.value, group_by=g, rows=rows))
    return out


def medical_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[MedicalKpiGroupBy] | None,
    codes: list[str],
    categories: list[FitnessCategory],
) -> MedicalKpiResponse:
    wanted = [m for m in (metrics or MEDICAL_METRICS) if m in MEDICAL_METRICS] or MEDICAL_METRICS
    e = med_engine(scope, codes, categories)
    values = [service.kpi_value(scope, m, engine=e) for m in wanted]
    if not small_ok(scope):
        values = [_suppress_value(v) for v in values]
    return MedicalKpiResponse(
        context=service.context(scope),
        metrics=values,
        breakdowns=_breakdowns(scope, e, wanted, group_by or []),
    )
