"""Phase 2 tables (spec 2-access-permits §3): worker register, deployments, inductions, zone
access profiles, airport passes, ADPs, offences, vehicles, AVPs, NOTAM and obstacle clearances,
work-area access permits, ops events, credential lifecycle, QR tokens, gates and the gate log."""

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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access_enums import (
    AreaCategory,
    CardColour,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CrewMemberStatus,
    CrewRole,
    CustodyStatus,
    DeploymentStatus,
    GateDirection,
    GateResult,
    GateStatus,
    GateSubjectKind,
    GateType,
    InductionResult,
    InductionStatus,
    InductionType,
    InspectionResult,
    LicenceClass,
    LicenceIssuer,
    LimitingFactor,
    NotamStatus,
    NotamType,
    ObstacleDecision,
    ObstacleEquipmentType,
    ObstacleStatus,
    OffenceStatus,
    OlsSurface,
    OpsEventSource,
    OpsEventType,
    PairingState,
    PairingWaitingFor,
    PassApplicationStatus,
    PassApplicationType,
    PassAreaKind,
    PlateType,
    PracticalTestResult,
    QrKind,
    QrTokenStatus,
    SuspendedContractorGateMode,
    SuspensionState,
    ValidityStatus,
    VehicleCategory,
    VehicleOwnerType,
    VehicleStatus,
    WapStatus,
    WorkerIdType,
    WorkerLanguage,
    WorkerPersonType,
    WorkerStatus,
)
from app.core.clock import now
from app.core.hse_enums import Trade
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col

UUIDS = ARRAY(PG_UUID(as_uuid=True))
STRS = ARRAY(String(40))
INTS = ARRAY(Integer)


class Audited(UUIDPk, TimestampMixin):
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class Numbered:
    """Per-project, per-year sequence behind `<PREFIX>-<project>-<yyyy>-<nnnn>` numbers."""

    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)


class CredentialFields:
    """Validity and custody of passes, ADPs and AVPs (§4.5, §4.9, §6.2)."""

    validity_status: Mapped[ValidityStatus] = enum_col(
        ValidityStatus, default=ValidityStatus.active
    )
    effective_valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[LimitingFactor | None] = enum_col(LimitingFactor, nullable=True)
    custody_status: Mapped[CustodyStatus | None] = enum_col(CustodyStatus, nullable=True)
    return_due_on: Mapped[date | None] = mapped_column(Date)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lost_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authority_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[CredentialReason | None] = enum_col(CredentialReason, nullable=True)
    expired_on: Mapped[date | None] = mapped_column(Date)


# ---- settings ------------------------------------------------------------------------------------


