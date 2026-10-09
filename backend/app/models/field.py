"""Phase 6d tables (spec 6d-field-assurance §3): project settings, the org-wide checklist template
and toolbox topic libraries (versions; items and sections as JSON inside the version), checklist
responses (answers as JSON), findings, stop-work orders, audits, toolbox talks with attendance rows
and briefing campaigns. Phase 1 inspection plans and inspections gain columns (§3.3, EXE-3).

Audit programme lines (§3.8) are derived on read, like the 6c drill programme (DECISIONS #157)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.field_enums import (
    AttendanceMethod,
    AuditGrade,
    AuditStatus,
    AuditType,
    CampaignReason,
    CampaignStatus,
    FindingSeverity,
    InstructedRole,
    ResponseOwnerType,
    ResponseResult,
    StopOrderStatus,
    TalkShift,
    TalkStatus,
    TemplateKind,
    TopicCategory,
    UnderstoodLanguage,
    VersionStatus,
)
from app.core.hse_enums import InspectionType
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col


class FieldSettings(Base):
    """§3.14 (one row per project). The two switch dates are columns; the other keys live in
    `values` and are merged over the defaults on read (services/field/common.DEFAULTS)."""

    __tablename__ = "project_field_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    inspection_template_required_from: Mapped[date | None] = mapped_column(Date)
    toolbox_register_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ChecklistTemplate(Audited, Base):
    """§3.1 one version of a template; sections and items (§3.2) as JSON rows."""

    __tablename__ = "checklist_templates"
    __table_args__ = (UniqueConstraint("template_code", "version"),)

    template_code: Mapped[str] = mapped_column(String(8), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[TemplateKind] = enum_col(TemplateKind)
    inspection_type: Mapped[InspectionType | None] = enum_col(InspectionType, nullable=True)
    audit_type: Mapped[AuditType | None] = enum_col(AuditType, nullable=True)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    zone_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    project_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    pass_mark_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("85.0"))
    review_due_on: Mapped[date | None] = mapped_column(Date)
    change_note: Mapped[str | None] = mapped_column(String(500))
    authored_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[VersionStatus] = enum_col(VersionStatus, default=VersionStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class ToolboxTopic(Audited, Base):
    """§3.10 one version of a topic."""

    __tablename__ = "toolbox_topics"
    __table_args__ = (UniqueConstraint("topic_code", "version"),)

    topic_code: Mapped[str] = mapped_column(String(10), index=True)
    version: Mapped[int] = mapped_column(Integer)
    category: Mapped[TopicCategory] = enum_col(TopicCategory)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150), default="")
    key_points_en: Mapped[list[str]] = mapped_column(JSONB, default=list)
    key_points_ar: Mapped[list[str]] = mapped_column(JSONB, default=list)
    translations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    linked_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    review_due_on: Mapped[date | None] = mapped_column(Date)
    authored_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[VersionStatus] = enum_col(VersionStatus, default=VersionStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class ChecklistResponse(Audited, Base):
    """§3.4 / §3.5 answers of one inspection or audit (site, zone, engagement and the local
    completed date are copied from the owner for the KPI queries)."""

    __tablename__ = "checklist_responses"
    __table_args__ = (
        UniqueConstraint("project_id", "client_uuid", name="uq_checklist_response_client_uuid"),
        Index("ix_checklist_response_completed", "project_id", "completed_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    client_uuid: Mapped[uuid.UUID] = mapped_column()
    owner_type: Mapped[ResponseOwnerType] = enum_col(ResponseOwnerType)
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inspections.id"))
    audit_id: Mapped[uuid.UUID | None] = mapped_column()
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklist_templates.id"))
    template_code: Mapped[str] = mapped_column(String(8))
    template_version: Mapped[int] = mapped_column(Integer)
    inspection_type: Mapped[InspectionType | None] = enum_col(InspectionType, nullable=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    airside: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offline_delay_min: Mapped[int | None] = mapped_column(Integer)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    applicable_count: Mapped[int] = mapped_column(Integer, default=0)
    compliant_count: Mapped[int] = mapped_column(Integer, default=0)
    applicable_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal(0))
    earned_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal(0))
    score_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    critical_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[ResponseResult | None] = enum_col(ResponseResult, nullable=True)
    grade: Mapped[AuditGrade | None] = enum_col(AuditGrade, nullable=True)
    stop_work_order_id: Mapped[uuid.UUID | None] = mapped_column()
    self_inspection: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class FieldFinding(Audited, Base):
    """§3.6 (one per non-compliant scored answer, FND-1, or manual, FND-2)."""

    __tablename__ = "field_findings"
    __table_args__ = (
        Index("ix_field_finding_repeat", "project_id", "item_code", "completed_date"),
        Index("ix_field_finding_response", "response_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    response_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklist_responses.id"))
    finding_no: Mapped[str] = mapped_column(String(60), unique=True)
    item_code: Mapped[str | None] = mapped_column(String(12))
    severity: Mapped[FindingSeverity] = enum_col(FindingSeverity)
    critical_item: Mapped[bool] = mapped_column(Boolean, default=False)
    description_en: Mapped[str | None] = mapped_column(String(1000))
    description_ar: Mapped[str | None] = mapped_column(String(1000))
    repeat_of_id: Mapped[uuid.UUID | None] = mapped_column()
    fixed_on_spot: Mapped[bool] = mapped_column(Boolean, default=False)
    ca_required: Mapped[bool] = mapped_column(Boolean, default=False)
    ca_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("corrective_actions.id"))
    responsible_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column()  # the response's engagement
    completed_date: Mapped[date | None] = mapped_column(Date)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)


class StopWorkOrder(Audited, Numbered, Base):
    """§3.9."""

    __tablename__ = "stop_work_orders"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    order_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    response_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklist_responses.id"))
    item_code: Mapped[str] = mapped_column(String(12))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    activity_en: Mapped[str | None] = mapped_column(String(300))
    activity_ar: Mapped[str | None] = mapped_column(String(300))
    instructed_role: Mapped[InstructedRole] = enum_col(InstructedRole)
    instructed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    permit_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    ca_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("corrective_actions.id"))
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_note: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[StopOrderStatus] = enum_col(StopOrderStatus, default=StopOrderStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)  # alerts + suspensions done
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FieldAudit(Audited, Numbered, Base):
    """§3.7."""

    __tablename__ = "field_audits"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    audit_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    audit_type: Mapped[AuditType] = enum_col(AuditType)
    template_code: Mapped[str] = mapped_column(String(8))
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checklist_templates.id"))
    auditee_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    lead_auditor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    team_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    planned_start: Mapped[date] = mapped_column(Date)
    planned_end: Mapped[date] = mapped_column(Date)
    fieldwork_start: Mapped[date | None] = mapped_column(Date)
    fieldwork_end: Mapped[date | None] = mapped_column(Date)
    opening_meeting_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closing_meeting_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auditee_attendee_roles: Mapped[str | None] = mapped_column(String(300))
    response_id: Mapped[uuid.UUID | None] = mapped_column()
    summary_en: Mapped[str | None] = mapped_column(String(3000))
    summary_ar: Mapped[str | None] = mapped_column(String(3000))
    report_en_id: Mapped[uuid.UUID | None] = mapped_column()
    report_ar_id: Mapped[uuid.UUID | None] = mapped_column()
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AuditStatus] = enum_col(AuditStatus, default=AuditStatus.planned)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class ToolboxTalk(Audited, Numbered, Base):
    """§3.11."""

    __tablename__ = "toolbox_talks"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        UniqueConstraint("project_id", "client_uuid", name="uq_toolbox_talk_client_uuid"),
        Index("ix_toolbox_talk_delivered", "project_id", "delivered_date"),
    )

    talk_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    client_uuid: Mapped[uuid.UUID] = mapped_column()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    host_engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    shift: Mapped[TalkShift] = enum_col(TalkShift)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_date: Mapped[date] = mapped_column(Date)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    presenter_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    presenter_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("worker_deployments.id")
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    topics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    topic_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    language: Mapped[str] = mapped_column(String(10))
    interpreter_languages: Mapped[list[str]] = mapped_column(STRS, default=list)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column()
    unnamed_count: Mapped[int] = mapped_column(Integer, default=0)
    sheet_photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    questions_raised: Mapped[str | None] = mapped_column(String(1000))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offline_delay_min: Mapped[int | None] = mapped_column(Integer)
    rejected_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[TalkStatus] = enum_col(TalkStatus, default=TalkStatus.delivered)
    status_reason: Mapped[str | None] = mapped_column(String(500))


class TalkAttendance(UUIDPk, Base):
    """§3.12."""

    __tablename__ = "toolbox_attendance"
    __table_args__ = (UniqueConstraint("talk_id", "deployment_id"),)

    talk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("toolbox_talks.id"), index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    method: Mapped[AttendanceMethod] = enum_col(AttendanceMethod)
    signature_id: Mapped[uuid.UUID | None] = mapped_column()
    understood_language: Mapped[UnderstoodLanguage] = enum_col(UnderstoodLanguage)
    counted_person_type: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class BriefingCampaign(Audited, Numbered, Base):
    """§3.13."""

    __tablename__ = "briefing_campaigns"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    campaign_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("toolbox_topics.id"))
    topic_code: Mapped[str] = mapped_column(String(10))
    reason: Mapped[CampaignReason] = enum_col(CampaignReason)
    reason_ref: Mapped[str | None] = mapped_column(String(60))
    message_en: Mapped[str | None] = mapped_column(String(1000))
    message_ar: Mapped[str | None] = mapped_column(String(1000))
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    pairs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CampaignStatus] = enum_col(CampaignStatus, default=CampaignStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
