"""Receiving inspection (spec 8-quality §D.2, Q-RCV-01…09): receipt header and lines, the
vehicle check `QRCV`, the proposed line decision from the criteria library (worst wins), the
recorded decision with the `receipt.deviation` / `receipt.reject` steps of the matrix, the
owner's approval (Q-RCV-03), automatic holds for quarantine (Q-RCV-04), NCR or claim for a
rejection (Q-RCV-05), seal mismatch (Q-RCV-06), M&TE on temperature-controlled lines (Q-RCV-07)
and dock dwell (Q-RCV-08)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QCriterionStatus,
    QDetectionStage,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QRecordType,
)
from app.core.quality.q3 import (
    DECISION_RANK,
    QUARANTINE_CONDITIONS,
    TEMP_CONTROLLED,
    QHoldReason,
    QLineCondition,
    QLineDecision,
    QReceiptStatus,
    QStorageClass,
)
from app.models import Project, Zone
from app.models.field import ChecklistResponse
from app.models.quality import QCriterion, QCustomer, QNcr
from app.models.quality.q3 import QProduct, QReceipt, QReceiptLine
from app.schemas.hse_common import ApiWarning
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import criteria as crit_svc
from app.services.quality import mte as mte_svc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b
from app.services.quality.q3 import checklists
from app.services.quality.q3 import holds as hold_svc

C = Capability
RT = QRecordType.receipt
LD = QLineDecision
A = AttachmentOwner
ST = QReceiptStatus

# ISO 2859-1 general inspection level II, single sampling: lot size upper bound → sample size
# [VERIFY] against the current edition before a customer relies on it.
SAMPLE_TABLE = (
    (8, 2), (15, 3), (25, 5), (50, 8), (90, 13), (150, 20), (280, 32), (500, 50),
    (1200, 80), (3200, 125), (10000, 200), (35000, 315), (150000, 500), (500000, 800),
)  # fmt: skip


def sample_hint(qty: Decimal | None) -> int | None:
    if qty is None or qty < 2:
        return None
    for top, n in SAMPLE_TABLE:
        if qty <= top:
            return n
    return 1250


def ctx(r: QReceipt, ln: QReceiptLine | None = None) -> rpm.Ctx:
    who = {r.created_by_user_id}
    if ln is not None:
        who |= {ln.recorded_by_user_id, ln.requested_by_user_id}
    return rpm.Ctx(site_id=r.site_id, requesters=qc.ids(*who))


def _steps(db: Session, r: QReceipt) -> b.StepList:
    out: list[tuple[str, rpm.Ctx, str | None]] = []
    for ln in lines_of(db, r):
        if ln.requested_decision is not None:
            out.append((step_for(ln.requested_decision), ctx(r, ln), None))
    return out


def get_receipt(db: Session, p: Principal, rid: uuid.UUID) -> tuple[QReceipt, Project]:
    r = db.get(QReceipt, rid)
    if r is None or not p.can_see_project(r.project_id):
        raise b.not_found(db, p, RT, rid, r.project_id if r else None)
    project = qc.get_project(db, p, r.project_id)
    if (
        r.status == ST.draft
        and r.created_by_user_id != p.user.id
        and p.grant(project.id, C.receiving_record) is None
    ):
        raise b.not_found(db, p, RT, rid, project.id)
    if not b.can_view(db, p, project, RT, r.id, r.site_id, lambda: _steps(db, r)):
        raise b.not_found(db, p, RT, rid, project.id)
    return r, project


def lines_of(db: Session, r: QReceipt) -> list[QReceiptLine]:
    return list(
        db.scalars(
            select(QReceiptLine)
            .where(QReceiptLine.receipt_id == r.id)
            .order_by(QReceiptLine.line_no)
        )
    )


def temp_controlled(db: Session, r: QReceipt) -> bool:
    for ln in lines_of(db, r):
        prod = db.get(QProduct, ln.product_id)
        if prod is not None and prod.storage_class in TEMP_CONTROLLED:
            return True
    return False


# ---- header -------------------------------------------------------------------------------------

HEADER = (
    "dock_zone_id",
    "supplier_id",
    "carrier_id",
    "po_ref",
    "asn_ref",
    "vehicle_plate",
    "reefer_display_c",
    "seal_expected",
    "seal_actual",
    "seal_intact",
    "expected_at",
    "arrived_at",
    "unload_start",
    "unload_end",
    "qty_deviation_note",
)


def _apply_header(
    db: Session, project: Project, r: QReceipt, body: dict[str, Any]
) -> list[ApiWarning]:
    warnings: list[ApiWarning] = []
    for k in HEADER:
        if k in body and (
            body[k] is not None or k in ("supplier_id", "carrier_id", "qty_deviation_note")
        ):
            setattr(r, k, body[k])
    if "customer_id" in body and body["customer_id"] is not None:
        r.customer_id = b.customer_of(db, project, body["customer_id"]).id
    zone = db.get(Zone, r.dock_zone_id)
    if zone is None or zone.site_id != r.site_id:
        raise qc.field_err(
            "dock_zone_id",
            "The dock must be a zone of the site.",
            "يجب أن يكون الرصيف منطقة في الموقع.",
        )
    seq = [x for x in (r.arrived_at, r.unload_start, r.unload_end) if x is not None]
    if seq != sorted(seq):
        raise qc.field_err(
            "unload_start",
            "Times must be in order: arrival, unloading start, unloading end.",
            "يجب أن تكون الأوقات بالترتيب.",
        )
    r.seal_flag = (not r.seal_intact) or bool(
        r.seal_expected and r.seal_actual and r.seal_expected.strip() != r.seal_actual.strip()
    )
    for sid in (r.supplier_id, r.carrier_id):
        warnings += b.supplier_warnings(db, sid)
    if r.seal_flag:
        warnings.append(
            qc.warning(
                "SEAL_MISMATCH",
                "Seal broken or not matching: any acceptance needs the receipt.deviation sign-off "
                "(Q-RCV-06).",
                "الختم مكسور أو غير مطابق: أي قبول يتطلب توقيع الانحراف.",
                "seal_actual",
            )
        )
    return warnings + dwell(db, project, r)


def dwell(db: Session, project: Project, r: QReceipt) -> list[ApiWarning]:
    """Q-RCV-08: dock dwell = unload_end − unload_start for temperature-controlled receipts."""
    if r.unload_start is None or r.unload_end is None:
        r.dwell_minutes = None
        return []
    r.dwell_minutes = b.minutes(r.unload_start, r.unload_end)
    limit = int(b.setting(db, project.id, "dock_dwell_max_minutes"))
    if r.dwell_minutes > limit and temp_controlled(db, r):
        return [
            qc.warning(
                "DOCK_DWELL_LONG",
                f"Dock dwell {r.dwell_minutes} min is over {limit} min.",
                f"مدة البقاء على الرصيف {r.dwell_minutes} دقيقة تتجاوز {limit}.",
                "unload_end",
            )
        ]
    return []


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.receiving_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    cust = b.customer_of(db, project, body["customer_id"])
    r = QReceipt(
        id=uuid.uuid4(),
        project_id=project.id,
        site_id=site.id,
        dock_zone_id=body["dock_zone_id"],
        customer_id=cust.id,
        arrived_at=body.get("arrived_at") or now(),
        status=ST.draft,
        seal_intact=True,
        created_by_user_id=p.user.id,
    )
    warnings = _apply_header(db, project, r, body)
    db.add(r)
    db.flush()
    for raw in body.get("lines") or []:
        warnings += _save_line(db, p, project, r, None, raw)
    warnings += dwell(db, project, r)
    b.audit_create(db, p, project, RT, r.id, customer=cust.code)
    return {**read(db, p, r), "warnings": b.warn_dump(warnings)}


def update(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    r, project = get_receipt(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.receiving_record)
    b.require_site(g, r.site_id)
    if r.status not in (ST.draft, ST.inspected):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A decided or cancelled receipt cannot change.",
            "لا يمكن تعديل استلام مقرر أو ملغى.",
        )
    warnings = _apply_header(db, project, r, body)
    r.updated_by_user_id = p.user.id
    return {**read(db, p, r), "warnings": b.warn_dump(warnings)}


def cancel(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    r, project = get_receipt(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.receiving_record)
    b.require_site(g, r.site_id)
    if r.status not in (ST.draft, ST.inspected) or any(ln.decision for ln in lines_of(db, r)):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a receipt without decided lines can be cancelled.",
            "يمكن إلغاء استلام بلا بنود مقررة فقط.",
        )
    r.cancel_reason = qc.reason(body.get("reason"))
    before = r.status
    r.status = ST.cancelled
    b.audit_status(db, p, project, RT, r.id, before, ST.cancelled, reason=r.cancel_reason)
    return read(db, p, r)


# ---- lines and the proposal (Q-RCV-01, -07) ------------------------------------------------------


def _criterion(db: Session, rule: str, cls: str | None = None) -> QCriterion | None:
    rows = db.scalars(
        select(QCriterion)
        .where(QCriterion.rule_code == rule, QCriterion.status == QCriterionStatus.published)
        .order_by(QCriterion.version.desc())
    )
    for c in rows:
        if cls is None or (c.params or {}).get("class") == cls:
            return c
    return None


def remaining_pct(db: Session, r: QReceipt, ln: QReceiptLine, prod: QProduct) -> Decimal | None:
    if ln.expiry_date is None or not prod.shelf_life_days:
        return None
    received = b.local_day(r.arrived_at)
    left = (ln.expiry_date - received).days
    return (Decimal(left) * 100 / prod.shelf_life_days).quantize(Decimal("0.1"), ROUND_HALF_UP)


def propose(db: Session, project: Project, r: QReceipt, ln: QReceiptLine) -> None:
    """Q-RCV-01: worst of arrival temperature, remaining shelf life, condition and labels."""
    prod = db.get(QProduct, ln.product_id)
    assert prod is not None  # noqa: S101
    reasons: list[dict[str, Any]] = []
    pinned: dict[str, Any] = {}
    worst = LD.accept

    def add(d: LD, code: str, en: str, ar: str) -> None:
        nonlocal worst
        reasons.append({"code": code, "decision": d.value, "en": en, "ar": ar})
        if DECISION_RANK[d] > DECISION_RANK[worst]:
            worst = d

    if ln.product_temp_c is not None:
        c = _criterion(db, "arrival_temperature", prod.storage_class.value)
        if c is not None:
            v = crit_svc.evaluate(
                c, {"temperature_c": ln.product_temp_c, "storage_class": prod.storage_class.value}
            )
            pinned["arrival_temperature"] = {"code": c.code, "version": c.version}
        else:
            from app.services.quality.q3 import rules  # noqa: PLC0415

            v = rules.arrival_temperature(
                {"class": prod.storage_class.value}, {"temperature_c": ln.product_temp_c}
            )
        dec = (v.detail or {}).get("decision")
        if dec:
            add(LD(dec), "arrival_temperature", v.reason_en, v.reason_ar)
    pct = remaining_pct(db, r, ln, prod)
    ln.remaining_shelf_life_pct = pct
    if pct is not None:
        lim = prod.min_remaining_shelf_life_pct or b.dsetting(
            db, project.id, "min_remaining_shelf_life_pct"
        )
        c = _criterion(db, "remaining_shelf_life")
        from app.services.quality.q3 import rules  # noqa: PLC0415

        v = rules.remaining_shelf_life(
            dict(c.params or {}) if c else {}, {"remaining_pct": pct, "min_pct": lim}
        )
        if c is not None:
            pinned["remaining_shelf_life"] = {
                "code": c.code,
                "version": c.version,
                "min_pct": str(lim),
            }
        add(
            LD((v.detail or {}).get("decision") or "accept_with_deviation"),
            "remaining_shelf_life",
            v.reason_en,
            v.reason_ar,
        )
    if ln.condition in QUARANTINE_CONDITIONS:
        add(
            LD.quarantine,
            "condition",
            f"Condition: {ln.condition.value}.",
            "حالة البضاعة تتطلب العزل.",
        )
    if not ln.labels_ok:
        add(LD.accept_with_deviation, "labels", "Labels not acceptable.", "الملصقات غير مقبولة.")
    ln.proposed_decision = worst
    ln.proposal_reasons = reasons
    ln.criteria_versions = pinned


def _save_line(
    db: Session,
    p: Principal,
    project: Project,
    r: QReceipt,
    ln: QReceiptLine | None,
    raw: dict[str, Any],
) -> list[ApiWarning]:
    prod = db.get(QProduct, raw.get("product_id") or (ln.product_id if ln else None))
    if prod is None or prod.project_id != project.id:
        raise qc.field_err(
            "product_id", "The product is not on this project.", "المنتج ليس في المشروع."
        )
    if prod.owner_customer_id != r.customer_id:
        raise qc.field_err(
            "product_id", "The product belongs to another owner.", "المنتج يخص مالكاً آخر."
        )
    if ln is None:
        n = len(lines_of(db, r)) + 1
        ln = QReceiptLine(
            receipt_id=r.id,
            line_no=n,
            product_id=prod.id,
            recorded_by_user_id=p.user.id,
            photo_ids=[],
            proposal_reasons=[],
            criteria_versions={},
        )
        db.add(ln)
    elif ln.decision is not None:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A decided line cannot change.",
            "لا يمكن تعديل بند مقرر.",
        )
    ln.product_id = prod.id
    for k in (
        "batch",
        "expiry_date",
        "production_date",
        "qty_expected",
        "qty_received",
        "unit",
        "labels_ok",
        "product_temp_c",
        "mte_id",
        "sample_count",
    ):
        if k in raw:
            setattr(ln, k, raw[k])
    if raw.get("condition"):
        ln.condition = QLineCondition(raw["condition"])
    if not ln.batch or ln.qty_received is None:
        raise qc.field_err(
            "batch",
            "Each line needs a batch and the received quantity.",
            "كل بند يحتاج دفعة وكمية مستلمة.",
        )
    if prod.dated and ln.expiry_date is None:
        raise qc.field_err(
            "expiry_date",
            "Dated products need the expiry date.",
            "المنتجات المؤرخة تحتاج تاريخ الانتهاء.",
        )
    warnings: list[ApiWarning] = []
    if prod.storage_class in TEMP_CONTROLLED and (ln.product_temp_c is None or ln.mte_id is None):
        raise qc.err(
            422,
            ErrorCode.MTE_REQUIRED,
            f"{prod.storage_class.value} lines need the product temperature measured with a "
            "registered instrument (Q-RCV-07).",
            "البنود المبردة تحتاج حرارة المنتج مقاسة بجهاز مسجل.",
        )
    if ln.mte_id is not None:
        b.mte_of(db, project, ln.mte_id)
        db.flush()
        _, w = mte_svc.record_usage(
            db,
            project,
            ln.mte_id,
            RT,
            r.id,
            p.user.id,
            None,
            f"line {ln.line_no} {ln.product_temp_c} °C",
        )
        warnings += w
    ln.recorded_by_user_id = p.user.id
    db.flush()
    propose(db, project, r, ln)
    if ln.qty_expected is not None and ln.qty_received != ln.qty_expected:
        warnings.append(
            qc.warning(
                "QTY_DIFFERENCE",
                f"Line {ln.line_no}: received {ln.qty_received}, ASN {ln.qty_expected} — a "
                "quantity deviation, not a quality rejection (Q-RCV-09).",
                "فرق كمية: انحراف كمي وليس رفض جودة.",
            )
        )
    db.flush()
    return warnings


def save_line(
    db: Session, p: Principal, rid: uuid.UUID, line_id: uuid.UUID | None, body: dict[str, Any]
) -> dict[str, Any]:
    r, project = get_receipt(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.receiving_record)
    b.require_site(g, r.site_id)
    if r.status not in (ST.draft, ST.inspected):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The receipt is decided or cancelled.",
            "الاستلام مقرر أو ملغى.",
        )
    ln = None
    if line_id is not None:
        ln = db.get(QReceiptLine, line_id)
        if ln is None or ln.receipt_id != r.id:
            raise b.not_found(db, p, RT, line_id, project.id)
    warnings = _save_line(db, p, project, r, ln, body)
    warnings += dwell(db, project, r)
    return {**read(db, p, r), "warnings": b.warn_dump(warnings)}


def vehicle_check(
    db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    r, project = get_receipt(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.receiving_record)
    b.require_site(g, r.site_id)
    if r.status not in (ST.draft, ST.inspected):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The receipt is decided or cancelled.",
            "الاستلام مقرر أو ملغى.",
        )
    out = checklists.respond(
        db,
        p.user.id,
        project,
        ResponseOwnerType.q_receipt,
        "receiving",
        r.site_id,
        body["answers"],
        zone_id=r.dock_zone_id,
        code=body.get("template_code"),
    )
    r.vehicle_response_id = out.response.id
    r.vehicle_check_passed = out.passed
    return read(db, p, r)


def inspect(db: Session, p: Principal, rid: uuid.UUID) -> dict[str, Any]:
    """Draft → Inspected: number assigned (Q-NUM-03), every line has its proposal."""
    r, project = get_receipt(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.receiving_record)
    b.require_site(g, r.site_id)
    if r.status != ST.draft:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Only a draft receipt.", "استلام مسودة فقط."
        )
    ls = lines_of(db, r)
    if not ls:
        raise qc.field_err("lines", "Add at least one line.", "أضف بنداً واحداً على الأقل.")
    if r.unload_start is None or r.unload_end is None:
        raise qc.field_err(
            "unload_end", "Record the unloading start and end.", "سجّل بدء التفريغ وانتهاءه."
        )
    if r.vehicle_response_id is None:
        raise qc.field_err(
            "vehicle_check", "Complete the vehicle check (QRCV).", "أكمل فحص المركبة."
        )
    for ln in ls:
        propose(db, project, r, ln)
    r.rcv_no = b.number(db, project, RT, r.arrived_at)
    r.status = ST.inspected
    r.inspected_at = now()
    r.inspected_by_user_id = p.user.id
    b.audit_status(db, p, project, RT, r.id, ST.draft, ST.inspected, rcv_no=r.rcv_no)
    return {**read(db, p, r), "warnings": b.warn_dump(dwell(db, project, r))}


# ---- decisions (Q-RCV-02…06) ---------------------------------------------------------------------


def step_for(d: LD) -> str:
    return "reject" if d == LD.reject else "deviation"


def needs_step(r: QReceipt, ln: QReceiptLine, d: LD) -> str | None:
    if d == LD.reject:
        return "reject"
    if d == LD.accept_with_deviation:
        return "deviation"
    if ln.proposed_decision is not None and DECISION_RANK[d] < DECISION_RANK[ln.proposed_decision]:
        return "deviation"  # Q-RCV-02: better than the proposal
    if r.seal_flag and d == LD.accept:
        return "deviation"  # Q-RCV-06
    return None


def decide(db: Session, p: Principal, line_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    ln = db.get(QReceiptLine, line_id)
    if ln is None:
        raise b.not_found(db, p, RT, line_id, None)
    r, project = get_receipt(db, p, ln.receipt_id)
    project, g = b.project_for_progress(
        db,
        p,
        project.id,
        C.receiving_record if p.grant(project.id, C.receiving_record) else C.receiving_decide,
        allow_n=True,
    )
    if r.status != ST.inspected:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Inspect the receipt first.", "افحص الاستلام أولاً."
        )
    if ln.decision is not None:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "The line is already decided.", "البند مقرر."
        )
    d = LD(body.get("decision") or (ln.requested_decision.value if ln.requested_decision else ""))
    why = (body.get("reason") or ln.reason or "").strip() or None
    owner_file = (
        b.attachment_on(
            db,
            body.get("owner_approval_attachment_id"),
            A.q_receipt,
            r.id,
            "owner_approval_attachment_id",
        )
        or ln.owner_approval_attachment_id
    )
    claim = (body.get("claim_ref") or ln.claim_ref or "").strip() or None
    ncr_id = body.get("ncr_id") or ln.ncr_id
    raise_ncr = bool(body.get("raise_ncr"))
    if d == LD.reject and not (ncr_id or claim or raise_ncr):
        raise qc.err(
            422,
            ErrorCode.REJECT_NEEDS_NCR_OR_CLAIM,
            "A rejection needs an NCR or a supplier / carrier claim number (Q-RCV-05).",
            "الرفض يتطلب تقرير عدم مطابقة أو رقم مطالبة.",
        )
    cust = db.get(QCustomer, r.customer_id)
    if (
        d == LD.accept_with_deviation
        and cust is not None
        and cust.owner_release_approval
        and owner_file is None
    ):
        raise qc.err(
            422,
            ErrorCode.OWNER_DECISION_REQUIRED,
            f"{cust.name_en} approves deviations on its goods: attach the owner's written "
            "approval (Q-RCV-03).",
            f"يعتمد {cust.name_ar} الانحرافات على بضاعته: أرفق موافقة المالك المكتوبة.",
        )
    step = needs_step(r, ln, d)
    better = (
        ln.proposed_decision is not None and DECISION_RANK[d] < DECISION_RANK[ln.proposed_decision]
    )
    if better and len(why or "") < 20:
        raise qc.err(
            422,
            ErrorCode.DECISION_BETTER_THAN_CRITERIA,
            f"The criteria propose {ln.proposed_decision}; a better decision needs the "
            "receipt.deviation sign-off with a reason of at least 20 characters "
            "(Q-RCV-02).",
            "القرار أفضل من مقترح المعايير: يتطلب توقيع الانحراف مع سبب لا يقل عن 20 حرفاً.",
        )
    if ncr_id is not None:
        n = db.get(QNcr, ncr_id)
        if n is None or n.project_id != project.id:
            raise qc.field_err(
                "ncr_id", "The NCR is not on this project.", "التقرير ليس في المشروع."
            )
    c = ctx(r, ln)
    signed = None
    if step is not None:
        if not b.resolves(db, p, project, RT, r.id, step, c) and body.get("request"):
            if g.scope.value == "responsible":
                raise forbidden_error()
            ln.requested_decision = d
            ln.requested_by_user_id = p.user.id
            ln.requested_at = now()
            ln.reason = why
            ln.claim_ref = claim
            ln.ncr_id = ncr_id
            ln.owner_approval_attachment_id = owner_file
            users = b.resolvers(db, project, RT, step, rpm.Ctx(site_id=r.site_id), record_id=r.id)
            b.send(
                db,
                project,
                users,
                f"rcv:{ln.id}:{step}:{d.value}",
                f"{r.rcv_no}: {d.value} needs your sign-off",
                f"{r.rcv_no}: القرار يحتاج توقيعك",
                rt=RT,
                rid=r.id,
                path=f"/quality/receiving/{r.id}",
                email=False,
            )
            return read(db, p, r)
        signed = b.sign(
            db,
            p,
            project,
            RT,
            r.id,
            step,
            c,
            decision="approved",
            comment=why,
            evidence=[x for x in [owner_file] if x],
        )
    elif g.scope.value == "responsible":
        raise forbidden_error()
    if raise_ncr and ncr_id is None:
        n = _raise_ncr(db, p, project, r, ln, d)
        ncr_id = n.id
    ln.decision = d
    ln.reason = why
    ln.claim_ref = claim
    ln.ncr_id = ncr_id
    ln.owner_approval_attachment_id = owner_file
    ln.decided_by_user_id = p.user.id
    ln.decided_at = now()
    ln.requested_decision = None
    if d == LD.quarantine:
        _quarantine(db, p, project, r, ln)
    if all(x.decision is not None for x in lines_of(db, r)):
        r.status = ST.decided
        r.decided_at = now()
        b.audit_status(db, p, project, RT, r.id, ST.inspected, ST.decided)
    db.flush()
    out = read(db, p, r)
    if signed is not None:
        out["signoff_id"] = signed.id
    return out


def _quarantine(
    db: Session, p: Principal | None, project: Project, r: QReceipt, ln: QReceiptLine
) -> None:
    """Q-RCV-04: quarantine creates a hold (reason receiving) with the line."""
    prod = db.get(QProduct, ln.product_id)
    h = hold_svc.place(
        db,
        project,
        site_id=r.site_id,
        reason=QHoldReason.receiving,
        lines=[
            {
                "owner_customer_id": r.customer_id,
                "product_id": ln.product_id,
                "batch": ln.batch,
                "expiry_date": ln.expiry_date,
                "qty": ln.qty_received,
                "unit": ln.unit,
                "location": "DOCK",
                "receipt_line_id": ln.id,
            }
        ],
        placed_by=ln.decided_by_user_id,
        zone_id=r.dock_zone_id,
        storage_class=QStorageClass.pharma_2_8
        if prod and prod.storage_class == QStorageClass.pharma_2_8
        else None,
        source=(RT, r.id, r.rcv_no),
        ncr_id=ln.ncr_id,
        p=p,
    )
    ln.hold_id = h.id


def _raise_ncr(
    db: Session, p: Principal, project: Project, r: QReceipt, ln: QReceiptLine, d: LD
) -> QNcr:

    prod = db.get(QProduct, ln.product_id)
    temp = any(
        x.get("code") == "arrival_temperature" and x.get("decision") != "accept"
        for x in ln.proposal_reasons or []
    )
    n = b.raise_ncr(
        db,
        project,
        QNcrSourceType.receipt,
        r.id,
        actor=p.user.id,
        classification=QNcrClass.major if d == LD.reject else QNcrClass.minor,
        category=QNcrCategory.temperature
        if temp
        else (
            QNcrCategory.expiry_shelf_life
            if any(x.get("code") == "remaining_shelf_life" for x in ln.proposal_reasons or [])
            else QNcrCategory.material
        ),
        title=f"{prod.sku if prod else ''} {ln.batch} {d.value} at receiving — {r.rcv_no}"[:150],
    )
    n.item_key = f"SKU:{prod.sku}" if prod else n.item_key
    n.quantity = ln.qty_received
    n.unit = ln.unit
    n.lot_refs = [ln.batch]
    return n


# ---- NCR source adapter (list NS `receipt`) ------------------------------------------------------


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    r = db.get(QReceipt, source_id)
    if r is None or r.project_id != project.id:
        raise qc.field_err(
            "source_id", "The receipt is not on this project.", "الاستلام ليس في المشروع."
        )
    ls = lines_of(db, r)
    bad = [ln for ln in ls if (ln.decision or ln.proposed_decision) not in (None, LD.accept)]
    ln = bad[-1] if bad else (ls[0] if ls else None)
    prod = db.get(QProduct, ln.product_id) if ln else None
    reasons = "; ".join(x.get("en", "") for x in (ln.proposal_reasons if ln else []) or [])
    return reg.SourceInfo(
        ref=r.rcv_no,
        title=f"Receiving deviation — {r.rcv_no}",
        site_id=r.site_id,
        zone_id=r.dock_zone_id,
        engagement_id=b.operator_engagement(db, project),
        supplier_id=r.supplier_id,
        customer_id=r.customer_id,
        item_key=f"SKU:{prod.sku}" if prod else f"RCV:{r.rcv_no}",
        detection_stage=QDetectionStage.receiving,
        requirement_en="Receiving criteria of the storage class and the owner (Q-RCV-01).",
        requirement_ar="معايير الاستلام لفئة التخزين والمالك.",
        finding_en=f"{prod.sku if prod else ''} batch {ln.batch if ln else ''}: "
        f"{reasons or 'see the receipt'}",
        finding_ar=f"{prod.sku if prod else ''} الدفعة {ln.batch if ln else ''}",
        proposed_class=QNcrClass.minor,
        quantity=ln.qty_received if ln else None,
        unit=ln.unit if ln else None,
        lot_refs=(ln.batch,) if ln else (),
        record_type=RT,
    )


# ---- read model ----------------------------------------------------------------------------------


def line_read(db: Session, ln: QReceiptLine) -> dict[str, Any]:
    prod = db.get(QProduct, ln.product_id)
    return {
        "id": ln.id,
        "line_no": ln.line_no,
        "product": {
            "id": prod.id,
            "sku": prod.sku,
            "description_en": prod.description_en,
            "description_ar": prod.description_ar,
            "storage_class": prod.storage_class,
            "shelf_life_days": prod.shelf_life_days,
        }
        if prod
        else None,
        "batch": ln.batch,
        "expiry_date": ln.expiry_date,
        "production_date": ln.production_date,
        "qty_expected": ln.qty_expected,
        "qty_received": ln.qty_received,
        "unit": ln.unit,
        "condition": ln.condition,
        "labels_ok": ln.labels_ok,
        "product_temp_c": ln.product_temp_c,
        "mte": b.mte_ref(db, ln.mte_id),
        "remaining_shelf_life_pct": ln.remaining_shelf_life_pct,
        "sample_count": ln.sample_count,
        "sample_hint": sample_hint(ln.qty_received),
        "proposed_decision": ln.proposed_decision,
        "proposal_reasons": ln.proposal_reasons,
        "criteria_versions": ln.criteria_versions,
        "decision": ln.decision,
        "requested_decision": ln.requested_decision,
        "reason": ln.reason,
        "ncr_id": ln.ncr_id,
        "claim_ref": ln.claim_ref,
        "hold_id": ln.hold_id,
        "owner_approval_attachment_id": ln.owner_approval_attachment_id,
        "decided_at": ln.decided_at,
    }


def read(db: Session, p: Principal, r: QReceipt) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    hide = b.hide_names(p, r.project_id)
    resp = db.get(ChecklistResponse, r.vehicle_response_id) if r.vehicle_response_id else None
    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    steps = []
    for st in ("deviation", "reject"):
        if b.resolves(db, p, project, RT, r.id, st, rpm.Ctx(site_id=r.site_id)):
            steps.append(st)
    return {
        "id": r.id,
        "project_id": r.project_id,
        "rcv_no": r.rcv_no,
        "site": b.site_ref(db, r.site_id),
        "dock_zone": b.zone_ref(db, r.dock_zone_id),
        "customer": b.customer_ref(db, r.customer_id),
        "supplier": b.supplier_ref(db, r.supplier_id),
        "carrier": b.supplier_ref(db, r.carrier_id),
        "po_ref": r.po_ref,
        "asn_ref": r.asn_ref,
        "vehicle_plate": r.vehicle_plate,
        "reefer_display_c": r.reefer_display_c,
        "seal_expected": r.seal_expected,
        "seal_actual": r.seal_actual,
        "seal_intact": r.seal_intact,
        "seal_flag": r.seal_flag,
        "expected_at": r.expected_at,
        "arrived_at": r.arrived_at,
        "unload_start": r.unload_start,
        "unload_end": r.unload_end,
        "dwell_minutes": r.dwell_minutes,
        "dwell_limit_minutes": int(b.setting(db, r.project_id, "dock_dwell_max_minutes")),
        "temp_controlled": temp_controlled(db, r),
        "vehicle_check": checklists.response_read(resp),
        "transit_batch_id": r.transit_batch_id,
        "qty_deviation_note": r.qty_deviation_note,
        "status": r.status,
        "inspected_at": r.inspected_at,
        "decided_at": r.decided_at,
        "cancel_reason": r.cancel_reason,
        "created_by": b.user_ref(db, r.created_by_user_id, hide),
        "lines": [line_read(db, ln) for ln in lines_of(db, r)],
        "my_steps": steps,
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, r.id)
        ],
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page_no: int,
    size: int,
    *,
    customer_id: uuid.UUID | None = None,
    decision: LD | None = None,
    deviation: bool | None = None,
    status: QReceiptStatus | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    stmt = select(QReceipt).where(QReceipt.project_id == project.id)
    if customer_id:
        stmt = stmt.where(QReceipt.customer_id == customer_id)
    if status:
        stmt = stmt.where(QReceipt.status == status)
    if q:
        stmt = stmt.where(
            QReceipt.rcv_no.ilike(f"%{q}%")
            | QReceipt.asn_ref.ilike(f"%{q}%")
            | QReceipt.po_ref.ilike(f"%{q}%")
        )
    items = []
    for r in db.scalars(stmt.order_by(QReceipt.arrived_at.desc()).limit(2000)):
        if (
            r.status == ST.draft
            and r.created_by_user_id != p.user.id
            and g.scope.value == "responsible"
        ):
            continue
        if g.scope.value == "responsible":
            if not b.can_view(db, p, project, RT, r.id, r.site_id, lambda r=r: _steps(db, r)):
                continue
        elif not g.covers_site(r.site_id):
            continue
        ls = lines_of(db, r)
        decs = {ln.decision for ln in ls}
        if decision and decision not in decs:
            continue
        has_dev = LD.accept_with_deviation in decs
        if deviation is not None and has_dev != deviation:
            continue
        items.append(
            {
                "id": r.id,
                "rcv_no": r.rcv_no,
                "status": r.status,
                "customer": b.customer_ref(db, r.customer_id),
                "supplier": b.supplier_ref(db, r.supplier_id),
                "arrived_at": r.arrived_at,
                "asn_ref": r.asn_ref,
                "lines": len(ls),
                "decisions": sorted(d.value for d in decs if d),
                "pending_signoff": any(ln.requested_decision for ln in ls),
                "seal_flag": r.seal_flag,
                "dwell_minutes": r.dwell_minutes,
                "dwell_long": bool(
                    r.dwell_minutes
                    and r.dwell_minutes > int(b.setting(db, project.id, "dock_dwell_max_minutes"))
                ),
            }
        )
    return b.page(items, page_no, size)


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    rows = db.execute(
        select(QReceiptLine, QReceipt)
        .join(QReceipt, QReceipt.id == QReceiptLine.receipt_id)
        .where(
            QReceipt.project_id == project.id,
            QReceiptLine.requested_decision.is_not(None),
            QReceiptLine.decision.is_(None),
        )
    ).all()
    for ln, r in rows:
        c = ctx(r, ln)
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT,
                    r.id,
                    project.id,
                    r.rcv_no or "RCV",
                    f"Line {ln.line_no}: {ln.requested_decision.value}",  # type: ignore[union-attr]
                    step_for(ln.requested_decision),  # type: ignore[arg-type]
                    ln.requested_at or r.arrived_at,
                    f"/quality/receiving/{r.id}",
                    "Q3",
                ),
                None,
                r.site_id,
                None,
                c.requesters,
            )
        )
    return out


_ = datetime
