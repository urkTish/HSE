"""Holds and quarantine (spec 8-quality §D.7.3, Q-HLD-01…08): placing (by 270 holders or the
system), zone-level holds completed with lines, segregation, release / reject by line through the
responsible-person matrix with the blockers of Q-HLD-04 and the owner's decision of Q-HLD-05,
final outcomes with evidence, derived hold status and the WMS export."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QNcrStatus, QRecordType
from app.core.quality.q3 import (
    QExcursionStatus,
    QHoldLineStatus,
    QHoldOutcome,
    QHoldReason,
    QHoldStatus,
    QRecallStatus,
    QRecallType,
    QSegregation,
    QStorageClass,
)
from app.models import Project
from app.models.quality import QCustomer, QLink, QNcr
from app.models.quality.q3 import QExcursion, QHold, QHoldLine, QProduct, QRecall
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b

C = Capability
RT = QRecordType.hold
L = QHoldLineStatus
A = AttachmentOwner


def qualifier(h: QHold) -> str | None:
    return QStorageClass.pharma_2_8.value if h.storage_class == QStorageClass.pharma_2_8 else None


def ctx(h: QHold) -> rpm.Ctx:
    return rpm.Ctx(
        site_id=h.site_id, requesters=qc.ids(h.placed_by_user_id), qualifier=qualifier(h)
    )


def lines_of(db: Session, h: QHold) -> list[QHoldLine]:
    return list(
        db.scalars(
            select(QHoldLine)
            .where(QHoldLine.hold_id == h.id)
            .order_by(QHoldLine.created_at, QHoldLine.sku, QHoldLine.batch)
        )
    )


def _steps(h: QHold) -> b.StepList:
    return [("release", ctx(h), qualifier(h)), ("reject", ctx(h), qualifier(h))]


def get_hold(db: Session, p: Principal, hold_id: uuid.UUID) -> tuple[QHold, Project]:
    h = db.get(QHold, hold_id)
    if h is None or not p.can_see_project(h.project_id):
        raise b.not_found(db, p, RT, hold_id, h.project_id if h else None)
    project = qc.get_project(db, p, h.project_id)
    if not b.can_view(db, p, project, RT, h.id, h.site_id, lambda: _steps(h)):
        raise b.not_found(db, p, RT, hold_id, project.id)
    return h, project


# ---- placing ------------------------------------------------------------------------------------


def _line(db: Session, project: Project, h: QHold, raw: dict[str, Any], t: datetime) -> QHoldLine:
    prod = db.get(QProduct, raw["product_id"]) if raw.get("product_id") else None
    if prod is not None and prod.project_id != project.id:
        raise qc.field_err("lines", "A product is not on this project.", "منتج ليس في المشروع.")
    sku = raw.get("sku") or (prod.sku if prod else None)
    if not sku or not raw.get("batch"):
        raise qc.field_err(
            "lines", "Each line needs a product (sku) and a batch.", "كل بند يحتاج منتجاً ودفعة."
        )
    qty = Decimal(str(raw.get("qty") or 0))
    if qty <= 0:
        raise qc.field_err(
            "lines", "Each line needs a positive quantity.", "كل بند يحتاج كمية موجبة."
        )
    owner = raw.get("owner_customer_id") or (prod.owner_customer_id if prod else None)
    if prod is not None and prod.storage_class == QStorageClass.pharma_2_8:
        h.storage_class = QStorageClass.pharma_2_8
    return QHoldLine(
        hold_id=h.id,
        owner_customer_id=owner,
        product_id=prod.id if prod else None,
        sku=sku,
        batch=raw["batch"],
        expiry_date=raw.get("expiry_date"),
        qty=qty,
        unit=raw.get("unit") or "unit",
        location=raw.get("location"),
        line_status=L.on_hold,
        receipt_line_id=raw.get("receipt_line_id"),
        stock_line_id=raw.get("stock_line_id"),
        created_at=t,
    )


def place(
    db: Session,
    project: Project,
    *,
    site_id: uuid.UUID,
    reason: QHoldReason,
    lines: list[dict[str, Any]],
    placed_by: uuid.UUID | None,
    zone_id: uuid.UUID | None = None,
    zone_level: bool = False,
    storage_class: QStorageClass | None = None,
    source: tuple[QRecordType | str, uuid.UUID, str | None] | None = None,
    ncr_id: uuid.UUID | None = None,
    note: str | None = None,
    p: Principal | None = None,
    at: datetime | None = None,
    notify: bool = True,
) -> QHold:
    """Q-HLD-01: placed by a 270 holder or automatically (receipt quarantine, excursion, recall,
    hygiene, damage, return grade C, expiry)."""
    t = at or now()
    h = QHold(
        id=uuid.uuid4(),
        project_id=project.id,
        hold_no=b.number(db, project, RT, t),
        site_id=site_id,
        zone_id=zone_id,
        reason=reason,
        reason_note=note,
        source_type=(source[0].value if isinstance(source[0], QRecordType) else source[0])
        if source
        else None,
        source_id=source[1] if source else None,
        source_ref=source[2] if source else None,
        ncr_id=ncr_id,
        zone_level=zone_level and not lines,
        storage_class=storage_class,
        placed_by_user_id=placed_by,
        placed_at=t,
        lines_added_at=t if lines else None,
        status=QHoldStatus.on_hold,
        alerts_sent=[],
        created_by_user_id=placed_by,
    )
    db.add(h)
    db.flush()
    for raw in lines:
        db.add(_line(db, project, h, raw, t))
    db.flush()
    if source is not None and isinstance(source[0], QRecordType):
        from app.core.quality.common import QLinkKind  # noqa: PLC0415
        from app.services.quality import links  # noqa: PLC0415

        links.add(db, project.id, RT, h.id, source[0], source[1], QLinkKind.raised_from, placed_by)
    if ncr_id is not None:
        from app.core.quality.common import QLinkKind  # noqa: PLC0415
        from app.services.quality import links  # noqa: PLC0415

        links.add(db, project.id, QRecordType.ncr, ncr_id, RT, h.id, QLinkKind.relates, placed_by)
    b.audit_create(db, p, project, RT, h.id, hold_no=h.hold_no, reason=reason.value)
    if notify:
        _notify_placed(db, project, h)
    return h


def _notify_placed(db: Session, project: Project, h: QHold) -> None:
    users = set(
        b.resolvers(db, project, RT, "release", ctx(h), qualifier=qualifier(h), record_id=h.id)
    )
    if h.placed_by_user_id:
        users.add(h.placed_by_user_id)
    b.send(
        db,
        project,
        users,
        f"hold:{h.id}:placed",
        f"Hold placed: {h.hold_no}",
        f"تم وضع حجز: {h.hold_no}",
        body_en=f"Reason: {h.reason.value}. Segregate and tag the stock.",
        body_ar="افصل المخزون المحجوز وضع عليه الوسم.",
        rt=RT,
        rid=h.id,
        path=f"/quality/holds/{h.id}",
    )


def create_api(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.hold_manage)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    zone_id = body.get("zone_id")
    if zone_id is not None:
        b.zone_of(db, project, zone_id)
    lines = body.get("lines") or []
    if not lines and not body.get("zone_level"):
        raise qc.field_err(
            "lines",
            "Add the held lines, or place a zone-level hold.",
            "أضف البنود أو ضع حجزاً على مستوى المنطقة.",
        )
    if body.get("zone_level") and zone_id is None:
        raise qc.field_err(
            "zone_id", "A zone-level hold names the zone.", "حدد المنطقة للحجز على مستوى المنطقة."
        )
    sc = None
    if zone_id is not None:
        from app.models.quality.q3 import QStorageZone  # noqa: PLC0415

        sz = db.get(QStorageZone, zone_id)
        sc = sz.storage_class if sz else None
    ncr_id = body.get("ncr_id")
    if ncr_id is not None:
        n = db.get(QNcr, ncr_id)
        if n is None or n.project_id != project.id:
            raise qc.field_err(
                "ncr_id", "The NCR is not on this project.", "التقرير ليس في المشروع."
            )
    h = place(
        db,
        project,
        site_id=site.id,
        reason=QHoldReason(body["reason"]),
        lines=lines,
        placed_by=p.user.id,
        zone_id=zone_id,
        zone_level=bool(body.get("zone_level")),
        storage_class=sc if sc == QStorageClass.pharma_2_8 else None,
        ncr_id=ncr_id,
        note=body.get("reason_note"),
        p=p,
    )
    return read(db, p, h)


def add_lines(
    db: Session, p: Principal, hold_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Q-HLD-02: a zone-level hold gets its lines."""
    h, project = get_hold(db, p, hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.hold_manage)
    b.require_site(g, h.site_id)
    _editable(h)
    t = now()
    lines = body.get("lines") or []
    if not lines:
        raise qc.field_err("lines", "Add at least one line.", "أضف بنداً واحداً على الأقل.")
    for raw in lines:
        db.add(_line(db, project, h, raw, t))
    h.zone_level = False
    h.lines_added_at = h.lines_added_at or t
    db.flush()
    refresh(db, h)
    return read(db, p, h)