class AccessSettings(Base):
    """§3.22 (one row per project, created with the defaults on first use)."""

    __tablename__ = "project_access_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    induction_pass_mark_pct: Mapped[int] = mapped_column(Integer, default=80)
    induction_retest_wait_hours: Mapped[int] = mapped_column(Integer, default=0)
    induction_max_attempts_30d: Mapped[int] = mapped_column(Integer, default=3)
    reinduction_absence_days: Mapped[int | None] = mapped_column(Integer)
    reinduction_grace_days: Mapped[int] = mapped_column(Integer, default=30)
    id_expiry_blocks_access: Mapped[bool] = mapped_column(Boolean, default=True)
    pass_max_validity_months: Mapped[int] = mapped_column(Integer, default=24)
    temp_escorted_pass_max_days: Mapped[int] = mapped_column(Integer, default=30)
    visitor_pass_max_days: Mapped[int] = mapped_column(Integer, default=1)
    bg_recheck_months: Mapped[int] = mapped_column(Integer, default=24)
    application_stale_days: Mapped[int] = mapped_column(Integer, default=30)
    id_copy_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    pass_return_days: Mapped[int] = mapped_column(Integer, default=3)
    lost_report_hours: Mapped[int] = mapped_column(Integer, default=24)
    escort_ratio_max_apron: Mapped[int] = mapped_column(Integer, default=5)
    escort_ratio_max_manoeuvring: Mapped[int] = mapped_column(Integer, default=2)
    escort_ratio_max_other: Mapped[int] = mapped_column(Integer, default=5)
    vehicle_escort_ratio_max_apron: Mapped[int] = mapped_column(Integer, default=3)
    vehicle_escort_ratio_max_manoeuvring: Mapped[int] = mapped_column(Integer, default=1)
    escort_pairing_seconds: Mapped[int] = mapped_column(Integer, default=120)
    adp_validity_months: Mapped[int] = mapped_column(Integer, default=24)
    adp_theory_pass_pct: Mapped[int] = mapped_column(Integer, default=80)
    adp_points_threshold: Mapped[int] = mapped_column(Integer, default=12)
    adp_points_window_days: Mapped[int] = mapped_column(Integer, default=365)
    adp_suspension_days: Mapped[int] = mapped_column(Integer, default=30)
    adp_revoke_after_suspensions: Mapped[int] = mapped_column(Integer, default=2)
    adp_revoke_after_suspensions_window_days: Mapped[int] = mapped_column(Integer, default=730)
    avp_validity_months: Mapped[int] = mapped_column(Integer, default=12)
    wap_max_days: Mapped[int] = mapped_column(Integer, default=30)
    wap_exit_grace_minutes: Mapped[int] = mapped_column(Integer, default=15)
    notam_request_lead_days: Mapped[int] = mapped_column(Integer, default=7)
    airac_lead_days: Mapped[int] = mapped_column(Integer, default=42)
    obstacle_clearance_lead_days: Mapped[int] = mapped_column(Integer, default=30)
    obstacle_height_threshold_m: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("45.00")
    )
    ols_buffer_m: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("3.00"))
    raised_suspension_max_hours: Mapped[int] = mapped_column(Integer, default=72)
    suspended_contractor_gate: Mapped[SuspendedContractorGateMode] = enum_col(
        SuspendedContractorGateMode, default=SuspendedContractorGateMode.deny
    )
    hook_policy: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    alert_schedule_long_days: Mapped[list[int]] = mapped_column(
        INTS, default=lambda: [30, 14, 7, 0]
    )
    alert_schedule_short_hours: Mapped[list[int]] = mapped_column(INTS, default=lambda: [72, 24, 0])
    gate_log_retention_months: Mapped[int] = mapped_column(Integer, default=12)
    worker_retention_years: Mapped[int] = mapped_column(Integer, default=5)
    induction_coverage_warning_pct: Mapped[int] = mapped_column(Integer, default=98)
    hook_requirements_by_adp_category: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    hook_requirements_by_vehicle_category: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )
    hook_requirements_by_crew_role: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


# ---- workers and deployments ---------------------------------------------------------------------


class Worker(Audited, Base):
    """§3.1 (org-wide). id_number is AES-GCM encrypted; id_number_bidx is a keyed HMAC blind
    index (separate key) used for exact-match lookup and uniqueness (WK-2, WK-3)."""

    __tablename__ = "workers"

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    worker_no: Mapped[str] = mapped_column(String(12), unique=True)
    person_type: Mapped[WorkerPersonType] = enum_col(WorkerPersonType)
    full_name_en: Mapped[str] = mapped_column(String(120))
    full_name_ar: Mapped[str] = mapped_column(String(120))
    id_type: Mapped[WorkerIdType | None] = enum_col(WorkerIdType, nullable=True)
    id_number_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    id_number_bidx: Mapped[str | None] = mapped_column(String(64), unique=True)
    id_number_masked: Mapped[str | None] = mapped_column(String(20))
    passport_country: Mapped[str | None] = mapped_column(String(2))
    id_expiry_date: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(2))
    adult_attestation: Mapped[bool] = mapped_column(Boolean, default=True)
    primary_language: Mapped[WorkerLanguage] = enum_col(WorkerLanguage)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[WorkerStatus] = enum_col(WorkerStatus, default=WorkerStatus.active)
    ban_reason: Mapped[str | None] = mapped_column(String(500))
    inactive_since: Mapped[date | None] = mapped_column(Date)
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_text: Mapped[str] = mapped_column(Text, default="")


