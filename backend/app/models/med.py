"""Phase 6a tables (spec 6a-occupational-health §3): fitness code catalogue, medical providers
(clinics), examiner registrations, the versioned requirement plan, worker health profiles,
fitness assessments with their lines, verification records, fitness holds, referrals, project
settings and import batches.

The hook policy state (kind medical_fitness) reuses the Phase 4 `hook_policy_states` table
(§3.9). Free texts that may describe a person's health (hold reason text, referral note,
revoke / status reasons, other_functional restriction text) are encrypted at application level
(P6-5); outcomes, restrictions and dates are coded values in plain columns so the KPI engine
can aggregate them (DECISIONS #120)."""

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
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.cert_enums import IdMatchResult, NameMatch, VerificationStatus
from app.core.clock import now
from app.core.med_enums import (
    AssessmentSource,
    AssessmentStatus,
    AssessmentType,
    ExaminerClass,
    ExaminerStatus,
    FitnessCategory,
    FitnessLimitingFactor,
    FitnessLineState,
    FitnessOutcome,
    FitnessVerificationMethod,
    FitnessVerificationOutcome,
    HoldCancelCode,
    HoldReason,
    HoldSourceType,
    HoldStatus,
    MedicalAppliesTo,
    MedicalBlacklistScope,
    MedicalImportSource,
    MedicalImportStatus,
    MedicalLineSource,
    MedicalProviderKind,
    MedicalProviderStatus,
    ReferralReason,
    ReferralStatus,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col

DOMAINS = ARRAY(String(253))

# ---- catalogue (§3.1) ----------------------------------------------------------------------------


class FitnessCode(Audited, Base):
    __tablename__ = "fitness_codes"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    category: Mapped[FitnessCategory] = enum_col(FitnessCategory)
    validity_months: Mapped[int] = mapped_column(Integer)
    examiner_classes: Mapped[list[str]] = mapped_column(STRS, default=list)
    provider_kinds: Mapped[list[str]] = mapped_column(STRS, default=list)
    typical_tests: Mapped[list[str]] = mapped_column(STRS, default=list)
    # MC-3 "a restriction added to another code's negates": extra RC codes negating this code
    extra_negated_by: Mapped[list[str]] = mapped_column(STRS, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- providers (§3.2) and examiners (§3.3) -------------------------------------------------------


class MedicalProvider(Audited, Base):
    __tablename__ = "medical_providers"

    provider_code: Mapped[str] = mapped_column(String(12), unique=True)
    legal_name_en: Mapped[str] = mapped_column(String(200))
    legal_name_ar: Mapped[str] = mapped_column(String(200))
    name_norm_en: Mapped[str] = mapped_column(String(200), unique=True)
    name_norm_ar: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[MedicalProviderKind] = enum_col(MedicalProviderKind)
    project_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contractors.id"))
    moh_licence_no: Mapped[str] = mapped_column(String(40), unique=True)
    licence_valid_until: Mapped[date] = mapped_column(Date)
    licence_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    licence_checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verification_domains: Mapped[list[str]] = mapped_column(DOMAINS, default=list)
    verification_email: Mapped[str | None] = mapped_column(String(254))
    verification_phone: Mapped[str | None] = mapped_column(String(20))
    verification_portal_url: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[MedicalProviderStatus] = enum_col(
        MedicalProviderStatus, default=MedicalProviderStatus.draft
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    approved_on: Mapped[date | None] = mapped_column(Date)
    # MP-4: [{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD" | null}] — new lines refused from the date
    suspension_periods: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    blacklist_scope: Mapped[MedicalBlacklistScope | None] = enum_col(
        MedicalBlacklistScope, nullable=True
    )
    blacklist_from: Mapped[date | None] = mapped_column(Date)
    blacklisted_on: Mapped[date | None] = mapped_column(Date)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class MedicalExaminer(Audited, Base):
    __tablename__ = "medical_examiners"

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    examiner_no: Mapped[str] = mapped_column(String(12), unique=True)
    full_name_en: Mapped[str] = mapped_column(String(120))
    full_name_ar: Mapped[str] = mapped_column(String(120))
    scfhs_licence_no: Mapped[str] = mapped_column(String(30), unique=True)
    classification: Mapped[ExaminerClass] = enum_col(ExaminerClass)
    licence_valid_until: Mapped[date] = mapped_column(Date)
    licence_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    licence_checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    provider_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), unique=True)
    status: Mapped[ExaminerStatus] = enum_col(ExaminerStatus, default=ExaminerStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- requirement plan (§3.4) and health profiles (§3.5) ------------------------------------------


class MedicalPlanLine(Audited, Base):
    """One version of a plan line: `line_id` is stable across versions; `id` is the version
    (as Phase 5 matrix lines). Derived lines (source hook / enforcement) mirror the medical
    attach points (MR-2); `hook_key` identifies the attach point."""

    __tablename__ = "medical_plan_lines"
    __table_args__ = (
        Index("ix_medical_plan_project", "project_id", "effective_from"),
        Index("ix_medical_plan_line", "line_id"),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    line_no: Mapped[str] = mapped_column(String(40))
    applies_to_kind: Mapped[MedicalAppliesTo] = enum_col(MedicalAppliesTo)
    applies_to_values: Mapped[list[str]] = mapped_column(STRS, default=list)
    # zone lines: the trades of the zone-profile hook (empty = everyone in the zone)
    trades: Mapped[list[str]] = mapped_column(STRS, default=list)
    code: Mapped[str] = mapped_column(String(24))
    due_within_days: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[MedicalLineSource] = enum_col(MedicalLineSource)
    kpi_counted: Mapped[bool] = mapped_column(Boolean, default=True)
    hook_key: Mapped[str | None] = mapped_column(String(200))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(300))


class HealthProfile(Audited, Base):
    """Per Phase 2 deployment; `history` rows {value[], from_date, to_date, by, reason?}."""

    __tablename__ = "health_profiles"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("worker_deployments.id"), unique=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    exposure_groups: Mapped[list[str]] = mapped_column(STRS, default=list)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


# ---- assessments (§3.6) and lines (§3.6a) --------------------------------------------------------


class FitnessAssessment(Numbered, Audited, Base):
    __tablename__ = "fitness_assessments"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        UniqueConstraint("provider_id", "certificate_no"),
        Index("ix_fitness_assessment_worker", "worker_id"),
        Index("ix_fitness_assessment_project", "project_id", "status"),
    )

    assessment_no: Mapped[str] = mapped_column(String(40), unique=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    assessment_type: Mapped[AssessmentType] = enum_col(AssessmentType)
    source: Mapped[AssessmentSource] = enum_col(AssessmentSource)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medical_providers.id"))
    examiner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medical_examiners.id"))
    examined_on: Mapped[date] = mapped_column(Date)
    certificate_no: Mapped[str] = mapped_column(String(40))
    related_hold_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    related_referral_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    purpose_notice_given: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose_notice_version: Mapped[str | None] = mapped_column(String(40))
    name_as_printed: Mapped[str | None] = mapped_column(String(120))
    name_match: Mapped[NameMatch | None] = enum_col(NameMatch, nullable=True)
    id_match_result: Mapped[IdMatchResult | None] = enum_col(IdMatchResult, nullable=True)
    scan_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    scan_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clinical_data_present: Mapped[bool | None] = mapped_column(Boolean)
    historic: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[AssessmentStatus] = enum_col(AssessmentStatus)
    status_reason_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.not_verified
    )
    verification_due_on: Mapped[date | None] = mapped_column(Date)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    signed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_code: Mapped[str | None] = mapped_column(String(40))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FitnessLine(UUIDPk, Base):
    """§3.6a. `valid_until` is the stored org default (§6.1); the project override applies on
    read. `restrictions`: [{code, value?, text_enc?}] (text encrypted, P6-5)."""

    __tablename__ = "fitness_lines"
    __table_args__ = (
        UniqueConstraint("assessment_id", "code"),
        Index("ix_fitness_line_worker", "worker_id", "code"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fitness_assessments.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    code: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[FitnessOutcome] = enum_col(FitnessOutcome)
    restrictions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    restriction_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    restriction_review_date: Mapped[date | None] = mapped_column(Date)
    unfit_review_date: Mapped[date | None] = mapped_column(Date)
    printed_next_due: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[FitnessLimitingFactor | None] = enum_col(
        FitnessLimitingFactor, nullable=True
    )
    line_state: Mapped[FitnessLineState] = enum_col(
        FitnessLineState, default=FitnessLineState.pending
    )
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    anonymised: Mapped[bool] = mapped_column(Boolean, default=False)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class FitnessVerification(UUIDPk, Base):
    __tablename__ = "fitness_verifications"
    __table_args__ = (Index("ix_fitness_verification_assessment", "assessment_id"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fitness_assessments.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medical_providers.id"))
    method: Mapped[FitnessVerificationMethod] = enum_col(FitnessVerificationMethod)
    channel_used: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[FitnessVerificationOutcome] = enum_col(FitnessVerificationOutcome)
    reference: Mapped[str] = mapped_column(String(100))
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    counts_as_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status_after: Mapped[VerificationStatus] = enum_col(VerificationStatus)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- holds (§3.7) and referrals (§3.8) -----------------------------------------------------------


class FitnessHold(Numbered, Audited, Base):
    """`work_during_hold`: [{event_type, ref, at}] (FH-8)."""

    __tablename__ = "fitness_holds"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_fitness_hold_worker", "worker_id", "status"),
    )

    hold_no: Mapped[str] = mapped_column(String(40), unique=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    reason: Mapped[HoldReason] = enum_col(HoldReason)
    source_type: Mapped[HoldSourceType] = enum_col(HoldSourceType)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(40))
    reason_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[HoldStatus] = enum_col(HoldStatus, default=HoldStatus.active)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_assessment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_code: Mapped[HoldCancelCode | None] = enum_col(HoldCancelCode, nullable=True)
    cancel_reason_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    work_during_hold: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class FitnessReferral(Numbered, Audited, Base):
    __tablename__ = "fitness_referrals"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_fitness_referral_worker", "worker_id", "status"),
    )

    referral_no: Mapped[str] = mapped_column(String(40), unique=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    reason: Mapped[ReferralReason] = enum_col(ReferralReason)
    note_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    remove_from_work: Mapped[bool] = mapped_column(Boolean, default=False)
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ReferralStatus] = enum_col(ReferralStatus, default=ReferralStatus.open)
    hold_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    source_cert_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- settings (§3.12) and imports (§3.11) --------------------------------------------------------


class MedicalSettings(Base):
    """§3.12 (one row per project, created with the defaults on first use)."""

    __tablename__ = "project_medical_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    medical_register_from: Mapped[date | None] = mapped_column(Date)
    fitness_validity_months: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    medical_hook_transition_days: Mapped[int] = mapped_column(Integer, default=30)
    medical_hook_critical_transition_days: Mapped[int] = mapped_column(Integer, default=7)
    medical_hook_critical_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    unverified_fitness_acceptance_hours: Mapped[int] = mapped_column(Integer, default=0)
    fitness_verification_due_days: Mapped[int] = mapped_column(Integer, default=3)
    referral_assessment_hours: Mapped[int] = mapped_column(Integer, default=24)
    signoff_due_hours: Mapped[int] = mapped_column(Integer, default=72)
    assessment_backdate_max_days: Mapped[int] = mapped_column(Integer, default=7)
    restriction_review_max_days: Mapped[int] = mapped_column(Integer, default=90)
    unfit_review_max_days: Mapped[int] = mapped_column(Integer, default=90)
    medical_line_max_due_days: Mapped[int] = mapped_column(Integer, default=30)
    rtw_hold_case_categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    heat_illness_natures: Mapped[list[str]] = mapped_column(STRS, default=list)
    exposure_group_trade_defaults: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict)
    medical_compliance_warning_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal("98.0")
    )
    health_cell_min: Mapped[int] = mapped_column(Integer, default=5)
    fitness_scan_retention_months: Mapped[int] = mapped_column(Integer, default=12)
    fitness_record_retention_years: Mapped[int] = mapped_column(Integer, default=10)
    surveillance_record_retention_years: Mapped[int] = mapped_column(Integer, default=30)
    worker_purpose_notice_version: Mapped[str] = mapped_column(
        String(40), default="WPN-MED-0.1 (draft)"
    )
    alert_schedule_long_days: Mapped[list[int]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class MedicalImportBatch(UUIDPk, Base):
    __tablename__ = "medical_import_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    source: Mapped[MedicalImportSource] = enum_col(MedicalImportSource)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("medical_providers.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    evidence_file_name: Mapped[str | None] = mapped_column(String(255))
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_sender: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[MedicalImportStatus] = enum_col(MedicalImportStatus)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    file_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # parsed rows, encrypted as one blob (sensitive, IM6-4); cleared at commit / discard / expiry
    rows_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    committed_assessment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
