"""Returns inspection (spec 8-quality §D.7.4, Q-STK-08): customer returns with condition grades
A–D; a temperature-controlled line without temperature history cannot be graded A
(`COLD_RETURN_NO_HISTORY`); grades are confirmed through the matrix (`return.disposition`) and a
grade C line goes on hold for the owner's decision."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QDetectionStage, QNcrClass, QRecordType
from app.core.quality.q3 import TEMP_CONTROLLED, QHoldReason, QReturnGrade, QReturnStatus
from app.models import Project
from app.models.field import ChecklistResponse
from app.models.quality.q3 import QProduct, QReturn, QReturnLine
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b
from app.services.quality.q3 import checklists
from app.services.quality.q3 import holds as hold_svc

C = Capability
RT = QRecordType.return_
ST = QReturnStatus
A = AttachmentOwner


def ctx(r: QReturn) -> rpm.Ctx:
    return rpm.Ctx(site_id=r.site_id, requesters=qc.ids(r.created_by_user_id))


def get_return(db: Session, p: Principal, rid: uuid.UUID) -> tuple[QReturn, Project]:
    r = db.get(QReturn, rid)
    if r is None or not p.can_see_project(r.project_id):
        raise b.not_found(db, p, RT, rid, r.project_id if r else None)
    project = qc.get_project(db, p, r.project_id)
    if not b.can_view(
        db,
        p,
        project,
        RT,
        r.id,
        r.site_id,
        lambda: [("disposition", ctx(r), None)] if r.status == ST.graded else [],
    ):
        raise b.not_found(db, p, RT, rid, project.id)
    return r, project


def lines_of(db: Session, r: QReturn) -> list[QReturnLine]:
    return list(
        db.scalars(
            select(QReturnLine).where(QReturnLine.return_id == r.id).order_by(QReturnLine.id)
        )
    )


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.stock_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    cust = b.customer_of(db, project, body["customer_id"])
    if not body.get("lines"):
        raise qc.field_err("lines", "Add the returned lines.", "أضف البنود المرتجعة.")
    at = body.get("received_at") or now()
    r = QReturn(
        id=uuid.uuid4(),
        project_id=project.id,
        ret_no=b.number(db, project, RT, at),
        site_id=site.id,
        customer_id=cust.id,
        rma_ref=body.get("rma_ref"),
        received_at=at,
        reason=body.get("reason"),
        status=ST.draft,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    for raw in body["lines"]:
        prod = db.get(QProduct, raw["product_id"])
        if prod is None or prod.project_id != project.id:
            raise qc.field_err("lines", "A product is not on this project.", "منتج ليس في المشروع.")
        db.add(
            QReturnLine(
                return_id=r.id,
                product_id=prod.id,
                batch=raw["batch"],
                qty=Decimal(str(raw["qty"])),
                unit=raw.get("unit") or "unit",
                temp_history=bool(raw.get("temp_history")),
            )
        )
    db.flush()
    return read(db, p, r)


def inspection(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    r, project = get_return(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.stock_record)
    b.require_site(g, r.site_id)
    out = checklists.respond(
        db,
        p.user.id,
        project,
        ResponseOwnerType.q_return,
        "return_inspection",
        r.site_id,
        body["answers"],
    )
    r.response_id = out.response.id
    return read(db, p, r)


def grade(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    r, project = get_return(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.stock_record)
    b.require_site(g, r.site_id)
    if r.status == ST.confirmed:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "The grades are confirmed.", "التصنيف مؤكد."
        )
    by_id = {ln.id: ln for ln in lines_of(db, r)}
    for raw in body.get("lines") or []:
        ln = by_id.get(raw["line_id"])
        if ln is None:
            raise qc.field_err("lines", "A line is not on this return.", "بند ليس في هذا المرتجع.")
        if "temp_history" in raw and raw["temp_history"] is not None:
            ln.temp_history = bool(raw["temp_history"])
        if raw.get("temp_history_attachment_id"):
            ln.temp_history_attachment_id = b.attachment_on(
                db,
                raw["temp_history_attachment_id"],
                A.q_return,
                r.id,
                "temp_history_attachment_id",
            )
            ln.temp_history = True
        gr = QReturnGrade(raw["grade"])
        prod = db.get(QProduct, ln.product_id)
        if (
            gr == QReturnGrade.A
            and prod is not None
            and prod.storage_class in TEMP_CONTROLLED
            and not ln.temp_history
        ):
            raise qc.err(
                422,
                ErrorCode.COLD_RETURN_NO_HISTORY,
                f"{prod.sku} {ln.batch}: a temperature-controlled return without temperature "
                "history cannot be graded A (Q-STK-08).",
                f"{prod.sku} {ln.batch}: لا يمكن تصنيف مرتجع مبرد بلا سجل حرارة بالدرجة أ.",
            )
        ln.grade = gr
        ln.note = raw.get("note")
    if all(ln.grade is not None for ln in by_id.values()):
        r.status = ST.graded
    db.flush()
    return read(db, p, r)


def confirm(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Graded → Confirmed (`return.disposition`); grade C lines go on hold (owner decision)."""
    r, project = get_return(db, p, rid)
    project, _ = b.project_for_progress(db, p, project.id, C.stock_record, allow_n=True)
    if r.status != ST.graded:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Grade every line first.", "صنّف كل البنود أولاً."
        )
    s = b.sign(db, p, project, RT, r.id, "disposition", ctx(r), comment=body.get("comment"))
    held = [ln for ln in lines_of(db, r) if ln.grade == QReturnGrade.C]
    if held:
        h = hold_svc.place(
            db,
            project,
            site_id=r.site_id,
            reason=QHoldReason.owner_request,
            lines=[
                {
                    "product_id": ln.product_id,
                    "batch": ln.batch,
                    "qty": ln.qty,
                    "unit": ln.unit,
                    "owner_customer_id": r.customer_id,
                    "location": "RETURNS",
                }
                for ln in held
            ],
            placed_by=p.user.id,
            source=(RT, r.id, r.ret_no),
            note="Return grade C: hold for the owner's decision",
            p=p,
        )
        r.hold_id = h.id
    r.status = ST.confirmed
    r.confirmed_at = now()
    b.audit_status(db, p, project, RT, r.id, ST.graded, ST.confirmed, signoff=str(s.id))
    return read(db, p, r)


