"""Stock quality (spec 8-quality §D.7.1, §D.7.2, §D.7.4): stock snapshots ("the stock at T",
Q-STK-01), the near-expiry list (Q-STK-02), throughput (Q-STK-03), FEFO / FIFO checks
(Q-STK-04…06), damage reports (Q-STK-07) and cycle counts (Q-STK-09). The platform never adjusts
stock (Q-IMP-06)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType
from app.core.quality.q3 import (
    QDamageCause,
    QDamageStage,
    QFefoException,
    QFefoResult,
    QHoldLineStatus,
    QHoldReason,
    QZoneRole,
)
from app.models import Project
from app.models.quality import QCustomer
from app.models.quality.q3 import (
    QCycleCount,
    QCycleCountLine,
    QDamageReport,
    QFefoCheck,
    QHold,
    QHoldLine,
    QProduct,
    QStockLine,
    QStockSnapshot,
    QStorageZone,
    QThroughput,
)
from app.schemas.hse_common import ApiWarning
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.q3 import base as b
from app.services.quality.q3 import holds as hold_svc

C = Capability
RT = QRecordType


# ---- snapshots (Q-STK-01) -----------------------------------------------------------------------


def latest_before(db: Session, site_id: uuid.UUID, t: datetime) -> QStockSnapshot | None:
    return db.scalar(
        select(QStockSnapshot)
        .where(QStockSnapshot.site_id == site_id, QStockSnapshot.voided.is_(False), QStockSnapshot.as_of <= t)
        .order_by(QStockSnapshot.as_of.desc())
        .limit(1)
    )


def first_at_or_after(db: Session, site_id: uuid.UUID, t: datetime) -> QStockSnapshot | None:
    return db.scalar(
        select(QStockSnapshot)
        .where(QStockSnapshot.site_id == site_id, QStockSnapshot.voided.is_(False), QStockSnapshot.as_of >= t)
        .order_by(QStockSnapshot.as_of)
        .limit(1)
    )


def lines(db: Session, snap: QStockSnapshot | None) -> list[QStockLine]:
    if snap is None:
        return []
    return list(db.scalars(select(QStockLine).where(QStockLine.snapshot_id == snap.id)))


def old_warning(snap: QStockSnapshot | None, at: datetime) -> list[ApiWarning]:
    if snap is None or at - snap.as_of <= timedelta(hours=24):
        return []
    return [
        qc.warning(
            "SNAPSHOT_OLD",
            f"The stock snapshot used is from {b.local(snap.as_of):%Y-%m-%d %H:%M} (older than 24 h).",
            "لقطة المخزون المستخدمة أقدم من 24 ساعة.",
        )
    ]


def snapshot_read(db: Session, s: QStockSnapshot) -> dict[str, Any]:
    return {"id": s.id, "site": b.site_ref(db, s.site_id), "as_of": s.as_of, "line_count": s.line_count, "batch_id": s.batch_id}


def list_snapshots(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    rows = db.scalars(
        select(QStockSnapshot)
        .where(QStockSnapshot.project_id == project.id, QStockSnapshot.voided.is_(False))
        .order_by(QStockSnapshot.as_of.desc())
        .limit(60)
    )
    return [snapshot_read(db, s) for s in rows]


# ---- near-expiry list (Q-STK-02) -----------------------------------------------------------------


def held_keys(db: Session, project_id: uuid.UUID) -> set[tuple[str, str]]:
    rows = db.execute(
        select(QHoldLine.sku, QHoldLine.batch)
        .join(QHold, QHold.id == QHoldLine.hold_id)
        .where(QHold.project_id == project_id, QHoldLine.line_status == QHoldLineStatus.on_hold)
    )
    return {(r[0], r[1]) for r in rows}


def near_expiry(db: Session, p: Principal, project_id: uuid.UUID, site_id: uuid.UUID | None = None) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    return _near_expiry(db, project, site_id)


def _near_expiry(db: Session, project: Project, site_id: uuid.UUID | None = None) -> dict[str, Any]:
    from app.models import Site  # noqa: PLC0415

    today = qc.project_day(project)
    days = int(b.setting(db, project.id, "near_expiry_days"))
    pct = Decimal(str(b.setting(db, project.id, "near_expiry_pct")))
    held = held_keys(db, project.id)
    out: list[dict[str, Any]] = []
    snaps = []
    for site in db.scalars(select(Site).where(Site.project_id == project.id)):
        if site_id is not None and site.id != site_id:
            continue
        snap = latest_before(db, site.id, now())
        if snap is None:
            continue
        snaps.append(snapshot_read(db, snap))
        prods = {x.id: x for x in db.scalars(select(QProduct).where(QProduct.project_id == project.id))}
        for ln in lines(db, snap):
            if ln.expiry_date is None:
                continue
            prod = prods.get(ln.product_id) if ln.product_id else None
            left = (ln.expiry_date - today).days
            kind = None
            if ln.expiry_date < today:
                kind = "expired"
            elif left <= days:
                kind = "near_expiry"
            elif prod is not None and prod.shelf_life_days:
                if Decimal(left) * 100 / prod.shelf_life_days <= pct:
                    kind = "near_expiry"
            if kind is None:
                continue
            out.append(
                {
                    "kind": kind,
                    "stock_line_id": ln.id,
                    "owner": b.customer_ref(db, ln.owner_customer_id),
                    "sku": ln.sku,
                    "product_id": ln.product_id,
                    "batch": ln.batch,
                    "expiry_date": ln.expiry_date,
                    "days_left": left,
                    "location": ln.location,
                    "zone_code": ln.zone_code,
                    "qty": ln.qty,
                    "unit": ln.unit,
                    "on_hold": (ln.sku, ln.batch) in held,
                    "site_id": site.id,
                }
            )
    out.sort(key=lambda r: ((r["owner"] or {}).get("code") or "", r["expiry_date"]))
    return {"snapshots": snaps, "items": out, "near_expiry_days": days, "near_expiry_pct": pct}


def place_expiry_hold(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """"Place hold" from the near-expiry list (reason expiry)."""
    project, g = b.project_for_create(db, p, project_id, RT.hold, C.hold_manage)
    rows = [db.get(QStockLine, i) for i in body.get("stock_line_ids") or []]
    if not rows or any(r is None for r in rows):
        raise qc.field_err("stock_line_ids", "Pick the stock lines to hold.", "اختر بنود المخزون.")
    snap = db.get(QStockSnapshot, rows[0].snapshot_id)  # type: ignore[union-attr]
    assert snap is not None  # noqa: S101
    b.require_site(g, snap.site_id)
    h = hold_svc.place(
        db,
        project,
        site_id=snap.site_id,
        reason=QHoldReason.expiry,
        lines=[_line_from_stock(x) for x in rows if x is not None],
        placed_by=p.user.id,
        p=p,
    )
    return hold_svc.read(db, p, h)


def _line_from_stock(ln: QStockLine) -> dict[str, Any]:
    return {
        "owner_customer_id": ln.owner_customer_id,
        "product_id": ln.product_id,
        "sku": ln.sku,
        "batch": ln.batch,
        "expiry_date": ln.expiry_date,
        "qty": ln.qty,
        "unit": ln.unit,
        "location": ln.location,
        "stock_line_id": ln.id,
    }


def stock_hold_lines(db: Session, snap: QStockSnapshot | None, zone_code: str | None) -> list[dict[str, Any]]:
    return [_line_from_stock(ln) for ln in lines(db, snap) if zone_code is None or ln.zone_code == zone_code]


def expired_alerts(db: Session, at: datetime) -> int:
    """Q-STK-02: an expired line not on a hold alerts 269 holders daily."""
    n = 0
    from app.core.quality.common import QSectorProfile  # noqa: PLC0415

    for project in db.scalars(select(Project)):
        if qc.profile_of(db, project.id) != QSectorProfile.logistics:
            continue
        res = _near_expiry(db, project)
        bad = [x for x in res["items"] if x["kind"] == "expired" and not x["on_hold"]]
        if not bad:
            continue
        day = b.local_day(at).isoformat()
        n += b.send(
            db,
            project,
            b.holders(db, project, C.stock_record),
            f"stock:{project.id}:expired:{day}",
            f"{len(bad)} expired stock lines are not on hold",
            f"{len(bad)} بنود منتهية الصلاحية غير محجوزة",
            body_en="Open the near-expiry list and place holds.",
            body_ar="افتح قائمة قرب الانتهاء وضع الحجوزات.",
            path="/quality/stock",
            email=False,
        )
    return n


# ---- FEFO / FIFO (Q-STK-04, -05) -------------------------------------------------------------------


def eligible_earliest(
    db: Session, project: Project, snap: QStockSnapshot | None, prod: QProduct, today: date
) -> tuple[date | None, str | None]:
    """Earliest expiry (dated) or receipt date (not dated) among the snapshot lines of the same
    owner and product, not on a Q3 hold, not expired, outside quarantine / returns zones."""
    held = held_keys(db, project.id)
    ok_zones = {
        z.zone_id
        for z in db.scalars(select(QStorageZone).where(QStorageZone.project_id == project.id))
        if z.role != QZoneRole.quarantine
    }
    best: tuple[date, str] | None = None
    for ln in lines(db, snap):
        if ln.product_id != prod.id and ln.sku != prod.sku:
            continue
        if ln.owner_customer_id not in (None, prod.owner_customer_id):
            continue
        if (ln.sku, ln.batch) in held:
            continue
        if ln.zone_id is None or ln.zone_id not in ok_zones:
            continue
        key = ln.expiry_date if prod.dated else ln.receipt_date
        if key is None or (prod.dated and key < today):
            continue
        if best is None or key < best[0]:
            best = (key, ln.batch)
    return (best[0], best[1]) if best else (None, None)


def create_fefo(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT.fefo_check, C.stock_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    prod = db.get(QProduct, body["product_id"])
    if prod is None or prod.project_id != project.id:
        raise qc.field_err("product_id", "The product is not on this project.", "المنتج ليس في المشروع.")
    at: datetime = body.get("checked_at") or now()
    snap = latest_before(db, site.id, at)
    today = qc.project_day(project, at)
    earliest, eb = eligible_earliest(db, project, snap, prod, today)
    picked = body.get("picked_expiry") if prod.dated else body.get("picked_receipt_date")
    if picked is None:
        raise qc.field_err(
            "picked_expiry" if prod.dated else "picked_receipt_date",
            "Enter the picked batch's expiry (or receipt date for undated products).",
            "أدخل تاريخ انتهاء الدفعة المنتقاة.",
        )
    compliant = earliest is None or picked <= earliest
    result = QFefoResult.compliant if compliant else QFefoResult.non_compliant
    exc = body.get("exception_reason")
    note = (body.get("exception_note") or "").strip() or None
    if not compliant and exc:
        result = QFefoResult.exception
        if QFefoException(exc) == QFefoException.other:
            note = qc.reason(note, 20, "exception_note")
    x = QFefoCheck(
        project_id=project.id,
        check_no=b.number(db, project, RT.fefo_check, at),
        site_id=site.id,
        checked_at=at,
        order_ref=body.get("order_ref"),
        product_id=prod.id,
        picked_batch=body["picked_batch"],
        picked_expiry=body.get("picked_expiry"),
        picked_receipt_date=body.get("picked_receipt_date"),
        location=body.get("location"),
        snapshot_id=snap.id if snap else None,
        eligible_earliest=earliest,
        eligible_batch=eb,
        result=result,
        exception_reason=QFefoException(exc) if result == QFefoResult.exception and exc else None,
        exception_note=note if result == QFefoResult.exception else None,
        created_by_user_id=p.user.id,
    )
    db.add(x)
    db.flush()
    return {**fefo_read(db, p, x), "warnings": b.warn_dump(old_warning(snap, at))}


def confirm_fefo(db: Session, p: Principal, check_id: uuid.UUID) -> dict[str, Any]:
    """Q-STK-05: an exception `other` needs the 266 holder's confirmation."""
    x = db.get(QFefoCheck, check_id)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, RT.fefo_check, check_id, None)
    project, g = b.project_for_progress(db, p, x.project_id, C.storage_manage)
    b.require_site(g, x.site_id)
    if x.exception_reason != QFefoException.other or x.confirmed_at is not None:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "Only an unconfirmed 'other' exception.", "فقط استثناء 'أخرى' غير مؤكد.")
    if x.created_by_user_id == p.user.id:
        raise qc.err(422, ErrorCode.SOD_CONFLICT, "Another person confirms your exception.", "يؤكد الاستثناء شخص آخر.")
    x.confirmed_by_user_id = p.user.id
    x.confirmed_at = now()
    _ = project
    return fefo_read(db, p, x)


