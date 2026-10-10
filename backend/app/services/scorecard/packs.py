"""Report packs (spec 6g §3.6, §4.4, RP-1…RP-10, SC-2, SC-3): the monthly client report (MCR),
the contractor scorecard pack (SCP), the performance summary (CPS), the OSHA 300-style log and the
heat season report. Every figure comes from a stored snapshot (RP-2); Issue freezes it, renders
the files (EN / AR PDF and XLSX) and distributes them; a re-issue is a new revision and the old
one is watermarked "SUPERSEDED BY Rev n"."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind, ProjectStatus
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.hse_enums import (
    RECORDABLE,
    AttachmentOwner,
    CaseCategory,
    KpiKind,
    KpiMetric,
    MonthlyReportStatus,
)
from app.core.scorecard_enums import (
    RpAction,
    RpFileKind,
    RpLanguages,
    RpStatus,
    RpType,
    ScCardStatus,
    ScModule,
    ScRemarkKind,
    ScScope,
    XpPurpose,
)
from app.kpi.cases import day_counts
from app.kpi.catalogue import CATALOGUE
from app.kpi.periods import Window
from app.models import (
    Contractor,
    InjuryCase,
    MonthlyReport,
    Project,
    ProjectEngagement,
    RpPack,
    ScCard,
    ScRemark,
    Site,
    User,
    Zone,
)
from app.schemas.scorecard import (
    RpFileRead,
    RpFileUrl,
    RpPackCreate,
    RpPackDetail,
    RpPackPage,
    RpPackRead,
    RpPackTransition,
    RpPackUpdate,
)
from app.services.permissions import Principal, deny, forbidden_error
from app.services.scorecard import common as cm
from app.services.scorecard import inputs, labels, render

D = Decimal
C = cm.C
EMAIL_LIMIT = 20 * 1024 * 1024
OPEN = (RpStatus.draft, RpStatus.in_review)
CTYPE = {"pdf": "application/pdf",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}  # fmt: skip

# RP-1 (2): module sections in order (key, module, title EN / AR, KPIs)
MODULES: list[tuple[str, ScModule, str, str, list[str]]] = [
    ("access", ScModule.access, "Access", "الدخول والتصاريح",
     ["K-49", "K-53", "K-54", "K-57", "K-59"]),
    ("ptw", ScModule.ptw, "Permit to work", "تصاريح العمل",
     ["K-46", "K-46b", "K-61", "K-64", "K-66", "K-69"]),
    ("cert", ScModule.cert, "Certification", "الشهادات",
     ["K-72", "K-74", "K-76", "K-80", "K-81"]),
    ("training", ScModule.training, "Training", "التدريب",
     ["K-37", "K-82", "K-83", "K-84", "K-85", "K-86", "K-87", "K-88"]),
    ("medical", ScModule.medical, "Occupational health", "الصحة المهنية",
     ["K-89", "K-90", "K-93", "K-94"]),
    ("heat", ScModule.heat, "Heat stress", "الإجهاد الحراري",
     ["K-97", "K-98", "K-99", "K-100", "K-101", "K-102", "K-103"]),
    ("emergency", ScModule.emergency, "Emergency", "الطوارئ",
     ["K-104", "K-105", "K-106", "K-107", "K-108", "K-109"]),
    ("field", ScModule.field, "Field assurance", "ضمان الميدان",
     ["K-110", "K-111", "K-112", "K-113", "K-114", "K-115", "K-116", "K-117"]),
    ("env", ScModule.env, "Environmental", "البيئة",
     ["K-118", "K-119", "K-120", "K-121", "K-122", "K-123", "K-124", "K-125", "K-126"]),
    ("followup", ScModule.followup, "Incident follow-up", "متابعة الحوادث",
     ["K-127", "K-128", "K-129", "K-130", "K-131"]),
]  # fmt: skip
KPI_COLS = [("kpi", "KPI", "المؤشر"), ("name", "Name", "الاسم"), ("month", "Month", "الشهر"),
            ("previous", "Previous", "السابق"), ("ytd", "YTD", "منذ بداية السنة"),
            ("r12", "R12", "12 شهراً"), ("target", "Target", "المستهدف")]  # fmt: skip
KPI_BY_CODE = {m.value: m for m in KpiMetric}


# ---- numbering, hashing -------------------------------------------------------------------------


def doc_no(rt: RpType, code: str, eng: str | None, period_end: date) -> str:
    mid = f"-{eng}" if eng else ""
    tail = f"-{period_end.month:02d}" if rt in (RpType.MCR, RpType.SCP, RpType.CPS) else ""
    return f"{rt.value}-{code}{mid}-{period_end.year}{tail}"


def digest(x: Any) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


def _tbl(cols: list[tuple[str, str, str]], rows: list[dict[str, Any]], en: str = "",
         ar: str = "", sheet: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {"columns": [list(c) for c in cols], "rows": rows, "title_en": en, "title_ar": ar,
            "sheet": sheet}  # fmt: skip


def _sec(key: str, en: str, ar: str, tables: list[dict[str, Any]] | None = None,
         pen: list[str] | None = None, par: list[str] | None = None,
         watermark: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {
        "key": key,
        "title_en": en,
        "title_ar": ar,
        "tables": tables or [],
        "paragraphs_en": pen or [],
        "paragraphs_ar": par or [],
        "watermark": watermark,
    }


# ---- KPI rows from the engine (RP-2: the module KPI snapshot) -----------------------------------


def _val(ctx: inputs.Ctx, kpi: str, w: Window, as_of: date) -> str:
    m = KPI_BY_CODE.get(kpi)
    if m is None:
        return "—"
    try:
        r = inputs.engine(ctx, None, as_of).result(
            m, inputs.agg(ctx, inputs.engine(ctx, None, as_of), w)
        )
    except Exception:
        return "—"
    if r.value is None:
        return "—"
    dec = CATALOGUE[m].decimals if m in CATALOGUE else 1
    return str(cm.q(D(r.value), "1" if dec == 0 else "0." + "0" * (dec - 1) + "1"))


def kpi_rows(ctx: inputs.Ctx, kpis: list[str], month: date) -> list[dict[str, Any]]:
    end = cm.month_end(month)
    prev = cm.add_months(month, -1)
    rows = []
    for k in kpis:
        m = KPI_BY_CODE.get(k)
        if m is None:
            continue
        d = CATALOGUE.get(m)
        rate = d is not None and d.kind == KpiKind.rate
        rows.append({
            "kpi": k, "name": d.label_en if d else k,
            "month": _val(ctx, k, Window(month, end), end),
            "previous": _val(ctx, k, Window(prev, cm.month_end(prev)), cm.month_end(prev)),
            "ytd": _val(ctx, k, Window(month.replace(month=1), end), end),
            "r12": _val(ctx, k, Window(cm.add_months(month, -11), end), end) if rate else "—",
            "target": "—",
        })  # fmt: skip
    return rows


# ---- snapshots -----------------------------------------------------------------------------------


def _phase1(db: Session, project: Project, month: date) -> MonthlyReport | None:
    return db.scalars(select(MonthlyReport).where(
        MonthlyReport.project_id == project.id, MonthlyReport.month == month,
        MonthlyReport.status == MonthlyReportStatus.published,
    ).order_by(MonthlyReport.published_at.desc())).first()  # fmt: skip


def _p1_sections(r: MonthlyReport, sc_section: dict[str, Any] | None) -> list[dict[str, Any]]:
    """AI-19 sections 2–12 from the frozen Published snapshot; 7 replaced by the scorecards."""
    out = []
    for s in sorted(r.sections or [], key=lambda x: x.get("order", 0)):
        order = int(s.get("order", 0))
        if order < 2 or order > 12:
            continue
        if order == 7 and sc_section is not None:
            out.append(_section7(sc_section, f"p1:{s.get('section')}", s.get("title_en", ""),
                                 s.get("title_ar", "")))  # fmt: skip
            continue
        tables = []
        for t in s.get("tables") or []:
            cols = [(c["key"], c.get("label_en", c["key"]), c.get("label_ar", c["key"]))
                    for c in t.get("columns", [])]  # fmt: skip
            tables.append(_tbl(cols, t.get("rows", [])))
        out.append(_sec(f"p1:{s.get('section')}", s.get("title_en", ""), s.get("title_ar", ""),
                        tables, [s["narrative_en"]] if s.get("narrative_en") else [],
                        [s["narrative_ar"]] if s.get("narrative_ar") else []))  # fmt: skip
    return out


SUMMARY_COLS = ("rank", "engagement", "score", "grade")


def _section7(sc: dict[str, Any], key: str, en: str, ar: str) -> dict[str, Any]:
    """RP-1 (1): Phase 1 section 7 keeps its title and shows the scorecard summary (ranking);
    the full contractor scorecards section (3) follows the modules, so it is not listed twice."""
    rank = sc["tables"][0]
    cols = [c for c in rank["columns"] if c[0] in SUMMARY_COLS]
    rows = [{k: r.get(k) for k in SUMMARY_COLS} for r in rank["rows"]]
    return _sec(key, en or sc["title_en"], ar or sc["title_ar"],
                [_tbl([tuple(c) for c in cols], rows, rank["title_en"], rank["title_ar"])],
                watermark=sc.get("watermark"))  # fmt: skip


def scorecard_section(db: Session, project_id: uuid.UUID, month: date,
                      provisional: bool = False) -> dict[str, Any] | None:  # fmt: skip
    """RP-1 (3): ranking table, watch list and commendations (Final or Issued revisions)."""
    from app.services.scorecard import cards, watch  # noqa: PLC0415

    own = cards.current(db, project_id, month, ScScope.own)
    if not own:
        return None
    own.sort(key=lambda c: (c.rank is None, c.rank or 0, cm.eng_code(db, c.engagement_id)))
    rows = [{"rank": c.rank or "—", "engagement": cm.eng_code(db, c.engagement_id),
             "score": cm.d1(c.score), "grade": cards._grade_display(c),
             "caps": ", ".join(x["cap_code"] for x in c.caps_applied) or "—",
             "trend": c.trend_label.value if c.trend_label else "—",
             "coverage": cm.d1(c.coverage_pct), "status": c.status.value,
             "revision": c.revision} for c in own]  # fmt: skip
    entries = [watch.open_entry(db, c.engagement_id) for c in own]
    wl = [{"entry": w.entry_no, "engagement": cm.eng_code(db, w.engagement_id),
           "level": w.level.value} for w in entries if w is not None]  # fmt: skip
    com = [cm.eng_code(db, c.engagement_id) for c in own if c.commended]
    cols = [("rank", "Rank", "الترتيب"), ("engagement", "Contractor", "المقاول"),
            ("score", "Score", "النتيجة"), ("grade", "Grade", "التقدير"),
            ("caps", "Caps", "الحدود"), ("trend", "Trend", "الاتجاه"),
            ("coverage", "Coverage %", "التغطية %"), ("status", "Status", "الحالة"),
            ("revision", "Rev", "المراجعة")]  # fmt: skip
    wcols = [("entry", "Entry", "الإدراج"), ("engagement", "Contractor", "المقاول"),
             ("level", "Level", "المستوى")]  # fmt: skip
    return _sec("scorecards", "Contractor scorecards", "بطاقات أداء المقاولين",
                [_tbl(cols, rows, "Ranking", "الترتيب", "Scorecards"),
                 _tbl(wcols, wl, "Watch list", "قائمة المراقبة", "Watch list")],
                [f"Commended: {', '.join(com)}"] if com else [],
                [f"مقاولون متميزون: {', '.join(com)}"] if com else [],
                render.PROVISIONAL if provisional else None)  # fmt: skip


def _mcr(db: Session, project: Project, month: date, provisional: bool) -> dict[str, Any]:
    from app.services.env.common import is_airport  # noqa: PLC0415

    inputs.reset(db)
    ctx = inputs.context(db, project)
    c = cm.cfg(db, project.id)
    sc = scorecard_section(db, project.id, month, provisional)
    r = _phase1(db, project, month)
    sections: list[dict[str, Any]] = _p1_sections(r, sc) if r is not None else []
    sources: list[dict[str, Any]] = []
    if r is not None:
        sources.append({"kind": "phase1_report", "ref": str(r.id), "version": 0,
                        "hash": r.data_hash})  # fmt: skip
    not_live = []
    for key, mod, en, ar, kpis in MODULES:
        if not c.live(mod, month):
            not_live.append(en)
            continue
        if key == "access" and not is_airport(db, project.id):
            continue
        if key == "heat" and not inputs.in_heat_season(ctx, month):
            continue
        rows = kpi_rows(ctx, kpis, month)
        sections.append(_sec(f"module:{key}", en, ar, [_tbl(KPI_COLS, rows, en, ar, en)]))
        sources.append({"kind": "module", "ref": key, "version": 0, "hash": digest(rows)})
    if sc is not None:
        sections.append(sc)
        for card in _cards(db, project.id, month):
            sources.append({"kind": "scorecard", "ref": card.scorecard_no,
                            "version": card.revision, "hash": card.inputs_hash})  # fmt: skip
    defs = [{"kpi": k, "name": CATALOGUE[KPI_BY_CODE[k]].label_en,
             "formula": CATALOGUE[KPI_BY_CODE[k]].formula_en}
            for _k, _m, _e, _a, ks in MODULES for k in ks
            if k in KPI_BY_CODE and KPI_BY_CODE[k] in CATALOGUE]  # fmt: skip
    nl = [{"module": x} for x in not_live]
    sections.append(_sec("appendix", "Appendix: definitions, data quality, modules not live",
                         "ملحق: التعريفات وجودة البيانات والوحدات غير المفعلة",
                         [_tbl([("kpi", "KPI", "المؤشر"), ("name", "Name", "الاسم"),
                                ("formula", "Formula", "المعادلة")], defs, "Definitions",
                               "التعريفات", "Definitions"),
                          _tbl([("module", "Module not yet live", "وحدة غير مفعلة")], nl,
                               "Modules not live", "وحدات غير مفعلة", "Not live")]))  # fmt: skip
    st = project.settings
    return {"sections": sections, "sources": sources, "not_live": not_live,
            "bases": {"ltifr": st.ltifr_base_hours if st else 1_000_000,
                      "rate": st.rate_base_hours if st else 200_000}}  # fmt: skip


def _cards(db: Session, project_id: uuid.UUID, month: date) -> list[ScCard]:
    from app.services.scorecard import cards  # noqa: PLC0415

    return cards.current(db, project_id, month, None)


def _scp(db: Session, card: ScCard) -> dict[str, Any]:
    """RP-8: one engagement's card; no other contractor is named."""
    from app.services.scorecard import cards, watch  # noqa: PLC0415

    rd = cards.to_read(db, card)
    summary = [
        {"item": "Score", "value": rd.score_display}, {"item": "Grade", "value": rd.grade_display},
        {"item": "Coverage", "value": rd.coverage_display},
        {"item": "Credibility Z", "value": rd.credibility_z_display},
        {"item": "Rank", "value": f"{rd.ranking.rank} of {rd.ranking.rank_of}"
         if rd.ranking.rank else (rd.ranking.rank_status.value if rd.ranking.rank_status else "—")},
        {"item": "Project median", "value": rd.ranking.median_display},
        {"item": "Trend", "value": rd.trend_label.value if rd.trend_label else "—"},
        {"item": "Commended", "value": "yes" if rd.commended else "no"},
        {"item": "Watch-list level", "value": rd.watch_level.value if rd.watch_level else "—"},
        {"item": "Profile", "value": f"{rd.profile_code} v{rd.profile_version}"},
    ]  # fmt: skip
    pillars = [{"pillar": x.pillar_code.value, "weight": x.weight,
                "effective": x.effective_weight_display, "score": x.score_display}
               for x in rd.pillars]  # fmt: skip
    lines = [{"metric": x.metric_code, "name": labels.METRIC_LABELS[x.metric_code][0],
              "kpi": x.kpi_ref, "value": x.value_display, "points": x.points_display,
              "status": x.line_status.value, "weight": x.effective_weight_display}
             for x in rd.lines]  # fmt: skip
    caps = [{"cap": c.cap_code.value, "max": c.max_grade.value, "refs": ", ".join(c.refs)}
            for c in rd.caps_applied]  # fmt: skip
    trend = []
    for k in range(11, -1, -1):
        mm = cm.add_months(card.month, -k)
        x = db.scalar(select(ScCard).where(ScCard.engagement_id == card.engagement_id,
                                           ScCard.scope == card.scope, ScCard.month == mm,
                                           ScCard.status.in_(cards.CURRENT)))  # fmt: skip
        if x is not None:
            trend.append({"month": cm.mkey(mm), "score": cm.d1(x.score),
                          "grade": x.grade.value if x.grade else "—"})  # fmt: skip
    disputes = [{"target": r.target_code or "—", "reason": r.reason_code.value if r.reason_code
                 else "—", "status": r.status.value,
                 "resolution": r.resolution.value if r.resolution else "—"}
                for r in db.scalars(select(ScRemark).where(ScRemark.card_id == card.id,
                                                           ScRemark.kind == ScRemarkKind.dispute))
                ]  # fmt: skip
    w = watch.open_entry(db, card.engagement_id)
    two = [("item", "Item", "البند"), ("value", "Value", "القيمة")]
    return {"sections": [
        _sec("summary", f"Scorecard {card.scorecard_no} R{card.revision}",
             f"بطاقة الأداء {card.scorecard_no}", [_tbl(two, summary, sheet="Summary")]),
        _sec("pillars", "Pillars", "المحاور", [_tbl(
            [("pillar", "Pillar", "المحور"), ("weight", "Weight", "الوزن"),
             ("effective", "Effective weight", "الوزن الفعلي"), ("score", "Score", "النتيجة")],
            pillars, sheet="Pillars")]),
        _sec("lines", "Lines", "البنود", [_tbl(
            [("metric", "Metric", "المقياس"), ("name", "Name", "الاسم"), ("kpi", "KPI", "المؤشر"),
             ("value", "Value", "القيمة"), ("points", "Points", "النقاط"),
             ("status", "Status", "الحالة"), ("weight", "Eff. weight", "الوزن الفعلي")],
            lines, sheet="Lines")]),
        _sec("caps", "Caps", "الحدود", [_tbl([("cap", "Cap", "الحد"), ("max", "Max", "الأقصى"),
                                              ("refs", "Refs", "المراجع")], caps, sheet="Caps")]),
        _sec("trend", "12-month trend (C39)", "اتجاه 12 شهراً", [_tbl(
            [("month", "Month", "الشهر"), ("score", "Score", "النتيجة"),
             ("grade", "Grade", "التقدير")], trend, sheet="Trend")]),
        _sec("disputes", "Disputes", "الاعتراضات", [_tbl(
            [("target", "Line / cap", "البند"), ("reason", "Reason", "السبب"),
             ("status", "Status", "الحالة"), ("resolution", "Resolution", "القرار")], disputes,
            sheet="Disputes")]),
        _sec("watch", "Watch list", "قائمة المراقبة", [], [
            f"{w.entry_no}: {w.level.value}" if w else "Not on the watch list"],
             [f"{w.entry_no}: {w.level.value}" if w else "ليس في قائمة المراقبة"]),
    ], "sources": [{"kind": "scorecard", "ref": card.scorecard_no, "version": card.revision,
                    "hash": card.inputs_hash}]}  # fmt: skip


