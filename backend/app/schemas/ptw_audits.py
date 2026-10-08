"""PTW audits: field, document review, unpermitted work (spec 3-ptw §3.15, §4.9, §5.11,
§6.8)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.ptw_enums import (
    AuditAnswer,
    AuditFindingSeverity,
    AuditItem,
    PtwAuditStatus,
    PtwAuditType,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, EngagementRef, SiteRef, UserRef, ZoneRef
from app.schemas.ptw_common import PermitRef


class AuditItemInput(StrictInput):
    """AU-3: every applicable item answered; n.a. only for items that do not apply. Severity
    defaults to the item default and may be raised, not lowered. Findings never name workers
    (AU-8); photos: 'avoid faces'."""

    code: AuditItem
    answer: AuditAnswer
    severity: AuditFindingSeverity | None = None
    note: str | None = Field(default=None, max_length=500)
    photo_attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class PtwAuditCreate(StrictInput):
    """Capability 101. Auditor = caller; AU-2 SoD (≠ issuer, receiver, area authority, HSE
    reviewer of the permit → 422 SOD_CONFLICT). field: permit Issued/Active/Suspended at
    audited_at; document_review: Closed/Expired permit; unpermitted_work: no permit, site /
    zone / engagement entered, item A00 only, stop-work record required (AU-6). The response
    lists the applicable items (unanswered)."""

    audit_type: PtwAuditType
    permit_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = Field(default=None, description="unpermitted_work only.")
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    audited_at: datetime = Field(description="≤ now.")
    items: list[AuditItemInput] = Field(default_factory=list)
    stop_work_issued_at: datetime | None = Field(
        default=None, description="unpermitted_work: when work was stopped (AU-6)."
    )
    unpermitted_work_desc: str | None = Field(default=None, max_length=1000)


class PtwAuditUpdate(PatchInput):
    """Draft (auditor) or Completed (auditor, within 7 days). Locked: HSE Manager only with
    edit_reason (AUDIT_LOCKED)."""

    items: list[AuditItemInput] | None = None
    audited_at: datetime | None = None
    stop_work_issued_at: datetime | None = None
    unpermitted_work_desc: str | None = Field(default=None, max_length=1000)
    edit_reason: str | None = Field(default=None, min_length=10, max_length=500)


class AuditItemRead(ApiModel):
    code: AuditItem
    label_en: str
    label_ar: str
    applies: bool
    default_severity: AuditFindingSeverity
    answer: AuditAnswer | None
    severity: AuditFindingSeverity | None
    note: str | None
    photo_attachment_ids: list[uuid.UUID]
    ca_required: bool = Field(description="AU-4: critical/major non-compliant → CA required.")


class AuditCaLink(ApiModel):
    id: uuid.UUID
    ref: str
    priority: str
    status: str
    item_code: AuditItem | None


class PtwAuditRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    audit_no: str = Field(examples=["PTA-ANIA-EXP-2026-00377"])
    audit_type: PtwAuditType
    permit: PermitRef | None
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef
    auditor: UserRef
    audited_at: datetime
    items: list[AuditItemRead]
    applicable_count: int
    compliant_count: int
    score_pct: DecimalStr | None = Field(description="§6.8, 1 dp half-up; null until answered.")
    critical_count: int
    required_cas: list[AuditItem] = Field(description="Items still needing a CA (CA_REQUIRED).")
    cas: list[AuditCaLink] = Field(
        description="CAs with source_type ptw_audit and source_id = this audit "
        "(create them with POST /projects/{id}/corrective-actions)."
    )
    stop_work_issued_at: datetime | None
    unpermitted_work_desc: str | None
    permit_suspended: bool = Field(description="AU-4: a critical finding suspended the permit.")
    status: PtwAuditStatus
    completed_at: datetime | None
    locks_at: datetime | None = Field(description="Completed + 7 days.")
    created_at: datetime
    updated_at: datetime


class PtwAuditListItem(ApiModel):
    id: uuid.UUID
    audit_no: str
    audit_type: PtwAuditType
    permit: PermitRef | None
    engagement: EngagementRef
    zone: ZoneRef | None
    auditor: UserRef
    audited_at: datetime
    score_pct: DecimalStr | None
    critical_count: int
    status: PtwAuditStatus


PtwAuditPage = Page[PtwAuditListItem]


class PtwAuditCompleteInput(StrictInput):
    """Draft → Completed: score computed; AU-5 every required CA exists (CA_REQUIRED); a
    critical non-compliant item on a field audit suspends the permit (audit_critical)."""

    note: str | None = Field(default=None, max_length=500)


class PtwAuditChecklist(ApiModel):
    """Applicable items for a permit (or for unpermitted work) before creating an audit."""

    audit_type: PtwAuditType
    permit: PermitRef | None
    items: list[AuditItemRead]
