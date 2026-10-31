"""Supplier master (spec 8-quality §A.8.2, Q-SHR-01…03): org-wide like contractors; register
278, approve / suspend / disqualify 279 with the responsible-person steps `supplier.approve` and
`supplier.suspend` resolved on the project named in the request (the matrix is per project).
Q4 adds evaluations and scorecards and a `SUPPLIER_GATES` blocker. Contacts are personal (P8-2):
shown to 278 holders only."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.quality.common import (
    SUPPLIER_USABLE,
    QAccreditationBody,
    QAccreditationStandard,
    QRecordType,
    QSupplierCategory,
    QSupplierStatus,
)
from app.core.text import normalize, search_blob
from app.models import Contractor
from app.models.quality import QSupplier, QSupplierAccreditation
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import duplicate, paginate
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm, signoff

C = Capability
SS = QSupplierStatus
CONTACT = ("contact_name", "contact_mobile", "contact_email")
FIELDS = (
    "legal_name_en",
    "legal_name_ar",
    "cr_number",
    "vat_number",
    "country",
    "contractor_id",
    "tpi_id",
    "scope_en",
    "scope_ar",
    "approved_scope",
    *CONTACT,
)


def _contacts(p: Principal) -> bool:
    return p.has_any(C.supplier_manage)


def _view(p: Principal) -> None:
    if not (p.has_any(C.quality_view) or p.has_any(C.supplier_manage)):
        raise forbidden_error()


def acc_read(a: QSupplierAccreditation, on: date) -> dict[str, Any]:
    return {
        "id": a.id,
        "body": a.body,
        "standard": a.standard,
        "number": a.number,
        "scope_text": a.scope_text,
        "scope_codes": list(a.scope_codes or []),
        "valid_from": a.valid_from,
        "valid_until": a.valid_until,
        "valid": (a.valid_from is None or a.valid_from <= on) and a.valid_until >= on,
    }


def read(db: Session, p: Principal | None, s: QSupplier, on: date | None = None) -> dict[str, Any]:
    day = on or today()
    contacts = p is None or _contacts(p)
    accs = list(
        db.scalars(select(QSupplierAccreditation).where(QSupplierAccreditation.supplier_id == s.id))
    )
    contractor = db.get(Contractor, s.contractor_id) if s.contractor_id else None
    return {
        "id": s.id,
        "supplier_code": s.supplier_code,
        "legal_name_en": s.legal_name_en,
        "legal_name_ar": s.legal_name_ar,
        "cr_number": s.cr_number,
        "vat_number": s.vat_number,
        "country": s.country,
        "categories": list(s.categories or []),
        "contractor_id": s.contractor_id,
        "contractor_code": contractor.short_code if contractor else None,
        "tpi_id": s.tpi_id,
        "scope_en": s.scope_en,
        "scope_ar": s.scope_ar,
        **{k: (getattr(s, k) if contacts else None) for k in CONTACT},
        "contacts_visible": contacts,
        "status": s.status,
        "status_reason": s.status_reason,
        "status_changed_at": s.status_changed_at,
        "approved_scope": s.approved_scope,
        "next_evaluation_due": s.next_evaluation_due,
        "accreditations": [acc_read(a, day) for a in accs],
    }


def list_page(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    *,
    statuses: list[QSupplierStatus] | None = None,
    category: QSupplierCategory | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    _view(p)
    stmt = select(QSupplier)
    if statuses:
        stmt = stmt.where(QSupplier.status.in_(statuses))
    if category:
        stmt = stmt.where(QSupplier.categories.contains([category.value]))
    if q:
        stmt = stmt.where(QSupplier.search_text.ilike(f"%{normalize(q)}%"))
    items, total = paginate(db, stmt.order_by(QSupplier.supplier_code), page, page_size)
    return {
        "items": [read(db, p, s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get(db: Session, supplier_id: uuid.UUID) -> QSupplier:
    s = db.get(QSupplier, supplier_id)
    if s is None:
        raise not_found("Supplier")
    return s


def read_one(db: Session, p: Principal, supplier_id: uuid.UUID) -> dict[str, Any]:
    _view(p)
    return read(db, p, get(db, supplier_id))


def _apply(db: Session, s: QSupplier, body: dict[str, Any]) -> None:
    for k in FIELDS:
        if k in body and body[k] is not None:
            setattr(s, k, body[k])
    if body.get("categories") is not None:
        cats = [QSupplierCategory(c).value for c in body["categories"]]
        if not cats:
            raise qc.field_err("categories", "At least one category is required.")
        s.categories = cats
    if s.cr_number and not re.fullmatch(r"[1-7]\d{9}", s.cr_number):
        raise qc.field_err("cr_number", "CR number: 10 digits starting 1–7.")
    if s.contractor_id and db.get(Contractor, s.contractor_id) is None:
        raise qc.field_err("contractor_id", "Unknown contractor.")
    s.legal_name_en_norm = normalize(s.legal_name_en)
    s.legal_name_ar_norm = normalize(s.legal_name_ar)
    clash = db.scalar(
        select(QSupplier.id).where(
            QSupplier.id != s.id,
            or_(
                QSupplier.legal_name_en_norm == s.legal_name_en_norm,
                QSupplier.legal_name_ar_norm == s.legal_name_ar_norm,
            ),
        )
    )
    if clash:
        raise duplicate("legal_name_en", "A supplier with this legal name exists.")
    s.search_text = search_blob(s.supplier_code, s.legal_name_en, s.legal_name_ar, s.cr_number)


def create(db: Session, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
    p.require_any(C.supplier_manage)
    code = str(body["supplier_code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,12}", code):
        raise qc.field_err("supplier_code", "Code: 2–12 capital letters, digits or -.")
    if db.scalar(select(QSupplier.id).where(QSupplier.supplier_code == code)):
        raise duplicate("supplier_code", "A supplier with this code exists.")
    s = QSupplier(
        id=uuid.uuid4(),
        supplier_code=code,
        status=SS.draft,
        country="SA",
        categories=[],
        created_by_user_id=p.user.id,
    )
    _apply(db, s, {"categories": body.get("categories") or [], **body})
    db.add(s)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(None),
        entity_type=EntityType.q_supplier,
        entity_id=s.id,
        after={"supplier_code": code},
    )
    return read(db, p, s)


def update(
    db: Session, p: Principal, supplier_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    p.require_any(C.supplier_manage)
    s = get(db, supplier_id)
    before = read(db, None, s)
    _apply(db, s, body)
    s.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(before, read(db, None, s))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(None),
            entity_type=EntityType.q_supplier,
            entity_id=s.id,
            before={k: v for k, v in b.items() if k not in CONTACT},
            after={k: v for k, v in a.items() if k not in CONTACT},
        )
    return read(db, p, s)


def add_accreditation(
    db: Session, p: Principal, supplier_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    p.require_any(C.supplier_manage)
    s = get(db, supplier_id)
    a = QSupplierAccreditation(
        supplier_id=s.id,
        body=QAccreditationBody(body["body"]),
        standard=QAccreditationStandard(body["standard"]),
        number=body["number"],
        scope_text=body.get("scope_text"),
        scope_codes=[str(x).upper() for x in body.get("scope_codes") or []],
        valid_from=body.get("valid_from"),
        valid_until=body["valid_until"],
        created_by_user_id=p.user.id,
    )
    if a.valid_from and a.valid_until < a.valid_from:
        raise qc.field_err("valid_until", "valid_until must be on or after valid_from.")
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(None),
        entity_type=EntityType.q_supplier,
        entity_id=s.id,
        details={"accreditation_added": a.number},
    )
    return read(db, p, s)


# ---- use on records (Q-SHR-02, Q-SHR-03) --------------------------------------------------------


def check_use(db: Session, supplier_id: uuid.UUID | None) -> list[ApiWarning]:
    """Warn `SUPPLIER_NOT_APPROVED` for a supplier not approved / conditional; refuse a
    disqualified one (422 `SUPPLIER_DISQUALIFIED`)."""
    if supplier_id is None:
        return []
    s = db.get(QSupplier, supplier_id)
    if s is None:
        raise qc.field_err("supplier_id", "Unknown supplier.")
    if s.status == SS.disqualified:
        raise qc.err(
            422,
            ErrorCode.SUPPLIER_DISQUALIFIED,
            f"{s.supplier_code} is disqualified and cannot be named on a record.",
            "المورد مستبعد ولا يمكن ذكره في سجل.",
        )
    out = []
    if s.status not in SUPPLIER_USABLE:
        out.append(
            qc.warning(
                ErrorCode.SUPPLIER_NOT_APPROVED,
                f"{s.supplier_code} is {s.status.value}, not approved.",
                "المورد غير معتمد.",
                "supplier_id",
            )
        )
    elif s.status == SS.conditional and s.approved_scope:
        out.append(
            qc.warning(
                ErrorCode.SUPPLIER_NOT_APPROVED,
                f"{s.supplier_code} is approved with conditions: {s.approved_scope}",
                f"المورد معتمد بشروط: {s.approved_scope}",
                "supplier_id",
            )
        )
    return out


def lab_scope_warning(
    db: Session, supplier_id: uuid.UUID, scope_code: str, on: date
) -> list[ApiWarning]:
    """Q-SHR-03 (for Q2 test requests and calibrations): a lab used outside its accreditation scope,
    or with no accreditation valid on the date, gives `LAB_NOT_ACCREDITED_FOR_SCOPE`."""
    accs = db.scalars(
        select(QSupplierAccreditation).where(QSupplierAccreditation.supplier_id == supplier_id)
    )
    for a in accs:
        valid = (a.valid_from is None or a.valid_from <= on) and a.valid_until >= on
        if valid and scope_code.upper() in (a.scope_codes or []):
            return []
    return [
        qc.warning(
            ErrorCode.LAB_NOT_ACCREDITED_FOR_SCOPE,
            f"The laboratory has no accreditation covering {scope_code} on {on.isoformat()}.",
            "المختبر غير معتمد لهذا النطاق في التاريخ المحدد.",
            "supplier_id",
        )
    ]


# ---- transitions (Q-SHR-01) ---------------------------------------------------------------------

# (from, to) → responsible-person step (None = 279 only) and whether a reason is required
EDGES: dict[tuple[SS, SS], tuple[str | None, bool]] = {
    (SS.draft, SS.pending_approval): (None, False),
    (SS.pending_approval, SS.approved): ("approve", False),
    (SS.pending_approval, SS.conditional): ("approve", False),
    (SS.pending_approval, SS.draft): ("approve", True),
    (SS.approved, SS.conditional): ("suspend", True),
    (SS.conditional, SS.approved): ("suspend", True),
    (SS.approved, SS.suspended): ("suspend", True),
    (SS.conditional, SS.suspended): ("suspend", True),
    (SS.suspended, SS.approved): ("suspend", True),
    (SS.suspended, SS.conditional): ("suspend", True),
    (SS.disqualified, SS.suspended): (None, True),  # "lift"
}
DECISION = {
    SS.approved: "approved",
    SS.conditional: "conditional",
    SS.draft: "returned",
    SS.suspended: "approved",
}


def transition(
    db: Session,
    p: Principal,
    supplier_id: uuid.UUID,
    to: QSupplierStatus,
    why: str | None,
    project_id: uuid.UUID | None,
    condition: str | None = None,
) -> dict[str, Any]:
    s = get(db, supplier_id)
    src = s.status
    if to == SS.disqualified and src != SS.disqualified:
        step: str | None = None
        need_reason = True
    elif (src, to) in EDGES:
        step, need_reason = EDGES[(src, to)]
    else:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Supplier", src, to)
    if (src, to) == (SS.draft, SS.pending_approval):
        p.require_any(C.supplier_manage)
    else:
        p.require_any(C.supplier_approve)
    text = qc.reason(why, 20) if need_reason else (why or "").strip() or None
    if to == SS.conditional and not (condition or s.approved_scope):
        raise qc.field_err("condition", "State the condition of a conditional approval.")
    if step is not None:
        if project_id is None:
            raise qc.field_err(
                "project_id",
                "Name the project whose responsible-person matrix applies to this step.",
                "حدد المشروع الذي تنطبق مصفوفة مسؤولياته على هذه الخطوة.",
            )
        project = qc.get_project(db, p, project_id)
        qc.writable(project, p)
        if src == SS.pending_approval and to in (SS.approved, SS.conditional):
            blockers = [b for gate in reg.SUPPLIER_GATES for b in gate(db, s, to.value)]
            if blockers:
                raise qc.err(
                    422,
                    ErrorCode.TRANSITION_CONDITION_NOT_MET,
                    blockers[0].detail_en,
                    blockers[0].detail_ar,
                    blockers=[b.__dict__ for b in blockers],
                )
        requesters = {u for u in (s.created_by_user_id, s.updated_by_user_id) if u}
        ctx = rpm.Ctx(requesters=frozenset(requesters if step == "approve" else ()))
        rule, capacity = rpm.check_signer(
            db, p, project, QRecordType.supplier, step, ctx, record_id=s.id
        )
        signoff.sign(
            db, p, project, QRecordType.supplier, s.id, step, DECISION[to], text, rule, capacity
        )
    if condition is not None:
        s.approved_scope = condition
    s.status = to
    s.status_reason = text
    s.status_changed_at = now()
    if to == SS.pending_approval:
        s.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project_id),
        entity_type=EntityType.q_supplier,
        entity_id=s.id,
        project_id=project_id,
        before={"status": src},
        after={"status": to},
        details={"reason": text} if text else None,
    )
    return read(db, p, s)