def _osha(db: Session, project: Project, year: int, end: date, names: bool) -> dict[str, Any]:
    """RP-9 / SG6: the 300-style log and the 300A-style summary (project, year or YTD)."""
    inputs.reset(db)
    ctx = inputs.context(db, project)
    start = date(year, 1, 1)
    cases = sorted((c for c in ctx.facts.cases if c.eligible and start <= c.d <= end
                    and c.category in RECORDABLE and c.project in (None, project.id)),
                   key=lambda c: (c.d, c.incident_ref))  # fmt: skip
    zones = {z.id: z.code for z in db.scalars(select(Zone))}
    sites = {s.id: s.code for s in db.scalars(select(Site).where(Site.project_id == project.id))}
    log = []
    tot = {"death": 0, "away": 0, "restricted": 0, "other": 0, "days_away": 0, "days_restr": 0}
    for n, c in enumerate(cases, start=1):
        ic = db.get(InjuryCase, c.id)
        dc = day_counts(c.dates, end, c.cap)
        col = (
            "death"
            if c.category == CaseCategory.FAT or c.fatal
            else "away"
            if c.category == CaseCategory.LTI
            else "restricted"
            if c.category in (CaseCategory.RWC, CaseCategory.JTC)
            else "other"
        )
        tot[col] += 1
        away = dc.days_away if col in ("away", "death") else 0
        restr = dc.restricted_days + dc.transfer_days
        tot["days_away"] += away
        tot["days_restr"] += restr
        trade = ic.trade.value if ic is not None else "—"
        if ic is not None and ic.privacy_case:
            person = "Privacy case"
        elif names and ic is not None:
            person = ic.person_name
        else:
            person = f"Person {n} · {trade} · {cm.eng_code(db, c.eng)}"
        desc = " · ".join(x for x in (ic.mechanism.value, ic.body_part.value, ic.nature.value)
                          ) if ic is not None else "—"  # fmt: skip
        log.append(
            {
                "case_no": n,
                "incident": c.incident_ref,
                "person": person,
                "job": trade,
                "date": c.d.isoformat(),
                "where": f"{sites.get(c.site, '—')}/{zones.get(c.zone, '—') if c.zone else '—'}",
                "description": desc,
                "classification": col,
                "days_away": away,
                "restricted": restr,
                "type": "illness" if ic is not None and ic.illness else "injury",
            }
        )
    e = inputs.engine(ctx, None, end)
    w = Window(start, end)
    a = inputs.agg(ctx, e, w)
    trir = inputs.result(ctx, e, "K-21", w)
    k03 = inputs.result(ctx, e, "K-03", w)
    total = tot["death"] + tot["away"] + tot["restricted"] + tot["other"]
    dart = (D(tot["away"] + tot["restricted"]) * ctx.config.rate_base / D(a.mh)) if a.mh else None
    summ = [{"item": k, "value": v} for k, v in [
        ("Deaths", tot["death"]), ("Days-away cases", tot["away"]),
        ("Job transfer or restriction", tot["restricted"]), ("Other recordable", tot["other"]),
        ("Total recordable", total), ("Days away", tot["days_away"]),
        ("Days restricted or transferred", tot["days_restr"]),
        ("Man-hours (K-01)", cm.s(D(a.mh))), ("Average headcount (K-03)", cm.d1(k03.value)),
        ("TRIR (K-21)", cm.d2(trir.value)), ("DART", cm.d2(dart)),
        ("Rate base", ctx.config.rate_base)]]  # fmt: skip
    cols = [("case_no", "Case", "الحالة"), ("incident", "Incident", "الحادث"),
            ("person", "Person", "الشخص"), ("job", "Job title", "المهنة"),
            ("date", "Date", "التاريخ"), ("where", "Where", "المكان"),
            ("description", "Description", "الوصف"),
            ("classification", "Classification", "التصنيف"),
            ("days_away", "Days away", "أيام الغياب"), ("restricted", "Restricted", "أيام التقييد"),
            ("type", "Injury / illness", "إصابة / مرض")]  # fmt: skip
    en, ar = labels.RT["OSHA300"]
    return {"sections": [
        _sec("log", en, ar, [_tbl(cols, log, "300-style log", "سجل الإصابات", "300 log")]),
        _sec("summary", "300A-style summary", "الملخص السنوي", [_tbl(
            [("item", "Item", "البند"), ("value", "Value", "القيمة")], summ, sheet="300A")],
             ["Commuting and non-contractor cases follow the Phase 1 rate settings."],
             ["تتبع حالات التنقل وغير المقاولين إعدادات المعدلات في المرحلة 1."]),
    ], "sources": [{"kind": "kpi", "ref": "K-21", "version": 0, "hash": digest(summ)}],
        "summary": dict(tot) | {"total": total, "mh": cm.s(D(a.mh)),
                                                      "trir": cm.d2(trir.value)}}  # fmt: skip