def segregate(
    db: Session, p: Principal, hold_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Q-HLD-03: segregation with a photo."""
    h, project = get_hold(db, p, hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.hold_manage)
    b.require_site(g, h.site_id)
    _editable(h)
    seg = QSegregation(body["segregation"])
    photo = b.attachment_on(
        db, body.get("photo_attachment_id"), A.q_hold, h.id, "photo_attachment_id"
    )
    if photo is None:
        raise qc.field_err(
            "photo_attachment_id", "A segregation photo is required.", "صورة العزل مطلوبة."
        )
    if seg == QSegregation.moved_to_quarantine and not body.get("location"):
        raise qc.field_err("location", "Name the quarantine location.", "حدد موقع العزل.")
    h.segregation = seg
    h.segregation_location = body.get("location")
    h.segregation_photo_id = photo
    h.segregation_at = now()
    return read(db, p, h)


def wms_confirmed(db: Session, p: Principal, hold_id: uuid.UUID) -> dict[str, Any]:
    """Q-HLD-08: ticked by the user after the WMS update."""
    h, project = get_hold(db, p, hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.hold_manage)
    b.require_site(g, h.site_id)
    h.wms_confirmed = True
    h.wms_confirmed_at = now()
    return read(db, p, h)


# ---- release / reject (Q-HLD-04, -05) ------------------------------------------------------------


def _linked_ncrs(db: Session, h: QHold) -> list[QNcr]:
    ids: set[uuid.UUID] = set()
    if h.ncr_id:
        ids.add(h.ncr_id)
    for lk in db.scalars(
        select(QLink).where(
            ((QLink.from_type == RT.value) & (QLink.from_id == h.id) & (QLink.to_type == "ncr"))
            | ((QLink.to_type == RT.value) & (QLink.to_id == h.id) & (QLink.from_type == "ncr"))
        )
    ):
        ids.add(lk.to_id if lk.to_type == "ncr" else lk.from_id)
    if h.source_type == QRecordType.excursion.value and h.source_id:
        x = db.get(QExcursion, h.source_id)
        if x is not None and x.ncr_id:
            ids.add(x.ncr_id)
    return [n for n in (db.get(QNcr, i) for i in ids) if n is not None]


def _linked_excursions(db: Session, h: QHold) -> list[QExcursion]:
    rows = list(db.scalars(select(QExcursion).where(QExcursion.hold_id == h.id)))
    if h.source_type == QRecordType.excursion.value and h.source_id:
        x = db.get(QExcursion, h.source_id)
        if x is not None and x not in rows:
            rows.append(x)
    return rows


def _open_recalls(db: Session, project_id: uuid.UUID) -> list[QRecall]:
    return list(
        db.scalars(
            select(QRecall).where(
                QRecall.project_id == project_id,
                QRecall.recall_type != QRecallType.mock,
                QRecall.status.in_(
                    [QRecallStatus.open, QRecallStatus.traced, QRecallStatus.recovering]
                ),
            )
        )
    )


def open_recalls_for(db: Session, project_id: uuid.UUID, sku: str, batch: str) -> list[QRecall]:
    return [
        r
        for r in _open_recalls(db, project_id)
        if any(it.get("batch") == batch and it.get("sku") == sku for it in r.items or [])
    ]


NCR_NOT_APPROVED = frozenset({QNcrStatus.draft, QNcrStatus.open, QNcrStatus.disposition_proposed})
EXC_ASSESSED = frozenset(
    {
        QExcursionStatus.assessed,
        QExcursionStatus.closed,
        QExcursionStatus.dismissed,
        QExcursionStatus.voided,
    }
)


def _editable(h: QHold) -> None:
    if h.status in (QHoldStatus.closed, QHoldStatus.voided):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The hold is closed or voided.",
            "الحجز مغلق أو ملغى.",
        )


def void_auto(db: Session, project: Project, h: QHold, reason: str) -> bool:
    """An automatic hold whose source no longer needs it (an excursion that became a transient,
    Q-EXC-03) is voided while nothing on it has been decided; afterwards it stays for the
    responsible person (D-352)."""
    lines = lines_of(db, h)
    if h.status != QHoldStatus.on_hold or any(ln.line_status != L.on_hold for ln in lines):
        return False
    before = h.status
    h.status = QHoldStatus.voided
    h.closed_at = now()
    b.audit_status(db, None, project, RT, h.id, before, QHoldStatus.voided, reason=reason)
    return True


def blockers(
    db: Session, h: QHold, line: QHoldLine | None = None, *, rejecting: bool = False
) -> list[reg.Blocker]:
    out: list[reg.Blocker] = []
    for n in _linked_ncrs(db, h):
        if n.status in NCR_NOT_APPROVED:
            out.append(
                reg.Blocker(
                    "NCR_DISPOSITION_NOT_APPROVED",
                    f"{n.ncr_no or 'NCR (draft)'}: the disposition is not approved yet.",
                    f"{n.ncr_no or 'تقرير مسودة'}: المعالجة غير معتمدة بعد.",
                )
            )
    for x in _linked_excursions(db, h):
        if x.status not in EXC_ASSESSED:
            out.append(
                reg.Blocker(
                    "EXCURSION_NOT_ASSESSED",
                    f"{x.exc_no}: the product impact is not assessed yet.",
                    f"{x.exc_no}: لم يُقيَّم أثر الانحراف على المنتج بعد.",
                )
            )
    if not rejecting:
        recalls = _open_recalls(db, h.project_id)
        for ln in [line] if line else lines_of(db, h):
            for r in recalls:
                if not any(
                    it.get("batch") == ln.batch and it.get("sku") == ln.sku for it in r.items or []
                ):
                    continue
                out.append(
                    reg.Blocker(
                        "BATCH_IN_OPEN_RECALL",
                        f"Batch {ln.batch} is in open recall {r.rcl_no}; it may only be rejected.",
                        f"الدفعة {ln.batch} ضمن استدعاء مفتوح {r.rcl_no}؛ يجوز رفضها فقط.",
                    )
                )
    seen: set[tuple[str, str]] = set()
    uniq: list[reg.Blocker] = []
    for bl in out:
        if (bl.code, bl.detail_en) not in seen:
            seen.add((bl.code, bl.detail_en))
            uniq.append(bl)
    return uniq


def _blocked(bl: list[reg.Blocker]) -> Any:
    return qc.err(
        422,
        ErrorCode.HOLD_RELEASE_BLOCKED,
        "The hold cannot be released yet: " + " ".join(x.detail_en for x in bl),
        "لا يمكن الإفراج عن الحجز بعد: " + " ".join(x.detail_ar for x in bl),
        blockers=[{"code": x.code, "detail_en": x.detail_en, "detail_ar": x.detail_ar} for x in bl],
    )


def decide(db: Session, p: Principal, hold_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Release or reject lines (hold.release / hold.reject through the matrix)."""
    h, project = get_hold(db, p, hold_id)
    project, _ = b.project_for_progress(db, p, project.id, C.hold_manage, allow_n=True)
    if b.place_only(db, p, project.id):
        raise forbidden_error(
            "Warehouse QC may place holds; a responsible person releases or rejects them."
        )
    _editable(h)
    action = body.get("action")
    if action not in ("release", "reject"):
        raise qc.field_err("action", "Action is release or reject.", "الإجراء: إفراج أو رفض.")
    ids = set(body.get("line_ids") or [])
    lines = [
        ln for ln in lines_of(db, h) if ln.line_status == L.on_hold and (not ids or ln.id in ids)
    ]
    if not lines:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "No line on hold to decide.",
            "لا يوجد بند محجوز لاتخاذ القرار.",
        )
    rejecting = action == "reject"
    why: str | None = (
        qc.reason(body.get("reason"), 20)
        if rejecting
        else ((body.get("reason") or "").strip() or None)
    )
    bl: list[reg.Blocker] = []
    for ln in lines:
        bl += blockers(db, h, ln, rejecting=rejecting)
    if bl:
        raise _blocked(list({(x.code, x.detail_en): x for x in bl}.values()))
    owner_file = b.attachment_on(
        db, body.get("owner_decision_attachment_id"), A.q_hold, h.id, "owner_decision_attachment_id"
    )
    if not rejecting:
        for ln in lines:
            cust = db.get(QCustomer, ln.owner_customer_id) if ln.owner_customer_id else None
            if (
                cust is not None
                and cust.owner_release_approval
                and not (owner_file or ln.owner_decision_attachment_id)
            ):
                raise qc.err(
                    422,
                    ErrorCode.OWNER_DECISION_REQUIRED,
                    f"{cust.name_en} decides on its goods: attach the owner's written decision "
                    "(Q-HLD-05).",
                    f"يقرر {cust.name_ar} بشأن بضاعته: أرفق قرار المالك المكتوب.",
                )
    s = b.sign(
        db,
        p,
        project,
        RT,
        h.id,
        action,
        ctx(h),
        decision="approved",
        comment=body.get("comment") or why,
        qualifier=qualifier(h),
        evidence=[x for x in [owner_file] if x],
    )
    t = now()
    for ln in lines:
        ln.line_status = L.rejected if rejecting else L.released
        ln.reason = why
        ln.decided_by_user_id = p.user.id
        ln.decided_at = t
        if owner_file and not ln.owner_decision_attachment_id:
            ln.owner_decision_attachment_id = owner_file
    db.flush()
    refresh(db, h)
    b.audit_status(db, p, project, RT, h.id, "on_hold", action, lines=len(lines), signoff=str(s.id))
    return read(db, p, h)


