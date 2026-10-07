"""Phase 2 domain enumerations (spec 2-access-permits §3, §4, §5).

Codes are stable (spec §3.21, Phase 0 rule 48): EN/AR labels live in reference lists or the
frontend i18n files. These enums are exported into the OpenAPI contract.
"""

from enum import StrEnum

# ---------------------------------------------------------------------------------------------
# Worker register (§3.1, §3.2, §4.1, §4.2)
# ---------------------------------------------------------------------------------------------


class WorkerPersonType(StrEnum):
    contractor_worker = "contractor_worker"
    client_pmc_staff = "client_pmc_staff"
    visitor = "visitor"


class WorkerIdType(StrEnum):
    """iqama ^2\\d{9}$, national_id ^1\\d{9}$, gcc_id ^[A-Z0-9]{6,15}$, passport ^[A-Z0-9]{6,9}$."""

    iqama = "iqama"
    national_id = "national_id"
    gcc_id = "gcc_id"
    passport = "passport"


class WorkerLanguage(StrEnum):
    ar = "ar"
    en = "en"
    ur = "ur"
    hi = "hi"
    bn = "bn"
    ne = "ne"
    tl = "tl"
    ml = "ml"
    ta = "ta"
    other = "other"


class WorkerStatus(StrEnum):
    """§4.1."""

    active = "active"
    banned = "banned"
    inactive = "inactive"
    anonymised = "anonymised"


class DeploymentStatus(StrEnum):
    """§4.2."""

    pending_induction = "pending_induction"
    mobilised = "mobilised"
    demobilised = "demobilised"


class UnmaskReason(StrEnum):
    """WK-5: reason for revealing a full ID number (capability 48)."""

    pass_application = "pass_application"
    authority_request = "authority_request"
    identity_verification = "identity_verification"
    incident_investigation = "incident_investigation"
    other = "other"


# ---------------------------------------------------------------------------------------------
# Induction (§3.3, §3.4, §4.3)
# ---------------------------------------------------------------------------------------------


class InductionType(StrEnum):
    general_site = "general_site"
    airside = "airside"
    zone_specific = "zone_specific"
    visitor = "visitor"


class InductionDelivererRole(StrEnum):
    hse_manager = "hse_manager"
    hse_officer = "hse_officer"
    contractor_hse_rep = "contractor_hse_rep"


class InductionResult(StrEnum):
    passed = "passed"
    failed = "failed"


class InductionStatus(StrEnum):
    """§4.3."""

    valid = "valid"
    failed = "failed"
    suspended = "suspended"
    revoked = "revoked"
    superseded = "superseded"
    expired = "expired"


# ---------------------------------------------------------------------------------------------
# Zone access profiles and hooks (§3.5, §5.3)
# ---------------------------------------------------------------------------------------------


class AreaCategory(StrEnum):
    """ADP category / AVP area (DP-1 coverage: manoeuvring ⊇ apron ⊇ airside_roads)."""

    apron = "apron"
    manoeuvring = "manoeuvring"
    airside_roads = "airside_roads"


class HookKind(StrEnum):
    """HK-1: requirements owned by later phases, evaluated through a provider (HK-3)."""

    training_course = "training_course"
    personnel_certificate = "personnel_certificate"
    equipment_certificate = "equipment_certificate"
    medical_fitness = "medical_fitness"


class HookPolicy(StrEnum):
    """HK-4: warn → not_evaluated becomes warn (HOOK_NOT_AVAILABLE); block → not_met."""

    warn = "warn"
    block = "block"


class SuspendedContractorGateMode(StrEnum):
    """Setting suspended_contractor_gate (§2, LC-7)."""

    deny = "deny"
    warn = "warn"


class HookSubjectType(StrEnum):
    worker = "worker"
    vehicle = "vehicle"


class HookProviderStatus(StrEnum):
    """HK-3 provider contract result."""

    met = "met"
    not_met = "not_met"
    expiring = "expiring"
    unknown_code = "unknown_code"


