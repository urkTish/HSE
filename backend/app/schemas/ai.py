"""AI assistant, auto-insights and monthly report (spec 1-dashboard §5.9).

POST /ai/ask streams Server-Sent Events; see `AiStreamEvent` for the event format.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.enums import Language
from app.core.hse_enums import (
    AiPromptWarning,
    AiTool,
    ControlLevel,
    GroundingResult,
    InsightKind,
    InsightSource,
    KpiMetric,
    MonthlyReportSection,
    MonthlyReportStatus,
    Severity,
)
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.dashboard import DashboardFilters
from app.schemas.hse_common import UserRef
from app.schemas.kpi import ChartSpec, ChartTable

AI_LABEL_EN = "AI-generated — to be reviewed by a competent person"
AI_LABEL_AR = "مُولَّد آلياً — يُراجع من شخص مختص"
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class AiAskRequest(StrictInput):
    project_id: uuid.UUID = Field(description="Project the question is about (scope, AI-4).")
    question: str = Field(min_length=1, max_length=2000)
    language: Language | None = Field(
        default=None, description="Answer language; default = the user's UI language (AI-13)."
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Continue a conversation (previous turns are context only)."
    )
    filters: DashboardFilters | None = Field(
        default=None,
        description="Current dashboard filters, used as the default scope for tool calls.",
    )
    deep_analysis: bool = Field(default=False, description="Use the deep-analysis model.")


class AiCitation(ApiModel):
    """AI-3 Sources entry, e.g. 'TRIR 0.92 — get_kpis, ANIA-EXP, Sep 2026, all contractors,
    per 200,000 h'."""

    id: str = Field(examples=["S1"])
    tool: AiTool
    metric: KpiMetric | None
    value_display: str | None
    period_label_en: str | None
    scope_label_en: str | None
    base_label_en: str | None
    refs: list[str] = Field(description="Incident/CA refs used.")
    text_en: str
    text_ar: str


class AiRecommendation(ApiModel):
    """AI-11. Ordered by the hierarchy of controls; prefill for 'Create CA' (CA-7)."""

    id: str = Field(examples=["R1"])
    control_level: ControlLevel
    title: str
    text: str
    citation_ids: list[str]


