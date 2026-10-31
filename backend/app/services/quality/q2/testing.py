"""Testing and lab (spec 8-quality §C.2, Q-TST-01…14): test types as versioned data, test requests
with specimens and due dates, results with an automatic verdict against the pinned criterion,
verification by the responsible person, amendments that keep the original (ISO/IEC 17025 7.8.8
idea), retests and the failed-result NCR (auto or prompt)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QCriterionStatus,
    QDetectionStage,
    QLinkKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QProfileScope,
    QRecordType,
    QSupplierCategory,
    QVerdict,
    profile_allows,
)
from app.core.quality.q2 import (
    TEST_WITH_RESULT,
    QCompetenceAppliesTo,
    QEvaluationMode,
    QResultFieldKind,
    QTestStatus,
    QTestTypeStatus,
    QTestVerdict,
)
from app.models import Project, Site, Zone
from app.models.quality import QCriterion, QMteItem, QSupplier
from app.models.quality.q2 import QMir, QPour, QTestRequest, QTestSpecimen, QTestType
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import paginate
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import criteria as qcrit
from app.services.quality import links, mte, numbering, rpm, suppliers
from app.services.quality import registry as reg
from app.services.quality import settings as qs
from app.services.quality.q2 import base, competence
from app.services.quality.q2.evaluators import LIST_RULES, STRENGTH_RULES, d, mean, r2

C = Capability
RT = QRecordType
ST = QTestStatus
A = AttachmentOwner
TT_ST = QTestTypeStatus
LIVE = (ST.requested, ST.sampled, ST.at_lab, ST.results_entered, ST.verified, ST.amended)


# ---- test types (Q-TST-01) ------------------------------------------------------------------


def type_read(t: QTestType) -> dict[str, Any]:
    return {
        "id": t.id,
        "code": t.code,
        "version": t.version,
        "name_en": t.name_en,
        "name_ar": t.name_ar,
        "discipline": t.discipline,
        "profile": t.profile,
        "standard_ref": t.standard_ref,
        "specimen_plan": t.specimen_plan or [],
        "result_fields": t.result_fields or [],
        "evaluation": t.evaluation,
        "criterion_code": t.criterion_code,
        "field_criteria": t.field_criteria or {},
        "acceptance_age_days": t.acceptance_age_days,
        "ncr_class_on_fail": t.ncr_class_on_fail or {},
        "competence_code": t.competence_code,
        "project_ids": list(t.project_ids or []),
        "status": t.status,
        "published_at": t.published_at,
    }


def list_types(
    db: Session,
    p: Principal,
    status: QTestTypeStatus | None,
    profile: QProfileScope | None,
    project_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    if not (p.has_any(C.quality_view) or p.has_any(C.test_record) or p.has_any(C.quality_author)):
        raise forbidden_error()
    stmt = select(QTestType)
    if status:
        stmt = stmt.where(QTestType.status == status)
    rows = list(db.scalars(stmt.order_by(QTestType.code, QTestType.version)))
    if profile:
        rows = [t for t in rows if t.profile in (profile, QProfileScope.both)]
    if project_id:
        rows = [t for t in rows if not t.project_ids or project_id in t.project_ids]
    return [type_read(t) for t in rows]


def get_type(db: Session, type_id: uuid.UUID) -> QTestType:
    t = db.get(QTestType, type_id)
    if t is None:
        raise not_found("Test type")
    return t


def _check_type(t: QTestType) -> None:
    keys = set()
    for i, f in enumerate(t.result_fields or []):
        k = str(f.get("key") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", k):
            raise qc.field_err(f"result_fields[{i}].key", "Key: lower-case letters, digits, _.")
        QResultFieldKind(f.get("kind") or "numeric")
        keys.add(k)
    if not keys:
        raise qc.field_err("result_fields", "A test type has at least one result field.")
    for i, row in enumerate(t.specimen_plan or []):
        if int(row.get("count") or 0) < 1:
            raise qc.field_err(f"specimen_plan[{i}].count", "Count ≥ 1.")
    if t.evaluation == QEvaluationMode.rule and not t.criterion_code:
        raise qc.field_err("criterion_code", "A rule evaluation names its criterion.")
    for k in t.field_criteria or {}:
        if k not in keys:
            raise qc.field_err("field_criteria", f"{k} is not a result field.")
    for k, v in (t.ncr_class_on_fail or {}).items():
        QNcrClass(v)
        _ = k


TYPE_EDIT = (
    "name_en",
    "name_ar",
    "discipline",
    "profile",
    "standard_ref",
    "specimen_plan",
    "result_fields",
    "evaluation",
    "criterion_code",
    "field_criteria",
    "acceptance_age_days",
    "ncr_class_on_fail",
    "competence_code",
    "project_ids",
)


def create_type(db: Session, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
    p.require_any(C.quality_author)
    code = str(body["code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,16}", code):
        raise qc.field_err("code", "Code: 2–16 capital letters, digits or -.")
    if db.scalar(select(QTestType.id).where(QTestType.code == code)):
        raise qc.field_err("code", "This code exists; create a new version instead.")
    t = QTestType(code=code, version=1, status=TT_ST.draft, created_by_user_id=p.user.id)
    for k in TYPE_EDIT:
        if k in body and body[k] is not None:
            setattr(t, k, body[k])
    t.evaluation = QEvaluationMode(t.evaluation or "fields")
    t.profile = QProfileScope(t.profile or "construction")
    _check_type(t)
    db.add(t)
    db.flush()
    _type_audit(db, p, t, AuditAction.create, {"code": t.code, "version": 1})
    return type_read(t)


def _type_audit(
    db: Session, p: Principal, t: QTestType, action: AuditAction, after: dict[str, Any]
) -> None:
    # org-wide library rows are audited under the test-request entity type (D-344)
    audit.record(
        db,
        action,
        p.actor(None),
        entity_type=EntityType.q_test_request,
        entity_id=t.id,
        after={k: str(v) for k, v in after.items()},
        details={"test_type": t.code, "version": t.version},
    )


def update_type(
    db: Session, p: Principal, type_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    p.require_any(C.quality_author)
    t = get_type(db, type_id)
    if t.status != TT_ST.draft:
        raise qc.err(
            409,
            ErrorCode.CRITERION_IMMUTABLE,
            "Only a Draft test type version can be changed; create a new version.",
            "يمكن تعديل الإصدار المسودة فقط؛ أنشئ إصداراً جديداً.",
        )
    for k in TYPE_EDIT:
        if k in body:
            setattr(t, k, body[k])
    t.evaluation = QEvaluationMode(t.evaluation)
    t.profile = QProfileScope(t.profile)
    _check_type(t)
    t.updated_by_user_id = p.user.id
    db.flush()
    _type_audit(db, p, t, AuditAction.update, {k: body[k] for k in body if k in TYPE_EDIT})
    return type_read(t)


def new_type_version(
    db: Session, p: Principal, type_id: uuid.UUID, project_id: uuid.UUID | None
) -> dict[str, Any]:
    """A new Draft version; with `project_id` it is that project's own version (Q-TST-01)."""
    p.require_any(C.quality_author)
    src = get_type(db, type_id)
    if db.scalar(
        select(QTestType.id).where(QTestType.code == src.code, QTestType.status == TT_ST.draft)
    ):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            f"{src.code} already has a Draft.",
            "يوجد إصدار مسودة.",
        )
    ver = int(db.scalar(select(func.max(QTestType.version)).where(QTestType.code == src.code)) or 0)
    t = QTestType(code=src.code, version=ver + 1, status=TT_ST.draft, created_by_user_id=p.user.id)
    for k in TYPE_EDIT:
        setattr(t, k, getattr(src, k))
    if project_id is not None:
        t.project_ids = [project_id]
    db.add(t)
    db.flush()
    _type_audit(
        db, p, t, AuditAction.create, {"code": t.code, "version": t.version, "from": src.version}
    )
    return type_read(t)


