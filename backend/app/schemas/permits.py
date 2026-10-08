"""Permits to work: core record, crew/equipment, documents, type sections, checklists,
lifecycle actions, shifts, handovers, suspensions, exemptions, board and print
(spec 3-ptw §3.5-§3.7, §3.13, §3.14, §4.1, §4.2, §5.1-§5.10, §8.4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.core.access_enums import FodCheckResult, NotamStatus, WapStatus
from app.core.ptw_enums import (
    AcceptancePurpose,
    AccessMethod,
    AircraftProximity,
    ChecklistAnswer,
    ChecklistKind,
    ClosureItem,
    CommunicationMethod,
    CrewLineStatus,
    CylinderKind,
    DocumentType,
    Egress,
    EnergizedJustification,
    EntryDirection,
    EquipmentCategory,
    EquipmentUse,
    ExcavationInspectionResult,
    ExcavationMethod,
    ExemptionKind,
    ExemptionStatus,
    Exposure,
    ExtinguisherType,
    FallProtection,
    GasStatus,
    HandoverStatus,
    HotWorkKind,
    LiftCriticalReason,
    MiddayExemptionReason,
    OpeningsProtected,
    PauseReason,
    PermitAction,
    PermitStatus,
    PermitType,
    PreIssueItem,
    ProtectiveSystem,
    PtwCrewRole,
    RadiationSource,
    RescueMethod,
    RiskBand,
    ShiftEndType,
    SimopsConflictStatus,
    SimopsResult,
    SoilType,
    SpaceHazard,
    StatusReason,
    Ventilation,
    VoltageClass,
    WindSource,
    WorkCondition,
    WorkStatus,
)
from app.core.ptw_enums import (
    JsaStatus as _JsaStatus,
)
from app.schemas.access_common import HookCondition, VehicleRef, WorkerRef
from app.schemas.cert_common import DeploymentRef, EquipmentRef, ScaffoldRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import (
    ApiWarning,
    DecimalStr,
    EngagementRef,
    SiteRef,
    UserRef,
    ZoneRef,
)
from app.schemas.inductions import EligibilityItem
from app.schemas.ptw_common import (
    PERMIT_NO_DOC,
    PT_QR_PATTERN,
    WINDOW_DOC,
    AppointmentRef,
    BlockerItem,
    CoSignature,
    Dec1,
    Dec2,
    Dec3,
    DetectorRef,
    GridM,
    PermitRef,
    PermitWindow,
    PermitWindowRead,
    SignatureRead,
    WarningItem,
    WindowInstance,
)

P3_HINT = "P3 hint: no ID numbers, medical details or personal mobiles of workers."

# ---- crew, equipment, documents (§3.6, §3.8) ----------------------------------------------------


class PermitCrewInput(StrictInput):
    """PT-7: worker of the permit's engagement or an ancestor engagement (CREW_NOT_IN_TREE),
    Mobilised on the project covering the site, not Banned. SoD PR-5 (f)/(g) and PR-10
    (KEY_ROLE_BUSY) are checked when added."""

    worker_id: uuid.UUID
    crew_role: PtwCrewRole
    appointment_id: uuid.UUID | None = Field(
        default=None,
        description="Required for gas_tester, competent_person, rpo, lift_supervisor (PR-4).",
    )
    escort_worker_id: uuid.UUID | None = Field(
        default=None, description="Airside escorted pass holders keep their WAP escort (AW-3)."
    )


class PermitCrewUpdate(PatchInput):
    non_nullable = frozenset({"crew_role"})

    crew_role: PtwCrewRole | None = None
    appointment_id: uuid.UUID | None = None
    escort_worker_id: uuid.UUID | None = None


class CrewEligibilityItem(EligibilityItem):
    """Phase 2 E(worker, zone, at, ptw) item plus the PTW hooks of the crew role (HK3-2).
    HK3-4/P3-3: a medical_fitness result is shown to callers without capability 56 as
    'Not eligible — HSE check' with kind/code removed (`redacted` = true)."""

    zone_id: uuid.UUID | None = None
    redacted: bool = False


class PermitCrewRead(ApiModel):
    """Viewer/Client and callers without capability 46 get `worker` = null (roles only,
    PT-19)."""

    id: uuid.UUID
    worker: WorkerRef | None
    crew_role: PtwCrewRole
    key_role: bool
    appointment: AppointmentRef | None
    escort_worker: WorkerRef | None
    status: CrewLineStatus
    excluded_reason: str | None = Field(
        description="Eligibility code, e.g. INDUCTION_EXPIRED, EXPIRES_DURING_SHIFT."
    )
    eligible: bool | None = Field(description="Null until first evaluated (Request).")
    eligibility: list[CrewEligibilityItem]
    evaluated_at: datetime | None
    briefed_current_shift: bool


class EquipmentTagInput(StrictInput):
    category: EquipmentCategory
    tag: str = Field(min_length=1, max_length=30, examples=["TC-01"], description="Per project.")
    description: str | None = Field(default=None, max_length=150)
    max_working_height_m: Dec2 | None = None


class PermitEquipmentInput(StrictInput):
    """One of vehicle_id (Phase 2 vehicle of the engagement or an ancestor) or equipment_tag
    (hook subject `equipment_tag` until Phase 4). v1.1 (4-third-party-cert §11.4): with Phase 4
    enabled, `equipment_item_id` (optional; resolved from the tag on the project when blank)
    and `operator_worker_id` — required for categories with an operator code in EQC (HK4-9,
    422 OPERATOR_REQUIRED)."""

    vehicle_id: uuid.UUID | None = None
    equipment_tag: EquipmentTagInput | None = None
    use: EquipmentUse
    equipment_item_id: uuid.UUID | None = None
    operator_worker_id: uuid.UUID | None = None


class PermitEquipmentRead(ApiModel):
    id: uuid.UUID
    vehicle: VehicleRef | None
    equipment_tag: EquipmentTagInput | None
    use: EquipmentUse
    max_working_height_m: DecimalStr | None
    hooks: list[EligibilityItem] = Field(description="HK3-2 equipment hooks (e.g. CRANE-TPI).")
    equipment_item: EquipmentRef | None = Field(
        default=None, description="v1.1: the Phase 4 item (given or resolved from the tag)."
    )
    deployment: DeploymentRef | None = Field(default=None, description="v1.1.")
    operator: WorkerRef | None = Field(
        default=None, description="v1.1 (HK4-9); name only with capability 46."
    )
    operator_hooks: list[EligibilityItem] = Field(
        default_factory=list,
        description="v1.1: operator-code hook results with the HK-3 context (HK4-9).",
    )
    conditions: list[HookCondition] = Field(
        default_factory=list, description="v1.1: limitations from the in-force line."
    )
    swl_t: DecimalStr | None = Field(default=None, description="v1.1: SWL of the in-force line.")


class PermitDocumentInput(StrictInput):
    doc_type: DocumentType
    ref: str = Field(min_length=1, max_length=40, examples=["RP-MSCP-02"])
    revision: str = Field(min_length=1, max_length=6, examples=["B"])
    attachment_id: uuid.UUID | None = Field(
        default=None, description="Optional file (PDF/image ≤ 20 MB, owner permit_document)."
    )
    approved_by_text: str | None = Field(
        default=None,
        max_length=120,
        description="Required for lift / critical-lift / rescue / PE-design plans.",
    )
    valid_until: date | None = None


class PermitDocumentRead(ApiModel):
    id: uuid.UUID
    doc_type: DocumentType
    ref: str
    revision: str
    attachment_id: uuid.UUID | None
    approved_by_text: str | None
    valid_until: date | None
    added_by: UserRef
    added_at: datetime


# ---- type sections (§3.7) -----------------------------------------------------------------------


class ExtinguisherInput(StrictInput):
    type: ExtinguisherType
    count: int = Field(ge=1, le=20)
    distance_m: Dec1 = Field(description="≤ hw_extinguisher_max_m (9.0) for at least one.")


class HotWorkSectionInput(StrictInput):
    """§3.7.1, HW-1…HW-9. combustibles_cleared_radius_m ≥ hw_combustible_clearance_m or a
    protection method (AC53); oxy_fuel needs flashback arrestors both ends; zone_0/zone_1 →
    422 HAZARDOUS_AREA_PROHIBITED; airside apron with hydrant pits → AW-6 (AIRCRAFT_PROXIMITY)."""

    work_type: Literal["hot_work"] = "hot_work"
    hot_work_kind: list[HotWorkKind] = Field(min_length=1)
    combustibles_cleared_radius_m: Dec1
    combustibles_protected_method: str | None = Field(default=None, max_length=200)
    fire_extinguishers: list[ExtinguisherInput] = Field(min_length=1)
    fire_blanket: bool
    work_height_above_floor_m: Dec2 = Decimal("0.00")
    openings_below_protected: OpeningsProtected = OpeningsProtected.na
    fire_system_impairment: bool = False
    impairment_hours_24h: Dec1 | None = None
    civil_defense_notified_at: datetime | None = Field(
        default=None, description="Required before Issue when impairment_hours_24h > 4 (HW-8)."
    )
    impairment_ref: str | None = Field(default=None, max_length=40)
    cylinders: CylinderKind = CylinderKind.none
    flashback_arrestors_both_ends: bool | None = None


class HotWorkSectionRead(HotWorkSectionInput):
    hot_work_ended_at: datetime | None
    fire_watch_until: datetime | None = Field(
        description="hot_work_ended_at + fire_watch_post_minutes (HW-4)."
    )
    hot_work_late: bool = Field(description="HW-5: ended after valid_to − fire watch.")
    latest_compliant_end_at: datetime = Field(description="valid_to_at − fire_watch_post_minutes.")


class CseHeatControls(StrictInput):
    """HT-6 controls when internal_temp_c ≥ cse_heat_control_temp_c."""

    forced_cool_air_ventilation: bool
    stay_time_max_minutes: int = Field(ge=5, le=30)
    water_at_entry: bool


class ConfinedSpaceSectionInput(StrictInput):
    """§3.7.2, CS-1…CS-7."""

    work_type: Literal["confined_space"] = "confined_space"
    space_id_desc: str = Field(min_length=1, max_length=150)
    space_hazards: list[SpaceHazard] = Field(min_length=1)
    isolations_required: bool = False
    ventilation: Ventilation
    ventilation_justification: str | None = Field(
        default=None, max_length=500, description="≥ 30 chars when none_justified (CS-4)."
    )
    continuous_monitor_detector_id: uuid.UUID
    rescue_method: RescueMethod
    rescue_response_minutes: int | None = Field(
        default=None,
        ge=1,
        le=60,
        description="external_rescue_service: ≤ cse_rescue_max_minutes, documented.",
    )
    rescue_equipment_checked: bool
    communication_method: CommunicationMethod
    heat_controls: CseHeatControls | None = None


class EntryLogRead(ApiModel):
    id: uuid.UUID
    worker: WorkerRef | None = Field(description="Null without capability 46.")
    in_at: datetime
    out_at: datetime | None


class ConfinedSpaceSectionRead(ConfinedSpaceSectionInput):
    continuous_monitor: DetectorRef | None
    internal_temp_c: DecimalStr | None = Field(description="Latest, from the gas tests (GT-9).")
    persons_inside: int
    entry_log: list[EntryLogRead]


class WorkAtHeightSectionInput(StrictInput):
    """§3.7.3, WH-1…WH-7. Fall clearance per §6.9 (FALL_CLEARANCE_INSUFFICIENT)."""

    work_type: Literal["work_at_height"] = "work_at_height"
    max_fall_height_m: Dec2
    access_method: list[AccessMethod] = Field(min_length=1)
    fall_protection: FallProtection
    anchor_desc: str | None = Field(default=None, max_length=150)
    anchor_rating_kn: Dec1 | None = Field(default=None, description="≥ 22.2 kN per person.")
    engineered_anchor_cert_ref: str | None = Field(default=None, max_length=40)
    lanyard_length_m: Dec2 | None = Field(default=None, le=Decimal("1.80"))
    manufacturer_deceleration_m: Dec2 | None = Field(
        default=None, description="§6.9 uses max(1.07, this)."
    )
    srl_required_clearance_m: Dec2 | None = None
    available_clearance_m: Dec2 | None = None
    scaffold_tag_ref: str | None = Field(default=None, max_length=30)
    drop_zone_controlled: bool
    tool_tethering: bool


class WorkAtHeightSectionRead(WorkAtHeightSectionInput):
    scaffold: ScaffoldRef | None = Field(
        default=None,
        description="v1.1: scaffold_tag_ref resolved on the Phase 4 register of the permit's "
        "project (SF-1); null before Phase 4 or when not found.",
    )
    required_clearance_m: DecimalStr | None = Field(description="§6.9, 2 dp.")
    clearance_ok: bool | None


class ExcavationInspectionInput(StrictInput):
    """EX-6: competent-person inspection before each shift and after rain/sandstorm/events.
    `unsafe` suspends the permit."""

    inspected_at: datetime
    appointment_id: uuid.UUID = Field(description="excavation_competent_person appointment.")
    result: ExcavationInspectionResult
    after_rain_or_event: bool = False
    note: str | None = Field(default=None, max_length=500)


class ExcavationInspectionRead(ApiModel):
    id: uuid.UUID
    inspected_at: datetime
    appointment: AppointmentRef
    result: ExcavationInspectionResult
    after_rain_or_event: bool
    note: str | None
    recorded_by: UserRef


class ExcavationSectionInput(StrictInput):
    """§3.7.4, EX-1…EX-7 (AC65-AC68)."""

    work_type: Literal["excavation"] = "excavation"
    max_depth_m: Dec2 = Field(gt=Decimal(0))
    method: ExcavationMethod
    soil_type: SoilType = SoilType.type_c
    protective_system: ProtectiveSystem
    slope_ratio_h_v: DecimalStr | None = Field(
        default=None,
        max_digits=3,
        decimal_places=2,
        description="sloping: ≥ 1.50 type_c, 1.00 type_b, 0.75 type_a.",
    )
    pe_design_ref: str | None = Field(default=None, max_length=40)
    utility_clearance_ref: str | None = Field(
        default=None,
        max_length=40,
        description="Mandatory before Approve (blocker UTILITY_CLEARANCE_MISSING).",
    )
    services_within_hand_dig_zone: bool = False
    spoil_setback_m: Dec2
    egress: Egress
    egress_travel_m: Dec1 | None = Field(default=None, description="≤ ex_egress_max_m (7.5).")
    atmosphere_hazard: bool = False
    edge_barriers: bool = True
    night_lighting: bool | None = None


class ExcavationSectionRead(ExcavationSectionInput):
    inspections: list[ExcavationInspectionRead]
    inspected_for_current_shift: bool


class TestForDeadInput(StrictInput):
    done_at: datetime
    by_worker_id: uuid.UUID | None = None
    by_user_id: uuid.UUID | None = None
    instrument_tag: str = Field(min_length=1, max_length=30)
    proving_unit_used: bool
    live_dead_live: bool


class ElectricalSectionInput(StrictInput):
    """§3.7.5, EL-1…EL-4. HV energized → 422 ENERGIZED_HV_PROHIBITED; LV energized needs a
    granted `energized_work` exemption (EXEMPTION_REQUIRED) and HSE review."""

    work_type: Literal["electrical_isolation"] = "electrical_isolation"
    system_voltage_v: int = Field(gt=0, le=500_000)
    dc: bool = Field(default=False, description="DC system (voltage bands differ).")
    work_condition: WorkCondition = WorkCondition.electrically_safe
    test_for_dead: TestForDeadInput | None = Field(
        default=None, description="Required for electrically_safe before Issue (EL-02)."
    )
    hv_earths_applied: bool | None = None
    switching_programme_ref: str | None = Field(default=None, max_length=40)
    energized_justification: EnergizedJustification | None = None
    energized_justification_text: str | None = Field(default=None, max_length=500)
    limited_approach_m: Dec2 | None = None
    restricted_approach_m: Dec2 | None = None
    incident_energy_cal_cm2: DecimalStr | None = Field(
        default=None, ge=Decimal(0), max_digits=5, decimal_places=1
    )
    arc_ppe_category: int | None = Field(default=None, ge=1, le=4)
    arc_ppe_rating_cal_cm2: DecimalStr | None = Field(
        default=None, ge=Decimal(0), max_digits=5, decimal_places=1
    )


class ElectricalSectionRead(ElectricalSectionInput):
    voltage_class: VoltageClass


class WindReadingInput(StrictInput):
    """LF-6 / WH-7: at Issue and each Start/Revalidate/Resume, and on demand."""

    measured_at: datetime
    speed_ms: DecimalStr = Field(ge=Decimal(0), max_digits=4, decimal_places=1)
    source: WindSource
    source_ref: str | None = Field(default=None, max_length=40, examples=["anemometer TC-01"])


class WindReadingRead(ApiModel):
    id: uuid.UUID
    measured_at: datetime
    speed_ms: DecimalStr
    source: WindSource
    source_ref: str | None
    limit_ms: DecimalStr
    within_limit: bool
    recorded_by: UserRef


class LiftingSectionInput(StrictInput):
    """§3.7.6, LF-1…LF-9. capacity_pct > 100.0 → 422 CAPACITY_EXCEEDED; > 90.0 needs a granted
    `lift_capacity_over_90` exemption (EXEMPTION_REQUIRED)."""

    work_type: Literal["lifting"] = "lifting"
    appliance_equipment_ids: list[uuid.UUID] = Field(
        min_length=1, description="Equipment lines with use lifting_appliance (one per crane)."
    )
    tandem: bool = False
    load_desc: str = Field(min_length=1, max_length=150)
    load_weight_t: Dec3 = Field(gt=Decimal(0))
    rigging_weight_t: Dec3 = Decimal("0.000")
    radius_m: Dec2
    rated_capacity_t: Dec3 = Field(gt=Decimal(0))
    personnel_lift: bool = False
    personnel_lift_justification: str | None = Field(default=None, max_length=500)
    wind_limit_ms: DecimalStr | None = Field(
        default=None,
        ge=Decimal(0),
        max_digits=4,
        decimal_places=1,
        description="Default lift_wind_limit_ms; personnel lifts ≤ man_basket_wind_limit_ms.",
    )
    exclusion_radius_m: Dec1 = Field(ge=Decimal("3.0"))
    landing_grid_x_m: GridM | None = None
    landing_grid_y_m: GridM | None = None
    slew_radius_m: Dec1 | None = None
    appliance_grid_x_m: GridM | None = None
    appliance_grid_y_m: GridM | None = None
    ground_bearing_checked: bool | None = None
    overhead_lines_within_6m: bool = False
    passes_over_occupied_or_live: bool = False
    within_15m_of_operational_airside: bool = False


class LiftingSectionRead(LiftingSectionInput):
    gross_t: DecimalStr = Field(description="§6.6, 3 dp.")
    capacity_pct: DecimalStr = Field(description="§6.6, 1 dp half-up.")
    critical: bool
    critical_reasons: list[LiftCriticalReason]
    effective_wind_limit_ms: DecimalStr
    wind_readings: list[WindReadingRead]


class BarrierSurveyInput(StrictInput):
    measured_at: datetime
    max_usv_h: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=1)
    meter_tag: str = Field(min_length=1, max_length=30)


class BarrierSurveyRead(ApiModel):
    id: uuid.UUID
    measured_at: datetime
    max_usv_h: DecimalStr
    meter_tag: str
    within_limit: bool
    recorded_by: UserRef


class SourceReturnInput(StrictInput):
    """RG-5: closure needs a survey ≤ 2 × background."""

    at: datetime
    survey_usv_h: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=1)
    background_usv_h: DecimalStr = Field(ge=Decimal(0), max_digits=7, decimal_places=2)


class RadiographySectionInput(StrictInput):
    """§3.7.7, RG-1…RG-6. The permit grid point is the source position (SM-R01)."""

    work_type: Literal["radiography"] = "radiography"
    source_type: RadiationSource
    activity_gbq: DecimalStr | None = Field(
        default=None, gt=Decimal(0), max_digits=7, decimal_places=1
    )
    xray_dose_rate_1m_usv_h: DecimalStr | None = Field(
        default=None, gt=Decimal(0), max_digits=10, decimal_places=1
    )
    collimator_transmission: DecimalStr = Field(
        default=Decimal("1.0000"), gt=Decimal(0), le=Decimal(1), max_digits=6, decimal_places=4
    )
    planned_barrier_m: Dec1 = Field(description="≥ computed_barrier_m (BARRIER_TOO_SMALL).")
    nrrc_licence_no: str = Field(min_length=1, max_length=40)
    licence_valid_until: date
    dosimetry_confirmed: bool


class RadiographySectionRead(RadiographySectionInput):
    dose_rate_1m_usv_h: DecimalStr = Field(description="D₁ (§6.7).")
    computed_barrier_m: DecimalStr = Field(description="ceil to 0.1 m (PT-21).")
    barrier_surveys: list[BarrierSurveyRead]
    barrier_verified: bool
    source_returned: SourceReturnInput | None


class AirsideSectionInput(StrictInput):
    """§3.7.8, AW-1…AW-8. Added automatically for airside zones (cannot be removed)."""

    work_type: Literal["airside_works"] = "airside_works"
    wap_id: uuid.UUID | None = Field(
        default=None,
        description="Active WAP of the engagement (or ancestor) covering every airside zone; "
        "required at Issue (WAP_NOT_ACTIVE).",
    )
    operator_works_permit_ref: str | None = Field(default=None, max_length=40)
    fod_control_plan: bool
    aircraft_proximity: AircraftProximity
    hydrant_operator_clearance_ref: str | None = Field(default=None, max_length=40)
    hydrant_pit_distance_m: Dec1 | None = Field(
        default=None, description="AW-6: ≥ airside_hotwork_separation_m for hot work on aprons."
    )
    ops_handback_ref: str | None = Field(
        default=None, max_length=40, description="Closure in movement-area zones (AW-8)."
    )


class WapLinkRead(ApiModel):
    id: uuid.UUID
    wap_no: str
    status: WapStatus
    blockers: list[str]


class NotamLinkRead(ApiModel):
    id: uuid.UUID
    ntm_no: str
    status: NotamStatus
    in_effect_now: bool


class PermitFodCheckRead(ApiModel):
    checked_by_worker: WorkerRef | None
    checked_by_user: UserRef | None
    checked_at: datetime
    result: FodCheckResult
    source: Literal["wap", "permit"]


class AirsideSectionRead(AirsideSectionInput):
    wap: WapLinkRead | None
    notams: list[NotamLinkRead] = Field(description="From the WAP (read-only).")
    fod_check: PermitFodCheckRead | None


PermitSectionInput = Annotated[
    HotWorkSectionInput
    | ConfinedSpaceSectionInput
    | WorkAtHeightSectionInput
    | ExcavationSectionInput
    | ElectricalSectionInput
    | LiftingSectionInput
    | RadiographySectionInput
    | AirsideSectionInput,
    Field(discriminator="work_type"),
]

PermitSectionRead = Annotated[
    HotWorkSectionRead
    | ConfinedSpaceSectionRead
    | WorkAtHeightSectionRead
    | ExcavationSectionRead
    | ElectricalSectionRead
    | LiftingSectionRead
    | RadiographySectionRead
    | AirsideSectionRead,
    Field(discriminator="work_type"),
]


# ---- checklists ---------------------------------------------------------------------------------


class ChecklistAnswerInput(StrictInput):
    code: PreIssueItem | ClosureItem
    answer: ChecklistAnswer = Field(description="'n.a.' only where list C/X allows it.")
    note: str | None = Field(default=None, max_length=300)


class ChecklistInput(StrictInput):
    """Answers for the permit's types (list C pre-issue / list X closure). Re-confirmed at each
    revalidation (SH-7)."""

    kind: ChecklistKind
    answers: list[ChecklistAnswerInput] = Field(min_length=1)


class ChecklistItemRead(ApiModel):
    code: str = Field(examples=["HW-01", "X-06"])
    work_type: PermitType | None = Field(description="Null for X items shared by all types.")
    label_en: str
    label_ar: str
    na_allowed: bool
    answer: ChecklistAnswer | None
    note: str | None
    answered_by: UserRef | None
    answered_at: datetime | None


class ChecklistRead(ApiModel):
    kind: ChecklistKind
    complete: bool
    items: list[ChecklistItemRead]


# ---- permit core (§3.5) -------------------------------------------------------------------------


class PermitFields(StrictInput):
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=3,
        description="All of one site (ZONES_NOT_SAME_SITE); airside and landside not mixed "
        "(MIXED_SIDE_ZONES); none Archived or Temporarily Closed (PT-4).",
    )
    location_desc: str = Field(min_length=1, max_length=200)
    grid_x_m: GridM | None = Field(default=None, description="Both or neither.")
    grid_y_m: GridM | None = None
    level_code: str | None = Field(default=None, max_length=10, examples=["B1", "L38"])
    elevation_m: DecimalStr | None = Field(
        default=None,
        max_digits=7,
        decimal_places=2,
        description="Required with level_code; relative to the zone's level datum.",
    )
    engagement_id: uuid.UUID = Field(
        description="Contractor Approved and not Suspended/Blacklisted (PT-6)."
    )
    work_types: list[PermitType] = Field(
        min_length=1, description="airside_works is added automatically for airside zones."
    )
    primary_type: PermitType
    title: str = Field(min_length=1, max_length=150)
    scope_en: str = Field(min_length=1, max_length=1000, description=P3_HINT)
    scope_ar: str | None = Field(default=None, max_length=1000)
    exposure: Exposure | None = Field(default=None, description="Default: zone profile.")
    flammables_in_use: bool = Field(
        default=False,
        description="Painting, coating, fuel transfer, solvent cleaning (GT-1, SM-R03).",
    )
    combustion_engine_plant: bool = Field(default=False, description="SM-R09.")
    valid_from_at: datetime = Field(description="≥ now − 15 min at Request (PT-10).")
    valid_to_at: datetime = Field(
        description="Duration ≤ the smallest type maximum (PT-11, DURATION_EXCEEDS_LIMIT)."
    )
    windows: list[PermitWindow] = Field(min_length=1, max_length=3, description=WINDOW_DOC)
    receiver_user_id: uuid.UUID = Field(
        description="Active permit_receiver on the engagement (PT-5)."
    )
    area_authority_user_id: uuid.UUID | None = Field(
        default=None, description="Required at Request (PR-3); default from the zone profile."
    )
    issuer_user_id: uuid.UUID | None = Field(
        default=None, description="Required at Approve (PR-2); any appointed issuer may sign."
    )
    hse_reviewer_user_id: uuid.UUID | None = Field(
        default=None, description="Required iff high_risk (capability 86)."
    )
    supervisor_worker_id: uuid.UUID | None = Field(
        default=None, description="Crew member with crew_role supervisor; required at Request."
    )
    conditions_en: str | None = Field(default=None, max_length=1000)
    conditions_ar: str | None = Field(default=None, max_length=1000)
    emergency_info: str = Field(
        min_length=1,
        max_length=300,
        description="Assembly point, emergency number, nearest first aid. No personal mobiles.",
    )
    linked_wap_ids: list[uuid.UUID] = Field(default_factory=list)
    linked_obs_ids: list[uuid.UUID] = Field(default_factory=list)
    isolation_cert_ids: list[uuid.UUID] = Field(default_factory=list)


class PermitCreate(PermitFields):
    """Capability 83 → Draft (PT-6: suspended / blacklisted contractor → 422
    CONTRACTOR_SUSPENDED / CONTRACTOR_BLACKLISTED, AC12). Crew, equipment, documents and
    sections may be sent now or added later."""

    crew: list[PermitCrewInput] = Field(default_factory=list)
    equipment: list[PermitEquipmentInput] = Field(default_factory=list)
    documents: list[PermitDocumentInput] = Field(default_factory=list)
    sections: list[PermitSectionInput] = Field(default_factory=list)
    jsa_template_id: uuid.UUID | None = Field(
        default=None, description="Copy this Approved template as the permit's JSA instance."
    )


class PermitUpdate(PatchInput):
    """Draft: any field (capability 83). After Approve (PT-13): changing zones, location,
    types, windows, valid_to, equipment or key-role crew returns the permit to Requested and
    clears the review; other edits (conditions, emergency info) keep the status."""

    non_nullable = frozenset(
        {
            "zone_ids",
            "location_desc",
            "work_types",
            "primary_type",
            "title",
            "scope_en",
            "exposure",
            "flammables_in_use",
            "combustion_engine_plant",
            "valid_from_at",
            "valid_to_at",
            "windows",
            "receiver_user_id",
            "emergency_info",
            "linked_wap_ids",
            "linked_obs_ids",
            "isolation_cert_ids",
        }
    )

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=3)
    location_desc: str | None = Field(default=None, min_length=1, max_length=200)
    grid_x_m: GridM | None = None
    grid_y_m: GridM | None = None
    level_code: str | None = Field(default=None, max_length=10)
    elevation_m: DecimalStr | None = Field(default=None, max_digits=7, decimal_places=2)
    work_types: list[PermitType] | None = Field(default=None, min_length=1)
    primary_type: PermitType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=150)
    scope_en: str | None = Field(default=None, min_length=1, max_length=1000)
    scope_ar: str | None = Field(default=None, max_length=1000)
    exposure: Exposure | None = None
    flammables_in_use: bool | None = None
    combustion_engine_plant: bool | None = None
    valid_from_at: datetime | None = None
    valid_to_at: datetime | None = None
    windows: list[PermitWindow] | None = Field(default=None, min_length=1, max_length=3)
    receiver_user_id: uuid.UUID | None = None
    area_authority_user_id: uuid.UUID | None = None
    issuer_user_id: uuid.UUID | None = None
    hse_reviewer_user_id: uuid.UUID | None = None
    supervisor_worker_id: uuid.UUID | None = None
    conditions_en: str | None = Field(default=None, max_length=1000)
    conditions_ar: str | None = Field(default=None, max_length=1000)
    emergency_info: str | None = Field(default=None, min_length=1, max_length=300)
    linked_wap_ids: list[uuid.UUID] | None = None
    linked_obs_ids: list[uuid.UUID] | None = None
    isolation_cert_ids: list[uuid.UUID] | None = None


class JsaSummary(ApiModel):
    id: uuid.UUID
    jsa_no: str = Field(examples=["JSA-ANIA-EXP-2026-0413"])
    status: _JsaStatus
    governing_residual_band: RiskBand | None
    residual_acceptance_complete: bool


class ObsLinkRead(ApiModel):
    id: uuid.UUID
    obs_no: str = Field(examples=["OBS-RBT-52-2026-0001"])
    status: str
    valid_to: date | None
    conditions: list[str]


class IsolationLinkRead(ApiModel):
    id: uuid.UUID
    iso_no: str = Field(examples=["ISO-ANIA-EXP-2026-0061"])
    status: str
    points_count: int
    personal_locks_applied: int


class ConflictSummary(ApiModel):
    id: uuid.UUID
    conflict_no: str = Field(examples=["SIM-RBT-52-2026-0021"])
    rule_code: str
    result: SimopsResult
    status: SimopsConflictStatus
    other_permit: PermitRef
    distance_m: DecimalStr | None
    overlap_from: datetime | None
    overlap_to: datetime | None


class GasTestBrief(ApiModel):
    id: uuid.UUID
    test_no: str
    tested_at: datetime
    result: str = Field(examples=["pass", "fail"])
    fail_codes: list[str]


class PermitGasState(ApiModel):
    """GT-1…GT-4 state for the UI (timers are server-computed)."""

    required: bool
    status: GasStatus
    latest_passing: GasTestBrief | None
    latest: GasTestBrief | None
    valid_for_start_until: datetime | None
    next_due_at: datetime | None = Field(description="Null while paused/suspended (GT-4).")
    interval_minutes: int | None
    post_break_test_required: bool


class PauseRead(ApiModel):
    from_at: datetime
    to_at: datetime | None
    reason: PauseReason
    note: str | None


class PermitShiftRead(ApiModel):
    """§3.13. planned_end_at = min(started_at + ptw_shift_max_hours, window end, valid_to_at)."""

    id: uuid.UUID
    shift_no: int
    started_at: datetime
    planned_end_at: datetime
    receiver: UserRef
    issuer: UserRef
    gas_test_id: uuid.UUID | None
    ambient_temp_c: DecimalStr | None
    crew_present: list[WorkerRef | None] = Field(description="Null entries without capability 46.")
    crew_present_count: int
    pauses: list[PauseRead]
    paused_now: bool
    ended_at: datetime | None
    end_type: ShiftEndType | None
    gas_compliant: bool | None = Field(description="K-66 (§6.3); null if gas not required.")


class SuspensionRead(ApiModel):
    """§3.14."""

    id: uuid.UUID
    suspended_at: datetime
    reason: StatusReason
    routine: bool
    raised_by: UserRef | None = Field(description="Null = system.")
    detail: str | None
    auto_source_ref: str | None = Field(examples=["WAP-ANIA-EXP-2026-0031", "PTA-…-00377"])
    resumed_at: datetime | None
    resumed_by: UserRef | None
    resume_gas_test_id: uuid.UUID | None
    cause_cleared_text: str | None


class ExemptionRead(ApiModel):
    """PT-17 exemptions (HT-4 midday ban, EL-3 energized work, HW-8 fire impairment, LF-3
    capacity > 90 %), granted by the HSE Manager (capability 102), audited."""

    id: uuid.UUID
    permit_id: uuid.UUID
    kind: ExemptionKind
    status: ExemptionStatus
    midday_reason: MiddayExemptionReason | None
    reason_text: str
    heat_controls_text: str | None
    valid_from: date | None
    valid_to: date | None
    requested_by: UserRef
    requested_at: datetime
    decided_by: UserRef | None
    decided_at: datetime | None
    decision_note: str | None


class ReceiverAcceptanceRead(ApiModel):
    purpose: AcceptancePurpose
    signed_at: datetime
    valid_until: datetime


class PostExpiryCheckRead(ApiModel):
    checked_by: UserRef
    checked_at: datetime
    site_visit_confirmed: bool
    area_safe: bool
    area_note: str
    entrants_zero: bool | None
    personal_locks_removed: bool | None
    fire_watch_status: str | None
    ca_id: uuid.UUID | None


class ClosureRequestRead(ApiModel):
    requested_by: UserRef
    requested_at: datetime
    work_status: WorkStatus
    remaining_work: str | None


class IncidentLinkRead(ApiModel):
    id: uuid.UUID
    ref: str = Field(examples=["INC-ANIA-EXP-2026-0150"])
    occurred_at: datetime


class PermitRead(ApiModel):
    """Full permit. Blockers and warnings are recomputed on every read (PT-16)."""

    id: uuid.UUID
    project_id: uuid.UUID
    permit_no: str = Field(description=PERMIT_NO_DOC)
    display_no: str
    site: SiteRef
    zones: list[ZoneRef]
    location_desc: str
    grid_x_m: DecimalStr | None
    grid_y_m: DecimalStr | None
    level_code: str | None
    elevation_m: DecimalStr | None
    engagement: EngagementRef
    work_types: list[PermitType]
    primary_type: PermitType
    high_risk: bool
    high_risk_reasons_en: list[str] = Field(description="Which §3.1 HSE-review conditions hold.")
    title: str
    scope_en: str
    scope_ar: str | None
    exposure: Exposure
    flammables_in_use: bool
    combustion_engine_plant: bool
    valid_from_at: datetime
    valid_to_at: datetime
    windows: list[PermitWindowRead]
    current_window: WindowInstance | None
    next_window: WindowInstance | None
    receiver: UserRef
    area_authority: UserRef | None
    issuer: UserRef | None
    hse_reviewer: UserRef | None
    supervisor: WorkerRef | None = Field(description="Null without capability 46.")
    jsa: JsaSummary | None
    documents: list[PermitDocumentRead]
    crew: list[PermitCrewRead]
    crew_count: int
    crew_roles: dict[PtwCrewRole, int] = Field(description="Listed crew per role (PT-19).")
    equipment: list[PermitEquipmentRead]
    sections: list[PermitSectionRead]
    pre_issue_checklist: ChecklistRead
    closure_checklist: ChecklistRead
    waps: list[WapLinkRead]
    obstacle_clearances: list[ObsLinkRead]
    isolations: list[IsolationLinkRead]
    simops: list[ConflictSummary]
    conditions_en: str | None
    conditions_ar: str | None
    copied_conditions: list[str] = Field(
        description="Obstacle-clearance conditions copied into the permit (LF-9)."
    )
    hook_conditions: list[HookCondition] = Field(
        default_factory=list,
        description="v1.1: yellow-tag restrictions and equipment limitations copied from "
        "Phase 4 hook results (§11.4 item 4).",
    )
    emergency_info: str
    status: PermitStatus
    status_reason: StatusReason | None
    status_detail: str | None
    blockers: list[BlockerItem]
    warnings: list[WarningItem]
    gas: PermitGasState
    current_shift: PermitShiftRead | None
    shifts_count: int
    handovers_count: int
    exemptions: list[ExemptionRead]
    signatures: list[SignatureRead]
    receiver_acceptance: ReceiverAcceptanceRead | None = Field(
        description="A pending receiver acceptance made on the receiver's own device."
    )
    closure_request: ClosureRequestRead | None
    post_expiry_check_pending: bool
    post_expiry_check: PostExpiryCheckRead | None
    incidents: list[IncidentLinkRead] = Field(
        description="Incidents whose investigation links this permit (Phase 1 ptw_ids)."
    )
    first_requested_at: datetime | None
    first_issued_at: datetime | None
    issued_at: datetime | None
    started_at: datetime | None
    closed_at: datetime | None
    allowed_actions: list[PermitAction] = Field(
        description="Actions the caller may attempt now (UI gating; the server re-checks)."
    )
    copied_from: PermitRef | None
    write_warnings: list[ApiWarning] = Field(
        default_factory=list, description="Non-blocking warnings of this write (P1-8 ID scan)."
    )
    created_at: datetime
    created_by: UserRef
    updated_at: datetime


class PermitListItem(ApiModel):
    id: uuid.UUID
    permit_no: str
    display_no: str
    title: str
    work_types: list[PermitType]
    primary_type: PermitType
    high_risk: bool
    status: PermitStatus
    status_reason: StatusReason | None
    site: SiteRef
    zones: list[ZoneRef]
    engagement: EngagementRef
    receiver: UserRef
    issuer: UserRef | None
    valid_from_at: datetime
    valid_to_at: datetime
    crew_count: int
    blockers: list[str]
    gas_status: GasStatus
    simops_open: int
    post_expiry_check_pending: bool


PermitPage = Page[PermitListItem]


# ---- lifecycle bodies (§4.1) --------------------------------------------------------------------


class RequestInput(StrictInput):
    """Draft → Requested (capability 84, named receiver). Runs the SIMOPS check (stored,
    informative) and crew eligibility (informative)."""

    comment: str | None = Field(default=None, max_length=500)


class ReturnInput(StrictInput):
    """Requested/Reviewed → Draft (85, 86 or 87)."""

    comment: str = Field(min_length=10, max_length=500)


class AreaReviewInput(StrictInput):
    """Requested → Reviewed (capability 85, the named area authority with an Active
    appointment covering every zone). PR-6."""

    area_conditions_known: Literal[True]
    simops_reviewed: Literal[True] = Field(
        description="Other activities reviewed against the SIMOPS result."
    )
    special_area_hazards: str | None = Field(default=None, max_length=500)
    wap_no_confirmed: str | None = Field(
        default=None, max_length=40, description="Airside zones: the WAP number checked."
    )


class HseReviewInput(StrictInput):
    """HSE review of a high-risk permit (capability 86, the named HSE reviewer; PR-5 d)."""

    decision: Literal["accepted", "returned"]
    comment: str | None = Field(default=None, max_length=1000)


class ApproveInput(StrictInput):
    comment: str | None = Field(default=None, max_length=500)


class CrewPresentInput(StrictInput):
    """SH-4: every worker in crew_present must be briefed this shift on the JSA and the permit
    conditions (CREW_NOT_BRIEFED)."""

    worker_id: uuid.UUID
    briefed: bool
    briefing_signature_png_base64: str | None = Field(
        default=None, max_length=400_000, description="Optional worker tick/signature image."
    )


class ShiftStartFields(StrictInput):
    crew_present: list[CrewPresentInput] = Field(min_length=1)
    ambient_temp_c: DecimalStr | None = Field(
        default=None,
        ge=Decimal(0),
        le=Decimal(60),
        max_digits=4,
        decimal_places=1,
        description="Required for outdoor exposure (HT-5).",
    )
    wind_reading: WindReadingInput | None = Field(
        default=None, description="Lifting / outdoor WAH (LF-6, WH-7)."
    )


class IssueInput(StrictInput):
    """Approved → Issued (capability 87 + issuer appointment). The receiver accepts in the same
    step: `receiver_cosign` on this device, or a receiver acceptance (purpose issue) made on
    the receiver's device within step_up_reauth_minutes."""

    site_visit_confirmed: Literal[True]
    receiver_cosign: CoSignature | None = None
    conditions_en: str | None = Field(default=None, max_length=1000)
    conditions_ar: str | None = Field(default=None, max_length=1000)
    wind_reading: WindReadingInput | None = None


