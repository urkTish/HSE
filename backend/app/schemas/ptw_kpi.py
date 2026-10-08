"""PTW KPIs and the dashboard PTW band (spec 3-ptw §6.11, §8.1, KP-1…KP-6).

Values come from the single KPI engine (`app/kpi`); the frontend only formats (KP-1)."""

from pydantic import Field

from app.core.ptw_enums import PtwKpiGroupBy
from app.schemas.common import ApiModel
from app.schemas.kpi import KpiContext, KpiValue, PtwBand


class PtwBreakdownRow(ApiModel):
    key: str = Field(examples=["hot_work", "ops_suspension", "A14", "SM-R05b", "2026-09"])
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class PtwBreakdown(ApiModel):
    metric: str = Field(examples=["K-62"])
    group_by: PtwKpiGroupBy
    rows: list[PtwBreakdownRow]


class PtwKpiResponse(ApiModel):
    """GET /kpi/ptw: K-46, K-46b, K-61…K-71 for the /kpi filters plus `permit_type`.
    Viewer/Client receive the same aggregates (no names, worker_no, signatures or appointment
    holders, KP-6)."""

    context: KpiContext
    band: PtwBand | None
    metrics: list[KpiValue]
    breakdowns: list[PtwBreakdown]
