"""Phase 4 enumerations — third-party certification (spec 4-third-party-cert v1.0).

Exported into the OpenAPI contract so the frontend gets typed unions. Code lists that the HSE
Manager can extend at run time (list PCT) are plain strings with a seeded catalogue
(`GET /cert-catalogue`); fixed lists are enums here.
"""

from enum import StrEnum

# ---------------------------------------------------------------------------------------------
# TPI organisations (§3.1-§3.3, §4.1)
# ---------------------------------------------------------------------------------------------


class TpiKind(StrEnum):
    """§3.1 kinds (AC2 adds ndt_body). No training-provider kind exists (BD-3)."""

    inspection_body = "inspection_body"  # ISO/IEC 17020
    personnel_certification_body = "personnel_certification_body"  # ISO/IEC 17024
    calibration_lab = "calibration_lab"  # ISO/IEC 17025
    ndt_body = "ndt_body"  # ISO 9712 personnel scheme, accredited to ISO/IEC 17024
    client_scheme = "client_scheme"
    fire_protection_service = "fire_protection_service"  # v1.2 (6c §11.5); never TP-4


class TpiStatus(StrEnum):
    """§4.1. "Accreditation lapsed" is derived (`accreditation_lapsed` on the read)."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    suspended = "suspended"
    blacklisted = "blacklisted"


class TpiBlacklistScope(StrEnum):
    all_certificates = "all_certificates"
    issued_from = "issued_from"


class AccreditationBody(StrEnum):
    sac = "sac"  # Saudi Accreditation Center (VERIFY current name)
    ilac_mra_other = "ilac_mra_other"
    client = "client"  # only with standard client_scheme


class AccreditationStandard(StrEnum):
    iso_iec_17020 = "iso_iec_17020"
    iso_iec_17024 = "iso_iec_17024"
    iso_iec_17025 = "iso_iec_17025"
    client_scheme = "client_scheme"
    civil_defense_licence = "civil_defense_licence"  # v1.2 (6c §11.5); no scope categories


class ClientApprovalStatus(StrEnum):
    active = "active"
    withdrawn = "withdrawn"


# ---------------------------------------------------------------------------------------------
# Equipment register (§3.4-§3.7, §3.16 EQC, §4.2, §4.3)
# ---------------------------------------------------------------------------------------------


class EquipmentCertCategory(StrEnum):
    """List EQC (§3.16). `scaffold` exists for hooks/KPIs only: scaffolds live in their own
    register (§3.8), equipment items never use it. Gas detectors are not an EQC category
    (EQ-3)."""

    tower_crane = "tower_crane"
    mobile_crane = "mobile_crane"
    crawler_crane = "crawler_crane"
    loader_crane = "loader_crane"
    overhead_gantry_crane = "overhead_gantry_crane"
    construction_hoist = "construction_hoist"
    mast_climber = "mast_climber"
    bmu = "bmu"
    mewp = "mewp"
    man_basket = "man_basket"
    forklift = "forklift"
    telehandler = "telehandler"
    excavator = "excavator"
    wheel_loader = "wheel_loader"
    piling_rig = "piling_rig"
    concrete_pump_boom = "concrete_pump_boom"
    lifting_accessory = "lifting_accessory"
    tripod_winch = "tripod_winch"
    pressure_vessel = "pressure_vessel"
    scaffold = "scaffold"


class EquipmentSubtype(StrEnum):
    """§3.4 subtype: required for lifting_accessory, mewp and pressure_vessel."""

    # tower crane (optional)
    flat_top = "flat_top"
    hammerhead = "hammerhead"
    luffing = "luffing"
    # mewp
    scissor = "scissor"
    boom = "boom"
    vertical_mast = "vertical_mast"
    # lifting accessory
    wire_rope_sling = "wire_rope_sling"
    chain_sling = "chain_sling"
    synthetic_sling = "synthetic_sling"
    shackle = "shackle"
    hook = "hook"
    eyebolt = "eyebolt"
    spreader_beam = "spreader_beam"
    lifting_beam = "lifting_beam"
    plate_clamp = "plate_clamp"
    chain_block = "chain_block"
    lever_hoist = "lever_hoist"
    beam_clamp = "beam_clamp"
    # pressure vessel
    air_receiver = "air_receiver"
    hydraulic_accumulator = "hydraulic_accumulator"
    other = "other"


class SafetyDevice(StrEnum):
    lmi_rci = "lmi_rci"
    anti_two_block = "anti_two_block"
    anemometer = "anemometer"
    anti_collision = "anti_collision"
    tilt_alarm = "tilt_alarm"
    emergency_lowering = "emergency_lowering"
    overload_cutout = "overload_cutout"


class EquipmentDocType(StrEnum):
    load_chart = "load_chart"
    operator_manual = "operator_manual"
    foundation_design = "foundation_design"
    erection_drawing = "erection_drawing"
    written_scheme = "written_scheme"
    other = "other"


class ServiceStatus(StrEnum):
    """§4.2 equipment item service status (system-maintained unless stated)."""

    awaiting_certificate = "awaiting_certificate"
    in_service = "in_service"
    quarantined = "quarantined"
    out_of_service = "out_of_service"
    blacklisted = "blacklisted"
    retired = "retired"


class ServiceStatusReason(StrEnum):
    """List SSR (§3.16)."""

    awaiting_certificate = "awaiting_certificate"
    certificate_expired = "certificate_expired"
    certificate_suspended = "certificate_suspended"
    certificate_revoked = "certificate_revoked"
    certificate_unverified = "certificate_unverified"
    configuration_changed = "configuration_changed"
    failed_inspection = "failed_inspection"
    defect_a = "defect_a"
    defect_b_overdue = "defect_b_overdue"
    tpi_blacklisted = "tpi_blacklisted"
    manual_tag_out = "manual_tag_out"
    blacklisted = "blacklisted"
    retired_destroyed = "retired_destroyed"
    retired_sold = "retired_sold"
    retired_other = "retired_other"


class RetireReason(StrEnum):
    """§4.2 manual retirement (capability 112); `retired_destroyed` is set by DF-7."""

    retired_sold = "retired_sold"
    retired_other = "retired_other"


class EquipmentBlacklistReason(StrEnum):
    """List EBR (§3.13)."""

    forged_certificate = "forged_certificate"
    identity_unverifiable = "identity_unverifiable"
    structural_damage = "structural_damage"
    repeated_dangerous_defects = "repeated_dangerous_defects"
    recall_unresolved = "recall_unresolved"
    other = "other"


class EquipmentDeploymentStatus(StrEnum):
    """§4.3."""

    planned = "planned"
    approved = "approved"
    on_site = "on_site"
    demobilised = "demobilised"
    cancelled = "cancelled"


class ArrivalChecklistItem(StrEnum):
    """List AIC (§3.16)."""

    AIC_01 = "AIC-01"
    AIC_02 = "AIC-02"
    AIC_03 = "AIC-03"
    AIC_04 = "AIC-04"
    AIC_05 = "AIC-05"
    AIC_06 = "AIC-06"
    AIC_07 = "AIC-07"
    AIC_08 = "AIC-08"


class ChecklistItemResult(StrEnum):
    pass_ = "pass"
    fail = "fail"
    na = "n.a."


class PassFail(StrEnum):
    pass_ = "pass"
    fail = "fail"


class ConfigurationEventType(StrEnum):
    """§3.7."""

    erection = "erection"
    climb_jacking = "climb_jacking"
    jib_change = "jib_change"
    tie_in_change = "tie_in_change"
    relocation = "relocation"
    mast_extension = "mast_extension"
    major_repair = "major_repair"
    storm_exceedance = "storm_exceedance"
    boom_configuration_change = "boom_configuration_change"


# ---------------------------------------------------------------------------------------------
# Certificates and verification (§3.6, §3.9, §3.10, §4.4)
# ---------------------------------------------------------------------------------------------


class CertKind(StrEnum):
    equipment = "equipment"
    personnel = "personnel"


class CertInspectionType(StrEnum):
    """§3.6 equipment certificate inspection type."""

    initial = "initial"
    periodic = "periodic"
    after_repair = "after_repair"
    after_configuration_change = "after_configuration_change"
    after_incident = "after_incident"
    pre_mobilisation = "pre_mobilisation"


class CertificateStatus(StrEnum):
    """§4.4 (equipment and personnel). `historic` = an already-expired certificate attached
    to the history by capability 107 (EC-2); never in force."""

    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"
    historic = "historic"


class CertStatusReason(StrEnum):
    """Why a certificate was suspended / revoked / rejected / superseded (system or user)."""

    configuration_changed = "configuration_changed"
    verification_failed = "verification_failed"
    tpi_blacklisted = "tpi_blacklisted"
    tpi_revocation_notice = "tpi_revocation_notice"
    tpi_suspension_notice = "tpi_suspension_notice"
    hse_suspension = "hse_suspension"
    document_review = "document_review"
    newer_certificate = "newer_certificate"
    other = "other"


class VerificationStatus(StrEnum):
    """§4.4 verification status (independent of the certificate status)."""

    not_verified = "not_verified"
    verified = "verified"
    failed = "failed"
    unable_to_verify = "unable_to_verify"


class CertSource(StrEnum):
    manual = "manual"
    import_ = "import"
    tpi_register_file = "tpi_register_file"


class LineResult(StrEnum):
    pass_ = "pass"
    pass_with_conditions = "pass_with_conditions"
    fail = "fail"


class CertLimitingFactor(StrEnum):
    """§6.1 / §6.2: the term that gives valid_until (the printed date on a tie)."""

    printed_next_due = "printed_next_due"
    category_interval = "category_interval"
    printed_expiry = "printed_expiry"
    cap = "cap"


class LimitationCode(StrEnum):
    """List LIM (equipment limitations)."""

    derated_swl = "derated_swl"
    no_personnel_lifting = "no_personnel_lifting"
    max_wind_ms = "max_wind_ms"
    daylight_only = "daylight_only"
    fixed_configuration_only = "fixed_configuration_only"
    outriggers_full_extension_only = "outriggers_full_extension_only"
    supervised_use_only = "supervised_use_only"
    reinspect_after_hours = "reinspect_after_hours"
    other = "other"


class PersonnelLimitationCode(StrEnum):
    """List LIM-P (non-medical only, P4-6)."""

    supervised_only = "supervised_only"
    trainee_logbook = "trainee_logbook"
    specific_model_only = "specific_model_only"
    other = "other"


class LiftingGearColour(StrEnum):
    """EC-12 colour code (scheme defined in settings)."""

    red = "red"
    yellow = "yellow"
    blue = "blue"
    green = "green"
    white = "white"
    orange = "orange"
    black = "black"
    brown = "brown"


class DefectCategory(StrEnum):
    """DF-1 (LOLER reg. 10 logic)."""

    A = "A"
    B = "B"
    C = "C"


class CertLevel(StrEnum):
    """§3.9 level: RIGGER / ROPE-ACCESS 1-3, RADIOGRAPHER I-III (I rejected), SCAFFOLDER
    basic/advanced."""

    level_1 = "1"
    level_2 = "2"
    level_3 = "3"
    level_i = "I"
    level_ii = "II"
    level_iii = "III"
    basic = "basic"
    advanced = "advanced"


class IdMatchResult(StrEnum):
    """PC-3 (the typed ID number itself is never stored)."""

    matched = "matched"
    matched_previous_id = "matched_previous_id"
    not_shown = "not_shown"


class NameMatch(StrEnum):
    """PC-4."""

    exact = "exact"
    partial = "partial"
    none = "none"


class CertVerificationMethod(StrEnum):
    """§3.10. `original_sighted` is recorded but never verifies (VF-3)."""

    tpi_portal = "tpi_portal"
    tpi_qr_url = "tpi_qr_url"
    tpi_email = "tpi_email"
    tpi_phone = "tpi_phone"
    tpi_register_file = "tpi_register_file"
    client_register = "client_register"
    original_sighted = "original_sighted"


class VerificationOutcome(StrEnum):
    confirmed = "confirmed"
    not_found = "not_found"
    details_differ = "details_differ"
    revoked_by_tpi = "revoked_by_tpi"
    no_response = "no_response"


class VerificationDifference(StrEnum):
    holder = "holder"
    serial = "serial"
    dates = "dates"
    scope = "scope"
    swl = "swl"
    result = "result"
    other = "other"


class ScanReason(StrEnum):
    """P4-3: reason required to open a personnel certificate scan (capability 119)."""

    verification = "verification"
    authority_request = "authority_request"
    incident_investigation = "incident_investigation"
    client_audit = "client_audit"
    other = "other"


class ScanSide(StrEnum):
    front = "front"
    back = "back"


# ---------------------------------------------------------------------------------------------
# Scaffolds (§3.8, §4.6)
# ---------------------------------------------------------------------------------------------


class ScaffoldType(StrEnum):
    independent_tied = "independent_tied"
    system_modular = "system_modular"
    mobile_tower = "mobile_tower"
    birdcage = "birdcage"
    cantilever = "cantilever"
    suspended_hanging = "suspended_hanging"
    loading_bay = "loading_bay"
    other = "other"


class ScaffoldTagStatus(StrEnum):
    none = "none"
    green = "green"
    yellow = "yellow"
    red = "red"
    expired = "expired"
    inspection_required = "inspection_required"


class ScaffoldStatus(StrEnum):
    """§4.6."""

    under_erection = "under_erection"
    in_use = "in_use"
    closed_red = "closed_red"
    under_alteration = "under_alteration"
    dismantled = "dismantled"


class ScaffoldInspectionType(StrEnum):
    handover = "handover"
    periodic = "periodic"
    after_alteration = "after_alteration"
    after_adverse_weather = "after_adverse_weather"
    after_incident = "after_incident"


class ScaffoldInspectionResult(StrEnum):
    green = "green"
    yellow = "yellow"
    red = "red"


class ScaffoldChecklistItem(StrEnum):
    """List SIC (§3.16). SIC-10 allows n.a."""

    SIC_01 = "SIC-01"
    SIC_02 = "SIC-02"
    SIC_03 = "SIC-03"
    SIC_04 = "SIC-04"
    SIC_05 = "SIC-05"
    SIC_06 = "SIC-06"
    SIC_07 = "SIC-07"
    SIC_08 = "SIC-08"
    SIC_09 = "SIC-09"
    SIC_10 = "SIC-10"
    SIC_11 = "SIC-11"


class ReinspectionReason(StrEnum):
    """SF-5 "Require re-inspection" (capability 112)."""

    adverse_weather = "adverse_weather"
    nearby_impact = "nearby_impact"
    incident = "incident"
    ops_event = "ops_event"  # system: Phase 2 dust_sandstorm / thunderstorm_lightning
    other = "other"


# ---------------------------------------------------------------------------------------------
# Defects (§3.11, §4.5)
# ---------------------------------------------------------------------------------------------


class DefectSource(StrEnum):
    tpi_inspection = "tpi_inspection"
    pre_use_check = "pre_use_check"
    arrival_inspection = "arrival_inspection"
    site_inspection = "site_inspection"
    incident = "incident"
    observation = "observation"
    ptw_audit = "ptw_audit"
    operator_report = "operator_report"
    other = "other"


class DefectStatus(StrEnum):
    open = "open"
    rectified = "rectified"
    closed = "closed"
    cancelled = "cancelled"


class DefectClosureMethod(StrEnum):
    tpi_certificate = "tpi_certificate"
    hse_verification = "hse_verification"
    destroyed = "destroyed"  # DF-7: destroyed / returned to manufacturer


# ---------------------------------------------------------------------------------------------
# Bans and blacklisting (§3.12, §3.13, §4.7)
# ---------------------------------------------------------------------------------------------


class BanReason(StrEnum):
    """List BR (sensitive, P4-1)."""

    forged_certificate = "forged_certificate"
    certificate_misuse = "certificate_misuse"
    unsafe_operation = "unsafe_operation"
    incident_investigation = "incident_investigation"
    other = "other"


class BanStatus(StrEnum):
    active = "active"
    lifted = "lifted"


class BlacklistSubject(StrEnum):
    """§8.4 blacklist and ban register rows."""

    equipment = "equipment"
    person = "person"
    tpi = "tpi"


# ---------------------------------------------------------------------------------------------
# Hooks (§3.14, §4.8, §5.10)
# ---------------------------------------------------------------------------------------------


class HookStage(StrEnum):
    """§4.8 per project and kind: warn (no provider) → transition → block. Never back."""

    warn = "warn"
    transition = "transition"
    block = "block"


class HookCodePolicy(StrEnum):
    """Effective policy of one code today: `transition` = not_met without hard stop is
    returned as warn (HOOK_NOT_MET_WARN); `block` = not_met blocks."""

    warn = "warn"
    transition = "transition"
    block = "block"


class HookReasonCode(StrEnum):
    """Provider detail reasons: Phase 4 (HK4-8, HK4-3, SF-, PC-, EC-) and, from v0.6.0, the
    Phase 5 training_course provider (5-training HK5-6). Every value is also an ErrorCode so
    the frontend translates one list."""

    EQUIPMENT_NOT_REGISTERED = "EQUIPMENT_NOT_REGISTERED"
    CATEGORY_MISMATCH = "CATEGORY_MISMATCH"
    EQUIPMENT_BLACKLISTED = "EQUIPMENT_BLACKLISTED"
    EQUIPMENT_RETIRED = "EQUIPMENT_RETIRED"
    EQUIPMENT_OUT_OF_SERVICE = "EQUIPMENT_OUT_OF_SERVICE"
    EQUIPMENT_QUARANTINED = "EQUIPMENT_QUARANTINED"
    EQUIPMENT_NOT_DEPLOYED = "EQUIPMENT_NOT_DEPLOYED"
    ARRIVAL_INSPECTION_MISSING = "ARRIVAL_INSPECTION_MISSING"
    CERT_MISSING = "CERT_MISSING"
    CERT_EXPIRED = "CERT_EXPIRED"
    CERT_UNVERIFIED = "CERT_UNVERIFIED"
    CERT_SUSPENDED = "CERT_SUSPENDED"
    CERT_REVOKED = "CERT_REVOKED"
    CONFIGURATION_CHANGED = "CONFIGURATION_CHANGED"
    SWL_LIMITATION = "SWL_LIMITATION"
    LIMITATION_CONFLICT = "LIMITATION_CONFLICT"
    LIFTING_DUTY_NOT_CERTIFIED = "LIFTING_DUTY_NOT_CERTIFIED"
    COLOUR_CODE_OUT_OF_PERIOD = "COLOUR_CODE_OUT_OF_PERIOD"
    TPI_BLACKLISTED = "TPI_BLACKLISTED"
    SCAFFOLD_NOT_REGISTERED = "SCAFFOLD_NOT_REGISTERED"
    SCAFFOLD_INSPECTION_OVERDUE = "SCAFFOLD_INSPECTION_OVERDUE"
    SCAFFOLD_TAG_RED = "SCAFFOLD_TAG_RED"
    SCAFFOLD_INSPECTION_REQUIRED = "SCAFFOLD_INSPECTION_REQUIRED"
    SCAFFOLD_YELLOW_TAG = "SCAFFOLD_YELLOW_TAG"
    CERT_HOLDER_BANNED = "CERT_HOLDER_BANNED"
    CERT_SCOPE_MISMATCH = "CERT_SCOPE_MISMATCH"
    CERT_LIMITATION = "CERT_LIMITATION"
    CARD_RESTRICTION_REVIEW = "CARD_RESTRICTION_REVIEW"
    EXPIRING_7D = "EXPIRING_7D"
    UNKNOWN_CODE = "UNKNOWN_CODE"
    # v0.6.0 (5-training HK5-3, HK5-6, HK5-7): training_course provider detail reasons
    TRAINING_MISSING = "TRAINING_MISSING"
    TRAINING_EXPIRED = "TRAINING_EXPIRED"
    TRAINING_PENDING_REVIEW = "TRAINING_PENDING_REVIEW"
    TRAINING_UNVERIFIED = "TRAINING_UNVERIFIED"
    TRAINING_SUSPENDED = "TRAINING_SUSPENDED"
    TRAINING_REVOKED = "TRAINING_REVOKED"
    TRAINING_VERIFICATION_FAILED = "TRAINING_VERIFICATION_FAILED"
    INDUCTION_NOT_VALID = "INDUCTION_NOT_VALID"
    HOLDER_NOT_LINKED = "HOLDER_NOT_LINKED"
    # v0.7.0 (6a-occupational-health HK6-3, HK6-6): medical_fitness provider detail reasons
    # (tier 3 only, HK6-7; gate logs never store them, P6-7)
    MEDICAL_HOLD = "MEDICAL_HOLD"
    MEDICAL_UNFIT = "MEDICAL_UNFIT"
    MEDICAL_PENDING_REVIEW = "MEDICAL_PENDING_REVIEW"
    MEDICAL_UNVERIFIED = "MEDICAL_UNVERIFIED"
    MEDICAL_REVOKED = "MEDICAL_REVOKED"
    MEDICAL_VERIFICATION_FAILED = "MEDICAL_VERIFICATION_FAILED"
    MEDICAL_MISSING = "MEDICAL_MISSING"
    RESTRICTION_CONFLICT = "RESTRICTION_CONFLICT"
    MEDICAL_REVIEW_DUE = "MEDICAL_REVIEW_DUE"
    MEDICAL_EXPIRED = "MEDICAL_EXPIRED"
    WORKER_UNKNOWN = "WORKER_UNKNOWN"


class CertScopeMismatch(StrEnum):
    """PC-7 meta `which`."""

    category = "category"
    capacity = "capacity"
    level = "level"
    subtype = "subtype"
    scaffolder_level = "scaffolder_level"


class HookUse(StrEnum):
    """HK-3 context `use` (HK4-8)."""

    lifting_appliance = "lifting_appliance"
    lifting_accessory = "lifting_accessory"
    personnel_lift = "personnel_lift"
    access_equipment = "access_equipment"
    excavating_plant = "excavating_plant"
    rescue_equipment = "rescue_equipment"
    vehicle_access = "vehicle_access"
    other = "other"


# ---------------------------------------------------------------------------------------------
# Imports (§3.15, §5.11)
# ---------------------------------------------------------------------------------------------


class CertImportTemplate(StrEnum):
    equipment_certificates = "equipment_certificates"
    personnel_certificates = "personnel_certificates"


class CertImportSource(StrEnum):
    contractor_file = "contractor_file"
    tpi_register_file = "tpi_register_file"


class CertImportCode(StrEnum):
    """IM-7 validation codes (errors block the row; a file-level error blocks the file)."""

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
    W01 = "W01"
    W02 = "W02"
    W03 = "W03"
    W04 = "W04"
    W05 = "W05"
    W06 = "W06"


class CertImportStatus(StrEnum):
    """§4.9 (as Phase 1 §4.1): validated → committed / discarded; validated → expired."""

    validated = "validated"
    committed = "committed"
    discarded = "discarded"
    expired = "expired"


# ---------------------------------------------------------------------------------------------
# Certification check (VF-8, VF-9) and KPIs (§6.7, KC-4)
# ---------------------------------------------------------------------------------------------


class CertCheckSubject(StrEnum):
    equipment = "equipment"
    scaffold = "scaffold"
    person = "person"
    training_record = "training_record"  # v0.6.0: TR QR (5-training CK5-1, capability 142)


class CertCheckResult(StrEnum):
    """Colour of the sticker check result (VF-8)."""

    in_service = "in_service"  # green
    restricted = "restricted"  # yellow tag / pass_with_conditions (amber)
    not_usable = "not_usable"  # red: out of service, quarantined, blacklisted, retired, red
    revoked_token = "revoked_token"  # CREDENTIAL_REVOKED
    unknown = "unknown"  # TOKEN_UNKNOWN / cert_no not found


class CertKpiGroupBy(StrEnum):
    """KC-4 / §8.1 breakdowns of /kpi/certification and T16."""

    category = "category"
    cert_type = "cert_type"
    contractor = "contractor"
    tpi = "tpi"
    defect_category = "defect_category"
    reason_code = "reason_code"
    month = "month"
