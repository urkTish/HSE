"""Dashboard action panel, expiring items and saved filters (spec 1-dashboard §8.1, D-2).
Counts reuse the KPI engine (overdue CAs = K-42, AC64) and the register filters, so every link
opens exactly the counted records."""

import uuid
from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.kpi_params import KpiQuery
from app.core.clock import now
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.errors import validation_error
from app.core.hse_enums import (
    ActionPanelItem,
    CaStatus,
    ExpiringItemKind,
    IncidentStatus,
    InspectionStatus,
    KpiMetric,
    ObservationStatus,
    RiskRating,
    Severity,
)
from app.kpi import scope as kscope
from app.kpi import service as ksvc
from app.kpi import warnings as kwarn
from app.kpi.facts import Filter
from app.models import (
    CorrectiveAction,
    DashboardPreference,
    ExternalNotification,
    Incident,
    Inspection,
    Investigation,
    Observation,
    PeriodLock,
)
from app.schemas.dashboard import (
    ActionPanelBreakdown,
    ActionPanelEntry,
    ActionPanelResponse,
    DashboardFilters,
    DashboardPreferencesRead,
    ExpiringItem,
    ExpiringItemsResponse,
    ListLink,
)
from app.services import corrective_actions as ca_svc
from app.services import hse_settings, projects
from app.services import incidents as inc_svc
from app.services.access import dashboard_items as access_items
from app.services.hse_common import Refs, project_today
from app.services.permissions import Principal, forbidden_error

LABELS: dict[ActionPanelItem, tuple[str, str]] = {
    ActionPanelItem.overdue_cas: ("Overdue corrective actions", "إجراءات تصحيحية متأخرة"),
    ActionPanelItem.cas_pending_verification: (
        "Actions awaiting verification",
        "إجراءات بانتظار التحقق",
    ),
    ActionPanelItem.investigations_overdue: ("Investigations overdue", "تحقيقات متأخرة"),
    ActionPanelItem.incidents_unclassified: (
        "Incidents not classified > 24 h",
        "حوادث غير مصنفة > 24 ساعة",
    ),
    ActionPanelItem.external_notifications_due: (
        "External notifications due",
        "إخطارات خارجية مستحقة",
    ),
    ActionPanelItem.open_lti_cases: (
        "Open LTI cases (no return to work)",
        "حالات إصابة مضيعة للوقت مفتوحة",
    ),
    ActionPanelItem.missed_inspections: ("Missed inspections", "عمليات تفتيش فائتة"),
    ActionPanelItem.missing_daily_returns: ("Missing daily returns", "بيانات يومية مفقودة"),
    ActionPanelItem.high_risk_observations_without_ca: (
        "High-risk observations without action > 24 h",
        "ملاحظات عالية الخطورة دون إجراء > 24 ساعة",
    ),
    ActionPanelItem.leading_warnings: ("Leading-indicator warnings", "تحذيرات المؤشرات الاستباقية"),
}


def _filters(sc: kscope.Scope) -> dict[str, list[str]]:
    q = sc.query
    out: dict[str, list[str]] = {}
    if q.site_ids:
        out["site_id"] = [str(x) for x in q.site_ids]
    if q.engagement_ids:
        out["engagement_id"] = [str(x) for x in q.engagement_ids]
    return out


def _link(resource: str, path: str, query: dict[str, Any]) -> ListLink:
    return ListLink(
        resource=resource,
        path=f"{API_PREFIX}{path}",
        query={k: v if isinstance(v, list) else str(v) for k, v in query.items()},
    )


LABELS.update(access_items.LABELS)


def _ok(f: Filter, site: uuid.UUID, eng: uuid.UUID | None) -> bool:
    return f.site_ok(site) and f.eng_ok(eng)


