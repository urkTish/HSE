"""Hold points block the next step (spec 8-quality Q-IR-08, Q-IR-09, Q-IR-11, Q-ITP-05).

For an IR whose points include seq s on ITP I at location key L, every point of I with type H
and seq < s must have an IR of the same ITP (any revision) at L in Approved or Approved with
Comments (not voided) that covers that seq, and the point's seq and type must be unchanged in the
revision that released it (Q-ITP-05). Holds that are points of the same IR are inspected with it.
When the releasing IR's decided round ticked "close comments before the next hold point", its open
comments must also be closed (Q-IR-11). Q1 registers the same logic as `HOLD_CHECKS["itp_point"]`
for other parts (Q2 pours, Q-TST-12)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.quality.q1 import IR_APPROVED, QIrCommentStatus, QPointType
from app.models.quality.q1 import QIr, QIrComment, QIrRound, QItp, QItpPoint
from app.services.quality.registry import Blocker


@dataclass
class HoldResult:
    blockers: list[Blocker] = field(default_factory=list)
    holds: list[int] = field(default_factory=list)  # hold seqs that gate this IR

    @property
    def ok(self) -> bool:
        return not self.blockers


def _types(db: Session, itp_id: uuid.UUID) -> dict[int, QPointType]:
    return {
        pt.seq: pt.point_type
        for pt in db.scalars(select(QItpPoint).where(QItpPoint.itp_id == itp_id))
    }


def _releasing(
    db: Session, family_id: uuid.UUID, key: str | None, seq: int, kind: QPointType
) -> list[QIr]:
    """Approved IRs of the family at key L that cover `seq` with an unchanged point type."""
    stmt = select(QIr).where(QIr.itp_family_id == family_id, QIr.status.in_(list(IR_APPROVED)))
    if key is not None:
        stmt = stmt.where(QIr.location_key == key)
    out = []
    type_cache: dict[uuid.UUID, dict[int, QPointType]] = {}
    for ir in db.scalars(stmt):
        if seq not in (ir.point_seqs or []):
            continue
        types = type_cache.setdefault(ir.itp_id, _types(db, ir.itp_id))
        if types.get(seq) == kind:
            out.append(ir)
    return out


def flagged_open_comments(db: Session, ir: QIr) -> list[QIrComment]:
    """Open comments of an IR whose deciding round asked to close them before the next hold."""
    rnd = db.scalar(
        select(QIrRound)
        .where(QIrRound.ir_id == ir.id, QIrRound.close_comments_before_next_hold.is_(True))
        .order_by(QIrRound.round_no.desc())
        .limit(1)
    )
    if rnd is None:
        return []
    return list(
        db.scalars(
            select(QIrComment).where(
                QIrComment.ir_id == ir.id, QIrComment.status != QIrCommentStatus.closed
            )
        )
    )


def check(
    db: Session,
    itp: QItp,
    seqs: list[int],
    key: str,
    governing: QPointType,
    *,
    exclude_ir: uuid.UUID | None = None,
) -> HoldResult:
    types = _types(db, itp.id)
    top = max(seqs) if seqs else 0
    res = HoldResult()
    for h in sorted(s for s, t in types.items() if t == QPointType.H and s < top and s not in seqs):
        res.holds.append(h)
        rel = [r for r in _releasing(db, itp.family_id, key, h, QPointType.H) if r.id != exclude_ir]
        if not rel:
            res.blockers.append(
                Blocker(
                    "HOLD_POINT_NOT_RELEASED",
                    f"Hold point {h} is not yet approved at this location.",
                    f"نقطة التوقف {h} لم تعتمد بعد في هذا الموقع.",
                )
            )
            continue
        # Q-IR-11: the releasing IR's flagged comments block the next hold-gated IR
        if all(flagged_open_comments(db, r) for r in rel):
            for c in flagged_open_comments(db, rel[0]):
                res.blockers.append(
                    Blocker(
                        "IR_COMMENT_OPEN",
                        f"Comment on {rel[0].ir_no} must be closed before the next hold point: "
                        f"{(c.text_en or c.text_ar or '')[:120]}",
                        f"يجب إغلاق ملاحظة {rel[0].ir_no} قبل نقطة التوقف التالية.",
                    )
                )
    # Q-IR-11 also covers an H IR right after an approved-with-comments point at L
    if governing == QPointType.H:
        for prior in db.scalars(
            select(QIr).where(
                QIr.itp_family_id == itp.family_id,
                QIr.location_key == key,
                QIr.status.in_(list(IR_APPROVED)),
            )
        ):
            if prior.id == exclude_ir or not prior.point_seqs or max(prior.point_seqs) >= top:
                continue
            if any(prior.point_seqs and h in prior.point_seqs for h in res.holds):
                continue  # already checked as a releasing IR above
            for c in flagged_open_comments(db, prior):
                res.blockers.append(
                    Blocker(
                        "IR_COMMENT_OPEN",
                        f"Comment on {prior.ir_no} must be closed before this hold point: "
                        f"{(c.text_en or c.text_ar or '')[:120]}",
                        f"يجب إغلاق ملاحظة {prior.ir_no} قبل نقطة التوقف هذه.",
                    )
                )
    return res


def hold_point_of(db: Session, ir_id: uuid.UUID) -> tuple[uuid.UUID, str] | None:
    """`HOLD_POINT_OF_IR["ir"]` (D-370): the point a pre-pour IR releases — its highest H point,
    else its highest point — with the IR's location key, so a Q2 pour linked to the IR is checked
    at that point and location (Q-TST-12)."""
    ir = db.get(QIr, ir_id)
    if ir is None or not ir.point_seqs:
        return None
    types = _types(db, ir.itp_id)
    holds = [s for s in ir.point_seqs if types.get(s) == QPointType.H]
    seq = max(holds or ir.point_seqs)
    pt = db.scalar(select(QItpPoint).where(QItpPoint.itp_id == ir.itp_id, QItpPoint.seq == seq))
    return (pt.id, ir.location_key) if pt is not None else None


def released(db: Session, itp_point_id: uuid.UUID, location_key: str | None) -> bool | None:
    """`HOLD_CHECKS["itp_point"]`: is this ITP point approved at the location key (any key when
    None)? None when the point is unknown."""
    pt = db.get(QItpPoint, itp_point_id)
    if pt is None:
        return None
    itp = db.get(QItp, pt.itp_id)
    if itp is None:
        return None
    return bool(_releasing(db, itp.family_id, location_key, pt.seq, pt.point_type))
