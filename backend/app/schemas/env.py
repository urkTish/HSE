"""Phase 6e schemas — environmental management (spec 6e-environmental v1.0).

Percentages are decimal strings with 1 dp; tonnes with 3 dp (shown 1 dp); readings with the
stored precision (shown 1 dp). Personal fields (driver name / mobile, vehicle plate, complainant
name / contact, photos) are absent (null) for Viewer/Client and for callers without the capability
named in each field (P6e-1…P6e-3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.env_enums import (
    AreaStatus,
    AspectAction,
    AspectCondition,
    AspectStatus,
    Averaging,
    BackgroundSource,
    ComplaintAction,
    ComplaintCategory,
    ComplaintChannel,
    ComplaintStatus,
    ConsignmentAction,
    ConsignmentStatus,
    EnvActionKind,
    EnvKpiGroupBy,
    ExceedanceCause,
    ExceedanceStatus,
    InstrumentAction,
    InstrumentKind,
    InstrumentStatus,
    Issuer,
    LicenceActivity,
    LimitSource,
    NoiseArea,
    NoisePeriod,
    Parameter,
    PermitAction,
    PermitStatus,
    PermitType,
    PointKind,
    PointSource,
    ProviderAction,
    ProviderKind,
    ProviderStatus,
    QuantityUnit,
    ReadingResult,
    ReadingSource,
    RecordState,
    Schedule,
    SpillAction,
    SpillSource,
    SpillStatus,
    SpillSubstance,
    SpillSurface,
    StorageAreaType,
    WasteClass,
    WasteRoute,
    WaterSource,
)
from app.core.hse_enums import (
    Activity,
    CaStatus,
    ControlLevel,
    EnvReached,
    IncidentShift,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning
from app.schemas.kpi import KpiContext, KpiValue

# ---- reference and settings (§3.16, §3.17) -------------------------------------------------------


class EnvRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    detail: str | None = Field(
        default=None,
        description="WS: class · default route · density; PT: holder · issuer · expiry; "
        "NA: day / night dB(A); PA: unit · range.",
    )


class EnvReference(ApiModel):
    """GET /env-reference: every 6e list with EN/AR labels (§3.17) and the DL limit library."""

    lists: dict[str, list[EnvRefItem]]
    limit_library: list["LimitRow"]


class LimitRow(ApiModel):
    parameter: Parameter
    averaging: Averaging
    period: NoisePeriod = NoisePeriod.any
    noise_area_category: NoiseArea | None = None
    alert_value: str | None
    limit_value: str | None
    limit_min: str | None = None
    limit_max: str | None = None
    source: LimitSource


class EnvSettingsRead(ApiModel):
    project_id: uuid.UUID
    env_notifications_from: date | None
    permit_alert_days: list[int]
    provider_licence_alert_days: list[int]
    manifest_return_days: int
    weight_discrepancy_pct: str
    mwan_manifest_required_for: list[WasteClass]
    haz_storage_max_days: int
    containment_min_pct: int
    spill_reportable_l: str
    airside_spill_always_reportable: bool
    data_capture_pct: str
    noise_day_start: str
    noise_night_start: str
    background_ops_event_types: list[str]
    post_storm_check_hours: int
    exceedance_review_days: int
    complaint_response_days: int
    authority_complaint_response_days: int
    aspect_review_months: int
    diversion_target_pct: str
    monitoring_warning_pct: str
    custody_warning_pct: str
    exceedance_warning_count: int
    photo_retention_months: int
    complainant_retention_months: int


class EnvSettingsUpdate(PatchInput):
    """Capability 213 (HSE Manager). Values outside "Allowed" → 422; loosening → 422
    SETTING_LOOSENING (§3.16)."""

    env_notifications_from: date | None = None
    permit_alert_days: list[int] | None = None
    provider_licence_alert_days: list[int] | None = None
    manifest_return_days: int | None = Field(default=None, ge=1, le=14)
    weight_discrepancy_pct: Decimal | None = Field(default=None, ge=2, le=20)
    mwan_manifest_required_for: list[WasteClass] | None = None
    haz_storage_max_days: int | None = Field(default=None, ge=30, le=90)
    containment_min_pct: int | None = Field(default=None, ge=110, le=150)
    spill_reportable_l: Decimal | None = Field(default=None, ge=1, le=200)
    airside_spill_always_reportable: bool | None = None
    data_capture_pct: Decimal | None = Field(default=None, ge=50, le=100)
    noise_day_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    noise_night_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    background_ops_event_types: list[str] | None = None
    post_storm_check_hours: int | None = Field(default=None, ge=1, le=12)
    exceedance_review_days: int | None = Field(default=None, ge=1, le=7)
    complaint_response_days: int | None = Field(default=None, ge=1, le=14)
    authority_complaint_response_days: int | None = Field(default=None, ge=1, le=7)
    aspect_review_months: int | None = Field(default=None, ge=6, le=12)
    diversion_target_pct: Decimal | None = Field(default=None, ge=0, le=100)
    monitoring_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    custody_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    exceedance_warning_count: int | None = Field(default=None, ge=1, le=10)
    photo_retention_months: int | None = Field(default=None, ge=12, le=60)
    complainant_retention_months: int | None = Field(default=None, ge=6, le=24)


class EnvVoid(StrictInput):
    """Capability 214; reason ≥ 20 chars."""

    reason: str = Field(min_length=1, max_length=500)


class PhotoInput(StrictInput):
    file_name: str = Field(max_length=120)
    content_base64: str = Field(description="jpg / png ≤ 5 MB; EXIF stripped on receipt.")


# ---- aspects (§3.1, §4.1, ASP) -------------------------------------------------------------------


class AspectControl(ApiModel):
    text_en: str = Field(max_length=300)
    text_ar: str = Field(default="", max_length=300)
    control_level: ControlLevel


class MonitoringLink(ApiModel):
    """Either a point and parameter or a 6d template code."""

    point_id: uuid.UUID | None = None
    parameter: Parameter | None = None
    template_code: str | None = Field(default=None, max_length=8)


class AspectCreate(StrictInput):
    activity: Activity
    aspect: str = Field(description="List AS code.", examples=["dust_emission"])
    impact: str = Field(description="List IM code.", examples=["aviation_safety"])
    condition: AspectCondition
    site_ids: list[uuid.UUID] = Field(min_length=1)
    engagement_ids: list[uuid.UUID] = Field(default_factory=list)
    severity: int = Field(ge=1, le=5)
    likelihood: int = Field(ge=1, le=5)
    legal_requirement: bool = False
    permit_ids: list[uuid.UUID] = Field(default_factory=list)
    stakeholder_concern: bool = False
    controls: list[AspectControl] = Field(default_factory=list)
    monitoring_links: list[MonitoringLink] = Field(default_factory=list)


class AspectUpdate(PatchInput):
    activity: Activity | None = None
    aspect: str | None = None
    impact: str | None = None
    condition: AspectCondition | None = None
    site_ids: list[uuid.UUID] | None = None
    engagement_ids: list[uuid.UUID] | None = None
    severity: int | None = Field(default=None, ge=1, le=5)
    likelihood: int | None = Field(default=None, ge=1, le=5)
    legal_requirement: bool | None = None
    permit_ids: list[uuid.UUID] | None = None
    stakeholder_concern: bool | None = None
    controls: list[AspectControl] | None = None
    monitoring_links: list[MonitoringLink] | None = None


class AspectTransition(StrictInput):
    """activate (ASP-2), archive (reason ≥ 20 chars), review (resets review_due_on, clears the
    flag)."""

    action: AspectAction
    reason: str | None = Field(default=None, max_length=500)


class AspectRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    aspect_no: str
    activity: str
    aspect: str
    impact: str
    condition: AspectCondition
    site_ids: list[uuid.UUID]
    engagement_ids: list[uuid.UUID]
    severity: int
    likelihood: int
    legal_requirement: bool
    permit_ids: list[uuid.UUID]
    stakeholder_concern: bool
    score: int
    significant: bool
    controls: list[AspectControl]
    monitoring_links: list[MonitoringLink]
    activated_on: date | None
    review_due_on: date | None
    review_flag: bool
    status: AspectStatus
    status_reason: str | None


class AspectPage(Page[AspectRead]):
    pass


# ---- providers and permits (§3.2, §3.3, §4.2, PRM, PRV) ------------------------------------------


class Facility(ApiModel):
    facility_code: str = Field(max_length=20)
    name_en: str = Field(max_length=150)
    name_ar: str = Field(default="", max_length=150)
    city: str = Field(default="", max_length=60)
    kind: ProviderKind


class ProviderCreate(StrictInput):
    """Capability 204; created approved."""

    provider_code: str = Field(pattern=r"^[A-Z0-9-]{2,12}$")
    name_en: str = Field(max_length=150)
    name_ar: str = Field(max_length=150)
    cr_number: str = Field(pattern=r"^\d{10}$")
    kinds: list[ProviderKind] = Field(min_length=1)
    facilities: list[Facility] = Field(default_factory=list)
    contact_email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)


class ProviderUpdate(PatchInput):
    name_en: str | None = Field(default=None, max_length=150)
    name_ar: str | None = Field(default=None, max_length=150)
    kinds: list[ProviderKind] | None = None
    facilities: list[Facility] | None = None
    contact_email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)


class ProviderTransition(StrictInput):
    """Capability 213 (HSE Manager); reason ≥ 20 chars for suspend / blacklist."""

    action: ProviderAction
    reason: str | None = Field(default=None, max_length=500)


class ProviderRead(ApiModel):
    id: uuid.UUID
    provider_code: str
    name_en: str
    name_ar: str
    cr_number: str
    kinds: list[ProviderKind]
    facilities: list[Facility]
    contact_email: str | None
    phone: str | None
    status: ProviderStatus
    status_reason: str | None
    licences: list["PermitRead"] = Field(default_factory=list)


class ProviderPage(Page[ProviderRead]):
    pass


class PermitScope(ApiModel):
    activities: list[LicenceActivity] = Field(default_factory=list)
    waste_classes: list[WasteClass] = Field(default_factory=list)
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    facility_code: str | None = None


class PermitCondition(ApiModel):
    """A condition linked to a point and parameter whose limit_value is lower than the
    requirement's replaces it (LIM-2, PRM-5)."""

    code: str = Field(max_length=12)
    text_en: str = Field(max_length=500)
    text_ar: str = Field(default="", max_length=500)
    point_id: uuid.UUID | None = None
    parameter: Parameter | None = None
    averaging: Averaging | None = None
    limit_value: Decimal | None = None
    template_code: str | None = Field(default=None, max_length=8)


