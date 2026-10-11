"""Option 7a vehicle accident details (spec 7a-vehicle-accident-details v1.1 §3, §5, §8). Every
schema carries the `Veh` prefix so no OpenAPI component of an earlier module changes name
(DECISIONS D-202)."""

import uuid
from datetime import date, datetime

from pydantic import Field, field_validator

from app.core.access_enums import LicenceClass, LicenceIssuer, PlateType
from app.core.hse_enums import ExternalBody
from app.core.vehicle_enums import (
    VehCategory,
    VehDamage,
    VehDocState,
    VehDriverKind,
    VehJourneyPurpose,
    VehLicenceCheck,
    VehLight,
    VehOwnership,
    VehReportAuthority,
    VehRoadType,
    VehRole,
    VehSeatBelt,
    VehSpeedSource,
    VehSurface,
)
from app.schemas.common import ApiModel, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, SarAmount, UserRef

LIABILITY = (0, 25, 50, 75, 100)
PLATE_DIGITS = r"^\d{1,4}$"
REASON_HINT = "Required (≥ 20 characters) once the investigation is approved (Phase 1 rule, 7a §4)."


def _liability(v: int | None) -> int | None:
    if v is not None and v not in LIABILITY:
        raise ValueError("liability_pct_own must be 0, 25, 50, 75 or 100")
    return v


# ---- incident-level fields (embedded in IncidentCreate / IncidentUpdate) -------------------------


class VehDocsInput(StrictInput):
    """Documents valid at the time, entered when the row has no register vehicle (VA-4)."""

    istimara: VehDocState = VehDocState.unknown
    insurance: VehDocState = VehDocState.unknown
    mvpi: VehDocState = VehDocState.unknown


class VehDocsRead(ApiModel):
    istimara: VehDocState
    insurance: VehDocState
    mvpi: VehDocState
    source: str = Field(
        description="`register` (computed from the Phase 2 vehicle at the occurred date and "
        "frozen at Closed, VA-4) or `entered`."
    )


class VehVehicleRef(ApiModel):
    id: uuid.UUID
    vehicle_no: str = Field(examples=["VEH-0002"])


class VehWorkerRef(ApiModel):
    """Driver identity (capability 29 only, P7a-1)."""

    id: uuid.UUID
    worker_no: str
    full_name_en: str
    full_name_ar: str | None = None


# ---- vehicle rows (§3.2) -------------------------------------------------------------------------


class _VehRowFields(StrictInput):
    engagement_id: uuid.UUID | None = Field(
        default=None,
        description="Required for own_company / contractor / hired: an engagement of the project.",
    )
    vehicle_id: uuid.UUID | None = Field(
        default=None,
        description="Phase 2 vehicle of the same project; prefills plate, category, make_model and "
        "computes docs_valid_at_time (VA-4).",
    )
    plate_type: PlateType | None = None
    plate_letters_ar: str | None = Field(default=None, max_length=5, examples=["ح ط ر"])
    plate_letters_en: str | None = Field(default=None, max_length=3, examples=["JTR"])
    plate_digits: str | None = Field(default=None, pattern=PLATE_DIGITS, examples=["9012"])
    category: VehCategory | None = None
    make_model: str | None = Field(default=None, max_length=60)
    damage: VehDamage | None = None
    damage_cost_sar: SarAmount | None = None
    docs: VehDocsInput | None = Field(
        default=None, description="Only when vehicle_id is not set (otherwise computed)."
    )
    insurer: str | None = Field(default=None, max_length=80, description="third_party only.")
    policy_no: str | None = Field(default=None, max_length=40, description="third_party only.")
    seat_belt: VehSeatBelt | None = None
    speed_kmh: int | None = Field(default=None, ge=0, le=250)
    speed_limit_kmh: int | None = Field(default=None, ge=5, le=140)
    speed_source: VehSpeedSource | None = None
    driver_kind: VehDriverKind | None = None
    worker_id: uuid.UUID | None = Field(
        default=None,
        description="driver_kind worker: a Phase 2 worker with a deployment on the project; an "
        "ADP on the project prefills licence issuer, class and expiry (VA-3).",
    )
    external_driver_name: str | None = Field(default=None, max_length=120)
    licence_issuer: LicenceIssuer | None = None
    licence_class: LicenceClass | None = None
    licence_expiry: date | None = None
    licence_no: str | None = Field(
        default=None,
        max_length=30,
        description="GCC / international licences only; a KSA licence number is never stored "
        "(it equals the holder's ID) → 422.",
    )
    hours_on_duty: DecimalStr | None = Field(
        default=None, ge=0, le=24, max_digits=4, decimal_places=1
    )
    driver_case_no: int | None = Field(
        default=None, ge=1, description="person_no of an injury case on this incident."
    )
    adp_offence_id: uuid.UUID | None = Field(
        default=None, description="Phase 2 airside offence of the same project (VA-8)."
    )
    reason: str | None = Field(default=None, max_length=1000, description=REASON_HINT)


