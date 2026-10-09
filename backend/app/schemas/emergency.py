"""Phase 6c schemas — emergency preparedness & drills (spec 6c-emergency-drills v1.0).

Minutes are decimal strings with 1 dp ("8.7"). Muster roll entries (names, worker numbers) are
returned only to callers allowed by P6c-4; events never carry casualty names (P6c-3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.emergency_enums import (
    ActiveStatus,
    Agency,
    AnnouncementRequirement,
    ApKind,
    AssetAction,
    AssetStatus,
    AssetType,
    CheckAnswer,
    CheckItem,
    CheckMethod,
    CheckOutcome,
    CheckResult,
    CoverageState,
    Criterion,
    DrillAction,
    DrillResult,
    DrillShift,
    DrillStatus,
    DrillType,
    EmergencyActionKind,
    EmergencyKpiGroupBy,
    EmergencyRole,
    EntryMethod,
    EntryState,
    ErpAction,
    ErpStatus,
    EventAction,
    EventStatus,
    EventType,
    ExpiryItem,
    FindingCategory,
    FindingSeverity,
    LineSource,
    LineStatus,
    MusterMode,
    MusterSource,
    MusterStatus,
    NotReadyReason,
    ProgrammeScope,
    RecordStatus,
    ResolutionReason,
    ResponseType,
    RosterShift,
    ScenarioType,
    ShiftRequirement,
    TeamReason,
    TeamType,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.kpi import KpiContext, KpiValue

# ---- reference (§3.14) ---------------------------------------------------------------------------


class EmRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    critical: bool | None = Field(default=None, description="ES ★ mandatory; EC / DC ★ critical.")
    value: str | None = Field(
        default=None,
        description="DT: minimum frequency in months; EAT: check interval days; AG: default "
        "number.",
    )
    applies_to: list[str] | None = Field(
        default=None, description="EC: asset types answering the item; DC: drill types."
    )


class EmergencyReference(ApiModel):
    """GET /emergency-reference: lists ES, DT, AG, EOR, EAT, EC, DC, FC, MS, UR with EN/AR."""

    scenarios: list[EmRefItem]
    event_types: list[EmRefItem]
    drill_types: list[EmRefItem]
    agencies: list[EmRefItem]
    roles: list[EmRefItem]
    asset_types: list[EmRefItem]
    check_items: list[EmRefItem]
    criteria: list[EmRefItem]
    finding_categories: list[EmRefItem]
    entry_states: list[EmRefItem]
    resolution_reasons: list[EmRefItem]
    response_types: list[EmRefItem]


# ---- settings (§3.15) ----------------------------------------------------------------------------


class ShiftStarts(ApiModel):
    day: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["06:00"])
    night: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["18:00"])


class RescueByType(ApiModel):
    confined_space: int
    height: int


class EmergencySettingsRead(ApiModel):
    project_id: uuid.UUID
    emergency_register_from: date | None
    emergency_ptw_enforcement_from: date | None
    erp_review_months: int
    erp_client_acceptance_required: bool
    first_aider_ratio: int
    warden_ratio: int
    coordinator_required_per_shift: bool
    shift_start_times: ShiftStarts
    coverage_check_offset_minutes: int
    drill_minimums: dict[str, int]
    first_drill_grace_days: int
    repeat_drill_days: int
    evacuation_target_minutes: int
    headcount_target_minutes: int
    response_target_minutes: int
    rescue_target_minutes: RescueByType
    drill_evaluation_days: int
    event_review_days: int
    muster_roll_window_hours: int
    asset_check_intervals: dict[str, int]
    min_extinguishers_per_zone: int
    min_first_aid_kits_per_zone: int
    min_aed_per_site: int
    rescue_team_min_members: RescueByType
    drill_compliance_warning_pct: str
    coverage_warning_pct: str
    equipment_readiness_warning_pct: str
    muster_detail_retention_months: int
    emergency_record_retention_years: int
    gate_presence_excluded_site_ids: list[uuid.UUID] = Field(
        description="Sites treated as without gates for presence (EO-4) and muster mode (MU-1) "
        "although they have an active gate (DECISIONS: incomplete gate log)."
    )


class EmergencySettingsUpdate(PatchInput):
    """Capability 180 (HSE Manager). Loosening values → 422 SETTING_LOOSENING (ER-9)."""

    emergency_register_from: date | None = None
    emergency_ptw_enforcement_from: date | None = None
    erp_review_months: int | None = Field(default=None, ge=3, le=12)
    erp_client_acceptance_required: bool | None = None
    first_aider_ratio: int | None = Field(default=None, ge=10, le=50)
    warden_ratio: int | None = Field(default=None, ge=10, le=50)
    coordinator_required_per_shift: bool | None = None
    shift_start_times: ShiftStarts | None = None
    coverage_check_offset_minutes: int | None = Field(default=None, ge=30, le=120)
    drill_minimums: dict[DrillType, int] | None = None
    first_drill_grace_days: int | None = Field(default=None, ge=0, le=60)
    repeat_drill_days: int | None = Field(default=None, ge=7, le=30)
    evacuation_target_minutes: int | None = Field(default=None, ge=3, le=15)
    headcount_target_minutes: int | None = Field(default=None, ge=5, le=30)
    response_target_minutes: int | None = Field(default=None, ge=2, le=4)
    rescue_target_minutes: RescueByType | None = None
    drill_evaluation_days: int | None = Field(default=None, ge=1, le=7)
    event_review_days: int | None = Field(default=None, ge=1, le=14)
    muster_roll_window_hours: int | None = Field(default=None, ge=12, le=24)
    asset_check_intervals: dict[AssetType, int] | None = None
    min_extinguishers_per_zone: int | None = Field(default=None, ge=1, le=20)
    min_first_aid_kits_per_zone: int | None = Field(default=None, ge=1, le=10)
    min_aed_per_site: int | None = Field(default=None, ge=0, le=10)
    rescue_team_min_members: RescueByType | None = None
    drill_compliance_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    coverage_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    equipment_readiness_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    muster_detail_retention_months: int | None = Field(default=None, ge=3, le=24)
    emergency_record_retention_years: int | None = Field(default=None, ge=2, le=10)
    gate_presence_excluded_site_ids: list[uuid.UUID] | None = None


# ---- ERP (§3.1, §3.2) ----------------------------------------------------------------------------


class Scenario(StrictInput):
    scenario_code: str = Field(min_length=1, max_length=16, examples=["SC-FIRE"])
    scenario_type: ScenarioType
    site_ids: list[uuid.UUID] = Field(min_length=1)
    alarm_signal_en: str = Field(min_length=1, max_length=150)
    alarm_signal_ar: str = Field(min_length=1, max_length=150)
    response_type: ResponseType
    response_summary_en: str | None = Field(default=None, max_length=2000)
    response_summary_ar: str | None = Field(default=None, max_length=2000)
    agencies: list[Agency] = Field(min_length=1)
    drill_type: DrillType
    drill_frequency_months: int = Field(ge=1, le=24)
    rescue_plan_refs: list[str] = Field(default_factory=list)
    no_such_work: bool = Field(
        default=False,
        description="ER-4: the response summary states the project has no such work.",
    )


class ErpCreate(StrictInput):
    """New Draft revision (179). Without a body field the current revision is copied."""

    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    document_ref: str | None = Field(default=None, max_length=40)


class ErpUpdate(PatchInput):
    """Draft only (179)."""

    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    document_ref: str | None = Field(default=None, max_length=40)
    document_attachment_id: uuid.UUID | None = None
    site_ids: list[uuid.UUID] | None = None
    scenarios: list[Scenario] | None = None
    client_acceptance_ref: str | None = Field(default=None, max_length=40)
    accepted_on: date | None = None
    airport_interface_ref: str | None = Field(default=None, max_length=40)


class ErpTransition(StrictInput):
    """submit (179) · return (180, reason ≥ 20) · approve (180, ER-3, approver ≠ preparer)."""

    action: ErpAction
    reason: str | None = Field(default=None, max_length=500)


class ScenarioRead(ApiModel):
    scenario_code: str
    scenario_type: ScenarioType
    site_ids: list[uuid.UUID]
    alarm_signal_en: str
    alarm_signal_ar: str
    response_type: ResponseType
    response_summary_en: str | None
    response_summary_ar: str | None
    agencies: list[Agency]
    drill_type: DrillType
    drill_frequency_months: int
    rescue_plan_refs: list[str]
    no_such_work: bool


class ReviewTrigger(ApiModel):
    kind: str
    ref: str | None
    at: datetime


class ErpRead(ApiModel):
    id: uuid.UUID
    erp_no: str
    project_id: uuid.UUID
    revision: int
    title_en: str
    title_ar: str
    document_ref: str
    document_attachment_id: uuid.UUID | None
    site_ids: list[uuid.UUID]
    scenarios: list[ScenarioRead]
    client_acceptance_ref: str | None
    accepted_on: date | None
    airport_interface_ref: str | None
    prepared_by: UserRef | None
    approved_by: UserRef | None
    approved_at: datetime | None
    review_due_on: date | None
    overdue: bool = Field(description="ER-7: still the plan in force when overdue.")
    in_force: bool
    review_required: bool
    review_triggers: list[ReviewTrigger]
    status: ErpStatus
    status_reason: str | None


class ErpPage(Page[ErpRead]):
    pass


# ---- assembly points, contacts, zone profiles (§3.3–§3.5) ----------------------------------------


class ApCreate(StrictInput):
    ap_code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Z0-9-]+$")
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    location_en: str = Field(min_length=1, max_length=200)
    location_ar: str = Field(min_length=1, max_length=200)
    gps_lat: Decimal | None = Field(default=None, ge=16, le=33)
    gps_lng: Decimal | None = Field(default=None, ge=34, le=56)
    capacity_persons: int = Field(ge=10, le=10000)
    zones_served: list[uuid.UUID] = Field(min_length=1)
    kind: ApKind


class ApUpdate(PatchInput):
    location_en: str | None = Field(default=None, max_length=200)
    location_ar: str | None = Field(default=None, max_length=200)
    capacity_persons: int | None = Field(default=None, ge=10, le=10000)
    zones_served: list[uuid.UUID] | None = None
    kind: ApKind | None = None
    status: ActiveStatus | None = Field(
        default=None, description="Inactive refused for the last AP of an active zone."
    )


class ApRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    ap_code: str
    site_id: uuid.UUID
    site_code: str
    zone_id: uuid.UUID | None
    zone_code: str | None
    location_en: str
    location_ar: str
    gps_lat: Decimal | None
    gps_lng: Decimal | None
    capacity_persons: int
    zones_served: list[uuid.UUID]
    zones_served_codes: list[str]
    kind: ApKind
    sticker_payload: str | None = Field(description="HSE2:MP:… (no personal data).")
    status: ActiveStatus


class ApPage(Page[ApRead]):
    pass


class ContactCreate(StrictInput):
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    agency: Agency
    display_name_en: str = Field(min_length=1, max_length=150)
    display_name_ar: str = Field(min_length=1, max_length=150)
    phone: str = Field(pattern=r"^(\+[1-9]\d{6,14}|\d{3,4})$", examples=["997"])
    person_name: str | None = Field(default=None, max_length=120)
    available_24h: bool = True
    priority: int = Field(default=1, ge=1, le=9)


class ContactUpdate(PatchInput):
    site_ids: list[uuid.UUID] | None = None
    display_name_en: str | None = Field(default=None, max_length=150)
    display_name_ar: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=r"^(\+[1-9]\d{6,14}|\d{3,4})$")
    person_name: str | None = Field(default=None, max_length=120)
    available_24h: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=9)
    active: bool | None = None


class ContactRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_ids: list[uuid.UUID]
    agency: Agency
    display_name_en: str
    display_name_ar: str
    phone: str
    person_name: str | None
    available_24h: bool
    priority: int
    active: bool


class ContactPage(Page[ContactRead]):
    pass


class ZoneProfileInput(StrictInput):
    """Values may only be raised above the project defaults (§3.5)."""

    eyewash_required: bool = False
    min_extinguishers: int | None = Field(default=None, ge=1, le=20)
    min_first_aid_kits: int | None = Field(default=None, ge=1, le=10)
    warden_required: bool = True
    notes: str | None = Field(default=None, max_length=500)


class ZoneProfileRead(ApiModel):
    zone_id: uuid.UUID
    zone_code: str
    site_id: uuid.UUID
    eyewash_required: bool
    min_extinguishers: int
    min_first_aid_kits: int
    warden_required: bool
    notes: str | None
    stored: bool = Field(description="False = project defaults (no stored profile).")


class ZoneProfileList(ApiModel):
    items: list[ZoneProfileRead]


# ---- roster and rescue teams (§3.6, §3.7) --------------------------------------------------------


class RosterCreate(StrictInput):
    """Capability 181 (C scope for Contractor HSE Reps, EO-1)."""

    role: EmergencyRole
    deployment_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = Field(default=None, description="emergency_coordinator only.")
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    shift: RosterShift
    valid_from: date
    valid_to: date | None = None


class RosterEnd(StrictInput):
    valid_to: date
    reason: str | None = Field(default=None, max_length=300)


class RosterRead(ApiModel):
    id: uuid.UUID
    assignment_no: str
    project_id: uuid.UUID
    role: EmergencyRole
    deployment_id: uuid.UUID | None
    worker: WorkerRef | None
    user: UserRef | None
    engagement_code: str | None
    site_id: uuid.UUID
    site_code: str
    zone_ids: list[uuid.UUID]
    zone_codes: list[str]
    shift: RosterShift
    valid_from: date
    valid_to: date | None
    active: bool
    qualified_today: bool | None = Field(description="EO-3 (null for roles without a code).")
    qualification_code: str | None
    qualification_reason: str | None


class RosterPage(Page[RosterRead]):
    pass


class RosterCreated(ApiModel):
    assignment: RosterRead
    matrix_role_added: bool = Field(description="EO-2: Phase 5 matrix role added.")


class TeamCreate(StrictInput):
    team_code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Z0-9-]+$")
    team_type: TeamType
    site_ids: list[uuid.UUID] = Field(min_length=1)
    lead_deployment_id: uuid.UUID
    member_deployment_ids: list[uuid.UUID] = Field(default_factory=list)
    equipment_item_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Phase 4 tripod_winch items."
    )
    asset_ids: list[uuid.UUID] = Field(default_factory=list, description="6c rescue kits.")


class TeamUpdate(PatchInput):
    site_ids: list[uuid.UUID] | None = None
    lead_deployment_id: uuid.UUID | None = None
    member_deployment_ids: list[uuid.UUID] | None = None
    equipment_item_ids: list[uuid.UUID] | None = None
    asset_ids: list[uuid.UUID] | None = None
    status: ActiveStatus | None = None


class TeamMember(ApiModel):
    deployment_id: uuid.UUID
    worker: WorkerRef | None
    lead: bool
    qualified: bool
    first_aider: bool


class TeamReadiness(ApiModel):
    current: bool
    reasons: list[TeamReason]
    last_drill_on: date | None
    current_until: date | None


class TeamRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    team_code: str
    team_type: TeamType
    site_ids: list[uuid.UUID]
    members: list[TeamMember]
    equipment_item_ids: list[uuid.UUID]
    equipment_nos: list[str]
    asset_ids: list[uuid.UUID]
    asset_tags: list[str]
    status: ActiveStatus
    readiness: TeamReadiness


class TeamPage(Page[TeamRead]):
    pass


# ---- coverage (§6.2) -----------------------------------------------------------------------------


class CoverageRow(ApiModel):
    site_id: uuid.UUID
    site_code: str
    day: date
    shift: DrillShift
    headcount: int
    zones_with_work: list[str]
    state: CoverageState
    first_aiders_required: int
    first_aiders_counted: int
    wardens_required: int
    wardens_counted: int
    zones_without_warden: list[str]
    coordinator_ok: bool
    reasons: list[str] = Field(description="first_aider · fire_warden · zone · coordinator")
    rostered_not_qualified: list[str] = Field(
        default_factory=list, description="Worker numbers (P6c-2: visible to 178)."
    )


class CoverageList(ApiModel):
    project_id: uuid.UUID
    date_from: date
    date_to: date
    rows: list[CoverageRow]


# ---- assets and checks (§3.8, §3.9) --------------------------------------------------------------


class ExpiryInput(StrictInput):
    item: ExpiryItem
    expires_on: date


class AssetCreate(StrictInput):
    asset_tag: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    asset_type: AssetType
    subtype: str | None = Field(default=None, max_length=20)
    capacity: str | None = Field(default=None, max_length=20)
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    location_en: str = Field(min_length=1, max_length=200)
    owner_engagement_id: uuid.UUID
    manufactured_year: int | None = Field(default=None, ge=1980, le=2100)
    serial_no: str | None = Field(default=None, max_length=40)
    last_service_on: date | None = None
    service_provider_tpi_id: uuid.UUID | None = None
    service_ref: str | None = Field(default=None, max_length=40)
    expiries: list[ExpiryInput] = Field(default_factory=list)


class AssetUpdate(PatchInput):
    zone_id: uuid.UUID | None = None
    location_en: str | None = Field(default=None, max_length=200)
    capacity: str | None = Field(default=None, max_length=20)
    last_service_on: date | None = None
    service_provider_tpi_id: uuid.UUID | None = None
    service_ref: str | None = Field(default=None, max_length=40)
    expiries: list[ExpiryInput] | None = None


class AssetTransition(StrictInput):
    """tag_out (183) · retire (182, terminal; sticker revoked). Reason required."""

    action: AssetAction
    reason: str = Field(min_length=5, max_length=500)


class AssetReadiness(ApiModel):
    ready: bool
    reasons: list[NotReadyReason]
    check_due_on: date | None
    service_due_on: date | None
    hydrotest_due_on: date | None


class AssetRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    asset_tag: str
    asset_type: AssetType
    subtype: str | None
    capacity: str | None
    site_id: uuid.UUID
    site_code: str
    zone_id: uuid.UUID | None
    zone_code: str | None
    location_en: str
    owner_engagement_id: uuid.UUID
    owner_code: str | None
    manufactured_year: int | None
    serial_no: str | None
    last_service_on: date | None
    service_provider_tpi_id: uuid.UUID | None
    service_ref: str | None
    expiries: list[dict[str, Any]]
    last_check_at: datetime | None
    last_check_result: CheckResult | None
    flagged_without_scan: bool
    sticker_payload: str | None
    status: AssetStatus
    status_reason: str | None
    readiness: AssetReadiness


class AssetPage(Page[AssetRead]):
    pass


class CheckAnswerInput(StrictInput):
    item: CheckItem
    answer: CheckAnswer


class CheckCreate(StrictInput):
    """Capability 183. Send `sticker_payload` (HSE2:EA:…, method qr_scan) or `asset_id` (manual).
    Backdating limited to 72 h (CHECK_BACKDATED)."""

    asset_id: uuid.UUID | None = None
    sticker_payload: str | None = Field(default=None, max_length=80)
    checked_at: datetime | None = None
    outcome: CheckOutcome
    items: list[CheckAnswerInput] = Field(default_factory=list)
    fixed_on_spot: bool = False
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=3)


class CheckRead(ApiModel):
    id: uuid.UUID
    check_no: str
    asset_id: uuid.UUID
    asset_tag: str
    checked_at: datetime
    checked_by: UserRef | None
    method: CheckMethod
    outcome: CheckOutcome
    items: list[dict[str, Any]]
    fixed_on_spot: bool
    result: CheckResult
    ca_ref: str | None
    status: RecordStatus
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class CheckPage(Page[CheckRead]):
    pass


class VoidInput(StrictInput):
    reason: str = Field(min_length=20, max_length=500)


# ---- programme (§3.10) ---------------------------------------------------------------------------


class ProgrammeLine(ApiModel):
    line_no: str
    drill_type: DrillType
    scope: ProgrammeScope
    site_id: uuid.UUID | None
    site_code: str | None
    team_id: uuid.UUID | None
    team_code: str | None
    shift_requirement: ShiftRequirement
    announcement_requirement: AnnouncementRequirement
    frequency_months: int | None
    source: LineSource
    source_drill_no: str | None
    due_by: date | None
    last_satisfied_by: str | None
    last_satisfied_on: date | None
    status: LineStatus
    days_to_due: int | None


class Programme(ApiModel):
    project_id: uuid.UUID
    as_of: date
    lines: list[ProgrammeLine]


# ---- drills (§3.11) ------------------------------------------------------------------------------


class Timeline(StrictInput):
    alarm_at: datetime | None = None
    evacuation_complete_at: datetime | None = None
    all_clear_at: datetime | None = None
    first_responder_at: datetime | None = None
    casualty_reached_at: datetime | None = None
    casualty_recovered_at: datetime | None = None


class ExternalParticipation(StrictInput):
    agency: Agency
    ref: str | None = Field(default=None, max_length=40)
    arrived_at: datetime | None = None


class DrillCreate(StrictInput):
    """Capability 184 (DR-1)."""

    drill_type: DrillType
    scenario_code: str = Field(min_length=1, max_length=16)
    site_id: uuid.UUID | None = None
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    team_id: uuid.UUID | None = None
    planned_at: datetime
    shift: DrillShift
    announced: bool = True
    suspend_permits: bool | None = Field(
        default=None, description="Default true for evacuation and shelter types (PE-2)."
    )
    conductor_user_id: uuid.UUID
    evaluator_user_ids: list[uuid.UUID] = Field(min_length=1)
    plan_note: str | None = Field(default=None, max_length=500)
    rescue_plan_ref: str | None = Field(default=None, max_length=40)
    airport_exercise_ref: str | None = Field(default=None, max_length=40)


class DrillUpdate(PatchInput):
    """Timings and participation (185) while In Progress / Conducted (DR-5)."""

    timeline: Timeline | None = None
    external_participation: list[ExternalParticipation] | None = None
    rescue_plan_ref: str | None = Field(default=None, max_length=40)
    plan_note: str | None = Field(default=None, max_length=500)


class DrillTransition(StrictInput):
    """start (185; `alarm_at` optional, past > 15 min = late entry) · conduct (185) · cancel
    (184, reason ≥ 20) · void (190, reason ≥ 20)."""

    action: DrillAction
    alarm_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class CriterionAnswer(StrictInput):
    criterion: Criterion
    answer: CheckAnswer


class FindingInput(StrictInput):
    category: FindingCategory
    severity: FindingSeverity
    description_en: str = Field(min_length=1, max_length=1000)
    description_ar: str | None = Field(default=None, max_length=1000)
    engagement_id: uuid.UUID | None = None
    create_ca: bool = Field(default=False, description="Minor findings only (DR-6).")


class EvaluationInput(StrictInput):
    """Capability 186 (an evaluator of the drill), within drill_evaluation_days (DR-6)."""

    criteria: list[CriterionAnswer]
    findings: list[FindingInput] = Field(default_factory=list)
    summary_en: str | None = Field(default=None, max_length=2000)
    summary_ar: str | None = Field(default=None, max_length=2000)


class DrillMeasures(ApiModel):
    evac_min: str | None
    headcount_min: str | None
    response_min: str | None
    rescue_min: str | None


class DrillRead(ApiModel):
    id: uuid.UUID
    drill_no: str
    project_id: uuid.UUID
    drill_type: DrillType
    scenario_code: str
    site_id: uuid.UUID | None
    site_code: str | None
    zone_ids: list[uuid.UUID]
    team_id: uuid.UUID | None
    team_code: str | None
    planned_at: datetime
    shift: DrillShift
    announced: bool
    suspend_permits: bool
    conductor: UserRef | None
    evaluators: list[UserRef]
    plan_note: str | None
    rescue_plan_ref: str | None
    timeline: dict[str, Any]
    targets: dict[str, Any]
    measures: DrillMeasures
    muster_id: uuid.UUID | None
    muster_no: str | None
    external_participation: list[dict[str, Any]]
    airport_exercise_ref: str | None
    evaluation: dict[str, Any] | None
    result: DrillResult | None
    late_entry: bool
    status: DrillStatus
    status_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class DrillPage(Page[DrillRead]):
    pass


# ---- musters (§3.12) -----------------------------------------------------------------------------


class CountRowInput(StrictInput):
    engagement_id: uuid.UUID
    expected: int = Field(ge=0, le=20000)
    accounted: int = Field(ge=0, le=20000)


class CountResolutionInput(StrictInput):
    engagement_id: uuid.UUID
    reason: ResolutionReason
    count: int = Field(ge=1, le=20000)
    note: str | None = Field(default=None, max_length=500)


class CountsInput(StrictInput):
    """Count mode (MU-3): rows set expected / accounted; resolutions add counts with a reason."""

    rows: list[CountRowInput] = Field(default_factory=list)
    resolutions: list[CountResolutionInput] = Field(default_factory=list)
    visitors_expected: int | None = Field(default=None, ge=0)
    visitors_accounted: int | None = Field(default=None, ge=0)


class ScanInput(StrictInput):
    """MU-4: the worker's access card QR (HSE2:AC:…) at an assembly point."""

    payload: str = Field(min_length=10, max_length=80)
    ap_id: uuid.UUID | None = None


