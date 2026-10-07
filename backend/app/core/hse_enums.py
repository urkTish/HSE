"""Phase 1 domain enumerations (spec 1-dashboard §3, §4, §5, §6).

Codes are immutable (§3.11): labels (EN/AR) live in the reference-list table and may be edited
by the HSE Manager, codes never. These enums are exported into the OpenAPI contract.
"""

from enum import IntEnum, StrEnum

# ---------------------------------------------------------------------------------------------
# Workforce (§3.1, §3.2, §4.1)
# ---------------------------------------------------------------------------------------------


class Shift(StrEnum):
    day = "day"
    night = "night"
    all = "all"


class IncidentShift(StrEnum):
    day = "day"
    night = "night"


class WorkforceSource(StrEnum):
    manual = "manual"
    import_ = "import"


class WorkforceStatus(StrEnum):
    """§4.1. KPIs use submitted, verified and locked rows; drafts are excluded."""

    draft = "draft"
    submitted = "submitted"
    verified = "verified"
    locked = "locked"


class TierClass(StrEnum):
    """Derived from engagement tier: 1 = direct, ≥ 2 = subcontractor (§3.1, §10 Q1)."""

    direct = "direct"
    subcontractor = "subcontractor"


class ImportMode(StrEnum):
    insert_only = "insert_only"
    upsert = "upsert"


class ImportStatus(StrEnum):
    validated = "validated"
    committed = "committed"
    discarded = "discarded"
    expired = "expired"


class ImportRowStatus(StrEnum):
    ok = "ok"
    warning = "warning"
    error = "error"


class ImportCode(StrEnum):
    """§3.2 validation codes. E* block commit, W* do not."""

    E01 = "E01"
    E02 = "E02"
    E03 = "E03"
    E04 = "E04"
    E05 = "E05"
    E06 = "E06"
    E07 = "E07"
    E08 = "E08"
    E09 = "E09"
    E10 = "E10"
    E11 = "E11"
    E12 = "E12"
    E13 = "E13"
    E14 = "E14"
    W01 = "W01"
    W02 = "W02"
    W03 = "W03"
    W04 = "W04"
    W05 = "W05"
    W06 = "W06"


class MonthLockStatus(StrEnum):
    open = "open"
    locked = "locked"


# ---------------------------------------------------------------------------------------------
# Incidents, injury cases, investigations (§3.3-§3.5, §4.2)
# ---------------------------------------------------------------------------------------------


class IncidentType(StrEnum):
    injury_illness = "injury_illness"
    near_miss = "near_miss"
    property_damage = "property_damage"
    environmental = "environmental"
    dangerous_occurrence = "dangerous_occurrence"


class IncidentStatus(StrEnum):
    draft = "draft"
    reported = "reported"
    under_investigation = "under_investigation"
    pending_review = "pending_review"
    actions_pending = "actions_pending"
    closed = "closed"
    voided = "voided"


class NotWorkRelatedReason(StrEnum):
    """OSHA 1904.5 exceptions offered when work_related = false."""

    off_duty_camp = "off_duty_camp"
    personal_task = "personal_task"
    pre_existing_condition = "pre_existing_condition"
    commuting = "commuting"
    voluntary_wellness = "voluntary_wellness"
    other = "other"


class AirsideFlag(StrEnum):
    runway_incursion = "runway_incursion"
    fod_event = "fod_event"
    aircraft_involved = "aircraft_involved"
    gse_damage = "gse_damage"
    notam_breach = "notam_breach"
    ols_infringement = "ols_infringement"
    wildlife = "wildlife"
    airside_vehicle_incident = "airside_vehicle_incident"


class AssetType(StrEnum):
    plant = "plant"
    vehicle = "vehicle"
    structure = "structure"
    utility = "utility"
    airport_asset = "airport_asset"
    aircraft = "aircraft"
    other = "other"


class EnvCategory(StrEnum):
    spill = "spill"
    emission = "emission"
    dust = "dust"
    noise = "noise"
    waste = "waste"
    water = "water"
    wildlife_habitat = "wildlife_habitat"


class EnvReached(StrEnum):
    none = "none"
    soil = "soil"
    drain = "drain"
    water_body = "water_body"


