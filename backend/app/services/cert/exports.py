"""Phase 4 certification register exports (spec 4-third-party-cert §8.4, capability 123).

Rows come from the same visibility-scoped list services the registers use, so an export never
shows more than the caller's register. Person names only with capability 46 (otherwise worker_no
only, AC111). ID numbers, scans, the medical flag, ban reasons and verification-failure details are
never exported. blacklist_register: HSE Manager and HSE Officers (decision 8). Every export
writes an `export` audit entry with row count, columns and filters."""

import uuid
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.cert_enums import (
    BlacklistSubject,
    CertificateStatus,
    DefectStatus,
    EquipmentDeploymentStatus,
    ScaffoldStatus,
    ServiceStatus,
)
from app.core.enums import AuditAction, Capability, ExportDataset, ExportFormat
from app.core.errors import validation_error
from app.models import Project
from app.services import audit, projects
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.cert import bans
from app.services.cert import defects as defect_svc
from app.services.cert import deployments as dep_svc
from app.services.cert import equipment as eq_svc
from app.services.cert import equipment_certs as ec_svc
from app.services.cert import imports as imp_svc
from app.services.cert import personnel as pc_svc
from app.services.cert import scaffolds as sc_svc
from app.services.cert import tpis as tpi_svc
from app.services.cert import verification as vf_svc
from app.services.permissions import Principal, forbidden_error

C = Capability
D = ExportDataset
MAX_ROWS = 50_000
PAGE = 500
DATASETS = frozenset(
    {
        D.tpis,
        D.equipment,
        D.equipment_deployments,
        D.equipment_certificates,
        D.scaffolds,
        D.personnel_certificates,
        D.cert_verifications,
        D.equipment_defects,
        D.blacklist_register,
        D.cert_imports,
    }
)
Rows = tuple[list[str], list[list[Any]]]


def _v(x: Any) -> Any:
    if x is None:
        return ""
    return getattr(x, "value", x)


def _join(xs: Any) -> str:
    return ";".join(str(_v(x)) for x in xs or [])


def _all(fetch: Callable[[int, int], Any]) -> list[Any]:
    out: list[Any] = []
    page = 1
    while len(out) < MAX_ROWS:
        res = fetch(page, PAGE)
        out.extend(res.items)
        if len(res.items) < PAGE or len(out) >= res.total:
            break
        page += 1
    return out[:MAX_ROWS]


def _parse(enum: Any, status: str | None) -> list[Any] | None:
    if not status:
        return None
    try:
        return [enum(s.strip()) for s in status.split(",") if s.strip()]
    except ValueError as exc:
        raise validation_error("status", "Unknown status for this register.") from exc


def _user(u: Any, names: bool) -> str:
    if u is None or not names:
        return ""
    return str(u.full_name_en)


def _lims(items: Sequence[Any]) -> str:
    return ";".join(f"{_v(x.code)}:{x.value}" if x.value is not None else _v(x.code) for x in items)


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, names: bool) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.names = names


def _tpis(c: _Ctx, status: str | None, q: str | None) -> Rows:
    from app.core.cert_enums import TpiStatus  # noqa: PLC0415

    sts = _parse(TpiStatus, status)
    items = _all(
        lambda pg, ps: tpi_svc.list_tpis(
            c.db, c.p, pg, ps, q=q, statuses=sts, project_id=c.project.id
        )
    )
    cols = [
        "tpi_code", "legal_name_en", "legal_name_ar", "kinds", "country", "status",
        "accepted_for_use", "accreditation_lapsed", "accreditations", "accreditation_valid_until",
    ]  # fmt: skip
    rows = [
        [
            t.tpi_code, t.legal_name_en, t.legal_name_ar, _join(t.kinds), t.country, _v(t.status),
            t.accepted_for_use, t.accreditation_lapsed,
            ";".join(f"{_v(a.accreditation_body)} {a.accreditation_no}" for a in t.accreditations),
            min((a.valid_until for a in t.accreditations), default=""),
        ]
        for t in items
    ]  # fmt: skip
    return cols, rows


