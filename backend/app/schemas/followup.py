"""Phase 6f schemas — incident follow-up (spec 6f-incident-followup v1.0).

Every schema carries the `Fu` prefix (DECISIONS D-202). Percentages are decimal strings with 1 dp.
Pack snapshots of the `identity` / `identity_medical` field sets are returned only to holders of
capability 29 (and 30 for medical) in scope; Viewer / Client never sees packs or evidence files
(P6f-5). Files travel inline as base64 (`FuFileInput`, ≤ 5 MB each)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.field_enums import TopicCategory
from app.core.followup_enums import (
    FuAckResponse,
    FuActionKind,
    FuChangeStatus,
    FuChannel,
    FuCheckStatus,
    FuClientIdentity,
    FuDeadlineBasis,
    FuDistributionStatus,
    FuEffectResult,
    FuFieldSet,
    FuFiler,
    FuForm,
    FuKpiGroupBy,
    FuLessonAction,
    FuLessonSource,
    FuLessonStatus,
    FuLinkKind,
    FuPackAction,
    FuPackStatus,
    FuRecipientRole,
    FuRequirementStatus,
    FuRuleSource,
    FuStage,
    FuSubmissionStatus,
    FuTrigger,
    FuWaiverReason,
)
from app.core.hse_enums import (
    Activity,
    ControlLevel,
    DangerousOccurrenceCategory,
    ExternalBody,
    InvestigationLevel,
    Mechanism,
    Trade,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.kpi import KpiContext, KpiValue

# ---- shared ----------------------------------------------------------------------------------


class FuFileInput(StrictInput):
    """A file sent inline (base64). PDF, PNG, JPEG, EML or TXT; ≤ 5 MB decoded."""

    file_name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4)
    content_type: str | None = Field(default=None, max_length=100)


class FuRefItem(ApiModel):
    code: str
    label_en: str
    label_ar: str
    detail: str | None = None


class FuReference(ApiModel):
    """List NT, PF, FS, WV, bodies, stages, channels, statuses and responses with EN/AR labels."""

    lists: dict[str, list[FuRefItem]]


# ---- settings and profile (§3.2, §3.10) -------------------------------------------------------


class FuRecipient(ApiModel):
    organisation_en: str = Field(max_length=150)
    organisation_ar: str = Field(max_length=150)
    role: FuRecipientRole
    email: str | None = Field(default=None, max_length=200)


class FuDirectoryEntry(ApiModel):
    body: ExternalBody
    office_name_en: str = Field(max_length=150)
    office_name_ar: str = Field(max_length=150)
    address_or_portal: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=200)


class FuSettingsRead(ApiModel):
    project_id: uuid.UUID
    followup_rules_from: date | None
    notification_alert_lead_hours: int
    client_pack_identity: FuClientIdentity
    client_identity_clause: str | None
    lesson_required_levels: list[InvestigationLevel]
    lesson_publish_days: int
    lesson_ack_days: int
    lesson_effectiveness_days: int
    followup_warning_pct: str
    lesson_ack_warning_pct: str
    client_recipients: list[FuRecipient]
    body_directory: list[FuDirectoryEntry]
    signatory_role_en: str | None
    signatory_role_ar: str | None


class FuSettingsUpdate(PatchInput):
    """Capability 218 (HSE Manager). Loosening → 422 SETTING_LOOSENING (§3.10)."""

    followup_rules_from: date | None = None
    notification_alert_lead_hours: int | None = Field(default=None, ge=2, le=48)
    client_pack_identity: FuClientIdentity | None = None
    client_identity_clause: str | None = Field(default=None, max_length=1000)
    lesson_required_levels: list[InvestigationLevel] | None = None
    lesson_publish_days: int | None = Field(default=None, ge=3, le=30)
    lesson_ack_days: int | None = Field(default=None, ge=1, le=14)
    lesson_effectiveness_days: int | None = Field(default=None, ge=30, le=180)
    followup_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    lesson_ack_warning_pct: Decimal | None = Field(default=None, ge=50, le=100)
    client_recipients: list[FuRecipient] | None = None
    body_directory: list[FuDirectoryEntry] | None = None
    signatory_role_en: str | None = Field(default=None, max_length=120)
    signatory_role_ar: str | None = Field(default=None, max_length=120)


class FuRuleRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    rule_code: str
    body: ExternalBody
    stage: FuStage
    source: FuRuleSource
    triggers: list[FuTrigger]
    trigger_params: dict[str, Any]
    deadline_hours: int | None
    deadline_basis: FuDeadlineBasis
    form_code: FuForm | None
    filer: FuFiler
    active: bool
    updated_at: datetime


class FuRuleList(ApiModel):
    items: list[FuRuleRead]


class FuRuleCreate(StrictInput):
    """A client / PMC row (capability 218; NR-3 client rows are edited freely)."""

    rule_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Z0-9-]+$")
    stage: FuStage
    triggers: list[FuTrigger] = Field(min_length=1)
    trigger_params: dict[str, Any] = Field(default_factory=dict)
    deadline_hours: int | None = Field(default=None, ge=1, le=720)
    deadline_basis: FuDeadlineBasis = FuDeadlineBasis.trigger
    form_code: FuForm | None = None
    active: bool = True


class FuRuleUpdate(PatchInput):
    """Statutory rows only tighten (NR-3: lower hours, add triggers) → else 422 RULE_LOOSENING."""

    non_nullable = frozenset({"triggers", "active", "filer"})

    triggers: list[FuTrigger] | None = None
    trigger_params: dict[str, Any] | None = None
    deadline_hours: int | None = Field(default=None, ge=1, le=720)
    form_code: FuForm | None = None
    filer: FuFiler | None = None
    active: bool | None = None


# ---- requirements (§3.3) ----------------------------------------------------------------------


class FuRequirementRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    incident_id: uuid.UUID
    incident_ref: str
    rule_code: str
    body: ExternalBody
    stage: FuStage
    source: FuRuleSource
    form_code: FuForm | None
    filer: FuFiler
    case_labels: list[str] = Field(description="Case person numbers, e.g. ['P1'] (no names).")
    trigger_met_at: datetime
    due_at: datetime
    filer_engagement_id: uuid.UUID | None
    filer_code: str | None
    responsible_code: str | None
    status: FuRequirementStatus
    trigger_note: str | None
    waiver_reason_code: FuWaiverReason | None
    waiver_text: str | None
    waiver_reference: str | None
    waived_at: datetime | None
    submission_no: str | None = Field(description="First valid submission.")
    submitted_at: datetime | None
    on_time: bool | None
    reference_no: str | None
    acknowledged_at: datetime | None
    pack_id: uuid.UUID | None = Field(description="Current (non-superseded) pack.")
    pack_no: str | None
    pack_status: FuPackStatus | None


FuRequirementPage = Page[FuRequirementRead]


class FuWaiverRequest(StrictInput):
    """NR-8 (capability 218). `body_confirmed_not_required` and `reported_by_other_party` need an
    evidence file; the latter also the other party's reference (WAIVER_EVIDENCE_REQUIRED)."""

    reason_code: FuWaiverReason
    text: str = Field(min_length=20, max_length=500)
    reference: str | None = Field(default=None, max_length=60)
    evidence_file: FuFileInput | None = None