class ResolveInput(StrictInput):
    reason: ResolutionReason
    note: str | None = Field(default=None, max_length=500)


class MusterEntryRead(ApiModel):
    id: uuid.UUID
    deployment_id: uuid.UUID
    worker: WorkerRef | None
    engagement_code: str | None
    state: EntryState
    at: datetime | None
    method: EntryMethod | None
    ap_id: uuid.UUID | None
    resolution_reason: ResolutionReason | None
    note: str | None
    extra: bool


class MusterCountRow(ApiModel):
    engagement_id: uuid.UUID
    engagement_code: str | None
    expected: int
    accounted: int
    resolved: list[dict[str, Any]]
    outstanding: int


class MusterRead(ApiModel):
    id: uuid.UUID
    muster_no: str
    project_id: uuid.UUID
    source_type: MusterSource
    source_id: uuid.UUID
    site_id: uuid.UUID
    ap_ids: list[uuid.UUID]
    mode: MusterMode
    opened_at: datetime
    expected: int
    accounted: int
    resolved: int
    unaccounted: int
    extras: int
    by_state: dict[str, int]
    by_reason: dict[str, int]
    visitors_expected: int | None
    visitors_accounted: int | None
    headcount_complete_at: datetime | None
    headcount_min: str | None
    status: MusterStatus
    entries: list[MusterEntryRead] | None = Field(
        description="Named roll (P6c-4); null when the caller may not see names."
    )
    count_rows: list[MusterCountRow]


