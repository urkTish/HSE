"""Environmental KPI page (GET /kpi/environmental, spec 6e-environmental §6.7, §8.1, EK-1, EK-2).

Engine values only; aggregates only (EK-2): stream, class, route, provider (organisation), point,
parameter, cause, substance, engagement codes and months are the only keys."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.env_enums import EnvKpiGroupBy
from app.core.hse_enums import KpiMetric
from app.kpi import env as ke
from app.kpi import fmt, present, service
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import EnvPoint, EnvProvider
from app.schemas.env import EnvBreakdown, EnvBreakdownRow, EnvKpiResponse

M = KpiMetric
G = EnvKpiGroupBy
D = Decimal
ENV_METRICS = [M.K118, M.K119, M.K120, M.K121, M.K122, M.K123, M.K124, M.K125, M.K126]


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> EnvBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return EnvBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=present.value_str(defn, r.value),
        display=present.display(defn, r.value), numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )  # fmt: skip


def _num(key: str, en: str, ar: str, v: Decimal, unit: str = "") -> EnvBreakdownRow:
    q = v.quantize(D("0.1"), rounding=ROUND_HALF_UP)
    return EnvBreakdownRow(key=key, label_en=en, label_ar=ar, value=str(q),
                           display=f"{q} {unit}".strip())  # fmt: skip


def _breakdowns(
    db: Session, scope: Scope, metrics: list[KpiMetric], group_by: list[EnvKpiGroupBy]
) -> list[EnvBreakdown]:
    from app.services.env import reference as rf  # noqa: PLC0415

    w = scope.window
    e = scope.engine
    out: list[EnvBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(EnvBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            engs = sorted(scope.facts.engagements.values(), key=lambda x: x.code)
            engs = [x for x in engs if scope.flt.eng_ok(x.id)]
            for m in metrics:
                if m in (M.K118, M.K122, M.K126):
                    continue
                rows = [
                    _row(m, x.code, x.code, x.code,
                         scope.sub_engine(scope.narrowed_filter(engs=frozenset({x.id}))), w)
                    for x in engs
                ]  # fmt: skip
                out.append(EnvBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g in (G.stream, G.waste_class, G.route, G.transporter, G.facility):
            acc: dict[str, Decimal] = defaultdict(D)
            for c in ke.dispatched(e, w):
                if c.t is None:
                    continue
                if g == G.stream:
                    k = c.stream
                elif g == G.waste_class:
                    k = c.wclass
                elif g == G.route:
                    k = c.route
                else:
                    pv = db.get(EnvProvider, c.transporter if g == G.transporter else c.facility)
                    k = pv.provider_code if pv else "?"
                acc[k] += c.t
            labels: dict[str, tuple[str, str]] = {}
            if g == G.stream:
                labels = {k: (v[0], v[1]) for k, v in rf.WS.items()}
            elif g == G.waste_class:
                labels = {k.value: v for k, v in rf.WC_LABELS.items()}
            elif g == G.route:
                labels = {k.value: v for k, v in rf.TR_LABELS.items()}
            rows = [
                _num(k, labels.get(k, (k, k))[0], labels.get(k, (k, k))[1], v, "t")
                for k, v in sorted(acc.items(), key=lambda x: (-x[1], x[0]))
            ]
            out.append(EnvBreakdown(metric=M.K119.value, group_by=g, rows=rows))
        elif g in (G.parameter, G.cause, G.point):
            from app.services.env.exceedances import project_caused  # noqa: PLC0415

            cnt: dict[str, int] = defaultdict(int)
            for x in ke.exceedances(e, w):
                if g == G.parameter:
                    if not project_caused(x):
                        continue
                    k = x.parameter.value
                elif g == G.cause:
                    c = x.cause or x.suggested_cause
                    k = c.value if c else "unreviewed"
                else:
                    if not project_caused(x):
                        continue
                    pt = db.get(EnvPoint, x.point_id)
                    k = pt.point_code if pt else "?"
                cnt[k] += 1
            rows = [
                EnvBreakdownRow(key=k, label_en=k, label_ar=k, value=str(v), display=str(v))
                for k, v in sorted(cnt.items())
            ]
            out.append(EnvBreakdown(metric=M.K123.value, group_by=g, rows=rows))
        elif g == G.substance:
            cnt2: dict[str, int] = defaultdict(int)
            for s in ke.spills(e, w):
                cnt2[s.substance.value] += 1
            rows = [
                EnvBreakdownRow(key=k, label_en=rf.SS_LABELS_BY_CODE.get(k, (k, k))[0],
                                label_ar=rf.SS_LABELS_BY_CODE.get(k, (k, k))[1], value=str(v),
                                display=str(v))
                for k, v in sorted(cnt2.items())
            ]  # fmt: skip
            out.append(EnvBreakdown(metric=M.K124.value, group_by=g, rows=rows))
    return out


def notes(db: Session, scope: Scope) -> list[str]:
    from app.services.env import common as ec  # noqa: PLC0415

    out: list[str] = []
    if scope.flt.engs is not None:
        out.append("K-118 is project level only (— with a contractor filter).")
    targets = sorted({str(ec.q1(ec.cfg(db, p.id).dec("diversion_target_pct")))
                      for p in scope.projects})  # fmt: skip
    if targets:
        out.append("K-120 target: " + " / ".join(f"{t} %" for t in targets))
    return out


def env_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[EnvKpiGroupBy] | None,
) -> EnvKpiResponse:
    wanted = [m for m in (metrics or ENV_METRICS) if m in ENV_METRICS] or ENV_METRICS
    return EnvKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(db, scope, wanted, group_by or []),
        notes=notes(db, scope),
    )
