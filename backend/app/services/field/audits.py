"""Audits and the audit programme (spec 6d-field-assurance §3.7, §3.8, §4.4, §6.2, §6.4,
AUD-1…AUD-8): planning with independence (SOD_CONFLICT), 0–3 answers and NC grades, issue with
CAs (source `field_audit`) and the EN / AR report, automatic close, void, and programme lines."""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import (
    AUDIT_GRADES,
    AuditStatus,
    AuditType,
    FindingSeverity,
    ProgrammeLineStatus,
    ProgrammeScope,
    ResponseOwnerType,
    TemplateKind,
    VersionStatus,
)
from app.core.field_enums import AuditAction as AuditStep
from app.core.hse_enums import AttachmentOwner, CaSourceType, CaStatus, ControlLevel
from app.models import (
    ChecklistResponse,
    ChecklistTemplate,
    CorrectiveAction,
    FieldAudit,
    FieldFinding,
    Project,
    ProjectEngagement,
    RoleAssignment,
    Site,
    User,
    WorkforceReturn,
)
from app.schemas.field import (
    AuditAnswers,
    AuditCreate,
    AuditPage,
    AuditProgramme,
    AuditRead,
    AuditTransition,
    AuditUpdate,
    ProgrammeItem,
    ProgrammeLineRead,
)
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.field import common as fc
from app.services.field import execution, library, scoring
from app.services.field.reference import AUDIT_TYPES, grade_for
from app.services.hse_common import Refs
from app.services.permissions import Principal, build_principal, forbidden_error

C = Capability
S = AuditStatus
FS = FindingSeverity
D = Decimal
SATISFYING = (S.issued, S.closed)
NC_PRIORITY = {FS.major_nc: "major_nc", FS.minor_nc: "minor_nc"}


def _sod(en: str, fld: str | None = None) -> Any:
    return fc.err(422, ErrorCode.SOD_CONFLICT, en, "تعارض في الاستقلالية (فصل المهام).", field=fld)


def line_type(a: FieldAudit) -> AuditType:
    """AT: client_requested counts as contractor_hse when an auditee is set."""
    if a.audit_type == AuditType.client_requested and a.auditee_engagement_id:
        return AuditType.contractor_hse
    return a.audit_type


# ---- reads ---------------------------------------------------------------------------------------


def audit_read(db: Session, p: Principal | None, a: FieldAudit) -> AuditRead:
    refs = Refs(db).load(
        sites=list(a.site_ids or []),
        engs=[a.auditee_engagement_id],
        users=[a.lead_auditor_id, a.issued_by_user_id, *list(a.team_ids or [])],
    )
    r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
    t = db.get(ChecklistTemplate, a.template_id) if a.template_id else None
    days = int(fc.cfg(db, a.project_id)["audit_report_days"])
    return AuditRead(
        id=a.id,
        audit_no=a.audit_no,
        project_id=a.project_id,
        audit_type=a.audit_type,
        template_code=a.template_code,
        template_version=t.version if t else None,
        auditee_engagement=refs.eng(a.auditee_engagement_id),
        sites=[refs.site(s) for s in a.site_ids or []],
        lead_auditor=refs.user(a.lead_auditor_id),
        team=[u for u in (refs.user(x) for x in a.team_ids or []) if u is not None],
        planned_start=a.planned_start,
        planned_end=a.planned_end,
        fieldwork_start=a.fieldwork_start,
        fieldwork_end=a.fieldwork_end,
        opening_meeting_at=a.opening_meeting_at,
        closing_meeting_at=a.closing_meeting_at,
        auditee_attendee_roles=a.auditee_attendee_roles,
        report_due_by=a.fieldwork_end + timedelta(days=days) if a.fieldwork_end else None,
        response=execution.response_read(db, p, r) if r else None,
        summary_en=a.summary_en,
        summary_ar=a.summary_ar,
        report_en_id=a.report_en_id,
        report_ar_id=a.report_ar_id,
        issued_by=refs.user(a.issued_by_user_id),
        issued_at=a.issued_at,
        closed_at=a.closed_at,
        status=a.status,
        status_reason=a.status_reason,
    )


