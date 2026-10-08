"""Phase 3 PTW register exports (spec 3-ptw, capability 104).

Rows are limited to the caller's capability-104 scope (sites / contractor tree) inside one
project. Person names and worker_no only with capability 46 (P3-2; otherwise those columns are left
out).
Signatures, signature attachments, gas readings JSON and medical data are never exported. Every
export writes an `export` audit entry with row count, columns and filters."""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import Select, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, ExportDataset, ExportFormat
from app.core.errors import validation_error
from app.models import (
    GasDetector,
    GasTest,
    IsolationCertificate,
    Jsa,
    Lock,
    Permit,
    PermitCrew,
    PermitSuspension,
    Project,
    PtwAppointment,
    PtwAudit,
    SimopsConflict,
    User,
    Worker,
)
from app.services import audit, projects
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
D = ExportDataset
MAX_ROWS = 50_000
DATASETS = frozenset(
    {
        D.permits, D.permit_suspensions, D.gas_tests, D.gas_detectors, D.isolations, D.locks,
        D.ptw_appointments, D.jsa_templates, D.simops_conflicts, D.ptw_audits,
    }
)  # fmt: skip
Rows = tuple[list[str], list[list[Any]]]


def _v(x: Any) -> Any:
    if x is None:
        return ""
    return getattr(x, "value", x)


def _join(xs: Any) -> str:
    return ";".join(str(_v(x)) for x in xs or [])


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, g: Grant, names: bool) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.g = g
        self.names = names
        self.refs = Refs(db)
        self._permits: dict[uuid.UUID, Permit | None] = {}

    def eng_clause(self, col: Any) -> Any:
        if self.g.engagement_ids is None:
            return true()
        return col.in_(list(self.g.engagement_ids)) if self.g.engagement_ids else false()

    def site_clause(self, col: Any) -> Any:
        if self.g.site_ids is None:
            return true()
        return col.in_(list(self.g.site_ids)) if self.g.site_ids else false()

    def permit_scope(self) -> Any:
        return select(Permit.id).where(
            Permit.project_id == self.project.id,
            self.site_clause(Permit.site_id),
            self.eng_clause(Permit.engagement_id),
        )

    def eng(self, eid: uuid.UUID | None) -> str:
        e = self.refs.eng(eid)
        return e.short_code if e else ""

    def site(self, sid: uuid.UUID | None) -> str:
        return self.refs.site(sid).code if sid else ""

    def zones(self, zids: list[uuid.UUID] | None) -> str:
        out = []
        for z in zids or []:
            zone = self.refs.zone(z)
            out.append(zone.code if zone else "")
        return ";".join(out)

    def permit_no(self, pid: uuid.UUID | None) -> str:
        if pid is None:
            return ""
        if pid not in self._permits:
            self._permits[pid] = self.db.get(Permit, pid)
        x = self._permits[pid]
        return x.permit_no if x else ""

    def user(self, uid: uuid.UUID | None) -> str:
        u = self.db.get(User, uid) if uid else None
        return u.full_name_en if u else ""

    def worker_no(self, wid: uuid.UUID | None) -> str:
        w = self.db.get(Worker, wid) if wid else None
        return w.worker_no if w else ""

    def worker_name(self, wid: uuid.UUID | None) -> str:
        w = self.db.get(Worker, wid) if wid else None
        return w.full_name_en if w else ""

    def scalars(self, stmt: Select[Any]) -> list[Any]:
        return list(self.db.scalars(stmt.limit(MAX_ROWS)))


def _status(stmt: Any, col: Any, status: str | None) -> Any:
    return stmt.where(col == status) if status else stmt


