"""Training KPIs and the dashboard training band (spec 5-training §6.8, §8.1, TK-1…TK-5).

Values come from the single KPI engine (`app/kpi`); the frontend only formats (TK-1)."""

from pydantic import Field

from app.core.train_enums import TrainingKpiGroupBy
from app.schemas.common import ApiModel
from app.schemas.kpi import KpiContext, KpiValue, TrainingBand


class TrainingBreakdownRow(ApiModel):
    """Course codes, categories, contractor short codes, trades, provider codes and months as
    keys; never names, worker_no, certificate numbers, scores, ID data or verification-failure
    details (TK-4)."""

    key: str = Field(examples=["WAH", "high_risk_task", "RAWABI", "scaffolder", "HAYAT", "2026-09"])
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class TrainingBreakdown(ApiModel):
    metric: str = Field(examples=["K-82"])
    group_by: TrainingKpiGroupBy
    rows: list[TrainingBreakdownRow]


class TrainingKpiResponse(ApiModel):
    """GET /kpi/training: K-37 (revised source) and K-82…K-88 for the /kpi filters plus
    `trade`, `course_code` and `course_category`. Multi-value metrics use `components` (K-84
    gaps · workers · hook_gaps; K-86 contractor · staff · voided). Viewer/Client receive the
    same aggregates (TK-5)."""

    context: KpiContext
    band: TrainingBand | None
    metrics: list[KpiValue]
    breakdowns: list[TrainingBreakdown]