def rehold(db: Session, p: Principal, line_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Released → On Hold on new information (270, reason ≥ 20 chars)."""
    ln = db.get(QHoldLine, line_id)
    if ln is None:
        raise b.not_found(db, p, RT, line_id, None)
    h, project = get_hold(db, p, ln.hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.hold_manage)
    b.require_site(g, h.site_id)
    _editable(h)
    if ln.line_status != L.released:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a released line can be held again.",
            "يمكن إعادة حجز بند مُفرج عنه فقط.",
        )
    ln.reason = qc.reason(body.get("reason"))
    ln.line_status = L.on_hold
    h.closed_at = None
    refresh(db, h)
    return read(db, p, h)


def outcome(db: Session, p: Principal, line_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Rejected → Destroyed / Returned (269) with the evidence file (Q-HLD-06)."""
    ln = db.get(QHoldLine, line_id)
    if ln is None:
        raise b.not_found(db, p, RT, line_id, None)
    h, project = get_hold(db, p, ln.hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.stock_record)
    b.require_site(g, h.site_id)
    if ln.line_status != L.rejected or ln.final_outcome is not None:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a rejected line without an outcome.",
            "فقط بند مرفوض بلا نتيجة نهائية.",
        )
    ev = b.attachment_on(
        db, body.get("evidence_attachment_id"), A.q_hold, h.id, "evidence_attachment_id"
    )
    if ev is None:
        raise qc.field_err(
            "evidence_attachment_id",
            "Attach the destruction certificate or the return note.",
            "أرفق شهادة الإتلاف أو مذكرة الإرجاع.",
        )
    ln.final_outcome = QHoldOutcome(body["outcome"])
    ln.evidence_attachment_id = ev
    ln.outcome_at = body.get("at") or now()
    refresh(db, h)
    return read(db, p, h)


