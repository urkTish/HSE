"""Phase 2 register exports (spec 2-access-permits P2-10, capabilities 76/78/79).

Rows are limited to the caller's capability-78 scope (sites / contractor tree). IDs are masked;
full ID numbers only with `include_identity`, capability 79 and a stated purpose (pass_office,
authority_request, legal, other + text) recorded in the `export` audit entry. Photos, ID copies
and background-check data are never exported. Worker names only with capability 46. The gate log
also needs capability 76. Gate logs are not a time-and-attendance export (P2-8)."""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import Select, and_, false, or_, select, true
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.enums import AuditAction, Capability, ExportDataset, ExportFormat
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import ExportPurpose
from app.models import (
    Adp,
    AirportPass,
    Avp,
    Deployment,
    Gate,
    GateCheck,
    InductionCourse,
    InductionRecord,
    NotamRequest,
    ObstacleClearance,
    Offence,
    OpsEvent,
    PassApplication,
    Project,
    Vehicle,
    Wap,
    WapCrew,
    Worker,
)
from app.services import audit, projects
from app.services import exports as export_svc
from app.services.access import common, workers
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
D = ExportDataset
MAX_ROWS = 50_000
ACCESS_PURPOSES = frozenset(
    {ExportPurpose.pass_office, ExportPurpose.authority_request, ExportPurpose.legal,
     ExportPurpose.other}
)  # fmt: skip
IDENTITY_DATASETS = frozenset(
    {D.workers, D.deployments, D.inductions, D.pass_applications, D.airport_passes, D.adps}
)
DATASETS = frozenset(
    {
        D.workers, D.deployments, D.inductions, D.pass_applications, D.airport_passes, D.adps,
        D.airside_offences, D.vehicles, D.avps, D.waps, D.notam_requests, D.obstacle_clearances,
        D.ops_events, D.gate_log,
    }
)  # fmt: skip


class _Ctx:
    def __init__(
        self, db: Session, p: Principal, project: Project, g: Grant, names: bool, ident: bool
    ) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.g = g
        self.names = names
        self.ident = ident
        self.refs = Refs(db)
        self._workers: dict[uuid.UUID, Worker | None] = {}

    def eng_clause(self, col: Any) -> Any:
        if self.g.engagement_ids is None:
            return true()
        return col.in_(list(self.g.engagement_ids)) if self.g.engagement_ids else false()

    def site_clause(self, col: Any) -> Any:
        if self.g.site_ids is None:
            return true()
        return col.in_(list(self.g.site_ids)) if self.g.site_ids else false()

    def eng(self, eid: uuid.UUID | None) -> str:
        e = self.refs.eng(eid)
        return e.short_code if e else ""

    def zone(self, zid: uuid.UUID | None) -> str:
        z = self.refs.zone(zid)
        return z.code if z else ""

    def zones(self, zids: list[uuid.UUID] | None) -> str:
        return ";".join(self.zone(z) for z in zids or [])

    def site(self, sid: uuid.UUID | None) -> str:
        return self.refs.site(sid).code if sid else ""

    def worker(self, wid: uuid.UUID | None) -> Worker | None:
        if wid is None:
            return None
        if wid not in self._workers:
            self._workers[wid] = self.db.get(Worker, wid)
        return self._workers[wid]

    def person_cols(self) -> list[str]:
        cols = ["worker_no"]
        if self.names:
            cols += ["full_name_en", "full_name_ar"]
        cols += ["id_type", "id_number_masked"]
        if self.ident:
            cols.append("id_number")
        return cols

    def person(self, wid: uuid.UUID | None) -> list[Any]:
        w = self.worker(wid)
        if w is None:
            return [""] * len(self.person_cols())
        out: list[Any] = [w.worker_no]
        if self.names:
            out += [w.full_name_en, w.full_name_ar]
        out += [w.id_type.value if w.id_type else "", w.id_number_masked or ""]
        if self.ident:
            out.append(crypto.decrypt(w.id_number_enc) if w.id_number_enc else "")
        return out

    def scalars(self, stmt: Select[Any]) -> list[Any]:
        return list(self.db.scalars(stmt.limit(MAX_ROWS)))