def type_transition(
    db: Session, p: Principal, type_id: uuid.UUID, action: str, why: str | None
) -> dict[str, Any]:
    """publish (239; supersedes the Published version of the same scope) · retire (239)."""
    p.require_any(C.quality_settings)
    t = get_type(db, type_id)
    if action == "publish":
        if t.status != TT_ST.draft:
            raise qc.err(
                409, ErrorCode.INVALID_TRANSITION, "Only a Draft is published.", "يُنشر المسودة فقط."
            )
        _check_type(t)
        if not t.name_en.strip() or not t.name_ar.strip():
            raise qc.field_err("name_ar", "EN and AR names are required to publish.")
        for old in db.scalars(
            select(QTestType).where(QTestType.code == t.code, QTestType.status == TT_ST.published)
        ):
            if sorted(map(str, old.project_ids or [])) == sorted(map(str, t.project_ids or [])):
                old.status = TT_ST.superseded
        t.status, t.published_at = TT_ST.published, now()
    elif action == "retire":
        if t.status != TT_ST.published:
            raise qc.err(
                409, ErrorCode.INVALID_TRANSITION, "Only a Published version is retired.", ""
            )
        qc.reason(why, 20)
        t.status = TT_ST.retired
    else:
        raise qc.field_err("action", "publish or retire")
    db.flush()
    _type_audit(db, p, t, AuditAction.status_change, {"status": t.status.value})
    return type_read(t)


def published_type(db: Session, code: str, project_id: uuid.UUID) -> QTestType | None:
    rows = list(
        db.scalars(
            select(QTestType).where(QTestType.code == code, QTestType.status == TT_ST.published)
        )
    )
    own = [t for t in rows if project_id in (t.project_ids or [])]
    if own:
        return max(own, key=lambda t: t.version)
    gen = [t for t in rows if not t.project_ids]
    return max(gen, key=lambda t: t.version) if gen else None


def published_criterion(db: Session, code: str | None, project_id: uuid.UUID) -> QCriterion | None:
    if not code:
        return None
    rows = list(
        db.scalars(
            select(QCriterion).where(
                QCriterion.code == code, QCriterion.status == QCriterionStatus.published
            )
        )
    )
    own = [c for c in rows if project_id in (c.project_ids or [])]
    pick = own or [c for c in rows if not c.project_ids]
    return max(pick, key=lambda c: c.version) if pick else None


# ---- reads ----------------------------------------------------------------------------------


def specimens_of(db: Session, t: QTestRequest) -> list[QTestSpecimen]:
    return list(
        db.scalars(
            select(QTestSpecimen)
            .where(QTestSpecimen.test_request_id == t.id)
            .order_by(QTestSpecimen.position, QTestSpecimen.specimen_ref)
        )
    )


def _specimen_read(s: QTestSpecimen) -> dict[str, Any]:
    return {
        "id": s.id,
        "specimen_ref": s.specimen_ref,
        "age_days": s.age_days,
        "due_on": s.due_on,
        "tested_on": s.tested_on,
        "values": s.values or {},
        "spare": s.spare,
    }


def ctx(t: QTestRequest) -> rpm.Ctx:
    return rpm.Ctx(
        t.site_id,
        t.engagement_id,
        qc.ids(t.results_entered_by_user_id, t.requested_by_user_id, t.created_by_user_id),
    )


def pending_steps(t: QTestRequest) -> list[tuple[str, rpm.Ctx]]:
    if t.status in (ST.results_entered, ST.amended):
        return [("verify", ctx(t))]
    return []


def can_view(db: Session, p: Principal, t: QTestRequest) -> bool:
    return base.can_view(
        db,
        p,
        t.project_id,
        (C.test_record, C.test_verify),
        t.site_id,
        t.engagement_id,
        rt=RT.test_request,
        rid=t.id,
        pending=lambda: pending_steps(t),
        own=(t.requested_by_user_id, t.created_by_user_id),
    )


def get_test(db: Session, p: Principal, test_id: uuid.UUID) -> QTestRequest:
    t = db.get(QTestRequest, test_id)
    base.require_view(
        db,
        p,
        t is not None and can_view(db, p, t),
        EntityType.q_test_request,
        test_id,
        t.project_id if t else None,
        "Test request",
    )
    assert t is not None  # noqa: S101
    return t


def actions(db: Session, p: Principal, t: QTestRequest) -> list[str]:
    out: list[str] = []
    g = p.grant(t.project_id, C.test_record)
    rec = qc.covers(g, t.site_id, t.engagement_id) or p.is_manager
    if rec and t.status == ST.requested:
        out += ["sample", "cancel"]
    if rec and t.status == ST.sampled:
        out += ["deliver", "cancel"]
    if rec and t.status in (ST.sampled, ST.at_lab):
        out.append("specimens")
    if rec and t.status == ST.at_lab:
        out.append("results")
    project = base.project_of(db, t.project_id)
    if t.status in (ST.results_entered, ST.amended) and rpm.resolves(
        db, p, project, RT.test_request, "verify", ctx(t), record_id=t.id
    ):
        out += ["verify", "return"]
    if t.status == ST.verified and rpm.resolves(
        db,
        p,
        project,
        RT.test_request,
        "verify",
        rpm.Ctx(t.site_id, t.engagement_id),
        record_id=t.id,
        can_act=False,
    ):
        out.append("amend")
    if (
        t.verdict == QTestVerdict.fail
        and t.status in TEST_WITH_RESULT
        and not t.ncr_decision.get("mode")
        and rec
    ):
        out.append("ncr_decision")
    if t.status != ST.voided and p.grant(t.project_id, C.quality_void) is not None:
        out.append("void")
    return out


