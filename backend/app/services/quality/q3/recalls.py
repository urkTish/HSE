"""Recalls and mock recalls (spec 8-quality §D.8, Q-RCL-01…06): the trace from Q3 data only
(received, on hand, shipped by consignee, destroyed, unaccounted), the recall hold on every
on-hand line (real recalls), consignee contacts, effectiveness and trace time against the
targets, the critical NCR of a real recall and the mock recall due alert."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.quality.common import (
    QDetectionStage,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QRecordType,
)
from app.core.quality.q3 import (
    QHoldLineStatus,
    QHoldOutcome,
    QHoldReason,
    QRecallClass,
    QRecallStatus,
    QRecallType,
)
from app.models import Project, Site
from app.models.quality.q3 import (
    QDamageReport,
    QHold,
    QHoldLine,
    QProduct,
    QReceipt,
    QReceiptLine,
    QRecall,
    QRecallItem,
    QShipment,
    QShipmentLine,
    QStockLine,
)
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b
from app.services.quality.q3 import holds as hold_svc
from app.services.quality.q3 import stock as stock_svc

C = Capability
RT = QRecordType.recall
ST = QRecallStatus
LIVE = frozenset({ST.open, ST.traced, ST.recovering})
ZERO = Decimal(0)


def ctx(r: QRecall) -> rpm.Ctx:
    return rpm.Ctx(site_id=r.site_id, requesters=qc.ids(r.created_by_user_id))


def get_recall(db: Session, p: Principal, rid: uuid.UUID) -> tuple[QRecall, Project]:
    r = db.get(QRecall, rid)
    if r is None or not p.can_see_project(r.project_id):
        raise b.not_found(db, p, RT, rid, r.project_id if r else None)
    project = qc.get_project(db, p, r.project_id)
    if not b.can_view(db, p, project, RT, r.id, r.site_id, lambda: [("close", ctx(r), None)] if r.status in LIVE else []):
        raise b.not_found(db, p, RT, rid, project.id)
    return r, project


def keys(r: QRecall) -> set[tuple[str, str]]:
    return {(it["sku"], it["batch"]) for it in r.items or []}


# ---- trace (Q-RCL-02) -----------------------------------------------------------------------------


def trace(db: Session, r: QRecall) -> dict[str, Any]:
    ks = keys(r)
    batches = [k[1] for k in ks]
    received = ZERO
    for ln, rc in db.execute(
        select(QReceiptLine, QReceipt)
        .join(QReceipt, QReceipt.id == QReceiptLine.receipt_id)
        .where(QReceipt.project_id == r.project_id, QReceiptLine.batch.in_(batches))
    ).all():
        prod = db.get(QProduct, ln.product_id)
        if prod is not None and (prod.sku, ln.batch) in ks and rc.status.value != "cancelled":
            received += ln.qty_received
    snap = stock_svc.first_at_or_after(db, r.site_id, r.initiated_at)
    old = False
    if snap is None:
        snap = stock_svc.latest_before(db, r.site_id, r.initiated_at)
        old = snap is not None
    on_hand = ZERO
    on_hand_lines: list[QStockLine] = []
    for sl in stock_svc.lines(db, snap):
        if (sl.sku, sl.batch) in ks and sl.qty > 0:
            on_hand += sl.qty
            on_hand_lines.append(sl)
    shipped = ZERO
    by_consignee: dict[str, dict[str, Any]] = defaultdict(lambda: {"qty": ZERO, "shipments": 0, "customer_id": None, "first": None, "last": None})
    for shl, s in db.execute(
        select(QShipmentLine, QShipment)
        .join(QShipment, QShipment.id == QShipmentLine.shipment_id)
        .where(QShipment.project_id == r.project_id, QShipmentLine.batch.in_(batches))
    ).all():
        if (shl.sku, shl.batch) not in ks:
            continue
        q = shl.delivered_qty if shl.delivered_qty is not None else shl.ordered_qty
        shipped += q
        c = by_consignee[s.consignee_name]
        c["qty"] += q
        c["shipments"] += 1
        c["customer_id"] = s.consignee_customer_id
        when = s.delivered_at or s.dispatched_at
        if when is not None:
            c["first"] = min(c["first"] or when, when)
            c["last"] = max(c["last"] or when, when)
    destroyed = ZERO
    for hl in db.scalars(
        select(QHoldLine)
        .join(QHold, QHold.id == QHoldLine.hold_id)
        .where(QHold.project_id == r.project_id, QHoldLine.batch.in_(batches), QHoldLine.line_status == QHoldLineStatus.rejected, QHoldLine.final_outcome == QHoldOutcome.destroyed)
    ):
        if (hl.sku, hl.batch) in ks:
            destroyed += hl.qty
    for d in db.scalars(select(QDamageReport).where(QDamageReport.project_id == r.project_id, QDamageReport.batch.in_(batches), QDamageReport.destroyed_on_spot.is_(True))):
        prod = db.get(QProduct, d.product_id)
        if prod is not None and (prod.sku, d.batch) in ks:
            destroyed += d.qty
    return {
        "received": received,
        "on_hand": on_hand,
        "shipped": shipped,
        "destroyed": destroyed,
        "unaccounted": received - on_hand - shipped - destroyed,
        "snapshot_id": snap.id if snap else None,
        "snapshot_as_of": snap.as_of if snap else None,
        "snapshot_old": old,
        "consignees": [
            {"name": k, "customer_id": v["customer_id"], "qty": v["qty"], "shipments": v["shipments"], "first": v["first"], "last": v["last"]}
            for k, v in sorted(by_consignee.items())
        ],
        "_lines": on_hand_lines,
    }


def effectiveness(db: Session, r: QRecall, t: dict[str, Any]) -> Decimal | None:
    """Q-RCL-04."""
    if not t["received"]:
        return None
    if r.recall_type == QRecallType.mock:
        named = sum((c["qty"] for c in t["consignees"] if c["name"] and c["name"] != "—"), ZERO)
        num: Decimal = t["on_hand"] + named + t["destroyed"]
    else:
        items = list(db.scalars(select(QRecallItem).where(QRecallItem.recall_id == r.id)))
        num = t["on_hand"] + sum((i.qty_retrieved for i in items), ZERO) + sum((i.qty_destroyed_by_consignee for i in items), ZERO) + t["destroyed"]
    received: Decimal = t["received"]
    return (num * 100 / received).quantize(Decimal("0.1"), ROUND_HALF_UP)


def _jsonable(t: dict[str, Any]) -> dict[str, Any]:
    def conv(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, uuid.UUID):
            return str(v)
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v

    return {k: conv(v) for k, v in t.items() if not k.startswith("_")}


# ---- transitions ---------------------------------------------------------------------------------


def create(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT, C.recall_manage)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    items = []
    for it in body.get("items") or []:
        prod = db.get(QProduct, it["product_id"]) if it.get("product_id") else None
        sku = prod.sku if prod else (it.get("sku") or "").strip()
        if not sku or not (it.get("batch") or "").strip():
            raise qc.field_err("items", "Each item needs a product and a batch (Q-RCL-01).", "كل بند يحتاج منتجاً ودفعة.")
        items.append({"product_id": str(prod.id) if prod else None, "sku": sku, "batch": it["batch"].strip()})
    if not items:
        raise qc.field_err("items", "A recall needs at least one product and batch (Q-RCL-01).", "الاستدعاء يحتاج منتجاً ودفعة على الأقل.")
    rtype = QRecallType(body["recall_type"])
    if rtype == QRecallType.regulator and not (body.get("external_ref") or "").strip():
        raise qc.field_err("external_ref", "A regulator recall needs the external reference (e.g. the SFDA notice).", "استدعاء الجهة الرقابية يحتاج المرجع الخارجي.")
    at = body.get("initiated_at") or now()
    r = QRecall(
        id=uuid.uuid4(),
        project_id=project.id,
        rcl_no=b.number(db, project, RT, at),
        site_id=site.id,
        recall_type=rtype,
        recall_class=QRecallClass(body["recall_class"]) if body.get("recall_class") else None,
        items=items,
        reason=qc.reason(body.get("reason"), 10),
        external_ref=body.get("external_ref"),
        supplier_id=body.get("supplier_id"),
        initiated_at=at,
        status=ST.open,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    if rtype != QRecallType.mock:
        start_real(db, p, project, r)
    b.audit_create(db, p, project, RT, r.id, type=rtype.value)
    return read(db, p, r)


def start_real(db: Session, p: Principal | None, project: Project, r: QRecall, *, notify: bool = True) -> None:
    """Q-RCL-03 hold on every on-hand line of the traced snapshot; Q-RCL-06 critical NCR."""
    from app.services.quality.ncr import core as ncr  # noqa: PLC0415

    t = trace(db, r)
    r.snapshot_id = t["snapshot_id"]
    uid = p.user.id if p else r.created_by_user_id
    h = hold_svc.place(
        db,
        project,
        site_id=r.site_id,
        reason=QHoldReason.recall,
        lines=[stock_svc._line_from_stock(x) for x in t["_lines"]],  # noqa: SLF001
        placed_by=uid,
        zone_level=not t["_lines"],
        source=(RT, r.id, r.rcl_no),
        p=p,
        note="Recalled lines may only be rejected (Q-HLD-04).",
    )
    r.hold_id = h.id
    n = ncr.auto_raise(
        db,
        project,
        QNcrSourceType.recall,
        r.id,
        raised_by=uid,
        owner_id=b.ncr_owner(db, project, uid),
        classification=QNcrClass.critical,
        category=QNcrCategory.traceability,
        title=f"Recall {r.rcl_no}: {', '.join(f'{i['sku']} {i['batch']}' for i in r.items)}"[:150],
    )
    r.ncr_id = n.id
    h.ncr_id = n.id
    if notify:
        users = b.holders(db, project, C.recall_manage, r.site_id)
        users |= set(b.resolvers(db, project, RT, "close", ctx(r), record_id=r.id))
        users |= set(b.resolvers(db, project, QRecordType.hold, "release", hold_svc.ctx(h), record_id=h.id))
        b.send(
            db,
            project,
            users,
            f"rcl:{r.id}:opened",
            f"Recall opened: {r.rcl_no}",
            f"تم فتح استدعاء: {r.rcl_no}",
            body_en=f"Batches: {', '.join(i['batch'] for i in r.items)}. Stock on hand is held.",
            body_ar="تم حجز المخزون الموجود من الدفعات المستدعاة.",
            rt=RT,
            rid=r.id,
            path=f"/quality/recalls/{r.id}",
        )


def confirm_trace(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Open → Traced: the trace reviewed and confirmed; trace_completed_at set."""
    r, project = get_recall(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.recall_manage)
    b.require_site(g, r.site_id)
    if r.status != ST.open:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "Only an open recall.", "استدعاء مفتوح فقط.")
    t = trace(db, r)
    r.trace = _jsonable(t)
    r.trace_completed_at = body.get("completed_at") or now()
    r.effectiveness_pct = effectiveness(db, r, t)
    if r.recall_type != QRecallType.mock:
        for c in t["consignees"]:
            db.add(QRecallItem(recall_id=r.id, consignee_customer_id=c["customer_id"], consignee_name=c["name"], qty_shipped=c["qty"]))
    r.status = ST.traced
    b.audit_status(db, p, project, RT, r.id, ST.open, ST.traced)
    return read(db, p, r)