class StartInput(ShiftStartFields):
    """Issued → Active (capability 84): ≤ issued_at + issue_to_start_max_minutes, gas test still
    valid for start (GT-3), personal locks (IS-5), fire watch present (HW-1), heat controls
    (HT-6). Creates shift 1."""


class EndShiftInput(StrictInput):
    """Active → Suspended `shift_end` (routine; capability 84). CSE: 0 inside (ENTRANTS_INSIDE).
    Personal locks are removed by their holders (IS-5)."""

    note: str | None = Field(default=None, max_length=500)


class SuspendInput(StrictInput):
    """Stop work (capability 88): never blocked by any rule (SH-1). The receiver is notified."""

    reason: StatusReason = Field(description="stop_work, weather, emergency, other, …")
    detail: str = Field(min_length=10, max_length=500)


class GasAlarmInput(StrictInput):
    """GT-7: continuous-monitor alarm → Suspended `gas_alarm`; needs a passing post_alarm test
    before Resume."""

    detail: str | None = Field(default=None, max_length=500)


class RevalidateInput(ShiftStartFields):
    """Suspended (`shift_end` / `shift_lapsed`) → Active (capability 87). Same checks as Issue
    (PT-16), new shift, inside a window (OUTSIDE_WINDOW) and before valid_to; radiography →
    REVALIDATION_NOT_ALLOWED; excavation needs today's competent-person inspection
    (INSPECTION_REQUIRED)."""

    site_visit_confirmed: Literal[True]
    receiver_cosign: CoSignature | None = None
    checklist_reconfirmed: Literal[True]