def read(db: Session, p: Principal, t: QTestRequest, full: bool = True) -> dict[str, Any]:
    site = db.get(Site, t.site_id)
    zone = db.get(Zone, t.zone_id) if t.zone_id else None
    lab = db.get(QSupplier, t.lab_supplier_id)
    crit = db.get(QCriterion, t.criterion_id) if t.criterion_id else None
    tt = db.get(QTestType, t.test_type_id)
    pour = db.get(QPour, t.pour_id) if t.pour_id else None
    hide = base.read_only(p, t.project_id)
    out: dict[str, Any] = {
        "id": t.id,
        "project_id": t.project_id,
        "test_no": t.test_no,
        "test_type_id": t.test_type_id,
        "test_type_code": t.test_type_code,
        "test_type_version": tt.version if tt else 0,
        "test_type_name_en": tt.name_en if tt else "",
        "test_type_name_ar": tt.name_ar if tt else "",
        "criterion_id": t.criterion_id,
        "criterion_code": crit.code if crit else None,
        "criterion_version": crit.version if crit else None,
        "site_id": t.site_id,
        "site_code": site.code if site else "",
        "zone_id": t.zone_id,
        "zone_code": zone.code if zone else None,
        "system_id": t.system_id,
        "location_ref": t.location_ref,
        "engagement_id": t.engagement_id,
        "lab_supplier_id": t.lab_supplier_id,
        "lab_code": lab.supplier_code if lab else "",
        "pour_id": t.pour_id,
        "pour_no": pour.pour_no if pour else None,
        "mir_id": t.mir_id,
        "retest_of_id": t.retest_of_id,
        "mix_key": t.mix_key or None,
        "requested_by": base.user_ref(db, t.requested_by_user_id, hide),
        "sampled_at": t.sampled_at,
        "cast_date": t.cast_date,
        "sampled_by": base.user_ref(db, t.sampled_by_user_id, hide),
        "sample_ref": t.sample_ref,
        "mte_ids": list(t.mte_ids or []),
        "delivered_to_lab_on": t.delivered_to_lab_on,
        "results": t.results or {},
        "report_no": t.report_no,
        "tested_by_name": None if hide else t.tested_by_name,
        "verdict": t.verdict,
        "verdict_detail": t.verdict_detail or {},
        "result_version": t.result_version,
        "history": t.history or [] if full else [],
        "results_entered_at": t.results_entered_at,
        "results_entered_by": base.user_ref(db, t.results_entered_by_user_id, hide),
        "verified_at": t.verified_at,
        "verified_by": base.user_ref(db, t.verified_by_user_id, hide),
        "ncr_decision": t.ncr_decision or {},
        "status": t.status,
        "status_reason": t.status_reason,
        "specimens": [_specimen_read(s) for s in specimens_of(db, t)] if full else [],
        "result_fields": tt.result_fields if tt else [],
        "report_count": base.attachment_count(db, A.q_test_report, t.id),
        "actions": actions(db, p, t) if full else [],
    }
    return out


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[QTestStatus] | None = None,
    verdict: QTestVerdict | None = None,
    test_type: str | None = None,
    pour_id: uuid.UUID | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.test_record, C.test_verify)

    def n_ids() -> list[uuid.UUID]:
        return [
            t.id
            for t in db.scalars(
                select(QTestRequest).where(
                    QTestRequest.project_id == project.id,
                    QTestRequest.status.in_([ST.results_entered, ST.amended, ST.verified]),
                )
            )
            if can_view(db, p, t)
        ]

    T = QTestRequest  # noqa: N806
    stmt = select(T).where(
        T.project_id == project.id,
        base.scope_cond(
            p, project.id, (C.test_record, C.test_verify), T.site_id, T.engagement_id, n_ids, T.id
        ),
    )
    if statuses:
        stmt = stmt.where(T.status.in_(statuses))
    if verdict:
        stmt = stmt.where(T.verdict == verdict)
    if test_type:
        stmt = stmt.where(T.test_type_code == test_type.upper())
    if pour_id:
        stmt = stmt.where(T.pour_id == pour_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            T.test_no.ilike(like) | T.location_ref.ilike(like) | T.sample_ref.ilike(like)
        )
    items, total = paginate(db, stmt.order_by(T.created_at.desc()), page, page_size)
    return {
        "items": [read(db, p, t, full=False) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def specimen_calendar(
    db: Session, p: Principal, project_id: uuid.UUID, on: date | None
) -> dict[str, Any]:
    """Desk specimen calendar: due today and overdue (untested) specimens."""
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.test_record, C.test_verify)
    today = on or qc.project_day(project)
    rows = db.execute(
        select(QTestSpecimen, QTestRequest)
        .join(QTestRequest, QTestRequest.id == QTestSpecimen.test_request_id)
        .where(
            QTestRequest.project_id == project.id,
            QTestRequest.status.in_([ST.sampled, ST.at_lab]),
            QTestSpecimen.tested_on.is_(None),
            QTestSpecimen.spare.is_(False),
            QTestSpecimen.due_on.is_not(None),
            QTestSpecimen.due_on <= today + timedelta(days=7),
        )
        .order_by(QTestSpecimen.due_on, QTestRequest.test_no)
    ).all()
    out = []
    for s, t in rows:
        if not can_view(db, p, t):
            continue
        assert s.due_on is not None  # noqa: S101
        out.append(
            {
                "test_id": t.id,
                "test_no": t.test_no,
                "test_type_code": t.test_type_code,
                "specimen_ref": s.specimen_ref,
                "age_days": s.age_days,
                "due_on": s.due_on,
                "state": "overdue"
                if s.due_on < today
                else "today"
                if s.due_on == today
                else "upcoming",
            }
        )
    return {"on": today, "items": out}


# ---- create / sample / deliver -------------------------------------------------------------


def _lab_checks(db: Session, lab_id: uuid.UUID, code: str, on: date) -> list[ApiWarning]:
    lab = db.get(QSupplier, lab_id)
    if lab is None:
        raise qc.field_err("lab_supplier_id", "Unknown laboratory.")
    cats = {str(x) for x in (lab.categories or [])}
    if not cats & {QSupplierCategory.testing_lab.value, QSupplierCategory.ndt_provider.value}:
        raise qc.field_err(
            "lab_supplier_id",
            "The laboratory must be a supplier of category testing_lab or ndt_provider (Q-TST-02).",
            "يجب أن يكون المختبر من فئة مختبر اختبارات أو مزود فحص غير إتلافي.",
        )
    out = suppliers.check_use(db, lab.id)
    out += suppliers.lab_scope_warning(db, lab.id, code, on)
    return out


def _engagement_from_links(db: Session, body: dict[str, Any]) -> uuid.UUID | None:
    if body.get("pour_id"):
        pour = db.get(QPour, body["pour_id"])
        if pour is not None:
            return pour.engagement_id
    if body.get("mir_id"):
        mir = db.get(QMir, body["mir_id"])
        if mir is not None:
            return mir.engagement_id
    if body.get("ir_id"):
        ad = reg.RECORD_TYPES.get(RT.ir)
        row = ad.get(db, body["ir_id"]) if ad else None
        if ad is not None and row is not None:
            return ad.engagement(db, row)
    return None


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QTestRequest, list[ApiWarning]]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    prof = qc.require_profile(db, project)
    tt = db.get(QTestType, body["test_type_id"]) if body.get("test_type_id") else None
    if tt is None and body.get("test_type_code"):
        tt = published_type(db, str(body["test_type_code"]).upper(), project.id)
    if (
        tt is None
        or tt.status != TT_ST.published
        or (tt.project_ids and project.id not in tt.project_ids)
    ):
        raise qc.field_err("test_type_id", "Pick a Published test type of this project.")
    if not profile_allows(tt.profile, prof):
        raise qc.err(
            409,
            ErrorCode.PROFILE_INACTIVE,
            f"{tt.code} belongs to the {tt.profile.value} profile; the project uses {prof.value}.",
            "نوع الاختبار يخص قطاعاً غير مفعّل في المشروع.",
        )
    pour = db.get(QPour, body["pour_id"]) if body.get("pour_id") else None
    if body.get("pour_id") and (pour is None or pour.project_id != project.id):
        raise qc.field_err("pour_id", "The pour is not on this project.")
    mir = db.get(QMir, body["mir_id"]) if body.get("mir_id") else None
    if body.get("mir_id") and (mir is None or mir.project_id != project.id):
        raise qc.field_err("mir_id", "The MIR is not on this project.")
    retest = db.get(QTestRequest, body["retest_of_id"]) if body.get("retest_of_id") else None
    if body.get("retest_of_id") and (retest is None or retest.project_id != project.id):
        raise qc.field_err("retest_of_id", "The original test is not on this project.")
    eng = (
        body.get("engagement_id")
        or _engagement_from_links(db, body)
        or (retest.engagement_id if retest else None)
    )
    site_id = (
        body.get("site_id")
        or (pour.site_id if pour else None)
        or (retest.site_id if retest else None)
    )
    if site_id is None:
        raise qc.field_err("site_id", "Pick the site.")
    site = db.get(Site, site_id)
    if site is None or site.project_id != project.id:
        raise qc.field_err("site_id", "The site does not belong to this project.")
    qc.require_cover(p, project.id, C.test_record, site_id, eng)
    today = qc.project_day(project)
    warnings = _lab_checks(db, body["lab_supplier_id"], tt.code, today)
    crit = db.get(QCriterion, body["criterion_id"]) if body.get("criterion_id") else None
    if body.get("criterion_id") and (crit is None or crit.status != QCriterionStatus.published):
        raise qc.field_err("criterion_id", "Pick a Published criterion.")
    if crit is None and tt.evaluation == QEvaluationMode.rule:
        code = tt.criterion_code
        if pour is not None and pour.fc_mpa is not None and code:
            # the pour's grade picks the criterion of the same rule family (e.g. CONC-ACI-40)
            code = (
                re.sub(r"\d+$", str(int(pour.fc_mpa)), code) if re.search(r"\d+$", code) else code
            )
        crit = published_criterion(db, code, project.id) or published_criterion(
            db, tt.criterion_code, project.id
        )
    pinned = {}
    for k, code in (tt.field_criteria or {}).items():
        c = published_criterion(db, code, project.id)
        if c is not None:
            pinned[k] = str(c.id)
    t = QTestRequest(
        id=uuid.uuid4(),
        project_id=project.id,
        test_no=numbering.assign(db, project, RT.test_request),
        test_type_id=tt.id,
        test_type_code=tt.code,
        criterion_id=crit.id if crit else None,
        field_criterion_ids=pinned,
        site_id=site_id,
        zone_id=body.get("zone_id") or (pour.zone_id if pour else None),
        system_id=body.get("system_id"),
        location_ref=(body.get("location_ref") or (pour.location_ref if pour else None) or "—")[
            :120
        ],
        engagement_id=eng,
        lab_supplier_id=body["lab_supplier_id"],
        pour_id=pour.id if pour else None,
        mir_id=mir.id if mir else None,
        retest_of_id=retest.id if retest else None,
        mix_key=(
            body.get("mix_key")
            or (pour.mix_key if pour else "")
            or (retest.mix_key if retest else "")
            or ""
        )[:80],
        requested_by_user_id=p.user.id,
        status=ST.requested,
        results={},
        history=[],
        verdict_detail={},
        ncr_decision={},
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(t)
    db.flush()
    for rt_, rid in ((RT.pour, t.pour_id), (RT.mir, t.mir_id), (RT.test_request, t.retest_of_id)):
        if rid is not None:
            links.add(db, project.id, RT.test_request, t.id, rt_, rid, QLinkKind.relates, p.user.id)
    if body.get("ir_id") and RT.ir in reg.RECORD_TYPES:
        links.create(db, p, RT.test_request, t.id, RT.ir, body["ir_id"], QLinkKind.relates)
    base.audit_create(db, p, RT.test_request, t, test_type=tt.code, test_no=t.test_no)
    return t, warnings


def _plan(tt: QTestType) -> list[tuple[int | None, bool]]:
    out: list[tuple[int | None, bool]] = []
    for row in tt.specimen_plan or []:
        age = row.get("age_days")
        for _ in range(int(row.get("count") or 0)):
            out.append((int(age) if age is not None else None, bool(row.get("spare"))))
    return out


def sample(
    db: Session, p: Principal, test_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QTestRequest, list[ApiWarning]]:
    """Requested → Sampled: sampled_at, sample_ref, M&TE usage (Q-SHR-04), specimens with due
    dates (cast date + age, Q-TST-03); sampling measurements (slump, temperature) may be given."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status != ST.requested:
        raise base.invalid("The test request", t.status, "sampled")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    at: datetime = body.get("sampled_at") or now()
    if at > now() + timedelta(minutes=5):
        raise qc.field_err("sampled_at", "The sampling time cannot be in the future.")
    ref = (body.get("sample_ref") or "").strip()
    if not ref:
        raise qc.field_err("sample_ref", "Give the sample reference.")
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    warnings: list[ApiWarning] = []
    sampler = body.get("sampled_by_user_id") or p.user.id
    warnings += competence.enforce(
        db, project, sampler, tt.competence_code, base.local_day(project, at), "sampled_by_user_id"
    )
    t.sampled_at, t.sample_ref, t.sampled_by_user_id = at, ref[:40], sampler
    t.cast_date = base.local_day(project, at)
    mte_ids = list(dict.fromkeys(body.get("mte_ids") or []))
    for mid in mte_ids:
        note = (
            body.get("mte_notes", {}).get(str(mid))
            if isinstance(body.get("mte_notes"), dict)
            else None
        )
        _u, w = mte.record_usage(
            db, project, mid, RT.test_request, t.id, p.user.id, at, note or f"{t.test_no} sampling"
        )
        warnings += w
    t.mte_ids = mte_ids
    if body.get("results"):
        t.results = {**(t.results or {}), **_clean_values(tt, body["results"], "results")}
    for i, (age, spare) in enumerate(_plan(tt)):
        db.add(
            QTestSpecimen(
                test_request_id=t.id,
                specimen_ref=f"{ref}-{i + 1}"[:40],
                age_days=age,
                due_on=t.cast_date + timedelta(days=age) if age is not None else None,
                spare=spare,
                position=i,
            )
        )
    base.set_status(db, p, RT.test_request, t, ST.sampled, sample_ref=ref)
    return t, warnings


def deliver(db: Session, p: Principal, test_id: uuid.UUID, on: date | None) -> QTestRequest:
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status != ST.sampled:
        raise base.invalid("The test request", t.status, "sent to the lab")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    t.delivered_to_lab_on = on or qc.project_day(project)
    base.set_status(db, p, RT.test_request, t, ST.at_lab)
    return t


# ---- results and verdict (Q-TST-04…09) --------------------------------------------------------


def _clean_values(tt: QTestType, values: dict[str, Any], where: str) -> dict[str, Any]:
    fields = {f["key"]: f for f in tt.result_fields or []}
    out: dict[str, Any] = {}
    for k, v in values.items():
        f = fields.get(k)
        if f is None:
            raise qc.field_err(f"{where}.{k}", f"{k} is not a result field of {tt.code}.")
        kind = QResultFieldKind(f.get("kind") or "numeric")
        if v is None or v == "":
            continue
        if kind == QResultFieldKind.numeric:
            if d(v) is None:
                raise qc.field_err(f"{where}.{k}", f"{k} must be a number.")
            out[k] = str(d(v))
        elif kind == QResultFieldKind.pass_fail:
            if str(v) not in ("pass", "fail"):
                raise qc.field_err(f"{where}.{k}", "pass or fail")
            out[k] = str(v)
        else:
            out[k] = str(v)[:500]
    return out


def _first_numeric(tt: QTestType) -> str | None:
    for f in tt.result_fields or []:
        if (f.get("kind") or "numeric") == "numeric":
            return str(f["key"])
    return None


def _strength_test(tt: QTestType, specs: list[QTestSpecimen]) -> Decimal | None:
    key = _first_numeric(tt)
    acc = [
        d((s.values or {}).get(key or ""))
        for s in specs
        if not s.spare and s.age_days == tt.acceptance_age_days
    ]
    vals = [x for x in acc if x is not None]
    return mean(vals) if vals else None


def _history_tests(db: Session, t: QTestRequest, crit: QCriterion) -> list[Decimal]:
    """Earlier strength tests of the same mix and criterion code, in cast-date order (Q-TST-08)."""
    if not t.mix_key:
        return []
    rows = db.scalars(
        select(QTestRequest).where(
            QTestRequest.project_id == t.project_id,
            QTestRequest.mix_key == t.mix_key,
            QTestRequest.id != t.id,
            QTestRequest.status.in_(list(TEST_WITH_RESULT)),
            QTestRequest.cast_date.is_not(None),
        )
    )
    out: list[tuple[date, datetime, Decimal]] = []
    for o in rows:
        oc = db.get(QCriterion, o.criterion_id) if o.criterion_id else None
        if oc is None or oc.code != crit.code or o.retest_of_id is not None:
            continue
        v = d((o.verdict_detail or {}).get("test"))
        if v is None or o.cast_date is None:
            continue
        if t.cast_date is not None and (o.cast_date, o.created_at) >= (t.cast_date, t.created_at):
            continue
        out.append((o.cast_date, o.created_at, v))
    return [x[2] for x in sorted(out)]


def compute(
    db: Session, t: QTestRequest, final: bool
) -> tuple[QTestVerdict, dict[str, Any], list[str]]:
    """The verdict of the current result version; returns (verdict, detail, missing inputs)."""
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    specs = specimens_of(db, t)
    missing: list[str] = []
    if tt.evaluation == QEvaluationMode.rule:
        crit = db.get(QCriterion, t.criterion_id) if t.criterion_id else None
        if crit is None:
            return QTestVerdict.pending, {"reason_en": "No criterion pinned."}, ["criterion"]
        rule = crit.rule_code or ""
        values: dict[str, Any] = dict(t.results or {})
        if rule in STRENGTH_RULES:
            cur = _strength_test(tt, specs)
            if cur is None:
                return QTestVerdict.pending, {}, ["acceptance-age specimens"]
            values["tests"] = [*_history_tests(db, t, crit), cur]
        elif rule in LIST_RULES:
            key = _first_numeric(tt) or ""
            vals = [(s.values or {}).get(key) for s in specs if not s.spare]
            vals = [v for v in vals if v not in (None, "")]
            if not vals:
                return QTestVerdict.pending, {}, ["specimen values"]
            values[LIST_RULES[rule]] = vals
        else:
            key = _first_numeric(tt)
            if key and key in values:
                values["value"] = values[key]
        v = qcrit.evaluate(crit, values)
        det = {
            **v.detail,
            "reason_en": v.reason_en,
            "reason_ar": v.reason_ar,
            "criterion": f"{crit.code} v{crit.version}",
        }
        if rule in STRENGTH_RULES:
            det["test"] = str(values["tests"][-1])
        if v.verdict == QVerdict.not_evaluable:
            return QTestVerdict.pending, det, [v.reason_en]
        return QTestVerdict(v.verdict.value), det, missing
    # one criterion per field
    verdicts: dict[str, Any] = {}
    overall = QTestVerdict.pass_
    for f in tt.result_fields or []:
        key = str(f["key"])
        cid = (t.field_criterion_ids or {}).get(key)
        raw: Any = (t.results or {}).get(key)
        if raw is None and specs:
            nums = [d((s.values or {}).get(key)) for s in specs if not s.spare]
            nums2 = [x for x in nums if x is not None]
            raw = str(mean(nums2)) if nums2 else None
        if raw is None:
            missing.append(key)
            continue
        if not cid:
            continue
        crit = db.get(QCriterion, uuid.UUID(cid))
        if crit is None:
            continue
        val = {"verdict": raw} if (f.get("kind") == "pass_fail") else {"value": raw}
        v = qcrit.evaluate(crit, val)
        verdicts[key] = {
            "verdict": v.verdict.value,
            "reason_en": v.reason_en,
            "reason_ar": v.reason_ar,
            "criterion": f"{crit.code} v{crit.version}",
        }
        if v.verdict == QVerdict.fail:
            overall = QTestVerdict.fail
        elif v.verdict == QVerdict.not_evaluable:
            missing.append(key)
    if missing and overall != QTestVerdict.fail:
        return QTestVerdict.pending, {"fields": verdicts}, missing
    reason = "; ".join(f"{k}: {x['reason_en']}" for k, x in verdicts.items())
    reason_ar = "؛ ".join(f"{k}: {x['reason_ar']}" for k, x in verdicts.items())
    return overall, {"fields": verdicts, "reason_en": reason, "reason_ar": reason_ar}, missing


def _apply_specimens(
    db: Session, t: QTestRequest, tt: QTestType, rows: list[dict[str, Any]]
) -> None:
    specs = {str(s.id): s for s in specimens_of(db, t)}
    by_ref = {s.specimen_ref: s for s in specs.values()}
    for i, row in enumerate(rows):
        s = specs.get(str(row.get("id"))) or by_ref.get(str(row.get("specimen_ref") or ""))
        if s is None:
            raise qc.field_err(f"specimens[{i}]", "Unknown specimen.")
        vals = _clean_values(tt, dict(row.get("values") or {}), f"specimens[{i}].values")
        s.values = {**(s.values or {}), **vals}
        s.tested_on = (
            row.get("tested_on")
            or s.tested_on
            or (qc.project_day(base.project_of(db, t.project_id)) if vals else None)
        )
    db.flush()


def _fc(db: Session, t: QTestRequest) -> Decimal | None:
    crit = db.get(QCriterion, t.criterion_id) if t.criterion_id else None
    if crit is None:
        return None
    return d((crit.params or {}).get("fc")) or d((crit.params or {}).get("fck"))


def early_strength(
    db: Session, project: Project, t: QTestRequest, tt: QTestType
) -> list[ApiWarning]:
    """Q-TST-07: indicative early-age strength < `early_age_warning_ratio` × f'c warns the
    requester and the pour's quality engineer."""
    fc = _fc(db, t)
    if fc is None or tt.acceptance_age_days is None:
        return []
    key = _first_numeric(tt) or ""
    out: list[ApiWarning] = []
    ages = sorted(
        {
            s.age_days
            for s in specimens_of(db, t)
            if s.age_days is not None and s.age_days < tt.acceptance_age_days
        }
    )
    ratio = Decimal(str(qs.value(db, project.id, "early_age_warning_ratio") or "0.65"))
    for age in ages:
        vals = [
            d((s.values or {}).get(key))
            for s in specimens_of(db, t)
            if s.age_days == age and not s.spare
        ]
        nums = [x for x in vals if x is not None]
        if not nums:
            continue
        m = mean(nums)
        det = dict(t.verdict_detail or {})
        det.setdefault("indicative", {})[str(age)] = r2(m)
        t.verdict_detail = det
        if m < ratio * fc:
            out.append(
                qc.warning(
                    ErrorCode.EARLY_STRENGTH_LOW,
                    f"{age}-day mean {r2(m)} MPa < {ratio} × f'c ({r2(ratio * fc)} MPa); watch the "
                    "28-day result.",
                    f"متوسط عمر {age} يوم {r2(m)} أقل من {ratio} × المقاومة المطلوبة.",
                )
            )
            pour = db.get(QPour, t.pour_id) if t.pour_id else None
            qc.send(
                db,
                [
                    u
                    for u in (t.requested_by_user_id, pour.quality_engineer_id if pour else None)
                    if u
                ],
                f"{t.test_no}: early strength low ({age} d mean {r2(m)} MPa)",
                f"{t.test_no}: مقاومة مبكرة منخفضة",
                entity_type=EntityType.q_test_request,
                entity_id=t.id,
                project_id=project.id,
                key=f"early_low:{t.id}:{age}",
                path=f"/quality/tests/{t.id}",
            )
    return out


def record_specimens(
    db: Session, p: Principal, test_id: uuid.UUID, rows: list[dict[str, Any]]
) -> tuple[QTestRequest, list[ApiWarning]]:
    """Specimen values while Sampled / At Lab: earlier ages are indicative (Q-TST-07)."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status in (ST.verified, ST.amended):
        raise _verified()
    if t.status not in (ST.sampled, ST.at_lab):
        raise base.invalid("The test request", t.status, "given specimen results")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    _apply_specimens(db, t, tt, rows)
    warnings = early_strength(db, project, t, tt)
    if t.verdict == QTestVerdict.pending and (t.verdict_detail or {}).get("indicative"):
        t.verdict = QTestVerdict.indicative
    db.flush()
    return t, warnings


def _verified() -> Any:
    return qc.err(
        409,
        ErrorCode.RESULT_VERIFIED,
        "Verified results are never edited; record an amendment with the lab's amended report.",
        "النتائج المعتمدة لا تُعدَّل؛ سجّل تعديلاً بتقرير المختبر المعدّل.",
    )


def _complete(db: Session, t: QTestRequest, tt: QTestType, more_than: int = 0) -> None:
    """Q-TST-04: the lab report file and number and every result field of the tested specimens
    (all acceptance-age specimens) or of the test."""
    problems: list[str] = []
    if not (t.report_no or "").strip():
        problems.append("report_no")
    if base.attachment_count(db, A.q_test_report, t.id) <= more_than:
        problems.append("lab report file" + (" (amended)" if more_than else ""))
    keys = [str(f["key"]) for f in tt.result_fields or []]
    specs = specimens_of(db, t)
    if specs:
        for s in specs:
            if s.spare:
                continue
            due_at_acc = tt.acceptance_age_days is None or s.age_days == tt.acceptance_age_days
            if (
                (s.tested_on or due_at_acc)
                and any((s.values or {}).get(k) in (None, "") for k in keys)
                and (due_at_acc or s.tested_on)
            ):
                problems.append(f"specimen {s.specimen_ref}")
    else:
        problems += [k for k in keys if (t.results or {}).get(k) in (None, "")]
    if problems:
        raise qc.err(
            422,
            ErrorCode.TEST_RESULT_INCOMPLETE,
            "Results are incomplete: " + ", ".join(problems) + ".",
            "النتائج غير مكتملة: " + "، ".join(problems),
            missing=problems,
        )


def _snapshot(db: Session, t: QTestRequest) -> dict[str, Any]:
    return {
        "version": t.result_version,
        "verdict": t.verdict.value,
        "verdict_detail": t.verdict_detail or {},
        "results": t.results or {},
        "specimens": [
            _specimen_read(s)
            | {
                "id": str(s.id),
                "due_on": s.due_on.isoformat() if s.due_on else None,
                "tested_on": s.tested_on.isoformat() if s.tested_on else None,
            }
            for s in specimens_of(db, t)
        ],
        "report_no": t.report_no,
        "verified_at": t.verified_at.isoformat() if t.verified_at else None,
    }


def _ncr_class(tt: QTestType, detail: dict[str, Any]) -> QNcrClass:
    m = tt.ncr_class_on_fail or {}
    clause = str(detail.get("clause") or "")
    return QNcrClass(m.get(clause) or m.get("default") or "major")


def _raise_ncr(
    db: Session, project: Project, t: QTestRequest, tt: QTestType, user_id: uuid.UUID | None
) -> uuid.UUID:

    pour = db.get(QPour, t.pour_id) if t.pour_id else None
    owner = (pour.quality_engineer_id if pour else None) or t.requested_by_user_id or user_id
    assert owner is not None  # noqa: S101
    n = base.auto_ncr(
        db,
        project,
        QNcrSourceType.test_result,
        t.id,
        raised_by=user_id,
        owner_id=owner,
        classification=_ncr_class(tt, t.verdict_detail or {}),
        category=QNcrCategory.testing_failure,
        evidence=((A.q_test_report, t.id),),
    )
    t.ncr_decision = {
        "mode": "raised",
        "ncr_id": str(n.id),
        "ncr_no": n.ncr_no,
        "at": now().isoformat(),
    }
    return n.id


def _failed(
    db: Session, project: Project, p: Principal, t: QTestRequest, tt: QTestType
) -> dict[str, Any]:
    """Q-TST-06 at Results Entered: `auto` opens the NCR now (System, containment starts at once);
    `prompt` asks the user to raise it or record why not."""
    if t.ncr_decision.get("mode") == "raised":
        return {"ncr_prompt": False}
    mode = qs.value(db, project.id, "test_auto_ncr")
    pour = db.get(QPour, t.pour_id) if t.pour_id else None
    recips = [u for u in (t.requested_by_user_id, pour.quality_engineer_id if pour else None) if u]
    qc.send(
        db,
        recips + base.quality_engineers(db, project),
        f"{t.test_no}: {t.test_type_code} result FAILED",
        f"{t.test_no}: نتيجة الاختبار راسبة",
        body_en=(t.verdict_detail or {}).get("reason_en"),
        body_ar=(t.verdict_detail or {}).get("reason_ar"),
        entity_type=EntityType.q_test_request,
        entity_id=t.id,
        project_id=project.id,
        key=f"test_failed:{t.id}:{t.result_version}",
        path=f"/quality/tests/{t.id}",
    )
    if mode == "auto":
        _raise_ncr(db, project, t, tt, p.user.id)
        return {"ncr_prompt": False}
    return {"ncr_prompt": True}


def enter_results(
    db: Session, p: Principal, test_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QTestRequest, list[ApiWarning], dict[str, Any]]:
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status in (ST.verified, ST.amended):
        raise _verified()
    if t.status != ST.at_lab:
        raise base.invalid("The test request", t.status, "given its results")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    if body.get("specimens"):
        _apply_specimens(db, t, tt, body["specimens"])
    if body.get("results"):
        t.results = {**(t.results or {}), **_clean_values(tt, body["results"], "results")}
    for k in ("report_no", "tested_by_name"):
        if body.get(k) is not None:
            setattr(t, k, str(body[k]).strip()[: 60 if k == "report_no" else 120])
    _complete(db, t, tt)
    warnings = early_strength(db, project, t, tt)
    verdict, detail, missing = compute(db, t, True)
    if missing:
        raise qc.err(
            422,
            ErrorCode.TEST_RESULT_INCOMPLETE,
            "Results are incomplete: " + ", ".join(missing) + ".",
            "النتائج غير مكتملة.",
            missing=missing,
        )
    t.verdict, t.verdict_detail = verdict, {**(t.verdict_detail or {}), **detail}
    t.result_version = 1
    t.results_entered_at, t.results_entered_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.test_request, t, ST.results_entered, verdict=verdict.value)
    extra = {"ncr_prompt": False}
    if verdict == QTestVerdict.fail:
        extra = _failed(db, project, p, t, tt)
    _notify_verify(db, project, t)
    return t, warnings, extra


def _notify_verify(db: Session, project: Project, t: QTestRequest) -> None:
    qc.send(
        db,
        base.resolvers(db, project, RT.test_request, "verify", ctx(t), t.id),
        f"{t.test_no}: results to verify",
        f"{t.test_no}: نتائج بانتظار التحقق",
        entity_type=EntityType.q_test_request,
        entity_id=t.id,
        project_id=project.id,
        key=f"test_verify:{t.id}:{t.result_version}",
        path=f"/quality/tests/{t.id}",
    )


def ncr_decision(
    db: Session, p: Principal, test_id: uuid.UUID, raise_ncr: bool, why: str | None
) -> QTestRequest:
    """Q-TST-06 prompt mode: raise the NCR, or record why not (reason ≥ 20 chars, counted)."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.verdict != QTestVerdict.fail or t.status not in TEST_WITH_RESULT:
        raise base.invalid("The test request", t.status, "given an NCR decision")
    if t.ncr_decision.get("mode"):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The NCR decision is already recorded.",
            "تم تسجيل القرار.",
        )
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    if raise_ncr:
        p.require(project.id, C.ncr_raise)
        _raise_ncr(db, project, t, tt, p.user.id)
    else:
        text = qc.reason(why, 20)
        t.ncr_decision = {
            "mode": "declined",
            "reason": text,
            "by": str(p.user.id),
            "at": now().isoformat(),
        }
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_test_request,
            entity_id=t.id,
            project_id=project.id,
            details={"ncr_declined": text},
        )
    db.flush()
    return t