class VehIncidentVehicleCreate(_VehRowFields):
    """Add a vehicle row (1–10 per incident). Only ownership and role are needed now; the rest is
    required before the investigation is submitted (VA-2). 422 `PLATE_IS_REGISTERED` when a
    third_party plate is in the Phase 2 register (VA-6)."""

    ownership: VehOwnership
    role: VehRole


class VehIncidentVehicleUpdate(PatchInput):
    """Edit a vehicle row while the incident is not Closed or Voided."""

    non_nullable = frozenset({"ownership", "role"})

    ownership: VehOwnership | None = None
    role: VehRole | None = None
    engagement_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    plate_type: PlateType | None = None
    plate_letters_ar: str | None = Field(default=None, max_length=5)
    plate_letters_en: str | None = Field(default=None, max_length=3)
    plate_digits: str | None = Field(default=None, pattern=PLATE_DIGITS)
    category: VehCategory | None = None
    make_model: str | None = Field(default=None, max_length=60)
    damage: VehDamage | None = None
    damage_cost_sar: SarAmount | None = None
    docs: VehDocsInput | None = None
    insurer: str | None = Field(default=None, max_length=80)
    policy_no: str | None = Field(default=None, max_length=40)
    seat_belt: VehSeatBelt | None = None
    speed_kmh: int | None = Field(default=None, ge=0, le=250)
    speed_limit_kmh: int | None = Field(default=None, ge=5, le=140)
    speed_source: VehSpeedSource | None = None
    driver_kind: VehDriverKind | None = None
    worker_id: uuid.UUID | None = None
    external_driver_name: str | None = Field(default=None, max_length=120)
    licence_issuer: LicenceIssuer | None = None
    licence_class: LicenceClass | None = None
    licence_expiry: date | None = None
    licence_no: str | None = Field(default=None, max_length=30)
    hours_on_duty: DecimalStr | None = Field(
        default=None, ge=0, le=24, max_digits=4, decimal_places=1
    )
    driver_case_no: int | None = Field(default=None, ge=1)
    adp_offence_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=1000, description=REASON_HINT)


class VehIncidentVehicleRead(ApiModel):
    """One vehicle row. Driver identity, licence class / expiry / number, hours on duty, insurer,
    policy and third-party plates are personal (P7a-1): they are null without capability 29 and
    `redacted_groups` says so; `licence_check` and `driver_summary_*` stay visible. Reads that
    return identity are audited (`sensitive_field_read`)."""

    id: uuid.UUID
    incident_id: uuid.UUID
    seq: int
    label: str = Field(examples=["V1"])
    ownership: VehOwnership
    engagement: EngagementRef | None
    vehicle: VehVehicleRef | None
    suggested_vehicle: VehVehicleRef | None = Field(
        default=None,
        description="VA-6: own / contractor / hired row without vehicle_id whose plate matches the "
        "Phase 2 register.",
    )
    plate_type: PlateType | None
    plate_letters_ar: str | None
    plate_letters_en: str | None
    plate_digits: str | None
    category: VehCategory | None
    make_model: str | None
    role: VehRole
    damage: VehDamage | None
    damage_cost_sar: SarAmount | None
    docs_valid_at_time: VehDocsRead
    insurer: str | None
    policy_no: str | None
    seat_belt: VehSeatBelt | None
    speed_kmh: int | None
    speed_limit_kmh: int | None
    speed_source: VehSpeedSource | None
    driver_kind: VehDriverKind | None
    worker: VehWorkerRef | None
    external_driver_name: str | None
    licence_issuer: LicenceIssuer | None
    licence_class: LicenceClass | None
    licence_expiry: date | None
    licence_no: str | None
    licence_prefilled_from_adp: bool
    licence_check: VehLicenceCheck | None = Field(description="VA-3; visible to every reader.")
    hours_on_duty: DecimalStr | None
    driver_case_no: int | None
    adp_offence_id: uuid.UUID | None
    driver_summary_en: str = Field(examples=["Driver: worker of GULFPAVE · licence valid"])
    driver_summary_ar: str
    redacted_groups: list[str] = Field(
        description="['driver_identity'] when personal fields were withheld (P7a-1)."
    )
    warnings: list[ApiWarning] = Field(
        default_factory=list,
        description="VEHICLE_DOCS_EXPIRED_AT_TIME, LICENCE_NOT_VALID_AT_TIME (not blocking).",
    )
    created_at: datetime
    updated_at: datetime


class VehIncidentVehicleList(ApiModel):
    items: list[VehIncidentVehicleRead]


# ---- section read --------------------------------------------------------------------------------


class VehPrompt(ApiModel):
    """VA-4 investigation prompt (a required root-cause consideration, not a block)."""

    code: str = Field(examples=["VEHICLE_DOCS_EXPIRED_AT_TIME", "LICENCE_NOT_VALID_AT_TIME"])
    vehicle_seq: int
    message_en: str
    message_ar: str