def read(db: Session, p: Principal, r: QReturn) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, project.id)
    resp = db.get(ChecklistResponse, r.response_id) if r.response_id else None
    out_lines = []
    for ln in lines_of(db, r):
        prod = db.get(QProduct, ln.product_id)
        out_lines.append(
            {
                "id": ln.id,
                "product": {
                    "id": prod.id,
                    "sku": prod.sku,
                    "description_en": prod.description_en,
                    "description_ar": prod.description_ar,
                    "storage_class": prod.storage_class,
                }
                if prod
                else None,
                "batch": ln.batch,
                "qty": ln.qty,
                "unit": ln.unit,
                "temp_history": ln.temp_history,
                "temp_history_attachment_id": ln.temp_history_attachment_id,
                "grade": ln.grade,
                "note": ln.note,
            }
        )
    return {
        "id": r.id,
        "ret_no": r.ret_no,
        "site_id": r.site_id,
        "customer": b.customer_ref(db, r.customer_id),
        "rma_ref": r.rma_ref,
        "received_at": r.received_at,
        "reason": r.reason,
        "status": r.status,
        "inspection": checklists.response_read(resp),
        "lines": out_lines,
        "hold_id": r.hold_id,
        "can_confirm": r.status == ST.graded
        and b.resolves(db, p, project, RT, r.id, "disposition", ctx(r)),
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, r.id)
        ],
    }


def list_returns(
    db: Session, p: Principal, project_id: uuid.UUID, page_no: int, size: int
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    items = []
    for r in db.scalars(
        select(QReturn)
        .where(QReturn.project_id == project.id)
        .order_by(QReturn.received_at.desc())
        .limit(1000)
    ):
        if g.scope.value == "responsible":
            if not b.can_view(
                db,
                p,
                project,
                RT,
                r.id,
                r.site_id,
                lambda r=r: [("disposition", ctx(r), None)] if r.status == ST.graded else [],
            ):
                continue
        elif not g.covers_site(r.site_id):
            continue
        ls = lines_of(db, r)
        items.append(
            {
                "id": r.id,
                "ret_no": r.ret_no,
                "customer": b.customer_ref(db, r.customer_id),
                "rma_ref": r.rma_ref,
                "received_at": r.received_at,
                "status": r.status,
                "lines": len(ls),
                "grades": sorted({ln.grade.value for ln in ls if ln.grade}),
            }
        )
    return b.page(items, page_no, size)


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    return [
        reg.OpenStep(
            reg.PendingStep(
                RT,
                r.id,
                project.id,
                r.ret_no,
                f"Return {r.rma_ref or ''}",
                "disposition",
                r.updated_at,
                f"/quality/returns/{r.id}",
                "Q3",
            ),
            None,
            r.site_id,
            None,
            ctx(r).requesters,
        )
        for r in db.scalars(
            select(QReturn).where(QReturn.project_id == project.id, QReturn.status == ST.graded)
        )
    ]


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    r = db.get(QReturn, source_id)
    if r is None or r.project_id != project.id:
        raise qc.field_err(
            "source_id", "The return is not on this project.", "المرتجع ليس في المشروع."
        )
    return reg.SourceInfo(
        ref=r.ret_no,
        title=f"Return inspection — {r.ret_no}",
        site_id=r.site_id,
        engagement_id=b.operator_engagement(db, project),
        customer_id=r.customer_id,
        item_key=f"RET:{r.customer_id}",
        detection_stage=QDetectionStage.at_customer,
        requirement_en="Returned goods inspected and graded before restocking.",
        requirement_ar="فحص المرتجعات وتصنيفها قبل إعادة التخزين.",
        finding_en=r.reason or "Return inspection finding.",
        finding_ar=r.reason or "ملاحظة فحص مرتجع.",
        proposed_class=QNcrClass.minor,
        record_type=RT,
    )
