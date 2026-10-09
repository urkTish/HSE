"""Emergency KPI page (GET /kpi/emergency, 6c-emergency-drills §6.8, EM-1…EM-3).

Engine values only; aggregates only (EM-2): site codes, months, drill / asset / event types are
the only keys."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.emergency_enums import EmergencyKpiGroupBy
from app.core.hse_enums import KpiMetric
from app.kpi import emergency as ke
from app.kpi import fmt, present, service
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import Site
from app.schemas.emergency import EmergencyBreakdown, EmergencyBreakdownRow, EmergencyKpiResponse
from app.services.emergency import reference as ref

M = KpiMetric
G = EmergencyKpiGroupBy
EM_METRICS = [M.K104, M.K105, M.K106, M.K107, M.K108, M.K109]


def _row(
    metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window
) -> EmergencyBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return EmergencyBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _pct_row(key: str, en: str, ar: str, num: int, den: int) -> EmergencyBreakdownRow:
    v = (Decimal(num) * 100 / Decimal(den)) if den else None
    return EmergencyBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=fmt.exact(v.quantize(Decimal("0.1"))) if v is not None else None,
        display=f"{v.quantize(Decimal('0.1'))} %" if v is not None else "—",
        numerator=str(num),
        denominator=str(den),
    )


def _breakdowns(
    db: Session, scope: Scope, metrics: list[KpiMetric], group_by: list[EmergencyKpiGroupBy]
) -> list[EmergencyBreakdown]:
    w = scope.window
    e = scope.engine
    out: list[EmergencyBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.site:
            sites = list(
                db.scalars(
                    select(Site).where(Site.project_id.in_([p.id for p in scope.projects]))
                    .order_by(Site.code)
                )
            )  # fmt: skip
            sites = [s for s in sites if scope.flt.site_ok(s.id)]
            for m in metrics:
                rows = [
                    _row(m, s.code, s.code, s.code,
                         scope.sub_engine(scope.narrowed_filter(sites=frozenset({s.id}))), w)
                    for s in sites
                ]  # fmt: skip
                out.append(EmergencyBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(EmergencyBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.drill_type and M.K104 in metrics:
            acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for it in ke.programme_items(e, w):
                acc[it.drill_type][1] += 1
                acc[it.drill_type][0] += it.met
            rows = [
                _pct_row(k.value, v[0], v[1], *acc[k.value])
                for k, v in ref.DRILL_TYPES.items()
                if k.value in acc
            ]
            out.append(EmergencyBreakdown(metric=M.K104.value, group_by=g, rows=rows))
        elif g == G.asset_type and M.K107 in metrics:
            s = ke.asset_stats(e, w)
            rows = [
                _pct_row(k.value, v[0], v[1], *s.by_type[k.value])
                for k, v in ref.ASSET_TYPES.items()
                if k.value in s.by_type
            ]
            out.append(EmergencyBreakdown(metric=M.K107.value, group_by=g, rows=rows))
        elif g == G.event_type and M.K109 in metrics:
            ev = ke.event_stats(e, w)
            rows = [
                EmergencyBreakdownRow(
                    key=k.value,
                    label_en=v[0],
                    label_ar=v[1],
                    value=str(ev.by_type[k.value]),
                    display=str(ev.by_type[k.value]),
                )
                for k, v in ref.EVENT_TYPES.items()
                if k.value in ev.by_type
            ]
            out.append(EmergencyBreakdown(metric=M.K109.value, group_by=g, rows=rows))
    return out


def emergency_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[EmergencyKpiGroupBy] | None,
) -> EmergencyKpiResponse:
    wanted = [m for m in (metrics or EM_METRICS) if m in EM_METRICS] or EM_METRICS
    return EmergencyKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(db, scope, wanted, group_by or []),
    )