class RequirementKind(StrEnum):
    """ZP-4 steps evaluated by the eligibility function E (ZP-3)."""

    deployment = "deployment"
    worker_status = "worker_status"
    contractor_status = "contractor_status"
    id_validity = "id_validity"
    induction = "induction"
    airport_pass = "airport_pass"
    escort = "escort"
    work_area_permit = "work_area_permit"
    adp = "adp"
    hook = "hook"


class RequirementStatus(StrEnum):
    """ZP-3. "expiring" = met with valid_until ≤ local date(at) + 7 days."""

    met = "met"
    not_met = "not_met"
    expiring = "expiring"
    warn = "warn"
    not_evaluated = "not_evaluated"


class EligibilityContext(StrEnum):
    """ZP-5: where E is evaluated. Only `gate` checks the WAP step (ZP-4 step 7)."""

    check = "check"
    gate = "gate"
    wap = "wap"
    application = "application"
    ptw = "ptw"


# ---------------------------------------------------------------------------------------------
# Airport passes (§3.6-§3.9, §4.4)
# ---------------------------------------------------------------------------------------------


class CardColour(StrEnum):
    red = "red"
    blue = "blue"
    green = "green"
    yellow = "yellow"
    orange = "orange"
    white = "white"
    grey = "grey"


class PassAreaKind(StrEnum):
    apron = "apron"
    manoeuvring = "manoeuvring"
    terminal_airside = "terminal_airside"
    airside_roads = "airside_roads"
    other_sra = "other_sra"


class PassApplicationType(StrEnum):
    new = "new"
    renewal = "renewal"
    replacement_lost = "replacement_lost"
    replacement_damaged = "replacement_damaged"
    area_change = "area_change"


class PassApplicationStatus(StrEnum):
    """§4.4."""

    draft = "draft"
    submitted = "submitted"
    endorsed = "endorsed"
    lodged = "lodged"
    approved = "approved"
    refused = "refused"
    issued = "issued"
    withdrawn = "withdrawn"
    cancelled = "cancelled"


class BackgroundCheckStatus(StrEnum):
    """Sensitive (P2-1): returned only with capability 56."""

    not_required = "not_required"
    submitted = "submitted"
    in_progress = "in_progress"
    cleared = "cleared"
    not_cleared = "not_cleared"
    expired = "expired"


class ValidityStatus(StrEnum):
    """§4.5 for airport passes, ADPs and AVPs. `pending` and `withdrawn` exist only for ADP/AVP
    applications that have not been issued yet (DECISIONS: the spec has no ADP/AVP application
    entity)."""

    pending = "pending"
    active = "active"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"
    withdrawn = "withdrawn"


class CustodyStatus(StrEnum):
    """§4.9. "Overdue" is derived: return_due and today > return_due_on."""

    held = "held"
    return_due = "return_due"
    returned = "returned"
    lost = "lost"


class LimitingFactor(StrEnum):
    """§6.2: the term that gives the effective validity."""

    card_expiry_date = "card_expiry_date"
    own_valid_until = "own_valid_until"
    worker_id_expiry_date = "worker.id_expiry_date"
    deployment_planned_demob_on = "deployment.planned_demob_on"
    engagement_demobilisation_date = "engagement.demobilisation_date"
    project_planned_end_date = "project.planned_end_date"
    background_recheck_due = "background.recheck_due"
    pass_effective_valid_until = "pass.effective_valid_until"
    licence_expiry_date = "licence_expiry_date"
    istimara_expiry = "istimara_expiry"
    insurance_expiry = "insurance_expiry"
    mvpi_expiry = "mvpi_expiry"
    equipment_certificate = "equipment_certificate"
    category_max_validity = "category.max_validity_days"
    valid_until = "valid_until"


# ---------------------------------------------------------------------------------------------
# ADP and offences (§3.10, §3.11)
# ---------------------------------------------------------------------------------------------


class VehicleClass(StrEnum):
    light = "light"
    heavy = "heavy"
    special_plant = "special_plant"


class LicenceIssuer(StrEnum):
    ksa = "ksa"
    gcc = "gcc"
    international = "international"


