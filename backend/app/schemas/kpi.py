"""KPI engine API (spec 1-dashboard §5.6, §5.7, §6).

Every number shown by the frontend or quoted by the AI comes from these payloads (D-1, AI-1).
Numeric values are decimal strings already rounded per K-R8 (half-up); `display` strings are
the exact text to show (western digits, thousands separators, units). The frontend may only
re-map digits (Arabic-Indic per project `digits` setting) — never recompute (AC63).
"""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.enums import EntityType, ZoneType
from app.core.hse_enums import (
    AxisKind,
    BandKind,
    BreakdownDimension,
    BreakdownMeasure,
    ChartKind,
    ComparisonKind,
    DeltaDirection,
    Granularity,
    KpiBaseKind,
    KpiBetter,
    KpiGroup,
    KpiKind,
    KpiMetric,
    KpiWarning,
    LeadingWarningCode,
    NullReason,
    PeriodPreset,
    PyramidLayer,
    Rag,
    SeriesKind,
    Severity,
)
from app.schemas.common import ApiModel, Page
from app.schemas.hse_common import EngagementRef

DEC = "Decimal string rounded per K-R8 (half-up); null = '—'."

# ---- context -----------------------------------------------------------------------------------


class PeriodRead(ApiModel):
    preset: PeriodPreset
    start: date = Field(description="Inclusive (project-local date).")
    end: date = Field(description="Inclusive.")
    as_of: date = Field(description="Open cases accrue and 'overdue' is evaluated at this date.")
    label_en: str = Field(examples=["Sep 2026", "R12 to Sep 2026", "05 Sep 2026 – 14 Sep 2026"])
    label_ar: str


class ComparisonPeriod(ApiModel):
    kind: ComparisonKind
    start: date
    end: date
    label_en: str
    label_ar: str


class AppliedFilters(ApiModel):
    """Echo of the filters after role scoping (D-3) and contractor roll-up (K-R5)."""

    project_ids: list[uuid.UUID]
    project_codes: list[str]
    all_projects: bool
    site_ids: list[uuid.UUID]
    zone_ids: list[uuid.UUID]
    zone_type: ZoneType | None
    engagement_ids: list[uuid.UUID] = Field(description="As requested.")
    include_subcontractors: bool
    tiers: list[int]
    effective_engagement_ids: list[uuid.UUID] | None = Field(
        description="Engagements actually counted (roll-up + role scope); null = all."
    )
    scope_narrowed: bool = Field(
        description="True when the caller's role scope reduced the request (D-3, AI-4)."
    )


class BasesRead(ApiModel):
    ltifr_base_hours: int
    rate_base_hours: int
    ltifr_label_en: str = Field(examples=["per 1,000,000 h"])
    ltifr_label_ar: str
    rate_label_en: str = Field(examples=["per 200,000 h"])
    rate_label_ar: str
    mixed_projects: bool = Field(
        description="K-R12: selected projects use different bases; 1,000,000/200,000 applied."
    )


class Banner(ApiModel):
    code: KpiWarning
    severity: Severity
    message_en: str
    message_ar: str
    params: dict[str, str] = Field(
        default_factory=dict, description="e.g. {missing_engagement_days: '7'}."
    )


class KpiContext(ApiModel):
    """K-R13: period, filters, bases, completeness, provisional count, restated flag."""

    period: PeriodRead
    comparisons: list[ComparisonPeriod]
    filters: AppliedFilters
    bases: BasesRead
    data_completeness_pct: str | None = Field(description="K-45, 1 dp. " + DEC)
    data_completeness_display: str = Field(examples=["97.5 %"])
    missing_engagement_days: int
    completeness_below_threshold: bool = Field(description="D-6 banner condition.")
    provisional_cases_count: int = Field(description="K-R14.")
    restated: bool = Field(description="Inputs changed after a month lock (W-10, I-9).")
    restated_months: list[str] = Field(examples=[["2026-08"]])
    banners: list[Banner]
    computed_at: datetime
    snapshot_hash: str = Field(
        description="Hash of the inputs in scope; equal hashes ⇒ identical figures (AI cache, "
        "report freezing)."
    )


# ---- values ------------------------------------------------------------------------------------


class KpiCell(ApiModel):
    value: str | None = Field(description=DEC)
    display: str
    null_reason: NullReason | None = None


class KpiComponent(KpiCell):
    """Named part of a composite KPI, e.g. K-02 direct/subcontractor, K-30 safe/unsafe,
    K-42 ageing buckets, K-43 control-level mix, K-15 cost (SAR)."""

    key: str = Field(examples=["direct", "subcontractor", "8-30", "engineering"])
    label_en: str
    label_ar: str
    share_pct: str | None = Field(default=None, description="Share of the parent, 1 dp.")
    share_display: str | None = None


