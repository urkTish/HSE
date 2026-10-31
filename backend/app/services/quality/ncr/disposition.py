"""Disposition lines (spec 8-quality Q-NCR-11): the lines cover the affected quantity (Σ = NCR
quantity when one is given, `DISPOSITION_QTY_MISMATCH`); `use_as_is` and `repair` need a
justification ≥ 50 characters and ≥ 1 evidence file (`CONCESSION_EVIDENCE_REQUIRED`); `repair`
names the repair procedure; `reject_return` names the return note or claim no. and `reject_scrap`
has destruction evidence by closure (checked at close, Q-NCR-15)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import CONCESSION_DISPOSITIONS, QDisposition, QNcrStatus
from app.models.quality import QNcr, QNcrLine
from app.services.common import invalid_transition
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.ncr import core

ST = QNcrStatus


def check(db: Session, n: QNcr, lines: list[QNcrLine], final: bool) -> None:
    if not lines:
        if final:
            raise qc.field_err(
                "lines", "Give at least one disposition line.", "أدخل بند معالجة واحداً على الأقل."
            )
        return
    if n.quantity is not None:
        total = sum((x.quantity or Decimal(0)) for x in lines)
        if total != n.quantity:
            raise qc.err(
                422,
                ErrorCode.DISPOSITION_QTY_MISMATCH,
                f"The lines cover {total} {n.unit or ''}; the NCR quantity is {n.quantity} "
                f"{n.unit or ''} (Q-NCR-11).",
                "مجموع كميات بنود المعالجة لا يساوي كمية التقرير.",
                lines_total=str(total),
                quantity=str(n.quantity),
            )
    if any(x.disposition in CONCESSION_DISPOSITIONS for x in lines):
        just = qc.text_of(n.disposition_justification_en, n.disposition_justification_ar)
        evidence = core.evidence_count(db, n, (AttachmentOwner.q_ncr_evidence,))
        if len(just) < 50 or evidence == 0:
            raise qc.err(
                422,
                ErrorCode.CONCESSION_EVIDENCE_REQUIRED,
                "Use as is and repair need a justification of at least 50 characters and at least "
                "one evidence file (calculation, core results, stability data) (Q-NCR-11).",
                "يتطلب الاستخدام كما هو والإصلاح مبرراً لا يقل عن 50 حرفاً وملف دليل واحداً على "
                "الأقل.",
            )
    for x in lines:
        if x.disposition == QDisposition.repair and not (x.repair_procedure or "").strip():
            raise qc.field_err(
                "repair_procedure",
                "A repair line names the repair procedure.",
                "يجب ذكر إجراء الإصلاح.",
            )


def save(db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]) -> QNcr:
    n = core.get_ncr(db, p, ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status != ST.open:
        raise invalid_transition("NCR", n.status, "disposition")
    core._manager_grant(p, n)
    for k in ("disposition_justification_en", "disposition_justification_ar"):
        if k in body:
            setattr(n, k, (body[k] or "").strip() or None)
    for old in core.lines_of(db, n):
        db.delete(old)
    db.flush()
    new: list[QNcrLine] = []
    for i, raw in enumerate(body.get("lines") or []):
        qty = raw.get("quantity")
        line = QNcrLine(
            ncr_id=n.id,
            disposition=QDisposition(raw["disposition"]),
            quantity=Decimal(str(qty)) if qty is not None else None,
            note=raw.get("note"),
            repair_procedure=raw.get("repair_procedure"),
            return_ref=raw.get("return_ref"),
            destruction_evidenced=bool(raw.get("destruction_evidenced", False)),
            position=i,
            created_by_user_id=p.user.id,
        )
        if line.quantity is not None and line.quantity <= 0:
            raise qc.field_err("lines.quantity", "Line quantities must be positive.")
        new.append(line)
    check(db, n, new, final=False)
    for line in new:
        db.add(line)
    n.updated_by_user_id = p.user.id
    db.flush()
    core._audit(
        db,
        p,
        n,
        AuditAction.update,
        after={"disposition_lines": [f"{x.disposition.value}:{x.quantity}" for x in new]},
    )
    return n


def update_line(db: Session, p: Principal, line_id: uuid.UUID, body: dict[str, Any]) -> QNcr:
    """Evidence of a reject line after approval (return note / claim no., destruction)."""
    line = db.get(QNcrLine, line_id)
    if line is None:
        raise not_found("Disposition line")
    n = core.get_ncr(db, p, line.ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status not in (ST.open, ST.disposition_approved, ST.pending_verification):
        raise invalid_transition("NCR", n.status, "line evidence")
    core._manager_grant(p, n)
    if "return_ref" in body:
        line.return_ref = (body["return_ref"] or "").strip() or None
    if body.get("destruction_evidenced") is not None:
        if (
            body["destruction_evidenced"]
            and core.evidence_count(db, n, (AttachmentOwner.q_ncr_evidence,)) == 0
        ):
            raise qc.field_err(
                "destruction_evidenced",
                "Attach the destruction evidence first.",
                "أرفق دليل الإتلاف أولاً.",
            )
        line.destruction_evidenced = bool(body["destruction_evidenced"])
    if body.get("note") is not None:
        line.note = body["note"]
    db.flush()
    core._audit(
        db,
        p,
        n,
        AuditAction.update,
        after={
            "line": str(line.id),
            "return_ref": line.return_ref,
            "destruction_evidenced": line.destruction_evidenced,
        },
    )
    return n