class LicenceClass(StrEnum):
    private = "private"
    public_transport = "public_transport"
    heavy_transport = "heavy_transport"
    heavy_equipment = "heavy_equipment"
    motorcycle = "motorcycle"


class PracticalTestResult(StrEnum):
    passed = "passed"
    failed = "failed"


class OffenceStatus(StrEnum):
    """Only recorded/upheld (and disputed until withdrawn, DP-10) count points."""

    recorded = "recorded"
    disputed = "disputed"
    upheld = "upheld"
    withdrawn = "withdrawn"


# ---------------------------------------------------------------------------------------------
# Vehicles and AVPs (§3.12, §3.13)
# ---------------------------------------------------------------------------------------------


class VehicleOwnerType(StrEnum):
    company = "company"
    rental = "rental"
    individual = "individual"


class VehicleCategory(StrEnum):
    """List VC (§3.21)."""

    light_vehicle = "light_vehicle"
    pickup = "pickup"
    van = "van"
    bus = "bus"
    truck = "truck"
    tipper = "tipper"
    water_tanker = "water_tanker"
    fuel_bowser = "fuel_bowser"
    concrete_mixer = "concrete_mixer"
    mobile_crane = "mobile_crane"
    crawler_crane = "crawler_crane"
    mewp = "mewp"
    forklift = "forklift"
    telehandler = "telehandler"
    excavator = "excavator"
    wheel_loader = "wheel_loader"
    grader = "grader"
    roller = "roller"
    paver = "paver"
    milling_machine = "milling_machine"
    line_marking_vehicle = "line_marking_vehicle"
    sweeper = "sweeper"
    lighting_tower = "lighting_tower"
    trailer = "trailer"
    other = "other"


class PlateType(StrEnum):
    private = "private"
    transport = "transport"
    heavy_equipment = "heavy_equipment"
    none = "none"


class VehicleStatus(StrEnum):
    active = "active"
    off_site = "off_site"
    withdrawn = "withdrawn"


class InspectionResult(StrEnum):
    passed = "passed"
    failed = "failed"


class AvpChecklistItem(StrEnum):
    """§3.13 checklist; n.a. not allowed for amber_beacon, company_marking, fire_extinguisher,
    tyres_brakes, lights (VP-4)."""

    amber_beacon = "amber_beacon"
    company_marking = "company_marking"
    chequered_flag_or_marking = "chequered_flag_or_marking"
    radio_fitted = "radio_fitted"
    fire_extinguisher = "fire_extinguisher"
    spill_kit = "spill_kit"
    fod_bin = "fod_bin"
    tyres_brakes = "tyres_brakes"
    reverse_alarm = "reverse_alarm"
    lights = "lights"
    no_loose_items = "no_loose_items"
    height_marking = "height_marking"


class ChecklistOutcome(StrEnum):
    pass_ = "pass"
    fail = "fail"
    na = "n.a."


# ---------------------------------------------------------------------------------------------
# NOTAM works clearances and obstacle clearances (§3.14, §3.15, §4.6, §4.7)
# ---------------------------------------------------------------------------------------------


class WorksImpact(StrEnum):
    taxiway_closure = "taxiway_closure"
    runway_closure = "runway_closure"
    declared_distances_change = "declared_distances_change"
    ils_outage = "ils_outage"
    lighting_outage = "lighting_outage"
    stand_closure = "stand_closure"
    obstacle = "obstacle"
    other = "other"


class NotamType(StrEnum):
    N = "N"
    R = "R"
    C = "C"


class NotamStatus(StrEnum):
    """§4.6. "In effect" is derived (issued and now inside the effective window)."""

    draft = "draft"
    submitted_to_ops = "submitted_to_ops"
    requested_from_ais = "requested_from_ais"
    issued = "issued"
    rejected = "rejected"
    replaced = "replaced"
    cancelled = "cancelled"
    expired = "expired"


class ObstacleEquipmentType(StrEnum):
    mobile_crane = "mobile_crane"
    tower_crane = "tower_crane"
    crawler_crane = "crawler_crane"
    piling_rig = "piling_rig"
    drilling_rig = "drilling_rig"
    mewp = "mewp"
    concrete_pump_boom = "concrete_pump_boom"
    excavator = "excavator"
    temporary_structure = "temporary_structure"
    other = "other"


