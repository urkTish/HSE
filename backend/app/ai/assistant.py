"""POST /ai/ask (spec 1-dashboard §5.9): permission and AI-14 checks, AI-15 masking, AI-17 rate
limit, snapshot cache, the tool loop, AI-2 grounding with one regeneration, AI-7 data notes,
AI-3 Sources block, AI-11 recommendation checks and AI-16 logging."""

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.ai import grounding, prompts
from app.ai import tools as ai_tools
from app.ai.client import AiUnavailable, LlmClient, LlmResponse
from app.ai.masking import mask_prompt
from app.api.kpi_params import KpiQuery
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import Capability, Language
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.hse_enums import AiPromptWarning, AiTool, ControlLevel, GroundingResult
from app.db.session import get_sessionmaker
from app.hse_jobs import project_scope
from app.kpi import scope as kscope
from app.kpi import service
from app.kpi.periods import Window, add_months, month_start
from app.models import AiAnswerRecord, AiLog, Project
from app.schemas.ai import (
    AiAnswer,
    AiAskRequest,
    AiCitation,
    AiRecommendation,
    AiStreamStatus,
)
from app.schemas.dashboard import DashboardFilters
from app.schemas.kpi import ChartTable, ChartTableColumn
from app.services import hse_settings, projects
from app.services import incidents as inc_svc
from app.services.hse_common import project_today
from app.services.permissions import Principal, forbidden_error

HIERARCHY = list(ControlLevel)
HIGHER = {ControlLevel.elimination, ControlLevel.substitution, ControlLevel.engineering}
REC_BLOCK = re.compile(r"```recommendations\s*(.*?)```", re.S)
FALLBACK_EN = (
    "I could not produce a verified answer. The figures returned by the platform are shown "
    "in the table below."
)
FALLBACK_AR = "تعذّر إنتاج إجابة موثّقة. الأرقام التي أعادتها المنصة معروضة في الجدول أدناه."


# ---- checks --------------------------------------------------------------------------------------


def ai_disabled_error() -> ApiError:
    return ApiError(
        403,
        ErrorCode.AI_DISABLED,
        "The AI assistant is not enabled for this project (client transfer approval required).",
        "المساعد الذكي غير مفعّل لهذا المشروع (يلزم اعتماد العميل لنقل البيانات).",
    )


def rate_limited(retry_after: int, what: str) -> ApiError:
    return ApiError(
        429,
        ErrorCode.AI_RATE_LIMITED,
        f"AI limit reached ({what}). Try again later.",
        "تم بلوغ حد الاستخدام للمساعد الذكي.",
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def day_start_utc(project: Project) -> datetime:
    tz = inc_svc.tz_of(project)
    local = now().astimezone(tz)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def questions_used_today(db: Session, user_id: uuid.UUID, project: Project) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AiLog)
            .where(
                AiLog.user_id == user_id,
                AiLog.kind == "ask",
                AiLog.cached.is_(False),
                AiLog.created_at >= day_start_utc(project),
            )
        )
        or 0
    )


def require_enabled(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, Capability.ai_ask) is None:
        raise forbidden_error("Asking the AI assistant needs capability 40.")
    if not hse_settings.get(db, project.id).ai_enabled:
        raise ai_disabled_error()
    return project


# ---- query and scope -----------------------------------------------------------------------------


def default_query(project: Project, f: DashboardFilters | None, as_of: Any) -> KpiQuery | None:
    if f is None or (f.project_id and f.project_id != project.id):
        return None
    return KpiQuery(
        project_ids=[project.id],
        all_projects=False,
        site_ids=list(f.site_ids),
        zone_ids=list(f.zone_ids),
        zone_type=f.zone_type,
        engagement_ids=list(f.engagement_ids),
        include_subcontractors=f.include_subcontractors,
        tiers=list(f.tiers),
        period=f.period,
        anchor=None,
        start=f.start,
        end=f.end,
        as_of=as_of,
        compare=list(f.compare),
    )


def snapshot_for(db: Session, p: Principal, project: Project, q: KpiQuery | None) -> str:
    as_of = project_today(project)
    sc = kscope.build(db, p, q) if q is not None else project_scope(db, project, as_of)
    w = sc.window
    span = Window(add_months(month_start(w.end), -24), w.end)
    return service.snapshot(sc, span)


# ---- the loop ------------------------------------------------------------------------------------