class KpiComparison(ApiModel):
    """K-R9: abs Δ = current − comparison (unrounded, then 2 dp); % Δ 1 dp; 'n/a' when the
    comparison is 0 or '—'."""

    kind: ComparisonKind
    start: date
    end: date
    label_en: str
    label_ar: str
    value: str | None = Field(description=DEC)
    display: str
    abs_delta: str | None
    abs_delta_display: str = Field(examples=["−0.01", "+0.26", "n/a"])
    pct_delta: str | None
    pct_delta_display: str = Field(examples=["−1.1 %", "+40.2 %", "n/a"])
    direction: DeltaDirection = Field(description="better/worse per the metric's `better`.")


class SourceSet(ApiModel):
    """Records behind a numerator or denominator (drill-down)."""

    entity_type: EntityType
    count: int
    ids: list[uuid.UUID] = Field(description="First `source_limit` ids (single-KPI endpoint).")
    truncated: bool


class KpiSources(ApiModel):
    numerator: SourceSet | None
    denominator: SourceSet | None


class KpiValue(ApiModel):
    metric: KpiMetric
    label_en: str = Field(
        description="Includes the base for rates (K-R15).",
        examples=["TRIR (per 200,000 h)"],
    )
    label_ar: str
    short_label_en: str = Field(examples=["TRIR"])
    short_label_ar: str
    kind: KpiKind
    group: KpiGroup
    unit_en: str
    unit_ar: str
    better: KpiBetter
    value: str | None = Field(description=DEC)
    display: str = Field(examples=["0.92", "870,000", "41.4 %", "2.4 : 1", "—"])
    null_reason: NullReason | None
    numerator: str | None = Field(description="Count or sum used as numerator (unrounded sums).")
    denominator: str | None = Field(description="Man-hours for rates; other denominators else.")
    numerator_label_en: str | None
    denominator_label_en: str | None
    base: int | None = Field(description="Normalisation base for rates, else null.")
    base_kind: KpiBaseKind | None
    components: list[KpiComponent]
    comparisons: list[KpiComparison]
    target: str | None
    target_display: str | None
    rag: Rag | None = Field(description="D-4; null when no target is set.")
    warnings: list[KpiWarning]
    one_case_changes_rate_by: str | None = Field(
        description="AI-7(b): base ÷ man-hours, 2 dp; set for rates with low exposure."
    )
    sources: KpiSources | None = Field(
        description="Present on GET /kpi/metrics/{metric}; null in bundles (use drill-down)."
    )


class SparkPoint(ApiModel):
    period_start: date
    label_en: str
    label_ar: str
    value: str | None
    display: str


class KpiTile(KpiValue):
    sparkline: list[SparkPoint] = Field(description="Last 12 months ending at the period end.")


class KpiResponse(ApiModel):
    context: KpiContext
    kpi: KpiValue


class KpiListResponse(ApiModel):
    context: KpiContext
    kpis: list[KpiValue]


class KpiDefinition(ApiModel):
    metric: KpiMetric
    label_en: str
    label_ar: str
    short_label_en: str
    short_label_ar: str
    kind: KpiKind
    group: KpiGroup
    unit_en: str
    unit_ar: str
    better: KpiBetter
    decimals: int
    base_kind: KpiBaseKind | None
    formula_en: str
    spec_ref: str = Field(examples=["1-dashboard §6.1 K-21"])
    available: bool = Field(description="False for placeholders (K-46 'Available from Phase 3').")


class KpiCatalogue(ApiModel):
    items: list[KpiDefinition]


# ---- LTI-free, dashboard bundle ----------------------------------------------------------------


class LtiFreeRead(ApiModel):
    """§6.4 / D-5."""

    as_of: date
    days: int
    days_display: str
    man_hours: str
    man_hours_display: str
    basis: str = Field(description="since_last_lti | since_start")
    last_lti_date: date | None
    last_lti_incident_id: uuid.UUID | None = Field(
        description="Null when the caller may not open that incident."
    )
    last_lti_incident_ref: str | None
    run_start: date = Field(description="Day after last LTI, or run start (§6.4.3).")
    label_en: str = Field(examples=["since last LTI on 08 Sep 2026 (INC-ANIA-EXP-2026-0147)"])
    label_ar: str
    longest_run_days: int
    longest_run_start: date | None
    longest_run_end: date | None


class KpiPlaceholder(ApiModel):
    metric: KpiMetric
    label_en: str
    label_ar: str
    message_en: str = Field(examples=["Available from Phase 3"])
    message_ar: str


