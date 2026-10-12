"""Option 7b Site Vehicle & Plant Readiness — **Prototype** (spec 7b-fleet-driver v2.0 §3, §5, §8).
Every schema carries the `SiteVeh` prefix so no OpenAPI component of an earlier module changes
name (DECISIONS D-202). Personal columns (driver identity, licence, hook results) follow P7b-1:
Site engineers get authorisation status only (`redacted` = true); the Viewer / Client gets
aggregates only (summary and KPIs; registers 403)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.access_enums import (
    HookKind,
    HookProviderStatus,
    LicenceClass,
    LicenceIssuer,
    PlateType,
    VehicleCategory,
    VehicleOwnerType,
    VehicleStatus,
)
from app.core.cert_enums import ServiceStatus
from app.core.field_enums import FindingSeverity
from app.core.hse_enums import Weekday
from app.core.site_vehicle_enums import (
    SiteVehAuthStatus,
    SiteVehCheckSource,
    SiteVehDriverGroup,
    SiteVehHookResult,
    SiteVehJourneyStatus,
    SiteVehKpiGroupBy,
    SiteVehLimitingFactor,
    SiteVehPolicy,
    SiteVehReadiness,
    SiteVehScope,
    SiteVehUseClass,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.field import AnswerInput, PhotoInput, TemplateRead
from app.schemas.hse_common import ApiWarning, EngagementRef, UserRef
from app.schemas.kpi import KpiContext, KpiValue

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
PROTOTYPE = "Prototype (نموذج أولي): every 7b page carries the badge."

# ---- settings (§3.5) -----------------------------------------------------------------------------


class SiteVehSettingsRead(ApiModel):
    """§3.5. `live` = site_vehicles_from is set (null = 7b off: other 7b endpoints answer 422
    SITE_VEHICLES_NOT_LIVE)."""

    project_id: uuid.UUID
    live: bool
    site_vehicles_from: date | None
    driver_auth_validity_months: int = Field(description="12–36 (default 24 ASSUMPTION).")
    defensive_driving_code: str = Field(examples=["DEF-DRV"])
    bus_driving_code: str = Field(examples=["BUS-DRV"])
    driver_hook_policy: SiteVehPolicy
    driver_auth_policy: SiteVehPolicy
    pre_use_required_groups: list[SiteVehDriverGroup]
    rest_weekday: Weekday
    journey_hint_km: int = Field(description="50–500 (prototype default 150).")
    journey_hint_night_from: str = Field(examples=["22:00"])
    journey_hint_night_to: str = Field(examples=["05:00"])
    updated_at: datetime | None
    updated_by: UserRef | None


class SiteVehSettingsUpdate(PatchInput):
    """Capability 237 (HSE Manager); out of range → 422 SETTING_OUT_OF_RANGE. Course codes must
    exist in the Phase 5 catalogue (DEF-DRV / BUS-DRV are created when 7b is first switched on)."""

    site_vehicles_from: date | None = Field(default=None, description="≤ today + 30; null = off.")
    driver_auth_validity_months: int | None = None
    defensive_driving_code: str | None = Field(default=None, max_length=20)
    bus_driving_code: str | None = Field(default=None, max_length=20)
    driver_hook_policy: SiteVehPolicy | None = None
    driver_auth_policy: SiteVehPolicy | None = None
    pre_use_required_groups: list[SiteVehDriverGroup] | None = None
    rest_weekday: Weekday | None = None
    journey_hint_km: int | None = None
    journey_hint_night_from: str | None = Field(default=None, pattern=HHMM)
    journey_hint_night_to: str | None = Field(default=None, pattern=HHMM)

    non_nullable = frozenset(
        {
            "driver_auth_validity_months",
            "defensive_driving_code",
            "bus_driving_code",
            "driver_hook_policy",
            "driver_auth_policy",
            "pre_use_required_groups",
            "rest_weekday",
            "journey_hint_km",
            "journey_hint_night_from",
            "journey_hint_night_to",
        }
    )


# ---- reference lists (§3.6) ----------------------------------------------------------------------


class SiteVehLabel(ApiModel):
    code: str
    label_en: str
    label_ar: str


class SiteVehUseClassRead(SiteVehLabel):
    driver_group: SiteVehDriverGroup
    seats_required: bool = Field(description="crew_bus, crew_pickup: seats 2–60.")
    operating_card_required: bool = Field(
        description="crew_bus, tipper, goods_heavy when plated (R2 VERIFY)."
    )


class SiteVehReference(ApiModel):
    """Lists SU and DG plus the EN/AR labels of every 7b state and code."""

    use_classes: list[SiteVehUseClassRead]
    driver_groups: list[SiteVehLabel]
    readiness: list[SiteVehLabel]
    authorisation_statuses: list[SiteVehLabel]
    journey_statuses: list[SiteVehLabel]
    limiting_factors: list[SiteVehLabel]
    warnings: list[SiteVehLabel]
    prototype_badge: SiteVehLabel


# ---- site vehicles (§3.1, SV) --------------------------------------------------------------------


class SiteVehDocRead(ApiModel):
    kind: str = Field(description="istimara · insurance · mvpi · operating_card")
    expiry: date
    days_left: int
    state: str = Field(description="valid · expiring (≤ 30 days) · expired")


class SiteVehPhase4Read(ApiModel):
    """SV-3: the Phase 4 equipment item linked to this vehicle (read-only in 7b)."""

    equipment_id: uuid.UUID
    equipment_no: str = Field(examples=["EQP-000214"])
    service_status: ServiceStatus
    operator_code: str | None = Field(description="EQC operator certificate code (DA-2).")


class SiteVehHoldRead(ApiModel):
    check_id: uuid.UUID
    check_no: str
    set_on: date
    failed_items: list[str]
    ca_id: uuid.UUID | None
    ca_ref: str | None


class SiteVehTodayCheck(ApiModel):
    check_id: uuid.UUID
    check_no: str
    passed: bool


class SiteVehRead(Timestamps):
    id: uuid.UUID
    vehicle_no: str = Field(examples=["VEH-0107"])
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
    site_scope: SiteVehScope
    use_class: SiteVehUseClass | None
    driver_group: SiteVehDriverGroup | None
    seats: int | None
    operating_card_no: str | None
    operating_card_expiry: date | None
    istimara_expiry: date | None
    insurance_policy_no: str
    insurance_expiry: date
    mvpi_expiry: date | None
    documents: list[SiteVehDocRead]
    docs_verified: bool
    docs_verified_by: UserRef | None
    docs_verified_at: datetime | None
    idle_from: date | None
    idle_to: date | None
    status: VehicleStatus
    withdrawn_on: date | None
    readiness: SiteVehReadiness = Field(description="§4.1 today (derived; first match wins).")
    readiness_reasons: list[str] = Field(
        description="e.g. insurance:2026-10-19, defect_hold:VPC-…, phase4:out_of_service."
    )
    phase4: SiteVehPhase4Read | None
    hold: SiteVehHoldRead | None
    today_check: SiteVehTodayCheck | None
    pre_use_required_today: bool
    warnings: list[ApiWarning] = Field(
        default_factory=list, description="VEHICLE_DOCS_UNVERIFIED (readiness unchanged, SV-4)."
    )


class SiteVehPage(Page[SiteVehRead]):
    pass


class SiteVehCreate(StrictInput):
    """Capability 234 (reps: own engagement). Creates the Phase 2 vehicle (VEH-nnnn) with the
    7b fields; Phase 2 plate / VIN / document rules apply (Istimara and MVPI required when
    plated). 422 OPERATING_CARD_REQUIRED for crew_bus / tipper / goods_heavy with a plate."""

    engagement_id: uuid.UUID
    owner_type: VehicleOwnerType
    category: VehicleCategory
    plate_type: PlateType
    plate_letters_ar: str | None = Field(default=None, max_length=5)
    plate_letters_en: str | None = Field(default=None, max_length=3)
    plate_digits: str | None = Field(default=None, pattern=r"^\d{1,4}$")
    fleet_no: str = Field(min_length=1, max_length=20)
    serial_or_vin: str = Field(min_length=1, max_length=30)
    make_model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1990)
    colour: str = Field(default="White", min_length=1, max_length=30)
    travel_height_m: Decimal | None = Field(default=None, description="Default 2.00 m.")
    max_working_height_m_agl: Decimal | None = Field(default=None, description="Default travel.")
    istimara_expiry: date | None = None
    insurance_policy_no: str = Field(min_length=1, max_length=40)
    insurance_expiry: date
    mvpi_expiry: date | None = None
    site_scope: SiteVehScope = Field(description="site or both (airside_only is Phase 2 only).")
    use_class: SiteVehUseClass
    seats: int | None = Field(default=None, description="crew_bus / crew_pickup: 2–60.")
    operating_card_no: str | None = Field(default=None, max_length=30)
    operating_card_expiry: date | None = None
    idle_from: date | None = None
    idle_to: date | None = None


class SiteVehUpdate(PatchInput):
    """Capability 234. Also enrols an existing Phase 2 (airside_only) vehicle by setting
    site_scope = site / both with a use_class (SV-1). Changing a document date clears the
    document verification (SV-4)."""

    site_scope: SiteVehScope | None = None
    use_class: SiteVehUseClass | None = None
    seats: int | None = None
    operating_card_no: str | None = Field(default=None, max_length=30)
    operating_card_expiry: date | None = None
    istimara_expiry: date | None = None
    insurance_policy_no: str | None = Field(default=None, min_length=1, max_length=40)
    insurance_expiry: date | None = None
    mvpi_expiry: date | None = None
    idle_from: date | None = None
    idle_to: date | None = None
    fleet_no: str | None = Field(default=None, min_length=1, max_length=20)
    make_model: str | None = Field(default=None, min_length=1, max_length=80)

    non_nullable = frozenset(
        {"site_scope", "insurance_policy_no", "insurance_expiry", "fleet_no", "make_model"}
    )


class SiteVehClearHold(StrictInput):
    """PU-3 / §4.1: needs a passing check completed after the hold (else 409
    VEHICLE_DEFECT_HOLD)."""

    repair_note: str = Field(min_length=10, max_length=1000)


class SiteVehWithdraw(StrictInput):
    reason: str = Field(min_length=10, max_length=500)
    withdrawn_on: date | None = Field(default=None, description="Default today.")


class SiteVehSummary(ApiModel):
    """Aggregates (Viewer / Client allowed): counts only, no plates or names."""

    project_id: uuid.UUID
    as_of: date
    live: bool
    site_vehicles: int
    by_readiness: dict[str, int]
    docs_expired: int
    docs_expiring_30d: int
    docs_unverified: int
    pre_use_required_today: int
    pre_use_done_today: int
    active_authorisations: int
    authorisations_expiring_30d: int
    journeys_planned: int
    journeys_overdue: int


# ---- driver / operator authorisations (§3.2, DA) ----


class SiteVehHookResultRead(ApiModel):
    kind: HookKind
    code: str = Field(examples=["DEF-DRV", "DRIVER-FIT", "PLANT-OPERATOR"])
    result: SiteVehHookResult
    provider_status: HookProviderStatus
    valid_until: date | None
    ref: str | None
    reason_code: str | None
    vehicle_id: uuid.UUID | None = Field(
        default=None, description="The plant whose Phase 4 EQC gave the operator code."
    )


class SiteVehAuthFields(StrictInput):
    groups: list[SiteVehDriverGroup] = Field(min_length=1)
    licence_issuer: LicenceIssuer | None = None
    licence_class: LicenceClass | None = Field(
        default=None, description="Must cover every road group (LCV; LICENCE_CLASS_NOT_COVERING)."
    )
    licence_expiry: date | None = None
    assessment_date: date = Field(description="≤ 12 months before issued_on (ASSESSMENT_TOO_OLD).")
    assessor: str = Field(min_length=2, max_length=120)
    issued_on: date
    own_valid_until: date | None = Field(
        default=None, description="Default issued_on + driver_auth_validity_months − 1 day."
    )
    plant_vehicle_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Group plant: site plant operated; a Phase 4-linked item adds its EQC "
        "operator-certificate hook (DA-2).",
    )


class SiteVehAuthCreate(SiteVehAuthFields):
    """Draft (235; a Contractor HSE Rep proposes for his engagement tree). Licence fields left
    empty are prefilled from the worker's ADP when one exists."""

    worker_id: uuid.UUID