class WorkerIdHistory(UUIDPk, Base):
    """WK-9: previous ID values, encrypted (P2-2); deleted at anonymisation (P2-7)."""

    __tablename__ = "worker_id_history"

    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    id_type: Mapped[WorkerIdType] = enum_col(WorkerIdType)
    id_number_enc: Mapped[bytes] = mapped_column(LargeBinary)
    id_number_masked: Mapped[str] = mapped_column(String(20))
    passport_country: Mapped[str | None] = mapped_column(String(2))
    replaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    replaced_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Deployment(Audited, Base):
    """§3.2 worker on a project."""

    __tablename__ = "worker_deployments"
    __table_args__ = (
        Index(
            "uq_deployment_open",
            "worker_id",
            "project_id",
            unique=True,
            postgresql_where=text("status <> 'demobilised'"),
        ),
        Index("ix_deployment_project_status", "project_id", "status"),
    )

    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    employee_no: Mapped[str | None] = mapped_column(String(20))
    trade: Mapped[Trade] = enum_col(Trade)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    mobilised_on: Mapped[date] = mapped_column(Date)
    planned_demob_on: Mapped[date | None] = mapped_column(Date)
    demobilised_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[DeploymentStatus] = enum_col(
        DeploymentStatus, default=DeploymentStatus.pending_induction
    )
    inducted_on: Mapped[date | None] = mapped_column(Date)  # pending → mobilised (IN-1)
    access_card_issued_on: Mapped[date | None] = mapped_column(Date)
    reissue_count: Mapped[int] = mapped_column(Integer, default=0)
    passport_alerts_sent: Mapped[list[int]] = mapped_column(INTS, default=list)


class QrToken(UUIDPk, Base):
    """§3.20: opaque token printed as `HSE2:<kind>:<token>`; no personal data."""

    __tablename__ = "qr_tokens"
    __table_args__ = (Index("ix_qr_subject", "subject_id", "status"),)

    token: Mapped[str] = mapped_column(String(22), unique=True)
    kind: Mapped[QrKind] = enum_col(QrKind)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    printed_ref: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[QrTokenStatus] = enum_col(QrTokenStatus, default=QrTokenStatus.active)
    lost: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---- inductions ----------------------------------------------------------------------------------