def _equipment(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(ServiceStatus, status)
    items = _all(
        lambda pg, ps: eq_svc.list_items(
            c.db, c.p, pg, ps, q=q, project_id=c.project.id, statuses=sts
        )
    )
    cols = [
        "equipment_no", "category", "subtype", "manufacturer", "model", "serial_no",
        "year_of_manufacture", "owner", "rated_capacity_t", "service_status",
        "service_status_reason", "has_valid_certificate", "current_swl_t", "current_valid_until",
        "current_limitations", "open_defects",
    ]  # fmt: skip
    rows = []
    for e in items:
        line = e.current_line
        rows.append(
            [
                e.equipment_no, _v(e.category), _v(e.subtype), e.manufacturer, e.model,
                e.serial_no, e.year_of_manufacture, e.owner_short_code, e.rated_capacity_t,
                _v(e.service_status), _v(e.service_status_reason), e.has_valid_certificate,
                line.swl_t if line else "",
                line.line.valid_until if line else "",
                _lims(line.limitations) if line else "",
                ";".join(d.defect_no for d in e.open_defects),
            ]
        )  # fmt: skip
    return cols, rows


def _deployments(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(EquipmentDeploymentStatus, status)
    items = _all(
        lambda pg, ps: dep_svc.list_deployments(c.db, c.p, c.project.id, pg, ps, q=q, statuses=sts)
    )
    cols = [
        "deployment_no", "tag", "equipment_no", "category", "contractor", "sites", "zone",
        "planned_arrival_on", "approved_at", "arrived_at", "arrival_inspection_result", "status",
        "demobilised_on", "usable", "not_usable_reason",
    ]  # fmt: skip
    rows = [
        [
            d.deployment_no, d.tag, d.equipment.equipment_no, _v(d.equipment.category),
            d.engagement.short_code, ";".join(s.code for s in d.sites),
            d.zone.code if d.zone else "", d.planned_arrival_on, d.approved_at, d.arrived_at,
            _v(d.arrival_inspection.result) if d.arrival_inspection else "", _v(d.status),
            d.demobilised_on, d.usable, d.not_usable_reason,
        ]
        for d in items
    ]  # fmt: skip
    return cols, rows


def _eq_certs(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(CertificateStatus, status)
    items = _all(
        lambda pg, ps: ec_svc.list_certificates(c.db, c.p, c.project.id, pg, ps, q=q, statuses=sts)
    )
    cols = [
        "cert_no", "tpi_code", "inspection_type", "inspected_on", "issued_on", "printed_next_due",
        "equipment_no", "serial_as_printed", "result", "swl_t", "limitations", "line_valid_until",
        "limiting_factor", "in_force", "status", "status_reason", "verification_status",
        "verification_due_on", "source", "submitted_at", "reviewed_at",
    ]  # fmt: skip
    if c.names:
        cols += ["inspector_name", "submitted_by", "reviewed_by"]
    rows = []
    for e in items:
        for ln in e.lines or [None]:
            row = [
                e.cert_no, e.tpi.tpi_code, _v(e.inspection_type), e.inspected_on, e.issued_on,
                e.printed_next_due,
                ln.equipment.equipment_no if ln else "", ln.serial_as_printed if ln else "",
                _v(ln.result) if ln else "", ln.swl_t if ln else "",
                _lims(ln.limitations) if ln else "", ln.validity.valid_until if ln else "",
                _v(ln.validity.limiting_factor) if ln else "", ln.validity.in_force if ln else "",
                _v(e.status), _v(e.status_reason), _v(e.verification_status),
                e.verification_due_on, _v(e.source), e.submitted_at, e.reviewed_at,
            ]  # fmt: skip
            if c.names:
                row += [e.inspector_name, _user(e.submitted_by, True), _user(e.reviewed_by, True)]
            rows.append(row)
    return cols, rows


def _scaffolds(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(ScaffoldStatus, status)
    items = _all(
        lambda pg, ps: sc_svc.list_scaffolds(c.db, c.p, c.project.id, pg, ps, q=q, statuses=sts)
    )
    cols = [
        "scaffold_no", "tag", "contractor", "zone", "location", "level", "scaffold_type",
        "height_m", "load_class", "design_ref", "design_required", "status", "tag_status",
        "tag_valid_until", "usable_today", "restrictions_en", "inspection_required_reason",
        "last_inspected_at",
    ]  # fmt: skip
    rows = [
        [
            s.scaffold_no, s.tag, s.engagement.short_code, s.zone.code, s.location_desc,
            s.level_code, _v(s.scaffold_type), s.height_m, s.load_class, s.design_ref,
            s.design_required, _v(s.status), _v(s.tag_status), s.tag_valid_until, s.usable_today,
            s.restrictions_en, _v(s.inspection_required_reason),
            s.last_inspection.inspected_at if s.last_inspection else "",
        ]
        for s in items
    ]  # fmt: skip
    return cols, rows


def _personnel(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(CertificateStatus, status)
    items = _all(
        lambda pg, ps: pc_svc.list_certificates(c.db, c.p, c.project.id, pg, ps, q=q, statuses=sts)
    )
    cols = ["record_no", "worker_no"]
    if c.names:
        cols += ["worker_name_en", "worker_name_ar"]
    cols += [
        "contractor", "cert_type", "tpi_code", "cert_no", "issued_on", "printed_expiry",
        "valid_until", "limiting_factor", "in_force", "scope_categories", "max_capacity_t",
        "level", "id_match_result", "name_match", "status", "verification_status",
        "verification_due_on", "source",
    ]  # fmt: skip
    rows = []
    for x in items:
        row: list[Any] = [x.record_no, x.worker.worker_no]
        if c.names:
            row += [x.worker.full_name_en or "", x.worker.full_name_ar or ""]
        row += [
            x.engagement.short_code if x.engagement else "", x.cert_type, x.tpi.tpi_code,
            x.cert_no, x.issued_on, x.printed_expiry, x.validity.valid_until,
            _v(x.validity.limiting_factor), x.validity.in_force, _join(x.scope_categories),
            x.max_capacity_t, _v(x.level), _v(x.id_match_result), _v(x.name_match),
            _v(x.status), _v(x.verification_status), x.verification_due_on, _v(x.source),
        ]  # fmt: skip
        rows.append(row)
    return cols, rows


def _verifications(c: _Ctx, status: str | None, q: str | None) -> Rows:
    from app.core.cert_enums import VerificationOutcome  # noqa: PLC0415

    outs = _parse(VerificationOutcome, status)
    items = _all(lambda pg, ps: vf_svc.log(c.db, c.p, c.project.id, pg, ps, outcomes=outs))
    # Failure details (differences, free text) are never exported (§8.4).
    cols = [
        "cert_kind", "cert_no", "holder_or_item", "method", "channel_used", "outcome",
        "reference", "performed_at", "counts_as_verification", "verification_status_after",
    ]  # fmt: skip
    if c.names:
        cols.append("performed_by")
    rows = []
    for v in items:
        row = [
            _v(v.cert_kind), v.cert_no, v.holder_or_item_ref, _v(v.method), v.channel_used,
            _v(v.outcome), v.reference, v.performed_at, v.counts_as_verification,
            _v(v.verification_status_after),
        ]  # fmt: skip
        if c.names:
            row.append(_user(v.performed_by, True))
        rows.append(row)
    return cols, rows


def _defects(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(DefectStatus, status)
    items = _all(
        lambda pg, ps: defect_svc.list_defects(c.db, c.p, c.project.id, pg, ps, statuses=sts)
    )
    cols = [
        "defect_no", "category", "item", "tag", "contractor", "source", "source_ref",
        "description_en", "raised_at", "physical_tag_applied", "due_date", "days_left",
        "overdue", "status", "rectified_at", "closed_at",
    ]  # fmt: skip
    rows = [
        [
            d.defect_no, _v(d.category),
            d.equipment.equipment_no if d.equipment else (d.scaffold.scaffold_no if d.scaffold
                                                          else ""),
            d.tag, d.engagement.short_code if d.engagement else "", _v(d.source), d.source_ref,
            d.description_en, d.raised_at, d.physical_tag_applied, d.due_date, d.days_left,
            d.overdue, _v(d.status), d.rectification.rectified_at if d.rectification else "",
            d.closure.closed_at if d.closure else "",
        ]
        for d in items
        if not q or q.lower() in f"{d.defect_no} {d.tag or ''}".lower()
    ]  # fmt: skip
    return cols, rows


def _blacklist(c: _Ctx, status: str | None, q: str | None) -> Rows:
    if not bans.hse_viewer(c.p):
        raise forbidden_error("The blacklist and ban register export is for HSE staff only.")
    reg = bans.register(c.db, c.p, project_id=c.project.id, active_only=status != "all")
    # Reasons are never exported (§8.4).
    cols = ["subject", "ref", "label_en", "label_ar", "from_date", "review_due_on", "status"]
    rows = []
    for r in reg.items:
        show = c.names or r.subject != BlacklistSubject.person
        rows.append(
            [
                _v(r.subject),
                r.ref,
                r.label_en if show else "",
                r.label_ar if show else "",
                r.from_date,
                r.review_due_on,
                r.status,
            ]
        )
    return cols, rows


def _imports(c: _Ctx, status: str | None, q: str | None) -> Rows:
    from app.core.cert_enums import CertImportStatus  # noqa: PLC0415

    sts = _parse(CertImportStatus, status)
    items = _all(
        lambda pg, ps: imp_svc.list_batches(
            c.db, c.p, c.project.id, pg, ps, sts[0] if sts else None
        )
    )
    cols = [
        "created_at", "template", "source", "tpi_code", "file_name", "status", "rows_total",
        "rows_ok", "rows_warning", "rows_error", "certificates_created", "committed_at",
    ]  # fmt: skip
    if c.names:
        cols.append("uploaded_by")
    rows = []
    for b in items:
        k = b.counts
        row = [
            b.created_at, _v(b.template), _v(b.source), b.tpi_code, b.file_name, _v(b.status),
            k.rows_total, k.rows_ok, k.rows_warning, k.rows_error, k.certificates_created,
            b.committed_at,
        ]  # fmt: skip
        if c.names:
            row.append(_user(b.uploaded_by, True))
        rows.append(row)
    return cols, rows


BUILDERS: dict[ExportDataset, Callable[[_Ctx, str | None, str | None], Rows]] = {
    D.tpis: _tpis,
    D.equipment: _equipment,
    D.equipment_deployments: _deployments,
    D.equipment_certificates: _eq_certs,
    D.scaffolds: _scaffolds,
    D.personnel_certificates: _personnel,
    D.cert_verifications: _verifications,
    D.equipment_defects: _defects,
    D.blacklist_register: _blacklist,
    D.cert_imports: _imports,
}


def export(
    db: Session,
    p: Principal,
    dataset: ExportDataset,
    fmt: ExportFormat,
    project_id: uuid.UUID | None,
    status: str | None,
    q: str | None,
) -> tuple[bytes, str, str]:
    if project_id is None:
        raise validation_error("project_id", "Choose a project to export.")
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.export_cert) is None:
        raise forbidden_error("Exporting certification registers needs capability 123.")
    c = _Ctx(db, p, project, acommon.can_see_names(p, project.id))
    cols, rows = BUILDERS[dataset](c, status, q)
    audit.record(
        db,
        AuditAction.export,
        p.actor(project.id),
        project_id=project.id,
        details={
            "dataset": dataset.value,
            "format": fmt.value,
            "row_count": len(rows),
            "columns": cols,
            "filters": {k: v for k, v in {"status": status, "q": q}.items() if v},
        },
    )
    return export_svc.encode(cols, rows, fmt, dataset.value)