class SiteVehAuthUpdate(PatchInput):
    """Draft only."""

    groups: list[SiteVehDriverGroup] | None = Field(default=None, min_length=1)
    licence_issuer: LicenceIssuer | None = None
    licence_class: LicenceClass | None = None
    licence_expiry: date | None = None
    assessment_date: date | None = None
    assessor: str | None = Field(default=None, min_length=2, max_length=120)
    issued_on: date | None = None
    own_valid_until: date | None = None
    plant_vehicle_ids: list[uuid.UUID] | None = None

    non_nullable = frozenset({"groups", "assessment_date", "assessor", "issued_on"})


class SiteVehAuthTransition(StrictInput):
    """§4.2: activate (draft / suspended → active; DA-1), suspend (reason ≥ 20), revoke (final).
    Capability 235 (not reps)."""

    to_status: SiteVehAuthStatus
    reason: str | None = Field(default=None, max_length=500)


class SiteVehAuthRead(Timestamps):
    id: uuid.UUID
    auth_no: str = Field(examples=["DA-ANIA-EXP-0042"])
    project_id: uuid.UUID
    worker: WorkerRef
    engagement: EngagementRef | None
    groups: list[SiteVehDriverGroup]
    status: SiteVehAuthStatus
    redacted: bool = Field(description="Site engineer: status only (P7b-1, AC 12).")
    licence_issuer: LicenceIssuer | None
    licence_class: LicenceClass | None
    licence_expiry: date | None
    licence_prefilled_from_adp: bool
    assessment_date: date | None
    assessor: str | None
    issued_on: date
    own_valid_until: date | None
    effective_valid_until: date | None
    limiting_factor: SiteVehLimitingFactor | None
    hook_results: list[SiteVehHookResultRead]
    hooks_evaluated_at: datetime | None
    plant_vehicle_ids: list[uuid.UUID]
    status_reason: str | None
    status_changed_at: datetime | None
    activated_at: datetime | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class SiteVehAuthPage(Page[SiteVehAuthRead]):
    pass