class ResumeInput(ShiftStartFields):
    """Suspended (other reasons) → Active (capability 87). Non-routine: cause_cleared_text
    ≥ 20 chars (SH-3); after audit_critical the linked CA must be In Progress; after
    gas_test_failed / gas_alarm a passing post_alarm test; midday_ban: from 15:00 (MIDDAY_BAN).
    A Resume starts a new shift."""

    site_visit_confirmed: Literal[True]
    receiver_cosign: CoSignature | None = None
    cause_cleared_text: str | None = Field(default=None, min_length=20, max_length=500)


class ReceiverAcceptanceInput(StrictInput):
    """The named receiver signs acceptance on their own device; consumed by the next
    Issue / Revalidate / Resume within step_up_reauth_minutes."""

    purpose: AcceptancePurpose


class ClosureRequestInput(StrictInput):
    """CL-1 (capability 84): closure checklist (list X) answered first; entry log 0 inside;
    personal locks removed; hot_work_ended_at recorded for hot work."""

    work_status: WorkStatus
    remaining_work: str | None = Field(
        default=None,
        min_length=20,
        max_length=1000,
        description="Required for incomplete_area_safe: what remains and how it was made safe.",
    )
    crew_withdrawn: Literal[True]


class CloseInput(StrictInput):
    """CL-2 (capability 87): site visit; not before fire_watch_until (FIRE_WATCH_RUNNING);
    airside FOD/hand-back (FOD_HANDBACK_REQUIRED); radiography source return. Missing items →
    422 CLOSURE_INCOMPLETE (meta.items). Isolations stay applied (CL-3)."""

    site_visit_confirmed: Literal[True]
    note: str | None = Field(default=None, max_length=500)