def close(db: Session, p: Principal, hold_id: uuid.UUID) -> dict[str, Any]:
    h, project = get_hold(db, p, hold_id)
    _, g = b.project_for_progress(db, p, project.id, C.hold_manage)
    b.require_site(g, h.site_id)
    lines = lines_of(db, h)
    problems = []
    if not lines or any(ln.line_status == L.on_hold for ln in lines):
        problems.append(("lines", "Lines are still on hold.", "ما زالت بنود محجوزة."))
    if any(
        ln.line_status == L.rejected
        and (ln.final_outcome is None or ln.evidence_attachment_id is None)
        for ln in lines
    ):
        problems.append(
            (
                "lines",
                "A rejected line has no destruction certificate or return note (Q-HLD-06).",
                "بند مرفوض بلا شهادة إتلاف أو مذكرة إرجاع.",
            )
        )
    if problems:
        raise qc.field_err(
            problems[0][0], " ".join(x[1] for x in problems), " ".join(x[2] for x in problems)
        )
    h.status = QHoldStatus.closed
    h.closed_at = now()
    after_change(db, h)
    return read(db, p, h)


def derived(lines: list[QHoldLine]) -> QHoldStatus:
    if not lines or any(ln.line_status == L.on_hold for ln in lines):
        return QHoldStatus.on_hold
    st = {ln.line_status for ln in lines}
    if any(ln.line_status == L.rejected and ln.final_outcome is None for ln in lines):
        if st == {L.rejected}:
            return QHoldStatus.rejected
        return QHoldStatus.partly_released
    return QHoldStatus.closed


