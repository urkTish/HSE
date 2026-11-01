"""API schemas of package Q4: documents, transmittals, quality audits, programme, management
reviews, supplier evaluations and scores, KPIs, SPC (spec 8-quality Part E). Every name carries the
`Q4` prefix so nothing clashes with earlier modules in the OpenAPI contract. Nested KPI and chart
payloads are plain JSON objects documented in the summaries (aggregates only, P8-4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from app.core.field_enums import AuditDomain, AuditStatus, AuditType
from app.core.quality.common import QProfileScope
from app.core.quality.q4 import (
    QDocType,
    QMrvStatus,
    QProgrammeStatus,
    QProgrammeSubject,
    QResponseCode,
    QRevStatus,
    QRisk,
    QScorePeriod,
    QScoreStatus,
    QSevKind,
    QSevMethod,
    QSevRecommendation,
    QSevStatus,
    QSpcBaseline,
    QSpcSource,
    QSpcType,
    QTransmittalItemKind,
    QTransmittalMethod,
    QTransmittalPurpose,
    QTransmittalStatus,
    QTransmittalTo,
)
from app.schemas.common import ApiModel, Page, StrictInput

Obj = dict[str, Any]


class Q4UserRef(ApiModel):
    id: uuid.UUID
    name_en: str
    name_ar: str


# ---- documents --------------------------------------------------------------------------------


class Q4DocumentCreate(StrictInput):
    doc_type: QDocType
    title_en: str = Field(min_length=3, max_length=200)
    title_ar: str = Field(default="", max_length=200)
    doc_no: str | None = Field(
        default=None, max_length=60, description="Default: numbering format."
    )
    profile: QProfileScope = QProfileScope.both
    discipline: str | None = Field(default=None, max_length=40)
    process_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    change_summary: str | None = Field(default=None, max_length=2000)


class Q4DocumentUpdate(StrictInput):
    title_en: str | None = Field(default=None, min_length=3, max_length=200)
    title_ar: str | None = Field(default=None, max_length=200)
    discipline: str | None = Field(default=None, max_length=40)
    process_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None


class Q4RevisionUpdate(StrictInput):
    file_attachment_id: uuid.UUID | None = None
    source_attachment_id: uuid.UUID | None = None
    change_summary: str | None = Field(default=None, max_length=2000)
    effective_date: date | None = None


class Q4Decision(StrictInput):
    decision: Literal["approved", "approved_with_comments", "returned"] = "approved"
    comment: str | None = Field(default=None, max_length=2000)


class Q4Reason(StrictInput):
    reason: str | None = Field(default=None, max_length=1000)


class Q4Distribution(StrictInput):
    roles: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    engagement_ids: list[uuid.UUID] = Field(default_factory=list)
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    ack_required: bool = False


class Q4AckStats(ApiModel):
    required: int
    acked: int
    pct: str


class Q4RevisionRead(ApiModel):
    id: uuid.UUID
    document_id: uuid.UUID
    rev_code: str
    status: QRevStatus
    file_attachment_id: uuid.UUID | None
    source_attachment_id: uuid.UUID | None
    change_summary: str | None
    effective_date: date | None
    author: Q4UserRef | None
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: Q4UserRef | None
    returned_comment: str | None
    ack_due_on: date | None
    acks: Q4AckStats
    signoffs: list[Obj]
    download_name: str | None


class Q4DocumentListItem(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    doc_no: str
    doc_type: QDocType
    doc_type_en: str
    doc_type_ar: str
    title_en: str
    title_ar: str
    profile: QProfileScope
    discipline: str | None
    process_id: uuid.UUID | None
    owner: Q4UserRef | None
    status: QRevStatus
    current_rev: str | None
    open_rev: str | None
    open_rev_status: QRevStatus | None
    review_due_on: date | None
    review_overdue: bool


class Q4DocumentRead(Q4DocumentListItem):
    revisions: list[Q4RevisionRead]
    distribution: Obj
    status_reason: str | None
    can_author: bool
    can_review: bool
    can_approve: bool
    my_ack: Obj | None


Q4DocumentPage = Page[Q4DocumentListItem]


class Q4AckResult(ApiModel):
    revision_id: uuid.UUID
    acked_at: datetime | None
    acks: Q4AckStats


class Q4MyAck(ApiModel):
    document_id: uuid.UUID
    doc_no: str
    title_en: str
    title_ar: str
    revision_id: uuid.UUID
    rev_code: str
    revision_status: QRevStatus
    file_attachment_id: uuid.UUID | None
    due_on: date
    acked_at: datetime | None


class Q4Citation(ApiModel):
    document_id: uuid.UUID
    doc_no: str
    revision_id: uuid.UUID
    rev_code: str
    status: QRevStatus
    newer_revision_available: bool
    newer_rev_code: str | None


class Q4CiteInput(StrictInput):
    record_type: str
    record_id: uuid.UUID


class Q4TransmittalItemInput(StrictInput):
    revision_id: uuid.UUID | None = None
    record_type: str | None = None
    record_id: uuid.UUID | None = None


class Q4TransmittalCreate(StrictInput):
    to_kind: QTransmittalTo
    to_engagement_id: uuid.UUID | None = None
    to_supplier_id: uuid.UUID | None = None
    to_customer_id: uuid.UUID | None = None
    to_name: str | None = Field(default=None, max_length=200)
    to_email: str | None = Field(default=None, max_length=200)
    purpose: QTransmittalPurpose
    method: QTransmittalMethod = QTransmittalMethod.email
    subject: str = Field(min_length=3, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    response_due_on: date | None = None
    items: list[Q4TransmittalItemInput] = Field(min_length=1, max_length=100)


class Q4ItemResponse(StrictInput):
    item_id: uuid.UUID
    response_code: QResponseCode
    note: str | None = Field(default=None, max_length=1000)


class Q4TransmittalRespond(StrictInput):
    received_on: date | None = None
    response_name: str | None = Field(default=None, max_length=200)
    items: list[Q4ItemResponse] = Field(default_factory=list)


class Q4TransmittalItemRead(ApiModel):
    id: uuid.UUID
    kind: QTransmittalItemKind
    revision_id: uuid.UUID | None
    record_type: str | None
    record_id: uuid.UUID | None
    ref: str
    title: str
    response_code: QResponseCode | None
    response_note: str | None


class Q4TransmittalRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    trm_no: str | None
    to_kind: QTransmittalTo
    to_engagement_id: uuid.UUID | None
    to_supplier_id: uuid.UUID | None
    to_customer_id: uuid.UUID | None
    to_label_en: str
    to_label_ar: str
    to_name: str | None
    to_email: str | None
    purpose: QTransmittalPurpose
    method: QTransmittalMethod
    subject: str
    note: str | None
    sent_at: datetime | None
    response_due_on: date | None
    response_received_on: date | None
    response_name: str | None
    status: QTransmittalStatus
    cover_en_id: uuid.UUID | None
    cover_ar_id: uuid.UUID | None
    outbox_id: uuid.UUID | None
    items: list[Q4TransmittalItemRead]


Q4TransmittalPage = Page[Q4TransmittalRead]


# ---- processes, programme, audits, management reviews --------------------------------------


class Q4ProcessInput(StrictInput):
    code: str | None = Field(default=None, max_length=20)
    name_en: str | None = Field(default=None, max_length=150)
    name_ar: str | None = Field(default=None, max_length=150)
    owner_user_id: uuid.UUID | None = None
    profile: QProfileScope | None = None
    risk: QRisk | None = None
    document_ids: list[uuid.UUID] | None = None
    active: bool | None = None


class Q4ProcessRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    owner: Q4UserRef | None
    profile: QProfileScope
    risk: QRisk
    document_ids: list[uuid.UUID]
    active: bool


class Q4LineCreate(StrictInput):
    year: int = Field(ge=2020, le=2100)
    subject_kind: QProgrammeSubject
    process_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    clause_set: str | None = Field(default=None, max_length=100)
    risk: QRisk = QRisk.medium
    planned_month: int = Field(ge=1, le=12)


class Q4LineUpdate(StrictInput):
    status: QProgrammeStatus | None = None
    reason: str | None = Field(default=None, max_length=500)
    planned_month: int | None = Field(default=None, ge=1, le=12)


class Q4LineRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    year: int
    subject_kind: QProgrammeSubject
    process_id: uuid.UUID | None
    process_code: str | None
    process_name_en: str | None
    process_name_ar: str | None
    supplier: Obj | None
    engagement_id: uuid.UUID | None
    engagement_code: str | None
    clause_set: str | None
    risk: QRisk
    planned_month: int
    audit_id: uuid.UUID | None
    audit_no: str | None
    status: QProgrammeStatus
    status_reason: str | None
    on_time: bool
    auto: bool


class Q4AuditCreate(StrictInput):
    audit_type: AuditType
    template_code: str = Field(min_length=2, max_length=8)
    auditee_supplier_id: uuid.UUID | None = None
    auditee_engagement_id: uuid.UUID | None = None
    process_ids: list[uuid.UUID] = Field(default_factory=list)
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    lead_auditor_id: uuid.UUID
    team_ids: list[uuid.UUID] = Field(default_factory=list)
    planned_start: date
    planned_end: date
    programme_line_id: uuid.UUID | None = None


class Q4AuditUpdate(StrictInput):
    fieldwork_start: date | None = None
    fieldwork_end: date | None = None
    opening_meeting_at: datetime | None = None
    closing_meeting_at: datetime | None = None
    summary_en: str | None = Field(default=None, max_length=3000)
    summary_ar: str | None = Field(default=None, max_length=3000)
    auditee_attendee_roles: str | None = Field(default=None, max_length=300)


class Q4AuditIssue(StrictInput):
    comment: str | None = Field(default=None, max_length=2000)
    ca_for_observations: bool = False


class Q4AuditRead(ApiModel):
    id: uuid.UUID
    audit_no: str
    project_id: uuid.UUID
    audit_type: AuditType
    domain: AuditDomain
    template_code: str
    status: AuditStatus
    planned_start: date
    planned_end: date
    fieldwork_start: date | None
    fieldwork_end: date | None
    opening_meeting_at: datetime | None
    closing_meeting_at: datetime | None
    lead_auditor: Obj | None
    team: list[Obj]
    sites: list[Obj]
    auditee_engagement: Obj | None
    auditee_supplier: Obj | None
    processes: list[Obj]
    response: Obj | None
    summary_en: str | None
    summary_ar: str | None
    report_en_id: uuid.UUID | None
    report_ar_id: uuid.UUID | None
    issued_at: datetime | None
    report_due_by: date | None
    can_issue: bool
    ncr_ids: list[uuid.UUID]
    status_reason: str | None
    warnings: list[Obj] = Field(default_factory=list)


Q4AuditPage = Page[Q4AuditRead]


class Q4MrvCreate(StrictInput):
    period_start: date
    period_end: date
    chair_user_id: uuid.UUID | None = None
    attendee_user_ids: list[uuid.UUID] = Field(default_factory=list)
    external_attendees: list[str] = Field(default_factory=list)


class Q4MrvInput(StrictInput):
    note: str | None = Field(default=None, max_length=3000)
    not_applicable: bool = False


class Q4MrvOutput(StrictInput):
    id: str | None = None
    kind: Literal["improvement", "qms_change", "resource"] = "improvement"
    text: str = Field(min_length=3, max_length=1000)
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None
    create_ca: bool = False


class Q4MrvUpdate(StrictInput):
    inputs: dict[str, Q4MrvInput] | None = None
    outputs: list[Q4MrvOutput] | None = None
    chair_user_id: uuid.UUID | None = None
    held_on: date | None = None
    attendee_user_ids: list[uuid.UUID] | None = None
    external_attendees: list[str] | None = None


class Q4MrvHold(StrictInput):
    held_on: date | None = None


class Q4MrvRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    mrv_no: str | None
    period_start: date
    period_end: date
    held_on: date | None
    chair: Q4UserRef | None
    attendees: list[Obj | None]
    external_attendees: list[str]
    inputs: list[Obj]
    kpi_snapshot: Obj | None
    outputs: list[Obj]
    minutes_en_id: uuid.UUID | None
    minutes_ar_id: uuid.UUID | None
    status: QMrvStatus
    can_issue: bool


# ---- suppliers ------------------------------------------------------------------------------


class Q4Criterion(StrictInput):
    criterion: str = Field(min_length=1, max_length=150)
    weight: Decimal = Field(ge=0, le=100)
    score: Decimal = Field(ge=0, le=100)


class Q4SevCreate(StrictInput):
    supplier_id: uuid.UUID
    kind: QSevKind
    method: QSevMethod
    audit_id: uuid.UUID | None = None
    criteria: list[Q4Criterion] = Field(default_factory=list)
    recommendation: QSevRecommendation | None = None
    conditions: str | None = Field(default=None, max_length=1000)
    evaluated_at: date | None = None


class Q4SevUpdate(StrictInput):
    method: QSevMethod | None = None
    audit_id: uuid.UUID | None = None
    criteria: list[Q4Criterion] | None = None
    recommendation: QSevRecommendation | None = None
    conditions: str | None = Field(default=None, max_length=1000)
    evaluated_at: date | None = None


class Q4SevAction(StrictInput):
    action: Literal["submit", "approve", "return", "cancel"]
    comment: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=1000)


class Q4SevRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sev_no: str | None
    supplier: Obj | None
    kind: QSevKind
    method: QSevMethod
    audit_id: uuid.UUID | None
    criteria: list[Obj]
    total: Decimal | None
    recommendation: QSevRecommendation | None
    conditions: str | None
    evaluated_at: date | None
    submitted_at: datetime | None
    submitted_by: Q4UserRef | None
    approved_at: datetime | None
    next_evaluation_due: date | None
    status: QSevStatus
    status_reason: str | None
    can_approve: bool


class Q4ScoreRead(ApiModel):
    id: uuid.UUID
    supplier: Obj | None
    period_kind: QScorePeriod
    period_start: date
    period_end: date
    metrics: Obj
    score: Decimal | None
    band: str | None
    recommendation: str | None
    status: QScoreStatus
    finalised_at: datetime | None


class Q4ContractorScore(ApiModel):
    supplier: Obj | None
    score: Decimal | None
    band: str | None
    period_start: date | None
    period_end: date | None


# ---- KPIs, targets, work value, SPC --------------------------------------------------------


class Q4KpiPage(ApiModel):
    project_id: uuid.UUID
    profile: str | None
    period_start: date
    period_end: date
    as_of: date
    tiles: list[Obj] = Field(
        description="K-141…K-169 tiles: value, display, numerator, "
        "denominator, chips, target, rag (green / amber / red)."
    )
    warnings: list[Obj] = Field(description="E26–E28 for the month ending at period_end.")
    charts: Obj = Field(description="C42–C46, C49–C51 series (aggregates only).")


class Q4KpiTargetInput(StrictInput):
    kpi_id: str = Field(pattern=r"^K-1(4[1-9]|5[0-9]|6[0-9])$")
    target: Decimal
    valid_from: date


class Q4KpiTargetRead(ApiModel):
    id: uuid.UUID
    kpi_id: str
    target: Decimal
    valid_from: date


class Q4WorkValueInput(StrictInput):
    month: date = Field(description="Any day of the month (stored as the first).")
    value_sar: Decimal = Field(ge=0)


class Q4WorkValueRead(ApiModel):
    id: uuid.UUID
    month: date
    value_sar: Decimal


class Q4SpcInput(StrictInput):
    code: str | None = Field(default=None, max_length=30)
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    chart_type: QSpcType | None = None
    source: QSpcSource | None = None
    filters: dict[str, Any] | None = None
    subgroup_size: int | None = Field(default=None, ge=2, le=10)
    baseline: QSpcBaseline | None = None
    baseline_keys: list[str] | None = None
    lsl: Decimal | None = None
    usl: Decimal | None = None
    owner_user_id: uuid.UUID | None = None
    active: bool | None = None


class Q4SpcRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    title_en: str
    title_ar: str
    chart_type: QSpcType
    source: QSpcSource
    filters: Obj
    subgroup_size: int | None
    baseline: QSpcBaseline
    lsl: Decimal | None
    usl: Decimal | None
    owner_user_id: uuid.UUID | None
    active: bool
    result: Obj = Field(
        description="Centre and limits, provisional flag, points, signals "
        "(rule, chart), capability (Cp / Cpk, short-term)."
    )