class CancelInput(StrictInput):
    """Capability 89 (receiver: own permit in Draft/Requested). Issued → Cancelled needs
    site_visit_confirmed (area left safe)."""

    reason: StatusReason = Field(
        description="rejected, not_required, duplicate, contractor_suspended, "
        "contractor_blacklisted, other."
    )
    detail: str | None = Field(default=None, max_length=500)
    site_visit_confirmed: bool = False


class PostExpiryCheckInput(StrictInput):
    """CL-6 within 24 h by an appointed issuer of the project. area_safe = false requires a
    corrective action first (`ca_id`, source_type other, permit number in the description)."""

    site_visit_confirmed: Literal[True]
    area_safe: bool
    area_note: str = Field(min_length=10, max_length=500)
    entrants_zero: bool | None = None
    personal_locks_removed: bool | None = None
    fire_watch_status: str | None = Field(default=None, max_length=200)
    ca_id: uuid.UUID | None = None


class PauseStartInput(StrictInput):
    """SH-9 (receiver). A pause never spans the shift end and may last ≤ 2 h; CSE: 0 inside."""

    reason: PauseReason
    note: str | None = Field(default=None, max_length=300)


class PauseEndInput(StrictInput):
    """Ending a pause ≥ gas_break_retest_minutes needs a post_break test valid for start
    (GAS_TEST_EXPIRED)."""

    note: str | None = Field(default=None, max_length=300)