def _status(stmt: Any, col: Any, status: str | None) -> Any:
    return stmt.where(col == status) if status else stmt


def _dep_scope(c: _Ctx) -> Any:
    return and_(
        Deployment.project_id == c.project.id,
        workers.dep_clause(c.p, C.export_access),
    )


def _workers(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Worker)
        .where(Worker.id.in_(select(Deployment.worker_id).where(_dep_scope(c))))
        .order_by(Worker.worker_no)
    )
    stmt = _status(stmt, Worker.status, status)
    if q:
        stmt = stmt.where(
            or_(Worker.worker_no.ilike(f"%{q}%"), Worker.search_text.ilike(f"%{q.lower()}%"))
            if c.names
            else Worker.worker_no.ilike(f"%{q}%")
        )
    cols = [
        *c.person_cols(), "person_type", "id_expiry_date", "nationality", "primary_language",
        "status",
    ]  # fmt: skip
    rows = [
        [*c.person(w.id), w.person_type.value, w.id_expiry_date, w.nationality or "",
         w.primary_language.value, w.status.value]
        for w in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _deployments(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = select(Deployment).where(_dep_scope(c)).order_by(Deployment.mobilised_on)
    stmt = _status(stmt, Deployment.status, status)
    cols = [
        *c.person_cols(), "contractor", "employee_no", "trade", "sites", "mobilised_on",
        "planned_demob_on", "demobilised_on", "status", "inducted_on",
    ]  # fmt: skip
    rows = [
        [*c.person(d.worker_id), c.eng(d.engagement_id), d.employee_no or "", d.trade.value,
         ";".join(c.site(s) for s in d.site_ids or []), d.mobilised_on, d.planned_demob_on,
         d.demobilised_on, d.status.value, d.inducted_on]
        for d in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _inductions(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(InductionRecord, InductionCourse.code)
        .join(Deployment, Deployment.id == InductionRecord.deployment_id)
        .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
        .where(_dep_scope(c))
        .order_by(InductionRecord.delivered_at)
    )
    stmt = _status(stmt, InductionRecord.status, status)
    cols = [
        "induction_no", *c.person_cols(), "contractor", "course", "course_version",
        "delivered_on", "delivery_language", "interpreter_used", "language_mismatch",
        "duration_minutes", "test_score_pct", "attempt_no", "result", "valid_until", "status",
    ]  # fmt: skip
    rows = [
        [r.induction_no, *c.person(r.worker_id), c.eng(r.engagement_id), code, r.course_version,
         r.delivered_on, r.delivery_language.value, r.interpreter_used, r.language_mismatch,
         r.duration_minutes, r.test_score_pct, r.attempt_no, r.result.value, r.valid_until,
         r.status.value]
        for r, code in c.db.execute(stmt.limit(MAX_ROWS)).all()
    ]  # fmt: skip
    return cols, rows


def _applications(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(PassApplication)
        .join(Deployment, Deployment.id == PassApplication.deployment_id)
        .where(_dep_scope(c))
        .order_by(PassApplication.year, PassApplication.seq)
    )
    stmt = _status(stmt, PassApplication.status, status)
    cols = [
        "application_no", "application_type", *c.person_cols(), "sponsor", "pass_category",
        "requested_area_codes", "requested_valid_until", "submitted_at", "lodged_at",
        "authority_ref", "decided_at", "status",
    ]  # fmt: skip
    rows = [
        [a.application_no, a.application_type.value, *c.person(a.worker_id),
         c.eng(a.sponsor_engagement_id), a.pass_category, ";".join(a.requested_area_codes),
         a.requested_valid_until, a.submitted_at, a.lodged_at, a.authority_ref or "",
         a.decided_at, a.status.value]
        for a in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _cred(o: AirportPass | Adp | Avp) -> list[Any]:
    return [
        o.effective_valid_until,
        o.limiting_factor.value if o.limiting_factor else "",
        o.validity_status.value,
        o.custody_status.value if o.custody_status else "",
        o.return_due_on,
    ]


CRED_COLS = ["effective_valid_until", "limiting_factor", "validity_status", "custody_status",
             "return_due_on"]  # fmt: skip


def _passes(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(AirportPass)
        .join(Deployment, Deployment.id == AirportPass.deployment_id)
        .where(_dep_scope(c))
        .order_by(AirportPass.issued_on)
    )
    stmt = _status(stmt, AirportPass.validity_status, status)
    cols = [
        "pass_no", *c.person_cols(), "contractor", "pass_category", "area_codes", "card_colour",
        "escorted", "issued_on", "card_expiry_date", *CRED_COLS,
    ]  # fmt: skip
    rows = [
        [ps.pass_no, *c.person(ps.worker_id), c.eng(ps.engagement_id), ps.pass_category,
         ";".join(ps.area_codes), ps.card_colour.value, ps.escorted, ps.issued_on,
         ps.card_expiry_date, *_cred(ps)]
        for ps in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _adps(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Adp)
        .join(Deployment, Deployment.id == Adp.deployment_id)
        .where(_dep_scope(c))
        .order_by(Adp.created_at)
    )
    stmt = _status(stmt, Adp.validity_status, status)
    cols = [
        "adp_no", *c.person_cols(), "contractor", "category", "vehicle_classes",
        "licence_class", "licence_expiry_date", "issued_on", "own_valid_until", *CRED_COLS,
    ]  # fmt: skip
    rows = [
        [a.adp_no or "", *c.person(a.worker_id), c.eng(a.engagement_id), a.category.value,
         ";".join(a.vehicle_classes), a.licence_class.value, a.licence_expiry_date, a.issued_on,
         a.own_valid_until, *_cred(a)]
        for a in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _offences(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Offence)
        .where(Offence.project_id == c.project.id, c.eng_clause(Offence.engagement_id))
        .order_by(Offence.offence_at)
    )
    stmt = _status(stmt, Offence.status, status)
    cols = [
        "offence_no", *c.person_cols(), "contractor", "adp_no", "offence_code", "points",
        "immediate_suspension", "offence_date", "zone", "status",
    ]  # fmt: skip
    rows = []
    for o in c.scalars(stmt):
        a = c.db.get(Adp, o.adp_id) if o.adp_id else None
        rows.append(
            [o.offence_no, *c.person(o.worker_id), c.eng(o.engagement_id),
             (a.adp_no or "") if a else "", o.offence_code, o.points, o.immediate_suspension,
             o.offence_date, c.zone(o.zone_id), o.status.value]
        )  # fmt: skip
    return cols, rows


VEH_COLS = ["vehicle_no", "plate", "fleet_no"]


def _veh(v: Vehicle | None) -> list[Any]:
    if v is None:
        return ["", "", ""]
    return [v.vehicle_no, common.plate_display(v) or "", v.fleet_no]


def _vehicles(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Vehicle)
        .where(Vehicle.project_id == c.project.id, c.eng_clause(Vehicle.engagement_id))
        .order_by(Vehicle.vehicle_no)
    )
    stmt = _status(stmt, Vehicle.status, status)
    cols = [
        *VEH_COLS, "contractor", "owner_type", "category", "make_model", "year_built",
        "travel_height_m", "max_working_height_m_agl", "istimara_expiry", "insurance_expiry",
        "mvpi_expiry", "status",
    ]  # fmt: skip
    rows = [
        [*_veh(v), c.eng(v.engagement_id), v.owner_type.value, v.category.value, v.make_model,
         v.year_built, v.travel_height_m, v.max_working_height_m_agl, v.istimara_expiry,
         v.insurance_expiry, v.mvpi_expiry, v.status.value]
        for v in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _avps(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Avp)
        .where(Avp.project_id == c.project.id, c.eng_clause(Avp.engagement_id))
        .order_by(Avp.created_at)
    )
    stmt = _status(stmt, Avp.validity_status, status)
    cols = [
        "avp_no", *VEH_COLS, "contractor", "areas", "inspection_date", "inspection_result",
        "sticker_no", "issued_on", "own_valid_until", *CRED_COLS,
    ]  # fmt: skip
    rows = [
        [a.avp_no or "", *_veh(c.db.get(Vehicle, a.vehicle_id)), c.eng(a.engagement_id),
         ";".join(a.areas), a.inspection_date,
         a.inspection_result.value if a.inspection_result else "", a.sticker_no or "",
         a.issued_on, a.own_valid_until, *_cred(a)]
        for a in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _ntm_nos(c: _Ctx, ids: list[uuid.UUID] | None) -> str:
    out = []
    for i in ids or []:
        n = c.db.get(NotamRequest, i)
        if n is not None:
            out.append(n.ntm_no)
    return ";".join(out)


def _waps(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(Wap)
        .where(
            Wap.project_id == c.project.id,
            Wap.revision_of_id.is_(None),
            c.eng_clause(Wap.engagement_id),
            c.site_clause(Wap.site_id),
        )
        .order_by(Wap.year, Wap.seq)
    )
    stmt = _status(stmt, Wap.status, status)
    cols = [
        "wap_no", "revision_no", "site", "zones", "contractor", "valid_from", "valid_to",
        "crew_count", "linked_notams", "fod_handback_required", "approved_at", "status",
        "suspension_reason",
    ]  # fmt: skip
    rows = []
    for w in c.scalars(stmt):
        crew = c.db.scalars(
            select(WapCrew.id).where(WapCrew.wap_id == w.id, WapCrew.removed_at.is_(None))
        ).all()
        rows.append(
            [w.wap_no, w.revision_no, c.site(w.site_id), c.zones(w.zone_ids),
             c.eng(w.engagement_id), w.valid_from, w.valid_to, len(crew),
             _ntm_nos(c, w.linked_ntm_ids), w.fod_handback_required, w.approved_at,
             w.status.value, w.suspension_reason.value if w.suspension_reason else ""]
        )  # fmt: skip
    return cols, rows


def _notams(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(NotamRequest)
        .where(NotamRequest.project_id == c.project.id)
        .order_by(NotamRequest.year, NotamRequest.seq)
    )
    if c.g.engagement_ids is not None:
        stmt = stmt.where(c.eng_clause(NotamRequest.engagement_id))
    stmt = _status(stmt, NotamRequest.status, status)
    cols = [
        "ntm_no", "zones", "contractor", "works_impact", "requested_start_utc",
        "requested_end_utc", "submitted_to_ops_at", "late_request", "notam_number", "notam_type",
        "effective_from_utc", "effective_to_utc", "status",
    ]  # fmt: skip
    rows = [
        [n.ntm_no, c.zones(n.zone_ids), c.eng(n.engagement_id), ";".join(n.works_impact),
         n.requested_start_utc, n.requested_end_utc, n.submitted_to_ops_at, n.late_request,
         n.notam_number or "", n.notam_type.value if n.notam_type else "", n.effective_from_utc,
         n.effective_to_utc, n.status.value]
        for n in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _obstacles(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(ObstacleClearance)
        .where(ObstacleClearance.project_id == c.project.id)
        .order_by(ObstacleClearance.year, ObstacleClearance.seq)
    )
    if c.g.engagement_ids is not None:
        stmt = stmt.where(c.eng_clause(ObstacleClearance.engagement_id))
    stmt = _status(stmt, ObstacleClearance.status, status)
    cols = [
        "obs_no", "zone", "contractor", "equipment_type", "ground_elevation_m_amsl",
        "max_height_m_agl", "top_elevation_m_amsl", "ols_limit_m_amsl", "penetration_m",
        "clearance_reasons", "requested_from", "requested_to", "late_request", "decision",
        "approved_max_height_m_agl", "conditions", "valid_from", "valid_to", "status",
    ]  # fmt: skip
    rows = [
        [o.obs_no, c.zone(o.zone_id), c.eng(o.engagement_id), o.equipment_type.value,
         o.ground_elevation_m_amsl, o.max_height_m_agl, o.top_elevation_m_amsl,
         o.ols_limit_m_amsl, o.penetration_m, ";".join(o.clearance_reasons), o.requested_from,
         o.requested_to, o.late_request, o.decision.value if o.decision else "",
         o.approved_max_height_m_agl, ";".join(o.conditions), o.valid_from, o.valid_to,
         o.status.value]
        for o in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _ops(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    stmt = (
        select(OpsEvent)
        .where(OpsEvent.project_id == c.project.id, c.site_clause(OpsEvent.site_id))
        .order_by(OpsEvent.started_at)
    )
    cols = [
        "ops_no", "site", "type", "zones", "source", "source_ref", "started_at", "ended_at",
        "suspended_waps",
    ]  # fmt: skip
    rows = [
        [e.ops_no, c.site(e.site_id), e.type.value, c.zones(e.zone_ids), e.source.value,
         e.source_ref, e.started_at, e.ended_at, len(e.suspended_wap_ids or [])]
        for e in c.scalars(stmt)
    ]  # fmt: skip
    return cols, rows


def _gate_log(c: _Ctx, status: str | None, q: str | None) -> tuple[list[str], list[list[Any]]]:
    g76 = c.p.grant(c.project.id, C.gate_log_view)
    if g76 is None:
        raise forbidden_error("Exporting the gate log needs capability 76.")
    stmt = (
        select(GateCheck, Gate.gate_code)
        .join(Gate, Gate.id == GateCheck.gate_id)
        .where(
            GateCheck.project_id == c.project.id,
            c.eng_clause(GateCheck.engagement_id),
            c.site_clause(GateCheck.site_id),
        )
        .order_by(GateCheck.occurred_at)
    )
    if g76.engagement_ids is not None:
        stmt = stmt.where(GateCheck.engagement_id.in_(list(g76.engagement_ids)))
    stmt = _status(stmt, GateCheck.result, status)
    cols = [
        "occurred_at", "local_date", "gate", "direction", "subject_kind", "subject_ref",
        "contractor", "zone", "result", "reason_codes", "final", "late_exit",
        "admitted_despite_denial",
    ]  # fmt: skip
    rows = [
        [r.occurred_at, r.local_date, code, r.direction.value, r.subject_kind.value,
         r.subject_ref or "", c.eng(r.engagement_id), c.zone(r.zone_id), r.result.value,
         ";".join(r.reason_codes), r.final, r.late_exit, r.admitted_despite_denial]
        for r, code in c.db.execute(stmt.limit(MAX_ROWS)).all()
    ]  # fmt: skip
    return cols, rows


BUILDERS: dict[ExportDataset, Callable[[_Ctx, str | None, str | None], tuple[list[str], Any]]] = {
    D.workers: _workers,
    D.deployments: _deployments,
    D.inductions: _inductions,
    D.pass_applications: _applications,
    D.airport_passes: _passes,
    D.adps: _adps,
    D.airside_offences: _offences,
    D.vehicles: _vehicles,
    D.avps: _avps,
    D.waps: _waps,
    D.notam_requests: _notams,
    D.obstacle_clearances: _obstacles,
    D.ops_events: _ops,
    D.gate_log: _gate_log,
}


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
    g = p.grant(project.id, C.export_access)
    if g is None:
        raise forbidden_error("Exporting access registers needs capability 78.")
    if include_identity:
        if dataset not in IDENTITY_DATASETS:
            raise validation_error("include_identity", "This register has no ID numbers.")
        if p.grant(project.id, C.export_access_identity) is None:
            raise forbidden_error("Exporting full ID numbers needs capability 79.")
        if (
            purpose not in ACCESS_PURPOSES
            or purpose is None
            or (purpose == ExportPurpose.other and not (purpose_text or "").strip())
        ):
            raise ApiError(
                422,
                ErrorCode.EXPORT_PURPOSE_REQUIRED,
                "State the purpose of an export with full ID numbers: pass_office, "
                "authority_request, legal or other with a text (P2-10).",
                "يجب ذكر الغرض من تصدير أرقام الهوية الكاملة.",
            )
    c = _Ctx(db, p, project, g, common.can_see_names(p, project.id), include_identity)
    cols, rows = BUILDERS[dataset](c, status, q)
    audit.record(
        db,
        AuditAction.export,
        p.actor(project.id),
        project_id=project.id,
        fields_read=["id_number"] if include_identity else None,
        details={
            "dataset": dataset.value,
            "format": fmt.value,
            "row_count": len(rows),
            "columns": cols,
            "filters": {k: v for k, v in {"status": status, "q": q}.items() if v},
            "include_identity": include_identity,
            "purpose": purpose.value if purpose and include_identity else None,
            "purpose_text": purpose_text if include_identity else None,
        },
    )
    return export_svc.encode(cols, rows, fmt, dataset.value)