class OlsSurface(StrEnum):
    approach = "approach"
    take_off_climb = "take_off_climb"
    transitional = "transitional"
    inner_horizontal = "inner_horizontal"
    conical = "conical"
    inner_approach = "inner_approach"
    inner_transitional = "inner_transitional"
    balked_landing = "balked_landing"
    none_applicable = "none_applicable"


class ClearanceReason(StrEnum):
    """OB-3, computed. Clearance is required iff the list is not empty."""

    zone_height_exceeded = "zone_height_exceeded"
    ols_penetration = "ols_penetration"
    within_ols_buffer = "within_ols_buffer"
    height_threshold = "height_threshold"
    operator_requires = "operator_requires"


class ObstacleDecision(StrEnum):
    approved = "approved"
    approved_with_conditions = "approved_with_conditions"
    rejected = "rejected"


class ObstacleCondition(StrEnum):
    obstruction_light = "obstruction_light"
    day_marking = "day_marking"
    lower_when_idle = "lower_when_idle"
    lower_at_night = "lower_at_night"
    notam_required = "notam_required"
    ats_coordination_each_lift = "ats_coordination_each_lift"
    daylight_only = "daylight_only"


class ObstacleStatus(StrEnum):
    """§4.7."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    approved_with_conditions = "approved_with_conditions"
    rejected = "rejected"
    suspended = "suspended"
    withdrawn = "withdrawn"
    expired = "expired"


# ---------------------------------------------------------------------------------------------
# Work-area access permits and operational suspensions (§3.16, §3.17, §4.8)
# ---------------------------------------------------------------------------------------------


class CrewRole(StrEnum):
    worker = "worker"
    supervisor = "supervisor"
    escort = "escort"
    driver = "driver"
    banksman = "banksman"


class WapStatus(StrEnum):
    """§4.8."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    active = "active"
    suspended = "suspended"
    closed = "closed"
    cancelled = "cancelled"
    expired = "expired"


class WapBlocker(StrEnum):
    """WA-13 blockers (recomputed on every change and at each window start)."""

    NOTAM_NOT_ISSUED = "NOTAM_NOT_ISSUED"
    NOTAM_NOT_COVERING_WINDOW = "NOTAM_NOT_COVERING_WINDOW"
    ILS_OUTAGE_NOTAM_REQUIRED = "ILS_OUTAGE_NOTAM_REQUIRED"
    HEIGHT_CLEARANCE_REQUIRED = "HEIGHT_CLEARANCE_REQUIRED"
    OBS_NOT_ACTIVE = "OBS_NOT_ACTIVE"
    WSP_REQUIRED = "WSP_REQUIRED"
    SUPERVISOR_INELIGIBLE = "SUPERVISOR_INELIGIBLE"
    NO_ELIGIBLE_CREW = "NO_ELIGIBLE_CREW"
    CONTRACTOR_SUSPENDED = "CONTRACTOR_SUSPENDED"
    OPS_SUSPENSION_ACTIVE = "OPS_SUSPENSION_ACTIVE"


class CrewMemberStatus(StrEnum):
    """WA-10/WA-11: ineligible non-supervisors are excluded automatically and re-included at
    the next evaluation once eligible."""

    included = "included"
    excluded = "excluded"
    removed = "removed"


class FodCheckResult(StrEnum):
    clear = "clear"
    not_clear = "not_clear"


class OpsEventType(StrEnum):
    lvp = "lvp"
    dust_sandstorm = "dust_sandstorm"
    thunderstorm_lightning = "thunderstorm_lightning"
    security_alert = "security_alert"
    aircraft_emergency = "aircraft_emergency"
    atc_instruction = "atc_instruction"
    vip_movement = "vip_movement"
    other = "other"


class OpsEventSource(StrEnum):
    aocc = "aocc"
    atc = "atc"
    airport_security = "airport_security"
    hse = "hse"