def fefo_counts(x: QFefoCheck) -> bool:
    """K-166: compliant, or an exception with a listed reason (or a confirmed `other`)."""
    if x.result == QFefoResult.compliant:
        return True
    if x.result != QFefoResult.exception:
        return False
    return x.exception_reason != QFefoException.other or x.confirmed_at is not None


def fefo_read(db: Session, p: Principal, x: QFefoCheck) -> dict[str, Any]:
    prod = db.get(QProduct, x.product_id)
    return {
        "id": x.id,
        "check_no": x.check_no,
        "site_id": x.site_id,
        "checked_at": x.checked_at,
        "order_ref": x.order_ref,
        "product": {"id": prod.id, "sku": prod.sku, "description_en": prod.description_en, "description_ar": prod.description_ar, "dated": prod.dated} if prod else None,
        "picked_batch": x.picked_batch,
        "picked_expiry": x.picked_expiry,
        "picked_receipt_date": x.picked_receipt_date,
        "location": x.location,
        "eligible_earliest": x.eligible_earliest,
        "eligible_batch": x.eligible_batch,
        "result": x.result,
        "exception_reason": x.exception_reason,
        "exception_note": x.exception_note,
        "confirmed": x.confirmed_at is not None,
        "counts_compliant": fefo_counts(x),
        "recorded_by": b.user_ref(db, x.created_by_user_id, b.hide_names(p, x.project_id)),
    }


