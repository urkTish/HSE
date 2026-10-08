"""PTW KPI page (GET /kpi/ptw), dashboard PTW band and tiles, charts C13-C15 (3-ptw §6.11,
§8.1, KP-1…KP-6). Engine values only; aggregates only (no names, KP-6)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.hse_enums import AxisKind, ChartId, ChartKind, KpiMetric, SeriesKind
from app.core.ptw_enums import (
    ROUTINE_REASONS,
    PermitStatus,
    PermitType,
    PtwAuditType,
    PtwKpiGroupBy,
)
from app.kpi import charts as ch
from app.kpi import fmt, present, service
from app.kpi import ptw as kp
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.facts import Filter
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import Project
from app.schemas.kpi import (
    ChartAxis,
    ChartCategory,
    ChartSpec,
    ChartXAxis,
    PtwBand,
    PtwBandTypeCount,
)
from app.schemas.ptw_kpi import PtwBreakdown, PtwBreakdownRow, PtwKpiResponse

M = KpiMetric
G = PtwKpiGroupBy
PTW_METRICS = [
    M.K46,
    M.K46b,
    M.K61,
    M.K62,
    M.K63,
    M.K64,
    M.K65,
    M.K66,
    M.K67,
    M.K68,
    M.K69,
    M.K70,
    M.K71,
]


def has_ptw(scope: Scope) -> bool:
    return any(scope.p.grant(x.id, Capability.ptw_kpi_view) is not None for x in scope.projects)


def ptw_engine(scope: Scope, e: Engine | None = None) -> Engine:
    e = e or scope.engine
    types = frozenset(t.value for t in getattr(scope.query, "permit_types", []) or [])
    e.permit_types = types or None  # type: ignore[attr-defined]
    return e


def _reason_label(code: str) -> tuple[str, str]:
    from app.core.ptw_enums import StatusReason  # noqa: PLC0415
    from app.services.ptw.reference import REASON_TEXT  # noqa: PLC0415

    try:
        return REASON_TEXT[StatusReason(code)]
    except (KeyError, ValueError):
        return code, code


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> PtwBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return PtwBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _count_row(key: str, en: str, ar: str, n: int) -> PtwBreakdownRow:
    return PtwBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=str(n), display=fmt.number(Decimal(n))
    )


def _sub(scope: Scope, flt: Filter) -> Engine:
    return ptw_engine(scope, scope.sub_engine(flt))


def _breakdowns(
    db: Session, scope: Scope, e: Engine, metrics: list[KpiMetric], group_by: list[PtwKpiGroupBy]
) -> list[PtwBreakdown]:
    w = scope.window
    a = e.aggregate(w)
    out: list[PtwBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.type:
            for m in metrics:
                rows = []
                for t in PermitType:
                    sub = scope.sub_engine(scope.flt)
                    sub.permit_types = frozenset({t.value})  # type: ignore[attr-defined]
                    rows.append(_row(m, t.value, *kp.TYPE_LABELS[t.value], sub, w))
                out.append(PtwBreakdown(metric=m.value, group_by=g, rows=rows))
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
                            scope.narrowed_filter(engs=frozenset(scope.facts.descendants(top.id))),
                        ),
                        w,
                    )
                    for top in tops
                ]
                out.append(PtwBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.zone:
            zone_ids = sorted(
                {z for p in kp.facts(e).permits.values() if kp.permit_ok(e, p) for z in p.zones},
                key=lambda z: scope.facts.zones[z].code if z in scope.facts.zones else str(z),
            )
            for m in metrics:
                rows = []
                for z in zone_ids:
                    zf = scope.facts.zones.get(z)
                    code = zf.code if zf else str(z)
                    rows.append(
                        _row(
                            m,
                            code,
                            code,
                            code,
                            _sub(
                                scope,
                                Filter(
                                    sites=scope.flt.sites,
                                    zones=frozenset({z}),
                                    zone_type=scope.flt.zone_type,
                                    engs=scope.flt.engs,
                                ),
                            ),
                            w,
                        )
                    )
                out.append(PtwBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(PtwBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.week:
            for m in metrics:
                rows = []
                start = w.start
                while start <= w.end:
                    end = min(start + timedelta(days=6), w.end)
                    ww = Window(start, end)
                    rows.append(
                        _row(
                            m,
                            start.isoformat(),
                            f"Week of {start:%d %b}",
                            f"أسبوع {start:%d/%m}",
                            e,
                            ww,
                        )
                    )
                    start = end + timedelta(days=1)
                out.append(PtwBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.suspension_reason:
            by = Counter(s.reason.value for _p, s in kp.suspensions(e, a))
            rows = [
                _count_row(k, *_reason_label(k), v)
                for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            out.append(PtwBreakdown(metric=M.K65.value, group_by=g, rows=rows))
        elif g == G.audit_item:
            from app.services.ptw.reference import AUDIT_ITEMS  # noqa: PLC0415

            nc: Counter[str] = Counter()
            for x in kp.field_audits(e, a):
                for code, answer, _sev in x.items:
                    if answer == "non_compliant":
                        nc[code] += 1
            rows = [
                _count_row(k, AUDIT_ITEMS[k][0], AUDIT_ITEMS[k][1], v)
                for k, v in sorted(nc.items(), key=lambda kv: (-kv[1], kv[0]))
                if k in AUDIT_ITEMS
            ]
            out.append(PtwBreakdown(metric=M.K61.value, group_by=g, rows=rows))
        elif g == G.simops_rule:
            pf = kp.facts(e)
            by = Counter(
                c.rule
                for c in pf.conflicts
                if kp._in(e, a, c.d) and kp._conflict_ok(e, pf, c.permits)
            )
            rows = [_count_row(k, k, k, v) for k, v in sorted(by.items())]
            out.append(PtwBreakdown(metric=M.K68.value, group_by=g, rows=rows))
    return out


def ptw_kpis(
    db: Session, scope: Scope, metrics: list[KpiMetric] | None, group_by: list[PtwKpiGroupBy] | None
) -> PtwKpiResponse:
    wanted = [m for m in (metrics or PTW_METRICS) if m in PTW_METRICS] or PTW_METRICS
    e = ptw_engine(scope)
    return PtwKpiResponse(
        context=service.context(scope),
        band=ptw_band(db, scope),
        metrics=[service.kpi_value(scope, m, engine=e) for m in wanted],
        breakdowns=_breakdowns(db, scope, e, wanted, group_by or []),
    )


# ---- dashboard band (§8.1 item 2) ----------------------------------------------------------------


def _project(scope: Scope) -> Project | None:
    p = scope.single_project
    if p is None or scope.p.grant(p.id, Capability.ptw_kpi_view) is None:
        return None
    return p


def ptw_band(db: Session, scope: Scope) -> PtwBand | None:
    proj = _project(scope)
    if proj is None:
        return None
    e = ptw_engine(scope)
    pf = kp.facts(e)
    live = [p for p in pf.permits.values() if p.project == proj.id and kp.permit_ok(e, p)]
    active = [p for p in live if p.status == PermitStatus.active]
    by = Counter(p.primary for p in active)
    susp = [
        p
        for p in live
        if p.status == PermitStatus.suspended and p.status_reason not in ROUTINE_REASONS
    ]
    k67 = service.kpi_value(scope, M.K67, engine=e, with_comparisons=False)
    r67 = e.result(M.K67, e.aggregate(scope.window))
    lt = next((int(c.value or 0) for c in r67.components if c.key == "long_term"), 0)
    day = scope.as_of
    open_conf = sum(
        1
        for c in pf.conflicts
        if c.project == proj.id
        and c.d <= day
        and (c.open_until is None or c.open_until > day)
        and kp._conflict_ok(e, pf, c.permits)
    )
    from app.kpi.periods import week_start  # noqa: PLC0415

    ws = week_start(day, proj.settings.week_start) if proj.settings else day
    done = sum(
        1
        for x in pf.audits
        if x.project == proj.id
        and x.counted
        and x.audit_type == PtwAuditType.field
        and ws <= x.d <= day
        and kp.audit_ok(e, x)
    )
    st = pf.settings.get(proj.id)
    target = int(st.ptw_audit_min_per_week) if st else 0
    elapsed = min(5, (day - ws).days + 1)
    behind = Decimal(done) < Decimal(target) * elapsed / 5 if target else False
    return PtwBand(
        project_id=proj.id,
        as_of=day,
        active_by_type=[
            PtwBandTypeCount(type=t, count=by[t.value]) for t in PermitType if by.get(t.value)
        ],
        active_total=len(active),
        suspended_non_routine=len(susp),
        high_risk_active=sum(1 for p in active if p.high_risk),
        active_isolations=k67,
        long_term_isolations=lt,
        open_simops_conflicts=open_conf,
        field_audits_this_week=done,
        field_audits_week_target=target,
        audits_behind_plan=behind,
    )


# ---- charts C13-C15 ------------------------------------------------------------------------------


def _axis(id_: str, en: str, ar: str, unit: str | None = None) -> ChartAxis:
    return ChartAxis(id=id_, label_en=en, label_ar=ar, unit_en=unit, unit_ar=unit)


def c13(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    per: list[Counter[str]] = []
    share: list[Decimal | None] = []
    for w in wins:
        a = e.aggregate(w)
        rows = [
            p
            for p in kp.facts(e).permits.values()
            if kp.permit_ok(e, p) and kp._in(e, a, p.issued_d)
        ]
        per.append(Counter(p.primary for p in rows))
        share.append(
            Decimal(sum(1 for p in rows if p.high_risk)) * 100 / Decimal(len(rows))
            if rows
            else None
        )
    series = [
        ch._series(
            t.value,
            *kp.TYPE_LABELS[t.value],
            SeriesKind.bar,
            "left",
            f"series-{(n % 8) + 1}",
            [ch._pt(k, c.get(t.value, 0), 0) for k, c in zip(keys, per, strict=True)],
            stack="types",
        )
        for n, t in enumerate(PermitType)
    ]
    series.append(
        ch._series(
            "high_risk_share",
            "High-risk share",
            "نسبة عالية الخطورة",
            SeriesKind.line,
            "right",
            "leading",
            [ch._pt(k, v, 1, "percent") for k, v in zip(keys, share, strict=True)],
        )
    )
    return ch._spec(
        scope,
        ChartId.C13,
        ChartKind.combo,
        ("Permits issued by month", "التصاريح الصادرة حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[
            _axis("left", "Permits issued", "التصاريح الصادرة"),
            _axis("right", "High-risk share", "نسبة عالية الخطورة", "%"),
        ],
        series=series,
        metric=M.K62,
    )


def c14(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    k61 = [e.result(M.K61, e.aggregate(w)).value for w in wins]
    k64 = [e.result(M.K64, e.aggregate(w)).value for w in wins]
    return ch._spec(
        scope,
        ChartId.C14,
        ChartKind.combo,
        (
            "PTW audit compliance and critical findings",
            "الالتزام في تدقيق التصاريح والمخالفات الحرجة",
        ),
        x_axis=ch._month_axis(wins),
        y_axes=[
            _axis("left", "Critical findings", "المخالفات الحرجة"),
            _axis("right", "Audit compliance", "الالتزام في التدقيق", "%"),
        ],
        series=[
            ch._series(
                "k64",
                "Critical findings",
                "المخالفات الحرجة",
                SeriesKind.bar,
                "left",
                "unsafe",
                [ch._pt(k, v, 0) for k, v in zip(keys, k64, strict=True)],
            ),
            ch._series(
                "k61",
                "Audit compliance",
                "الالتزام في التدقيق",
                SeriesKind.line,
                "right",
                "leading",
                [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k61, strict=True)],
            ),
        ],
        metric=M.K61,
    )


def c15(scope: Scope, e: Engine) -> ChartSpec:
    a = e.aggregate(scope.window)
    by = Counter(s.reason.value for _p, s in kp.suspensions(e, a) if not s.routine)
    rows = sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
    cats = [
        ChartCategory(key=k, label_en=_reason_label(k)[0], label_ar=_reason_label(k)[1])
        for k, _v in rows
    ]
    return ch._spec(
        scope,
        ChartId.C15,
        ChartKind.horizontal_bar,
        ("Non-routine suspensions by reason", "الإيقافات غير الاعتيادية حسب السبب"),
        x_axis=ChartXAxis(
            kind=AxisKind.category, label_en="Reason", label_ar="السبب", categories=cats
        ),
        y_axes=[_axis("left", "Suspensions", "الإيقافات")],
        series=[
            ch._series(
                "suspensions",
                "Suspensions",
                "الإيقافات",
                SeriesKind.bar,
                "left",
                "series-1",
                [ch._pt(k, v, 0) for k, v in rows],
            )
        ],
        metric=M.K65,
    )


PTW_CHARTS = {ChartId.C13: c13, ChartId.C14: c14, ChartId.C15: c15}


def chart(scope: Scope, chart_id: ChartId) -> ChartSpec:
    return PTW_CHARTS[chart_id](scope, ptw_engine(scope))
