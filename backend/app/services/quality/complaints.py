"""Customer complaints (spec 8-quality §A.10.3, Q-CMP-01 / -02): Received → Acknowledged →
Under Investigation → Responded (RPM `complaint.response`; a justified complaint links an NCR,
`NCR_REQUIRED_FOR_JUSTIFIED`) → Closed (RPM `complaint.close`; satisfaction recorded or "no reply"
after 14 days); Received / Acknowledged / Under Investigation → Withdrawn. Acknowledgement is due
within `complaint_ack_hours` and the response within `complaint_response_days` of receipt;
overdue alerts the 245 and 239 holders."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import CaSourceType
from app.core.quality.common import (
    QComplaintChannel,
    QComplaintSeverity,
    QComplaintStatus,
    QJustified,
    QNcrCategory,
    QNcrSourceType,
    QNcrStatus,
    QRecordType,
    QSatisfaction,
)
from app.models import Project
from app.models.quality import QComplaint, QCustomer, QNcr
from app.services import audit
from app.services.common import invalid_transition, paginate
from app.services.hse_common import id_warnings
from app.services.permissions import Principal, deny
from app.services.quality import common as qc
from app.services.quality import links, numbering, rpm, signoff
from app.services.quality import settings as qs

C = Capability
CS = QComplaintStatus
RT = QRecordType.complaint


def get_complaint(db: Session, p: Principal, cid: uuid.UUID) -> QComplaint:
    c = db.get(QComplaint, cid)
    ok = (
        c is not None
        and p.can_see_project(c.project_id)
        and (
            p.grant(c.project_id, C.complaint_manage) is not None
            or p.grant(c.project_id, C.quality_view) is not None
        )
    )
    if c is None or not ok:
        raise deny(db, p, EntityType.q_complaint, cid, c.project_id if c else None, "Complaint")
    return c


def deadlines(db: Session, c: QComplaint) -> tuple[datetime, datetime]:
    ack_h = int(qs.value(db, c.project_id, "complaint_ack_hours"))
    resp_d = int(qs.value(db, c.project_id, "complaint_response_days"))
    return c.received_at + timedelta(hours=ack_h), c.received_at + timedelta(days=resp_d)


def read(db: Session, p: Principal, c: QComplaint) -> dict[str, Any]:
    cust = db.get(QCustomer, c.customer_id)
    ncr = db.get(QNcr, c.ncr_id) if c.ncr_id else None
    ack_due, resp_due = deadlines(db, c)
    at = now()
    from app.services.quality.ncr import capa  # noqa: PLC0415

    return {
        "id": c.id,
        "project_id": c.project_id,
        "complaint_no": c.complaint_no,
        "customer": {
            "id": cust.id,
            "code": cust.code,
            "name_en": cust.name_en,
            "name_ar": cust.name_ar,
        }
        if cust
        else None,
        "site_id": c.site_id,
        "received_at": c.received_at,
        "channel": c.channel,
        "customer_reference": c.customer_reference,
        "category": c.category,
        "description": c.description,
        "product_refs": c.product_refs,
        "severity": c.severity,
        "acknowledged_at": c.acknowledged_at,
        "ack_method": c.ack_method,
        "ack_due_at": ack_due,
        "ack_overdue": c.acknowledged_at is None and c.status == CS.received and at > ack_due,
        "response_due_at": resp_due,
        "response_overdue": c.responded_at is None
        and c.status in (CS.received, CS.acknowledged, CS.under_investigation)
        and at > resp_due,
        "investigation_note": c.investigation_note,
        "justified": c.justified,
        "ncr": {"id": ncr.id, "ncr_no": ncr.ncr_no, "status": ncr.status} if ncr else None,
        "response_en": c.response_en,
        "response_ar": c.response_ar,
        "responded_at": c.responded_at,
        "satisfied": c.satisfied,
        "closed_at": c.closed_at,
        "status": c.status,
        "status_reason": c.status_reason,
        "actions": capa.summary(db, CaSourceType.quality_complaint, c.id),
        "signoffs": [signoff.read(db, s) for s in signoff.signoffs_for(db, RT, c.id)],
        "links": links.links_for(db, p, RT, c.id),
    }


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.require_profile(db, project)
    p.require(project.id, C.complaint_manage)
    cust = db.get(QCustomer, body["customer_id"])
    if cust is None or cust.project_id != project.id:
        raise qc.field_err("customer_id", "The customer is not on this project.")
    received = body.get("received_at") or now()
    c = QComplaint(
        project_id=project.id,
        complaint_no=numbering.assign(db, project, RT, on=qc.project_day(project, received)),
        customer_id=cust.id,
        site_id=body.get("site_id"),
        received_at=received,
        channel=QComplaintChannel(body["channel"]),
        customer_reference=body.get("customer_reference"),
        category=QNcrCategory(body["category"]),
        description=body["description"].strip(),
        product_refs=body.get("product_refs"),
        severity=QComplaintSeverity(body["severity"]),
        status=CS.received,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_complaint,
        entity_id=c.id,
        project_id=project.id,
        after={"complaint_no": c.complaint_no},
    )
    out = read(db, p, c)
    out["warnings"] = [w.model_dump() for w in id_warnings(description=c.description)]
    return out


def _move(db: Session, p: Principal, c: QComplaint, to: QComplaintStatus, **details: Any) -> None:
    src = c.status
    c.status = to
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(c.project_id),
        entity_type=EntityType.q_complaint,
        entity_id=c.id,
        project_id=c.project_id,
        before={"status": src},
        after={"status": to},
        details=details or None,
    )


def transition(
    db: Session, p: Principal, cid: uuid.UUID, to: QComplaintStatus, body: dict[str, Any]
) -> dict[str, Any]:
    c = get_complaint(db, p, cid)
    project: Project = qc.get_project(db, p, c.project_id)
    qc.writable(project, p)
    p.require(project.id, C.complaint_manage)
    src = c.status
    edges = {
        (CS.received, CS.acknowledged),
        (CS.acknowledged, CS.under_investigation),
        (CS.under_investigation, CS.responded),
        (CS.responded, CS.closed),
        (CS.received, CS.withdrawn),
        (CS.acknowledged, CS.withdrawn),
        (CS.under_investigation, CS.withdrawn),
    }
    if (src, to) not in edges:
        raise invalid_transition("Complaint", src, to)
    requesters = qc.ids(c.created_by_user_id)
    if to == CS.acknowledged:
        c.acknowledged_at = body.get("acknowledged_at") or now()
        c.ack_method = body.get("ack_method") or "email"
    elif to == CS.under_investigation:
        c.investigation_note = body.get("investigation_note") or c.investigation_note
    elif to == CS.responded:
        if body.get("justified"):
            c.justified = QJustified(body["justified"])
        if body.get("ncr_id"):
            ncr = db.get(QNcr, body["ncr_id"])
            if ncr is None or ncr.project_id != c.project_id or ncr.status == QNcrStatus.voided:
                raise qc.field_err("ncr_id", "The NCR is not on this project.")
            c.ncr_id = ncr.id
        for k in ("response_en", "response_ar", "investigation_note"):
            if body.get(k):
                setattr(c, k, body[k].strip())
        if c.justified is None:
            raise qc.field_err("justified", "Record whether the complaint is justified.")
        if not qc.text_of(c.response_en, c.response_ar):
            raise qc.field_err("response_en", "Write the response to the customer.")
        if c.justified in (QJustified.yes, QJustified.partly) and c.ncr_id is None:
            raise qc.err(
                422,
                ErrorCode.NCR_REQUIRED_FOR_JUSTIFIED,
                "A justified complaint is linked to an NCR (source complaint, detection "
                "at_customer).",
                "يجب ربط الشكوى المبررة بتقرير عدم مطابقة.",
            )
        rule, capacity = rpm.check_signer(
            db, p, project, RT, "response", rpm.Ctx(c.site_id, None, requesters), record_id=c.id
        )
        signoff.sign(
            db, p, project, RT, c.id, "response", "approved", body.get("comment"), rule, capacity
        )
        c.responded_at = now()
    elif to == CS.closed:
        sat = body.get("satisfied")
        if sat is None:
            raise qc.field_err("satisfied", "Record the customer's satisfaction.")
        c.satisfied = QSatisfaction(sat)
        if (
            c.satisfied == QSatisfaction.no_reply
            and c.responded_at
            and now() < c.responded_at + timedelta(days=14)
        ):
            raise qc.field_err(
                "satisfied", '"No reply" may be recorded 14 days after the response.'
            )
        rule, capacity = rpm.check_signer(
            db, p, project, RT, "close", rpm.Ctx(c.site_id, None, requesters), record_id=c.id
        )
        signoff.sign(
            db, p, project, RT, c.id, "close", "approved", body.get("comment"), rule, capacity
        )
        c.closed_at = now()
    else:
        c.status_reason = qc.reason(body.get("reason"), 10)
    _move(db, p, c, to)
    return read(db, p, c)


def raise_ncr(db: Session, p: Principal, cid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """An NCR from a justified complaint (source `complaint`, detection `at_customer`)."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    c = get_complaint(db, p, cid)
    n, warnings = core.create(
        db,
        p,
        c.project_id,
        {
            **body,
            "source_type": QNcrSourceType.complaint.value,
            "source_id": c.id,
        },
    )
    c.ncr_id = n.id
    db.flush()
    return core.read(db, p, n, warnings)


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[QComplaintStatus] | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    if p.grant(project.id, C.complaint_manage) is None:
        p.require(project.id, C.quality_view)
    stmt = select(QComplaint).where(QComplaint.project_id == project.id)
    if statuses:
        stmt = stmt.where(QComplaint.status.in_(statuses))
    items, total = paginate(db, stmt.order_by(QComplaint.received_at.desc()), page, page_size)
    return {
        "items": [read(db, p, c) for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def overdue_alerts(db: Session, at: datetime) -> int:
    """Q-CMP-01: at the deadline, the 245 and 239 holders (each deadline once)."""
    sent = 0
    for c in db.scalars(
        select(QComplaint).where(
            QComplaint.status.in_([CS.received, CS.acknowledged, CS.under_investigation])
        )
    ):
        project = db.get(Project, c.project_id)
        if project is None:
            continue
        ack_due, resp_due = deadlines(db, c)
        who = set(qc.holders_of(db, project, C.complaint_manage, include_manager=False))
        who |= set(qc.holders_of(db, project, C.quality_settings, include_manager=False))
        if c.status == CS.received and c.acknowledged_at is None and at >= ack_due:
            sent += qc.send(
                db,
                who,
                f"{c.complaint_no}: acknowledgement overdue",
                f"{c.complaint_no}: تأخر الإقرار بالشكوى",
                entity_type=EntityType.q_complaint,
                entity_id=c.id,
                project_id=c.project_id,
                key=f"complaint_ack:{c.id}",
                path=f"/quality/complaints/{c.id}",
            )
        if c.responded_at is None and at >= resp_due:
            sent += qc.send(
                db,
                who,
                f"{c.complaint_no}: response overdue",
                f"{c.complaint_no}: تأخر الرد على الشكوى",
                entity_type=EntityType.q_complaint,
                entity_id=c.id,
                project_id=c.project_id,
                key=f"complaint_resp:{c.id}",
                path=f"/quality/complaints/{c.id}",
            )
    return sent


def get_row(db: Session, cid: uuid.UUID) -> QComplaint:
    c = db.get(QComplaint, cid)
    if c is None:
        raise not_found("Complaint")
    return c