class AiAnswer(ApiModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    language: Language
    question_masked: str = Field(description="The question as sent to the model (AI-15).")
    prompt_warnings: list[AiPromptWarning]
    text: str = Field(description="Markdown. Ends with the Sources block (AI-3).")
    citations: list[AiCitation]
    recommendations: list[AiRecommendation]
    chart: ChartSpec | None
    grounding: GroundingResult
    fallback_table: ChartTable | None = Field(
        description="AI-2 second failure: raw tool table shown instead of an answer."
    )
    ai_label_en: str = AI_LABEL_EN
    ai_label_ar: str = AI_LABEL_AR
    model: str
    created_at: datetime


# ---- SSE stream ---------------------------------------------------------------------------------


class AiStreamMeta(ApiModel):
    answer_id: uuid.UUID
    conversation_id: uuid.UUID
    model: str
    prompt_warnings: list[AiPromptWarning]
    question_masked: str


class AiStreamStatus(ApiModel):
    stage: Literal["thinking", "tool", "grounding", "regenerating", "writing"]
    tool: AiTool | None = None
    message_en: str
    message_ar: str


class AiStreamDelta(ApiModel):
    text: str = Field(description="Next chunk of the verified answer text (append).")


class AiStreamError(ApiModel):
    code: str = Field(examples=["AI_UNAVAILABLE"])
    message: str
    message_ar: str | None


class AiStreamEvent(ApiModel):
    """One SSE frame of POST /ai/ask (`Content-Type: text/event-stream`):

    ```
    event: <event>
    data: <JSON of `data`>

    ```

    Order: `meta` (once) → `status`* (progress: tool calls, grounding check) → `delta`*
    (verified answer text, sent only after the AI-2 grounding check passed) → `citations`,
    `chart` (optional), `recommendations` (optional) → `done` (the full `AiAnswer`, the
    source of truth; replace what was rendered from deltas). On the AI-2 second failure the
    deltas carry the fallback message and `done.fallback_table` holds the raw tool table.
    Errors after the stream started arrive as `error` (e.g. AI_UNAVAILABLE on provider
    timeout) and end the stream. Errors before streaming (AI_DISABLED 403, AI_UNAVAILABLE 503,
    AI_RATE_LIMITED 429, scope 404) are normal JSON error responses.
    A `: keep-alive` comment line is sent every 15 s.
    """

    event: Literal[
        "meta", "status", "delta", "citations", "chart", "recommendations", "done", "error"
    ]
    data: (
        AiStreamMeta
        | AiStreamStatus
        | AiStreamDelta
        | list[AiCitation]
        | ChartSpec
        | list[AiRecommendation]
        | AiAnswer
        | AiStreamError
    )


# ---- status, insights -------------------------------------------------------------------------


class AiStatusRead(ApiModel):
    """Whether to show the assistant (AC73) and remaining quota."""

    project_id: uuid.UUID
    enabled: bool = Field(description="ai_enabled with transfer approval (AI-14).")
    available: bool = Field(description="Provider configured and reachable (AI-18).")
    reason_code: str | None = Field(description="AI_DISABLED | AI_UNAVAILABLE | null.")
    can_ask: bool = Field(description="Capability 40 on this project.")
    can_generate_report: bool = Field(description="Capability 41 generate.")
    questions_used_today: int
    questions_limit_per_day: int
    reports_used_this_month: int
    reports_limit_per_month: int
    default_model: str
    deep_model: str
    suggested_questions_en: list[str]
    suggested_questions_ar: list[str]


class Insight(ApiModel):
    id: str
    kind: InsightKind
    source: InsightSource = Field(description="rules = computed by the backend; ai = narrative.")
    severity: Severity
    metric: KpiMetric | None
    title_en: str
    title_ar: str
    text_en: str
    text_ar: str
    citations: list[AiCitation]
    chart: ChartSpec | None


class InsightsResponse(ApiModel):
    """Cached per project × filters × data snapshot (cost control). When the provider is
    unavailable, rule-based insights are still returned and `ai_available` is false."""

    project_id: uuid.UUID
    generated_at: datetime
    snapshot_hash: str
    ai_available: bool
    cached: bool
    items: list[Insight]


# ---- monthly report ---------------------------------------------------------------------------


class MonthlyReportCreate(StrictInput):
    """AI-19 draft (rate limit AI-17: 10 per project per month)."""

    project_id: uuid.UUID
    month: str = Field(pattern=MONTH, examples=["2026-09"], description="A complete month.")


class ReportSectionRead(ApiModel):
    section: MonthlyReportSection
    order: int = Field(ge=1, le=13)
    title_en: str
    title_ar: str
    narrative_en: str | None = Field(description="Model-written text (sections 2, 10, 11 …).")
    narrative_ar: str | None
    tables: list[ChartTable] = Field(description="Rendered by the backend from T1-T13 outputs.")
    charts: list[ChartSpec]
    citations: list[AiCitation]


class MonthlyReportRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    month: str
    status: MonthlyReportStatus
    status_label_en: str = Field(examples=["DRAFT — AI-assisted"])
    status_label_ar: str
    model: str | None
    error_code: str | None = Field(description="Set when status = failed.")
    sections: list[ReportSectionRead]
    data_hash: str | None = Field(description="Snapshot hash of the figures (AI-20).")
    revised_since_publication: bool = Field(
        description="Published report whose figures were restated later (AI-20, AC77)."
    )
    created_by: UserRef
    created_at: datetime
    generated_at: datetime | None
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    published_by: UserRef | None
    published_at: datetime | None
    ai_label_en: str = AI_LABEL_EN
    ai_label_ar: str = AI_LABEL_AR


class MonthlyReportSummary(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    month: str
    status: MonthlyReportStatus
    revised_since_publication: bool
    created_by: UserRef
    created_at: datetime
    published_at: datetime | None


class MonthlyReportPage(Page[MonthlyReportSummary]):
    pass


class ReportNarrativeEdit(StrictInput):
    section: MonthlyReportSection
    narrative_en: str | None = Field(default=None, max_length=8000)
    narrative_ar: str | None = Field(default=None, max_length=8000)


class MonthlyReportUpdate(StrictInput):
    """Edit narratives while draft/reviewed (tables are never editable)."""

    sections: list[ReportNarrativeEdit] = Field(min_length=1)


class MonthlyReportTransition(StrictInput):
    """AI-20: draft → reviewed (HSE Officer/Manager); reviewed → published (HSE Manager,
    freezes the snapshot); reviewed → draft (return, comment)."""

    to_status: MonthlyReportStatus
    comment: str | None = Field(default=None, max_length=1000)


# ---- logs (AI-16) ----------------------------------------------------------------------------


class AiToolCallLog(ApiModel):
    name: AiTool
    params: dict[str, Any]
    result_hash: str
    narrowed: bool = Field(description="Parameters were narrowed to the caller's scope.")


class AiLogEntry(ApiModel):
    id: uuid.UUID
    created_at: datetime
    user: UserRef
    project_code: str | None
    kind: Literal["ask", "insights", "monthly_report"]
    question_masked: str | None
    tool_calls: list[AiToolCallLog]
    answer_excerpt: str | None
    grounding: GroundingResult
    grounding_failures: list[str]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    error_code: str | None


class AiLogPage(Page[AiLogEntry]):
    pass
