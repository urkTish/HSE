"""Phase 5 tables (spec 5-training §3): course catalogue, training providers and their
accreditations, trainer authorisations, the versioned training matrix, worker training profiles,
requirement exemptions, sessions with nominations / attendance / assessment, training records,
verification records, settings, re-training notes and import batches.

The hook policy state (kind training_course) reuses the Phase 4 `hook_policy_states` table
(§3.12); session certificates use Phase 2 `qr_tokens` with kind TR (TR-14)."""

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access_enums import WorkerLanguage
from app.core.cert_enums import IdMatchResult, NameMatch, VerificationStatus
from app.core.clock import now
from app.core.train_enums import (
    AttendanceResult,
    CourseCategory,
    DeliveryMode,
    ExemptionStatus,
    MatrixAppliesTo,
    MatrixLevel,
    MatrixLineSource,
    NominationStatus,
    PracticalResult,
    ProviderBlacklistScope,
    SessionStatus,
    SessionVoidReason,
    TrainerAuthorisationStatus,
    TrainingImportSource,
    TrainingImportStatus,
    TrainingImportTemplate,
    TrainingLimitingFactor,
    TrainingProviderKind,
    TrainingProviderStatus,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
    UnderstoodLanguage,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col

DOMAINS = ARRAY(String(253))

# ---- catalogue (§3.1) ----------------------------------------------------------------------------


class TrainingCourse(Audited, Base):
    """Org-wide catalogue row. Built-in rows (§3.15) are created on first use (`seeded`)."""

    __tablename__ = "training_courses"

    code: Mapped[str] = mapped_column(String(20), unique=True)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    category: Mapped[CourseCategory] = enum_col(CourseCategory)
    induction_type: Mapped[str | None] = mapped_column(String(40))
    # project id (str) → Phase 2 induction course code (zone_specific links, CC-7)
    induction_project_codes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    validity_months: Mapped[int | None] = mapped_column(Integer)
    min_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    max_class_size: Mapped[int | None] = mapped_column(Integer)
    delivery_modes: Mapped[list[str]] = mapped_column(STRS, default=list)
    theory_required: Mapped[bool] = mapped_column(Boolean, default=False)
    pass_mark_pct: Mapped[int | None] = mapped_column(Integer)
    practical_required: Mapped[bool] = mapped_column(Boolean, default=False)
    prerequisite_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    satisfies: Mapped[list[str]] = mapped_column(STRS, default=list)
    renewal_course_code: Mapped[str | None] = mapped_column(String(20))
    renews_only: Mapped[bool] = mapped_column(Boolean, default=False)
    internal_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    contractor_delivery_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    accreditation_bodies_required: Mapped[list[str]] = mapped_column(STRS, default=list)
    languages_offered: Mapped[list[str]] = mapped_column(STRS, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- providers (§3.2) ----------------------------------------------------------------------------


class TrainingProvider(Audited, Base):
    __tablename__ = "training_providers"

    provider_code: Mapped[str] = mapped_column(String(12), unique=True)
    legal_name_en: Mapped[str] = mapped_column(String(200))
    legal_name_ar: Mapped[str] = mapped_column(String(200))
    name_norm_en: Mapped[str] = mapped_column(String(200), unique=True)
    name_norm_ar: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[TrainingProviderKind] = enum_col(TrainingProviderKind)
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contractors.id"))
    country: Mapped[str | None] = mapped_column(String(2))
    cr_number: Mapped[str | None] = mapped_column(String(10))
    foreign_reg_no: Mapped[str | None] = mapped_column(String(30))
    verification_portal_url: Mapped[str | None] = mapped_column(String(300))
    verification_domains: Mapped[list[str]] = mapped_column(DOMAINS, default=list)
    verification_email: Mapped[str | None] = mapped_column(String(254))
    verification_phone: Mapped[str | None] = mapped_column(String(20))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_mobile: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[TrainingProviderStatus] = enum_col(
        TrainingProviderStatus, default=TrainingProviderStatus.draft
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    # PV-5: [{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD" | null}] — refused from the date
    suspension_periods: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    blacklist_scope: Mapped[ProviderBlacklistScope | None] = enum_col(
        ProviderBlacklistScope, nullable=True
    )
    blacklist_from: Mapped[date | None] = mapped_column(Date)
    blacklisted_on: Mapped[date | None] = mapped_column(Date)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingProviderAccreditation(Audited, Base):
    __tablename__ = "training_provider_accreditations"
    __table_args__ = (UniqueConstraint("accreditation_body", "accreditation_no"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_providers.id"), index=True)
    accreditation_body: Mapped[str] = mapped_column(String(40))
    accreditation_no: Mapped[str] = mapped_column(String(40))
    scope_course_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    certificate_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    register_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    register_checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    register_check_note: Mapped[str | None] = mapped_column(String(300))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- trainer authorisations (§3.3) ---------------------------------------------------------------


class TrainerAuthorisation(Audited, Base):
    __tablename__ = "trainer_authorisations"
    __table_args__ = (UniqueConstraint("project_id", "seq"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    authorisation_no: Mapped[str] = mapped_column(String(40), unique=True)
    trainer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    trainer_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_providers.id"))
    course_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    roles: Mapped[list[str]] = mapped_column(STRS, default=list)
    basis: Mapped[str] = mapped_column(String(500))
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    status: Mapped[TrainerAuthorisationStatus] = enum_col(
        TrainerAuthorisationStatus, default=TrainerAuthorisationStatus.active
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    # [{"from": date, "to": date | null}] suspensions (TA-2 "on every session day")
    suspension_periods: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    ended_on: Mapped[date | None] = mapped_column(Date)
    authorised_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    authorised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- matrix (§3.4) and profiles (§3.5) -----------------------------------------------------------


class TrainingMatrixLine(Audited, Base):
    """One version of a matrix line: `line_id` is stable across versions; `id` is the version.
    A change closes the open version (effective_to = yesterday) and opens a new one from today
    (MX-7). Hook-derived lines (source hook) are kept in step with the Phase 2/3 attach points
    (MX-2); `hook_key` identifies the attach point."""

    __tablename__ = "training_matrix_lines"
    __table_args__ = (
        Index("ix_matrix_line_project", "project_id", "effective_from"),
        Index("ix_matrix_line_line", "line_id"),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    line_no: Mapped[str] = mapped_column(String(40))
    applies_to_kind: Mapped[MatrixAppliesTo] = enum_col(MatrixAppliesTo)
    applies_to_values: Mapped[list[str]] = mapped_column(STRS, default=list)
    course_code: Mapped[str | None] = mapped_column(String(20))
    any_of: Mapped[list[str]] = mapped_column(STRS, default=list)
    level: Mapped[MatrixLevel] = enum_col(MatrixLevel)
    due_within_days: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[MatrixLineSource] = enum_col(MatrixLineSource)
    kpi_counted: Mapped[bool] = mapped_column(Boolean, default=True)
    hook_key: Mapped[str | None] = mapped_column(String(200))
    hook_attach_point: Mapped[str | None] = mapped_column(String(200))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(300))


class TrainingProfile(Audited, Base):
    """Per Phase 2 deployment; `history` rows {field, value[], from_date, to_date, by} (MX-9)."""

    __tablename__ = "training_profiles"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("worker_deployments.id"), unique=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    matrix_roles: Mapped[list[str]] = mapped_column(STRS, default=list)
    work_zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class TrainingExemption(Audited, Base):
    __tablename__ = "training_exemptions"
    __table_args__ = (Index("ix_training_exemption_dep", "deployment_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    line_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String(500))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[ExemptionStatus] = enum_col(ExemptionStatus, default=ExemptionStatus.active)
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    withdrawn_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(String(500))


# ---- sessions (§3.6) and nominations (§3.7) ------------------------------------------------------


class TrainingSession(Numbered, Audited, Base):
    """`days`: [{"date", "start_time", "end_time", "break_minutes"}] (day_no = index + 1).
    `trainers`: [{"user_id", "worker_id", "external_name", "roles", "authorisation_id"}]."""

    __tablename__ = "training_sessions"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_training_session_project_day", "project_id", "first_day"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    session_no: Mapped[str] = mapped_column(String(40), unique=True)
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_providers.id"))
    delivery_mode: Mapped[DeliveryMode] = enum_col(DeliveryMode)
    trainers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    trainer_user_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    trainer_worker_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    offsite_text: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[WorkerLanguage] = enum_col(WorkerLanguage)
    interpreter_languages: Mapped[list[str]] = mapped_column(STRS, default=list)
    days: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    first_day: Mapped[date] = mapped_column(Date)
    last_day: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    net_minutes_total: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    status: Mapped[SessionStatus] = enum_col(SessionStatus, default=SessionStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attendance_sheet_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason_code: Mapped[SessionVoidReason | None] = enum_col(SessionVoidReason, nullable=True)
    void_reason_text: Mapped[str | None] = mapped_column(String(500))
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class TrainingNomination(Audited, Base):
    __tablename__ = "training_nominations"
    __table_args__ = (
        UniqueConstraint("session_id", "worker_id"),
        Index("ix_training_nomination_worker", "worker_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_sessions.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    contractor_worker: Mapped[bool] = mapped_column(Boolean, default=True)
    nominated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    nominated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[NominationStatus] = enum_col(
        NominationStatus, default=NominationStatus.nominated
    )
    # day_no (str) → attended minutes
    minutes_by_day: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    understood_language: Mapped[UnderstoodLanguage] = enum_col(UnderstoodLanguage)
    theory_score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    practical_result: Mapped[PracticalResult | None] = enum_col(PracticalResult, nullable=True)
    practical_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    result: Mapped[AttendanceResult] = enum_col(AttendanceResult, default=AttendanceResult.pending)
    result_reason: Mapped[str | None] = mapped_column(String(40))
    signature_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    record_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(String(300))


# ---- records (§3.8) and verification (§3.9) ------------------------------------------------------


class TrainingRecord(Audited, Base):
    __tablename__ = "training_records"
    __table_args__ = (
        UniqueConstraint("provider_id", "course_code", "certificate_no"),
        Index("ix_training_record_worker", "worker_id", "course_code"),
        Index("ix_training_record_project", "project_id", "status"),
    )

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    record_no: Mapped[str] = mapped_column(String(12), unique=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    course_code: Mapped[str] = mapped_column(String(20))
    source: Mapped[TrainingRecordSource] = enum_col(TrainingRecordSource)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_providers.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    certificate_no: Mapped[str] = mapped_column(String(40))
    completed_on: Mapped[date] = mapped_column(Date)
    printed_expiry: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[TrainingLimitingFactor] = enum_col(TrainingLimitingFactor)
    theory_score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    practical_result: Mapped[PracticalResult | None] = enum_col(PracticalResult, nullable=True)
    hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    project_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsoring_project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    name_as_printed: Mapped[str | None] = mapped_column(String(120))
    name_match: Mapped[NameMatch | None] = enum_col(NameMatch, nullable=True)
    id_match_result: Mapped[IdMatchResult | None] = enum_col(IdMatchResult, nullable=True)
    identity_confirmed_by_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    scans_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_verification_url: Mapped[str | None] = mapped_column(String(300))
    prerequisite_evidenced: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[TrainingRecordStatus] = enum_col(TrainingRecordStatus)
    status_reason: Mapped[TrainingStatusReason | None] = enum_col(
        TrainingStatusReason, nullable=True
    )
    status_reason_text: Mapped[str | None] = mapped_column(String(500))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.not_verified
    )
    verification_due_on: Mapped[date | None] = mapped_column(Date)
    historic: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # the moment the record first satisfied the in-force predicate (§6.6; KPIs as of a date)
    in_force_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    superseded_on: Mapped[date | None] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    anonymised: Mapped[bool] = mapped_column(Boolean, default=False)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class TrainingVerification(UUIDPk, Base):
    __tablename__ = "training_verifications"
    __table_args__ = (Index("ix_training_verification_record", "record_id"),)

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_records.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_providers.id"))
    method: Mapped[TrainingVerificationMethod] = enum_col(TrainingVerificationMethod)
    channel_used: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[TrainingVerificationOutcome] = enum_col(TrainingVerificationOutcome)
    differences: Mapped[list[str]] = mapped_column(STRS, default=list)
    differences_text: Mapped[str | None] = mapped_column(String(300))
    reference: Mapped[str] = mapped_column(String(100))
    evidence_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    counts_as_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status_after: Mapped[VerificationStatus] = enum_col(VerificationStatus)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- settings (§3.16), re-training notes (AT-5), imports (§3.13) ---------------------------------


class TrainingSettings(Base):
    """§3.16 (one row per project, created with the defaults on first use).
    `training_register_from` lives in the Phase 1 settings (project_hse_settings)."""

    __tablename__ = "project_training_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    course_validity_months: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    training_pass_mark_pct: Mapped[int] = mapped_column(Integer, default=80)
    training_max_attempts_30d: Mapped[int] = mapped_column(Integer, default=3)
    unverified_training_acceptance_hours: Mapped[int] = mapped_column(Integer, default=0)
    training_verification_due_days: Mapped[int] = mapped_column(Integer, default=3)
    session_close_deadline_days: Mapped[int] = mapped_column(Integer, default=3)
    session_backdate_max_days: Mapped[int] = mapped_column(Integer, default=7)
    session_day_max_net_hours: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("10.00")
    )
    trainer_authorisation_max_months: Mapped[int] = mapped_column(Integer, default=24)
    refresher_planning_days: Mapped[int] = mapped_column(Integer, default=60)
    refresher_max_lapse_days: Mapped[int] = mapped_column(Integer, default=0)
    matrix_line_max_due_days: Mapped[int] = mapped_column(Integer, default=90)
    language_block_categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    training_hook_transition_days: Mapped[int] = mapped_column(Integer, default=30)
    training_hook_critical_transition_days: Mapped[int] = mapped_column(Integer, default=7)
    training_hook_critical_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    training_matrix_warning_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal("98.0")
    )
    training_scan_retention_years: Mapped[int] = mapped_column(Integer, default=2)
    alert_schedule_long_days: Mapped[list[int]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class TrainingRetrainingNote(UUIDPk, Base):
    __tablename__ = "training_retraining_notes"
    __table_args__ = (Index("ix_training_retraining_worker", "worker_id", "course_code"),)

    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    course_code: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class TrainingImportBatch(UUIDPk, Base):
    __tablename__ = "training_import_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    template: Mapped[TrainingImportTemplate] = enum_col(TrainingImportTemplate)
    source: Mapped[TrainingImportSource] = enum_col(TrainingImportSource)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"))
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_providers.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    scans_zip_name: Mapped[str | None] = mapped_column(String(255))
    scans_count: Mapped[int | None] = mapped_column(Integer)
    # certificate_no → attachment id (created at upload, owner = batch; re-owned at commit)
    scan_map: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_file_name: Mapped[str | None] = mapped_column(String(255))
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[TrainingImportStatus] = enum_col(TrainingImportStatus)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    file_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # parsed rows (ID numbers encrypted per row, IM5-4); cleared at commit / discard / expiry
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    committed_record_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