class SiteVehAuthPrefill(ApiModel):
    worker_id: uuid.UUID
    adp_no: str | None
    licence_issuer: LicenceIssuer | None
    licence_class: LicenceClass | None
    licence_expiry: date | None
    live_authorisation_no: str | None = Field(description="One live authorisation per worker.")


# ---- pre-use checks (§3.3, PU) -------------------------------------------------------------------


class SiteVehVehicleRef(ApiModel):
    id: uuid.UUID
    vehicle_no: str
    fleet_no: str
    make_model: str
    use_class: SiteVehUseClass | None
    driver_group: SiteVehDriverGroup | None


class SiteVehCheckCreate(StrictInput):
    """Capability 236. Template by driver group (VPU-L light, VPU-B bus, VPU-H heavy / plant),
    pinned at start; 6d answer rules (EXE-2). One Completed check per vehicle per date (422
    PRE_USE_CHECK_EXISTS; a re-check is allowed while the vehicle is on defect hold). PU-6
    under block → 422 DRIVER_NOT_AUTHORISED; under warn the warning is returned."""

    vehicle_id: uuid.UUID
    driver_worker_id: uuid.UUID
    check_date: date | None = Field(default=None, description="Default today (local).")
    answers: list[AnswerInput] = Field(min_length=1)
    source: SiteVehCheckSource = SiteVehCheckSource.app
    paper_photo: PhotoInput | None = Field(
        default=None, description="Required when source = paper (PU-5)."
    )
    completed_at: datetime | None = None


