"""Phase 6d schemas — field assurance (spec 6d-field-assurance v1.0).

Percentages are decimal strings with 1 dp ("93.1"); weights with 3 dp. Photos, signatures and
sheet photos are sent inline (base64, ≤ 5 MB each after on-device compression) so an offline
submission is one request; the server strips EXIF (EXE-5) and stores them as attachments.
Attendance names are returned only to holders of capability 199 in scope; photos never to the
Viewer/Client (P6d-3, P6d-4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.access_enums import WorkerLanguage
from app.core.enums import ZoneType
from app.core.field_enums import (
    AttendanceMethod,
    AuditAction,
    AuditGrade,
    AuditStatus,
    AuditType,
    CampaignAction,
    CampaignReason,
    CampaignStatus,
    FieldActionKind,
    FieldKpiGroupBy,
    FindingSeverity,
    InstructedRole,
    ItemType,
    LinkedRefKind,
    OptionMapping,
    ProgrammeLineStatus,
    ProgrammeScope,
    ResponseOwnerType,
    ResponseResult,
    StopOrderStatus,
    StopRule,
    SuggestionSource,
    TalkShift,
    TalkStatus,
    TemplateKind,
    TopicCategory,
    UnderstoodLanguage,
    VersionAction,
    VersionStatus,
)
from app.core.hse_enums import CaStatus, ControlLevel, InspectionType
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef
from app.schemas.kpi import KpiContext, KpiValue

# ---- reference (§3.15) ---------------------------------------------------------------------------


class FieldRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    value: str | None = Field(default=None, description="AG: lower bound of the grade (score %).")


class FieldReference(ApiModel):
    """GET /field-reference: lists IT, FS, AT, AF, AG, topic categories, instructed roles and
    campaign reasons with EN/AR labels."""

    item_types: list[FieldRefItem]
    finding_severities: list[FieldRefItem]
    audit_types: list[FieldRefItem]
    audit_finding_grades: list[FieldRefItem]
    audit_grades: list[FieldRefItem]
    topic_categories: list[FieldRefItem]
    instructed_roles: list[FieldRefItem]
    campaign_reasons: list[FieldRefItem]


# ---- settings (§3.14) ----------------------------------------------------------------------------


class FieldSettingsRead(ApiModel):
    project_id: uuid.UUID
    inspection_template_required_from: date | None
    toolbox_register_from: date | None
    inspection_pass_mark_pct: str
    repeat_finding_days: int
    contractor_audit_months: int
    system_audit_months: int
    first_audit_grace_days: int
    audit_report_days: int
    offline_submit_max_hours: int
    offline_cache_hours: int
    tbt_min_minutes: int
    tbt_edit_window_hours: int
    campaign_default_days: int
    inspection_coverage_warning_pct: str
    audit_programme_warning_pct: str
    tbt_reach_warning_pct: str
    critical_fail_warning_per_100: str
    photo_retention_months: int


class FieldSettingsUpdate(PatchInput):
    """Capability 193 (HSE Manager). Values outside "Allowed" → 422; loosening values (lower pass
    mark, shorter repeat window, longer audit interval, later switch date) → 422
    SETTING_LOOSENING. Switch dates: ≥ project start, ≤ today; once set only move earlier."""

    inspection_template_required_from: date | None = None
    toolbox_register_from: date | None = None
    inspection_pass_mark_pct: Decimal | None = Field(default=None, ge=50, le=100)
    repeat_finding_days: int | None = Field(default=None, ge=1, le=90)
    contractor_audit_months: int | None = Field(default=None, ge=3, le=24)
    system_audit_months: int | None = Field(default=None, ge=3, le=24)
    first_audit_grace_days: int | None = Field(default=None, ge=1, le=90)
    audit_report_days: int | None = Field(default=None, ge=3, le=14)
    offline_submit_max_hours: int | None = Field(default=None, ge=12, le=72)
    offline_cache_hours: int | None = Field(default=None, ge=24, le=72)
    tbt_min_minutes: int | None = Field(default=None, ge=1, le=30)
    tbt_edit_window_hours: int | None = Field(default=None, ge=4, le=48)
    campaign_default_days: int | None = Field(default=None, ge=1, le=30)
    inspection_coverage_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    audit_programme_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    tbt_reach_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    critical_fail_warning_per_100: Decimal | None = Field(default=None, ge=1, le=20)
    photo_retention_months: int | None = Field(default=None, ge=12, le=60)


# ---- templates (§3.1, §3.2) ----------------------------------------------------------------------


class TemplateSection(ApiModel):
    code: str = Field(min_length=1, max_length=4, examples=["A"])
    title_en: str = Field(max_length=150)
    title_ar: str = Field(default="", max_length=150)
    order: int = 0


class NumericRule(ApiModel):
    unit: str = Field(max_length=20, examples=["ms"])
    min: Decimal
    max: Decimal


class ItemOption(ApiModel):
    code: str = Field(min_length=1, max_length=20)
    label_en: str = Field(max_length=150)
    label_ar: str = Field(default="", max_length=150)
    maps_to: OptionMapping


class TemplateItem(ApiModel):
    item_code: str = Field(pattern=r"^[A-Z]{2,8}-[0-9]{2,3}$", examples=["GSI-05"])
    section_code: str = Field(max_length=4)
    order: int = 0
    text_en: str = Field(max_length=300)
    text_ar: str = Field(default="", max_length=300)
    guidance_en: str | None = Field(default=None, max_length=1000)
    guidance_ar: str | None = Field(default=None, max_length=1000)
    item_type: ItemType
    weight: int = Field(default=1, description="1–5 (TPL-2); critical default 3.")
    critical: bool = False
    stop_rule: StopRule = StopRule.none
    na_allowed: bool = False
    photo_required_on_fail: bool = Field(default=False, description="Forced true when critical.")
    default_severity: FindingSeverity | None = Field(
        default=None, description="Non-critical scored items: minor or major."
    )
    airside_only: bool = False
    numeric_rule: NumericRule | None = None
    options: list[ItemOption] | None = None
    suggested_ca_en: str | None = Field(default=None, max_length=300)
    suggested_ca_ar: str | None = Field(default=None, max_length=300)
    suggested_control_level: ControlLevel | None = None
    reference: str | None = Field(default=None, max_length=80)


class TemplateCreate(StrictInput):
    """Capability 192. A new code starts at v1; an existing code gets the next version (Draft)."""

    template_code: str = Field(pattern=r"^[A-Z]{2,8}$", examples=["GSI"])
    kind: TemplateKind
    inspection_type: InspectionType | None = None
    audit_type: AuditType | None = None
    title_en: str = Field(min_length=1, max_length=150)
    title_ar: str = Field(default="", max_length=150)
    sections: list[TemplateSection] = Field(default_factory=list)
    items: list[TemplateItem] = Field(default_factory=list)
    zone_types: list[ZoneType] = Field(
        default_factory=lambda: [ZoneType.airside, ZoneType.landside, ZoneType.other]
    )
    project_ids: list[uuid.UUID] = Field(default_factory=list)
    pass_mark_pct: Decimal = Field(default=Decimal("85.0"), ge=50, le=100)
    change_note: str | None = Field(default=None, max_length=500)


class TemplateUpdate(PatchInput):
    """Drafts only (Published → 409 TEMPLATE_IMMUTABLE, TPL-3)."""

    title_en: str | None = Field(default=None, min_length=1, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    sections: list[TemplateSection] | None = None
    items: list[TemplateItem] | None = None
    zone_types: list[ZoneType] | None = None
    project_ids: list[uuid.UUID] | None = None
    pass_mark_pct: Decimal | None = Field(default=None, ge=50, le=100)
    change_note: str | None = Field(default=None, max_length=500)


class VersionTransition(StrictInput):
    """publish (193; TPL-2 / TBT-1 completeness, supersedes the Published version) · retire (193,
    reason ≥ 20 chars; TPL-5)."""

    action: VersionAction
    reason: str | None = Field(default=None, max_length=500)


class TemplateRead(ApiModel):
    id: uuid.UUID
    template_code: str
    version: int
    kind: TemplateKind
    inspection_type: InspectionType | None
    audit_type: AuditType | None
    title_en: str
    title_ar: str
    sections: list[TemplateSection]
    items: list[TemplateItem]
    zone_types: list[ZoneType]
    project_ids: list[uuid.UUID]
    pass_mark_pct: str
    review_due_on: date | None
    review_overdue: bool
    change_note: str | None
    authored_by: UserRef | None
    published_by: UserRef | None
    published_at: datetime | None
    status: VersionStatus
    status_reason: str | None
    item_count: int
    critical_count: int


class TemplatePage(Page[TemplateRead]):
    pass


# ---- topics (§3.10) ------------------------------------------------------------------------------


class TopicTranslation(ApiModel):
    language: WorkerLanguage
    key_points: list[str] = Field(max_length=10)
    reviewed_by_name_role: str | None = Field(default=None, max_length=150)


class LinkedRef(ApiModel):
    kind: LinkedRefKind
    ref: str = Field(max_length=60, examples=["INC-ANIA-EXP-2026-0147", "GSI-05"])


class TopicCreate(StrictInput):
    """Capability 192. A new code starts at v1; an existing code gets the next version."""

    topic_code: str = Field(pattern=r"^TT-[0-9]{3}$", examples=["TT-014"])
    category: TopicCategory
    title_en: str = Field(min_length=1, max_length=150)
    title_ar: str = Field(default="", max_length=150)
    key_points_en: list[str] = Field(default_factory=list, max_length=10)
    key_points_ar: list[str] = Field(default_factory=list, max_length=10)
    translations: list[TopicTranslation] = Field(default_factory=list)
    linked_refs: list[LinkedRef] = Field(default_factory=list)


class TopicUpdate(PatchInput):
    category: TopicCategory | None = None
    title_en: str | None = Field(default=None, min_length=1, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    key_points_en: list[str] | None = Field(default=None, max_length=10)
    key_points_ar: list[str] | None = Field(default=None, max_length=10)
    translations: list[TopicTranslation] | None = None
    linked_refs: list[LinkedRef] | None = None


class TopicRead(ApiModel):
    id: uuid.UUID
    topic_code: str
    version: int
    category: TopicCategory
    title_en: str
    title_ar: str
    key_points_en: list[str]
    key_points_ar: list[str]
    translations: list[TopicTranslation]
    linked_refs: list[LinkedRef]
    review_due_on: date | None
    review_overdue: bool
    published_at: datetime | None
    status: VersionStatus
    status_reason: str | None


class TopicPage(Page[TopicRead]):
    pass


# ---- execution (§3.4–§3.6, EXE, FND) -------------------------------------------------------------


class PhotoInput(StrictInput):
    file_name: str = Field(max_length=120, examples=["edge.jpg"])
    content_base64: str = Field(description="jpg / png, ≤ 5 MB decoded; EXIF stripped on receipt.")


class AnswerInput(StrictInput):
    """`answer`: yes_no compliant / non_compliant / na; rating_0_3 "0"–"3" or "na"; single_select
    the option code or "na"; text the text. numeric → `numeric_value`; count → `count_value`.
    A non-compliant answer needs a note ≥ 10 chars and, where photo_required_on_fail, a photo."""

    item_code: str = Field(max_length=12)
    answer: str | None = Field(default=None, max_length=500)
    numeric_value: Decimal | None = None
    count_value: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=3)
    equipment_ref: str | None = Field(
        default=None, max_length=80, description="Scanned EQ / EA token or tag (EXE-8)."
    )
    severity: FindingSeverity | None = Field(
        default=None, description="Raise the finding severity / grade (never lower, FND-1)."
    )
    fixed_on_spot: bool = Field(default=False, description="Minor findings only (FND-3).")
    ca_required: bool = Field(default=False, description="Minor finding: create a CA (FND-3).")
    finding_description_en: str | None = Field(default=None, max_length=1000)
    finding_description_ar: str | None = Field(default=None, max_length=1000)


class ManualFindingInput(StrictInput):
    """FND-2 / AUD-2: findings not tied to an item (no effect on the score)."""

    severity: FindingSeverity
    description_en: str | None = Field(default=None, max_length=1000)
    description_ar: str | None = Field(default=None, max_length=1000)
    ca_required: bool = False
    fixed_on_spot: bool = False
    responsible_engagement_id: uuid.UUID | None = None


class StopWorkInput(StrictInput):
    """FND-7 (required when a stop_work item is non-compliant)."""

    activity_en: str | None = Field(default=None, max_length=300)
    activity_ar: str | None = Field(default=None, max_length=300)
    instructed_role: InstructedRole
    instructed_at: datetime
    permit_ids: list[uuid.UUID] = Field(default_factory=list)


class SubmissionCreate(StrictInput):
    """POST /projects/{id}/checklist-submissions: one inspection response (planned instance or
    unplanned). Idempotent on client_uuid (EXE-6): a repeat returns the stored record."""

    client_uuid: uuid.UUID
    inspection_id: uuid.UUID | None = Field(
        default=None, description="A Planned or Missed instance; null = unplanned inspection."
    )
    template_id: uuid.UUID | None = Field(
        default=None, description="The pinned version (TPL-4); default the Published version."
    )
    template_code: str | None = Field(default=None, max_length=8)
    site_id: uuid.UUID | None = Field(default=None, description="Unplanned only.")
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    started_at: datetime
    completed_at: datetime
    answers: list[AnswerInput]
    manual_findings: list[ManualFindingInput] = Field(default_factory=list)
    stop_work: StopWorkInput | None = None


class AnswerRead(ApiModel):
    item_code: str
    item_type: ItemType
    answer: str | None
    numeric_value: str | None = None
    count_value: int | None = None
    note: str | None = None
    photo_ids: list[uuid.UUID] = Field(default_factory=list)
    equipment_ref: str | None = None
    applicable: bool
    compliant: bool | None
    earned_weight: str | None
    raise_defect_for: str | None = Field(
        default=None, description='EXE-8: "Raise a defect for <tag>" (Phase 4 DF-10, manual).'
    )


class FieldFindingRead(ApiModel):
    id: uuid.UUID
    finding_no: str
    owner_ref: str
    item_code: str | None
    item_text_en: str | None
    item_text_ar: str | None
    severity: FindingSeverity
    critical_item: bool
    description_en: str | None
    description_ar: str | None
    repeat_of: str | None = Field(description="finding_no of the earlier non-compliance (FND-5).")
    fixed_on_spot: bool
    ca_required: bool
    ca_id: uuid.UUID | None
    ca_ref: str | None
    ca_status: CaStatus | None
    responsible_engagement: EngagementRef | None
    site: SiteRef
    zone: ZoneRef | None
    completed_date: date | None
    voided: bool


class FieldFindingPage(Page[FieldFindingRead]):
    pass


class SectionScore(ApiModel):
    section_code: str
    title_en: str
    title_ar: str
    applicable_weight: str
    earned_weight: str
    score_pct: str | None


class ResponseRead(ApiModel):
    id: uuid.UUID
    client_uuid: uuid.UUID
    owner_type: ResponseOwnerType
    inspection_id: uuid.UUID | None
    inspection_ref: str | None
    audit_id: uuid.UUID | None
    template_id: uuid.UUID
    template_code: str
    template_version: int
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef | None
    started_at: datetime | None
    completed_at: datetime | None
    received_at: datetime | None
    offline_delay_min: int | None
    recorded_offline: bool = Field(description='EXE-7: shown as "recorded offline".')
    inspector: UserRef | None
    answers: list[AnswerRead]
    applicable_count: int
    compliant_count: int
    applicable_weight: str
    earned_weight: str
    score_pct: str | None = Field(description="1 dp; null when nothing is applicable (§6.2).")
    pass_mark_pct: str | None
    critical_fail_count: int
    result: ResponseResult | None
    grade: AuditGrade | None
    section_scores: list[SectionScore]
    findings: list[FieldFindingRead]
    stop_work_order_id: uuid.UUID | None
    stop_work_order_no: str | None
    self_inspection: bool
    submitted: bool
    voided: bool
    warnings: list[ApiWarning]


class InspectionVoid(StrictInput):
    """Capability 201 (EXE-9); reason ≥ 20 chars."""

    reason: str = Field(min_length=1, max_length=500)


# ---- stop-work orders (§3.9, §4.3) ---------------------------------------------------------------


class PermitBrief(ApiModel):
    id: uuid.UUID
    permit_no: str


class StopWorkRead(ApiModel):
    id: uuid.UUID
    order_no: str
    response_id: uuid.UUID
    inspection_ref: str | None
    item_code: str
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef | None
    activity_en: str | None
    activity_ar: str | None
    instructed_role: InstructedRole
    instructed_at: datetime
    raised_at: datetime
    received_at: datetime
    recorded_offline: bool
    permits: list[PermitBrief]
    ca_id: uuid.UUID | None
    ca_ref: str | None
    ca_status: CaStatus | None
    released_by: UserRef | None
    released_at: datetime | None
    release_note: str | None
    release_photo_ids: list[uuid.UUID]
    status: StopOrderStatus
    status_reason: str | None


class StopWorkPage(Page[StopWorkRead]):
    pass


class StopWorkRelease(StrictInput):
    """Capability 196 (FND-8): the CA In Progress, Pending Verification or Closed; note ≥ 20
    chars; ≥ 1 photo."""

    release_note: str = Field(min_length=1, max_length=1000)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=4)


class FieldVoid(StrictInput):
    """Capability 201; reason ≥ 20 chars."""

    reason: str = Field(min_length=1, max_length=500)


# ---- audits (§3.7, §3.8, §4.4) -------------------------------------------------------------------


class AuditCreate(StrictInput):
    """Capability 194 (AUD-1…AUD-3)."""

    audit_type: AuditType
    template_code: str = Field(max_length=8)
    auditee_engagement_id: uuid.UUID | None = None
    site_ids: list[uuid.UUID] = Field(min_length=1)
    lead_auditor_id: uuid.UUID
    team_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    planned_start: date
    planned_end: date


class AuditUpdate(PatchInput):
    team_ids: list[uuid.UUID] | None = Field(default=None, max_length=5)
    site_ids: list[uuid.UUID] | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    fieldwork_start: date | None = None
    fieldwork_end: date | None = None
    opening_meeting_at: datetime | None = None
    closing_meeting_at: datetime | None = None
    auditee_attendee_roles: str | None = Field(default=None, max_length=300)
    summary_en: str | None = Field(default=None, max_length=3000)
    summary_ar: str | None = Field(default=None, max_length=3000)


class AuditAnswers(StrictInput):
    """PUT /field-audits/{id}/answers: save answers (server draft; Planned → In Progress)."""

    answers: list[AnswerInput]
    manual_findings: list[ManualFindingInput] = Field(default_factory=list)


class AuditTransition(StrictInput):
    """start (lead) · complete_fieldwork (lead; EXE-2, closing meeting) · issue (195 ≠ lead;
    summary; AUD-4) · cancel (194, Planned, reason ≥ 20) · void (201, reason ≥ 20)."""

    action: AuditAction
    reason: str | None = Field(default=None, max_length=500)
    ca_for_observations: bool = Field(
        default=False, description="Issue: also create CAs for observations and OFIs (AUD-4)."
    )


class AuditRead(ApiModel):
    id: uuid.UUID
    audit_no: str
    project_id: uuid.UUID
    audit_type: AuditType
    template_code: str
    template_version: int | None
    auditee_engagement: EngagementRef | None
    sites: list[SiteRef]
    lead_auditor: UserRef | None
    team: list[UserRef]
    planned_start: date
    planned_end: date
    fieldwork_start: date | None
    fieldwork_end: date | None
    opening_meeting_at: datetime | None
    closing_meeting_at: datetime | None
    auditee_attendee_roles: str | None
    report_due_by: date | None
    response: ResponseRead | None
    summary_en: str | None
    summary_ar: str | None
    report_en_id: uuid.UUID | None
    report_ar_id: uuid.UUID | None
    issued_by: UserRef | None
    issued_at: datetime | None
    closed_at: datetime | None
    status: AuditStatus
    status_reason: str | None


class AuditPage(Page[AuditRead]):
    pass


class ProgrammeItem(ApiModel):
    due_by: date
    audit_no: str | None
    fieldwork_end: date | None
    met_on_time: bool


class ProgrammeLineRead(ApiModel):
    scope: ProgrammeScope
    engagement: EngagementRef | None
    audit_type: AuditType
    frequency_months: int
    line_start: date
    due_by: date
    last_satisfied_by: str | None = Field(description="audit_no of the last satisfying audit.")
    status: ProgrammeLineStatus
    items: list[ProgrammeItem] = Field(description="K-114 items (due_by ≤ as_of).")


class AuditProgramme(ApiModel):
    project_id: uuid.UUID
    as_of: date
    lines: list[ProgrammeLineRead]


# ---- toolbox talks (§3.11, §3.12) ----------------------------------------------------------------


class TalkTopicInput(StrictInput):
    """A library topic (topic_id = a Published version) or a free title with a category."""

    topic_id: uuid.UUID | None = None
    free_title_en: str | None = Field(default=None, max_length=150)
    free_title_ar: str | None = Field(default=None, max_length=150)
    category: TopicCategory | None = None


class AttendanceInput(StrictInput):
    """card_scan: `scanned_token` (offline: the raw HSE2:AC:… payload, resolved at sync and then
    deleted) or `deployment_id`; list: `deployment_id`. `signature`: drawn image (optional)."""

    method: AttendanceMethod
    deployment_id: uuid.UUID | None = None
    scanned_token: str | None = Field(default=None, max_length=80)
    signature: PhotoInput | None = None


class TalkCreate(StrictInput):
    """Capability 198 (TBT-3…TBT-7). Idempotent on client_uuid."""

    client_uuid: uuid.UUID
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    host_engagement_id: uuid.UUID
    shift: TalkShift
    delivered_at: datetime
    duration_minutes: int = Field(description="5–120 (TBT-4).")
    presenter_user_id: uuid.UUID | None = None
    presenter_deployment_id: uuid.UUID | None = None
    topics: list[TalkTopicInput] = Field(min_length=1, max_length=3)
    language: WorkerLanguage
    interpreter_languages: list[WorkerLanguage] = Field(default_factory=list)
    campaign_id: uuid.UUID | None = None
    attendance: list[AttendanceInput] = Field(default_factory=list)
    unnamed_count: int = Field(default=0, ge=0, le=200)
    sheet_photos: list[PhotoInput] = Field(default_factory=list, max_length=4)
    questions_raised: str | None = Field(default=None, max_length=1000)


class AttendanceAdd(StrictInput):
    """Add rows until Locked (TBT-8)."""

    rows: list[AttendanceInput] = Field(min_length=1)


class AttendanceRowRead(ApiModel):
    id: uuid.UUID
    deployment_id: uuid.UUID | None = Field(description="Only with capability 199.")
    worker_no: str | None = Field(description="Only with capability 199.")
    name_en: str | None = Field(description="Only with capability 199.")
    name_ar: str | None = Field(description="Only with capability 199.")
    engagement: EngagementRef | None
    method: AttendanceMethod
    signed: bool
    understood_language: UnderstoodLanguage
    counted_person_type: str


class RejectedRow(ApiModel):
    code: str = Field(examples=["TOKEN_UNKNOWN"])
    message: str
    message_ar: str | None = None
    index: int


class TalkTopicRead(ApiModel):
    topic_id: uuid.UUID | None
    topic_code: str | None
    version: int | None
    title_en: str
    title_ar: str
    category: TopicCategory | None


class TalkRead(ApiModel):
    id: uuid.UUID
    talk_no: str
    project_id: uuid.UUID
    site: SiteRef
    zones: list[ZoneRef]
    host_engagement: EngagementRef | None
    shift: TalkShift
    delivered_at: datetime
    duration_minutes: int
    presenter_name: str | None
    recorded_by: UserRef | None
    topics: list[TalkTopicRead]
    language: WorkerLanguage
    interpreter_languages: list[WorkerLanguage]
    campaign_id: uuid.UUID | None
    campaign_no: str | None
    attendance: list[AttendanceRowRead]
    named_count: int
    briefed_count: int
    unnamed_count: int
    sheet_photo_ids: list[uuid.UUID]
    questions_raised: str | None
    received_at: datetime | None
    offline_delay_min: int | None
    recorded_offline: bool
    rejected_rows: list[RejectedRow]
    warnings: list[ApiWarning]
    locks_at: datetime
    status: TalkStatus
    status_reason: str | None


class TalkPage(Page[TalkRead]):
    pass


class SuggestionRead(ApiModel):
    topic_id: uuid.UUID
    topic_code: str
    version: int
    title_en: str
    title_ar: str
    category: TopicCategory
    source: SuggestionSource
    reason_ref: str | None = Field(description="Campaign no, incident ref, item code or category.")
    delivered_recently: bool = Field(description="Delivered by the host on the site in 7 days.")


class SuggestionList(ApiModel):
    items: list[SuggestionRead]


# ---- campaigns (§3.13, §4.5) ---------------------------------------------------------------------


class CampaignCreate(StrictInput):
    """Capability 197 (Draft)."""

    topic_id: uuid.UUID
    reason: CampaignReason
    reason_ref: str | None = Field(default=None, max_length=60)
    message_en: str | None = Field(default=None, max_length=1000)
    message_ar: str | None = Field(default=None, max_length=1000)
    site_ids: list[uuid.UUID] = Field(min_length=1)
    due_date: date | None = Field(default=None, description="Default issue + campaign days.")


class CampaignUpdate(PatchInput):
    reason_ref: str | None = Field(default=None, max_length=60)
    message_en: str | None = Field(default=None, max_length=1000)
    message_ar: str | None = Field(default=None, max_length=1000)
    site_ids: list[uuid.UUID] | None = None
    due_date: date | None = None


class CampaignTransition(StrictInput):
    action: CampaignAction
    reason: str | None = Field(default=None, max_length=500)


class CampaignPair(ApiModel):
    engagement: EngagementRef | None
    site: SiteRef
    met: bool
    met_on: date | None
    on_time: bool | None
    talk_no: str | None


class CampaignRead(ApiModel):
    id: uuid.UUID
    campaign_no: str
    project_id: uuid.UUID
    topic_id: uuid.UUID
    topic_code: str
    topic_version: int
    topic_title_en: str
    topic_title_ar: str
    reason: CampaignReason
    reason_ref: str | None
    message_en: str | None
    message_ar: str | None
    sites: list[SiteRef]
    pairs: list[CampaignPair]
    met_count: int
    issued_by: UserRef | None
    issued_at: datetime | None
    due_date: date | None
    status: CampaignStatus
    status_reason: str | None
    warnings: list[ApiWarning]


class CampaignPage(Page[CampaignRead]):
    pass


# ---- board, offline pack (§8.1, §8.2, EXE-6) -----------------------------------------------------


class FieldActionItem(ApiModel):
    kind: FieldActionKind
    label_en: str
    label_ar: str
    count: int
    refs: list[str] = Field(description="Order numbers, plan names, engagement@site, line refs…")


class FieldActionPanel(ApiModel):
    project_id: uuid.UUID
    as_of: date
    items: list[FieldActionItem]


class FieldBand(ApiModel):
    """§8.1 item 2 (live)."""

    project_id: uuid.UUID
    stop_work_active: int
    critical_failures_today: int
    not_inspected_this_week: int
    campaigns_unmet: int
    audits_due_30_days: int


class OfflineDeployment(ApiModel):
    """EXE-6 / P6d-6: no ID numbers, no card tokens."""

    deployment_id: uuid.UUID
    worker_no: str
    name_en: str
    name_ar: str
    trade: str
    primary_language: WorkerLanguage
    engagement_id: uuid.UUID | None


class OfflineInstance(ApiModel):
    inspection_id: uuid.UUID
    ref: str
    planned_date: date | None
    site_id: uuid.UUID
    zone_id: uuid.UUID | None
    engagement_id: uuid.UUID | None
    template_id: uuid.UUID | None


class OfflinePack(ApiModel):
    """GET /projects/{id}/field-offline-pack: cache for `offline_cache_hours` (delete at logout)."""

    project_id: uuid.UUID
    generated_at: datetime
    expires_at: datetime
    instances: list[OfflineInstance]
    templates: list[TemplateRead]
    topics: list[TopicRead]
    deployments: list[OfflineDeployment]


# ---- KPIs (§6.7, FM-1…FM-3) ----------------------------------------------------------------------


class FieldBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None
    note: str | None = Field(default=None, description='FM-3 "small sample" (< 5 applicable).')


class FieldBreakdown(ApiModel):
    metric: str
    group_by: FieldKpiGroupBy
    rows: list[FieldBreakdownRow]


class FieldKpiResponse(ApiModel):
    """GET /kpi/field-assurance: K-34, K-35, K-36 and K-110…K-117 (aggregates only, FM-2).
    `notes`: the K-36 source and SRC-3 reconciliation, "checklist-based from <date>"."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[FieldBreakdown]
    notes: list[str]
