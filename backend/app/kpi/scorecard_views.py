"""Scorecard KPI page (GET /kpi/scorecards, spec 6g §6.7, §8.1, GK-1): K-132…K-135 with month
and contractor breakdowns, the grade mix and the watch list by level."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.hse_enums import KpiMetric
from app.core.scorecard_enums import ScKpiGroupBy
from app.kpi import fmt, present, service
from app.kpi import scorecard as ks
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.schemas.scorecard import ScBreakdown, ScBreakdownRow, ScKpiResponse

M = KpiMetric
G = ScKpiGroupBy
SC_METRICS = [M.K132, M.K133, M.K134, M.K135]


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> ScBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return ScBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=present.value_str(defn, r.value),
        display=present.display(defn, r.value), numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )  # fmt: skip


def _breakdowns(scope: Scope, metrics: list[KpiMetric], group_by: list[G]) -> list[ScBreakdown]:
    w = scope.window
    out: list[ScBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, scope.engine, mw))
                out.append(ScBreakdown(metric=m.value, group_by=g, rows=rows))
        else:
            engs = sorted(scope.facts.engagements.values(), key=lambda x: x.code)
            engs = [x for x in engs if scope.flt.eng_ok(x.id)]
            for m in [x for x in metrics if x in (M.K132, M.K133)]:
                rows = [_row(m, x.code, x.code, x.code,
                             scope.sub_engine(scope.narrowed_filter(engs=frozenset({x.id}))), w)
                        for x in engs]  # fmt: skip
                out.append(ScBreakdown(metric=m.value, group_by=g, rows=rows))
    return out


def sc_kpis(
    db: Session, scope: Scope, metrics: list[KpiMetric] | None, group_by: list[G] | None
) -> ScKpiResponse:
    wanted = [m for m in (metrics or SC_METRICS) if m in SC_METRICS] or SC_METRICS
    e = scope.engine
    w = scope.window
    cs = [c for c in ks.cards(e, w.start, min(e.as_of, w.end)) if c.grade is not None]
    mix: dict[str, int] = {}
    for c in cs:
        k = c.grade.value if c.grade else "—"
        mix[k] = mix.get(k, 0) + 1
    levels: dict[str, int] = {}
    for x in ks.entries(e, min(e.as_of, w.end)):
        levels[x.level.value] = levels.get(x.level.value, 0) + 1
    return ScKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(scope, wanted, group_by or []),
        grade_mix=dict(sorted(mix.items())), watch_by_level=levels,
        notes=["Cards → their month (Final revision, else Issued); disputes → due_at date; "
               "packs → due_on (GK-1)."],
    )  # fmt: skip
