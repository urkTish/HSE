"""Equipment register, project deployments, configuration events, stickers, tag-out,
retirement and equipment blacklisting (spec 4-third-party-cert §3.4, §3.5, §3.7, §3.13, §4.2,
§4.3, EQ-1…EQ-6, EM-1…EM-6, CF-1…CF-4, BL-3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.cert_enums import (
    ArrivalChecklistItem,
    ChecklistItemResult,
    ConfigurationEventType,
    DefectCategory,
    EquipmentBlacklistReason,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    EquipmentDocType,
    EquipmentSubtype,
    PassFail,
    RetireReason,
    SafetyDevice,
    ServiceStatus,
    ServiceStatusReason,
)
from app.schemas.access_common import QR_PAYLOAD_DOC, VehicleRef
from app.schemas.cert_common import (
    P4_HINT,
    TAG_PATTERN,
    CertLineRef,
    DefectRef,
    DeploymentRef,
    EquipmentLimitationRead,
    EquipmentRef,
    Metres2,
    Tonnes,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, SiteRef, UserRef, ZoneRef

QR_EQ = r"^HSE2:EQ:[A-Za-z0-9_-]{22}$"

# ---- equipment item (§3.4) --------------------------------------------------------------------


class PressureFields(StrictInput):
    """pressure_vessel: relief_set_bar ≤ mawp_bar (422 RELIEF_ABOVE_MAWP)."""

    design_pressure_bar: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=2)
    mawp_bar: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=2)
    volume_l: DecimalStr = Field(ge=Decimal(0), max_digits=9, decimal_places=1)
    relief_set_bar: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=2)


class PressureFieldsRead(ApiModel):
    design_pressure_bar: DecimalStr
    mawp_bar: DecimalStr
    volume_l: DecimalStr
    relief_set_bar: DecimalStr


class EquipmentDocumentInput(StrictInput):
    doc_type: EquipmentDocType
    ref: str = Field(min_length=1, max_length=60)
    attachment_id: uuid.UUID | None = Field(
        default=None, description="Owner equipment_document (PDF/image ≤ 20 MB)."
    )


class EquipmentDocumentRead(ApiModel):
    doc_type: EquipmentDocType
    ref: str
    attachment_id: uuid.UUID | None


class EquipmentFields(StrictInput):
    category: EquipmentCertCategory = Field(
        description="List EQC; not scaffold (own register). Gas detectors stay in the Phase 3 "
        "detector register (422 USE_DETECTOR_REGISTER, EQ-3)."
    )
    subtype: EquipmentSubtype | None = Field(
        default=None, description="Required for lifting_accessory, mewp, pressure_vessel."
    )
    manufacturer: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    serial_no: str = Field(
        min_length=1,
        max_length=40,
        description="As on the plate. (manufacturer, serial) normalised is unique org-wide: "
        "409 EQUIPMENT_EXISTS (meta.equipment_no) / EQUIPMENT_EXISTS_OUT_OF_SCOPE / "
        "EQUIPMENT_BLACKLISTED (EQ-1).",
        examples=["TESTSN-TC-0001"],
    )
    year_of_manufacture: int = Field(ge=1970, le=2100)
    owner_contractor_id: uuid.UUID = Field(
        description="Owner, or the hiring contractor for hired-in equipment (EQ-6)."
    )
    hired_from: str | None = Field(default=None, max_length=120, description=P4_HINT)
    owner_fleet_no: str | None = Field(default=None, max_length=20)
    vehicle_id: uuid.UUID | None = Field(
        default=None,
        description="Phase 2 vehicle (1 : 1). Category must pair with the vehicle category "
        "(422 CATEGORY_MISMATCH); a vehicle linked to another item → 422 "
        "VEHICLE_ALREADY_LINKED (EQ-2).",
    )
    rated_capacity_t: Tonnes | None = None
    max_radius_m: Metres2 | None = None
    max_height_m: Metres2 | None = None
    persons_capacity: int | None = Field(default=None, ge=1, le=100)
    pressure: PressureFields | None = None
    lifting_duty: bool = Field(
        default=False, description="Excavator / loader / telehandler lifting loads (EC-9)."
    )
    safety_devices: list[SafetyDevice] = Field(default_factory=list)
    documents: list[EquipmentDocumentInput] = Field(default_factory=list)


class EquipmentCreate(EquipmentFields):
    """Capability 106 → Awaiting Certificate. Category-required attributes are checked at
    Submit of the first certificate (422 ATTRIBUTE_REQUIRED, EQ-4)."""


class EquipmentUpdate(PatchInput):
    """Serial and manufacturer change only while no certificate has been submitted."""

    non_nullable = frozenset(
        {"manufacturer", "model", "serial_no", "year_of_manufacture", "owner_contractor_id"}
    )

    subtype: EquipmentSubtype | None = None
    manufacturer: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=80)
    serial_no: str | None = Field(default=None, min_length=1, max_length=40)
    year_of_manufacture: int | None = Field(default=None, ge=1970, le=2100)
    owner_contractor_id: uuid.UUID | None = None
    hired_from: str | None = Field(default=None, max_length=120)
    owner_fleet_no: str | None = Field(default=None, max_length=20)
    vehicle_id: uuid.UUID | None = None
    rated_capacity_t: Tonnes | None = None
    max_radius_m: Metres2 | None = None
    max_height_m: Metres2 | None = None
    persons_capacity: int | None = Field(default=None, ge=1, le=100)
    pressure: PressureFields | None = None
    lifting_duty: bool | None = None
    safety_devices: list[SafetyDevice] | None = None
    documents: list[EquipmentDocumentInput] | None = None


class EquipmentLineSummary(ApiModel):
    """The item's current (latest in-force, else latest) certificate line."""

    line: CertLineRef
    inspected_on: date
    result: str = Field(examples=["pass", "pass_with_conditions", "fail"])
    swl_t: DecimalStr | None
    limitations: list[EquipmentLimitationRead]
    in_force: bool
    expiring: bool
    days_left: int | None
    tpi_accreditation_lapsed: bool = Field(
        description="TP-7 note 'TPI accreditation since lapsed' (still in force)."
    )


