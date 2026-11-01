"""Quality audits on the 6d engine, the process register, the audit programme and management
reviews (spec 8-quality §E.2, Q-AUD-01…07, Q-MRV-01…03).

Quality audits are 6d `field_audits` rows with `domain = quality`: answers, scoring, grades,
findings and the report renderer are 6d's (`app.services.field.audits`); planning, conduct and
issue use capabilities 276 / 277 instead of 194 / 195, quality templates (kind `quality`,
`quality_type` q_audit or supplier_audit) and the Phase 8 number QAU (Q-AUD-01). At issue each
major / minor NC opens an NCR (source `q_audit_finding`) with the clause in the requirement; an
observation or OFI gets a CA (source `quality_audit`) only when the issuer asks; no 6d HSE CA
(Q-AUD-03). 6d's own lists, programme and K-114 / K-115 keep to `domain = hse` (Q-AUD-05)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Role
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import (
    QUALITY_AUDIT_TYPES,
    AuditDomain,
    AuditStatus,
    AuditType,
    FindingSeverity,
    TemplateKind,
    VersionStatus,
)
from app.core.hse_enums import AttachmentOwner, CaPriority, CaSourceType, ControlLevel
from app.core.quality.common import (
    QDetectionStage,
    QLinkKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QRecordType,
    QSectorProfile,
)
from app.core.quality.q4 import (
    MRV_INPUT_KEYS,
    MRV_INPUTS,
    QMrvStatus,
    QProgrammeStatus,
    QProgrammeSubject,
    QRevStatus,
    QRisk,
)
from app.models import (
    ChecklistResponse,
    ChecklistTemplate,
    FieldAudit,
    FieldFinding,
    Project,
    ProjectEngagement,
    RoleAssignment,
    Site,
    User,
)
from app.models.quality import QSupplier
from app.models.quality.q4 import (
    QAuditProgrammeLine,
    QDocument,
    QDocumentRevision,
    QManagementReview,
    QProcess,
)
from app.schemas.actions import CaInline
from app.services.field import audits as fa
from app.services.field import common as fc
from app.services.field import scoring
from app.services.permissions import Principal, build_principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, rpm
from app.services.quality import registry as reg
from app.services.quality.q4 import base as b
from app.services.scorecard import render

C = b.C
RT = QRecordType
S = AuditStatus
FS = FindingSeverity
NC_CLASS = {FS.major_nc: QNcrClass.major, FS.minor_nc: QNcrClass.minor}
QTYPES = ("q_audit", "supplier_audit")


# ---- processes ----------------------------------------------------------------------------------


def process_read(db: Session, x: QProcess, hide: bool = False) -> dict[str, Any]:
    return {
        "id": x.id,
        "project_id": x.project_id,
        "code": x.code,
        "name_en": x.name_en,
        "name_ar": x.name_ar,
        "owner": b.user_ref(db, x.owner_user_id, hide),
        "profile": x.profile,
        "risk": x.risk,
        "document_ids": list(x.document_ids or []),
        "active": x.active,
    }


def list_processes(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    b.viewer(db, p, project_id)
    hide = b.hide_names(p, project_id)
    rows = db.scalars(
        select(QProcess).where(QProcess.project_id == project_id).order_by(QProcess.code)
    )
    return [process_read(db, x, hide) for x in rows]


def save_process(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: dict[str, Any],
    pid: uuid.UUID | None = None,
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.quality_audit_conduct)
    if pid is not None:
        x = db.get(QProcess, pid)
        if x is None or x.project_id != project.id:
            raise not_found("Process")
    else:
        code = str(body.get("code") or "").strip().upper()
        if not code:
            raise qc.field_err("code", "Give the process code.", "أدخل رمز العملية.")
        if db.scalar(
            select(QProcess.id).where(QProcess.project_id == project.id, QProcess.code == code)
        ):
            raise qc.err(409, ErrorCode.DUPLICATE_VALUE, f"{code} exists.", "الرمز مستخدم.")
        x = QProcess(
            id=uuid.uuid4(), project_id=project.id, code=code, created_by_user_id=p.user.id
        )
        db.add(x)
    for k in ("name_en", "name_ar", "owner_user_id", "profile", "risk", "active"):
        if k in body and body[k] is not None:
            setattr(x, k, body[k])
    if "document_ids" in body:
        for did in body["document_ids"] or []:
            d = db.get(QDocument, did)
            if d is None or d.project_id != project.id:
                raise qc.field_err("document_ids", "Documents of the project.", "وثائق المشروع.")
        x.document_ids = list(body["document_ids"] or [])
    if not (x.name_en or "").strip():
        raise qc.field_err("name_en", "Give the process name.", "أدخل اسم العملية.")
    x.updated_by_user_id = p.user.id
    db.flush()
    return process_read(db, x)


# ---- audit programme (Q-AUD-06) ----------------------------------------------------------------


def months_for(freq: Decimal, year: int) -> list[int]:
    """Planned months for a frequency of audits per year (ASSUMPTION Q-AUD-06, D-363): 1 → 6;
    2 → 3 and 9; 3 → 2, 6, 10; 4 → 2, 5, 8, 11; below 1 → month 6 every round(1 ÷ f) years
    (even years for 0.5)."""
    if freq >= 1:
        n = min(int(freq.quantize(Decimal("1"), ROUND_HALF_UP)), 4)
        return {1: [6], 2: [3, 9], 3: [2, 6, 10], 4: [2, 5, 8, 11]}[n]
    every = max(int((1 / freq).quantize(Decimal("1"), ROUND_HALF_UP)), 1)
    return [6] if year % every == 0 else []


def generate_programme(db: Session, project: Project, year: int, by: uuid.UUID | None) -> int:
    """Lines per active process by risk (idempotent: a process keeps its existing lines)."""
    freq = b.setting(db, project.id, "q_audit_frequency") or {}
    prof = qc.profile_of(db, project.id)
    n = 0
    for x in db.scalars(
        select(QProcess).where(QProcess.project_id == project.id, QProcess.active.is_(True))
    ):
        if prof is not None and x.profile.value not in ("both", prof.value):
            continue
        has = db.scalar(
            select(QAuditProgrammeLine.id)
            .where(
                QAuditProgrammeLine.project_id == project.id,
                QAuditProgrammeLine.year == year,
                QAuditProgrammeLine.process_id == x.id,
                QAuditProgrammeLine.auto.is_(True),
            )
            .limit(1)
        )
        if has:
            continue
        f = Decimal(str(freq.get(x.risk.value, "1")))
        for m in months_for(f, year):
            db.add(
                QAuditProgrammeLine(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    year=year,
                    subject_kind=QProgrammeSubject.process,
                    process_id=x.id,
                    risk=x.risk,
                    planned_month=m,
                    status=QProgrammeStatus.planned,
                    auto=True,
                    created_by_user_id=by,
                    alerts_sent=[],
                )
            )
            n += 1
    db.flush()
    return n


def month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def line_on_time(db: Session, ln: QAuditProgrammeLine) -> bool:
    """Done on time ⇔ an issued audit linked to it has fieldwork_end ≤ the last day of the month."""
    a = db.get(FieldAudit, ln.audit_id) if ln.audit_id else None
    return (
        a is not None
        and a.status in (S.issued, S.closed)
        and a.fieldwork_end is not None
        and a.fieldwork_end <= month_end(ln.year, ln.planned_month)
    )


def line_read(db: Session, ln: QAuditProgrammeLine) -> dict[str, Any]:
    x = db.get(QProcess, ln.process_id) if ln.process_id else None
    a = db.get(FieldAudit, ln.audit_id) if ln.audit_id else None
    e = db.get(ProjectEngagement, ln.engagement_id) if ln.engagement_id else None
    return {
        "id": ln.id,
        "project_id": ln.project_id,
        "year": ln.year,
        "subject_kind": ln.subject_kind,
        "process_id": ln.process_id,
        "process_code": x.code if x else None,
        "process_name_en": x.name_en if x else None,
        "process_name_ar": x.name_ar if x else None,
        "supplier": b.supplier_ref(db, ln.supplier_id),
        "engagement_id": ln.engagement_id,
        "engagement_code": e.contractor.short_code if e else None,
        "clause_set": ln.clause_set,
        "risk": ln.risk,
        "planned_month": ln.planned_month,
        "audit_id": ln.audit_id,
        "audit_no": a.audit_no if a else None,
        "status": ln.status,
        "status_reason": ln.status_reason,
        "on_time": line_on_time(db, ln),
        "auto": ln.auto,
    }


def programme(db: Session, p: Principal, project_id: uuid.UUID, year: int) -> list[dict[str, Any]]:
    b.viewer(db, p, project_id)
    rows = db.scalars(
        select(QAuditProgrammeLine)
        .where(QAuditProgrammeLine.project_id == project_id, QAuditProgrammeLine.year == year)
        .order_by(QAuditProgrammeLine.planned_month, QAuditProgrammeLine.created_at)
    )
    return [line_read(db, ln) for ln in rows]


def programme_generate(
    db: Session, p: Principal, project_id: uuid.UUID, year: int
) -> list[dict[str, Any]]:
    project, _g = b.writer(db, p, project_id, C.quality_audit_conduct)
    generate_programme(db, project, year, p.user.id)
    return programme(db, p, project_id, year)


def add_line(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Supplier, subcontractor and clause-set audits are added by hand (Q-AUD-06)."""
    project, _g = b.writer(db, p, project_id, C.quality_audit_conduct)
    month = int(body["planned_month"])
    if not 1 <= month <= 12:
        raise qc.field_err("planned_month", "Month 1–12.", "الشهر من 1 إلى 12.")
    ln = QAuditProgrammeLine(
        id=uuid.uuid4(),
        project_id=project.id,
        year=int(body["year"]),
        subject_kind=QProgrammeSubject(body["subject_kind"]),
        process_id=body.get("process_id"),
        supplier_id=body.get("supplier_id"),
        engagement_id=body.get("engagement_id"),
        clause_set=body.get("clause_set"),
        risk=QRisk(body.get("risk") or "medium"),
        planned_month=month,
        status=QProgrammeStatus.planned,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(ln)
    db.flush()
    return line_read(db, ln)


def update_line(
    db: Session, p: Principal, line_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    ln = db.get(QAuditProgrammeLine, line_id)
    if ln is None:
        raise not_found("Programme line")
    b.writer(db, p, ln.project_id, C.quality_audit_conduct)
    st = QProgrammeStatus(body["status"]) if body.get("status") else None
    if st in (QProgrammeStatus.postponed, QProgrammeStatus.cancelled):
        ln.status_reason = qc.reason(body.get("reason"), 20)
        ln.status = st
    if body.get("planned_month"):
        ln.planned_month = int(body["planned_month"])
    db.flush()
    return line_read(db, ln)


def k158(db: Session, project_id: uuid.UUID, start: date, end: date, as_of: date) -> dict[str, int]:
    """K-158: lines done on time ÷ lines with planned month in the period and ended ≤ as_of."""
    den = num = 0
    for ln in db.scalars(
        select(QAuditProgrammeLine).where(
            QAuditProgrammeLine.project_id == project_id,
            QAuditProgrammeLine.status != QProgrammeStatus.cancelled,
            QAuditProgrammeLine.year >= start.year,
            QAuditProgrammeLine.year <= end.year,
        )
    ):
        last = month_end(ln.year, ln.planned_month)
        if not (start <= last <= end) or last > as_of:
            continue
        den += 1
        num += line_on_time(db, ln)
    return {"lines": den, "on_time": num}


# ---- quality audits on 6d ----------------------------------------------------------------------


def _get(db: Session, p: Principal, audit_id: uuid.UUID) -> FieldAudit:
    a = db.get(FieldAudit, audit_id)
    if a is None or a.domain != AuditDomain.quality or not p.can_see_project(a.project_id):
        raise not_found("Quality audit")
    team = p.user.id == a.lead_auditor_id or p.user.id in (a.team_ids or [])
    g = p.grant(a.project_id, C.quality_view)
    if team or (g is not None and g.scope != b.S.responsible):
        return a
    project = db.get(Project, a.project_id)
    if project is not None and rpm.resolves(
        db, p, project, RT.q_audit, "issue", _ctx(a), record_id=a.id, can_act=False
    ):
        return a
    raise not_found("Quality audit")


def _site(a: FieldAudit) -> uuid.UUID | None:
    return a.site_ids[0] if a.site_ids else None


def _ctx(a: FieldAudit) -> rpm.Ctx:
    return rpm.Ctx(
        site_id=_site(a),
        engagement_id=a.auditee_engagement_id,
        requesters=frozenset({a.lead_auditor_id}),
    )


def audit_read(db: Session, p: Principal | None, a: FieldAudit) -> dict[str, Any]:
    base_ = fa.audit_read(db, p, a).model_dump()
    hide = b.hide_names(p, a.project_id) if p else False
    if hide:
        base_["lead_auditor"] = None
        base_["team"] = []
        base_["issued_by"] = None
    procs = [db.get(QProcess, x) for x in a.process_ids or []]
    days = int(b.setting(db, a.project_id, "q_audit_report_days"))
    project = db.get(Project, a.project_id)
    can_issue = False
    if p is not None and project is not None and a.status == S.fieldwork_complete:
        can_issue = p.user.id != a.lead_auditor_id and rpm.resolves(
            db, p, project, RT.q_audit, "issue", _ctx(a), record_id=a.id
        )
    ncrs = [
        {"id": ln.from_id}
        for ln in db.scalars(
            select(reg_link()).where(
                reg_link().to_type == RT.q_audit.value,
                reg_link().to_id == a.id,
                reg_link().from_type == RT.ncr.value,
            )
        )
    ]
    return {
        **base_,
        "domain": a.domain,
        "auditee_supplier": b.supplier_ref(db, a.auditee_supplier_id),
        "processes": [
            {"id": x.id, "code": x.code, "name_en": x.name_en, "name_ar": x.name_ar}
            for x in procs
            if x
        ],
        "report_due_by": a.fieldwork_end + timedelta(days=days) if a.fieldwork_end else None,
        "can_issue": can_issue,
        "ncr_ids": [x["id"] for x in ncrs],
    }


def reg_link() -> Any:
    from app.models.quality import QLink  # noqa: PLC0415

    return QLink


def list_audits(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[S] | None,
    page_no: int,
    size: int,
) -> dict[str, Any]:
    g = b.viewer(db, p, project_id, allow_n=True)
    stmt = select(FieldAudit).where(
        FieldAudit.project_id == project_id, FieldAudit.domain == AuditDomain.quality
    )
    if statuses:
        stmt = stmt.where(FieldAudit.status.in_(statuses))
    rows = list(
        db.scalars(stmt.order_by(FieldAudit.planned_start.desc(), FieldAudit.audit_no.desc()))
    )
    if g.scope == b.S.responsible:
        rows = [a for a in rows if _visible_n(db, p, a)]
    return b.page([audit_read(db, p, a) for a in rows], page_no, size)


def _visible_n(db: Session, p: Principal, a: FieldAudit) -> bool:
    try:
        _get(db, p, a.id)
    except Exception:
        return False
    return True


def read_audit(db: Session, p: Principal, audit_id: uuid.UUID) -> dict[str, Any]:
    return audit_read(db, p, _get(db, p, audit_id))


def _template(db: Session, code: str, project_id: uuid.UUID) -> ChecklistTemplate:
    from app.services.field import library  # noqa: PLC0415

    t = library.published(db, code)
    if t is None or t.kind != TemplateKind.quality or t.quality_type not in QTYPES:
        raise qc.err(
            422,
            ErrorCode.TEMPLATE_NOT_APPLICABLE,
            "Use a Published quality audit checklist (kind quality, type q_audit or "
            "supplier_audit) (Q-AUD-01).",
            "استخدم قائمة تدقيق جودة منشورة.",
            field="template_code",
        )
    return t


def _auditor(db: Session, project: Project, uid: uuid.UUID, fld: str) -> None:
    u = db.get(User, uid)
    if u is None:
        raise validation_error(fld, "Unknown user.")
    if build_principal(db, u, None).grant(project.id, C.quality_audit_conduct) is None:
        raise validation_error(fld, "Auditors hold capability 276 on the project.")


def _sod(en: str, fld: str) -> Any:
    return qc.err(
        422, ErrorCode.SOD_CONFLICT, en, "تعارض في استقلالية المدقق (ISO 19011).", field=fld
    )


def _independent(
    db: Session,
    project: Project,
    uid: uuid.UUID,
    fld: str,
    procs: list[QProcess],
    eng: uuid.UUID | None,
    supplier: QSupplier | None,
) -> None:
    """Q-AUD-02: not the owner of an audited process, not employed by the auditee engagement or
    supplier (contractor link), not the author of the audited documents' current revisions."""
    for x in procs:
        if x.owner_user_id == uid:
            raise _sod(f"The auditor owns process {x.code} (Q-AUD-02).", fld)
        for did in x.document_ids or []:
            d = db.get(QDocument, did)
            r = (
                db.get(QDocumentRevision, d.current_revision_id)
                if d and d.current_revision_id
                else None
            )
            if r is not None and r.author_user_id == uid:
                raise _sod(f"The auditor wrote {d.doc_no} Rev.{r.rev_code} (Q-AUD-02).", fld)  # type: ignore[union-attr]
    engs = {
        x.contractor_engagement_id
        for x in db.scalars(
            select(RoleAssignment).where(
                RoleAssignment.user_id == uid,
                RoleAssignment.project_id == project.id,
                RoleAssignment.revoked_at.is_(None),
            )
        )
    } - {None}
    if eng is not None and eng in engs:
        raise _sod("The auditor is employed by the auditee (Q-AUD-02).", fld)
    if supplier is not None and supplier.contractor_id is not None:
        cids = set(
            db.scalars(
                select(ProjectEngagement.contractor_id).where(ProjectEngagement.id.in_(list(engs)))
            )
        )
        if supplier.contractor_id in cids:
            raise _sod("The auditor is employed by the audited supplier (Q-AUD-02).", fld)


def _competence(db: Session, project: Project, uid: uuid.UUID, day: date) -> list[dict[str, Any]]:
    v = reg.competence_check(db, uid, "QMS-AUDITOR", day)
    if v.met is False:
        if b.setting(db, project.id, "competence_policy") == "block":
            raise qc.err(422, ErrorCode.COMPETENCE_NOT_MET, v.detail_en, v.detail_ar)
        return [
            qc.warning(
                ErrorCode.COMPETENCE_NOT_MET, v.detail_en, v.detail_ar, "lead_auditor_id"
            ).model_dump()
        ]
    return []


def create_audit(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.quality_audit_conduct)
    at = AuditType(body["audit_type"])
    if at not in QUALITY_AUDIT_TYPES:
        raise validation_error("audit_type", "Use a quality audit type (Q-AUD-01).")
    t = _template(db, body["template_code"], project.id)
    procs = []
    for pid in body.get("process_ids") or []:
        x = db.get(QProcess, pid)
        if x is None or x.project_id != project.id:
            raise validation_error("process_ids", "Processes of the project.")
        procs.append(x)
    sup = (
        db.get(QSupplier, body["auditee_supplier_id"]) if body.get("auditee_supplier_id") else None
    )
    if at == AuditType.supplier_quality and sup is None:
        raise validation_error("auditee_supplier_id", "A supplier audit names the supplier.")
    eng = body.get("auditee_engagement_id")
    if at == AuditType.subcontractor_quality and eng is None:
        raise validation_error(
            "auditee_engagement_id", "A subcontractor audit names the engagement."
        )
    if eng is not None:
        e = db.get(ProjectEngagement, eng)
        if e is None or e.project_id != project.id:
            raise validation_error("auditee_engagement_id", "Not an engagement of the project.")
    sites = list(body.get("site_ids") or [])
    for s in sites:
        site = db.get(Site, s)
        if site is None or site.project_id != project.id:
            raise validation_error("site_ids", "Sites of the project.")
    if not sites:
        first = db.scalar(
            select(Site.id).where(Site.project_id == project.id).order_by(Site.code).limit(1)
        )
        sites = [first] if first else []
    ps, pe = body["planned_start"], body["planned_end"]
    if pe < ps or (pe - ps).days > 9:
        raise validation_error("planned_end", "End ≥ start and at most 10 days.")
    lead = body["lead_auditor_id"]
    team = [x for x in dict.fromkeys(body.get("team_ids") or []) if x != lead]
    _independent(db, project, lead, "lead_auditor_id", procs, eng, sup)  # SoD first (AC-Q4-08)
    _auditor(db, project, lead, "lead_auditor_id")
    for i, uid in enumerate(team):
        _independent(db, project, uid, f"team_ids[{i}]", procs, eng, sup)
        _auditor(db, project, uid, f"team_ids[{i}]")
    warnings = _competence(db, project, lead, ps)
    year = ps.year
    seq = fc.next_seq(db, FieldAudit, project.id, year)
    a = FieldAudit(
        id=uuid.uuid4(),
        audit_no=b.number(db, project, RT.q_audit),
        year=year,
        seq=seq,
        project_id=project.id,
        audit_type=at,
        template_code=t.template_code,
        template_id=t.id,
        auditee_engagement_id=eng,
        site_ids=sites,
        lead_auditor_id=lead,
        team_ids=team,
        planned_start=ps,
        planned_end=pe,
        status=S.planned,
        created_by_user_id=p.user.id,
        domain=AuditDomain.quality,
        auditee_supplier_id=sup.id if sup else None,
        process_ids=[x.id for x in procs],
        alerts_sent=[],
    )
    db.add(a)
    db.flush()
    if body.get("programme_line_id"):
        ln = db.get(QAuditProgrammeLine, body["programme_line_id"])
        if ln is None or ln.project_id != project.id:
            raise validation_error("programme_line_id", "A programme line of the project.")
        ln.audit_id = a.id
        ln.status = QProgrammeStatus.scheduled
    b.record(db, p, AuditAction.create, RT.q_audit, a, project.id, details={"audit_no": a.audit_no})
    out = audit_read(db, p, a)
    out["warnings"] = warnings
    return out


def _conductor(p: Principal, a: FieldAudit) -> None:
    team = p.user.id == a.lead_auditor_id or p.user.id in (a.team_ids or [])
    if not team and not p.is_manager:
        raise forbidden_error("Only the audit team records the audit.")
    p.require(a.project_id, C.quality_audit_conduct)


def update_audit(
    db: Session, p: Principal, audit_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    a = _get(db, p, audit_id)
    b.writer(db, p, a.project_id, C.quality_audit_conduct)
    _conductor(p, a)
    if a.status not in (S.planned, S.in_progress, S.fieldwork_complete):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The audit is closed for edits.",
            "التدقيق مغلق للتعديل.",
        )
    for k in (
        "fieldwork_start",
        "fieldwork_end",
        "opening_meeting_at",
        "closing_meeting_at",
        "summary_en",
        "summary_ar",
        "auditee_attendee_roles",
    ):
        if k in body:
            setattr(a, k, body[k])
    if a.fieldwork_start and a.fieldwork_end and a.fieldwork_end < a.fieldwork_start:
        raise validation_error("fieldwork_end", "End ≥ start.")
    if a.status == S.planned and a.opening_meeting_at is not None:
        a.status = S.in_progress
    a.updated_at = now()
    db.flush()
    return audit_read(db, p, a)


def save_answers(db: Session, p: Principal, audit_id: uuid.UUID, body: Any) -> dict[str, Any]:
    a = _get(db, p, audit_id)
    project, _g = b.writer(db, p, a.project_id, C.quality_audit_conduct)
    _conductor(p, a)
    if a.status not in (S.planned, S.in_progress):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Answers are recorded during fieldwork.",
            "تسجل الإجابات أثناء العمل الميداني.",
        )
    fa.apply_answers(db, project, a, body.answers, body.manual_findings, p.user.id)
    if a.status == S.planned:
        a.status = S.in_progress
    db.flush()
    return audit_read(db, p, a)


def complete_fieldwork(db: Session, p: Principal, audit_id: uuid.UUID) -> dict[str, Any]:
    a = _get(db, p, audit_id)
    b.writer(db, p, a.project_id, C.quality_audit_conduct)
    if p.user.id != a.lead_auditor_id and not p.is_manager:
        raise forbidden_error("The lead auditor completes the fieldwork.")
    if a.status != S.in_progress:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The audit is not in progress.",
            "التدقيق ليس قيد التنفيذ.",
        )
    if a.closing_meeting_at is None:
        raise validation_error("closing_meeting_at", "Record the closing meeting.")
    if a.fieldwork_start is None or a.fieldwork_end is None:
        raise validation_error("fieldwork_end", "Record the fieldwork dates.")
    r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
    t = db.get(ChecklistTemplate, a.template_id) if a.template_id else None
    if r is None or t is None:
        raise validation_error("answers", "Answer every item first.")
    scoring.evaluate(t.items, r.answers, True, require_all=True, audit=True)
    r.completed_at = now()
    r.completed_date = a.fieldwork_end
    r.received_at = now()
    r.submitted = True
    for f in db.scalars(select(FieldFinding).where(FieldFinding.response_id == r.id)):
        f.completed_date = a.fieldwork_end
    a.status = S.fieldwork_complete
    db.flush()
    return audit_read(db, p, a)


