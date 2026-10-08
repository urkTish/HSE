"""Phase 5 training register exports (spec 5-training §8.4, capability 144).

Rows come from the same visibility-scoped services the registers use, so an export never shows
more than the caller's register. Never ID numbers or scans; person names only with capability
46; scores (training_attendance, training_records) only for HSE Manager / Officer (P5-5).
Verification-failure details (differences, free text) are never exported. Every export writes an
`export` audit entry with row count, columns and filters."""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import AuditAction, Capability, ExportDataset, ExportFormat
from app.core.errors import validation_error
from app.core.train_enums import (
    RefresherPlanState,
    RequirementState,
    SessionStatus,
    TrainerAuthorisationStatus,
    TrainingImportStatus,
    TrainingProviderStatus,
    TrainingRecordStatus,
)
from app.models import Project, TrainingImportBatch, TrainingRecord, User
from app.services import audit, projects
from app.services import exports as export_svc
from app.services.access import common as acommon
from app.services.permissions import Principal, forbidden_error
from app.services.train import common as tcommon
from app.services.train import config as tconfig
from app.services.train import courses as course_svc
from app.services.train import gaps as gap_svc
from app.services.train import matrix as matrix_svc
from app.services.train import providers as provider_svc
from app.services.train import records as record_svc
from app.services.train import sessions as session_svc
from app.services.train import trainers as trainer_svc