def _visible(p: Principal, a: FieldAudit) -> bool:
    if p.user.id == a.lead_auditor_id or p.user.id in (a.team_ids or []):
        return True
    g = p.grant(a.project_id, C.field_view)
    if g is None:
        return False
    return g.engagement_ids is None or g.covers_engagement(a.auditee_engagement_id)


def _get(db: Session, p: Principal, audit_id: uuid.UUID) -> FieldAudit:
    a = db.get(FieldAudit, audit_id)
    if a is None or not p.can_see_project(a.project_id) or not _visible(p, a):
        raise not_found("Audit")
    return a


def read_audit(db: Session, p: Principal, audit_id: uuid.UUID) -> AuditRead:
    return audit_read(db, p, _get(db, p, audit_id))


def list_audits(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    audit_type: AuditType | None,
    statuses: list[AuditStatus] | None,
    auditee: uuid.UUID | None,
    page: int,
    page_size: int,
) -> AuditPage:
    fc.project(db, p, project_id)
    g = fc.view_grant(p, project_id)
    A = FieldAudit  # noqa: N806
    stmt = select(A).where(A.project_id == project_id)
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        stmt = stmt.where(A.auditee_engagement_id.in_(engs) if engs else false())
    if audit_type:
        stmt = stmt.where(A.audit_type == audit_type)
    if statuses:
        stmt = stmt.where(A.status.in_(statuses))
    if auditee:
        stmt = stmt.where(A.auditee_engagement_id == auditee)
    items, total = paginate(
        db, stmt.order_by(A.planned_start.desc(), A.audit_no.desc()), page, page_size
    )
    return AuditPage(
        items=[audit_read(db, p, a) for a in items], total=total, page=page, page_size=page_size
    )


# ---- planning (AUD-1…AUD-3) ----------------------------------------------------------------------


def _assignments(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> list[RoleAssignment]:
    day = fc.local_day()
    return [
        x
        for x in db.scalars(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.project_id == project_id,
                RoleAssignment.revoked_at.is_(None),
            )
        )
        if x.is_active_on(day)
    ]


def _independent(
    db: Session,
    proj: Project,
    a_type: AuditType,
    auditee: uuid.UUID | None,
    uid: uuid.UUID,
    fld: str,
) -> None:
    """AUD-3: not employed by the auditee (a rep audits only engagements strictly below their
    own); for system audits the lead is not an HSE Officer of the project."""
    for x in _assignments(db, uid, proj.id):
        if auditee is not None and x.contractor_engagement_id is not None:
            tree = fc.tree_of(db, auditee)
            if x.contractor_engagement_id == auditee or x.contractor_engagement_id not in tree:
                raise _sod("The auditor is not independent of the auditee (AUD-3).", fld)
        if (
            a_type == AuditType.system_iso45001
            and fld == "lead_auditor_id"
            and (x.role == Role.hse_officer)
        ):
            raise _sod("A system audit is led by someone who is not an HSE Officer of the "
                       "project (AUD-3).", fld)  # fmt: skip


def _auditor(db: Session, proj: Project, uid: uuid.UUID, fld: str) -> None:
    u = db.get(User, uid)
    if u is None:
        raise validation_error(fld, "Unknown user.")
    if build_principal(db, u, None).grant(proj.id, C.field_audit_conduct) is None:
        raise validation_error(fld, "Auditors hold capability 194 on the project.")


def _template(
    db: Session, code: str, a_type: AuditType, project_id: uuid.UUID
) -> ChecklistTemplate:
    t = library.published(db, code)
    want = AuditType.contractor_hse if a_type == AuditType.client_requested else a_type
    if (
        t is None
        or t.kind != TemplateKind.audit
        or t.audit_type not in (a_type, want)
        or not library.offered(t, project_id)
    ):
        raise fc.err(422, ErrorCode.TEMPLATE_NOT_APPLICABLE,
                     "Use a Published audit template of the same audit type (AUD-1).",
                     "استخدم نموذج تدقيق منشوراً من النوع نفسه.", field="template_code")  # fmt: skip
    return t


