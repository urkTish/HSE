"""Dashboard charts C1-C9 (spec 1-dashboard §8.1 item 5) as renderer-agnostic ChartSpecs.
Every value is an engine value formatted per K-R8; the client draws them as given (D-1)."""

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import validation_error
from app.core.hse_enums import (
    AxisKind,
    BandKind,
    BreakdownDimension,
    BreakdownMeasure,
    CaseCategory,
    ChartId,
    ChartKind,
    KpiMetric,
    SeriesKind,
)
from app.kpi import breakdowns, calendar, fmt, service
from app.kpi.engine import BUCKETS, CONTROL_LABELS, Agg
from app.kpi.periods import Window, fmt_month, month_key, months_ending, r12_ending
from app.kpi.scope import Scope
from app.schemas.kpi import (
    ChartAxis,
    ChartBand,
    ChartCategory,
    ChartCitation,
    ChartPoint,
    ChartReferenceLine,
    ChartSeries,
    ChartSpec,
    ChartTable,
    ChartTableColumn,
    ChartXAxis,
)

M = KpiMetric
C = CaseCategory
HEAT_NATURES = {"heat_exhaustion", "heat_stroke"}


def _months(scope: Scope) -> list[Window]:
    return months_ending(scope.window.end, 12)


def _month_axis(wins: list[Window]) -> ChartXAxis:
    cats = []
    for w in wins:
        en, ar = fmt_month(w.start)
        cats.append(ChartCategory(key=month_key(w.start), label_en=en, label_ar=ar))
    return ChartXAxis(kind=AxisKind.period, label_en="Month", label_ar="الشهر", categories=cats)


def _pt(x: str, v: Decimal | int | None, dp: int, kind: str = "number") -> ChartPoint:
    if v is None:
        return ChartPoint(x=x, value=None, display=fmt.DASH)
    d = Decimal(v)
    disp = fmt.percent(d, dp) if kind == "percent" else fmt.number(d, dp)
    return ChartPoint(x=x, value=fmt.dec_str(d, dp), display=disp)


def _series(
    key: str,
    en: str,
    ar: str,
    kind: SeriesKind,
    axis: str,
    color: str,
    points: list[ChartPoint],
    stack: str | None = None,
) -> ChartSeries:
    return ChartSeries(
        key=key,
        label_en=en,
        label_ar=ar,
        kind=kind,
        y_axis=axis,
        stack=stack,
        color_role=color,
        points=points,
    )


def _citation(
    scope: Scope, chart: str, metric: KpiMetric | None, base: bool = False
) -> ChartCitation:
    base_label = fmt.hours_label(scope.config.rate_base)[0] if base else None
    return ChartCitation(
        tool=f"kpi/charts/{chart}",
        metric=metric,
        period_label_en=scope.period.label_en,
        scope_label_en=service.scope_label(scope),
        base_label_en=base_label,
    )


def _spec(
    scope: Scope,
    chart: ChartId,
    kind: ChartKind,
    title: tuple[str, str],
    *,
    x_axis: ChartXAxis | None,
    y_axes: list[ChartAxis],
    series: list[ChartSeries],
    bands: list[ChartBand] | None = None,
    refs: list[ChartReferenceLine] | None = None,
    table: ChartTable | None = None,
    metric: KpiMetric | None = None,
    base: bool = False,
) -> ChartSpec:
    return ChartSpec(
        chart_id=chart.value,
        kind=kind,
        title_en=title[0],
        title_ar=title[1],
        x_axis=x_axis,
        y_axes=y_axes,
        series=series,
        bands=bands or [],
        reference_lines=refs or [],
        table=table,
        notes=list(service.context(scope).banners),
        citation=_citation(scope, chart.value, metric, base),
    )