class PermitCreate(StrictInput):
    """Capability 204. Project holder: POST /projects/{id}/env-permits; provider licence: POST
    /env-providers/{id}/licences. `pending` true: applied, no reference yet."""

    permit_type: PermitType
    issuer: Issuer
    requirement_code: str | None = Field(default=None, max_length=20)
    required: bool = False
    applies_from: date | None = None
    applies_to: date | None = None
    reference_no: str | None = Field(default=None, max_length=40)
    scope: PermitScope = Field(default_factory=PermitScope)
    valid_from: date | None = None
    valid_to: date | None = None
    conditions: list[PermitCondition] = Field(default_factory=list)
    document_id: uuid.UUID | None = Field(
        default=None, description="Attachment (owner type env_permit_document)."
    )
    supersedes_id: uuid.UUID | None = None
    pending: bool = False


class PermitUpdate(PatchInput):
    reference_no: str | None = Field(default=None, max_length=40)
    valid_from: date | None = None
    valid_to: date | None = None
    applies_from: date | None = None
    applies_to: date | None = None
    conditions: list[PermitCondition] | None = None
    document_id: uuid.UUID | None = None
    scope: PermitScope | None = None
    required: bool | None = None


class PermitTransition(StrictInput):
    """suspend / cancel (204, reason ≥ 20 chars), reinstate."""

    action: PermitAction
    reason: str | None = Field(default=None, max_length=500)