def _heat(db: Session, project: Project, year: int, as_of: date) -> dict[str, Any]:
    """RP-10: the 6b season metrics rendered as a pack."""
    from app.services.heat import report as hr  # noqa: PLC0415

    m = hr.compute(db, project.id, year, as_of)
    rows = []
    for k, v in m.items():
        if isinstance(v, (str, int, float, Decimal)) or v is None:
            rows.append({"metric": k, "value": cm.s(D(str(v))) if isinstance(v, (int, float,
                                                                                Decimal))
                         else v})  # fmt: skip
        elif isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()):
            rows.extend({"metric": f"{k}.{kk}", "value": vv} for kk, vv in v.items())
    en, ar = labels.RT["HEAT"]
    return {
        "sections": [
            _sec(
                "season",
                en,
                ar,
                [
                    _tbl(
                        [("metric", "Metric", "المؤشر"), ("value", "Value", "القيمة")],
                        rows,
                        sheet="Season",
                    )
                ],
            )
        ],
        "sources": [{"kind": "heat", "ref": str(year), "version": 0, "hash": digest(rows)}],
    }


def _cps(db: Session, p: Principal, contractor_id: uuid.UUID) -> dict[str, Any]:
    from app.services.scorecard import watch  # noqa: PLC0415

    s = watch.performance_summary(db, p, contractor_id)
    rows = [{"project": x.project_code, "month": x.month, "score": x.score_display,
             "grade": x.grade.value if x.grade else "—", "caps": ", ".join(c.value for c in x.caps),
             "profile": x.profile} for x in s.months]  # fmt: skip
    wl = [
        {
            "entry": w.entry_no,
            "level": w.level.value,
            "status": w.status.value,
            "decision": w.decision.value if w.decision else "—",
        }
        for w in s.watch_entries
    ]
    en, ar = labels.RT["CPS"]
    return {"sections": [
        _sec("summary", en, ar, [], [f"Weighted mean score: {s.weighted_mean_display}; grade mix "
                                     f"{s.grade_mix}; caps applied {s.caps_applied}"],
             [f"المتوسط المرجح: {s.weighted_mean_display}"]),
        _sec("months", "Final months", "الأشهر المعتمدة", [_tbl(
            [("project", "Project", "المشروع"), ("month", "Month", "الشهر"),
             ("score", "Score", "النتيجة"), ("grade", "Grade", "التقدير"),
             ("caps", "Caps", "الحدود"), ("profile", "Profile", "الملف")], rows, sheet="Months")]),
        _sec("watch", "Watch-list entries", "قائمة المراقبة", [_tbl(
            [("entry", "Entry", "الإدراج"), ("level", "Level", "المستوى"),
             ("status", "Status", "الحالة"), ("decision", "Decision", "القرار")], wl,
            sheet="Watch list")]),
    ], "sources": []}  # fmt: skip


