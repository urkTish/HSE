"""Q1 jobs (spec 8-quality §4, §B.9): in the `quality_alerts` slot (07:12) IRs not scheduled within
`ir_schedule_hours`, waived witness points not reviewed within `witness_review_days` and IR
comments overdue (the day after due); in the `quality_weekly` slot (Sunday 07:12) the punch
overdue digest to each engagement's quality contacts. Each record, step and recipient is alerted
once (`common.send(key=…)`)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability, EntityType
from app.core.quality.q1 import PUNCH_LIVE, QIrCommentStatus, QIrStatus
from app.models.quality.q1 import QIr, QIrComment, QPunchItem
from app.services.quality import common as qc
from app.services.quality import settings as qs
from app.services.quality.jobs import _projects
from app.services.quality.q1 import ir as irs

C = Capability


def ir_alerts(db: Session, at: datetime) -> dict[str, Any]:
    from app.services.quality.ncr import core  # noqa: PLC0415

    out = {"not_scheduled": 0, "waiver_review_due": 0, "comments_overdue": 0}
    for pr in _projects(db):
        day = qc.project_day(pr, at)
        hours = int(qs.value(db, pr.id, "ir_schedule_hours"))
        review_days = int(qs.value(db, pr.id, "witness_review_days"))
        managers = qc.holders_of(db, pr, C.quality_settings, include_manager=False)
        for ir in db.scalars(
            select(QIr).where(QIr.project_id == pr.id, QIr.status == QIrStatus.submitted)
        ):
            if ir.submitted_at and ir.submitted_at + timedelta(hours=hours) <= at:
                res = irs.resolvers(db, pr, ir)
                out["not_scheduled"] += qc.send(
                    db,
                    {*res.users, *managers} - set(irs.requesters(db, ir)),
                    f"{ir.ir_no} is not scheduled after {hours} h",
                    f"{ir.ir_no} لم يُجدول بعد {hours} ساعة",
                    entity_type=EntityType.q_ir,
                    entity_id=ir.id,
                    project_id=pr.id,
                    key=f"ir_not_scheduled:{ir.id}",
                    path=f"/quality/inspection-requests/{ir.id}",
                )
        for ir in db.scalars(
            select(QIr).where(QIr.project_id == pr.id, QIr.status == QIrStatus.witness_waived)
        ):
            rnd = irs.current(db, ir)
            if rnd is None or rnd.waived_at is None:
                continue
            if qc.project_day(pr, rnd.waived_at) + timedelta(days=review_days) <= day:
                res = irs.resolvers(db, pr, ir)
                out["waiver_review_due"] += qc.send(
                    db,
                    set(res.users) - set(irs.requesters(db, ir)),
                    f"{ir.ir_no}: review the waived witness point",
                    f"{ir.ir_no}: راجع نقطة الشهادة المتنازل عنها",
                    entity_type=EntityType.q_ir,
                    entity_id=ir.id,
                    project_id=pr.id,
                    key=f"ir_waiver_review:{ir.id}:{rnd.round_no}",
                    path=f"/quality/inspection-requests/{ir.id}",
                )
        for cm in db.scalars(
            select(QIrComment).where(
                QIrComment.project_id == pr.id,
                QIrComment.status != QIrCommentStatus.closed,
                QIrComment.due_on < day,
            )
        ):
            owner = db.get(QIr, cm.ir_id)
            if owner is None or owner.status == QIrStatus.voided:
                continue
            to = {owner.requested_by_user_id} | core.engagement_contacts(
                db, pr, owner.engagement_id
            )
            out["comments_overdue"] += qc.send(
                db,
                to,
                f"{owner.ir_no}: approval comment overdue since {cm.due_on}",
                f"{owner.ir_no}: ملاحظة اعتماد متأخرة منذ {cm.due_on}",
                entity_type=EntityType.q_ir,
                entity_id=owner.id,
                project_id=pr.id,
                email=False,
                key=f"ir_comment_overdue:{cm.id}",
                path=f"/quality/inspection-requests/{owner.id}",
            )
    db.flush()
    return out


def punch_digest(db: Session, at: datetime) -> dict[str, Any]:
    """Q-PUN-03: weekly digest of overdue items to the engagement's quality contacts."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    sent = 0
    for pr in _projects(db):
        day = qc.project_day(pr, at)
        by_eng: dict[Any, list[QPunchItem]] = defaultdict(list)
        for it in db.scalars(
            select(QPunchItem).where(
                QPunchItem.project_id == pr.id,
                QPunchItem.status.in_(list(PUNCH_LIVE)),
                QPunchItem.target_date < day,
            )
        ):
            by_eng[it.responsible_engagement_id].append(it)
        for eng_id, items in by_eng.items():
            to = core.engagement_contacts(db, pr, eng_id)
            if not to:
                continue
            refs = ", ".join(i.punch_no for i in sorted(items, key=lambda x: x.punch_no)[:30])
            n_a = sum(1 for i in items if i.category.value == "A")
            sent += qc.send(
                db,
                to,
                f"{len(items)} punch item(s) overdue ({n_a} category A)",
                f"{len(items)} بند نواقص متأخر ({n_a} من الفئة A)",
                body_en=refs,
                body_ar=refs,
                entity_type=EntityType.q_punch_item,
                project_id=pr.id,
                key=f"punch_digest:{pr.id}:{eng_id}:{day.isoformat()}",
                path="/quality/punch?overdue=true",
            )
    db.flush()
    return {"digests": sent}