class DangerousOccurrenceCategory(StrEnum):
    crane_lifting_failure = "crane_lifting_failure"
    scaffold_collapse = "scaffold_collapse"
    structural_collapse = "structural_collapse"
    excavation_collapse = "excavation_collapse"
    electrical_short_fire = "electrical_short_fire"
    fire_explosion = "fire_explosion"
    gas_release = "gas_release"
    pressure_failure = "pressure_failure"
    vehicle_overturn = "vehicle_overturn"
    other = "other"


class ExternalBody(StrEnum):
    gosi = "gosi"
    mhrsd = "mhrsd"
    civil_defense = "civil_defense"
    gaca = "gaca"
    airport_operator = "airport_operator"
    client = "client"
    police = "police"


class NotificationState(StrEnum):
    """Derived state of a required external notification (§5.2 rule I-20)."""

    due = "due"
    done = "done"
    overdue = "overdue"


class PersonType(StrEnum):
    contractor_worker = "contractor_worker"
    client_pmc_staff = "client_pmc_staff"
    visitor = "visitor"
    third_party_public = "third_party_public"


class IdType(StrEnum):
    iqama = "iqama"
    national_id = "national_id"
    gcc_id = "gcc_id"  # v1.1 (Phase 2 worker register)
    passport = "passport"


class AgeBand(StrEnum):
    lt20 = "<20"
    a20_29 = "20-29"
    a30_39 = "30-39"
    a40_49 = "40-49"
    a50_59 = "50-59"
    a60_plus = "60+"


class BodySide(StrEnum):
    left = "left"
    right = "right"
    both = "both"
    na = "n/a"


class TreatedAt(StrEnum):
    site_clinic = "site_clinic"
    hospital_outpatient = "hospital_outpatient"
    hospital_admitted = "hospital_admitted"
    none = "none"


class PermanentDisability(StrEnum):
    none = "none"
    partial = "partial"
    total = "total"


class CaseCategory(StrEnum):
    """§5.2 rule I-5. Most severe first."""

    FAT = "FAT"
    LTI = "LTI"
    RWC = "RWC"
    JTC = "JTC"
    MTC = "MTC"
    FAC = "FAC"


RECORDABLE: frozenset[CaseCategory] = frozenset(
    {CaseCategory.FAT, CaseCategory.LTI, CaseCategory.RWC, CaseCategory.JTC, CaseCategory.MTC}
)


class ClassificationStatus(StrEnum):
    provisional = "provisional"
    confirmed = "confirmed"


class RateExclusionReason(StrEnum):
    """Why a case is listed but excluded from rates (§5.2 rule I-4)."""

    not_work_related = "not_work_related"
    commuting = "commuting"
    non_contractor_person = "non_contractor_person"
    incident_voided = "incident_voided"
    incident_draft = "incident_draft"


class InvestigationLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class InvestigationMethod(StrEnum):
    simple = "simple"
    five_why = "five_why"
    icam = "icam"
    taproot = "taproot"


class IcamLevel(StrEnum):
    AD = "AD"
    IT = "IT"
    TE = "TE"
    OF = "OF"


class RootCauseCode(StrEnum):
    """§3.11 list R (ICAM) `VERIFY` against the client's licence version."""

    AD_01 = "AD-01"
    AD_02 = "AD-02"
    AD_03 = "AD-03"
    AD_04 = "AD-04"
    AD_05 = "AD-05"
    AD_06 = "AD-06"
    AD_07 = "AD-07"
    IT_01 = "IT-01"
    IT_02 = "IT-02"
    IT_03 = "IT-03"
    IT_04 = "IT-04"
    TE_01 = "TE-01"
    TE_02 = "TE-02"
    TE_03 = "TE-03"
    TE_04 = "TE-04"
    TE_05 = "TE-05"
    TE_06 = "TE-06"
    TE_07 = "TE-07"
    TE_08 = "TE-08"
    OF_01 = "OF-01"
    OF_02 = "OF-02"
    OF_03 = "OF-03"
    OF_04 = "OF-04"
    OF_05 = "OF-05"
    OF_06 = "OF-06"
    OF_07 = "OF-07"
    OF_08 = "OF-08"
    OF_09 = "OF-09"
    OF_10 = "OF-10"


class SeverityLevel(IntEnum):
    """§3.11 list S (1-5)."""

    negligible = 1
    minor = 2
    serious = 3
    major = 4
    catastrophic = 5