class PermitRead(ApiModel):
    id: uuid.UUID
    record_no: str
    project_id: uuid.UUID | None
    provider_id: uuid.UUID | None
    permit_type: PermitType
    issuer: Issuer
    requirement_code: str | None
    required: bool
    applies_from: date | None
    applies_to: date | None
    reference_no: str | None
    scope: PermitScope
    valid_from: date | None
    valid_to: date | None
    conditions: list[PermitCondition]
    document_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    status: PermitStatus = Field(description="§4.2 at today.")
    days_to_expiry: int | None
    status_reason: str | None


class PermitPage(Page[PermitRead]):
    pass


# ---- waste (§3.4–§3.6, WST, CON) -----------------------------------------------------------------


class StreamRead(ApiModel):
    stream_code: str
    label_en: str
    label_ar: str
    waste_class: WasteClass
    default_route: WasteRoute
    density: str
    density_unit: str = Field(description='"t/m3", "kg/L" or "m3 only" (sewage).')
    wildlife_attractant: bool
    excluded_from_tonnage: bool
    active: bool


class StreamUpsert(StrictInput):
    """Capability 205 (WST-1): activate a list WS stream, edit route and density."""

    default_route: WasteRoute | None = None
    density: Decimal | None = Field(default=None, ge=Decimal("0.01"), le=Decimal("3.00"))
    active: bool = True