# ---- packs (§3.4) -----------------------------------------------------------------------------


class FuPackCreate(StrictInput):
    """Generate (or regenerate: version + 1, the old one Superseded) the pack of a requirement."""

    narrative_en: str | None = Field(default=None, max_length=3000)
    narrative_ar: str | None = Field(default=None, max_length=3000)
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    languages: list[str] | None = Field(default=None, description="Client forms: ['en', 'ar'].")


class FuPackUpdate(PatchInput):
    narrative_en: str | None = Field(default=None, max_length=3000)
    narrative_ar: str | None = Field(default=None, max_length=3000)
    extra_fields: dict[str, Any] | None = None


class FuPackTransition(StrictInput):
    action: FuPackAction
    reason: str | None = Field(default=None, max_length=500)


class FuPackRead(ApiModel):
    id: uuid.UUID
    pack_no: str
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    incident_ref: str
    body: ExternalBody
    stage: FuStage
    version: int
    form_code: FuForm
    field_set: FuFieldSet
    languages: list[str]
    snapshot: dict[str, Any] | None = Field(
        description="Frozen field values (PK-2); null when the caller may not see the field set."
    )
    narrative_en: str | None
    narrative_ar: str | None
    extra_fields: dict[str, Any] | None
    has_file: bool
    prepared_by: UserRef | None
    approved_by: UserRef | None
    approved_at: datetime | None
    status: FuPackStatus
    incident_changed: bool = Field(description="PK-2: a snapshot field differs from the incident.")
    identity_deleted: bool = Field(description="P6f-4: identity removed at anonymisation.")
    warnings: list[ApiWarning] = Field(default_factory=list)
    created_at: datetime