def create_audit(db: Session, p: Principal, project_id: uuid.UUID, body: AuditCreate) -> AuditRead:
    proj = fc.project(db, p, project_id)
    ensure_open(proj)
    g = p.require(project_id, C.field_audit_conduct)
    t = _template(db, body.template_code, body.audit_type, project_id)
    auditee = body.auditee_engagement_id
    if body.audit_type == AuditType.contractor_hse and auditee is None:
        raise validation_error("auditee_engagement_id", "A contractor audit needs an auditee.")
    if body.audit_type == AuditType.system_iso45001 and auditee is not None:
        raise validation_error("auditee_engagement_id", "A system audit has project scope.")
    if auditee is not None:
        e = db.get(ProjectEngagement, auditee)
        if e is None or e.project_id != project_id:
            raise validation_error("auditee_engagement_id", "Not an engagement of the project.")
        if g.engagement_ids is not None and auditee not in g.engagement_ids:
            raise forbidden_error()
    elif g.engagement_ids is not None:
        raise forbidden_error()
    if g.engagement_ids is not None or g.site_ids is not None:  # reps and site engineers
        _independent(db, proj, body.audit_type, auditee, p.user.id, "auditee_engagement_id")
    for s in body.site_ids:
        site = db.get(Site, s)
        if site is None or site.project_id != project_id:
            raise validation_error("site_ids", "Sites of the project.")
    if body.planned_end < body.planned_start or (body.planned_end - body.planned_start).days > 9:
        raise validation_error("planned_end", "End ≥ start and at most 10 days.")
    team = list(dict.fromkeys(body.team_ids))
    if body.lead_auditor_id in team:
        raise validation_error("team_ids", "The lead auditor is not also a team member.")
    _auditor(db, proj, body.lead_auditor_id, "lead_auditor_id")
    _independent(db, proj, body.audit_type, auditee, body.lead_auditor_id, "lead_auditor_id")
    for i, uid in enumerate(team):
        _auditor(db, proj, uid, f"team_ids[{i}]")
        _independent(db, proj, body.audit_type, auditee, uid, f"team_ids[{i}]")
    year = body.planned_start.year
    seq = fc.next_seq(db, FieldAudit, project_id, year)
    from app.services.hse_common import make_ref  # noqa: PLC0415

    a = FieldAudit(
        audit_no=make_ref("AUD", proj.code, year, seq, 3),
        year=year,
        seq=seq,
        project_id=project_id,
        audit_type=body.audit_type,
        template_code=t.template_code,
        auditee_engagement_id=auditee,
        site_ids=list(body.site_ids),
        lead_auditor_id=body.lead_auditor_id,
        team_ids=team,
        planned_start=body.planned_start,
        planned_end=body.planned_end,
        status=S.planned,
        created_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    fc.record(db, p, AuditAction.create, EntityType.field_audit, a, project_id)
    return audit_read(db, p, a)


def _conductor(p: Principal, a: FieldAudit) -> None:
    team = p.user.id == a.lead_auditor_id or p.user.id in (a.team_ids or [])
    if not team and not p.is_manager:
        raise forbidden_error("Only the audit team records the audit.")
    p.require(a.project_id, C.field_audit_conduct)


def update_audit(db: Session, p: Principal, audit_id: uuid.UUID, body: AuditUpdate) -> AuditRead:
    a = _get(db, p, audit_id)
    proj = fc.project(db, p, a.project_id)
    ensure_open(proj)
    _conductor(p, a)
    if a.status not in (S.planned, S.in_progress, S.fieldwork_complete):
        raise invalid_transition("Audit", a.status, a.status)
    ch = body.model_dump(exclude_unset=True)
    if "team_ids" in ch:
        team = list(dict.fromkeys(ch["team_ids"] or []))
        for i, uid in enumerate(team):
            _auditor(db, proj, uid, f"team_ids[{i}]")
            _independent(db, proj, a.audit_type, a.auditee_engagement_id, uid, f"team_ids[{i}]")
        ch["team_ids"] = team
    for k in ("summary_en", "summary_ar"):
        if ch.get(k) and fc.p18(ch[k]):
            pass  # P1-8 hint shown by the client; summaries are not blocked
    for k, v in ch.items():
        if v is not None or k in ("summary_en", "summary_ar", "auditee_attendee_roles"):
            setattr(a, k, v)
    if a.fieldwork_start and a.fieldwork_end and a.fieldwork_end < a.fieldwork_start:
        raise validation_error("fieldwork_end", "End ≥ start.")
    if a.status == S.planned and a.opening_meeting_at is not None:
        a.status = S.in_progress  # §4.4: opening meeting recorded
    a.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.update, EntityType.field_audit, a, a.project_id)
    return audit_read(db, p, a)