C = Capability
D = ExportDataset
MAX_ROWS = 50_000
PAGE = 500
DATASETS = frozenset(
    {
        D.training_courses,
        D.training_providers,
        D.trainer_authorisations,
        D.training_matrix,
        D.training_sessions,
        D.training_attendance,
        D.training_records,
        D.training_verifications,
        D.training_gaps,
        D.refresher_plan,
        D.training_hours,
        D.training_imports,
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


def _match(q: str | None, *parts: Any) -> bool:
    return not q or q.lower() in " ".join(str(x or "") for x in parts).lower()


class _Ctx:
    def __init__(
        self, db: Session, p: Principal, project: Project, names: bool, scores: bool
    ) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.names = names
        self.scores = scores


def _worker_cols(c: _Ctx) -> list[str]:
    return ["worker_no"] + (["worker_name_en", "worker_name_ar"] if c.names else [])


def _worker(c: _Ctx, w: Any) -> list[Any]:
    out: list[Any] = [w.worker_no]
    if c.names:
        out += [w.full_name_en or "", w.full_name_ar or ""]
    return out


def _courses(c: _Ctx, status: str | None, q: str | None) -> Rows:
    active = None if not status else status == "active"
    res = course_svc.list_courses(c.db, c.p, None, active, None, q, c.project.id)
    cols = [
        "code", "name_en", "name_ar", "category", "validity_months", "effective_validity_months",
        "min_duration_hours", "delivery_modes", "theory_required", "pass_mark_pct",
        "practical_required", "prerequisite_codes", "satisfies", "renewal_course_code",
        "accreditation_bodies_required", "internal_allowed", "contractor_delivery_allowed",
        "languages_offered",
        "hook_code", "critical_on_project", "active",
    ]  # fmt: skip
    rows = []
    for x in res.items:
        pr = x.provider_rule
        rows.append(
            [
                x.code, x.name_en, x.name_ar, _v(x.category), x.validity_months,
                x.effective_validity_months, x.min_duration_hours, _join(x.delivery_modes),
                x.theory_required, x.pass_mark_pct, x.practical_required,
                _join(x.prerequisite_codes), _join(x.satisfies), x.renewal_course_code,
                _join(pr.accreditation_bodies_required) if pr else "",
                pr.internal_allowed if pr else "", pr.contractor_delivery_allowed if pr else "",
                _join(x.languages_offered), x.hook_code,
                x.critical_on_project, x.active,
            ]
        )  # fmt: skip
    return cols, rows


def _providers(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(TrainingProviderStatus, status)
    items = _all(
        lambda pg, ps: provider_svc.list_providers(
            c.db, c.p, pg, ps, q, sts, None, None, None, None
        )
    )
    cols = [
        "provider_code", "legal_name_en", "legal_name_ar", "kind", "contractor", "status",
        "accepted_for_use", "accredited_course_codes", "next_accreditation_expiry",
    ]  # fmt: skip
    rows = [
        [
            x.provider_code, x.legal_name_en, x.legal_name_ar, _v(x.kind),
            x.contractor_short_code, _v(x.status), x.accepted_for_use,
            _join(x.accredited_course_codes), x.next_accreditation_expiry,
        ]
        for x in items
    ]  # fmt: skip
    return cols, rows


def _trainers(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(TrainerAuthorisationStatus, status)
    items = _all(
        lambda pg, ps: trainer_svc.list_authorisations(
            c.db, c.p, c.project.id, pg, ps, sts, None, None, None, None
        )
    )
    cols = ["authorisation_no"]
    if c.names:
        cols.append("trainer_name")
    cols += [
        "trainer_worker_no", "provider_code", "course_codes", "roles", "valid_from", "valid_to",
        "days_left", "status",
    ]  # fmt: skip
    if c.names:
        cols.append("authorised_by")
    rows = []
    for x in items:
        tw = x.trainer_worker
        name = (
            x.trainer_user.full_name_en
            if x.trainer_user is not None
            else (tw.full_name_en if tw is not None else "")
        )
        if not _match(q, x.authorisation_no, x.provider.provider_code, name if c.names else ""):
            continue
        row: list[Any] = [x.authorisation_no]
        if c.names:
            row.append(name or "")
        row += [
            tw.worker_no if tw is not None else "", x.provider.provider_code,
            _join(x.course_codes), _join(x.roles), x.valid_from, x.valid_to, x.days_left,
            _v(x.status),
        ]  # fmt: skip
        if c.names:
            row.append(x.authorised_by.full_name_en)
        rows.append(row)
    return cols, rows


def _matrix(c: _Ctx, status: str | None, q: str | None) -> Rows:
    m = matrix_svc.read_matrix(c.db, c.p, c.project.id, include_counts=True)
    cols = [
        "line_no", "applies_to_kind", "applies_to_values", "requirement", "level",
        "due_within_days", "source", "kpi_counted", "hook_attach_point", "effective_from",
        "effective_to", "applicable_deployments",
    ]  # fmt: skip
    rows = []
    for ln in m.lines:
        req = ln.requirement.course_code or " | ".join(ln.requirement.any_of or [])
        if not _match(q, ln.line_no, req, " ".join(ln.applies_to_values)):
            continue
        rows.append(
            [
                ln.line_no, _v(ln.applies_to_kind), _join(ln.applies_to_values), req,
                _v(ln.level), ln.due_within_days, _v(ln.source), ln.kpi_counted,
                ln.hook_attach_point, ln.effective_from, ln.effective_to,
                ln.applicable_deployments,
            ]
        )  # fmt: skip
    return cols, rows


def _session_items(c: _Ctx, status: str | None) -> list[Any]:
    sts = _parse(SessionStatus, status)
    return _all(
        lambda pg, ps: session_svc.list_sessions(
            c.db, c.p, c.project.id, pg, ps, sts, None, None, None, None, None, None
        )
    )


def _sessions(c: _Ctx, status: str | None, q: str | None) -> Rows:
    cols = [
        "session_no", "course_code", "course_name_en", "provider_code", "language", "first_day",
        "last_day", "site", "status", "capacity", "nominated", "close_overdue",
    ]  # fmt: skip
    rows = [
        [
            s.session_no, s.course.code, s.course.name_en, s.provider_code, _v(s.language),
            s.first_day, s.last_day, s.site_code, _v(s.status), s.capacity, s.nominated,
            s.close_overdue,
        ]
        for s in _session_items(c, status)
        if _match(q, s.session_no, s.course.code, s.provider_code)
    ]  # fmt: skip
    return cols, rows


def _attendance(c: _Ctx, status: str | None, q: str | None) -> Rows:
    cols = ["session_no", "course_code", *_worker_cols(c)]
    cols += ["contractor", "status", "attended_hours", "attendance_complete"]
    if c.scores:
        cols += ["theory_score_pct", "practical_result"]
    cols += ["attempt_no", "result", "record_no"]
    rows = []
    for s in _session_items(c, status):
        if not _match(q, s.session_no, s.course.code):
            continue
        for n in session_svc.list_nominations(c.db, c.p, s.id).items:
            row = [s.session_no, s.course.code, *_worker(c, n.worker)]
            row += [
                n.engagement.short_code if n.engagement else "", _v(n.status), n.attended_hours,
                n.attendance_complete,
            ]  # fmt: skip
            if c.scores:
                row += [n.theory_score_pct, _v(n.practical_result)]
            row += [n.attempt_no, _v(n.result), n.record.record_no if n.record else ""]
            rows.append(row)
    return cols, rows


def _records(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(TrainingRecordStatus, status)
    items = _all(
        lambda pg, ps: record_svc.list_records(c.db, c.p, c.project.id, pg, ps, q=q, statuses=sts)
    )
    scores: dict[uuid.UUID, Any] = {}
    if c.scores and items:
        scores = dict(
            c.db.execute(
                select(TrainingRecord.id, TrainingRecord.theory_score_pct).where(
                    TrainingRecord.id.in_([x.id for x in items])
                )
            ).all()
        )
    cols = ["record_no", *_worker_cols(c)]
    cols += [
        "contractor", "course_code", "course_name_en", "provider_code", "source",
        "certificate_no", "completed_on", "valid_until", "limiting_factor", "days_left",
        "in_force", "status", "verification_status", "historic",
    ]  # fmt: skip
    if c.scores:
        cols.append("theory_score_pct")
    rows = []
    for x in items:
        row = [x.record_no, *_worker(c, x.worker)]
        row += [
            x.engagement.short_code if x.engagement else "", x.course_code, x.course_name_en,
            x.provider_code, _v(x.source), x.certificate_no, x.completed_on, x.valid_until,
            _v(x.limiting_factor), x.days_left, x.in_force, _v(x.status),
            _v(x.verification_status), x.historic,
        ]  # fmt: skip
        if c.scores:
            row.append(scores.get(x.id) or "")
        rows.append(row)
    return cols, rows


def _verifications(c: _Ctx, status: str | None, q: str | None) -> Rows:
    items = _all(
        lambda pg, ps: record_svc.verification_log(
            c.db, c.p, c.project.id, pg, ps, failed_only=status == "failed"
        )
    )
    # Failure details (differences, free text) are never exported (§8.4).
    cols = [
        "record_no", "certificate_no", "worker_no", "course_code", "provider_code", "method",
        "channel_used", "outcome", "reference", "performed_at", "counts_as_verification",
        "verification_status_after",
    ]  # fmt: skip
    if c.names:
        cols.append("performed_by")
    rows = []
    for v in items:
        if not _match(q, v.record_no, v.certificate_no, v.worker_no, v.course_code):
            continue
        row = [
            v.record_no, v.certificate_no, v.worker_no, v.course_code, v.provider_code,
            _v(v.method), v.channel_used, _v(v.outcome), v.reference, v.performed_at,
            v.counts_as_verification, _v(v.verification_status_after),
        ]  # fmt: skip
        if c.names:
            row.append(v.performed_by.full_name_en if v.performed_by else "system")
        rows.append(row)
    return cols, rows


def _gaps(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(RequirementState, status)
    items = _all(
        lambda pg, ps: gap_svc.list_gaps(
            c.db, c.p, c.project.id, pg, ps, None, sts, None, True, None, None, None, None, False
        )
    )
    cols = [*_worker_cols(c), "contractor", "trade", "line_nos", "requirement", "level"]
    cols += [
        "hook_code", "critical", "due_date", "state", "days_overdue", "valid_until",
        "booked_session", "live_permits", "live_wap_nos",
    ]  # fmt: skip
    rows = []
    for g in items:
        req = g.requirement.course_code or " | ".join(g.requirement.any_of or [])
        if not _match(q, g.worker.worker_no, req, g.engagement.short_code):
            continue
        row = [*_worker(c, g.worker), g.engagement.short_code, _v(g.trade)]
        row += [
            _join(g.line_nos), req, _v(g.level), g.hook_code, g.critical, g.due_date,
            _v(g.state), g.days_overdue, g.valid_until,
            g.booked_session.session_no if g.booked_session else "",
            ";".join(x.permit_no for x in g.live_permits),
            _join(g.live_wap_nos),
        ]  # fmt: skip
        rows.append(row)
    return cols, rows


def _refresher(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(RefresherPlanState, status)
    items = _all(
        lambda pg, ps: gap_svc.refresher_plan(
            c.db, c.p, c.project.id, pg, ps, None, sts, None, None, None
        )
    )
    cols = ["record_no", *_worker_cols(c), "contractor", "language", "course_code"]
    cols += [
        "course_name_en", "valid_until", "days_left", "refresher_due_from", "reason_required",
        "booked_session", "state",
    ]  # fmt: skip
    rows = []
    for x in items:
        if not _match(q, x.record.record_no, x.worker.worker_no, x.course.code):
            continue
        row = [x.record.record_no, *_worker(c, x.worker), x.engagement.short_code]
        row += [
            _v(x.language), x.course.code, x.course.name_en, x.valid_until, x.days_left,
            x.refresher_due_from, x.reason_required,
            x.booked_session.session_no if x.booked_session else "", _v(x.state),
        ]  # fmt: skip
        rows.append(row)
    return cols, rows


def _hours(c: _Ctx, status: str | None, q: str | None) -> Rows:
    start = tcommon.register_from(c.db, c.project.id) or c.project.start_date
    rep = tconfig.hours_report(c.db, c.p, c.project.id, start, today())
    cols = [
        "month", "contractor", "source", "register_days", "register_hours",
        "daily_return_hours", "daily_return_hours_register_days", "staff_hours", "voided_hours",
        "reconciliation_pct", "reconciliation_note", "sessions_not_closed",
    ]  # fmt: skip
    rows = [
        [
            r.month, r.engagement.short_code if r.engagement else "TOTAL", _v(r.source),
            r.register_days, r.register_hours, r.daily_return_hours,
            r.daily_return_hours_register_days, r.staff_hours, r.voided_hours,
            r.reconciliation_pct, r.reconciliation_note, r.sessions_not_closed,
        ]
        for r in rep.rows
        if _match(q, r.month, r.engagement.short_code if r.engagement else "")
    ]  # fmt: skip
    return cols, rows


def _imports(c: _Ctx, status: str | None, q: str | None) -> Rows:
    sts = _parse(TrainingImportStatus, status)
    stmt = select(TrainingImportBatch).where(TrainingImportBatch.project_id == c.project.id)
    if sts:
        stmt = stmt.where(TrainingImportBatch.status.in_(sts))
    batches = list(c.db.scalars(stmt.order_by(TrainingImportBatch.created_at.desc())))
    users = (
        {u.id: u for u in c.db.scalars(select(User).where(User.id.in_(
            {b.uploaded_by_user_id for b in batches})))}
        if c.names and batches
        else {}
    )  # fmt: skip
    cols = [
        "created_at", "template", "source", "file_name", "status", "rows_total", "rows_ok",
        "rows_warning", "rows_error", "records_created", "committed_at",
    ]  # fmt: skip
    if c.names:
        cols.append("uploaded_by")
    rows = []
    for b in batches[:MAX_ROWS]:
        if not _match(q, b.file_name):
            continue
        k = b.counts or {}
        row = [
            b.created_at, _v(b.template), _v(b.source), b.file_name, _v(b.status),
            k.get("rows_total", 0), k.get("rows_ok", 0), k.get("rows_warning", 0),
            k.get("rows_error", 0), len(b.committed_record_ids or []), b.committed_at,
        ]  # fmt: skip
        if c.names:
            u = users.get(b.uploaded_by_user_id)
            row.append(u.full_name_en if u is not None else "")
        rows.append(row)
    return cols, rows


BUILDERS: dict[ExportDataset, Callable[[_Ctx, str | None, str | None], Rows]] = {
    D.training_courses: _courses,
    D.training_providers: _providers,
    D.trainer_authorisations: _trainers,
    D.training_matrix: _matrix,
    D.training_sessions: _sessions,
    D.training_attendance: _attendance,
    D.training_records: _records,
    D.training_verifications: _verifications,
    D.training_gaps: _gaps,
    D.refresher_plan: _refresher,
    D.training_hours: _hours,
    D.training_imports: _imports,
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
    if p.grant(project.id, C.export_training) is None:
        raise forbidden_error("Exporting training registers needs capability 144.")
    c = _Ctx(
        db,
        p,
        project,
        acommon.can_see_names(p, project.id),
        tcommon.is_hse(p, project.id),
    )
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