class SiteVehFindingRead(ApiModel):
    finding_no: str
    item_code: str | None
    severity: FindingSeverity
    critical_item: bool
    ca_id: uuid.UUID | None
    ca_ref: str | None


class SiteVehCheckRead(Timestamps):
    id: uuid.UUID
    check_no: str = Field(examples=["VPC-ANIA-EXP-20261011-0031"])
    project_id: uuid.UUID
    vehicle: SiteVehVehicleRef
    engagement: EngagementRef | None
    driver: WorkerRef
    driver_group: SiteVehDriverGroup | None
    driver_authorised: bool
    authorisation_no: str | None
    check_date: date
    template_code: str
    response_id: uuid.UUID | None
    passed: bool
    critical_fail_count: int
    failed_items: list[str]
    source: SiteVehCheckSource
    paper_photo_id: uuid.UUID | None
    recorded_by: UserRef | None
    completed_at: datetime
    findings: list[SiteVehFindingRead]
    phase4_defect_id: uuid.UUID | None
    phase4_defect_no: str | None
    hold_set: bool
    hold_cleared_at: datetime | None
    hold_repair_note: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class SiteVehCheckPage(Page[SiteVehCheckRead]):
    pass


class SiteVehCheckForm(ApiModel):
    """What the check screen needs for one vehicle: the published template and today's state."""

    vehicle: SiteVehVehicleRef
    template: TemplateRead
    check_date: date
    existing_check_no: str | None
    on_defect_hold: bool
    readiness: SiteVehReadiness


