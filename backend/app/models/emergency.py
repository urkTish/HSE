"""Phase 6c tables (spec 6c-emergency-drills §3): project settings, ERP revisions (scenarios as
JSON inside the revision), assembly points, emergency contacts, zone emergency profiles, the
emergency roster, rescue teams, emergency assets and their checks, drills, musters (named entries
in a child table; count rows as JSON), real emergency events and muster-reader devices.

Drill programme lines (§3.10) are derived on read from the settings, the ERP and the drills
(DECISIONS: computed, not stored), like the 6b zone heat state."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.emergency_enums import (
    ActiveStatus,
    ApKind,
    AssetStatus,
    AssetType,
    CheckMethod,
    CheckOutcome,
    CheckResult,
    DrillResult,
    DrillShift,
    DrillStatus,
    DrillType,
    EmergencyRole,
    EntryMethod,
    EntryState,
    ErpStatus,
    EventStatus,
    EventType,
    MusterMode,
    MusterSource,
    MusterStatus,
    RecordStatus,
    ResolutionReason,
    ResponseType,
    RosterShift,
    TeamType,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col


class EmergencySettings(Base):
    """§3.15 (one row per project). Dates are columns; the other keys live in `values` and are
    merged over the defaults on read (services/emergency/common.DEFAULTS)."""

    __tablename__ = "project_emergency_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    emergency_register_from: Mapped[date | None] = mapped_column(Date)
    emergency_ptw_enforcement_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Erp(Audited, Base):
    """§3.1 ERP revision with its scenarios (§3.2) as JSON rows."""

    __tablename__ = "emergency_erps"
    __table_args__ = (UniqueConstraint("project_id", "revision"),)

    erp_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    title_en: Mapped[str] = mapped_column(String(150))
    title_ar: Mapped[str] = mapped_column(String(150))
    document_ref: Mapped[str] = mapped_column(String(40))
    document_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    scenarios: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    client_acceptance_ref: Mapped[str | None] = mapped_column(String(40))
    accepted_on: Mapped[date | None] = mapped_column(Date)
    airport_interface_ref: Mapped[str | None] = mapped_column(String(40))
    prepared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_due_on: Mapped[date | None] = mapped_column(Date)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    review_triggers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[ErpStatus] = enum_col(ErpStatus, default=ErpStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class AssemblyPoint(Audited, Base):
    """§3.3."""

    __tablename__ = "emergency_assembly_points"
    __table_args__ = (UniqueConstraint("project_id", "ap_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    ap_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    location_en: Mapped[str] = mapped_column(String(200))
    location_ar: Mapped[str] = mapped_column(String(200))
    gps_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    gps_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    capacity_persons: Mapped[int] = mapped_column(Integer)
    zones_served: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    kind: Mapped[ApKind] = enum_col(ApKind)
    status: Mapped[ActiveStatus] = enum_col(ActiveStatus, default=ActiveStatus.active)


class EmergencyContact(Audited, Base):
    """§3.4."""

    __tablename__ = "emergency_contacts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    agency: Mapped[str] = mapped_column(String(40))
    display_name_en: Mapped[str] = mapped_column(String(150))
    display_name_ar: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20))
    person_name: Mapped[str | None] = mapped_column(String(120))
    available_24h: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ZoneEmergencyProfile(Base):
    """§3.5 (1 : 1 with the zone, optional)."""

    __tablename__ = "zone_emergency_profiles"

    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    eyewash_required: Mapped[bool] = mapped_column(Boolean, default=False)
    min_extinguishers: Mapped[int | None] = mapped_column(Integer)
    min_first_aid_kits: Mapped[int | None] = mapped_column(Integer)
    warden_required: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class RosterAssignment(Audited, Base):
    """§3.6."""

    __tablename__ = "emergency_roster"
    __table_args__ = (
        UniqueConstraint("project_id", "seq"),
        Index("ix_emergency_roster_site", "project_id", "site_id"),
    )

    assignment_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[EmergencyRole] = enum_col(EmergencyRole)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("worker_deployments.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    shift: Mapped[RosterShift] = enum_col(RosterShift)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    designated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ended_reason: Mapped[str | None] = mapped_column(String(300))


class RescueTeam(Audited, Base):
    """§3.7. Equipment: Phase 4 tripod_winch equipment items and 6c assets."""

    __tablename__ = "emergency_rescue_teams"
    __table_args__ = (UniqueConstraint("project_id", "team_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    team_code: Mapped[str] = mapped_column(String(16))
    team_type: Mapped[TeamType] = enum_col(TeamType)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    lead_deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    member_deployment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    equipment_item_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    asset_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    created_on: Mapped[date] = mapped_column(Date)
    status: Mapped[ActiveStatus] = enum_col(ActiveStatus, default=ActiveStatus.active)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class EmergencyAsset(Audited, Base):
    """§3.8."""

    __tablename__ = "emergency_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_tag"),
        Index("ix_emergency_asset_site", "project_id", "site_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    asset_tag: Mapped[str] = mapped_column(String(20))
    asset_type: Mapped[AssetType] = enum_col(AssetType)
    subtype: Mapped[str | None] = mapped_column(String(20))
    capacity: Mapped[str | None] = mapped_column(String(20))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    location_en: Mapped[str] = mapped_column(String(200))
    owner_engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    manufactured_year: Mapped[int | None] = mapped_column(Integer)
    serial_no: Mapped[str | None] = mapped_column(String(40))
    last_service_on: Mapped[date | None] = mapped_column(Date)
    service_provider_tpi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tpis.id"))
    service_ref: Mapped[str | None] = mapped_column(String(40))
    expiries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    registered_on: Mapped[date] = mapped_column(Date)
    status: Mapped[AssetStatus] = enum_col(AssetStatus, default=AssetStatus.in_service)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    status_changed_on: Mapped[date | None] = mapped_column(Date)
    flagged_without_scan: Mapped[bool] = mapped_column(Boolean, default=False)
    # 6c v1.2 (6e SPL-5): used in a 6e spill; not ready (USED_REPLENISH) until a later pass check
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetCheck(Audited, Numbered, Base):
    """§3.9."""

    __tablename__ = "emergency_asset_checks"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_emergency_check_asset", "asset_id", "checked_at"),
    )

    check_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emergency_assets.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    method: Mapped[CheckMethod] = enum_col(CheckMethod)
    outcome: Mapped[CheckOutcome] = enum_col(CheckOutcome)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    fixed_on_spot: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[CheckResult] = enum_col(CheckResult)
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    ca_id: Mapped[uuid.UUID | None] = mapped_column()
    warnings: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[RecordStatus] = enum_col(RecordStatus, default=RecordStatus.valid)
    void_reason: Mapped[str | None] = mapped_column(String(500))


class Drill(Audited, Numbered, Base):
    """§3.11. timeline / targets / evaluation / external participation are JSON."""

    __tablename__ = "emergency_drills"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_emergency_drill_project_status", "project_id", "status"),
    )

    drill_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    drill_type: Mapped[DrillType] = enum_col(DrillType)
    scenario_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("emergency_rescue_teams.id"))
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shift: Mapped[DrillShift] = enum_col(DrillShift)
    announced: Mapped[bool] = mapped_column(Boolean, default=True)
    suspend_permits: Mapped[bool] = mapped_column(Boolean, default=True)
    conductor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    evaluator_user_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    plan_note: Mapped[str | None] = mapped_column(String(500))
    rescue_plan_ref: Mapped[str | None] = mapped_column(String(40))
    timeline: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    targets: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    muster_id: Mapped[uuid.UUID | None] = mapped_column()
    external_participation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    airport_exercise_ref: Mapped[str | None] = mapped_column(String(40))
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[DrillResult | None] = enum_col(DrillResult, nullable=True)
    late_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    conducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[DrillStatus] = enum_col(DrillStatus, default=DrillStatus.planned)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class Muster(Audited, Numbered, Base):
    """§3.12. Count-mode rows: `counts` = [{engagement_id, expected, accounted, resolved:
    [{reason, count, at}], by, at}]. After retention, `summary` holds counts by state/reason."""

    __tablename__ = "emergency_musters"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    muster_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    source_type: Mapped[MusterSource] = enum_col(MusterSource)
    source_id: Mapped[uuid.UUID] = mapped_column()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    ap_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    mode: Mapped[MusterMode] = enum_col(MusterMode)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    counts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    visitors_expected: Mapped[int | None] = mapped_column(Integer)
    visitors_accounted: Mapped[int | None] = mapped_column(Integer)
    headcount_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extras: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MusterStatus] = enum_col(MusterStatus, default=MusterStatus.open)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class MusterEntry(UUIDPk, Base):
    """§3.12 roll entry (personal: a person's presence at a place and time, P6c-4)."""

    __tablename__ = "emergency_muster_entries"
    __table_args__ = (UniqueConstraint("muster_id", "deployment_id"),)

    muster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("emergency_musters.id", ondelete="CASCADE"), index=True
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column()
    source_gate_check_id: Mapped[uuid.UUID | None] = mapped_column()
    state: Mapped[EntryState] = enum_col(EntryState, default=EntryState.expected)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ap_id: Mapped[uuid.UUID | None] = mapped_column()
    method: Mapped[EntryMethod | None] = enum_col(EntryMethod, nullable=True)
    resolution_reason: Mapped[ResolutionReason | None] = enum_col(ResolutionReason, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500))
    extra: Mapped[bool] = mapped_column(Boolean, default=False)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class EmergencyEvent(Audited, Numbered, Base):
    """§3.13 real emergency (casualty counts only, P6c-3)."""

    __tablename__ = "emergency_events"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    event_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    event_type: Mapped[EventType] = enum_col(EventType)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    location_en: Mapped[str | None] = mapped_column(String(200))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    response_type: Mapped[ResponseType] = enum_col(ResponseType)
    muster_id: Mapped[uuid.UUID | None] = mapped_column()
    first_responder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_services: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    casualties_count: Mapped[int] = mapped_column(Integer, default=0)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"))
    ops_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ops_events.id"))
    all_clear_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    all_clear_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    late_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EventStatus] = enum_col(EventStatus, default=EventStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class MusterDevice(UUIDPk, Base):
    """2-access-permits v1.5 §3.19 device kind `muster_reader`: bound to one assembly point; its
    session may call only the muster scan endpoint for that point (§11.3)."""

    __tablename__ = "emergency_muster_devices"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    ap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emergency_assembly_points.id"))
    device_id: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)