def refresh(db: Session, h: QHold) -> QHoldStatus:
    if h.status == QHoldStatus.voided:
        return h.status
    st = derived(lines_of(db, h))
    if st != h.status:
        h.status = st
        h.closed_at = now() if st == QHoldStatus.closed else None
    db.flush()
    after_change(db, h)
    return h.status


def after_change(db: Session, h: QHold) -> None:
    """A final hold may close its excursion (Assessed → Closed, §D.4)."""
    from app.services.quality.q3 import excursions  # noqa: PLC0415

    for x in _linked_excursions(db, h):
        excursions.maybe_close(db, x)


def final(db: Session, h: QHold) -> bool:
    return all(
        ln.line_status == L.released
        or (ln.line_status == L.rejected and ln.final_outcome is not None)
        for ln in lines_of(db, h)
    )


# ---- read model ---------------------------------------------------------------------------------


def line_read(db: Session, ln: QHoldLine) -> dict[str, Any]:
    prod = db.get(QProduct, ln.product_id) if ln.product_id else None
    return {
        "id": ln.id,
        "owner": b.customer_ref(db, ln.owner_customer_id),
        "product_id": ln.product_id,
        "sku": ln.sku,
        "description_en": prod.description_en if prod else None,
        "description_ar": prod.description_ar if prod else None,
        "batch": ln.batch,
        "expiry_date": ln.expiry_date,
        "qty": ln.qty,
        "unit": ln.unit,
        "location": ln.location,
        "line_status": ln.line_status,
        "proposed_decision": ln.proposed_decision,
        "owner_decision_attachment_id": ln.owner_decision_attachment_id,
        "final_outcome": ln.final_outcome,
        "evidence_attachment_id": ln.evidence_attachment_id,
        "outcome_at": ln.outcome_at,
        "reason": ln.reason,
        "decided_at": ln.decided_at,
    }