class Activity(StrEnum):
    excavation = "excavation"
    concrete = "concrete"
    formwork = "formwork"
    rebar = "rebar"
    steel_erection = "steel_erection"
    scaffolding = "scaffolding"
    lifting = "lifting"
    work_at_height = "work_at_height"
    electrical = "electrical"
    mep_installation = "mep_installation"
    hot_work = "hot_work"
    paving_asphalt = "paving_asphalt"
    airfield_lighting = "airfield_lighting"
    road_works = "road_works"
    demolition = "demolition"
    driving_transport = "driving_transport"
    material_handling = "material_handling"
    housekeeping = "housekeeping"
    survey = "survey"
    testing_commissioning = "testing_commissioning"
    maintenance = "maintenance"
    other = "other"


class Trade(StrEnum):
    labourer = "labourer"
    carpenter = "carpenter"
    steel_fixer = "steel_fixer"
    steel_erector = "steel_erector"
    scaffolder = "scaffolder"
    rigger = "rigger"
    crane_operator = "crane_operator"
    plant_operator = "plant_operator"
    driver = "driver"
    electrician = "electrician"
    plumber = "plumber"
    welder = "welder"
    mason = "mason"
    painter = "painter"
    surveyor = "surveyor"
    supervisor = "supervisor"
    engineer = "engineer"
    hse_staff = "hse_staff"
    flagman = "flagman"
    other = "other"


class BodyPart(StrEnum):
    head = "head"
    eye = "eye"
    face = "face"
    neck = "neck"
    shoulder = "shoulder"
    upper_arm = "upper_arm"
    elbow = "elbow"
    forearm = "forearm"
    wrist = "wrist"
    hand = "hand"
    finger = "finger"
    chest = "chest"
    upper_back = "upper_back"
    lower_back = "lower_back"
    abdomen = "abdomen"
    hip_pelvis = "hip_pelvis"
    thigh = "thigh"
    knee = "knee"
    lower_leg = "lower_leg"
    ankle = "ankle"
    foot = "foot"
    toe = "toe"
    multiple = "multiple"
    internal_systemic = "internal_systemic"


class InjuryNature(StrEnum):
    fracture = "fracture"
    laceration = "laceration"
    abrasion = "abrasion"
    contusion = "contusion"
    sprain_strain = "sprain_strain"
    puncture = "puncture"
    burn_thermal = "burn_thermal"
    burn_chemical = "burn_chemical"
    electric_shock = "electric_shock"
    amputation = "amputation"
    crush = "crush"
    dislocation = "dislocation"
    foreign_body_eye = "foreign_body_eye"
    concussion = "concussion"
    heat_exhaustion = "heat_exhaustion"
    heat_stroke = "heat_stroke"
    inhalation_poisoning = "inhalation_poisoning"
    noise_hearing = "noise_hearing"
    dermatitis = "dermatitis"
    multiple = "multiple"
    other = "other"


SIGNIFICANT_NATURES: frozenset[InjuryNature] = frozenset(
    {
        InjuryNature.fracture,
        InjuryNature.dislocation,
        InjuryNature.amputation,
        InjuryNature.concussion,
        InjuryNature.heat_stroke,
    }
)


class Mechanism(StrEnum):
    fall_from_height = "fall_from_height"
    slip_trip_same_level = "slip_trip_same_level"
    struck_by_falling_object = "struck_by_falling_object"
    struck_by_moving_object = "struck_by_moving_object"
    struck_against = "struck_against"
    caught_in_between = "caught_in_between"
    contact_electricity = "contact_electricity"
    contact_hot_fire = "contact_hot_fire"
    contact_chemical = "contact_chemical"
    overexertion_manual_handling = "overexertion_manual_handling"
    repetitive_motion = "repetitive_motion"
    vehicle_plant_collision = "vehicle_plant_collision"
    vehicle_overturn = "vehicle_overturn"
    exposure_heat = "exposure_heat"
    exposure_noise = "exposure_noise"
    bite_sting = "bite_sting"
    assault = "assault"
    other = "other"


class Agency(StrEnum):
    scaffold = "scaffold"
    ladder = "ladder"
    mewp = "mewp"
    crane_lifting_gear = "crane_lifting_gear"
    earthmoving = "earthmoving"
    light_vehicle = "light_vehicle"
    heavy_vehicle = "heavy_vehicle"
    airside_gse = "airside_gse"
    aircraft = "aircraft"
    hand_tool = "hand_tool"
    power_tool = "power_tool"
    formwork = "formwork"
    rebar_steel = "rebar_steel"
    materials = "materials"
    electrical_installation = "electrical_installation"
    chemical = "chemical"
    hot_work_equipment = "hot_work_equipment"
    ground_surface = "ground_surface"
    stairs_openings = "stairs_openings"
    excavation_trench = "excavation_trench"
    weather_sun = "weather_sun"
    other = "other"