def _permits(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = select(Permit).where(Permit.id.in_(c.permit_scope())).order_by(Permit.permit_no)
    stmt = _status(stmt, Permit.status, status)
    if q:
        stmt = stmt.where(or_(Permit.permit_no.ilike(f"%{q}%"), Permit.title.ilike(f"%{q}%")))
    cols = [
        "permit_no", "title", "work_types", "primary_type", "high_risk", "critical_lift",
        "status", "status_reason", "site", "zones", "contractor", "valid_from", "valid_to",
        "first_issued_at", "closed_at", "crew_count",
    ]  # fmt: skip
    if c.names:
        cols += ["receiver", "area_authority", "issuer"]
    rows = []
    for x in c.scalars(stmt):
        crew = c.db.scalars(
            select(PermitCrew.id).where(
                PermitCrew.permit_id == x.id, PermitCrew.removed_at.is_(None)
            )
        ).all()
        row = [
            x.permit_no, x.title, _join(x.work_types), _v(x.primary_type), x.high_risk,
            x.critical_lift, _v(x.status), _v(x.status_reason), c.site(x.site_id),
            c.zones(x.zone_ids), c.eng(x.engagement_id), x.valid_from_at, x.valid_to_at,
            x.first_issued_at, x.closed_at, len(crew),
        ]  # fmt: skip
        if c.names:
            row += [
                c.user(x.receiver_user_id), c.user(x.area_authority_user_id),
                c.user(x.issuer_user_id),
            ]  # fmt: skip
        rows.append(row)
    return cols, rows


def _suspensions(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(PermitSuspension)
        .where(
            PermitSuspension.project_id == c.project.id,
            PermitSuspension.permit_id.in_(c.permit_scope()),
        )
        .order_by(PermitSuspension.suspended_at)
    )
    stmt = _status(stmt, PermitSuspension.reason, status)
    cols = ["permit_no", "reason", "routine", "suspended_at", "resumed_at", "detail"]
    rows = [
        [c.permit_no(s.permit_id), _v(s.reason), s.routine, s.suspended_at, s.resumed_at,
         s.detail or ""]
        for s in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _gas_tests(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(GasTest)
        .where(GasTest.project_id == c.project.id, GasTest.permit_id.in_(c.permit_scope()))
        .order_by(GasTest.tested_at)
    )
    stmt = _status(stmt, GasTest.result, status)
    cols = [
        "test_no", "permit_no", "test_type", "tested_at", "result", "fail_codes", "detector_no",
        "superseded",
    ]  # fmt: skip
    if c.names:
        cols.append("tester_appointment_no")  # gas tester identity is personal (P3-1)
    rows = []
    for t in c.scalars(stmt):
        d = c.db.get(GasDetector, t.detector_id) if t.detector_id else None
        a = c.db.get(PtwAppointment, t.tester_appointment_id) if t.tester_appointment_id else None
        rows.append(
            [t.test_no, c.permit_no(t.permit_id), _v(t.test_type), t.tested_at, _v(t.result),
             _join(t.fail_codes), d.detector_no if d else "", t.superseded]
            + ([a.appointment_no if a else ""] if c.names else [])
        )  # fmt: skip
    return cols, rows


def _detectors(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(GasDetector)
        .where(GasDetector.project_id == c.project.id, c.eng_clause(GasDetector.engagement_id))
        .order_by(GasDetector.detector_no)
    )
    stmt = _status(stmt, GasDetector.status, status)
    cols = [
        "detector_no", "contractor", "make_model", "serial", "sensors", "calibrated_on",
        "calibration_due_on", "status",
    ]  # fmt: skip
    rows = [
        [d.detector_no, c.eng(d.engagement_id), d.make_model, d.serial, _join(d.sensors),
         d.calibrated_on, d.calibration_due_on, _v(d.status)]
        for d in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _isolations(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(IsolationCertificate)
        .where(
            IsolationCertificate.project_id == c.project.id,
            c.eng_clause(IsolationCertificate.engagement_id),
        )
        .order_by(IsolationCertificate.iso_no)
    )
    stmt = _status(stmt, IsolationCertificate.status, status)
    cols = [
        "iso_no", "contractor", "equipment_desc", "energy_types", "hv", "status", "isolated_at",
        "verified_at", "deisolated_at",
    ]  # fmt: skip
    if c.names:
        cols.append("isolation_authority")
    rows = []
    for i in c.scalars(stmt):
        row = [
            i.iso_no, c.eng(i.engagement_id), i.equipment_desc, _join(i.energy_types), i.hv,
            _v(i.status), i.isolated_at, i.verified_at, i.deisolated_at,
        ]  # fmt: skip
        if c.names:
            row.append(c.user(i.isolation_authority_user_id))
        rows.append(row)
    return cols, rows


def _locks(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = select(Lock).where(Lock.project_id == c.project.id).order_by(Lock.lock_no)
    stmt = _status(stmt, Lock.status, status)
    cols = ["lock_no", "lock_type", "status", "applied_on"]
    if c.names:
        cols += ["holder_worker_no", "holder_name"]
    rows = []
    for lk in c.scalars(stmt):
        row = [
            lk.lock_no, _v(lk.lock_type), _v(lk.status), lk.applied_on,
        ]  # fmt: skip
        if c.names:
            row += [c.worker_no(lk.holder_worker_id), c.worker_name(lk.holder_worker_id)]
        rows.append(row)
    return cols, rows


def _appointments(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(PtwAppointment)
        .where(PtwAppointment.project_id == c.project.id)
        .order_by(PtwAppointment.appointment_no)
    )
    if c.g.site_ids is not None:
        stmt = stmt.where(PtwAppointment.site_ids.overlap(list(c.g.site_ids)))
    stmt = _status(stmt, PtwAppointment.status, status)
    cols = [
        "appointment_no", "function", "discipline", "permit_types", "sites", "valid_from",
        "valid_to", "status",
    ]  # fmt: skip
    if c.names:
        cols += ["holder_worker_no", "holder_name"]
    rows = []
    for a in c.scalars(stmt):
        row = [
            a.appointment_no, _v(a.function), _v(a.discipline), _join(a.permit_types),
            ";".join(c.site(s) for s in a.site_ids or []), a.valid_from, a.valid_to,
            _v(a.status),
        ]  # fmt: skip
        if c.names:
            row += [
                c.worker_no(a.holder_worker_id),
                c.user(a.holder_user_id) if a.holder_user_id else c.worker_name(a.holder_worker_id),
            ]
        rows.append(row)
    return cols, rows


def _jsa_templates(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(Jsa)
        .where(Jsa.project_id == c.project.id, Jsa.is_template.is_(True))
        .order_by(Jsa.jsa_no)
    )
    stmt = _status(stmt, Jsa.status, status)
    cols = ["jsa_no", "revision", "title_en", "title_ar", "work_types", "status", "review_due_on"]
    rows = [
        [j.jsa_no, j.revision, j.title_en, j.title_ar or "", _join(j.work_types), _v(j.status),
         j.review_due_on]
        for j in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _conflicts(c: _Ctx, status: str | None, q: str | None) -> Rows:
    scope = c.permit_scope()
    stmt = (
        select(SimopsConflict)
        .where(
            SimopsConflict.project_id == c.project.id,
            SimopsConflict.permit_a_id.in_(scope),
            SimopsConflict.permit_b_id.in_(scope),
        )
        .order_by(SimopsConflict.conflict_no)
    )
    stmt = _status(stmt, SimopsConflict.status, status)
    cols = [
        "conflict_no", "permit_a", "permit_b", "rule_code", "result", "status", "distance_m",
        "overlap_from", "overlap_to", "detected_at", "resolved_at",
    ]  # fmt: skip
    rows = [
        [s.conflict_no, c.permit_no(s.permit_a_id), c.permit_no(s.permit_b_id), s.rule_code,
         _v(s.result), _v(s.status), s.distance_m, s.overlap_from, s.overlap_to, s.detected_at,
         s.resolved_at]
        for s in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _audits(c: _Ctx, status: str | None, q: str | None) -> Rows:
    stmt = (
        select(PtwAudit)
        .where(
            PtwAudit.project_id == c.project.id,
            c.site_clause(PtwAudit.site_id),
            or_(PtwAudit.engagement_id.is_(None), c.eng_clause(PtwAudit.engagement_id)),
        )
        .order_by(PtwAudit.audit_no)
    )
    stmt = _status(stmt, PtwAudit.status, status)
    cols = [
        "audit_no", "audit_type", "permit_no", "site", "contractor", "audited_at",
        "applicable_count", "compliant_count", "score_pct", "critical_count", "permit_suspended",
        "status", "completed_at",
    ]  # fmt: skip
    if c.names:
        cols.append("auditor")
    rows = []
    for a in c.scalars(stmt):
        row = [
            a.audit_no, _v(a.audit_type), c.permit_no(a.permit_id), c.site(a.site_id),
            c.eng(a.engagement_id), a.audited_at, a.applicable_count, a.compliant_count,
            a.score_pct, a.critical_count, a.permit_suspended, _v(a.status), a.completed_at,
        ]  # fmt: skip
        if c.names:
            row.append(c.user(a.auditor_user_id))
        rows.append(row)
    return cols, rows


BUILDERS: dict[ExportDataset, Callable[[_Ctx, str | None, str | None], Rows]] = {
    D.permits: _permits,
    D.permit_suspensions: _suspensions,
    D.gas_tests: _gas_tests,
    D.gas_detectors: _detectors,
    D.isolations: _isolations,
    D.locks: _locks,
    D.ptw_appointments: _appointments,
    D.jsa_templates: _jsa_templates,
    D.simops_conflicts: _conflicts,
    D.ptw_audits: _audits,
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
    g = p.grant(project.id, C.export_ptw)
    if g is None:
        raise forbidden_error("Exporting PTW registers needs capability 104.")
    c = _Ctx(db, p, project, g, acommon.can_see_names(p, project.id))
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
