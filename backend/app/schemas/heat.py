"""Phase 6b schemas — heat stress management (spec 6b-heat-stress v1.0).

Temperatures are decimal strings with 1 dp ("30.2"). Heat-illness log reads omit review texts
and worker names for callers below the needed capability (P6b-2), and post_heat_illness plans
are shown as `returner` with trigger `absence` below 6a tier 2 (P6b-3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.heat_enums import (
    AcclimatisationBasis,
    AcclimatisationStatus,
    BanExemptionReason,
    BanExemptionStatus,
    CheckAnswer,
    Cooling,
    HeatActionKind,
    HeatKpiGroupBy,
    HeatLogSource,
    HeatLogStatus,
    HeatStateKind,
    InstrumentAction,
    InstrumentKind,
    InstrumentStatus,
    PatrolOutcome,
    PlanStatus,
    PlanTriggerKind,
    PlanType,
    PointSourceKind,
    ReadingSource,
    RecordStatus,
    Regime,
    ReviewAnswer,
    ReviewQuestion,
    SeasonReportStatus,
    StationType,
    WelfareItem,
    Workload,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, UserRef
from app.schemas.kpi import KpiContext, KpiValue

Temp = Decimal

# ---- reference (§3.13) ---------------------------------------------------------------------------


class HeatRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    critical: bool | None = None
    na_allowed: bool | None = None
    value: str | None = Field(
        default=None,
        description="CL: °C added to WBGT; RGM: rest minutes per hour; WL: metabolic band.",
    )


class HeatReference(ApiModel):
    """GET /heat-reference: lists WL, CL, RGM, APT, HW, BO, HC and the station enums with
    EN/AR labels. Every regime card shows `water_advice_en` / `water_advice_ar` (R5)."""

    workloads: list[HeatRefItem]
    clothing: list[HeatRefItem]
    hood_adjustment_c: str
    regimes: list[HeatRefItem]
    plan_types: list[HeatRefItem]
    welfare_items: list[HeatRefItem]
    patrol_outcomes: list[HeatRefItem]
    review_questions: list[HeatRefItem]
    station_types: list[HeatRefItem]
    cooling: list[HeatRefItem]
    exemption_reasons: list[HeatRefItem]
    water_advice_en: str
    water_advice_ar: str


# ---- settings (§3.14) and regime table (§3.4) ----------------------------------------------------


class MmddRange(ApiModel):
    start_mmdd: str = Field(pattern=r"^\d{2}-\d{2}$", examples=["05-01"])
    end_mmdd: str = Field(pattern=r"^\d{2}-\d{2}$", examples=["09-30"])


class TimeRange(ApiModel):
    start_local: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["07:00"])
    end_local: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["18:00"])


class ReadingValidMinutes(ApiModel):
    manual: int = Field(ge=15, le=60)
    station: int = Field(ge=5, le=30)


class AcclimatisationSchedules(ApiModel):
    new_worker: list[int]
    returner: list[int]


class HeatSettingsRead(ApiModel):
    project_id: uuid.UUID
    heat_register_from: date | None
    heat_ptw_enforcement_from: date | None
    heat_controls_period: MmddRange
    heat_monitoring_hours: TimeRange
    reading_valid_minutes: ReadingValidMinutes
    regime_relax_minutes: int
    wbgt_limit_offset_c: DecimalStr
    headline_workload: Workload
    trade_workload_defaults: dict[str, Workload]
    reading_backdate_max_hours: int
    wbgt_component_tolerance_c: DecimalStr
    acclimatisation_schedules: AcclimatisationSchedules
    standard_shift_hours: DecimalStr
    deacclimatisation_days: int
    acclimatisation_restart_gap_days: int
    plan_confirmation_hours: int
    cool_water_max_c: DecimalStr
    welfare_checks_per_station_day: int
    ban_patrols_per_zone_day: int
    heat_illness_review_days: int
    heat_case_merge_hours: int
    wbgt_coverage_warning_pct: DecimalStr
    welfare_compliance_warning_pct: DecimalStr
    ban_patrol_coverage_warning_pct: DecimalStr
    heat_fitness_required: bool
    heat_photo_retention_months: int
    heat_record_retention_years: int
    midday_ban_period: MmddRange = Field(description="Read from Phase 3 (single source).")
    midday_ban_hours: TimeRange = Field(description="Read from Phase 3 (single source).")
    midday_ban_prewarn_minutes: int


class HeatSettingsUpdate(PatchInput):
    """Capability 175. Only the §3.14 'Allowed' range is accepted; tighten-only keys refuse a
    loosening (422 VALIDATION_ERROR naming the key; PERIOD_TOO_SHORT; HEAT_COVERAGE_INCOMPLETE
    when `heat_ptw_enforcement_from` is set with a required zone uncovered, HS-7)."""

    heat_register_from: date | None = None
    heat_ptw_enforcement_from: date | None = None
    heat_controls_period: MmddRange | None = None
    heat_monitoring_hours: TimeRange | None = None
    reading_valid_minutes: ReadingValidMinutes | None = None
    regime_relax_minutes: int | None = Field(default=None, ge=30, le=60)
    wbgt_limit_offset_c: Decimal | None = None
    headline_workload: Workload | None = None
    trade_workload_defaults: dict[str, Workload] | None = None
    reading_backdate_max_hours: int | None = Field(default=None, ge=0, le=24)
    wbgt_component_tolerance_c: Decimal | None = Field(default=None, ge=Decimal("0.2"), le=1)
    acclimatisation_schedules: AcclimatisationSchedules | None = None
    standard_shift_hours: Decimal | None = Field(default=None, ge=8, le=12)
    deacclimatisation_days: int | None = Field(default=None, ge=3, le=7)
    acclimatisation_restart_gap_days: int | None = Field(default=None, ge=2, le=4)
    plan_confirmation_hours: int | None = Field(default=None, ge=4, le=24)
    cool_water_max_c: Decimal | None = Field(default=None, ge=10, le=15)
    welfare_checks_per_station_day: int | None = Field(default=None, ge=1, le=4)
    ban_patrols_per_zone_day: int | None = Field(default=None, ge=1, le=4)
    heat_illness_review_days: int | None = Field(default=None, ge=1, le=7)
    heat_case_merge_hours: int | None = Field(default=None, ge=24, le=72)
    wbgt_coverage_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    welfare_compliance_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    ban_patrol_coverage_warning_pct: Decimal | None = Field(default=None, ge=80, le=100)
    heat_fitness_required: bool | None = None
    heat_photo_retention_months: int | None = Field(default=None, ge=6, le=36)
    heat_record_retention_years: int | None = Field(default=None, ge=2, le=10)


class RegimeLimitRow(ApiModel):
    basis: AcclimatisationBasis
    regime: Regime
    workload: Workload
    limit_c: DecimalStr


class RegimeTableRead(ApiModel):
    """§3.4 (org-wide). Above the R3 limit the regime is R4. The project offset
    (`wbgt_limit_offset_c`, ≤ 0) is subtracted on each project."""

    rows: list[RegimeLimitRow]


class RegimeLimitInput(StrictInput):
    basis: AcclimatisationBasis
    regime: Regime
    workload: Workload
    limit_c: Decimal = Field(ge=0, le=60)


class RegimeTableUpdate(StrictInput):
    """Capability 175; values may only be lowered (422 REGIME_LOOSENING)."""

    rows: list[RegimeLimitInput] = Field(min_length=1)


# ---- instruments, devices, points (§3.1, §3.2) ---------------------------------------------------


class InstrumentCreate(StrictInput):
    """Capability 168. Activation needs iso7243_compliant = true (INSTRUMENT_NOT_COMPLIANT) and
    calibration_valid_until > today (INSTRUMENT_CALIBRATION_EXPIRED), HS-2."""

    kind: InstrumentKind
    make_model: str = Field(min_length=1, max_length=80)
    serial_no: str = Field(min_length=1, max_length=40)
    iso7243_compliant: bool
    calibration_valid_until: date
    calibration_cert_ref: str = Field(min_length=1, max_length=40)


class InstrumentTransition(StrictInput):
    """activate (from quarantined: new calibration date and cert ref), quarantine (reason),
    retire (terminal)."""

    action: InstrumentAction
    reason: str | None = Field(default=None, max_length=300)
    calibration_valid_until: date | None = None
    calibration_cert_ref: str | None = Field(default=None, max_length=40)


class StationDeviceRead(ApiModel):
    id: uuid.UUID
    device_id: str
    label: str
    registered_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class InstrumentRead(ApiModel):
    id: uuid.UUID
    instrument_no: str
    project_id: uuid.UUID
    kind: InstrumentKind
    make_model: str
    serial_no: str
    iso7243_compliant: bool
    calibration_valid_until: date
    calibration_cert_ref: str
    status: InstrumentStatus
    status_reason: str | None
    devices: list[StationDeviceRead] = Field(default_factory=list)
    point_codes: list[str] = Field(default_factory=list)


class InstrumentPage(Page[InstrumentRead]):
    pass


class StationDeviceCreate(StrictInput):
    """2-access-permits v1.4: kind weather_station (capability 168; fixed_station only)."""

    device_id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)


class StationDeviceRegistered(ApiModel):
    device: StationDeviceRead
    device_token: str = Field(description="Shown once; rotate by revoking and registering again.")


class StationSessionInput(StrictInput):
    device_token: str = Field(min_length=10, max_length=200)


class StationSessionRead(ApiModel):
    """A weather-station session: the token may call only POST /heat/station-readings (HS-4);
    any other endpoint answers 403 GATE_DEVICE_FORBIDDEN."""

    access_token: str
    instrument_no: str
    point_code: str | None


class PointCreate(StrictInput):
    point_code: str = Field(min_length=1, max_length=16)
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1)
    source_kind: PointSourceKind
    instrument_id: uuid.UUID | None = Field(
        default=None, description="station: an active fixed_station instrument (HS-4)."
    )
    solar_load: bool = True


class PointUpdate(PatchInput):
    non_nullable = frozenset({"zone_ids", "active", "solar_load"})

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    instrument_id: uuid.UUID | None = None
    solar_load: bool | None = None
    active: bool | None = None


class PointRead(ApiModel):
    id: uuid.UUID
    point_code: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID]
    zone_codes: list[str]
    source_kind: PointSourceKind
    instrument_id: uuid.UUID | None
    instrument_no: str | None
    solar_load: bool
    active: bool


class PointPage(Page[PointRead]):
    pass


# ---- readings (§3.3) -----------------------------------------------------------------------------


class ReadingComponents(StrictInput):
    ta_c: Decimal | None = Field(default=None, description="Dry bulb, 0–60.")
    tnwb_c: Decimal | None = Field(default=None, description="Natural wet bulb, 0–45.")
    tg_c: Decimal | None = Field(default=None, description="Globe, 0–90.")
    rh_pct: int | None = Field(default=None, description="0–100.")
    wbgt_entered_c: Decimal | None = Field(
        default=None,
        description="Required unless tnwb and tg (and ta with solar load) are given; 10.0–45.0.",
    )


class ReadingCreate(ReadingComponents):
    """Manual reading (capability 167, WB-1). Back-dating up to `reading_backdate_max_hours`
    (BACKDATED_READING); > 15 min old = late_entry (no live alert, HA-5). Dry bulb alone →
    WBGT_REQUIRED (WB-3). `point_id` or (PH-2 / WR-7) `zone_id` + `permit_id` for a permit
    shift in a zone without a covering point."""

    point_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    permit_id: uuid.UUID | None = None
    instrument_id: uuid.UUID
    measured_at: datetime


class StationReadingCreate(ReadingComponents):
    """Weather-station ingest (device session only). A repeated (device, measured_at) is
    ignored (WB-1, idempotent)."""

    measured_at: datetime


class ReadingRead(ApiModel):
    id: uuid.UUID
    reading_no: str
    point_id: uuid.UUID
    point_code: str
    measured_at: datetime
    source: ReadingSource
    instrument_no: str
    ta_c: DecimalStr | None
    tnwb_c: DecimalStr | None
    tg_c: DecimalStr | None
    rh_pct: int | None
    wbgt_entered_c: DecimalStr | None
    wbgt_c: DecimalStr
    regime_cells: dict[str, Regime] = Field(
        description='Work clothes: {"acclimatised.light": "R0", …, "unacclimatised.very_heavy": …}.'
    )
    late_entry: bool
    status: RecordStatus
    void_reason: str | None
    recorded_by: UserRef | None
    created_at: datetime
    warnings: list[ApiWarning] = Field(default_factory=list)


class ReadingPage(Page[ReadingRead]):
    pass


class VoidInput(StrictInput):
    """Capability 177; reason ≥ 20 chars."""

    reason: str = Field(min_length=1, max_length=300)


class ReadingImportRow(ApiModel):
    row: int
    ok: bool
    code: str | None = None
    message: str | None = None


class ReadingImportResult(ApiModel):
    """WB-4 template `wbgt_readings` (.csv: point_code, measured_at ISO, instrument_no, ta_c,
    tnwb_c, tg_c, rh_pct, wbgt_c). Dry run validates; commit creates late-entry readings."""

    dry_run: bool
    rows_total: int
    rows_ok: int
    created: int
    rows: list[ReadingImportRow]


# ---- zone heat state and board (§3.5, §8.1 item 2) -----------------------------------------------


class RegimeCell(ApiModel):
    basis: AcclimatisationBasis
    workload: Workload
    regime: Regime
    rest_minutes_per_hour: int | None


class ZoneHeatState(ApiModel):
    zone_id: uuid.UUID
    zone_code: str
    site_id: uuid.UUID
    required: bool = Field(description="Phase 3 default_exposure outdoor_direct_sun (HS-3).")
    point_code: str | None
    state: HeatStateKind
    wbgt_c: DecimalStr | None
    reading_no: str | None
    measured_at: datetime | None
    age_minutes: int | None
    headline_workload: Workload
    headline_regime: Regime
    rest_minutes_per_hour: int | None
    cells: list[RegimeCell]
    ban_in_force: bool
    active_exemptions: list[str]


class HeatBoard(ApiModel):
    project_id: uuid.UUID
    at: datetime
    in_controls_period: bool
    ban_in_force: bool
    zones: list[ZoneHeatState]
    coverage_gaps: list[str] = Field(description="Required zones without an active point.")
    acclimatising_today: int
    open_reviews: int
    water_advice_en: str
    water_advice_ar: str


# ---- acclimatisation (§3.6) ----------------------------------------------------------------------


class PlanDay(ApiModel):
    day_no: int
    work_date: date | None
    max_pct: int
    max_minutes: int
    confirmed_by: UserRef | None = None
    confirmed_at: datetime | None = None
    followed: bool | None = None
    note: str | None = None


class PlanTrigger(ApiModel):
    kind: PlanTriggerKind
    ref: str | None = None
    on: date | None = None


class PlanRead(ApiModel):
    """P6b-3: below 6a tier 2 a post_heat_illness plan is shown as `returner` with trigger
    `absence` and no reference."""

    id: uuid.UUID
    plan_no: str
    project_id: uuid.UUID
    deployment_id: uuid.UUID
    worker: WorkerRef
    engagement_id: uuid.UUID | None
    plan_type: PlanType
    trigger: PlanTrigger
    schedule_pct: list[int]
    prior_heat_experience: dict[str, Any] | None
    days: list[PlanDay]
    status: PlanStatus
    status_reason: str | None
    completed_as_planned: bool | None


class PlanPage(Page[PlanRead]):
    pass


class PriorExperienceInput(StrictInput):
    """AP-3 (capability 172), new_worker plans before day 2: text ≥ 20 chars; the plan switches
    to the returner schedule (TOO_LATE_TO_CHANGE after day 1)."""

    text: str = Field(min_length=1, max_length=500)


class PlanDayConfirm(StrictInput):
    """AP-8: followed yes / no (note ≥ 10 chars when no)."""

    followed: bool
    note: str | None = Field(default=None, max_length=300)


class PlanCancel(StrictInput):
    reason: str = Field(min_length=1, max_length=300)


class DutyWorker(ApiModel):
    worker: WorkerRef
    plan_no: str | None = None
    day_no: int | None = None
    max_pct: int | None = None
    max_minutes: int | None = None
    label_en: str | None = None
    label_ar: str | None = None


class HeatDutyList(ApiModel):
    """§8.4 per engagement and day (capability 166)."""

    project_id: uuid.UUID
    day: date
    engagement_id: uuid.UUID | None
    acclimatising: list[DutyWorker]
    not_for_heat_work: list[DutyWorker]
    zones: list[ZoneHeatState]


# ---- rest stations and welfare checks (§3.7, §3.8) -----------------------------------------------


class RestStationCreate(StrictInput):
    station_code: str = Field(min_length=1, max_length=16)
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1)
    station_type: StationType
    capacity_persons: int = Field(ge=1, le=200)
    cooling: Cooling


class RestStationUpdate(PatchInput):
    non_nullable = frozenset({"zone_ids", "active", "capacity_persons", "cooling"})

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    capacity_persons: int | None = Field(default=None, ge=1, le=200)
    cooling: Cooling | None = None
    active: bool | None = None


class RestStationRead(ApiModel):
    id: uuid.UUID
    station_code: str
    project_id: uuid.UUID
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID]
    zone_codes: list[str]
    station_type: StationType
    capacity_persons: int
    cooling: Cooling
    active: bool


class RestStationPage(Page[RestStationRead]):
    pass


class WelfareAnswer(StrictInput):
    item: WelfareItem
    answer: CheckAnswer
    note: str | None = Field(default=None, max_length=300)


class WelfareCheckCreate(StrictInput):
    """Capability 169 (RS-4: contractor roles at stations of sites where their engagement is
    Mobilised). Every HW item answered; `na` only where list HW allows it (NA_NOT_ALLOWED)."""

    station_id: uuid.UUID
    checked_at: datetime
    engagement_id: uuid.UUID | None = None
    items: list[WelfareAnswer] = Field(min_length=1)
    water_temp_c: Decimal | None = Field(default=None, ge=0, le=50)
    persons_present: int | None = Field(default=None, ge=0, le=500)


class WelfareAnswerRead(ApiModel):
    item: WelfareItem
    answer: CheckAnswer
    note: str | None = None


class WelfareCheckRead(ApiModel):
    id: uuid.UUID
    check_no: str
    project_id: uuid.UUID
    station_id: uuid.UUID
    station_code: str
    checked_at: datetime
    checked_by: UserRef | None
    engagement_id: uuid.UUID | None
    items: list[WelfareAnswerRead]
    water_temp_c: DecimalStr | None
    persons_present: int | None
    critical_fail: bool
    ca_refs: list[str]
    status: RecordStatus
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class WelfareCheckPage(Page[WelfareCheckRead]):
    pass


# ---- midday ban: patrols and exemptions (§3.9, §3.10) --------------------------------------------


class PatrolCreate(StrictInput):
    """Capability 170 (MB-1). violation / exempt_work need engagement, headcount 1–500 and
    activity. exempt_work needs an active exemption covering engagement and zone
    (NO_ACTIVE_EXEMPTION). checked_at inside the ban hours of a ban date (NOT_IN_BAN_WINDOW)."""

    zone_id: uuid.UUID
    checked_at: datetime
    outcome: PatrolOutcome
    engagement_id: uuid.UUID | None = None
    headcount: int | None = Field(default=None, ge=1, le=500)
    activity: str | None = Field(default=None, max_length=200)
    permit_id: uuid.UUID | None = None
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=3)


class PatrolRead(ApiModel):
    id: uuid.UUID
    patrol_no: str
    project_id: uuid.UUID
    zone_id: uuid.UUID
    zone_code: str
    checked_at: datetime
    checked_by: UserRef | None
    outcome: PatrolOutcome
    engagement_id: uuid.UUID | None
    contractor_code: str | None
    headcount: int | None
    activity: str | None
    exemption_ref: str | None
    permit_id: uuid.UUID | None
    photo_ids: list[uuid.UUID]
    ca_ref: str | None
    status: RecordStatus
    void_reason: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class PatrolPage(Page[PatrolRead]):
    pass


class BanExemptionCreate(StrictInput):
    """Capability 171 (HSE Manager, MB-5): dates inside the ban period (OUTSIDE_BAN_PERIOD),
    ≤ 14 days; controls ≥ 30 chars in one language."""

    engagement_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1)
    date_from: date
    date_to: date
    reason: BanExemptionReason
    controls_en: str | None = Field(default=None, max_length=1000)
    controls_ar: str | None = Field(default=None, max_length=1000)


class BanExemptionRead(ApiModel):
    id: uuid.UUID
    exemption_no: str
    project_id: uuid.UUID
    engagement_id: uuid.UUID
    contractor_code: str | None
    zone_ids: list[uuid.UUID]
    zone_codes: list[str]
    date_from: date
    date_to: date
    reason: BanExemptionReason
    controls_en: str | None
    controls_ar: str | None
    granted_by: UserRef | None
    granted_at: datetime
    status: BanExemptionStatus
    status_reason: str | None


class BanExemptionPage(Page[BanExemptionRead]):
    pass


class RevokeInput(StrictInput):
    reason: str = Field(min_length=1, max_length=300)


# ---- heat-illness log (§3.11) --------------------------------------------------------------------


class HeatReviewInput(StrictInput):
    """HI-4 (capability 173 with write: HSE Manager, HSE Officer). Answers for HC1–HC6."""

    answers: dict[ReviewQuestion, ReviewAnswer]
    factors_text: str | None = Field(default=None, max_length=500)


class HeatReviewRead(ApiModel):
    answers: dict[ReviewQuestion, ReviewAnswer]
    factors_text: str | None = None
    reviewed_by: UserRef | None = None
    reviewed_at: datetime | None = None


class HeatLogRead(ApiModel):
    """P6b-2: names only with Phase 1 capability 29; contractor roles get no review texts."""

    id: uuid.UUID
    entry_no: str
    project_id: uuid.UUID
    source_type: HeatLogSource
    source_ref: str | None
    related_referral_no: str | None
    worker: WorkerRef | None
    event_at: datetime
    zone_id: uuid.UUID | None
    zone_code: str | None
    context: dict[str, Any] = Field(description="§6.7 snapshot.")
    review: HeatReviewRead | None
    control_gap: bool
    status: HeatLogStatus
    hold_no: str | None
    review_due_at: datetime


class HeatLogPage(Page[HeatLogRead]):
    pass


class ReopenInput(StrictInput):
    reason: str = Field(min_length=1, max_length=300)


# ---- KPIs, action panel, season report (§6.6, §8) ------------------------------------------------


class HeatBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class HeatBreakdown(ApiModel):
    metric: str
    group_by: HeatKpiGroupBy
    rows: list[HeatBreakdownRow]


class HeatKpiResponse(ApiModel):
    """GET /kpi/heat-stress: K-97…K-103 (aggregates only, HM-2). Components: K-98 hours by
    regime; K-100 rate per 100 patrols; K-101 checked station-days chip; K-103 rate,
    recordable count and rate. Heat-illness counts < 3 display "<3" below the HSE Manager."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[HeatBreakdown]