def age_days(h: QHold, today: date) -> int:
    return (today - b.local_day(h.placed_at)).days


def read(db: Session, p: Principal, h: QHold) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    project = db.get(Project, h.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, project.id)
    lines = lines_of(db, h)
    bl = blockers(db, h)
    actions = []
    if p.grant(project.id, C.hold_manage) is not None:
        live = any(ln.line_status == L.on_hold for ln in lines)
        if live and not b.place_only(db, p, project.id):
            for step in ("release", "reject"):
                if b.resolves(db, p, project, RT, h.id, step, ctx(h), qualifier(h)):
                    actions.append(step)
    return {
        "id": h.id,
        "project_id": h.project_id,
        "hold_no": h.hold_no,
        "site": b.site_ref(db, h.site_id),
        "zone": b.zone_ref(db, h.zone_id),
        "reason": h.reason,
        "reason_note": h.reason_note,
        "source_type": h.source_type,
        "source_id": h.source_id,
        "source_ref": h.source_ref,
        "ncr_id": h.ncr_id,
        "zone_level": h.zone_level,
        "storage_class": h.storage_class,
        "segregation": h.segregation,
        "segregation_location": h.segregation_location,
        "segregation_photo_id": None if hide else h.segregation_photo_id,
        "segregation_at": h.segregation_at,
        "wms_confirmed": h.wms_confirmed,
        "wms_confirmed_at": h.wms_confirmed_at,
        "placed_by": b.user_ref(db, h.placed_by_user_id, hide),
        "placed_at": h.placed_at,
        "status": h.status,
        "age_days": age_days(h, qc.project_day(project)),
        "lines": [line_read(db, ln) for ln in lines],
        "blockers": [
            {"code": x.code, "detail_en": x.detail_en, "detail_ar": x.detail_ar} for x in bl
        ],
        "allowed_actions": actions,
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, h.id)
        ],
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page_no: int,
    size: int,
    *,
    statuses: list[QHoldStatus] | None = None,
    reason: QHoldReason | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    deadlines(db, now(), project.id)  # Q-HLD-02 / -03 on time without an hourly slot (D-355)
    stmt = select(QHold).where(QHold.project_id == project.id)
    if statuses:
        stmt = stmt.where(QHold.status.in_(statuses))
    if reason:
        stmt = stmt.where(QHold.reason == reason)
    if q:
        stmt = stmt.where(QHold.hold_no.ilike(f"%{q}%") | QHold.source_ref.ilike(f"%{q}%"))
    today = qc.project_day(project)
    items = []
    for h in db.scalars(stmt.order_by(QHold.placed_at.desc())):
        if g.scope.value == "responsible":
            if not b.can_view(db, p, project, RT, h.id, h.site_id, lambda h=h: _steps(h)):
                continue
        elif not g.covers_site(h.site_id):
            continue
        lines = lines_of(db, h)
        items.append(
            {
                "id": h.id,
                "hold_no": h.hold_no,
                "reason": h.reason,
                "status": h.status,
                "zone": b.zone_ref(db, h.zone_id),
                "zone_level": h.zone_level,
                "source_ref": h.source_ref,
                "placed_at": h.placed_at,
                "age_days": age_days(h, today),
                "lines": len(lines),
                "lines_on_hold": sum(1 for ln in lines if ln.line_status == L.on_hold),
                "qty_on_hold": sum(
                    (ln.qty for ln in lines if ln.line_status == L.on_hold), Decimal(0)
                ),
                "blocked": bool(blockers(db, h)) if h.status == QHoldStatus.on_hold else False,
                "segregated": h.segregation is not None,
                "wms_confirmed": h.wms_confirmed,
            }
        )
    return b.page(items, page_no, size)


