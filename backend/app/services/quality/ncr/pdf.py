"""NCR PDF (spec 8-quality Q-NCR-19, D-319): EN or AR (RTL) with the 6g renderer, the Gregorian
and Umm al-Qura Hijri issue date (`app.core.hijri`), all sections, sign-offs and the cost
summary; cost rates and lines only for a reader holding 242 (or 239 / the HSE Manager); no person
names for the Viewer / Client (P8-4). Generated on demand, never stored."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.hijri import hijri_ar, hijri_en
from app.core.quality.common import label
from app.models.quality import QNcr
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.ncr import core
from app.services.scorecard import render


def _t(en: str | None, ar: str | None, rtl: bool) -> str:
    return ((ar or en) if rtl else (en or ar)) or "—"


def doc(db: Session, p: Principal, n: QNcr) -> render.Doc:
    r = core.read(db, p, n)
    project = core.project_of(db, n)
    issued = qc.project_day(project)
    hide = r["names_hidden"]

    def name(u: dict[str, Any] | None, ar: bool) -> str:
        if not u:
            return "—"
        return str((u.get("full_name_ar") or u["full_name_en"]) if ar else u["full_name_en"])

    eng = r["responsible_engagement"]
    control: list[tuple[str, ...]] = [
        ("NCR no.", "رقم التقرير", n.ncr_no or "Draft"),
        ("Project", "المشروع", project.code),
        ("Status", "الحالة", label("ncr_status", n.status), label("ncr_status", n.status, True)),
        (
            "Class",
            "التصنيف",
            label("ncr_class", n.classification or "—"),
            label("ncr_class", n.classification or "—", True),
        ),
        (
            "Category",
            "فئة العيب",
            label("ncr_category", n.category or "—"),
            label("ncr_category", n.category or "—", True),
        ),
        (
            "Source",
            "المصدر",
            f"{label('ncr_source', n.source_type)} {n.source_ref or ''}".strip(),
            f"{label('ncr_source', n.source_type, True)} {n.source_ref or ''}".strip(),
        ),
        (
            "Detection stage",
            "مرحلة الاكتشاف",
            label("detection_stage", n.detection_stage or "—"),
            label("detection_stage", n.detection_stage or "—", True),
        ),
        ("Site", "الموقع", r["site"]["code"]),
        ("Responsible", "الجهة المسؤولة", eng["short_code"] if eng else "—"),
        ("Opened", "تاريخ الفتح", n.opened_date.isoformat() if n.opened_date else "—"),
        (
            "Target close",
            "الإغلاق المستهدف",
            n.target_close_date.isoformat() if n.target_close_date else "—",
        ),
        ("Owner", "مسؤول المعالجة", name(r["owner"], False), name(r["owner"], True)),
        ("Issue date", "تاريخ الإصدار", issued.isoformat()),
        (
            "Issue date (Hijri, Umm al-Qura)",
            "تاريخ الإصدار الهجري، أم القرى",
            hijri_en(issued),
            hijri_ar(issued),
        ),
    ]
    if hide:
        control = [c for c in control if c[0] != "Owner"]
    sections = [
        render.Section(
            "finding",
            "Requirement and finding",
            "المتطلب والوضع الفعلي",
            paragraphs_en=[
                n.title,
                f"Requirement: {_t(n.requirement_en, n.requirement_ar, False)}",
                f"Finding: {_t(n.finding_en, n.finding_ar, False)}",
            ],
            paragraphs_ar=[
                n.title,
                f"المتطلب: {_t(n.requirement_en, n.requirement_ar, True)}",
                f"الوضع الفعلي: {_t(n.finding_en, n.finding_ar, True)}",
            ],
        ),
        render.Section(
            "containment",
            "Containment",
            "الاحتواء",
            paragraphs_en=[_t(n.containment_en, n.containment_ar, False)],
            paragraphs_ar=[_t(n.containment_en, n.containment_ar, True)],
        ),
    ]
    rca = r["rca"]
    if rca:
        sections.append(
            render.Section(
                "rca",
                "Root cause",
                "السبب الجذري",
                paragraphs_en=[
                    f"{label('rca_method', rca['method'])}: {rca['root_cause'] or '—'} "
                    f"({label('cause_category', rca['cause_category'] or '—')})"
                ],
                paragraphs_ar=[
                    f"{label('rca_method', rca['method'], True)}: {rca['root_cause'] or '—'} "
                    f"({label('cause_category', rca['cause_category'] or '—', True)})"
                ],
            )
        )
    cols = [
        ("disposition", "Disposition", "المعالجة"),
        ("quantity", "Quantity", "الكمية"),
        ("note", "Note", "ملاحظة"),
    ]
    rows = [
        {
            "disposition": label("disposition", x["disposition"]),
            "quantity": x["quantity"] or "",
            "note": x["note"] or "",
        }
        for x in r["disposition_lines"]
    ]
    rows_ar = [
        {
            "disposition": label("disposition", x["disposition"], True),
            "quantity": x["quantity"] or "",
            "note": x["note"] or "",
        }
        for x in r["disposition_lines"]
    ]
    sections.append(
        render.Section(
            "disposition",
            "Disposition",
            "المعالجة",
            tables=[render.Table(cols, rows, rows_ar=rows_ar)] if rows else [],
            paragraphs_en=[
                _t(n.disposition_justification_en, n.disposition_justification_ar, False)
            ],
            paragraphs_ar=[
                _t(n.disposition_justification_en, n.disposition_justification_ar, True)
            ],
        )
    )
    if r["actions"]:
        acols = [
            ("ref", "Action", "الإجراء"),
            ("title", "Title", "العنوان"),
            ("status", "Status", "الحالة"),
            ("due", "Due", "الاستحقاق"),
        ]
        arows = [
            {
                "ref": a["ref"],
                "title": a["title"],
                "status": a["status"].value,
                "due": a["due_date"].isoformat(),
            }
            for a in r["actions"]
        ]
        sections.append(
            render.Section(
                "actions",
                "Corrective actions",
                "الإجراءات التصحيحية",
                tables=[render.Table(acols, arows)],
            )
        )
    if not hide:
        cost_en = [
            f"Gross SAR {r['cost_gross_sar']}, recovered SAR {r['cost_recovered_sar']}, "
            f"net SAR {r['cost_net_sar']} ({r['failure_class'] or '—'} failure)."
        ]
        cost_ar = [
            f"الإجمالي {r['cost_gross_sar']} ريال، المسترد {r['cost_recovered_sar']} ريال، "
            f"الصافي {r['cost_net_sar']} ريال."
        ]
        tables = []
        if r["cost_lines_visible"] and r["cost_lines"]:
            ccols = [
                ("type", "Cost type", "نوع التكلفة"),
                ("qty", "Qty", "الكمية"),
                ("rate", "Rate SAR", "السعر"),
                ("amount", "Amount SAR", "المبلغ"),
            ]
            crows = [
                {
                    "type": label("cost_type", c["cost_type"]),
                    "qty": c["quantity"],
                    "rate": c["rate_sar"],
                    "amount": c["amount_sar"],
                }
                for c in r["cost_lines"]
            ]
            crows_ar = [
                {**x, "type": label("cost_type", c["cost_type"], True)}
                for x, c in zip(crows, r["cost_lines"], strict=True)
            ]
            tables.append(render.Table(ccols, crows, rows_ar=crows_ar))
        sections.append(
            render.Section(
                "costs",
                "Cost of the NCR",
                "تكلفة التقرير",
                tables=tables,
                paragraphs_en=cost_en,
                paragraphs_ar=cost_ar,
            )
        )
        scols = [
            ("step", "Step", "الخطوة"),
            ("decision", "Decision", "القرار"),
            ("by", "Signed", "التوقيع"),
            ("at", "Date", "التاريخ"),
        ]
        srows = [
            {
                "step": s["step"],
                "decision": s["decision"],
                "by": s["text_en"],
                "at": s["signed_at"].date().isoformat(),
            }
            for s in r["signoffs"]
        ]
        srows_ar = [{**x, "by": s["text_ar"]} for x, s in zip(srows, r["signoffs"], strict=True)]
        sections.append(
            render.Section(
                "signoffs",
                "Sign-offs",
                "التوقيعات",
                tables=[render.Table(scols, srows, rows_ar=srows_ar)] if srows else [],
                paragraphs_en=[] if srows else ["No sign-offs yet."],
                paragraphs_ar=[] if srows else ["لا توجد توقيعات بعد."],
            )
        )
        sections.append(
            render.Section(
                "photos",
                "Photos and evidence",
                "الصور والأدلة",
                paragraphs_en=[
                    f"{r['photo_count']} photo(s), {r['evidence_count']} evidence file(s)."
                ],
                paragraphs_ar=[f"{r['photo_count']} صورة، {r['evidence_count']} ملف دليل."],
            )
        )
    digest = hashlib.sha256(
        json.dumps([control, [s.key for s in sections]], default=str).encode()
    ).hexdigest()
    return render.Doc(
        doc_no=n.ncr_no or "NCR-DRAFT",
        revision=n.reopened_count or 0,
        title_en=f"Nonconformance Report {n.ncr_no or ''}".strip(),
        title_ar=f"تقرير عدم مطابقة {n.ncr_no or ''}".strip(),
        snapshot_hash=digest,
        control=control,
        sections=sections,
    )


def pdf(db: Session, p: Principal, ncr_id: Any, lang: str) -> tuple[bytes, str]:
    n = core.get_ncr(db, p, ncr_id)
    d = doc(db, p, n)
    return render.pdf(d, lang), f"{n.ncr_no or 'NCR-DRAFT'}-{lang.upper()}.pdf"
