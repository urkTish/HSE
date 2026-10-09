"""Phase 6d scheduled jobs (6d-field-assurance §4, §7, P6d-3).

`field_minute` (every 60 s): stop-work alerts and permit suspensions of synced submissions not yet
processed (FND-7, FND-9; normally done inline at receipt).
`field_daily` (00:09): talks Delivered → Locked (§4.6), audits Issued → Closed (§4.4), photo
retention (P6d-3) and the settings cache reset.
`field_alerts` (07:06): stop-work orders Active > 24 h, engagement-sites not inspected this week
(ISP-4), audit lines due / overdue (AUD-7), audit reports not issued (AUD-5), campaign reminders
and close (CMP-4, §4.5), template and topic review due (TPL-6).

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind, ProjectStatus
from app.core.field_enums import AuditStatus, StopOrderStatus, VersionStatus
from app.core.hse_enums import AttachmentOwner, CaStatus
from app.models import (
    Attachment,
    ChecklistResponse,
    ChecklistTemplate,
    CorrectiveAction,
    FieldAudit,
    FieldFinding,
    Project,
    StopWorkOrder,
    ToolboxTopic,
)

NK = NotificationKind


def _projects(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(Project.id).where(Project.status != ProjectStatus.closed)))


def field_minute(db: Session) -> dict[str, Any]:
    from app.services.field import execution  # noqa: PLC0415

    n = 0
    for o in db.scalars(
        select(StopWorkOrder).where(
            StopWorkOrder.processed.is_(False), StopWorkOrder.status == StopOrderStatus.active
        )
    ):
        execution.process_order(db, o)
        n += 1
    db.flush()
    return {"orders_processed": n}


def _retention(db: Session, pid: uuid.UUID, today: date) -> int:
    """P6d-3: answer photos older than photo_retention_months, unless a linked CA is open or the
    stop-work order is Active. Scores and findings stay."""
    from app.services import attachments  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415
    from app.services.train.common import add_months  # noqa: PLC0415

    months = int(fc.cfg(db, pid)["photo_retention_months"])
    cutoff = add_months(today, -months)
    n = 0
    for r in db.scalars(
        select(ChecklistResponse).where(
            ChecklistResponse.project_id == pid, ChecklistResponse.completed_date < cutoff
        )
    ):
        if not any(a.get("photo_ids") for a in r.answers or []):
            continue
        ca_ids = [
            x
            for x in db.scalars(
                select(FieldFinding.ca_id).where(
                    FieldFinding.response_id == r.id, FieldFinding.ca_id.is_not(None)
                )
            )
            if x is not None
        ]
        if ca_ids and db.scalar(
            select(CorrectiveAction.id).where(
                CorrectiveAction.id.in_(ca_ids),
                CorrectiveAction.status.not_in((CaStatus.closed, CaStatus.cancelled)),
            )
        ):
            continue
        if r.stop_work_order_id:
            o = db.get(StopWorkOrder, r.stop_work_order_id)
            if o is not None and o.status == StopOrderStatus.active:
                continue
        for a in db.scalars(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwner.field_photo, Attachment.owner_id == r.id
            )
        ):
            attachments.erase(db, a)
            n += 1
        r.answers = [{**a, "photo_ids": []} for a in r.answers or []]
    db.flush()
    return n


def field_daily(db: Session) -> dict[str, Any]:
    from app.services.field import audits, talks  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    fc.clear_cache(db)
    today = fc.local_day()
    out = {"locked": 0, "closed": 0, "photos_deleted": 0}
    for pid in _projects(db):
        out["locked"] += talks.lock_due(db, pid)
        out["closed"] += audits.close_issued(db, pid)
        out["photos_deleted"] += _retention(db, pid, today)
    return out


def field_alerts(db: Session) -> dict[str, Any]:
    from app.services.field import audits as au  # noqa: PLC0415
    from app.services.field import board, campaigns  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    today = fc.local_day()
    sent = 0
    for pid in _projects(db):
        offs = fc.officers(db, pid)
        # stop-work orders Active > 24 h (daily)
        for o in db.scalars(
            select(StopWorkOrder).where(
                StopWorkOrder.project_id == pid,
                StopWorkOrder.status == StopOrderStatus.active,
                StopWorkOrder.raised_at <= now() - timedelta(hours=24),
            )
        ):
            if fc.once(db, f"field:swo24:{o.id}:{today}"):
                sent += fc.send(db, offs | fc.managers(db), NK.stop_work_order,
                                f"{o.order_no} still Active after 24 h",
                                f"{o.order_no} ما زال سارياً بعد 24 ساعة", pid,
                                EntityType.stop_work_order, o.id, email=True)  # fmt: skip
        # ISP-4: the day before the last day of the week
        ws, we = board.week_bounds(db, pid, today)
        if today == we - timedelta(days=1):
            for e, s in board.uncovered_this_week(db, pid, today):
                if fc.once(db, f"field:isp4:{e}:{s}:{ws}"):
                    sent += fc.send(db, fc.reps(db, pid, e) | fc.site_engineers(db, pid, s),
                                    NK.inspection_coverage_gap,
                                    "No inspection of your engagement on this site this week "
                                    "(ISP-4)", "لم يتم تفتيش أعمال المقاول في هذا الموقع هذا "
                                    "الأسبوع", pid, EntityType.inspection, None)  # fmt: skip
        # AUD-7 programme lines: 30 / 7 / 0 days, first overdue day, then weekly
        for ln in au.lines(db, pid, today):
            left = (ln.due_by - today).days
            step: str | None = None
            if left in (30, 7, 0):
                step = str(left)
            elif left < 0 and (-left - 1) % 7 == 0:
                step = f"over{-left}"
            if step and fc.once(db, f"field:aud7:{pid}:{ln.engagement_id}:{ln.due_by}:{step}"):
                who = offs | fc.reps(db, pid, ln.engagement_id)
                sent += fc.send(db, who, NK.audit_due,
                                f"Audit due by {ln.due_by} ({ln.audit_type.value})",
                                f"تدقيق مستحق بتاريخ {ln.due_by}", pid, EntityType.field_audit,
                                ln.last.id if ln.last else None, email=True)  # fmt: skip
        # AUD-5 report not issued
        days = int(fc.cfg(db, pid)["audit_report_days"])
        for a in db.scalars(
            select(FieldAudit).where(
                FieldAudit.project_id == pid,
                FieldAudit.status.in_((AuditStatus.in_progress, AuditStatus.fieldwork_complete)),
                FieldAudit.fieldwork_end.is_not(None),
            )
        ):
            assert a.fieldwork_end is not None  # noqa: S101
            deadline = a.fieldwork_end + timedelta(days=days)
            if today < deadline:
                continue
            if fc.once(db, f"field:aud5:{a.id}:{today}"):
                who = {a.lead_auditor_id} | offs
                if today >= deadline + timedelta(days=3):
                    who |= fc.managers(db)
                sent += fc.send(db, who, NK.audit_report_overdue,
                                f"{a.audit_no}: report not issued (due {deadline})",
                                f"{a.audit_no}: لم يصدر التقرير", pid, EntityType.field_audit,
                                a.id, email=True)  # fmt: skip
        campaigns.daily(db, pid, today)
    # TPL-6 review due 30 / 0 days (org-wide)
    rows: list[Any] = [
        *db.scalars(
            select(ChecklistTemplate).where(ChecklistTemplate.status == VersionStatus.published)
        ),
        *db.scalars(select(ToolboxTopic).where(ToolboxTopic.status == VersionStatus.published)),
    ]
    for t in rows:
        if t.review_due_on is None:
            continue
        left = (t.review_due_on - today).days
        if left in (30, 0) and fc.once(db, f"field:review:{t.id}:{left}"):
            code = getattr(t, "template_code", None) or getattr(t, "topic_code", "")
            sent += fc.send(db, fc.managers(db), NK.field_library_review,
                            f"{code} review due {t.review_due_on}",
                            f"موعد مراجعة {code}: {t.review_due_on}", None)  # fmt: skip
    return {"sent": sent}


PHASE6D_JOBS = {
    "field_minute": field_minute,
    "field_daily": field_daily,
    "field_alerts": field_alerts,
}
