"""GET /ai/status and GET /ai/logs (AI-16, visible to the HSE Manager)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.ai.assistant import questions_used_today
from app.core.config import get_settings
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.hse_enums import AiTool, GroundingResult
from app.models import AiLog, MonthlyReport, Project
from app.schemas.ai import AiLogEntry, AiLogPage, AiStatusRead, AiToolCallLog
from app.services import hse_settings, projects
from app.services.common import paginate
from app.services.hse_common import Refs, project_today
from app.services.permissions import Principal, forbidden_error

SUGGESTED_EN = [
    "What was our TRIR last month and how does it compare with the previous month?",
    "Which contractors have overdue corrective actions?",
    "Show the injury cases by mechanism this year.",
    "Is there a difference in incident rates during the heat season?",
    "Summarise data-quality issues for this month.",
]
SUGGESTED_AR = [
    "ما معدل TRIR في الشهر الماضي وكيف يقارن بالشهر السابق؟",
    "أي المقاولين لديهم إجراءات تصحيحية متأخرة؟",
    "اعرض حالات الإصابة حسب آلية الإصابة لهذا العام.",
    "هل يوجد فرق في معدلات الحوادث خلال موسم الحرارة؟",
    "لخّص مشكلات جودة البيانات لهذا الشهر.",
]


def status(db: Session, p: Principal, project_id: uuid.UUID) -> AiStatusRead:
    project = projects.get_visible(db, p, project_id)
    s = get_settings()
    enabled = hse_settings.get(db, project.id).ai_enabled
    available = llm.available()
    reason = None if enabled else ErrorCode.AI_DISABLED.value
    if reason is None and not available:
        reason = ErrorCode.AI_UNAVAILABLE.value
    first = project_today(project).replace(day=1)
    reports = db.scalar(
        select(func.count())
        .select_from(MonthlyReport)
        .where(
            MonthlyReport.project_id == project.id,
            MonthlyReport.created_at >= datetime.combine(first, time(0), UTC),
        )
    )
    return AiStatusRead(
        project_id=project.id,
        enabled=enabled,
        available=available,
        reason_code=reason,
        can_ask=p.grant(project.id, Capability.ai_ask) is not None,
        can_generate_report=p.grant(project.id, Capability.monthly_report_generate) is not None,
        questions_used_today=questions_used_today(db, p.user.id, project),
        questions_limit_per_day=s.ai_questions_per_user_day,
        reports_used_this_month=int(reports or 0),
        reports_limit_per_month=s.ai_reports_per_project_month,
        default_model=s.ai_model_default,
        deep_model=s.ai_model_deep,
        suggested_questions_en=SUGGESTED_EN,
        suggested_questions_ar=SUGGESTED_AR,
    )


def logs(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    project_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    grounding_failed: bool | None,
    date_from: date | None,
    date_to: date | None,
) -> AiLogPage:
    if not p.is_manager:
        raise forbidden_error("The AI log is visible to the HSE Manager.")
    stmt = select(AiLog)
    if project_id:
        stmt = stmt.where(AiLog.project_id == project_id)
    if user_id:
        stmt = stmt.where(AiLog.user_id == user_id)
    if grounding_failed is not None:
        failed = AiLog.grounding == GroundingResult.failed
        stmt = stmt.where(failed if grounding_failed else ~failed)
    if date_from:
        stmt = stmt.where(AiLog.created_at >= datetime.combine(date_from, time(0), UTC))
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time(0), UTC)
        stmt = stmt.where(AiLog.created_at < end)
    rows, total = paginate(db, stmt.order_by(AiLog.created_at.desc()), page, page_size)
    refs = Refs(db).load(users=[r.user_id for r in rows])
    codes = dict(db.execute(select(Project.id, Project.code)).all())
    items = []
    for r in rows:
        u = refs.user(r.user_id)
        assert u is not None  # noqa: S101
        calls = []
        for c in r.tool_calls or []:
            try:
                calls.append(
                    AiToolCallLog(
                        name=AiTool(c["name"]),
                        params=c.get("params") or {},
                        result_hash=c.get("result_hash", ""),
                        narrowed=bool(c.get("narrowed")),
                    )
                )
            except (KeyError, ValueError):
                continue
        items.append(
            AiLogEntry(
                id=r.id,
                created_at=r.created_at,
                user=u,
                project_code=codes.get(r.project_id) if r.project_id else None,
                kind=r.kind,
                question_masked=r.question_masked,
                tool_calls=calls,
                answer_excerpt=r.answer_excerpt,
                grounding=r.grounding,
                grounding_failures=list(r.grounding_failures or []),
                model=r.model,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                latency_ms=r.latency_ms,
                error_code=r.error_code,
            )
        )
    return AiLogPage(items=items, total=total, page=page, page_size=page_size)
