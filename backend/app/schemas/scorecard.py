"""Phase 6g schemas — contractor HSE scorecard, report packs and the generic register export
(spec 6g-scorecard-reports v1.0).

Every schema carries the `Sc` (scorecard), `Rp` (report packs) or `Xp` (exports) prefix
(DECISIONS D-202). Numbers are decimal strings: `*_display` fields are rounded half-up at output
(score, points, pillar values 1 dp; Z 4 dp; rates 2 dp; percentages 1 dp, K-R8) and the plain
fields are unrounded. A Contractor HSE Rep only ever receives cards of engagements in their C
scope, with "rank n of N" and the project median (RK-2)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import EmailStr, Field

from app.core.scorecard_enums import (
    RpAction,
    RpChannel,
    RpDeliveryStatus,
    RpFileKind,
    RpLanguage,
    RpLanguages,
    RpMemberKind,
    RpStatus,
    RpType,
    ScCap,
    ScCardStatus,
    ScDisputeReason,
    ScGrade,
    ScKpiGroupBy,
    ScLineStatus,
    ScModule,
    ScPillar,
    ScProfileStatus,
    ScRankStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScResolution,
    ScScope,
    ScTrend,
    ScWatchAction,
    ScWatchDecision,
    ScWatchLevel,
    ScWatchProposal,
    ScWatchStatus,
    ScWindow,
    XpFormat,
    XpFrequency,
    XpJobStatus,
    XpMaskMode,
    XpPdpl,
    XpPurpose,
    XpPurposeRule,
)
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.kpi import KpiContext, KpiValue

# ---- reference -----------------------------------------------------------------------------------


class ScRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    detail: str | None = None


class ScReference(ApiModel):
    """Lists PL, SM, CP, GB, DR, WLL, RT, EP, MM, statuses and settings keys with EN/AR labels."""

    lists: dict[str, list[ScRefItem]]


class ScFileInput(StrictInput):
    """A file sent inline (base64). PDF, PNG or JPEG; ≤ 10 MB decoded."""

    file_name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4)
    content_type: str | None = Field(default=None, max_length=100)


# ---- settings ------------------------------------------------------------------------------------


class ScSettingsRead(ApiModel):
    """§3.9 project settings (capability 225 edits)."""

    project_id: uuid.UUID
    scorecard_from_month: str | None = Field(description="yyyy-mm or null")
    source_live_from: dict[ScModule, date | None]
    sources_confirmed_at: datetime | None
    scorecard_min_exposure_hours: int
    scorecard_min_coverage_pct: str
    scorecard_comment_days: int
    dispute_resolution_days: int
    scorecard_trend_points: str
    scorecard_drop_points: str
    pip_submit_days: int
    client_report_due_day: int
    external_distribution_enabled: bool
    external_domains: list[str]
    report_languages: RpLanguages
    updated_at: datetime | None = None


class ScSettingsUpdate(StrictInput):
    """Any subset; values outside "Allowed" → 422 SETTING_OUT_OF_RANGE."""

    scorecard_from_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    source_live_from: dict[ScModule, date | None] | None = None
    scorecard_min_exposure_hours: int | None = None
    scorecard_min_coverage_pct: str | None = None
    scorecard_comment_days: int | None = None
    dispute_resolution_days: int | None = None
    scorecard_trend_points: str | None = None
    scorecard_drop_points: str | None = None
    pip_submit_days: int | None = None
    client_report_due_day: int | None = None
    external_distribution_enabled: bool | None = None
    external_domains: list[str] | None = None
    report_languages: RpLanguages | None = None


# ---- profiles ------------------------------------------------------------------------------------


class ScPillarWeight(ApiModel):
    pillar_code: ScPillar
    weight: str


class ScMetricConfig(ApiModel):
    metric_code: str
    pillar_code: ScPillar
    kpi_ref: str
    window: ScWindow
    weight: str
    good: str
    bad: str
    min_volume: int
    enabled: bool


class ScCapConfig(ApiModel):
    cap_code: ScCap
    max_grade: ScGrade
    enabled: bool


class ScBand(ApiModel):
    grade: ScGrade
    min_score: str


class ScProfileRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    profile_code: str
    version: int
    effective_from_month: str
    pillars: list[ScPillarWeight]
    metrics: list[ScMetricConfig]
    caps: list[ScCapConfig]
    bands: list[ScBand]
    status: ScProfileStatus
    activated_at: datetime | None


class ScProfilePage(Page[ScProfileRead]):
    pass


class ScProfileCreate(StrictInput):
    """A new Draft version: of `ORG` (project_id null) or of a project's own profile (a copy of
    the active ORG version when the project has none, SP-5)."""

    project_id: uuid.UUID | None = None


class ScMetricPatch(StrictInput):
    metric_code: str
    weight: str | None = None
    good: str | None = None
    bad: str | None = None
    min_volume: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class ScProfileUpdate(StrictInput):
    """Draft only. Validation of the sums happens at activation (SP-1)."""

    effective_from_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    pillars: list[ScPillarWeight] | None = None
    metrics: list[ScMetricPatch] | None = None
    caps: list[ScCapConfig] | None = None
    bands: list[ScBand] | None = None


# ---- cards ---------------------------------------------------------------------------------------


class ScLineRead(ApiModel):
    metric_code: str
    pillar_code: ScPillar
    kpi_ref: str
    window: ScWindow
    value: str | None
    value_display: str
    numerator: str | None
    denominator: str | None
    base: int | None
    own_value: str | None
    project_value: str | None
    points: str | None
    points_display: str
    line_status: ScLineStatus
    original_weight: str
    effective_weight: str
    effective_weight_display: str
    contribution: str
    note: str | None = None


class ScPillarRead(ApiModel):
    pillar_code: ScPillar
    weight: str
    effective_weight: str
    effective_weight_display: str
    score: str | None
    score_display: str
    redistributed: bool


class ScCapApplied(ApiModel):
    cap_code: ScCap
    max_grade: ScGrade
    refs: list[str]


class ScRankInfo(ApiModel):
    rank: int | None
    rank_of: int | None
    rank_status: ScRankStatus | None
    median: str | None
    median_display: str


class ScCardRead(ApiModel):
    id: uuid.UUID | None = Field(description="null for a Provisional card (computed on read)")
    scorecard_no: str
    revision: int
    project_id: uuid.UUID
    engagement_id: uuid.UUID
    engagement_code: str
    month: str
    scope: ScScope
    profile_code: str
    profile_version: int
    month_man_hours: str
    r12_man_hours: str
    credibility_z: str
    credibility_z_display: str
    score: str | None
    score_display: str
    indicative: bool
    coverage_pct: str
    coverage_display: str
    band_grade: ScGrade | None
    grade: ScGrade | None
    grade_display: str
    caps_applied: list[ScCapApplied]
    trend_delta: str | None
    trend_label: ScTrend | None
    ranking: ScRankInfo
    commended: bool
    inputs_hash: str
    comment_until: datetime | None
    status: ScCardStatus
    revised_since_final: bool
    recomputed_score: str | None
    issued_at: datetime | None
    finalised_at: datetime | None
    reissue_reason: str | None
    watch_level: ScWatchLevel | None
    open_disputes: int
    banner: str | None = Field(default=None, description="SG-5 provisional banner")
    pillars: list[ScPillarRead] = Field(default_factory=list)
    lines: list[ScLineRead] = Field(default_factory=list)


class ScCardPage(Page[ScCardRead]):
    pass


class ScRankingRow(ApiModel):
    engagement_id: uuid.UUID
    engagement_code: str
    card_id: uuid.UUID | None
    score: str | None
    score_display: str
    grade: ScGrade | None
    band_grade: ScGrade | None
    caps: list[ScCap]
    trend_label: ScTrend | None
    coverage_display: str
    rank: int | None
    rank_status: ScRankStatus | None
    watch_level: ScWatchLevel | None
    commended: bool
    tree_score_display: str | None = None


class ScRanking(ApiModel):
    """RK-1 / RK-3. A Contractor HSE Rep receives only rows of their scope (RK-2)."""

    project_id: uuid.UUID
    month: str
    status: ScCardStatus | None
    rows: list[ScRankingRow]
    ranked_count: int
    median: str | None
    median_display: str
    profile: str


class ScFinaliseRequest(StrictInput):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")


class ScReissueRequest(StrictInput):
    reason: str = Field(max_length=500)


class ScFinaliseResult(ApiModel):
    month: str
    finalised: int
    scp_issued: int
    watch_entries: list[str]
    warnings: list[str]


# ---- comments and disputes -------------------------------------------------------------------


class ScRemarkCreate(StrictInput):
    kind: ScRemarkKind
    target_code: str | None = Field(default=None, max_length=20, description="SM or CP code")
    reason_code: ScDisputeReason | None = None
    text: str = Field(max_length=1000)
    files: list[ScFileInput] = Field(default_factory=list, max_length=3)


class ScRemarkResolve(StrictInput):
    resolution: ScResolution
    resolution_text: str = Field(max_length=1000)
    corrected_record_ref: str | None = Field(default=None, max_length=80)


class ScRemarkRead(ApiModel):
    id: uuid.UUID
    card_id: uuid.UUID
    scorecard_no: str
    engagement_code: str
    kind: ScRemarkKind
    internal: bool
    target_code: str | None
    reason_code: ScDisputeReason | None
    text: str
    file_ids: list[uuid.UUID]
    raised_by: UserRef | None
    raised_at: datetime
    due_at: datetime | None
    resolution: ScResolution | None
    resolution_text: str | None
    corrected_record_ref: str | None
    old_points: str | None
    new_points: str | None
    old_score: str | None
    new_score: str | None
    resolved_by: UserRef | None
    resolved_at: datetime | None
    status: ScRemarkStatus
    warnings: list[ApiWarning] = Field(default_factory=list)


class ScRemarkPage(Page[ScRemarkRead]):
    pass


# ---- watch list --------------------------------------------------------------------------------


class ScTriggerRef(ApiModel):
    month: str
    trigger: str
    scorecard_no: str | None


class ScWatchRead(ApiModel):
    id: uuid.UUID
    entry_no: str
    project_id: uuid.UUID
    engagement_id: uuid.UUID
    engagement_code: str
    level: ScWatchLevel
    trigger_refs: list[ScTriggerRef]
    baseline_score: str | None
    opened_at: datetime
    opened_reason: str | None
    proposal: ScWatchProposal | None
    proposal_reason: str | None
    review_ca_ref: str | None
    pip_ca_refs: list[str]
    pip_due_on: date | None
    pip_submitted_at: datetime | None
    pip_accepted_at: datetime | None
    decision: ScWatchDecision | None
    decision_text: str | None
    contractor_status_ref: str | None
    closed_reason: str | None
    closed_at: datetime | None
    status: ScWatchStatus


class ScWatchPage(Page[ScWatchRead]):
    pass


class ScWatchCreate(StrictInput):
    """Manual opening (226), e.g. on client instruction (WL-6)."""

    engagement_id: uuid.UUID
    reason: str = Field(max_length=500)


class ScWatchTransition(StrictInput):
    action: ScWatchAction
    reason: str | None = Field(default=None, max_length=1000)
    pip_ca_ids: list[uuid.UUID] | None = None
    decision: ScWatchDecision | None = None


class ScEngagementRef(ApiModel):
    project_code: str
    engagement_code: str
    tier: int
    demobilisation_date: date | None


class ScSuspensionForm(ApiModel):
    """WL-5: the Phase 0 Approved → Suspended form, prefilled. The platform never submits it."""

    contractor_id: uuid.UUID
    contractor_code: str
    current_status: str
    target_status: str
    status_reason: str
    warning_en: str
    warning_ar: str
    engagements: list[ScEngagementRef]
    submit_path: str


class ScCpsMonth(ApiModel):
    project_code: str
    month: str
    score_display: str
    grade: ScGrade | None
    caps: list[ScCap]
    profile: str


class ScPerformanceSummary(ApiModel):
    """WL-8 / CPS: last 12 Final months on all projects (226)."""

    contractor_id: uuid.UUID
    contractor_code: str
    weighted_mean_score: str | None
    weighted_mean_display: str
    grade_mix: dict[str, int]
    caps_applied: int
    months: list[ScCpsMonth]
    watch_entries: list[ScWatchRead]


# ---- report packs ------------------------------------------------------------------------------


class RpFileRead(ApiModel):
    kind: RpFileKind
    file_name: str
    sha256: str
    size_bytes: int


class RpPackRead(ApiModel):
    id: uuid.UUID
    doc_no: str
    revision: int
    report_type: RpType
    project_id: uuid.UUID | None
    engagement_id: uuid.UUID | None
    contractor_id: uuid.UUID | None
    period_start: date
    period_end: date
    status: RpStatus
    due_on: date | None
    sources: list[dict[str, Any]]
    snapshot_hash: str | None
    files: list[RpFileRead]
    with_names: bool
    scorecards_provisional: bool
    provisional_reason: str | None
    prepared_by: UserRef | None
    prepared_at: datetime | None
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    issued_by: UserRef | None
    issued_at: datetime | None
    review_comment: str | None
    reissue_reason: str | None
    revised_since_issue: bool
    superseded_by_revision: int | None
    sections: list[str] = Field(default_factory=list, description="RP-1 section keys, in order")


class RpPackDetail(RpPackRead):
    snapshot: dict[str, Any]


class RpPackPage(Page[RpPackRead]):
    pass


class RpPackCreate(StrictInput):
    """A Draft (229). MCR: one month; SCP: engagement + month; OSHA300: a calendar year (YTD up
    to `period_end`); HEAT: a season year; CPS: contractor (226). `with_names` (OSHA300 only)
    needs capability 43 and a purpose; such a pack is download-only (P6g-3)."""

    report_type: RpType
    project_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    contractor_id: uuid.UUID | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    year: int | None = Field(default=None, ge=2000, le=2100)
    period_end: date | None = None
    with_names: bool = False
    purpose: XpPurpose | None = None
    purpose_text: str | None = Field(default=None, max_length=500)


class RpPackUpdate(StrictInput):
    """Draft / In Review only (an Issued pack → 409 PACK_ISSUED_IMMUTABLE)."""

    review_comment: str | None = Field(default=None, max_length=500)


class RpPackTransition(StrictInput):
    action: RpAction
    comment: str | None = Field(default=None, max_length=500)
    scorecards_provisional: bool = False
    provisional_reason: str | None = Field(default=None, max_length=500)
    remove_xlsx_for_externals: bool = False


class RpReissueRequest(StrictInput):
    reason: str = Field(max_length=500)


class RpFileUrl(ApiModel):
    url: str
    expires_at: datetime


class RpMemberInput(StrictInput):
    kind: RpMemberKind
    user_id: uuid.UUID | None = None
    display_name_en: str | None = Field(default=None, max_length=120)
    display_name_ar: str | None = Field(default=None, max_length=120)
    organisation: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    language: RpLanguage = RpLanguage.both
    acknowledge_disclosure: bool = Field(
        default=False,
        description="P6g-6: the HSE Manager confirms the client contract allows disclosure of "
        "aggregate HSE statistics to this external recipient.",
    )


class RpMemberRead(ApiModel):
    id: uuid.UUID
    kind: RpMemberKind
    user: UserRef | None
    display_name_en: str | None
    display_name_ar: str | None
    organisation: str | None
    email: str | None
    language: RpLanguage


class RpDistributionList(ApiModel):
    project_id: uuid.UUID
    report_type: RpType
    members: list[RpMemberRead]


class RpDistributionUpdate(StrictInput):
    members: list[RpMemberInput]


class RpDeliveryRead(ApiModel):
    id: uuid.UUID
    pack_doc_no: str
    revision: int
    member: str
    channel: RpChannel
    attachments: list[str]
    subject: str | None
    status: RpDeliveryStatus
    error: str | None
    sent_at: datetime


class RpDeliveryPage(Page[RpDeliveryRead]):
    pass


# ---- generic export ------------------------------------------------------------------------------


class XpColumnRead(ApiModel):
    column_code: str
    label_en: str
    label_ar: str
    pdpl_class: XpPdpl
    needs_capability: str | None
    mask_mode: XpMaskMode | None
    default: bool
    allowed: bool = Field(description="The caller may export this column unmasked")


class XpDatasetRead(ApiModel):
    dataset_code: str
    owner_module: str
    view_capability: str
    export_capability: str
    label_en: str
    label_ar: str
    columns: list[XpColumnRead]
    purpose_required_when: XpPurposeRule
    aggregate: bool
    pdf_allowed: bool
    project_required: bool


class XpDatasetList(ApiModel):
    items: list[XpDatasetRead]


class XpExportRequest(StrictInput):
    """EX-1…EX-9. `columns` empty = the dataset's de-identified default set."""

    dataset: str = Field(max_length=40)
    format: XpFormat = XpFormat.csv
    project_id: uuid.UUID | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    purpose: XpPurpose | None = None
    purpose_text: str | None = Field(default=None, max_length=500)


