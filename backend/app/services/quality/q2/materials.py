"""Materials (spec 8-quality §C.3, Q-MAT-01…08): Material Approval Requests with revisions and
approval codes A–D, Material Inspection Requests on delivery and quarantined material (red tag).
Construction profile only (Q-PRF-04)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, EntityType
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    NCR_LIVE,
    QDetectionStage,
    QDisposition,
    QLinkKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QRecordType,
)
from app.core.quality.q2 import (
    MAR_APPROVED,
    MAR_CODE_STATUS,
    QCompliance,
    QMarStatus,
    QMaterialCategory,
    QMirResult,
    QMirStatus,
    QQuarantineStatus,
    QTestVerdict,
)
from app.models import Project, ProjectEngagement, Site, Zone
from app.models.quality import QNcr, QNcrLine, QSupplier
from app.models.quality.q2 import QMar, QMir, QQuarantineItem, QTestRequest
from app.schemas.hse_common import ApiWarning
from app.services.common import paginate
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import links, numbering, rpm, suppliers
from app.services.quality import registry as reg
from app.services.quality.q2 import base
from app.services.quality.q2.evaluators import d

C = Capability
RT = QRecordType
A = AttachmentOwner
MS = QMarStatus
IS = QMirStatus
QS = QQuarantineStatus
RELEASE_DISPOSITIONS = {QDisposition.use_as_is, QDisposition.repair, QDisposition.rework}


def _eng_code(db: Session, eid: uuid.UUID | None) -> str | None:
    if eid is None:
        return None
    e = db.get(ProjectEngagement, eid)
    if e is None:
        return None
    from app.models import Contractor  # noqa: PLC0415

    c = db.get(Contractor, e.contractor_id)
    return c.short_code if c else None


# ==== MAR (§C.3.1) ===============================================================================


def mar_ctx(m: QMar) -> rpm.Ctx:
    return rpm.Ctx(None, m.engagement_id, qc.ids(m.created_by_user_id, m.submitted_by_user_id))


def mar_pending(m: QMar) -> list[tuple[str, rpm.Ctx]]:
    return [("approve", mar_ctx(m))] if m.status == MS.submitted else []


def mar_can_view(db: Session, p: Principal, m: QMar) -> bool:
    if m.status == MS.draft and p.user.id != m.created_by_user_id and not p.is_manager:
        g = p.grant(m.project_id, C.material_submit)
        return qc.covers(g, None, m.engagement_id)
    return base.can_view(
        db,
        p,
        m.project_id,
        (C.material_submit, C.material_decide),
        None,
        m.engagement_id,
        rt=RT.mar,
        rid=m.id,
        pending=lambda: mar_pending(m),
        own=(m.created_by_user_id,),
    )


def get_mar(db: Session, p: Principal, mar_id: uuid.UUID) -> QMar:
    m = db.get(QMar, mar_id)
    base.require_view(
        db,
        p,
        m is not None and mar_can_view(db, p, m),
        EntityType.q_mar,
        mar_id,
        m.project_id if m else None,
        "MAR",
    )
    assert m is not None  # noqa: S101
    return m


def revisions(db: Session, m: QMar) -> list[QMar]:
    root = m.root_id or m.id
    return list(
        db.scalars(
            select(QMar).where((QMar.root_id == root) | (QMar.id == root)).order_by(QMar.revision)
        )
    )


def mar_actions(db: Session, p: Principal, m: QMar) -> list[str]:
    out: list[str] = []
    sub = qc.covers(p.grant(m.project_id, C.material_submit), None, m.engagement_id) or p.is_manager
    if sub and m.status == MS.draft:
        out += ["edit", "submit"]
    if (
        sub
        and m.status == MS.revise_resubmit
        and not any(r.revision > m.revision for r in revisions(db, m))
    ):
        out.append("resubmit")
    if m.status == MS.submitted and rpm.resolves(
        db, p, base.project_of(db, m.project_id), RT.mar, "approve", mar_ctx(m), record_id=m.id
    ):
        out.append("decide")
    if m.status in MAR_APPROVED and p.grant(m.project_id, C.quality_settings) is not None:
        out.append("withdraw")
    return out


def mar_read(db: Session, p: Principal, m: QMar, full: bool = True) -> dict[str, Any]:
    sup = db.get(QSupplier, m.supplier_id) if m.supplier_id else None
    hide = base.read_only(p, m.project_id)
    return {
        "id": m.id,
        "project_id": m.project_id,
        "mar_no": m.mar_no,
        "revision": m.revision,
        "root_id": m.root_id or m.id,
        "engagement_id": m.engagement_id,
        "engagement_code": _eng_code(db, m.engagement_id),
        "title_en": m.title_en,
        "title_ar": m.title_ar,
        "category": m.category,
        "spec_section": m.spec_section,
        "manufacturer": m.manufacturer,
        "supplier_id": m.supplier_id,
        "supplier_code": sup.supplier_code if sup else None,
        "country_of_origin": m.country_of_origin,
        "brand_model": m.brand_model,
        "compliance": m.compliance or [],
        "deviations_note": m.deviations_note,
        "with_deviations": m.with_deviations,
        "deviations_accepted": m.deviations_accepted,
        "sample_ref": m.sample_ref,
        "approval_code": m.approval_code,
        "decision_comment": m.decision_comment,
        "submitted_at": m.submitted_at,
        "submitted_by": base.user_ref(db, m.submitted_by_user_id, hide),
        "decided_at": m.decided_at,
        "decided_by": base.user_ref(db, m.decided_by_user_id, hide),
        "status": m.status,
        "status_reason": m.status_reason,
        "document_count": base.attachment_count(db, A.q_mar, m.id),
        "revisions": [
            {
                "id": r.id,
                "revision": r.revision,
                "status": r.status,
                "approval_code": r.approval_code,
            }
            for r in revisions(db, m)
        ]
        if full
        else [],
        "actions": mar_actions(db, p, m) if full else [],
    }


def mar_list(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[QMarStatus] | None,
    category: QMaterialCategory | None,
    q: str | None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.material_submit, C.material_decide)

    def n_ids() -> list[uuid.UUID]:
        return [
            m.id
            for m in db.scalars(
                select(QMar).where(QMar.project_id == project.id, QMar.status != MS.draft)
            )
            if mar_can_view(db, p, m)
        ]

    stmt = select(QMar).where(
        QMar.project_id == project.id,
        base.scope_cond(
            p,
            project.id,
            (C.material_submit, C.material_decide),
            None,
            QMar.engagement_id,
            n_ids,
            QMar.id,
        ),
    )
    if not (p.is_manager or p.grant(project.id, C.material_submit) is not None):
        stmt = stmt.where((QMar.status != MS.draft) | (QMar.created_by_user_id == p.user.id))
    if status:
        stmt = stmt.where(QMar.status.in_(status))
    if category:
        stmt = stmt.where(QMar.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            QMar.mar_no.ilike(like) | QMar.title_en.ilike(like) | QMar.manufacturer.ilike(like)
        )
    items, total = paginate(db, stmt.order_by(QMar.created_at.desc()), page, page_size)
    return {
        "items": [mar_read(db, p, m, full=False) for m in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


MAR_EDIT = (
    "title_en",
    "title_ar",
    "category",
    "spec_section",
    "manufacturer",
    "supplier_id",
    "country_of_origin",
    "brand_model",
    "compliance",
    "deviations_note",
    "sample_ref",
)


def _mar_apply(db: Session, m: QMar, body: dict[str, Any]) -> list[ApiWarning]:
    for k in MAR_EDIT:
        if k in body and (body[k] is not None or k in ("deviations_note", "supplier_id")):
            setattr(m, k, body[k])
    m.category = QMaterialCategory(m.category)
    rows = []
    for i, r in enumerate(m.compliance or []):
        try:
            res = QCompliance(r.get("result") or "complies")
        except ValueError as exc:
            raise qc.field_err(
                f"compliance[{i}].result", "complies, deviation or not_applicable"
            ) from exc
        if not str(r.get("requirement") or "").strip():
            raise qc.field_err(f"compliance[{i}].requirement", "Each row names the requirement.")
        rows.append(
            {
                "requirement": str(r["requirement"])[:300],
                "offered": str(r.get("offered") or "")[:300],
                "result": res.value,
                "note": str(r.get("note") or "")[:300],
            }
        )
    m.compliance = rows
    m.with_deviations = any(r["result"] == QCompliance.deviation.value for r in rows)
    return suppliers.check_use(db, m.supplier_id)


def mar_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QMar, list[ApiWarning]]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.ensure_profile_for(db, project, RT.mar, "A material approval request")
    eng = db.get(ProjectEngagement, body["engagement_id"])
    if eng is None or eng.project_id != project.id:
        raise qc.field_err(
            "engagement_id", "The requesting contractor must be engaged on the project."
        )
    qc.require_cover(p, project.id, C.material_submit, None, eng.id)
    m = QMar(
        id=uuid.uuid4(),
        project_id=project.id,
        revision=0,
        engagement_id=eng.id,
        title_en=body["title_en"],
        category=QMaterialCategory(body["category"]),
        status=MS.draft,
        compliance=[],
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    warnings = _mar_apply(db, m, body)
    db.add(m)
    db.flush()
    base.audit_create(db, p, RT.mar, m, title=m.title_en)
    return m, warnings


def mar_update(
    db: Session, p: Principal, mar_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QMar, list[ApiWarning]]:
    m = get_mar(db, p, mar_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    if m.status != MS.draft:
        raise base.invalid("The MAR", m.status, "edited")
    qc.require_cover(p, project.id, C.material_submit, None, m.engagement_id)
    warnings = _mar_apply(db, m, body)
    m.updated_by_user_id = p.user.id
    db.flush()
    return m, warnings


def mar_submit(db: Session, p: Principal, mar_id: uuid.UUID) -> tuple[QMar, list[ApiWarning]]:
    """Q-MAT-01: ≥ 1 compliance row and the technical data sheet (a document on the MAR); a
    deviation row needs the deviations note (`MAR_INCOMPLETE`)."""
    m = get_mar(db, p, mar_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    if m.status != MS.draft:
        raise base.invalid("The MAR", m.status, "submitted")
    qc.require_cover(p, project.id, C.material_submit, None, m.engagement_id)
    missing = []
    if not m.compliance:
        missing.append("compliance table")
    if base.attachment_count(db, A.q_mar, m.id) == 0:
        missing.append("technical data sheet")
    if m.with_deviations and not (m.deviations_note or "").strip():
        missing.append("deviations note")
    if missing:
        raise qc.err(
            422,
            ErrorCode.MAR_INCOMPLETE,
            "The MAR is incomplete: " + ", ".join(missing) + ".",
            "طلب الاعتماد غير مكتمل: " + "، ".join(missing),
            missing=missing,
        )
    warnings = suppliers.check_use(db, m.supplier_id)
    if m.mar_no is None:
        m.mar_no = numbering.assign(db, project, RT.mar)
    m.submitted_at, m.submitted_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.mar, m, MS.submitted)
    qc.send(
        db,
        base.resolvers(db, project, RT.mar, "approve", mar_ctx(m), m.id),
        f"{m.mar_no} Rev.{m.revision}: material approval request to decide",
        f"{m.mar_no}: طلب اعتماد مواد بانتظار القرار",
        entity_type=EntityType.q_mar,
        entity_id=m.id,
        project_id=project.id,
        key=f"mar_submitted:{m.id}",
        path=f"/quality/materials/{m.id}",
    )
    return m, warnings


def mar_decide(
    db: Session,
    p: Principal,
    mar_id: uuid.UUID,
    code: str,
    comment: str | None,
    accept_deviations: bool,
    paper: dict[str, Any] | None = None,
) -> QMar:
    """Submitted → A / B / C / D (256 + RPM `mar.approve`); B, C and D need a comment ≥ 20 chars;
    a MAR with deviations needs the approver's explicit acceptance for A / B (recorded)."""
    m = get_mar(db, p, mar_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    if m.status != MS.submitted:
        raise base.invalid("The MAR", m.status, "decided")
    code = code.upper()
    if code not in MAR_CODE_STATUS:
        raise qc.field_err("approval_code", "A, B, C or D")
    text = qc.reason(comment, 20, "comment") if code in ("B", "C", "D") else comment
    if m.with_deviations and code in ("A", "B") and not accept_deviations:
        raise qc.field_err(
            "accept_deviations",
            "The MAR has deviations; accept them explicitly to approve.",
            "يحتوي الطلب على انحرافات؛ يجب قبولها صراحةً للاعتماد.",
        )
    accepted = " [deviations accepted]" if m.with_deviations and code in ("A", "B") else ""
    note = f"{text or ''}{accepted}".strip()
    base.sign(db, p, project, RT.mar, m.id, "approve", code, note or None, mar_ctx(m), paper=paper)
    m.approval_code, m.decision_comment = code, text
    m.deviations_accepted = bool(m.with_deviations and code in ("A", "B"))
    m.decided_at, m.decided_by_user_id = now(), p.user.id
    to = MAR_CODE_STATUS[code]
    if to in MAR_APPROVED:
        for old in revisions(db, m):
            if old.id != m.id and old.status in MAR_APPROVED:
                base.set_status(db, p, RT.mar, old, MS.superseded, by=str(m.id))
    base.set_status(db, p, RT.mar, m, to, code=code)
    return m


def mar_resubmit(db: Session, p: Principal, mar_id: uuid.UUID) -> QMar:
    """C → the author's new revision (revision + 1, copied) as a Draft."""
    m = get_mar(db, p, mar_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    if m.status != MS.revise_resubmit:
        raise base.invalid("The MAR", m.status, "resubmitted")
    qc.require_cover(p, project.id, C.material_submit, None, m.engagement_id)
    top = max(r.revision for r in revisions(db, m))
    if top > m.revision:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A later revision already exists.",
            "يوجد إصدار أحدث.",
        )
    n = QMar(
        id=uuid.uuid4(),
        project_id=m.project_id,
        mar_no=m.mar_no,
        revision=m.revision + 1,
        root_id=m.root_id or m.id,
        status=MS.draft,
        alerts_sent=[],
        created_by_user_id=p.user.id,
        engagement_id=m.engagement_id,
        title_en=m.title_en,
        category=m.category,
    )
    for k in MAR_EDIT:
        setattr(n, k, getattr(m, k))
    n.with_deviations = m.with_deviations
    db.add(n)
    db.flush()
    links.add(db, project.id, RT.mar, n.id, RT.mar, m.id, QLinkKind.supersedes, p.user.id)
    base.audit_create(db, p, RT.mar, n, revision=n.revision, mar_no=n.mar_no)
    return n


def mar_withdraw(db: Session, p: Principal, mar_id: uuid.UUID, why: str | None) -> QMar:
    m = get_mar(db, p, mar_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    if m.status not in MAR_APPROVED:
        raise base.invalid("The MAR", m.status, "withdrawn")
    p.require(project.id, C.quality_settings)
    m.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.mar, m, MS.withdrawn, reason=m.status_reason)
    return m


def mar_overdue_alerts(db: Session, at: datetime) -> int:
    """Q-MAT-02: not decided within `mar_review_days` → resolvers and 239 holders."""
    n = 0
    for m in db.scalars(select(QMar).where(QMar.status == MS.submitted)):
        project = db.get(Project, m.project_id)
        if project is None or m.submitted_at is None:
            continue
        days = int(base.setting(db, project.id, "mar_review_days") or 14)
        if base.local_day(project, at) < base.local_day(project, m.submitted_at) + timedelta(
            days=days
        ):
            continue
        users = base.resolvers(db, project, RT.mar, "approve", mar_ctx(m), m.id) + qc.holders_of(
            db, project, C.quality_settings
        )
        n += qc.send(
            db,
            users,
            f"{m.mar_no} Rev.{m.revision}: not decided within {days} days",
            f"{m.mar_no}: لم يُبتّ في الطلب خلال {days} يوماً",
            entity_type=EntityType.q_mar,
            entity_id=m.id,
            project_id=project.id,
            key=f"mar_overdue:{m.id}",
            path=f"/quality/materials/{m.id}",
        )
    return n


# ==== MIR (§C.3.2) ===============================================================================


def mir_ctx(x: QMir) -> rpm.Ctx:
    return rpm.Ctx(x.site_id, x.engagement_id, qc.ids(x.created_by_user_id, x.submitted_by_user_id))


def mir_pending(x: QMir) -> list[tuple[str, rpm.Ctx]]:
    return [("decide", mir_ctx(x))] if x.status == IS.submitted else []


def mir_can_view(db: Session, p: Principal, x: QMir) -> bool:
    return base.can_view(
        db,
        p,
        x.project_id,
        (C.material_submit, C.material_decide),
        x.site_id,
        x.engagement_id,
        rt=RT.mir,
        rid=x.id,
        pending=lambda: mir_pending(x),
        own=(x.created_by_user_id,),
    )


def get_mir(db: Session, p: Principal, mir_id: uuid.UUID) -> QMir:
    x = db.get(QMir, mir_id)
    base.require_view(
        db,
        p,
        x is not None and mir_can_view(db, p, x),
        EntityType.q_mir,
        mir_id,
        x.project_id if x else None,
        "MIR",
    )
    assert x is not None  # noqa: S101
    return x


def heat_mismatch(x: QMir) -> list[str]:
    certs = {h.strip().upper() for h in (x.cert_heat_numbers or []) if h.strip()}
    if not certs and not x.lot_numbers:
        return []
    return [h for h in (x.lot_numbers or []) if h.strip() and h.strip().upper() not in certs]


def _heat_warning(x: QMir) -> list[ApiWarning]:
    bad = heat_mismatch(x)
    if not bad:
        return []
    return [
        qc.warning(
            ErrorCode.HEAT_NUMBER_MISMATCH,
            f"Heat / lot numbers on the tags not on any certificate: {', '.join(bad)}.",
            f"أرقام الصهر على البطاقات غير موجودة في الشهادات: {'، '.join(bad)}",
            "lot_numbers",
        )
    ]


def mir_actions(db: Session, p: Principal, x: QMir) -> list[str]:
    out: list[str] = []
    sub = (
        qc.covers(p.grant(x.project_id, C.material_submit), x.site_id, x.engagement_id)
        or p.is_manager
    )
    if sub and x.status == IS.draft:
        out += ["edit", "submit", "cancel"]
    if x.status == IS.submitted and rpm.resolves(
        db, p, base.project_of(db, x.project_id), RT.mir, "decide", mir_ctx(x), record_id=x.id
    ):
        out.append("decide")
    if x.status == IS.decided and sub:
        out.append("quarantine")
    return out


def mir_read(db: Session, p: Principal, x: QMir, full: bool = True) -> dict[str, Any]:
    mar = db.get(QMar, x.mar_id) if x.mar_id else None
    sup = db.get(QSupplier, x.supplier_id) if x.supplier_id else None
    zone = db.get(Zone, x.storage_zone_id) if x.storage_zone_id else None
    tests = []
    if full:
        for t in db.scalars(select(QTestRequest).where(QTestRequest.mir_id == x.id)):
            tests.append(
                {
                    "id": t.id,
                    "test_no": t.test_no,
                    "test_type_code": t.test_type_code,
                    "verdict": t.verdict,
                    "status": t.status,
                }
            )
    hide = base.read_only(p, x.project_id)
    return {
        "id": x.id,
        "project_id": x.project_id,
        "mir_no": x.mir_no,
        "mar_id": x.mar_id,
        "mar_no": mar.mar_no if mar else None,
        "mar_revision": x.mar_revision,
        "mar_status": mar.status if mar else None,
        "engagement_id": x.engagement_id,
        "engagement_code": _eng_code(db, x.engagement_id),
        "category": x.category,
        "material_description": x.material_description,
        "site_id": x.site_id,
        "delivery_note_no": x.delivery_note_no,
        "po_no": x.po_no,
        "supplier_id": x.supplier_id,
        "supplier_code": sup.supplier_code if sup else None,
        "delivered_at": x.delivered_at,
        "quantity": str(x.quantity),
        "unit": x.unit,
        "lot_numbers": x.lot_numbers or [],
        "cert_heat_numbers": x.cert_heat_numbers or [],
        "heat_mismatch": heat_mismatch(x),
        "storage_zone_id": x.storage_zone_id,
        "storage_zone_code": zone.code if zone else None,
        "accepted_qty": str(x.accepted_qty) if x.accepted_qty is not None else None,
        "rejected_qty": str(x.rejected_qty) if x.rejected_qty is not None else None,
        "result": x.result,
        "decision_comment": x.decision_comment,
        "submitted_at": x.submitted_at,
        "submitted_by": base.user_ref(db, x.submitted_by_user_id, hide),
        "decided_at": x.decided_at,
        "decided_by": base.user_ref(db, x.decided_by_user_id, hide),
        "status": x.status,
        "tests": tests,
        "failed_tests": sum(1 for t in tests if t["verdict"] == QTestVerdict.fail),
        "quarantine_ids": [
            q.id for q in db.scalars(select(QQuarantineItem).where(QQuarantineItem.mir_id == x.id))
        ]
        if full
        else [],
        "certificate_count": base.attachment_count(db, A.q_mir, x.id),
        "actions": mir_actions(db, p, x) if full else [],
    }


def mir_list(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[QMirStatus] | None,
    result: QMirResult | None,
    q: str | None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.material_submit, C.material_decide)

    def n_ids() -> list[uuid.UUID]:
        return [
            x.id
            for x in db.scalars(
                select(QMir).where(QMir.project_id == project.id, QMir.status != IS.draft)
            )
            if mir_can_view(db, p, x)
        ]

    stmt = select(QMir).where(
        QMir.project_id == project.id,
        base.scope_cond(
            p,
            project.id,
            (C.material_submit, C.material_decide),
            QMir.site_id,
            QMir.engagement_id,
            n_ids,
            QMir.id,
        ),
    )
    if status:
        stmt = stmt.where(QMir.status.in_(status))
    if result:
        stmt = stmt.where(QMir.result == result)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            QMir.mir_no.ilike(like)
            | QMir.material_description.ilike(like)
            | QMir.delivery_note_no.ilike(like)
        )
    items, total = paginate(db, stmt.order_by(QMir.created_at.desc()), page, page_size)
    return {
        "items": [mir_read(db, p, x, full=False) for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


MIR_EDIT = (
    "material_description",
    "site_id",
    "delivery_note_no",
    "po_no",
    "supplier_id",
    "delivered_at",
    "quantity",
    "unit",
    "lot_numbers",
    "cert_heat_numbers",
    "storage_zone_id",
)


def _mir_apply(db: Session, project: Project, x: QMir, body: dict[str, Any]) -> list[ApiWarning]:
    for k in MIR_EDIT:
        if k in body and body[k] is not None:
            v = body[k]
            if k in ("lot_numbers", "cert_heat_numbers"):
                v = [str(h).strip()[:40] for h in v if str(h).strip()][:100]
            if k == "quantity":
                v = Decimal(str(v))
            setattr(x, k, v)
    if x.site_id is not None:
        s = db.get(Site, x.site_id)
        if s is None or s.project_id != project.id:
            raise qc.field_err("site_id", "The site does not belong to this project.")
    if x.quantity is not None and x.quantity <= 0:
        raise qc.field_err("quantity", "Quantity must be above 0.")
    return suppliers.check_use(db, x.supplier_id) + _heat_warning(x)


def mir_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QMir, list[ApiWarning]]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.ensure_profile_for(db, project, RT.mir, "A material inspection request")
    mar = db.get(QMar, body["mar_id"]) if body.get("mar_id") else None
    if body.get("mar_id") and (mar is None or mar.project_id != project.id):
        raise qc.field_err("mar_id", "The MAR is not on this project.")
    eng = mar.engagement_id if mar else body.get("engagement_id")  # Q-RPM-07: copied from the MAR
    category = mar.category if mar else QMaterialCategory(body.get("category") or "other")
    qc.require_cover(p, project.id, C.material_submit, body.get("site_id"), eng)
    x = QMir(
        id=uuid.uuid4(),
        project_id=project.id,
        mar_id=mar.id if mar else None,
        mar_revision=mar.revision if mar else None,
        engagement_id=eng,
        category=category,
        material_description=body.get("material_description") or (mar.title_en if mar else "—"),
        quantity=Decimal(str(body["quantity"])),
        unit=body["unit"],
        status=IS.draft,
        lot_numbers=[],
        cert_heat_numbers=[],
        heat_mismatch=[],
        supplier_id=body.get("supplier_id") or (mar.supplier_id if mar else None),
        created_by_user_id=p.user.id,
    )
    warnings = _mir_apply(db, project, x, body)
    db.add(x)
    db.flush()
    if mar is not None:
        links.add(db, project.id, RT.mir, x.id, RT.mar, mar.id, QLinkKind.requires, p.user.id)
    base.audit_create(db, p, RT.mir, x, material=x.material_description)
    return x, warnings


def mir_update(
    db: Session, p: Principal, mir_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QMir, list[ApiWarning]]:
    x = get_mir(db, p, mir_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != IS.draft:
        raise base.invalid("The MIR", x.status, "edited")
    qc.require_cover(p, project.id, C.material_submit, x.site_id, x.engagement_id)
    warnings = _mir_apply(db, project, x, body)
    db.flush()
    return x, warnings


def _required_mar(db: Session, project: Project, x: QMir) -> None:
    """Q-MAT-03: categories in `mar_required_categories` need a MAR of the same material in
    Approved or Approved as Noted (`MAR_NOT_APPROVED`)."""
    required = set(base.setting(db, project.id, "mar_required_categories") or [])
    if x.category.value not in required:
        return
    mar = db.get(QMar, x.mar_id) if x.mar_id else None
    if mar is None or mar.status not in MAR_APPROVED:
        st = mar.status.value if mar else "missing"
        raise qc.err(
            422,
            ErrorCode.MAR_NOT_APPROVED,
            f"{x.category.value} needs an approved MAR before delivery inspection (MAR {st}).",
            "هذه الفئة تتطلب طلب اعتماد مواد معتمداً قبل فحص التوريد.",
            mar_status=st,
        )


def mir_submit(db: Session, p: Principal, mir_id: uuid.UUID) -> tuple[QMir, list[ApiWarning]]:
    x = get_mir(db, p, mir_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != IS.draft:
        raise base.invalid("The MIR", x.status, "submitted")
    qc.require_cover(p, project.id, C.material_submit, x.site_id, x.engagement_id)
    _required_mar(db, project, x)
    x.mir_no = x.mir_no or numbering.assign(db, project, RT.mir)
    x.submitted_at, x.submitted_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.mir, x, IS.submitted)
    qc.send(
        db,
        base.resolvers(db, project, RT.mir, "decide", mir_ctx(x), x.id),
        f"{x.mir_no}: delivery inspection to decide",
        f"{x.mir_no}: فحص مواد موردة بانتظار القرار",
        entity_type=EntityType.q_mir,
        entity_id=x.id,
        project_id=project.id,
        key=f"mir_submitted:{x.id}",
        path=f"/quality/material-inspections/{x.id}",
    )
    return x, suppliers.check_use(db, x.supplier_id) + _heat_warning(x)


def mir_decide(
    db: Session,
    p: Principal,
    mir_id: uuid.UUID,
    body: dict[str, Any],
    paper: dict[str, Any] | None = None,
) -> tuple[QMir, list[ApiWarning]]:
    """Submitted → Decided (256 + RPM `mir.decide`): accepted + rejected = quantity
    (`MIR_QTY_MISMATCH`, Q-MAT-05); heat numbers not on a certificate need a comment ≥ 20 to accept
    (Q-MAT-04); a rejected quantity > 0 creates a quarantine item and an NCR (source mir, major)."""
    x = get_mir(db, p, mir_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != IS.submitted:
        raise base.invalid("The MIR", x.status, "decided")
    result = QMirResult(body["result"])
    acc, rej = d(body.get("accepted_qty")), d(body.get("rejected_qty"))
    if acc is None or rej is None or acc < 0 or rej < 0:
        raise qc.field_err("accepted_qty", "Give the accepted and rejected quantities (≥ 0).")
    if acc + rej != x.quantity:
        raise qc.err(
            422,
            ErrorCode.MIR_QTY_MISMATCH,
            f"Accepted {acc} + rejected {rej} must equal the delivered {x.quantity} {x.unit}.",
            "مجموع الكمية المقبولة والمرفوضة يجب أن يساوي الكمية الموردة.",
        )
    if result == QMirResult.rejected and acc > 0:
        raise qc.field_err(
            "result", "A rejected delivery has no accepted quantity; use accepted with comments."
        )
    if result != QMirResult.rejected and acc == 0:
        raise qc.field_err("result", "Nothing was accepted; the result is rejected.")
    comment = body.get("comment")
    warnings = _heat_warning(x)
    if result in (QMirResult.accepted_with_comments, QMirResult.rejected) or rej > 0:
        comment = qc.reason(comment, 20, "comment")
    if warnings and result != QMirResult.rejected:
        comment = qc.reason(comment, 20, "comment")
    base.sign(
        db, p, project, RT.mir, x.id, "decide", result.value, comment, mir_ctx(x), paper=paper
    )
    x.result, x.accepted_qty, x.rejected_qty, x.decision_comment = result, acc, rej, comment
    x.heat_mismatch = heat_mismatch(x)
    x.decided_at, x.decided_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.mir, x, IS.decided, result=result.value)
    if rej > 0:
        _reject(db, p, project, x, rej)
    return x, warnings


def _reject(db: Session, p: Principal, project: Project, x: QMir, qty: Decimal) -> None:
    from app.services.quality.ncr import core as ncr_core  # noqa: PLC0415

    q = new_quarantine(db, project, p.user.id, x.material_description, qty, x.unit, mir=x)
    owner = x.submitted_by_user_id or p.user.id
    n = ncr_core.auto_raise(
        db,
        project,
        QNcrSourceType.mir,
        x.id,
        raised_by=p.user.id,
        owner_id=owner,
        classification=QNcrClass.major,
        category=QNcrCategory.material,
    )
    q.ncr_id = n.id
    links.add(db, project.id, RT.quarantine, q.id, RT.ncr, n.id, QLinkKind.relates, p.user.id)
    db.flush()
    qc.send(
        db,
        [owner, *ncr_core.engagement_contacts(db, project, x.engagement_id)],
        f"{x.mir_no}: {qty} {x.unit} rejected → {q.tag_no}, {n.ncr_no}",
        f"{x.mir_no}: رُفضت {qty} {x.unit}",
        entity_type=EntityType.q_mir,
        entity_id=x.id,
        project_id=project.id,
        key=f"mir_rejected:{x.id}",
        path=f"/quality/material-inspections/{x.id}",
    )


def mir_cancel(db: Session, p: Principal, mir_id: uuid.UUID, why: str | None) -> QMir:
    x = get_mir(db, p, mir_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != IS.draft:
        raise base.invalid("The MIR", x.status, "cancelled")
    qc.require_cover(p, project.id, C.material_submit, x.site_id, x.engagement_id)
    x.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.mir, x, IS.cancelled)
    return x


def mir_quarantine(
    db: Session, p: Principal, mir_id: uuid.UUID, body: dict[str, Any]
) -> QQuarantineItem:
    """Q-MAT-06: after a failed test of material accepted subject to tests, quarantine the remaining
    stock (entered quantity)."""
    x = get_mir(db, p, mir_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != IS.decided:
        raise base.invalid("The MIR", x.status, "quarantined")
    qc.require_cover(p, project.id, C.material_submit, x.site_id, x.engagement_id)
    qty = d(body.get("quantity"))
    if qty is None or qty <= 0 or qty > (x.accepted_qty or Decimal(0)):
        raise qc.field_err("quantity", "Quantity: above 0 and not more than the accepted quantity.")
    q = new_quarantine(
        db,
        project,
        p.user.id,
        x.material_description,
        qty,
        x.unit,
        mir=x,
        ncr_id=body.get("ncr_id"),
        location_ref=body.get("location_ref"),
    )
    return q


# ==== quarantine (§C.3.3) ========================================================================


def new_quarantine(
    db: Session,
    project: Project,
    user_id: uuid.UUID | None,
    what: str,
    qty: Decimal,
    unit: str,
    *,
    mir: QMir | None = None,
    ncr_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    location_ref: str | None = None,
) -> QQuarantineItem:
    q = QQuarantineItem(
        id=uuid.uuid4(),
        project_id=project.id,
        tag_no=numbering.assign(db, project, RT.quarantine),
        material_description=what[:200],
        mir_id=mir.id if mir else None,
        engagement_id=mir.engagement_id if mir else None,
        quantity=qty,
        unit=unit,
        site_id=site_id or (mir.site_id if mir else None),
        zone_id=zone_id or (mir.storage_zone_id if mir else None),
        location_ref=location_ref,
        ncr_id=ncr_id,
        quarantined_on=qc.project_day(project),
        status=QS.quarantined,
        created_by_user_id=user_id,
    )
    db.add(q)
    db.flush()
    if mir is not None:
        links.add(
            db, project.id, RT.quarantine, q.id, RT.mir, mir.id, QLinkKind.raised_from, user_id
        )
    return q


def q_ctx(db: Session, q: QQuarantineItem) -> rpm.Ctx:
    mir = db.get(QMir, q.mir_id) if q.mir_id else None
    reqs = qc.ids(q.created_by_user_id, mir.submitted_by_user_id if mir else None)
    return rpm.Ctx(q.site_id, q.engagement_id, reqs)


def q_can_view(db: Session, p: Principal, q: QQuarantineItem) -> bool:
    return base.can_view(
        db,
        p,
        q.project_id,
        (C.material_submit, C.material_decide),
        q.site_id,
        q.engagement_id,
        rt=RT.quarantine,
        rid=q.id,
        pending=lambda: [("dispose", q_ctx(db, q))] if q.status == QS.quarantined else [],
        own=(q.created_by_user_id,),
    )


def get_quarantine(db: Session, p: Principal, qid: uuid.UUID) -> QQuarantineItem:
    q = db.get(QQuarantineItem, qid)
    base.require_view(
        db,
        p,
        q is not None and q_can_view(db, p, q),
        EntityType.q_quarantine,
        qid,
        q.project_id if q else None,
        "Quarantine item",
    )
    assert q is not None  # noqa: S101
    return q


def q_read(db: Session, p: Principal, q: QQuarantineItem) -> dict[str, Any]:
    mir = db.get(QMir, q.mir_id) if q.mir_id else None
    ncr = db.get(QNcr, q.ncr_id) if q.ncr_id else None
    zone = db.get(Zone, q.zone_id) if q.zone_id else None
    project = base.project_of(db, q.project_id)
    age = (qc.project_day(project) - q.quarantined_on).days
    acts = []
    if q.status == QS.quarantined and rpm.resolves(
        db, p, project, RT.quarantine, "dispose", q_ctx(db, q), record_id=q.id
    ):
        acts = ["release", "return", "scrap"]
    if q.status == QS.quarantined and qc.covers(
        p.grant(q.project_id, C.material_submit), q.site_id, q.engagement_id
    ):
        acts.append("link_ncr")
    return {
        "id": q.id,
        "project_id": q.project_id,
        "tag_no": q.tag_no,
        "material_description": q.material_description,
        "mir_id": q.mir_id,
        "mir_no": mir.mir_no if mir else None,
        "engagement_id": q.engagement_id,
        "quantity": str(q.quantity),
        "unit": q.unit,
        "site_id": q.site_id,
        "zone_id": q.zone_id,
        "zone_code": zone.code if zone else None,
        "location_ref": q.location_ref,
        "ncr_id": q.ncr_id,
        "ncr_no": ncr.ncr_no if ncr else None,
        "ncr_status": ncr.status if ncr else None,
        "quarantined_on": q.quarantined_on,
        "age_days": age if q.status == QS.quarantined else None,
        "ageing": q.status == QS.quarantined
        and age > int(base.setting(db, q.project_id, "quarantine_ageing_days") or 14),
        "return_note_no": q.return_note_no,
        "disposal_note": q.disposal_note,
        "disposed_at": q.disposed_at,
        "status": q.status,
        "evidence_count": base.attachment_count(db, A.q_quarantine, q.id),
        "actions": acts,
    }


def q_list(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: QQuarantineStatus | None,
    q: str | None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.material_submit, C.material_decide)
    Q = QQuarantineItem  # noqa: N806
    stmt = select(Q).where(
        Q.project_id == project.id,
        base.scope_cond(
            p, project.id, (C.material_submit, C.material_decide), Q.site_id, Q.engagement_id
        ),
    )
    if status:
        stmt = stmt.where(Q.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Q.tag_no.ilike(like) | Q.material_description.ilike(like))
    items, total = paginate(
        db, stmt.order_by(Q.quarantined_on.desc(), Q.tag_no.desc()), page, page_size
    )
    return {
        "items": [q_read(db, p, x) for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def q_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> QQuarantineItem:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.ensure_profile_for(db, project, RT.quarantine, "Quarantined material")
    qc.require_cover(
        p, project.id, C.material_submit, body.get("site_id"), body.get("engagement_id")
    )
    qty = d(body.get("quantity"))
    if qty is None or qty <= 0:
        raise qc.field_err("quantity", "Quantity must be above 0.")
    q = new_quarantine(
        db,
        project,
        p.user.id,
        body["material_description"],
        qty,
        body["unit"],
        zone_id=body.get("zone_id"),
        site_id=body.get("site_id"),
        location_ref=body.get("location_ref"),
        ncr_id=body.get("ncr_id"),
    )
    q.engagement_id = body.get("engagement_id")
    db.flush()
    return q


def q_link_ncr(db: Session, p: Principal, qid: uuid.UUID, ncr_id: uuid.UUID) -> QQuarantineItem:
    q = get_quarantine(db, p, qid)
    project = base.project_of(db, q.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.material_submit, q.site_id, q.engagement_id)
    n = db.get(QNcr, ncr_id)
    if n is None or n.project_id != q.project_id:
        raise qc.field_err("ncr_id", "The NCR is not on this project.")
    q.ncr_id = n.id
    links.add(db, project.id, RT.quarantine, q.id, RT.ncr, n.id, QLinkKind.relates, p.user.id)
    db.flush()
    return q


def _release_ok(db: Session, n: QNcr | None) -> bool:
    if n is None or n.status not in (
        QNcrStatus.disposition_approved,
        QNcrStatus.pending_verification,
        QNcrStatus.closed,
    ):
        return False
    lines = db.scalars(select(QNcrLine).where(QNcrLine.ncr_id == n.id))
    return any(line.disposition in RELEASE_DISPOSITIONS for line in lines)


def q_dispose(
    db: Session,
    p: Principal,
    qid: uuid.UUID,
    body: dict[str, Any],
    paper: dict[str, Any] | None = None,
) -> QQuarantineItem:
    """quarantined → released (linked NCR with an Approved use-as-is / repair / rework disposition,
    else `QUARANTINE_RELEASE_BLOCKED`) · returned (return note no.) · scrapped (disposal evidence);
    256 + RPM `quarantine.dispose` (Q-MAT-07)."""
    q = get_quarantine(db, p, qid)
    project = base.project_of(db, q.project_id)
    qc.writable(project, p)
    if q.status != QS.quarantined:
        raise base.invalid("The quarantine item", q.status, "disposed of")
    to = QQuarantineStatus(body["to_status"])
    if to == QS.released and not _release_ok(db, db.get(QNcr, q.ncr_id) if q.ncr_id else None):
        raise qc.err(
            422,
            ErrorCode.QUARANTINE_RELEASE_BLOCKED,
            "Release needs a linked NCR whose use-as-is, repair or rework disposition is approved.",
            "الإفراج يتطلب تقرير عدم مطابقة مرتبطاً بمعالجة معتمدة "
            "(استخدام كما هو أو إصلاح أو إعادة عمل).",
        )
    if to == QS.returned:
        note = (body.get("return_note_no") or "").strip()
        if not note:
            raise qc.field_err(
                "return_note_no", "Give the return note number.", "أدخل رقم مذكرة الإرجاع."
            )
        q.return_note_no = note[:60]
    if to == QS.scrapped and base.attachment_count(db, A.q_quarantine, q.id) == 0:
        raise qc.field_err(
            "evidence", "Attach the disposal evidence first.", "أرفق دليل الإتلاف أولاً."
        )
    if to == QS.quarantined:
        raise qc.field_err("to_status", "released, returned or scrapped")
    q.disposal_note = (body.get("note") or "").strip()[:1000] or None
    base.sign(
        db,
        p,
        project,
        RT.quarantine,
        q.id,
        "dispose",
        "approved",
        q.disposal_note or to.value,
        q_ctx(db, q),
        paper=paper,
    )
    q.disposed_at, q.disposed_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.quarantine, q, to)
    return q


def ageing_alerts(db: Session, at: datetime) -> int:
    """Q-MAT-08 weekly: items quarantined longer than `quarantine_ageing_days` alert the NCR
    owner."""
    n = 0
    for q in db.scalars(select(QQuarantineItem).where(QQuarantineItem.status == QS.quarantined)):
        project = db.get(Project, q.project_id)
        if project is None:
            continue
        days = int(base.setting(db, project.id, "quarantine_ageing_days") or 14)
        today = qc.project_day(project, at)
        if (today - q.quarantined_on).days <= days:
            continue
        ncr = db.get(QNcr, q.ncr_id) if q.ncr_id else None
        users = [u for u in ((ncr.owner_id if ncr else None), q.created_by_user_id) if u]
        n += qc.send(
            db,
            users,
            f"{q.tag_no}: quarantined for {(today - q.quarantined_on).days} days",
            f"{q.tag_no}: مواد محجوزة منذ {(today - q.quarantined_on).days} يوماً",
            entity_type=EntityType.q_quarantine,
            entity_id=q.id,
            project_id=project.id,
            key=f"qtn_ageing:{q.id}:{today.isocalendar()[0]}-{today.isocalendar()[1]}",
            path=f"/quality/quarantine/{q.id}",
        )
    return n


# ==== NCR source adapters (list NS `mir`) ====================================================


def mir_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    x = db.get(QMir, source_id)
    if x is None or x.project_id != project.id:
        raise qc.field_err("source_id", "The MIR is not on this project.")
    mar = db.get(QMar, x.mar_id) if x.mar_id else None
    return reg.SourceInfo(
        ref=x.mir_no,
        title=f"{x.material_description} rejected on delivery — {x.mir_no}",
        site_id=x.site_id,
        zone_id=x.storage_zone_id,
        engagement_id=x.engagement_id,
        supplier_id=x.supplier_id,
        item_key=f"MAT:{x.category.value}" + (f":{mar.mar_no}" if mar and mar.mar_no else ""),
        detection_stage=QDetectionStage.receiving,
        requirement_en=f"{mar.mar_no} Rev.{mar.revision} ({mar.title_en})"
        if mar
        else "Approved material and certificates",
        finding_en=x.decision_comment,
        proposed_class=QNcrClass.major,
        quantity=x.rejected_qty,
        unit=x.unit,
        lot_refs=tuple((x.lot_numbers or [])[:50]),
        record_type=RT.mir,
    )


def mir_close_check(db: Session, n: QNcr) -> list[reg.Blocker]:
    """An NCR from a rejected delivery closes only once its quarantined material is disposed of."""
    out = []
    for q in db.scalars(
        select(QQuarantineItem).where(
            QQuarantineItem.ncr_id == n.id, QQuarantineItem.status == QS.quarantined
        )
    ):
        out.append(
            reg.Blocker(
                "QUARANTINE_OPEN", f"{q.tag_no} is still quarantined.", f"{q.tag_no} ما زال محجوزاً."
            )
        )
    return out


def mir_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
    x = db.get(QMir, rid)
    return x is not None and mir_can_view(db, p, x)


_ = (NCR_LIVE, func)