def list_fefo(db: Session, p: Principal, project_id: uuid.UUID, page_no: int, size: int, result: QFefoResult | None = None) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    q = select(QFefoCheck).where(QFefoCheck.project_id == project.id)
    if result:
        q = q.where(QFefoCheck.result == result)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(QFefoCheck.checked_at.desc()).offset((page_no - 1) * size).limit(size))
    return {"items": [fefo_read(db, p, x) for x in rows], "total": total, "page": page_no, "page_size": size}


# ---- damage reports (Q-STK-07) -------------------------------------------------------------------


def create_damage(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT.damage_report, C.stock_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    prod = db.get(QProduct, body["product_id"])
    if prod is None or prod.project_id != project.id:
        raise qc.field_err("product_id", "The product is not on this project.", "المنتج ليس في المشروع.")
    qty = Decimal(str(body["qty"]))
    if qty <= 0:
        raise qc.field_err("qty", "Quantity must be positive.", "يجب أن تكون الكمية موجبة.")
    at: datetime = body.get("reported_at") or now()
    d = QDamageReport(
        id=uuid.uuid4(),
        project_id=project.id,
        dmg_no=b.number(db, project, RT.damage_report, at),
        site_id=site.id,
        zone_id=body.get("zone_id"),
        stage=QDamageStage(body["stage"]),
        product_id=prod.id,
        batch=body["batch"],
        qty=qty,
        unit=body.get("unit") or "unit",
        location=body.get("location"),
        cause=QDamageCause(body["cause"]),
        note=body.get("note"),
        destroyed_on_spot=bool(body.get("destroyed_on_spot")),
        owner_notified_at=body.get("owner_notified_at"),
        reported_at=at,
        created_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    finish_damage(db, p, project, d, photo_count=int(body.get("photo_count") or 0))
    return damage_read(db, p, d)


def finish_damage(db: Session, p: Principal | None, project: Project, d: QDamageReport, photo_count: int = 0) -> None:
    """A damage report creates a hold unless the units are destroyed on the spot with photo
    evidence and owner notification (Q-STK-07). The photo is uploaded to the report afterwards
    (`q_damage`); destroyed-on-spot requires the owner notification time now."""
    if d.destroyed_on_spot:
        if d.owner_notified_at is None:
            raise qc.field_err(
                "owner_notified_at",
                "Destroyed on the spot needs the time the owner was notified.",
                "الإتلاف في الموقع يتطلب وقت إبلاغ المالك.",
            )
        return
    prod = db.get(QProduct, d.product_id)
    h = hold_svc.place(
        db,
        project,
        site_id=d.site_id,
        reason=QHoldReason.damage,
        lines=[{"product_id": d.product_id, "batch": d.batch, "qty": d.qty, "unit": d.unit, "location": d.location, "owner_customer_id": prod.owner_customer_id if prod else None}],
        placed_by=d.created_by_user_id,
        zone_id=d.zone_id,
        source=(RT.damage_report, d.id, d.dmg_no),
        p=p,
        at=d.reported_at,
    )
    d.hold_id = h.id
    _ = photo_count


def damage_destroyed(db: Session, d: QDamageReport) -> bool:
    """Destroyed units of a damage report: destroyed on the spot, or its hold line rejected and
    destroyed."""
    if d.destroyed_on_spot:
        return True
    if d.hold_id is None:
        return False
    return (
        db.scalar(
            select(QHoldLine.id).where(
                QHoldLine.hold_id == d.hold_id,
                QHoldLine.line_status == QHoldLineStatus.rejected,
                QHoldLine.final_outcome == "destroyed",
            )
        )
        is not None
    )


def damage_read(db: Session, p: Principal, d: QDamageReport) -> dict[str, Any]:
    prod = db.get(QProduct, d.product_id)
    return {
        "id": d.id,
        "dmg_no": d.dmg_no,
        "site_id": d.site_id,
        "zone": b.zone_ref(db, d.zone_id),
        "stage": d.stage,
        "product": {"id": prod.id, "sku": prod.sku, "description_en": prod.description_en, "description_ar": prod.description_ar} if prod else None,
        "batch": d.batch,
        "qty": d.qty,
        "unit": d.unit,
        "location": d.location,
        "cause": d.cause,
        "note": d.note,
        "destroyed_on_spot": d.destroyed_on_spot,
        "owner_notified_at": d.owner_notified_at,
        "reported_at": d.reported_at,
        "hold_id": d.hold_id,
        "reported_by": b.user_ref(db, d.created_by_user_id, b.hide_names(p, d.project_id)),
    }


def list_damage(db: Session, p: Principal, project_id: uuid.UUID, page_no: int, size: int) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    q = select(QDamageReport).where(QDamageReport.project_id == project.id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(QDamageReport.reported_at.desc()).offset((page_no - 1) * size).limit(size))
    return {"items": [damage_read(db, p, d) for d in rows], "total": total, "page": page_no, "page_size": size}


# ---- cycle counts (Q-STK-09) ---------------------------------------------------------------------


def cc_line(raw: dict[str, Any], tol_default: Decimal, cc_id: uuid.UUID) -> QCycleCountLine:
    sys_q = Decimal(str(raw["system_qty"]))
    cnt = Decimal(str(raw["counted_qty"]))
    rc = raw.get("recount_qty")
    rc_d = Decimal(str(rc)) if rc not in (None, "") else None
    tol = Decimal(str(raw["tolerance"])) if raw.get("tolerance") not in (None, "") else tol_default
    used = rc_d if rc_d is not None else cnt
    return QCycleCountLine(
        cc_id=cc_id,
        product_id=raw.get("product_id"),
        sku=raw["sku"],
        batch=raw.get("batch"),
        location=raw["location"],
        system_qty=sys_q,
        counted_qty=cnt,
        recount_qty=rc_d,
        unit=raw.get("unit") or "unit",
        tolerance=tol,
        within_tolerance=abs(used - sys_q) <= tol,
        variance_reason=raw.get("variance_reason"),
    )


def create_count(
    db: Session,
    project: Project,
    site_id: uuid.UUID,
    counted_at: datetime,
    rows: list[dict[str, Any]],
    user_id: uuid.UUID | None,
    zone_codes: list[str] | None = None,
    batch_id: uuid.UUID | None = None,
) -> QCycleCount:
    tol = Decimal(str(b.setting(db, project.id, "cycle_count_tolerance_units")))
    cc = QCycleCount(
        id=uuid.uuid4(),
        project_id=project.id,
        cc_no=b.number(db, project, RT.cycle_count, counted_at),
        site_id=site_id,
        counted_at=counted_at,
        zone_codes=zone_codes or sorted({r.get("zone_code") for r in rows if r.get("zone_code")}),
        batch_id=batch_id,
        created_by_user_id=user_id,
    )
    db.add(cc)
    db.flush()
    for r in rows:
        db.add(cc_line(r, tol, cc.id))
    db.flush()
    return cc


def create_count_api(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT.cycle_count, C.stock_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    if not body.get("lines"):
        raise qc.field_err("lines", "Add the counted lines.", "أضف البنود المعدودة.")
    cc = create_count(db, project, site.id, body.get("counted_at") or now(), body["lines"], p.user.id, body.get("zone_codes"))
    return count_read(db, cc)


def count_read(db: Session, cc: QCycleCount, with_lines: bool = True) -> dict[str, Any]:
    ls = list(db.scalars(select(QCycleCountLine).where(QCycleCountLine.cc_id == cc.id)))
    within = sum(1 for x in ls if x.within_tolerance)
    return {
        "id": cc.id,
        "cc_no": cc.cc_no,
        "site_id": cc.site_id,
        "counted_at": cc.counted_at,
        "zone_codes": cc.zone_codes,
        "lines_counted": len(ls),
        "lines_within": within,
        "ira_pct": b.q1(Decimal(within) * 100 / len(ls)) if ls else None,
        "lines": [
            {
                "id": x.id,
                "sku": x.sku,
                "batch": x.batch,
                "location": x.location,
                "system_qty": x.system_qty,
                "counted_qty": x.counted_qty,
                "recount_qty": x.recount_qty,
                "tolerance": x.tolerance,
                "within_tolerance": x.within_tolerance,
                "variance_reason": x.variance_reason,
            }
            for x in ls
        ]
        if with_lines
        else [],
    }


def list_counts(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    rows = db.scalars(
        select(QCycleCount).where(QCycleCount.project_id == project.id, QCycleCount.voided.is_(False)).order_by(QCycleCount.counted_at.desc()).limit(100)
    )
    return [count_read(db, c, with_lines=False) for c in rows]


# ---- throughput (Q-STK-03) -----------------------------------------------------------------------


def upsert_throughput(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    project, g = b.project_for_create(db, p, project_id, RT.cycle_count, C.stock_record)
    site = b.site_of(db, project, body["site_id"])
    b.require_site(g, site.id)
    m: date = body["month"]
    m = m.replace(day=1)
    row = db.scalar(select(QThroughput).where(QThroughput.site_id == site.id, QThroughput.month == m))
    if row is None:
        row = QThroughput(project_id=project.id, site_id=site.id, month=m)
        db.add(row)
    for k in ("units_received", "units_dispatched", "deliveries", "shipments"):
        v = body.get(k)
        if v is not None:
            if int(v) < 0:
                raise qc.field_err(k, "Must be zero or more.", "يجب ألا تكون سالبة.")
            setattr(row, k, int(v))
    row.entered_by_user_id = p.user.id
    row.updated_at = now()
    db.flush()
    return throughput_read(row)


def throughput_read(t: QThroughput) -> dict[str, Any]:
    return {
        "id": t.id,
        "site_id": t.site_id,
        "month": t.month,
        "units_received": t.units_received,
        "units_dispatched": t.units_dispatched,
        "deliveries": t.deliveries,
        "shipments": t.shipments,
    }


def list_throughput(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    return [throughput_read(t) for t in db.scalars(select(QThroughput).where(QThroughput.project_id == project.id).order_by(QThroughput.month.desc()))]


_ = (QCustomer, AttachmentOwner)