# ---------------------------------------------------------------------------------------------
# Credential lifecycle (§3.18, §5.9)
# ---------------------------------------------------------------------------------------------


class CredentialKind(StrEnum):
    """§3.18. `wap` and `worker` events are written by the WAP and worker transitions; the
    /credentials endpoints accept induction, airport_pass, adp, avp and access_card."""

    induction = "induction"
    airport_pass = "airport_pass"
    adp = "adp"
    avp = "avp"
    wap = "wap"
    access_card = "access_card"
    worker = "worker"


class CredentialAction(StrEnum):
    suspend_raised = "suspend_raised"
    suspend_confirmed = "suspend_confirmed"
    reinstated = "reinstated"
    revoked = "revoked"
    expired = "expired"
    return_due = "return_due"
    returned = "returned"
    lost_reported = "lost_reported"
    token_rotated = "token_rotated"
    auto_suspended = "auto_suspended"
    auto_reinstated = "auto_reinstated"


class CredentialReason(StrEnum):
    """List LC-R (§3.21)."""

    violation = "violation"
    investigation_pending = "investigation_pending"
    contractor_suspended = "contractor_suspended"
    contractor_blacklisted = "contractor_blacklisted"
    worker_banned = "worker_banned"
    id_expired = "id_expired"
    licence_expired = "licence_expired"
    vehicle_document_expired = "vehicle_document_expired"
    dependency_invalid = "dependency_invalid"
    points_threshold = "points_threshold"
    security_request = "security_request"
    ops_suspension = "ops_suspension"
    demobilised = "demobilised"
    superseded = "superseded"
    lost_stolen = "lost_stolen"
    fraud_misuse = "fraud_misuse"
    other = "other"


DEPENDENCY_REASONS: frozenset[CredentialReason] = frozenset(
    {
        CredentialReason.dependency_invalid,
        CredentialReason.id_expired,
        CredentialReason.licence_expired,
        CredentialReason.vehicle_document_expired,
    }
)
"""LC-6: applied and lifted by the system only."""


class SuspensionState(StrEnum):
    """An open suspension on a credential: raised (≤ raised_suspension_max_hours, LC-3),
    confirmed (until lifted), or system (dependency / points / violation)."""

    raised = "raised"
    confirmed = "confirmed"
    system = "system"


class AccessCardReissueReason(StrEnum):
    lost = "lost"
    damaged = "damaged"
    other = "other"


# ---------------------------------------------------------------------------------------------
# Gates and gate checks (§3.19, §3.20, §5.10)
# ---------------------------------------------------------------------------------------------


class GateType(StrEnum):
    site_gate = "site_gate"
    zone_entry = "zone_entry"
    airside_precheck = "airside_precheck"


class GateStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class QrKind(StrEnum):
    """§3.20 payload `HSE2:<kind>:<token>`."""

    AC = "AC"
    VS = "VS"
    WP = "WP"


class QrTokenStatus(StrEnum):
    active = "active"
    rotated = "rotated"
    revoked = "revoked"


class GateDirection(StrEnum):
    in_ = "in"
    out = "out"


class GateResult(StrEnum):
    """GC-5."""

    GRANTED = "GRANTED"
    GRANTED_WITH_WARNING = "GRANTED_WITH_WARNING"
    DENIED = "DENIED"
    PENDING_ESCORT = "PENDING_ESCORT"
    PENDING_DRIVER = "PENDING_DRIVER"
    PENDING_ESCORT_VEHICLE = "PENDING_ESCORT_VEHICLE"
    EXIT_RECORDED = "EXIT_RECORDED"
    WAP_VIEW = "WAP_VIEW"


class GateReasonSeverity(StrEnum):
    deny = "deny"
    warn = "warn"


