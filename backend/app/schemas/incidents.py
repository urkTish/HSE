"""Incident register, injury cases, investigations and external notifications (spec
1-dashboard §3.3-§3.5, §4.2, §5.2, §5.8)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.hse_enums import (
    Activity,
    AgeBand,
    Agency,
    AirsideFlag,
    AssetType,
    BodyPart,
    BodySide,
    CaseCategory,
    CaStatus,
    ClassificationStatus,
    ControlLevel,
    DangerousOccurrenceCategory,
    EnvCategory,
    EnvReached,
    ExternalBody,
    IcamLevel,
    IdType,
    IncidentShift,
    IncidentStatus,
    IncidentType,
    InjuryNature,
    InvestigationLevel,
    InvestigationMethod,
    Mechanism,
    NotificationState,
    NotWorkRelatedReason,
    PermanentDisability,
    PersonType,
    PrivacyCaseReason,
    RateExclusionReason,
    RootCauseCode,
    Trade,
    TreatedAt,
    Treatment,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import (
    ApiWarning,
    DecimalStr,
    EngagementRef,
    SarAmount,
    SiteRef,
    UserRef,
    ZoneRef,
)

P3_HINT = "Do not enter person names, ID numbers or medical details here (P3)."
ISO2 = r"^[A-Z]{2}$"

# ---- incident ------------------------------------------------------------------------------------


class PropertyDamageInput(StrictInput):
    asset_type: AssetType
    estimated_cost_sar: SarAmount


class EnvironmentalInput(StrictInput):
    category: EnvCategory
    substance: str | None = Field(default=None, max_length=100)
    quantity_l: DecimalStr | None = Field(default=None, ge=0, max_digits=10, decimal_places=1)
    contained: bool
    reached: EnvReached


class DangerousOccurrenceInput(StrictInput):
    category: DangerousOccurrenceCategory


class _IncidentFields(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = Field(default=None, description="Zone of the site (I-18).")
    location_detail: str | None = Field(default=None, max_length=200)
    responsible_engagement_id: uuid.UUID | None = Field(
        default=None, description="Required at Draft → Reported."
    )
    occurred_at: datetime = Field(description="UTC instant; ≤ now. Displayed in project tz.")
    shift: IncidentShift | None = None
    incident_types: list[IncidentType] = Field(
        min_length=1,
        description="near_miss cannot be combined with any other type → 422 NEAR_MISS_EXCLUSIVE.",
    )
    primary_type: IncidentType = Field(description="One of incident_types.")
    title: str = Field(min_length=1, max_length=150, description=P3_HINT)
    description: str | None = Field(default=None, max_length=4000, description=P3_HINT)
    immediate_actions: str | None = Field(default=None, max_length=2000)
    activity: Activity | None = None
    work_related: bool = True
    not_work_related_reason: NotWorkRelatedReason | None = Field(
        default=None, description="Required iff work_related = false (OSHA 1904.5)."
    )
    work_related_rationale: str | None = Field(default=None, max_length=500)
    actual_severity: int | None = Field(default=None, ge=1, le=5, description="§3.11 list S.")
    potential_severity: int | None = Field(
        default=None, ge=1, le=5, description="≥ actual_severity; ≥ 4 ⇒ HiPo (I-13)."
    )
    ambient_temp_c: DecimalStr | None = Field(
        default=None, ge=0, le=60, max_digits=4, decimal_places=1
    )
    airside_flags: list[AirsideFlag] = Field(
        default_factory=list, description="Only for zones with zone_type = airside (I-18)."
    )
    property_damage: PropertyDamageInput | None = Field(
        default=None, description="Required iff property_damage in incident_types."
    )
    environmental: EnvironmentalInput | None = Field(
        default=None, description="Required iff environmental in incident_types."
    )
    dangerous_occurrence: DangerousOccurrenceInput | None = Field(
        default=None, description="Required iff dangerous_occurrence in incident_types."
    )


class IncidentCreate(_IncidentFields):
    """Creates a Draft. Fields marked 'required at Draft → Reported' may be left empty in the
    draft. Free-text fields are scanned for possible ID numbers (P1-8): a
    `POSSIBLE_ID_NUMBER` warning is returned in `warnings` (not blocking)."""


class IncidentUpdate(PatchInput):
    """Editable while draft/reported/under_investigation (HSE Officer/Manager or reporter in
    draft). Closed/voided → 409 INVALID_TRANSITION."""

    non_nullable = frozenset(
        {"site_id", "occurred_at", "incident_types", "primary_type", "title", "work_related"}
    )

    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    location_detail: str | None = Field(default=None, max_length=200)
    responsible_engagement_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    shift: IncidentShift | None = None
    incident_types: list[IncidentType] | None = Field(default=None, min_length=1)
    primary_type: IncidentType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    immediate_actions: str | None = Field(default=None, max_length=2000)
    activity: Activity | None = None
    work_related: bool | None = None
    not_work_related_reason: NotWorkRelatedReason | None = None
    work_related_rationale: str | None = Field(default=None, max_length=500)
    actual_severity: int | None = Field(default=None, ge=1, le=5)
    potential_severity: int | None = Field(default=None, ge=1, le=5)
    ambient_temp_c: DecimalStr | None = Field(
        default=None, ge=0, le=60, max_digits=4, decimal_places=1
    )
    airside_flags: list[AirsideFlag] | None = None
    property_damage: PropertyDamageInput | None = None
    environmental: EnvironmentalInput | None = None
    dangerous_occurrence: DangerousOccurrenceInput | None = None


class PropertyDamageRead(ApiModel):
    asset_type: AssetType
    estimated_cost_sar: SarAmount


class EnvironmentalRead(ApiModel):
    category: EnvCategory
    substance: str | None
    quantity_l: DecimalStr | None
    contained: bool
    reached: EnvReached


class DangerousOccurrenceRead(ApiModel):
    category: DangerousOccurrenceCategory


class ExternalNotificationRead(ApiModel):
    """I-20: required notifications are derived; recorded ones show done."""

    body: ExternalBody
    required: bool = Field(description="Derived from the incident and its cases (I-20).")
    required_reason: str | None = Field(
        default=None, description="Why it is required, e.g. 'LTI case P1 (contractor worker)'."
    )
    due_at: datetime | None = Field(description="Deadline (ASSUMPTION/VERIFY per body).")
    state: NotificationState | None = Field(description="null when not required and not done.")
    notified_at: datetime | None
    reference_no: str | None
    notified_by: UserRef | None


class ExternalNotificationRecord(StrictInput):
    """Record that a body was notified (tracking only; I-21: the platform does not submit)."""

    notified_at: datetime
    reference_no: str | None = Field(default=None, max_length=60)


class InjuryCaseSummary(ApiModel):
    """De-identified case row used in the incident view (P1-2): 'Person 1 · scaffolder · NAJD'."""

    id: uuid.UUID
    case_no: str = Field(examples=["INC-ANIA-EXP-2026-0147-P1"])
    display_label: str = Field(examples=["Person 1 · scaffolder · NAJD"])
    display_label_ar: str
    person_type: PersonType
    trade: Trade
    employer: EngagementRef | None
    mechanism: Mechanism
    agency: Agency
    case_category: CaseCategory | None = Field(description="Effective (confirmed or derived).")
    classification_status: ClassificationStatus
    excluded_from_rates: bool
    exclusion_reasons: list[RateExclusionReason]
    open_lti: bool = Field(description="LTI with rtw_date null (I-8).")


class InvestigationSummary(ApiModel):
    level: InvestigationLevel
    lead_investigator: UserRef | None
    due_date: date | None
    overdue: bool
    submitted_at: datetime | None
    approved_at: datetime | None


class LinkedCaSummary(ApiModel):
    id: uuid.UUID
    ref: str
    title: str
    status: CaStatus
    control_level: ControlLevel
    due_date: date
    overdue: bool


class IncidentRead(Timestamps):
    id: uuid.UUID
    ref: str = Field(examples=["INC-ANIA-EXP-2026-0147"])
    project_id: uuid.UUID
    site: SiteRef
    zone: ZoneRef | None
    location_detail: str | None
    responsible_engagement: EngagementRef | None
    occurred_at: datetime
    reported_at: datetime | None
    reported_by: UserRef | None
    shift: IncidentShift | None
    incident_types: list[IncidentType]
    primary_type: IncidentType
    title: str
    description: str | None
    immediate_actions: str | None
    activity: Activity | None
    work_related: bool
    not_work_related_reason: NotWorkRelatedReason | None
    work_related_rationale: str | None
    actual_severity: int | None
    potential_severity: int | None
    hipo: bool = Field(description="Derived: potential_severity ≥ 4 (I-13).")
    late_report: bool = Field(description="reported_at − occurred_at > 24 h (I-19, K-47).")
    ambient_temp_c: DecimalStr | None
    airside_flags: list[AirsideFlag]
    property_damage: PropertyDamageRead | None
    environmental: EnvironmentalRead | None
    dangerous_occurrence: DangerousOccurrenceRead | None
    status: IncidentStatus
    void_reason: str | None
    minimum_investigation_level: InvestigationLevel = Field(description="Derived (I-14).")
    cases: list[InjuryCaseSummary]
    investigation: InvestigationSummary | None
    external_notifications: list[ExternalNotificationRead]
    corrective_actions: list[LinkedCaSummary]
    allowed_transitions: list[IncidentStatus] = Field(
        description="Transitions the caller may trigger now (UI hint; the server re-checks)."
    )
    warnings: list[ApiWarning] = Field(default_factory=list)


class IncidentListItem(ApiModel):
    id: uuid.UUID
    ref: str
    occurred_at: datetime
    shift: IncidentShift | None
    incident_types: list[IncidentType]
    primary_type: IncidentType
    title: str
    site: SiteRef
    zone: ZoneRef | None
    responsible_engagement: EngagementRef | None
    activity: Activity | None
    actual_severity: int | None
    potential_severity: int | None
    hipo: bool
    status: IncidentStatus
    case_count: int
    case_categories: list[CaseCategory]
    provisional_cases: int
    excluded_cases: int = Field(description="Cases listed but excluded from rates (I-4).")
    late_report: bool
    investigation_level: InvestigationLevel | None
    investigation_due_date: date | None


class IncidentPage(Page[IncidentListItem]):
    pass


class InvestigationAssignment(StrictInput):
    """Set on Reported → Under Investigation (§4.2)."""

    level: InvestigationLevel = Field(
        description="≥ minimum level (I-14) → else 422 INVESTIGATION_LEVEL_TOO_LOW."
    )
    lead_investigator_id: uuid.UUID
    team_member_ids: list[uuid.UUID] = Field(
        default_factory=list, description="L3: ≥ 2 incl. ≥ 1 from the responsible contractor."
    )
    method: InvestigationMethod | None = None


class IncidentTransitionRequest(StrictInput):
    """§4.2 transitions:

    * draft → reported (reporter): all required fields; injury needs ≥ 1 case
      (`INJURY_CASE_REQUIRED`); near_miss alone (`NEAR_MISS_EXCLUSIVE`).
    * reported → under_investigation (HSE Officer/Manager): `investigation` required.
    * reported → closed (L1 quick close, HSE Officer): level L1 and no CA required; `reason`.
    * under_investigation → pending_review (lead): investigation complete
      (`INVESTIGATION_INCOMPLETE`, rule I-16).
    * pending_review → under_investigation (approver): `reason` = return comment.
    * pending_review → actions_pending | closed (approver; L3 HSE Manager only): all cases
      confirmed (`CASES_NOT_CONFIRMED`); I-17 (`HIGHER_CONTROL_REQUIRED` unless
      `higher_control_justification`); approver ≠ lead (`APPROVER_IS_LEAD`).
    * reported/under_investigation → voided (HSE Officer/Manager): `reason`.
    * closed → under_investigation, voided → reported (HSE Manager): `reason`.
    """

    to_status: IncidentStatus
    reason: str | None = Field(default=None, max_length=1000)
    investigation: InvestigationAssignment | None = None
    higher_control_justification: str | None = Field(
        default=None,
        min_length=20,
        max_length=1000,
        description="I-17 / CA-6: why no elimination/substitution/engineering control is "
        "reasonably practicable.",
    )


# ---- injury cases --------------------------------------------------------------------------------


class _InjuryCaseFields(StrictInput):
    person_type: PersonType
    employer_engagement_id: uuid.UUID | None = Field(
        default=None, description="Required iff person_type = contractor_worker."
    )
    person_name: str = Field(min_length=1, max_length=120, description="Sensitive (P1-1).")
    id_type: IdType | None = None
    id_number: str | None = Field(
        default=None,
        max_length=10,
        description="iqama ^2\\d{9}$, national_id ^1\\d{9}$, passport ^[A-Z0-9]{6,9}$. "
        "Encrypted at rest; never returned in full except by GET …/id-number.",
    )
    employee_no: str | None = Field(default=None, max_length=20)
    nationality: str | None = Field(default=None, pattern=ISO2)
    trade: Trade
    age_band: AgeBand | None = None
    site_start_date: date | None = None
    hours_into_shift: DecimalStr | None = Field(
        default=None, ge=0, le=16, max_digits=3, decimal_places=1
    )
    illness: bool = False
    body_part: BodyPart
    body_side: BodySide | None = None
    nature: InjuryNature
    mechanism: Mechanism
    agency: Agency
    treatments: list[Treatment] = Field(min_length=1)
    loss_of_consciousness: bool = False
    treated_at: TreatedAt
    fatal: bool = False
    date_of_death: date | None = None
    away_start_date: date | None = Field(
        default=None, description="Default incident local date + 1; > incident date."
    )
    rtw_date: date | None = Field(
        default=None, description="First day back on any duty; null = still away."
    )
    restricted_start: date | None = None
    restricted_end: date | None = Field(default=None, description="Inclusive; null = open.")
    transfer_start: date | None = None
    transfer_end: date | None = None
    permanent_disability: PermanentDisability = PermanentDisability.none
    commuting: bool = False
    privacy_case: bool = False
    privacy_reason: PrivacyCaseReason | None = None
    medical_notes: str | None = Field(default=None, max_length=2000)
    gosi_case_ref: str | None = Field(default=None, max_length=30)


class InjuryCaseCreate(_InjuryCaseFields):
    """Add an injured/ill person to an injury_illness incident. The category is derived
    (I-5) and stays provisional until confirmed."""


class InjuryCaseUpdate(PatchInput):
    """Any change re-derives the category (I-9); a change in a Locked month marks it restated."""

    non_nullable = frozenset(
        {
            "person_type",
            "person_name",
            "trade",
            "body_part",
            "nature",
            "mechanism",
            "agency",
            "treatments",
            "treated_at",
            "permanent_disability",
            "illness",
            "loss_of_consciousness",
            "fatal",
            "commuting",
            "privacy_case",
        }
    )

    person_type: PersonType | None = None
    employer_engagement_id: uuid.UUID | None = None
    person_name: str | None = Field(default=None, min_length=1, max_length=120)
    id_type: IdType | None = None
    id_number: str | None = Field(default=None, max_length=10)
    employee_no: str | None = Field(default=None, max_length=20)
    nationality: str | None = Field(default=None, pattern=ISO2)
    trade: Trade | None = None
    age_band: AgeBand | None = None
    site_start_date: date | None = None
    hours_into_shift: DecimalStr | None = Field(
        default=None, ge=0, le=16, max_digits=3, decimal_places=1
    )
    illness: bool | None = None
    body_part: BodyPart | None = None
    body_side: BodySide | None = None
    nature: InjuryNature | None = None
    mechanism: Mechanism | None = None
    agency: Agency | None = None
    treatments: list[Treatment] | None = Field(default=None, min_length=1)
    loss_of_consciousness: bool | None = None
    treated_at: TreatedAt | None = None
    fatal: bool | None = None
    date_of_death: date | None = None
    away_start_date: date | None = None
    rtw_date: date | None = None
    restricted_start: date | None = None
    restricted_end: date | None = None
    transfer_start: date | None = None
    transfer_end: date | None = None
    permanent_disability: PermanentDisability | None = None
    commuting: bool | None = None
    privacy_case: bool | None = None
    privacy_reason: PrivacyCaseReason | None = None
    medical_notes: str | None = Field(default=None, max_length=2000)
    gosi_case_ref: str | None = Field(default=None, max_length=30)


class CaseDayCounts(ApiModel):
    """§6.3 day counts at `as_of` (sensitive per person: capability 30)."""

    as_of: date
    days_away: int
    restricted_days: int
    transfer_days: int
    capped: bool
    lost_days_charged: int = Field(description="K-17 contribution incl. fatality charge.")


class InjuryCaseRead(ApiModel):
    """Field groups are present only when the caller may read them (response omits the keys):

    * identity (capability 29): person_name, id_type, id_number_masked, employee_no,
      nationality, age_band, site_start_date, days_on_site, hours_into_shift, gosi_case_ref.
      For privacy cases person_name = "Privacy case / حالة خصوصية" and the ID is omitted for
      everyone except the HSE Manager (I-12).
    * medical (capability 30): illness, body_part, body_side, nature, treatments,
      loss_of_consciousness, treated_at, fatal, date_of_death, absence/restriction/transfer
      dates, permanent_disability, privacy_case, privacy_reason, day_counts, medical_notes.

    Every read that returns identity or medical fields writes a `sensitive_field_read` audit
    entry listing the fields (P5). `redacted_groups` lists the groups withheld."""

    id: uuid.UUID
    incident_id: uuid.UUID
    case_no: str
    display_label: str
    display_label_ar: str
    person_type: PersonType
    employer: EngagementRef | None
    trade: Trade
    mechanism: Mechanism
    agency: Agency
    commuting: bool
    derived_category: CaseCategory
    case_category: CaseCategory = Field(description="Effective category used by KPIs.")
    classification_status: ClassificationStatus
    category_override_justification: str | None
    excluded_from_rates: bool
    exclusion_reasons: list[RateExclusionReason]
    open_lti: bool
    redacted_groups: list[str] = Field(description="Subset of ['identity', 'medical'].")
    # identity group
    person_name: str | None = None
    id_type: IdType | None = None
    id_number_masked: str | None = Field(default=None, examples=["2*******17"])
    employee_no: str | None = None
    nationality: str | None = None
    age_band: AgeBand | None = None
    site_start_date: date | None = None
    days_on_site: int | None = None
    hours_into_shift: DecimalStr | None = None
    gosi_case_ref: str | None = None
    # medical group
    illness: bool | None = None
    body_part: BodyPart | None = None
    body_side: BodySide | None = None
    nature: InjuryNature | None = None
    treatments: list[Treatment] | None = None
    loss_of_consciousness: bool | None = None
    treated_at: TreatedAt | None = None
    fatal: bool | None = None
    date_of_death: date | None = None
    away_start_date: date | None = None
    rtw_date: date | None = None
    restricted_start: date | None = None
    restricted_end: date | None = None
    transfer_start: date | None = None
    transfer_end: date | None = None
    permanent_disability: PermanentDisability | None = None
    privacy_case: bool | None = None
    privacy_reason: PrivacyCaseReason | None = None
    day_counts: CaseDayCounts | None = None
    medical_notes: str | None = None
    warnings: list[ApiWarning] = Field(default_factory=list)


class IdNumberRead(ApiModel):
    """Full ID number (capability 29; privacy cases HSE Manager only). Audited."""

    id_type: IdType | None
    id_number: str | None


class ClassificationConfirm(StrictInput):
    """Confirm the case category (HSE Officer/Manager, capability 26). A category different
    from the derived one requires HSE Manager and `justification` ≥ 20 chars (I-6) →
    `JUSTIFICATION_REQUIRED`."""

    case_category: CaseCategory
    justification: str | None = Field(default=None, min_length=20, max_length=1000)


# ---- investigation -------------------------------------------------------------------------------


class RootCauseInput(StrictInput):
    code: RootCauseCode = Field(description="§3.11 list R; ICAM level derived from the prefix.")
    text: str = Field(min_length=1, max_length=1000)
    linked_ca_ids: list[uuid.UUID] = Field(default_factory=list)
    no_action_justification: str | None = Field(
        default=None, max_length=1000, description="I-16: when no CA is linked."
    )


class RootCauseRead(ApiModel):
    code: RootCauseCode
    icam_level: IcamLevel
    text: str
    linked_ca_ids: list[uuid.UUID]
    no_action_justification: str | None


class InvestigationUpdate(PatchInput):
    """Edit by lead/team (capability 27) or HSE Officer/Manager. Level may be raised, never
    lowered below the minimum (I-14)."""

    level: InvestigationLevel | None = None
    lead_investigator_id: uuid.UUID | None = None
    team_member_ids: list[uuid.UUID] | None = None
    method: InvestigationMethod | None = None
    preliminary_report: str | None = Field(
        default=None, max_length=4000, description="Sets preliminary_report_at (L3 within 48 h)."
    )
    sequence_of_events: str | None = Field(default=None, max_length=4000)
    immediate_causes: str | None = Field(default=None, max_length=2000)
    root_causes: list[RootCauseInput] | None = None
    lessons_learned: str | None = Field(default=None, max_length=2000)
    ptw_involved: bool | None = None
    ptw_ref: str | None = Field(default=None, max_length=40)


class InvestigationExtensionRequest(StrictInput):
    """HSE Manager extends the due date with a reason (§3.5)."""

    new_due_date: date
    reason: str = Field(min_length=1, max_length=500)


class InvestigationExtensionRead(ApiModel):
    new_due_date: date
    previous_due_date: date
    reason: str
    approved_by: UserRef
    approved_at: datetime


class InvestigationRead(ApiModel):
    incident_id: uuid.UUID
    level: InvestigationLevel
    minimum_level: InvestigationLevel
    lead_investigator: UserRef | None
    team_members: list[UserRef]
    method: InvestigationMethod | None
    due_date: date | None
    overdue: bool
    extensions: list[InvestigationExtensionRead]
    preliminary_report: str | None
    preliminary_report_at: datetime | None
    preliminary_report_due_at: datetime | None = Field(description="L3: occurred_at + 48 h.")
    sequence_of_events: str | None
    immediate_causes: str | None
    root_causes: list[RootCauseRead]
    lessons_learned: str | None
    ptw_involved: bool | None
    ptw_ref: str | None
    submitted_at: datetime | None
    returned_comment: str | None
    approved_by: UserRef | None
    approved_at: datetime | None
    higher_control_justification: str | None
    missing_for_submit: list[str] = Field(
        description="Fields/rules still blocking Under Investigation → Pending Review."
    )


# ---- excluded-from-rates listing (AC21) ----------------------------------------------------------


class ExcludedCaseRow(ApiModel):
    incident_id: uuid.UUID
    incident_ref: str
    case_id: uuid.UUID | None
    case_no: str | None
    occurred_at: datetime
    case_category: CaseCategory | None
    reasons: list[RateExclusionReason]
    reason_detail: str | None = Field(
        description="e.g. not_work_related_reason code 'off_duty_camp'."
    )


class ExcludedCaseList(ApiModel):
    items: list[ExcludedCaseRow]