class Treatment(StrEnum):
    """§3.11 lists F (first aid), MT (medical treatment) and the two diagnostic-only items."""

    # F — first aid (OSHA 1904.7(b)(5)(ii))
    otc_medication_otc_strength = "otc_medication_otc_strength"
    tetanus_immunisation = "tetanus_immunisation"
    wound_cleaning = "wound_cleaning"
    wound_covering_steristrips = "wound_covering_steristrips"
    hot_cold_therapy = "hot_cold_therapy"
    non_rigid_support = "non_rigid_support"
    temporary_immobilisation_transport = "temporary_immobilisation_transport"
    nail_drilling = "nail_drilling"
    eye_patch = "eye_patch"
    eye_irrigation_swab = "eye_irrigation_swab"
    splinter_removal = "splinter_removal"
    finger_guard = "finger_guard"
    massage = "massage"
    fluids_oral_heat = "fluids_oral_heat"
    # MT — medical treatment beyond first aid
    sutures_staples_glue = "sutures_staples_glue"
    rigid_splint = "rigid_splint"
    prescription_medication = "prescription_medication"
    otc_at_prescription_strength = "otc_at_prescription_strength"
    iv_fluids = "iv_fluids"
    physiotherapy = "physiotherapy"
    foreign_body_removal_eye_tools = "foreign_body_removal_eye_tools"
    surgical_debridement = "surgical_debridement"
    hospital_admission = "hospital_admission"
    other_medical = "other_medical"
    # diagnostic only — neither FA nor MT
    x_ray_diagnosis = "x_ray_diagnosis"
    observation_only = "observation_only"


class TreatmentClass(StrEnum):
    first_aid = "first_aid"
    medical_treatment = "medical_treatment"
    diagnostic = "diagnostic"


MEDICAL_TREATMENTS: frozenset[Treatment] = frozenset(
    {
        Treatment.sutures_staples_glue,
        Treatment.rigid_splint,
        Treatment.prescription_medication,
        Treatment.otc_at_prescription_strength,
        Treatment.iv_fluids,
        Treatment.physiotherapy,
        Treatment.foreign_body_removal_eye_tools,
        Treatment.surgical_debridement,
        Treatment.hospital_admission,
        Treatment.other_medical,
    }
)
DIAGNOSTIC_TREATMENTS: frozenset[Treatment] = frozenset(
    {Treatment.x_ray_diagnosis, Treatment.observation_only}
)


def treatment_class(t: Treatment) -> TreatmentClass:
    if t in MEDICAL_TREATMENTS:
        return TreatmentClass.medical_treatment
    if t in DIAGNOSTIC_TREATMENTS:
        return TreatmentClass.diagnostic
    return TreatmentClass.first_aid


class PrivacyCaseReason(StrEnum):
    """OSHA 1904.29(b)(7) list."""

    sexual_assault = "sexual_assault"
    mental_illness = "mental_illness"
    infectious_disease = "infectious_disease"
    needlestick_contaminated = "needlestick_contaminated"
    reproductive_organs = "reproductive_organs"
    employee_request = "employee_request"


# ---------------------------------------------------------------------------------------------
# Observations, inspections, corrective actions, meetings (§3.6-§3.9, §4.3-§4.5)
# ---------------------------------------------------------------------------------------------


class ObservationType(StrEnum):
    safe_behaviour = "safe_behaviour"
    safe_condition = "safe_condition"
    unsafe_act = "unsafe_act"
    unsafe_condition = "unsafe_condition"


SAFE_OBSERVATIONS: frozenset[ObservationType] = frozenset(
    {ObservationType.safe_behaviour, ObservationType.safe_condition}
)


