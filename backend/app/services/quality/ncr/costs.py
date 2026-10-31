"""NCR costs and the COPQ input (spec 8-quality §A.9.6, Q-COST-01…03): amount = quantity × rate
(2 dp, half-up); labour, plant and delay default to the project rates (a delay line needs
`delay_rate_sar_day`, `DELAY_RATE_NOT_SET`); the rate in use is stored on the line; failure class
internal / external from the detection stage."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction
from app.core.errors import ErrorCode, not_found
from app.core.quality.common import INTERNAL_STAGES, QCostType, QNcrStatus
from app.models.quality import QNcr, QNcrCost
from app.services.common import invalid_transition
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import settings as qs
from app.services.quality.ncr import core

CT = QCostType
CENT = Decimal("0.01")
RATE_KEY = {
    CT.rework_labour: "labour_rate_sar_h",
    CT.repair_labour: "labour_rate_sar_h",
    CT.plant: "plant_rate_sar_h",
    CT.delay: "delay_rate_sar_day",
}
UNIT = {CT.rework_labour: "h", CT.repair_labour: "h", CT.plant: "h", CT.delay: "day"}
EDITABLE = (
    QNcrStatus.open,
    QNcrStatus.disposition_proposed,
    QNcrStatus.disposition_approved,
    QNcrStatus.pending_verification,
)


def money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def failure_class(n: QNcr) -> str | None:
    if n.detection_stage is None:
        return None
    return "internal" if n.detection_stage in INTERNAL_STAGES else "external"


def lines(db: Session, n: QNcr) -> list[QNcrCost]:
    return list(
        db.scalars(select(QNcrCost).where(QNcrCost.ncr_id == n.id).order_by(QNcrCost.entered_at))
    )


def line_read(c: QNcrCost) -> dict[str, Any]:
    return {
        "id": c.id,
        "cost_type": c.cost_type,
        "description": c.description,
        "quantity": str(c.quantity),
        "unit": c.unit,
        "rate_sar": str(c.rate_sar),
        "amount_sar": str(c.amount_sar),
        "recoverable": c.recoverable,
        "recovered_sar": str(c.recovered_sar),
        "entered_at": c.entered_at,
    }


def recompute(db: Session, n: QNcr) -> None:
    gross, rec = db.execute(
        select(
            func.coalesce(func.sum(QNcrCost.amount_sar), 0),
            func.coalesce(func.sum(QNcrCost.recovered_sar), 0),
        ).where(QNcrCost.ncr_id == n.id)
    ).one()
    n.cost_gross_sar = money(Decimal(gross))
    n.cost_recovered_sar = money(Decimal(rec))


def build(db: Session, n: QNcr, body: dict[str, Any], user_id: uuid.UUID | None) -> QNcrCost:
    ct = CT(body["cost_type"])
    qty = Decimal(str(body.get("quantity") if body.get("quantity") is not None else 1))
    if qty <= 0:
        raise qc.field_err("quantity", "Quantity must be positive.")
    rate_raw = body.get("rate_sar")
    if ct == CT.delay:
        setting = qs.dec(db, n.project_id, "delay_rate_sar_day")
        if setting is None:
            raise qc.err(
                422,
                ErrorCode.DELAY_RATE_NOT_SET,
                "Set the project's delay cost per day (Quality settings) before adding a delay "
                "line.",
                "حدد تكلفة يوم التأخير في إعدادات الجودة قبل إضافة بند تأخير.",
            )
        rate = Decimal(str(rate_raw)) if rate_raw is not None else setting
    elif ct in RATE_KEY and rate_raw is None:
        rate = qs.dec(db, n.project_id, RATE_KEY[ct]) or Decimal(0)
    elif rate_raw is None:
        raise qc.field_err("rate_sar", "Give the rate (a lump sum has quantity 1).")
    else:
        rate = Decimal(str(rate_raw))
    if rate < 0:
        raise qc.field_err("rate_sar", "Amounts are ≥ 0.")
    amount = money(qty * rate)
    recovered = money(Decimal(str(body.get("recovered_sar") or 0)))
    recoverable = bool(body.get("recoverable", False)) or recovered > 0
    if recovered < 0 or recovered > amount:
        raise qc.field_err("recovered_sar", "Recovered must be between 0 and the line amount.")
    return QNcrCost(
        ncr_id=n.id,
        cost_type=ct,
        description=body.get("description"),
        quantity=qty,
        unit=body.get("unit") or UNIT.get(ct),
        rate_sar=money(rate),
        amount_sar=amount,
        recoverable=recoverable,
        recovered_sar=recovered,
        entered_by_user_id=user_id,
        entered_at=now(),
        created_by_user_id=user_id,
    )


def add(db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]) -> QNcr:
    n = core.get_ncr(db, p, ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status not in EDITABLE:
        raise invalid_transition("NCR", n.status, "costs")
    core._manager_grant(p, n)
    c = build(db, n, body, p.user.id)
    db.add(c)
    db.flush()
    recompute(db, n)
    n.no_cost_reason = None
    db.flush()
    core._audit(
        db,
        p,
        n,
        AuditAction.update,
        after={"cost_added": c.cost_type.value, "amount": str(c.amount_sar)},
    )
    return n


def update(db: Session, p: Principal, cost_id: uuid.UUID, body: dict[str, Any]) -> QNcr:
    c = db.get(QNcrCost, cost_id)
    if c is None:
        raise not_found("Cost line")
    n = core.get_ncr(db, p, c.ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status not in EDITABLE:
        raise invalid_transition("NCR", n.status, "costs")
    core._manager_grant(p, n)
    if body.get("recovered_sar") is not None:
        rec = money(Decimal(str(body["recovered_sar"])))
        if rec < 0 or rec > c.amount_sar:
            raise qc.field_err("recovered_sar", "Recovered must be between 0 and the amount.")
        c.recovered_sar = rec
        c.recoverable = c.recoverable or rec > 0
    if body.get("description") is not None:
        c.description = body["description"]
    db.flush()
    recompute(db, n)
    db.flush()
    core._audit(
        db, p, n, AuditAction.update, after={"cost": str(c.id), "recovered": str(c.recovered_sar)}
    )
    return n


def delete(db: Session, p: Principal, cost_id: uuid.UUID) -> QNcr:
    c = db.get(QNcrCost, cost_id)
    if c is None:
        raise not_found("Cost line")
    n = core.get_ncr(db, p, c.ncr_id)
    qc.writable(core.project_of(db, n), p)
    if n.status not in EDITABLE:
        raise invalid_transition("NCR", n.status, "costs")
    core._manager_grant(p, n)
    db.delete(c)
    db.flush()
    recompute(db, n)
    db.flush()
    core._audit(db, p, n, AuditAction.update, after={"cost_deleted": str(cost_id)})
    return n
