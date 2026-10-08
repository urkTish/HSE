"""Monthly HSE report (spec 1-dashboard AI-19, AI-20). Tables are rendered by the backend from
the KPI engine for the whole project (as of the month end); the deep-analysis model writes the
narrative sections only, in EN and AR, checked by the number-grounding rule (AI-2)."""

import hashlib
import json
import re
import time
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.ai import grounding
from app.ai.assistant import ai_disabled_error, rate_limited, tool_call_logs, write_log
from app.ai.client import AiUnavailable
from app.ai.masking import redact
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.hse_enums import (
    RECORDABLE,
    BreakdownDimension,
    BreakdownMeasure,
    ChartId,
    GroundingResult,
    InvestigationLevel,
    KpiMetric,
    MonthlyReportSection,
    MonthlyReportStatus,
)
from app.db.session import get_sessionmaker
from app.hse_jobs import project_scope
from app.kpi import charts, fmt, present, service, views
from app.kpi.catalogue import CATALOGUE
from app.kpi.periods import add_months, fmt_month, month_end, month_key, month_start
from app.kpi.scope import Scope
from app.models import (
    Incident,
    InjuryCase,
    Investigation,
    MonthlyReport,
    Project,
    User,
)
from app.schemas.ai import (
    MonthlyReportCreate,
    MonthlyReportPage,
    MonthlyReportRead,
    MonthlyReportSummary,
    MonthlyReportTransition,
    MonthlyReportUpdate,
    ReportSectionRead,
)
from app.schemas.kpi import ChartSpec, ChartTable, ChartTableColumn
from app.services import audit, hse_settings, projects
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, project_today
from app.services.permissions import Principal, forbidden_error

S = MonthlyReportSection
ST = MonthlyReportStatus
TITLES: dict[MonthlyReportSection, tuple[str, str]] = {
    S.cover: ("Cover", "الغلاف"),
    S.executive_summary: ("Executive summary", "الملخص التنفيذي"),
    S.kpi_table: ("KPI table", "جدول مؤشرات الأداء"),
    S.manpower_exposure: ("Manpower & exposure", "القوى العاملة والتعرض"),
    S.lagging_indicators: ("Lagging indicators", "المؤشرات المتأخرة"),
    S.leading_indicators: ("Leading indicators", "المؤشرات الاستباقية"),
    S.contractor_performance: ("Contractor performance", "أداء المقاولين"),
    S.investigations_root_causes: (
        "Investigations & root-cause themes",
        "التحقيقات والأسباب الجذرية",
    ),
    S.corrective_actions: ("Corrective actions", "الإجراءات التصحيحية"),
    S.trends_insights: ("Trends & insights", "الاتجاهات والرؤى"),
    S.recommendations: ("Recommendations & focus areas", "التوصيات ومجالات التركيز"),
    S.data_quality: ("Data-quality notes and restatements", "ملاحظات جودة البيانات والتعديلات"),
    S.appendix_definitions: ("Appendix: definitions and formulas", "ملحق: التعريفات والمعادلات"),
}
NARRATIVE = [S.executive_summary, S.trends_insights, S.recommendations]
STATUS_LABELS = {
    ST.generating: ("GENERATING — AI-assisted", "قيد الإنشاء — بمساعدة الذكاء الاصطناعي"),
    ST.draft: ("DRAFT — AI-assisted", "مسودة — بمساعدة الذكاء الاصطناعي"),
    ST.reviewed: ("REVIEWED — AI-assisted", "تمت المراجعة — بمساعدة الذكاء الاصطناعي"),
    ST.published: ("PUBLISHED — AI-assisted", "منشور — بمساعدة الذكاء الاصطناعي"),
    ST.failed: ("FAILED", "فشل"),
}
UNVERIFIED_EN = "The narrative could not be verified against the figures; see the tables."
UNVERIFIED_AR = "تعذّر التحقق من النص مقابل الأرقام؛ راجع الجداول."
LEADING = [
    KpiMetric.K30,
    KpiMetric.K31,
    KpiMetric.K32,
    KpiMetric.K34,
    KpiMetric.K35,
    KpiMetric.K36,
    KpiMetric.K37,
    KpiMetric.K39,
    KpiMetric.K41,
    KpiMetric.K42,
]
CA_METRICS = [KpiMetric.K40, KpiMetric.K41, KpiMetric.K42, KpiMetric.K42b, KpiMetric.K43]