class HotWorkEndInput(StrictInput):
    """HW-4: starts the fire watch (fire_watch_until = ended_at + fire_watch_post_minutes)."""

    ended_at: datetime


class EntryLogInput(StrictInput):
    """CS-7 entry/exit of an entrant (receiver or standby person's device)."""

    worker_id: uuid.UUID
    direction: EntryDirection
    at: datetime


class PermitFodCheckInput(StrictInput):
    """AW-8 permit-level FOD check (alternative to the WAP's WA-17 record)."""

    checked_by_worker_id: uuid.UUID | None = None
    checked_by_user_id: uuid.UUID | None = None
    checked_at: datetime
    result: FodCheckResult


class ExemptionCreate(StrictInput):
    """Request an exemption (users who may prepare or issue the permit); the HSE Manager
    decides (capability 102). Created by the HSE Manager → granted at once. midday_ban needs
    midday_reason, heat_controls_text ≥ 30 chars and a date range (HT-4)."""

    kind: ExemptionKind
    midday_reason: MiddayExemptionReason | None = None
    reason_text: str = Field(min_length=10, max_length=500)
    heat_controls_text: str | None = Field(default=None, min_length=30, max_length=1000)
    valid_from: date | None = None
    valid_to: date | None = None


class ExemptionDecision(StrictInput):
    decision: Literal["granted", "refused"]
    note: str | None = Field(default=None, max_length=500)