class StreamList(ApiModel):
    items: list[StreamRead]


class Accumulation(ApiModel):
    stream_code: str
    started_on: date | None


class AreaCreate(StrictInput):
    area_code: str = Field(max_length=16)
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    type: StorageAreaType
    accepted_streams: list[str] = Field(min_length=1)
    capacity_m3: Decimal = Field(gt=0)
    secondary_containment_pct: int | None = Field(default=None, ge=0, le=300)
    covered: bool = False
    lidded_secured: bool = False
    signage_bilingual: bool = False
    accumulation: list[Accumulation] = Field(default_factory=list)


class AreaUpdate(PatchInput):
    zone_id: uuid.UUID | None = None
    type: StorageAreaType | None = None
    accepted_streams: list[str] | None = None
    capacity_m3: Decimal | None = Field(default=None, gt=0)
    secondary_containment_pct: int | None = Field(default=None, ge=0, le=300)
    covered: bool | None = None
    lidded_secured: bool | None = None
    signage_bilingual: bool | None = None
    accumulation: list[Accumulation] | None = None
    status: AreaStatus | None = None


class HazDeadline(ApiModel):
    stream_code: str
    started_on: date
    deadline: date
    days_left: int
    overdue: bool


class InspectionAnswerRow(ApiModel):
    """WST-4: the last 6d WSA / ENV answers in the area's zone (non-compliant first)."""

    inspection_id: uuid.UUID | None
    template_code: str
    item_code: str
    compliant: bool
    completed_date: date | None
    ca_id: uuid.UUID | None = None


class AreaRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    area_code: str
    site_id: uuid.UUID
    zone_id: uuid.UUID | None
    zone_code: str | None
    type: StorageAreaType
    accepted_streams: list[str]
    capacity_m3: str
    secondary_containment_pct: int | None
    covered: bool
    lidded_secured: bool
    signage_bilingual: bool
    accumulation: list[Accumulation]
    haz_deadlines: list[HazDeadline]
    status: AreaStatus
    inspection_answers: list[InspectionAnswerRow] = Field(default_factory=list)
    last_consignments: list[str] = Field(default_factory=list)


class AreaPage(Page[AreaRead]):
    pass


class ConsignmentCreate(StrictInput):
    """Capability 206 (CON-1…CON-5, AIR-3). dispatched_at ≥ now − 72 h, ≤ now + 5 min."""

    stream_code: str
    storage_area_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = Field(default=None, description="Defaults to the area's site.")
    generator_engagement_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit: QuantityUnit
    route: WasteRoute | None = Field(default=None, description="Default: the stream's route.")
    transporter_id: uuid.UUID
    facility_provider_id: uuid.UUID
    facility_code: str | None = None
    vehicle_plate: str = Field(min_length=3, max_length=12)
    driver_name: str | None = Field(default=None, max_length=120)
    driver_mobile: str | None = Field(default=None, max_length=15)
    mwan_manifest_ref: str | None = Field(default=None, max_length=40)
    dispatched_at: datetime
    redispatch_of_id: uuid.UUID | None = None


class ConsignmentUpdate(PatchInput):
    """Until Closed (409 CONSIGNMENT_CLOSED)."""

    vehicle_plate: str | None = Field(default=None, min_length=3, max_length=12)
    driver_name: str | None = Field(default=None, max_length=120)
    driver_mobile: str | None = Field(default=None, max_length=15)
    mwan_manifest_ref: str | None = Field(default=None, max_length=40)


class ReceiptInput(StrictInput):
    """CON-6 (206 / 207): ticket_file_id = an attachment of owner type consignment_ticket."""

    received_at: datetime
    received_net_t: Decimal = Field(gt=0)
    ticket_ref: str = Field(min_length=1, max_length=40)
    ticket_file_id: uuid.UUID


