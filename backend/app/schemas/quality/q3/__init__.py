"""API schemas of package Q3 logistics: receiving, storage and cold chain, stock, recalls,
transport (spec 8-quality Part D). Every name carries the `Q3` prefix so nothing clashes with
earlier modules in the OpenAPI contract. Temperatures are °C decimals; times are UTC."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.core.quality.common import QCalStatus
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
    QPestActivity,
    QPestStationType,
    QPestType,
    QPodException,
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
    QTestWindowKind,
    QTripStatus,
    QZoneRole,
)
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.field import AnswerInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.quality.q0 import QSignoffRead

Temp = Decimal
Qty = Decimal


# ---- shared refs ---------------------------------------------------------------------------------


class Q3Ref(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str


class Q3CustomerRef(Q3Ref):
    owner_release_approval: bool


class Q3SupplierRef(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    status: str


class Q3MteRef(ApiModel):
    id: uuid.UUID
    mte_no: str
    description: str
    cal_status: QCalStatus
    cal_due_on: date | None


class Q3ProductRef(ApiModel):
    id: uuid.UUID
    sku: str
    description_en: str
    description_ar: str
    storage_class: QStorageClass | None = None
    shelf_life_days: int | None = None
    dated: bool | None = None


class Q3Blocker(ApiModel):
    code: str
    detail_en: str
    detail_ar: str


class Q3ChecklistResponse(ApiModel):
    id: uuid.UUID
    template_code: str
    template_version: int
    completed_at: datetime | None
    score_pct: Decimal | None
    result: str | None
    critical_fail_count: int
    answers: list[dict[str, Any]]


class Q3AnswersInput(StrictInput):
    answers: list[AnswerInput] = Field(min_length=1, max_length=200)
    template_code: str | None = Field(default=None, max_length=8)


# ---- products ------------------------------------------------------------------------------------


class Q3ProductCreate(StrictInput):
    owner_customer_id: uuid.UUID
    sku: str = Field(min_length=1, max_length=40)
    description_en: str = Field(min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=200)
    gtin: str | None = Field(default=None, max_length=14)
    storage_class: QStorageClass
    temp_min: Temp | None = None
    temp_max: Temp | None = None
    shelf_life_days: int | None = Field(default=None, ge=1, le=10000)
    min_remaining_shelf_life_pct: Decimal | None = None
    dated: bool = True


class Q3ProductUpdate(StrictInput):
    description_en: str | None = Field(default=None, max_length=200)
    description_ar: str | None = Field(default=None, max_length=200)
    gtin: str | None = Field(default=None, max_length=14)
    storage_class: QStorageClass | None = None
    temp_min: Temp | None = None
    temp_max: Temp | None = None
    shelf_life_days: int | None = Field(default=None, ge=1, le=10000)
    min_remaining_shelf_life_pct: Decimal | None = None
    dated: bool | None = None
    active: bool | None = None


class Q3ProductRead(ApiModel):
    id: uuid.UUID
    sku: str
    owner: Q3CustomerRef | None
    description_en: str
    description_ar: str
    gtin: str | None
    storage_class: QStorageClass
    temp_min: Temp | None
    temp_max: Temp | None
    shelf_life_days: int | None
    min_remaining_shelf_life_pct: Decimal | None
    dated: bool
    active: bool


# ---- imports -------------------------------------------------------------------------------------


class Q3ImportRead(ApiModel):
    id: uuid.UUID
    kind: QImportKind
    file_name: str
    sha256: str
    attachment_id: uuid.UUID | None
    target_type: QImportTarget
    target_id: uuid.UUID
    profile: dict[str, Any]
    rows_read: int
    rows_accepted: int
    rows_rejected: int
    errors: list[dict[str, Any]] = Field(description="[{row, reason}] (row 1 is the header).")
    first_at: datetime | None
    last_at: datetime | None
    status: QImportStatus
    imported_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    voidable: bool


class Q3ExcursionBrief(ApiModel):
    id: uuid.UUID
    exc_no: str | None
    severity: QExcursionSeverity
    status: QExcursionStatus
    started_at: datetime
    ended_at: datetime | None
    duration_min: int


class Q3ImportResult(Q3ImportRead):
    excursions: list[Q3ExcursionBrief] = Field(default_factory=list)
    snapshot_id: uuid.UUID | None = None
    shipments: int | None = None
    products_created: int | None = None
    products_updated: int | None = None
    cycle_count_id: uuid.UUID | None = None


class Q3ImportPage(Page[Q3ImportRead]):
    pass


class Q3ImportPreview(ApiModel):
    columns: list[str]
    rows: int
    sample: list[dict[str, Any]]
    profile: dict[str, Any]


class Q3VoidInput(StrictInput):
    reason: str = Field(min_length=20, max_length=500)


# ---- storage -------------------------------------------------------------------------------------


class Q3LoggerAssignment(ApiModel):
    mte_id: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None
    mte: Q3MteRef | None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class Q3PointRead(ApiModel):
    id: uuid.UUID
    zone_id: uuid.UUID
    code: str
    position: QPointPosition
    position_note: str | None
    interval_minutes: int
    loggers: list[dict[str, Any]]
    active: bool


class Q3ZoneRead(ApiModel):
    zone_id: uuid.UUID
    project_id: uuid.UUID
    site: Q3Ref | None
    code: str
    name_en: str
    name_ar: str
    storage_class: QStorageClass
    role: QZoneRole
    temp_min: Temp | None
    temp_max: Temp | None
    setpoint: Temp | None
    humidity_min: Decimal | None
    humidity_max: Decimal | None
    alarm_delay_minutes: int
    d1: Decimal
    d2: Decimal
    t1: int
    t2: int
    interval_minutes: int
    mapping_state: QMappingState
    mapped_until: date | None
    remap_reason: str | None
    change_notes: list[dict[str, Any]]
    dispatch_override_allowed: bool
    active: bool
    points: list[Q3PointRead]
    live_status: Literal["in_range", "excursion", "gap", "not_mapped"] | None = None


class Q3ZoneCreate(StrictInput):
    zone_id: uuid.UUID
    storage_class: QStorageClass
    role: QZoneRole = QZoneRole.storage
    setpoint: Temp | None = None
    temp_min: Temp | None = None
    temp_max: Temp | None = None
    humidity_min: Decimal | None = None
    humidity_max: Decimal | None = None
    alarm_delay_minutes: int | None = Field(default=None, ge=0, le=1440)
    d1: Decimal | None = None
    d2: Decimal | None = None
    t1: int | None = Field(default=None, ge=1)
    t2: int | None = Field(default=None, ge=1)
    interval_minutes: int | None = Field(default=None, ge=1, le=240)


class Q3ZoneUpdate(StrictInput):
    storage_class: QStorageClass | None = None
    role: QZoneRole | None = None
    setpoint: Temp | None = None
    temp_min: Temp | None = None
    temp_max: Temp | None = None
    humidity_min: Decimal | None = None
    humidity_max: Decimal | None = None
    alarm_delay_minutes: int | None = Field(default=None, ge=0, le=1440)
    d1: Decimal | None = None
    d2: Decimal | None = None
    t1: int | None = Field(default=None, ge=1)
    t2: int | None = Field(default=None, ge=1)
    interval_minutes: int | None = Field(default=None, ge=1, le=240)
    active: bool | None = None


class Q3ChangeNote(StrictInput):
    kind: Literal["layout", "hvac"]
    note: str = Field(min_length=20, max_length=1000)


class Q3PointCreate(StrictInput):
    code: str = Field(min_length=1, max_length=20)
    position: QPointPosition = QPointPosition.general
    position_note: str | None = Field(default=None, max_length=200)
    interval_minutes: int | None = Field(default=None, ge=1, le=240)


class Q3PointUpdate(StrictInput):
    position: QPointPosition | None = None
    position_note: str | None = Field(default=None, max_length=200)
    interval_minutes: int | None = Field(default=None, ge=1, le=240)
    active: bool | None = None


class Q3LoggerAssign(StrictInput):
    mte_id: uuid.UUID
    from_: datetime | None = Field(default=None, alias="from")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Q3PointWithWarnings(Q3PointRead):
    warnings: list[ApiWarning] = Field(default_factory=list)


class Q3ManualReading(StrictInput):
    measured_at: datetime
    temperature_c: Temp | None = Field(default=None, ge=-80, le=80)
    humidity_pct: Decimal | None = Field(default=None, ge=0, le=100)
    mte_id: uuid.UUID | None = None


class Q3ReadingRead(ApiModel):
    id: int
    target_type: QReadingTarget
    target_id: uuid.UUID
    channel: str
    measured_at: datetime
    temperature_c: Temp | None
    humidity_pct: Decimal | None
    source: QReadingSource
    batch_id: uuid.UUID | None
    mte_id: uuid.UUID | None
    annotation: dict[str, Any] | None
    probe_fault: bool


class Q3ManualReadingResult(ApiModel):
    reading: Q3ReadingRead
    excursions: list[Q3ExcursionBrief]
    warnings: list[ApiWarning]


class Q3Annotation(StrictInput):
    text: str = Field(min_length=5, max_length=500)


class Q3ZoneReport(ApiModel):
    zone: Q3ZoneRead
    start: datetime
    end: datetime
    period_minutes: int
    monitored_minutes: int
    out_minutes: int
    coverage_pct: Decimal | None
    tor_pct: Decimal | None
    gaps: list[dict[str, Any]]
    series: list[dict[str, Any]] = Field(
        description="Per point: {point_id, code, values: [{t, c, rh, fault}], mkt}."
    )
    excursions: list[dict[str, Any]]


# ---- excursions ----------------------------------------------------------------------------------


class Q3ExcursionListItem(Q3ExcursionBrief):
    kind: QExcursionKind
    zone: Q3Ref | None
    trip_id: uuid.UUID | None
    storage_class: QStorageClass
    peak_value: Temp | None
    max_deviation: Decimal
    data_gap: bool
    acknowledged: bool
    ncr_id: uuid.UUID | None
    hold_id: uuid.UUID | None


class Q3ExcursionPage(Page[Q3ExcursionListItem]):
    pass


class Q3HoldLineRead(ApiModel):
    id: uuid.UUID
    owner: Q3CustomerRef | None
    product_id: uuid.UUID | None
    sku: str
    description_en: str | None
    description_ar: str | None
    batch: str
    expiry_date: date | None
    qty: Qty
    unit: str
    location: str | None
    line_status: QHoldLineStatus
    proposed_decision: QImpactDecision | None
    owner_decision_attachment_id: uuid.UUID | None
    final_outcome: QHoldOutcome | None
    evidence_attachment_id: uuid.UUID | None
    outcome_at: datetime | None
    reason: str | None
    decided_at: datetime | None


class Q3ImpactLineRead(ApiModel):
    hold_line: Q3HoldLineRead
    decision: QImpactDecision | None
    justification: str | None
    evidence_attachment_id: uuid.UUID | None
    owner_decision_attachment_id: uuid.UUID | None
    owner_contact_name: str | None
    owner_decision_date: date | None


class Q3NcrRef(ApiModel):
    id: uuid.UUID
    ncr_no: str | None
    status: str
    classification: str | None


class Q3HoldRef(ApiModel):
    id: uuid.UUID
    hold_no: str
    status: QHoldStatus
    zone_level: bool


class Q3TripRef(ApiModel):
    id: uuid.UUID
    trip_no: str


class Q3ExcursionRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    exc_no: str | None
    kind: QExcursionKind
    site: Q3Ref | None
    zone: Q3Ref | None
    trip: Q3TripRef | None
    compartment: str | None
    storage_class: QStorageClass
    transient: bool
    started_at: datetime
    ended_at: datetime | None
    duration_min: int
    peak_value: Temp | None
    peak_point: str | None
    max_deviation: Decimal
    degree_minutes: Decimal
    severity: QExcursionSeverity
    data_gap: bool
    range_min: Temp | None
    range_max: Temp | None
    cause: QExcursionCause | None
    cause_note: str | None
    status: QExcursionStatus
    impact_required: bool
    no_impact_note: str | None
    dismissal: dict[str, Any] | None
    acknowledged_at: datetime | None
    acknowledged_by: UserRef | None
    detected_at: datetime
    assessed_at: datetime | None
    closed_at: datetime | None
    ncr: Q3NcrRef | None
    hold: Q3HoldRef | None
    impact_lines: list[Q3ImpactLineRead]
    allowed_actions: list[str]
    signoffs: list[QSignoffRead]


class Q3CauseInput(StrictInput):
    cause: QExcursionCause
    cause_note: str | None = Field(default=None, max_length=1000)


class Q3ImpactLineInput(StrictInput):
    hold_line_id: uuid.UUID
    decision: QImpactDecision
    justification: str | None = Field(default=None, max_length=2000)
    evidence_attachment_id: uuid.UUID | None = None
    owner_decision_attachment_id: uuid.UUID | None = None
    owner_contact_name: str | None = Field(default=None, max_length=120)
    owner_decision_date: date | None = None


class Q3ImpactsInput(StrictInput):
    lines: list[Q3ImpactLineInput] = Field(max_length=2000)


class Q3AssessInput(StrictInput):
    lines: list[Q3ImpactLineInput] | None = Field(default=None, max_length=2000)
    decision: Literal["approved", "returned"] = "approved"
    comment: str | None = Field(default=None, max_length=1000)


class Q3ReasonInput(StrictInput):
    reason: str = Field(min_length=20, max_length=500)


class Q3NoteInput(StrictInput):
    note: str = Field(min_length=20, max_length=1000)


class Q3DismissInput(StrictInput):
    evidence_kind: Literal["calibration_check", "second_instrument"]
    mte_id: uuid.UUID
    second_mte_id: uuid.UUID | None = None
    error_c: Decimal | None = None
    attachment_id: uuid.UUID | None = None
    note: str = Field(min_length=20, max_length=1000)


# ---- holds ---------------------------------------------------------------------------------------


class Q3HoldLineInput(StrictInput):
    owner_customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    sku: str | None = Field(default=None, max_length=40)
    batch: str = Field(min_length=1, max_length=40)
    expiry_date: date | None = None
    qty: Qty = Field(gt=0)
    unit: str = Field(default="unit", max_length=10)
    location: str | None = Field(default=None, max_length=40)


class Q3HoldCreate(StrictInput):
    site_id: uuid.UUID
    reason: QHoldReason
    reason_note: str | None = Field(default=None, max_length=1000)
    zone_id: uuid.UUID | None = None
    zone_level: bool = False
    ncr_id: uuid.UUID | None = None
    lines: list[Q3HoldLineInput] = Field(default_factory=list, max_length=2000)


class Q3HoldLinesInput(StrictInput):
    lines: list[Q3HoldLineInput] = Field(min_length=1, max_length=2000)


class Q3SegregationInput(StrictInput):
    segregation: QSegregation
    location: str | None = Field(default=None, max_length=40)
    photo_attachment_id: uuid.UUID


class Q3HoldDecide(StrictInput):
    action: Literal["release", "reject"]
    line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)
    reason: str | None = Field(default=None, max_length=1000)
    comment: str | None = Field(default=None, max_length=1000)
    owner_decision_attachment_id: uuid.UUID | None = None


class Q3OutcomeInput(StrictInput):
    outcome: QHoldOutcome
    evidence_attachment_id: uuid.UUID
    at: datetime | None = None


class Q3HoldRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    hold_no: str
    site: Q3Ref | None
    zone: Q3Ref | None
    reason: QHoldReason
    reason_note: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    source_ref: str | None
    ncr_id: uuid.UUID | None
    zone_level: bool
    storage_class: QStorageClass | None
    segregation: QSegregation | None
    segregation_location: str | None
    segregation_photo_id: uuid.UUID | None
    segregation_at: datetime | None
    wms_confirmed: bool
    wms_confirmed_at: datetime | None
    placed_by: UserRef | None
    placed_at: datetime
    status: QHoldStatus
    age_days: int
    lines: list[Q3HoldLineRead]
    blockers: list[Q3Blocker]
    allowed_actions: list[str]
    signoffs: list[QSignoffRead]


class Q3HoldListItem(ApiModel):
    id: uuid.UUID
    hold_no: str
    reason: QHoldReason
    status: QHoldStatus
    zone: Q3Ref | None
    zone_level: bool
    source_ref: str | None
    placed_at: datetime
    age_days: int
    lines: int
    lines_on_hold: int
    qty_on_hold: Qty
    blocked: bool
    segregated: bool
    wms_confirmed: bool


class Q3HoldPage(Page[Q3HoldListItem]):
    pass


# ---- receiving -----------------------------------------------------------------------------------


class Q3ReceiptLineInput(StrictInput):
    product_id: uuid.UUID | None = None
    batch: str | None = Field(default=None, max_length=40)
    expiry_date: date | None = None
    production_date: date | None = None
    qty_expected: Qty | None = Field(default=None, ge=0)
    qty_received: Qty | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=10)
    condition: QLineCondition | None = None
    labels_ok: bool | None = None
    product_temp_c: Temp | None = Field(default=None, ge=-80, le=80)
    mte_id: uuid.UUID | None = None
    sample_count: int | None = Field(default=None, ge=0)


class Q3ReceiptHeader(StrictInput):
    dock_zone_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    carrier_id: uuid.UUID | None = None
    po_ref: str | None = Field(default=None, max_length=40)
    asn_ref: str | None = Field(default=None, max_length=40)
    vehicle_plate: str | None = Field(default=None, max_length=20)
    reefer_display_c: Temp | None = None
    seal_expected: str | None = Field(default=None, max_length=40)
    seal_actual: str | None = Field(default=None, max_length=40)
    seal_intact: bool | None = None
    expected_at: datetime | None = None
    arrived_at: datetime | None = None
    unload_start: datetime | None = None
    unload_end: datetime | None = None
    qty_deviation_note: str | None = Field(default=None, max_length=500)


class Q3ReceiptCreate(Q3ReceiptHeader):
    site_id: uuid.UUID
    dock_zone_id: uuid.UUID
    customer_id: uuid.UUID
    lines: list[Q3ReceiptLineInput] = Field(default_factory=list, max_length=200)


class Q3LineDecide(StrictInput):
    decision: QLineDecision | None = None
    reason: str | None = Field(default=None, max_length=1000)
    owner_approval_attachment_id: uuid.UUID | None = None
    claim_ref: str | None = Field(default=None, max_length=40)
    ncr_id: uuid.UUID | None = None
    raise_ncr: bool = False
    request: bool = Field(
        default=False,
        description="Ask the responsible person to sign when you do not resolve for the step.",
    )


class Q3ReceiptLineRead(ApiModel):
    id: uuid.UUID
    line_no: int
    product: Q3ProductRef | None
    batch: str
    expiry_date: date | None
    production_date: date | None
    qty_expected: Qty | None
    qty_received: Qty
    unit: str
    condition: QLineCondition
    labels_ok: bool
    product_temp_c: Temp | None
    mte: Q3MteRef | None
    remaining_shelf_life_pct: Decimal | None
    sample_count: int | None
    sample_hint: int | None = Field(
        description="ISO 2859-1 general level II single sampling `[VERIFY]`."
    )
    proposed_decision: QLineDecision | None
    proposal_reasons: list[dict[str, Any]]
    criteria_versions: dict[str, Any]
    decision: QLineDecision | None
    requested_decision: QLineDecision | None
    reason: str | None
    ncr_id: uuid.UUID | None
    claim_ref: str | None
    hold_id: uuid.UUID | None
    owner_approval_attachment_id: uuid.UUID | None
    decided_at: datetime | None


class Q3ReceiptRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    rcv_no: str | None
    site: Q3Ref | None
    dock_zone: Q3Ref | None
    customer: Q3CustomerRef | None
    supplier: Q3SupplierRef | None
    carrier: Q3SupplierRef | None
    po_ref: str | None
    asn_ref: str | None
    vehicle_plate: str | None
    reefer_display_c: Temp | None
    seal_expected: str | None
    seal_actual: str | None
    seal_intact: bool
    seal_flag: bool
    expected_at: datetime | None
    arrived_at: datetime
    unload_start: datetime | None
    unload_end: datetime | None
    dwell_minutes: int | None
    dwell_limit_minutes: int
    temp_controlled: bool
    vehicle_check: Q3ChecklistResponse | None
    transit_batch_id: uuid.UUID | None
    qty_deviation_note: str | None
    status: QReceiptStatus
    inspected_at: datetime | None
    decided_at: datetime | None
    cancel_reason: str | None
    created_by: UserRef | None
    lines: list[Q3ReceiptLineRead]
    my_steps: list[str]
    signoffs: list[QSignoffRead]
    warnings: list[ApiWarning] = Field(default_factory=list)
    signoff_id: uuid.UUID | None = None


class Q3ReceiptListItem(ApiModel):
    id: uuid.UUID
    rcv_no: str | None
    status: QReceiptStatus
    customer: Q3CustomerRef | None
    supplier: Q3SupplierRef | None
    arrived_at: datetime
    asn_ref: str | None
    lines: int
    decisions: list[str]
    pending_signoff: bool
    seal_flag: bool
    dwell_minutes: int | None
    dwell_long: bool


class Q3ReceiptPage(Page[Q3ReceiptListItem]):
    pass


# ---- mapping -------------------------------------------------------------------------------------


class Q3MappingLogger(StrictInput):
    mte_id: uuid.UUID
    position_code: str = Field(min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)


class Q3TestWindow(StrictInput):
    kind: QTestWindowKind
    from_: datetime = Field(alias="from")
    to: datetime

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Q3MappingInput(StrictInput):
    purpose: QMappingPurpose | None = None
    season: QSeason | None = None
    load_state: QLoadState | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=60)
    lead_user_id: uuid.UUID | None = None
    loggers: list[Q3MappingLogger] | None = Field(default=None, max_length=200)
    test_windows: list[Q3TestWindow] | None = Field(default=None, max_length=50)


class Q3MappingCreate(Q3MappingInput):
    zone_id: uuid.UUID
    purpose: QMappingPurpose


class Q3ApproveInput(StrictInput):
    decision: Literal["approved", "returned"] = "approved"
    comment: str | None = Field(default=None, max_length=1000)
    approved_on: date | None = None


class Q3MappingRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    map_no: str | None
    zone: dict[str, Any]
    purpose: QMappingPurpose
    season: QSeason
    load_state: QLoadState
    planned_start: datetime | None
    planned_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    interval_minutes: int
    loggers: list[dict[str, Any]]
    test_windows: list[dict[str, Any]]
    lead: UserRef | None
    results: dict[str, Any] | None
    passed: bool | None
    recommended_positions: list[dict[str, Any]]
    report_attachment_id: uuid.UUID | None
    status: QMappingStatus
    approved_on: date | None
    valid_until: date | None
    reject_reason: str | None
    can_approve: bool
    signoffs: list[QSignoffRead]
    warnings: list[ApiWarning] = Field(default_factory=list)


class Q3MappingListItem(ApiModel):
    id: uuid.UUID
    map_no: str | None
    zone_code: str
    purpose: QMappingPurpose
    season: QSeason
    status: QMappingStatus
    passed: bool | None
    loggers: int
    planned_start: datetime | None
    planned_end: datetime | None
    valid_until: date | None


# ---- hygiene and pest ----------------------------------------------------------------------------


class Q3ScheduleCreate(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    check_type: QCheckType
    template_code: str | None = Field(default=None, max_length=8)
    frequency: QCheckFrequency
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_date: date | None = None
    assignee_role: str | None = Field(default=None, max_length=40)


class Q3ScheduleUpdate(StrictInput):
    frequency: QCheckFrequency | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    assignee_role: str | None = Field(default=None, max_length=40)
    active: bool | None = None


class Q3SchedulePeriod(ApiModel):
    from_: date = Field(alias="from")
    to: date
    status: Literal["done", "due", "overdue"]

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class Q3ScheduleRead(ApiModel):
    id: uuid.UUID
    site: Q3Ref | None
    zone: Q3Ref | None
    check_type: QCheckType
    template_code: str
    frequency: QCheckFrequency
    weekday: int | None
    start_date: date
    assignee_role: str
    active: bool
    current: dict[str, Any] | None
    overdue: list[dict[str, Any]]
    recent: list[dict[str, Any]]


class Q3CheckRunInput(StrictInput):
    answers: list[AnswerInput] = Field(min_length=1, max_length=200)
    completed_at: datetime | None = None


class Q3CheckRunResult(ApiModel):
    response: Q3ChecklistResponse | None
    passed: bool
    proposals: list[dict[str, Any]]


class Q3StationCreate(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    code: str = Field(min_length=1, max_length=20)
    station_type: QPestStationType
    location_note: str | None = Field(default=None, max_length=200)
    provider_supplier_id: uuid.UUID | None = None


class Q3StationRead(ApiModel):
    id: uuid.UUID
    code: str
    site_id: uuid.UUID
    zone: Q3Ref | None
    station_type: QPestStationType
    location_note: str | None
    provider: Q3SupplierRef | None
    activity_trend: bool
    active: bool


class Q3StationResult(StrictInput):
    station_id: uuid.UUID
    activity: QPestActivity = QPestActivity.none
    pest_type: QPestType | None = None
    bait_consumed_pct: int | None = Field(default=None, ge=0, le=100)
    action: str | None = Field(default=None, max_length=200)


class Q3Chemical(StrictInput):
    product: str = Field(max_length=120)
    registration_no: str | None = Field(default=None, max_length=60)
    quantity: str | None = Field(default=None, max_length=40)


class Q3VisitCreate(StrictInput):
    site_id: uuid.UUID
    provider_supplier_id: uuid.UUID | None = None
    visited_at: datetime | None = None
    technician_name: str | None = Field(default=None, max_length=120)
    chemicals: list[Q3Chemical] = Field(default_factory=list, max_length=50)
    station_results: list[Q3StationResult] = Field(default_factory=list, max_length=1000)
    answers: list[AnswerInput] | None = Field(default=None, max_length=200)


class Q3VisitRead(ApiModel):
    id: uuid.UUID
    visit_no: str
    site_id: uuid.UUID
    provider: Q3SupplierRef | None
    visited_at: datetime
    technician_name: str | None
    chemicals: list[dict[str, Any]]
    station_results: list[dict[str, Any]]
    not_serviced: list[str]
    proposals: list[dict[str, Any]]
    response_id: uuid.UUID | None
    warnings: list[ApiWarning] = Field(default_factory=list)


# ---- stock ---------------------------------------------------------------------------------------


class Q3SnapshotRead(ApiModel):
    id: uuid.UUID
    site: Q3Ref | None
    as_of: datetime
    line_count: int
    batch_id: uuid.UUID | None


class Q3NearExpiryItem(ApiModel):
    kind: Literal["expired", "near_expiry"]
    stock_line_id: uuid.UUID
    owner: Q3CustomerRef | None
    sku: str
    product_id: uuid.UUID | None
    batch: str
    expiry_date: date
    days_left: int
    location: str
    zone_code: str | None
    qty: Qty
    unit: str
    on_hold: bool
    site_id: uuid.UUID


class Q3NearExpiry(ApiModel):
    snapshots: list[Q3SnapshotRead]
    items: list[Q3NearExpiryItem]
    near_expiry_days: int
    near_expiry_pct: Decimal


class Q3ExpiryHoldInput(StrictInput):
    stock_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class Q3FefoCreate(StrictInput):
    site_id: uuid.UUID
    product_id: uuid.UUID
    picked_batch: str = Field(min_length=1, max_length=40)
    picked_expiry: date | None = None
    picked_receipt_date: date | None = None
    location: str | None = Field(default=None, max_length=40)
    order_ref: str | None = Field(default=None, max_length=40)
    checked_at: datetime | None = None
    exception_reason: QFefoException | None = None
    exception_note: str | None = Field(default=None, max_length=500)


class Q3FefoRead(ApiModel):
    id: uuid.UUID
    check_no: str
    site_id: uuid.UUID
    checked_at: datetime
    order_ref: str | None
    product: Q3ProductRef | None
    picked_batch: str
    picked_expiry: date | None
    picked_receipt_date: date | None
    location: str | None
    eligible_earliest: date | None
    eligible_batch: str | None
    result: QFefoResult
    exception_reason: QFefoException | None
    exception_note: str | None
    confirmed: bool
    counts_compliant: bool
    recorded_by: UserRef | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class Q3FefoPage(Page[Q3FefoRead]):
    pass


class Q3DamageCreate(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    stage: QDamageStage
    product_id: uuid.UUID
    batch: str = Field(min_length=1, max_length=40)
    qty: Qty = Field(gt=0)
    unit: str = Field(default="unit", max_length=10)
    location: str | None = Field(default=None, max_length=40)
    cause: QDamageCause
    note: str | None = Field(default=None, max_length=1000)
    destroyed_on_spot: bool = False
    owner_notified_at: datetime | None = None
    reported_at: datetime | None = None


class Q3DamageRead(ApiModel):
    id: uuid.UUID
    dmg_no: str
    site_id: uuid.UUID
    zone: Q3Ref | None
    stage: QDamageStage
    product: Q3ProductRef | None
    batch: str
    qty: Qty
    unit: str
    location: str | None
    cause: QDamageCause
    note: str | None
    destroyed_on_spot: bool
    owner_notified_at: datetime | None
    reported_at: datetime
    hold_id: uuid.UUID | None
    reported_by: UserRef | None


class Q3DamagePage(Page[Q3DamageRead]):
    pass


class Q3CountLineInput(StrictInput):
    product_id: uuid.UUID | None = None
    sku: str = Field(min_length=1, max_length=40)
    batch: str | None = Field(default=None, max_length=40)
    location: str = Field(min_length=1, max_length=40)
    zone_code: str | None = Field(default=None, max_length=20)
    system_qty: Qty
    counted_qty: Qty
    recount_qty: Qty | None = None
    tolerance: Qty | None = None
    unit: str | None = Field(default=None, max_length=10)
    variance_reason: str | None = Field(default=None, max_length=200)


class Q3CountCreate(StrictInput):
    site_id: uuid.UUID
    counted_at: datetime | None = None
    zone_codes: list[str] | None = None
    lines: list[Q3CountLineInput] = Field(min_length=1, max_length=5000)


class Q3CountRead(ApiModel):
    id: uuid.UUID
    cc_no: str
    site_id: uuid.UUID
    counted_at: datetime
    zone_codes: list[str]
    lines_counted: int
    lines_within: int
    ira_pct: Decimal | None
    lines: list[dict[str, Any]]


class Q3ThroughputInput(StrictInput):
    site_id: uuid.UUID
    month: date
    units_received: int | None = Field(default=None, ge=0)
    units_dispatched: int | None = Field(default=None, ge=0)
    deliveries: int | None = Field(default=None, ge=0)
    shipments: int | None = Field(default=None, ge=0)


class Q3ThroughputRead(ApiModel):
    id: uuid.UUID
    site_id: uuid.UUID
    month: date
    units_received: int
    units_dispatched: int
    deliveries: int
    shipments: int


# ---- returns -------------------------------------------------------------------------------------


class Q3ReturnLineInput(StrictInput):
    product_id: uuid.UUID
    batch: str = Field(min_length=1, max_length=40)
    qty: Qty = Field(gt=0)
    unit: str = Field(default="unit", max_length=10)
    temp_history: bool = False


class Q3ReturnCreate(StrictInput):
    site_id: uuid.UUID
    customer_id: uuid.UUID
    rma_ref: str | None = Field(default=None, max_length=40)
    received_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)
    lines: list[Q3ReturnLineInput] = Field(min_length=1, max_length=500)


class Q3GradeLine(StrictInput):
    line_id: uuid.UUID
    grade: QReturnGrade
    temp_history: bool | None = None
    temp_history_attachment_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class Q3GradeInput(StrictInput):
    lines: list[Q3GradeLine] = Field(min_length=1, max_length=500)


class Q3CommentInput(StrictInput):
    comment: str | None = Field(default=None, max_length=1000)


class Q3ReturnRead(ApiModel):
    id: uuid.UUID
    ret_no: str
    site_id: uuid.UUID
    customer: Q3CustomerRef | None
    rma_ref: str | None
    received_at: datetime
    reason: str | None
    status: QReturnStatus
    inspection: Q3ChecklistResponse | None
    lines: list[dict[str, Any]]
    hold_id: uuid.UUID | None
    can_confirm: bool
    signoffs: list[QSignoffRead]


class Q3ReturnListItem(ApiModel):
    id: uuid.UUID
    ret_no: str
    customer: Q3CustomerRef | None
    rma_ref: str | None
    received_at: datetime
    status: QReturnStatus
    lines: int
    grades: list[str]


class Q3ReturnPage(Page[Q3ReturnListItem]):
    pass


# ---- recalls -------------------------------------------------------------------------------------


class Q3RecallItemInput(StrictInput):
    product_id: uuid.UUID | None = None
    sku: str | None = Field(default=None, max_length=40)
    batch: str = Field(min_length=1, max_length=40)


class Q3RecallCreate(StrictInput):
    site_id: uuid.UUID
    recall_type: QRecallType
    recall_class: QRecallClass | None = None
    items: list[Q3RecallItemInput] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=10, max_length=1000)
    external_ref: str | None = Field(default=None, max_length=60)
    supplier_id: uuid.UUID | None = None
    initiated_at: datetime | None = None


class Q3TraceConfirm(StrictInput):
    completed_at: datetime | None = None


class Q3RecallContactUpdate(StrictInput):
    contacted_at: datetime | None = None
    method: str | None = Field(default=None, max_length=40)
    response: str | None = Field(default=None, max_length=500)
    qty_retrieved: Qty | None = Field(default=None, ge=0)
    qty_destroyed_by_consignee: Qty | None = Field(default=None, ge=0)


class Q3RecallClose(StrictInput):
    justification: str | None = Field(default=None, max_length=2000)
    comment: str | None = Field(default=None, max_length=1000)


class Q3RecallRead(ApiModel):
    id: uuid.UUID
    rcl_no: str
    site_id: uuid.UUID
    recall_type: QRecallType
    recall_class: QRecallClass | None
    items: list[dict[str, Any]]
    reason: str
    external_ref: str | None
    supplier: Q3SupplierRef | None
    initiated_at: datetime
    status: QRecallStatus
    trace: dict[str, Any] = Field(
        description="Live trace: received, on_hand, shipped, destroyed, unaccounted, consignees, "
        "snapshot."
    )
    trace_confirmed: dict[str, Any] | None
    trace_completed_at: datetime | None
    trace_minutes: int | None
    trace_target_hours: int
    trace_slow: bool
    effectiveness_pct: Decimal | None
    effectiveness_target_pct: Decimal
    justification: str | None
    hold_id: uuid.UUID | None
    ncr_id: uuid.UUID | None
    cancel_reason: str | None
    closed_at: datetime | None
    consignee_contacts: list[dict[str, Any]]
    can_close: bool
    warnings: list[dict[str, Any]]
    created_by: UserRef | None
    signoffs: list[QSignoffRead]


class Q3RecallListItem(ApiModel):
    id: uuid.UUID
    rcl_no: str
    recall_type: QRecallType
    recall_class: QRecallClass | None
    batches: list[str]
    status: QRecallStatus
    initiated_at: datetime
    effectiveness_pct: Decimal | None
    trace_minutes: int | None


# ---- transport -----------------------------------------------------------------------------------


class Q3CompartmentInput(StrictInput):
    code: str = Field(min_length=1, max_length=20)
    setpoint: Temp | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=60)


class Q3TripShipment(StrictInput):
    shipment_id: uuid.UUID
    compartment: str | None = Field(default=None, max_length=20)


class Q3TripCreate(StrictInput):
    site_id: uuid.UUID
    carrier_id: uuid.UUID | None = None
    own_fleet: bool = False
    vehicle_id: uuid.UUID | None = None
    plate_text: str | None = Field(default=None, max_length=20)
    reefer_serial: str | None = Field(default=None, max_length=40)
    compartments: list[Q3CompartmentInput] = Field(default_factory=list, max_length=6)
    driver_worker_id: uuid.UUID | None = None
    driver_name: str | None = Field(default=None, max_length=120)
    logger_mte_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    seal_numbers: list[str] = Field(default_factory=list, max_length=10)
    planned_departure: datetime | None = None
    shipments: list[Q3TripShipment] = Field(min_length=1, max_length=200)


class Q3LoadingTemp(StrictInput):
    shipment_id: uuid.UUID
    temp_c: Temp = Field(ge=-80, le=80)
    mte_id: uuid.UUID | None = None


class Q3PreloadInput(StrictInput):
    answers: list[AnswerInput] = Field(min_length=1, max_length=200)
    template_code: str | None = Field(default=None, max_length=8)
    box_temp_c: Temp | None = Field(default=None, ge=-80, le=80)
    loading_temps: list[Q3LoadingTemp] = Field(default_factory=list, max_length=500)


class Q3DispatchInput(StrictInput):
    override_reason: str | None = Field(default=None, max_length=500)
    request_override: bool = False
    departed_at: datetime | None = None


class Q3PodException(StrictInput):
    kind: QPodException
    qty: Qty | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class Q3PodCreate(StrictInput):
    shipment_id: uuid.UUID
    delivered_at: datetime | None = None
    receiver_name: str = Field(min_length=1, max_length=120)
    receiver_role: str | None = Field(default=None, max_length=80)
    signature_attachment_id: uuid.UUID
    seal_intact: bool = True
    product_temp_c: Temp | None = Field(default=None, ge=-80, le=80)
    mte_id: uuid.UUID | None = None
    exceptions: list[Q3PodException] = Field(default_factory=list, max_length=20)
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=6)


class Q3TripRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    trip_no: str
    site_id: uuid.UUID
    carrier: Q3SupplierRef | None
    own_fleet: bool
    vehicle_id: uuid.UUID | None
    plate_text: str | None
    reefer_serial: str | None
    compartments: list[dict[str, Any]]
    driver_name: str | None
    driver_worker_id: uuid.UUID | None
    loggers: list[Q3MteRef | None]
    seal_numbers: list[str]
    planned_departure: datetime | None
    preload: Q3ChecklistResponse | None
    preload_passed: bool | None
    preload_failures: list[str]
    preload_box_temp_c: Temp | None
    loading_temps: list[dict[str, Any]]
    override_allowed: bool
    override_reason: str | None
    override_requested: bool
    can_override: bool
    readiness: dict[str, Any] | None
    departed_at: datetime | None
    delivered_at: datetime | None
    closed_at: datetime | None
    transit_data: bool
    status: QTripStatus
    cancel_reason: str | None
    shipments: list[dict[str, Any]]
    excursions: list[dict[str, Any]]
    signoffs: list[QSignoffRead]
    warnings: list[ApiWarning] = Field(default_factory=list)
    proposals: list[dict[str, Any]] = Field(default_factory=list)


class Q3TripListItem(ApiModel):
    id: uuid.UUID
    trip_no: str
    status: QTripStatus
    carrier: Q3SupplierRef | None
    plate_text: str | None
    planned_departure: datetime | None
    departed_at: datetime | None
    delivered_at: datetime | None
    shipments: int
    preload_passed: bool | None
    overridden: bool
    transit_excursions: bool


class Q3TripPage(Page[Q3TripListItem]):
    pass


class Q3ShipmentRead(ApiModel):
    id: uuid.UUID
    shipment_ref: str
    consignee_name: str
    owner: Q3CustomerRef | None
    classes: list[str]
    promised_at: datetime | None
    delivered_at: datetime | None
    trip_id: uuid.UUID | None


# ---- metrics -------------------------------------------------------------------------------------


class Q3Metrics(ApiModel):
    """K-160…K-168 inputs and values of one month (§E.4; Q4 owns the KPI catalogue)."""

    year: int
    month: int
    k160: dict[str, Any]
    k161: dict[str, Any]
    k162: dict[str, Any]
    k163: dict[str, Any]
    k164: dict[str, Any]
    k165: dict[str, Any]
    k166: dict[str, Any]
    k167: dict[str, Any]
    k168: dict[str, Any]