class SectionsInput(StrictInput):
    """Replace one or more type sections (each must be one of the permit's work types)."""

    sections: list[PermitSectionInput] = Field(min_length=1)


# ---- handovers (§3.13, SH-6) --------------------------------------------------------------------


class HandoverCreate(StrictInput):
    """Outgoing receiver (capability 84), ≤ 60 min before planned_end_at (HANDOVER_TOO_EARLY).
    Hot work and CSE: at most one handover (HANDOVER_LIMIT)."""

    to_receiver_user_id: uuid.UUID
    to_issuer_user_id: uuid.UUID
    notes_en: str = Field(
        min_length=10,
        max_length=500,
        description="Work status, hazards changed, isolations, persons inside a confined space.",
    )
    notes_ar: str | None = Field(default=None, max_length=500)


class HandoverAcceptInput(ShiftStartFields):
    """Incoming receiver and incoming issuer both sign (each on their own device, or one
    co-signs here). The handover is Accepted when both signatures exist before
    planned_end_at; Active continues with a new shift."""

    cosign: CoSignature | None = None


class HandoverRead(ApiModel):
    id: uuid.UUID
    permit_id: uuid.UUID
    from_shift_no: int
    from_receiver: UserRef
    to_receiver: UserRef
    to_issuer: UserRef
    initiated_at: datetime
    accepted_at: datetime | None
    receiver_signed_at: datetime | None
    issuer_signed_at: datetime | None
    status: HandoverStatus
    notes_en: str
    notes_ar: str | None
    deadline_at: datetime = Field(description="planned_end_at of the outgoing shift.")