FuPackPage = Page[FuPackRead]


# ---- submissions (§3.5) -----------------------------------------------------------------------


class FuSubmissionCreate(StrictInput):
    """SB-1…SB-3 (capability 216)."""

    pack_id: uuid.UUID | None = None
    channel: FuChannel
    submitted_at: datetime
    contacted_desk_en: str | None = Field(default=None, max_length=120)
    contacted_desk_ar: str | None = Field(default=None, max_length=120)
    reference_no: str | None = Field(default=None, max_length=60)
    call_note: str | None = Field(default=None, max_length=200)
    evidence_files: list[FuFileInput] = Field(default_factory=list, max_length=5)
    stamped_copy: FuFileInput | None = None
    external_document: FuFileInput | None = None


class FuSubmissionUpdate(PatchInput):
    """Editable by the recorder for 24 h (SB-5), then 409 SUBMISSION_LOCKED."""

    submitted_at: datetime | None = None
    contacted_desk_en: str | None = Field(default=None, max_length=120)
    contacted_desk_ar: str | None = Field(default=None, max_length=120)
    reference_no: str | None = Field(default=None, max_length=60)
    call_note: str | None = Field(default=None, max_length=200)


class FuSubmissionAck(StrictInput):
    acknowledged_at: datetime
    ack_reference: str | None = Field(default=None, max_length=60)
    ack_file: FuFileInput | None = None


class FuSubmissionVoid(StrictInput):
    reason: str = Field(min_length=20, max_length=500)


class FuSubmissionRead(ApiModel):
    id: uuid.UUID
    submission_no: str
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    incident_ref: str
    body: ExternalBody
    stage: FuStage
    pack_id: uuid.UUID | None
    pack_no: str | None
    channel: FuChannel
    submitted_at: datetime
    contacted_desk_en: str | None
    contacted_desk_ar: str | None
    reference_no: str | None
    call_note: str | None
    evidence_file_ids: list[uuid.UUID] | None = Field(description="Null for Viewer / Client.")
    has_external_document: bool
    acknowledged_at: datetime | None
    ack_reference: str | None
    on_time: bool
    status: FuSubmissionStatus
    void_reason: str | None
    recorded_by: UserRef | None
    created_at: datetime


FuSubmissionPage = Page[FuSubmissionRead]


# ---- lessons (§3.6-§3.9) ----------------------------------------------------------------------


class FuKeyLesson(ApiModel):
    text_en: str = Field(default="", max_length=500)
    text_ar: str = Field(default="", max_length=500)


class FuActionTaken(ApiModel):
    ca_ref: str
    control_level: ControlLevel | None = None