class InductionCourse(Audited, Base):
    """§3.3."""

    __tablename__ = "induction_courses"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(10))
    induction_type: Mapped[InductionType] = enum_col(InductionType)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    version: Mapped[str] = mapped_column(String(10))
    version_published_on: Mapped[date | None] = mapped_column(Date)
    requires_reinduction: Mapped[bool] = mapped_column(Boolean, default=False)
    validity_months: Mapped[int | None] = mapped_column(Integer)
    validity_days: Mapped[int | None] = mapped_column(Integer)
    min_duration_minutes: Mapped[int] = mapped_column(Integer)
    test_required: Mapped[bool] = mapped_column(Boolean)
    pass_mark_pct: Mapped[int | None] = mapped_column(Integer)
    languages_offered: Mapped[list[str]] = mapped_column(STRS, default=list)
    prerequisite_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    delivered_by_roles: Mapped[list[str]] = mapped_column(STRS, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InductionRecord(Audited, Numbered, Base):
    """§3.4."""

    __tablename__ = "induction_records"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_induction_worker_course", "worker_id", "course_id"),
        Index("ix_induction_project_delivered", "project_id", "delivered_at"),
        Index(
            "uq_helmet_sticker",
            "project_id",
            "helmet_sticker_no",
            unique=True,
            postgresql_where=text("helmet_sticker_no IS NOT NULL"),
        ),
    )

    induction_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("induction_courses.id"))
    induction_type: Mapped[InductionType] = enum_col(InductionType)
    course_version: Mapped[str] = mapped_column(String(10))
    session_ref: Mapped[str | None] = mapped_column(String(30))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_on: Mapped[date] = mapped_column(Date)  # local date of delivered_at
    delivered_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    delivery_language: Mapped[WorkerLanguage] = enum_col(WorkerLanguage)
    interpreter_used: Mapped[bool] = mapped_column(Boolean, default=False)
    language_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    test_score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    result: Mapped[InductionResult] = enum_col(InductionResult)
    privacy_notice_version: Mapped[str] = mapped_column(String(20))
    signature_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    reinduction_due_on: Mapped[date | None] = mapped_column(Date)
    helmet_sticker_no: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[InductionStatus] = enum_col(InductionStatus)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InductionRetrainingNote(UUIDPk, Base):
    """IN-5 re-training note (lets a worker attempt again)."""

    __tablename__ = "induction_retraining_notes"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("induction_courses.id"))
    note: Mapped[str] = mapped_column(String(500))
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ZoneAccessProfile(Base):
    """§3.5 (1:1 with zone; created with ZP-1 defaults)."""

    __tablename__ = "zone_access_profiles"

    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    required_inductions: Mapped[list[str]] = mapped_column(STRS, default=list)
    airport_pass_area_code: Mapped[str | None] = mapped_column(String(4))
    access_permit_required: Mapped[bool] = mapped_column(Boolean, default=False)
    adp_category_required: Mapped[AreaCategory | None] = enum_col(AreaCategory, nullable=True)
    avp_area_required: Mapped[AreaCategory | None] = enum_col(AreaCategory, nullable=True)
    escort_ratio_max: Mapped[int | None] = mapped_column(Integer)
    lvp_withdrawal_required: Mapped[bool] = mapped_column(Boolean, default=False)
    ils_outage_notam_required: Mapped[bool] = mapped_column(Boolean, default=False)
    hook_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


# ---- airport passes ------------------------------------------------------------------------------


class PassCategory(UUIDPk, Base):
    """§3.6 AP-CAT."""

    __tablename__ = "pass_categories"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str] = mapped_column(String(8))
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    escorted: Mapped[bool] = mapped_column(Boolean)
    background_check_required: Mapped[bool] = mapped_column(Boolean)
    max_validity_days: Mapped[int] = mapped_column(Integer)
    card_colour: Mapped[CardColour] = enum_col(CardColour)
    allows_adp: Mapped[bool] = mapped_column(Boolean)
    hook_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PassArea(UUIDPk, Base):
    """§3.7 AP-AREA."""

    __tablename__ = "pass_areas"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str] = mapped_column(String(4))
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    colour: Mapped[CardColour] = enum_col(CardColour)
    area_kind: Mapped[PassAreaKind] = enum_col(PassAreaKind)
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PassApplication(Audited, Numbered, Base):
    """§3.8. Background-check status and dates are encrypted (P2-2) in `background_enc`."""

    __tablename__ = "pass_applications"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_pass_application_worker", "worker_id", "project_id"),
    )

    application_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    application_type: Mapped[PassApplicationType] = enum_col(PassApplicationType)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    sponsor_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    sponsor_letter_ref: Mapped[str] = mapped_column(String(40))
    client_sponsor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    pass_category: Mapped[str] = mapped_column(String(8))
    requested_area_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    requested_valid_until: Mapped[date] = mapped_column(Date)
    justification: Mapped[str] = mapped_column(String(500))
    prerequisite_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lodged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authority_ref: Mapped[str | None] = mapped_column(String(40))
    background_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    outcome_note: Mapped[str | None] = mapped_column(String(300))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_pass_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    id_copy_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_alerted_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PassApplicationStatus] = enum_col(
        PassApplicationStatus, default=PassApplicationStatus.draft
    )