def c1(scope: Scope) -> ChartSpec:
    wins = _months(scope)
    e = scope.engine
    aggs = [e.aggregate(w) for w in wins]
    keys = [month_key(w.start) for w in wins]
    series = [
        _series(
            f"tier_{t}",
            f"Tier {t}",
            f"المستوى {t}",
            SeriesKind.bar,
            "left",
            f"series-{t}",
            [_pt(k, a.mh_tier.get(t, Decimal(0)), 0) for k, a in zip(keys, aggs, strict=True)],
            stack="mh",
        )
        for t in (1, 2, 3)
    ]
    series.append(
        _series(
            "avg_headcount",
            "Average headcount",
            "متوسط العمالة",
            SeriesKind.line,
            "right",
            "series-4",
            [_pt(k, e.result(M.K03, a).value, 0) for k, a in zip(keys, aggs, strict=True)],
        )
    )
    return _spec(
        scope,
        ChartId.C1,
        ChartKind.combo,
        ("Man-hours by month", "ساعات العمل حسب الشهر"),
        x_axis=_month_axis(wins),
        y_axes=[
            ChartAxis(
                id="left", label_en="Man-hours", label_ar="ساعات العمل", unit_en="h", unit_ar="ساعة"
            ),
            ChartAxis(
                id="right", label_en="Headcount", label_ar="العمالة", unit_en=None, unit_ar=None
            ),
        ],
        series=series,
        metric=M.K01,
    )


def c2(scope: Scope) -> ChartSpec:
    wins = _months(scope)
    e = scope.engine
    keys = [month_key(w.start) for w in wins]
    trir = [e.result(M.K21, e.aggregate(w)).value for w in wins]
    r12_trir = [e.result(M.K21, e.aggregate(r12_ending(w.end))).value for w in wins]
    r12_ltifr = [e.result(M.K20, e.aggregate(r12_ending(w.end))).value for w in wins]
    refs = []
    target = service.target_of(scope, M.K21)
    if target is not None:
        refs.append(
            ChartReferenceLine(
                y_axis="left",
                value=fmt.dec_str(target, 2) or "",
                display=fmt.number(target, 2),
                label_en="TRIR target",
                label_ar="مستهدف TRIR",
            )
        )
    rate_en, rate_ar = fmt.hours_label(scope.config.rate_base)
    l_en, l_ar = fmt.hours_label(scope.config.ltifr_base)
    return _spec(
        scope,
        ChartId.C2,
        ChartKind.combo,
        ("TRIR and rolling 12-month rates", "معدل الإصابات المسجلة والمعدلات المتحركة 12 شهراً"),
        x_axis=_month_axis(wins),
        y_axes=[
            ChartAxis(
                id="left",
                label_en=f"TRIR ({rate_en})",
                label_ar=f"TRIR ({rate_ar})",
                unit_en=rate_en,
                unit_ar=rate_ar,
            ),
            ChartAxis(
                id="right",
                label_en=f"LTIFR ({l_en})",
                label_ar=f"LTIFR ({l_ar})",
                unit_en=l_en,
                unit_ar=l_ar,
            ),
        ],
        series=[
            _series(
                "trir",
                "TRIR (month)",
                "TRIR (الشهر)",
                SeriesKind.bar,
                "left",
                "lagging",
                [_pt(k, v, 2) for k, v in zip(keys, trir, strict=True)],
            ),
            _series(
                "r12_trir",
                "R12 TRIR",
                "TRIR آخر 12 شهراً",
                SeriesKind.line,
                "left",
                "series-2",
                [_pt(k, v, 2) for k, v in zip(keys, r12_trir, strict=True)],
            ),
            _series(
                "r12_ltifr",
                "R12 LTIFR",
                "LTIFR آخر 12 شهراً",
                SeriesKind.line,
                "right",
                "series-3",
                [_pt(k, v, 2) for k, v in zip(keys, r12_ltifr, strict=True)],
            ),
        ],
        refs=refs,
        metric=M.K21,
        base=True,
    )


C3_SERIES: list[tuple[str, str, str, Callable[[Agg], int]]] = [
    ("lti", "LTI (incl. FAT)", "إصابات مضيعة للوقت", lambda a: a.lti),
    ("rwc_jtc", "RWC + JTC", "عمل مقيد + نقل", lambda a: a.cats[C.RWC] + a.cats[C.JTC]),
    ("mtc", "MTC", "علاج طبي", lambda a: a.cats[C.MTC]),
    ("fac", "FAC", "إسعاف أولي", lambda a: a.cats[C.FAC]),
    ("nm", "Near misses", "حوادث وشيكة", lambda a: a.nm),
    ("do", "Dangerous occurrences", "أحداث خطيرة", lambda a: a.do),
    ("pd", "Property damage", "أضرار ممتلكات", lambda a: a.pd),
    ("env", "Environmental", "بيئية", lambda a: a.env),
]