def verify(
    db: Session,
    p: Principal,
    test_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QTestRequest:
    """Results Entered / Amended → Verified (258 + RPM `test_request.verify`; the user who entered
    the results never verifies, Q-TST-05); `returned` sends it back to At Lab (comment ≥ 20)."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status not in (ST.results_entered, ST.amended):
        raise base.invalid("The test request", t.status, "verified")
    if decision not in ("approved", "returned"):
        raise qc.field_err("decision", "approved or returned")
    text = qc.reason(comment, 20, "comment") if decision == "returned" else comment
    base.sign(db, p, project, RT.test_request, t.id, "verify", decision, text, ctx(t), paper=paper)
    if decision == "returned":
        t.status_reason = text
        base.set_status(db, p, RT.test_request, t, ST.at_lab, comment=text)
        return t
    t.verified_at, t.verified_by_user_id = now(), p.user.id
    # the amended report must be a new file (Q-TST-09): remember how many were verified
    t.verdict_detail = {
        **(t.verdict_detail or {}),
        "reports_at_verify": base.attachment_count(db, A.q_test_report, t.id),
    }
    base.set_status(db, p, RT.test_request, t, ST.verified)
    return t


def amend(
    db: Session, p: Principal, test_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QTestRequest, list[ApiWarning], dict[str, Any]]:
    """Q-TST-09: Verified → Amended with the lab's amended report and a reason ≥ 20 chars; a new
    result version is evaluated and the original kept. An NCR of the original failure stays."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status != ST.verified:
        raise base.invalid("The test request", t.status, "amended")
    text = qc.reason(body.get("reason"), 20)
    res = rpm.resolve(
        db, project, RT.test_request, "verify", rpm.Ctx(t.site_id, t.engagement_id), record_id=t.id
    )
    if res.rule is None:
        raise rpm.not_set_error(RT.test_request, "verify")
    if p.user.id not in res.users:
        raise forbidden_error(
            "Amending verified results needs the responsible person for verification."
        )
    tt = db.get(QTestType, t.test_type_id)
    assert tt is not None  # noqa: S101
    snap = _snapshot(db, t)
    if not body.get("report_no"):
        raise qc.err(
            422,
            ErrorCode.TEST_RESULT_INCOMPLETE,
            "Give the amended report number.",
            "أدخل رقم التقرير المعدّل.",
        )
    t.report_no = str(body["report_no"]).strip()[:60]
    if body.get("specimens"):
        _apply_specimens(db, t, tt, body["specimens"])
    if body.get("results"):
        t.results = {**(t.results or {}), **_clean_values(tt, body["results"], "results")}
    _complete(db, t, tt, more_than=int((t.verdict_detail or {}).get("reports_at_verify") or 1))
    verdict, detail, missing = compute(db, t, True)
    if missing:
        raise qc.err(
            422,
            ErrorCode.TEST_RESULT_INCOMPLETE,
            "Results are incomplete: " + ", ".join(missing),
            "النتائج غير مكتملة.",
        )
    snap["amended_at"], snap["reason"], snap["by"] = now().isoformat(), text, str(p.user.id)
    t.history = [*(t.history or []), snap]
    t.verdict, t.verdict_detail = verdict, detail
    t.result_version = (t.result_version or 1) + 1
    t.results_entered_at, t.results_entered_by_user_id = now(), p.user.id
    t.verified_at = t.verified_by_user_id = None
    base.set_status(db, p, RT.test_request, t, ST.amended, reason=text, verdict=verdict.value)
    extra = {"ncr_prompt": False}
    if verdict == QTestVerdict.fail:
        extra = _failed(db, project, p, t, tt)
    _notify_verify(db, project, t)
    return t, [], extra


def update(db: Session, p: Principal, test_id: uuid.UUID, body: dict[str, Any]) -> QTestRequest:
    """Edit the request details before results; after verification → 409 RESULT_VERIFIED."""
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status in (ST.verified, ST.amended):
        raise _verified()
    if t.status in (ST.results_entered, ST.cancelled, ST.voided):
        raise base.invalid("The test request", t.status, "edited")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    for k in ("location_ref", "zone_id", "system_id", "sample_ref", "tested_by_name"):
        if k in body and body[k] is not None:
            setattr(t, k, body[k])
    t.updated_by_user_id = p.user.id
    db.flush()
    return t


def cancel(db: Session, p: Principal, test_id: uuid.UUID, why: str | None) -> QTestRequest:
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status not in (ST.requested, ST.sampled):
        raise base.invalid("The test request", t.status, "cancelled")
    qc.require_cover(p, project.id, C.test_record, t.site_id, t.engagement_id)
    t.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.test_request, t, ST.cancelled, reason=t.status_reason)
    return t