@dataclass
class LoopResult:
    text: str
    responses: list[LlmResponse] = field(default_factory=list)
    model: str = ""

    @property
    def input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.responses)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.responses)


def tool_loop(
    c: LlmClient,
    ctx: ai_tools.ToolContext,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    statuses: list[AiStreamStatus],
    tools: list[dict[str, Any]] | None = None,
) -> LoopResult:
    res = LoopResult(text="", model=model)
    rounds = get_settings().ai_max_tool_rounds
    for _ in range(rounds + 1):
        r = c.create(
            model=model,
            system=system,
            messages=messages,
            tools=ai_tools.TOOL_DEFS if tools is None else tools,
            max_tokens=4096,
        )
        res.responses.append(r)
        res.model = r.model or model
        uses = r.tool_uses
        messages.append({"role": "assistant", "content": r.assistant_content()})
        if not uses or r.stop_reason not in ("tool_use", "pause_turn"):
            res.text = r.text
            return res
        results = []
        for u in uses:
            try:
                tool = AiTool(u.name)
            except ValueError:
                tool = None
            statuses.append(
                AiStreamStatus(
                    stage="tool",
                    tool=tool,
                    message_en=f"Querying {u.name}",
                    message_ar=f"استعلام {u.name}",
                )
            )
            out = ai_tools.run(ctx, u.name, u.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": u.id,
                    "content": json.dumps(out, ensure_ascii=False, default=str),
                }
            )
        messages.append({"role": "user", "content": results})
    res.text = res.responses[-1].text if res.responses else ""
    return res


# ---- post-processing -----------------------------------------------------------------------------


def parse_recommendations(
    text: str, citation_ids: set[str]
) -> tuple[str, list[AiRecommendation], list[str]]:
    """Extracts the ```recommendations``` JSON block; returns (text without it, ordered
    recommendations, AI-11 issues)."""
    m = REC_BLOCK.search(text)
    if not m:
        return text, [], []
    body = text[: m.start()] + text[m.end() :]
    issues: list[str] = []
    try:
        raw = json.loads(m.group(1))
        assert isinstance(raw, list)  # noqa: S101
    except (json.JSONDecodeError, AssertionError):
        return body.strip(), [], ["recommendations_unreadable"]
    recs: list[AiRecommendation] = []
    for i, item in enumerate(raw):
        try:
            level = ControlLevel(str(item.get("control_level")))
            cites = [str(x) for x in item.get("citation_ids") or item.get("sources") or []]
            recs.append(
                AiRecommendation(
                    id=f"R{i + 1}",
                    control_level=level,
                    title=str(item.get("title") or "")[:200],
                    text=str(item.get("text") or "")[:2000],
                    citation_ids=[x for x in cites if x in citation_ids],
                )
            )
        except (ValueError, AttributeError, ValidationError):
            issues.append("recommendation_invalid")
    recs.sort(key=lambda r: HIERARCHY.index(r.control_level))
    recs = [r.model_copy(update={"id": f"R{i + 1}"}) for i, r in enumerate(recs)]
    if recs and not any(r.control_level in HIGHER for r in recs):
        issues.append("no_control_above_administrative")
    if any(not r.citation_ids for r in recs):
        issues.append("recommendation_without_source")
    return body.strip(), recs, issues


def _result_contexts(runs: list[ai_tools.ToolRun]) -> list[dict[str, Any]]:
    out = []
    for r in runs:
        c = r.result.get("context")
        if isinstance(c, dict):
            out.append(c)
    return out


