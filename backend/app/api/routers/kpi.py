"""KPI engine endpoints (spec 1-dashboard §5.6, §6, §8.1). All values are computed by
`app.kpi` — the only place rates are computed (D-1)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import DB, CurrentUser, PageParams
from app.api.kpi_params import KpiParams
from app.core.access_enums import AccessKpiGroupBy
from app.core.enums import Capability, ExportFormat
from app.core.errors import error_responses
from app.core.hse_enums import (
    BreakdownDimension,
    BreakdownMeasure,
    ChartId,
    Granularity,
    KpiExportTable,
    KpiMetric,
)
from app.core.ptw_enums import PtwKpiGroupBy
from app.kpi import access_views, charts, ptw_views, scope, service, views
from app.schemas.access_kpi import AccessKpiResponse
from app.schemas.kpi import (
    BreakdownResponse,
    ChartResponse,
    ComparisonTableResponse,
    ContractorLeagueResponse,
    DashboardResponse,
    DataQualityResponse,
    KpiCatalogue,
    KpiListResponse,
    KpiResponse,
    LeadingIndicatorsResponse,
    LtiFreeRead,
    PyramidResponse,
    SourceRecordPage,
    TrendsResponse,
)
from app.schemas.ptw_kpi import PtwKpiResponse

router = APIRouter(prefix="/kpi", tags=["kpi"])

FILTERS = (
    "Common filters (all /kpi endpoints): `project_id` (repeatable) or `all_projects`, "
    "`site_id`, `zone_id`, `zone_type`, `engagement_id` (+ `include_subcontractors`, default "
    "true), `tier`, `period` (+ `anchor` or `start`/`end` for custom), `as_of`, `compare`. "
    "Role scope is applied first (D-3): a narrower scope is reported in "
    "`context.filters.scope_narrowed`. Capability 38."
)
KPI_ERRORS = error_responses(401, 403, 404, 422)
PHASE2_CHARTS = frozenset({ChartId.C10, ChartId.C11, ChartId.C12})
PHASE3_CHARTS = frozenset({ChartId.C13, ChartId.C14, ChartId.C15})


@router.get(
    "/catalogue",
    response_model=KpiCatalogue,
    summary="KPI definitions (labels EN/AR, unit, better direction, formula)",
    responses=error_responses(401, 403),
)
def kpi_catalogue(user: CurrentUser) -> KpiCatalogue:
    return service.catalogue()


@router.get(
    "/metrics",
    response_model=KpiListResponse,
    summary="Several KPIs for one scope and period, with comparisons",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_kpis(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    metric: Annotated[
        list[KpiMetric] | None, Query(description="Metrics to compute; default all.")
    ] = None,
) -> KpiListResponse:
    sc = scope.build(db, user, q)
    return KpiListResponse(context=service.context(sc), kpis=service.metric_list(sc, metric))


@router.get(
    "/metrics/{metric}",
    response_model=KpiResponse,
    summary="One KPI: value, numerator, denominator, base, period, filters, source ids",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_kpi(
    metric: KpiMetric,
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    source_limit: Annotated[
        int, Query(ge=0, le=1000, description="Max source ids per part in `sources`.")
    ] = 200,
) -> KpiResponse:
    sc = scope.build(db, user, q)
    return KpiResponse(
        context=service.context(sc), kpi=service.single_kpi(sc, metric, source_limit)
    )


@router.get(
    "/metrics/{metric}/sources",
    response_model=SourceRecordPage,
    summary="Drill-down: the records behind a KPI's numerator or denominator",
    description=FILTERS + " Records the caller cannot open have `detail_path` = null.",
    responses=KPI_ERRORS,
)
def get_kpi_sources(
    metric: KpiMetric,
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    pg: PageParams,
    part: Literal["numerator", "denominator"] = "numerator",
) -> SourceRecordPage:
    sc = scope.build(db, user, q)
    return service.source_records(db, sc, metric, part, pg.page, pg.page_size)


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard bundle: headline, lagging and leading tiles with sparklines",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_dashboard(user: CurrentUser, db: DB, q: KpiParams) -> DashboardResponse:
    return service.dashboard(scope.build(db, user, q), db)


@router.get(
    "/lti-free",
    response_model=LtiFreeRead,
    summary="LTI-free days and man-hours (§6.4)",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_lti_free(user: CurrentUser, db: DB, q: KpiParams) -> LtiFreeRead:
    return service.lti_free_read(scope.build(db, user, q))


@router.get(
    "/trends",
    response_model=TrendsResponse,
    summary="Time series per metric with R12 and 3-period moving average",
    description=FILTERS + " The series covers `start`…`end` of the period (default: the 13 "
    "months ending at the period end).",
    responses=KPI_ERRORS,
)
def get_trends(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    metric: Annotated[list[KpiMetric], Query(min_length=1, max_length=8)],
    granularity: Granularity = Granularity.month,
    series_start: Annotated[date | None, Query(description="First period start.")] = None,
    series_end: Annotated[date | None, Query(description="Last period end.")] = None,
) -> TrendsResponse:
    sc = scope.build(db, user, q)
    return service.trends(sc, metric, granularity, series_start, series_end)


@router.get(
    "/comparisons",
    response_model=ComparisonTableResponse,
    summary="KPI table: period, previous, SPLY, YTD, R12, target, with deltas",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_comparisons(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    metric: Annotated[list[KpiMetric] | None, Query()] = None,
) -> ComparisonTableResponse:
    return service.comparison_table(scope.build(db, user, q), metric)


@router.get(
    "/breakdowns",
    response_model=BreakdownResponse,
    summary="Breakdown of a measure by a dimension (§6.8)",
    description=FILTERS + " `age_band`/`nationality` need capability 39 (403 "
    "RESTRICTED_DIMENSION); cells of 1-2 persons are suppressed to '<3' for other roles.",
    responses=KPI_ERRORS,
)
def get_breakdown(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    measure: BreakdownMeasure,
    dimension: BreakdownDimension,
    top_n: Annotated[int, Query(ge=1, le=20)] = 10,
) -> BreakdownResponse:
    return views.breakdown(db, scope.build(db, user, q), measure, dimension, top_n)


@router.get(
    "/pyramid",
    response_model=PyramidResponse,
    summary="Safety pyramid for the period (C4)",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_pyramid(user: CurrentUser, db: DB, q: KpiParams) -> PyramidResponse:
    return service.pyramid(scope.build(db, user, q))


@router.get(
    "/leading-indicators",
    response_model=LeadingIndicatorsResponse,
    summary="Leading tiles and leading-indicator warnings E1-E4 (§6.9)",
    description=FILTERS + " Warnings are evaluated for the last `months` complete months "
    "ending at the period end.",
    responses=KPI_ERRORS,
)
def get_leading_indicators(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    months: Annotated[int, Query(ge=1, le=12)] = 3,
) -> LeadingIndicatorsResponse:
    return views.leading_indicators(scope.build(db, user, q), months)


@router.get(
    "/contractors",
    response_model=ContractorLeagueResponse,
    summary="Contractor league table (C6)",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_contractor_league(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    rollup: Annotated[bool, Query(description="Each row includes its subcontractors.")] = False,
) -> ContractorLeagueResponse:
    return service.contractor_league(scope.build(db, user, q), rollup)


@router.get(
    "/data-quality",
    response_model=DataQualityResponse,
    summary="Completeness, missing returns, provisional cases, late reports, restatements",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_data_quality(user: CurrentUser, db: DB, q: KpiParams) -> DataQualityResponse:
    return service.data_quality(db, scope.build(db, user, q))


@router.get(
    "/charts/{chart_id}",
    response_model=ChartResponse,
    summary="Dashboard chart C1-C15 as a renderer-agnostic ChartSpec",
    description=FILTERS + " C7 needs `dimension` (and optional `measure`, default "
    "injury_cases). Monthly charts cover the 12 months ending at the period end.",
    responses=KPI_ERRORS,
)
def get_chart(
    chart_id: ChartId,
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    dimension: BreakdownDimension | None = None,
    measure: BreakdownMeasure | None = None,
    gate_id: Annotated[
        uuid.UUID | None, Query(description="C10/C11: one gate's checks only.")
    ] = None,
) -> ChartResponse:
    if chart_id in PHASE3_CHARTS:
        sc = scope.build(db, user, q, Capability.ptw_kpi_view)
        return ChartResponse(context=service.context(sc), chart=ptw_views.chart(sc, chart_id))
    if chart_id in PHASE2_CHARTS:
        sc = scope.build(db, user, q, Capability.access_kpi_view)
        spec = access_views.chart(db, sc, chart_id, gate_id)
        return ChartResponse(context=service.context(sc), chart=spec)
    sc = scope.build(db, user, q)
    spec = charts.chart(db, sc, chart_id, dimension, measure)
    return ChartResponse(context=service.context(sc), chart=spec)


@router.get(
    "/export/{table}",
    summary="Export a dashboard table as CSV/Excel (capability 42, audited)",
    description=FILTERS,
    response_class=Response,
    responses={
        200: {
            "description": "The exported file (Content-Disposition: attachment).",
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
            },
        },
        **KPI_ERRORS,
    },
)
def export_kpi_table(
    table: KpiExportTable,
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.csv,
    dimension: BreakdownDimension | None = None,
    measure: BreakdownMeasure | None = None,
) -> Response:
    sc = scope.build(db, user, q)
    content, media, name = views.export_table(db, sc, table, format_, dimension, measure)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/access",
    response_model=AccessKpiResponse,
    summary="Access KPIs K-38, K-48…K-60, K-53b with breakdowns (2-access-permits §6.8)",
    description=FILTERS + " Plus `gate_id` (gate KPIs only). Capability 77; Viewer/Client get "
    "aggregates only (KA-4). `group_by` adds breakdown tables: K-51 by kind, K-53 by reason "
    "code (first DENY reason), contractor, zone, gate or month.",
    responses=KPI_ERRORS,
)
def get_access_kpis(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    metric: Annotated[
        list[KpiMetric] | None, Query(description="Default: all access KPIs.")
    ] = None,
    group_by: Annotated[list[AccessKpiGroupBy] | None, Query()] = None,
    gate_id: Annotated[uuid.UUID | None, Query(description="Gate KPIs for one gate.")] = None,
) -> AccessKpiResponse:
    sc = scope.build(db, user, q, Capability.access_kpi_view)
    return access_views.access_kpis(db, sc, metric, group_by, gate_id)


@router.get(
    "/ptw",
    response_model=PtwKpiResponse,
    summary="PTW KPIs K-46, K-46b, K-61…K-71 with breakdowns and the PTW band (3-ptw §6.11)",
    description=FILTERS + " Plus `permit_type` (PTW KPIs only). Capability 103; Viewer/Client "
    "get aggregates only. `group_by` adds breakdown tables (KP-5).",
    responses=KPI_ERRORS,
)
def get_ptw_kpis(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    metric: Annotated[list[KpiMetric] | None, Query(description="Default: all PTW KPIs.")] = None,
    group_by: Annotated[list[PtwKpiGroupBy] | None, Query()] = None,
) -> PtwKpiResponse:
    sc = scope.build(db, user, q, Capability.ptw_kpi_view)
    return ptw_views.ptw_kpis(db, sc, metric, group_by)
