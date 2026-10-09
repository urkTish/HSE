"""Phase 6f tables (spec 6f-incident-followup §3): project follow-up settings and profile, the
notification rule profile, per-incident trigger clocks, notification requirements, packs,
submissions, lessons learned, distribution items, 6d links and effectiveness checks."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.followup_enums import (
    FuAckResponse,
    FuChangeStatus,
    FuChannel,
    FuCheckStatus,
    FuDeadlineBasis,
    FuDistributionStatus,
    FuEffectResult,
    FuFieldSet,
    FuFiler,
    FuLessonSource,
    FuLessonStatus,
    FuLinkKind,
    FuPackStatus,
    FuRuleSource,
    FuStage,
    FuSubmissionStatus,
    FuWaiverReason,
)
from app.core.hse_enums import ExternalBody
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import enum_col


class FuSettings(Base):
    """§3.2 profile and §3.10 settings (one row per project). `followup_rules_from` is a column
    (NR-1); the other keys live in `values`, merged over the defaults on read."""

    __tablename__ = "project_followup_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    followup_rules_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    client_recipients: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    body_directory: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    signatory_role_en: Mapped[str | None] = mapped_column(String(120))
    signatory_role_ar: Mapped[str | None] = mapped_column(String(120))
    client_identity_clause: Mapped[str | None] = mapped_column(String(1000))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class FuRule(Audited, Base):
    """§3.1 one row of the project's notification rule profile."""

    __tablename__ = "fu_rules"
    __table_args__ = (UniqueConstraint("project_id", "rule_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(16))
    body: Mapped[ExternalBody] = enum_col(ExternalBody)
    stage: Mapped[FuStage] = enum_col(FuStage)
    source: Mapped[FuRuleSource] = enum_col(FuRuleSource)
    triggers: Mapped[list[str]] = mapped_column(STRS, default=list)
    trigger_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    deadline_hours: Mapped[int | None] = mapped_column(Integer)
    deadline_basis: Mapped[FuDeadlineBasis] = enum_col(FuDeadlineBasis)
    form_code: Mapped[str | None] = mapped_column(String(20))
    filer: Mapped[FuFiler] = enum_col(FuFiler)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FuIncidentClock(Base):
    """NR-5: first time each trigger (per case where it applies) was true for the incident."""

    __tablename__ = "fu_incident_clocks"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    trigger_times: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    derived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FuRequirement(Audited, Base):
    """§3.3 one requirement per (incident, rule, case) — GOSI / MHRSD-F per case (NR-6)."""

    __tablename__ = "fu_requirements"
    __table_args__ = (
        UniqueConstraint("incident_id", "rule_code", "case_key"),
        Index("ix_fu_requirement_project_due", "project_id", "due_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(16))
    case_key: Mapped[str] = mapped_column(String(8), default="")
    body: Mapped[ExternalBody] = enum_col(ExternalBody)
    stage: Mapped[FuStage] = enum_col(FuStage)
    source: Mapped[FuRuleSource] = enum_col(FuRuleSource)
    form_code: Mapped[str | None] = mapped_column(String(20))
    filer: Mapped[FuFiler] = enum_col(FuFiler)
    trigger_met_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_hours: Mapped[int | None] = mapped_column(Integer)
    filer_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    responsible_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    case_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    not_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_note: Mapped[str | None] = mapped_column(String(200))
    waiver_reason_code: Mapped[FuWaiverReason | None] = enum_col(FuWaiverReason, nullable=True)
    waiver_text: Mapped[str | None] = mapped_column(String(500))
    waiver_reference: Mapped[str | None] = mapped_column(String(60))
    waiver_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    waived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FuPack(Audited, Numbered, Base):
    """§3.4."""

    __tablename__ = "fu_packs"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    pack_no: Mapped[str] = mapped_column(String(40))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fu_requirements.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    form_code: Mapped[str] = mapped_column(String(20))
    field_set: Mapped[FuFieldSet] = enum_col(FuFieldSet)
    languages: Mapped[list[str]] = mapped_column(STRS, default=list)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    narrative_en: Mapped[str | None] = mapped_column(Text)
    narrative_ar: Mapped[str | None] = mapped_column(Text)
    extra_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[FuPackStatus] = enum_col(FuPackStatus, default=FuPackStatus.draft)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FuSubmission(Audited, Numbered, Base):
    """§3.5."""

    __tablename__ = "fu_submissions"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    submission_no: Mapped[str] = mapped_column(String(40))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fu_requirements.id"), index=True)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fu_packs.id"))
    channel: Mapped[FuChannel] = enum_col(FuChannel)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    contacted_desk_en: Mapped[str | None] = mapped_column(String(120))
    contacted_desk_ar: Mapped[str | None] = mapped_column(String(120))
    reference_no: Mapped[str | None] = mapped_column(String(60))
    call_note: Mapped[str | None] = mapped_column(String(200))
    evidence_file_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    stamped_copy_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    external_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_reference: Mapped[str | None] = mapped_column(String(60))
    ack_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    on_time: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[FuSubmissionStatus] = enum_col(
        FuSubmissionStatus, default=FuSubmissionStatus.recorded
    )
    void_reason: Mapped[str | None] = mapped_column(String(500))


class FuLesson(Audited, Base):
    """§3.6 (org-wide numbering LL-<yyyy>-<nnn>)."""

    __tablename__ = "fu_lessons"
    __table_args__ = (UniqueConstraint("year", "seq"),)

    lesson_no: Mapped[str] = mapped_column(String(20), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    source: Mapped[FuLessonSource] = enum_col(FuLessonSource)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    external_ref: Mapped[str | None] = mapped_column(String(200))
    system_created: Mapped[bool] = mapped_column(Boolean, default=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    title_en: Mapped[str | None] = mapped_column(String(150))
    title_ar: Mapped[str | None] = mapped_column(String(150))
    what_happened_en: Mapped[str | None] = mapped_column(Text)
    what_happened_ar: Mapped[str | None] = mapped_column(Text)
    why_en: Mapped[str | None] = mapped_column(Text)
    why_ar: Mapped[str | None] = mapped_column(Text)
    root_cause_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    key_lessons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    actions_taken: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    severity_potential: Mapped[int | None] = mapped_column(Integer)
    photos: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    distribution_project_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    removed_engagements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    publish_due_on: Mapped[date | None] = mapped_column(Date)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fu_lessons.id"))
    return_comment: Mapped[str | None] = mapped_column(String(500))
    status_reason: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[FuLessonStatus] = enum_col(FuLessonStatus, default=FuLessonStatus.draft)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FuDistribution(Audited, Base):
    """§3.7 one (project, engagement) item fixed at publication (DS-1)."""

    __tablename__ = "fu_distribution_items"
    __table_args__ = (UniqueConstraint("lesson_id", "project_id", "engagement_id"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fu_lessons.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    ack_due_on: Mapped[date] = mapped_column(Date)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response: Mapped[FuAckResponse | None] = enum_col(FuAckResponse, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    on_behalf_note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[FuDistributionStatus] = enum_col(
        FuDistributionStatus, default=FuDistributionStatus.pending
    )
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FuLessonLink(Audited, Base):
    """§3.8 a link to a 6d topic or campaign, or a template change request."""

    __tablename__ = "fu_lesson_links"

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fu_lessons.id"), index=True)
    kind: Mapped[FuLinkKind] = enum_col(FuLinkKind)
    ref: Mapped[str] = mapped_column(String(40))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    item_code: Mapped[str | None] = mapped_column(String(20))
    proposed_text_en: Mapped[str | None] = mapped_column(String(1000))
    proposed_text_ar: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[FuChangeStatus | None] = enum_col(FuChangeStatus, nullable=True)
    adopted_version: Mapped[int | None] = mapped_column(Integer)
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FuEffectivenessCheck(Audited, Base):
    """§3.9."""

    __tablename__ = "fu_effectiveness_checks"

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fu_lessons.id"), unique=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    due_on: Mapped[date] = mapped_column(Date)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    suggested_result: Mapped[FuEffectResult | None] = enum_col(FuEffectResult, nullable=True)
    result: Mapped[FuEffectResult | None] = enum_col(FuEffectResult, nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(1000))
    follow_up_ca_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("corrective_actions.id"))
    follow_up_lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fu_lessons.id"))
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[FuCheckStatus] = enum_col(FuCheckStatus, default=FuCheckStatus.scheduled)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


__all__ = [
    "FuDistribution",
    "FuEffectivenessCheck",
    "FuIncidentClock",
    "FuLesson",
    "FuLessonLink",
    "FuPack",
    "FuRequirement",
    "FuRule",
    "FuSettings",
    "FuSubmission",
]
