"""Phase 6e tables (spec 6e-environmental §3): project settings, aspects, the org-wide provider
register, permits and licences (project or provider holder), waste streams, storage areas and
consignments, instruments with `env_monitor` devices, monitoring points (requirements as JSON rows),
readings, background declarations, exceedances, spills, water entries, discharge days and
complaints. Post-storm tasks (AIR-4) are derived on read from Phase 2 ops events."""

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
from app.core.env_enums import (
    AreaStatus,
    AspectCondition,
    AspectStatus,
    Averaging,
    BackgroundSource,
    ComplaintCategory,
    ComplaintChannel,
    ComplaintStatus,
    ConsignmentStatus,
    ExceedanceCause,
    ExceedanceStatus,
    InstrumentKind,
    InstrumentStatus,
    Issuer,
    NoiseArea,
    NoisePeriod,
    Parameter,
    PermitStatus,
    PermitType,
    PointKind,
    PointSource,
    ProviderStatus,
    QuantityUnit,
    ReadingResult,
    ReadingSource,
    RecordState,
    SpillSource,
    SpillStatus,
    SpillSubstance,
    SpillSurface,
    StorageAreaType,
    WasteRoute,
    WaterSource,
)
from app.core.hse_enums import EnvReached
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col


class EnvSettings(Base):
    """§3.16 (one row per project). `env_notifications_from` is a column (1-dashboard v1.8 I-20);
    the other keys live in `values`, merged over the defaults on read (services/env/common)."""

    __tablename__ = "project_env_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    env_notifications_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class EnvAspect(Audited, Base):
    """§3.1."""

    __tablename__ = "env_aspects"
    __table_args__ = (UniqueConstraint("project_id", "seq"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    aspect_no: Mapped[str] = mapped_column(String(40), unique=True)
    seq: Mapped[int] = mapped_column(Integer)
    activity: Mapped[str] = mapped_column(String(40))
    aspect: Mapped[str] = mapped_column(String(40))
    impact: Mapped[str] = mapped_column(String(40))
    condition: Mapped[AspectCondition] = enum_col(AspectCondition)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    engagement_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    severity: Mapped[int] = mapped_column(Integer)
    likelihood: Mapped[int] = mapped_column(Integer)
    legal_requirement: Mapped[bool] = mapped_column(Boolean, default=False)
    permit_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    stakeholder_concern: Mapped[bool] = mapped_column(Boolean, default=False)
    controls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    monitoring_links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    activated_on: Mapped[date | None] = mapped_column(Date)
    review_due_on: Mapped[date | None] = mapped_column(Date)
    review_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[AspectStatus] = enum_col(AspectStatus, default=AspectStatus.draft)
    status_reason: Mapped[str | None] = mapped_column(String(500))


class EnvProvider(Audited, Base):
    """§3.2 (org-wide)."""

    __tablename__ = "env_providers"

    provider_code: Mapped[str] = mapped_column(String(12), unique=True)
    name_en: Mapped[str] = mapped_column(String(150))
    name_ar: Mapped[str] = mapped_column(String(150))
    cr_number: Mapped[str] = mapped_column(String(10))
    kinds: Mapped[list[str]] = mapped_column(STRS, default=list)
    facilities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    contact_email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[ProviderStatus] = enum_col(ProviderStatus, default=ProviderStatus.approved)
    status_reason: Mapped[str | None] = mapped_column(String(500))


class EnvPermit(Audited, Base):
    """§3.3 project permit or provider licence; the status is derived (§4.2) from the dates and
    `manual_status` (pending / suspended / cancelled)."""

    __tablename__ = "env_permits"

    record_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("env_providers.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    permit_type: Mapped[PermitType] = enum_col(PermitType)
    issuer: Mapped[Issuer] = enum_col(Issuer)
    requirement_code: Mapped[str | None] = mapped_column(String(20))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_from: Mapped[date | None] = mapped_column(Date)
    applies_to: Mapped[date | None] = mapped_column(Date)
    reference_no: Mapped[str | None] = mapped_column(String(40))
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    document_id: Mapped[uuid.UUID | None] = mapped_column()
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_permits.id"))
    manual_status: Mapped[PermitStatus | None] = enum_col(PermitStatus, nullable=True)
    manual_from: Mapped[date | None] = mapped_column(Date)
    status_reason: Mapped[str | None] = mapped_column(String(500))


class WasteStream(Audited, Base):
    """§3.4 (one per project and list WS code)."""

    __tablename__ = "waste_streams"
    __table_args__ = (UniqueConstraint("project_id", "stream_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    stream_code: Mapped[str] = mapped_column(String(30))
    default_route: Mapped[WasteRoute] = enum_col(WasteRoute)
    density: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WasteStorageArea(Audited, Base):
    """§3.5."""

    __tablename__ = "waste_storage_areas"
    __table_args__ = (UniqueConstraint("project_id", "area_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    area_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    type: Mapped[StorageAreaType] = enum_col(StorageAreaType)
    accepted_streams: Mapped[list[str]] = mapped_column(STRS, default=list)
    capacity_m3: Mapped[Decimal] = mapped_column(Numeric(7, 1))
    secondary_containment_pct: Mapped[int | None] = mapped_column(Integer)
    covered: Mapped[bool] = mapped_column(Boolean, default=False)
    lidded_secured: Mapped[bool] = mapped_column(Boolean, default=False)
    signage_bilingual: Mapped[bool] = mapped_column(Boolean, default=False)
    accumulation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[AreaStatus] = enum_col(AreaStatus, default=AreaStatus.active)


class WasteConsignment(Audited, Numbered, Base):
    """§3.6 consignment note / manifest."""

    __tablename__ = "waste_consignments"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_consignment_project_dispatch", "project_id", "dispatched_date"),
    )

    consignment_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    stream_code: Mapped[str] = mapped_column(String(30))
    storage_area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("waste_storage_areas.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    generator_engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(9, 3))
    unit: Mapped[QuantityUnit] = enum_col(QuantityUnit)
    estimated_t: Mapped[Decimal] = mapped_column(Numeric(9, 3))
    route: Mapped[WasteRoute] = enum_col(WasteRoute)
    transporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_providers.id"))
    transporter_licence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_permits.id"))
    facility_provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_providers.id"))
    facility_code: Mapped[str | None] = mapped_column(String(20))
    facility_licence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_permits.id"))
    vehicle_plate: Mapped[str] = mapped_column(String(12))
    driver_name: Mapped[str | None] = mapped_column(String(120))
    driver_mobile: Mapped[str | None] = mapped_column(String(15))
    mwan_manifest_ref: Mapped[str | None] = mapped_column(String(40))
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_date: Mapped[date] = mapped_column(Date)
    dispatched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_on: Mapped[date] = mapped_column(Date)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_net_t: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    ticket_ref: Mapped[str | None] = mapped_column(String(40))
    ticket_file_id: Mapped[uuid.UUID | None] = mapped_column()
    receipt_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discrepancy_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    discrepancy_reason: Mapped[str | None] = mapped_column(String(500))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    redispatch_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("waste_consignments.id"))
    ca_id: Mapped[uuid.UUID | None] = mapped_column()
    warnings: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[ConsignmentStatus] = enum_col(ConsignmentStatus)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnvInstrument(Audited, Base):
    """§3.7."""

    __tablename__ = "env_instruments"
    __table_args__ = (
        UniqueConstraint("project_id", "instrument_no", name="uq_env_instrument_no"),
        UniqueConstraint("project_id", "serial_no", name="uq_env_instrument_serial"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    instrument_no: Mapped[str] = mapped_column(String(30))
    kind: Mapped[InstrumentKind] = enum_col(InstrumentKind)
    make_model: Mapped[str] = mapped_column(String(80))
    serial_no: Mapped[str] = mapped_column(String(40))
    standard_class: Mapped[str | None] = mapped_column(String(2))
    calibration_valid_until: Mapped[date] = mapped_column(Date)
    calibration_cert_ref: Mapped[str] = mapped_column(String(40))
    status: Mapped[InstrumentStatus] = enum_col(InstrumentStatus, default=InstrumentStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(500))


class EnvMonitorDevice(UUIDPk, Base):
    """2-access-permits v1.7 §3.19 device kind `env_monitor`: not bound to a gate; its session may
    call only the 6e reading-ingest endpoint (MON-2)."""

    __tablename__ = "env_monitor_devices"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_instruments.id"))
    device_id: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class EnvPoint(Audited, Base):
    """§3.8 with the §3.9 requirement rows as JSON."""

    __tablename__ = "env_points"
    __table_args__ = (UniqueConstraint("project_id", "point_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    point_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    kind: Mapped[PointKind] = enum_col(PointKind)
    noise_area_category: Mapped[NoiseArea | None] = enum_col(NoiseArea, nullable=True)
    source_kind: Mapped[PointSource] = enum_col(PointSource)
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_instruments.id"))
    permit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_permits.id"))
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class EnvReading(Audited, Base):
    """§3.10. `day` = local date(window_end) (EK-1); `reading_no` per project and day."""

    __tablename__ = "env_readings"
    __table_args__ = (
        UniqueConstraint("project_id", "day", "seq"),
        Index("ix_env_reading_point", "point_id", "parameter", "averaging", "window_start"),
        Index("ix_env_reading_project_day", "project_id", "day"),
    )

    reading_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    day: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer)
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_points.id"))
    parameter: Mapped[Parameter] = enum_col(Parameter)
    averaging: Mapped[Averaging] = enum_col(Averaging)
    period: Mapped[NoisePeriod] = enum_col(NoisePeriod, default=NoisePeriod.any)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[ReadingSource] = enum_col(ReadingSource)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_instruments.id"))
    device_pk: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_monitor_devices.id"))
    lab_provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("env_providers.id"))
    lab_report_ref: Mapped[str | None] = mapped_column(String(40))
    field_calibration_checked: Mapped[bool | None] = mapped_column(Boolean)
    background: Mapped[bool] = mapped_column(Boolean, default=False)
    background_ref: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[ReadingResult] = enum_col(ReadingResult)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    late_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    exceedance_id: Mapped[uuid.UUID | None] = mapped_column()
    warnings: Mapped[list[str]] = mapped_column(STRS, default=list)
    status: Mapped[RecordState] = enum_col(RecordState, default=RecordState.valid)
    void_reason: Mapped[str | None] = mapped_column(String(500))


class BackgroundDeclaration(Audited, Numbered, Base):
    """§3.11."""

    __tablename__ = "env_background_declarations"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    declaration_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[BackgroundSource] = enum_col(BackgroundSource)
    source_ref: Mapped[str] = mapped_column(String(40))
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class EnvExceedance(Audited, Numbered, Base):
    """§3.12 (EXD-1…EXD-6). `day` = local date(window_end) of the first reading (EK-1)."""

    __tablename__ = "env_exceedances"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_env_exceedance_point", "point_id", "parameter", "averaging"),
    )

    exceedance_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_points.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    parameter: Mapped[Parameter] = enum_col(Parameter)
    averaging: Mapped[Averaging] = enum_col(Averaging)
    period: Mapped[NoisePeriod] = enum_col(NoisePeriod, default=NoisePeriod.any)
    reading_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    day: Mapped[date] = mapped_column(Date)
    peak_value: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    limit_value: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    margin_pct: Mapped[Decimal] = mapped_column(Numeric(8, 1))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    episode_open: Mapped[bool] = mapped_column(Boolean, default=True)
    late_result: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_cause: Mapped[ExceedanceCause | None] = enum_col(ExceedanceCause, nullable=True)
    background_ref: Mapped[str | None] = mapped_column(String(40))
    cause: Mapped[ExceedanceCause | None] = enum_col(ExceedanceCause, nullable=True)
    responsible_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    activity_en: Mapped[str | None] = mapped_column(String(300))
    activity_ar: Mapped[str | None] = mapped_column(String(300))
    immediate_action_en: Mapped[str | None] = mapped_column(Text)
    immediate_action_ar: Mapped[str | None] = mapped_column(Text)
    ca_id: Mapped[uuid.UUID | None] = mapped_column()
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ExceedanceStatus] = enum_col(ExceedanceStatus, default=ExceedanceStatus.open)
    void_reason: Mapped[str | None] = mapped_column(String(500))


class Spill(Audited, Numbered, Base):
    """§3.13."""

    __tablename__ = "env_spills"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        UniqueConstraint("project_id", "client_uuid", name="uq_env_spill_client_uuid"),
    )

    spill_no: Mapped[str] = mapped_column(String(40), unique=True)
    client_uuid: Mapped[uuid.UUID] = mapped_column()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_date: Mapped[date] = mapped_column(Date)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    responsible_engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    substance: Mapped[SpillSubstance] = enum_col(SpillSubstance)
    source: Mapped[SpillSource] = enum_col(SpillSource)
    quantity_l: Mapped[Decimal] = mapped_column(Numeric(9, 1))
    surface: Mapped[SpillSurface] = enum_col(SpillSurface)
    contained: Mapped[bool] = mapped_column(Boolean)
    reached: Mapped[EnvReached] = enum_col(EnvReached)
    spill_kit_asset_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    reportable: Mapped[bool] = mapped_column(Boolean, default=False)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"))
    cleanup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_consignment_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    cleanup_storage_area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("waste_storage_areas.id")
    )
    absorbed_and_binned: Mapped[bool] = mapped_column(Boolean, default=False)
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SpillStatus] = enum_col(SpillStatus, default=SpillStatus.reported)
    void_reason: Mapped[str | None] = mapped_column(String(500))


class WaterEntry(Audited, Base):
    """§3.14 monthly water use (one valid entry per site, month and source)."""

    __tablename__ = "env_water_entries"
    __table_args__ = (Index("ix_water_entry_key", "project_id", "site_id", "month", "source"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    month: Mapped[str] = mapped_column(String(7))
    source: Mapped[WaterSource] = enum_col(WaterSource)
    volume_m3: Mapped[Decimal] = mapped_column(Numeric(10, 1))
    purpose: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[RecordState] = enum_col(RecordState, default=RecordState.valid)
    void_reason: Mapped[str | None] = mapped_column(String(500))


class DischargeDay(Audited, Base):
    """§3.14 dewatering discharge day on a `discharge` point (WAT-2, WAT-3)."""

    __tablename__ = "env_discharge_days"
    __table_args__ = (UniqueConstraint("point_id", "day"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("env_points.id"))
    day: Mapped[date] = mapped_column(Date)
    volume_m3: Mapped[Decimal] = mapped_column(Numeric(10, 1))
    warnings: Mapped[list[str]] = mapped_column(STRS, default=list)


class EnvComplaint(Audited, Numbered, Base):
    """§3.15 (complainant data per P6e-2)."""

    __tablename__ = "env_complaints"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    complaint_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_date: Mapped[date] = mapped_column(Date)
    channel: Mapped[ComplaintChannel] = enum_col(ComplaintChannel)
    category: Mapped[ComplaintCategory] = enum_col(ComplaintCategory)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    location_text: Mapped[str | None] = mapped_column(String(200))
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    complainant_name: Mapped[str | None] = mapped_column(String(120))
    complainant_contact: Mapped[str | None] = mapped_column(String(60))
    contact_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)
    reading_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    exceedance_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    investigation_en: Mapped[str | None] = mapped_column(Text)
    investigation_ar: Mapped[str | None] = mapped_column(Text)
    response_due_on: Mapped[date] = mapped_column(Date)
    response_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_summary: Mapped[str | None] = mapped_column(Text)
    ca_id: Mapped[uuid.UUID | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ComplaintStatus] = enum_col(ComplaintStatus, default=ComplaintStatus.open)
    void_reason: Mapped[str | None] = mapped_column(String(500))