class XpJobRead(ApiModel):
    id: uuid.UUID
    export_no: str
    dataset: str
    format: XpFormat
    project_id: uuid.UUID | None
    filters: dict[str, Any]
    columns: list[str]
    notes: list[str]
    purpose: XpPurpose | None
    purpose_text: str | None
    row_count: int | None
    sha256: str | None
    contains_personal: bool
    contains_sensitive: bool
    status: XpJobStatus
    expires_at: datetime | None
    requested_by: UserRef | None
    created_at: datetime
    ready_at: datetime | None


class XpJobPage(Page[XpJobRead]):
    pass


class XpFileUrl(ApiModel):
    url: str
    expires_at: datetime


class XpSubscriptionCreate(StrictInput):
    dataset: str = Field(max_length=40)
    project_id: uuid.UUID | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    format: XpFormat = XpFormat.csv
    frequency: XpFrequency


class XpSubscriptionRead(ApiModel):
    id: uuid.UUID
    dataset: str
    project_id: uuid.UUID | None
    filters: dict[str, Any]
    columns: list[str]
    format: XpFormat
    frequency: XpFrequency
    active: bool
    last_run_at: datetime | None


class XpSubscriptionList(ApiModel):
    items: list[XpSubscriptionRead]


# ---- KPIs ---------------------------------------------------------------------------------------


class ScBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class ScBreakdown(ApiModel):
    metric: str
    group_by: ScKpiGroupBy
    rows: list[ScBreakdownRow]


class ScKpiResponse(ApiModel):
    """GET /kpi/scorecards: K-132…K-135 (GK-1)."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[ScBreakdown]
    grade_mix: dict[str, int]
    watch_by_level: dict[str, int]
    notes: list[str]
