"""Sign-offs (spec 8-quality §A.8.6, Q-RPM-05, Q-RPM-08). `q_signoffs` is append-only: there is
no update or delete function and no such route (AC-Q0-15).

A part calls `sign(...)` from its own transition after `rpm.check_signer` (in-app) or
`sign_paper(...)` for a decision recorded on behalf of an external signatory."""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType, QSignoffChannel, entity_type_value, step_def
from app.models import Project, User
from app.models.quality import QRpRule, QSignoff
from app.services import attachments, audit
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import rpm

C = Capability


def sign(
    db: Session,
    p: Principal,
    project: Project,
    record_type: QRecordType,
    record_id: uuid.UUID,
    step: str,
    decision: str,
    comment: str | None,
    rule: QRpRule | None,
    capacity: str,
    *,
    evidence_ids: list[uuid.UUID] | None = None,
) -> QSignoff:
    sd = step_def(record_type, step)
    if sd is not None and decision not in sd.decisions:
        raise qc.field_err(
            "decision",
            f"Decision must be one of {', '.join(sd.decisions)}.",
            "القرار غير صالح لهذه الخطوة.",
        )
    s = QSignoff(
        project_id=project.id,
        record_type=record_type.value,
        record_id=record_id,
        step=step,
        decision=decision,
        comment=(comment or "").strip() or None,
        signed_by_user_id=p.user.id,
        signed_at=now(),
        signer_capacity=capacity,
        channel=QSignoffChannel.in_app,
        evidence_attachment_ids=list(evidence_ids or []),
        rule_id=rule.id if rule else None,
    )
    db.add(s)
    db.flush()
    _audit(db, p, project, s)
    return s


def _audit(db: Session, p: Principal, project: Project, s: QSignoff) -> None:
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_signoff,
        entity_id=s.id,
        project_id=project.id,
        after={
            "record_type": s.record_type,
            "record_id": str(s.record_id),
            "step": s.step,
            "decision": s.decision,
            "channel": s.channel,
        },
    )
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType(entity_type_value(s.record_type)),
        entity_id=s.record_id,
        project_id=project.id,
        details={"signoff": s.step, "decision": s.decision, "channel": s.channel.value},
    )