class ConsignmentTransition(StrictInput):
    """close (207; discrepancy_reason ≥ 20 chars when above the threshold), reject (207, reason),
    void (214, reason ≥ 20 chars)."""

    action: ConsignmentAction
    reason: str | None = Field(default=None, max_length=500)
    discrepancy_reason: str | None = Field(default=None, max_length=500)


class ConsignmentRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    consignment_no: str
    stream_code: str
    waste_class: WasteClass
    storage_area_id: uuid.UUID | None
    site_id: uuid.UUID | None
    generator_engagement_id: uuid.UUID
    generator_code: str | None
    quantity: str
    unit: QuantityUnit
    estimated_t: str
    tonnes: str | None = Field(description="§6.3: received_net_t, else estimated_t; null sewage.")
    provisional: bool
    route: WasteRoute
    transporter_id: uuid.UUID
    transporter_code: str
    transporter_licence_id: uuid.UUID | None
    facility_provider_id: uuid.UUID
    facility_provider_code: str
    facility_code: str | None
    facility_licence_id: uuid.UUID | None
    vehicle_plate: str | None = Field(description="Personal (P6e-3): null for Viewer/Client.")
    driver_name: str | None
    driver_mobile: str | None
    mwan_manifest_ref: str | None
    dispatched_at: datetime
    due_on: date
    overdue: bool
    received_at: datetime | None
    received_net_t: str | None
    ticket_ref: str | None
    ticket_file_id: uuid.UUID | None
    receipt_recorded_at: datetime | None
    discrepancy_pct: str | None
    discrepancy_reason: str | None
    rejection_reason: str | None
    redispatch_of_id: uuid.UUID | None
    ca_id: uuid.UUID | None
    status: ConsignmentStatus
    status_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class ConsignmentPage(Page[ConsignmentRead]):
    pass


# ---- monitoring (§3.7–§3.12, MON, LIM, EXD) ------------------------------------------------------


class InstrumentCreate(StrictInput):
    """Capability 208 (MON-1): calibration_valid_until > today; SLM class 1 or 2."""

    kind: InstrumentKind
    make_model: str = Field(max_length=80)
    serial_no: str = Field(max_length=40)
    standard_class: str | None = Field(default=None, pattern=r"^[12]$")
    calibration_valid_until: date
    calibration_cert_ref: str = Field(max_length=40)


class InstrumentUpdate(PatchInput):
    make_model: str | None = Field(default=None, max_length=80)
    calibration_valid_until: date | None = None
    calibration_cert_ref: str | None = Field(default=None, max_length=40)


class InstrumentTransition(StrictInput):
    action: InstrumentAction
    reason: str | None = Field(default=None, max_length=500)


class InstrumentRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    instrument_no: str
    kind: InstrumentKind
    make_model: str
    serial_no: str
    standard_class: str | None
    calibration_valid_until: date
    calibration_cert_ref: str
    status: InstrumentStatus
    status_reason: str | None


class InstrumentPage(Page[InstrumentRead]):
    pass


class EnvDeviceCreate(StrictInput):
    device_id: str = Field(max_length=40)
    label: str = Field(max_length=80)


class EnvDeviceRead(ApiModel):
    id: uuid.UUID
    instrument_id: uuid.UUID
    device_id: str
    label: str
    registered_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    device_token: str | None = Field(default=None, description="Returned once at registration.")


class EnvStationSessionInput(StrictInput):
    device_token: str = Field(min_length=10, max_length=200)


class EnvStationSessionRead(ApiModel):
    access_token: str
    instrument_no: str
    point_code: str | None


class StationValue(StrictInput):
    parameter: Parameter
    window_start: datetime = Field(description="Start of the 15-minute window.")
    value: Decimal


class StationPush(StrictInput):
    """MON-2: `15min` values; a repeated (device, parameter, window_start) is ignored."""

    values: list[StationValue] = Field(min_length=1, max_length=200)


class StationPushResult(ApiModel):
    accepted: int
    duplicates: int
    derived: int


class Requirement(ApiModel):
    """§3.9. Prefilled from list DL (and NA for noise); values may only tighten (LIM-2)."""

    parameter: Parameter
    averaging: Averaging
    schedule: Schedule
    period: NoisePeriod = NoisePeriod.any
    alert_value: Decimal | None = None
    limit_value: Decimal | None = None
    limit_min: Decimal | None = None
    limit_max: Decimal | None = None
    limit_source: LimitSource | None = None
    library_ref: str | None = None


