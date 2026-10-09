"""6d action panel (§8.2) and field band (§8.1 item 2): live counts from the registers."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, NotificationKind
from app.core.field_enums import (
    AuditStatus,
    CampaignStatus,
    FieldActionKind,
    ProgrammeLineStatus,
    StopOrderStatus,
)
from app.models import (
    BriefingCampaign,
    ChecklistResponse,
    FieldAudit,
    Inspection,
    InspectionPlan,
    Notification,
    StopWorkOrder,
    WorkforceReturn,
)
from app.schemas.field import FieldActionItem, FieldActionPanel, FieldBand
from app.services.field import audits as au
from app.services.field import campaigns as cmp
from app.services.field import common as fc
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal

C = Capability
K = FieldActionKind
LABELS: dict[FieldActionKind, tuple[str, str]] = {
    K.stop_work_active: ("Active stop-work orders", "أوامر إيقاف عمل سارية"),
    K.plan_without_checklist: ("Plans without checklist", "خطط تفتيش بدون قائمة تحقق"),
    K.not_inspected_this_week: ("Not inspected this week", "لم يتم تفتيشها هذا الأسبوع"),
    K.audit_lines_overdue: ("Audit lines overdue", "بنود تدقيق متأخرة"),
    K.audit_reports_overdue: ("Audit reports overdue", "تقارير تدقيق متأخرة"),
    K.campaigns_unmet: ("Campaigns with unmet pairs", "حملات توعية غير مكتملة"),
    K.offline_rejected: ("Offline submissions rejected (7 days)", "إرسالات مرفوضة دون اتصال"),
}


def week_bounds(db: Session, project_id: uuid.UUID, today: date) -> tuple[date, date]:
    ws = fc.week_of(db, project_id, today)
    return ws, ws + timedelta(days=6)


def uncovered_this_week(
    db: Session, project_id: uuid.UUID, today: date
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """ISP-4: engagement-sites with recent work (daily-return headcount > 0 since the start of
    the previous week) and no Completed inspection with that engagement and site this week."""
    ws, we = week_bounds(db, project_id, today)
    W = WorkforceReturn  # noqa: N806
    req = set(
        db.execute(
            select(W.engagement_id, W.site_id).where(
                W.project_id == project_id,
                W.headcount > 0,
                W.work_date >= ws - timedelta(days=7),
                W.work_date <= today,
            )
        ).all()
    )
    done = set(
        db.execute(
            select(Inspection.engagement_id, Inspection.site_id).where(
                Inspection.project_id == project_id,
                Inspection.status == "completed",
                Inspection.completed_date >= ws,
                Inspection.completed_date <= we,
            )
        ).all()
    )
    return sorted(
        ((e, s) for e, s in req if (e, s) not in done and e is not None),
        key=lambda x: (str(x[1]), str(x[0])),
    )


def _ok(g: Grant, site: uuid.UUID | None, eng: uuid.UUID | None) -> bool:
    return fc.in_scope(g, site, eng) or (
        g.engagement_ids is not None and eng is None and g.covers_site(site)
    )


def action_panel(db: Session, p: Principal, project_id: uuid.UUID) -> FieldActionPanel:
    fc.project(db, p, project_id)
    g = fc.view_grant(p, project_id)
    today = fc.local_day()
    refs = Refs(db)
    items: list[FieldActionItem] = []

    def add(kind: FieldActionKind, rs: list[str]) -> None:
        if rs:
            en, ar = LABELS[kind]
            items.append(FieldActionItem(kind=kind, label_en=en, label_ar=ar, count=len(rs),
                                         refs=rs))  # fmt: skip

    add(K.stop_work_active, [
        o.order_no for o in db.scalars(select(StopWorkOrder).where(
            StopWorkOrder.project_id == project_id,
            StopWorkOrder.status == StopOrderStatus.active).order_by(StopWorkOrder.order_no))
        if _ok(g, o.site_id, o.engagement_id)
    ])  # fmt: skip
    c = fc.cfg(db, project_id)
    if c.templates_required(today):
        add(K.plan_without_checklist, [
            pl.name_en for pl in db.scalars(select(InspectionPlan).where(
                InspectionPlan.project_id == project_id, InspectionPlan.active.is_(True),
                InspectionPlan.template_code.is_(None)).order_by(InspectionPlan.name_en))
            if g.covers_site(pl.site_id)
        ])  # fmt: skip
    _ws, we = week_bounds(db, project_id, today)
    if today >= we - timedelta(days=1):
        rs = []
        for e, s in uncovered_this_week(db, project_id, today):
            if _ok(g, s, e):
                refs.load(sites=[s], engs=[e])
                er, sr = refs.eng(e), refs.site(s)
                rs.append(f"{er.short_code if er else e}@{sr.code if sr else s}")
        add(K.not_inspected_this_week, rs)
    lines = au.lines(db, project_id, today)
    rs = []
    for ln in lines:
        if today > ln.due_by and (g.engagement_ids is None or ln.engagement_id in g.engagement_ids):
            refs.load(engs=[ln.engagement_id])
            er = refs.eng(ln.engagement_id)
            rs.append(f"{ln.audit_type.value}:{er.short_code if er else 'project'}")
    add(K.audit_lines_overdue, rs)
    days = int(c["audit_report_days"])
    add(K.audit_reports_overdue, [
        a.audit_no for a in db.scalars(select(FieldAudit).where(
            FieldAudit.project_id == project_id,
            FieldAudit.status.in_((AuditStatus.in_progress, AuditStatus.fieldwork_complete)),
            FieldAudit.fieldwork_end.is_not(None)).order_by(FieldAudit.audit_no))
        if a.fieldwork_end and today > a.fieldwork_end + timedelta(days=days)
    ])  # fmt: skip
    B = BriefingCampaign  # noqa: N806
    add(K.campaigns_unmet, [
        x.campaign_no for x in db.scalars(select(B).where(
            B.project_id == project_id, B.status == CampaignStatus.issued).order_by(B.campaign_no))
        if x.due_date and today >= x.due_date - timedelta(days=2)
        and any(s.met_on is None for s in cmp.pair_states(db, x))
    ])  # fmt: skip
    rej = db.scalars(
        select(Notification.title_en)
        .where(
            Notification.project_id == project_id,
            Notification.kind == NotificationKind.offline_submission_rejected,
            Notification.created_at >= now() - timedelta(days=7),
        )
        .distinct()
    )
    add(K.offline_rejected, sorted(rej))
    return FieldActionPanel(project_id=project_id, as_of=today, items=items)


def band(db: Session, p: Principal, project_id: uuid.UUID) -> FieldBand:
    fc.project(db, p, project_id)
    fc.view_grant(p, project_id)
    today = fc.local_day()
    active = db.scalar(
        select(func.count())
        .select_from(StopWorkOrder)
        .where(
            StopWorkOrder.project_id == project_id,
            StopWorkOrder.status == StopOrderStatus.active,
        )
    )
    crit = db.scalar(
        select(func.coalesce(func.sum(ChecklistResponse.critical_fail_count), 0)).where(
            ChecklistResponse.project_id == project_id,
            ChecklistResponse.completed_date == today,
            ChecklistResponse.voided.is_(False),
            ChecklistResponse.owner_type == "inspection",
        )
    )
    unmet = sum(
        1
        for x in db.scalars(
            select(BriefingCampaign).where(
                BriefingCampaign.project_id == project_id,
                BriefingCampaign.status == CampaignStatus.issued,
            )
        )
        if any(s.met_on is None for s in cmp.pair_states(db, x))
    )
    due30 = sum(
        1
        for ln in au.lines(db, project_id, today)
        if ln.due_by <= today + timedelta(days=30)
        and au_status(ln.due_by, today) == ProgrammeLineStatus.due
    )
    return FieldBand(
        project_id=project_id,
        stop_work_active=int(active or 0),
        critical_failures_today=int(crit or 0),
        not_inspected_this_week=len(uncovered_this_week(db, project_id, today)),
        campaigns_unmet=unmet,
        audits_due_30_days=due30,
    )


def au_status(due: date, today: date) -> ProgrammeLineStatus:
    return ProgrammeLineStatus.overdue if today > due else ProgrammeLineStatus.due
