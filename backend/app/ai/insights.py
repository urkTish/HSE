"""GET /ai/insights: rule-based items computed by the backend (leading warnings §6.9, data
quality, comparison deltas returned by the KPI engine) plus optional AI narrative items, cached
per data snapshot (cost control)."""

import hashlib
import json
import time
from datetime import timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.ai import grounding
from app.ai.assistant import write_log
from app.ai.client import AiUnavailable
from app.api.kpi_params import KpiQuery
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import Capability
from app.core.errors import validation_error
from app.core.hse_enums import (
    AiTool,
    DeltaDirection,
    GroundingResult,
    InsightKind,
    InsightSource,
    KpiMetric,
    Severity,
)
from app.kpi import scope as kscope
from app.kpi import service, views
from app.models import AiInsightCache
from app.schemas.ai import AiCitation, Insight, InsightsResponse
from app.services import hse_settings
from app.services.permissions import Principal

WATCH = [KpiMetric.K21, KpiMetric.K20, KpiMetric.K10, KpiMetric.K41, KpiMetric.K42, KpiMetric.K31]
NARRATIVE_SYSTEM = """\
You turn backend-computed HSE dashboard insights into at most two short narrative insights.
Use only numbers that appear in the JSON, exactly as displayed; no arithmetic; no names; do not
claim trends unless the JSON says trend_established is true. Return only JSON:
[{"title_en": "...", "title_ar": "...", "text_en": "...", "text_ar": "..."}]
"""


def _cite(
    sc: kscope.Scope,
    tool: AiTool,
    text: str,
    metric: KpiMetric | None = None,
    value: str | None = None,
) -> AiCitation:
    return AiCitation(
        id="S1",
        tool=tool,
        metric=metric,
        value_display=value,
        period_label_en=sc.period.label_en,
        scope_label_en=service.scope_label(sc),
        base_label_en=None,
        refs=[],
        text_en=text,
        text_ar=text,
    )


def rule_items(sc: kscope.Scope) -> list[Insight]:
    items: list[Insight] = []
    ctx = service.context(sc)
    period = ctx.period.label_en
    scope_label = service.scope_label(sc)
    n = 0

    def nid() -> str:
        nonlocal n
        n += 1
        return f"I{n}"

    for v in service.metric_list(sc, WATCH):
        prev = next((c for c in v.comparisons if c.kind.value == "previous"), None)
        if prev is None or prev.value is None or v.value is None or prev.abs_delta in (None, "0"):
            continue
        if prev.direction not in (DeltaDirection.better, DeltaDirection.worse):
            continue
        worse = prev.direction == DeltaDirection.worse
        word_en = "worse than" if worse else "better than"
        word_ar = "أسوأ من" if worse else "أفضل من"
        text = (
            f"{v.short_label_en} {v.display} in {period} vs {prev.display} in {prev.label_en} "
            f"({prev.abs_delta_display}, {prev.pct_delta_display})."
        )
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.anomaly if worse else InsightKind.positive,
                source=InsightSource.rules,
                severity=Severity.warning if worse else Severity.info,
                metric=v.metric,
                title_en=f"{v.short_label_en} {word_en} the previous period",
                title_ar=f"{v.short_label_ar} {word_ar} الفترة السابقة",
                text_en=text,
                text_ar=text,
                citations=[
                    _cite(
                        sc,
                        AiTool.get_kpis,
                        f"{v.short_label_en} {v.display} — get_kpis, {scope_label}, {period}",
                        v.metric,
                        v.display,
                    )
                ],
                chart=None,
            )
        )
    for w in views.leading_indicators(sc, 3).warnings:
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.warning,
                source=InsightSource.rules,
                severity=Severity.warning,
                metric=None,
                title_en=f"Leading warning {w.code.value} ({w.month})",
                title_ar=f"تحذير استباقي {w.code.value} ({w.month})",
                text_en=w.message_en,
                text_ar=w.message_ar,
                citations=[
                    _cite(
                        sc,
                        AiTool.get_leading_warnings,
                        f"{w.code.value} {w.month} — get_leading_warnings, {scope_label}",
                    )
                ],
                chart=None,
            )
        )
    if ctx.completeness_below_threshold:
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.data_quality,
                source=InsightSource.rules,
                severity=Severity.warning,
                metric=KpiMetric.K45,
                title_en="Man-hours data incomplete",
                title_ar="بيانات ساعات العمل غير مكتملة",
                text_en=f"Data completeness is {ctx.data_completeness_display} with "
                f"{ctx.missing_engagement_days} missing engagement-days; rates may be overstated.",
                text_ar=f"اكتمال البيانات {ctx.data_completeness_display} مع "
                f"{ctx.missing_engagement_days} يوم-مقاول مفقود؛ قد تكون المعدلات أعلى من الواقع.",
                citations=[
                    _cite(
                        sc,
                        AiTool.get_data_quality,
                        f"K-45 {ctx.data_completeness_display}"
                        f" — get_data_quality, {scope_label}, {period}",
                        KpiMetric.K45,
                        ctx.data_completeness_display,
                    )
                ],
                chart=None,
            )
        )
    if ctx.provisional_cases_count:
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.data_quality,
                source=InsightSource.rules,
                severity=Severity.info,
                metric=None,
                title_en="Provisional classifications",
                title_ar="تصنيفات مبدئية",
                text_en=f"{ctx.provisional_cases_count} case classification(s) are provisional.",
                text_ar=f"{ctx.provisional_cases_count} تصنيف حالة مبدئي.",
                citations=[
                    _cite(
                        sc,
                        AiTool.get_data_quality,
                        f"Provisional cases — get_data_quality, {scope_label}, {period}",
                    )
                ],
                chart=None,
            )
        )
    if ctx.restated_months:
        months = ", ".join(ctx.restated_months)
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.data_quality,
                source=InsightSource.rules,
                severity=Severity.info,
                metric=None,
                title_en="Figures restated after month lock",
                title_ar="أرقام معدلة بعد قفل الشهر",
                text_en=f"Restated months: {months}.",
                text_ar=f"أشهر معدلة: {months}.",
                citations=[
                    _cite(
                        sc,
                        AiTool.get_data_quality,
                        f"Restated {months} — get_data_quality, {scope_label}",
                    )
                ],
                chart=None,
            )
        )
    lf = service.lti_free_read(sc)
    if lf.days >= 100:
        items.append(
            Insight(
                id=nid(),
                kind=InsightKind.positive,
                source=InsightSource.rules,
                severity=Severity.info,
                metric=KpiMetric.K28,
                title_en=f"{lf.days_display} LTI-free days",
                title_ar=f"{lf.days_display} يوماً بدون إصابة مضيعة للوقت",
                text_en=f"{lf.days_display} days and {lf.man_hours_display} man-hours "
                f"{lf.label_en}.",
                text_ar=f"{lf.days_display} يوماً و{lf.man_hours_display} ساعة عمل {lf.label_ar}.",
                citations=[
                    _cite(
                        sc,
                        AiTool.get_lti_free,
                        f"LTI-free {lf.days_display} days — get_lti_free, {scope_label}",
                        KpiMetric.K28,
                        lf.days_display,
                    )
                ],
                chart=None,
            )
        )
    return items