# ---- answers (AUD-2) -----------------------------------------------------------------------------


def _ensure_response(
    db: Session, a: FieldAudit, t: ChecklistTemplate, uid: uuid.UUID
) -> ChecklistResponse:
    r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
    if r is not None:
        return r
    r = ChecklistResponse(
        project_id=a.project_id,
        client_uuid=uuid.uuid4(),
        owner_type=ResponseOwnerType.audit,
        audit_id=a.id,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        site_id=a.site_ids[0],
        engagement_id=a.auditee_engagement_id,
        started_at=now(),
        inspector_id=uid,
        answers=[],
        created_by_user_id=uid,
    )
    db.add(r)
    db.flush()
    a.response_id = r.id
    a.template_id = t.id
    return r


def apply_answers(
    db: Session,
    proj: Project,
    a: FieldAudit,
    answers: list[Any],
    manual: list[Any],
    uid: uuid.UUID,
    *,
    require_all: bool = False,
) -> ChecklistResponse:
    """Store the answers and rebuild the findings, score and grade (§6.2, AUD-2)."""
    t = (
        db.get(ChecklistTemplate, a.template_id)
        if a.template_id
        else library.published(db, a.template_code)
    )
    assert t is not None  # noqa: S101
    r = _ensure_response(db, a, t, uid)
    raw = [x.model_dump(mode="json") for x in answers]
    sc = scoring.evaluate(t.items, raw, airside=True, require_all=require_all, audit=True)
    by_code = {x.item_code: (i, x) for i, x in enumerate(answers)}
    for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == r.id)):
        db.delete(f)
    db.flush()
    warnings: list[dict[str, Any]] = []
    r.answers = execution.store_answers(db, uid, r, sc, by_code, warnings)
    capped = False
    n = 0
    for ev in sc.evals:
        sev0 = scoring.finding_severity(ev, audit=True)
        if sev0 is None:
            continue
        idx, x = by_code[ev.code]
        if x.severity is not None and x.severity not in AUDIT_GRADES:
            raise validation_error(f"answers[{idx}].severity", "Use an audit finding grade.")
        sev = scoring.raised(sev0, x.severity, f"answers[{idx}].severity")
        if sev == FS.major_nc and ev.critical:
            capped = True
        n += 1
        db.add(_finding(a, r, n, ev.code, sev, ev.critical,
                        (x.finding_description_en or x.note or ev.item.get("text_en")),
                        x.finding_description_ar, uid))  # fmt: skip
    for i, mf in enumerate(manual):
        if mf.severity not in AUDIT_GRADES:
            raise validation_error(f"manual_findings[{i}].severity", "Use an audit finding grade.")
        if not ((mf.description_en or "").strip() or (mf.description_ar or "").strip()):
            raise validation_error(f"manual_findings[{i}].description_en", "Describe it.")
        n += 1
        db.add(_finding(a, r, n, None, mf.severity, False, mf.description_en,
                        mf.description_ar, uid, mf.ca_required))  # fmt: skip
    pct = sc.pct
    r.applicable_count = sc.applicable_count
    r.compliant_count = sc.compliant_count
    r.applicable_weight = sc.applicable_weight
    r.earned_weight = sc.earned_weight
    r.score_pct = scoring.q(pct) if pct is not None else None
    r.critical_fail_count = sc.critical_fails
    r.grade = grade_for(pct, capped)
    r.warnings = warnings
    r.updated_at = now()
    db.flush()
    return r