def c3(scope: Scope) -> ChartSpec:
    wins = _months(scope)
    e = scope.engine
    aggs = [e.aggregate(w) for w in wins]
    keys = [month_key(w.start) for w in wins]
    series = [
        _series(
            k,
            en,
            ar,
            SeriesKind.bar,
            "left",
            f"series-{i + 1}",
            [_pt(x, fn(a), 0) for x, a in zip(keys, aggs, strict=True)],
            stack="events",
        )
        for i, (k, en, ar, fn) in enumerate(C3_SERIES)
    ]
    return _spec(
        scope,
        ChartId.C3,
        ChartKind.stacked_bar,
        ("Events by type", "الأحداث حسب النوع"),
        x_axis=_month_axis(wins),
        y_axes=[
            ChartAxis(id="left", label_en="Count", label_ar="العدد", unit_en=None, unit_ar=None)
        ],
        series=series,
    )


def c4(scope: Scope) -> ChartSpec:
    a = scope.engine.aggregate(scope.window)
    counts = service.pyramid_counts(a)
    points = []
    rows = []
    for layer, en, _ in service.PYRAMID:
        n = counts[layer]
        ratio = Decimal(n) / Decimal(a.tri) if a.tri else None
        points.append(_pt(layer.value, n, 0))
        rows.append(
            {
                "layer": en,
                "count": fmt.number(n),
                "ratio": fmt.ratio(ratio) if ratio is not None else fmt.DASH,
            }
        )
    cats = [
        ChartCategory(key=layer.value, label_en=en, label_ar=ar)
        for layer, en, ar in service.PYRAMID
    ]
    return _spec(
        scope,
        ChartId.C4,
        ChartKind.pyramid,
        ("Safety pyramid", "هرم السلامة"),
        x_axis=ChartXAxis(
            kind=AxisKind.category, label_en="Layer", label_ar="المستوى", categories=cats
        ),
        y_axes=[
            ChartAxis(id="left", label_en="Count", label_ar="العدد", unit_en=None, unit_ar=None)
        ],
        series=[_series("count", "Count", "العدد", SeriesKind.bar, "left", "lagging", points)],
        table=ChartTable(
            columns=[
                ChartTableColumn(key="layer", label_en="Layer", label_ar="المستوى", numeric=False),
                ChartTableColumn(key="count", label_en="Count", label_ar="العدد", numeric=True),
                ChartTableColumn(
                    key="ratio",
                    label_en="Ratio to TRI",
                    label_ar="النسبة إلى الإصابات المسجلة",
                    numeric=True,
                ),
            ],
            rows=rows,
        ),
    )


def c5(scope: Scope) -> ChartSpec:
    wins = _months(scope)
    e = scope.engine
    aggs = [e.aggregate(w) for w in wins]
    keys = [month_key(w.start) for w in wins]
    z = list(zip(keys, aggs, strict=True))
    return _spec(
        scope,
        ChartId.C5,
        ChartKind.combo,
        ("Leading indicator trends", "اتجاهات المؤشرات الاستباقية"),
        x_axis=_month_axis(wins),
        y_axes=[
            ChartAxis(id="left", label_en="Count", label_ar="العدد", unit_en=None, unit_ar=None),
            ChartAxis(
                id="right",
                label_en="Inspection compliance",
                label_ar="الالتزام بالتفتيش",
                unit_en="%",
                unit_ar="%",
            ),
        ],
        series=[
            _series(
                "safe",
                "Safe observations",
                "ملاحظات آمنة",
                SeriesKind.bar,
                "left",
                "safe",
                [_pt(k, a.obs_safe, 0) for k, a in z],
                stack="obs",
            ),
            _series(
                "unsafe",
                "Unsafe observations",
                "ملاحظات غير آمنة",
                SeriesKind.bar,
                "left",
                "unsafe",
                [_pt(k, a.obs_unsafe, 0) for k, a in z],
                stack="obs",
            ),
            _series(
                "overdue_cas",
                "Overdue CAs (month end)",
                "الإجراءات المتأخرة (نهاية الشهر)",
                SeriesKind.bar,
                "left",
                "series-3",
                [_pt(k, a.overdue, 0) for k, a in z],
            ),
            _series(
                "inspection_compliance",
                "Inspection compliance",
                "الالتزام بالتفتيش",
                SeriesKind.line,
                "right",
                "leading",
                [_pt(k, e.result(M.K34, a).value, 1, "percent") for k, a in z],
            ),
        ],
    )


