"""AI assistant (spec 1-dashboard §5.9): ask (SSE), insights, monthly report, status, logs."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.kpi_params import KpiParams
from app.core.errors import error_responses, not_implemented
from app.schemas.ai import (
    AiAnswer,
    AiAskRequest,
    AiLogPage,
    AiStatusRead,
    InsightsResponse,
    MonthlyReportCreate,
    MonthlyReportPage,
    MonthlyReportRead,
    MonthlyReportTransition,
    MonthlyReportUpdate,
)

router = APIRouter(tags=["ai"])

ASK_DESCRIPTION = """
Answers strictly from tool results (KPI engine and read-only query services, executed with the
caller's identity and scope). Prompts are masked for IDs/emails/+966 mobiles before sending
(AI-15); no person names or medical data are ever sent to the model (AI-5).

**Response formats** (choose with `Accept`):

* `text/event-stream` (default): Server-Sent Events, one JSON `data:` per event, see schema
  `AiStreamEvent`. Sequence: `meta` → `status`* → `delta`* → `citations` → `chart`? →
  `recommendations`? → `done` (full `AiAnswer`). `error` ends the stream. Answer text is only
  streamed after the number-grounding check (AI-2) passed, so no unverified number is ever
  displayed.
* `application/json`: the final `AiAnswer` in one response.

Errors before the stream starts are JSON: 403 `AI_DISABLED` (ai_enabled false or no transfer
approval, AC73), 403 capability 40, 404 project out of scope, 429 `AI_RATE_LIMITED` (60
questions/user/day, `Retry-After`), 503 `AI_UNAVAILABLE` (no API key configured / provider
down).
"""

_ASK_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "model": AiAnswer,
        "description": "SSE stream (text/event-stream) or the final answer (application/json).",
        "content": {
            "text/event-stream": {"schema": {"$ref": "#/components/schemas/AiStreamEvent"}}
        },
    },
    **error_responses(401, 403, 404, 422, 429, 503),
}


@router.post(
    "/ai/ask",
    summary="Ask the HSE assistant (streamed)",
    description=ASK_DESCRIPTION,
    response_class=Response,
    responses=_ASK_RESPONSES,
)
def ai_ask(body: AiAskRequest, user: CurrentUser, db: DB) -> Response:
    raise not_implemented()


@router.get(
    "/ai/answers/{answer_id}",
    response_model=AiAnswer,
    summary="Get a stored answer of mine (e.g. to create a CA from a recommendation, CA-7)",
    responses=error_responses(401, 403, 404),
)
def get_ai_answer(answer_id: uuid.UUID, user: CurrentUser, db: DB) -> AiAnswer:
    raise not_implemented()


@router.get(
    "/ai/status",
    response_model=AiStatusRead,
    summary="Is the assistant enabled/available for this project, and my remaining quota",
    responses=error_responses(401, 403, 404),
)
def get_ai_status(project_id: uuid.UUID, user: CurrentUser, db: DB) -> AiStatusRead:
    raise not_implemented()


@router.get(
    "/ai/insights",
    response_model=InsightsResponse,
    summary="Cached auto-insights (trends, anomalies, warnings) for the dashboard filters",
    description="Uses the /kpi filters; exactly one project. Rule-based items (leading "
    "warnings, data quality, trend checks) are always returned; AI narrative items only when "
    "the assistant is enabled and available. Cached per data snapshot.",
    responses=error_responses(401, 403, 404, 422),
)
def get_ai_insights(
    user: CurrentUser,
    db: DB,
    q: KpiParams,
    refresh: Annotated[bool, Query(description="Bypass the cache (counts toward quota).")] = False,
) -> InsightsResponse:
    raise not_implemented()


@router.post(
    "/ai/monthly-report",
    response_model=MonthlyReportRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a monthly HSE report draft (capability 41; deep-analysis model)",
    description="Returns the report in status `generating`; poll GET /monthly-reports/{id} "
    "until `draft` (or `failed` with error_code). Tables are rendered by the backend from the "
    "KPI engine; the model writes narrative only, EN and AR (AI-19). 429 AI_RATE_LIMITED "
    "after 10 reports per project per month; 403 AI_DISABLED; 503 AI_UNAVAILABLE.",
    responses=error_responses(401, 403, 404, 409, 422, 429, 503),
)
def create_monthly_report(
    body: MonthlyReportCreate, user: CurrentUser, db: DB
) -> MonthlyReportRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/monthly-reports",
    response_model=MonthlyReportPage,
    summary="List monthly reports (viewers see published only)",
    responses=error_responses(401, 403, 404, 422),
)
def list_monthly_reports(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> MonthlyReportPage:
    raise not_implemented()


@router.get(
    "/monthly-reports/{report_id}",
    response_model=MonthlyReportRead,
    summary="Get a monthly report (published: frozen snapshot + revised flag, AI-20)",
    responses=error_responses(401, 403, 404),
)
def get_monthly_report(report_id: uuid.UUID, user: CurrentUser, db: DB) -> MonthlyReportRead:
    raise not_implemented()


@router.patch(
    "/monthly-reports/{report_id}",
    response_model=MonthlyReportRead,
    summary="Edit report narratives (draft/reviewed only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_monthly_report(
    report_id: uuid.UUID, body: MonthlyReportUpdate, user: CurrentUser, db: DB
) -> MonthlyReportRead:
    raise not_implemented()


@router.post(
    "/monthly-reports/{report_id}/transitions",
    response_model=MonthlyReportRead,
    summary="Review / publish / return a monthly report (AI-20)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_monthly_report(
    report_id: uuid.UUID, body: MonthlyReportTransition, user: CurrentUser, db: DB
) -> MonthlyReportRead:
    raise not_implemented()


@router.get(
    "/ai/logs",
    response_model=AiLogPage,
    summary="AI prompt/response log without sensitive data (HSE Manager, AI-16)",
    responses=error_responses(401, 403, 422),
)
def list_ai_logs(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    grounding_failed: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AiLogPage:
    raise not_implemented()