class MusterDeviceCreate(StrictInput):
    ap_id: uuid.UUID
    device_id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)


class MusterDeviceRead(ApiModel):
    id: uuid.UUID
    ap_id: uuid.UUID
    device_id: str
    label: str
    registered_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class MusterDeviceRegistered(ApiModel):
    device: MusterDeviceRead
    device_token: str = Field(description="Shown once.")


class MusterSessionInput(StrictInput):
    device_token: str = Field(min_length=20, max_length=200)


class MusterSessionRead(ApiModel):
    access_token: str
    ap_id: uuid.UUID
    ap_code: str


class MusterSheet(ApiModel):
    """MU-9 printable sheet: per engagement, names and worker_no only (audited `export`)."""

    muster_no: str
    generated_at: datetime
    engagements: list[dict[str, Any]]


# ---- events (§3.13) ------------------------------------------------------------------------------


class ExternalService(StrictInput):
    agency: Agency
    called_at: datetime | None = None
    arrived_at: datetime | None = None
    reference: str | None = Field(default=None, max_length=40)


class EventCreate(StrictInput):
    """Capability 187; raised_at back-dated up to 24 h (late entry)."""

    event_type: EventType
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1)
    location_en: str | None = Field(default=None, max_length=200)
    raised_at: datetime | None = None
    response_type: ResponseType
    casualties_count: int = Field(default=0, ge=0, le=500)
    incident_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class EventUpdate(PatchInput):
    first_responder_at: datetime | None = None
    external_services: list[ExternalService] | None = None
    casualties_count: int | None = Field(default=None, ge=0, le=500)
    incident_id: uuid.UUID | None = None
    location_en: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class EventTransition(StrictInput):
    """all_clear (188) · void (190, reason ≥ 20)."""

    action: EventAction
    at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class EventReviewInput(StrictInput):
    """Capability 188 (not site engineers), within event_review_days (EV-5)."""

    what_worked: str = Field(min_length=1, max_length=2000)
    issues: str = Field(min_length=1, max_length=2000)
    erp_update_needed: bool = False
    create_ca: bool = False
    ca_title: str | None = Field(default=None, max_length=150)