def _finding(
    a: FieldAudit,
    r: ChecklistResponse,
    n: int,
    code: str | None,
    sev: FindingSeverity,
    critical: bool,
    en: str | None,
    ar: str | None,
    uid: uuid.UUID,
    ca_required: bool = False,
) -> FieldFinding:
    return FieldFinding(
        project_id=a.project_id,
        response_id=r.id,
        finding_no=f"{a.audit_no}-F{n:02d}",
        item_code=code,
        severity=sev,
        critical_item=critical,
        description_en=(en or "")[:1000] or None,
        description_ar=ar,
        ca_required=ca_required,
        responsible_engagement_id=a.auditee_engagement_id,
        site_id=a.site_ids[0],
        engagement_id=a.auditee_engagement_id,
        completed_date=a.fieldwork_end,
        created_by_user_id=uid,
    )


def save_answers(db: Session, p: Principal, audit_id: uuid.UUID, body: AuditAnswers) -> AuditRead:
    a = _get(db, p, audit_id)
    proj = fc.project(db, p, a.project_id)
    ensure_open(proj)
    _conductor(p, a)
    if a.status not in (S.planned, S.in_progress):
        raise invalid_transition("Audit", a.status, S.in_progress)
    apply_answers(db, proj, a, body.answers, body.manual_findings, p.user.id)
    if a.status == S.planned:
        a.status = S.in_progress  # §4.4: first answer saved
    a.updated_at = now()
    db.flush()
    return audit_read(db, p, a)


# ---- transitions ---------------------------------------------------------------------------------


def transition_audit(
    db: Session, p: Principal, audit_id: uuid.UUID, body: AuditTransition
) -> AuditRead:
    a = _get(db, p, audit_id)
    proj = fc.project(db, p, a.project_id)
    ensure_open(proj)
    before = {"status": a.status.value}
    act = body.action
    if act == AuditStep.start:
        _conductor(p, a)
        if a.status != S.planned:
            raise invalid_transition("Audit", a.status, S.in_progress)
        a.opening_meeting_at = a.opening_meeting_at or now()
        a.fieldwork_start = a.fieldwork_start or fc.local_day()
        a.status = S.in_progress
    elif act == AuditStep.complete_fieldwork:
        if p.user.id != a.lead_auditor_id and not p.is_manager:
            raise forbidden_error("The lead auditor completes the fieldwork.")
        if a.status != S.in_progress:
            raise invalid_transition("Audit", a.status, S.fieldwork_complete)
        if a.closing_meeting_at is None:
            raise validation_error("closing_meeting_at", "Record the closing meeting.")
        if a.fieldwork_start is None or a.fieldwork_end is None:
            raise validation_error("fieldwork_end", "Record the fieldwork dates.")
        r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
        t = db.get(ChecklistTemplate, a.template_id) if a.template_id else None
        if r is None or t is None:
            raise validation_error("answers", "Answer every item first (EXE-2).")
        scoring.evaluate(t.items, r.answers, True, require_all=True, audit=True)
        r.completed_at = now()
        r.completed_date = a.fieldwork_end
        r.received_at = now()
        r.submitted = True
        for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == r.id)):
            f.completed_date = a.fieldwork_end
        a.status = S.fieldwork_complete
    elif act == AuditStep.issue:
        _issue(db, p, proj, a, body.ca_for_observations)
    elif act == AuditStep.cancel:
        p.require(a.project_id, C.field_audit_conduct)
        if a.status != S.planned:
            raise invalid_transition("Audit", a.status, S.cancelled)
        a.status_reason = fc.reason(body.reason, 20)
        a.status = S.cancelled
    else:
        p.require(a.project_id, C.field_void)
        if a.status not in (S.in_progress, S.fieldwork_complete, S.issued):
            raise invalid_transition("Audit", a.status, S.voided)
        a.status_reason = fc.reason(body.reason, 20)
        a.status = S.voided
        r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
        if r is not None:
            r.voided = True
            for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == r.id)):
                f.voided = True
    a.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.field_audit, a, a.project_id,
              before=before, details={"action": act.value})  # fmt: skip
    return audit_read(db, p, a)