class ObservationCategory(StrEnum):
    work_at_height = "work_at_height"
    lifting = "lifting"
    excavation = "excavation"
    scaffolding = "scaffolding"
    electrical = "electrical"
    hot_work = "hot_work"
    ppe = "ppe"
    housekeeping = "housekeeping"
    traffic_plant = "traffic_plant"
    airside_fod_control = "airside_fod_control"
    airside_driving = "airside_driving"
    heat_stress = "heat_stress"
    confined_space = "confined_space"
    manual_handling = "manual_handling"
    tools_equipment = "tools_equipment"
    environmental = "environmental"
    fire_safety = "fire_safety"
    welfare = "welfare"
    permit_compliance = "permit_compliance"
    behaviour_other = "behaviour_other"


class RiskRating(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ObservationStatus(StrEnum):
    open = "open"
    action_raised = "action_raised"
    closed = "closed"


class InspectionType(StrEnum):
    general_site = "general_site"
    scaffold = "scaffold"
    lifting_equipment = "lifting_equipment"
    electrical = "electrical"
    excavation = "excavation"
    housekeeping = "housekeeping"
    fire_safety = "fire_safety"
    welfare = "welfare"
    airside_fod_walk = "airside_fod_walk"
    plant_vehicle = "plant_vehicle"
    environmental = "environmental"
    ppe = "ppe"
    leadership_walk = "leadership_walk"


class InspectionFrequency(StrEnum):
    daily = "daily"
    weekly = "weekly"
    fortnightly = "fortnightly"
    monthly = "monthly"
    once = "once"


class Weekday(StrEnum):
    sunday = "sunday"
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"


class InspectionAssigneeRole(StrEnum):
    hse_officer = "hse_officer"
    site_engineer = "site_engineer"
    contractor_hse_rep = "contractor_hse_rep"


class InspectionStatus(StrEnum):
    planned = "planned"
    completed = "completed"
    missed = "missed"
    cancelled = "cancelled"


class InspectionTimeliness(StrEnum):
    """Derived (§5.4 rule N-2)."""

    on_time = "on_time"
    late = "late"
    missed = "missed"
    pending = "pending"
    unplanned = "unplanned"
    cancelled = "cancelled"


class FindingSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CaSourceType(StrEnum):
    incident = "incident"
    observation = "observation"
    inspection = "inspection"
    ai_recommendation = "ai_recommendation"
    other = "other"


class ControlLevel(StrEnum):
    """Hierarchy of controls, highest first."""

    elimination = "elimination"
    substitution = "substitution"
    engineering = "engineering"
    administrative = "administrative"
    ppe = "ppe"


HIGHER_CONTROLS: frozenset[ControlLevel] = frozenset(
    {ControlLevel.elimination, ControlLevel.substitution, ControlLevel.engineering}
)


class CaPriority(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class CaStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    pending_verification = "pending_verification"
    closed = "closed"
    cancelled = "cancelled"


class ExtensionStatus(StrEnum):
    requested = "requested"
    approved = "approved"
    rejected = "rejected"


class OverdueBucket(StrEnum):
    """K-42 ageing buckets (days overdue)."""

    d1_7 = "1-7"
    d8_30 = "8-30"
    d31_60 = "31-60"
    d60_plus = ">60"


class MeetingType(StrEnum):
    hse_committee = "hse_committee"
    contractor_hse = "contractor_hse"
    management_walk = "management_walk"
    other = "other"


# ---------------------------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------------------------


class AttachmentOwner(StrEnum):
    incident = "incident"
    injury_case_medical = "injury_case_medical"
    observation = "observation"
    corrective_action_evidence = "corrective_action_evidence"
    hse_meeting_minutes = "hse_meeting_minutes"
    # Phase 2 (encrypted bucket, signed URL ≤ 5 min)
    worker_photo = "worker_photo"
    pass_application_id_copy = "pass_application_id_copy"
    induction_signature = "induction_signature"
    offence_evidence = "offence_evidence"


class ScanStatus(StrEnum):
    pending = "pending"
    clean = "clean"
    infected = "infected"
    skipped = "skipped"


class ExportPurpose(StrEnum):
    """P1-6: purpose recorded when exporting incidents with identity columns; P2-10:
    pass_office / authority_request / legal / other for access exports with full IDs."""

    gosi = "gosi"
    client_report = "client_report"
    legal = "legal"
    insurance = "insurance"
    other = "other"
    pass_office = "pass_office"
    authority_request = "authority_request"


# ---------------------------------------------------------------------------------------------
# KPI engine (§5.6, §6)
# ---------------------------------------------------------------------------------------------


class KpiMetric(StrEnum):
    """KPI catalogue §6.1. K-26 is split into one id per event type (DO / PD / ENV)."""

    K01 = "K-01"
    K02 = "K-02"
    K03 = "K-03"
    K04 = "K-04"
    K05 = "K-05"
    K05b = "K-05b"
    K06 = "K-06"
    K07 = "K-07"
    K08 = "K-08"
    K09 = "K-09"
    K10 = "K-10"
    K11 = "K-11"
    K12 = "K-12"
    K13 = "K-13"
    K14 = "K-14"
    K15 = "K-15"
    K16 = "K-16"
    K17 = "K-17"
    K18 = "K-18"
    K20 = "K-20"
    K21 = "K-21"
    K22 = "K-22"
    K23 = "K-23"
    K24 = "K-24"
    K25 = "K-25"
    K26a = "K-26a"
    K26b = "K-26b"
    K26c = "K-26c"
    K27 = "K-27"
    K28 = "K-28"
    K29 = "K-29"
    K30 = "K-30"
    K31 = "K-31"
    K32 = "K-32"
    K33 = "K-33"
    K34 = "K-34"
    K35 = "K-35"
    K35b = "K-35b"
    K36 = "K-36"
    K37 = "K-37"
    K38 = "K-38"
    K39 = "K-39"
    K40 = "K-40"
    K41 = "K-41"
    K42 = "K-42"
    K42b = "K-42b"
    K43 = "K-43"
    K44 = "K-44"
    K45 = "K-45"
    K46 = "K-46"
    K47 = "K-47"
    # Phase 2 access KPIs (2-access-permits §6.8)
    K48 = "K-48"
    K49 = "K-49"
    K50 = "K-50"
    K51 = "K-51"
    K52 = "K-52"
    K53 = "K-53"
    K53b = "K-53b"
    K54 = "K-54"
    K55 = "K-55"
    K56 = "K-56"
    K57 = "K-57"
    K58 = "K-58"
    K59 = "K-59"
    K60 = "K-60"


class KpiKind(StrEnum):
    count_ = "count"
    hours = "hours"
    rate = "rate"
    percentage = "percentage"
    ratio = "ratio"
    average = "average"
    days = "days"
    placeholder = "placeholder"


class KpiBetter(StrEnum):
    lower_is_better = "lower"
    higher_is_better = "higher"
    none = "none"


class KpiGroup(StrEnum):
    exposure = "exposure"
    lagging = "lagging"
    leading = "leading"
    data_quality = "data_quality"


class KpiBaseKind(StrEnum):
    """Which project setting normalises a rate: ltifr_base_hours (B_L) or rate_base_hours (B)."""

    ltifr = "ltifr"
    rate = "rate"


class NullReason(StrEnum):
    """Why a KPI value is null ("—")."""

    NO_EXPOSURE = "NO_EXPOSURE"
    NO_ZONE_EXPOSURE = "NO_ZONE_EXPOSURE"
    NO_DENOMINATOR = "NO_DENOMINATOR"
    NOT_AVAILABLE_YET = "NOT_AVAILABLE_YET"


class KpiWarning(StrEnum):
    PARTIAL_EXPOSURE = "PARTIAL_EXPOSURE"
    LOW_EXPOSURE = "LOW_EXPOSURE"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"
    PROVISIONAL_CASES = "PROVISIONAL_CASES"
    RESTATED = "RESTATED"
    MIXED_BASES = "MIXED_BASES"
    CAPPED_CASES = "CAPPED_CASES"


class PeriodPreset(StrEnum):
    """K-R10. All ranges inclusive."""

    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"
    mtd = "mtd"
    qtd = "qtd"
    ytd = "ytd"
    r12 = "r12"
    itd = "itd"
    custom = "custom"


class ComparisonKind(StrEnum):
    """K-R11."""

    previous = "previous"
    sply = "sply"
    r12 = "r12"


class DeltaDirection(StrEnum):
    better = "better"
    worse = "worse"
    same = "same"
    na = "n/a"


class Rag(StrEnum):
    green = "green"
    amber = "amber"
    red = "red"


class Granularity(StrEnum):
    week = "week"
    month = "month"


class BreakdownMeasure(StrEnum):
    injury_cases = "injury_cases"
    recordable_cases = "recordable_cases"
    events_by_type = "events_by_type"
    observations = "observations"
    unsafe_observations = "unsafe_observations"
    cas = "cas"
    inspections = "inspections"


class BreakdownDimension(StrEnum):
    """§6.8. age_band and nationality are restricted (D-7, AI-6)."""

    site = "site"
    zone = "zone"
    zone_type = "zone_type"
    airside_area = "airside_area"
    contractor = "contractor"
    tier = "tier"
    activity = "activity"
    mechanism = "mechanism"
    agency = "agency"
    body_part = "body_part"
    nature = "nature"
    case_category = "case_category"
    incident_type = "incident_type"
    root_cause_level = "root_cause_level"
    root_cause_code = "root_cause_code"
    shift = "shift"
    hour_band = "hour_band"
    weekday = "weekday"
    month = "month"
    heat_season = "heat_season"
    ramadan = "ramadan"
    days_on_site_band = "days_on_site_band"
    trade = "trade"
    age_band = "age_band"
    nationality = "nationality"
    observation_category = "observation_category"
    observation_type = "observation_type"
    inspection_type = "inspection_type"
    control_level = "control_level"
    ca_priority = "ca_priority"


RESTRICTED_DIMENSIONS: frozenset[BreakdownDimension] = frozenset(
    {BreakdownDimension.age_band, BreakdownDimension.nationality}
)


class CompareDimension(StrEnum):
    """T9 compare_groups dimensions (§5.9)."""

    heat_season = "heat_season"
    shift = "shift"
    hour_band = "hour_band"
    weekday = "weekday"
    contractor = "contractor"
    activity = "activity"
    new_starter = "new_starter"
    site = "site"
    zone_type = "zone_type"
    ptw_involved = "ptw_involved"
    ca_overdue_at_event = "ca_overdue_at_event"
    ramadan = "ramadan"


class ExposureBasis(StrEnum):
    man_hours = "man_hours"
    headcount_days = "headcount_days"
    none = "none"


class PyramidLayer(StrEnum):
    FAT = "FAT"
    LTI = "LTI"
    RWC_JTC = "RWC_JTC"
    MTC = "MTC"
    FAC = "FAC"
    NM = "NM"
    UNSAFE_OBS = "UNSAFE_OBS"


class LeadingWarningCode(StrEnum):
    """§6.9."""

    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"  # 2-access-permits §6.9: induction coverage below threshold
    E6 = "E6"  # gate denial rate ≥ 2 × prior-3-month mean and ≥ 1.00 %
    E7 = "E7"  # ≥ 1 OFF-05 offence or ≥ 3 ADP suspensions in the month


class ChartId(StrEnum):
    """Dashboard charts §8.1 item 5."""

    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"
    C6 = "C6"
    C7 = "C7"
    C8 = "C8"
    C9 = "C9"
    C10 = "C10"  # gate checks by month with denial rate (2-access-permits §8.1)
    C11 = "C11"  # denial reasons breakdown, top 8
    C12 = "C12"  # expiring credentials next 90 days by week and kind


class ChartKind(StrEnum):
    bar = "bar"
    stacked_bar = "stacked_bar"
    horizontal_bar = "horizontal_bar"
    line = "line"
    combo = "combo"
    pyramid = "pyramid"
    table = "table"


class SeriesKind(StrEnum):
    bar = "bar"
    line = "line"
    area = "area"


class AxisKind(StrEnum):
    category = "category"
    period = "period"


class BandKind(StrEnum):
    heat_season = "heat_season"
    ramadan = "ramadan"


class ActionPanelItem(StrEnum):
    """§8.1 item 6."""

    overdue_cas = "overdue_cas"
    cas_pending_verification = "cas_pending_verification"
    investigations_overdue = "investigations_overdue"
    incidents_unclassified = "incidents_unclassified"
    external_notifications_due = "external_notifications_due"
    open_lti_cases = "open_lti_cases"
    missed_inspections = "missed_inspections"
    missing_daily_returns = "missing_daily_returns"
    high_risk_observations_without_ca = "high_risk_observations_without_ca"
    leading_warnings = "leading_warnings"
    # Phase 2 (2-access-permits §8.3)
    pass_applications_stale = "pass_applications_stale"
    raised_suspensions_pending = "raised_suspensions_pending"
    unreturned_overdue = "unreturned_overdue"
    lost_without_authority_notice = "lost_without_authority_notice"
    waps_approved_blocked = "waps_approved_blocked"
    ops_suspensions_active = "ops_suspensions_active"
    notam_not_issued_48h = "notam_not_issued_48h"
    revoked_token_scans = "revoked_token_scans"
    admitted_despite_denial = "admitted_despite_denial"
    induction_language_mismatch = "induction_language_mismatch"


class ExpiringItemKind(StrEnum):
    ca_due = "ca_due"
    investigation_due = "investigation_due"
    external_notification_due = "external_notification_due"
    inspection_planned = "inspection_planned"
    month_lock = "month_lock"
    # Phase 2 (2-access-permits §8.2)
    induction_expiry = "induction_expiry"
    reinduction_due = "reinduction_due"
    worker_id_expiry = "worker_id_expiry"
    airport_pass_expiry = "airport_pass_expiry"
    bg_recheck_due = "bg_recheck_due"
    adp_expiry = "adp_expiry"
    adp_suspension_end = "adp_suspension_end"
    avp_expiry = "avp_expiry"
    vehicle_document_expiry = "vehicle_document_expiry"
    wap_expiry = "wap_expiry"
    notam_expiry = "notam_expiry"
    obstacle_clearance_expiry = "obstacle_clearance_expiry"
    pass_return_due = "pass_return_due"


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class KpiExportTable(StrEnum):
    metrics = "metrics"
    comparisons = "comparisons"
    contractors = "contractors"
    breakdown = "breakdown"


# ---------------------------------------------------------------------------------------------
# AI (§5.9)
# ---------------------------------------------------------------------------------------------


class AiTool(StrEnum):
    get_kpis = "get_kpis"
    get_kpi_timeseries = "get_kpi_timeseries"
    get_breakdown = "get_breakdown"
    search_incidents = "search_incidents"
    get_incident = "get_incident"
    list_corrective_actions = "list_corrective_actions"
    list_observations_summary = "list_observations_summary"
    list_inspections_summary = "list_inspections_summary"
    compare_groups = "compare_groups"
    get_data_quality = "get_data_quality"
    get_lti_free = "get_lti_free"
    get_settings_and_targets = "get_settings_and_targets"
    get_leading_warnings = "get_leading_warnings"
    get_expiring_items = "get_expiring_items"
    propose_chart = "propose_chart"
    get_access_kpis = "get_access_kpis"  # T14 (1-dashboard v1.1)


class GroundingResult(StrEnum):
    passed = "passed"
    passed_after_retry = "passed_after_retry"
    failed = "failed"
    not_applicable = "not_applicable"


class InsightKind(StrEnum):
    trend = "trend"
    anomaly = "anomaly"
    warning = "warning"
    data_quality = "data_quality"
    positive = "positive"


class InsightSource(StrEnum):
    rules = "rules"
    ai = "ai"


class AiPromptWarning(StrEnum):
    """AI-15: what was masked in the user's prompt."""

    ID_NUMBER_MASKED = "ID_NUMBER_MASKED"
    EMAIL_MASKED = "EMAIL_MASKED"
    MOBILE_MASKED = "MOBILE_MASKED"


class MonthlyReportStatus(StrEnum):
    """AI-20: generating/failed are technical states around the spec's Draft."""

    generating = "generating"
    draft = "draft"
    reviewed = "reviewed"
    published = "published"
    failed = "failed"


class MonthlyReportSection(StrEnum):
    """AI-19 sections 1-13."""

    cover = "cover"
    executive_summary = "executive_summary"
    kpi_table = "kpi_table"
    manpower_exposure = "manpower_exposure"
    lagging_indicators = "lagging_indicators"
    leading_indicators = "leading_indicators"
    contractor_performance = "contractor_performance"
    investigations_root_causes = "investigations_root_causes"
    corrective_actions = "corrective_actions"
    trends_insights = "trends_insights"
    recommendations = "recommendations"
    data_quality = "data_quality"
    appendix_definitions = "appendix_definitions"


class ReferenceList(StrEnum):
    """§3.11 reference lists exposed at GET /reference-lists."""

    severity = "severity"
    activity = "activity"
    trade = "trade"
    body_part = "body_part"
    nature = "nature"
    mechanism = "mechanism"
    agency = "agency"
    treatment = "treatment"
    observation_category = "observation_category"
    inspection_type = "inspection_type"
    root_cause = "root_cause"
    # Phase 2 (2-access-permits §3.21)
    airside_offence = "airside_offence"
    vehicle_category = "vehicle_category"
    credential_reason = "credential_reason"