class AirportPass(Audited, CredentialFields, Base):
    """§3.9 issued credential."""

    __tablename__ = "airport_passes"
    __table_args__ = (
        UniqueConstraint("project_id", "pass_no"),
        Index("ix_airport_pass_worker", "worker_id", "project_id"),
    )

    pass_no: Mapped[str] = mapped_column(String(30))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pass_applications.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    pass_category: Mapped[str] = mapped_column(String(8))
    area_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    card_colour: Mapped[CardColour] = enum_col(CardColour)
    escorted: Mapped[bool] = mapped_column(Boolean)
    issued_on: Mapped[date] = mapped_column(Date)
    card_expiry_date: Mapped[date] = mapped_column(Date)


# ---- ADP and offences ----------------------------------------------------------------------------


class Adp(Audited, CredentialFields, Base):
    """§3.10. `validity_status = pending` is the application (DECISIONS #30)."""

    __tablename__ = "airside_driving_permits"
    __table_args__ = (
        Index(
            "uq_adp_no",
            "project_id",
            "adp_no",
            unique=True,
            postgresql_where=text("adp_no IS NOT NULL"),
        ),
        Index("ix_adp_worker", "worker_id", "project_id"),
    )

    adp_no: Mapped[str | None] = mapped_column(String(30))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    category: Mapped[AreaCategory] = enum_col(AreaCategory)
    vehicle_classes: Mapped[list[str]] = mapped_column(STRS, default=list)
    licence_issuer: Mapped[LicenceIssuer] = enum_col(LicenceIssuer)
    licence_class: Mapped[LicenceClass] = enum_col(LicenceClass)
    licence_expiry_date: Mapped[date] = mapped_column(Date)
    theory_test_date: Mapped[date | None] = mapped_column(Date)
    theory_score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    practical_test_date: Mapped[date | None] = mapped_column(Date)
    practical_result: Mapped[PracticalTestResult | None] = enum_col(
        PracticalTestResult, nullable=True
    )
    practical_examiner: Mapped[str | None] = mapped_column(String(120))
    practical_included_manoeuvring: Mapped[bool | None] = mapped_column(Boolean)
    rtf_competence: Mapped[bool | None] = mapped_column(Boolean)
    issued_on: Mapped[date | None] = mapped_column(Date)
    own_valid_until: Mapped[date | None] = mapped_column(Date)
    pass_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("airport_passes.id"))


class Offence(Audited, Numbered, Base):
    """§3.11."""

    __tablename__ = "airside_offences"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_offence_worker_date", "worker_id", "offence_date"),
    )

    offence_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    adp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("airside_driving_permits.id"))
    offence_code: Mapped[str] = mapped_column(String(10))
    points: Mapped[int] = mapped_column(Integer)
    immediate_suspension: Mapped[bool] = mapped_column(Boolean, default=False)
    offence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    offence_date: Mapped[date] = mapped_column(Date)
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    reported_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[OffenceStatus] = enum_col(OffenceStatus, default=OffenceStatus.recorded)
    resulting_actions: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- vehicles and AVPs ---------------------------------------------------------------------------


class Vehicle(Audited, Base):
    """§3.12."""

    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("project_id", "seq", name="uq_vehicles_project_seq"),
        UniqueConstraint("project_id", "serial_or_vin", name="uq_vehicles_project_vin"),
        Index(
            "uq_vehicle_plate",
            "plate_letters_ar",
            "plate_digits",
            unique=True,
            postgresql_where=text("plate_digits IS NOT NULL AND status <> 'withdrawn'"),
        ),
    )

    seq: Mapped[int] = mapped_column(Integer)
    vehicle_no: Mapped[str] = mapped_column(String(12))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    owner_type: Mapped[VehicleOwnerType] = enum_col(VehicleOwnerType)
    category: Mapped[VehicleCategory] = enum_col(VehicleCategory)
    plate_type: Mapped[PlateType] = enum_col(PlateType)
    plate_letters_ar: Mapped[str | None] = mapped_column(String(5))
    plate_letters_en: Mapped[str | None] = mapped_column(String(3))
    plate_digits: Mapped[str | None] = mapped_column(String(4))
    fleet_no: Mapped[str] = mapped_column(String(20))
    serial_or_vin: Mapped[str] = mapped_column(String(30))
    make_model: Mapped[str] = mapped_column(String(80))
    year_built: Mapped[int] = mapped_column(Integer)
    colour: Mapped[str] = mapped_column(String(30))
    travel_height_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    max_working_height_m_agl: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    istimara_expiry: Mapped[date | None] = mapped_column(Date)
    insurance_policy_no: Mapped[str] = mapped_column(String(40))
    insurance_expiry: Mapped[date] = mapped_column(Date)
    mvpi_expiry: Mapped[date | None] = mapped_column(Date)
    status: Mapped[VehicleStatus] = enum_col(VehicleStatus, default=VehicleStatus.active)


