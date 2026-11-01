"""Tables of package Q3 logistics: receiving, storage and cold chain, stock, recalls, transport
(spec 8-quality Part D, §3.3 Q3 row).

Q3 refers to Q0 tables (customers, suppliers, M&TE, NCRs) and to platform tables (projects,
sites, zones, vehicles, workers) by foreign key; it never refers to a Q1 / Q2 / Q4 table (§3.4).
Readings are immutable (Q-STO-07): there is no update path except the batch void flag."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.quality.q3 import (
    QCheckFrequency,
    QCheckType,
    QDamageCause,
    QDamageStage,
    QExcursionCause,
    QExcursionKind,
    QExcursionSeverity,
    QExcursionStatus,
    QFefoException,
    QFefoResult,
    QHoldLineStatus,
    QHoldOutcome,
    QHoldReason,
    QHoldStatus,
    QImpactDecision,
    QImportKind,
    QImportStatus,
    QImportTarget,
    QLineCondition,
    QLineDecision,
    QLoadState,
    QMappingPurpose,
    QMappingState,
    QMappingStatus,
    QPestStationType,
    QPointPosition,
    QReadingSource,
    QReadingTarget,
    QRecallClass,
    QRecallStatus,
    QRecallType,
    QReceiptStatus,
    QReturnGrade,
    QReturnStatus,
    QSeason,
    QSegregation,
    QStorageClass,
    QTripStatus,
    QZoneRole,
)
from app.db.base import Base
from app.models.access import STRS, UUIDS, Audited
from app.models.base import enum_col

TEMP = Numeric(6, 2)
QTY = Numeric(14, 3)
PCT = Numeric(6, 2)

__all__ = [
    "QCheckSchedule",
    "QCycleCount",
    "QCycleCountLine",
    "QDamageReport",
    "QExcursion",
    "QExcursionImpact",
    "QFefoCheck",
    "QHold",
    "QHoldLine",
    "QImportBatch",
    "QMappingStudy",
    "QMonitoringPoint",
    "QPestStation",
    "QPestVisit",
    "QPod",
    "QProduct",
    "QReading",
    "QRecall",
    "QRecallItem",
    "QReceipt",
    "QReceiptLine",
    "QReturn",
    "QReturnLine",
    "QShipment",
    "QShipmentLine",
    "QStockLine",
    "QStockSnapshot",
    "QStorageZone",
    "QThroughput",
    "QTrip",
]


# ---- products and imports (§D.1.3, §D.1.4) -------------------------------------------------------


class QProduct(Audited, Base):
    """§D.1.3 product master (sku unique per project and owner)."""

    __tablename__ = "q_products"
    __table_args__ = (UniqueConstraint("project_id", "owner_customer_id", "sku"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_customers.id"))
    sku: Mapped[str] = mapped_column(String(40))
    description_en: Mapped[str] = mapped_column(String(200))
    description_ar: Mapped[str] = mapped_column(String(200), default="")
    gtin: Mapped[str | None] = mapped_column(String(14))
    storage_class: Mapped[QStorageClass] = enum_col(QStorageClass)
    temp_min: Mapped[Decimal | None] = mapped_column(TEMP)
    temp_max: Mapped[Decimal | None] = mapped_column(TEMP)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    min_remaining_shelf_life_pct: Mapped[Decimal | None] = mapped_column(PCT)
    dated: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QImportBatch(Base):
    """§D.1.4 one imported file (stored unchanged with its SHA-256, Q-IMP-01)."""

    __tablename__ = "q_import_batches"
    __table_args__ = (
        Index(
            "uq_q_import_batches_file",
            "project_id",
            "sha256",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'imported'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[QImportKind] = enum_col(QImportKind)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    file_name: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    target_type: Mapped[QImportTarget] = enum_col(QImportTarget)
    target_id: Mapped[uuid.UUID] = mapped_column()
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    first_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QImportStatus] = enum_col(QImportStatus)
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(500))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- storage zones, points, readings (§D.3) ------------------------------------------------------


class QStorageZone(Base):
    """§D.3 storage settings of one Phase 0 zone (PK = zone_id)."""

    __tablename__ = "q_storage_zones"

    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    storage_class: Mapped[QStorageClass] = enum_col(QStorageClass)
    role: Mapped[QZoneRole] = enum_col(QZoneRole, default=QZoneRole.storage)
    temp_min: Mapped[Decimal | None] = mapped_column(TEMP)
    temp_max: Mapped[Decimal | None] = mapped_column(TEMP)
    setpoint: Mapped[Decimal | None] = mapped_column(TEMP)
    humidity_min: Mapped[Decimal | None] = mapped_column(PCT)
    humidity_max: Mapped[Decimal | None] = mapped_column(PCT)
    alarm_delay_minutes: Mapped[int] = mapped_column(Integer)
    d1: Mapped[Decimal] = mapped_column(TEMP)
    d2: Mapped[Decimal] = mapped_column(TEMP)
    t1: Mapped[int] = mapped_column(Integer)
    t2: Mapped[int] = mapped_column(Integer)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    mapping_state: Mapped[QMappingState] = enum_col(QMappingState, default=QMappingState.not_mapped)
    mapped_until: Mapped[date | None] = mapped_column(Date)
    remap_reason: Mapped[str | None] = mapped_column(String(500))
    change_notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QMonitoringGap(Base):
    """Q-STO-04 "monitoring gap" entry: a stretch of at least `monitoring_gap_alert_minutes` in
    which no active point of the zone covered a minute (bounded by monitored minutes on both
    sides); kept in step with the readings by the detection (D-351)."""

    __tablename__ = "q_monitoring_gaps"
    __table_args__ = (UniqueConstraint("zone_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_storage_zones.zone_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minutes: Mapped[int] = mapped_column(Integer)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QZoneDay(Base):
    """Per zone and local day: period, monitored and out minutes of the minute model (D-351), so
    month coverage, time out of range and K-161 / K-162 are sums. Recomputed by the detection for
    the days it touches (imports, manual readings, voids, probe-fault dismissals) and filled on
    first use for days not yet summarised."""

    __tablename__ = "q_zone_days"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("q_storage_zones.zone_id"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    period_minutes: Mapped[int] = mapped_column(Integer)
    monitored_minutes: Mapped[int] = mapped_column(Integer)
    out_minutes: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QMonitoringPoint(Audited, Base):
    """§D.3 a monitoring point of a storage zone with its logger assignments."""

    __tablename__ = "q_monitoring_points"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_storage_zones.zone_id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    position: Mapped[QPointPosition] = enum_col(QPointPosition, default=QPointPosition.general)
    position_note: Mapped[str | None] = mapped_column(String(200))
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    # [{mte_id, from, to}] (ISO timestamps; `to` null = current)
    loggers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QReading(Base):
    """§D.3 one temperature / humidity reading of a point, trip compartment or mapping logger.
    Unique per (target, channel, measured_at) among non-voided rows (Q-IMP-02)."""

    __tablename__ = "q_readings"
    __table_args__ = (
        Index(
            "uq_q_readings_target_time",
            "target_type",
            "target_id",
            "channel",
            "measured_at",
            unique=True,
            postgresql_where=text("voided = false"),
        ),
        Index("ix_q_readings_target", "target_id", "measured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    target_type: Mapped[QReadingTarget] = enum_col(QReadingTarget)
    target_id: Mapped[uuid.UUID] = mapped_column()
    # '' for a point; the compartment code of a trip; the logger position code of a study
    channel: Mapped[str] = mapped_column(String(20), default="")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature_c: Mapped[Decimal | None] = mapped_column(TEMP)
    humidity_pct: Mapped[Decimal | None] = mapped_column(PCT)
    source: Mapped[QReadingSource] = enum_col(QReadingSource)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_import_batches.id"))
    mte_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mte_items.id"))
    entered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    annotation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    probe_fault: Mapped[bool] = mapped_column(Boolean, default=False)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---- excursions (§D.4) ---------------------------------------------------------------------------


class QExcursion(Audited, Base):
    """§D.4 a storage or transit excursion (or a stored transient, Q-EXC-03)."""

    __tablename__ = "q_excursions"
    __table_args__ = (
        UniqueConstraint("project_id", "exc_no"),
        Index("ix_q_excursions_zone_start", "zone_id", "started_at"),
        Index("ix_q_excursions_project_start", "project_id", "started_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    exc_no: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[QExcursionKind] = enum_col(QExcursionKind)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_storage_zones.zone_id"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_trips.id"))
    compartment: Mapped[str | None] = mapped_column(String(20))
    storage_class: Mapped[QStorageClass] = enum_col(QStorageClass)
    transient: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    peak_value: Mapped[Decimal | None] = mapped_column(TEMP)
    peak_point_id: Mapped[uuid.UUID | None] = mapped_column()
    max_deviation: Mapped[Decimal] = mapped_column(TEMP, default=Decimal(0))
    degree_minutes: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    severity: Mapped[QExcursionSeverity] = enum_col(QExcursionSeverity)
    data_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    range_min: Mapped[Decimal | None] = mapped_column(TEMP)
    range_max: Mapped[Decimal | None] = mapped_column(TEMP)
    cause: Mapped[QExcursionCause | None] = enum_col(QExcursionCause, nullable=True)
    cause_note: Mapped[str | None] = mapped_column(String(1000))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_holds.id"))
    status: Mapped[QExcursionStatus] = enum_col(QExcursionStatus)
    no_impact_note: Mapped[str | None] = mapped_column(String(1000))
    reopen_reason: Mapped[str | None] = mapped_column(String(500))
    dismissal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QExcursionImpact(Base):
    """§D.4 one impact-assessment line (one per hold line, Q-EXC-07)."""

    __tablename__ = "q_excursion_impacts"
    __table_args__ = (UniqueConstraint("excursion_id", "hold_line_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    excursion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_excursions.id"), index=True)
    hold_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_hold_lines.id"))
    decision: Mapped[QImpactDecision] = enum_col(QImpactDecision)
    evidence_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    justification: Mapped[str | None] = mapped_column(String(2000))
    owner_decision_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    owner_contact_name: Mapped[str | None] = mapped_column(String(120))
    owner_decision_date: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---- mapping (§D.5) ------------------------------------------------------------------------------


class QMappingStudy(Audited, Base):
    __tablename__ = "q_mapping_studies"
    __table_args__ = (UniqueConstraint("project_id", "map_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    map_no: Mapped[str | None] = mapped_column(String(40))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_storage_zones.zone_id"))
    purpose: Mapped[QMappingPurpose] = enum_col(QMappingPurpose)
    season: Mapped[QSeason] = enum_col(QSeason, default=QSeason.n_a)
    load_state: Mapped[QLoadState] = enum_col(QLoadState, default=QLoadState.loaded)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    # [{mte_id, position_code, description}]
    loggers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{kind, from, to}]
    test_windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    recommended_positions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[QMappingStatus] = enum_col(QMappingStatus, default=QMappingStatus.draft)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_on: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    reject_reason: Mapped[str | None] = mapped_column(String(500))


# ---- hygiene and pest (§D.6) ---------------------------------------------------------------------


class QCheckSchedule(Audited, Base):
    __tablename__ = "q_check_schedules"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    check_type: Mapped[QCheckType] = enum_col(QCheckType)
    template_code: Mapped[str] = mapped_column(String(8))
    frequency: Mapped[QCheckFrequency] = enum_col(QCheckFrequency)
    weekday: Mapped[int | None] = mapped_column(Integer)  # 0 = Monday (ISO - 1)
    start_date: Mapped[date] = mapped_column(Date)
    assignee_role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QPestStation(Audited, Base):
    __tablename__ = "q_pest_stations"
    __table_args__ = (UniqueConstraint("site_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    code: Mapped[str] = mapped_column(String(20))
    station_type: Mapped[QPestStationType] = enum_col(QPestStationType)
    location_note: Mapped[str | None] = mapped_column(String(200))
    provider_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    activity_trend: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class QPestVisit(Audited, Base):
    __tablename__ = "q_pest_visits"
    __table_args__ = (UniqueConstraint("project_id", "visit_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    visit_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    provider_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    technician_name: Mapped[str | None] = mapped_column(String(120))  # personal (P8-1)
    chemicals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{station_id, activity, pest_type, bait_consumed_pct, action}]
    station_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checklist_responses.id"))
    not_serviced: Mapped[list[str]] = mapped_column(STRS, default=list)
    proposals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


# ---- receiving (§D.2) ----------------------------------------------------------------------------


class QReceipt(Audited, Base):
    __tablename__ = "q_receipts"
    __table_args__ = (
        UniqueConstraint("project_id", "rcv_no"),
        Index("ix_q_receipts_project_decided", "project_id", "decided_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    rcv_no: Mapped[str | None] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    dock_zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_customers.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    po_ref: Mapped[str | None] = mapped_column(String(40))
    asn_ref: Mapped[str | None] = mapped_column(String(40))
    vehicle_plate: Mapped[str | None] = mapped_column(String(20))
    reefer_display_c: Mapped[Decimal | None] = mapped_column(TEMP)
    seal_expected: Mapped[str | None] = mapped_column(String(40))
    seal_actual: Mapped[str | None] = mapped_column(String(40))
    seal_intact: Mapped[bool] = mapped_column(Boolean, default=True)
    seal_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    unload_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unload_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dwell_minutes: Mapped[int | None] = mapped_column(Integer)
    vehicle_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checklist_responses.id")
    )
    vehicle_check_passed: Mapped[bool | None] = mapped_column(Boolean)
    transit_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_import_batches.id"))
    qty_deviation_note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[QReceiptStatus] = enum_col(QReceiptStatus, default=QReceiptStatus.draft)
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))


class QReceiptLine(Base):
    __tablename__ = "q_receipt_lines"
    __table_args__ = (UniqueConstraint("receipt_id", "line_no"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_receipts.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_products.id"))
    batch: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    production_date: Mapped[date | None] = mapped_column(Date)
    qty_expected: Mapped[Decimal | None] = mapped_column(QTY)
    qty_received: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    condition: Mapped[QLineCondition] = enum_col(QLineCondition, default=QLineCondition.good)
    labels_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    product_temp_c: Mapped[Decimal | None] = mapped_column(TEMP)
    mte_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mte_items.id"))
    remaining_shelf_life_pct: Mapped[Decimal | None] = mapped_column(PCT)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    proposed_decision: Mapped[QLineDecision | None] = enum_col(QLineDecision, nullable=True)
    proposal_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    criteria_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decision: Mapped[QLineDecision | None] = enum_col(QLineDecision, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000))
    requested_decision: Mapped[QLineDecision | None] = enum_col(QLineDecision, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_approval_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    claim_ref: Mapped[str | None] = mapped_column(String(40))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_holds.id"))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---- stock (§D.7) --------------------------------------------------------------------------------


class QStockSnapshot(Base):
    __tablename__ = "q_stock_snapshots"
    __table_args__ = (Index("ix_q_stock_snapshots_site_asof", "site_id", "as_of"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_import_batches.id"))
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QStockLine(Base):
    __tablename__ = "q_stock_lines"
    __table_args__ = (Index("ix_q_stock_lines_snap_batch", "snapshot_id", "batch"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_stock_snapshots.id"))
    owner_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_products.id"))
    sku: Mapped[str] = mapped_column(String(40))
    batch: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    receipt_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(40))
    zone_code: Mapped[str | None] = mapped_column(String(20))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    wms_status: Mapped[str | None] = mapped_column(String(20))


class QThroughput(Base):
    """Q-STK-03 units handled per site and month (denominator of K-164, K-169)."""

    __tablename__ = "q_throughput"
    __table_args__ = (UniqueConstraint("site_id", "month"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    month: Mapped[date] = mapped_column(Date)
    units_received: Mapped[int] = mapped_column(BigInteger, default=0)
    units_dispatched: Mapped[int] = mapped_column(BigInteger, default=0)
    deliveries: Mapped[int] = mapped_column(Integer, default=0)
    shipments: Mapped[int] = mapped_column(Integer, default=0)
    entered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QFefoCheck(Audited, Base):
    __tablename__ = "q_fefo_checks"
    __table_args__ = (UniqueConstraint("project_id", "check_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    check_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order_ref: Mapped[str | None] = mapped_column(String(40))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_products.id"))
    picked_batch: Mapped[str] = mapped_column(String(40))
    picked_expiry: Mapped[date | None] = mapped_column(Date)
    picked_receipt_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(40))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_stock_snapshots.id"))
    eligible_earliest: Mapped[date | None] = mapped_column(Date)
    eligible_batch: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[QFefoResult] = enum_col(QFefoResult)
    exception_reason: Mapped[QFefoException | None] = enum_col(QFefoException, nullable=True)
    exception_note: Mapped[str | None] = mapped_column(String(500))
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QHold(Audited, Base):
    """§D.7.3 a hold (status derived from its lines and stored)."""

    __tablename__ = "q_holds"
    __table_args__ = (UniqueConstraint("project_id", "hold_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    hold_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    reason: Mapped[QHoldReason] = enum_col(QHoldReason)
    reason_note: Mapped[str | None] = mapped_column(String(1000))
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    source_ref: Mapped[str | None] = mapped_column(String(40))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    zone_level: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_class: Mapped[QStorageClass | None] = enum_col(QStorageClass, nullable=True)
    segregation: Mapped[QSegregation | None] = enum_col(QSegregation, nullable=True)
    segregation_location: Mapped[str | None] = mapped_column(String(40))
    segregation_photo_id: Mapped[uuid.UUID | None] = mapped_column()
    segregation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wms_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    wms_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    placed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lines_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[QHoldStatus] = enum_col(QHoldStatus, default=QHoldStatus.on_hold)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QHoldLine(Base):
    __tablename__ = "q_hold_lines"
    __table_args__ = (Index("ix_q_hold_lines_sku_batch", "sku", "batch"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hold_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_holds.id"), index=True)
    owner_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_products.id"))
    sku: Mapped[str] = mapped_column(String(40))
    batch: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    location: Mapped[str | None] = mapped_column(String(40))
    line_status: Mapped[QHoldLineStatus] = enum_col(
        QHoldLineStatus, default=QHoldLineStatus.on_hold
    )
    proposed_decision: Mapped[QImpactDecision | None] = enum_col(QImpactDecision, nullable=True)
    owner_decision_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    final_outcome: Mapped[QHoldOutcome | None] = enum_col(QHoldOutcome, nullable=True)
    evidence_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(1000))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_receipt_lines.id"))
    stock_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_stock_lines.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QDamageReport(Audited, Base):
    __tablename__ = "q_damage_reports"
    __table_args__ = (UniqueConstraint("project_id", "dmg_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    dmg_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zones.id"))
    stage: Mapped[QDamageStage] = enum_col(QDamageStage)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_products.id"))
    batch: Mapped[str] = mapped_column(String(40))
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    location: Mapped[str | None] = mapped_column(String(40))
    cause: Mapped[QDamageCause] = enum_col(QDamageCause)
    note: Mapped[str | None] = mapped_column(String(1000))
    destroyed_on_spot: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_holds.id"))


class QReturn(Audited, Base):
    __tablename__ = "q_returns"
    __table_args__ = (UniqueConstraint("project_id", "ret_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    ret_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_customers.id"))
    rma_ref: Mapped[str | None] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checklist_responses.id"))
    status: Mapped[QReturnStatus] = enum_col(QReturnStatus, default=QReturnStatus.draft)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_holds.id"))


class QReturnLine(Base):
    __tablename__ = "q_return_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_returns.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_products.id"))
    batch: Mapped[str] = mapped_column(String(40))
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    temp_history: Mapped[bool] = mapped_column(Boolean, default=False)
    temp_history_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    grade: Mapped[QReturnGrade | None] = enum_col(QReturnGrade, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500))


class QCycleCount(Audited, Base):
    __tablename__ = "q_cycle_counts"
    __table_args__ = (UniqueConstraint("project_id", "cc_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    cc_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    zone_codes: Mapped[list[str]] = mapped_column(STRS, default=list)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_import_batches.id"))
    voided: Mapped[bool] = mapped_column(Boolean, default=False)


class QCycleCountLine(Base):
    __tablename__ = "q_cycle_count_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cc_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_cycle_counts.id"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_products.id"))
    sku: Mapped[str] = mapped_column(String(40))
    batch: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(40))
    system_qty: Mapped[Decimal] = mapped_column(QTY)
    counted_qty: Mapped[Decimal] = mapped_column(QTY)
    recount_qty: Mapped[Decimal | None] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")
    tolerance: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))
    within_tolerance: Mapped[bool] = mapped_column(Boolean)
    variance_reason: Mapped[str | None] = mapped_column(String(200))


# ---- recalls (§D.8) ------------------------------------------------------------------------------


class QRecall(Audited, Base):
    __tablename__ = "q_recalls"
    __table_args__ = (UniqueConstraint("project_id", "rcl_no"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    rcl_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    recall_type: Mapped[QRecallType] = enum_col(QRecallType)
    recall_class: Mapped[QRecallClass | None] = enum_col(QRecallClass, nullable=True)
    # [{product_id, sku, batch}]
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    reason: Mapped[str] = mapped_column(String(1000))
    external_ref: Mapped[str | None] = mapped_column(String(60))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trace_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_stock_snapshots.id"))
    effectiveness_pct: Mapped[Decimal | None] = mapped_column(PCT)
    justification: Mapped[str | None] = mapped_column(String(2000))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_holds.id"))
    ncr_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_ncrs.id"))
    status: Mapped[QRecallStatus] = enum_col(QRecallStatus, default=QRecallStatus.open)
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QRecallItem(Base):
    """§D.8 consignee contact of a recall."""

    __tablename__ = "q_recall_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recall_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_recalls.id"), index=True)
    consignee_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    consignee_name: Mapped[str] = mapped_column(String(200))
    qty_shipped: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str | None] = mapped_column(String(40))
    response: Mapped[str | None] = mapped_column(String(500))
    qty_retrieved: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))
    qty_destroyed_by_consignee: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))


# ---- transport (§D.9) ----------------------------------------------------------------------------


class QShipment(Base):
    """Imported shipment (Q-IMP shipments) with its delivery facts for OTIF (Q-TRN-08)."""

    __tablename__ = "q_shipments"
    __table_args__ = (
        UniqueConstraint("project_id", "shipment_ref"),
        Index("ix_q_shipments_project_delivered", "project_id", "delivered_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    shipment_ref: Mapped[str] = mapped_column(String(40))
    owner_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    consignee_customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_customers.id"))
    consignee_name: Mapped[str] = mapped_column(String(200))
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_trips.id"), index=True)
    compartment: Mapped[str | None] = mapped_column(String(20))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_import_batches.id"))
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_consignee: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seed_fake: Mapped[bool] = mapped_column(Boolean, default=False)


class QShipmentLine(Base):
    __tablename__ = "q_shipment_lines"
    __table_args__ = (Index("ix_q_shipment_lines_batch", "batch"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_shipments.id"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_products.id"))
    sku: Mapped[str] = mapped_column(String(40))
    batch: Mapped[str | None] = mapped_column(String(40))
    storage_class: Mapped[QStorageClass | None] = enum_col(QStorageClass, nullable=True)
    ordered_qty: Mapped[Decimal] = mapped_column(QTY)
    delivered_qty: Mapped[Decimal | None] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10), default="unit")


class QTrip(Audited, Base):
    __tablename__ = "q_trips"
    __table_args__ = (
        UniqueConstraint("project_id", "trip_no"),
        Index("ix_q_trips_project_delivered", "project_id", "delivered_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    trip_no: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_suppliers.id"))
    own_fleet: Mapped[bool] = mapped_column(Boolean, default=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    plate_text: Mapped[str | None] = mapped_column(String(20))
    reefer_serial: Mapped[str | None] = mapped_column(String(40))
    # [{code, setpoint, classes, range_min, range_max}]
    compartments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    driver_worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    driver_name: Mapped[str | None] = mapped_column(String(120))  # personal (P8-1)
    logger_mte_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    seal_numbers: Mapped[list[str]] = mapped_column(STRS, default=list)
    planned_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preload_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checklist_responses.id")
    )
    preload_passed: Mapped[bool | None] = mapped_column(Boolean)
    preload_failures: Mapped[list[str]] = mapped_column(STRS, default=list)
    preload_box_temp_c: Mapped[Decimal | None] = mapped_column(TEMP)
    # [{shipment_id, compartment, storage_class, temp_c, mte_id, ok}]
    loading_temps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    override_reason: Mapped[str | None] = mapped_column(String(500))
    override_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    override_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    readiness: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transit_data: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[QTripStatus] = enum_col(QTripStatus, default=QTripStatus.planned)
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    alerts_sent: Mapped[list[str]] = mapped_column(STRS, default=list)


class QPod(Base):
    """Proof of delivery of one shipment (Q-TRN-06)."""

    __tablename__ = "q_pods"
    __table_args__ = (UniqueConstraint("shipment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_trips.id"), index=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("q_shipments.id"))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receiver_name: Mapped[str] = mapped_column(String(120))  # personal (P8-1)
    receiver_role: Mapped[str | None] = mapped_column(String(80))
    signature_attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    seal_intact: Mapped[bool] = mapped_column(Boolean, default=True)
    product_temp_c: Mapped[Decimal | None] = mapped_column(TEMP)
    mte_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("q_mte_items.id"))
    # [{kind, qty, note}]
    exceptions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDS, default=list)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
