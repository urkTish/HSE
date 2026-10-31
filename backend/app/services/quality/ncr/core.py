"""NCR core (spec 8-quality §A.9.1, §A.9.3, Q-NCR-01…08, -12, -13, -15…-18): raise (manual, from a
source, auto), open with number and target dates, class changes, containment, proposal, the
responsible-person sign-offs (disposition, concession, close), implementation, reopen, void,
effectiveness, supplier response, visibility (P / S / C / N), the list and the read model."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ApiError, ErrorCode, FieldError, not_found
from app.core.hse_enums import AttachmentOwner, CaSourceType, CaStatus
from app.core.quality.common import (
    CLASS_RANK,
    CONCESSION_DISPOSITIONS,
    INTERNAL_STAGES,
    NCR_LIVE,
    NCR_SOURCE_DEFS,
    QDetectionStage,
    QDisposition,
    QEffectiveness,
    QLinkKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QRcaMethod,
    QRecordType,
)
from app.models import Attachment, CorrectiveAction, Project, Site, User
from app.models.quality import QNcr, QNcrCost, QNcrLine, QNcrRca, QSignoff, QSupplier
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, check_engagement, check_site_zone, id_warnings
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, numbering, rpm, signoff, suppliers
from app.services.quality import registry as reg
from app.services.quality import settings as qs
from app.services.quality.ncr import capa

C = Capability
S = CapabilityScope
ST = QNcrStatus
RT = QRecordType.ncr
EVIDENCE_OWNERS = (AttachmentOwner.q_ncr, AttachmentOwner.q_ncr_evidence)
TEXT_FIELDS = (
    "title",
    "requirement_en",
    "requirement_ar",
    "finding_en",
    "finding_ar",
    "location_ref",
    "containment_en",
    "containment_ar",
)
EDITABLE = (
    "site_id",
    "zone_id",
    "system_id",
    "location_ref",
    "title",
    "requirement_en",
    "requirement_ar",
    "finding_en",
    "finding_ar",
    "category",
    "detection_stage",
    "responsible_engagement_id",
    "supplier_id",
    "customer_id",
    "quantity",
    "unit",
    "lot_refs",
    "owner_id",
)


# ---- loading and visibility ---------------------------------------------------------------------


def get_row(db: Session, ncr_id: uuid.UUID) -> QNcr:
    n = db.get(QNcr, ncr_id)
    if n is None:
        raise not_found("NCR")
    return n


def project_of(db: Session, n: QNcr) -> Project:
    project = db.get(Project, n.project_id)
    assert project is not None  # noqa: S101
    return project


def signed_by(db: Session, n: QNcr, uid: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(QSignoff.id).where(
                QSignoff.record_type == RT.value,
                QSignoff.record_id == n.id,
                QSignoff.signed_by_user_id == uid,
            )
        )
        is not None
    )


def can_view(db: Session, p: Principal, n: QNcr) -> bool:
    uid = p.user.id
    if n.status == ST.draft:
        return uid == n.raised_by_user_id or p.is_manager
    if uid in (n.raised_by_user_id, n.owner_id):
        return True
    g = p.grant(n.project_id, C.quality_view)
    if g is None:
        return False
    if g.scope != S.responsible:
        return qc.covers(g, n.site_id, n.responsible_engagement_id)
    # Q-ROL-04: only records where the user resolves for a pending step or has signed
    if signed_by(db, n, uid):
        return True
    project = project_of(db, n)
    return any(
        rpm.resolves(db, p, project, RT, step, ctx_for(n, step), record_id=n.id, can_act=False)
        for step in pending_steps(db, n)
    )


def get_ncr(db: Session, p: Principal, ncr_id: uuid.UUID) -> QNcr:
    n = db.get(QNcr, ncr_id)
    if n is None or not p.can_see_project(n.project_id) or not can_view(db, p, n):
        raise deny(db, p, EntityType.q_ncr, ncr_id, n.project_id if n else None, "NCR")
    return n


def read_only_viewer(p: Principal, project_id: uuid.UUID) -> bool:
    """P8: the Viewer / Client sees aggregates — no names, no photos, no costs."""
    if p.is_manager:
        return False
    scope = p.projects.get(project_id)
    return bool(scope and scope.read_only)


def sees_cost_lines(p: Principal, project_id: uuid.UUID) -> bool:
    """Q-COST-03: cost lines for 242 and 239 holders and the HSE Manager; others totals only."""
    return p.is_manager or any(
        (g := p.grant(project_id, c)) is not None and g.scope != S.responsible
        for c in (C.ncr_manage, C.quality_settings)
    )


# ---- steps (Q-NCR-12, -15) --------------------------------------------------------------------


def needs_concession(db: Session, n: QNcr) -> bool:
    return any(line.disposition in CONCESSION_DISPOSITIONS for line in lines_of(db, n))


def required_steps(db: Session, n: QNcr) -> list[str]:
    if n.status == ST.disposition_proposed:
        return ["disposition", *(["concession"] if needs_concession(db, n) else [])]
    if n.status == ST.pending_verification:
        return ["close"]
    return []


def _approved_since(db: Session, n: QNcr, step: str, since: datetime | None) -> bool:
    s = signoff.latest(db, RT, n.id, step, since)
    return s is not None and s.decision == "approved"


def pending_steps(db: Session, n: QNcr) -> list[str]:
    since = n.disposition_proposed_at if n.status == ST.disposition_proposed else n.implemented_at
    return [s for s in required_steps(db, n) if not _approved_since(db, n, s, since)]


def requesters(n: QNcr, step: str) -> frozenset[uuid.UUID]:
    """Q-RPM-06: the raiser and the owner never sign; nor the user who proposed the
    disposition (disposition, concession) or submitted the implementation (close)."""
    ids = {n.raised_by_user_id, n.owner_id}
    if step in ("disposition", "concession"):
        ids.add(n.disposition_proposed_by_user_id)
    if step == "close":
        ids.add(n.implemented_by_user_id)
    return frozenset(i for i in ids if i is not None)


def ctx_for(n: QNcr, step: str) -> rpm.Ctx:
    return rpm.Ctx(n.site_id, n.responsible_engagement_id, requesters(n, step))


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    """`registry.OPEN_STEPS["Q0"]` for NCRs (Q-RPM-10 / -11)."""
    out = []
    for n in db.scalars(
        select(QNcr).where(
            QNcr.project_id == project.id,
            QNcr.status.in_([ST.disposition_proposed, ST.pending_verification]),
        )
    ):
        since = (
            n.disposition_proposed_at if n.status == ST.disposition_proposed else n.implemented_at
        )
        for step in pending_steps(db, n):
            out.append(
                reg.OpenStep(
                    reg.PendingStep(
                        RT,
                        n.id,
                        n.project_id,
                        n.ncr_no or "NCR",
                        n.title,
                        step,
                        since or n.updated_at,
                        f"/quality/ncrs/{n.id}",
                        "Q0",
                    ),
                    None,
                    n.site_id,
                    n.responsible_engagement_id,
                    requesters(n, step),
                )
            )
    return out


# ---- helpers ----------------------------------------------------------------------------------


def lines_of(db: Session, n: QNcr) -> list[QNcrLine]:
    return list(
        db.scalars(select(QNcrLine).where(QNcrLine.ncr_id == n.id).order_by(QNcrLine.position))
    )


def evidence_count(
    db: Session, n: QNcr, owners: tuple[AttachmentOwner, ...] = EVIDENCE_OWNERS
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.owner_type.in_(owners), Attachment.owner_id == n.id)
        )
        or 0
    )


def _audit(db: Session, p: Principal | None, n: QNcr, action: AuditAction, **kw: Any) -> None:
    audit.record(
        db,
        action,
        p.actor(n.project_id) if p else audit.SYSTEM,
        entity_type=EntityType.q_ncr,
        entity_id=n.id,
        project_id=n.project_id,
        **kw,
    )


def _status(db: Session, p: Principal | None, n: QNcr, to: QNcrStatus, **details: Any) -> None:
    src = n.status
    n.status = to
    n.status_changed_at = now()
    db.flush()
    _audit(
        db,
        p,
        n,
        AuditAction.status_change,
        before={"status": src},
        after={"status": to},
        details=details or None,
    )
    src_def = reg.NCR_SOURCES.get(n.source_type)
    if src_def is not None and src_def.on_ncr_status is not None:
        src_def.on_ncr_status(db, n, to)


def _manager_grant(p: Principal, n: QNcr) -> None:
    """242 in scope (owner work)."""
    g = p.require(n.project_id, C.ncr_manage)
    if not qc.covers(g, n.site_id, n.responsible_engagement_id):
        raise forbidden_error("This NCR is outside your scope.")


def _ensure_live(n: QNcr, *allowed: QNcrStatus) -> None:
    if n.status not in allowed:
        raise invalid_transition("NCR", n.status, "changed")


def _owner_ok(db: Session, project: Project, uid: uuid.UUID) -> None:
    if uid not in qc.holders_of(db, project, C.ncr_manage):
        raise qc.field_err(
            "owner_id",
            "The owner must be a user on the project holding capability 242.",
            "يجب أن يكون مسؤول المعالجة مستخدماً في المشروع لديه الصلاحية 242.",
        )


def _dates(db: Session, n: QNcr) -> None:
    """§A.3 by class, from the original opened_at (Q-NCR-05)."""
    if n.opened_at is None or n.classification is None or n.opened_date is None:
        return
    hours = qs.value(db, n.project_id, "ncr_containment_hours")
    days = qs.value(db, n.project_id, "ncr_target_close_days")
    n.containment_due_at = n.opened_at + timedelta(hours=int(hours[n.classification.value]))
    n.target_close_date = n.opened_date + timedelta(days=int(days[n.classification.value]))


def _texts(n: QNcr) -> list[ApiWarning]:
    return id_warnings(**{k: getattr(n, k) for k in TEXT_FIELDS})


# ---- create (Q-NCR-01 / -02) ------------------------------------------------------------------


def _apply(db: Session, project: Project, n: QNcr, body: dict[str, Any]) -> list[ApiWarning]:
    warnings: list[ApiWarning] = []
    for k in EDITABLE:
        if k in body:
            setattr(n, k, body[k])
    if n.category is not None:
        n.category = QNcrCategory(n.category)
    if n.detection_stage is not None:
        n.detection_stage = QDetectionStage(n.detection_stage)
    if n.site_id is None:
        raise qc.field_err("site_id", "The site is required.", "الموقع مطلوب.")
    check_site_zone(db, project, n.site_id, n.zone_id)
    if n.responsible_engagement_id is not None:
        check_engagement(db, project, n.responsible_engagement_id, "responsible_engagement_id")
    if n.system_id is not None:
        from app.models.quality import QSystem  # noqa: PLC0415

        sys_ = db.get(QSystem, n.system_id)
        if sys_ is None or sys_.project_id != project.id:
            raise qc.field_err("system_id", "The system is not on this project.")
    if n.customer_id is not None:
        from app.models.quality import QCustomer  # noqa: PLC0415

        cu = db.get(QCustomer, n.customer_id)
        if cu is None or cu.project_id != project.id:
            raise qc.field_err("customer_id", "The customer is not on this project.")
    if "supplier_id" in body:
        warnings += suppliers.check_use(db, n.supplier_id)  # Q-SHR-02
    if n.owner_id is not None and "owner_id" in body:
        _owner_ok(db, project, n.owner_id)
    if n.quantity is not None:
        n.quantity = Decimal(str(n.quantity))
        if n.quantity <= 0:
            raise qc.field_err("quantity", "Quantity must be positive.")
    if n.lot_refs and len(n.lot_refs) > 50:
        raise qc.field_err("lot_refs", "At most 50 lots, heats, batches or serials.")
    return warnings + _texts(n)


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QNcr, list[ApiWarning]]:
    """Draft from the register or the phone, or prefilled from a source (Q-NCR-01 / -02); with
    `open = true` it is opened in the same request."""
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    prof = qc.require_profile(db, project)
    cu = body.get("client_uuid")
    if cu is not None:
        dup = db.scalar(select(QNcr).where(QNcr.client_uuid == cu))
        if dup is not None:
            if dup.raised_by_user_id != p.user.id:
                raise forbidden_error()
            return dup, []
    st = QNcrSourceType(body.get("source_type") or "manual")
    g = p.require(project.id, C.ncr_raise)
    info: reg.SourceInfo | None = None
    if st != QNcrSourceType.manual:
        from app.services.quality import ensure_registered  # noqa: PLC0415

        ensure_registered()
        src = reg.NCR_SOURCES.get(st)
        if src is None or body.get("source_id") is None:
            raise qc.field_err("source_id", f"Source {st.value} is not available on this install.")
        info = src.resolve(db, project, body["source_id"])
    elif g.scope == S.responsible:
        raise forbidden_error("A responsible person raises NCRs from a record they act on.")
    data = dict(body)
    if info is not None:
        prefill = {
            "site_id": info.site_id,
            "zone_id": info.zone_id,
            "system_id": info.system_id,
            "responsible_engagement_id": info.engagement_id,
            "supplier_id": info.supplier_id,
            "customer_id": info.customer_id,
            "detection_stage": info.detection_stage,
            "title": info.title,
            "requirement_en": info.requirement_en,
            "requirement_ar": info.requirement_ar,
            "finding_en": info.finding_en,
            "finding_ar": info.finding_ar,
            "location_ref": info.location_ref,
            "quantity": info.quantity,
            "unit": info.unit,
            "lot_refs": list(info.lot_refs) if info.lot_refs else None,
        }
        for k, v in prefill.items():
            if data.get(k) is None and v is not None:
                data[k] = v
        if data.get("classification") is None:
            data["classification"] = info.proposed_class or NCR_SOURCE_DEFS[st][1]
    if g.scope != S.responsible and not qc.covers(
        g, data.get("site_id"), data.get("responsible_engagement_id")
    ):
        raise forbidden_error("This site or contractor is outside your scope.")
    n = QNcr(
        id=uuid.uuid4(),
        project_id=project.id,
        profile=prof,
        source_type=st,
        source_id=body.get("source_id") if st != QNcrSourceType.manual else None,
        source_ref=info.ref if info else None,
        item_key=info.item_key if info else None,
        title=(data.get("title") or "").strip() or "—",
        status=ST.draft,
        raised_by_user_id=p.user.id,
        owner_id=data.get("owner_id"),
        client_uuid=cu,
        lot_refs=[],
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    data.setdefault("title", n.title)
    warnings = _apply(db, project, n, {k: data[k] for k in EDITABLE if k in data})
    if data.get("classification") is not None:
        n.classification = QNcrClass(data["classification"])
    db.add(n)
    db.flush()
    if info is not None and info.record_type is not None and n.source_id is not None:
        links.add(
            db,
            project.id,
            RT,
            n.id,
            info.record_type,
            n.source_id,
            QLinkKind.raised_from,
            p.user.id,
        )
    _audit(db, p, n, AuditAction.create, after={"source": st.value, "title": n.title})
    if body.get("open"):
        warnings += open_ncr(db, p, n.id)[1]
    return n, warnings


def auto_raise(
    db: Session,
    project: Project,
    source_type: QNcrSourceType,
    source_id: uuid.UUID,
    *,
    raised_by: uuid.UUID | None,
    owner_id: uuid.UUID,
    classification: QNcrClass | None = None,
    category: QNcrCategory = QNcrCategory.other,
    title: str | None = None,
) -> QNcr:
    """— → Open by the System (list NS raise mode `auto`): for wave-2 parts. The raiser is the
    user whose action triggered it (or None for jobs); Q-NCR-03 fields come from the adapter."""
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    info = reg.NCR_SOURCES[source_type].resolve(db, project, source_id)
    n = QNcr(
        id=uuid.uuid4(),
        project_id=project.id,
        profile=qc.require_profile(db, project),
        source_type=source_type,
        source_id=source_id,
        source_ref=info.ref,
        item_key=info.item_key,
        site_id=info.site_id,
        zone_id=info.zone_id,
        system_id=info.system_id,
        location_ref=info.location_ref,
        title=title or info.title or info.ref or source_type.value,
        requirement_en=info.requirement_en,
        requirement_ar=info.requirement_ar,
        finding_en=info.finding_en,
        finding_ar=info.finding_ar,
        category=category,
        detection_stage=info.detection_stage or QDetectionStage.in_process,
        classification=classification
        or info.proposed_class
        or NCR_SOURCE_DEFS[source_type][1]
        or QNcrClass.major,
        responsible_engagement_id=info.engagement_id,
        supplier_id=info.supplier_id,
        customer_id=info.customer_id,
        quantity=info.quantity,
        unit=info.unit,
        lot_refs=list(info.lot_refs),
        raised_by_user_id=raised_by,
        owner_id=owner_id,
        status=ST.draft,
        alerts_sent=[],
        created_by_user_id=raised_by,
    )
    db.add(n)
    db.flush()
    if info.record_type is not None:
        links.add(
            db, project.id, RT, n.id, info.record_type, source_id, QLinkKind.raised_from, raised_by
        )
    _do_open(db, None, project, n)
    return n


# ---- edit -------------------------------------------------------------------------------------


def update(
    db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QNcr, list[ApiWarning]]:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status == ST.draft:
        if p.user.id != n.raised_by_user_id:
            raise forbidden_error()
    else:
        _ensure_live(
            n, ST.open, ST.disposition_proposed, ST.disposition_approved, ST.pending_verification
        )
        _manager_grant(p, n)
    before = {k: getattr(n, k) for k in EDITABLE}
    changes = {k: v for k, v in body.items() if k in EDITABLE}
    if n.status != ST.draft:
        for k in ("site_id",):
            changes.pop(k, None) if changes.get(k) == getattr(n, k) else None
    warnings = _apply(db, project, n, changes)
    if "classification" in body and body["classification"] is not None:
        if n.status == ST.draft:
            n.classification = QNcrClass(body["classification"])
        elif QNcrClass(body["classification"]) != n.classification:
            raise qc.field_err(
                "classification", "Change the class with the class action (Q-NCR-05)."
            )
    n.updated_by_user_id = p.user.id
    db.flush()
    after = {k: getattr(n, k) for k in EDITABLE}
    b, a = audit.diff(before, after)
    if a:
        _audit(db, p, n, AuditAction.update, before=b, after=a)
    return n, warnings


def delete_draft(db: Session, p: Principal, ncr_id: uuid.UUID) -> None:
    n = get_ncr(db, p, ncr_id)
    if n.status != ST.draft or n.ncr_no is not None:
        raise invalid_transition("NCR", n.status, "deleted")
    if p.user.id != n.raised_by_user_id:
        raise forbidden_error("Only the raiser deletes a draft.")
    _audit(db, p, n, AuditAction.archive, details={"draft_deleted": True})
    from app.models.quality import QLink  # noqa: PLC0415

    for link in db.scalars(select(QLink).where(or_(QLink.from_id == n.id, QLink.to_id == n.id))):
        db.delete(link)
    for line in lines_of(db, n):
        db.delete(line)
    db.delete(n)
    db.flush()


# ---- open (Q-NCR-03, -06, -16) ----------------------------------------------------------------


def _open_problems(db: Session, n: QNcr) -> list[FieldError]:
    miss: list[tuple[str, str]] = []
    if not (n.title or "").strip() or n.title == "—":
        miss.append(("title", "The title is required."))
    if not qc.text_of(n.requirement_en, n.requirement_ar):
        miss.append(("requirement_en", "State the requirement (one language)."))
    if not qc.text_of(n.finding_en, n.finding_ar):
        miss.append(("finding_en", "State the finding (one language)."))
    for k in (
        "category",
        "detection_stage",
        "classification",
        "responsible_engagement_id",
        "owner_id",
    ):
        if getattr(n, k) is None:
            miss.append((k, f"{k} is required to open the NCR."))
    return [FieldError(loc=["body", k], msg=m, type="missing") for k, m in miss]


def open_ncr(db: Session, p: Principal, ncr_id: uuid.UUID) -> tuple[QNcr, list[ApiWarning]]:
    """Draft → Open by the raiser (241)."""
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status != ST.draft:
        raise invalid_transition("NCR", n.status, ST.open)
    if p.user.id != n.raised_by_user_id:
        raise forbidden_error("The raiser opens the draft.")
    p.require(project.id, C.ncr_raise)
    warnings = _do_open(db, p, project, n)
    return n, warnings


def _do_open(db: Session, p: Principal | None, project: Project, n: QNcr) -> list[ApiWarning]:
    problems = _open_problems(db, n)
    if problems:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Complete the NCR before opening it: " + "; ".join(e.msg for e in problems),
            "أكمل بيانات التقرير قبل فتحه.",
            errors=problems,
        )
    if n.classification == QNcrClass.critical and evidence_count(db, n) == 0:
        raise qc.err(
            422,
            ErrorCode.EVIDENCE_REQUIRED,
            "A critical NCR needs at least one photo or evidence file (Q-NCR-03).",
            "يتطلب التقرير الحرج صورة أو ملف دليل واحد على الأقل.",
        )
    if n.supplier_id is not None:
        suppliers.check_use(db, n.supplier_id)
    at = now()
    n.opened_at = at
    n.opened_date = qc.project_day(project, at)
    n.ncr_no = numbering.assign(db, project, RT, on=n.opened_date)
    row = qc.settings_row(db, project.id)
    n.before_quality_start = bool(
        row and row.quality_start_date and n.opened_date < row.quality_start_date
    )
    warnings: list[ApiWarning] = []
    rep = find_repeat(db, n)
    if rep is not None:
        n.repeat_of_id = rep.id
        if n.classification == QNcrClass.minor:
            n.classification = QNcrClass.major  # Q-NCR-16: raised by the repeat rule
        warnings.append(
            qc.warning(
                "NCR_REPEAT",
                f"Repeat of {rep.ncr_no}: raised to major if minor; RCA must be 5-Why, Ishikawa "
                f"or 8D.",
                f"تكرار للتقرير {rep.ncr_no}: يُرفع إلى جوهري، ويجب أن يكون التحليل 5-Why أو "
                "عظم السمكة أو 8D.",
            )
        )
    if n.before_quality_start:
        warnings.append(
            qc.warning(
                ErrorCode.BEFORE_QUALITY_START,
                "Before the project's Quality start date (excluded from KPIs).",
                "قبل تاريخ بدء الجودة في المشروع (مستبعد من المؤشرات).",
            )
        )
    _dates(db, n)
    _status(db, p, n, ST.open, ncr_no=n.ncr_no)
    _notify_opened(db, project, n)
    return warnings


def find_repeat(db: Session, n: QNcr) -> QNcr | None:
    """Q-NCR-16: same category, same responsible party (supplier when set, else responsible
    engagement) and same item_key, opened within the previous `ncr_repeat_days`, not voided."""
    if n.item_key is None or n.category is None or n.opened_date is None:
        return None
    days = int(qs.value(db, n.project_id, "ncr_repeat_days"))
    party = (
        QNcr.supplier_id == n.supplier_id
        if n.supplier_id is not None
        else and_(
            QNcr.supplier_id.is_(None),
            QNcr.responsible_engagement_id == n.responsible_engagement_id,
        )
    )
    return db.scalar(
        select(QNcr)
        .where(
            QNcr.project_id == n.project_id,
            QNcr.id != n.id,
            QNcr.category == n.category,
            QNcr.item_key == n.item_key,
            party,
            QNcr.status.notin_([ST.voided, ST.draft]),
            QNcr.opened_date >= n.opened_date - timedelta(days=days),
            QNcr.opened_date <= n.opened_date,
        )
        .order_by(QNcr.opened_date.desc())
        .limit(1)
    )


def engagement_contacts(db: Session, project: Project, eng_id: uuid.UUID | None) -> set[uuid.UUID]:
    """Contractor-assigned quality users whose engagement tree holds the engagement."""
    from app.services.permissions import QUALITY_ROLES, engagement_descendants  # noqa: PLC0415

    out: set[uuid.UUID] = set()
    if eng_id is None:
        return out
    for role in QUALITY_ROLES:
        for a in qc.role_holders(db, project, role):
            if a.contractor_engagement_id and eng_id in engagement_descendants(
                db, a.contractor_engagement_id
            ):
                out.add(a.user_id)
    return out


def _notify_opened(db: Session, project: Project, n: QNcr) -> None:
    """Q-NCR-06: owner, the engagement's quality contacts, the `ncr.disposition` resolvers and,
    for critical, every 239 holder (in-app + email)."""
    who: set[uuid.UUID] = {n.owner_id} if n.owner_id else set()
    who |= engagement_contacts(db, project, n.responsible_engagement_id)
    res = rpm.resolve(db, project, RT, "disposition", ctx_for(n, "disposition"), record_id=n.id)
    who |= set(res.users)
    if n.classification == QNcrClass.critical:
        who |= set(qc.holders_of(db, project, C.quality_settings, include_manager=False))
    cls = n.classification.value if n.classification else ""
    qc.send(
        db,
        who,
        f"{n.ncr_no} opened ({cls}): {n.title}",
        f"فُتح تقرير عدم المطابقة {n.ncr_no} ({cls}): {n.title}",
        entity_type=EntityType.q_ncr,
        entity_id=n.id,
        project_id=n.project_id,
        key=f"ncr_opened:{n.id}",
        path=f"/quality/ncrs/{n.id}",
    )


# ---- class (Q-NCR-05) ---------------------------------------------------------------------------


def set_class(
    db: Session, p: Principal, ncr_id: uuid.UUID, cls: QNcrClass, why: str | None
) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    _ensure_live(
        n, ST.open, ST.disposition_proposed, ST.disposition_approved, ST.pending_verification
    )
    old = n.classification
    if old == cls:
        return n
    lowering = old is not None and CLASS_RANK[cls] < CLASS_RANK[old]
    details: dict[str, Any] = {}
    if lowering:
        text = qc.reason(why, 20)
        try:
            rpm.check_signer(
                db, p, project, RT, "disposition", ctx_for(n, "disposition"), record_id=n.id
            )
        except ApiError as e:
            if e.code == ErrorCode.RESPONSIBLE_PERSON_NOT_SET:
                raise
            raise qc.err(
                422,
                ErrorCode.CLASS_LOWERED_NEEDS_APPROVAL,
                "Only the responsible person for the disposition may lower the class, with a "
                "reason (Q-NCR-05).",
                "لا يخفض التصنيف إلا الشخص المسؤول عن اعتماد المعالجة مع ذكر السبب.",
            ) from e
        details["reason"] = text
        if n.repeat_of_id is not None and cls == QNcrClass.minor:
            raise qc.err(
                422,
                ErrorCode.CLASS_LOWERED_NEEDS_APPROVAL,
                "A repeat NCR stays at least major (Q-NCR-16).",
                "يبقى التقرير المتكرر جوهرياً على الأقل.",
            )
    else:
        _manager_grant(p, n)
        if why:
            details["reason"] = why.strip()
    n.classification = cls
    _dates(db, n)
    n.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        n,
        AuditAction.update,
        before={"classification": old},
        after={"classification": cls},
        details=details or None,
    )
    return n


# ---- containment (Q-NCR-07) -------------------------------------------------------------------


def set_containment(db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    _ensure_live(n, ST.open, ST.disposition_proposed, ST.disposition_approved)
    _manager_grant(p, n)
    before = {
        "containment_en": n.containment_en,
        "containment_ar": n.containment_ar,
        "done": n.containment_done_at,
    }
    for k in ("containment_en", "containment_ar"):
        if k in body:
            setattr(n, k, (body[k] or "").strip() or None)
    if "no_product_affected" in body and body["no_product_affected"] is not None:
        n.no_product_affected = bool(body["no_product_affected"])
        if n.no_product_affected and len(qc.text_of(n.containment_en, n.containment_ar)) < 20:
            raise qc.field_err(
                "containment_en",
                "Give the reason why no product is affected (at least 20 characters).",
                "اذكر سبب عدم تأثر أي منتج (20 حرفاً على الأقل).",
            )
    if body.get("done"):
        if not qc.text_of(n.containment_en, n.containment_ar):
            raise qc.field_err("containment_en", "Describe the containment first.")
        n.containment_done_at = now()
        n.containment_by_user_id = p.user.id
    n.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        n,
        AuditAction.update,
        before=before,
        after={
            "containment_en": n.containment_en,
            "containment_ar": n.containment_ar,
            "done": n.containment_done_at,
        },
    )
    return n


def containment_ok(db: Session, n: QNcr) -> bool:
    if n.classification not in (QNcrClass.major, QNcrClass.critical):
        return True
    if n.containment_done_at is not None and qc.text_of(n.containment_en, n.containment_ar):
        return True
    # logistics: a linked Q3 hold counts as containment
    from app.models.quality import QLink  # noqa: PLC0415

    return (
        db.scalar(
            select(QLink.id).where(
                or_(
                    (QLink.from_id == n.id) & (QLink.to_type == QRecordType.hold.value),
                    (QLink.to_id == n.id) & (QLink.from_type == QRecordType.hold.value),
                )
            )
        )
        is not None
    )


# ---- propose (Open → Disposition Proposed) ------------------------------------------------------


def rca_of(db: Session, n: QNcr) -> QNcrRca | None:
    return db.scalar(select(QNcrRca).where(QNcrRca.ncr_id == n.id))


def live_cas(db: Session, n: QNcr) -> list[CorrectiveAction]:
    return [
        c for c in capa.cas_of(db, CaSourceType.quality_ncr, n.id) if c.status != CaStatus.cancelled
    ]


def propose(db: Session, p: Principal, ncr_id: uuid.UUID) -> QNcr:
    from app.services.quality.ncr import disposition, rca  # noqa: PLC0415

    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status != ST.open:
        raise invalid_transition("NCR", n.status, ST.disposition_proposed)
    _manager_grant(p, n)
    if not containment_ok(db, n):
        raise qc.err(
            422,
            ErrorCode.CONTAINMENT_REQUIRED,
            "Record the containment of this major / critical NCR first (Q-NCR-07).",
            "سجّل إجراءات الاحتواء لهذا التقرير الجوهري أو الحرج أولاً.",
        )
    r = rca_of(db, n)
    rca.check_for_propose(db, n, r)
    disposition.check(db, n, lines_of(db, n), final=True)
    needs_ca = n.classification in (QNcrClass.major, QNcrClass.critical) or (
        r is not None and r.method != QRcaMethod.simple
    )
    if needs_ca and not live_cas(db, n):
        raise qc.err(
            422,
            ErrorCode.CA_REQUIRED,
            "Plan at least one corrective action (not cancelled) before proposing the "
            "disposition (Q-CAP-02).",
            "خطط إجراءً تصحيحياً واحداً على الأقل قبل اقتراح المعالجة.",
        )
    n.disposition_proposed_at = now()
    n.disposition_proposed_by_user_id = p.user.id
    _status(db, p, n, ST.disposition_proposed)
    _notify_step(db, project, n)
    return n


def _notify_step(db: Session, project: Project, n: QNcr) -> None:
    """Step pending for me (§A.13), at the step."""
    for step in pending_steps(db, n):
        res = rpm.resolve(db, project, RT, step, ctx_for(n, step), record_id=n.id)
        qc.send(
            db,
            [u for u in res.users if u not in requesters(n, step)],
            f"{n.ncr_no}: {step} waiting for your sign-off",
            f"{n.ncr_no}: الخطوة بانتظار توقيعك",
            entity_type=EntityType.q_ncr,
            entity_id=n.id,
            project_id=n.project_id,
            key=f"ncr_step:{n.id}:{step}:{(n.disposition_proposed_at or n.implemented_at)}",
            path=f"/quality/ncrs/{n.id}",
        )


# ---- sign-offs (Q-NCR-12, -15) ----------------------------------------------------------------


def close_blockers(db: Session, n: QNcr) -> list[reg.Blocker]:
    out: list[reg.Blocker] = []
    open_cas = [
        c
        for c in capa.cas_of(db, CaSourceType.quality_ncr, n.id)
        if c.status not in (CaStatus.closed, CaStatus.cancelled)
    ]
    if open_cas:
        out.append(
            reg.Blocker(
                "CA_OPEN",
                f"Corrective actions still open: {', '.join(c.ref for c in open_cas)}.",
                "إجراءات تصحيحية ما زالت مفتوحة.",
            )
        )
    for line in lines_of(db, n):
        if line.disposition == QDisposition.reject_return and not line.return_ref:
            out.append(
                reg.Blocker(
                    "RETURN_NOT_EVIDENCED",
                    "A reject-and-return line has no return note or claim no.",
                    "بند الإرجاع بلا مذكرة إرجاع أو رقم مطالبة.",
                )
            )
        if line.disposition == QDisposition.reject_scrap and not line.destruction_evidenced:
            out.append(
                reg.Blocker(
                    "DESTRUCTION_NOT_EVIDENCED",
                    "A reject-and-scrap line has no destruction evidence.",
                    "بند الإتلاف بلا دليل إتلاف.",
                )
            )
    has_cost = db.scalar(select(QNcrCost.id).where(QNcrCost.ncr_id == n.id).limit(1))
    if has_cost is None and not n.no_cost_reason:
        out.append(
            reg.Blocker(
                ErrorCode.COST_NOT_RECORDED.value,
                'Record the costs or confirm "no cost incurred" (Q-NCR-14).',
                "سجّل التكاليف أو أكّد عدم وجود تكلفة.",
            )
        )
    src = reg.NCR_SOURCES.get(n.source_type)
    if src is not None and src.close_check is not None:
        out += src.close_check(db, n)
    return out


def sign_step(
    db: Session,
    p: Principal,
    ncr_id: uuid.UUID,
    step: str,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    expected = {
        "disposition": ST.disposition_proposed,
        "concession": ST.disposition_proposed,
        "close": ST.pending_verification,
    }.get(step)
    if expected is None:
        raise qc.field_err("step", "disposition, concession or close")
    if n.status != expected or step not in required_steps(db, n):
        raise invalid_transition("NCR", n.status, f"{step} sign-off")
    if step not in pending_steps(db, n):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            f"The {step} step is already signed.",
            "تم توقيع هذه الخطوة مسبقاً.",
        )
    negative = decision in ("returned", "rejected")
    text = qc.reason(comment, 20, "comment") if negative else comment
    ctx = ctx_for(n, step)
    if paper:
        s = signoff.sign_paper(db, p, project, RT, n.id, step, decision, text, paper, ctx)
    else:
        rule, capacity = rpm.check_signer(db, p, project, RT, step, ctx, record_id=n.id)
        if step == "close" and decision == "approved":
            _raise_blockers(db, n)
        s = signoff.sign(db, p, project, RT, n.id, step, decision, text, rule, capacity)
    if step == "close" and decision == "approved" and paper:
        _raise_blockers(db, n)
    if step in ("disposition", "concession"):
        if negative:
            _status(db, p, n, ST.open, step=step, comment=text)
        elif not pending_steps(db, n):
            n.disposition_approved_at = now()
            _status(db, p, n, ST.disposition_approved, signoff=str(s.id))
    elif negative:
        _status(db, p, n, ST.disposition_approved, verification="failed", comment=text)
    else:
        _close(db, p, project, n)
    return n


def _raise_blockers(db: Session, n: QNcr) -> None:
    blockers = close_blockers(db, n)
    if blockers:
        raise qc.err(
            422,
            ErrorCode.NCR_CLOSE_BLOCKED,
            "The NCR cannot be closed yet: " + " ".join(b.detail_en for b in blockers),
            "لا يمكن إغلاق التقرير بعد.",
            blockers=[b.__dict__ for b in blockers],
        )


def _close(db: Session, p: Principal | None, project: Project, n: QNcr) -> None:
    at = now()
    n.closed_at = at
    n.closed_date = qc.project_day(project, at)
    days = int(qs.value(db, n.project_id, "ncr_effectiveness_days"))
    n.effectiveness = {"due_on": (n.closed_date + timedelta(days=days)).isoformat()}
    _status(db, p, n, ST.closed)


# ---- implementation (Disposition Approved → Pending Verification) ------------------------------


def implement(db: Session, p: Principal, ncr_id: uuid.UUID, note: str | None) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status != ST.disposition_approved:
        raise invalid_transition("NCR", n.status, ST.pending_verification)
    _manager_grant(p, n)
    text = (note or "").strip()
    if len(text) < 20 and evidence_count(db, n, (AttachmentOwner.q_ncr_evidence,)) == 0:
        raise qc.field_err(
            "implementation_note",
            "Describe the implementation (≥ 20 characters) or attach evidence.",
            "صف التنفيذ أو أرفق دليلاً.",
        )
    bad = [
        c.ref for c in capa.cas_of(db, CaSourceType.quality_ncr, n.id) if c.status == CaStatus.open
    ]
    if bad:
        raise qc.err(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            f"Corrective actions not started yet: {', '.join(bad)}.",
            "إجراءات تصحيحية لم تبدأ بعد.",
            actions=bad,
        )
    n.implementation_note = text or n.implementation_note
    n.implemented_at = now()
    n.implemented_by_user_id = p.user.id
    _status(db, p, n, ST.pending_verification)
    _notify_step(db, project, n)
    return n


def add_action(
    db: Session, p: Principal, ncr_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QNcr, list[ApiWarning]]:
    """A Phase 1 CA (source quality_ncr) created inline by a 242 holder (Q-CAP-02…05)."""
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    _manager_grant(p, n)
    if n.status not in NCR_LIVE:
        raise invalid_transition("NCR", n.status, "action")
    _ca, warnings = capa.create_for(
        db, p, project, CaSourceType.quality_ncr, n, body, n.classification
    )
    return n, warnings


# ---- reopen / void -------------------------------------------------------------------------------


def reopen(db: Session, p: Principal, ncr_id: uuid.UUID, why: str | None) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status != ST.closed or n.closed_date is None:
        raise invalid_transition("NCR", n.status, ST.open)
    p.require(project.id, C.quality_settings)
    text = qc.reason(why, 20)
    if (qc.project_day(project) - n.closed_date).days > 30:
        raise qc.err(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "An NCR may be reopened within 30 days of closure; raise a new one.",
            "يُعاد فتح التقرير خلال 30 يوماً من إغلاقه فقط.",
        )
    n.closed_at = None
    n.closed_date = None
    n.effectiveness = None
    n.reopened_count = (n.reopened_count or 0) + 1
    _status(db, p, n, ST.open, reason=text, reopened=True)
    return n


def void(
    db: Session, p: Principal, ncr_id: uuid.UUID, why: str | None, duplicate_of: uuid.UUID | None
) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    _ensure_live(n, ST.draft, ST.open, ST.disposition_proposed, ST.disposition_approved)
    p.require(project.id, C.quality_void)
    text = qc.reason(why, 20)
    if duplicate_of is not None:
        dup = db.get(QNcr, duplicate_of)
        if dup is None or dup.project_id != n.project_id or dup.id == n.id:
            raise qc.field_err("duplicate_of", "The duplicate must be another NCR of the project.")
        n.duplicate_of_id = dup.id
    elif "duplicate" in text.lower():
        raise qc.field_err("duplicate_of", "Name the NCR this one duplicates.")
    n.status_reason = text
    _status(db, p, n, ST.voided, reason=text)
    # Q-CAP-08: CAs stay; their verifiers are told the source is voided
    for c in capa.cas_of(db, CaSourceType.quality_ncr, n.id):
        if c.status not in (CaStatus.closed, CaStatus.cancelled):
            qc.send(
                db,
                [c.verifier_id],
                f"{c.ref}: source {n.ncr_no or 'NCR'} voided",
                f"{c.ref}: أُلغي المصدر {n.ncr_no or ''}",
                entity_type=EntityType.corrective_action,
                entity_id=c.id,
                project_id=n.project_id,
                email=False,
                key=f"ca_source_voided:{c.id}",
            )
    return n


# ---- effectiveness (Q-NCR-17) -------------------------------------------------------------------


def propose_effectiveness(db: Session, n: QNcr) -> str:
    """Job: effective when no repeat (Q-NCR-16 key) was opened since closure."""
    if n.closed_date is None:
        return "not_closed"
    stmt = select(QNcr.id).where(
        QNcr.project_id == n.project_id,
        QNcr.id != n.id,
        QNcr.category == n.category,
        QNcr.item_key == n.item_key,
        QNcr.status.notin_([ST.voided, ST.draft]),
        QNcr.opened_date > n.closed_date,
    )
    stmt = stmt.where(
        QNcr.supplier_id == n.supplier_id
        if n.supplier_id is not None
        else QNcr.responsible_engagement_id == n.responsible_engagement_id
    )
    repeat = n.item_key is not None and db.scalar(stmt.limit(1)) is not None
    return QEffectiveness.not_effective.value if repeat else QEffectiveness.effective.value


def confirm_effectiveness(
    db: Session, p: Principal, ncr_id: uuid.UUID, result: QEffectiveness, note: str | None
) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    if n.status != ST.closed:
        raise invalid_transition("NCR", n.status, "effectiveness")
    _manager_grant(p, n)
    eff = dict(n.effectiveness or {})
    if eff.get("result"):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Effectiveness is already confirmed.",
            "تم تأكيد الفعالية مسبقاً.",
        )
    eff.update(
        {
            "result": result.value,
            "note": (note or "").strip() or None,
            "by": str(p.user.id),
            "at": now().isoformat(),
        }
    )
    n.effectiveness = eff
    db.flush()
    _audit(db, p, n, AuditAction.update, after={"effectiveness": result.value})
    return n


# ---- supplier response / SCAR (Q-NCR-13) -----------------------------------------------------


def supplier_response(
    db: Session, p: Principal, ncr_id: uuid.UUID, action: str, body: dict[str, Any]
) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    project = project_of(db, n)
    qc.writable(project, p)
    _ensure_live(
        n, ST.open, ST.disposition_proposed, ST.disposition_approved, ST.pending_verification
    )
    _manager_grant(p, n)
    if n.supplier_id is None:
        raise qc.field_err("supplier_id", "The NCR names no supplier.")
    sr = dict(n.supplier_response or {})
    today = qc.project_day(project)
    if action == "request":
        due = body.get("due_on") or (today + timedelta(days=14))
        sr = {
            "requested_at": now().isoformat(),
            "due_on": str(due),
            "received_at": None,
            "accepted": None,
            "note": body.get("note"),
        }
    elif action == "receive":
        if not sr.get("requested_at"):
            raise invalid_transition("Supplier response", "none", "received")
        sr["received_at"] = now().isoformat()
        sr["received_on_time"] = today.isoformat() <= str(sr.get("due_on"))
        sr["note"] = body.get("note") or sr.get("note")
    elif action in ("accept", "reject"):
        if not sr.get("received_at"):
            raise invalid_transition("Supplier response", "requested", action)
        sr["accepted"] = action == "accept"
        sr["decided_at"] = now().isoformat()
        sr["decision_note"] = body.get("note")
    else:
        raise qc.field_err("action", "request, receive, accept or reject")
    n.supplier_response = sr
    db.flush()
    _audit(db, p, n, AuditAction.update, details={"supplier_response": action})
    return n


def no_cost(db: Session, p: Principal, ncr_id: uuid.UUID, why: str | None) -> QNcr:
    n = get_ncr(db, p, ncr_id)
    qc.writable(project_of(db, n), p)
    _ensure_live(
        n, ST.open, ST.disposition_proposed, ST.disposition_approved, ST.pending_verification
    )
    _manager_grant(p, n)
    n.no_cost_reason = qc.reason(why, 20) if why else None
    db.flush()
    _audit(db, p, n, AuditAction.update, after={"no_cost_reason": n.no_cost_reason})
    return n


# ---- ageing (Q-NCR-18) -------------------------------------------------------------------------


def age_days(n: QNcr, today: date) -> int | None:
    if n.opened_date is None or n.status in (ST.closed, ST.voided, ST.draft):
        return None
    return (today - n.opened_date).days


def closure_days(n: QNcr) -> int | None:
    if n.closed_date is None or n.opened_date is None:
        return None
    return (n.closed_date - n.opened_date).days


def on_time(n: QNcr) -> bool | None:
    if n.closed_date is None or n.target_close_date is None:
        return None
    return n.closed_date <= n.target_close_date


# ---- list --------------------------------------------------------------------------------------


def _scope_cond(db: Session, p: Principal, project: Project) -> Any:
    uid = p.user.id
    own = or_(QNcr.raised_by_user_id == uid, QNcr.owner_id == uid)
    not_draft = QNcr.status != ST.draft
    if p.is_manager:
        return or_(not_draft, QNcr.raised_by_user_id == uid)
    g = p.grant(project.id, C.quality_view)
    if g is None:
        return and_(own, or_(not_draft, QNcr.raised_by_user_id == uid))
    if g.scope == S.responsible:
        ids = [
            n.id
            for n in db.scalars(
                select(QNcr).where(QNcr.project_id == project.id, QNcr.status != ST.draft)
            )
            if can_view(db, p, n)
        ]
        return or_(QNcr.id.in_(ids) if ids else false(), and_(own, not_draft))
    conds: list[Any] = [not_draft]
    if g.site_ids is not None:
        conds.append(QNcr.site_id.in_(list(g.site_ids)) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        conds.append(QNcr.responsible_engagement_id.in_(engs) if engs else false())
    return or_(and_(*conds), and_(own, or_(not_draft, QNcr.raised_by_user_id == uid)))


def scoped(db: Session, p: Principal, project: Project) -> Select[Any]:
    return select(QNcr).where(QNcr.project_id == project.id, _scope_cond(db, p, project))


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[QNcrStatus] | None = None,
    classes: list[QNcrClass] | None = None,
    categories: list[QNcrCategory] | None = None,
    source_type: QNcrSourceType | None = None,
    source_id: uuid.UUID | None = None,
    detection_stage: QDetectionStage | None = None,
    profile: str | None = None,
    repeat: bool | None = None,
    mine: bool = False,
    open_only: bool = False,
    overdue: bool | None = None,
    supplier_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    q: str | None = None,
    sort: str = "-opened_at",
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    if p.grant(project.id, C.quality_view) is None and p.grant(project.id, C.ncr_raise) is None:
        raise forbidden_error()
    today = qc.project_day(project)
    stmt = scoped(db, p, project)
    if statuses:
        stmt = stmt.where(QNcr.status.in_(statuses))
    if classes:
        stmt = stmt.where(QNcr.classification.in_(classes))
    if categories:
        stmt = stmt.where(QNcr.category.in_(categories))
    if source_type:
        stmt = stmt.where(QNcr.source_type == source_type)
    if source_id:
        stmt = stmt.where(QNcr.source_id == source_id)
    if detection_stage:
        stmt = stmt.where(QNcr.detection_stage == detection_stage)
    if profile:
        stmt = stmt.where(QNcr.profile == profile)
    if repeat is not None:
        stmt = stmt.where(QNcr.repeat_of_id.is_not(None) if repeat else QNcr.repeat_of_id.is_(None))
    if mine:
        stmt = stmt.where(or_(QNcr.owner_id == p.user.id, QNcr.raised_by_user_id == p.user.id))
    if open_only:
        stmt = stmt.where(QNcr.status.in_(list(NCR_LIVE)))
    if overdue is not None:
        cond = and_(QNcr.status.in_(list(NCR_LIVE)), QNcr.target_close_date < today)
        stmt = stmt.where(cond if overdue else ~cond)
    if supplier_id:
        stmt = stmt.where(QNcr.supplier_id == supplier_id)
    if engagement_id:
        stmt = stmt.where(QNcr.responsible_engagement_id == engagement_id)
    if site_id:
        stmt = stmt.where(QNcr.site_id == site_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(QNcr.ncr_no.ilike(like), QNcr.title.ilike(like)))
    order: Any = {
        "-opened_at": QNcr.opened_at.desc().nulls_first(),
        "opened_at": QNcr.opened_at.asc().nulls_last(),
        "target_close_date": QNcr.target_close_date.asc().nulls_last(),
        "-cost": QNcr.cost_gross_sar.desc(),
        "ncr_no": QNcr.ncr_no.asc(),
    }[sort]
    items, total = paginate(db, stmt.order_by(order, QNcr.created_at.desc()), page, page_size)
    return {
        "items": [list_item(db, p, project, n, today) for n in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---- read model ----------------------------------------------------------------------------------


def _user(refs: Refs, uid: uuid.UUID | None, hide: bool) -> dict[str, Any] | None:
    if uid is None or hide:
        return None
    u = refs.user(uid)
    return u.model_dump() if u else None


def _supplier(db: Session, sid: uuid.UUID | None) -> dict[str, Any] | None:
    s = db.get(QSupplier, sid) if sid else None
    if s is None:
        return None
    return {
        "id": s.id,
        "code": s.supplier_code,
        "name_en": s.legal_name_en,
        "name_ar": s.legal_name_ar,
        "status": s.status,
    }


def list_item(db: Session, p: Principal, project: Project, n: QNcr, today: date) -> dict[str, Any]:
    hide = read_only_viewer(p, project.id)
    refs = Refs(db)
    site = db.get(Site, n.site_id)
    eng = refs.eng(n.responsible_engagement_id)
    return {
        "id": n.id,
        "project_id": n.project_id,
        "ncr_no": n.ncr_no,
        "title": n.title,
        "status": n.status,
        "classification": n.classification,
        "category": n.category,
        "source_type": n.source_type,
        "source_ref": n.source_ref,
        "detection_stage": n.detection_stage,
        "profile": n.profile,
        "site_code": site.code if site else None,
        "responsible_engagement": eng.model_dump() if eng else None,
        "supplier": _supplier(db, n.supplier_id),
        "owner": _user(refs, n.owner_id, hide),
        "opened_at": n.opened_at,
        "target_close_date": n.target_close_date,
        "closed_date": n.closed_date,
        "age_days": age_days(n, today),
        "overdue": n.status in NCR_LIVE
        and bool(n.target_close_date and n.target_close_date < today),
        "repeat": n.repeat_of_id is not None,
        "cost_gross_sar": None if hide else str(n.cost_gross_sar),
        "before_quality_start": n.before_quality_start,
    }


def allowed_actions(db: Session, p: Principal, project: Project, n: QNcr) -> list[str]:
    """What the UI may offer (the server re-checks every action)."""
    out: list[str] = []
    mg = p.grant(project.id, C.ncr_manage)
    manage = qc.covers(mg, n.site_id, n.responsible_engagement_id)
    if n.status == ST.draft and p.user.id == n.raised_by_user_id:
        out += ["edit", "open", "delete"]
    if n.status in NCR_LIVE and manage:
        out += ["edit", "class", "costs", "actions", "supplier_response"]
    if n.status in (ST.open, ST.disposition_proposed, ST.disposition_approved) and manage:
        out.append("containment")
    if n.status == ST.open and manage:
        out += ["rca", "disposition", "propose"]
    if n.status == ST.disposition_approved and manage:
        out.append("implement")
    for step in pending_steps(db, n):
        if rpm.resolves(db, p, project, RT, step, ctx_for(n, step), record_id=n.id):
            out.append(f"sign:{step}")
        sd_cap = C.ncr_approve
        g = p.grant(project.id, sd_cap)
        if qc.covers(g, n.site_id, n.responsible_engagement_id):
            out.append(f"paper:{step}")
    if n.status in NCR_LIVE and (p.is_manager or p.grant(project.id, C.quality_settings)):
        out.append("reassign")
    if n.status == ST.closed and p.grant(project.id, C.quality_settings) is not None:
        out.append("reopen")
    if n.status == ST.closed and manage:
        out.append("effectiveness")
    if n.status in (ST.draft, ST.open, ST.disposition_proposed, ST.disposition_approved) and (
        p.grant(project.id, C.quality_void) is not None
    ):
        out.append("void")
    return sorted(set(out))


def read(
    db: Session, p: Principal, n: QNcr, warnings: list[ApiWarning] | None = None
) -> dict[str, Any]:
    from app.services.quality.ncr import costs as costs_svc  # noqa: PLC0415

    project = project_of(db, n)
    today = qc.project_day(project)
    hide = read_only_viewer(p, project.id)
    refs = Refs(db)
    item = list_item(db, p, project, n, today)
    r = rca_of(db, n)
    rep = db.get(QNcr, n.repeat_of_id) if n.repeat_of_id else None
    steps = []
    for step in required_steps(db, n):
        res = rpm.resolve(db, project, RT, step, ctx_for(n, step), record_id=n.id)
        steps.append(
            {
                "step": step,
                "pending": step in pending_steps(db, n),
                "responsible_set": res.rule is not None,
                "resolvers": []
                if hide
                else [_user(refs, u, False) for u in res.users if u not in requesters(n, step)],
                "me": p.user.id in res.users,
            }
        )
    show_lines = sees_cost_lines(p, project.id) and not hide
    return {
        **item,
        "source_id": n.source_id,
        "item_key": n.item_key,
        "zone": zone.model_dump() if (zone := refs.zone(n.zone_id)) else None,
        "site": refs.site(n.site_id).model_dump(),
        "system_id": n.system_id,
        "location_ref": n.location_ref,
        "requirement_en": n.requirement_en,
        "requirement_ar": n.requirement_ar,
        "finding_en": n.finding_en,
        "finding_ar": n.finding_ar,
        "customer_id": n.customer_id,
        "quantity": str(n.quantity) if n.quantity is not None else None,
        "unit": n.unit,
        "lot_refs": list(n.lot_refs or []),
        "raised_by": _user(refs, n.raised_by_user_id, hide),
        "opened_date": n.opened_date,
        "containment_en": n.containment_en,
        "containment_ar": n.containment_ar,
        "containment_done_at": n.containment_done_at,
        "containment_by": _user(refs, n.containment_by_user_id, hide),
        "containment_due_at": n.containment_due_at,
        "containment_overdue": bool(
            n.containment_due_at
            and n.containment_done_at is None
            and n.status in NCR_LIVE
            and n.containment_due_at < now()
        ),
        "no_product_affected": n.no_product_affected,
        "cause_category": n.cause_category,
        "rca": rca_read(r) if r else None,
        "disposition_lines": [line_read(x) for x in lines_of(db, n)],
        "disposition_justification_en": n.disposition_justification_en,
        "disposition_justification_ar": n.disposition_justification_ar,
        "disposition_proposed_at": n.disposition_proposed_at,
        "disposition_approved_at": n.disposition_approved_at,
        "implementation_note": n.implementation_note,
        "implemented_at": n.implemented_at,
        "supplier_response": n.supplier_response,
        "repeat_of": {"id": rep.id, "ncr_no": rep.ncr_no} if rep else None,
        "closed_at": n.closed_at,
        "closure_days": closure_days(n),
        "on_time": on_time(n),
        "effectiveness": n.effectiveness,
        "no_cost_reason": n.no_cost_reason,
        "cost_recovered_sar": None if hide else str(n.cost_recovered_sar),
        "cost_net_sar": None if hide else str(n.cost_gross_sar - n.cost_recovered_sar),
        "failure_class": costs_svc.failure_class(n),
        "cost_lines": [costs_svc.line_read(c) for c in costs_svc.lines(db, n)]
        if show_lines
        else [],
        "cost_lines_visible": show_lines,
        "duplicate_of_id": n.duplicate_of_id,
        "status_reason": n.status_reason,
        "reopened_count": n.reopened_count,
        "actions": [] if hide else capa.summary(db, CaSourceType.quality_ncr, n.id),
        "steps": steps,
        "signoffs": [signoff.read(db, s, not hide) for s in signoff.signoffs_for(db, RT, n.id)]
        if not hide
        else [],
        "links": links.links_for(db, p, RT, n.id),
        "photo_count": evidence_count(db, n, (AttachmentOwner.q_ncr,)),
        "evidence_count": evidence_count(db, n, (AttachmentOwner.q_ncr_evidence,)),
        "allowed_actions": allowed_actions(db, p, project, n),
        "names_hidden": hide,
        "warnings": [w.model_dump() for w in (warnings or [])],
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }


def rca_read(r: QNcrRca) -> dict[str, Any]:
    return {
        "method": r.method,
        "data": r.data or {},
        "root_cause": r.root_cause,
        "cause_category": r.cause_category,
        "complete": r.complete,
    }


def line_read(x: QNcrLine) -> dict[str, Any]:
    return {
        "id": x.id,
        "disposition": x.disposition,
        "quantity": str(x.quantity) if x.quantity is not None else None,
        "note": x.note,
        "repair_procedure": x.repair_procedure,
        "return_ref": x.return_ref,
        "destruction_evidenced": x.destruction_evidenced,
    }


def users_ref(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}


_ = (INTERNAL_STAGES, true)