class HandoverList(ApiModel):
    items: list[HandoverRead]


class ShiftList(ApiModel):
    items: list[PermitShiftRead]


class SuspensionList(ApiModel):
    items: list[SuspensionRead]


class SuspensionLogItem(SuspensionRead):
    permit: PermitRef
    engagement: EngagementRef
    zone_codes: list[str]


SuspensionPage = Page[SuspensionLogItem]


# ---- blockers preview ---------------------------------------------------------------------------


class PermitReadiness(ApiModel):
    """GET /permits/{id}/readiness: what would block a transition now."""

    action: PermitAction
    allowed: bool
    blockers: list[BlockerItem]
    warnings: list[WarningItem]
    errors: list[str] = Field(
        description="Other error codes the action would return (e.g. OUTSIDE_WINDOW, "
        "REAUTH_REQUIRED, RECEIVER_LIMIT)."
    )


# ---- board (§8.4) -------------------------------------------------------------------------------


class BoardPermit(ApiModel):
    id: uuid.UUID
    permit_no: str
    display_no: str
    title: str
    work_types: list[PermitType]
    primary_type: PermitType
    high_risk: bool
    status: PermitStatus
    status_reason: StatusReason | None
    engagement_code: str
    window_today: str | None = Field(examples=["07:00–19:00"])
    in_window_now: bool
    shift_no: int | None
    shift_planned_end_at: datetime | None
    crew_count: int
    crew_present_count: int | None
    gas_status: GasStatus
    gas_next_due_at: datetime | None
    simops_chips: list[str] = Field(examples=[["SM-R05b conditional open"]])
    wap_chip: str | None = Field(examples=["WAP-ANIA-EXP-2026-0031 active"])
    notam_chip: str | None
    blockers: list[str]
    persons_inside: int | None = Field(description="Confined space only.")
    fire_watch_until: datetime | None