class Avp(Audited, CredentialFields, Base):
    """§3.13. `validity_status = pending` is the application (DECISIONS #30)."""

    __tablename__ = "airside_vehicle_permits"
    __table_args__ = (
        Index(
            "uq_avp_no",
            "project_id",
            "avp_no",
            unique=True,
            postgresql_where=text("avp_no IS NOT NULL"),
        ),
    )

    avp_no: Mapped[str | None] = mapped_column(String(30))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    areas: Mapped[list[str]] = mapped_column(STRS, default=list)
    inspection_date: Mapped[date | None] = mapped_column(Date)
    inspector: Mapped[str | None] = mapped_column(String(120))
    inspection_result: Mapped[InspectionResult | None] = enum_col(InspectionResult, nullable=True)
    checklist: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    sticker_no: Mapped[str | None] = mapped_column(String(20))
    issued_on: Mapped[date | None] = mapped_column(Date)
    own_valid_until: Mapped[date | None] = mapped_column(Date)


# ---- NOTAM and obstacle clearances ---------------------------------------------------------------


class NotamRequest(Audited, Numbered, Base):
    """§3.14."""

    __tablename__ = "notam_requests"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index(
            "uq_notam_number",
            "project_id",
            "notam_number",
            unique=True,
            postgresql_where=text("notam_number IS NOT NULL"),
        ),
    )

    ntm_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    works_impact: Mapped[list[str]] = mapped_column(STRS, default=list)
    description_en: Mapped[str] = mapped_column(String(1000))
    description_ar: Mapped[str] = mapped_column(String(1000))
    requested_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schedule_text: Mapped[str | None] = mapped_column(String(200))
    submitted_to_ops_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_request: Mapped[bool] = mapped_column(Boolean, default=False)
    late_justification: Mapped[str | None] = mapped_column(String(500))
    notam_number: Mapped[str | None] = mapped_column(String(12))
    notam_type: Mapped[NotamType | None] = enum_col(NotamType, nullable=True)
    effective_from_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_e_text: Mapped[str | None] = mapped_column(String(2000))
    replaces_ntm_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[NotamStatus] = enum_col(NotamStatus, default=NotamStatus.draft)


