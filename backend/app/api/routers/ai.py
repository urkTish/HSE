"""AI assistant (spec 1-dashboard §5.9): ask (SSE), insights, monthly report, status, logs."""

import json
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.ai import assistant, insights, reports
from app.ai import status as ai_status
from app.ai.client import unavailable_error
from app.api.deps import DB, CurrentUser, PageParams
from app.api.kpi_params import KpiParams
from app.core.errors import error_responses
from app.schemas.ai import (
    AiAnswer,
    AiAskRequest,
    AiLogPage,
    AiStatusRead,
    AiStreamDelta,
    AiStreamError,
    AiStreamEvent,
    AiStreamMeta,
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
def ai_ask(body: AiAskRequest, request: Request, user: CurrentUser, db: DB) -> Response:
    sse = "application/json" not in request.headers.get("accept", "")
    try:
        out = assistant.ask(db, user, body)
    except assistant.AskFailed as e:
        err = unavailable_error(e.reason)
        if not sse:
            raise err from e
        meta = AiStreamMeta(
            answer_id=e.answer_id,
            conversation_id=e.conversation_id,
            model=e.model,
            prompt_warnings=e.warnings,
            question_masked=e.masked,
        )
        error = AiStreamError(code=err.code.value, message=err.message, message_ar=err.message_ar)
        frames = [_frame("meta", meta), _frame("error", error)]
        return StreamingResponse(iter(frames), media_type="text/event-stream")
    a = out.answer
    if not sse:
        return JSONResponse(a.model_dump(mode="json"))
    frames = [
        _frame(
            "meta",
            AiStreamMeta(
                answer_id=a.id,
                conversation_id=a.conversation_id,
                model=a.model,
                prompt_warnings=a.prompt_warnings,
                question_masked=a.question_masked,
            ),
        )
    ]
    frames += [_frame("status", s) for s in out.statuses]
    frames += [_frame("delta", AiStreamDelta(text=c)) for c in _chunks(a.text)]
    frames.append(_frame("citations", a.citations))
    if a.chart is not None:
        frames.append(_frame("chart", a.chart))
    if a.recommendations:
        frames.append(_frame("recommendations", a.recommendations))
    frames.append(_frame("done", a))
    return StreamingResponse(iter(frames), media_type="text/event-stream")


def _chunks(text: str, size: int = 400) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _frame(event: str, data: Any) -> str:
    ev = AiStreamEvent(event=event, data=data)
    payload = json.dumps(ev.model_dump(mode="json")["data"], ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get(
    "/ai/answers/{answer_id}",
    response_model=AiAnswer,
    summary="Get a stored answer of mine (e.g. to create a CA from a recommendation, CA-7)",
    responses=error_responses(401, 403, 404),
)
def get_ai_answer(answer_id: uuid.UUID, user: CurrentUser, db: DB) -> AiAnswer:
    return assistant.get_answer(db, user, answer_id)


@router.get(
    "/ai/status",
    response_model=AiStatusRead,
    summary="Is the assistant enabled/available for this project, and my remaining quota",
    responses=error_responses(401, 403, 404),
)
def get_ai_status(project_id: uuid.UUID, user: CurrentUser, db: DB) -> AiStatusRead:
    return ai_status.status(db, user, project_id)


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
    return insights.insights(db, user, q, refresh)


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
    body: MonthlyReportCreate, user: CurrentUser, db: DB, tasks: BackgroundTasks
) -> MonthlyReportRead:
    r = reports.create(db, user, body)
    out = reports.to_read(db, r)
    db.commit()
    tasks.add_task(reports.generate, r.id)
    return out


@router.get(
    "/projects/{project_id}/monthly-reports",
    response_model=MonthlyReportPage,
    summary="List monthly reports (viewers see published only)",
    responses=error_responses(401, 403, 404, 422),
)
def list_monthly_reports(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> MonthlyReportPage:
    return reports.list_page(db, user, project_id, pg.page, pg.page_size)


@router.get(
    "/monthly-reports/{report_id}",
    response_model=MonthlyReportRead,
    summary="Get a monthly report (published: frozen snapshot + revised flag, AI-20)",
    responses=error_responses(401, 403, 404),
)
def get_monthly_report(report_id: uuid.UUID, user: CurrentUser, db: DB) -> MonthlyReportRead:
    return reports.read(db, user, report_id)


@router.patch(
    "/monthly-reports/{report_id}",
    response_model=MonthlyReportRead,
    summary="Edit report narratives (draft/reviewed only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_monthly_report(
    report_id: uuid.UUID, body: MonthlyReportUpdate, user: CurrentUser, db: DB
) -> MonthlyReportRead:
    return reports.update(db, user, report_id, body)


@router.post(
    "/monthly-reports/{report_id}/transitions",
    response_model=MonthlyReportRead,
    summary="Review / publish / return a monthly report (AI-20)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_monthly_report(
    report_id: uuid.UUID, body: MonthlyReportTransition, user: CurrentUser, db: DB
) -> MonthlyReportRead:
    return reports.transition(db, user, report_id, body)


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
    return ai_status.logs(
        db, user, pg.page, pg.page_size, project_id, user_id, grounding_failed, date_from, date_to
    )