class HeatActionItem(ApiModel):
    kind: HeatActionKind
    count: int
    refs: list[str]
    label_en: str
    label_ar: str


class HeatActionPanel(ApiModel):
    project_id: uuid.UUID
    at: datetime
    items: list[HeatActionItem]


class SeasonReportRead(ApiModel):
    report_no: str | None
    project_id: uuid.UUID
    season_year: int
    revision: int | None
    status: SeasonReportStatus
    period_from: date
    period_to: date
    metrics: dict[str, Any]
    comments_en: str | None
    comments_ar: str | None
    issued_by: UserRef | None
    issued_at: datetime | None


class SeasonReportList(ApiModel):
    draft: SeasonReportRead | None = Field(description="Omitted for Viewer/Client (HM-4).")
    issued: list[SeasonReportRead]


class SeasonReportIssue(StrictInput):
    """Capability 175. Re-issue needs `reason` ≥ 20 chars and supersedes the previous one."""

    season_year: int = Field(ge=2020, le=2100)
    comments_en: str | None = Field(default=None, max_length=2000)
    comments_ar: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=300)


class AcclimatisationStatusRead(ApiModel):
    worker_id: uuid.UUID
    day: date
    status: AcclimatisationStatus
    basis: AcclimatisationBasis
    plan_no: str | None
    day_no: int | None