def _issue(db: Session, p: Principal, proj: Project, a: FieldAudit, obs_ca: bool) -> None:
    """AUD-4: 195 ≠ lead auditor; CAs per NC; the EN / AR report."""
    p.require(a.project_id, C.field_audit_issue)
    if a.status != S.fieldwork_complete:
        raise invalid_transition("Audit", a.status, S.issued)
    if p.user.id == a.lead_auditor_id:
        raise _sod("The lead auditor cannot issue their own report (AUD-4).")
    if not ((a.summary_en or "").strip() or (a.summary_ar or "").strip()):
        raise validation_error("summary_en", "Write the summary before issuing.")
    r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
    assert r is not None  # noqa: S101
    site = a.site_ids[0]
    findings = list(
        db.scalars(
            select(FieldFinding)
            .where(FieldFinding.response_id == r.id)
            .order_by(FieldFinding.finding_no)
        )
    )
    t = db.get(ChecklistTemplate, a.template_id)
    items = {it["item_code"]: it for it in (t.items if t else [])}
    for f in findings:
        if (
            f.severity in NC_PRIORITY
            or (obs_ca and f.severity in (FS.observation, FS.ofi))
            or (f.ca_required)
        ):
            it = items.get(f.item_code or "", {})
            ctl = it.get("suggested_control_level")
            ca = fc.make_ca(
                db, proj, CaSourceType.field_audit, a.id, site, None, a.auditee_engagement_id,
                f.severity.value,
                it.get("suggested_ca_en") or f"{a.audit_no} {f.item_code or ''}: "
                f"{(f.description_en or f.description_ar or '')[:100]}",
                f"{f.finding_no}: {f.description_en or f.description_ar or ''}"[:2000],
                ControlLevel(ctl) if ctl else ControlLevel.administrative,
                a.lead_auditor_id, p.user.id,
            )  # fmt: skip
            f.ca_id = ca.id
    a.issued_by_user_id = p.user.id
    a.issued_at = now()
    a.status = S.issued
    db.flush()
    en, ar = report_html(db, a, r, findings)
    from app.services import attachments  # noqa: PLC0415

    a.report_en_id = attachments.store(
        db, AttachmentOwner.field_audit_report, a.id, a.project_id, f"{a.audit_no}-EN.html",
        en.encode(), "text/html", p.user.id,
    ).id  # fmt: skip
    a.report_ar_id = attachments.store(
        db, AttachmentOwner.field_audit_report, a.id, a.project_id, f"{a.audit_no}-AR.html",
        ar.encode(), "text/html", p.user.id,
    ).id  # fmt: skip