def build(db: Session, p: Principal | None, pk: RpPack) -> None:
    """(Re)generate the snapshot of a Draft (RP-3)."""
    project = db.get(Project, pk.project_id) if pk.project_id else None
    if pk.report_type == RpType.MCR:
        assert project is not None  # noqa: S101
        snap = _mcr(db, project, pk.period_start, pk.scorecards_provisional)
    elif pk.report_type == RpType.SCP:
        card = _scp_card(db, pk)
        snap = _scp(db, card)
    elif pk.report_type == RpType.OSHA300:
        assert project is not None  # noqa: S101
        snap = _osha(db, project, pk.period_start.year, pk.period_end, pk.with_names)
    elif pk.report_type == RpType.HEAT:
        assert project is not None  # noqa: S101
        snap = _heat(db, project, pk.period_start.year, min(cm.local_day(), pk.period_end))
    else:
        assert p is not None and pk.contractor_id is not None  # noqa: S101
        snap = _cps(db, p, pk.contractor_id)
    pk.sources = snap.pop("sources", [])
    pk.snapshot = snap
    pk.snapshot_hash = digest(snap)


def _scp_card(db: Session, pk: RpPack) -> ScCard:
    from app.services.scorecard import cards  # noqa: PLC0415

    c = db.scalar(select(ScCard).where(ScCard.engagement_id == pk.engagement_id,
                                       ScCard.scope == ScScope.own,
                                       ScCard.month == pk.period_start,
                                       ScCard.status.in_(cards.CURRENT)))  # fmt: skip
    if c is None:
        raise validation_error("month", "No Issued or Final card for that month.")
    return c