class FuApplicability(ApiModel):
    activities: list[Activity] = Field(default_factory=list)
    zone_types: list[str] = Field(default_factory=list)
    trades: list[Trade] = Field(default_factory=list)
    mechanisms: list[Mechanism] = Field(default_factory=list)
    do_categories: list[DangerousOccurrenceCategory] = Field(default_factory=list)


class FuLessonPhoto(StrictInput):
    """Keep an existing photo (attachment_id) or add one (file); redaction must be confirmed."""

    attachment_id: uuid.UUID | None = None
    file: FuFileInput | None = None
    redaction_confirmed: bool = False


class FuRemovedEngagement(ApiModel):
    project_id: uuid.UUID
    engagement_id: uuid.UUID
    reason: str = Field(min_length=20, max_length=500)


class FuLessonCreate(StrictInput):
    """A manual lesson (capability 219): from an incident with an investigation, or external."""

    source: FuLessonSource
    incident_id: uuid.UUID | None = None
    external_ref: str | None = Field(default=None, max_length=200)
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)


class FuLessonUpdate(PatchInput):
    """Draft edits by the author or 219 / 220 holders."""

    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    what_happened_en: str | None = Field(default=None, max_length=1500)
    what_happened_ar: str | None = Field(default=None, max_length=1500)
    why_en: str | None = Field(default=None, max_length=1500)
    why_ar: str | None = Field(default=None, max_length=1500)
    root_cause_codes: list[str] | None = None
    key_lessons: list[FuKeyLesson] | None = Field(default=None, max_length=5)
    applicability: FuApplicability | None = None
    photos: list[FuLessonPhoto] | None = Field(default=None, max_length=4)
    distribution_project_ids: list[uuid.UUID] | None = None
    removed_engagements: list[FuRemovedEngagement] | None = None


class FuLessonTransition(StrictInput):
    action: FuLessonAction
    comment: str | None = Field(default=None, max_length=500)
    superseded_by_lesson_id: uuid.UUID | None = None


class FuLinkRead(ApiModel):
    id: uuid.UUID
    kind: FuLinkKind
    ref: str
    project_id: uuid.UUID | None
    item_code: str | None
    proposed_text_en: str | None
    proposed_text_ar: str | None
    status: FuChangeStatus | None
    adopted_version: int | None
    reject_reason: str | None
    lesson_no: str | None = None
    created_at: datetime


class FuLinkCreate(StrictInput):
    """LK-1: (a) topic — link `ref` (an existing topic code) or open a Draft (ref omitted);
    (b) campaign — open a 6d campaign Draft on `project_id` for topic `ref`;
    (c) template_change — `ref` = template code, `item_code` or null for a new item."""

    kind: FuLinkKind
    ref: str | None = Field(default=None, max_length=40)
    project_id: uuid.UUID | None = None
    topic_category: TopicCategory | None = None
    item_code: str | None = Field(default=None, max_length=20)
    proposed_text_en: str | None = Field(default=None, max_length=1000)
    proposed_text_ar: str | None = Field(default=None, max_length=1000)


class FuLinkDecision(StrictInput):
    """LK-3: 193 holders reject an open change request (reason ≥ 20 chars)."""

    reason: str = Field(min_length=20, max_length=500)


class FuLinkPage(ApiModel):
    items: list[FuLinkRead]


