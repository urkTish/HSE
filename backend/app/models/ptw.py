"""Phase 3 tables (spec 3-ptw §3): PTW settings, permit-type overrides, zone PTW profiles, zone
adjacency, SIMOPS rules, appointments, permits (crew, equipment, documents, signatures, shifts,
handovers, suspensions, exemptions, field records), JSA, gas detectors / bump tests / gas tests,
isolations and locks, SIMOPS conflicts and coordination records, PTW audits."""

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

from app.core.clock import now
from app.core.ptw_enums import (
    AppointmentDiscipline,
    AppointmentFunction,
    AppointmentStatus,
    BumpTestResult,
    CoordinationStatus,
    CrewLineStatus,
    DetectorStatus,
    DistanceBasis,
    DocumentType,
    EnergyType,
    EquipmentCategory,
    EquipmentUse,
    ExemptionKind,
    ExemptionStatus,
    Exposure,
    GasTestResult,
    GasTestType,
    HandoverStatus,
    HazardousAreaClass,
    IsolationMethod,
    IsolationStatus,
    JsaStatus,
    LelReferenceGas,
    LockStatus,
    LockType,
    MiddayExemptionReason,
    PermitStatus,
    PermitType,
    PersonalLockRemoval,
    PtwAuditStatus,
    PtwAuditType,
    PtwCrewRole,
    QuarantineReason,
    ShiftEndType,
    SignaturePurpose,
    SimopsCondition,
    SimopsConflictStatus,
    SimopsResult,
    SimopsTypeSelector,
    StatusReason,
    VerificationMethod,
    VerticalRelation,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col

# ---- configuration -------------------------------------------------------------------------------


class PtwSettings(Base):
    """§3.17 (one row per project, created with the defaults on first use)."""

    __tablename__ = "project_ptw_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    ptw_shift_max_hours: Mapped[int] = mapped_column(Integer, default=12)
    issue_to_start_max_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_active_permits_per_receiver: Mapped[int] = mapped_column(Integer, default=3)
    type_max_duration_days: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    gas_pre_start_validity_minutes: Mapped[int] = mapped_column(Integer, default=30)
    gas_retest_interval_minutes: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    gas_break_retest_minutes: Mapped[int] = mapped_column(Integer, default=30)
    gas_limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    detector_calibration_interval_days: Mapped[int] = mapped_column(Integer, default=180)
    fire_watch_post_minutes: Mapped[int] = mapped_column(Integer, default=60)
    hw_combustible_clearance_m: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=Decimal("11.0")
    )
    hw_extinguisher_max_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("9.0"))
    airside_hotwork_separation_m: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=Decimal("15.0")
    )
    wah_permit_threshold_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("1.8"))
    wah_rescue_max_minutes: Mapped[int] = mapped_column(Integer, default=15)
    cse_rescue_max_minutes: Mapped[int] = mapped_column(Integer, default=4)
    cse_heat_control_temp_c: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("35.0"))
    ex_permit_depth_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("1.2"))
    ex_protective_system_depth_m: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=Decimal("1.2")
    )
    ex_pe_design_depth_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("6.0"))
    ex_spoil_setback_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0.6"))
    ex_egress_max_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("7.5"))
    ex_hand_dig_distance_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("1.0"))
    critical_lift_capacity_pct: Mapped[int] = mapped_column(Integer, default=75)
    critical_lift_weight_t: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("20.0"))
    lift_wind_limit_ms: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("9.8"))
    man_basket_wind_limit_ms: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("7.0"))
    rg_barrier_limit_usv_h: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("7.5"))
    drop_zone_radius_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("6.0"))
    vertical_separation_m: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("2.0"))
    midday_ban_period: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    midday_ban_hours: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    midday_ban_prewarn_minutes: Mapped[int] = mapped_column(Integer, default=15)
    jsa_review_months: Mapped[int] = mapped_column(Integer, default=12)
    long_term_isolation_days: Mapped[int] = mapped_column(Integer, default=7)
    appointment_max_months: Mapped[int] = mapped_column(Integer, default=12)
    ptw_audit_min_per_week: Mapped[int] = mapped_column(Integer, default=5)
    ptw_audit_warning_pct: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("85.0"))
    ptw_critical_findings_warning: Mapped[int] = mapped_column(Integer, default=3)
    ptw_closure_warning_pct: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("95.0"))
    step_up_reauth_minutes: Mapped[int] = mapped_column(Integer, default=15)
    ptw_retention_years: Mapped[int] = mapped_column(Integer, default=5)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class PermitTypeConfig(Base):
    """§3.1 per-project additions (the spec defaults live in code and cannot be removed)."""

    __tablename__ = "permit_type_configs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    type: Mapped[PermitType] = enum_col(PermitType, primary_key=True)
    extra_pre_issue: Mapped[list[str]] = mapped_column(STRS, default=list)
    extra_closure: Mapped[list[str]] = mapped_column(STRS, default=list)
    extra_hazards: Mapped[list[str]] = mapped_column(STRS, default=list)
    extra_crew_hooks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    extra_equipment_hooks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ZonePtwProfile(Base):
    """§3.2 (1:1 with zone, created with the PT-3 defaults)."""

    __tablename__ = "zone_ptw_profiles"

    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    permit_required_all_work: Mapped[bool] = mapped_column(Boolean, default=False)
    gas_test_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    hazardous_area_class: Mapped[HazardousAreaClass] = enum_col(
        HazardousAreaClass, default=HazardousAreaClass.none
    )
    hazardous_area_note: Mapped[str | None] = mapped_column(String(200))
    default_exposure: Mapped[Exposure] = enum_col(Exposure, default=Exposure.indoor)
    fire_protection_present: Mapped[bool] = mapped_column(Boolean, default=False)
    level_datum_note: Mapped[str | None] = mapped_column(String(100))
    default_area_authority_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ZoneAdjacency(Audited, Base):
    """§3.3 (unordered pair; stored with zone_a_id < zone_b_id)."""

    __tablename__ = "zone_adjacencies"
    __table_args__ = (UniqueConstraint("zone_a_id", "zone_b_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    zone_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    zone_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    distance_m: Mapped[Decimal] = mapped_column(Numeric(7, 1))
    vertical_relation: Mapped[VerticalRelation] = enum_col(
        VerticalRelation, default=VerticalRelation.none
    )


class SimopsRule(Audited, Base):
    """§3.12 / SM-3 matrix row (codes immutable; R01–R12 cannot be deleted or loosened)."""

    __tablename__ = "simops_rules"
    __table_args__ = (UniqueConstraint("project_id", "rule_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(10))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    type_a: Mapped[SimopsTypeSelector] = enum_col(SimopsTypeSelector)
    type_b: Mapped[SimopsTypeSelector] = enum_col(SimopsTypeSelector)
    condition: Mapped[SimopsCondition] = enum_col(SimopsCondition)
    threshold_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    result: Mapped[SimopsResult] = enum_col(SimopsResult)
    required_controls_en: Mapped[str | None] = mapped_column(String(1000))
    required_controls_ar: Mapped[str | None] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---- appointments --------------------------------------------------------------------------------


class PtwAppointment(Audited, Base):
    """§3.4 (`APT-<project>-<nnnn>`)."""

    __tablename__ = "ptw_appointments"
    __table_args__ = (UniqueConstraint("project_id", "seq"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    appointment_no: Mapped[str] = mapped_column(String(40), unique=True)
    function: Mapped[AppointmentFunction] = enum_col(AppointmentFunction)
    discipline: Mapped[AppointmentDiscipline | None] = enum_col(
        AppointmentDiscipline, nullable=True
    )
    holder_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    holder_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"), index=True)
    permit_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    basis: Mapped[str] = mapped_column(String(300))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    appointed_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[AppointmentStatus] = enum_col(
        AppointmentStatus, default=AppointmentStatus.active
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- permits -------------------------------------------------------------------------------------


class Permit(Audited, Numbered, Base):
    """§3.5 core permit. Type sections and checklist answers are JSON (validated by the
    schemas); blockers / warnings are recomputed (PT-16) and cached here for lists and jobs."""

    __tablename__ = "permits"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_permit_project_status", "project_id", "status"),
    )

    permit_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    location_desc: Mapped[str] = mapped_column(String(200))
    grid_x_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    grid_y_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    level_code: Mapped[str | None] = mapped_column(String(10))
    elevation_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id"), index=True
    )
    work_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    primary_type: Mapped[PermitType] = enum_col(PermitType)
    high_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    critical_lift: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(150))
    scope_en: Mapped[str] = mapped_column(String(1000))
    scope_ar: Mapped[str | None] = mapped_column(String(1000))
    exposure: Mapped[Exposure] = enum_col(Exposure)
    # 3-ptw v1.3 (6b PH-1): set for outdoor exposure; null = the type default (§11.4 item 1)
    heat_workload: Mapped[str | None] = mapped_column(String(20))
    heat_clothing: Mapped[str | None] = mapped_column(String(40))
    heat_hood: Mapped[bool] = mapped_column(Boolean, default=False)
    flammables_in_use: Mapped[bool] = mapped_column(Boolean, default=False)
    combustion_engine_plant: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    receiver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    area_authority_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issuer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    hse_reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    supervisor_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    jsa_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    linked_wap_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    linked_obs_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    isolation_cert_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    conditions_en: Mapped[str | None] = mapped_column(String(1000))
    conditions_ar: Mapped[str | None] = mapped_column(String(1000))
    copied_conditions: Mapped[list[str]] = mapped_column(STRS, default=list)
    # v1.1 (4-third-party-cert §11.4 item 4): SCAFFOLD-TAG results of the WAH scaffold_tag_ref
    # and the conditions copied from Phase 4 hook results (yellow tags, limitations)
    scaffold_hooks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    hook_conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    emergency_info: Mapped[str] = mapped_column(String(300))
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    checklists: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    area_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    hse_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[PermitStatus] = enum_col(PermitStatus, default=PermitStatus.draft)
    status_reason: Mapped[StatusReason | None] = enum_col(StatusReason, nullable=True)
    status_detail: Mapped[str | None] = mapped_column(String(500))
    returned_comment: Mapped[str | None] = mapped_column(String(500))
    current_shift_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    first_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receiver_acceptance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    closure_request: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    post_expiry_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fod_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_return: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    copied_from_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class PermitCrew(UUIDPk, Base):
    """§3.6 crew line."""

    __tablename__ = "permit_crew"
    __table_args__ = (Index("ix_permit_crew_worker", "worker_id"),)

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    crew_role: Mapped[PtwCrewRole] = enum_col(PtwCrewRole)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ptw_appointments.id"))
    escort_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    status: Mapped[CrewLineStatus] = enum_col(CrewLineStatus, default=CrewLineStatus.listed)
    excluded_reason: Mapped[str | None] = mapped_column(String(60))
    eligible: Mapped[bool | None] = mapped_column(Boolean)
    eligibility: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PermitEquipment(UUIDPk, Base):
    __tablename__ = "permit_equipment"

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    category: Mapped[EquipmentCategory | None] = enum_col(EquipmentCategory, nullable=True)
    tag: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(150))
    max_working_height_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    use: Mapped[EquipmentUse] = enum_col(EquipmentUse)
    hooks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # v1.1 (4-third-party-cert §11.4): Phase 4 item, operator binding (HK4-9), conditions
    equipment_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    operator_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    operator_hooks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    swl_t: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PermitDocument(UUIDPk, Base):
    __tablename__ = "permit_documents"

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    doc_type: Mapped[DocumentType] = enum_col(DocumentType)
    ref: Mapped[str] = mapped_column(String(40))
    revision: Mapped[str] = mapped_column(String(6))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    approved_by_text: Mapped[str | None] = mapped_column(String(120))
    valid_until: Mapped[date | None] = mapped_column(Date)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PermitSignature(UUIDPk, Base):
    """PT-15 signature: {user, role/appointment, transition, timestamp, permit hash}."""

    __tablename__ = "permit_signatures"

    permit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("permits.id"), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    purpose: Mapped[SignaturePurpose] = enum_col(SignaturePurpose)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    role_label: Mapped[str] = mapped_column(String(40))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    permit_hash: Mapped[str] = mapped_column(String(64))
    co_signed_on_device_of_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PermitShift(UUIDPk, Base):
    """§3.13 shift record. gas_required / gas_compliant are fixed when the shift ends (K-66)."""

    __tablename__ = "permit_shifts"
    __table_args__ = (
        UniqueConstraint("permit_id", "shift_no"),
        Index("ix_permit_shift_started", "started_at"),
    )

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    shift_no: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receiver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    issuer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    gas_test_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    ambient_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wbgt_reading_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))  # v1.3
    crew_present: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    briefed: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    pauses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_type: Mapped[ShiftEndType | None] = enum_col(ShiftEndType, nullable=True)
    gas_required: Mapped[bool] = mapped_column(Boolean, default=False)
    gas_compliant: Mapped[bool | None] = mapped_column(Boolean)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PermitHandover(UUIDPk, Base):
    __tablename__ = "permit_handovers"

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    from_shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permit_shifts.id"))
    from_receiver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    to_receiver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    to_issuer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    receiver_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issuer_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[HandoverStatus] = enum_col(HandoverStatus, default=HandoverStatus.initiated)
    notes_en: Mapped[str] = mapped_column(String(500))
    notes_ar: Mapped[str | None] = mapped_column(String(500))


class PermitSuspension(UUIDPk, Base):
    """§3.14 suspension event."""

    __tablename__ = "permit_suspensions"
    __table_args__ = (Index("ix_permit_susp_project_time", "project_id", "suspended_at"),)

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    suspended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[StatusReason] = enum_col(StatusReason)
    routine: Mapped[bool] = mapped_column(Boolean, default=False)
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    detail: Mapped[str | None] = mapped_column(String(500))
    auto_source_ref: Mapped[str | None] = mapped_column(String(60))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resume_gas_test_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    cause_cleared_text: Mapped[str | None] = mapped_column(String(500))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class PermitExemption(UUIDPk, Base):
    """PT-17 exemptions (HT-4, EL-3, HW-8, LF-3)."""

    __tablename__ = "permit_exemptions"

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[ExemptionKind] = enum_col(ExemptionKind)
    status: Mapped[ExemptionStatus] = enum_col(ExemptionStatus, default=ExemptionStatus.requested)
    midday_reason: Mapped[MiddayExemptionReason | None] = enum_col(
        MiddayExemptionReason, nullable=True
    )
    reason_text: Mapped[str] = mapped_column(String(500))
    heat_controls_text: Mapped[str | None] = mapped_column(String(1000))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))