# ---- rendering and files -------------------------------------------------------------------------


def to_doc(db: Session, pk: RpPack) -> render.Doc:
    en, ar = labels.RT[pk.report_type.value]
    snap = pk.snapshot or {}
    ctl = [
        ("Document", "الوثيقة", pk.doc_no),
        ("Revision", "المراجعة", str(pk.revision)),
        ("Period", "الفترة", f"{pk.period_start.isoformat()} – {pk.period_end.isoformat()}"),
    ]
    if snap.get("bases"):
        b = snap["bases"]
        ctl.append(
            ("Rate bases", "أساس المعدلات", f"LTIFR {b['ltifr']:,} h; others {b['rate']:,} h")
        )
    for lbl, lar, uid in (("Prepared by", "أعدّه", pk.prepared_by_user_id),
                          ("Reviewed by", "راجعه", pk.reviewed_by_user_id),
                          ("Issued by", "أصدره", pk.issued_by_user_id)):  # fmt: skip
        u = db.get(User, uid) if uid else None
        if u is not None:
            ctl.append((lbl, lar, u.full_name_en))
    if pk.issued_at:
        ctl.append(("Issue date", "تاريخ الإصدار", cm.to_local(pk.issued_at).date().isoformat()))
    if pk.reissue_reason:
        ctl.append(("Re-issue reason", "سبب إعادة الإصدار", pk.reissue_reason))
    if pk.report_type == RpType.MCR and pk.project_id:
        from app.services.scorecard import distribution  # noqa: PLC0415

        ctl.append(
            ("Distribution", "التوزيع", distribution.summary(db, pk.project_id, pk.report_type))
        )
    secs = [render.Section(
        key=s["key"], title_en=s["title_en"], title_ar=s["title_ar"],
        tables=[render.Table(columns=[tuple(c) for c in t["columns"]],
                             rows=t["rows"], title_en=t["title_en"], title_ar=t["title_ar"],
                             sheet=t["sheet"]) for t in s["tables"]],
        paragraphs_en=s["paragraphs_en"], paragraphs_ar=s["paragraphs_ar"],
        watermark=s.get("watermark"),
    ) for s in snap.get("sections", [])]  # fmt: skip
    return render.Doc(doc_no=pk.doc_no, revision=pk.revision, title_en=en, title_ar=ar,
                      snapshot_hash=pk.snapshot_hash or "", control=ctl, sections=secs)  # fmt: skip


def _owner_project(db: Session, pk: RpPack) -> uuid.UUID:
    if pk.project_id:
        return pk.project_id
    pid = db.scalar(select(ProjectEngagement.project_id).where(
        ProjectEngagement.contractor_id == pk.contractor_id))  # fmt: skip
    if pid is None:
        pid = db.scalar(select(Project.id))
    assert pid is not None  # noqa: S101
    return pid


def render_files(db: Session, pk: RpPack, by: uuid.UUID, superseded_by: int | None = None) -> None:
    """RP-5: EN / AR PDFs (or one bilingual PDF) and the XLSX, stored as attachments."""
    from app.services import attachments  # noqa: PLC0415

    doc = to_doc(db, pk)
    pid = _owner_project(db, pk)
    langs = cm.cfg(db, pid)["report_languages"] if pk.project_id else "en_ar_separate"
    out: list[tuple[RpFileKind, bytes, str]] = []
    if langs == RpLanguages.bilingual_single.value:
        out.append((RpFileKind.pdf_bilingual, render.pdf(doc, "both", superseded_by), "pdf"))
    else:
        out.append((RpFileKind.pdf_en, render.pdf(doc, "en", superseded_by), "pdf"))
        out.append((RpFileKind.pdf_ar, render.pdf(doc, "ar", superseded_by), "pdf"))
    if superseded_by is None:
        out.append((RpFileKind.xlsx, render.xlsx(doc), "xlsx"))
    files = dict(pk.files or {})
    for kind, content, ext in out:
        lang = "-" + kind.value.split("_")[-1] if ext == "pdf" else ""
        name = f"{pk.doc_no}-R{pk.revision}{lang}.{ext}"
        a = attachments.store(
            db, AttachmentOwner.rp_pack_file, pk.id, pid, name, content, CTYPE[ext], by
        )
        files[kind.value] = {
            "attachment_id": str(a.id),
            "file_name": name,
            "sha256": a.sha256,
            "size_bytes": a.size_bytes,
        }
        if pk.with_names:
            files[kind.value]["expires_at"] = (now() + timedelta(hours=24)).isoformat()
    pk.files = files


# ---- reads ---------------------------------------------------------------------------------------


def can_view(db: Session, p: Principal, pk: RpPack) -> bool:
    if p.is_manager:
        return True
    if pk.report_type == RpType.CPS or pk.project_id is None:
        return False
    if pk.with_names:
        return (pk.prepared_by_user_id == p.user.id
                or p.grant(pk.project_id, C.export_identity) is not None)  # fmt: skip
    issued = pk.status in (RpStatus.issued, RpStatus.superseded)
    if p.grant(pk.project_id, C.report_pack_prepare) is not None:
        return True
    g = p.grant(pk.project_id, C.report_pack_view)
    if g is None or not issued:
        return False
    if cm.is_viewer(p, pk.project_id):
        return pk.report_type in (RpType.MCR, RpType.OSHA300, RpType.HEAT)
    if g.engagement_ids is not None:
        return pk.report_type == RpType.SCP and g.covers_engagement(pk.engagement_id)
    return True


def get_pack(db: Session, p: Principal, pack_id: uuid.UUID) -> RpPack:
    pk = db.get(RpPack, pack_id)
    if pk is None or not can_view(db, p, pk):
        raise deny(db, p, EntityType.report_pack, pack_id, pk.project_id if pk else None,
                   "Report pack")  # fmt: skip
    return pk


def to_read(db: Session, pk: RpPack) -> RpPackRead:
    return RpPackRead(**_fields(db, pk))


def _fields(db: Session, pk: RpPack) -> dict[str, Any]:
    return dict(  # noqa: C408
        id=pk.id,
        doc_no=pk.doc_no,
        revision=pk.revision,
        report_type=pk.report_type,
        project_id=pk.project_id,
        engagement_id=pk.engagement_id,
        contractor_id=pk.contractor_id,
        period_start=pk.period_start,
        period_end=pk.period_end,
        status=pk.status,
        due_on=pk.due_on,
        sources=pk.sources or [],
        snapshot_hash=pk.snapshot_hash,
        files=[
            RpFileRead(
                kind=RpFileKind(k),
                file_name=v["file_name"],
                sha256=v["sha256"],
                size_bytes=v["size_bytes"],
            )
            for k, v in (pk.files or {}).items()
        ],
        with_names=pk.with_names,
        scorecards_provisional=pk.scorecards_provisional,
        provisional_reason=pk.provisional_reason,
        prepared_by=cm.user_ref(db, pk.prepared_by_user_id),
        prepared_at=pk.prepared_at,
        reviewed_by=cm.user_ref(db, pk.reviewed_by_user_id),
        reviewed_at=pk.reviewed_at,
        issued_by=cm.user_ref(db, pk.issued_by_user_id),
        issued_at=pk.issued_at,
        review_comment=pk.review_comment,
        reissue_reason=pk.reissue_reason,
        revised_since_issue=pk.revised_since_issue,
        superseded_by_revision=pk.superseded_by_revision,
        sections=[s["key"] for s in (pk.snapshot or {}).get("sections", [])],
    )