class VehSubmissionOffer(ApiModel):
    """AC21: report_no is entered and the police / Najm notification is still open → the UI
    offers to record the submission with this reference (6f requirement or Phase 1 I-20 row)."""

    body: ExternalBody
    reference_no: str
    requirement_id: uuid.UUID | None = Field(
        description="6f requirement to record against; null = the Phase 1 external notification."
    )


class VehReportFileRead(ApiModel):
    """An archived report file (capability 29 only, VA-15). Superseded versions are kept."""

    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: UserRef
    created_at: datetime
    superseded: bool
    superseded_by_id: uuid.UUID | None
    superseded_at: datetime | None


class VehAccidentReportRead(ApiModel):
    """The "Accident report (archive)" card (VA-14, VA-15). Internal record: no client copy.
    Files are listed only for capability 29 (`files_visible`); others see number and date only."""

    incident_id: uuid.UUID
    report_authority: VehReportAuthority | None
    report_no: str | None
    report_date: date | None
    liability_pct_own: int | None
    required_to_close: bool = Field(
        description="report_authority ≠ none_internal and not waived through 6f (VA-5, VA-14)."
    )
    waived: bool
    locked: bool = Field(description="Incident Closed: files may be added, none deleted.")
    missing_to_close: list[str] = Field(examples=[["report_no", "report_date", "report_files"]])
    file_count: int = Field(description="Current (not superseded) files.")
    files_visible: bool
    files: list[VehReportFileRead]


class VehAccidentReportUpdate(StrictInput):
    """Set the report record (allowed until the incident is Closed, also while Pending Review or
    Actions Pending). public_road requires an authority ≠ none_internal
    (`ACCIDENT_REPORT_AUTHORITY_REQUIRED`)."""

    report_authority: VehReportAuthority | None = None
    report_no: str | None = Field(default=None, max_length=40, examples=["NJM-TEST-2026-00871"])
    report_date: date | None = Field(default=None, description="≥ the occurred date.")
    liability_pct_own: int | None = Field(default=None, description="0, 25, 50, 75 or 100.")
    reason: str | None = Field(default=None, max_length=1000, description=REASON_HINT)

    _check_liability = field_validator("liability_pct_own")(_liability)


class VehSectionRead(ApiModel):
    """The incident's vehicle section (7a §3.1, §8). Present when vehicle_involved."""

    vehicle_involved_locked: bool = Field(
        description="VA-1 signal holds (vehicle mechanism / agency, pd vehicle, DO vehicle "
        "overturn, airside vehicle flag): vehicle_involved cannot be cleared."
    )
    road_type: VehRoadType | None
    road_location: str | None
    journey_purpose: VehJourneyPurpose | None
    light: VehLight | None
    surface: VehSurface | None
    third_party_damage_desc: str | None
    third_party_damage_cost_sar: SarAmount | None
    recorded_not_counted: bool = Field(
        description="VA-13: commuting journey → 'Recorded, not counted — commuting (OSHA)'."
    )
    vehicles: list[VehIncidentVehicleRead]
    accident_report: VehAccidentReportRead
    missing_for_report: list[str] = Field(
        description="VA-2: fields needed for Draft → Reported (road_type, vehicles)."
    )
    missing_for_investigation: list[str] = Field(
        description="VA-2: fields needed before the investigation is submitted for approval "
        "(e.g. journey_purpose, V1.seat_belt)."
    )
    investigation_prompts: list[VehPrompt]
    commuting_proposed_case_ids: list[uuid.UUID] = Field(
        description="VA-7: worker cases proposed commuting = true (the classifier confirms)."
    )
    report_submission_offer: VehSubmissionOffer | None


class VehPrefillVehicle(ApiModel):
    id: uuid.UUID
    vehicle_no: str
    engagement: EngagementRef | None
    category: VehCategory
    make_model: str
    plate_type: PlateType
    plate_letters_ar: str | None
    plate_letters_en: str | None
    plate_digits: str | None
    docs_valid_at_time: VehDocsRead


class VehPrefillDriver(ApiModel):
    """VA-3 / AC8: a worker driver holding an ADP on the project. No KSA licence number field."""

    worker_id: uuid.UUID
    has_adp: bool
    adp_no: str | None
    licence_issuer: LicenceIssuer | None
    licence_class: LicenceClass | None
    licence_expiry: date | None
    licence_number_field: bool = Field(
        description="False for KSA licences (the number equals the holder's ID and is never "
        "stored)."
    )


class VehPrefillRead(ApiModel):
    vehicle: VehPrefillVehicle | None = Field(
        description="Register vehicle (by vehicle_id, or matched by normalised plate, VA-6)."
    )
    plate_registered: bool = Field(
        description="The plate is in the Phase 2 register (a third_party row would get "
        "PLATE_IS_REGISTERED)."
    )
    driver: VehPrefillDriver | None
