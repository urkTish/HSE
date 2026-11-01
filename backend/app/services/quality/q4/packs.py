"""Quality report packs on the 6g `rp_packs` flow (spec 8-quality §E.8, Q-RPT-01…05): QMR monthly
quality report (sections by profile), QNCR NCR register, QSUP supplier scorecards and QMRV
management review minutes. This module only builds the snapshot sections; prepare, review, issue,
distribution, re-issue and the EN / AR PDFs with the Gregorian and Hijri issue date are 6g's
(`app.services.scorecard.packs`). Charts are rendered as tables (Q-RPT-03)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.quality.common import NCR_LIVE, QNcrStatus, QSectorProfile
from app.core.quality.q4 import QKpi, QMrvStatus, QPackType
from app.kpi import quality as qk
from app.models import Project
from app.models.quality import QNcr, QSupplier
from app.models.quality.q4 import QManagementReview, QSupplierScore

KPI_COLS = [
    ("kpi", "KPI", "المؤشر"),
    ("name", "Name", "الاسم"),
    ("value", "Value", "القيمة"),
    ("num", "Numerator", "البسط"),
    ("den", "Denominator", "المقام"),
    ("target", "Target", "المستهدف"),
    ("rag", "Status", "الحالة"),
]


def _tbl(
    cols: list[tuple[str, str, str]],
    rows: list[dict[str, Any]],
    en: str = "",
    ar: str = "",
    rows_ar: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    t = {
        "columns": [list(c) for c in cols],
        "rows": rows,
        "title_en": en,
        "title_ar": ar,
        "sheet": (en or "Table")[:28],
    }
    if rows_ar is not None:
        t["rows_ar"] = rows_ar
    return t


def _sec(
    key: str,
    en: str,
    ar: str,
    tables: list[dict[str, Any]],
    pen: list[str] | None = None,
    par: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title_en": en,
        "title_ar": ar,
        "tables": tables,
        "paragraphs_en": pen or [],
        "paragraphs_ar": par or [],
        "watermark": None,
    }


def kpi_section(
    db: Session, e: qk.Engine, kpis: list[QKpi], key: str, en: str, ar: str
) -> dict[str, Any]:
    rows, rows_ar = [], []
    for k in kpis:
        r = e.result(k)
        t = qk.target_of(db, e.project.id, k, e.end)
        base = {
            "kpi": k.value,
            "value": r.display,
            "num": str(r.numerator or "—"),
            "den": str(r.denominator or "—"),
            "target": str(t) if t is not None else "—",
            "rag": qk.rag_for(r, t) or "—",
        }
        rows.append({**base, "name": qk.CATALOGUE[k][0]})
        rows_ar.append({**base, "name": qk.CATALOGUE[k][1]})
    return _sec(key, en, ar, [_tbl(KPI_COLS, rows, en, ar, rows_ar)])


def _ncr_rows(db: Session, project: Project, start: date, end: date) -> list[dict[str, Any]]:
    out = []
    for n in db.scalars(
        select(QNcr)
        .where(
            QNcr.project_id == project.id,
            QNcr.status.not_in([QNcrStatus.draft, QNcrStatus.voided]),
            QNcr.opened_date <= end,
            (QNcr.closed_date.is_(None)) | (QNcr.closed_date >= start),
        )
        .order_by(QNcr.ncr_no)
    ):
        out.append(
            {
                "no": n.ncr_no,
                "title": n.title,
                "class": n.classification.value if n.classification else "",
                "category": n.category.value if n.category else "",
                "status": n.status.value,
                "opened": n.opened_date.isoformat() if n.opened_date else "",
                "target": n.target_close_date.isoformat() if n.target_close_date else "",
                "closed": n.closed_date.isoformat() if n.closed_date else "",
            }
        )
    return out


NCR_COLS = [
    ("no", "NCR", "التقرير"),
    ("title", "Title", "العنوان"),
    ("class", "Class", "التصنيف"),
    ("category", "Category", "الفئة"),
    ("status", "Status", "الحالة"),
    ("opened", "Opened", "تاريخ الفتح"),
    ("target", "Target close", "الإغلاق المستهدف"),
    ("closed", "Closed", "تاريخ الإغلاق"),
]


def _pareto_table(e: qk.Engine) -> dict[str, Any]:
    par = e.result(QKpi.K150).extra["pareto"]
    return _tbl(
        [
            ("code", "Category", "الفئة"),
            ("count", "Count", "العدد"),
            ("pct", "%", "%"),
            ("cumulative_pct", "Cumulative %", "التراكمي %"),
        ],
        par["rows"],
        "Pareto of defect causes (C43)",
        "باريتو أسباب العيوب",
    )


def qmr(db: Session, project: Project, start: date, end: date) -> dict[str, Any]:
    """Q-RPT-03 monthly quality report."""
    e = qk.Engine(db, project, start, end, end)
    shared = [
        QKpi.K143,
        QKpi.K144,
        QKpi.K145,
        QKpi.K146,
        QKpi.K147,
        QKpi.K148,
        QKpi.K149,
        QKpi.K154,
        QKpi.K155,
        QKpi.K157,
        QKpi.K158,
        QKpi.K159,
        QKpi.K169,
    ]
    secs = [
        kpi_section(
            db,
            e,
            qk.tiles_for(e.profile),
            "summary",
            "KPI summary against targets",
            "ملخص المؤشرات مقابل المستهدفات",
        )
    ]
    open_rows = [r for r in _ncr_rows(db, project, start, end) if r["closed"] == ""]
    open_rows.sort(key=lambda r: r["opened"])
    secs.append(
        _sec(
            "ncrs",
            "Nonconformities",
            "حالات عدم المطابقة",
            [
                _pareto_table(e),
                _tbl(NCR_COLS, open_rows[:5], "Top 5 open NCRs by age", "أقدم 5 تقارير مفتوحة"),
            ],
        )
    )
    secs.append(
        kpi_section(
            db,
            e,
            shared,
            "shared",
            "NCRs, COPQ, calibration, competence, audits, suppliers, complaints",
            "التقارير والتكلفة والمعايرة والكفاءة والتدقيق والموردون والشكاوى",
        )
    )
    if e.profile == QSectorProfile.logistics:
        secs.append(
            kpi_section(
                db,
                e,
                [
                    QKpi.K160,
                    QKpi.K161,
                    QKpi.K162,
                    QKpi.K163,
                    QKpi.K164,
                    QKpi.K165,
                    QKpi.K166,
                    QKpi.K167,
                    QKpi.K168,
                ],
                "logistics",
                "Logistics: receiving, cold chain, stock, transport, hygiene",
                "اللوجستيات: الاستلام وسلسلة التبريد والمخزون والنقل والنظافة",
            )
        )
        zones = e.result(QKpi.K162).extra.get("zones") or []
        secs.append(
            _sec(
                "zones",
                "Time out of range per zone",
                "الزمن خارج النطاق لكل منطقة",
                [
                    _tbl(
                        [
                            ("zone_id", "Zone", "المنطقة"),
                            ("monitored", "Monitored min", "دقائق المراقبة"),
                            ("out", "Out min", "دقائق خارج النطاق"),
                            ("tor_pct", "TOR %", "النسبة %"),
                            ("coverage_pct", "Coverage %", "التغطية %"),
                        ],
                        [{k: str(v) for k, v in z.items()} for z in zones],
                    )
                ],
            )
        )
    else:
        secs.append(
            kpi_section(
                db,
                e,
                [QKpi.K141, QKpi.K142, QKpi.K151, QKpi.K152, QKpi.K153, QKpi.K156],
                "construction",
                "Construction: IRs, materials, tests, welding, punch",
                "الإنشاءات: طلبات الفحص والمواد والاختبارات واللحام والنواقص",
            )
        )
    proc = [{"process": k, **{kk: str(v) for kk, v in x.items()}} for k, x in e.dpmo().items()]
    secs.append(
        _sec(
            "sigma",
            "DPMO and sigma level by process (C51)",
            "العيوب ومستوى سيجما (C51)",
            [
                _tbl(
                    [
                        ("process", "Process", "العملية"),
                        ("units", "Units", "الوحدات"),
                        ("opportunities", "Opportunities", "الفرص"),
                        ("defects", "Defects", "العيوب"),
                        ("dpmo", "DPMO", "DPMO"),
                        ("sigma_display", "Sigma", "سيجما"),
                    ],
                    proc,
                )
            ],
        )
    )
    warn = qk.warnings(db, project, end)
    secs.append(
        _sec(
            "warnings",
            "Warnings E26–E28",
            "الإنذارات E26–E28",
            [_tbl([("code", "Code", "الرمز"), ("message_en", "Warning", "الإنذار")], warn)],
            [] if warn else ["No warning for the month."],
            [] if warn else ["لا توجد إنذارات للشهر."],
        )
    )
    return {"sections": secs, "sources": []}


def qncr(db: Session, project: Project, start: date, end: date) -> dict[str, Any]:
    e = qk.Engine(db, project, start, end, end)
    rows = _ncr_rows(db, project, start, end)
    live = sum(1 for r in rows if r["status"] in {s.value for s in NCR_LIVE})
    return {
        "sections": [
            kpi_section(
                db,
                e,
                [QKpi.K143, QKpi.K144, QKpi.K145, QKpi.K146, QKpi.K147],
                "summary",
                "NCR KPIs",
                "مؤشرات تقارير عدم المطابقة",
            ),
            _sec(
                "register",
                "NCR register",
                "سجل التقارير",
                [_tbl(NCR_COLS, rows, "NCRs", "التقارير")],
                [f"{len(rows)} NCRs in the register for the period; {live} open."],
                [f"{len(rows)} تقريراً في السجل للفترة؛ {live} مفتوحة."],
            ),
            _sec("pareto", "Pareto", "باريتو", [_pareto_table(e)]),
        ],
        "sources": [],
    }


def qsup(db: Session, project: Project, start: date, end: date) -> dict[str, Any]:
    rows = []
    for x, s in db.execute(
        select(QSupplierScore, QSupplier)
        .join(QSupplier, QSupplier.id == QSupplierScore.supplier_id)
        .where(QSupplierScore.period_end >= start, QSupplierScore.period_start <= end)
        .order_by(QSupplierScore.score.desc())
    ):
        pts = (x.metrics or {}).get("points", {})
        rows.append(
            {
                "code": s.supplier_code,
                "name": s.legal_name_en,
                "score": str(x.score or "—"),
                "band": x.band or "—",
                "status": x.status.value,
                **{m: pts.get(m, "—") for m in ("M1", "M2", "M3", "M4", "M5", "M6")},
            }
        )
    cols = [
        ("code", "Supplier", "المورد"),
        ("name", "Name", "الاسم"),
        ("score", "Score", "الدرجة"),
        ("band", "Band", "الفئة"),
        ("status", "Status", "الحالة"),
        *[(m, m, m) for m in ("M1", "M2", "M3", "M4", "M5", "M6")],
    ]
    return {
        "sections": [
            _sec(
                "scores",
                "Supplier quality scorecards (C50)",
                "بطاقات أداء الموردين (C50)",
                [_tbl(cols, rows, "Scores", "الدرجات")],
                [] if rows else ["No scorecard in the period."],
                [] if rows else ["لا توجد بطاقات للفترة."],
            )
        ],
        "sources": [],
    }


def qmrv(db: Session, project: Project, start: date, end: date) -> dict[str, Any]:
    from app.services.quality.q4 import audits  # noqa: PLC0415

    m = db.scalar(
        select(QManagementReview)
        .where(
            QManagementReview.project_id == project.id,
            QManagementReview.status.in_([QMrvStatus.held, QMrvStatus.minutes_issued]),
            QManagementReview.held_on >= start,
            QManagementReview.held_on <= end,
        )
        .order_by(QManagementReview.held_on.desc())
        .limit(1)
    )
    if m is None:
        return {
            "sections": [
                _sec(
                    "none",
                    "Management review",
                    "مراجعة الإدارة",
                    [],
                    ["No management review was held in the period."],
                    ["لم تُعقد مراجعة إدارة في الفترة."],
                )
            ],
            "sources": [],
        }
    doc = audits.minutes_doc(db, m, project)
    secs = []
    for s in doc.sections:
        secs.append(
            _sec(
                s.key,
                s.title_en,
                s.title_ar,
                [
                    _tbl(list(t.columns), t.rows, t.title_en, t.title_ar, t.rows_ar)
                    for t in s.tables
                ],
                s.paragraphs_en,
                s.paragraphs_ar,
            )
        )
    return {"sections": secs, "sources": [{"mrv_no": m.mrv_no}]}


BUILDERS = {QPackType.QMR: qmr, QPackType.QNCR: qncr, QPackType.QSUP: qsup, QPackType.QMRV: qmrv}


def snapshot(
    db: Session, project: Project, report_type: str, start: date, end: date
) -> dict[str, Any]:
    return BUILDERS[QPackType(report_type)](db, project, start, end)
