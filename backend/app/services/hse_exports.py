"""Phase 1 register exports (spec 1-dashboard P1-6, capability 42/43). Every export lists only
records the caller may see; injured-person identity columns need capability 43 and a purpose;
medical fields and attachments are never exported (P1-3)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.enums import AuditAction, Capability, ExportDataset, ExportFormat
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import ExportPurpose
from app.models import HseMeeting, Incident
from app.services import audit, hse_settings, projects
from app.services import corrective_actions as ca_svc
from app.services import exports as export_svc
from app.services import incidents as inc_svc
from app.services import inspections as ins_svc
from app.services import observations as obs_svc
from app.services import workforce as wf_svc
from app.services.hse_common import Refs, project_today
from app.services.injury_cases import PRIVACY_EN
from app.services.permissions import Principal, forbidden_error

MAX_ROWS = 50_000
IDENTITY_COLS = ["person_name", "id_type", "id_number", "employee_no", "gosi_case_ref"]


def _eng(refs: Refs, eid: uuid.UUID | None) -> str:
    e = refs.eng(eid)
    return e.short_code if e else ""


def export(
    db: Session,
    p: Principal,
    dataset: ExportDataset,
    fmt: ExportFormat,
    project_id: uuid.UUID | None,
    status: str | None,
    q: str | None,
    include_identity: bool,
    purpose: ExportPurpose | None,
    purpose_text: str | None,
) -> tuple[bytes, str, str]:
    if project_id is None:
        raise validation_error("project_id", "Choose a project to export.")
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, Capability.export_kpis) is None:
        raise forbidden_error()
    if include_identity:
        if dataset != ExportDataset.incidents:
            raise validation_error("include_identity", "Identity columns exist only for incidents.")
        if p.grant(project.id, Capability.export_identity) is None:
            raise forbidden_error("Exporting identities needs capability 43.")
        if purpose is None or (purpose == ExportPurpose.other and not (purpose_text or "").strip()):
            raise ApiError(
                422,
                ErrorCode.EXPORT_PURPOSE_REQUIRED,
                "State the purpose of an export with identities (P1-6).",
                "يجب ذكر الغرض من تصدير البيانات الشخصية.",
            )
    refs = Refs(db)
    cols: list[str]
    rows: list[list[Any]] = []
    if dataset == ExportDataset.workforce_returns:
        page = wf_svc.list_page(db, p, project.id, 1, MAX_ROWS)
        cols = [
            "work_date",
            "site",
            "zone",
            "contractor",
            "shift",
            "no_work",
            "headcount",
            "man_hours",
            "toolbox_talks",
            "toolbox_attendees",
            "inductions",
            "training_hours",
            "status",
            "source",
        ]
        for r in page.items:
            rows.append(
                [
                    r.work_date,
                    r.site.code,
                    r.zone.code if r.zone else "",
                    r.engagement.short_code,
                    r.shift.value,
                    r.no_work,
                    r.headcount,
                    r.man_hours,
                    r.toolbox_talks,
                    r.toolbox_attendees,
                    r.inductions,
                    r.training_hours,
                    r.status.value,
                    r.source.value,
                ]
            )
    elif dataset == ExportDataset.incidents:
        stmt = inc_svc.scoped_query(db, p, project)
        if status:
            stmt = stmt.where(Incident.status == status)
        incs = list(db.scalars(stmt.order_by(Incident.occurred_at).limit(MAX_ROWS)))
        cases = inc_svc.load_cases(db, [i.id for i in incs])
        s = hse_settings.get(db, project.id)
        refs.load(
            sites=[i.site_id for i in incs],
            zones=[i.zone_id for i in incs],
            engs=[i.responsible_engagement_id for i in incs]
            + [c.employer_engagement_id for cs in cases.values() for c in cs],
        )
        base = [
            "ref",
            "occurred_date",
            "site",
            "zone",
            "contractor",
            "incident_types",
            "primary_type",
            "title",
            "activity",
            "actual_severity",
            "potential_severity",
            "hipo",
            "status",
            "late_report",
            "work_related",
        ]
        case_cols = [
            "case_no",
            "person_type",
            "employer",
            "trade",
            "case_category",
            "classification_status",
            "excluded_from_rates",
        ]
        cols = base + case_cols + (IDENTITY_COLS if include_identity else [])
        for i in incs:
            head = [
                i.ref,
                i.occurred_date,
                refs.site(i.site_id).code,
                (z.code if (z := refs.zone(i.zone_id)) else ""),
                _eng(refs, i.responsible_engagement_id),
                ",".join(i.incident_types),
                i.primary_type.value,
                i.title,
                i.activity.value if i.activity else "",
                i.actual_severity,
                i.potential_severity,
                i.hipo,
                i.status.value,
                i.late_report,
                i.work_related,
            ]
            cs = cases.get(i.id, [])
            if not cs:
                rows.append(head + [""] * (len(cols) - len(head)))
                continue
            for c in cs:
                row = [
                    *head,
                    f"{i.ref}-P{c.person_no}",
                    c.person_type.value,
                    _eng(refs, c.employer_engagement_id),
                    c.trade.value,
                    c.category.value,
                    c.classification_status.value,
                    bool(inc_svc.exclusion_reasons(i, c, s)),
                ]
                if include_identity:
                    hidden = c.privacy_case and not p.is_manager
                    row += [
                        PRIVACY_EN if hidden else c.person_name,
                        "" if hidden or not c.id_type else c.id_type.value,
                        "" if hidden or not c.id_number_enc else crypto.decrypt(c.id_number_enc),
                        c.employee_no or "",
                        c.gosi_case_ref or "",
                    ]
                rows.append(row)
    elif dataset == ExportDataset.observations:
        page_o = obs_svc.list_page(db, p, project.id, 1, MAX_ROWS)
        cols = [
            "ref",
            "observed_at",
            "site",
            "zone",
            "contractor",
            "obs_type",
            "category",
            "risk_rating",
            "status",
            "stop_work_applied",
            "observer",
            "description",
        ]
        for o in page_o.items:
            rows.append(
                [
                    o.ref,
                    o.observed_at,
                    o.site.code,
                    o.zone.code if o.zone else "",
                    o.observed_engagement.short_code,
                    o.obs_type.value,
                    o.category.value,
                    o.risk_rating.value if o.risk_rating else "",
                    o.status.value,
                    o.stop_work_applied,
                    o.observer.full_name_en if o.observer else ("anonymous" if o.anonymous else ""),
                    o.description,
                ]
            )
    elif dataset == ExportDataset.inspections:
        page_i = ins_svc.list_page(db, p, project.id, 1, MAX_ROWS)
        cols = [
            "ref",
            "plan",
            "inspection_type",
            "site",
            "contractor",
            "planned_date",
            "completed_at",
            "status",
            "timeliness",
            "items_checked",
            "items_compliant",
            "score_pct",
            "findings",
        ]
        for x in page_i.items:
            rows.append(
                [
                    x.ref,
                    x.plan_name_en or "",
                    x.inspection_type.value,
                    x.site.code,
                    x.engagement.short_code if x.engagement else "",
                    x.planned_date or "",
                    x.completed_at or "",
                    x.status.value,
                    x.timeliness.value,
                    x.items_checked,
                    x.items_compliant,
                    x.score_pct,
                    len(x.findings),
                ]
            )
    elif dataset == ExportDataset.corrective_actions:
        page_c = ca_svc.list_page(db, p, project.id, 1, MAX_ROWS)
        cols = [
            "ref",
            "source",
            "title",
            "control_level",
            "priority",
            "contractor",
            "owner",
            "verifier",
            "due_date",
            "original_due_date",
            "status",
            "overdue",
            "days_overdue",
        ]
        for a in page_c.items:
            rows.append(
                [
                    a.ref,
                    a.source.ref or a.source.type.value,
                    a.title,
                    a.control_level.value,
                    a.priority.value,
                    a.responsible_engagement.short_code,
                    a.owner.full_name_en,
                    a.verifier.full_name_en,
                    a.due_date,
                    a.original_due_date,
                    a.status.value,
                    a.overdue,
                    a.days_overdue,
                ]
            )
    else:
        cols = [
            "meeting_type",
            "title",
            "contractor",
            "planned_date",
            "held_date",
            "invited",
            "attended",
        ]
        for m in db.scalars(
            select(HseMeeting)
            .where(HseMeeting.project_id == project.id)
            .order_by(HseMeeting.planned_date)
        ):
            rows.append(
                [
                    m.meeting_type.value,
                    m.title or "",
                    _eng(refs, m.engagement_id),
                    m.planned_date,
                    m.held_date or "",
                    m.invited_count,
                    m.attended_count,
                ]
            )
    details: dict[str, Any] = {
        "dataset": dataset.value,
        "format": fmt.value,
        "row_count": len(rows),
        "columns": cols,
        "filters": {
            k: v for k, v in {"project_id": str(project.id), "status": status, "q": q}.items() if v
        },
        "as_of": project_today(project).isoformat(),
    }
    if include_identity:
        details["include_identity"] = True
        details["purpose"] = purpose.value if purpose else None
        details["purpose_text"] = purpose_text
    audit.record(
        db,
        AuditAction.export,
        p.actor(project.id),
        project_id=project.id,
        fields_read=IDENTITY_COLS if include_identity else None,
        details=details,
    )
    return export_svc.encode(cols, rows, fmt, f"{dataset.value}-{project.code}")