def void(db: Session, p: Principal, test_id: uuid.UUID, why: str | None) -> QTestRequest:
    t = get_test(db, p, test_id)
    project = base.project_of(db, t.project_id)
    qc.writable(project, p)
    if t.status == ST.voided:
        raise base.invalid("The test request", t.status, "voided")
    p.require(project.id, C.quality_void)
    t.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.test_request, t, ST.voided, reason=t.status_reason)
    return t


# ---- jobs (Q-TST-03) ---------------------------------------------------------------------------


def overdue_specimen_alerts(db: Session, at: datetime) -> int:
    """An untested specimen past due_on + `test_overdue_days` alerts the requester once."""
    n = 0
    rows = db.execute(
        select(QTestSpecimen, QTestRequest)
        .join(QTestRequest, QTestRequest.id == QTestSpecimen.test_request_id)
        .where(
            QTestRequest.status.in_([ST.sampled, ST.at_lab]),
            QTestSpecimen.tested_on.is_(None),
            QTestSpecimen.spare.is_(False),
            QTestSpecimen.due_on.is_not(None),
        )
    ).all()
    for s, t in rows:
        project = db.get(Project, t.project_id)
        if project is None or s.due_on is None or t.requested_by_user_id is None:
            continue
        grace = int(qs.value(db, project.id, "test_overdue_days") or 0)
        if qc.project_day(project, at) <= s.due_on + timedelta(days=grace):
            continue
        n += qc.send(
            db,
            [t.requested_by_user_id],
            f"{t.test_no}: specimen {s.specimen_ref} ({s.age_days} d) not tested, "
            f"due {s.due_on.isoformat()}",
            f"{t.test_no}: العينة {s.specimen_ref} متأخرة عن موعد الاختبار",
            entity_type=EntityType.q_test_request,
            entity_id=t.id,
            project_id=project.id,
            email=False,
            key=f"specimen_overdue:{s.id}",
            path=f"/quality/tests/{t.id}",
        )
    return n


