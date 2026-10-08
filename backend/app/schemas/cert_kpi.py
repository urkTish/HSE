"""Certification KPIs and the dashboard certification band (spec 4-third-party-cert §6.7,
§8.1, KC-1…KC-5).

Values come from the single KPI engine (`app/kpi`); the frontend only formats (KC-1)."""

from pydantic import Field

from app.core.cert_enums import CertKpiGroupBy
from app.schemas.common import ApiModel
from app.schemas.kpi import CertBand, KpiContext, KpiValue


class CertBreakdownRow(ApiModel):
    """Equipment tags and TPI codes may appear as keys; never names, worker_no, cert numbers,
    ID data, ban reasons or verification-failure details (KC-4)."""

    key: str = Field(examples=["mobile_crane", "RIGGER", "RAWABI", "AICC", "A", "2026-09"])
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class CertBreakdown(ApiModel):
    metric: str = Field(examples=["K-72"])
    group_by: CertKpiGroupBy
    rows: list[CertBreakdownRow]


class CertKpiResponse(ApiModel):
    """GET /kpi/certification: K-72…K-81 for the /kpi filters plus `equipment_category` and
    `cert_type`. Multi-value metrics use `components` (K-74 out_of_service · a_defects; K-75
    equipment · scaffolds; K-78 equipment · persons · tpis; K-79 pct · failed). Viewer/Client
    receive the same aggregates (KC-5)."""

    context: KpiContext
    band: CertBand | None
    metrics: list[KpiValue]
    breakdowns: list[CertBreakdown]
