"""Site vehicle KPI page (GET /kpi/site-vehicles, spec 7b-fleet-driver §6.4, §8; prototype):
K-138…K-140 with month and contractor breakdowns. Aggregates only (SK-2): engagement codes and
counts, never plates or names."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.hse_enums import KpiMetric
from app.core.site_vehicle_enums import SiteVehKpiGroupBy
from app.kpi import fmt, present, service
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.schemas.site_vehicle import SiteVehBreakdown, SiteVehBreakdownRow, SiteVehKpiResponse

M = KpiMetric
G = SiteVehKpiGroupBy
SV_METRICS = [M.K138, M.K139, M.K140]


def _row(
    metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window
) -> SiteVehBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return SiteVehBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=present.value_str(defn, r.value),
        display=present.display(defn, r.value), numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )  # fmt: skip


def _breakdowns(
    scope: Scope, metrics: list[KpiMetric], group_by: list[G]
) -> list[SiteVehBreakdown]:
    w = scope.window
    out: list[SiteVehBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, scope.engine, mw))
                out.append(SiteVehBreakdown(metric=m.value, group_by=g, rows=rows))
        else:
            engs = sorted(scope.facts.engagements.values(), key=lambda x: x.code)
            engs = [x for x in engs if scope.flt.eng_ok(x.id)]
            for m in metrics:
                rows = [_row(m, x.code, x.code, x.code,
                             scope.sub_engine(scope.narrowed_filter(engs=frozenset({x.id}))), w)
                        for x in engs]  # fmt: skip
                out.append(SiteVehBreakdown(metric=m.value, group_by=g, rows=rows))
    return out


def sv_kpis(
    db: Session, scope: Scope, metrics: list[KpiMetric] | None, group_by: list[G] | None
) -> SiteVehKpiResponse:
    wanted = [m for m in (metrics or SV_METRICS) if m in SV_METRICS] or SV_METRICS
    return SiteVehKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(scope, wanted, group_by or []),
        notes=["Prototype (نموذج أولي). K-138 at min(as_of, period end); K-139 checks and journey "
               "plans by date; K-140 required vehicle-days (§6.2). Only projects with "
               "site_vehicles_from set count."],
    )  # fmt: skip