class GateReasonCode(StrEnum):
    """GC-6, in the order used for K-53 (a check counts under its first DENY reason).
    CONTRACTOR_SUSPENDED is deny or warn per the `suspended_contractor_gate` setting."""

    TOKEN_UNKNOWN = "TOKEN_UNKNOWN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    WORKER_NOT_DEPLOYED = "WORKER_NOT_DEPLOYED"
    WORKER_BANNED = "WORKER_BANNED"
    CONTRACTOR_SUSPENDED = "CONTRACTOR_SUSPENDED"
    CONTRACTOR_BLACKLISTED = "CONTRACTOR_BLACKLISTED"
    ID_EXPIRED = "ID_EXPIRED"
    INDUCTION_MISSING = "INDUCTION_MISSING"
    INDUCTION_EXPIRED = "INDUCTION_EXPIRED"
    INDUCTION_SUSPENDED = "INDUCTION_SUSPENDED"
    INDUCTION_ABSENCE = "INDUCTION_ABSENCE"
    PASS_MISSING = "PASS_MISSING"
    PASS_AREA_NOT_COVERED = "PASS_AREA_NOT_COVERED"
    PASS_SUSPENDED = "PASS_SUSPENDED"
    PASS_EXPIRED = "PASS_EXPIRED"
    CREDENTIAL_REVOKED = "CREDENTIAL_REVOKED"
    CREDENTIAL_LOST = "CREDENTIAL_LOST"
    ESCORT_REQUIRED = "ESCORT_REQUIRED"
    ESCORT_INVALID = "ESCORT_INVALID"
    ESCORT_RATIO_EXCEEDED = "ESCORT_RATIO_EXCEEDED"
    WAP_MISSING = "WAP_MISSING"
    WAP_NOT_ACTIVE = "WAP_NOT_ACTIVE"
    WAP_SUSPENDED = "WAP_SUSPENDED"
    WAP_OUTSIDE_WINDOW = "WAP_OUTSIDE_WINDOW"
    CREW_EXCLUDED = "CREW_EXCLUDED"
    ADP_MISSING = "ADP_MISSING"
    ADP_CATEGORY = "ADP_CATEGORY"
    ADP_SUSPENDED = "ADP_SUSPENDED"
    AVP_MISSING = "AVP_MISSING"
    AVP_AREA = "AVP_AREA"
    AVP_SUSPENDED = "AVP_SUSPENDED"
    VEHICLE_DOC_EXPIRED = "VEHICLE_DOC_EXPIRED"
    HEIGHT_CLEARANCE_REQUIRED = "HEIGHT_CLEARANCE_REQUIRED"
    HOOK_NOT_MET = "HOOK_NOT_MET"
    # warn severity
    EXPIRING_7D = "EXPIRING_7D"
    HOOK_NOT_AVAILABLE = "HOOK_NOT_AVAILABLE"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"


GATE_WARN_CODES: frozenset[GateReasonCode] = frozenset(
    {
        GateReasonCode.EXPIRING_7D,
        GateReasonCode.HOOK_NOT_AVAILABLE,
        GateReasonCode.LANGUAGE_MISMATCH,
    }
)


class GateSubjectKind(StrEnum):
    person = "person"
    vehicle = "vehicle"
    wap = "wap"
    unknown = "unknown"


class PairingWaitingFor(StrEnum):
    escort = "escort"
    driver = "driver"
    escort_vehicle = "escort_vehicle"


class PairingState(StrEnum):
    waiting = "waiting"
    completed = "completed"
    timed_out = "timed_out"
    cancelled = "cancelled"


class GateCallerKind(StrEnum):
    user = "user"
    device = "device"


# ---------------------------------------------------------------------------------------------
# KPIs (§6.8)
# ---------------------------------------------------------------------------------------------


class ExpiringCredentialKind(StrEnum):
    """K-51 kinds."""

    induction = "induction"
    airport_pass = "airport_pass"
    adp = "adp"
    avp = "avp"
    worker_id = "worker_id"
    vehicle_document = "vehicle_document"
    bg_recheck = "bg_recheck"
    obstacle_clearance = "obstacle_clearance"


class AccessKpiGroupBy(StrEnum):
    """T14 group_by (1-dashboard v1.1 §5.9)."""

    kind = "kind"
    reason_code = "reason_code"
    contractor = "contractor"
    zone = "zone"
    gate = "gate"
    month = "month"
