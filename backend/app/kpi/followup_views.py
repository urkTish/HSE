"""Incident follow-up KPI page (GET /kpi/incident-followup, spec 6f §6.2, §8.1, FK-1, FK-2).

Aggregates only (FK-2): bodies, stages, months and engagement codes are the only keys."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.followup_enums import FuKpiGroupBy
from app.core.hse_enums import KpiMetric
from app.kpi import fmt, present, service
from app.kpi import followup as kf
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.schemas.followup import FuBreakdown, FuBreakdownRow, FuKpiResponse

M = KpiMetric
G = FuKpiGroupBy
D = Decimal
FU_METRICS = [M.K127, M.K128, M.K129, M.K130, M.K131]


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> FuBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return FuBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=present.value_str(defn, r.value),
        display=present.display(defn, r.value), numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )  # fmt: skip


def _pct_row(key: str, en: str, ar: str, n: int, d: int) -> FuBreakdownRow:
    if not d:
        return FuBreakdownRow(key=key, label_en=en, label_ar=ar, value=None, display="—",
                              numerator=str(n), denominator=str(d))  # fmt: skip
    v = (D(n) * 100 / D(d)).quantize(D("0.1"), rounding=ROUND_HALF_UP)
    return FuBreakdownRow(key=key, label_en=en, label_ar=ar, value=str(v), display=f"{v} %",
                          numerator=str(n), denominator=str(d))  # fmt: skip


def _by_attr(
    e: Engine, w: Window, attr: str, labels: dict[str, tuple[str, str]]
) -> list[FuBreakdown]:
    num, den = kf.timeliness(e, w)
    n: dict[str, int] = defaultdict(int)
    d: dict[str, int] = defaultdict(int)
    for r in den:
        d[getattr(r, attr)] += 1
    for r in num:
        n[getattr(r, attr)] += 1
    od: dict[str, int] = defaultdict(int)
    for r in kf.overdue_at(e, w):
        od[getattr(r, attr)] += 1
    g = G.body if attr == "body" else G.stage

    def lab(k: str) -> tuple[str, str]:
        return labels.get(k, (k, k))

    return [
        FuBreakdown(metric=M.K127.value, group_by=g,
                    rows=[_pct_row(k, *lab(k), n[k], d[k]) for k in sorted(d)]),
        FuBreakdown(metric=M.K128.value, group_by=g,
                    rows=[FuBreakdownRow(key=k, label_en=lab(k)[0], label_ar=lab(k)[1],
                                         value=str(v), display=str(v))
                          for k, v in sorted(od.items())]),
    ]  # fmt: skip


def _breakdowns(
    db: Session, scope: Scope, metrics: list[KpiMetric], group_by: list[FuKpiGroupBy]
) -> list[FuBreakdown]:
    from app.services.followup.config import LABELS  # noqa: PLC0415

    w = scope.window
    e = scope.engine
    out: list[FuBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(FuBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            engs = sorted(scope.facts.engagements.values(), key=lambda x: x.code)
            engs = [x for x in engs if scope.flt.eng_ok(x.id)]
            for m in metrics:
                rows = [
                    _row(m, x.code, x.code, x.code,
                         scope.sub_engine(scope.narrowed_filter(engs=frozenset({x.id}))), w)
                    for x in engs
                ]  # fmt: skip
                out.append(FuBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.body:
            out += _by_attr(e, w, "body", dict(LABELS.get("bodies", {})))
        elif g == G.stage:
            out += _by_attr(e, w, "stage", dict(LABELS.get("stages", {})))
    return out


def fu_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[FuKpiGroupBy] | None,
) -> FuKpiResponse:
    wanted = [m for m in (metrics or FU_METRICS) if m in FU_METRICS] or FU_METRICS
    return FuKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(db, scope, wanted, group_by or []),
        notes=["K-127 excludes waived and not-required items and items not yet due (FK-1)."],
    )
