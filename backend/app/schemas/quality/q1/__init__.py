"""API schemas of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Part B). Every name carries the `Q` prefix (no clash in the OpenAPI contract)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from app.core.quality.common import (
    QAssigneeKind,
    QCriterionKind,
    QDiscipline,
    QNcrCategory,
    QNcrClass,
    QNcrStatus,
)
from app.core.quality.q1 import (
    QApprovalCode,
    QAsbuiltStatus,
    QDossierStatus,
    QIrCommentStatus,
    QIrResult,
    QIrStatus,
    QItpStatus,
    QPlanStatus,
    QPointType,
    QPunchCategory,
    QPunchRaisedDuring,
    QPunchStatus,
    QVerifyingRecord,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.field import AnswerInput, PhotoInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.quality.q0 import QLinkRead, QPaperSignoff, QSignoffRead

# ---- shared refs -------------------------------------------------------------------------------


class QCodeRef(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str | None = None


class QEngRef(ApiModel):
    id: uuid.UUID
    short_code: str
    legal_name_en: str
    legal_name_ar: str | None = None


class QBlockerRead(ApiModel):
    code: str
    detail_en: str
    detail_ar: str
    section: str | None = None
    letter: str | None = None


# ---- ITP ---------------------------------------------------------------------------------------


class QRpOverride(StrictInput):
    assignee_kind: QAssigneeKind
    assignee: str = Field(max_length=64, description="User id, role code or position code.")


class QItpPointInput(StrictInput):
    seq: int = Field(ge=1, le=9999)
    activity_en: str = Field(default="", max_length=200)
    activity_ar: str = Field(default="", max_length=200)
    characteristic_en: str = Field(default="", max_length=300)
    characteristic_ar: str = Field(default="", max_length=300)
    point_type: QPointType
    criteria_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Criteria library version ids."
    )
    acceptance_text_en: str | None = Field(default=None, max_length=500)
    acceptance_text_ar: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=120)
    verifying_record: QVerifyingRecord = QVerifyingRecord.ir
    checklist_template_code: str | None = Field(default=None, max_length=8)
    test_type_codes: list[str] = Field(default_factory=list, max_length=20)
    frequency_text: str | None = Field(default=None, max_length=120)
    frequency_qty: Decimal | None = None
    frequency_unit: str | None = Field(default=None, max_length=20)
    rp_override: QRpOverride | None = None
    notice_hours: int | None = Field(default=None, ge=0, le=168)
    competence_code: str | None = Field(default=None, max_length=40)


class QItpCreate(StrictInput):
    title_en: str = Field(default="", max_length=150)
    title_ar: str = Field(default="", max_length=150)
    discipline: QDiscipline
    work_package_en: str | None = Field(default=None, max_length=150)
    work_package_ar: str | None = Field(default=None, max_length=150)
    engagement_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    system_ids: list[uuid.UUID] = Field(default_factory=list)
    spec_refs: list[str] = Field(default_factory=list, max_length=20)
    code_refs: list[str] = Field(default_factory=list, max_length=20)
    method_statement_ref: str | None = Field(default=None, max_length=120)
    change_note: str | None = Field(default=None, max_length=500)
    points: list[QItpPointInput] = Field(default_factory=list, max_length=200)


class QItpUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    discipline: QDiscipline | None = None
    work_package_en: str | None = Field(default=None, max_length=150)
    work_package_ar: str | None = Field(default=None, max_length=150)
    engagement_id: uuid.UUID | None = None
    zone_ids: list[uuid.UUID] | None = None
    system_ids: list[uuid.UUID] | None = None
    spec_refs: list[str] | None = Field(default=None, max_length=20)
    code_refs: list[str] | None = Field(default=None, max_length=20)
    method_statement_ref: str | None = Field(default=None, max_length=120)
    change_note: str | None = Field(default=None, max_length=500)
    points: list[QItpPointInput] | None = Field(default=None, max_length=200)


class QItpDecide(StrictInput):
    code: QApprovalCode = Field(
        description="A approved · B approved as noted · C revise and resubmit · D rejected"
    )
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QItpNewRevision(StrictInput):
    change_note: str | None = Field(default=None, max_length=500)


class QCriterionRef(ApiModel):
    id: uuid.UUID
    code: str
    version: int
    title_en: str
    title_ar: str
    kind: QCriterionKind
    unit: str | None


class QItpPointRead(ApiModel):
    id: uuid.UUID
    seq: int
    activity_en: str
    activity_ar: str
    characteristic_en: str
    characteristic_ar: str
    point_type: QPointType
    criteria: list[QCriterionRef]
    criteria_ids: list[uuid.UUID]
    acceptance_text_en: str | None
    acceptance_text_ar: str | None
    reference: str | None
    verifying_record: QVerifyingRecord
    checklist_template_code: str | None
    test_type_codes: list[str]
    frequency_text: str | None
    frequency_qty: str | None
    frequency_unit: str | None
    rp_override: dict[str, Any] | None
    notice_hours: int | None
    competence_code: str | None


class QItpListItem(ApiModel):
    id: uuid.UUID
    family_id: uuid.UUID
    itp_no: str | None
    revision: int
    display_no: str
    title_en: str
    title_ar: str
    discipline: QDiscipline
    engagement: QEngRef | None
    status: QItpStatus
    approval_code: QApprovalCode | None
    point_count: int
    approved_at: datetime | None
    updated_at: datetime | None


class QItpPage(ApiModel):
    items: list[QItpListItem]
    total: int
    page: int
    page_size: int


class QRevisionRef(ApiModel):
    id: uuid.UUID
    revision: int
    status: str
    approved_at: datetime | None = None


class QItpRead(QItpListItem):
    project_id: uuid.UUID
    work_package_en: str | None
    work_package_ar: str | None
    zones: list[QCodeRef]
    systems: list[QCodeRef]
    spec_refs: list[str]
    code_refs: list[str]
    method_statement_ref: str | None
    change_note: str | None
    decision_comment: str | None
    prepared_by: UserRef | None
    submitted_at: datetime | None
    submitted_by: UserRef | None
    decided_at: datetime | None
    status_reason: str | None
    points: list[QItpPointRead]
    revisions: list[QRevisionRef]
    responsible: list[UserRef]
    rp_not_set: bool
    signoffs: list[QSignoffRead]
    links: list[QLinkRead]
    allowed_actions: list[str]
    problems: list[str]


class QCoverageCell(ApiModel):
    seq: int
    state: Literal[
        "approved", "approved_with_comments", "rejected", "scheduled", "waived", "not_started"
    ]
    ir_no: str | None


class QCoverageRow(ApiModel):
    location_key: str
    location_ref: str
    cells: list[QCoverageCell]


class QCoveragePoint(ApiModel):
    seq: int
    point_type: QPointType
    activity_en: str
    activity_ar: str


class QItpCoverage(ApiModel):
    itp_id: uuid.UUID
    points: list[QCoveragePoint]
    rows: list[QCoverageRow]


# ---- IR ----------------------------------------------------------------------------------------


class QIrCreate(StrictInput):
    itp_id: uuid.UUID = Field(description="The current Approved revision (Q-ITP-04).")
    point_seqs: list[int] = Field(min_length=1, max_length=10)
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str = Field(min_length=1, max_length=120)
    extent: str | None = Field(default=None, max_length=150)
    proposed_at: datetime | None = None
    self_check_done: bool = False
    self_check_note: str | None = Field(default=None, max_length=500)
    client_uuid: uuid.UUID | None = None
    submit: bool = False
    short_notice_reason: str | None = Field(default=None, max_length=1000)


class QIrUpdate(StrictInput):
    itp_id: uuid.UUID | None = None
    point_seqs: list[int] | None = Field(default=None, max_length=10)
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    extent: str | None = Field(default=None, max_length=150)
    proposed_at: datetime | None = None
    self_check_done: bool | None = None
    self_check_note: str | None = Field(default=None, max_length=500)


class QIrSubmit(StrictInput):
    short_notice_reason: str | None = Field(
        default=None,
        max_length=1000,
        description="≥ 20 chars for an urgent IR with less notice (Q-IR-03).",
    )


class QIrSchedule(StrictInput):
    scheduled_at: datetime
    inspector_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the scheduler; must resolve for ir.inspect."
    )
    reason: str | None = Field(
        default=None, max_length=1000, description="Required to re-schedule."
    )


class QIrMeasurement(StrictInput):
    point_seq: int
    name: str | None = Field(default=None, max_length=120)
    value: Decimal | None = None
    values: dict[str, Any] | None = Field(
        default=None, description="Extra inputs of a coded rule criterion."
    )
    unit: str | None = Field(default=None, max_length=20)
    criterion_id: uuid.UUID | None = None
    mte_id: uuid.UUID | None = None
    verdict: Literal["pass", "fail"] | None = Field(
        default=None, description="Pass / fail and text criteria."
    )


class QIrCommentInput(StrictInput):
    text_en: str | None = Field(default=None, max_length=1000)
    text_ar: str | None = Field(default=None, max_length=1000)


class QIrDecide(StrictInput):
    result: QIrResult
    comment: str | None = Field(default=None, max_length=2000)
    comments: list[QIrCommentInput] = Field(default_factory=list, max_length=30)
    reject_category: QNcrCategory | None = None
    close_comments_before_next_hold: bool = False
    answers: dict[str, list[AnswerInput]] = Field(
        default_factory=dict, description="Checklist answers by ITP point seq."
    )
    measurements: list[QIrMeasurement] = Field(default_factory=list, max_length=100)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=20)
    raise_ncr: bool = False
    ncr_owner_id: uuid.UUID | None = None
    paper: QPaperSignoff | None = None
    client_uuid: uuid.UUID | None = None
    recorded_at: datetime | None = Field(
        default=None, description="Device time of an offline round (Q-IR-14)."
    )


class QIrWaive(StrictInput):
    answers: dict[str, list[AnswerInput]] = Field(default_factory=dict)
    measurements: list[QIrMeasurement] = Field(default_factory=list, max_length=100)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)


class QIrSelfCheck(StrictInput):
    """Q-IR-04 round 0: the contractor's pre-inspection on the points' checklists."""

    answers: dict[str, list[AnswerInput]] = Field(description="Checklist answers by ITP point seq.")
    note: str | None = Field(default=None, max_length=500)


class QIrReinspect(StrictInput):
    note: str = Field(min_length=1, max_length=1000)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=10)


class QIrConfirm(StrictInput):
    discard: bool = False


class QReason(StrictInput):
    reason: str = Field(min_length=1, max_length=2000)


class QCommentText(StrictInput):
    comment: str = Field(min_length=1, max_length=2000)


class QIrCommentRespond(StrictInput):
    response_text: str = Field(min_length=1, max_length=1000)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=5)


class QIrCommentClose(StrictInput):
    accept: bool = True
    note: str | None = Field(default=None, max_length=1000)


class QIrListItem(ApiModel):
    id: uuid.UUID
    ir_no: str | None
    status: QIrStatus
    itp_id: uuid.UUID
    itp_display_no: str | None
    discipline: QDiscipline | None
    point_seqs: list[int]
    governing_type: QPointType
    location_ref: str
    location_key: str
    zone: QCodeRef | None
    engagement: QEngRef | None
    requested_by: UserRef | None
    proposed_at: datetime | None
    submitted_at: datetime | None
    current_round: int
    scheduled_at: datetime | None
    inspector: UserRef | None
    short_notice: bool
    reblocked: bool
    needs_confirmation: bool
    decided_at: datetime | None


class QIrPage(ApiModel):
    items: list[QIrListItem]
    total: int
    page: int
    page_size: int


class QMeasurementRead(ApiModel):
    point_seq: int
    name: str | None
    value: str | None
    unit: str | None
    criterion_id: str | None
    criterion_code: str | None
    criterion_version: int | None
    mte_id: str | None
    mte_no: str | None
    mte_cal_due_on: str | None = None
    mte_cal_status: str | None = None
    verdict: str | None
    reason_en: str | None
    reason_ar: str | None


class QAnswerRead(ApiModel):
    item_code: str
    text_en: str | None
    text_ar: str | None
    answer: str | None
    numeric_value: str | None
    note: str | None
    compliant: bool | None
    critical: bool | None


class QResponseRead(ApiModel):
    seq: int
    id: uuid.UUID | None = None
    template_code: str | None = None
    template_version: int | None = None
    title_en: str | None = None
    title_ar: str | None = None
    applicable_count: int | None = None
    compliant_count: int | None = None
    score_pct: str | None = None
    critical_fail_count: int | None = None
    result: str | None = None
    answers: list[QAnswerRead] = Field(default_factory=list)


class QIrRoundRead(ApiModel):
    id: uuid.UUID
    round_no: int
    scheduled_at: datetime | None
    inspector: UserRef | None
    attended_at: datetime | None
    inspected_at: datetime | None
    result: QIrResult | None
    review_result: QIrResult | None
    reviewed_at: datetime | None
    reject_category: QNcrCategory | None
    comment: str | None
    close_comments_before_next_hold: bool
    correction_note: str | None
    waived_at: datetime | None
    waived_by: UserRef | None
    reschedule_count: int
    reschedules: list[dict[str, Any]]
    measurements: list[QMeasurementRead]
    responses: list[QResponseRead]
    photo_ids: list[uuid.UUID]
    needs_confirmation: bool
    recorded_offline_at: datetime | None
    warnings: list[dict[str, Any]]


class QIrCommentRead(ApiModel):
    id: uuid.UUID
    round_id: uuid.UUID
    text_en: str | None
    text_ar: str | None
    status: QIrCommentStatus
    due_on: date | None
    response_text: str | None
    responded_at: datetime | None
    closed_at: datetime | None
    reopen_comment: str | None
    overdue: bool


class QNcrRef(ApiModel):
    id: uuid.UUID
    ncr_no: str | None
    status: QNcrStatus
    classification: QNcrClass | None = None


class QChecklistItemRead(ApiModel):
    item_code: str
    text_en: str | None
    text_ar: str | None
    item_type: str | None
    critical: bool
    na_allowed: bool


class QChecklistRead(ApiModel):
    seq: int | None = Field(description="The ITP point the checklist belongs to (IR rounds).")
    template_code: str
    version: int
    quality_type: str | None
    title_en: str
    title_ar: str
    items: list[QChecklistItemRead]


class QIrRead(QIrListItem):
    project_id: uuid.UUID
    itp_family_id: uuid.UUID
    itp_revision: int
    itp_status: QItpStatus | None
    itp_title_en: str | None
    itp_title_ar: str | None
    points: list[QItpPointRead]
    checklists: list[QChecklistRead]
    site: QCodeRef | None
    system: QCodeRef | None
    extent: str | None
    self_check_done: bool
    self_check_note: str | None
    short_notice_reason: str | None
    notice_hours: int | None
    status_reason: str | None
    rounds: list[QIrRoundRead]
    comments: list[QIrCommentRead]
    responsible: list[UserRef]
    rp_not_set: bool
    hold_blockers: list[QBlockerRead]
    signoffs: list[QSignoffRead]
    ncrs: list[QNcrRef]
    links: list[QLinkRead]
    allowed_actions: list[str]
    warnings: list[ApiWarning]
    ncr_prompt: bool = Field(description="Rejected: offer 'Raise NCR' (Q-IR-06).")
    ncr_required_next: bool = Field(description="A further rejection will require an NCR.")
    ncr_id: uuid.UUID | None = None


class QLocationSuggestion(ApiModel):
    location_key: str
    location_ref: str


class QIrCounts(ApiModel):
    """Part B counts behind K-141 / K-142 / K-149 (ir_inspection) for a period (§E.4)."""

    project_id: uuid.UUID
    date_from: date
    date_to: date
    first_rounds: int
    first_passes: int
    first_time_pass_pct: str | None
    rounds_decided: int
    rounds_failed: int
    rejection_rate_pct: str | None
    waived: int
    short_notice: int
    paper_signoffs: int
    opportunities: int
    defects: int
    punch_with_target: int
    punch_closed_on_time: int
    punch_closure_pct: str | None
    punch_open_a: int
    punch_open_b: int


# ---- punch and floor plans --------------------------------------------------------------------


class QPin(StrictInput):
    floor_plan_id: uuid.UUID | None = None
    x_pct: Decimal | None = Field(default=None, ge=0, le=100)
    y_pct: Decimal | None = Field(default=None, ge=0, le=100)


class QPunchCreate(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID
    system_id: uuid.UUID | None = None
    location_ref: str = Field(min_length=1, max_length=120)
    discipline: QDiscipline
    description_en: str | None = Field(default=None, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)
    category: QPunchCategory
    raised_during: QPunchRaisedDuring = QPunchRaisedDuring.walkdown
    responsible_engagement_id: uuid.UUID
    target_date: date | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=5)
    pin: QPin | None = None
    client_uuid: uuid.UUID | None = None


class QPunchUpdate(StrictInput):
    description_en: str | None = Field(default=None, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)
    location_ref: str | None = Field(default=None, max_length=120)
    category: QPunchCategory | None = None
    target_date: date | None = None
    pin: QPin | None = None
    confirm_pin: bool = False


class QPunchReady(StrictInput):
    note: str = Field(default="", max_length=1000)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=5)


class QPunchVerify(StrictInput):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QWalkdownAnswer(AnswerInput):
    location_ref: str | None = Field(default=None, max_length=120)
    category: QPunchCategory | None = None
    pin: QPin | None = None


class QWalkdownEntry(StrictInput):
    location_ref: str | None = Field(default=None, max_length=120)
    description_en: str | None = Field(default=None, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)
    category: QPunchCategory = QPunchCategory.B
    discipline: QDiscipline | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=5)
    pin: QPin | None = None


class QWalkdown(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID
    system_id: uuid.UUID | None = None
    responsible_engagement_id: uuid.UUID
    discipline: QDiscipline
    location_ref: str | None = Field(default=None, max_length=120)
    category: QPunchCategory | None = None
    template_code: str | None = Field(default=None, max_length=8)
    answers: list[QWalkdownAnswer] = Field(default_factory=list, max_length=100)
    entries: list[QWalkdownEntry] = Field(default_factory=list, max_length=100)


class QPunchListItem(ApiModel):
    id: uuid.UUID
    punch_no: str
    status: QPunchStatus
    category: QPunchCategory
    discipline: QDiscipline
    description_en: str | None
    description_ar: str | None
    location_ref: str
    zone: QCodeRef | None
    engagement: QEngRef | None
    raised_date: date
    target_date: date
    closed_date: date | None
    overdue: bool
    floor_plan_id: uuid.UUID | None
    pin_x_pct: str | None
    pin_y_pct: str | None
    pin_check: bool
    raised_by: UserRef | None


class QPunchPage(ApiModel):
    items: list[QPunchListItem]
    total: int
    page: int
    page_size: int


class QPunchRead(QPunchListItem):
    project_id: uuid.UUID
    site: QCodeRef | None
    system_id: uuid.UUID | None
    raised_during: QPunchRaisedDuring
    raised_at: datetime
    photo_before_ids: list[uuid.UUID]
    photo_after_ids: list[uuid.UUID]
    ready_note: str | None
    ready_at: datetime | None
    ready_by: UserRef | None
    closed_by: UserRef | None
    status_reason: str | None
    responsible: list[UserRef]
    signoffs: list[QSignoffRead]
    ncrs: list[QNcrRef]
    links: list[QLinkRead]
    allowed_actions: list[str]
    warnings: list[ApiWarning]


class QWalkdownResult(ApiModel):
    items: list[QPunchListItem]
    warnings: list[ApiWarning]


class QFloorPlanRead(ApiModel):
    id: uuid.UUID
    family_id: uuid.UUID
    zone: QCodeRef | None
    level_label: str
    title_en: str
    title_ar: str
    revision: str
    width_px: int
    height_px: int
    status: QPlanStatus
    attachment_id: uuid.UUID | None
    pin_count: int
    pins: list[QPunchListItem]
    unpinned_count: int
    created_at: datetime


# ---- dossier ----------------------------------------------------------------------------------


class QDossierCreate(StrictInput):
    title_en: str = Field(min_length=1, max_length=150)
    title_ar: str = Field(min_length=1, max_length=150)
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    system_ids: list[uuid.UUID] = Field(default_factory=list)
    sections: list[str] | None = Field(
        default=None, description="Section codes; default all registered."
    )


class QDossierUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    zone_ids: list[uuid.UUID] | None = None
    system_ids: list[uuid.UUID] | None = None
    sections: list[str] | None = None


class QDossierDecide(StrictInput):
    decision: Literal["approved", "returned"]
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QAsbuiltCreate(StrictInput):
    drawing_no: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    revision: str = Field(default="0", max_length=20)
    drawing_date: date | None = None
    status: QAsbuiltStatus = QAsbuiltStatus.submitted
    attachment_id: uuid.UUID | None = Field(
        default=None, description="A `q_dossier` attachment of this dossier."
    )


class QAsbuiltUpdate(StrictInput):
    drawing_no: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, max_length=200)
    revision: str | None = Field(default=None, max_length=20)
    drawing_date: date | None = None
    status: QAsbuiltStatus | None = None
    attachment_id: uuid.UUID | None = None
    delete: bool = False


class QDossierListItem(ApiModel):
    id: uuid.UUID
    family_id: uuid.UUID
    dossier_no: str
    revision: int
    title_en: str
    title_ar: str
    status: QDossierStatus
    zones: list[QCodeRef]
    system_ids: list[uuid.UUID]
    compiled_at: datetime | None
    submitted_at: datetime | None
    decided_at: datetime | None


class QDossierPage(ApiModel):
    items: list[QDossierListItem]
    total: int
    page: int
    page_size: int


class QSectionRef(ApiModel):
    code: str
    title_en: str
    title_ar: str


class QSnapshotSection(ApiModel):
    code: str
    title_en: str | None
    title_ar: str | None
    item_count: int
    file_count: int


class QAsbuiltRead(ApiModel):
    id: uuid.UUID
    drawing_no: str
    title: str
    revision: str
    drawing_date: date | None
    status: QAsbuiltStatus
    attachment_id: uuid.UUID | None


class QDossierRead(QDossierListItem):
    project_id: uuid.UUID
    systems: list[QCodeRef]
    sections: list[str]
    available_sections: list[QSectionRef]
    compiled_by: UserRef | None
    snapshot_sections: list[QSnapshotSection]
    package_sha256: str | None
    has_files: bool
    blockers: list[QBlockerRead]
    warnings: list[QBlockerRead]
    status_reason: str | None
    asbuilt: list[QAsbuiltRead]
    revisions: list[QRevisionRef]
    responsible: list[UserRef]
    signoffs: list[QSignoffRead]
    links: list[QLinkRead]
    allowed_actions: list[str]