def _col(key: str, en: str, ar: str, numeric: bool = True) -> ChartTableColumn:
    return ChartTableColumn(key=key, label_en=en, label_ar=ar, numeric=numeric)


def _metric_table(sc: Scope, metrics: list[KpiMetric]) -> ChartTable:
    rows = []
    for v in service.metric_list(sc, metrics):
        prev = next((c for c in v.comparisons if c.kind.value == "previous"), None)
        rows.append(
            {
                "metric": f"{v.short_label_en} ({v.metric.value})",
                "value": v.display,
                "previous": prev.display if prev else "",
                "delta": prev.abs_delta_display if prev else "",
                "unit": v.unit_en,
            }
        )
    return ChartTable(
        columns=[
            _col("metric", "Metric", "المؤشر", False),
            _col("value", "Month", "الشهر"),
            _col("previous", "Previous", "السابق"),
            _col("delta", "Δ", "الفرق"),
            _col("unit", "Unit", "الوحدة", False),
        ],
        rows=rows,
    )


def _kpi_table(sc: Scope) -> ChartTable:
    t = service.comparison_table(sc, None)
    rows = []
    for r in t.rows:
        d = {x.kind.value: x.abs_delta_display for x in r.deltas}
        rows.append(
            {
                "metric": f"{r.label_en} ({r.metric.value})",
                **{k: c.display for k, c in r.cells.items()},
                "delta_previous": d.get("previous", ""),
                "delta_sply": d.get("sply", ""),
            }
        )
    cols = [_col("metric", "Metric", "المؤشر", False)] + [
        _col(c.key, c.label_en, c.label_ar) for c in t.columns
    ]
    cols += [
        _col("delta_previous", "Δ previous", "الفرق عن السابق"),
        _col("delta_sply", "Δ SPLY", "الفرق عن العام الماضي"),
    ]
    return ChartTable(columns=cols, rows=rows)


def _manpower(sc: Scope) -> list[ChartTable]:
    rows = []
    for e in service.league_engagements(sc):
        eng = service.league_engine(sc, e, False)
        a = eng.aggregate(sc.window)
        k03 = eng.result(KpiMetric.K03, a)
        k04 = eng.result(KpiMetric.K04, a)
        rows.append(
            {
                "contractor": e.code,
                "tier": str(e.tier),
                "man_hours": fmt.number(a.mh, 0),
                "avg_headcount": present.display(CATALOGUE[KpiMetric.K03], k03.value),
                "peak_headcount": present.display(CATALOGUE[KpiMetric.K04], k04.value),
            }
        )
    by_contractor = ChartTable(
        columns=[
            _col("contractor", "Contractor", "المقاول", False),
            _col("tier", "Tier", "المستوى"),
            _col("man_hours", "Man-hours", "ساعات العمل"),
            _col("avg_headcount", "Avg headcount", "متوسط العدد"),
            _col("peak_headcount", "Peak headcount", "أعلى عدد"),
        ],
        rows=rows,
    )
    return [
        by_contractor,
        _metric_table(
            sc, [KpiMetric.K01, KpiMetric.K02, KpiMetric.K03, KpiMetric.K04, KpiMetric.K45]
        ),
    ]