class ObstacleClearance(Audited, Numbered, Base):
    """§3.15."""

    __tablename__ = "obstacle_clearances"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    obs_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    # v1.2 (4-third-party-cert CF-4): Phase 4 equipment item whose height changes re-check it
    equipment_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    equipment_desc: Mapped[str | None] = mapped_column(String(150))
    equipment_type: Mapped[ObstacleEquipmentType] = enum_col(ObstacleEquipmentType)
    location_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    location_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    location_desc: Mapped[str] = mapped_column(String(150))
    ground_elevation_m_amsl: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    max_height_m_agl: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    ols_surface: Mapped[OlsSurface | None] = enum_col(OlsSurface, nullable=True)
    ols_limit_m_amsl: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    ols_source_ref: Mapped[str | None] = mapped_column(String(40))
    clearance_reasons: Mapped[list[str]] = mapped_column(STRS, default=list)
    top_elevation_m_amsl: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    penetration_m: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal(0))
    requested_from: Mapped[date] = mapped_column(Date)
    requested_to: Mapped[date] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_request: Mapped[bool] = mapped_column(Boolean, default=False)
    late_justification: Mapped[str | None] = mapped_column(String(500))
    authority_ref: Mapped[str | None] = mapped_column(String(40))
    decision: Mapped[ObstacleDecision | None] = enum_col(ObstacleDecision, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_max_height_m_agl: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    approved_top_m_amsl: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    conditions: Mapped[list[str]] = mapped_column(STRS, default=list)
    conditions_text: Mapped[str | None] = mapped_column(String(1000))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    linked_ntm_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    system_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[ObstacleStatus] = enum_col(ObstacleStatus, default=ObstacleStatus.draft)


# ---- work-area access permits and ops events -----------------------------------------------------


class Wap(Audited, Numbered, Base):
    """§3.16. A revision (WA-14) is a row with `revision_of_id`; on approval its changes are
    applied to the original WAP and the revision row is closed."""

    __tablename__ = "work_area_permits"
    __table_args__ = (Index("ix_wap_project_status", "project_id", "status"),)

    wap_no: Mapped[str] = mapped_column(String(40), index=True)
    revision_no: Mapped[int] = mapped_column(Integer, default=0)
    revision_of_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    revision_reason: Mapped[str | None] = mapped_column(String(500))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    supervisor_worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    scope_en: Mapped[str] = mapped_column(String(500))
    scope_ar: Mapped[str] = mapped_column(String(500))
    works_safety_plan_ref: Mapped[str | None] = mapped_column(String(40))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    operator_permit_ref: Mapped[str | None] = mapped_column(String(40))
    linked_ntm_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    linked_obs_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    fod_handback_required: Mapped[bool] = mapped_column(Boolean, default=False)
    fod_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    conditions_en: Mapped[str | None] = mapped_column(String(1000))
    conditions_ar: Mapped[str | None] = mapped_column(String(1000))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    suspension_reason: Mapped[CredentialReason | None] = enum_col(CredentialReason, nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[WapStatus] = enum_col(WapStatus, default=WapStatus.draft)


class WapCrew(UUIDPk, Base):
    __tablename__ = "wap_crew"
    __table_args__ = (Index("ix_wap_crew_worker", "worker_id"),)

    wap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_area_permits.id"), index=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    crew_role: Mapped[CrewRole] = enum_col(CrewRole)
    escort_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    status: Mapped[CrewMemberStatus] = enum_col(CrewMemberStatus, default=CrewMemberStatus.included)
    exclusion_reasons: Mapped[list[str]] = mapped_column(STRS, default=list)
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)
    eligible_now: Mapped[bool | None] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WapVehicle(UUIDPk, Base):
    __tablename__ = "wap_vehicles"

    wap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_area_permits.id"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), index=True)
    escort_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    height_limited_to_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    status: Mapped[CrewMemberStatus] = enum_col(CrewMemberStatus, default=CrewMemberStatus.included)
    exclusion_reasons: Mapped[list[str]] = mapped_column(STRS, default=list)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpsEvent(Audited, Numbered, Base):
    """§3.17 operational suspension event."""

    __tablename__ = "ops_events"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    ops_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    type: Mapped[OpsEventType] = enum_col(OpsEventType)
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    default_zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    source: Mapped[OpsEventSource] = enum_col(OpsEventSource)
    source_ref: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    suspended_wap_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)


# ---- credential lifecycle ------------------------------------------------------------------------