class EquipmentBlacklistRead(ApiModel):
    """§3.13 event. reason fields are shown to HSE Manager / Officer only (P4-4)."""

    reason_code: EquipmentBlacklistReason | None
    reason_text: str | None
    from_date: date
    by: UserRef | None
    lifted_at: datetime | None
    lifted_by: UserRef | None
    lift_reason: str | None


class EquipmentDeploymentSummary(ApiModel):
    id: uuid.UUID
    deployment_no: str
    project_id: uuid.UUID
    project_code: str
    tag: str
    status: EquipmentDeploymentStatus


class EquipmentRead(ApiModel):
    id: uuid.UUID
    equipment_no: str = Field(examples=["EQP-000101"])
    category: EquipmentCertCategory
    subtype: EquipmentSubtype | None
    manufacturer: str
    model: str
    serial_no: str
    serial_norm: str
    year_of_manufacture: int
    owner_contractor_id: uuid.UUID
    owner_short_code: str
    hired_from: str | None
    owner_fleet_no: str | None
    vehicle: VehicleRef | None
    rated_capacity_t: DecimalStr | None
    max_radius_m: DecimalStr | None
    max_height_m: DecimalStr | None
    persons_capacity: int | None
    pressure: PressureFieldsRead | None
    lifting_duty: bool
    safety_devices: list[SafetyDevice]
    documents: list[EquipmentDocumentRead]
    service_status: ServiceStatus
    service_status_reason: ServiceStatusReason | None
    service_status_text: str | None
    service_status_since: datetime | None
    has_valid_certificate: bool = Field(description="§6.6 'item has a valid certificate'.")
    configuration_suspended: bool = Field(description="CF-1 suspension not yet cleared.")
    current_line: EquipmentLineSummary | None
    open_defects: list[DefectRef]
    deployments: list[EquipmentDeploymentSummary]
    blacklist: EquipmentBlacklistRead | None
    hook_code: str | None = Field(examples=["CRANE-TPI"], description="List EQC hook code.")
    operator_code: str | None = Field(examples=["CRANE-OPERATOR"])
    created_at: datetime
    updated_at: datetime


class EquipmentListItem(ApiModel):
    id: uuid.UUID
    equipment_no: str
    category: EquipmentCertCategory
    subtype: EquipmentSubtype | None
    manufacturer: str
    model: str
    serial_no: str
    owner_short_code: str
    service_status: ServiceStatus
    service_status_reason: ServiceStatusReason | None
    current_tag: str | None
    current_project_code: str | None
    valid_until: date | None
    swl_t: DecimalStr | None


class EquipmentPage(Page[EquipmentListItem]):
    pass


