"""Phase 6b tables (spec 6b-heat-stress §3): project settings, the org-wide regime table, heat
instruments and their weather-station devices, monitoring points, WBGT readings, acclimatisation
plans, rest stations, welfare checks, midday-ban patrols and exemptions, the heat-illness log and
season reports.

The zone heat state (§3.5) is derived on read from the valid readings of the covering point
(DECISIONS: computed, not stored), so a reading or a void changes it at once."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.heat_enums import (
    AcclimatisationBasis,
    BanExemptionReason,
    BanExemptionStatus,
    Cooling,
    HeatLogSource,
    HeatLogStatus,
    InstrumentKind,
    InstrumentStatus,
    PatrolOutcome,
    PlanStatus,
    PlanType,
    PointSourceKind,
    ReadingSource,
    RecordStatus,
    Regime,
    SeasonReportStatus,
    StationType,
    Workload,
)
from app.db.base import Base
from app.models.access import INTS, STRS, UUIDS, Audited, Numbered
from app.models.base import UUIDPk, enum_col


class HeatSettings(Base):
    """§3.14 (one row per project). Dates are columns; the other keys live in `values` and are
    merged over the defaults on read (services/heat/common.DEFAULTS)."""

    __tablename__ = "project_heat_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    heat_register_from: Mapped[date | None] = mapped_column(Date)
    heat_ptw_enforcement_from: Mapped[date | None] = mapped_column(Date)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class HeatRegimeLimit(Base):
    """§3.4: org-wide, tighten only (HS-5). History is the audit log."""

    __tablename__ = "heat_regime_limits"
    __table_args__ = (UniqueConstraint("basis", "regime", "workload"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    basis: Mapped[AcclimatisationBasis] = enum_col(AcclimatisationBasis)
    regime: Mapped[Regime] = enum_col(Regime)
    workload: Mapped[Workload] = enum_col(Workload)
    limit_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class HeatInstrument(Audited, Base):
    """§3.1."""

    __tablename__ = "heat_instruments"
    __table_args__ = (
        UniqueConstraint("project_id", "seq", name="uq_heat_instruments_seq"),
        UniqueConstraint("project_id", "serial_no", name="uq_heat_instruments_serial"),
    )

    instrument_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[InstrumentKind] = enum_col(InstrumentKind)
    make_model: Mapped[str] = mapped_column(String(80))
    serial_no: Mapped[str] = mapped_column(String(40))
    iso7243_compliant: Mapped[bool] = mapped_column(Boolean, default=False)
    calibration_valid_until: Mapped[date] = mapped_column(Date)
    calibration_cert_ref: Mapped[str] = mapped_column(String(40))
    status: Mapped[InstrumentStatus] = enum_col(InstrumentStatus, default=InstrumentStatus.active)
    status_reason: Mapped[str | None] = mapped_column(String(300))


class HeatStationDevice(UUIDPk, Base):
    """2-access-permits v1.4 §3.19 device kind `weather_station`: not bound to a gate; its
    session may call only the reading-ingest endpoint (HS-4)."""

    __tablename__ = "heat_station_devices"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("heat_instruments.id"))
    device_id: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class MonitoringPoint(Audited, Base):
    """§3.2."""

    __tablename__ = "heat_monitoring_points"
    __table_args__ = (UniqueConstraint("project_id", "point_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    point_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    source_kind: Mapped[PointSourceKind] = enum_col(PointSourceKind)
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("heat_instruments.id"))
    solar_load: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WbgtReading(UUIDPk, Base):
    """§3.3. `regime_cells`: {"acclimatised.heavy": "R2", …} for work_clothes (WR-5)."""

    __tablename__ = "wbgt_readings"
    __table_args__ = (
        Index("ix_wbgt_point_time", "point_id", "measured_at"),
        Index("ix_wbgt_project_time", "project_id", "measured_at"),
        Index(
            "uq_wbgt_station_time",
            "device_pk",
            "measured_at",
            unique=True,
            postgresql_where=text("device_pk IS NOT NULL"),
        ),
        UniqueConstraint("project_id", "local_date", "seq"),
    )

    reading_no: Mapped[str] = mapped_column(String(48), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    local_date: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer)
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("heat_monitoring_points.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))  # WR-7 permit read
    permit_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[ReadingSource] = enum_col(ReadingSource)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("heat_instruments.id"))
    device_pk: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("heat_station_devices.id"))
    ta_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    tnwb_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    tg_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    rh_pct: Mapped[int | None] = mapped_column(Integer)
    wbgt_entered_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wbgt_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    regime_cells: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    late_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[RecordStatus] = enum_col(RecordStatus, default=RecordStatus.valid)
    void_reason: Mapped[str | None] = mapped_column(String(300))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class AcclimatisationPlan(Numbered, Audited, Base):
    """§3.6. `trigger`: {kind, ref, on}; `days`: [{day_no, work_date, max_pct, max_minutes,
    confirmed_by, confirmed_at, followed, note}]."""

    __tablename__ = "acclimatisation_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_acclim_plan_deployment", "deployment_id", "status"),
    )

    plan_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("worker_deployments.id"))
    worker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workers.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    plan_type: Mapped[PlanType] = enum_col(PlanType)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    trigger_date: Mapped[date] = mapped_column(Date)
    schedule_pct: Mapped[list[int]] = mapped_column(INTS, default=list)
    prior_heat_experience: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    days: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[PlanStatus] = enum_col(PlanStatus)
    status_reason: Mapped[str | None] = mapped_column(String(300))
    completed_on: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class RestStation(Audited, Base):
    """§3.7."""

    __tablename__ = "heat_rest_stations"
    __table_args__ = (UniqueConstraint("project_id", "station_code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    station_code: Mapped[str] = mapped_column(String(16))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    station_type: Mapped[StationType] = enum_col(StationType)
    capacity_persons: Mapped[int] = mapped_column(Integer)
    cooling: Mapped[Cooling] = enum_col(Cooling)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HeatWelfareCheck(Numbered, Audited, Base):
    """§3.8. `items`: [{item, answer, note}]."""

    __tablename__ = "heat_welfare_checks"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_welfare_station_time", "station_id", "checked_at"),
    )

    check_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("heat_rest_stations.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    water_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    persons_present: Mapped[int | None] = mapped_column(Integer)
    ca_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    status: Mapped[RecordStatus] = enum_col(RecordStatus, default=RecordStatus.valid)
    void_reason: Mapped[str | None] = mapped_column(String(300))


class BanExemption(Numbered, Audited, Base):
    """§3.10 non-permit midday-ban exemption (capability 171)."""

    __tablename__ = "heat_ban_exemptions"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    exemption_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_engagements.id"))
    zone_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    reason: Mapped[BanExemptionReason] = enum_col(BanExemptionReason)
    controls_en: Mapped[str | None] = mapped_column(String(1000))
    controls_ar: Mapped[str | None] = mapped_column(String(1000))
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BanExemptionStatus] = enum_col(
        BanExemptionStatus, default=BanExemptionStatus.active
    )
    status_reason: Mapped[str | None] = mapped_column(String(300))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class BanPatrol(Numbered, Audited, Base):
    """§3.9."""

    __tablename__ = "heat_ban_patrols"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "seq"),
        Index("ix_ban_patrol_zone_time", "zone_id", "checked_at"),
    )

    patrol_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[PatrolOutcome] = enum_col(PatrolOutcome)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    headcount: Mapped[int | None] = mapped_column(Integer)
    activity: Mapped[str | None] = mapped_column(String(200))
    exemption_ref: Mapped[str | None] = mapped_column(String(40))
    permit_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    ca_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    status: Mapped[RecordStatus] = enum_col(RecordStatus, default=RecordStatus.valid)
    void_reason: Mapped[str | None] = mapped_column(String(300))


class HeatIllnessEntry(Numbered, Audited, Base):
    """§3.11. Stores no clinical data: nature and category stay in Phase 1. `review`:
    {answers: {HC1: yes|no|unknown|na, …}, factors_text, reviewed_by, reviewed_at}."""

    __tablename__ = "heat_illness_entries"
    __table_args__ = (UniqueConstraint("project_id", "year", "seq"),)

    entry_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    source_type: Mapped[HeatLogSource] = enum_col(HeatLogSource)
    source_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    related_referral_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_engagements.id"))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    control_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[HeatLogStatus] = enum_col(HeatLogStatus, default=HeatLogStatus.open)
    hold_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class HeatSeasonReport(UUIDPk, Base):
    """§3.12 issued revisions (the Draft is computed live, HM-4)."""

    __tablename__ = "heat_season_reports"
    __table_args__ = (UniqueConstraint("project_id", "season_year", "revision"),)

    report_no: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    season_year: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    status: Mapped[SeasonReportStatus] = enum_col(SeasonReportStatus)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    comments_en: Mapped[str | None] = mapped_column(String(2000))
    comments_ar: Mapped[str | None] = mapped_column(String(2000))
    reissue_reason: Mapped[str | None] = mapped_column(String(300))
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = [
    "AcclimatisationPlan",
    "BanExemption",
    "BanPatrol",
    "HeatIllnessEntry",
    "HeatInstrument",
    "HeatRegimeLimit",
    "HeatSeasonReport",
    "HeatSettings",
    "HeatStationDevice",
    "HeatWelfareCheck",
    "MonitoringPoint",
    "RestStation",
    "WbgtReading",
]