class RequirementRead(Requirement):
    effective_limit: str | None = Field(description="After permit conditions (PRM-5).")
    effective_source: LimitSource | None
    condition_code: str | None = None


class PointCreate(StrictInput):
    point_code: str = Field(max_length=16)
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    kind: PointKind
    noise_area_category: NoiseArea | None = None
    source_kind: PointSource
    instrument_id: uuid.UUID | None = None
    permit_id: uuid.UUID | None = None
    requirements: list[Requirement] = Field(min_length=1)
    active: bool = True


class PointUpdate(PatchInput):
    zone_id: uuid.UUID | None = None
    instrument_id: uuid.UUID | None = None
    permit_id: uuid.UUID | None = None
    requirements: list[Requirement] | None = None
    active: bool | None = None


class PointRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    point_code: str
    site_id: uuid.UUID
    zone_id: uuid.UUID | None
    zone_code: str | None
    airside: bool
    kind: PointKind
    noise_area_category: NoiseArea | None
    source_kind: PointSource
    instrument_id: uuid.UUID | None
    permit_id: uuid.UUID | None
    requirements: list[RequirementRead]
    active: bool


class PointPage(Page[PointRead]):
    pass


class ReadingCreate(StrictInput):
    """Capability 209 (MON-3). Manual: an active calibrated instrument, ≤ 72 h back; laeq needs
    field_calibration_checked. Lab: lab_provider_id + lab_report_ref; the window is the sampling
    window (any past time). Visual: no instrument; value = score 0–3."""

    point_id: uuid.UUID
    parameter: Parameter
    averaging: Averaging
    window_start: datetime
    window_end: datetime
    value: Decimal
    instrument_id: uuid.UUID | None = None
    lab_provider_id: uuid.UUID | None = None
    lab_report_ref: str | None = Field(default=None, max_length=40)
    field_calibration_checked: bool | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=3)


class ReadingRead(ApiModel):
    id: uuid.UUID
    reading_no: str
    project_id: uuid.UUID
    point_id: uuid.UUID
    point_code: str
    parameter: Parameter
    averaging: Averaging
    period: NoisePeriod
    window_start: datetime
    window_end: datetime
    source: ReadingSource
    value: str
    display: str = Field(description="1 dp with unit.")
    instrument_id: uuid.UUID | None
    lab_provider_id: uuid.UUID | None
    lab_report_ref: str | None
    field_calibration_checked: bool | None
    background: bool
    background_ref: str | None
    result: ReadingResult
    limit_value: str | None
    late_entry: bool
    exceedance_id: uuid.UUID | None
    photo_ids: list[uuid.UUID] | None
    status: RecordState
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class ReadingPage(Page[ReadingRead]):
    pass


class BackgroundCreate(StrictInput):
    """Capability 208 (§3.11): to − from ≤ 72 h."""

    site_ids: list[uuid.UUID] = Field(min_length=1)
    from_at: datetime
    to_at: datetime
    source: BackgroundSource
    source_ref: str = Field(max_length=40)


class BackgroundRead(ApiModel):
    id: uuid.UUID
    declaration_no: str
    project_id: uuid.UUID
    site_ids: list[uuid.UUID]
    from_at: datetime
    to_at: datetime
    source: BackgroundSource
    source_ref: str


class BackgroundPage(Page[BackgroundRead]):
    pass


class ExceedanceReview(StrictInput):
    """Capability 210 (EXD-5). project_activity needs responsible_engagement_id and creates one CA
    (high); third_party / unknown create a CA only with create_ca."""

    cause: ExceedanceCause
    responsible_engagement_id: uuid.UUID | None = None
    activity_en: str | None = Field(default=None, max_length=300)
    activity_ar: str | None = Field(default=None, max_length=300)
    immediate_action_en: str = Field(min_length=1, max_length=1000)
    immediate_action_ar: str | None = Field(default=None, max_length=1000)
    create_ca: bool = False