LEAGUE_COLUMNS = [
    ("contractor", "Contractor", "المقاول", False),
    ("tier", "Tier", "المستوى", True),
    ("man_hours", "Man-hours", "ساعات العمل", True),
    ("tri", "TRI", "TRI", True),
    ("trir", "TRIR", "TRIR", True),
    ("ltifr", "LTIFR", "LTIFR", True),
    ("lti_free_days", "LTI-free days", "أيام بدون إصابة", True),
    ("near_misses", "Near misses", "حوادث وشيكة", True),
    ("unsafe_observations", "Unsafe obs.", "ملاحظات غير آمنة", True),
    ("ca_on_time_pct", "CA on time", "الإغلاق في الموعد", True),
    ("overdue_cas", "Overdue CAs", "الإجراءات المتأخرة", True),
    ("low_exposure", "Low exposure", "تعرض منخفض", False),
]


def league_table(scope: Scope, rollup: bool = False) -> ChartTable:
    rows = []
    for e in service.league_engagements(scope):
        r = service.league_row(scope, e, rollup)
        rows.append(
            {
                "contractor": e.code,
                "tier": str(e.tier),
                "man_hours": r.man_hours.display,
                "tri": r.tri.display,
                "trir": r.trir.display,
                "ltifr": r.ltifr.display,
                "lti_free_days": r.lti_free_days.display,
                "near_misses": r.near_misses.display,
                "unsafe_observations": r.unsafe_observations.display,
                "ca_on_time_pct": r.ca_on_time_pct.display,
                "overdue_cas": r.overdue_cas.display,
                "low_exposure": "low exposure" if r.low_exposure else "",
            }
        )
    return ChartTable(
        columns=[
            ChartTableColumn(key=k, label_en=en, label_ar=ar, numeric=n)
            for k, en, ar, n in LEAGUE_COLUMNS
        ],
        rows=rows,
    )


def c6(scope: Scope) -> ChartSpec:
    return _spec(
        scope,
        ChartId.C6,
        ChartKind.table,
        ("Contractor league table", "جدول ترتيب المقاولين"),
        x_axis=None,
        y_axes=[],
        series=[],
        table=league_table(scope),
        base=True,
    )


def c7(
    db: Session,
    scope: Scope,
    dimension: BreakdownDimension | None,
    measure: BreakdownMeasure | None,
) -> ChartSpec:
    if dimension is None:
        raise validation_error("dimension", "C7 needs a dimension.")
    m = measure or BreakdownMeasure.injury_cases
    bd = breakdowns.compute(db, scope, m, dimension)
    small_ok = breakdowns.can_see_small_cells(scope)
    cats, points = [], []
    for r in bd.rows:
        cats.append(ChartCategory(key=r.key, label_en=r.label_en, label_ar=r.label_ar))
        if bd.persons and not small_ok and 0 < r.count < 3:
            points.append(ChartPoint(x=r.key, value=None, display="<3"))
        else:
            points.append(_pt(r.key, r.count, 0))
    men, mar = breakdowns.MEASURE_LABELS[m]
    return _spec(
        scope,
        ChartId.C7,
        ChartKind.horizontal_bar,
        (f"{men} by {dimension.value.replace('_', ' ')}", f"{mar} حسب {dimension.value}"),
        x_axis=ChartXAxis(
            kind=AxisKind.category,
            label_en=dimension.value,
            label_ar=dimension.value,
            categories=cats,
        ),
        y_axes=[
            ChartAxis(id="left", label_en="Count", label_ar="العدد", unit_en=None, unit_ar=None)
        ],
        series=[_series("count", men, mar, SeriesKind.bar, "left", "series-1", points)],
    )