class DashboardHeadline(ApiModel):
    lti_free: LtiFreeRead
    man_hours_period: KpiValue
    man_hours_itd: KpiValue
    average_headcount: KpiValue
    peak_headcount: KpiValue
    direct_sub_split: KpiValue


class DashboardResponse(ApiModel):
    """§8.1 items 1-4 in one call. Charts: GET /kpi/charts/{chart_id}; action panel:
    GET /dashboard/action-panel."""

    context: KpiContext
    headline: DashboardHeadline
    lagging: list[KpiTile]
    leading: list[KpiTile]
    placeholders: list[KpiPlaceholder]


# ---- trends, comparisons table ----------------------------------------------------------------


class TrendPoint(ApiModel):
    period_start: date
    period_end: date
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None
    denominator: str | None
    null_reason: NullReason | None


class TrendSeries(ApiModel):
    metric: KpiMetric
    label_en: str
    label_ar: str
    granularity: Granularity
    points: list[TrendPoint]
    r12: list[TrendPoint] = Field(description="R12 value ending at each point (monthly only).")
    ma3: list[TrendPoint] = Field(description="3-period moving average of the point values.")
    periods_with_exposure: int
    trend_established: bool = Field(
        description="AI-8: ≥ 6 monthly points with man-hours > 0; otherwise report values only."
    )


class TrendsResponse(ApiModel):
    context: KpiContext
    series: list[TrendSeries]


class ComparisonColumn(ApiModel):
    key: str = Field(examples=["current", "previous", "sply", "ytd", "r12", "target"])
    label_en: str
    label_ar: str
    start: date | None
    end: date | None


class ComparisonRow(ApiModel):
    metric: KpiMetric
    label_en: str
    label_ar: str
    cells: dict[str, KpiCell] = Field(description="Keyed by column key.")
    deltas: list[KpiComparison] = Field(description="Current vs previous / SPLY / R12.")


class ComparisonTableResponse(ApiModel):
    """AI-19 §3 KPI table: month, previous month, SPLY, YTD, R12, target, with Δ."""

    context: KpiContext
    columns: list[ComparisonColumn]
    rows: list[ComparisonRow]


# ---- breakdowns, pyramid, league table -------------------------------------------------------


class BreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    count: int | None = Field(description="Null when suppressed.")
    count_display: str = Field(examples=["12", "<3"])
    suppressed: bool = Field(description="D-7 / AI-6: 1-2 persons for non-manager/officer.")
    man_hours: str | None = Field(description="Exposure, when the dimension has man-hours.")
    rate: str | None
    rate_display: str | None
    share_pct: str | None
    share_display: str | None


class BreakdownResponse(ApiModel):
    context: KpiContext
    measure: BreakdownMeasure
    dimension: BreakdownDimension
    exposure_available: bool = Field(
        description="Man-hours exist for this dimension (site, zone, contractor, tier, shift…)."
    )
    rate_label_en: str | None
    rate_label_ar: str | None
    total_count: int
    rows: list[BreakdownRow]
    other: BreakdownRow | None = Field(description="Remaining values beyond top_n.")


class PyramidLayerRead(ApiModel):
    layer: PyramidLayer
    label_en: str
    label_ar: str
    count: int
    ratio_to_tri: str | None = Field(description="count ÷ TRI, 1 dp; null when TRI = 0.")
    ratio_display: str = Field(examples=["6.0 : 1", "—"])


class PyramidResponse(ApiModel):
    context: KpiContext
    tri: int
    layers: list[PyramidLayerRead] = Field(description="FAT at the top → unsafe observations.")


class ContractorRow(ApiModel):
    engagement: EngagementRef
    parent_engagement_id: uuid.UUID | None
    man_hours: KpiCell
    tri: KpiCell
    trir: KpiCell
    ltifr: KpiCell
    lti_free_days: KpiCell
    near_misses: KpiCell
    unsafe_observations: KpiCell
    ca_on_time_pct: KpiCell
    overdue_cas: KpiCell
    low_exposure: bool = Field(description="Man-hours < low_exposure_hours (flag, not ranked).")


class ContractorLeagueResponse(ApiModel):
    """C6. Each row is the engagement itself, or the engagement + descendants when
    `rollup=true`."""

    context: KpiContext
    rollup: bool
    rows: list[ContractorRow]


# ---- leading indicators & warnings -----------------------------------------------------------


class WarningInput(ApiModel):
    key: str = Field(examples=["nm_rate_month", "nm_rate_prior3_mean", "overdue_end_month"])
    label_en: str
    label_ar: str
    value: str | None
    display: str