class PermitRecord(UUIDPk, Base):
    """Field records of a permit: entry_log (CS-7), wind (LF-6/WH-7), excavation_inspection
    (EX-6), barrier_survey (RG-3). `data` holds the record fields."""

    __tablename__ = "permit_records"
    __table_args__ = (Index("ix_permit_record_kind", "permit_id", "kind"),)

    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"))
    kind: Mapped[str] = mapped_column(String(30))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- JSA -----------------------------------------------------------------------------------------


class Jsa(Audited, Base):
    """§3.8 template (`JSA-T-<project>-<nnnn>`) or permit instance (`JSA-<permit tail>`)."""

    __tablename__ = "jsas"
    __table_args__ = (Index("ix_jsa_project_template", "project_id", "is_template"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    jsa_no: Mapped[str] = mapped_column(String(40), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    permit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("permits.id"), index=True)
    work_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str | None] = mapped_column(String(150))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    residual_acceptances: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    crew_briefings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    review_due_on: Mapped[date | None] = mapped_column(Date)
    returned_comment: Mapped[str | None] = mapped_column(String(500))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    status: Mapped[JsaStatus] = enum_col(JsaStatus, default=JsaStatus.draft)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


# ---- gas -----------------------------------------------------------------------------------------


class GasDetector(Audited, Base):
    """§3.9 (`GD-<project short>-<nnn>`)."""

    __tablename__ = "gas_detectors"
    __table_args__ = (UniqueConstraint("project_id", "serial"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    detector_no: Mapped[str] = mapped_column(String(30), unique=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    make_model: Mapped[str] = mapped_column(String(80))
    serial: Mapped[str] = mapped_column(String(40))
    sensors: Mapped[list[str]] = mapped_column(STRS, default=list)
    lel_reference_gas: Mapped[LelReferenceGas | None] = enum_col(LelReferenceGas, nullable=True)
    calibrated_on: Mapped[date] = mapped_column(Date)
    calibration_cert_ref: Mapped[str] = mapped_column(String(40))
    certificate_due_on: Mapped[date | None] = mapped_column(Date)
    calibration_due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[DetectorStatus] = enum_col(DetectorStatus, default=DetectorStatus.in_service)
    quarantine_reason: Mapped[QuarantineReason | None] = enum_col(QuarantineReason, nullable=True)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_reason: Mapped[str | None] = mapped_column(String(300))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    # v1.1 (4-third-party-cert EQ-3, BL-7): calibration lab registered as a TPI
    calibration_body_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tpis.id"))


class BumpTest(UUIDPk, Base):
    __tablename__ = "gas_bump_tests"
    __table_args__ = (Index("ix_bump_detector_time", "detector_id", "tested_at"),)

    detector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gas_detectors.id"))
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[BumpTestResult] = enum_col(BumpTestResult)
    sensors_responded: Mapped[list[str]] = mapped_column(STRS, default=list)
    tested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    tested_by_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    gas_cylinder_lot: Mapped[str] = mapped_column(String(40))
    gas_cylinder_expiry: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class GasTest(UUIDPk, Base):
    """§3.10 (immutable after save, GT-8; corrections supersede)."""

    __tablename__ = "gas_tests"
    __table_args__ = (Index("ix_gas_test_permit_time", "permit_id", "tested_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    permit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    seq: Mapped[int] = mapped_column(Integer)
    test_no: Mapped[str] = mapped_column(String(60), unique=True)
    test_type: Mapped[GasTestType] = enum_col(GasTestType)
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tester_appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ptw_appointments.id"))
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    tester_signature_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    detector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gas_detectors.id"))
    readings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    internal_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    applicable_limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[GasTestResult] = enum_col(GasTestResult)
    fail_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    valid_for_start_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_reason: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- isolations / LOTO ---------------------------------------------------------------------------


class Lock(Audited, Base):
    """§3.11 lock register (`L-…` isolation lock, `P-…` personal lock, `LB-…` lockbox)."""

    __tablename__ = "ptw_locks"
    __table_args__ = (UniqueConstraint("project_id", "lock_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    lock_no: Mapped[str] = mapped_column(String(20))
    lock_type: Mapped[LockType] = enum_col(LockType)
    holder_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    status: Mapped[LockStatus] = enum_col(LockStatus, default=LockStatus.available)
    applied_on: Mapped[str | None] = mapped_column(String(80))
    lost_detail: Mapped[str | None] = mapped_column(String(300))


class IsolationCertificate(Audited, Numbered, Base):
    """§3.11 (`ISO-<project>-<yyyy>-<nnnn>`). Status timestamps feed K-67 at any as_of."""

    __tablename__ = "isolation_certificates"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    iso_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    equipment_desc: Mapped[str] = mapped_column(String(200))
    energy_types: Mapped[list[str]] = mapped_column(STRS, default=list)
    hv: Mapped[bool] = mapped_column(Boolean, default=False)
    isolation_authority_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lockbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ptw_locks.id"))
    switching_programme_ref: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[IsolationStatus] = enum_col(IsolationStatus, default=IsolationStatus.planned)
    isolated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deisolation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deisolation_authorised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id")
    )
    deisolation_authorised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deisolated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviews: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class IsolationPoint(UUIDPk, Base):
    __tablename__ = "isolation_points"
    __table_args__ = (UniqueConstraint("certificate_id", "point_no"),)

    certificate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("isolation_certificates.id"), index=True
    )
    point_no: Mapped[int] = mapped_column(Integer)
    energy_type: Mapped[EnergyType] = enum_col(EnergyType)
    device_tag: Mapped[str] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(200))
    method: Mapped[IsolationMethod] = enum_col(IsolationMethod)
    isolation_lock_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ptw_locks.id"))
    tag_no: Mapped[str | None] = mapped_column(String(20))
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_by_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_method: Mapped[VerificationMethod | None] = enum_col(
        VerificationMethod, nullable=True
    )
    removed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PersonalLockEvent(UUIDPk, Base):
    __tablename__ = "personal_lock_events"
    __table_args__ = (Index("ix_personal_lock_box", "lockbox_id", "removed_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    lock_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ptw_locks.id"))
    lockbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ptw_locks.id"))
    certificate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("isolation_certificates.id")
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    permit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("permits.id"))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[PersonalLockRemoval | None] = enum_col(PersonalLockRemoval, nullable=True)
    cut_record: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- SIMOPS --------------------------------------------------------------------------------------


class SimopsConflict(Numbered, UUIDPk, Base):
    """§3.12 conflict (`SIM-<project>-<yyyy>-<nnnn>`)."""

    __tablename__ = "simops_conflicts"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_simops_pair", "permit_a_id", "permit_b_id", "rule_code"),
    )

    conflict_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    permit_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"))
    permit_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permits.id"))
    rule_code: Mapped[str] = mapped_column(String(10))
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    distance_basis: Mapped[DistanceBasis] = enum_col(DistanceBasis)
    vertical_note: Mapped[str | None] = mapped_column(String(120))
    overlap_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overlap_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[SimopsResult] = enum_col(SimopsResult)
    required_controls_en: Mapped[str | None] = mapped_column(String(1000))
    required_controls_ar: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[SimopsConflictStatus] = enum_col(
        SimopsConflictStatus, default=SimopsConflictStatus.open
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    coordinated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class SimopsCoordination(UUIDPk, Base):
    __tablename__ = "simops_coordinations"

    conflict_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simops_conflicts.id"), unique=True)
    agreed_controls_en: Mapped[str] = mapped_column(String(1000))
    agreed_controls_ar: Mapped[str | None] = mapped_column(String(1000))
    # [{role, user_id, signed_at|None}]
    signatures: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[CoordinationStatus] = enum_col(
        CoordinationStatus, default=CoordinationStatus.pending_signatures
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---- audits --------------------------------------------------------------------------------------


class PtwAudit(Audited, Numbered, Base):
    """§3.15 (`PTA-<project>-<yyyy>-<nnnnn>`)."""

    __tablename__ = "ptw_audits"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_ptw_audit_project_time", "project_id", "audited_at"),
    )

    audit_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    audit_type: Mapped[PtwAuditType] = enum_col(PtwAuditType)
    permit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("permits.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    auditor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # [{code, answer, severity, note, photo_attachment_ids}]
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    applicable_count: Mapped[int] = mapped_column(Integer, default=0)
    compliant_count: Mapped[int] = mapped_column(Integer, default=0)
    score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    stop_work_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unpermitted_work_desc: Mapped[str | None] = mapped_column(String(1000))
    permit_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[PtwAuditStatus] = enum_col(PtwAuditStatus, default=PtwAuditStatus.draft)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edit_log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


__all__ = [
    "BumpTest",
    "GasDetector",
    "GasTest",
    "IsolationCertificate",
    "IsolationPoint",
    "Jsa",
    "Lock",
    "Permit",
    "PermitCrew",
    "PermitDocument",
    "PermitEquipment",
    "PermitExemption",
    "PermitHandover",
    "PermitRecord",
    "PermitShift",
    "PermitSignature",
    "PermitSuspension",
    "PermitTypeConfig",
    "PersonalLockEvent",
    "PtwAppointment",
    "PtwAudit",
    "PtwSettings",
    "SimopsConflict",
    "SimopsCoordination",
    "SimopsRule",
    "ZoneAdjacency",
    "ZonePtwProfile",
]
