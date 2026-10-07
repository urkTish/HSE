"""Access KPI page, dashboard access band and charts C10-C12 (2-access-permits §6.8, §8.1).

Everything is an engine value (KA-1); responses carry aggregates only (KA-4)."""

import uuid
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import AccessKpiGroupBy, ValidityStatus, WapStatus
from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AxisKind, ChartId, ChartKind, KpiMetric, SeriesKind
from app.kpi import access as ak
from app.kpi import charts as ch
from app.kpi import fmt, present, service
from app.kpi.access_facts import GateAgg
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import Adp, AirportPass, Avp, Gate, OpsEvent, Project, Wap, Zone
from app.schemas.access_kpi import AccessBreakdown, AccessBreakdownRow, AccessKpiResponse
from app.schemas.kpi import (
    AccessBand,
    ChartAxis,
    ChartCategory,
    ChartSpec,
    ChartXAxis,
    KpiValue,
)
from app.services.hse_common import Refs

M = KpiMetric
ACCESS_METRICS = [
    M.K38,
    M.K48,
    M.K49,
    M.K50,
    M.K51,
    M.K52,
    M.K53,
    M.K53b,
    M.K54,
    M.K55,
    M.K56,
    M.K57,
    M.K58,
    M.K59,
    M.K60,
]
ACCESS_TILES = [M.K49, M.K53, M.K54, M.K59, M.K57]
GATE_METRICS = (M.K52, M.K53, M.K53b)
LOCAL = timedelta(hours=3)


def has_access(scope: Scope) -> bool:
    """Access KPIs show for airport projects the caller may see with capability 77."""
    return any(
        x.is_airport and scope.p.grant(x.id, Capability.access_kpi_view) is not None
        for x in scope.projects
    )


def gate_engine(db: Session, scope: Scope, gate_id: uuid.UUID | None) -> Engine:
    if gate_id is None:
        return scope.engine
    g = db.get(Gate, gate_id)
    if g is None or g.project_id not in {x.id for x in scope.projects}:
        raise not_found("Gate")
    e = scope.sub_engine(scope.flt)
    e.gate_id = gate_id  # type: ignore[attr-defined]
    return e


# ---- /kpi/access ---------------------------------------------------------------------------------


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> AccessBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return AccessBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _count_row(key: str, en: str, ar: str, n: int) -> AccessBreakdownRow:
    return AccessBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=str(n), display=fmt.number(Decimal(n))
    )


def _components(metric: KpiMetric, e: Engine, w: Window) -> list[AccessBreakdownRow]:
    r = e.result(metric, e.aggregate(w))
    return [_count_row(c.key, c.label_en, c.label_ar, int(c.value or 0)) for c in r.components]


def _gate_rate_rows(
    metric: KpiMetric, groups: dict[str, list[GateAgg]], labels: dict[str, tuple[str, str]]
) -> list[AccessBreakdownRow]:
    defn = CATALOGUE[metric]
    out = []
    for key, rows in sorted(groups.items(), key=lambda kv: labels.get(kv[0], (kv[0],))[0]):
        total = sum(r.n for r in rows)
        denied = sum(r.n for r in rows if r.denied)
        if metric == M.K53:
            v = Decimal(denied) / Decimal(total) * 100 if total else None
            num, den = denied, total
        else:
            v, num, den = Decimal(total), total, None
        en, ar = labels.get(key, (key, key))
        out.append(
            AccessBreakdownRow(
                key=key,
                label_en=en,
                label_ar=ar,
                value=present.value_str(defn, v),
                display=present.display(defn, v),
                numerator=str(num),
                denominator=None if den is None else str(den),
            )
        )
    return out


