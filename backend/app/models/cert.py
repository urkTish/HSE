"""Phase 4 tables (spec 4-third-party-cert §3): TPI organisations, accreditations and client
approvals; equipment register, deployments, certificates and lines, configuration events,
status / blacklist events; scaffolds and inspections; personnel certificates; verification
records; defects; certification bans; hook policy state; settings; certificate types; import
batches."""

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
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access_enums import HookKind
from app.core.cert_enums import (
    AccreditationBody,
    AccreditationStandard,
    BanReason,
    BanStatus,
    CertificateStatus,
    CertImportSource,
    CertImportStatus,
    CertImportTemplate,
    CertInspectionType,
    CertKind,
    CertLevel,
    CertLimitingFactor,
    CertSource,
    CertStatusReason,
    CertVerificationMethod,
    ClientApprovalStatus,
    ConfigurationEventType,
    DefectCategory,
    DefectSource,
    DefectStatus,
    EquipmentBlacklistReason,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    EquipmentSubtype,
    HookStage,
    IdMatchResult,
    LiftingGearColour,
    LineResult,
    NameMatch,
    ReinspectionReason,
    ScaffoldInspectionResult,
    ScaffoldInspectionType,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ScaffoldType,
    ServiceStatus,
    ServiceStatusReason,
    TpiBlacklistScope,
    TpiStatus,
    VerificationOutcome,
    VerificationStatus,
)
from app.core.clock import now
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col

# ---- TPI organisations (§3.1-§3.3) ---------------------------------------------------------------


