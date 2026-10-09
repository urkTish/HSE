"""Heat-stress KPI page (GET /kpi/heat-stress, 6b §6.6, HM-1…HM-3).

Engine values only; aggregates only (HM-2): zone codes, site codes, contractor short codes and
months are the only keys. Heat-illness counts (K-103 and its recordable component) of 1–2 are
shown as "<3" except to the HSE Manager (HM-3)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.heat_enums import HeatKpiGroupBy
from app.core.hse_enums import KpiMetric
from app.kpi import fmt, present, service
from app.kpi import heat as kh
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.facts import Filter
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.schemas.heat import HeatBreakdown, HeatBreakdownRow, HeatKpiResponse
from app.schemas.kpi import KpiValue

M = KpiMetric
G = HeatKpiGroupBy
HEAT_METRICS = [M.K97, M.K98, M.K99, M.K100, M.K101, M.K102, M.K103]
ZONE_METRICS = [M.K97, M.K98, M.K99, M.K100, M.K103]
SMALL = "<3"


def _small(v: str | None) -> bool:
    if v is None:
        return False
    try:
        return 0 < Decimal(v) < 3
    except ArithmeticError:
        return False


def _suppress(v: KpiValue) -> KpiValue:
    if v.metric != M.K103:
        return v
    if _small(v.value):
        v.value, v.display, v.numerator = None, SMALL, None
        v.comparisons = []
    for c in v.components:
        if c.key == "recordable" and _small(c.value):
            c.value, c.display = None, SMALL
    return v


def _row(
    metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window, hide: bool
) -> HeatBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    value = present.value_str(defn, r.value)
    if hide and metric == M.K103 and _small(value):
        return HeatBreakdownRow(key=key, label_en=en, label_ar=ar, value=None, display=SMALL)
    return HeatBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=value,
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _with_zone(f: Filter, zone: uuid.UUID) -> Filter:
    z = frozenset({zone})
    return Filter(
        sites=f.sites,
        zones=z if f.zones is None else (f.zones & z),
        zone_type=f.zone_type,
        engs=f.engs,
    )


def _breakdowns(
    scope: Scope, metrics: list[KpiMetric], group_by: list[HeatKpiGroupBy]
) -> list[HeatBreakdown]:
    w = scope.window
    hide = not scope.p.is_manager
    out: list[HeatBreakdown] = []
    hf = kh.hfacts(scope.engine)
    projs = hf.all() if hf is not None else []
    zones = scope.facts.zones
    for g in dict.fromkeys(group_by):
        if g == G.zone:
            ids = sorted(
                {z for p in projs for z in kh.req_zones(scope.engine, p)},
                key=lambda z: zones[z].code if z in zones else str(z),
            )
            for m in (x for x in metrics if x in ZONE_METRICS):
                rows = []
                for z in ids:
                    code = zones[z].code if z in zones else str(z)
                    e = scope.sub_engine(_with_zone(scope.flt, z))
                    rows.append(_row(m, code, code, code, e, w, hide))
                out.append(HeatBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.site:
            sites = sorted(
                {s for p in projs for s in {p.zone_site.get(z) for z in p.required} if s}
            )
            codes = _site_codes(scope, sites)
            for m in metrics:
                rows = [
                    _row(m, codes[s], codes[s], codes[s],
                         scope.sub_engine(scope.narrowed_filter(sites=frozenset({s}))), w, hide)
                    for s in sorted(sites, key=lambda s: codes[s])
                ]  # fmt: skip
                out.append(HeatBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            tops = sorted(
                (
                    x
                    for x in scope.facts.engagements.values()
                    if x.tier == 1 and (scope.flt.engs is None or x.id in scope.flt.engs)
                ),
                key=lambda x: x.code,
            )
            for m in (x for x in metrics if x in (M.K99, M.K100, M.K101, M.K102, M.K103)):
                rows = [
                    _row(m, top.code, top.name_en, top.name_ar,
                         scope.sub_engine(scope.narrowed_filter(
                             engs=frozenset(scope.facts.descendants(top.id)))), w, hide)
                    for top in tops
                ]  # fmt: skip
                out.append(HeatBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, scope.engine, mw, hide))
                out.append(HeatBreakdown(metric=m.value, group_by=g, rows=rows))
    return out


def _site_codes(scope: Scope, sites: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    from sqlalchemy import select  # noqa: PLC0415

    from app.models import Site  # noqa: PLC0415

    hf = kh.hfacts(scope.engine)
    if hf is None or not sites:
        return {}
    return dict(hf.db.execute(select(Site.id, Site.code).where(Site.id.in_(sites))).all())


def heat_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[HeatKpiGroupBy] | None,
) -> HeatKpiResponse:
    wanted = [m for m in (metrics or HEAT_METRICS) if m in HEAT_METRICS] or HEAT_METRICS
    values = [service.kpi_value(scope, m) for m in wanted]
    if not scope.p.is_manager:
        values = [_suppress(v) for v in values]
    return HeatKpiResponse(
        context=service.context(scope),
        metrics=values,
        breakdowns=_breakdowns(scope, wanted, group_by or []),
    )