def _breakdowns(
    db: Session,
    scope: Scope,
    e: Engine,
    metrics: list[KpiMetric],
    group_by: list[AccessKpiGroupBy],
) -> list[AccessBreakdown]:
    w = scope.window
    out: list[AccessBreakdown] = []
    G = AccessKpiGroupBy  # noqa: N806
    for g in dict.fromkeys(group_by):
        if g == G.kind and M.K51 in metrics:
            out.append(
                AccessBreakdown(metric=M.K51.value, group_by=g, rows=_components(M.K51, e, w))
            )
        elif g == G.reason_code and M.K53 in metrics:
            out.append(
                AccessBreakdown(metric=M.K53.value, group_by=g, rows=_components(M.K53, e, w))
            )
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
                rows = []
                for top in tops:
                    sub = scope.sub_engine(
                        scope.narrowed_filter(engs=frozenset(scope.facts.descendants(top.id)))
                    )
                    gid = getattr(e, "gate_id", None)
                    if gid is not None:
                        sub.gate_id = gid  # type: ignore[attr-defined]
                    rows.append(_row(m, top.code, top.name_en, top.name_ar, sub, w))
                out.append(AccessBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(AccessBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g in (G.zone, G.gate):
            rows_all = ak.gate_rows(e, e.aggregate(w), getattr(e, "gate_id", None))
            groups: dict[str, list[GateAgg]] = {}
            labels: dict[str, tuple[str, str]] = {}
            if g == G.zone:
                zone_ids = {r.zone for r in rows_all if r.zone is not None}
                for z in db.scalars(select(Zone).where(Zone.id.in_(zone_ids))) if zone_ids else []:
                    labels[str(z.id)] = (f"{z.code} {z.name_en}", f"{z.code} {z.name_ar}")
                for r in rows_all:
                    groups.setdefault(str(r.zone) if r.zone else "none", []).append(r)
                labels.setdefault("none", ("No zone", "بدون منطقة"))
            else:
                gate_ids = {r.gate for r in rows_all}
                for gt in db.scalars(select(Gate).where(Gate.id.in_(gate_ids))) if gate_ids else []:
                    labels[str(gt.id)] = (
                        f"{gt.gate_code} {gt.name_en}",
                        f"{gt.gate_code} {gt.name_ar}",
                    )
                for r in rows_all:
                    groups.setdefault(str(r.gate), []).append(r)
            for m in metrics:
                if m in (M.K52, M.K53):
                    out.append(
                        AccessBreakdown(
                            metric=m.value, group_by=g, rows=_gate_rate_rows(m, groups, labels)
                        )
                    )
    return out


GATE_NOTE = (
    "Gate KPIs count in-direction checks only; a check counts once under its first DENY reason "
    "(KA-3, K-53)."
)


def access_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[AccessKpiGroupBy] | None,
    gate_id: uuid.UUID | None,
) -> AccessKpiResponse:
    wanted = [m for m in (metrics or ACCESS_METRICS) if m in ACCESS_METRICS] or ACCESS_METRICS
    e = gate_engine(db, scope, gate_id)
    values: list[KpiValue] = [service.kpi_value(scope, m, engine=e) for m in wanted]
    return AccessKpiResponse(
        context=service.context(scope),
        band=access_band(db, scope),
        metrics=values,
        breakdowns=_breakdowns(db, scope, e, wanted, group_by or []),
    )


# ---- dashboard band ------------------------------------------------------------------------------


def _project(scope: Scope) -> Project | None:
    p = scope.single_project
    if p is None or not p.is_airport:
        return None
    if scope.p.grant(p.id, Capability.access_kpi_view) is None:
        return None
    return p


def access_band(db: Session, scope: Scope) -> AccessBand | None:
    proj = _project(scope)
    if proj is None:
        return None
    flt = scope.flt
    day = scope.as_of
    at = min(datetime.combine(day, time(23, 59, 59), tzinfo=UTC) - LOCAL, now())

    def count(model: type[AirportPass] | type[Adp] | type[Avp]) -> int:
        q = (
            select(func.count())
            .select_from(model)
            .where(
                model.project_id == proj.id,
                model.validity_status == ValidityStatus.active,
                or_(model.effective_valid_until.is_(None), model.effective_valid_until >= day),
            )
        )
        if flt.engs is not None:
            q = q.where(model.engagement_id.in_(flt.engs))
        return int(db.scalar(q) or 0)

    wq = select(Wap).where(
        Wap.project_id == proj.id, Wap.status == WapStatus.active, Wap.revision_of_id.is_(None)
    )
    if flt.engs is not None:
        wq = wq.where(Wap.engagement_id.in_(flt.engs))
    if flt.sites is not None:
        wq = wq.where(Wap.site_id.in_(flt.sites))
    waps_now = [
        w
        for w in db.scalars(wq)
        if not flt.zone_filtered or any(flt.zone_ok(z, scope.facts.zones) for z in w.zone_ids)
    ]
    oq = select(OpsEvent).where(
        OpsEvent.project_id == proj.id,
        OpsEvent.started_at <= at,
        or_(OpsEvent.ended_at.is_(None), OpsEvent.ended_at > at),
    )
    if flt.sites is not None:
        oq = oq.where(OpsEvent.site_id.in_(flt.sites))
    ops = list(db.scalars(oq))
    zone_ids = list(dict.fromkeys(z for o in ops for z in o.zone_ids))
    refs = Refs(db)
    zones = [z for z in (refs.zone(x) for x in zone_ids) if z is not None]
    e = scope.engine
    k60 = e.result(M.K60, e.aggregate(scope.window))
    return AccessBand(
        project_id=proj.id,
        as_of=day,
        active_deployed_workers=service.kpi_value(scope, M.K48, with_comparisons=False),
        active_passes=count(AirportPass),
        active_adps=count(Adp),
        active_avps=count(Avp),
        active_waps_now=len(waps_now),
        active_obstacle_clearances=int(k60.value or 0),
        ops_suspension_in_force=bool(ops),
        ops_suspension_zones=sorted(zones, key=lambda z: z.code),
    )


# ---- charts C10-C12 ------------------------------------------------------------------------------


def _axis(id_: str, en: str, ar: str, unit: str | None = None) -> ChartAxis:
    return ChartAxis(id=id_, label_en=en, label_ar=ar, unit_en=unit, unit_ar=unit)


def c10(scope: Scope, e: Engine) -> ChartSpec:

    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    checks = [e.result(M.K52, e.aggregate(w)).value for w in wins]
    rates = [e.result(M.K53, e.aggregate(w)).value for w in wins]
    return ch._spec(
        scope,
        ChartId.C10,
        ChartKind.combo,
        ("Gate checks by month", "عمليات التحقق عند البوابات حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[
            _axis("left", "Gate checks", "عمليات التحقق"),
            _axis("right", "Denial rate", "نسبة الرفض", "%"),
        ],
        series=[
            ch._series(
                "checks",
                "Gate checks",
                "عمليات التحقق",
                SeriesKind.bar,
                "left",
                "series-1",
                [ch._pt(k, v, 0) for k, v in zip(keys, checks, strict=True)],
            ),
            ch._series(
                "denial_rate",
                "Denial rate",
                "نسبة الرفض",
                SeriesKind.line,
                "right",
                "series-2",
                [ch._pt(k, v, 2, "percent") for k, v in zip(keys, rates, strict=True)],
            ),
        ],
        metric=M.K53,
    )


def c11(scope: Scope, e: Engine) -> ChartSpec:

    r = e.result(M.K53, e.aggregate(scope.window))
    top = r.components[:8]
    cats = [ChartCategory(key=c.key, label_en=c.label_en, label_ar=c.label_ar) for c in top]
    return ch._spec(
        scope,
        ChartId.C11,
        ChartKind.horizontal_bar,
        ("Gate denial reasons (top 8)", "أسباب الرفض عند البوابات (أعلى 8)"),
        x_axis=ChartXAxis(
            kind=AxisKind.category, label_en="Reason", label_ar="السبب", categories=cats
        ),
        y_axes=[_axis("left", "Denied checks", "عمليات مرفوضة")],
        series=[
            ch._series(
                "denied",
                "Denied checks",
                "عمليات مرفوضة",
                SeriesKind.bar,
                "left",
                "series-1",
                [ch._pt(c.key, c.value, 0) for c in top],
            ),
        ],
        metric=M.K53,
    )


def c12(scope: Scope, e: Engine) -> ChartSpec:

    start = scope.as_of
    weeks = [(start + timedelta(days=7 * i), start + timedelta(days=7 * i + 6)) for i in range(13)]
    last = start + timedelta(days=90)
    weeks[-1] = (weeks[-1][0], last)
    counts: dict[str, Counter[int]] = {k: Counter() for k, _, _ in ak.K51_KINDS}
    for x in ak._facts(e).creds:
        if not (start <= x.eff <= last) or not e.flt.eng_ok(x.eng):
            continue
        if x.sites and not ak._sites_ok(e, x.sites):
            continue
        counts.setdefault(x.kind, Counter())[min((x.eff - start).days // 7, 12)] += 1
    cats = []
    for a, _b in weeks:
        cats.append(
            ChartCategory(
                key=a.isoformat(), label_en=f"Week of {a:%d %b}", label_ar=f"أسبوع {a:%d/%m}"
            )
        )
    series = [
        ch._series(
            k,
            en,
            ar,
            SeriesKind.bar,
            "left",
            f"series-{n + 1}",
            [ch._pt(c.key, counts[k].get(i, 0), 0) for i, c in enumerate(cats)],
            stack="kinds",
        )
        for n, (k, en, ar) in enumerate(ak.K51_KINDS)
    ]
    return ch._spec(
        scope,
        ChartId.C12,
        ChartKind.stacked_bar,
        ("Credentials expiring in the next 90 days", "التصاريح التي تنتهي خلال 90 يوماً"),
        x_axis=ChartXAxis(
            kind=AxisKind.period, label_en="Week", label_ar="الأسبوع", categories=cats
        ),
        y_axes=[_axis("left", "Credentials", "التصاريح")],
        series=series,
        metric=M.K51,
    )


ACCESS_CHARTS = {ChartId.C10: c10, ChartId.C11: c11, ChartId.C12: c12}


def chart(db: Session, scope: Scope, chart_id: ChartId, gate_id: uuid.UUID | None) -> ChartSpec:
    return ACCESS_CHARTS[chart_id](scope, gate_engine(db, scope, gate_id))