def c8(scope: Scope) -> ChartSpec:
    wins = _months(scope)
    e = scope.engine
    keys = [month_key(w.start) for w in wins]
    s = scope.settings()
    cases, heat = [], []
    for w in wins:
        cs = [c for c in e.cases_in(w) if c.d <= e.as_of]
        cases.append(len(cs))
        heat.append(
            sum(1 for c in cs if c.nature in HEAT_NATURES or c.mechanism == "exposure_heat")
        )
    bands = []
    run: list[str] = []
    for w, k in zip(wins, keys, strict=True):
        if calendar.in_heat_season(
            w.start, s.heat_season_start, s.heat_season_end
        ) or calendar.in_heat_season(w.end, s.heat_season_start, s.heat_season_end):
            run.append(k)
        elif run:
            bands.append(run)
            run = []
    if run:
        bands.append(run)
    return _spec(
        scope,
        ChartId.C8,
        ChartKind.combo,
        ("Heat season view", "عرض موسم الحرارة"),
        x_axis=_month_axis(wins),
        y_axes=[
            ChartAxis(id="left", label_en="Cases", label_ar="الحالات", unit_en=None, unit_ar=None)
        ],
        series=[
            _series(
                "injury_cases",
                "Injury cases",
                "حالات الإصابة",
                SeriesKind.bar,
                "left",
                "lagging",
                [_pt(k, v, 0) for k, v in zip(keys, cases, strict=True)],
            ),
            _series(
                "heat_cases",
                "Heat-related cases",
                "حالات مرتبطة بالحرارة",
                SeriesKind.line,
                "left",
                "series-5",
                [_pt(k, v, 0) for k, v in zip(keys, heat, strict=True)],
            ),
        ],
        bands=[
            ChartBand(
                kind=BandKind.heat_season,
                x_from=b[0],
                x_to=b[-1],
                label_en="Heat season",
                label_ar="موسم الحرارة",
            )
            for b in bands
        ],
    )


def c9(scope: Scope) -> ChartSpec:
    a = scope.engine.aggregate(scope.window)
    cats = [
        ChartCategory(
            key=b.value,
            label_en=f"{b.value.replace('d', '').replace('_', '–')} days",
            label_ar=f"{b.value} يوم",
        )
        for b, _, _ in BUCKETS
    ]
    points = [_pt(b.value, a.buckets[b], 0) for b, _, _ in BUCKETS]
    rows = []
    for level, (en, _) in CONTROL_LABELS.items():
        n = a.controls[level]
        share = Decimal(n) / Decimal(a.raised) * 100 if a.raised else None
        rows.append(
            {
                "control_level": en,
                "count": fmt.number(n),
                "share": fmt.percent(share) if share is not None else fmt.DASH,
            }
        )
    return _spec(
        scope,
        ChartId.C9,
        ChartKind.bar,
        ("CA ageing and control-level mix", "أعمار الإجراءات المتأخرة ومستويات التحكم"),
        x_axis=ChartXAxis(
            kind=AxisKind.category,
            label_en="Days overdue",
            label_ar="أيام التأخير",
            categories=cats,
        ),
        y_axes=[
            ChartAxis(
                id="left",
                label_en="Overdue CAs",
                label_ar="الإجراءات المتأخرة",
                unit_en=None,
                unit_ar=None,
            )
        ],
        series=[
            _series(
                "overdue",
                "Overdue CAs",
                "الإجراءات المتأخرة",
                SeriesKind.bar,
                "left",
                "series-3",
                points,
            )
        ],
        table=ChartTable(
            columns=[
                ChartTableColumn(
                    key="control_level",
                    label_en="Control level",
                    label_ar="مستوى التحكم",
                    numeric=False,
                ),
                ChartTableColumn(
                    key="count", label_en="CAs raised", label_ar="الإجراءات", numeric=True
                ),
                ChartTableColumn(key="share", label_en="Share", label_ar="النسبة", numeric=True),
            ],
            rows=rows,
        ),
        metric=M.K42,
    )


def chart(
    db: Session,
    scope: Scope,
    chart_id: ChartId,
    dimension: BreakdownDimension | None = None,
    measure: BreakdownMeasure | None = None,
) -> ChartSpec:
    if chart_id == ChartId.C7:
        return c7(db, scope, dimension, measure)
    builders = {
        ChartId.C1: c1,
        ChartId.C2: c2,
        ChartId.C3: c3,
        ChartId.C4: c4,
        ChartId.C5: c5,
        ChartId.C6: c6,
        ChartId.C8: c8,
        ChartId.C9: c9,
    }
    return builders[chart_id](scope)