class ExceedanceRead(ApiModel):
    id: uuid.UUID
    exceedance_no: str
    project_id: uuid.UUID
    point_id: uuid.UUID
    point_code: str
    site_id: uuid.UUID
    parameter: Parameter
    averaging: Averaging
    period: NoisePeriod
    reading_ids: list[uuid.UUID]
    day: date
    peak_value: str
    limit_value: str
    margin_pct: str
    started_at: datetime
    ended_at: datetime | None
    late_result: bool
    airside: bool
    suggested_cause: ExceedanceCause | None
    background_ref: str | None
    cause: ExceedanceCause | None
    responsible_engagement_id: uuid.UUID | None
    activity_en: str | None
    activity_ar: str | None
    immediate_action_en: str | None
    immediate_action_ar: str | None
    ca_id: uuid.UUID | None
    ca_ref: str | None
    ca_status: CaStatus | None
    review_due_on: date
    reviewed_at: datetime | None
    status: ExceedanceStatus
    project_caused: bool = Field(description="Counts in K-123.")


class ExceedancePage(Page[ExceedanceRead]):
    pass


# ---- spills (§3.13, SPL) -------------------------------------------------------------------------


class SpillIncidentFields(StrictInput):
    actual_severity: int = Field(ge=1, le=5)
    potential_severity: int = Field(ge=1, le=5)
    activity: Activity
    shift: IncidentShift
    description: str = Field(min_length=1, max_length=2000)
    immediate_actions: str = Field(min_length=1, max_length=2000)


class SpillCreate(StrictInput):
    """Capability 211 (SPL-1…SPL-5). Idempotent on client_uuid. Spill kits: 6c asset ids, or EA
    sticker payloads in spill_kit_payloads."""

    client_uuid: uuid.UUID
    occurred_at: datetime
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    responsible_engagement_id: uuid.UUID
    substance: SpillSubstance
    source: SpillSource
    quantity_l: Decimal = Field(ge=Decimal("0.1"), le=100000)
    surface: SpillSurface
    contained: bool
    reached: EnvReached
    spill_kit_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    spill_kit_payloads: list[str] = Field(default_factory=list)
    incident_id: uuid.UUID | None = Field(
        default=None, description="An existing environmental incident (±24 h, same site)."
    )
    incident_fields: SpillIncidentFields | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=5)


class SpillTransition(StrictInput):
    """clean_up (211; cleanup_completed_at), close (210; SPL-6 cleanup waste), void (214)."""

    action: SpillAction
    cleanup_completed_at: datetime | None = None
    cleanup_consignment_ids: list[uuid.UUID] = Field(default_factory=list)
    cleanup_storage_area_id: uuid.UUID | None = None
    absorbed_and_binned: bool = False
    reason: str | None = Field(default=None, max_length=500)


class SpillRead(ApiModel):
    id: uuid.UUID
    spill_no: str
    client_uuid: uuid.UUID
    project_id: uuid.UUID
    occurred_at: datetime
    site_id: uuid.UUID
    zone_id: uuid.UUID | None
    zone_code: str | None
    responsible_engagement_id: uuid.UUID
    responsible_code: str | None
    substance: SpillSubstance
    source: SpillSource
    quantity_l: str
    surface: SpillSurface
    contained: bool
    reached: EnvReached
    spill_kit_asset_ids: list[uuid.UUID]
    reportable: bool
    incident_id: uuid.UUID | None
    incident_ref: str | None
    cleanup_completed_at: datetime | None
    cleanup_consignment_ids: list[uuid.UUID]
    cleanup_storage_area_id: uuid.UUID | None
    absorbed_and_binned: bool
    photo_ids: list[uuid.UUID] | None
    status: SpillStatus
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class SpillPage(Page[SpillRead]):
    pass


# ---- water (§3.14, WAT) and complaints (§3.15, CPL) ----------------------------------------------


class WaterCreate(StrictInput):
    """Capability 209 (WAT-1); one per (site, month, source); editable until the 10th of the
    next month."""

    site_id: uuid.UUID
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    source: WaterSource
    volume_m3: Decimal = Field(ge=0)
    purpose: dict[str, Decimal] = Field(
        default_factory=dict,
        description="dust_suppression, concrete_curing, welfare, other (sum = volume).",
    )


class WaterUpdate(PatchInput):
    volume_m3: Decimal | None = Field(default=None, ge=0)
    purpose: dict[str, Decimal] | None = None


class WaterRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    month: str
    source: WaterSource
    volume_m3: str
    purpose: dict[str, str]
    status: RecordState
    void_reason: str | None


class WaterPage(Page[WaterRead]):
    pass