def report_html(
    db: Session, a: FieldAudit, r: ChecklistResponse, findings: list[FieldFinding]
) -> tuple[str, str]:
    """AUD-4 report (HTML, EN and AR): scope, team (names), score, grade, section scores and
    findings; never auditee worker names (findings carry no names, FND-4)."""
    refs = Refs(db).load(
        sites=list(a.site_ids or []),
        engs=[a.auditee_engagement_id],
        users=[a.lead_auditor_id, *list(a.team_ids or [])],
    )
    rr = execution.response_read(db, None, r)
    e = html.escape
    out = []
    for lang in ("en", "ar"):
        ar = lang == "ar"
        eng = refs.eng(a.auditee_engagement_id)
        scope = (eng.name_en if eng else "Project") if not ar else (
            (eng.name_ar or eng.name_en) if eng else "المشروع")  # fmt: skip
        team = [u for u in (refs.user(x) for x in [a.lead_auditor_id, *a.team_ids]) if u]
        names = ", ".join(e((u.full_name_ar or u.full_name_en) if ar else u.full_name_en)
                          for u in team)  # fmt: skip
        label = AUDIT_TYPES[a.audit_type][1 if ar else 0]
        rows = "".join(
            f"<tr><td>{e(s.section_code)}</td><td>{e(s.title_ar if ar else s.title_en)}</td>"
            f"<td>{e(s.score_pct or '—')}</td></tr>"
            for s in rr.section_scores
        )
        frows = "".join(
            f"<tr><td>{e(f.finding_no)}</td><td>{e(f.item_code or '')}</td>"
            f"<td>{e(f.severity.value)}</td>"
            f"<td>{e(_desc(f, ar))}</td></tr>"
            for f in findings
        )
        summary = (a.summary_ar or a.summary_en) if ar else (a.summary_en or a.summary_ar)
        h = (
            ("تقرير التدقيق", "النطاق", "الفريق", "النتيجة", "التقدير", "الأقسام", "الملاحظات")
            if ar
            else ("Audit report", "Scope", "Team", "Score", "Grade", "Sections", "Findings")
        )
        out.append(
            f'<!doctype html><html lang="{lang}" dir="{"rtl" if ar else "ltr"}"><head>'
            f'<meta charset="utf-8"><title>{e(a.audit_no)}</title></head><body>'
            f"<h1>{h[0]} {e(a.audit_no)}</h1><p>{e(label)}</p>"
            f"<p>{h[1]}: {e(scope)}</p><p>{h[2]}: {names}</p>"
            f"<p>{h[3]}: <bdi>{e(rr.score_pct or '—')} %</bdi> · {h[4]}: "
            f"{e(r.grade.value if r.grade else '—')}</p><p>{e(summary or '')}</p>"
            f"<h2>{h[5]}</h2><table>{rows}</table><h2>{h[6]}</h2><table>{frows}</table>"
            "</body></html>"
        )
    return out[0], out[1]


def _desc(f: FieldFinding, ar: bool) -> str:
    x = (f.description_ar or f.description_en) if ar else (f.description_en or f.description_ar)
    return x or ""


def close_issued(db: Session, project_id: uuid.UUID) -> int:
    """§4.4 Issued → Closed when every CA of the audit is Closed or Cancelled."""
    n = 0
    for a in db.scalars(
        select(FieldAudit).where(FieldAudit.project_id == project_id, FieldAudit.status == S.issued)
    ):
        open_cas = db.scalar(
            select(func.count())
            .select_from(CorrectiveAction)
            .where(
                CorrectiveAction.source_type == CaSourceType.field_audit,
                CorrectiveAction.source_id == a.id,
                CorrectiveAction.status.not_in((CaStatus.closed, CaStatus.cancelled)),
            )
        )
        if not open_cas:
            a.status = S.closed
            a.closed_at = now()
            fc.record(db, None, AuditAction.status_change, EntityType.field_audit, a,
                      project_id, before={"status": "issued"})  # fmt: skip
            n += 1
    db.flush()
    return n


# ---- programme (§3.8, §6.4, AUD-6, AUD-7) --------------------------------------------------------


@dataclass
class Line:
    scope: ProgrammeScope
    engagement_id: uuid.UUID | None
    audit_type: AuditType
    months: int
    start: date
    due_by: date
    last: FieldAudit | None = None
    items: list[tuple[date, FieldAudit | None]] = field(default_factory=list)


def _first_template_day(db: Session) -> date | None:
    at = db.scalar(
        select(func.min(ChecklistTemplate.published_at)).where(
            ChecklistTemplate.kind == TemplateKind.audit,
            ChecklistTemplate.published_at.is_not(None),
            ChecklistTemplate.status != VersionStatus.draft,
        )
    )
    return fc.local_day(at) if at else None