def detail(db: Session, pk: RpPack) -> RpPackDetail:
    return RpPackDetail(**_fields(db, pk), snapshot=pk.snapshot or {})


def list_packs(
    db: Session, p: Principal, project_id: uuid.UUID, report_type: RpType | None,
    status: RpStatus | None, page: int, size: int,
) -> RpPackPage:  # fmt: skip
    cm.project(db, p, project_id)
    if (p.grant(project_id, C.report_pack_view) is None
            and p.grant(project_id, C.report_pack_prepare) is None):  # fmt: skip
        raise forbidden_error()
    stmt = select(RpPack).where(RpPack.project_id == project_id)
    if report_type is not None:
        stmt = stmt.where(RpPack.report_type == report_type)
    if status is not None:
        stmt = stmt.where(RpPack.status == status)
    rows = [x for x in db.scalars(stmt.order_by(RpPack.doc_no.desc(), RpPack.revision.desc()))
            if can_view(db, p, x)]  # fmt: skip
    return RpPackPage(items=[to_read(db, x) for x in rows[(page - 1) * size : page * size]],
                      total=len(rows), page=page, page_size=size)  # fmt: skip


def read(db: Session, p: Principal, pack_id: uuid.UUID) -> RpPackDetail:
    return detail(db, get_pack(db, p, pack_id))


def file_url(db: Session, p: Principal, pack_id: uuid.UUID, kind: RpFileKind) -> RpFileUrl:
    from app.services import attachments  # noqa: PLC0415

    pk = get_pack(db, p, pack_id)
    f = (pk.files or {}).get(kind.value)
    if f is None:
        raise not_found("File")
    exp = f.get("expires_at")
    if exp and datetime.fromisoformat(exp) <= now():
        raise not_found("File")
    ttl = 300
    cm.record(db, p, AuditAction.export, EntityType.report_pack, pk, pk.project_id,
              details={"file": f["file_name"], "kind": kind.value})  # fmt: skip
    return RpFileUrl(url=attachments.raw_signed_url(uuid.UUID(f["attachment_id"]), ttl),
                     expires_at=now() + timedelta(seconds=ttl))  # fmt: skip


# ---- create, update, transitions ----------------------------------------------------------------


def _period(body: RpPackCreate) -> tuple[date, date]:
    if body.report_type in (RpType.MCR, RpType.SCP, RpType.CPS):
        if not body.month:
            raise validation_error("month", "Give the month (yyyy-mm).")
        m = cm.parse_month(body.month)
        return m, cm.month_end(m)
    if body.year is None:
        raise validation_error("year", "Give the year.")
    end = body.period_end or date(body.year, 12, 31)
    return date(body.year, 1, 1), min(end, date(body.year, 12, 31))


def due_on(db: Session, rt: RpType, project_id: uuid.UUID | None, start: date,
           end: date) -> date | None:  # fmt: skip
    if rt == RpType.MCR and project_id:
        nxt = cm.add_months(start, 1)
        return nxt.replace(day=int(cm.cfg(db, project_id)["client_report_due_day"]))
    if rt == RpType.OSHA300:
        return date(start.year + 1, 1, 31)
    if rt == RpType.HEAT and project_id:
        return heat_end(db, project_id, start.year) + timedelta(days=20)
    return None


def heat_end(db: Session, project_id: uuid.UUID, year: int, start: bool = False) -> date:
    from app.services import hse_settings  # noqa: PLC0415

    h = hse_settings.get(db, project_id)
    mmdd = h.heat_season_start if start else h.heat_season_end
    return date(year, int(mmdd[:2]), int(mmdd[3:5]))


def new_pack(
    db: Session, rt: RpType, project: Project | None, eng: ProjectEngagement | None,
    contractor: Contractor | None, start: date, end: date, revision: int,
    by: uuid.UUID | None, with_names: bool = False, p: Principal | None = None,
) -> RpPack:  # fmt: skip
    code = project.code if project else (contractor.short_code if contractor else "?")
    eng_code = eng.contractor.short_code if eng is not None else None
    pk = RpPack(
        id=uuid.uuid4(), report_type=rt, project_id=project.id if project else None,
        engagement_id=eng.id if eng else None,
        contractor_id=contractor.id if contractor else (eng.contractor_id if eng else None),
        period_start=start, period_end=end, doc_no=doc_no(rt, code, eng_code, end),
        revision=revision, with_names=with_names, status=RpStatus.draft,
        due_on=due_on(db, rt, project.id if project else None, start, end),
        prepared_by_user_id=by, prepared_at=now(), created_by_user_id=by, files={},
    )  # fmt: skip
    db.add(pk)
    db.flush()
    build(db, p, pk)
    return pk


def _latest(db: Session, doc: str) -> RpPack | None:
    return db.scalars(select(RpPack).where(RpPack.doc_no == doc)
                      .order_by(RpPack.revision.desc())).first()  # fmt: skip


def create(db: Session, p: Principal, body: RpPackCreate) -> RpPackDetail:
    start, end = _period(body)
    rt = body.report_type
    if rt == RpType.HEAT and body.project_id is not None:
        start = heat_end(db, body.project_id, start.year, True)
        end = heat_end(db, body.project_id, start.year)
    project = eng = contractor = None
    if rt == RpType.CPS:
        cm.require_manager(p)
        contractor = db.get(Contractor, body.contractor_id) if body.contractor_id else None
        if contractor is None:
            raise validation_error("contractor_id", "Give the contractor.")
    else:
        if body.project_id is None:
            raise validation_error("project_id", "Give the project.")
        project = cm.project(db, p, body.project_id)
        p.require(project.id, C.report_pack_prepare)
        if rt == RpType.SCP:
            eng = cm.eng(db, body.engagement_id) if body.engagement_id else None
            if eng is None or eng.project_id != project.id:
                raise validation_error("engagement_id", "An SCP needs an engagement (§3.6).")
    if body.with_names:
        if (
            rt != RpType.OSHA300
            or project is None
            or p.grant(project.id, C.export_identity) is None
        ):
            raise forbidden_error("Names need capability 43 (RP-9).")
        if body.purpose is None or (body.purpose == XpPurpose.other
                                    and len((body.purpose_text or "").strip()) < 20):  # fmt: skip
            raise cm.code_err(ErrorCode.PURPOSE_REQUIRED, "Give a purpose for names (RP-9).",
                              "حدد الغرض.", "purpose")  # fmt: skip
    code = project.code if project else (contractor.short_code if contractor else "?")
    prev = _latest(db, doc_no(rt, code, eng.contractor.short_code if eng else None, end))
    if prev is not None and not body.with_names:
        raise cm.err(
            409,
            ErrorCode.DUPLICATE_VALUE,
            f"{prev.doc_no} exists; regenerate or re-issue it.",
            "الوثيقة موجودة.",
        )
    pk = new_pack(db, rt, project, eng, contractor, start, end,
                  prev.revision + 1 if prev else 0, p.user.id, body.with_names, p)  # fmt: skip
    cm.record(db, p, AuditAction.create, EntityType.report_pack, pk, pk.project_id,
              details={"purpose": body.purpose.value if body.purpose else None})  # fmt: skip
    db.flush()
    return detail(db, pk)