def _cases_list(db: Session, sc: Scope, project: Project) -> ChartTable:
    w = sc.window
    incs = list(
        db.scalars(
            select(Incident).where(
                Incident.project_id == project.id,
                Incident.occurred_date >= w.start,
                Incident.occurred_date <= w.end,
            )
        )
    )
    counted = {e.id for e in sc.engine.events_in(w)}
    cases = {c.incident_id: c for c in sc.engine.cases_in(w)}
    names = [
        n for row in db.execute(select(User.full_name_en, User.full_name_ar)) for n in row if n
    ]
    names += [
        n
        for n in db.scalars(
            select(InjuryCase.person_name).where(InjuryCase.project_id == project.id)
        )
        if n
    ]
    refs = Refs(db)
    rows = []
    for i in sorted(incs, key=lambda x: x.occurred_at):
        if i.id not in counted:
            continue
        c = cases.get(i.id)
        recordable = c is not None and c.category in RECORDABLE
        if not (recordable or i.hipo):
            continue
        e = refs.eng(i.responsible_engagement_id)
        rows.append(
            {
                "ref": i.ref,
                "date": i.occurred_date.isoformat(),
                "contractor": e.short_code if e else "",
                "category": c.category.value if c else "",
                "mechanism": (c.mechanism or "") if c else "",
                "hipo": "HiPo" if i.hipo else "",
                "description": redact(i.title, names) or "",
            }
        )
    return ChartTable(
        columns=[
            _col("ref", "Ref", "المرجع", False),
            _col("date", "Date", "التاريخ", False),
            _col("contractor", "Contractor", "المقاول", False),
            _col("category", "Category", "الفئة", False),
            _col("mechanism", "Mechanism", "الآلية", False),
            _col("hipo", "HiPo", "عالي الخطورة", False),
            _col("description", "Description", "الوصف", False),
        ],
        rows=rows,
    )


def _pyramid(sc: Scope) -> ChartTable:
    pr = service.pyramid(sc)
    return ChartTable(
        columns=[
            _col("layer", "Layer", "المستوى", False),
            _col("count", "Count", "العدد"),
            _col("ratio", "Ratio to TRI", "النسبة إلى TRI"),
        ],
        rows=[
            {"layer": x.label_en, "count": str(x.count), "ratio": x.ratio_display}
            for x in pr.layers
        ],
    )


def _warnings(sc: Scope) -> ChartTable:
    res = views.leading_indicators(sc, 1)
    return ChartTable(
        columns=[
            _col("code", "Warning", "التحذير", False),
            _col("month", "Month", "الشهر", False),
            _col("contractor", "Contractor tree", "المقاول", False),
            _col("message", "Message", "الرسالة", False),
        ],
        rows=[
            {
                "code": w.code.value,
                "month": w.month,
                "contractor": w.engagement.short_code if w.engagement else "Project",
                "message": w.message_en,
            }
            for w in res.warnings
        ],
    )


def _investigations(db: Session, sc: Scope, project: Project) -> list[ChartTable]:
    w = sc.window
    rows = db.execute(
        select(Investigation.level, func.count())
        .join(Incident, Incident.id == Investigation.incident_id)
        .where(
            Incident.project_id == project.id,
            Incident.occurred_date >= w.start,
            Incident.occurred_date <= w.end,
        )
        .group_by(Investigation.level)
    ).all()
    counts = dict(rows)
    levels = ChartTable(
        columns=[
            _col("level", "Level", "المستوى", False),
            _col("count", "Investigations", "العدد"),
        ],
        rows=[{"level": lv.value, "count": str(counts.get(lv, 0))} for lv in InvestigationLevel]
        + [{"level": "Overdue", "count": str(service.investigations_overdue(db, sc))}],
    )
    bd = views.breakdown(
        db, sc, BreakdownMeasure.events_by_type, BreakdownDimension.root_cause_code, 10
    )
    causes = ChartTable(
        columns=[
            _col("code", "Root cause", "السبب الجذري", False),
            _col("count", "Events", "الأحداث"),
        ],
        rows=[{"code": r.label_en, "count": r.count_display} for r in bd.rows],
    )
    return [levels, causes]


def _data_quality(db: Session, sc: Scope) -> ChartTable:
    dq = service.data_quality(db, sc)
    rows = [
        {"item": "Data completeness (K-45)", "value": dq.completeness.display},
        {"item": "Missing engagement-days", "value": str(dq.context.missing_engagement_days)},
        {"item": "Provisional cases", "value": str(dq.provisional_cases)},
        {"item": "Late reports", "value": str(dq.late_reports)},
        {"item": "Investigations overdue", "value": str(dq.investigations_overdue)},
        {"item": "Restated months", "value": ", ".join(dq.restated_months) or "none"},
    ]
    return ChartTable(
        columns=[_col("item", "Item", "البند", False), _col("value", "Value", "القيمة")],
        rows=rows,
    )