def _narrative(db: Session, p: Principal, sc: kscope.Scope, items: list[Insight]) -> list[Insight]:
    """AI narrative items; dropped when they fail the grounding check."""
    payload = [i.model_dump(mode="json", include={"title_en", "text_en", "metric"}) for i in items]
    if not payload:
        return []
    model = get_settings().ai_model_default
    t0 = time.monotonic()
    r = llm.get_client().create(
        model=model,
        system=NARRATIVE_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        tools=[],
        max_tokens=1500,
    )
    out: list[Insight] = []
    failures: list[str] = []
    try:
        raw = json.loads(r.text[r.text.find("[") : r.text.rfind("]") + 1] or "[]")
    except json.JSONDecodeError:
        raw = []
    for k, item in enumerate(raw[:2] if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        text = " ".join(
            str(item.get(f, "")) for f in ("title_en", "text_en", "title_ar", "text_ar")
        )
        bad = grounding.check(text, payload)
        if bad:
            failures += bad
            continue
        out.append(
            Insight(
                id=f"A{k + 1}",
                kind=InsightKind.trend,
                source=InsightSource.ai,
                severity=Severity.info,
                metric=None,
                title_en=str(item.get("title_en", ""))[:200],
                title_ar=str(item.get("title_ar", ""))[:200],
                text_en=str(item.get("text_en", ""))[:1000],
                text_ar=str(item.get("text_ar", ""))[:1000],
                citations=[c for i in items for c in i.citations][:5],
                chart=None,
            )
        )
    write_log(
        db,
        user_id=p.user.id,
        project_id=sc.projects[0].id,
        kind="insights",
        question_masked=None,
        tool_calls=[],
        answer_excerpt=" | ".join(i.title_en for i in out)[:500] or None,
        grounding=GroundingResult.failed if failures and not out else GroundingResult.passed,
        grounding_failures=failures[:50],
        model=r.model or model,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )
    return out


def insights(db: Session, p: Principal, q: KpiQuery, refresh: bool) -> InsightsResponse:
    if len(q.project_ids) != 1 or q.all_projects:
        raise validation_error("project_id", "Insights need exactly one project.")
    sc = kscope.build(db, p, q)
    project = sc.projects[0]
    snap = service.snapshot(sc)
    enabled = (
        hse_settings.get(db, project.id).ai_enabled
        and p.grant(project.id, Capability.ai_ask) is not None
    )
    use_ai = enabled and llm.available()
    key = hashlib.sha256(f"insights-v1:{snap}:{use_ai}".encode()).hexdigest()
    ttl = timedelta(minutes=get_settings().ai_insights_cache_minutes)
    row = db.get(AiInsightCache, key)
    if row is not None and not refresh and row.created_at >= now() - ttl:
        data: dict[str, Any] = dict(row.payload)
        data["cached"] = True
        return InsightsResponse.model_validate(data)
    items = rule_items(sc)
    ai_ok = use_ai
    if use_ai:
        try:
            items += _narrative(db, p, sc, items)
        except AiUnavailable:
            ai_ok = False
    res = InsightsResponse(
        project_id=project.id,
        generated_at=now(),
        snapshot_hash=snap,
        ai_available=ai_ok,
        cached=False,
        items=items,
    )
    # upsert: the dashboard can ask twice at once (two tabs, a refetch), and both miss the cache
    payload = res.model_dump(mode="json")
    at = now()
    db.execute(
        pg_insert(AiInsightCache)
        .values(cache_key=key, project_id=project.id, payload=payload, created_at=at)
        .on_conflict_do_update(
            index_elements=[AiInsightCache.cache_key], set_={"payload": payload, "created_at": at}
        )
    )
    if row is not None:
        db.expire(row)
    return res