def export_csv(db: Session, p: Principal, project_id: uuid.UUID) -> bytes:
    """Q-HLD-08: owner, sku, batch, location, qty, hold no, status (WMS-friendly)."""
    project = qc.get_project(db, p, project_id)
    p.require(project.id, C.export_quality)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["owner", "sku", "batch", "location", "qty", "unit", "hold_no", "status"])
    for h in db.scalars(
        select(QHold).where(QHold.project_id == project.id).order_by(QHold.hold_no)
    ):
        for ln in lines_of(db, h):
            cust = db.get(QCustomer, ln.owner_customer_id) if ln.owner_customer_id else None
            w.writerow(
                [
                    cust.code if cust else "",
                    ln.sku,
                    ln.batch,
                    ln.location or "",
                    ln.qty,
                    ln.unit,
                    h.hold_no,
                    ln.line_status.value,
                ]
            )
    from app.core.enums import AuditAction  # noqa: PLC0415
    from app.services import audit  # noqa: PLC0415

    audit.record(
        db,
        AuditAction.export,
        p.actor(project.id),
        project_id=project.id,
        details={"dataset": "quality_holds_wms"},
    )
    return buf.getvalue().encode("utf-8-sig")


# ---- deadlines (Q-HLD-02, -03, -07) --------------------------------------------------------------


