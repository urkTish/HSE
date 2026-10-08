"""KPI API payloads (spec 1-dashboard §5.6 K-R13, §6, §8.1). Every number the frontend shows
or the AI quotes is formatted here from the engine's exact values (D-1, AI-1)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, EntityType
from app.core.hse_enums import (
    CaseCategory as C,
)
from app.core.hse_enums import (
    ComparisonKind,
    Granularity,
    IncidentStatus,
    KpiBaseKind,
    KpiMetric,
    KpiWarning,
    NullReason,
    PyramidLayer,
    Severity,
)
from app.kpi import data, fmt, present
from app.kpi.catalogue import (
    CATALOGUE,
    CERT_TILES,
    LAGGING_TILES,
    LEADING_TILES,
    PLACEHOLDERS,
    PTW_TILES,
    TRAINING_TILES,
    KpiDef,
)
from app.kpi.engine import Agg, Component, Engine, LtiFree, Result
from app.kpi.facts import EngFact
from app.kpi.periods import (
    Window,
    add_months,
    comparison,
    fmt_day,
    fmt_month,
    month_start,
    months_between,
    months_ending,
    previous,
    r12_ending,
    range_label,
    sply,
    weeks_between,
)
from app.kpi.scope import Scope
from app.models import (
    CorrectiveAction,
    HseMeeting,
    Incident,
    InjuryCase,
    Inspection,
    Investigation,
    Observation,
    Site,
    WorkforceReturn,
)
from app.schemas.hse_common import EngagementRef
from app.schemas.kpi import (
    AppliedFilters,
    Banner,
    BasesRead,
    ComparisonColumn,
    ComparisonPeriod,
    ComparisonRow,
    ComparisonTableResponse,
    ContractorLeagueResponse,
    ContractorRow,
    DashboardHeadline,
    DashboardResponse,
    DataQualityResponse,
    KpiCatalogue,
    KpiCell,
    KpiComparison,
    KpiComponent,
    KpiContext,
    KpiDefinition,
    KpiPlaceholder,
    KpiSources,
    KpiTile,
    KpiValue,
    LtiFreeRead,
    MissingReturn,
    PeriodRead,
    PyramidLayerRead,
    PyramidResponse,
    SourceRecord,
    SourceRecordPage,
    SourceSet,
    SparkPoint,
    TrendPoint,
    TrendSeries,
    TrendsResponse,
)
from app.services.permissions import Principal

M = KpiMetric
API = "/api/v1"
COMPARISON_LABELS = {
    ComparisonKind.previous: ("Previous period", "الفترة السابقة"),
    ComparisonKind.sply: ("Same period last year", "نفس الفترة من العام الماضي"),
    ComparisonKind.r12: ("Rolling 12 months", "آخر 12 شهراً"),
}

# ---- labels --------------------------------------------------------------------------------------


def metric_label(defn: KpiDef, scope: Scope) -> tuple[str, str]:
    """K-R15: rate labels include the base."""
    if defn.base_kind is None:
        return defn.label_en, defn.label_ar
    base = (
        scope.config.ltifr_base if defn.base_kind == KpiBaseKind.ltifr else scope.config.rate_base
    )
    en, ar = fmt.hours_label(base)
    if defn.metric == M.K23:
        return f"{defn.label_en} (days {en})", f"{defn.label_ar} (أيام {ar})"
    return f"{defn.label_en} ({en})", f"{defn.label_ar} ({ar})"


def eng_ref(e: EngFact) -> EngagementRef:
    return EngagementRef(
        id=e.id,
        contractor_id=e.contractor_id or e.id,
        short_code=e.code,
        name_en=e.name_en,
        name_ar=e.name_ar,
        tier=min(max(e.tier, 1), 3),
    )


def scope_label(scope: Scope) -> str:
    codes = ", ".join(x.code for x in scope.projects) or "—"
    if scope.flt.engs is None:
        who = "all contractors"
    else:
        names = sorted(scope.engagement_label(e) for e in scope.flt.engs)
        who = ", ".join(names[:4]) + (" …" if len(names) > 4 else "") if names else "none"
    extra = []
    if scope.flt.sites is not None and scope.query.site_ids:
        extra.append(f"{len(scope.flt.sites)} site(s)")
    if scope.flt.zone_filtered:
        extra.append("zone filter")
    return f"{codes}, {who}" + (f", {', '.join(extra)}" if extra else "")


# ---- context -------------------------------------------------------------------------------------


def _bases(scope: Scope) -> BasesRead:
    le, la = fmt.hours_label(scope.config.ltifr_base)
    re_, ra = fmt.hours_label(scope.config.rate_base)
    return BasesRead(
        ltifr_base_hours=scope.config.ltifr_base,
        rate_base_hours=scope.config.rate_base,
        ltifr_label_en=le,
        ltifr_label_ar=la,
        rate_label_en=re_,
        rate_label_ar=ra,
        mixed_projects=scope.mixed_bases,
    )


def snapshot(scope: Scope, w: Window | None = None) -> str:
    e = scope.engine
    w = w or scope.window
    head = [sorted(str(x.id) for x in scope.projects), scope.flt, scope.as_of, scope.config]
    key = ("snapshot", repr(head), repr(scope.restated))
    digest = scope.facts.memo.get(key)
    if digest is None:
        # The fact lists are large; their digest is computed once per cached Facts build.
        digest = data.snapshot_hash(
            [
                e.wf,
                e.all_cases,
                e.events,
                e.obs,
                e.insp,
                e.cas,
                e.meetings,
                sorted(scope.facts.engagements.items(), key=lambda kv: str(kv[0])),
            ]
        )
        scope.facts.memo[key] = digest
    return data.snapshot_hash([*head, w, scope.restated, digest])


def completeness(
    scope: Scope, w: Window, engine: Engine | None = None
) -> tuple[Decimal | None, int]:
    a = (engine or scope.engine).aggregate(w)
    pct = Decimal(a.reported) / Decimal(a.expected) * 100 if a.expected else None
    return pct, a.expected - a.reported


def threshold(scope: Scope) -> int:
    return min((s.completeness_threshold_pct for s in scope.hse.values()), default=95)


def context(scope: Scope, w: Window | None = None) -> KpiContext:
    w = w or scope.window
    agg = scope.engine.aggregate(w)
    pct, missing = completeness(scope, w)
    thr = threshold(scope)
    below = pct is not None and pct < thr
    banners: list[Banner] = []
    if below:
        banners.append(
            Banner(
                code=KpiWarning.INCOMPLETE_DATA,
                severity=Severity.warning,
                message_en=f"Man-hours incomplete for {missing} engagement-days — rates may be "
                "overstated",
                message_ar=f"ساعات العمل غير مكتملة لعدد {missing} يوم-مقاول — قد تكون المعدلات "
                "أعلى من الواقع",
                params={"missing_engagement_days": str(missing), "threshold_pct": str(thr)},
            )
        )
    if scope.mixed_bases:
        banners.append(
            Banner(
                code=KpiWarning.MIXED_BASES,
                severity=Severity.info,
                message_en="Selected projects use different bases; rates are computed per "
                "1,000,000 h (LTIFR) and 200,000 h (other rates)",
                message_ar="المشاريع المختارة تستخدم أساسات مختلفة؛ تم احتساب المعدلات لكل "
                "1,000,000 ساعة (LTIFR) و200,000 ساعة (بقية المعدلات)",
                params={"ltifr_base_hours": "1000000", "rate_base_hours": "200000"},
            )
        )
    restated = scope.restated_in(w)
    if restated:
        banners.append(
            Banner(
                code=KpiWarning.RESTATED,
                severity=Severity.info,
                message_en="Figures restated after month lock: " + ", ".join(restated),
                message_ar="أرقام معدلة بعد قفل الشهر: " + "، ".join(restated),
                params={"months": ",".join(restated)},
            )
        )
    if agg.provisional:
        banners.append(
            Banner(
                code=KpiWarning.PROVISIONAL_CASES,
                severity=Severity.info,
                message_en=f"{agg.provisional} provisional case classification(s) included",
                message_ar=f"يشمل {agg.provisional} تصنيف حالة مبدئي",
                params={"provisional_cases": str(agg.provisional)},
            )
        )
    q = scope.query
    return KpiContext(
        period=PeriodRead(
            preset=scope.period.preset,
            start=w.start,
            end=w.end,
            as_of=scope.as_of,
            label_en=scope.period.label_en if w == scope.window else range_label(w)[0],
            label_ar=scope.period.label_ar if w == scope.window else range_label(w)[1],
        ),
        comparisons=[comparison_period(k, cw) for k, cw in scope.comparisons],
        filters=AppliedFilters(
            project_ids=[x.id for x in scope.projects],
            project_codes=[x.code for x in scope.projects],
            all_projects=q.all_projects,
            site_ids=list(q.site_ids),
            zone_ids=list(q.zone_ids),
            zone_type=q.zone_type,
            engagement_ids=list(q.engagement_ids),
            include_subcontractors=q.include_subcontractors,
            tiers=list(q.tiers),
            effective_engagement_ids=sorted(scope.flt.engs, key=str)
            if scope.flt.engs is not None
            else None,
            scope_narrowed=scope.narrowed or scope.role_scoped,
        ),
        bases=_bases(scope),
        data_completeness_pct=fmt.dec_str(pct, 1),
        data_completeness_display=fmt.percent(pct, 1) if pct is not None else fmt.DASH,
        missing_engagement_days=missing,
        completeness_below_threshold=below,
        provisional_cases_count=agg.provisional,
        restated=bool(restated),
        restated_months=restated,
        banners=banners,
        computed_at=now(),
        snapshot_hash=snapshot(scope, w),
    )


def comparison_period(kind: ComparisonKind, w: Window) -> ComparisonPeriod:
    en, ar = range_label(w)
    return ComparisonPeriod(kind=kind, start=w.start, end=w.end, label_en=en, label_ar=ar)


# ---- values --------------------------------------------------------------------------------------


def _component(c: Component) -> KpiComponent:
    dp = present.kind_decimals(c.kind, c.decimals)
    return KpiComponent(
        key=c.key,
        label_en=c.label_en,
        label_ar=c.label_ar,
        value=fmt.dec_str(c.value, dp),
        display=present.display_kind(c.kind, c.value, dp),
        share_pct=fmt.dec_str(c.share, 1),
        share_display=fmt.percent(c.share, 1) if c.share is not None else None,
    )


def target_of(scope: Scope, metric: KpiMetric) -> Decimal | None:
    proj = scope.single_project
    if proj is None:
        return None
    raw = (scope.hse[proj.id].kpi_targets or {}).get(metric.value)
    return Decimal(str(raw)) if raw not in (None, "") else None


def kpi_comparison(
    defn: KpiDef, kind: ComparisonKind, cw: Window, cur: Result, comp: Result
) -> KpiComparison:
    abs_s, abs_d, pct_s, pct_d, direction = present.delta(defn, cur.value, comp.value)
    en, ar = range_label(cw)
    return KpiComparison(
        kind=kind,
        start=cw.start,
        end=cw.end,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, comp.value),
        display=present.display(defn, comp.value),
        abs_delta=abs_s,
        abs_delta_display=abs_d,
        pct_delta=pct_s,
        pct_delta_display=pct_d,
        direction=direction,
    )


def kpi_value(
    scope: Scope,
    metric: KpiMetric,
    w: Window | None = None,
    *,
    engine: Engine | None = None,
    with_comparisons: bool = True,
    sources: KpiSources | None = None,
) -> KpiValue:
    eng = engine or scope.engine
    w = w or scope.window
    defn = CATALOGUE[metric]
    res = eng.result(metric, eng.aggregate(w))
    comps = []
    if with_comparisons and defn.available and metric not in (M.K28, M.K29):
        for kind, scope_cw in scope.comparisons:
            cw = scope_cw if w == scope.window else comparison(kind, scope.period.preset, w)
            comp = eng.result(metric, eng.aggregate(cw))
            comps.append(kpi_comparison(defn, kind, cw, res, comp))
    target = target_of(scope, metric)
    en, ar = metric_label(defn, scope)
    display = present.display(defn, res.value)
    if not defn.available:
        display = "Available from Phase 3" if metric == M.K46 else "—"
    return KpiValue(
        metric=metric,
        label_en=en,
        label_ar=ar,
        short_label_en=defn.short_en,
        short_label_ar=defn.short_ar,
        kind=defn.kind,
        group=defn.group,
        unit_en=defn.unit_en,
        unit_ar=defn.unit_ar,
        better=defn.better,
        value=present.value_str(defn, res.value),
        display=display,
        null_reason=res.null_reason,
        numerator=fmt.exact(res.numerator),
        denominator=fmt.exact(res.denominator),
        numerator_label_en=defn.numerator_en,
        denominator_label_en=defn.denominator_en,
        base=res.base,
        base_kind=defn.base_kind,
        components=[_component(c) for c in res.components],
        comparisons=comps,
        target=fmt.dec_str(target, present.decimals(defn)) if target is not None else None,
        target_display=present.display(defn, target) if target is not None else None,
        rag=present.rag(defn, res.value, target),
        warnings=list(dict.fromkeys(res.warnings)),
        one_case_changes_rate_by=fmt.dec_str(res.one_case_changes_rate_by, 2),
        sources=sources,
        data_source=res.data_source,
        notes=list(res.notes),
    )


def sparkline(scope: Scope, metric: KpiMetric, engine: Engine | None = None) -> list[SparkPoint]:
    eng = engine or scope.engine
    defn = CATALOGUE[metric]
    out = []
    for mw in months_ending(scope.window.end, 12):
        r = eng.result(metric, eng.aggregate(mw))
        en, ar = fmt_month(mw.start)
        out.append(
            SparkPoint(
                period_start=mw.start,
                label_en=en,
                label_ar=ar,
                value=present.value_str(defn, r.value),
                display=present.display(defn, r.value),
            )
        )
    return out


def tile(scope: Scope, metric: KpiMetric) -> KpiTile:
    v = kpi_value(scope, metric)
    return KpiTile(**v.model_dump(), sparkline=sparkline(scope, metric))


def metric_list(scope: Scope, metrics: list[KpiMetric] | None) -> list[KpiValue]:
    return [kpi_value(scope, m) for m in (metrics or list(KpiMetric))]


def source_set(src: tuple[EntityType, list[uuid.UUID]] | None, limit: int) -> SourceSet | None:
    if src is None:
        return None
    et, ids = src
    return SourceSet(entity_type=et, count=len(ids), ids=ids[:limit], truncated=len(ids) > limit)


def single_kpi(scope: Scope, metric: KpiMetric, limit: int) -> KpiValue:
    num, den = scope.engine.sources(metric, scope.window)
    return kpi_value(
        scope, metric, sources=KpiSources(numerator=source_set(num, limit),
                                          denominator=source_set(den, limit))
    )  # fmt: skip


# ---- LTI-free & dashboard ------------------------------------------------------------------------


def can_open_incident(p: Principal, project_id: uuid.UUID | None, site: uuid.UUID,
                      eng: uuid.UUID | None) -> bool:  # fmt: skip
    g = p.grant(project_id, Capability.incident_view)
    return g is not None and g.covers_site(site) and g.covers_engagement(eng)


def lti_free_read(scope: Scope, lf: LtiFree | None = None) -> LtiFreeRead:
    lf = lf or scope.engine.lti_free()
    case = lf.last_lti_case
    ref = inc_id = None
    if case is not None and can_open_incident(scope.p, case.project, case.site, case.eng):
        ref, inc_id = case.incident_ref, case.incident_id
    if lf.last_lti_date is not None:
        de, da = fmt_day(lf.last_lti_date)
        en = f"since last LTI on {de}" + (f" ({ref})" if ref else "")
        ar = f"منذ آخر إصابة مضيعة للوقت في {da}" + (f" ({ref})" if ref else "")
    else:
        de, da = fmt_day(lf.run_start)
        en, ar = f"since {de}", f"منذ {da}"
    return LtiFreeRead(
        as_of=lf.as_of,
        days=lf.days,
        days_display=fmt.number(lf.days),
        man_hours=fmt.dec_str(lf.man_hours, 2) or "0.00",
        man_hours_display=fmt.number(lf.man_hours),
        basis=lf.basis,
        last_lti_date=lf.last_lti_date,
        last_lti_incident_id=inc_id,
        last_lti_incident_ref=ref,
        run_start=lf.run_start,
        label_en=en,
        label_ar=ar,
        longest_run_days=lf.longest_days,
        longest_run_start=lf.longest_start,
        longest_run_end=lf.longest_end,
    )


def itd_window(scope: Scope) -> Window:
    start = scope.facts.project_start or scope.window.start
    return Window(min(start, scope.as_of), scope.as_of)


def dashboard(scope: Scope, db: Session | None = None) -> DashboardResponse:
    from app.kpi import access_views, cert_views, ptw_views  # noqa: PLC0415 (cycle)

    access = db is not None and access_views.has_access(scope)
    ptw = ptw_views.has_ptw(scope)
    if ptw:
        ptw_views.ptw_engine(scope)
    cert = cert_views.has_cert(scope)
    if cert:
        cert_views.cert_engine(scope)
    from app.kpi import train_views  # noqa: PLC0415 (cycle)

    train = train_views.has_training(scope)
    if train:
        train_views.train_engine(scope)
    headline = DashboardHeadline(
        lti_free=lti_free_read(scope),
        man_hours_period=kpi_value(scope, M.K01),
        man_hours_itd=kpi_value(scope, M.K01, itd_window(scope), with_comparisons=False),
        average_headcount=kpi_value(scope, M.K03),
        peak_headcount=kpi_value(scope, M.K04),
        direct_sub_split=kpi_value(scope, M.K02),
    )
    return DashboardResponse(
        context=context(scope),
        headline=headline,
        lagging=[tile(scope, m) for m in LAGGING_TILES],
        leading=[tile(scope, m) for m in LEADING_TILES]
        + ([tile(scope, m) for m in access_views.ACCESS_TILES] if access else [])
        + ([tile(scope, m) for m in PTW_TILES] if ptw else [])
        + ([tile(scope, m) for m in CERT_TILES] if cert else [])
        + ([tile(scope, m) for m in TRAINING_TILES] if train else []),
        access_band=access_views.access_band(db, scope) if access and db is not None else None,
        ptw_band=ptw_views.ptw_band(db, scope) if ptw and db is not None else None,
        cert_band=cert_views.cert_band(db, scope) if cert and db is not None else None,
        training_band=train_views.training_band(db, scope) if train and db is not None else None,
        placeholders=[
            KpiPlaceholder(
                metric=m,
                label_en=CATALOGUE[m].label_en,
                label_ar=CATALOGUE[m].label_ar,
                message_en="Available from Phase 3",
                message_ar="متاح من المرحلة 3",
            )
            for m in PLACEHOLDERS
        ],
    )


def catalogue() -> KpiCatalogue:
    return KpiCatalogue(
        items=[
            KpiDefinition(
                metric=d.metric,
                label_en=d.label_en,
                label_ar=d.label_ar,
                short_label_en=d.short_en,
                short_label_ar=d.short_ar,
                kind=d.kind,
                group=d.group,
                unit_en=d.unit_en,
                unit_ar=d.unit_ar,
                better=d.better,
                decimals=present.decimals(d),
                base_kind=d.base_kind,
                formula_en=d.formula_en,
                spec_ref=d.spec_ref,
                available=d.available,
            )
            for d in CATALOGUE.values()
        ]
    )


# ---- trends --------------------------------------------------------------------------------------


def _point(defn: KpiDef, w: Window, r: Result, label: tuple[str, str] | None = None) -> TrendPoint:
    en, ar = label or range_label(w)
    return TrendPoint(
        period_start=w.start,
        period_end=w.end,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
        null_reason=r.null_reason,
    )


def series_windows(
    scope: Scope, granularity: Granularity, start: date | None, end: date | None
) -> list[Window]:
    end = end or scope.window.end
    if granularity == Granularity.month:
        start = start or add_months(month_start(end), -12)
        return months_between(start, end)
    start = start or end - timedelta(days=7 * 12)
    week = scope.projects[0].settings.week_start if scope.projects[0].settings else "sunday"
    return weeks_between(start, end, week)  # type: ignore[arg-type]


def trend_series(
    scope: Scope,
    metric: KpiMetric,
    granularity: Granularity = Granularity.month,
    start: date | None = None,
    end: date | None = None,
) -> TrendSeries:
    eng = scope.engine
    defn = CATALOGUE[metric]
    wins = series_windows(scope, granularity, start, end)
    results = [eng.result(metric, eng.aggregate(w)) for w in wins]
    monthly = granularity == Granularity.month
    points = [
        _point(defn, w, r, fmt_month(w.start) if monthly else None)
        for w, r in zip(wins, results, strict=True)
    ]
    r12 = []
    if monthly:
        for w in wins:
            rw = r12_ending(w.end)
            r12.append(_point(defn, rw, eng.result(metric, eng.aggregate(rw))))
    ma3 = []
    for i, w in enumerate(wins):
        vals = [r.value for r in results[max(0, i - 2) : i + 1] if r.value is not None]
        avg = sum(vals, Decimal(0)) / 3 if i >= 2 and len(vals) == 3 else None
        r = Result(metric, avg, null_reason=None if avg is not None else NullReason.NO_DENOMINATOR)
        ma3.append(_point(defn, w, r, fmt_month(w.start) if monthly else None))
    exposure = sum(1 for w in wins if eng.aggregate(w).mh > 0)
    return TrendSeries(
        metric=metric,
        label_en=metric_label(defn, scope)[0],
        label_ar=metric_label(defn, scope)[1],
        granularity=granularity,
        points=points,
        r12=r12,
        ma3=ma3,
        periods_with_exposure=exposure,
        trend_established=monthly and exposure >= 6,
    )


def trends(
    scope: Scope,
    metrics: list[KpiMetric],
    granularity: Granularity,
    start: date | None,
    end: date | None,
) -> TrendsResponse:
    return TrendsResponse(
        context=context(scope),
        series=[trend_series(scope, m, granularity, start, end) for m in metrics],
    )


# ---- comparison table (AI-19 §3) -----------------------------------------------------------------

TABLE_METRICS = [
    M.K01, M.K03, M.K05, M.K06, M.K09, M.K10, M.K11, M.K12, M.K13, M.K14, M.K15, M.K16,
    M.K17, M.K20, M.K21, M.K22, M.K23, M.K24, M.K25, M.K27, M.K30, M.K31, M.K32, M.K34,
    M.K35, M.K36, M.K37, M.K39, M.K41, M.K42, M.K44, M.K45,
]  # fmt: skip


def _cell(defn: KpiDef, r: Result | None, value: Decimal | None = None) -> KpiCell:
    v = r.value if r is not None else value
    return KpiCell(
        value=present.value_str(defn, v),
        display=present.display(defn, v),
        null_reason=r.null_reason if r is not None else None,
    )


def comparison_table(scope: Scope, metrics: list[KpiMetric] | None) -> ComparisonTableResponse:
    w = scope.window
    eng = scope.engine
    prev = previous(scope.period.preset, w)
    sp = sply(w)
    r12 = r12_ending(w.end)
    resolved = {
        "current": w,
        "previous": prev,
        "sply": sp,
        "ytd": Window(date(w.end.year, 1, 1), w.end),
        "r12": r12,
    }
    cur_en, cur_ar = range_label(w)
    cols = [
        ("current", cur_en, cur_ar),
        ("previous", "Previous", "السابقة"),
        ("sply", "SPLY", "نفس الفترة من العام الماضي"),
        ("ytd", "YTD", "منذ بداية العام"),
        ("r12", "R12", "آخر 12 شهراً"),
        ("target", "Target", "المستهدف"),
    ]
    columns = [
        ComparisonColumn(
            key=k,
            label_en=en,
            label_ar=ar,
            start=resolved[k].start if k in resolved else None,
            end=resolved[k].end if k in resolved else None,
        )
        for k, en, ar in cols
    ]
    rows = []
    for m in metrics or TABLE_METRICS:
        defn = CATALOGUE[m]
        res = {k: eng.result(m, eng.aggregate(win)) for k, win in resolved.items()}
        cells = {k: _cell(defn, r) for k, r in res.items()}
        target = target_of(scope, m)
        cells["target"] = _cell(defn, None, target)
        en, ar = metric_label(defn, scope)
        rows.append(
            ComparisonRow(
                metric=m,
                label_en=en,
                label_ar=ar,
                cells=cells,
                deltas=[
                    kpi_comparison(defn, k, cw, res["current"], res[k.value])
                    for k, cw in (
                        (ComparisonKind.previous, prev),
                        (ComparisonKind.sply, sp),
                        (ComparisonKind.r12, r12),
                    )
                ],
            )
        )
    return ComparisonTableResponse(context=context(scope), columns=columns, rows=rows)


# ---- pyramid -------------------------------------------------------------------------------------

PYRAMID = [
    (PyramidLayer.FAT, "Fatalities", "الوفيات"),
    (PyramidLayer.LTI, "Lost time injuries", "إصابات مضيعة للوقت"),
    (PyramidLayer.RWC_JTC, "Restricted / transfer", "عمل مقيد / نقل"),
    (PyramidLayer.MTC, "Medical treatment", "علاج طبي"),
    (PyramidLayer.FAC, "First aid", "إسعاف أولي"),
    (PyramidLayer.NM, "Near misses", "حوادث وشيكة"),
    (PyramidLayer.UNSAFE_OBS, "Unsafe acts & conditions", "تصرفات وأوضاع غير آمنة"),
]


def pyramid_counts(a: Agg) -> dict[PyramidLayer, int]:
    return {
        PyramidLayer.FAT: a.cats[C.FAT],
        PyramidLayer.LTI: a.cats[C.LTI],
        PyramidLayer.RWC_JTC: a.cats[C.RWC] + a.cats[C.JTC],
        PyramidLayer.MTC: a.cats[C.MTC],
        PyramidLayer.FAC: a.cats[C.FAC],
        PyramidLayer.NM: a.nm,
        PyramidLayer.UNSAFE_OBS: a.obs_unsafe,
    }


def pyramid(scope: Scope) -> PyramidResponse:
    a = scope.engine.aggregate(scope.window)
    counts = pyramid_counts(a)
    layers = []
    for layer, en, ar in PYRAMID:
        n = counts[layer]
        ratio = Decimal(n) / Decimal(a.tri) if a.tri else None
        layers.append(
            PyramidLayerRead(
                layer=layer,
                label_en=en,
                label_ar=ar,
                count=n,
                ratio_to_tri=fmt.dec_str(ratio, 1),
                ratio_display=fmt.ratio(ratio, 1) if ratio is not None else fmt.DASH,
            )
        )
    return PyramidResponse(context=context(scope), tri=a.tri, layers=layers)


# ---- contractor league (C6) ----------------------------------------------------------------------

LEAGUE_METRICS = {
    "man_hours": M.K01, "tri": M.K10, "trir": M.K21, "ltifr": M.K20, "lti_free_days": M.K28,
    "near_misses": M.K13, "ca_on_time_pct": M.K41, "overdue_cas": M.K42,
}  # fmt: skip


def league_engagements(scope: Scope) -> list[EngFact]:
    engs = [
        e
        for e in scope.facts.engagements.values()
        if scope.flt.engs is None or e.id in scope.flt.engs
    ]
    return sorted(engs, key=lambda e: (e.tier, e.code))


def league_engine(scope: Scope, e: EngFact, rollup: bool) -> Engine:
    ids = frozenset(scope.facts.descendants(e.id)) if rollup else frozenset({e.id})
    return scope.sub_engine(scope.narrowed_filter(engs=ids))


def league_row(scope: Scope, e: EngFact, rollup: bool) -> ContractorRow:
    eng = league_engine(scope, e, rollup)
    a = eng.aggregate(scope.window)
    cells = {}
    for key, m in LEAGUE_METRICS.items():
        defn = CATALOGUE[m]
        r = eng.result(m, a)
        cells[key] = KpiCell(
            value=present.value_str(defn, r.value),
            display=present.display(defn, r.value),
            null_reason=r.null_reason,
        )
    unsafe = Decimal(a.obs_unsafe)
    cells["unsafe_observations"] = KpiCell(value=str(a.obs_unsafe), display=fmt.number(unsafe))
    return ContractorRow(
        engagement=eng_ref(e),
        parent_engagement_id=e.parent,
        low_exposure=a.mh < scope.config.low_exposure_hours,
        **cells,
    )


def contractor_league(scope: Scope, rollup: bool) -> ContractorLeagueResponse:
    return ContractorLeagueResponse(
        context=context(scope),
        rollup=rollup,
        rows=[league_row(scope, e, rollup) for e in league_engagements(scope)],
    )


# ---- data quality (T10) --------------------------------------------------------------------------


def investigations_overdue(db: Session, scope: Scope) -> int:
    rows = db.execute(
        select(Incident.site_id, Incident.responsible_engagement_id)
        .join(Investigation, Investigation.incident_id == Incident.id)
        .where(
            Incident.project_id.in_([x.id for x in scope.projects]),
            Incident.status.in_([IncidentStatus.reported, IncidentStatus.under_investigation]),
            Investigation.due_date.is_not(None),
            Investigation.due_date < scope.as_of,
            Investigation.submitted_at.is_(None),
        )
    ).all()
    f = scope.flt
    return sum(1 for site, eng in rows if f.site_ok(site) and f.eng_ok(eng))


def missing_returns(db: Session, scope: Scope, w: Window, limit: int = 200) -> list[MissingReturn]:
    cells = sorted(scope.engine.missing_cells(w), key=lambda c: (c[2], str(c[0])), reverse=True)
    sites = dict(db.execute(select(Site.id, Site.code)).all()) if cells else {}
    out = []
    for eng_id, site_id, d in cells[:limit]:
        e = scope.facts.engagements[eng_id]
        out.append(MissingReturn(engagement=eng_ref(e), site_code=sites.get(site_id, "?"),
                                 work_date=d))  # fmt: skip
    return out


def data_quality(db: Session, scope: Scope) -> DataQualityResponse:
    a = scope.engine.aggregate(scope.window)
    return DataQualityResponse(
        context=context(scope),
        completeness=kpi_value(scope, M.K45),
        missing_returns=missing_returns(db, scope, scope.window),
        provisional_cases=a.provisional,
        late_reports=a.late,
        investigations_overdue=investigations_overdue(db, scope),
        restated_months=scope.restated_in(scope.window),
    )


# ---- drill-down records --------------------------------------------------------------------------


def source_records(
    db: Session,
    scope: Scope,
    metric: KpiMetric,
    part: str,
    page: int,
    page_size: int,
) -> SourceRecordPage:
    num, den = scope.engine.sources(metric, scope.window)
    src = num if part == "numerator" else den
    if src is None:
        return SourceRecordPage(items=[], total=0, page=page, page_size=page_size,
                                metric=metric, part=part)  # fmt: skip
    et, ids = src
    chunk = ids[(page - 1) * page_size : page * page_size]
    items = _records(db, scope, et, chunk)
    return SourceRecordPage(items=items, total=len(ids), page=page, page_size=page_size,
                            metric=metric, part=part)  # fmt: skip


def _records(db: Session, scope: Scope, et: EntityType, ids: list[uuid.UUID]) -> list[SourceRecord]:
    if not ids:
        return []
    sites: dict[uuid.UUID, str] = dict(db.execute(select(Site.id, Site.code)).all())
    code = scope.engagement_label
    p = scope.p
    out: list[SourceRecord] = []

    def add(
        rid: uuid.UUID,
        ref: str | None,
        d: date,
        label: str,
        site: uuid.UUID | None,
        eng: uuid.UUID | None,
        path: str | None,
        label_ar: str | None = None,
    ) -> None:
        out.append(
            SourceRecord(
                entity_type=et,
                id=rid,
                ref=ref,
                date=d,
                label_en=label,
                label_ar=label_ar or label,
                site_code=sites.get(site) if site else None,
                engagement_code=code(eng) if eng else None,
                detail_path=path,
            )
        )

    if et == EntityType.workforce_return:
        for r in db.scalars(select(WorkforceReturn).where(WorkforceReturn.id.in_(ids))):
            mh = fmt.number(r.man_hours)
            tail = f"{code(r.engagement_id)} · {sites.get(r.site_id, '')}"
            add(r.id, None, r.work_date, f"{mh} h · {tail}", r.site_id, r.engagement_id,
                f"{API}/workforce-returns/{r.id}", f"{mh} ساعة · {tail}")  # fmt: skip
    elif et == EntityType.injury_case:
        rows = db.execute(
            select(InjuryCase, Incident)
            .join(Incident, Incident.id == InjuryCase.incident_id)
            .where(InjuryCase.id.in_(ids))
        ).all()
        for c, inc in rows:
            eng = c.employer_engagement_id
            ok = can_open_incident(p, inc.project_id, inc.site_id, eng)
            label = f"{c.category.value} · {code(eng)} · {sites.get(inc.site_id, '')}"
            add(c.id, f"{inc.ref}-P{c.person_no}", inc.occurred_date, label, inc.site_id, eng,
                f"{API}/incidents/{inc.id}" if ok else None)  # fmt: skip
    elif et == EntityType.incident:
        for inc in db.scalars(select(Incident).where(Incident.id.in_(ids))):
            eng = inc.responsible_engagement_id
            ok = can_open_incident(p, inc.project_id, inc.site_id, eng)
            label = f"{inc.primary_type.value} · {code(eng)} · {sites.get(inc.site_id, '')}"
            add(inc.id, inc.ref, inc.occurred_date, label, inc.site_id, eng,
                f"{API}/incidents/{inc.id}" if ok else None)  # fmt: skip
    elif et == EntityType.observation:
        for o in db.scalars(select(Observation).where(Observation.id.in_(ids))):
            eng = o.observed_engagement_id
            label = f"{o.obs_type.value} · {code(eng)} · {sites.get(o.site_id, '')}"
            add(o.id, o.ref, o.observed_date, label, o.site_id, eng,
                f"{API}/observations/{o.id}")  # fmt: skip
    elif et == EntityType.inspection:
        for i in db.scalars(select(Inspection).where(Inspection.id.in_(ids))):
            label = f"{i.inspection_type.value} · {i.status.value} · {sites.get(i.site_id, '')}"
            d = i.planned_date or i.completed_date or scope.as_of
            add(i.id, i.ref, d, label, i.site_id, i.engagement_id, f"{API}/inspections/{i.id}")
    elif et == EntityType.corrective_action:
        for ca in db.scalars(select(CorrectiveAction).where(CorrectiveAction.id.in_(ids))):
            eng = ca.responsible_engagement_id
            label = f"{ca.priority.value} · {ca.status.value} · {code(eng)}"
            add(ca.id, ca.ref, ca.due_date, label, ca.site_id, eng,
                f"{API}/corrective-actions/{ca.id}")  # fmt: skip
    elif et == EntityType.hse_meeting:
        for m in db.scalars(select(HseMeeting).where(HseMeeting.id.in_(ids))):
            label = f"{m.meeting_type.value} · {m.attended_count or 0}/{m.invited_count}"
            add(m.id, None, m.planned_date, label, None, m.engagement_id,
                f"{API}/hse-meetings/{m.id}")  # fmt: skip
    order = {i: n for n, i in enumerate(ids)}
    out.sort(key=lambda r: order.get(r.id, 0))
    return out