def lines(db: Session, project_id: uuid.UUID, as_of: date) -> list[Line]:
    from app.services.train.common import add_months  # noqa: PLC0415

    proj = db.get(Project, project_id)
    assert proj is not None  # noqa: S101
    c = fc.cfg(db, project_id)
    grace = int(c["first_audit_grace_days"])
    tday = _first_template_day(db)
    W = WorkforceReturn  # noqa: N806
    engs = set(
        db.scalars(
            select(W.engagement_id).where(
                W.project_id == project_id,
                W.headcount > 0,
                W.work_date > as_of - timedelta(days=90),
                W.work_date <= as_of,
            )
        )
    )
    audits = list(
        db.scalars(
            select(FieldAudit).where(
                FieldAudit.project_id == project_id,
                FieldAudit.status.in_(SATISFYING),
                FieldAudit.fieldwork_end.is_not(None),
            )
        )
    )
    specs: list[tuple[ProgrammeScope, uuid.UUID | None, AuditType, int, date]] = []
    for eid0 in engs:
        e = db.get(ProjectEngagement, eid0)
        if e is None:
            continue
        start = max(e.mobilisation_date, tday) if tday else e.mobilisation_date
        specs.append((ProgrammeScope.engagement, e.id, AuditType.contractor_hse,
                      int(c["contractor_audit_months"]), start))  # fmt: skip
    specs.append((ProgrammeScope.project, None, AuditType.system_iso45001,
                  int(c["system_audit_months"]), proj.start_date))  # fmt: skip
    out = []
    for scope, eid, at_, months, start in specs:
        mine = sorted(
            (
                a
                for a in audits
                if line_type(a) == at_ and (at_ == AuditType.system_iso45001 or
                                            a.auditee_engagement_id == eid)
            ),
            key=lambda a: (a.fieldwork_end, a.audit_no),
        )  # fmt: skip
        due = start + timedelta(days=grace)
        ln = Line(scope, eid, at_, months, start, due)
        for a in mine:
            assert a.fieldwork_end is not None  # noqa: S101
            ln.items.append((due, a))
            ln.last = a
            due = add_months(a.fieldwork_end, months) - timedelta(days=1)
        ln.due_by = due
        ln.items.append((due, None))
        out.append(ln)
    out.sort(key=lambda x: (x.scope != ProgrammeScope.project, str(x.engagement_id)))
    return out


def met_on_time(item: tuple[date, FieldAudit | None]) -> bool:
    due, a = item
    return a is not None and a.fieldwork_end is not None and a.fieldwork_end <= due


def programme(db: Session, p: Principal, project_id: uuid.UUID) -> AuditProgramme:
    fc.project(db, p, project_id)
    g = p.grant(project_id, C.field_audit_conduct) or fc.view_grant(p, project_id)
    as_of = fc.local_day()
    refs = Refs(db)
    rows = []
    for ln in lines(db, project_id, as_of):
        if g.engagement_ids is not None and ln.engagement_id not in g.engagement_ids:
            continue
        refs.load(engs=[ln.engagement_id])
        rows.append(
            ProgrammeLineRead(
                scope=ln.scope,
                engagement=refs.eng(ln.engagement_id),
                audit_type=ln.audit_type,
                frequency_months=ln.months,
                line_start=ln.start,
                due_by=ln.due_by,
                last_satisfied_by=ln.last.audit_no if ln.last else None,
                status=ProgrammeLineStatus.overdue
                if as_of > ln.due_by
                else ProgrammeLineStatus.due,
                items=[
                    ProgrammeItem(
                        due_by=d,
                        audit_no=a.audit_no if a else None,
                        fieldwork_end=a.fieldwork_end if a else None,
                        met_on_time=met_on_time((d, a)),
                    )
                    for d, a in ln.items
                    if d <= as_of
                ],
            )
        )
    return AuditProgramme(project_id=project_id, as_of=as_of, lines=rows)