class SiteVehMissingRow(ApiModel):
    vehicle: SiteVehVehicleRef
    engagement: EngagementRef | None
    readiness: SiteVehReadiness


class SiteVehMissingByContractor(ApiModel):
    engagement: EngagementRef | None
    required: int
    completed: int
    missing: int


class SiteVehMissingRead(ApiModel):
    """PU-1 for one day: required vehicles without a Completed check, per contractor."""

    date: date
    working_day: bool
    required: int
    completed: int
    items: list[SiteVehMissingRow]
    by_contractor: list[SiteVehMissingByContractor]


# ---- journey plans (§3.4, JM — prototype) ----


class SiteVehJourneyHintInput(StrictInput):
    distance_km: int = Field(ge=1, le=1000)
    planned_depart: datetime
    planned_arrive: datetime


class SiteVehJourneyHint(ApiModel):
    """JM-1: a hint only; the platform never requires a plan."""

    recommended: bool
    reasons: list[str] = Field(description="distance · night")
    message_en: str | None
    message_ar: str | None


class SiteVehJourneyCreate(StrictInput):
    """Capability 236. JM-2: 409 VEHICLE_NOT_READY (defect_hold / not_certified / withdrawn);
    PU-6 policy; 422 PASSENGERS_EXCEED_SEATS, JOURNEY_TIMES_INVALID, JOURNEY_CONTACT_IS_DRIVER."""

    vehicle_id: uuid.UUID
    driver_worker_id: uuid.UUID
    passengers: int = Field(ge=0, le=59)
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    distance_km: int = Field(ge=1, le=1000)
    planned_depart: datetime
    planned_arrive: datetime
    contact_user_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=500)


class SiteVehJourneyArrive(StrictInput):
    arrived_at: datetime | None = Field(default=None, description="Default now.")


class SiteVehJourneyCancel(StrictInput):
    reason: str = Field(min_length=5, max_length=500)


class SiteVehJourneyRead(Timestamps):
    id: uuid.UUID
    plan_no: str = Field(examples=["JP-ANIA-EXP-2026-0118"])
    project_id: uuid.UUID
    vehicle: SiteVehVehicleRef
    engagement: EngagementRef | None
    driver: WorkerRef
    driver_group: SiteVehDriverGroup | None
    driver_authorised: bool
    passengers: int
    origin: str
    destination: str
    distance_km: int
    planned_depart: datetime
    planned_arrive: datetime
    contact: UserRef | None
    notes: str | None
    hint_recommended: bool
    status: SiteVehJourneyStatus
    overdue: bool = Field(
        description="Display flag only: Planned and now > planned_arrive + 60 min (no alert)."
    )
    arrived_at: datetime | None
    cancelled_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class SiteVehJourneyPage(Page[SiteVehJourneyRead]):
    pass


# ---- KPIs (§6.4) ---------------------------------------------------------------------------------


class SiteVehBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class SiteVehBreakdown(ApiModel):
    metric: str
    group_by: SiteVehKpiGroupBy
    rows: list[SiteVehBreakdownRow]


class SiteVehKpiResponse(ApiModel):
    """GET /kpi/site-vehicles: K-138…K-140 (aggregates only; SK-2)."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[SiteVehBreakdown]
    notes: list[str]