class FuDistributionRead(ApiModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_no: str
    project_id: uuid.UUID
    project_code: str
    engagement_id: uuid.UUID
    engagement_code: str | None
    ack_due_on: date
    acknowledged_by: UserRef | None
    acknowledged_at: datetime | None
    response: FuAckResponse | None
    reason: str | None
    on_behalf_note: str | None
    status: FuDistributionStatus
    overdue: bool


class FuDistributionList(ApiModel):
    items: list[FuDistributionRead]


class FuAckRequest(StrictInput):
    """DS-3 (capability 221)."""

    response: FuAckResponse
    reason: str | None = Field(default=None, max_length=500)
    on_behalf_note: str | None = Field(default=None, max_length=500)


class FuCheckRead(ApiModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_no: str
    project_id: uuid.UUID | None
    due_on: date
    facts: dict[str, Any]
    suggested_result: FuEffectResult | None
    result: FuEffectResult | None
    rationale: str | None
    follow_up_ca_ref: str | None
    follow_up_lesson_no: str | None
    completed_by: UserRef | None
    completed_at: datetime | None
    status: FuCheckStatus
    overdue: bool


FuCheckPage = Page[FuCheckRead]


class FuFollowUpCa(StrictInput):
    owner_id: uuid.UUID
    title: str | None = Field(default=None, max_length=150)
    due_date: date | None = None


class FuCheckComplete(StrictInput):
    """EF-4 / EF-5 (capability 223)."""

    result: FuEffectResult
    rationale: str | None = Field(default=None, max_length=1000)
    follow_up_ca: FuFollowUpCa | None = None
    follow_up_lesson_id: uuid.UUID | None = None


class FuLessonRead(ApiModel):
    id: uuid.UUID
    lesson_no: str
    source: FuLessonSource
    incident_id: uuid.UUID | None
    incident_ref: str | None = Field(description="Hidden in the library for non-staff.")
    source_project_id: uuid.UUID | None
    source_project_code: str | None
    external_ref: str | None
    system_created: bool
    required: bool
    title_en: str | None
    title_ar: str | None
    what_happened_en: str | None
    what_happened_ar: str | None
    why_en: str | None
    why_ar: str | None
    root_cause_codes: list[str]
    key_lessons: list[FuKeyLesson]
    actions_taken: list[FuActionTaken]
    applicability: FuApplicability
    severity_potential: int | None
    photos: list[dict[str, Any]]
    distribution_project_ids: list[uuid.UUID]
    distribution_project_codes: list[str]
    removed_engagements: list[FuRemovedEngagement]
    publish_due_on: date | None
    author: UserRef | None
    approved_by: UserRef | None
    published_at: datetime | None
    archived_at: datetime | None
    superseded_by_lesson_no: str | None
    return_comment: str | None
    status_reason: str | None
    status: FuLessonStatus
    links: list[FuLinkRead]
    acknowledged: int
    distribution_items: int
    check: FuCheckRead | None
    warnings: list[ApiWarning] = Field(default_factory=list)
    created_at: datetime


class FuLessonListItem(ApiModel):
    id: uuid.UUID
    lesson_no: str
    title_en: str | None
    title_ar: str | None
    status: FuLessonStatus
    archived: bool
    source_project_code: str | None
    published_at: datetime | None
    publish_due_on: date | None
    month: str | None = Field(description="Publication month yyyy-mm (LL-2: month and year).")
    root_cause_codes: list[str]
    applicability: FuApplicability
    key_lessons: list[FuKeyLesson]


FuLessonPage = Page[FuLessonListItem]


class FuSimilarLessons(ApiModel):
    """LL-6: up to 3 Published lessons."""

    items: list[FuLessonListItem]


# ---- band, action panel, KPIs ------------------------------------------------------------------


class FuBand(ApiModel):
    """§8.1 item 2 (live)."""

    verbal_due_next_hour: list[FuRequirementRead]
    overdue: list[FuRequirementRead]
    packs_awaiting_approval: int
    lessons_publish_due_soon: list[str]


class FuActionItem(ApiModel):
    kind: FuActionKind
    count: int
    refs: list[str]


class FuActionPanel(ApiModel):
    items: list[FuActionItem]


class FuBreakdownRow(ApiModel):
    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None


class FuBreakdown(ApiModel):
    metric: str
    group_by: FuKpiGroupBy
    rows: list[FuBreakdownRow]


class FuKpiResponse(ApiModel):
    """GET /kpi/incident-followup: K-127…K-131 (aggregates only, FK-2)."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[FuBreakdown]
    notes: list[str]
