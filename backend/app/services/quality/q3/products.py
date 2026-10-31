"""Product master (spec 8-quality §D.1.3): sku unique per project and owner, GTIN with a valid
check digit, storage class, shelf life, dated (FEFO) or not (FIFO). Entered here or imported
(Q-IMP products)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.quality.common import QRecordType
from app.core.quality.q3 import QStorageClass
from app.models.quality.q3 import QProduct
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.q3 import base as b
from app.services.quality.q3.imports import gtin_ok

C = Capability
FIELDS = (
    "description_en",
    "description_ar",
    "gtin",
    "temp_min",
    "temp_max",
    "shelf_life_days",
    "min_remaining_shelf_life_pct",
    "dated",
    "active",
)


def read(db: Session, x: QProduct) -> dict[str, Any]:
    return {
        "id": x.id,
        "sku": x.sku,
        "owner": b.customer_ref(db, x.owner_customer_id),
        "description_en": x.description_en,
        "description_ar": x.description_ar,
        "gtin": x.gtin,
        "storage_class": x.storage_class,
        "temp_min": x.temp_min,
        "temp_max": x.temp_max,
        "shelf_life_days": x.shelf_life_days,
        "min_remaining_shelf_life_pct": x.min_remaining_shelf_life_pct,
        "dated": x.dated,
        "active": x.active,
    }


def _check(x: QProduct) -> None:
    if x.gtin and not gtin_ok(x.gtin):
        raise qc.field_err(
            "gtin",
            "GTIN must have 8, 12, 13 or 14 digits and a valid check digit.",
            "رقم GTIN غير صالح.",
        )
    if x.shelf_life_days is not None and x.shelf_life_days <= 0:
        raise qc.field_err(
            "shelf_life_days", "Shelf life must be positive.", "يجب أن يكون العمر موجباً."
        )
    if x.min_remaining_shelf_life_pct is not None and not (
        Decimal(10) <= x.min_remaining_shelf_life_pct <= Decimal(100)
    ):
        raise qc.field_err("min_remaining_shelf_life_pct", "10–100 %.", "بين 10 و100 %.")


def list_products(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    b.list_grant(p, project.id)
    stmt = select(QProduct).where(QProduct.project_id == project.id)
    if owner_id:
        stmt = stmt.where(QProduct.owner_customer_id == owner_id)
    if q:
        stmt = stmt.where(
            QProduct.sku.ilike(f"%{q}%")
            | QProduct.description_en.ilike(f"%{q}%")
            | QProduct.description_ar.ilike(f"%{q}%")
        )
    return [read(db, x) for x in db.scalars(stmt.order_by(QProduct.sku))]


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _ = b.project_for_create(db, p, project_id, QRecordType.receipt, C.stock_record)
    owner = b.customer_of(db, project, body["owner_customer_id"], "owner_customer_id")
    sku = body["sku"].strip()
    if db.scalar(
        select(QProduct.id).where(
            QProduct.project_id == project.id,
            QProduct.owner_customer_id == owner.id,
            QProduct.sku == sku,
        )
    ):
        raise qc.field_err(
            "sku", "This SKU already exists for the owner.", "رمز المنتج موجود لهذا المالك."
        )
    x = QProduct(
        project_id=project.id,
        owner_customer_id=owner.id,
        sku=sku,
        storage_class=QStorageClass(body["storage_class"]),
        created_by_user_id=p.user.id,
    )
    for k in FIELDS:
        if k in body and body[k] is not None:
            setattr(x, k, body[k])
    x.description_ar = x.description_ar or ""
    _check(x)
    db.add(x)
    db.flush()
    return read(db, x)


def update(
    db: Session, p: Principal, product_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    x = db.get(QProduct, product_id)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, QRecordType.receipt, product_id, None)
    b.project_for_progress(db, p, x.project_id, C.stock_record)
    for k in FIELDS:
        if k in body and body[k] is not None:
            setattr(x, k, body[k])
    if body.get("storage_class"):
        x.storage_class = QStorageClass(body["storage_class"])
    _check(x)
    x.updated_by_user_id = p.user.id
    return read(db, x)