def data_notes(runs: list[ai_tools.ToolRun], lang: Language) -> list[str]:
    """AI-7 caveats derived from the tool results (not left to the model)."""
    notes: list[str] = []
    seen: set[str] = set()

    def add(key: str, en: str, ar: str) -> None:
        if key not in seen:
            seen.add(key)
            notes.append(ar if lang == Language.ar else en)

    for c in _result_contexts(runs):
        scope, period = c.get("scope"), c.get("period")
        if c.get("no_man_hours"):
            add(
                f"nomh:{scope}:{period}",
                f"No man-hours recorded for {scope}, {period}; rates cannot be calculated.",
                f"لا توجد ساعات عمل مسجلة لـ {scope}، {period}؛ لا يمكن حساب المعدلات.",
            )
        if c.get("completeness_below_threshold"):
            add(
                f"comp:{scope}:{period}",
                f"Data completeness for {scope}, {period} is {c.get('data_completeness')} "
                f"(below {c.get('completeness_threshold_pct')} %); rates may be overstated.",
                f"اكتمال البيانات لـ {scope}، {period} هو {c.get('data_completeness')}؛ "
                "قد تكون المعدلات أعلى من الواقع.",
            )
        if c.get("provisional_cases"):
            add(
                f"prov:{scope}:{period}",
                f"{c.get('provisional_cases')} provisional case classification(s) are included.",
                f"يشمل {c.get('provisional_cases')} تصنيف حالة مبدئي.",
            )
        if c.get("restated_months"):
            months = ", ".join(c["restated_months"])
            add(f"rest:{months}", f"Restated months: {months}.", f"أشهر معدلة: {months}.")
    for r in runs:
        for k in r.result.get("kpis") or []:
            by = k.get("one_case_changes_rate_by")
            if by and "LOW_EXPOSURE" in (k.get("warnings") or []):
                add(
                    f"low:{k['metric']}",
                    f"{k['name']}: low exposure — one case changes the rate by {by}.",
                    f"{k['name']}: تعرّض منخفض — حالة واحدة تغيّر المعدل بمقدار {by}.",
                )
    if any(r.narrowed for r in runs):
        add(
            "narrowed",
            "Some requested data is outside your access and was not used.",
            "بعض البيانات المطلوبة خارج نطاق صلاحياتك ولم تُستخدم.",
        )
    return notes


def used_citations(text: str, citations: list[AiCitation]) -> list[AiCitation]:
    marked = set(re.findall(r"\b([SR]\d+)\b", text))
    used = []
    for c in citations:
        v = c.value_display or ""
        shown = bool(v) and v != "—" and v in text
        if c.id in marked or shown or any(ref in text for ref in c.refs):
            used.append(c)
    return used or citations[:12]


def sources_block(citations: list[AiCitation], lang: Language) -> str:
    if not citations:
        return ""
    head = "**المصادر**" if lang == Language.ar else "**Sources**"
    lines = [f"- [{c.id}] {c.text_en}" for c in citations]
    return "\n\n" + head + "\n" + "\n".join(lines)


def fallback_table(citations: list[AiCitation], runs: list[ai_tools.ToolRun]) -> ChartTable:
    rows: list[dict[str, str]] = []
    for r in runs:
        for k in r.result.get("kpis") or []:
            ctx = (r.result.get("context") or {}) if isinstance(r.result, dict) else {}
            rows.append(
                {
                    "source": f"{k.get('name')} ({r.name})",
                    "value": str(k.get("value")),
                    "period": str(ctx.get("period") or ""),
                    "scope": str(ctx.get("scope") or ""),
                }
            )
    if not rows:
        rows = [
            {
                "source": c.tool.value,
                "value": c.value_display or "",
                "period": c.period_label_en or "",
                "scope": c.scope_label_en or "",
            }
            for c in citations
        ]
    cols = [
        ChartTableColumn(key="source", label_en="Source", label_ar="المصدر", numeric=False),
        ChartTableColumn(key="value", label_en="Value", label_ar="القيمة", numeric=True),
        ChartTableColumn(key="period", label_en="Period", label_ar="الفترة", numeric=False),
        ChartTableColumn(key="scope", label_en="Scope", label_ar="النطاق", numeric=False),
    ]
    return ChartTable(columns=cols, rows=rows)


def verify(
    text: str, ctx: ai_tools.ToolContext, question: str
) -> tuple[str, list[AiRecommendation], list[str]]:
    """Returns (display text, recommendations, failures)."""
    body, recs, rec_issues = parse_recommendations(text, {c.id for c in ctx.citations})
    outputs = [r.result for r in ctx.runs]
    rec_text = " ".join(f"{r.title} {r.text}" for r in recs)
    failures = grounding.check(body + " " + rec_text, outputs, question)
    issues = grounding.language_issues(body, outputs) + rec_issues
    return body, recs, failures + [f"rule:{i}" for i in issues]


# ---- logging -------------------------------------------------------------------------------------


def tool_call_logs(runs: list[ai_tools.ToolRun]) -> list[dict[str, Any]]:
    out = []
    for r in runs:
        try:
            name = AiTool(r.name).value
        except ValueError:
            continue
        out.append(
            {"name": name, "params": r.params, "result_hash": r.result_hash, "narrowed": r.narrowed}
        )
    return out