def deadlines(db: Session, at: datetime, project_id: uuid.UUID | None = None) -> int:
    """Zone-level holds without lines 24 h after placing; segregation not recorded 4 h after
    placing; checked by the jobs, on every hold list read and with the Quality home tiles (each
    alert once, D-355)."""
    n = 0
    q = select(QHold).where(QHold.status == QHoldStatus.on_hold)
    if project_id is not None:
        q = q.where(QHold.project_id == project_id)
    for h in db.scalars(q):
        project = db.get(Project, h.project_id)
        if project is None:
            continue
        mgr = b.holders(db, project, C.storage_manage, h.site_id)
        if h.zone_level and h.lines_added_at is None and at >= h.placed_at + timedelta(hours=24):
            users = mgr | qc.ids(h.placed_by_user_id)
            n += b.send(
                db,
                project,
                users,
                f"hold:{h.id}:no_lines",
                f"{h.hold_no}: zone-level hold still has no lines",
                f"{h.hold_no}: الحجز على مستوى المنطقة بلا بنود",
                rt=RT,
                rid=h.id,
                path=f"/quality/holds/{h.id}",
            )
        if h.segregation_at is None and at >= h.placed_at + timedelta(hours=4):
            n += b.send(
                db,
                project,
                qc.ids(h.placed_by_user_id) | mgr,
                f"hold:{h.id}:segregation",
                f"{h.hold_no}: record the segregation with a photo",
                f"{h.hold_no}: سجّل العزل مع صورة",
                rt=RT,
                rid=h.id,
                path=f"/quality/holds/{h.id}",
                email=False,
            )
    return n


def ageing(db: Session, at: datetime) -> int:
    """Q-HLD-07: holds on hold longer than `hold_ageing_days` alert the release resolvers weekly."""
    n = 0
    for h in db.scalars(select(QHold).where(QHold.status == QHoldStatus.on_hold)):
        project = db.get(Project, h.project_id)
        if project is None:
            continue
        days = int(b.setting(db, project.id, "hold_ageing_days"))
        if at < h.placed_at + timedelta(days=days):
            continue
        week = b.local_day(at).isocalendar()
        users = b.resolvers(
            db, project, RT, "release", ctx(h), qualifier=qualifier(h), record_id=h.id
        )
        n += b.send(
            db,
            project,
            users,
            f"hold:{h.id}:ageing:{week[0]}-{week[1]}",
            f"{h.hold_no} has been on hold for over {days} days",
            f"{h.hold_no} محجوز منذ أكثر من {days} يوماً",
            rt=RT,
            rid=h.id,
            path=f"/quality/holds/{h.id}",
        )
    return n


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    for h in db.scalars(
        select(QHold).where(QHold.project_id == project.id, QHold.status == QHoldStatus.on_hold)
    ):
        if blockers(db, h):
            continue
        c = ctx(h)
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT,
                    h.id,
                    project.id,
                    h.hold_no,
                    f"{h.reason.value} hold",
                    "release",
                    h.placed_at,
                    f"/quality/holds/{h.id}",
                    "Q3",
                ),
                qualifier(h),
                h.site_id,
                None,
                c.requesters,
            )
        )
    return out