class Tpi(Audited, Base):
    __tablename__ = "tpis"

    tpi_code: Mapped[str] = mapped_column(String(12), unique=True)
    legal_name_en: Mapped[str] = mapped_column(String(200))
    legal_name_ar: Mapped[str] = mapped_column(String(200))
    name_norm_en: Mapped[str] = mapped_column(String(200), unique=True)
    name_norm_ar: Mapped[str] = mapped_column(String(200), unique=True)
    kinds: Mapped[list[str]] = mapped_column(STRS, default=list)
    country: Mapped[str] = mapped_column(String(2))
    cr_number: Mapped[str | None] = mapped_column(String(10))
    foreign_reg_no: Mapped[str | None] = mapped_column(String(30))
    verification_portal_url: Mapped[str | None] = mapped_column(String(300))
    verification_domains: Mapped[list[str]] = mapped_column(STRS, default=list)
    verification_email: Mapped[str | None] = mapped_column(String(254))
    verification_phone: Mapped[str | None] = mapped_column(String(20))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_mobile: Mapped[str | None] = mapped_column(String(20))
    affiliated_contractor_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[TpiStatus] = enum_col(TpiStatus, default=TpiStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    blacklist_scope: Mapped[TpiBlacklistScope | None] = enum_col(TpiBlacklistScope, nullable=True)
    blacklist_from: Mapped[date | None] = mapped_column(Date)
    blacklisted_on: Mapped[date | None] = mapped_column(Date)
    # BL-6: [{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD" | null}] — certificates inspected / issued
    # on a date inside a period are refused (TP-4).
    suspension_periods: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TpiAccreditation(Audited, Base):
    __tablename__ = "tpi_accreditations"
    __table_args__ = (UniqueConstraint("accreditation_body", "accreditation_no"),)

    tpi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tpis.id"), index=True)
    accreditation_body: Mapped[AccreditationBody] = enum_col(AccreditationBody)
    standard: Mapped[AccreditationStandard] = enum_col(AccreditationStandard)
    accreditation_no: Mapped[str] = mapped_column(String(40))
    scope_categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    scope_cert_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    certificate_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    register_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    register_checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    register_check_note: Mapped[str | None] = mapped_column(String(300))


class TpiClientApproval(Audited, Base):
    __tablename__ = "tpi_client_approvals"
    __table_args__ = (UniqueConstraint("project_id", "tpi_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    tpi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tpis.id"))
    approval_ref: Mapped[str] = mapped_column(String(40))
    scope_categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    scope_cert_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[ClientApprovalStatus] = enum_col(
        ClientApprovalStatus, default=ClientApprovalStatus.active
    )


# ---- equipment register (§3.4, §3.5, §3.7, §3.13) ------------------------------------------------


class EquipmentItem(Audited, Base):
    __tablename__ = "equipment_items"
    __table_args__ = (UniqueConstraint("manufacturer_norm", "serial_norm"),)

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    equipment_no: Mapped[str] = mapped_column(String(12), unique=True)
    category: Mapped[EquipmentCertCategory] = enum_col(EquipmentCertCategory)
    subtype: Mapped[EquipmentSubtype | None] = enum_col(EquipmentSubtype, nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(80))
    manufacturer_norm: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    serial_no: Mapped[str] = mapped_column(String(40))
    serial_norm: Mapped[str] = mapped_column(String(40), index=True)
    year_of_manufacture: Mapped[int] = mapped_column(Integer)
    owner_contractor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contractors.id"))
    hired_from: Mapped[str | None] = mapped_column(String(120))
    owner_fleet_no: Mapped[str | None] = mapped_column(String(20))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"), unique=True)
    rated_capacity_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    max_radius_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    max_height_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    persons_capacity: Mapped[int | None] = mapped_column(Integer)
    pressure: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lifting_duty: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_devices: Mapped[list[str]] = mapped_column(STRS, default=list)
    documents: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    service_status: Mapped[ServiceStatus] = enum_col(
        ServiceStatus, default=ServiceStatus.awaiting_certificate
    )
    service_status_reason: Mapped[ServiceStatusReason | None] = enum_col(
        ServiceStatusReason, nullable=True
    )
    service_status_text: Mapped[str | None] = mapped_column(String(500))
    service_status_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # DF-6: who recorded the last rectification / tag-out (return-to-service SoD)
    tagged_out_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class EquipmentStatusEvent(UUIDPk, Base):
    __tablename__ = "equipment_status_events"
    __table_args__ = (Index("ix_eq_status_event_item", "equipment_id", "occurred_at"),)

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_items.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    from_status: Mapped[ServiceStatus | None] = enum_col(ServiceStatus, nullable=True)
    to_status: Mapped[ServiceStatus] = enum_col(ServiceStatus)
    reason: Mapped[ServiceStatusReason | None] = enum_col(ServiceStatusReason, nullable=True)
    text: Mapped[str | None] = mapped_column(String(500))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ref: Mapped[str | None] = mapped_column(String(60))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class EquipmentBlacklistEvent(Audited, Base):
    """§3.13."""

    __tablename__ = "equipment_blacklist_events"

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_items.id"), index=True)
    reason_code: Mapped[EquipmentBlacklistReason] = enum_col(EquipmentBlacklistReason)
    reason_text: Mapped[str] = mapped_column(String(500))
    from_date: Mapped[date] = mapped_column(Date)
    by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lift_reason: Mapped[str | None] = mapped_column(String(500))


class EquipmentDeployment(Audited, Base):
    """§3.5 `EQD-<project>-<nnnn>`. Tag uniqueness among non-demobilised deployments of the
    project and one live deployment per item are enforced by the service (EM-1, EM-4)."""

    __tablename__ = "equipment_deployments"
    __table_args__ = (
        Index("ix_eq_deployment_project_tag", "project_id", "tag"),
        Index("ix_eq_deployment_item", "equipment_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    deployment_no: Mapped[str] = mapped_column(String(40), unique=True)
    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_items.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    tag: Mapped[str] = mapped_column(String(20))
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    planned_arrival_on: Mapped[date] = mapped_column(Date)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrival_inspection: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    arrival_inspection_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    demobilised_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[EquipmentDeploymentStatus] = enum_col(
        EquipmentDeploymentStatus, default=EquipmentDeploymentStatus.planned
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class ConfigurationEvent(Audited, Base):
    """§3.7 / CF-1…CF-4."""

    __tablename__ = "equipment_configuration_events"

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_items.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    event_type: Mapped[ConfigurationEventType] = enum_col(ConfigurationEventType)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_configuration: Mapped[str] = mapped_column(String(100))
    new_height_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    late_record: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_line_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    cleared_by_line_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    obstacle_refs: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- equipment certificates (§3.6) ---------------------------------------------------------------


class EquipmentCertificate(Audited, Base):
    __tablename__ = "equipment_certificates"
    __table_args__ = (UniqueConstraint("tpi_id", "cert_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    tpi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tpis.id"))
    cert_no: Mapped[str] = mapped_column(String(40))
    inspection_type: Mapped[CertInspectionType] = enum_col(CertInspectionType)
    inspected_on: Mapped[date] = mapped_column(Date)
    issued_on: Mapped[date] = mapped_column(Date)
    printed_next_due: Mapped[date | None] = mapped_column(Date)
    inspector_name: Mapped[str] = mapped_column(String(120))
    inspector_staff_no: Mapped[str | None] = mapped_column(String(30))
    scan_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    tpi_verification_url: Mapped[str | None] = mapped_column(String(300))
    configuration_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment_configuration_events.id")
    )
    configuration_mismatch_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[CertificateStatus] = enum_col(CertificateStatus, default=CertificateStatus.draft)
    status_reason: Mapped[CertStatusReason | None] = enum_col(CertStatusReason, nullable=True)
    status_reason_text: Mapped[str | None] = mapped_column(String(500))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.not_verified
    )
    verification_due_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[CertSource] = enum_col(CertSource, default=CertSource.manual)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    in_force_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_on: Mapped[date | None] = mapped_column(Date)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class EquipmentCertLine(UUIDPk, Base):
    __tablename__ = "equipment_cert_lines"
    __table_args__ = (
        UniqueConstraint("certificate_id", "equipment_id"),
        Index("ix_eq_cert_line_item", "equipment_id"),
    )

    certificate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_certificates.id"))
    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment_items.id"))
    serial_as_printed: Mapped[str] = mapped_column(String(40))
    result: Mapped[LineResult] = enum_col(LineResult)
    swl_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    configuration_ref: Mapped[str | None] = mapped_column(String(100))
    load_test: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    structural_repair: Mapped[bool] = mapped_column(Boolean, default=False)
    lifting_duty_certified: Mapped[bool] = mapped_column(Boolean, default=False)
    colour_code: Mapped[LiftingGearColour | None] = enum_col(LiftingGearColour, nullable=True)
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    defects_input: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    interval_end: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[CertLimitingFactor | None] = enum_col(CertLimitingFactor, nullable=True)
    superseded_by_line_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    suspended_for_configuration: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- scaffolds (§3.8) ----------------------------------------------------------------------------


class Scaffold(Audited, Base):
    __tablename__ = "scaffolds"
    __table_args__ = (Index("ix_scaffold_project_tag", "project_id", "tag"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    scaffold_no: Mapped[str] = mapped_column(String(40), unique=True)
    tag: Mapped[str] = mapped_column(String(20))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    location_desc: Mapped[str] = mapped_column(String(150))
    level_code: Mapped[str | None] = mapped_column(String(10))
    grid_x_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    grid_y_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    scaffold_type: Mapped[ScaffoldType] = enum_col(ScaffoldType)
    height_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    load_class: Mapped[int] = mapped_column(Integer)
    design_ref: Mapped[str | None] = mapped_column(String(40))
    sheeting_fitted: Mapped[bool] = mapped_column(Boolean, default=False)
    erection_supervisor_worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    erection_crew_worker_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[ScaffoldStatus] = enum_col(ScaffoldStatus, default=ScaffoldStatus.under_erection)
    tag_status: Mapped[ScaffoldTagStatus] = enum_col(
        ScaffoldTagStatus, default=ScaffoldTagStatus.red
    )
    tag_valid_until: Mapped[date | None] = mapped_column(Date)
    restrictions_en: Mapped[str | None] = mapped_column(String(300))
    restrictions_ar: Mapped[str | None] = mapped_column(String(300))
    inspection_required_reason: Mapped[ReinspectionReason | None] = enum_col(
        ReinspectionReason, nullable=True
    )
    inspection_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_inspection_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class ScaffoldInspection(UUIDPk, Base):
    __tablename__ = "scaffold_inspections"
    __table_args__ = (Index("ix_scaffold_inspection", "scaffold_id", "inspected_at"),)

    scaffold_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scaffolds.id"))
    inspection_type: Mapped[ScaffoldInspectionType] = enum_col(ScaffoldInspectionType)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inspector_worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    result: Mapped[ScaffoldInspectionResult] = enum_col(ScaffoldInspectionResult)
    restrictions_en: Mapped[str | None] = mapped_column(String(300))
    restrictions_ar: Mapped[str | None] = mapped_column(String(300))
    tag_valid_until: Mapped[date | None] = mapped_column(Date)
    photo_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- personnel certificates (§3.9) ---------------------------------------------------------------


class PersonnelCertificate(Audited, Base):
    __tablename__ = "personnel_certificates"
    __table_args__ = (
        UniqueConstraint("tpi_id", "cert_type", "cert_no"),
        Index("ix_personnel_cert_worker", "worker_id", "cert_type"),
    )

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    record_no: Mapped[str] = mapped_column(String(12), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    cert_type: Mapped[str] = mapped_column(String(40))
    tpi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tpis.id"))
    cert_no: Mapped[str | None] = mapped_column(String(40))
    issued_on: Mapped[date] = mapped_column(Date)
    printed_expiry: Mapped[date | None] = mapped_column(Date)
    cap_end: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    limiting_factor: Mapped[CertLimitingFactor | None] = enum_col(CertLimitingFactor, nullable=True)
    scope_categories: Mapped[list[str]] = mapped_column(STRS, default=list)
    max_capacity_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    level: Mapped[CertLevel | None] = enum_col(CertLevel, nullable=True)
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    medical_restriction_on_card: Mapped[bool] = mapped_column(Boolean, default=False)
    restriction_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restriction_reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id")
    )
    name_as_printed: Mapped[str | None] = mapped_column(String(120))
    id_match_result: Mapped[IdMatchResult] = enum_col(IdMatchResult)
    name_match: Mapped[NameMatch] = enum_col(NameMatch)
    identity_confirmed_by_tpi: Mapped[bool] = mapped_column(Boolean, default=False)
    assessment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scan_front_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    scan_back_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    scans_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tpi_verification_url: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[CertificateStatus] = enum_col(CertificateStatus, default=CertificateStatus.draft)
    status_reason: Mapped[CertStatusReason | None] = enum_col(CertStatusReason, nullable=True)
    status_reason_text: Mapped[str | None] = mapped_column(String(500))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.not_verified
    )
    verification_due_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[CertSource] = enum_col(CertSource, default=CertSource.manual)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    in_force_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_on: Mapped[date | None] = mapped_column(Date)
    anonymised: Mapped[bool] = mapped_column(Boolean, default=False)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- verification (§3.10) ------------------------------------------------------------------------


class CertVerification(UUIDPk, Base):
    __tablename__ = "cert_verifications"
    __table_args__ = (Index("ix_cert_verification_cert", "cert_kind", "cert_id"),)

    cert_kind: Mapped[CertKind] = enum_col(CertKind)
    cert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    tpi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tpis.id"))
    method: Mapped[CertVerificationMethod] = enum_col(CertVerificationMethod)
    channel_used: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[VerificationOutcome] = enum_col(VerificationOutcome)
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


# ---- defects (§3.11) -----------------------------------------------------------------------------


class EquipmentDefect(Numbered, Audited, Base):
    __tablename__ = "equipment_defects"
    __table_args__ = (
        Index("ix_defect_item", "equipment_id"),
        Index("ix_defect_project_raised", "project_id", "raised_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    defect_no: Mapped[str] = mapped_column(String(40), unique=True)
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("equipment_items.id"))
    scaffold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scaffolds.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    source: Mapped[DefectSource] = enum_col(DefectSource)
    source_ref: Mapped[str | None] = mapped_column(String(40))
    cert_line_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    category: Mapped[DefectCategory] = enum_col(DefectCategory)
    description_en: Mapped[str] = mapped_column(String(1000))
    description_ar: Mapped[str | None] = mapped_column(String(1000))
    photo_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    raised_by_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    physical_tag_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    tpi_due_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    rectification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rectified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rectified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[DefectStatus] = enum_col(DefectStatus, default=DefectStatus.open)
    cancelled_reason: Mapped[str | None] = mapped_column(String(500))
    overdue_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- bans (§3.12) --------------------------------------------------------------------------------


class CertificationBan(Audited, Base):
    __tablename__ = "certification_bans"

    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    scope_all: Mapped[bool] = mapped_column(Boolean, default=True)
    cert_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    reason_code: Mapped[BanReason] = enum_col(BanReason)
    reason_text: Mapped[str] = mapped_column(String(500))
    from_date: Mapped[date] = mapped_column(Date)
    review_due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[BanStatus] = enum_col(BanStatus, default=BanStatus.active)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lift_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- hook policy state (§3.14) -------------------------------------------------------------------


class HookPolicyState(Audited, Base):
    __tablename__ = "hook_policy_states"
    __table_args__ = (UniqueConstraint("project_id", "kind"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[HookKind] = enum_col(HookKind)
    provider_registered_on: Mapped[date] = mapped_column(Date)
    critical_block_from: Mapped[date] = mapped_column(Date)
    general_block_from: Mapped[date] = mapped_column(Date)
    original_general_block_from: Mapped[date] = mapped_column(Date)
    deferral: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # HK4-5 early switches: [{"at", "by", "all_codes", "codes"}]
    early_switches: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    switched_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    all_switched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    critical_switched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    general_switched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage: Mapped[HookStage] = enum_col(HookStage, default=HookStage.transition)


# ---- settings and catalogue (§3.16, §3.17) -------------------------------------------------------


class CertSettings(Base):
    """§3.17 (one row per project, created with the defaults on first use)."""

    __tablename__ = "project_cert_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    equipment_interval_months: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    personnel_cert_cap_months: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    require_client_approved_tpi: Mapped[bool] = mapped_column(Boolean, default=False)
    client_approval_required_from: Mapped[date | None] = mapped_column(Date)
    unverified_acceptance_hours: Mapped[int] = mapped_column(Integer, default=0)
    verification_due_days: Mapped[int] = mapped_column(Integer, default=3)
    defect_b_max_days: Mapped[int] = mapped_column(Integer, default=30)
    defect_b_default_days: Mapped[int] = mapped_column(Integer, default=14)
    scaffold_inspection_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    scaffold_design_height_m: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("20.00")
    )
    arrival_inspection_hours: Mapped[int] = mapped_column(Integer, default=24)
    rigger_level_critical_min: Mapped[int] = mapped_column(Integer, default=2)
    trade_cert_requirements: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    hook_transition_days: Mapped[int] = mapped_column(Integer, default=30)
    hook_critical_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    hook_critical_transition_days: Mapped[int] = mapped_column(Integer, default=7)
    lifting_gear_colour_scheme: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    equipment_cert_warning_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal("98.0")
    )
    personnel_cert_warning_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal("95.0")
    )
    scaffold_tag_warning_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal("95.0")
    )
    dangerous_defect_warning_count: Mapped[int] = mapped_column(Integer, default=3)
    ban_review_months: Mapped[int] = mapped_column(Integer, default=6)
    cert_scan_retention_years: Mapped[int] = mapped_column(Integer, default=2)
    alert_schedule_long_days: Mapped[list[int]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class CertType(Base):
    """List PCT rows added or relabelled by the HSE Manager (built-ins live in
    `services/cert/reference.py`; a row here overrides the labels of a built-in)."""

    __tablename__ = "cert_types"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_en: Mapped[str] = mapped_column(String(120))
    label_ar: Mapped[str] = mapped_column(String(120))
    cap_months: Mapped[int] = mapped_column(Integer)
    scope_categories_allowed: Mapped[list[str]] = mapped_column(STRS, default=list)
    levels_allowed: Mapped[list[str]] = mapped_column(STRS, default=list)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


# ---- import batches (§3.15) ----------------------------------------------------------------------


class CertImportBatch(UUIDPk, Base):
    __tablename__ = "cert_import_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    template: Mapped[CertImportTemplate] = enum_col(CertImportTemplate)
    source: Mapped[CertImportSource] = enum_col(CertImportSource)
    tpi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tpis.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    create_items: Mapped[bool] = mapped_column(Boolean, default=False)
    scans_zip_name: Mapped[str | None] = mapped_column(String(255))
    scans_count: Mapped[int | None] = mapped_column(Integer)
    # cert_no(+ side) → attachment id, created at upload; unused ones deleted at commit/discard
    scan_map: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_file_name: Mapped[str | None] = mapped_column(String(255))
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[CertImportStatus] = enum_col(CertImportStatus)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    file_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Parsed rows (ID numbers encrypted per row, IM-4); cleared at commit / discard / expiry
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    committed_certificate_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