def sign_paper(
    db: Session,
    p: Principal,
    project: Project,
    record_type: QRecordType,
    record_id: uuid.UUID,
    step: str,
    decision: str,
    comment: str | None,
    paper: dict[str, Any],
    ctx: rpm.Ctx,
    *,
    qualifier: str | None = None,
) -> QSignoff:
    """Q-RPM-08: a holder of the step's capability records the decision of a named external
    signatory (name, organisation, position, signed date and ≥ 1 scanned signed form), where the
    effective row allows paper. Stored with channel `paper`."""
    qc.writable(project, p)
    sd = step_def(record_type, step)
    if sd is None:
        raise qc.field_err("step", "Unknown step.", "خطوة غير معروفة.")
    g = p.grant(project.id, sd.capability)
    if g is None or not qc.covers(g, ctx.site_id, ctx.engagement_id):
        raise forbidden_error("Recording a paper sign-off needs the step's capability.")
    rule = rpm.effective_rule(
        db, project.id, record_type, step, qualifier=qualifier, record_id=record_id
    )
    if rule is None:
        raise rpm.not_set_error(record_type, step)
    if not rule.paper_allowed:
        raise qc.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Paper sign-off is not allowed for this step (matrix row).",
            "التوقيع الورقي غير مسموح لهذه الخطوة.",
        )
    name = (paper.get("name") or "").strip()
    org = (paper.get("organisation") or "").strip()
    pos = (paper.get("position") or "").strip()
    signed_on = paper.get("signed_on")
    scans = paper.get("scans") or []
    if not name or not org or not pos or signed_on is None:
        raise qc.field_err(
            "paper",
            "Give the signatory's name, organisation, position and signed date.",
            "أدخل اسم الموقّع وجهته ومنصبه وتاريخ التوقيع.",
        )
    if not scans:
        raise qc.field_err(
            "paper.scans",
            "Attach at least one scanned signed form (PDF or image).",
            "أرفق نسخة ممسوحة واحدة على الأقل من النموذج الموقّع.",
        )
    if isinstance(signed_on, str):
        signed_on = date.fromisoformat(signed_on)
    if signed_on > qc.project_day(project):
        raise qc.field_err("paper.signed_on", "The signed date cannot be in the future.")
    s = QSignoff(
        project_id=project.id,
        record_type=record_type.value,
        record_id=record_id,
        step=step,
        decision=decision,
        comment=(comment or "").strip() or None,
        signed_by_user_id=p.user.id,
        signed_at=now(),
        signer_capacity=f"paper: {pos}",
        channel=QSignoffChannel.paper,
        external_name=name[:120],
        external_organisation=org[:150],
        external_position=pos[:120],
        external_signed_on=signed_on,
        rule_id=rule.id,
    )
    if sd is not None and decision not in sd.decisions:
        raise qc.field_err("decision", "Decision not allowed for this step.")
    db.add(s)
    db.flush()
    ids = []
    for f in scans:
        try:
            content = base64.b64decode(str(f.get("content_base64") or ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise qc.field_err("paper.scans", "The scan is not valid base64.") from exc
        fname = str(f.get("file_name") or "signed-form.pdf")
        ctype = attachments._content_type(fname, content)
        a = attachments.store(
            db, AttachmentOwner.q_signoff_scan, s.id, project.id, fname, content, ctype, p.user.id
        )
        ids.append(a.id)
    s.evidence_attachment_ids = ids
    db.flush()
    _audit(db, p, project, s)
    return s


def signoffs_for(
    db: Session, record_type: QRecordType | str, record_id: uuid.UUID
) -> list[QSignoff]:
    return list(
        db.scalars(
            select(QSignoff)
            .where(
                QSignoff.record_type == QRecordType(record_type).value,
                QSignoff.record_id == record_id,
            )
            .order_by(QSignoff.signed_at)
        )
    )


def latest(
    db: Session, record_type: QRecordType, record_id: uuid.UUID, step: str, after: Any = None
) -> QSignoff | None:
    rows = [s for s in signoffs_for(db, record_type, record_id) if s.step == step]
    if after is not None:
        rows = [s for s in rows if s.signed_at >= after]
    return rows[-1] if rows else None


def read(db: Session, s: QSignoff, show_scans: bool = True) -> dict[str, Any]:
    u = db.get(User, s.signed_by_user_id)
    by_en = u.full_name_en if u else "—"
    by_ar = (u.full_name_ar or u.full_name_en) if u else "—"
    if s.channel == QSignoffChannel.paper:
        text_en = (
            f"Signed on paper by {s.external_name} ({s.external_organisation}), recorded by {by_en}"
        )
        text_ar = f"وُقّع ورقياً من {s.external_name} ({s.external_organisation})، سجّله {by_ar}"
    else:
        text_en = f"Signed by {by_en} ({s.signer_capacity})"
        text_ar = f"وقّعه {by_ar} ({s.signer_capacity})"
    return {
        "id": s.id,
        "record_type": s.record_type,
        "record_id": s.record_id,
        "step": s.step,
        "decision": s.decision,
        "comment": s.comment,
        "signed_by": {"id": s.signed_by_user_id, "full_name_en": by_en, "full_name_ar": by_ar},
        "signed_at": s.signed_at,
        "signer_capacity": s.signer_capacity,
        "channel": s.channel,
        "external_name": s.external_name,
        "external_organisation": s.external_organisation,
        "external_position": s.external_position,
        "external_signed_on": s.external_signed_on,
        "evidence_attachment_ids": list(s.evidence_attachment_ids or []) if show_scans else [],
        "text_en": text_en,
        "text_ar": text_ar,
    }