def recover(db: Session, p: Principal, rid: uuid.UUID) -> dict[str, Any]:
    r, project = get_recall(db, p, rid)
    _, g = b.project_for_progress(db, p, project.id, C.recall_manage)
    b.require_site(g, r.site_id)
    if r.status != ST.traced or r.recall_type == QRecallType.mock:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "A traced real recall moves to recovering.", "الاستدعاء الحقيقي المتتبع فقط.")
    r.status = ST.recovering
    b.audit_status(db, p, project, RT, r.id, ST.traced, ST.recovering)
    return read(db, p, r)


def update_item(db: Session, p: Principal, item_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    it = db.get(QRecallItem, item_id)
    if it is None:
        raise b.not_found(db, p, RT, item_id, None)
    r, project = get_recall(db, p, it.recall_id)
    _, g = b.project_for_progress(db, p, project.id, C.recall_manage)
    b.require_site(g, r.site_id)
    if r.status not in (ST.traced, ST.recovering):
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "Consignee contacts are recorded while traced or recovering.", "تُسجل الاتصالات أثناء التتبع أو الاسترجاع.")
    for k in ("contacted_at", "method", "response"):
        if k in body:
            setattr(it, k, body[k])
    for k in ("qty_retrieved", "qty_destroyed_by_consignee"):
        if body.get(k) is not None:
            v = Decimal(str(body[k]))
            if v < 0:
                raise qc.field_err(k, "Must be zero or more.", "يجب ألا تكون سالبة.")
            setattr(it, k, v)
    if it.qty_retrieved + it.qty_destroyed_by_consignee > it.qty_shipped:
        raise qc.field_err("qty_retrieved", "More than was shipped to this consignee.", "أكثر مما شُحن لهذا المستلم.")
    r.effectiveness_pct = effectiveness(db, r, trace(db, r))
    return read(db, p, r)