class EquipmentStatusEvent(ApiModel):
    id: uuid.UUID
    occurred_at: datetime
    from_status: ServiceStatus | None
    to_status: ServiceStatus
    reason: ServiceStatusReason | None
    text: str | None
    actor: UserRef | None = Field(description="Null = system.")
    ref: str | None = Field(examples=["DEF-ANIA-EXP-2026-0007", "NKTI-TEST-26-0929"])


class EquipmentStatusEventList(ApiModel):
    items: list[EquipmentStatusEvent]


class TagOutRequest(StrictInput):
    """DF-8 manual tag-out (capability 110, any user in scope): a stop-use act never blocked
    by any rule; notifies the owner's Contractor HSE Rep and HSE Officer."""

    project_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=500, description=P4_HINT)
    physical_tag_applied: bool = Field(description="Must be true (422 PHYSICAL_TAG_REQUIRED).")


class ReturnToServiceRequest(StrictInput):
    """DF-6 (capability 112; ≠ rectifier and not employed by the owner, 422 SOD_CONFLICT).
    Every A and overdue B defect must be Closed (422 DEFECTS_OPEN); the target state follows
    the certificate state (In Service / Quarantined)."""

    note: str = Field(min_length=10, max_length=500)


class RetireRequest(StrictInput):
    """Capability 112 → Retired (terminal); sticker tokens revoked."""

    reason: RetireReason
    reason_text: str = Field(min_length=10, max_length=500)


class EquipmentBlacklistRequest(StrictInput):
    """BL-3 (capability 115): Blacklisted on every project; deployments Demobilised; tokens
    revoked; the serial cannot be registered again."""

    reason_code: EquipmentBlacklistReason
    reason_text: str = Field(min_length=20, max_length=500, description=P4_HINT)


class LiftBlacklistRequest(StrictInput):
    """Blacklisted → Out of Service (a new TPI certificate is needed before use)."""

    reason: str = Field(min_length=10, max_length=500)


class EquipmentLookupRequest(StrictInput):
    """EQ-1 duplicate check before registering (no write)."""

    manufacturer: str = Field(min_length=1, max_length=80)
    serial_no: str = Field(min_length=1, max_length=40)


class EquipmentLookupResult(ApiModel):
    exists: bool
    blacklisted: bool
    equipment: EquipmentRef | None = Field(description="Only when the caller can see it.")


# ---- configuration events (§3.7, CF-1…CF-4) ----------------------------------------------------


class ConfigurationEventCreate(StrictInput):
    """Capability 106 (site engineers too). Tower crane, hoist, mast climber, BMU (any type);
    mobile / crawler crane only major_repair, storm_exceedance, boom_configuration_change
    (422 CONFIGURATION_EVENT_NOT_ALLOWED). occurred_at ≤ now and ≥ now − 24 h (422
    BACKDATED_EVENT). Suspends every in-force line (`configuration_changed`) and quarantines
    the item (CF-1)."""

    project_id: uuid.UUID
    event_type: ConfigurationEventType
    occurred_at: datetime = Field(description="UTC.")
    new_configuration: str = Field(
        min_length=1, max_length=100, examples=["HUH 236.00 m, jib 60 m, 9 tie-ins"]
    )
    new_height_m: Metres2 | None = Field(
        default=None, description="CF-4: updates max_height_m and re-checks clearances."
    )