def _immutable() -> Exception:
    return cm.err(409, ErrorCode.PACK_ISSUED_IMMUTABLE, "An Issued pack cannot be changed.",
                  "لا يمكن تعديل حزمة صادرة.")  # fmt: skip


def update(db: Session, p: Principal, pack_id: uuid.UUID, body: RpPackUpdate) -> RpPackDetail:
    pk = get_pack(db, p, pack_id)
    if pk.status not in OPEN:
        raise _immutable()
    if pk.project_id:
        p.require(pk.project_id, C.report_pack_prepare)
    pk.review_comment = body.review_comment
    db.flush()
    return detail(db, pk)


def _check_issue(db: Session, p: Principal, pk: RpPack, body: RpPackTransition) -> None:
    if pk.reviewed_by_user_id is None:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Review the pack first.",
                     "يجب مراجعة الحزمة أولاً.")  # fmt: skip
    if pk.reviewed_by_user_id == p.user.id:
        raise cm.code_err(ErrorCode.SELF_REVIEW, "The reviewer cannot issue the pack (RP-4).",
                          "لا يجوز للمراجع إصدار الحزمة.")  # fmt: skip
    if pk.report_type == RpType.MCR and pk.project_id:
        project = cm.project_by_id(db, pk.project_id)
        if _phase1(db, project, pk.period_start) is None:
            raise cm.code_err(ErrorCode.SOURCE_REPORT_NOT_PUBLISHED,
                              "Publish the Phase 1 monthly report first (RP-4).",
                              "يجب نشر التقرير الشهري أولاً.")  # fmt: skip
        cards_ = _cards(db, pk.project_id, pk.period_start)
        if any(c.status != ScCardStatus.final for c in cards_):
            if not body.scorecards_provisional:
                raise cm.code_err(ErrorCode.SCORECARDS_NOT_FINAL,
                                  "The month's scorecards are not Final; wait or issue them as "
                                  "provisional with a reason (RP-4).",
                                  "بطاقات الأداء غير معتمدة.")  # fmt: skip
            pk.scorecards_provisional = True
            pk.provisional_reason = cm.reason(body.provisional_reason, 20, "provisional_reason")
        else:
            pk.scorecards_provisional = False


def transition(
    db: Session, p: Principal, pack_id: uuid.UUID, body: RpPackTransition
) -> RpPackDetail:
    pk = get_pack(db, p, pack_id)
    a = body.action
    if pk.status not in OPEN:
        raise _immutable()
    if pk.report_type == RpType.CPS or pk.project_id is None:
        cm.require_manager(p)
    bad = cm.err(409, ErrorCode.INVALID_TRANSITION, f"{a.value} is not allowed now.",
                 "الإجراء غير مسموح الآن.")  # fmt: skip
    t = now()
    if a == RpAction.issue:
        if pk.project_id:
            p.require(pk.project_id, C.report_pack_issue)
        if pk.status != RpStatus.in_review:
            raise bad
        _check_issue(db, p, pk, body)
        issue(db, pk, p.user.id, t, body.remove_xlsx_for_externals, p)
    else:
        if pk.project_id:
            p.require(pk.project_id, C.report_pack_prepare)
        if a == RpAction.submit_for_review and pk.status == RpStatus.draft:
            pk.status = RpStatus.in_review
            pk.prepared_by_user_id, pk.prepared_at = p.user.id, t
        elif a == RpAction.return_to_draft and pk.status == RpStatus.in_review:
            pk.status = RpStatus.draft
            pk.review_comment = cm.reason(body.comment, 5, "comment")
            pk.reviewed_by_user_id = pk.reviewed_at = None
        elif a == RpAction.review and pk.status == RpStatus.in_review:
            pk.reviewed_by_user_id, pk.reviewed_at = p.user.id, t
            pk.review_comment = body.comment
        elif a == RpAction.regenerate and pk.status == RpStatus.draft:
            build(db, p, pk)
        else:
            raise bad
    cm.record(db, p, AuditAction.status_change, EntityType.report_pack, pk, pk.project_id,
              details={"action": a.value})  # fmt: skip
    db.flush()
    return detail(db, pk)


def issue(db: Session, pk: RpPack, by: uuid.UUID, t: datetime, no_xlsx_ext: bool = False,
          p: Principal | None = None) -> None:  # fmt: skip
    """Freeze, render, supersede the previous revision and distribute (RP-5, RP-6, DL-4)."""
    from app.services.scorecard import distribution  # noqa: PLC0415

    if pk.report_type == RpType.MCR and pk.project_id:
        sc = scorecard_section(db, pk.project_id, pk.period_start, pk.scorecards_provisional)
        secs = [s for s in pk.snapshot.get("sections", [])
                if s["key"] not in ("scorecards", "p1:contractor_performance")]  # fmt: skip
        if sc is not None:
            idx = next((i for i, s in enumerate(secs) if s["key"] == "appendix"), len(secs))
            secs.insert(idx, sc)
            p1 = next((i for i, s in enumerate(pk.snapshot.get("sections", []))
                       if s["key"] == "p1:contractor_performance"), None)  # fmt: skip
            if p1 is not None:
                old7 = pk.snapshot["sections"][p1]
                secs.insert(p1, _section7(sc, "p1:contractor_performance", old7["title_en"],
                                          old7["title_ar"]))  # fmt: skip
        pk.snapshot = {**pk.snapshot, "sections": secs}
        pk.snapshot_hash = digest(pk.snapshot)
    pk.issued_by_user_id, pk.issued_at = by, t
    distribution.precheck(db, pk, no_xlsx_ext)
    render_files(db, pk, by)
    pk.status = RpStatus.issued
    for old in db.scalars(select(RpPack).where(RpPack.doc_no == pk.doc_no,
                                               RpPack.revision < pk.revision,
                                               RpPack.status == RpStatus.issued)):  # fmt: skip
        old.status = RpStatus.superseded
        old.superseded_by_revision = pk.revision
        render_files(db, old, by, superseded_by=pk.revision)
    db.flush()
    distribution.distribute(db, pk, no_xlsx_ext)