def write_log(db: Session | None, **fields: Any) -> None:
    """In the request session, or (db = None, after an error) in its own transaction."""
    entry = AiLog(**fields)
    if db is not None:
        db.add(entry)
        db.flush()
        return
    with get_sessionmaker()() as own:
        own.add(entry)
        own.commit()


# ---- ask -----------------------------------------------------------------------------------------


@dataclass
class AskOutcome:
    answer: AiAnswer
    statuses: list[AiStreamStatus]


class AskFailed(Exception):  # noqa: N818
    def __init__(
        self,
        answer_id: uuid.UUID,
        conversation_id: uuid.UUID,
        model: str,
        masked: str,
        warnings: list[AiPromptWarning],
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.answer_id = answer_id
        self.conversation_id = conversation_id
        self.model = model
        self.masked = masked
        self.warnings = warnings
        self.reason = reason


def preflight(db: Session, p: Principal, body: AiAskRequest) -> Project:
    """Errors returned as JSON before any stream starts (AC73, AI-17, AI-18)."""
    project = require_enabled(db, p, body.project_id)
    if not llm.available():
        raise llm.unavailable_error()
    limit = get_settings().ai_questions_per_user_day
    if questions_used_today(db, p.user.id, project) >= limit:
        nxt = day_start_utc(project) + timedelta(days=1)
        raise rate_limited(int((nxt - now()).total_seconds()), f"{limit} questions per day")
    return project


def history(db: Session, p: Principal, conversation_id: uuid.UUID | None) -> list[dict[str, Any]]:
    if conversation_id is None:
        return []
    rows = db.scalars(
        select(AiAnswerRecord)
        .where(
            AiAnswerRecord.conversation_id == conversation_id,
            AiAnswerRecord.user_id == p.user.id,
        )
        .order_by(AiAnswerRecord.created_at)
        .limit(10)
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({"role": "user", "content": r.payload.get("question_masked", "")})
        txt = str(r.payload.get("text", "")).split("\n\n**Sources**")[0]
        out.append({"role": "assistant", "content": txt or "(no answer)"})
    return out


def ask(db: Session, p: Principal, body: AiAskRequest) -> AskOutcome:
    t0 = time.monotonic()
    project = preflight(db, p, body)
    s = get_settings()
    lang = body.language or p.user.preferred_language or Language.en
    masked, warns = mask_prompt(body.question)
    model = s.ai_model_deep if body.deep_analysis else s.ai_model_default
    as_of = project_today(project)
    dq = default_query(project, body.filters, as_of)
    snap = snapshot_for(db, p, project, dq)
    filt = body.filters.model_dump(mode="json") if body.filters else None
    key_src = [
        str(p.user.id),
        str(project.id),
        masked,
        lang.value,
        filt,
        body.deep_analysis,
        snap,
        model,
    ]
    cache_key = hashlib.sha256(json.dumps(key_src, default=str).encode()).hexdigest()
    answer_id = uuid.uuid4()
    conversation_id = body.conversation_id or uuid.uuid4()
    statuses: list[AiStreamStatus] = []

    if body.conversation_id is None:
        since = now() - timedelta(minutes=s.ai_insights_cache_minutes)
        hit = db.scalar(
            select(AiAnswerRecord)
            .where(AiAnswerRecord.cache_key == cache_key, AiAnswerRecord.created_at >= since)
            .order_by(AiAnswerRecord.created_at.desc())
            .limit(1)
        )
        if hit is not None:
            cached = AiAnswer.model_validate(hit.payload)
            write_log(
                db,
                user_id=p.user.id,
                project_id=project.id,
                kind="ask",
                question_masked=masked,
                tool_calls=[],
                answer_excerpt=cached.text[:500],
                grounding=cached.grounding,
                grounding_failures=[],
                model=cached.model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                cached=True,
            )
            return AskOutcome(cached, [])

    ctx = ai_tools.ToolContext(db=db, p=p, project=project, as_of=as_of, default_query=dq)
    system = prompts.system_prompt(project, lang, as_of, p)
    messages = [*history(db, p, body.conversation_id), {"role": "user", "content": masked}]
    statuses.append(
        AiStreamStatus(stage="thinking", message_en="Thinking", message_ar="جارٍ التفكير")
    )
    responses: list[LlmResponse] = []
    try:
        c = llm.get_client()
        res = tool_loop(c, ctx, model, system, messages, statuses)
        responses += res.responses
        statuses.append(
            AiStreamStatus(
                stage="grounding", message_en="Checking numbers", message_ar="التحقق من الأرقام"
            )
        )
        text, recs, failures = verify(res.text, ctx, masked)
        all_failures = list(failures)
        result = GroundingResult.passed
        if failures:
            statuses.append(
                AiStreamStatus(
                    stage="regenerating",
                    message_en="Regenerating a verified answer",
                    message_ar="إعادة توليد إجابة موثّقة",
                )
            )
            messages.append({"role": "user", "content": prompts.regenerate(failures)})
            res2 = tool_loop(c, ctx, model, system, messages, statuses)
            responses += res2.responses
            text, recs, failures = verify(res2.text, ctx, masked)
            all_failures += [f for f in failures if f not in all_failures]
            result = GroundingResult.passed_after_retry if not failures else GroundingResult.failed
        elif not grounding.numbers_in(text):
            result = GroundingResult.not_applicable if not ctx.runs else GroundingResult.passed
    except AiUnavailable as e:
        write_log(
            None,
            user_id=p.user.id,
            project_id=project.id,
            kind="ask",
            question_masked=masked,
            tool_calls=tool_call_logs(ctx.runs),
            answer_excerpt=None,
            grounding=GroundingResult.not_applicable,
            grounding_failures=[],
            model=model,
            input_tokens=sum(r.input_tokens for r in responses) or None,
            output_tokens=sum(r.output_tokens for r in responses) or None,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error_code=ErrorCode.AI_UNAVAILABLE.value,
        )
        raise AskFailed(answer_id, conversation_id, model, masked, warns, e.reason) from e

    fallback = None
    if result == GroundingResult.failed:
        text = FALLBACK_AR if lang == Language.ar else FALLBACK_EN
        recs = []
        fallback = fallback_table(ctx.citations, ctx.runs)
        cites = ctx.citations
    else:
        cites = used_citations(text, ctx.citations)
        for r in recs:
            for cid in r.citation_ids:
                if cid not in {x.id for x in cites}:
                    cites += [x for x in ctx.citations if x.id == cid]
    notes = data_notes(ctx.runs, lang)
    if notes and result != GroundingResult.failed:
        head = "**ملاحظات البيانات**" if lang == Language.ar else "**Data notes**"
        text = text.rstrip() + "\n\n" + head + "\n" + "\n".join(f"- {n}" for n in notes)
    if recs:
        label = (
            "مُولَّد آلياً — يُراجع من شخص مختص"
            if lang == Language.ar
            else ("AI-generated — to be reviewed by a competent person")
        )
        text = text.rstrip() + "\n\n_" + label + "_"
    text = text.rstrip() + sources_block(cites, lang)
    model_used = responses[-1].model if responses else model
    answer = AiAnswer(
        id=answer_id,
        conversation_id=conversation_id,
        project_id=project.id,
        language=lang,
        question_masked=masked,
        prompt_warnings=warns,
        text=text,
        citations=cites,
        recommendations=recs,
        chart=ctx.chart if result != GroundingResult.failed else None,
        grounding=result,
        fallback_table=fallback,
        model=model_used,
        created_at=now(),
    )
    db.add(
        AiAnswerRecord(
            id=answer_id,
            conversation_id=conversation_id,
            user_id=p.user.id,
            project_id=project.id,
            cache_key=cache_key if result != GroundingResult.failed else "",
            payload=answer.model_dump(mode="json"),
            grounding=result,
        )
    )
    write_log(
        db,
        user_id=p.user.id,
        project_id=project.id,
        kind="ask",
        question_masked=masked,
        tool_calls=tool_call_logs(ctx.runs),
        answer_excerpt=text[:500],
        grounding=result,
        grounding_failures=all_failures,
        model=model_used,
        input_tokens=sum(r.input_tokens for r in responses),
        output_tokens=sum(r.output_tokens for r in responses),
        latency_ms=int((time.monotonic() - t0) * 1000),
    )
    statuses.append(AiStreamStatus(stage="writing", message_en="Writing", message_ar="جارٍ الكتابة"))
    return AskOutcome(answer, statuses)


def get_answer(db: Session, p: Principal, answer_id: uuid.UUID) -> AiAnswer:
    rec = db.get(AiAnswerRecord, answer_id)
    if rec is None or rec.user_id != p.user.id:
        raise not_found("Answer")
    return AiAnswer.model_validate(rec.payload)
