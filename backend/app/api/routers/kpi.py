"""KPI engine endpoints (spec 1-dashboard §5.6, §6, §8.1). All values are computed by
`app.kpi` — the only place rates are computed (D-1)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import DB, CurrentUser, PageParams
from app.api.kpi_params import KpiParams
from app.core.enums import ExportFormat
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import (
    BreakdownDimension,
    BreakdownMeasure,
    ChartId,
    Granularity,
    KpiExportTable,
    KpiMetric,
)
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

router = APIRouter(prefix="/kpi", tags=["kpi"])

FILTERS = (
    "Common filters (all /kpi endpoints): `project_id` (repeatable) or `all_projects`, "
    "`site_id`, `zone_id`, `zone_type`, `engagement_id` (+ `include_subcontractors`, default "
    "true), `tier`, `period` (+ `anchor` or `start`/`end` for custom), `as_of`, `compare`. "
    "Role scope is applied first (D-3): a narrower scope is reported in "
    "`context.filters.scope_narrowed`. Capability 38."
)
KPI_ERRORS = error_responses(401, 403, 404, 422)


@router.get(
    "/catalogue",
    response_model=KpiCatalogue,
    summary="KPI definitions (labels EN/AR, unit, better direction, formula)",
    responses=error_responses(401, 403),
)
def kpi_catalogue(user: CurrentUser) -> KpiCatalogue:
    raise not_implemented()


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
    raise not_implemented()


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
    raise not_implemented()


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
    raise not_implemented()


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard bundle: headline, lagging and leading tiles with sparklines",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_dashboard(user: CurrentUser, db: DB, q: KpiParams) -> DashboardResponse:
    raise not_implemented()


@router.get(
    "/lti-free",
    response_model=LtiFreeRead,
    summary="LTI-free days and man-hours (§6.4)",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_lti_free(user: CurrentUser, db: DB, q: KpiParams) -> LtiFreeRead:
    raise not_implemented()


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
    raise not_implemented()


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
    raise not_implemented()


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
    raise not_implemented()


@router.get(
    "/pyramid",
    response_model=PyramidResponse,
    summary="Safety pyramid for the period (C4)",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_pyramid(user: CurrentUser, db: DB, q: KpiParams) -> PyramidResponse:
    raise not_implemented()


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
    raise not_implemented()


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
    raise not_implemented()


@router.get(
    "/data-quality",
    response_model=DataQualityResponse,
    summary="Completeness, missing returns, provisional cases, late reports, restatements",
    description=FILTERS,
    responses=KPI_ERRORS,
)
def get_data_quality(user: CurrentUser, db: DB, q: KpiParams) -> DataQualityResponse:
    raise not_implemented()


@router.get(
    "/charts/{chart_id}",
    response_model=ChartResponse,
    summary="Dashboard chart C1-C9 as a renderer-agnostic ChartSpec",
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
) -> ChartResponse:
    raise not_implemented()


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
    raise not_implemented()