class DischargeCreate(StrictInput):
    """Capability 209 (WAT-2, WAT-3): saved with warning PERMIT_NOT_VALID when the point's permit
    requirement is not in force that day."""

    point_id: uuid.UUID
    day: date
    volume_m3: Decimal = Field(ge=0)


class DischargeRead(ApiModel):
    id: uuid.UUID
    point_id: uuid.UUID
    day: date
    volume_m3: str
    permit_valid: bool
    warnings: list[ApiWarning] = Field(default_factory=list)


class DischargePage(Page[DischargeRead]):
    pass


class ComplaintCreate(StrictInput):
    """Capability 212 (CPL-1); complainant fields only when not anonymous (P6e-2)."""

    received_at: datetime
    channel: ComplaintChannel
    category: ComplaintCategory
    site_id: uuid.UUID
    location_text: str | None = Field(default=None, max_length=200)
    anonymous: bool = False
    complainant_name: str | None = Field(default=None, max_length=120)
    complainant_contact: str | None = Field(default=None, max_length=60)
    description: str = Field(min_length=1, max_length=2000)
    reading_ids: list[uuid.UUID] = Field(default_factory=list)
    exceedance_ids: list[uuid.UUID] = Field(default_factory=list)


class ComplaintUpdate(PatchInput):
    location_text: str | None = Field(default=None, max_length=200)
    reading_ids: list[uuid.UUID] | None = None
    exceedance_ids: list[uuid.UUID] | None = None
    investigation_en: str | None = Field(default=None, max_length=2000)
    investigation_ar: str | None = Field(default=None, max_length=2000)


class ComplaintTransition(StrictInput):
    """respond (response_summary), close, void (214, reason ≥ 20 chars)."""

    action: ComplaintAction
    response_summary: str | None = Field(default=None, max_length=2000)
    response_sent_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class ComplaintRead(ApiModel):
    id: uuid.UUID
    complaint_no: str
    project_id: uuid.UUID
    received_at: datetime
    channel: ComplaintChannel
    category: ComplaintCategory
    site_id: uuid.UUID
    location_text: str | None
    anonymous: bool
    complainant_name: str | None = Field(description="212 holders only (P6e-2).")
    complainant_contact: str | None
    contact_note: str | None = Field(
        description='"Contact held by the HSE team" for callers without 212; "deleted" after '
        "retention."
    )
    description: str
    reading_ids: list[uuid.UUID]
    exceedance_ids: list[uuid.UUID]
    investigation_en: str | None
    investigation_ar: str | None
    response_due_on: date
    response_sent_at: datetime | None
    response_summary: str | None
    status: ComplaintStatus
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class ComplaintPage(Page[ComplaintRead]):
    pass


class NearbyReadings(ApiModel):
    """CPL-2: readings of points on the complaint's site within ± 2 h."""

    items: list[ReadingRead]


# ---- board, action panel (§8.1, §8.2) ------------------------------------------------------------


class EnvActionRow(ApiModel):
    kind: EnvActionKind
    ref: str
    label_en: str
    label_ar: str
    entity_id: uuid.UUID | None = None
    due: date | None = None


class EnvActionPanel(ApiModel):
    items: list[EnvActionRow]
    counts: dict[str, int]


class PostStormTask(ApiModel):
    """AIR-4 (derived from Phase 2 dust_sandstorm ops events)."""

    ops_no: str
    site_id: uuid.UUID
    site_code: str
    ended_at: datetime
    due_at: datetime
    met: bool
    met_by_inspection_id: uuid.UUID | None
    overdue: bool


class EnvBand(ApiModel):
    """§8.1 item 2 (live)."""

    open_exceedances: list[ExceedanceRead]
    airside_dust_alerts_24h: int
    expiring_permits: list[PermitRead]
    consignments_overdue: int
    haz_storage_due: list[HazDeadline]
    post_storm_tasks: list[PostStormTask]


# ---- KPIs (§6.7) ---------------------------------------------------------------------------------


class EnvBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class EnvBreakdown(ApiModel):
    metric: str
    group_by: EnvKpiGroupBy
    rows: list[EnvBreakdownRow]


class EnvKpiResponse(ApiModel):
    """GET /kpi/environmental: K-118…K-126 (aggregates only, EK-2). With a contractor filter
    K-118 shows "—" (project level only)."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[EnvBreakdown]
    notes: list[str]


EnvReference.model_rebuild()
ProviderRead.model_rebuild()