class CredentialEvent(UUIDPk, Base):
    """§3.18 status event log (append-only)."""

    __tablename__ = "credential_events"
    __table_args__ = (
        Index("ix_credential_event_subject", "credential_kind", "credential_id"),
        Index("ix_credential_event_project_time", "project_id", "occurred_at"),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    credential_kind: Mapped[CredentialKind] = enum_col(CredentialKind)
    credential_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    action: Mapped[CredentialAction] = enum_col(CredentialAction)
    reason_code: Mapped[CredentialReason] = enum_col(CredentialReason)
    reason_text: Mapped[str | None] = mapped_column(String(500))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class CredentialSuspension(UUIDPk, Base):
    """Open/closed suspensions on a credential (LC-3, LC-6, DP-8). A credential is active only
    when none is open."""

    __tablename__ = "credential_suspensions"
    __table_args__ = (Index("ix_credential_susp_subject", "credential_kind", "credential_id"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    credential_kind: Mapped[CredentialKind] = enum_col(CredentialKind)
    credential_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    state: Mapped[SuspensionState] = enum_col(SuspensionState)
    reason_code: Mapped[CredentialReason] = enum_col(CredentialReason)
    reason_text: Mapped[str | None] = mapped_column(String(500))
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_end: Mapped[date | None] = mapped_column(Date)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- gates and the gate log ----------------------------------------------------------------------


class Gate(Audited, Base):
    """§3.19."""

    __tablename__ = "gates"
    __table_args__ = (UniqueConstraint("project_id", "gate_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    gate_code: Mapped[str] = mapped_column(String(12))
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    protected_zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    gate_type: Mapped[GateType] = enum_col(GateType)
    status: Mapped[GateStatus] = enum_col(GateStatus, default=GateStatus.active)


class GateDevice(UUIDPk, Base):
    __tablename__ = "gate_devices"

    gate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gates.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class GateDeviceSession(UUIDPk, Base):
    """GC-1 device session (12 h idle)."""

    __tablename__ = "gate_device_sessions"

    device_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey("gate_devices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GatePairing(UUIDPk, Base):
    """GC-8/GC-9 escort, driver and escort-vehicle pairings (one device, timed)."""

    __tablename__ = "gate_pairings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    gate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gates.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    device_pk: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gate_devices.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    waiting_for: Mapped[PairingWaitingFor] = enum_col(PairingWaitingFor)
    state: Mapped[PairingState] = enum_col(PairingState, default=PairingState.waiting)
    started_check_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    # subjects collected so far: [{"kind": person|vehicle, "id": deployment/vehicle id,
    # "role": escorted|escort|vehicle|escort_vehicle|driver, "check_id": ..., "warn": [...]}]
    subjects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escort_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("worker_deployments.id")
    )
    escort_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    escort_day: Mapped[date | None] = mapped_column(Date)


class GateCheck(UUIDPk, Base):
    """GC-12 immutable gate-log row. `final` = the row counts as one check (KA-3): pending
    rows of a pairing are not final; the pairing writes the final row per subject."""

    __tablename__ = "gate_checks"
    __table_args__ = (
        Index("ix_gate_check_project_time", "project_id", "occurred_at"),
        Index("ix_gate_check_deployment", "deployment_id", "occurred_at"),
        Index("ix_gate_check_pairing", "pairing_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    local_date: Mapped[date] = mapped_column(Date)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    gate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gates.id"))
    device_pk: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gate_devices.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    direction: Mapped[GateDirection] = enum_col(GateDirection)
    qr_kind: Mapped[QrKind | None] = enum_col(QrKind, nullable=True)
    subject_kind: Mapped[GateSubjectKind] = enum_col(GateSubjectKind)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    wap_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # v1.2 GE-6: EQ sticker checks (subject_kind equipment_deployment)
    equipment_deployment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    subject_ref: Mapped[str | None] = mapped_column(String(60))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    result: Mapped[GateResult] = enum_col(GateResult)
    reason_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    first_deny_reason: Mapped[str | None] = mapped_column(String(40))
    final: Mapped[bool] = mapped_column(Boolean, default=True)
    pairing_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    late_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    admitted_despite_denial: Mapped[bool] = mapped_column(Boolean, default=False)
    admitted_reason: Mapped[str | None] = mapped_column(String(500))
    admitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