def reissue(db: Session, p: Principal, pack_id: uuid.UUID, reason: str) -> RpPackDetail:
    pk = get_pack(db, p, pack_id)
    if pk.project_id:
        p.require(pk.project_id, C.report_pack_issue)
    else:
        cm.require_manager(p)
    if pk.status != RpStatus.issued:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Only an Issued pack is re-issued.",
                     "تُعاد إصدار الحزم الصادرة فقط.")  # fmt: skip
    if _latest(db, pk.doc_no) is not pk:
        raise cm.err(
            409, ErrorCode.DUPLICATE_VALUE, "A newer revision exists.", "توجد مراجعة أحدث."
        )
    text = cm.reason(reason, 20)
    project = db.get(Project, pk.project_id) if pk.project_id else None
    eng = db.get(ProjectEngagement, pk.engagement_id) if pk.engagement_id else None
    con = db.get(Contractor, pk.contractor_id) if pk.contractor_id and not eng else None
    new = new_pack(db, pk.report_type, project, eng, con, pk.period_start, pk.period_end,
                   pk.revision + 1, p.user.id, pk.with_names, p)  # fmt: skip
    new.reissue_reason = text
    new.due_on = pk.due_on
    cm.record(db, p, AuditAction.create, EntityType.report_pack, new, new.project_id,
              details={"reissue_of": pk.revision, "reason": text})  # fmt: skip
    db.flush()
    return detail(db, new)


# ---- system packs and jobs ----------------------------------------------------------------------


def issue_scp(db: Session, card: ScCard, t: datetime, by: uuid.UUID | None = None) -> RpPack:
    """RP-8: generated and issued by the system at finalisation; to the engagement's reps."""
    project = cm.project_by_id(db, card.project_id)
    e = cm.eng(db, card.engagement_id)
    uid = by or sorted(cm.managers(db))[0]
    prev = _latest(db, doc_no(RpType.SCP, project.code, e.contractor.short_code, card.month))
    pk = new_pack(db, RpType.SCP, project, e, None, card.month, cm.month_end(card.month),
                  prev.revision + 1 if prev else 0, None)  # fmt: skip
    if prev is not None:
        pk.reissue_reason = f"Scorecard {card.scorecard_no} revision {card.revision}"
    pk.prepared_by_user_id = pk.reviewed_by_user_id = None
    issue(db, pk, uid, t)
    pk.issued_by_user_id = by
    return pk


def mcr_due(db: Session, project_id: uuid.UUID, month: date) -> date:
    d = due_on(db, RpType.MCR, project_id, month, cm.month_end(month))
    assert d is not None  # noqa: S101
    return d


def restatement(db: Session, t: datetime) -> int:
    """RP-7: Issued packs of the last 12 months whose sources changed → revised_since_issue and
    one alert to the HSE Manager. Re-issue is never automatic."""
    from app.ai import reports as p1  # noqa: PLC0415

    since = cm.add_months(cm.local_day(t).replace(day=1), -12)
    n = 0
    for pk in db.scalars(
        select(RpPack).where(
            RpPack.status == RpStatus.issued,
            RpPack.period_start >= since,
            RpPack.revised_since_issue.is_(False),
            RpPack.report_type.in_([RpType.MCR, RpType.SCP]),
        )
    ):
        changed = False
        for s in pk.sources or []:
            if s["kind"] == "phase1_report":
                r = db.get(MonthlyReport, uuid.UUID(s["ref"]))
                changed |= r is None or p1.revised(db, r)
            elif s["kind"] == "scorecard":
                c = db.scalar(select(ScCard).where(ScCard.scorecard_no == s["ref"],
                                                   ScCard.status.in_([ScCardStatus.issued,
                                                                      ScCardStatus.final]))
                              .order_by(ScCard.revision.desc()).limit(1))  # fmt: skip
                changed |= c is None or c.revision != s["version"] or c.revised_since_final
        if changed:
            pk.revised_since_issue = True
            if cm.once(db, f"rp_revised:{pk.id}"):
                n += cm.send(db, cm.managers(db), NotificationKind.scorecard_revised,
                             f"{pk.doc_no} Rev {pk.revision}: source numbers changed after Issue",
                             f"تغيّرت أرقام {pk.doc_no} بعد الإصدار", pk.project_id,
                             EntityType.report_pack, pk.id, email=True)  # fmt: skip
    db.flush()
    return n


def run_daily(db: Session, t: datetime) -> dict[str, int]:
    """`report_pack_daily` 07:00: MCR Drafts and due alerts (SC-2), OSHA300 / HEAT Drafts
    (SC-3), restatement watch (RP-7)."""
    from app.services import hse_settings  # noqa: PLC0415

    today = cm.local_day(t)
    created = alerts = 0
    sysuser = sorted(cm.managers(db))[0] if cm.managers(db) else None
    for project in db.scalars(select(Project).where(Project.status != ProjectStatus.closed)):
        c = cm.cfg(db, project.id)
        if c.from_month is None:
            continue
        month = cm.add_months(today.replace(day=1), -1)
        lock_day = hse_settings.get(db, project.id).month_lock_day
        due = mcr_due(db, project.id, month)
        no = doc_no(RpType.MCR, project.code, None, cm.month_end(month))
        pk = _latest(db, no)
        published = _phase1(db, project, month) is not None
        if pk is None and today.day >= lock_day + 1 and published:
            new_pack(db, RpType.MCR, project, None, None, month, cm.month_end(month), 0, sysuser)
            created += 1
            pk = _latest(db, no)
        ids = cm.officers(db, project.id) | cm.managers(db)
        if (
            due - timedelta(days=3) <= today < due
            and (pk is None or not published)
            and cm.once(db, f"rp_due3:{project.id}:{month}")
        ):
            alerts += cm.send(
                db,
                ids,
                NotificationKind.report_pack_due,
                f"{no} is due on {due}: "
                + ("no Draft yet" if pk is None else "Phase 1 report not Published"),
                f"{no} مستحق في {due}",
                project.id,
                email=True,
            )
        if today >= due and (pk is None or pk.status != RpStatus.issued):
            key = f"rp_due:{project.id}:{month}:" + ("due" if today == due else str(today))
            if cm.once(db, key):
                alerts += cm.send(
                    db,
                    cm.managers(db),
                    NotificationKind.report_pack_due,
                    f"{no} is {'due today' if today == due else 'overdue'} (due {due})",
                    f"{no} مستحق",
                    project.id,
                    email=True,
                )
        if today.month == 1 and today.day >= 15:
            ono = doc_no(RpType.OSHA300, project.code, None, date(today.year - 1, 12, 31))
            if _latest(db, ono) is None:
                new_pack(db, RpType.OSHA300, project, None, None, date(today.year - 1, 1, 1),
                         date(today.year - 1, 12, 31), 0, sysuser)  # fmt: skip
                created += 1
        hend = heat_end(db, project.id, today.year)
        if today >= hend + timedelta(days=10) and today.year >= c.from_month.year:
            hno = doc_no(RpType.HEAT, project.code, None, hend)
            if _latest(db, hno) is None:
                new_pack(db, RpType.HEAT, project, None, None,
                         heat_end(db, project.id, today.year, True), hend, 0, sysuser)  # fmt: skip
                created += 1
    revised = restatement(db, t)
    db.flush()
    return {"created": created, "alerts": alerts, "revised": revised}
