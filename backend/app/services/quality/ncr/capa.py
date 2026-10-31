"""CAPA through the existing Phase 1 corrective actions (spec 8-quality §A.9.5, Q-CAP-01…08).

There is no second CAPA table: quality CAs are `corrective_actions` rows with a quality source
type. `app.services.corrective_actions` calls back into this module (lazily) for the due-days
provider (Q-CAP-03), the verifier rule (Q-CAP-04), the source ref and resolution, and the
"all actions closed" notice (Q-CAP-07)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability, EntityType
from app.core.errors import ErrorCode, validation_error
from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel
from app.core.quality.common import QNcrClass
from app.models import CorrectiveAction, Project
from app.models.quality import QComplaint, QNcr, QObservation
from app.schemas.actions import CaInline
from app.schemas.hse_common import ApiWarning
from app.services.quality import common as qc
from app.services.quality import settings as qs

C = Capability
MODELS: dict[CaSourceType, Any] = {
    CaSourceType.quality_ncr: QNcr,
    CaSourceType.quality_observation: QObservation,
    CaSourceType.quality_complaint: QComplaint,
}
REF_ATTR = {QNcr: "ncr_no", QObservation: "obs_no", QComplaint: "complaint_no"}
PRIORITY_OF = {
    QNcrClass.critical: CaPriority.critical,
    QNcrClass.major: CaPriority.high,
    QNcrClass.minor: CaPriority.medium,
}
ORDER = [CaPriority.critical, CaPriority.high, CaPriority.medium, CaPriority.low]
LIVE = (CaStatus.open, CaStatus.in_progress, CaStatus.pending_verification)


def due_days(db: Session, project_id: uuid.UUID, priority: CaPriority) -> int:
    """Q-CAP-03: `quality_ca_due_days` instead of Phase 1 `ca_due_days`."""
    days = qs.value(db, project_id, "quality_ca_due_days")
    return int(days.get(priority.value, 30))


def verifier_ok(db: Session, project: Project, verifier_id: uuid.UUID) -> bool:
    """Q-CAP-04: a holder of 243 on the project, or the HSE Manager."""
    return verifier_id in qc.holders_of(db, project, C.ncr_approve)


def source_ref(db: Session, st: CaSourceType, sid: uuid.UUID) -> str | None:
    model = MODELS.get(st)
    if model is None:
        return None
    row = db.get(model, sid)
    return getattr(row, REF_ATTR[model], None) if row is not None else None


def resolve_source(db: Session, project: Project, st: CaSourceType, sid: uuid.UUID | None) -> Any:
    model = MODELS.get(st)
    if model is None or sid is None:
        raise validation_error("source_id", "The source record is not on this project.")
    row = db.get(model, sid)
    if row is None or row.project_id != project.id:
        raise validation_error("source_id", "The source record is not on this project.")
    return row


def cas_of(db: Session, st: CaSourceType, sid: uuid.UUID) -> list[CorrectiveAction]:
    return list(
        db.scalars(
            select(CorrectiveAction)
            .where(CorrectiveAction.source_type == st, CorrectiveAction.source_id == sid)
            .order_by(CorrectiveAction.created_at)
        )
    )


def on_settled(db: Session, ca: CorrectiveAction) -> None:
    """Q-CAP-07: when the last open CA of an NCR is Closed, tell the owner; the NCR does not
    change state by itself."""
    if ca.source_type != CaSourceType.quality_ncr or ca.source_id is None:
        return
    ncr = db.get(QNcr, ca.source_id)
    if ncr is None or ncr.owner_id is None:
        return
    live = [c for c in cas_of(db, ca.source_type, ncr.id) if c.status in LIVE]
    if live:
        return
    ref = ncr.ncr_no or "NCR"
    qc.send(
        db,
        [ncr.owner_id],
        f"{ref}: all actions closed — ready for verification",
        f"{ref}: أُغلقت جميع الإجراءات — جاهز للتحقق",
        entity_type=EntityType.q_ncr,
        entity_id=ncr.id,
        project_id=ncr.project_id,
        email=False,
        key=f"ncr_all_ca_closed:{ncr.id}:{ca.id}",
    )


def priority_for(
    cls: QNcrClass | None, requested: CaPriority | None, why: str | None
) -> CaPriority:
    """Q-CAP-03: critical → critical, major → high, minor → medium; editable down by one level
    with a reason."""
    base = PRIORITY_OF.get(cls or QNcrClass.minor, CaPriority.medium)
    if requested is None or requested == base:
        return base
    if ORDER.index(requested) == ORDER.index(base) + 1:
        qc.reason(why, 20, "priority_reason")
        return requested
    raise qc.field_err(
        "priority",
        f"The priority follows the class ({base.value}); it may be lowered by one level with a "
        "reason (Q-CAP-03).",
        "تتبع الأولوية تصنيف التقرير؛ يمكن خفضها مستوى واحداً مع ذكر السبب.",
    )


def create_for(
    db: Session,
    p: Any,
    project: Project,
    st: CaSourceType,
    source: Any,
    body: dict[str, Any],
    cls: QNcrClass | None,
) -> tuple[CorrectiveAction, list[ApiWarning]]:
    """Create one CA inline from a Quality record (caller checked 242 / 241)."""
    from app.services import corrective_actions as ca_svc  # noqa: PLC0415

    prio = priority_for(cls, body.get("priority"), body.get("priority_reason"))
    inline = CaInline(
        title=body["title"],
        description=body["description"],
        control_level=ControlLevel(body["control_level"]),
        priority=prio,
        owner_id=body["owner_id"],
        verifier_id=body["verifier_id"],
        responsible_engagement_id=body.get("responsible_engagement_id"),
        due_date=body.get("due_date"),
    )
    ca, warnings = ca_svc.new_ca(db, p, project, inline, st, source)
    if inline.control_level == ControlLevel.ppe and cls in (QNcrClass.major, QNcrClass.critical):
        warnings.append(
            qc.warning(
                ErrorCode.DETECTION_ONLY_ACTION,
                "Extra inspection only detects the problem; a major or critical NCR needs an "
                "action that removes the cause (Q-CAP-05).",
                "الفحص الإضافي يكشف المشكلة فقط؛ يحتاج التقرير الجوهري أو الحرج إلى إجراء يزيل "
                "السبب.",
                "control_level",
            )
        )
    return ca, warnings


def summary(db: Session, st: CaSourceType, sid: uuid.UUID) -> list[dict[str, Any]]:
    out = []
    for c in cas_of(db, st, sid):
        out.append(
            {
                "id": c.id,
                "ref": c.ref,
                "title": c.title,
                "status": c.status,
                "priority": c.priority,
                "control_level": c.control_level,
                "due_date": c.due_date,
                "owner_id": c.owner_id,
                "verifier_id": c.verifier_id,
            }
        )
    return out
