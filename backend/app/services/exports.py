"""CSV / Excel exports of lists (spec §5.8 rule 49, capability 18)."""

import csv
import io
import uuid
from enum import Enum
from typing import Any

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    ExportDataset,
    ExportFormat,
    Language,
    ProjectStatus,
    SiteStatus,
    UserStatus,
    ZoneStatus,
)
from app.core.errors import validation_error
from app.services import audit, audit_read, contractors, org, projects, users
from app.services.permissions import Principal, forbidden_error

MAX_ROWS = 50_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _status(enum_cls: type[Enum], value: str | None) -> Any:
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise validation_error("status", f"Unknown status {value!r} for this list.") from exc


def _cell(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if hasattr(v, "tzinfo") and getattr(v, "tzinfo", None) is not None:
        return v.isoformat()
    return v


def _rows(
    db: Session,
    p: Principal,
    dataset: ExportDataset,
    project_id: uuid.UUID | None,
    status: str | None,
    q: str | None,
) -> tuple[list[str], list[list[Any]]]:
    def need_project() -> uuid.UUID:
        if project_id is None:
            raise validation_error("project_id", "project_id is required for this list.")
        projects.get_visible(db, p, project_id)
        if p.grant(project_id, Capability.export_lists) is None:
            raise forbidden_error()
        return project_id

    if dataset == ExportDataset.projects:
        stmt = projects.list_query(
            p, [_status(ProjectStatus, status)] if status else None, None, q, "code", Language.en
        )
        cols = [
            "code",
            "name_en",
            "name_ar",
            "project_type",
            "status",
            "city",
            "client_name_en",
            "client_name_ar",
            "start_date",
            "planned_end_date",
            "airport_icao",
        ]
        return cols, [
            [_cell(getattr(r, c)) for c in cols] for r in db.scalars(stmt.limit(MAX_ROWS))
        ]
    if dataset == ExportDataset.sites:
        pid = need_project()
        stmt_s = org.list_sites_query(db, p, pid, _status(SiteStatus, status), None, q)
        cols = ["code", "name_en", "name_ar", "site_side", "status", "gps_lat", "gps_lng"]
        return cols, [
            [_cell(getattr(r, c)) for c in cols] for r in db.scalars(stmt_s.limit(MAX_ROWS))
        ]
    if dataset == ExportDataset.zones:
        pid = need_project()
        stmt_z = org.list_zones_query(db, p, pid, status=_status(ZoneStatus, status), q=q)
        cols = [
            "code",
            "name_en",
            "name_ar",
            "zone_type",
            "status",
            "airside_area",
            "in_movement_area",
            "runway_ref",
            "security_restricted_area",
            "notam_required_for_works",
            "ols_height_limit_m_amsl",
            "max_equipment_height_m_agl",
            "escort_required",
            "adp_required",
            "fod_control_required",
            "works_safety_plan_ref",
        ]
        rows = [
            [str(z.site_id), *[_cell(getattr(z, c)) for c in cols]]
            for z in db.scalars(stmt_z.limit(MAX_ROWS))
        ]
        return ["site_id", *cols], rows
    if dataset == ExportDataset.engagements:
        pid = need_project()
        stmt_e = contractors.list_engagements_query(db, p, pid)
        cols = [
            "contractor",
            "tier",
            "parent_engagement_id",
            "scope_of_work_en",
            "scope_of_work_ar",
            "mobilisation_date",
            "demobilisation_date",
            "parent_blacklisted",
        ]
        out = []
        for e in db.scalars(stmt_e.limit(MAX_ROWS)).unique():
            out.append([e.contractor.short_code, *[_cell(getattr(e, c)) for c in cols[1:]]])
        return cols, out
    if not p.has_any(Capability.export_lists):
        raise forbidden_error()
    if dataset == ExportDataset.contractors:
        stmt_c = contractors.list_query(
            db,
            p,
            [_status(ContractorStatus, status)] if status else None,
            q=q,
            project_id=project_id,
        )
        items = list(db.scalars(stmt_c.limit(MAX_ROWS)))
        base = [
            "short_code",
            "legal_name_en",
            "legal_name_ar",
            "cr_number",
            "cr_expiry_date",
            "vat_number",
            "contractor_category",
            "status",
        ]
        with_contacts = p.has_any(Capability.contractor_view_contacts)
        cols = base + (list(contractors.CONTACT_FIELDS) if with_contacts else [])
        allowed = (
            contractors.contact_visible_ids(db, p, [c.id for c in items])
            if with_contacts
            else set()
        )
        out = []
        for c in items:
            row = [_cell(getattr(c, f)) for f in base]
            if with_contacts:
                row += [
                    getattr(c, f) if c.id in allowed else "" for f in contractors.CONTACT_FIELDS
                ]
            out.append(row)
        return cols, out
    if dataset == ExportDataset.users:
        stmt_u = users.list_query(
            db,
            p,
            project_id=project_id,
            statuses=[_status(UserStatus, status)] if status else None,
            q=q,
        )
        items_u = list(db.scalars(stmt_u.limit(MAX_ROWS)))
        with_contacts = p.has_any(Capability.user_view_contacts)
        cols = ["full_name_en", "full_name_ar", "employer_type", "job_title", "status", "roles"]
        if with_contacts:
            cols += ["email", "mobile"]
        out = []
        for u in items_u:
            roles = sorted({a.role.value for a in u.assignments if a.is_active_on(p.today)})
            row = [
                u.full_name_en,
                u.full_name_ar,
                u.employer_type.value,
                u.job_title,
                u.status.value,
                ", ".join(roles),
            ]
            if with_contacts:
                show = users._can(db, p, Capability.user_view_contacts, u)
                row += [u.email if show else "", (u.mobile or "") if show else ""]
            out.append(row)
        return cols, out
    # audit log
    stmt_a = audit_read.audit_query(db, p, project_id=project_id)
    entries = list(db.scalars(stmt_a.limit(MAX_ROWS)))
    cols = [
        "seq",
        "occurred_at",
        "actor_user_id",
        "actor_role",
        "action",
        "entity_type",
        "entity_id",
        "project_id",
        "result",
        "before",
        "after",
        "details",
    ]
    if p.is_manager:
        cols += ["ip_address", "user_agent"]
    return cols, [
        [
            _cell(getattr(e, c)) if not isinstance(getattr(e, c), dict) else str(getattr(e, c))
            for c in cols
        ]
        for e in entries
    ]


def export(
    db: Session,
    p: Principal,
    dataset: ExportDataset,
    fmt: ExportFormat,
    project_id: uuid.UUID | None,
    status: str | None,
    q: str | None,
) -> tuple[bytes, str, str]:
    """Returns (content, media type, filename)."""
    cols, rows = _rows(db, p, dataset, project_id, status, q)
    audit.record(
        db,
        AuditAction.export,
        p.actor(project_id),
        entity_type=EntityType.audit_log if dataset == ExportDataset.audit_log else None,
        project_id=project_id,
        details={
            "dataset": dataset.value,
            "format": fmt.value,
            "row_count": len(rows),
            "columns": cols,
            "filters": {
                k: v for k, v in {"project_id": project_id, "status": status, "q": q}.items() if v
            },
        },
    )
    name = f"{dataset.value}.{fmt.value}"
    if fmt == ExportFormat.csv:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        writer.writerows(rows)
        return ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", name
    wb = Workbook()
    ws = wb.active
    ws.title = dataset.value
    ws.append(cols)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), XLSX, name
