"""Airside driving permits, offences, vehicles and airside vehicle permits
(spec 2-access-permits §3.10-§3.13, §5.5, §5.6, §6.5)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    AreaCategory,
    AvpChecklistItem,
    ChecklistOutcome,
    InspectionResult,
    LicenceClass,
    LicenceIssuer,
    OffenceStatus,
    PlateType,
    PracticalTestResult,
    QrTokenStatus,
    VehicleCategory,
    VehicleClass,
    VehicleOwnerType,
    VehicleStatus,
)
from app.schemas.access_common import (
    QR_PAYLOAD_DOC,
    Metres,
    ValidityBlock,
    VehicleRef,
    WorkerRef,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, UserRef, ZoneRef

PCT = r"^\d{1,3}(\.\d{1,2})?$"

# ---- ADP ----------------------------------------------------------------------------------------


class AdpCreate(StrictInput):
    """Apply for an ADP (capability 60) → validity_status pending. One Active ADP per worker per
    project (409 ADP_EXISTS, DP-2). Licence number is not stored (minimisation)."""

    deployment_id: uuid.UUID
    category: AreaCategory
    vehicle_classes: list[VehicleClass] = Field(min_length=1)
    licence_issuer: LicenceIssuer
    licence_class: LicenceClass
    licence_expiry_date: date


class AdpUpdate(PatchInput):
    """Pending ADPs: licence data (60) and tests (61)."""

    category: AreaCategory | None = None
    vehicle_classes: list[VehicleClass] | None = Field(default=None, min_length=1)
    licence_issuer: LicenceIssuer | None = None
    licence_class: LicenceClass | None = None
    licence_expiry_date: date | None = None
    theory_test_date: date | None = None
    theory_score_pct: str | None = Field(default=None, pattern=PCT)
    practical_test_date: date | None = None
    practical_result: PracticalTestResult | None = None
    practical_examiner: str | None = Field(default=None, max_length=120)
    practical_included_manoeuvring: bool | None = Field(
        default=None, description="DP-5 for manoeuvring."
    )
    rtf_competence: bool | None = None


class AdpIssueRequest(StrictInput):
    """pending → active (capability 61). Checks DP-3 (ADP_PASS_REQUIRED), DP-4
    (LICENCE_NOT_VALID), DP-5 (RTF_REQUIRED), DP-6 (TESTS_NOT_VALID: theory ≥
    adp_theory_pass_pct and practical passed, both ≤ 90 days before issued_on);
    own_valid_until ≤ issued_on + adp_validity_months."""

    adp_no: str = Field(min_length=1, max_length=30, examples=["ADP-OEXX-26-0042"])
    issued_on: date
    own_valid_until: date


class AdpPoints(ApiModel):
    """§6.5: Σ points of recorded/upheld/disputed offences with local date in
    (as_of − adp_points_window_days, as_of]."""

    as_of: date
    points_12m: int
    threshold: int
    window_start_exclusive: date
    offence_ids: list[uuid.UUID]


class AdpRead(Timestamps):
    id: uuid.UUID
    adp_no: str | None = Field(description="Null while pending.")
    project_id: uuid.UUID
    worker: WorkerRef
    deployment_id: uuid.UUID
    engagement: EngagementRef | None
    category: AreaCategory
    vehicle_classes: list[VehicleClass]
    licence_issuer: LicenceIssuer
    licence_class: LicenceClass
    licence_expiry_date: date
    theory_test_date: date | None
    theory_score_pct: str | None
    practical_test_date: date | None
    practical_result: PracticalTestResult | None
    practical_examiner: str | None
    practical_included_manoeuvring: bool | None
    rtf_competence: bool | None
    issued_on: date | None
    own_valid_until: date | None
    pass_id: uuid.UUID | None = Field(description="The pass the ADP depends on (DP-3).")
    points: AdpPoints | None
    suspension_count_window: int = Field(description="DP-9 suspensions in the revoke window.")
    validity: ValidityBlock


class AdpPage(Page[AdpRead]):
    pass


# ---- offences -----------------------------------------------------------------------------------


class OffenceCreate(StrictInput):
    """Capability 62. Points come from list OFF at offence time. OFF-05/OFF-06 suspend the ADP
    immediately (`violation`, DP-9); reaching adp_points_threshold auto-suspends (DP-8); the
    n-th suspension in the window revokes (DP-9). Without an Active ADP the offence is recorded
    against the worker (DP-11). Evidence: POST /attachments (owner_type offence_evidence)."""

    worker_id: uuid.UUID
    offence_code: str = Field(pattern=r"^OFF-\d{2}$", examples=["OFF-01"])
    offence_at: datetime
    zone_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = Field(default=None, description="Phase 1 incident.")
    notes: str | None = Field(default=None, max_length=500)


class OffenceTransitionRequest(StrictInput):
    """recorded → disputed / upheld / withdrawn; disputed → upheld / withdrawn (capability 58).
    Withdrawing recomputes points but never auto-reinstates (DP-10)."""

    to_status: OffenceStatus
    reason: str = Field(min_length=10, max_length=500)


class OffenceRead(Timestamps):
    id: uuid.UUID
    offence_no: str = Field(examples=["OFF-ANIA-EXP-2026-0031"])
    project_id: uuid.UUID
    worker: WorkerRef
    adp_id: uuid.UUID | None
    adp_no: str | None
    offence_code: str
    offence_label_en: str
    offence_label_ar: str
    offence_at: datetime
    zone: ZoneRef
    vehicle: VehicleRef | None
    points: int
    immediate_suspension: bool
    reported_by: UserRef
    incident_id: uuid.UUID | None
    notes: str | None
    status: OffenceStatus
    evidence_count: int
    resulting_actions: list[str] = Field(
        description="e.g. ['adp_suspended_points', 'adp_revoked'] caused by this offence."
    )


class OffencePage(Page[OffenceRead]):
    pass


# ---- vehicles -----------------------------------------------------------------------------------


class VehicleFields(StrictInput):
    engagement_id: uuid.UUID
    owner_type: VehicleOwnerType
    category: VehicleCategory
    plate_type: PlateType
    plate_letters_ar: str | None = Field(
        default=None, max_length=5, description="Required iff plate_type ≠ none (3 letters)."
    )
    plate_letters_en: str | None = Field(default=None, max_length=3)
    plate_digits: str | None = Field(default=None, pattern=r"^\d{1,4}$")
    fleet_no: str = Field(min_length=1, max_length=20)
    serial_or_vin: str = Field(
        min_length=1, max_length=30, description="VIN ^[A-HJ-NPR-Z0-9]{17}$ for road vehicles."
    )
    make_model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1990)
    colour: str = Field(min_length=1, max_length=30)
    travel_height_m: Metres = Field(description="0.5-20 m.")
    max_working_height_m_agl: Metres = Field(description="≥ travel height (OB-2).")
    istimara_expiry: date | None = Field(default=None, description="Required iff plated.")
    insurance_policy_no: str = Field(min_length=1, max_length=40)
    insurance_expiry: date
    mvpi_expiry: date | None = Field(default=None, description="Required iff plated (Fahas).")


class VehicleCreate(VehicleFields):
    """Capability 63; 422 NOT_AIRPORT_PROJECT on non-airport projects (AP-2). Duplicate plate
    (org-wide) or serial/VIN (project) → 409 DUPLICATE_VALUE (VP-1)."""


class VehicleUpdate(PatchInput):
    """A later document expiry auto-reinstates `vehicle_document_expired` suspensions (VP-5)."""

    non_nullable = frozenset(
        {
            "owner_type",
            "category",
            "plate_type",
            "fleet_no",
            "serial_or_vin",
            "make_model",
            "year",
            "colour",
            "travel_height_m",
            "max_working_height_m_agl",
            "insurance_policy_no",
            "insurance_expiry",
        }
    )

    owner_type: VehicleOwnerType | None = None
    category: VehicleCategory | None = None
    plate_type: PlateType | None = None
    plate_letters_ar: str | None = Field(default=None, max_length=5)
    plate_letters_en: str | None = Field(default=None, max_length=3)
    plate_digits: str | None = Field(default=None, pattern=r"^\d{1,4}$")
    fleet_no: str | None = Field(default=None, min_length=1, max_length=20)
    serial_or_vin: str | None = Field(default=None, min_length=1, max_length=30)
    make_model: str | None = Field(default=None, min_length=1, max_length=80)
    year: int | None = Field(default=None, ge=1990)
    colour: str | None = Field(default=None, min_length=1, max_length=30)
    travel_height_m: Metres | None = None
    max_working_height_m_agl: Metres | None = None
    istimara_expiry: date | None = None
    insurance_policy_no: str | None = Field(default=None, min_length=1, max_length=40)
    insurance_expiry: date | None = None
    mvpi_expiry: date | None = None


class VehicleTransitionRequest(StrictInput):
    to_status: VehicleStatus
    reason: str | None = Field(default=None, max_length=500)


class VehicleRead(Timestamps):
    """Plates of individually owned vehicles are personal data: plate fields are null for
    callers without capability 46 (and always in Viewer aggregates, KA-4)."""

    id: uuid.UUID
    vehicle_no: str = Field(examples=["VEH-0002"])
    project_id: uuid.UUID
    engagement: EngagementRef
    owner_type: VehicleOwnerType
    category: VehicleCategory
    plate_type: PlateType
    plate_letters_ar: str | None
    plate_letters_en: str | None
    plate_digits: str | None
    fleet_no: str
    serial_or_vin: str
    make_model: str
    year: int
    colour: str
    travel_height_m: DecimalStr
    max_working_height_m_agl: DecimalStr
    max_working_height_ft: DecimalStr = Field(description="m ÷ 0.3048, 2 dp (OB-9).")
    istimara_expiry: date | None
    insurance_policy_no: str
    insurance_expiry: date
    mvpi_expiry: date | None
    documents_valid: bool
    earliest_document_expiry: date | None
    status: VehicleStatus
    active_avp_id: uuid.UUID | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class VehiclePage(Page[VehicleRead]):
    pass


# ---- AVP ----------------------------------------------------------------------------------------


class AvpCreate(StrictInput):
    """Apply for an AVP (capability 63) → pending. One Active AVP per vehicle (409 AVP_EXISTS);
    areas must correspond to airside sites of the owning engagement (VP-2)."""

    vehicle_id: uuid.UUID
    areas: list[AreaCategory] = Field(min_length=1)


class AvpUpdate(PatchInput):
    """Inspection and checklist (capability 64) while pending."""

    areas: list[AreaCategory] | None = Field(default=None, min_length=1)
    inspection_date: date | None = None
    inspector: str | None = Field(default=None, max_length=120)
    inspection_result: InspectionResult | None = None
    checklist: dict[AvpChecklistItem, ChecklistOutcome] | None = None


class AvpIssueRequest(StrictInput):
    """pending → active (capability 64). VP-3/VP-4 → 422 AVP_PRECONDITION (inspection passed ≤
    14 days, documents valid, checklist complete, n.a. not allowed for amber_beacon,
    company_marking, fire_extinguisher, tyres_brakes, lights; height_marking when > 3.00 m;
    manoeuvring needs radio_fitted and chequered_flag_or_marking = pass)."""

    avp_no: str = Field(min_length=1, max_length=30, examples=["AVP-OEXX-26-0118"])
    sticker_no: str = Field(min_length=1, max_length=20, examples=["AVP-S-0118"])
    issued_on: date
    own_valid_until: date


class AvpRead(Timestamps):
    id: uuid.UUID
    avp_no: str | None
    project_id: uuid.UUID
    vehicle: VehicleRef
    engagement: EngagementRef
    areas: list[AreaCategory]
    inspection_date: date | None
    inspector: str | None
    inspection_result: InspectionResult | None
    checklist: dict[AvpChecklistItem, ChecklistOutcome]
    checklist_problems: list[AvpChecklistItem] = Field(description="Items blocking issue.")
    sticker_no: str | None
    sticker_token_status: QrTokenStatus | None
    issued_on: date | None
    own_valid_until: date | None
    validity: ValidityBlock
    hook_warnings: list[str] = Field(
        description="Equipment-certificate hook results (VP-6), e.g. 'CRANE-TPI: warn'."
    )


class AvpPage(Page[AvpRead]):
    pass


class AvpStickerRead(ApiModel):
    avp_id: uuid.UUID
    avp_no: str
    sticker_no: str
    vehicle_no: str
    fleet_no: str
    qr_payload: str = Field(
        pattern=r"^HSE2:VS:[A-Za-z0-9_-]{22}$",
        examples=["HSE2:VS:Zb1yQm3k9TnP0aL7cX2wRg"],
        description=QR_PAYLOAD_DOC,
    )
    printed_ref: str = Field(examples=["AVP-S-0118"])
    token_status: QrTokenStatus


class AvpStickerReissueRequest(StrictInput):
    reason: str = Field(min_length=10, max_length=500)