def _appendix(sc: Scope) -> ChartTable:
    b = service.context(sc).bases
    rows = [
        {"metric": "Bases", "formula": f"LTIFR {b.ltifr_label_en}; other rates {b.rate_label_en}"}
    ]
    for m in service.TABLE_METRICS:
        d = CATALOGUE[m]
        rows.append({"metric": f"{d.short_en} ({m.value})", "formula": d.formula_en})
    return ChartTable(
        columns=[
            _col("metric", "Metric", "المؤشر", False),
            _col("formula", "Definition", "التعريف", False),
        ],
        rows=rows,
    )


def render(
    db: Session, project: Project, month: date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Section skeletons with backend tables (no narrative) and a compact data digest for the
    model. Whole project, as of the month end."""
    sc = project_scope(db, project, month_end(month))
    ctx = service.context(sc)
    lti = service.lti_free_read(sc)
    tables: dict[MonthlyReportSection, list[ChartTable]] = {
        S.cover: [
            ChartTable(
                columns=[
                    _col("item", "Item", "البند", False),
                    _col("value", "Value", "القيمة", False),
                ],
                rows=[
                    {"item": "Project", "value": f"{project.code} · {project.name_en}"},
                    {"item": "Month", "value": fmt_month(month)[0]},
                    {
                        "item": "Bases",
                        "value": f"LTIFR {ctx.bases.ltifr_label_en}; other rates "
                        f"{ctx.bases.rate_label_en}",
                    },
                ],
            )
        ],
        S.executive_summary: [
            _metric_table(
                sc,
                [
                    KpiMetric.K01,
                    KpiMetric.K05,
                    KpiMetric.K06,
                    KpiMetric.K10,
                    KpiMetric.K20,
                    KpiMetric.K21,
                    KpiMetric.K13,
                    KpiMetric.K44,
                ],
            ),
            ChartTable(
                columns=[
                    _col("item", "LTI-free", "بدون إصابة مضيعة للوقت", False),
                    _col("value", "Value", "القيمة"),
                ],
                rows=[
                    {"item": "Days", "value": lti.days_display},
                    {"item": "Man-hours", "value": lti.man_hours_display},
                    {"item": "Since", "value": lti.label_en},
                ],
            ),
        ],
        S.kpi_table: [_kpi_table(sc)],
        S.manpower_exposure: _manpower(sc),
        S.lagging_indicators: [_pyramid(sc), _cases_list(db, sc, project)],
        S.leading_indicators: [_metric_table(sc, LEADING), _warnings(sc)],
        S.contractor_performance: [charts.league_table(sc)],
        S.investigations_root_causes: _investigations(db, sc, project),
        S.corrective_actions: [_metric_table(sc, CA_METRICS)],
        S.trends_insights: [],
        S.recommendations: [],
        S.data_quality: [_data_quality(db, sc)],
        S.appendix_definitions: [_appendix(sc)],
    }
    # 1-dashboard v1.3 AI-19 (4-third-party-cert §11.2): certification K-72…K-81 (aggregates
    # only) with the leading indicators once Phase 4 is enabled on the project
    from app.kpi import cert_views  # noqa: PLC0415
    from app.services.cert import dashboard_items as cert_items  # noqa: PLC0415

    if cert_items.enabled(db, project.id):
        cert_views.cert_engine(sc)
        tables[S.leading_indicators].append(_metric_table(sc, list(cert_views.CERT_METRICS)))
    trend_charts: list[ChartSpec] = [charts.chart(db, sc, cid) for cid in (ChartId.C1,)]
    sections = []
    for order, sec in enumerate(S, start=1):
        en, ar = TITLES[sec]
        sections.append(
            {
                "section": sec.value,
                "order": order,
                "title_en": en,
                "title_ar": ar,
                "narrative_en": None,
                "narrative_ar": None,
                "tables": [t.model_dump(mode="json") for t in tables[sec]],
                "charts": [c.model_dump(mode="json") for c in trend_charts]
                if sec == S.trends_insights
                else [],
                "citations": [],
            }
        )
    trend = service.trend_series(sc, KpiMetric.K21)
    digest = {
        "project": project.code,
        "month": fmt_month(month)[0],
        "tables": {s["section"]: s["tables"] for s in sections if s["tables"]},
        "trir_monthly": [{"month": p.label_en, "value": p.display} for p in trend.points],
        "trir_r12": [{"month": p.label_en, "value": p.display} for p in trend.r12],
        "trend_established": trend.trend_established,
    }
    return sections, digest


def figures_hash(sections: list[dict[str, Any]]) -> str:
    tables = [
        (s["section"], s["tables"], [c.get("series") for c in s.get("charts") or []])
        for s in sections
        if s["section"] != S.cover.value
    ]
    return hashlib.sha256(json.dumps(tables, sort_keys=True, default=str).encode()).hexdigest()


# ---- narrative -----------------------------------------------------------------------------------

REPORT_SYSTEM = """\
You write the narrative sections of a monthly construction HSE report. You receive the report's
figures as JSON. Rules: every number you write must appear in the JSON exactly as displayed; do
no arithmetic; state units and bases; describe a trend only if trend_established is true,
otherwise give values only; never name or identify persons; recommendations follow the hierarchy
of controls (elimination, substitution, engineering, administrative, ppe), include at least one
control at engineering level or higher, never PPE alone, and cite the table they rely on.
Return only a JSON object:
{"executive_summary": {"en": "...", "ar": "..."},
 "trends_insights": {"en": "...", "ar": "..."},
 "recommendations": {"en": "...", "ar": "..."}}
The executive summary is at most 150 words per language: headline numbers, LTI-free days and
hours, top 3 issues, top 3 positives. Recommendations include focus areas for next month.
"""


def _parse(text: str) -> dict[str, dict[str, str]]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return {}
    out: dict[str, dict[str, str]] = {}
    for sec in NARRATIVE:
        v = data.get(sec.value)
        if isinstance(v, dict):
            out[sec.value] = {"en": str(v.get("en") or ""), "ar": str(v.get("ar") or "")}
    return out


def _failures(parsed: dict[str, dict[str, str]], digest: dict[str, Any]) -> list[str]:
    if len(parsed) < len(NARRATIVE):
        return ["rule:narrative_missing"]
    out: list[str] = []
    for sec, v in parsed.items():
        for lang, txt in v.items():
            for f in grounding.check(txt, [digest]):
                out.append(f"{sec}.{lang}:{f}")
            if lang == "en":
                out += [f"rule:{i}" for i in grounding.language_issues(txt, [digest])]
    return out


def generate(report_id: uuid.UUID) -> None:
    """Background task: renders tables, asks the deep model for the narrative, verifies it."""
    with get_sessionmaker()() as db:
        r = db.get(MonthlyReport, report_id)
        if r is None:
            return
        project = db.get(Project, r.project_id)
        assert project is not None  # noqa: S101
        t0 = time.monotonic()
        model = get_settings().ai_model_deep
        result = GroundingResult.passed
        failures: list[str] = []
        tokens = [0, 0]
        try:
            sections, digest = render(db, project, r.month)
            c = llm.get_client()
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": json.dumps(digest, ensure_ascii=False, default=str)}
            ]
            parsed: dict[str, dict[str, str]] = {}
            for attempt in range(2):
                resp = c.create(
                    model=model, system=REPORT_SYSTEM, messages=messages, tools=[], max_tokens=8000
                )
                tokens[0] += resp.input_tokens
                tokens[1] += resp.output_tokens
                model = resp.model or model
                parsed = _parse(resp.text)
                fails = _failures(parsed, digest)
                if not fails:
                    result = (
                        GroundingResult.passed
                        if attempt == 0
                        else GroundingResult.passed_after_retry
                    )
                    break
                failures += fails
                messages += [
                    {"role": "assistant", "content": resp.text or "{}"},
                    {
                        "role": "user",
                        "content": "Verification failed: "
                        + ", ".join(fails[:30])
                        + ". Return the full JSON again using only numbers present in the data.",
                    },
                ]
            else:
                result = GroundingResult.failed
            for s in sections:
                if s["section"] in parsed and result != GroundingResult.failed:
                    s["narrative_en"] = parsed[s["section"]]["en"]
                    s["narrative_ar"] = parsed[s["section"]]["ar"]
                elif s["section"] in {x.value for x in NARRATIVE}:
                    s["narrative_en"], s["narrative_ar"] = UNVERIFIED_EN, UNVERIFIED_AR
            r.sections = sections
            r.data_hash = figures_hash(sections)
            r.status = ST.draft
            r.model = model
            r.generated_at = now()
        except AiUnavailable as e:
            r.status = ST.failed
            r.error_code = ErrorCode.AI_UNAVAILABLE.value
            failures.append(f"unavailable:{e.reason}")
            result = GroundingResult.not_applicable
        write_log(
            db,
            user_id=r.created_by_user_id,
            project_id=r.project_id,
            kind="monthly_report",
            question_masked=f"monthly report {month_key(r.month)}",
            tool_calls=tool_call_logs([]),
            answer_excerpt=None,
            grounding=result,
            grounding_failures=failures[:50],
            model=model,
            input_tokens=tokens[0] or None,
            output_tokens=tokens[1] or None,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error_code=r.error_code,
        )
        db.commit()


# ---- CRUD and workflow ---------------------------------------------------------------------------


def _month(value: str) -> date:
    y, m = (int(x) for x in value.split("-"))
    return date(y, m, 1)


def _can_see_all(p: Principal, pid: uuid.UUID) -> bool:
    return p.grant(pid, Capability.monthly_report_generate) is not None or (
        p.grant(pid, Capability.monthly_report_review) is not None
    )


def create(db: Session, p: Principal, body: MonthlyReportCreate) -> MonthlyReport:
    project = projects.get_visible(db, p, body.project_id)
    p.require(project.id, Capability.monthly_report_generate)
    if not hse_settings.get(db, project.id).ai_enabled:
        raise ai_disabled_error()
    if not llm.available():
        raise llm.unavailable_error()
    month = _month(body.month)
    if month >= month_start(project_today(project)):
        raise validation_error("month", "Choose a complete month.")
    start = project.start_date
    if start and month < month_start(start):
        raise validation_error("month", "The month is before the project start.")
    first = month_start(project_today(project))
    used = db.scalar(
        select(func.count())
        .select_from(MonthlyReport)
        .where(MonthlyReport.project_id == project.id, MonthlyReport.created_at >= first)
    )
    limit = get_settings().ai_reports_per_project_month
    if (used or 0) >= limit:
        nxt = add_months(first, 1)
        raise rate_limited(
            (nxt - project_today(project)).days * 86400, f"{limit} reports per month"
        )
    r = MonthlyReport(
        id=uuid.uuid4(),
        project_id=project.id,
        month=month,
        status=ST.generating,
        sections=[],
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.monthly_report,
        entity_id=r.id,
        project_id=project.id,
        details={"month": body.month},
    )
    return r


def _get(db: Session, p: Principal, report_id: uuid.UUID) -> MonthlyReport:
    r = db.get(MonthlyReport, report_id)
    if r is None or not p.can_see_project(r.project_id):
        raise not_found("Monthly report")
    if _can_see_all(p, r.project_id):
        return r
    if r.status == ST.published and p.grant(r.project_id, Capability.monthly_report_view):
        return r
    raise not_found("Monthly report")


def revised(db: Session, r: MonthlyReport) -> bool:
    if r.status != ST.published or not r.data_hash:
        return False
    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    sections, _ = render(db, project, r.month)
    return figures_hash(sections) != r.data_hash


def to_read(db: Session, r: MonthlyReport) -> MonthlyReportRead:
    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    refs = Refs(db).load(
        users=[r.created_by_user_id, r.reviewed_by_user_id, r.published_by_user_id]
    )
    en, ar = STATUS_LABELS[r.status]
    unknown = refs.user(r.created_by_user_id)
    assert unknown is not None  # noqa: S101
    return MonthlyReportRead(
        id=r.id,
        project_id=r.project_id,
        project_code=project.code,
        month=month_key(r.month),
        status=r.status,
        status_label_en=en,
        status_label_ar=ar,
        model=r.model,
        error_code=r.error_code,
        sections=[ReportSectionRead.model_validate(s) for s in r.sections],
        data_hash=r.data_hash,
        revised_since_publication=revised(db, r),
        created_by=unknown,
        created_at=r.created_at,
        generated_at=r.generated_at,
        reviewed_by=refs.user(r.reviewed_by_user_id),
        reviewed_at=r.reviewed_at,
        published_by=refs.user(r.published_by_user_id),
        published_at=r.published_at,
    )


def read(db: Session, p: Principal, report_id: uuid.UUID) -> MonthlyReportRead:
    return to_read(db, _get(db, p, report_id))


def list_page(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, page_size: int
) -> MonthlyReportPage:
    project = projects.get_visible(db, p, project_id)
    stmt = select(MonthlyReport).where(MonthlyReport.project_id == project.id)
    if not _can_see_all(p, project.id):
        if p.grant(project.id, Capability.monthly_report_view) is None:
            raise forbidden_error()
        stmt = stmt.where(MonthlyReport.status == ST.published)
    rows, total = paginate(
        db,
        stmt.order_by(MonthlyReport.month.desc(), MonthlyReport.created_at.desc()),
        page,
        page_size,
    )
    refs = Refs(db).load(users=[r.created_by_user_id for r in rows])
    items = []
    for r in rows:
        u = refs.user(r.created_by_user_id)
        assert u is not None  # noqa: S101
        items.append(
            MonthlyReportSummary(
                id=r.id,
                project_id=r.project_id,
                month=month_key(r.month),
                status=r.status,
                revised_since_publication=revised(db, r),
                created_by=u,
                created_at=r.created_at,
                published_at=r.published_at,
            )
        )
    return MonthlyReportPage(items=items, total=total, page=page, page_size=page_size)


def update(
    db: Session, p: Principal, report_id: uuid.UUID, body: MonthlyReportUpdate
) -> MonthlyReportRead:
    r = _get(db, p, report_id)
    p.require(r.project_id, Capability.monthly_report_generate)
    if r.status not in (ST.draft, ST.reviewed):
        raise invalid_transition("Monthly report", r.status, "edited")
    sections = [dict(s) for s in r.sections]
    for e in body.sections:
        for s in sections:
            if s["section"] == e.section.value:
                if e.narrative_en is not None:
                    s["narrative_en"] = e.narrative_en
                if e.narrative_ar is not None:
                    s["narrative_ar"] = e.narrative_ar
    r.sections = sections
    audit.record(
        db,
        AuditAction.update,
        p.actor(r.project_id),
        entity_type=EntityType.monthly_report,
        entity_id=r.id,
        project_id=r.project_id,
        details={"sections": [e.section.value for e in body.sections]},
    )
    db.flush()
    return to_read(db, r)


def transition(
    db: Session, p: Principal, report_id: uuid.UUID, body: MonthlyReportTransition
) -> MonthlyReportRead:
    r = _get(db, p, report_id)
    p.ensure_writer()
    to = body.to_status
    frm = r.status
    if frm == ST.draft and to == ST.reviewed:
        p.require(r.project_id, Capability.monthly_report_review)
        r.reviewed_by_user_id, r.reviewed_at = p.user.id, now()
    elif frm == ST.reviewed and to == ST.published:
        p.require(r.project_id, Capability.monthly_report_publish)
        project = db.get(Project, r.project_id)
        assert project is not None  # noqa: S101
        sections, _ = render(db, project, r.month)
        narr = {s["section"]: (s.get("narrative_en"), s.get("narrative_ar")) for s in r.sections}
        for s in sections:  # freeze current figures with the reviewed narrative
            s["narrative_en"], s["narrative_ar"] = narr.get(s["section"], (None, None))
        r.sections = sections
        r.data_hash = figures_hash(sections)
        r.published_by_user_id, r.published_at = p.user.id, now()
    elif frm == ST.reviewed and to == ST.draft:
        p.require(r.project_id, Capability.monthly_report_review)
        r.reviewed_by_user_id = r.reviewed_at = None
    else:
        raise invalid_transition("Monthly report", frm, to)
    r.status = to
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(r.project_id),
        entity_type=EntityType.monthly_report,
        entity_id=r.id,
        project_id=r.project_id,
        before={"status": frm.value},
        after={"status": to.value},
        details={"comment": body.comment} if body.comment else None,
    )
    db.flush()
    return to_read(db, r)