class EventTimes(ApiModel):
    first_response_min: str | None
    total_min: str | None
    external_arrival_min: dict[str, str | None]


class EventRead(ApiModel):
    id: uuid.UUID
    event_no: str
    project_id: uuid.UUID
    event_type: EventType
    site_id: uuid.UUID
    site_code: str
    zone_ids: list[uuid.UUID]
    zone_codes: list[str]
    location_en: str | None
    raised_at: datetime
    declared_by: UserRef | None
    response_type: ResponseType
    muster_id: uuid.UUID | None
    muster_no: str | None
    first_responder_at: datetime | None
    external_services: list[dict[str, Any]]
    casualties_count: int
    incident_id: uuid.UUID | None
    incident_ref: str | None
    ops_event_id: uuid.UUID | None
    all_clear_at: datetime | None
    all_clear_by: UserRef | None
    review: dict[str, Any] | None
    times: EventTimes
    late_entry: bool
    status: EventStatus
    status_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class EventPage(Page[EventRead]):
    pass


# ---- board, action panel, KPIs (§8) --------------------------------------------------------------


class BoardSite(ApiModel):
    site_id: uuid.UUID
    site_code: str
    shift: DrillShift
    coverage: CoverageRow | None
    provision_gaps: list[str]
    next_drills_due: list[ProgrammeLine]


class EmergencyBoard(ApiModel):
    project_id: uuid.UUID
    at: datetime
    erp: ErpRead | None
    active_events: list[EventRead]
    open_musters: list[MusterRead]
    sites: list[BoardSite]


class EmergencyActionItem(ApiModel):
    kind: EmergencyActionKind
    count: int
    refs: list[str]
    label_en: str
    label_ar: str


class EmergencyActionPanel(ApiModel):
    project_id: uuid.UUID
    at: datetime
    items: list[EmergencyActionItem]


class EmergencyBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class EmergencyBreakdown(ApiModel):
    metric: str
    group_by: EmergencyKpiGroupBy
    rows: list[EmergencyBreakdownRow]


class EmergencyKpiResponse(ApiModel):
    """GET /kpi/emergency: K-104…K-109 (aggregates only, EM-2). Components: K-105 median
    minutes; K-106 shortfalls by reason; K-107 not-ready reasons; K-109 by type and medians."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[EmergencyBreakdown]


class EmergencyInfo(ApiModel):
    """PE-6 pre-fill for a permit's emergency_info."""

    text: str
    assembly_point_code: str | None
    numbers: list[str]