def close(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Recovering → Closed (real) · Traced → Closed (mock): 271 + RPM `recall.close`; below the
    effectiveness target needs a justification ≥ 50 chars (Q-RCL-04); every recalled hold line
    rejected with its outcome (real)."""
    r, project = get_recall(db, p, rid)
    project, _ = b.project_for_progress(db, p, project.id, C.recall_manage, allow_n=True)
    ok_from = ST.traced if r.recall_type == QRecallType.mock else ST.recovering
    if r.status != ok_from:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, f"Close from {ok_from.value}.", "لا يمكن الإغلاق من هذه الحالة.")
    t = trace(db, r)
    eff = effectiveness(db, r, t)
    target = b.dsetting(db, project.id, "recall_effectiveness_target_pct")
    just = (body.get("justification") or "").strip()
    if eff is not None and eff < target and len(just) < 50:
        raise qc.err(
            422,
            ErrorCode.RECALL_TARGET_NOT_MET,
            f"Effectiveness {eff} % is below the {target} % target: justify in at least 50 characters.",
            f"الفعالية {eff} % أقل من الهدف {target} %: اكتب مبرراً لا يقل عن 50 حرفاً.",
        )
    if r.recall_type != QRecallType.mock and r.hold_id:
        h = db.get(QHold, r.hold_id)
        bad = [ln for ln in hold_svc.lines_of(db, h) if ln.line_status != QHoldLineStatus.rejected or ln.final_outcome is None] if h else []
        if bad:
            raise qc.err(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Every recalled hold line must be rejected with its final outcome before closing.",
                "يجب رفض كل بنود الحجز المستدعاة مع نتيجتها النهائية قبل الإغلاق.",
            )
    b.sign(db, p, project, RT, r.id, "close", ctx(r), comment=just or body.get("comment"))
    r.trace = _jsonable(t)
    r.effectiveness_pct = eff
    r.justification = just or None
    r.status = ST.closed
    r.closed_at = now()
    b.audit_status(db, p, project, RT, r.id, ok_from, ST.closed, effectiveness=str(eff))
    return read(db, p, r)


def cancel(db: Session, p: Principal, rid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    r, project = get_recall(db, p, rid)
    project, _ = b.project_for_progress(db, p, project.id, C.recall_manage, allow_n=True)
    if r.status not in LIVE:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "The recall is closed.", "الاستدعاء مغلق.")
    why = qc.reason(body.get("reason"))
    b.sign(db, p, project, RT, r.id, "close", ctx(r), comment=f"Cancelled: {why}")
    before = r.status
    r.status = ST.cancelled
    r.cancel_reason = why
    b.audit_status(db, p, project, RT, r.id, before, ST.cancelled, reason=why)
    return read(db, p, r)


# ---- reads, jobs, NCR source -----------------------------------------------------------------------


def trace_minutes(r: QRecall) -> int | None:
    if r.trace_completed_at is None:
        return None
    return b.minutes(r.initiated_at, r.trace_completed_at)


def read(db: Session, p: Principal, r: QRecall) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, project.id)
    live = trace(db, r)
    eff = effectiveness(db, r, live)
    tm = trace_minutes(r)
    target_h = int(b.setting(db, project.id, "recall_trace_target_hours"))
    items = list(db.scalars(select(QRecallItem).where(QRecallItem.recall_id == r.id).order_by(QRecallItem.consignee_name)))
    warnings = []
    if live["snapshot_old"]:
        warnings.append({"code": "SNAPSHOT_OLD", "message": "No snapshot at or after the recall start; the latest before it is used.", "message_ar": "لا توجد لقطة بعد بدء الاستدعاء؛ استُخدمت آخر لقطة قبله."})
    return {
        "id": r.id,
        "rcl_no": r.rcl_no,
        "site_id": r.site_id,
        "recall_type": r.recall_type,
        "recall_class": r.recall_class,
        "items": r.items,
        "reason": r.reason,
        "external_ref": r.external_ref,
        "supplier": b.supplier_ref(db, r.supplier_id),
        "initiated_at": r.initiated_at,
        "status": r.status,
        "trace": _jsonable(live),
        "trace_confirmed": r.trace,
        "trace_completed_at": r.trace_completed_at,
        "trace_minutes": tm,
        "trace_target_hours": target_h,
        "trace_slow": tm is not None and tm > target_h * 60,
        "effectiveness_pct": eff,
        "effectiveness_target_pct": b.dsetting(db, project.id, "recall_effectiveness_target_pct"),
        "justification": r.justification,
        "hold_id": r.hold_id,
        "ncr_id": r.ncr_id,
        "cancel_reason": r.cancel_reason,
        "closed_at": r.closed_at,
        "consignee_contacts": [
            {
                "id": i.id,
                "consignee_name": i.consignee_name,
                "qty_shipped": i.qty_shipped,
                "contacted_at": i.contacted_at,
                "method": i.method,
                "response": i.response,
                "qty_retrieved": i.qty_retrieved,
                "qty_destroyed_by_consignee": i.qty_destroyed_by_consignee,
            }
            for i in items
        ],
        "can_close": r.status in LIVE and b.resolves(db, p, project, RT, r.id, "close", ctx(r)),
        "warnings": warnings,
        "created_by": b.user_ref(db, r.created_by_user_id, hide),
        "signoffs": [signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, r.id)],
    }


def list_recalls(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    out = []
    for r in db.scalars(select(QRecall).where(QRecall.project_id == project.id).order_by(QRecall.initiated_at.desc())):
        if g.scope.value == "responsible":
            if not b.can_view(db, p, project, RT, r.id, r.site_id, lambda r=r: [("close", ctx(r), None)] if r.status in LIVE else []):
                continue
        out.append(
            {
                "id": r.id,
                "rcl_no": r.rcl_no,
                "recall_type": r.recall_type,
                "recall_class": r.recall_class,
                "batches": [i["batch"] for i in r.items],
                "status": r.status,
                "initiated_at": r.initiated_at,
                "effectiveness_pct": r.effectiveness_pct,
                "trace_minutes": trace_minutes(r),
            }
        )
    return out


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    for r in db.scalars(select(QRecall).where(QRecall.project_id == project.id, QRecall.status.in_([ST.recovering, ST.traced]))):
        if r.status == ST.traced and r.recall_type != QRecallType.mock:
            continue
        out.append(
            reg.OpenStep(
                reg.PendingStep(RT, r.id, project.id, r.rcl_no, f"Recall {r.recall_type.value}", "close", r.trace_completed_at or r.initiated_at, f"/quality/recalls/{r.id}", "Q3"),
                None,
                r.site_id,
                None,
                ctx(r).requesters,
            )
        )
    return out


def mock_due(db: Session, at: datetime) -> int:
    """Q-RCL-05: a site without a closed mock recall in the last `mock_recall_months` alerts the
    239 holders monthly."""
    from app.core.quality.common import QSectorProfile  # noqa: PLC0415

    n = 0
    for project in db.scalars(select(Project)):
        if qc.profile_of(db, project.id) != QSectorProfile.logistics:
            continue
        months = int(b.setting(db, project.id, "mock_recall_months"))
        since = at - timedelta(days=round(months * 30.44))
        for site in db.scalars(select(Site).where(Site.project_id == project.id)):
            last = db.scalar(
                select(QRecall.closed_at).where(QRecall.site_id == site.id, QRecall.recall_type == QRecallType.mock, QRecall.status == ST.closed).order_by(QRecall.closed_at.desc()).limit(1)
            )
            if last is not None and last >= since:
                continue
            month = b.local_day(at).strftime("%Y-%m")
            n += b.send(
                db,
                project,
                b.holders(db, project, C.quality_settings),
                f"rcl:mockdue:{site.id}:{month}",
                f"{site.code}: a mock recall is due",
                f"{site.code}: يستحق إجراء استدعاء تجريبي",
                path="/quality/recalls",
                email=False,
            )
    return n


def last_mock(db: Session, project: Project) -> QRecall | None:
    return db.scalar(
        select(QRecall).where(QRecall.project_id == project.id, QRecall.recall_type == QRecallType.mock, QRecall.status == ST.closed).order_by(QRecall.closed_at.desc()).limit(1)
    )


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    r = db.get(QRecall, source_id)
    if r is None or r.project_id != project.id:
        raise qc.field_err("source_id", "The recall is not on this project.", "الاستدعاء ليس في المشروع.")
    return reg.SourceInfo(
        ref=r.rcl_no,
        title=f"Recall {r.rcl_no}",
        site_id=r.site_id,
        engagement_id=b.operator_engagement(db, project),
        supplier_id=r.supplier_id,
        item_key=f"RCL:{','.join(sorted(i['batch'] for i in r.items))}"[:80],
        detection_stage=QDetectionStage.regulator if r.recall_type == QRecallType.regulator else QDetectionStage.at_customer,
        requirement_en="Recalled product traced, held and recovered (Q-RCL).",
        requirement_ar="تتبع المنتج المستدعى وحجزه واسترجاعه.",
        finding_en=r.reason,
        finding_ar=r.reason,
        proposed_class=QNcrClass.critical,
        lot_refs=tuple(i["batch"] for i in r.items),
        record_type=RT,
    )