class ConfigurationEventRead(ApiModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    project_id: uuid.UUID
    event_type: ConfigurationEventType
    occurred_at: datetime
    new_configuration: str
    new_height_m: DecimalStr | None
    recorded_by: UserRef
    recorded_at: datetime
    late_record: bool = Field(description="Recorded > 1 h after occurred_at (alerted).")
    suspended_lines: list[CertLineRef]
    cleared_by: CertLineRef | None = Field(
        description="The after_configuration_change / after_repair line inspected on or after "
        "occurred_at that cleared it."
    )
    cleared_at: datetime | None
    obstacle_clearances_rechecked: list[str] = Field(
        default_factory=list, description="CF-4 obstacle clearance refs re-checked."
    )


class ConfigurationEventList(ApiModel):
    items: list[ConfigurationEventRead]


# ---- deployments (§3.5, EM-) -------------------------------------------------------------------


class EquipmentDeploymentCreate(StrictInput):
    """Capability 106 → Planned. Engagement of the owner (or hiring) contractor on the
    project, contractor Approved (EQ-5); tag unique on the project among non-demobilised
    deployments (409 TAG_EXISTS, case-insensitive); site_ids ⊆ engagement sites; one
    non-demobilised deployment per item org-wide (422 EQUIPMENT_DEPLOYED_ELSEWHERE)."""

    equipment_id: uuid.UUID
    engagement_id: uuid.UUID
    tag: str = Field(pattern=TAG_PATTERN, examples=["TC-01"], description="Stored upper-case.")
    site_ids: list[uuid.UUID] = Field(min_length=1)
    zone_id: uuid.UUID | None = None
    planned_arrival_on: date


class EquipmentDeploymentUpdate(PatchInput):
    non_nullable = frozenset({"tag", "site_ids", "planned_arrival_on"})

    tag: str | None = Field(default=None, pattern=TAG_PATTERN)
    site_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    zone_id: uuid.UUID | None = None
    planned_arrival_on: date | None = None


class EquipmentDeploymentTransition(StrictInput):
    """§4.3: planned → approved (109; EM-2: item In Service — 422 EQUIPMENT_NOT_IN_SERVICE
    with meta.reason; contractor not suspended — 403/422 CONTRACTOR_SUSPENDED; issues the EQ
    sticker); planned → cancelled (106 / 109); approved → on_site (109 manual arrival, or the
    first gate `in` scan, GE-3); on_site / approved → demobilised (109; Contractor HSE Rep
    for own engagement; revokes the token, EM-5)."""

    to_status: EquipmentDeploymentStatus
    reason: str | None = Field(default=None, max_length=500)
    arrived_at: datetime | None = Field(default=None, description="Manual arrival; default now.")
    demobilised_on: date | None = Field(default=None, description="Default today.")


class ArrivalChecklistLine(StrictInput):
    item: ArrivalChecklistItem
    result: ChecklistItemResult
    defect_category: DefectCategory | None = Field(
        default=None, description="Required for a failed item: creates a Defect (EM-3)."
    )
    defect_description: str | None = Field(default=None, max_length=1000)


class ArrivalInspectionInput(StrictInput):
    """EM-3 (capability 109; site engineers too): every AIC item pass or n.a. for `pass`."""

    inspected_at: datetime | None = Field(default=None, description="UTC; default now.")
    checklist: list[ArrivalChecklistLine] = Field(min_length=8, max_length=8)
    notes: str | None = Field(default=None, max_length=500)


class ArrivalChecklistLineRead(ApiModel):
    item: ArrivalChecklistItem
    label_en: str
    label_ar: str
    result: ChecklistItemResult


class ArrivalInspectionRead(ApiModel):
    at: datetime
    by: UserRef
    checklist: list[ArrivalChecklistLineRead]
    result: PassFail
    notes: str | None
    defects: list[DefectRef]


class EquipmentDeploymentRead(ApiModel):
    id: uuid.UUID
    deployment_no: str = Field(examples=["EQD-RBT-52-0001"])
    project_id: uuid.UUID
    equipment: EquipmentRef
    engagement: EngagementRef
    tag: str
    sites: list[SiteRef]
    zone: ZoneRef | None
    planned_arrival_on: date
    approved_by: UserRef | None
    approved_at: datetime | None
    arrived_at: datetime | None
    arrival_inspection: ArrivalInspectionRead | None
    arrival_inspection_due_at: datetime | None = Field(
        description="arrived_at + arrival_inspection_hours while not passed."
    )
    status: EquipmentDeploymentStatus
    demobilised_on: date | None
    sticker_printed_ref: str | None = Field(examples=["RBT-52-TC-01"])
    has_sticker: bool
    usable: bool = Field(description="§6.6 'item usable' on this project today.")
    not_usable_reason: str | None = Field(
        description="HookReasonCode / SSR of the first failing check (HK4-8 order)."
    )
    warnings: list[ApiWarning]
    created_at: datetime
    updated_at: datetime


class EquipmentDeploymentPage(Page[EquipmentDeploymentRead]):
    pass


class EquipmentStickerRead(ApiModel):
    """EQ sticker (EM-2 / §3.8): `qr_payload` + `printed_ref` beside it; no personal data."""

    deployment: DeploymentRef | None
    scaffold_id: uuid.UUID | None = None
    qr_payload: str = Field(pattern=QR_EQ, description=QR_PAYLOAD_DOC)
    printed_ref: str = Field(examples=["RBT-52-TC-01", "ANIA-EXP-SC-0142"])
    category: EquipmentCertCategory
    tag: str
    owner_short_code: str
    issued_at: datetime


class StickerReissueRequest(StrictInput):
    """Rotates the token: the old sticker then scans as CREDENTIAL_REVOKED."""

    reason: str = Field(min_length=10, max_length=300)
