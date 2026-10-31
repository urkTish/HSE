"""IR form PDF (spec 8-quality Q-IR-13, D-319): EN or AR (RTL) with the 6g renderer, the Gregorian
and Umm al-Qura Hijri issue date, project and contractor, ITP points, location, rounds, checklist
answers, measurements with the M&TE numbers and calibration due dates, and every sign-off including
paper sign-offs ("Signed on paper by …"). No person names for the Viewer / Client (P8-4)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.hijri import hijri_ar, hijri_en
from app.core.quality.common import label
from app.models.quality.q1 import QItp
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.q1 import common as q1c
from app.services.quality.q1 import ir as irs
from app.services.quality.q1 import itp as itps
from app.services.scorecard import render


def doc(db: Session, p: Principal, ir_id: uuid.UUID) -> tuple[render.Doc, str]:
    ir = irs.get_ir(db, p, ir_id)
    r = irs.read(db, p, ir)
    pr = q1c.project(db, ir.project_id)
    it = db.get(QItp, ir.itp_id)
    issued = qc.project_day(pr)
    eng = r["engagement"] or {}
    control: list[tuple[str, ...]] = [
        ("IR no.", "رقم الطلب", ir.ir_no or "Draft"),
        ("Project", "المشروع", pr.code),
        ("Contractor", "المقاول", eng.get("short_code") or "—"),
        ("ITP", "الخطة", itps.display_no(it) if it else "—"),
        ("Points", "النقاط", ", ".join(f"{s}" for s in ir.point_seqs)),
        (
            "Governing point type",
            "نوع النقطة الحاكم",
            label("point_type", ir.governing_type),
            label("point_type", ir.governing_type, True),
        ),
        ("Location", "الموقع", ir.location_ref),
        ("Status", "الحالة", label("ir_status", ir.status), label("ir_status", ir.status, True)),
        (
            "Proposed",
            "الموعد المقترح",
            ir.proposed_at.strftime("%Y-%m-%d %H:%M") if ir.proposed_at else "—",
        ),
        ("Issue date", "تاريخ الإصدار", issued.isoformat()),
        (
            "Issue date (Hijri, Umm al-Qura)",
            "تاريخ الإصدار الهجري، أم القرى",
            hijri_en(issued),
            hijri_ar(issued),
        ),
    ]
    pcols = [
        ("seq", "Point", "النقطة"),
        ("type", "Type", "النوع"),
        ("activity", "Activity", "النشاط"),
        ("check", "Characteristic", "الخاصية"),
        ("crit", "Criteria", "المعايير"),
    ]
    prow = [
        {
            "seq": str(x["seq"]),
            "type": x["point_type"].value,
            "activity": x["activity_en"],
            "check": x["characteristic_en"],
            "crit": ", ".join(c["code"] for c in x["criteria"]) or (x["acceptance_text_en"] or ""),
        }
        for x in r["points"]
    ]
    prow_ar = [
        {
            **row,
            "type": label("point_type", x["point_type"], True),
            "activity": x["activity_ar"] or x["activity_en"],
            "check": x["characteristic_ar"] or x["characteristic_en"],
        }
        for row, x in zip(prow, r["points"], strict=True)
    ]
    sections = [
        render.Section(
            "points",
            "ITP points",
            "نقاط الخطة",
            tables=[render.Table(pcols, prow, rows_ar=prow_ar)],
        )
    ]
    for rd in r["rounds"]:
        paras_en = [
            f"Round {rd['round_no']}: "
            f"{label('ir_result', rd['result']) if rd['result'] else 'not decided'}"
            + (
                f"; review {label('ir_result', rd['review_result'])}" if rd["review_result"] else ""
            ),
            f"Scheduled {rd['scheduled_at']:%Y-%m-%d %H:%M}"
            if rd["scheduled_at"]
            else "Not scheduled",
        ]
        paras_ar = [
            f"الجولة {rd['round_no']}: "
            f"{label('ir_result', rd['result'], True) if rd['result'] else 'لم يُتخذ قرار'}",
            f"موعد الفحص {rd['scheduled_at']:%Y-%m-%d %H:%M}" if rd["scheduled_at"] else "لم يُجدول",
        ]
        if rd["comment"]:
            paras_en.append(f"Comment: {rd['comment']}")
            paras_ar.append(f"الملاحظة: {rd['comment']}")
        tables = []
        if rd["measurements"]:
            mcols = [
                ("name", "Measurement", "القياس"),
                ("value", "Value", "القيمة"),
                ("crit", "Criterion", "المعيار"),
                ("verdict", "Verdict", "النتيجة"),
                ("mte", "M&TE", "جهاز القياس"),
                ("due", "Calibration due", "استحقاق المعايرة"),
            ]
            mrows = [
                {
                    "name": m.get("name") or "",
                    "value": f"{m.get('value') or ''} {m.get('unit') or ''}".strip(),
                    "crit": f"{m.get('criterion_code') or ''} v{m.get('criterion_version')}"
                    if m.get("criterion_code")
                    else "",
                    "verdict": label("verdict", m["verdict"]) if m.get("verdict") else "",
                    "mte": m.get("mte_no") or "",
                    "due": m.get("mte_cal_due_on") or "",
                }
                for m in rd["measurements"]
            ]
            mrows_ar = [
                {**row, "verdict": label("verdict", m["verdict"], True) if m.get("verdict") else ""}
                for row, m in zip(mrows, rd["measurements"], strict=True)
            ]
            tables.append(
                render.Table(
                    mcols, mrows, title_en="Measurements", title_ar="القياسات", rows_ar=mrows_ar
                )
            )
        for resp in rd["responses"]:
            acols = [
                ("item", "Item", "البند"),
                ("text", "Check", "الفحص"),
                ("answer", "Answer", "الإجابة"),
                ("note", "Note", "ملاحظة"),
            ]
            arows = [
                {
                    "item": a["item_code"],
                    "text": (a["text_en"] or "")[:60],
                    "answer": a["answer"] or a.get("numeric_value") or "",
                    "note": a["note"] or "",
                }
                for a in resp.get("answers") or []
            ]
            arows_ar = [
                {**row, "text": (a["text_ar"] or a["text_en"] or "")[:60]}
                for row, a in zip(arows, resp.get("answers") or [], strict=True)
            ]
            tables.append(
                render.Table(
                    acols,
                    arows,
                    title_en=f"Checklist {resp.get('template_code')} (point {resp['seq']})",
                    title_ar=f"قائمة الفحص {resp.get('template_code')} (النقطة {resp['seq']})",
                    rows_ar=arows_ar,
                )
            )
        sections.append(
            render.Section(
                f"round{rd['round_no']}",
                f"Round {rd['round_no']}",
                f"الجولة {rd['round_no']}",
                tables=tables,
                paragraphs_en=paras_en,
                paragraphs_ar=paras_ar,
            )
        )
    if not q1c.viewer(p, ir.project_id):
        scols = [
            ("step", "Step", "الخطوة"),
            ("decision", "Decision", "القرار"),
            ("by", "Signed", "التوقيع"),
            ("at", "Date", "التاريخ"),
        ]
        srows = [
            {
                "step": s["step"],
                "decision": label("ir_result", s["decision"]),
                "by": s["text_en"],
                "at": s["signed_at"].date().isoformat(),
            }
            for s in r["signoffs"]
        ]
        srows_ar = [
            {**x, "decision": label("ir_result", s["decision"], True), "by": s["text_ar"]}
            for x, s in zip(srows, r["signoffs"], strict=True)
        ]
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
    digest = hashlib.sha256(
        json.dumps([control, [s.key for s in sections]], default=str).encode()
    ).hexdigest()
    d = render.Doc(
        doc_no=ir.ir_no or "IR-DRAFT",
        revision=ir.current_round,
        title_en=f"Inspection Request {ir.ir_no or ''}".strip(),
        title_ar=f"طلب فحص {ir.ir_no or ''}".strip(),
        snapshot_hash=digest,
        control=control,
        sections=sections,
    )
    return d, ir.ir_no or "IR-DRAFT"


def pdf(db: Session, p: Principal, ir_id: uuid.UUID, lang: str) -> tuple[bytes, str]:
    d, no = doc(db, p, ir_id)
    return render.pdf(d, lang), f"{no}-{lang.upper()}.pdf"


def text_of(db: Session, p: Principal, ir_id: uuid.UUID, lang: str) -> list[str]:
    """The texts printed on the form (tests check the Arabic content without parsing the PDF)."""
    d, _ = doc(db, p, ir_id)
    ar = lang == "ar"
    out: list[Any] = [x[3] if ar and len(x) > 3 else x[2] for x in d.control]
    for s in d.sections:
        out += s.paragraphs_ar if ar else s.paragraphs_en
        for t in s.tables:
            for row in (t.rows_ar or t.rows) if ar else t.rows:
                out += [str(v) for v in row.values()]
    return [str(x) for x in out]