class BoardZone(ApiModel):
    zone: ZoneRef
    permits: list[BoardPermit]


class PtwBoardResponse(ApiModel):
    """Live permit board (Issued / Active / Suspended now). Viewer/Client get counts only
    (no names); this payload never carries names."""

    project_id: uuid.UUID
    at: datetime
    zones: list[BoardZone]
    counts: dict[PermitStatus, int]


# ---- print (PT-20) ------------------------------------------------------------------------------


class PrintCrewLine(ApiModel):
    name_en: str | None = Field(description="Names and worker_no only with capability 46.")
    name_ar: str | None
    worker_no: str | None
    crew_role: PtwCrewRole


class PrintIsolationLine(ApiModel):
    iso_no: str
    point_no: int
    device_tag: str
    lock_no: str | None
    tag_no: str | None


class PermitPrintRead(ApiModel):
    """A4 EN/AR print. Never ID numbers, nationality or fitness detail (AC25)."""

    permit_no: str
    display_no: str
    project_code: str
    status: PermitStatus
    work_types: list[PermitType]
    location: str
    zones: list[str]
    valid_from_at: datetime
    valid_to_at: datetime
    windows: list[PermitWindowRead]
    current_shift_no: int | None
    receiver_name: str
    issuer_name: str | None
    area_authority_name: str | None
    crew: list[PrintCrewLine]
    latest_gas_test: GasTestBrief | None
    isolations: list[PrintIsolationLine]
    key_conditions: list[str]
    emergency_info: str
    qr_payload: str = Field(
        pattern=PT_QR_PATTERN,
        description="`HSE2:PT:<22-char token>` (no personal data); gates show a read-only "
        "permit summary (PTW_VIEW, GC-10).",
    )
    printed_ref: str = Field(description="Manual fallback beside the QR (the permit number).")
    generated_at: datetime
    audit_hash: str = Field(description="Footer: hash of the permit content (design P6).")


class ClosurePackRead(PermitPrintRead):
    """Closed-permit pack (§8.4): print view plus the full trail."""

    shifts: list[PermitShiftRead]
    suspensions: list[SuspensionRead]
    gas_tests: list[GasTestBrief]
    signatures: list[SignatureRead]
    closure_checklist: ChecklistRead
    closed_at: datetime | None


class PermitCopyInput(StrictInput):
    """CL-4: copy a closed (incomplete_area_safe) or any permit into a new Draft. JSA
    approval, gas tests and signatures start again."""

    valid_from_at: datetime
    valid_to_at: datetime


class IncidentPermitSuggestion(ApiModel):
    """1-dashboard v1.2: permits Issued, Active or Suspended in the incident's zone at
    occurred_at (suggested for investigation ptw_ids)."""

    permit: PermitRef
    zones: list[ZoneRef]
    status_at_occurrence: PermitStatus


class IncidentPermitSuggestions(ApiModel):
    items: list[IncidentPermitSuggestion]
