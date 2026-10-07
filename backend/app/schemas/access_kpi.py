"""Access KPIs and the dashboard access band (spec 2-access-permits §6.8, §8.1, KA-1…KA-5).

Values come from the single KPI engine (`app/kpi`); the frontend only formats (KA-1)."""

from pydantic import Field

from app.core.access_enums import AccessKpiGroupBy
from app.schemas.common import ApiModel
from app.schemas.kpi import AccessBand, KpiContext, KpiValue


class AccessBreakdownRow(ApiModel):
    key: str = Field(examples=["INDUCTION_EXPIRED", "2026-09", "GULFPAVE"])
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class AccessBreakdown(ApiModel):
    metric: str = Field(examples=["K-53"])
    group_by: AccessKpiGroupBy
    rows: list[AccessBreakdownRow]


class AccessKpiResponse(ApiModel):
    """GET /kpi/access: the access KPI page (K-38, K-48…K-60, K-53b) for the /kpi filters plus
    `gate_id`. Viewer/Client receive the same aggregates (no names, worker_no or plates)."""

    context: KpiContext
    band: AccessBand | None = Field(description="Null on non-airport projects.")
    metrics: list[KpiValue]
    breakdowns: list[AccessBreakdown]