class LeadingWarning(ApiModel):
    """§6.9 E1-E4, evaluated per complete month per project and per tier-1 contractor tree."""

    code: LeadingWarningCode
    month: str = Field(examples=["2026-07"])
    project_id: uuid.UUID
    engagement: EngagementRef | None = Field(description="Tier-1 tree, or null = whole project.")
    message_en: str
    message_ar: str
    inputs: list[WarningInput]


class LeadingIndicatorsResponse(ApiModel):
    context: KpiContext
    tiles: list[KpiTile]
    warnings: list[LeadingWarning] = Field(description="Raised in the evaluated months.")
    evaluated_months: list[str]


# ---- data quality ------------------------------------------------------------------------------


class MissingReturn(ApiModel):
    engagement: EngagementRef
    site_code: str
    work_date: date


class DataQualityResponse(ApiModel):
    """T10."""

    context: KpiContext
    completeness: KpiValue
    missing_returns: list[MissingReturn] = Field(description="First 200, newest first.")
    provisional_cases: int
    late_reports: int
    investigations_overdue: int
    restated_months: list[str]


# ---- drill-down -------------------------------------------------------------------------------


class SourceRecord(ApiModel):
    entity_type: EntityType
    id: uuid.UUID
    ref: str | None = Field(description="Incident/CA/observation/inspection ref; null for rows.")
    date: date
    label_en: str = Field(examples=["LTI · NAJD · S-LAND", "29,000 h · RAWABI · S-AIR"])
    label_ar: str
    site_code: str | None
    engagement_code: str | None
    detail_path: str | None = Field(
        description="API path of the record (e.g. /api/v1/incidents/{id}); null when the "
        "caller may not open it."
    )


class SourceRecordPage(Page[SourceRecord]):
    metric: KpiMetric
    part: str = Field(description="numerator | denominator")


# ---- chart spec (shared by dashboard charts and AI answers) --------------------------------


class ChartCategory(ApiModel):
    key: str = Field(examples=["2026-09", "RAWABI", "fall_from_height"])
    label_en: str
    label_ar: str


class ChartAxis(ApiModel):
    id: str = Field(examples=["left", "right"])
    label_en: str
    label_ar: str
    unit_en: str | None
    unit_ar: str | None


class ChartXAxis(ApiModel):
    kind: AxisKind
    label_en: str
    label_ar: str
    categories: list[ChartCategory] = Field(description="Order to draw (LTR; mirror for RTL).")


class ChartPoint(ApiModel):
    x: str = Field(description="Category key.")
    value: str | None = Field(description=DEC)
    display: str


class ChartSeries(ApiModel):
    key: str
    label_en: str
    label_ar: str
    kind: SeriesKind
    y_axis: str = Field(description="ChartAxis.id")
    stack: str | None = Field(description="Series with the same stack id are stacked.")
    color_role: str = Field(
        description="Token name from the design system: series-1…series-8, or a semantic role "
        "(target, lagging, leading, safe, unsafe).",
        examples=["series-1", "target"],
    )
    points: list[ChartPoint]


class ChartBand(ApiModel):
    kind: BandKind
    x_from: str
    x_to: str
    label_en: str
    label_ar: str


class ChartReferenceLine(ApiModel):
    y_axis: str
    value: str
    display: str
    label_en: str
    label_ar: str
    color_role: str = "target"


class ChartTableColumn(ApiModel):
    key: str
    label_en: str
    label_ar: str
    numeric: bool


class ChartTable(ApiModel):
    """For kind = table (e.g. C6 league table, AI fallback table). Cells are display strings."""

    columns: list[ChartTableColumn]
    rows: list[dict[str, str]]


class ChartCitation(ApiModel):
    tool: str = Field(examples=["get_kpis", "kpi/charts/C2"])
    metric: KpiMetric | None
    period_label_en: str
    scope_label_en: str = Field(examples=["ANIA-EXP, all contractors"])
    base_label_en: str | None


class ChartSpec(ApiModel):
    """Renderer-agnostic chart description. All values come from the KPI engine; the client
    draws them as given (no aggregation, no recomputation)."""

    chart_id: str = Field(description="C1…C9 for dashboard charts, 'ai-<n>' in AI answers.")
    kind: ChartKind
    title_en: str
    title_ar: str
    x_axis: ChartXAxis | None = Field(description="Null for kind = table/pyramid.")
    y_axes: list[ChartAxis]
    series: list[ChartSeries]
    bands: list[ChartBand]
    reference_lines: list[ChartReferenceLine]
    table: ChartTable | None
    notes: list[Banner]
    citation: ChartCitation


class ChartResponse(ApiModel):
    context: KpiContext
    chart: ChartSpec