def _clause(t: ChecklistTemplate | None, code: str | None) -> str:
    it = next((x for x in (t.items if t else []) if x.get("item_code") == code), None)
    return str((it or {}).get("reference") or "")


def issue(db: Session, p: Principal, audit_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Q-AUD-03 / -04: 277 + RPM `q_audit.issue`, not the lead auditor; NCRs per NC; CAs for
    observations / OFIs only when asked; EN / AR report with the Hijri date."""
    a = _get(db, p, audit_id)
    project, _g = b.writer(db, p, a.project_id, C.quality_audit_issue, allow_n=True)
    if a.status != S.fieldwork_complete:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Complete the fieldwork first.",
            "أكمل العمل الميداني أولاً.",
        )
    if p.user.id == a.lead_auditor_id:
        raise _sod("The lead auditor cannot issue their own report (Q-AUD-04).", "lead_auditor_id")
    if not ((a.summary_en or "").strip() or (a.summary_ar or "").strip()):
        raise validation_error("summary_en", "Write the summary before issuing.")
    b.sign(
        db,
        p,
        project,
        RT.q_audit,
        a.id,
        "issue",
        _ctx(a),
        decision="approved",
        comment=body.get("comment"),
    )
    r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
    assert r is not None  # noqa: S101
    findings = list(
        db.scalars(
            select(FieldFinding)
            .where(FieldFinding.response_id == r.id)
            .order_by(FieldFinding.finding_no)
        )
    )
    from app.services.quality.ncr import core as ncr_core  # noqa: PLC0415

    owner = b.ncr_owner(db, project, p.user.id)
    want_ca = bool(body.get("ca_for_observations"))
    for f in findings:
        if f.severity in NC_CLASS:
            n = ncr_core.auto_raise(
                db,
                project,
                QNcrSourceType.q_audit_finding,
                f.id,
                raised_by=p.user.id,
                owner_id=owner,
                classification=NC_CLASS[f.severity],
                category=QNcrCategory.other,
                title=f"{a.audit_no} {f.finding_no}: "
                f"{(f.description_en or f.description_ar or '')[:80]}",
            )
            links.add(
                db, project.id, RT.ncr, n.id, RT.q_audit, a.id, QLinkKind.raised_from, p.user.id
            )
        elif want_ca and f.severity in (FS.observation, FS.ofi):
            ca = _audit_ca(db, p, project, a, f)
            f.ca_id = ca.id
    a.issued_by_user_id = p.user.id
    a.issued_at = now()
    a.status = S.issued
    db.flush()
    doc = fa.report_doc(db, a, r, findings)
    a.report_en_id, a.report_ar_id = b.store_pdfs(
        db, AttachmentOwner.q_audit_report, a.id, project.id, doc, a.audit_no, p.user.id
    )
    for ln in db.scalars(select(QAuditProgrammeLine).where(QAuditProgrammeLine.audit_id == a.id)):
        ln.status = QProgrammeStatus.done
    db.flush()
    b.record(db, p, AuditAction.status_change, RT.q_audit, a, project.id, details={"to": "issued"})
    return audit_read(db, p, a)


def _audit_ca(db: Session, p: Principal, project: Project, a: FieldAudit, f: FieldFinding) -> Any:
    from app.services import corrective_actions as ca_svc  # noqa: PLC0415

    procs = [db.get(QProcess, x) for x in a.process_ids or []]
    owner = (
        next((x.owner_user_id for x in procs if x and x.owner_user_id), None) or a.lead_auditor_id
    )
    verifier = p.user.id if p.user.id != owner else a.lead_auditor_id
    eng = a.auditee_engagement_id or b.operator_engagement(db, project)
    inline = CaInline(
        title=f"{a.audit_no} {f.finding_no}"[:150],
        description=(f.description_en or f.description_ar or f.finding_no)[:2000],
        control_level=ControlLevel.administrative,
        priority=CaPriority.low,
        owner_id=owner,
        verifier_id=verifier,
        responsible_engagement_id=eng,
    )
    ca, _w = ca_svc.new_ca(db, p, project, inline, CaSourceType.quality_audit, a, site_id=_site(a))
    return ca


def cancel_or_void(
    db: Session, p: Principal, audit_id: uuid.UUID, action: str, reason: str | None
) -> dict[str, Any]:
    a = _get(db, p, audit_id)
    if action == "cancel":
        b.writer(db, p, a.project_id, C.quality_audit_conduct)
        if a.status != S.planned:
            raise qc.err(
                409,
                ErrorCode.INVALID_TRANSITION,
                "Only a planned audit is cancelled.",
                "يُلغى التدقيق المخطط فقط.",
            )
        a.status = S.cancelled
    else:
        b.writer(db, p, a.project_id, C.quality_void)
        if a.status not in (S.in_progress, S.fieldwork_complete, S.issued):
            raise qc.err(
                409,
                ErrorCode.INVALID_TRANSITION,
                "This audit cannot be voided.",
                "لا يمكن إلغاء هذا التدقيق.",
            )
        a.status = S.voided
        r = db.get(ChecklistResponse, a.response_id) if a.response_id else None
        if r is not None:
            r.voided = True
    a.status_reason = qc.reason(reason, 20)
    for ln in db.scalars(select(QAuditProgrammeLine).where(QAuditProgrammeLine.audit_id == a.id)):
        ln.audit_id = None
        ln.status = QProgrammeStatus.planned
    db.flush()
    return audit_read(db, p, a)


def finding_source(db: Session, project: Project, finding_id: uuid.UUID) -> reg.SourceInfo:
    """`NCR_SOURCES[q_audit_finding]`: the finding's audit, clause and auditee."""
    f = db.get(FieldFinding, finding_id)
    r = db.get(ChecklistResponse, f.response_id) if f else None
    a = db.get(FieldAudit, r.audit_id) if r and r.audit_id else None
    if f is None or a is None or a.project_id != project.id:
        raise validation_error("source_id", "The audit finding is not on this project.")
    t = db.get(ChecklistTemplate, a.template_id) if a.template_id else None
    clause = _clause(t, f.item_code)
    item = next((x for x in (t.items if t else []) if x.get("item_code") == f.item_code), {})
    req_en = (
        f"ISO 9001:2015 {clause}: {item.get('text_en', '')}".strip()
        if clause
        else item.get("text_en")
    )
    req_ar = (
        f"ISO 9001:2015 {clause}: {item.get('text_ar', '')}".strip()
        if clause
        else item.get("text_ar")
    )
    return reg.SourceInfo(
        ref=f.finding_no,
        title=f"{a.audit_no} {f.finding_no}",
        site_id=_site(a),
        engagement_id=a.auditee_engagement_id or b.operator_engagement(db, project),
        supplier_id=a.auditee_supplier_id,
        detection_stage=QDetectionStage.internal_audit,
        requirement_en=(req_en or "")[:1000] or None,
        requirement_ar=(req_ar or "")[:1000] or None,
        finding_en=f.description_en,
        finding_ar=f.description_ar,
        proposed_class=NC_CLASS.get(f.severity),
        item_key=f"audit:{f.item_code or f.finding_no}",
    )


def finding_visible(db: Session, p: Principal, finding_id: uuid.UUID) -> bool:
    f = db.get(FieldFinding, finding_id)
    r = db.get(ChecklistResponse, f.response_id) if f else None
    if r is None or r.audit_id is None:
        return False
    try:
        _get(db, p, r.audit_id)
    except Exception:
        return False
    return True


def audit_counts(db: Session, project_id: uuid.UUID, start: date, end: date) -> dict[str, int]:
    """K-158 chips: major / minor NC findings of quality audits issued in the period."""
    major = minor = 0
    for f, a in db.execute(
        select(FieldFinding, FieldAudit)
        .join(ChecklistResponse, ChecklistResponse.id == FieldFinding.response_id)
        .join(FieldAudit, FieldAudit.id == ChecklistResponse.audit_id)
        .where(
            FieldAudit.project_id == project_id,
            FieldAudit.domain == AuditDomain.quality,
            FieldAudit.status.in_((S.issued, S.closed)),
            FieldFinding.voided.is_(False),
        )
    ):
        day = b.local_day(a.issued_at) if a.issued_at else None
        if day is None or not start <= day <= end:
            continue
        major += f.severity == FS.major_nc
        minor += f.severity == FS.minor_nc
    return {"major_nc": major, "minor_nc": minor}


# ---- management review (§E.2.2) ----------------------------------------------------------------


def _mrv(db: Session, p: Principal, mid: uuid.UUID) -> QManagementReview:
    m = db.get(QManagementReview, mid)
    if m is None or not p.can_see_project(m.project_id):
        raise not_found("Management review")
    g = p.grant(m.project_id, C.quality_view)
    if g is None or g.scope == b.S.responsible:
        project = db.get(Project, m.project_id)
        if project is None or not rpm.resolves(
            db, p, project, RT.management_review, "approve", _mctx(m), record_id=m.id, can_act=False
        ):
            raise not_found("Management review")
    return m


def _mctx(m: QManagementReview) -> rpm.Ctx:
    return rpm.Ctx(requesters=frozenset(qc.ids(m.created_by_user_id)))


def mrv_read(db: Session, p: Principal | None, m: QManagementReview) -> dict[str, Any]:
    hide = b.hide_names(p, m.project_id) if p else False
    project = db.get(Project, m.project_id)
    can_issue = bool(
        p is not None
        and project is not None
        and m.status == QMrvStatus.held
        and rpm.resolves(db, p, project, RT.management_review, "approve", _mctx(m), record_id=m.id)
    )
    return {
        "id": m.id,
        "project_id": m.project_id,
        "mrv_no": m.mrv_no,
        "period_start": m.period_start,
        "period_end": m.period_end,
        "held_on": m.held_on,
        "chair": b.user_ref(db, m.chair_user_id, hide),
        "attendees": [] if hide else [b.user_ref(db, u) for u in m.attendee_user_ids or []],
        "external_attendees": [] if hide else list(m.external_attendees or []),
        "inputs": [
            {"key": k, "label_en": en, "label_ar": ar, **(m.inputs or {}).get(k, {})}
            for k, en, ar in MRV_INPUTS
        ],
        "kpi_snapshot": m.kpi_snapshot,
        "outputs": list(m.outputs or []),
        "minutes_en_id": m.minutes_en_id,
        "minutes_ar_id": m.minutes_ar_id,
        "status": m.status,
        "can_issue": can_issue,
    }


def list_mrv(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    b.viewer(db, p, project_id)
    rows = db.scalars(
        select(QManagementReview)
        .where(QManagementReview.project_id == project_id)
        .order_by(QManagementReview.period_end.desc())
    )
    return [mrv_read(db, p, m) for m in rows]


def read_mrv(db: Session, p: Principal, mid: uuid.UUID) -> dict[str, Any]:
    return mrv_read(db, p, _mrv(db, p, mid))


def create_mrv(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.quality_audit_conduct)
    if body["period_end"] < body["period_start"]:
        raise validation_error("period_end", "End ≥ start.")
    m = QManagementReview(
        id=uuid.uuid4(),
        project_id=project.id,
        period_start=body["period_start"],
        period_end=body["period_end"],
        chair_user_id=body.get("chair_user_id") or p.user.id,
        attendee_user_ids=list(body.get("attendee_user_ids") or []),
        external_attendees=list(body.get("external_attendees") or []),
        inputs={},
        outputs=[],
        status=QMrvStatus.draft,
        created_by_user_id=p.user.id,
    )
    m.mrv_no = b.number(db, project, RT.management_review)
    db.add(m)
    db.flush()
    b.record(db, p, AuditAction.create, RT.management_review, m, project.id)
    return mrv_read(db, p, m)


def update_mrv(db: Session, p: Principal, mid: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    m = _mrv(db, p, mid)
    project, _g = b.writer(db, p, m.project_id, C.quality_audit_conduct)
    if m.status == QMrvStatus.minutes_issued:
        raise qc.err(409, ErrorCode.INVALID_TRANSITION, "The minutes are issued.", "صدر المحضر.")
    if m.status == QMrvStatus.draft:
        inputs = dict(m.inputs or {})
        for k, v in (body.get("inputs") or {}).items():
            if k not in MRV_INPUT_KEYS:
                raise qc.field_err("inputs", f"Unknown input {k}.", "مدخل غير معروف.")
            inputs[k] = {
                "note": (v or {}).get("note"),
                "not_applicable": bool((v or {}).get("not_applicable")),
            }
        m.inputs = inputs
        for k in ("chair_user_id", "held_on"):
            if body.get(k):
                setattr(m, k, body[k])
        if "attendee_user_ids" in body:
            m.attendee_user_ids = list(body["attendee_user_ids"] or [])
        if "external_attendees" in body:
            m.external_attendees = list(body["external_attendees"] or [])
    if "outputs" in body:
        outs = []
        old = {str(o.get("id")): o for o in m.outputs or []}
        for o in body["outputs"] or []:
            oid = str(o.get("id") or uuid.uuid4())
            prev = old.get(oid, {})
            row = {
                "id": oid,
                "kind": o.get("kind") or "improvement",
                "text": o["text"],
                "owner_user_id": str(o["owner_user_id"]) if o.get("owner_user_id") else None,
                "due_date": str(o["due_date"]) if o.get("due_date") else None,
                "ca_id": prev.get("ca_id"),
            }
            if o.get("create_ca") and not row["ca_id"]:
                row["ca_id"] = str(_mrv_ca(db, p, project, m, row).id)
            outs.append(row)
        m.outputs = outs
    m.updated_by_user_id = p.user.id
    db.flush()
    return mrv_read(db, p, m)


def _mrv_ca(
    db: Session, p: Principal, project: Project, m: QManagementReview, o: dict[str, Any]
) -> Any:
    from app.services import corrective_actions as ca_svc  # noqa: PLC0415

    owner = (
        uuid.UUID(o["owner_user_id"]) if o.get("owner_user_id") else (m.chair_user_id or p.user.id)
    )
    verifier = m.chair_user_id if m.chair_user_id and m.chair_user_id != owner else p.user.id
    site = db.scalar(
        select(Site.id).where(Site.project_id == project.id).order_by(Site.code).limit(1)
    )
    inline = CaInline(
        title=f"{m.mrv_no}: {o['text']}"[:150],
        description=o["text"][:2000],
        control_level=ControlLevel.administrative,
        priority=CaPriority.medium,
        owner_id=owner,
        verifier_id=verifier,
        responsible_engagement_id=b.operator_engagement(db, project),
        due_date=date.fromisoformat(o["due_date"]) if o.get("due_date") else None,
    )
    ca, _w = ca_svc.new_ca(db, p, project, inline, CaSourceType.quality_review, m, site_id=site)
    return ca


def hold_mrv(db: Session, p: Principal, mid: uuid.UUID, held_on: date | None) -> dict[str, Any]:
    """Draft → Held: every input answered (Q-MRV-01); the KPI snapshot is frozen (Q-MRV-02)."""
    from app.kpi import quality as qk  # noqa: PLC0415

    m = _mrv(db, p, mid)
    project, _g = b.writer(db, p, m.project_id, C.quality_audit_conduct)
    if m.status != QMrvStatus.draft:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a Draft review is held.",
            "تُعقد المراجعة المسودة فقط.",
        )
    missing = [
        k
        for k in MRV_INPUT_KEYS
        if not (
            (m.inputs or {}).get(k, {}).get("not_applicable")
            or ((m.inputs or {}).get(k, {}).get("note") or "").strip()
        )
    ]
    if missing:
        raise qc.err(
            422,
            ErrorCode.MRV_INPUTS_INCOMPLETE,
            f"Answer every input heading (missing: {', '.join(missing)}) (Q-MRV-01).",
            "أجب عن كل عناوين المدخلات.",
            missing=missing,
        )
    m.held_on = held_on or m.held_on or b.today(project)
    m.kpi_snapshot = qk.snapshot(db, project, m.period_start, m.period_end)
    m.status = QMrvStatus.held
    db.flush()
    b.record(
        db,
        p,
        AuditAction.status_change,
        RT.management_review,
        m,
        project.id,
        details={"to": "held"},
    )
    return mrv_read(db, p, m)


def minutes_doc(db: Session, m: QManagementReview, project: Project) -> render.Doc:
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415

    day = b.local_day(m.issued_at) if m.issued_at else b.today(project)
    chair = db.get(User, m.chair_user_id) if m.chair_user_id else None
    ctl: list[tuple[str, ...]] = [
        ("Review", "المراجعة", m.mrv_no or "—"),
        ("Project", "المشروع", project.code),
        ("Period", "الفترة", f"{m.period_start.isoformat()} – {m.period_end.isoformat()}"),
        ("Held on", "تاريخ الانعقاد", m.held_on.isoformat() if m.held_on else "—"),
        (
            "Chair",
            "الرئيس",
            chair.full_name_en if chair else "—",
            (chair.full_name_ar or chair.full_name_en) if chair else "—",
        ),
        *b.issue_dates(day),
    ]
    rows = [
        {
            "h": en,
            "v": (
                "Not applicable"
                if (m.inputs or {}).get(k, {}).get("not_applicable")
                else (m.inputs or {}).get(k, {}).get("note") or ""
            ),
        }
        for k, en, _ar in MRV_INPUTS
    ]
    rows_ar = [
        {
            "h": ar,
            "v": (
                "غير منطبق"
                if (m.inputs or {}).get(k, {}).get("not_applicable")
                else (m.inputs or {}).get(k, {}).get("note") or ""
            ),
        }
        for k, _en, ar in MRV_INPUTS
    ]
    kpi_rows = [
        {
            "k": x["kpi"],
            "n": x["name_en"],
            "v": x.get("display") or "—",
            "t": x.get("target") or "—",
        }
        for x in (m.kpi_snapshot or {}).get("kpis", [])
    ]
    kpi_rows_ar = [
        {
            "k": x["kpi"],
            "n": x["name_ar"],
            "v": x.get("display") or "—",
            "t": x.get("target") or "—",
        }
        for x in (m.kpi_snapshot or {}).get("kpis", [])
    ]
    out_rows = [
        {"k": o.get("kind"), "t": o.get("text"), "ca": o.get("ca_id") or ""}
        for o in m.outputs or []
    ]
    secs = [
        b.section(
            "inputs",
            "Inputs (ISO 9001 9.3.2)",
            "المدخلات (ISO 9001 9.3.2)",
            tables=[
                b.table([("h", "Heading", "العنوان"), ("v", "Note", "الملاحظة")], rows, rows_ar)
            ],
        ),
        b.section(
            "kpis",
            "Quality KPIs (frozen)",
            "مؤشرات الجودة (مجمدة)",
            tables=[
                b.table(
                    [
                        ("k", "KPI", "المؤشر"),
                        ("n", "Name", "الاسم"),
                        ("v", "Value", "القيمة"),
                        ("t", "Target", "المستهدف"),
                    ],
                    kpi_rows,
                    kpi_rows_ar,
                )
            ],
        ),
        b.section(
            "outputs",
            "Outputs (9.3.3)",
            "المخرجات (9.3.3)",
            tables=[
                b.table(
                    [("k", "Kind", "النوع"), ("t", "Decision", "القرار"), ("ca", "CA", "الإجراء")],
                    out_rows,
                )
            ],
        ),
    ]
    digest = hashlib.sha256(
        json.dumps([ctl, rows, kpi_rows, out_rows], default=str).encode()
    ).hexdigest()
    return render.Doc(
        doc_no=m.mrv_no or "MRV",
        revision=0,
        title_en=f"Management review {m.mrv_no}",
        title_ar=f"مراجعة الإدارة {m.mrv_no}",
        snapshot_hash=digest,
        control=ctl,
        sections=secs,
    )


def issue_minutes(db: Session, p: Principal, mid: uuid.UUID, comment: str | None) -> dict[str, Any]:
    m = _mrv(db, p, mid)
    project, _g = b.writer(db, p, m.project_id, C.quality_audit_issue, allow_n=True)
    if m.status != QMrvStatus.held:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Hold the review first.", "اعقد المراجعة أولاً."
        )
    b.sign(
        db,
        p,
        project,
        RT.management_review,
        m.id,
        "approve",
        _mctx(m),
        decision="approved",
        comment=comment,
    )
    m.issued_at = now()
    m.status = QMrvStatus.minutes_issued
    db.flush()
    m.minutes_en_id, m.minutes_ar_id = b.store_pdfs(
        db,
        AttachmentOwner.q_mgmt_review,
        m.id,
        project.id,
        minutes_doc(db, m, project),
        m.mrv_no or "MRV",
        p.user.id,
    )
    db.flush()
    b.record(
        db,
        p,
        AuditAction.status_change,
        RT.management_review,
        m,
        project.id,
        details={"to": "minutes_issued"},
    )
    return mrv_read(db, p, m)


# ---- jobs ----------------------------------------------------------------------------------------


def alerts(db: Session, at: Any) -> dict[str, int]:
    """Audit lines due 30 / 0 days (process owner, lead auditor); audit report overdue (lead and
    239 holders) after `q_audit_report_days` (as 6d AUD-5)."""
    n = 0
    for ln in db.scalars(
        select(QAuditProgrammeLine).where(
            QAuditProgrammeLine.status.in_((QProgrammeStatus.planned, QProgrammeStatus.scheduled))
        )
    ):
        project = db.get(Project, ln.project_id)
        if project is None:
            continue
        day = qc.project_day(project, at)
        first = date(ln.year, ln.planned_month, 1)
        x = db.get(QProcess, ln.process_id) if ln.process_id else None
        a = db.get(FieldAudit, ln.audit_id) if ln.audit_id else None
        users = {u for u in (x.owner_user_id if x else None, a.lead_auditor_id if a else None) if u}
        for mark, when in (("due30", first - timedelta(days=30)), ("due0", first)):
            if day >= when and mark not in (ln.alerts_sent or []) and users:
                ln.alerts_sent = [*(ln.alerts_sent or []), mark]
                n += b.send(
                    db,
                    project,
                    users,
                    f"qprog:{ln.id}:{mark}",
                    f"Quality audit due {ln.year}-{ln.planned_month:02d}",
                    f"تدقيق جودة مستحق {ln.year}-{ln.planned_month:02d}",
                    path="/quality/audit-programme",
                    email=False,
                )
    for a in db.scalars(
        select(FieldAudit).where(
            FieldAudit.domain == AuditDomain.quality,
            FieldAudit.status == S.fieldwork_complete,
            FieldAudit.fieldwork_end.is_not(None),
        )
    ):
        project = db.get(Project, a.project_id)
        if project is None or a.fieldwork_end is None:
            continue
        days = int(b.setting(db, a.project_id, "q_audit_report_days"))
        if qc.project_day(project, at) > a.fieldwork_end + timedelta(
            days=days
        ) and "report_overdue" not in (a.alerts_sent or []):
            a.alerts_sent = [*(a.alerts_sent or []), "report_overdue"]
            users = {
                a.lead_auditor_id,
                *qc.holders_of(db, project, C.quality_settings, include_manager=False),
            }
            n += b.send(
                db,
                project,
                users,
                f"qau:{a.id}:overdue",
                f"{a.audit_no} report overdue",
                f"تأخر تقرير {a.audit_no}",
                rt=RT.q_audit,
                rid=a.id,
                path=f"/quality/audits/{a.id}",
            )
    db.flush()
    return {"q4_audits": n}


def mrv_due(db: Session, at: Any) -> dict[str, int]:
    """Q-MRV-03: no review held for `mgmt_review_months` → alert 239 holders (monthly)."""
    n = 0
    for pid in db.scalars(select(QManagementReview.project_id).distinct()):
        project = db.get(Project, pid)
        if project is None or qc.profile_of(db, pid) is None:
            continue
        last = db.scalar(
            select(QManagementReview.held_on)
            .where(QManagementReview.project_id == pid, QManagementReview.held_on.is_not(None))
            .order_by(QManagementReview.held_on.desc())
            .limit(1)
        )
        months = int(b.setting(db, pid, "mgmt_review_months"))
        day = qc.project_day(project, at)
        if last is None or b.add_months(last, months) <= day:
            users = qc.holders_of(db, project, C.quality_settings, include_manager=False)
            n += b.send(
                db,
                project,
                users,
                f"mrv-due:{pid}:{day.year}-{day.month}",
                "Management review due",
                "مراجعة الإدارة مستحقة",
                path="/quality/management-reviews",
                email=False,
            )
    return {"q4_mrv": n}


_ = (Role, QSectorProfile, QRevStatus, VersionStatus)