# ---- NCR source (list NS `test_result`) ------------------------------------------------------


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    t = db.get(QTestRequest, source_id)
    if t is None or t.project_id != project.id:
        raise qc.field_err("source_id", "The test request is not on this project.")
    tt = db.get(QTestType, t.test_type_id)
    crit = db.get(QCriterion, t.criterion_id) if t.criterion_id else None
    pour = db.get(QPour, t.pour_id) if t.pour_id else None
    mir = db.get(QMir, t.mir_id) if t.mir_id else None
    det = t.verdict_detail or {}
    req = (
        f"{crit.title_en} ({crit.code} v{crit.version}); {crit.reference or ''}".strip("; ")
        if crit
        else (tt.standard_ref if tt else None)
    )
    return reg.SourceInfo(
        ref=t.test_no,
        title=f"{t.test_type_code} result failed — {t.test_no}"
        + (f", {pour.pour_no}" if pour else ""),
        site_id=t.site_id,
        zone_id=t.zone_id,
        system_id=t.system_id,
        engagement_id=t.engagement_id,
        supplier_id=(pour.supplier_id if pour else None) or (mir.supplier_id if mir else None),
        item_key=f"TT:{t.test_type_code}",
        detection_stage=QDetectionStage.receiving if mir else QDetectionStage.in_process,
        requirement_en=req,
        finding_en=det.get("reason_en"),
        finding_ar=det.get("reason_ar"),
        proposed_class=_ncr_class(tt, det) if tt and t.verdict == QTestVerdict.fail else None,
        location_ref=t.location_ref,
        quantity=pour.volume_m3 if pour else None,
        unit="m3" if pour else None,
        lot_refs=(t.mix_key,) if t.mix_key else (),
        record_type=RT.test_request,
    )


def ncr_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
    t = db.get(QTestRequest, rid)
    return t is not None and can_view(db, p, t)


def mte_ok(db: Session, project: Project, mte_ids: list[uuid.UUID]) -> None:
    for mid in mte_ids:
        m = db.get(QMteItem, mid)
        if m is None or m.project_id != project.id:
            raise qc.field_err("mte_ids", "Unknown instrument.")


_ = (QCompetenceAppliesTo,)