def action_panel(db: Session, p: Principal, q: KpiQuery) -> ActionPanelResponse:
    sc = kscope.build(db, p, q)
    if not sc.single_project:
        raise validation_error("project_id", "The action panel needs exactly one project.")
    project = sc.projects[0]
    pid = project.id
    f = sc.flt
    w = sc.window
    day = min(sc.as_of, w.end)
    base = f"/projects/{pid}"
    flt = _filters(sc)
    refs = Refs(db)
    entries: list[ActionPanelEntry] = []

    def add(
        key: ActionPanelItem,
        count: int,
        severity: Severity,
        link: ListLink | None,
        by: Counter[uuid.UUID | None] | None = None,
    ) -> None:
        en, ar = LABELS[key]
        rows = []
        for eid, n in sorted((by or Counter()).items(), key=lambda kv: -kv[1]):
            ref = refs.eng(eid) if eid else None
            if ref is not None:
                rows.append(ActionPanelBreakdown(engagement=ref, count=n))
        entries.append(
            ActionPanelEntry(
                key=key,
                label_en=en,
                label_ar=ar,
                count=count,
                severity=severity if count else Severity.info,
                link=link,
                by_contractor=rows,
            )
        )

    # 1. overdue CAs = K-42 (same facts, same evaluation day)
    k42 = ksvc.kpi_value(sc, KpiMetric.K42, with_comparisons=False)
    by: Counter[uuid.UUID | None] = Counter()
    pending: Counter[uuid.UUID | None] = Counter()
    for ca in sc.engine.cas:
        if ca.created > day:
            continue
        done = ca.completed is not None and ca.completed <= day
        closed = ca.verified is not None and ca.verified <= day
        if not done and not closed and day > ca.due:
            by[ca.eng] += 1
        if done and not closed:
            pending[ca.eng] += 1
    add(
        ActionPanelItem.overdue_cas,
        int(k42.value or 0),
        Severity.critical,
        _link(
            "corrective_actions",
            f"{base}/corrective-actions",
            {"overdue": "true", "as_of": day.isoformat(), **flt},
        ),
        by,
    )
    add(
        ActionPanelItem.cas_pending_verification,
        sum(pending.values()),
        Severity.warning,
        _link(
            "corrective_actions",
            f"{base}/corrective-actions",
            {"status": CaStatus.pending_verification.value, **flt},
        ),
        pending,
    )
    # 2. incident register items
    incs = list(
        db.scalars(
            select(Incident).where(
                Incident.project_id == pid,
                Incident.status.not_in([IncidentStatus.draft, IncidentStatus.voided]),
            )
        )
    )
    incs = [i for i in incs if _ok(f, i.site_id, i.responsible_engagement_id)]
    ids = [i.id for i in incs]
    invs = {
        v.incident_id: v
        for v in (
            db.scalars(select(Investigation).where(Investigation.incident_id.in_(ids)))
            if ids
            else []
        )
    }
    inv_by: Counter[uuid.UUID | None] = Counter(
        i.responsible_engagement_id
        for i in incs
        if (v := invs.get(i.id)) is not None and inc_svc.investigation_overdue(i, v, sc.as_of)
    )
    add(
        ActionPanelItem.investigations_overdue,
        sum(inv_by.values()),
        Severity.warning,
        _link("incidents", f"{base}/incidents", {"investigation_overdue": "true", **flt}),
        inv_by,
    )
    cutoff = now() - timedelta(hours=24)
    uncl: Counter[uuid.UUID | None] = Counter(
        i.responsible_engagement_id
        for i in incs
        if i.status == IncidentStatus.reported and i.reported_at and i.reported_at < cutoff
    )
    add(
        ActionPanelItem.incidents_unclassified,
        sum(uncl.values()),
        Severity.warning,
        _link("incidents", f"{base}/incidents", {"unclassified_over_hours": "24", **flt}),
        uncl,
    )
    cases = inc_svc.load_cases(db, ids)
    recorded: dict[uuid.UUID, set[str]] = {}
    if ids:
        for n in db.scalars(
            select(ExternalNotification).where(ExternalNotification.incident_id.in_(ids))
        ):
            recorded.setdefault(n.incident_id, set()).add(str(n.body))
    notif: Counter[uuid.UUID | None] = Counter(
        i.responsible_engagement_id
        for i in incs
        if any(
            r.body.value not in recorded.get(i.id, set())
            for r in inc_svc.required_notifications(i, cases.get(i.id, []))
        )
    )
    add(
        ActionPanelItem.external_notifications_due,
        sum(notif.values()),
        Severity.critical,
        _link("incidents", f"{base}/incidents", {"notification_due": "true", **flt}),
        notif,
    )
    lti: Counter[uuid.UUID | None] = Counter()
    for i in incs:
        for c in cases.get(i.id, []):
            if inc_svc.open_lti(c):
                lti[c.employer_engagement_id or i.responsible_engagement_id] += 1
    add(
        ActionPanelItem.open_lti_cases,
        sum(lti.values()),
        Severity.warning,
        _link("incidents", f"{base}/incidents", {"open_lti": "true", **flt}),
        lti,
    )
    # 3. inspections
    missed: Counter[uuid.UUID | None] = Counter(
        ins.engagement_id
        for ins in db.scalars(
            select(Inspection).where(
                Inspection.project_id == pid,
                Inspection.status == InspectionStatus.missed,
                Inspection.planned_date >= w.start,
                Inspection.planned_date <= w.end,
            )
        )
        if f.site_ok(ins.site_id) and (f.engs is None or ins.engagement_id in f.engs)
    )
    add(
        ActionPanelItem.missed_inspections,
        sum(missed.values()),
        Severity.warning,
        _link(
            "inspections",
            f"{base}/inspections",
            {
                "status": InspectionStatus.missed.value,
                "planned_from": w.start.isoformat(),
                "planned_to": w.end.isoformat(),
                **flt,
            },
        ),
        missed,
    )
    # 4. returns
    cells = sc.engine.missing_cells(w)
    add(
        ActionPanelItem.missing_daily_returns,
        len(cells),
        Severity.warning,
        None,
        Counter(c[0] for c in cells),
    )
    # 5. observations
    obs: Counter[uuid.UUID | None] = Counter(
        o.observed_engagement_id
        for o in db.scalars(
            select(Observation).where(
                Observation.project_id == pid,
                Observation.status == ObservationStatus.open,
                Observation.risk_rating == RiskRating.high,
                Observation.closed_on_spot.is_(False),
                Observation.created_at < cutoff,
            )
        )
        if _ok(f, o.site_id, o.observed_engagement_id)
    )
    add(
        ActionPanelItem.high_risk_observations_without_ca,
        sum(obs.values()),
        Severity.warning,
        _link("observations", f"{base}/observations", {"without_ca_over_hours": "24", **flt}),
        obs,
    )
    # 6. leading warnings (last complete month)
    found = kwarn.evaluate(sc, kwarn.complete_months(sc, w, 1))
    add(
        ActionPanelItem.leading_warnings,
        len(found),
        Severity.warning,
        None,
        Counter(x.engagement.id if x.engagement else None for x in found),
    )
    # 7. Phase 2 access items (2-access-permits §8.3; airport projects, capability 77)
    access_items.action_items(db, p, project, day, f.engs, f.sites, add, _link, flt)
    return ActionPanelResponse(project_id=pid, as_of=day, items=entries)


# ---- expiring items ------------------------------------------------------------------------------


def expiring_items(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    within_days: int,
    include_overdue: bool,
    as_of: date | None,
) -> ExpiringItemsResponse:
    project = projects.get_visible(db, p, project_id)
    p_grant = p.grant(project.id, Capability.dashboard_view)
    if p_grant is None:
        raise forbidden_error()
    day = as_of or project_today(project)
    horizon = day + timedelta(days=within_days)
    refs = Refs(db)
    items: list[ExpiringItem] = []

    def keep(d: date) -> bool:
        return d <= horizon and (include_overdue or d >= day)

    for ca in db.scalars(
        ca_svc.scoped_query(p, project).where(
            CorrectiveAction.status.in_([CaStatus.open, CaStatus.in_progress])
        )
    ):
        if keep(ca.due_date):
            items.append(
                ExpiringItem(
                    kind=ExpiringItemKind.ca_due,
                    entity_type=EntityType.corrective_action,
                    entity_id=ca.id,
                    ref=ca.ref,
                    title_en=ca.title,
                    title_ar=ca.title,
                    due_date=ca.due_date,
                    days_left=(ca.due_date - day).days,
                    engagement=refs.eng(ca.responsible_engagement_id),
                    detail_path=f"{API_PREFIX}/corrective-actions/{ca.id}",
                )
            )
    incs = list(
        db.scalars(
            inc_svc.scoped_query(db, p, project).where(
                Incident.status.not_in([IncidentStatus.draft, IncidentStatus.voided])
            )
        )
    )
    ids = [i.id for i in incs]
    invs = {
        v.incident_id: v
        for v in (
            db.scalars(select(Investigation).where(Investigation.incident_id.in_(ids)))
            if ids
            else []
        )
    }
    cases = inc_svc.load_cases(db, ids)
    recorded: dict[uuid.UUID, set[str]] = {}
    if ids:
        for n in db.scalars(
            select(ExternalNotification).where(ExternalNotification.incident_id.in_(ids))
        ):
            recorded.setdefault(n.incident_id, set()).add(str(n.body))
    tz = inc_svc.tz_of(project)
    for i in incs:
        v = invs.get(i.id)
        if (
            v
            and v.due_date
            and v.submitted_at is None
            and i.status in (IncidentStatus.reported, IncidentStatus.under_investigation)
            and keep(v.due_date)
        ):
            items.append(
                ExpiringItem(
                    kind=ExpiringItemKind.investigation_due,
                    entity_type=EntityType.investigation,
                    entity_id=i.id,
                    ref=i.ref,
                    title_en=f"Investigation {v.level.value} due",
                    title_ar=f"استحقاق التحقيق {v.level.value}",
                    due_date=v.due_date,
                    days_left=(v.due_date - day).days,
                    engagement=refs.eng(i.responsible_engagement_id),
                    detail_path=f"{API_PREFIX}/incidents/{i.id}/investigation",
                )
            )
        for r in inc_svc.required_notifications(i, cases.get(i.id, [])):
            if r.body.value in recorded.get(i.id, set()):
                continue
            due = r.due_at.astimezone(tz).date()
            if keep(due):
                items.append(
                    ExpiringItem(
                        kind=ExpiringItemKind.external_notification_due,
                        entity_type=EntityType.incident,
                        entity_id=i.id,
                        ref=i.ref,
                        title_en=f"Notify {r.body.value}: {r.reason}",
                        title_ar=f"إخطار {r.body.value}",
                        due_date=due,
                        days_left=(due - day).days,
                        engagement=refs.eng(i.responsible_engagement_id),
                        detail_path=f"{API_PREFIX}/incidents/{i.id}",
                    )
                )
    for ins in db.scalars(
        select(Inspection).where(
            Inspection.project_id == project.id,
            Inspection.status == InspectionStatus.planned,
            Inspection.planned_date <= horizon,
        )
    ):
        if ins.planned_date is None or not keep(ins.planned_date):
            continue
        g = p.grant(project.id, Capability.incident_view)
        if not (
            p.user.id == ins.assignee_user_id
            or (g and g.covers_site(ins.site_id) and g.covers_engagement(ins.engagement_id))
            or (g and g.engagement_ids is None and g.covers_site(ins.site_id))
        ):
            continue
        items.append(
            ExpiringItem(
                kind=ExpiringItemKind.inspection_planned,
                entity_type=EntityType.inspection,
                entity_id=ins.id,
                ref=ins.ref,
                title_en=f"Inspection {ins.inspection_type.value}",
                title_ar=f"تفتيش {ins.inspection_type.value}",
                due_date=ins.planned_date,
                days_left=(ins.planned_date - day).days,
                engagement=refs.eng(ins.engagement_id),
                detail_path=f"{API_PREFIX}/inspections/{ins.id}",
            )
        )
    # month lock: previous month locks on month_lock_day of this month
    s = hse_settings.get(db, project.id)
    first = day.replace(day=1)
    lock_day = first.replace(day=min(s.month_lock_day, 28))
    prev = (first - timedelta(days=1)).replace(day=1)
    lock = db.get(PeriodLock, (project.id, prev))
    if (lock is None or not lock.locked) and keep(lock_day):
        items.append(
            ExpiringItem(
                kind=ExpiringItemKind.month_lock,
                entity_type=EntityType.workforce_month,
                entity_id=None,
                ref=prev.strftime("%Y-%m"),
                title_en=f"{prev.strftime('%Y-%m')} locks on {lock_day.isoformat()}",
                title_ar=f"يُقفل شهر {prev.strftime('%Y-%m')} في {lock_day.isoformat()}",
                due_date=lock_day,
                days_left=(lock_day - day).days,
                engagement=None,
                detail_path=f"{API_PREFIX}/projects/{project.id}/workforce-months",
            )
        )
    items.extend(access_items.expiring(db, p, project, day, horizon, include_overdue))
    items.sort(key=lambda x: (x.due_date, x.kind.value, x.ref or ""))
    return ExpiringItemsResponse(
        project_id=project.id, as_of=day, within_days=within_days, items=items
    )


# ---- preferences ---------------------------------------------------------------------------------


def get_preferences(db: Session, p: Principal) -> DashboardPreferencesRead:
    row = db.get(DashboardPreference, p.user.id)
    filters = DashboardFilters(**row.filters) if row and row.filters else DashboardFilters()
    return DashboardPreferencesRead(filters=filters)


def put_preferences(db: Session, p: Principal, body: DashboardFilters) -> DashboardPreferencesRead:
    if body.project_id is not None:
        projects.get_visible(db, p, body.project_id)
    if body.all_projects and not p.is_manager:
        body = body.model_copy(update={"all_projects": False})
    row = db.get(DashboardPreference, p.user.id)
    data = body.model_dump(mode="json")
    if row is None:
        db.add(DashboardPreference(user_id=p.user.id, filters=data, updated_at=now()))
    else:
        row.filters = data
        row.updated_at = now()
    db.flush()
    return DashboardPreferencesRead(filters=body)
