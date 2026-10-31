"""API schemas of package Q2 (spec 8-quality Part C). Every name carries the `Q` prefix; numbers
that need exact decimals travel as strings (K-R8 convention)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.core.quality.common import QCalStatus, QMteType, QProfileScope, QRecordType
from app.core.quality.q2 import (
    QAcceptReject,
    QCalKind,
    QCalRecordStatus,
    QCompetenceAppliesTo,
    QCompetencePolicy,
    QCompetenceState,
    QEvaluationMode,
    QJointType,
    QMarStatus,
    QMaterialCategory,
    QMirResult,
    QMirStatus,
    QMteOverride,
    QNdtMethod,
    QNdtSelection,
    QOotDecision,
    QOotStatus,
    QPourStatus,
    QPqrStatus,
    QQuarantineStatus,
    QTestStatus,
    QTestTypeStatus,
    QTestVerdict,
    QWelderStatus,
    QWeldProcess,
    QWeldStandard,
    QWeldStatus,
    QWpqMethod,
    QWpqStatus,
    QWpsStatus,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.field import AnswerInput
from app.schemas.hse_common import ApiWarning, UserRef
from app.schemas.quality.q0 import QPaperSignoff

Num = str | int | float


class QReasonBody(StrictInput):
    reason: str | None = Field(default=None, max_length=1000)


class QDecisionBody(StrictInput):
    decision: Literal["approved", "approved_with_comments", "rejected", "returned"]
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QWarningsRead(ApiModel):
    warnings: list[ApiWarning] = Field(default_factory=list)


# ==== calibration =================================================================================


class QCalPoint(StrictInput):
    nominal: Num
    as_found: Num
    as_left: Num | None = None
    tolerance: Num | None = None


class QCalPointRead(ApiModel):
    nominal: str
    as_found: str
    as_left: str | None
    tolerance: str
    error: str
    in_tolerance: bool
    as_left_in_tolerance: bool


class QCalibrationCreate(StrictInput):
    kind: QCalKind | None = None
    cal_date: date
    provider_supplier_id: uuid.UUID | None = None
    in_house: bool = False
    reference_mte_id: uuid.UUID | None = None
    certificate_no: str | None = Field(default=None, max_length=60)
    points: list[QCalPoint] = Field(default_factory=list, max_length=50)
    traceability: str | None = Field(default=None, max_length=300)
    uncertainty: str | None = Field(default=None, max_length=80)
    verification_note: str | None = Field(default=None, max_length=1000)


class QCalibrationUpdate(StrictInput):
    cal_date: date | None = None
    provider_supplier_id: uuid.UUID | None = None
    in_house: bool | None = None
    reference_mte_id: uuid.UUID | None = None
    certificate_no: str | None = Field(default=None, max_length=60)
    points: list[QCalPoint] | None = None
    traceability: str | None = Field(default=None, max_length=300)
    uncertainty: str | None = Field(default=None, max_length=80)
    verification_note: str | None = Field(default=None, max_length=1000)


class QCalibrationDecide(StrictInput):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=1000)
    paper: QPaperSignoff | None = None


class QCalibrationRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    cal_no: str | None
    mte_id: uuid.UUID
    mte_no: str | None
    mte_type: QMteType | None
    kind: QCalKind
    cal_date: date
    provider_supplier_id: uuid.UUID | None
    provider_code: str | None
    in_house: bool
    reference_mte_id: uuid.UUID | None
    reference_mte_no: str | None
    certificate_no: str | None
    points: list[QCalPointRead]
    as_found_ok: bool
    as_left_ok: bool
    max_found_error: str | None
    traceability: str | None
    uncertainty: str | None
    verification_note: str | None
    next_due: date | None
    decision_comment: str | None
    decided_at: datetime | None
    decided_by: UserRef | None
    status: QCalRecordStatus
    certificate_count: int
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QCalibrationPage(ApiModel):
    items: list[QCalibrationRead]
    total: int
    page: int
    page_size: int


class QMteOverrideSet(StrictInput):
    status: QMteOverride | None = None
    reason: str | None = Field(default=None, max_length=500)


class QMteLabelRead(ApiModel):
    mte_id: uuid.UUID
    mte_no: str
    project_code: str
    description: str
    cal_status: QCalStatus
    status_en: str
    status_ar: str
    colour: Literal["green", "amber", "red", "grey"]
    cal_date: date | None
    due_on: date | None
    path: str
    printed_at: datetime | None


class QOotItemRead(ApiModel):
    id: uuid.UUID
    record_type: str
    record_id: uuid.UUID
    ref: str | None
    used_at: datetime | None
    value: str | None
    limit_low: str | None
    limit_high: str | None
    margin: str | None
    error_abs: str
    proposed: QOotDecision | None
    decision: QOotDecision | None
    justification: str | None
    recheck_record_type: str | None
    recheck_record_id: uuid.UUID | None
    recheck_ref: str | None
    ncr_id: uuid.UUID | None
    decided_at: datetime | None


class QOotReviewRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    oot_no: str
    mte_id: uuid.UUID
    mte_no: str
    calibration_id: uuid.UUID
    period_from: date
    period_to: date
    error_abs: str
    due_on: date
    status: QOotStatus
    closed_at: datetime | None
    item_count: int
    decided_count: int
    proposed_no_impact: int
    ncr_count: int
    items: list[QOotItemRead]
    actions: list[str]


class QOotReviewListItem(ApiModel):
    id: uuid.UUID
    oot_no: str
    mte_id: uuid.UUID
    mte_no: str
    period_from: date
    period_to: date
    error_abs: str
    due_on: date
    status: QOotStatus
    item_count: int
    decided_count: int


class QOotItemDecide(StrictInput):
    decision: QOotDecision
    justification: str | None = Field(default=None, max_length=1000)
    recheck_record_type: QRecordType | None = None
    recheck_record_id: uuid.UUID | None = None
    recheck_ref: str | None = Field(default=None, max_length=60)
    owner_id: uuid.UUID | None = None


class QOotAcceptProposals(StrictInput):
    justification: str = Field(max_length=1000)


class QOotAccepted(ApiModel):
    decided: int


class QOotClose(StrictInput):
    comment: str | None = Field(default=None, max_length=1000)
    paper: QPaperSignoff | None = None


# ==== competence =================================================================================


class QEvidenceItem(StrictInput):
    kind: Literal["training_course", "personnel_certificate"]
    code: str = Field(min_length=1, max_length=40)
    min_level: str | None = Field(default=None, max_length=10)


class QEvidenceItemRead(ApiModel):
    kind: str
    code: str
    min_level: str | None = None


class QCompetenceReqCreate(StrictInput):
    code: str = Field(pattern=r"^[A-Z0-9-]{3,20}$")
    title_en: str = Field(min_length=1, max_length=150)
    title_ar: str = Field(default="", max_length=150)
    applies_to: list[QCompetenceAppliesTo] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    any_of: list[QEvidenceItem] = Field(default_factory=list)
    all_of: list[QEvidenceItem] = Field(default_factory=list)
    policy: QCompetencePolicy = QCompetencePolicy.inherit
    profile: QProfileScope = QProfileScope.both


class QCompetenceReqUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    applies_to: list[QCompetenceAppliesTo] | None = None
    filters: dict[str, Any] | None = None
    any_of: list[QEvidenceItem] | None = None
    all_of: list[QEvidenceItem] | None = None
    policy: QCompetencePolicy | None = None
    profile: QProfileScope | None = None
    active: bool | None = None


class QCompetenceReqRead(ApiModel):
    id: uuid.UUID
    code: str
    title_en: str
    title_ar: str
    applies_to: list[QCompetenceAppliesTo]
    filters: dict[str, Any]
    any_of: list[QEvidenceItemRead]
    all_of: list[QEvidenceItemRead]
    policy: QCompetencePolicy
    profile: QProfileScope
    active: bool


class QCompetenceEvidence(ApiModel):
    kind: str
    code: str
    met: bool
    valid_until: str | None
    ref: str | None
    reason: str | None


class QCompetenceCheckRead(ApiModel):
    requirement: str
    user_id: uuid.UUID
    met: bool | None
    code: str
    detail_en: str
    detail_ar: str
    valid_until: date | None
    evidence: list[QCompetenceEvidence]


class QCompetencePerson(ApiModel):
    user_id: uuid.UUID
    full_name_en: str
    full_name_ar: str | None
    linked_worker: bool


class QCompetenceCell(ApiModel):
    user_id: uuid.UUID
    code: str
    state: QCompetenceState
    valid_until: date | None
    reason: str | None


class QCompetenceMatrixRead(ApiModel):
    on: date
    requirements: list[QCompetenceReqRead]
    people: list[QCompetencePerson]
    cells: list[QCompetenceCell]
    applicable: int
    met: int


# ==== test types and tests ======================================================================


class QSpecimenPlanRow(StrictInput):
    age_days: int | None = Field(default=None, ge=0, le=400)
    count: int = Field(ge=1, le=50)
    spare: bool = False


class QSpecimenPlanRead(ApiModel):
    age_days: int | None = None
    count: int
    spare: bool = False


class QResultField(StrictInput):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")
    label_en: str = Field(min_length=1, max_length=80)
    label_ar: str = Field(default="", max_length=80)
    unit: str | None = Field(default=None, max_length=20)
    kind: Literal["numeric", "text", "pass_fail"] = "numeric"


class QResultFieldRead(ApiModel):
    key: str
    label_en: str
    label_ar: str = ""
    unit: str | None = None
    kind: str = "numeric"


class QTestTypeCreate(StrictInput):
    code: str = Field(min_length=2, max_length=16)
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(default="", max_length=150)
    discipline: str = Field(min_length=2, max_length=10)
    profile: QProfileScope = QProfileScope.construction
    standard_ref: str | None = Field(default=None, max_length=120)
    specimen_plan: list[QSpecimenPlanRow] = Field(default_factory=list, max_length=10)
    result_fields: list[QResultField] = Field(min_length=1, max_length=20)
    evaluation: QEvaluationMode = QEvaluationMode.fields
    criterion_code: str | None = Field(default=None, max_length=20)
    field_criteria: dict[str, str] = Field(default_factory=dict)
    acceptance_age_days: int | None = Field(default=None, ge=0, le=400)
    ncr_class_on_fail: dict[str, Literal["minor", "major", "critical"]] = Field(
        default_factory=dict
    )
    competence_code: str | None = Field(default=None, max_length=20)


class QTestTypeUpdate(StrictInput):
    name_en: str | None = Field(default=None, max_length=150)
    name_ar: str | None = Field(default=None, max_length=150)
    discipline: str | None = Field(default=None, max_length=10)
    profile: QProfileScope | None = None
    standard_ref: str | None = Field(default=None, max_length=120)
    specimen_plan: list[QSpecimenPlanRow] | None = None
    result_fields: list[QResultField] | None = None
    evaluation: QEvaluationMode | None = None
    criterion_code: str | None = Field(default=None, max_length=20)
    field_criteria: dict[str, str] | None = None
    acceptance_age_days: int | None = None
    ncr_class_on_fail: dict[str, Literal["minor", "major", "critical"]] | None = None
    competence_code: str | None = Field(default=None, max_length=20)


class QTestTypeNewVersion(StrictInput):
    project_id: uuid.UUID | None = None


class QTestTypeTransition(StrictInput):
    action: Literal["publish", "retire"]
    reason: str | None = Field(default=None, max_length=500)


class QTestTypeRead(ApiModel):
    id: uuid.UUID
    code: str
    version: int
    name_en: str
    name_ar: str
    discipline: str
    profile: QProfileScope
    standard_ref: str | None
    specimen_plan: list[QSpecimenPlanRead]
    result_fields: list[QResultFieldRead]
    evaluation: QEvaluationMode
    criterion_code: str | None
    field_criteria: dict[str, str]
    acceptance_age_days: int | None
    ncr_class_on_fail: dict[str, str]
    competence_code: str | None
    project_ids: list[uuid.UUID]
    status: QTestTypeStatus
    published_at: datetime | None


class QTestCreate(StrictInput):
    test_type_id: uuid.UUID | None = None
    test_type_code: str | None = Field(default=None, max_length=16)
    criterion_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    engagement_id: uuid.UUID | None = None
    lab_supplier_id: uuid.UUID
    pour_id: uuid.UUID | None = None
    mir_id: uuid.UUID | None = None
    ir_id: uuid.UUID | None = None
    retest_of_id: uuid.UUID | None = None
    mix_key: str | None = Field(default=None, max_length=80)


class QTestUpdate(StrictInput):
    location_ref: str | None = Field(default=None, max_length=120)
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    sample_ref: str | None = Field(default=None, max_length=40)
    tested_by_name: str | None = Field(default=None, max_length=120)


class QTestSample(StrictInput):
    sampled_at: datetime | None = None
    sample_ref: str = Field(min_length=1, max_length=40)
    sampled_by_user_id: uuid.UUID | None = None
    mte_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    mte_notes: dict[str, str] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)


class QTestDeliver(StrictInput):
    delivered_on: date | None = None


class QSpecimenValues(StrictInput):
    id: uuid.UUID | None = None
    specimen_ref: str | None = Field(default=None, max_length=40)
    tested_on: date | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class QTestSpecimens(StrictInput):
    specimens: list[QSpecimenValues] = Field(max_length=60)


class QTestResults(StrictInput):
    report_no: str | None = Field(default=None, max_length=60)
    tested_by_name: str | None = Field(default=None, max_length=120)
    specimens: list[QSpecimenValues] = Field(default_factory=list, max_length=60)
    results: dict[str, Any] = Field(default_factory=dict)


class QTestAmend(QTestResults):
    reason: str = Field(max_length=1000)


class QTestVerify(StrictInput):
    decision: Literal["approved", "returned"]
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QTestNcrDecision(StrictInput):
    raise_ncr: bool
    reason: str | None = Field(default=None, max_length=1000)


class QSpecimenRead(ApiModel):
    id: uuid.UUID
    specimen_ref: str
    age_days: int | None
    due_on: date | None
    tested_on: date | None
    values: dict[str, Any]
    spare: bool


class QTestRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    test_no: str
    test_type_id: uuid.UUID
    test_type_code: str
    test_type_version: int
    test_type_name_en: str
    test_type_name_ar: str
    criterion_id: uuid.UUID | None
    criterion_code: str | None
    criterion_version: int | None
    site_id: uuid.UUID
    site_code: str
    zone_id: uuid.UUID | None
    zone_code: str | None
    system_id: uuid.UUID | None
    location_ref: str
    engagement_id: uuid.UUID | None
    lab_supplier_id: uuid.UUID
    lab_code: str
    pour_id: uuid.UUID | None
    pour_no: str | None
    mir_id: uuid.UUID | None
    retest_of_id: uuid.UUID | None
    mix_key: str | None
    requested_by: UserRef | None
    sampled_at: datetime | None
    cast_date: date | None
    sampled_by: UserRef | None
    sample_ref: str | None
    mte_ids: list[uuid.UUID]
    delivered_to_lab_on: date | None
    results: dict[str, Any]
    report_no: str | None
    tested_by_name: str | None
    verdict: QTestVerdict
    verdict_detail: dict[str, Any]
    result_version: int
    history: list[dict[str, Any]]
    results_entered_at: datetime | None
    results_entered_by: UserRef | None
    verified_at: datetime | None
    verified_by: UserRef | None
    ncr_decision: dict[str, Any]
    status: QTestStatus
    status_reason: str | None
    specimens: list[QSpecimenRead]
    result_fields: list[QResultFieldRead]
    report_count: int
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)
    ncr_prompt: bool = False


class QTestPage(ApiModel):
    items: list[QTestRead]
    total: int
    page: int
    page_size: int


class QSpecimenDue(ApiModel):
    test_id: uuid.UUID
    test_no: str
    test_type_code: str
    specimen_ref: str
    age_days: int | None
    due_on: date
    state: Literal["overdue", "today", "upcoming"]


class QSpecimenCalendar(ApiModel):
    on: date
    items: list[QSpecimenDue]


# ==== pours ======================================================================================


class QPourCreate(StrictInput):
    element: str = Field(min_length=1, max_length=150)
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    engagement_id: uuid.UUID | None = None
    mar_id: uuid.UUID | None = None
    grade: str = Field(min_length=1, max_length=20)
    fc_mpa: Num | None = None
    volume_m3: Num
    supplier_id: uuid.UUID | None = None
    planned_on: date | None = None
    ambient_temp_c: Num | None = None
    pre_pour_ir_id: uuid.UUID | None = None
    itp_point_id: uuid.UUID | None = None
    quality_engineer_id: uuid.UUID | None = None


class QPourStart(StrictInput):
    started_at: datetime | None = None


class QPourClose(StrictInput):
    finished_at: datetime | None = None
    ambient_temp_c: Num | None = None


class QMixTest(ApiModel):
    test_id: uuid.UUID
    test_no: str
    pour_no: str | None
    cast_date: date | None
    test: str | None
    mean3: str | None
    verdict: QTestVerdict
    clause: str | None


class QMixStatus(ApiModel):
    tests: list[QMixTest]
    flagged_pour_ids: list[uuid.UUID]
    flagged: bool


class QPourRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    pour_no: str
    engagement_id: uuid.UUID | None
    element: str
    site_id: uuid.UUID
    site_code: str
    zone_id: uuid.UUID | None
    zone_code: str | None
    location_ref: str | None
    mar_id: uuid.UUID | None
    mar_no: str | None
    grade: str
    fc_mpa: str | None
    volume_m3: str
    supplier_id: uuid.UUID | None
    supplier_code: str | None
    planned_on: date | None
    started_at: datetime | None
    finished_at: datetime | None
    ambient_temp_c: str | None
    pre_pour_ir_id: uuid.UUID | None
    itp_point_id: uuid.UUID | None
    quality_engineer_id: uuid.UUID | None
    sets_required: int
    sets_taken: int
    set_test_ids: list[uuid.UUID]
    flags: list[str]
    status: QPourStatus
    mix_status: QMixStatus | None
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QPourPage(ApiModel):
    items: list[QPourRead]
    total: int
    page: int
    page_size: int


# ==== materials ==================================================================================


class QComplianceRow(StrictInput):
    requirement: str = Field(min_length=1, max_length=300)
    offered: str = Field(default="", max_length=300)
    result: Literal["complies", "deviation", "not_applicable"] = "complies"
    note: str = Field(default="", max_length=300)


class QComplianceRead(ApiModel):
    requirement: str
    offered: str
    result: str
    note: str


class QMarCreate(StrictInput):
    engagement_id: uuid.UUID
    title_en: str = Field(min_length=1, max_length=200)
    title_ar: str = Field(default="", max_length=200)
    category: QMaterialCategory
    spec_section: str | None = Field(default=None, max_length=60)
    manufacturer: str | None = Field(default=None, max_length=150)
    supplier_id: uuid.UUID | None = None
    country_of_origin: str | None = Field(default=None, max_length=60)
    brand_model: str | None = Field(default=None, max_length=150)
    compliance: list[QComplianceRow] = Field(default_factory=list, max_length=60)
    deviations_note: str | None = Field(default=None, max_length=2000)
    sample_ref: str | None = Field(default=None, max_length=60)


class QMarUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=200)
    title_ar: str | None = Field(default=None, max_length=200)
    category: QMaterialCategory | None = None
    spec_section: str | None = Field(default=None, max_length=60)
    manufacturer: str | None = Field(default=None, max_length=150)
    supplier_id: uuid.UUID | None = None
    country_of_origin: str | None = Field(default=None, max_length=60)
    brand_model: str | None = Field(default=None, max_length=150)
    compliance: list[QComplianceRow] | None = None
    deviations_note: str | None = Field(default=None, max_length=2000)
    sample_ref: str | None = Field(default=None, max_length=60)


class QMarDecide(StrictInput):
    approval_code: Literal["A", "B", "C", "D"]
    comment: str | None = Field(default=None, max_length=2000)
    accept_deviations: bool = False
    paper: QPaperSignoff | None = None


class QMarRevision(ApiModel):
    id: uuid.UUID
    revision: int
    status: QMarStatus
    approval_code: str | None


class QMarRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    mar_no: str | None
    revision: int
    root_id: uuid.UUID
    engagement_id: uuid.UUID
    engagement_code: str | None
    title_en: str
    title_ar: str
    category: QMaterialCategory
    spec_section: str | None
    manufacturer: str | None
    supplier_id: uuid.UUID | None
    supplier_code: str | None
    country_of_origin: str | None
    brand_model: str | None
    compliance: list[QComplianceRead]
    deviations_note: str | None
    with_deviations: bool
    deviations_accepted: bool
    sample_ref: str | None
    approval_code: str | None
    decision_comment: str | None
    submitted_at: datetime | None
    submitted_by: UserRef | None
    decided_at: datetime | None
    decided_by: UserRef | None
    status: QMarStatus
    status_reason: str | None
    document_count: int
    revisions: list[QMarRevision]
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QMarPage(ApiModel):
    items: list[QMarRead]
    total: int
    page: int
    page_size: int


class QMirCreate(StrictInput):
    mar_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    category: QMaterialCategory | None = None
    material_description: str | None = Field(default=None, max_length=200)
    site_id: uuid.UUID | None = None
    delivery_note_no: str | None = Field(default=None, max_length=60)
    po_no: str | None = Field(default=None, max_length=60)
    supplier_id: uuid.UUID | None = None
    delivered_at: datetime | None = None
    quantity: Num
    unit: str = Field(min_length=1, max_length=10)
    lot_numbers: list[str] = Field(default_factory=list, max_length=100)
    cert_heat_numbers: list[str] = Field(default_factory=list, max_length=100)
    storage_zone_id: uuid.UUID | None = None


class QMirUpdate(StrictInput):
    material_description: str | None = Field(default=None, max_length=200)
    site_id: uuid.UUID | None = None
    delivery_note_no: str | None = Field(default=None, max_length=60)
    po_no: str | None = Field(default=None, max_length=60)
    supplier_id: uuid.UUID | None = None
    delivered_at: datetime | None = None
    quantity: Num | None = None
    unit: str | None = Field(default=None, max_length=10)
    lot_numbers: list[str] | None = None
    cert_heat_numbers: list[str] | None = None
    storage_zone_id: uuid.UUID | None = None


class QMirDecide(StrictInput):
    result: QMirResult
    accepted_qty: Num
    rejected_qty: Num
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QMirQuarantine(StrictInput):
    quantity: Num
    ncr_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)


class QMirTest(ApiModel):
    id: uuid.UUID
    test_no: str
    test_type_code: str
    verdict: QTestVerdict
    status: QTestStatus


class QMirChecklistItemRead(ApiModel):
    item_code: str
    text_en: str
    text_ar: str
    critical: bool
    answer: str | None
    compliant: bool | None
    note: str | None


class QMirChecklistRead(ApiModel):
    """§C.3.2 the delivery checklist response (6d engine, owner type q_mir)."""

    id: uuid.UUID
    template_code: str
    template_version: int
    completed_at: datetime | None
    score_pct: str | None
    result: str | None
    critical_fail_count: int
    critical_failures: list[str]
    answers: list[QMirChecklistItemRead]


class QMirChecklistTemplateItem(ApiModel):
    item_code: str
    text_en: str
    text_ar: str
    critical: bool
    na_allowed: bool


class QMirChecklistTemplate(ApiModel):
    template_code: str
    version: int
    title_en: str
    title_ar: str
    items: list[QMirChecklistTemplateItem]


class QMirChecklistSave(StrictInput):
    """PUT /quality/mirs/{id}/checklist: yes_no answers `compliant` / `non_compliant` / `na`; a
    non-compliant answer needs a note of at least 10 characters (6d EXE-2)."""

    template_code: str | None = Field(default=None, max_length=12)
    completed_at: datetime | None = None
    answers: list[AnswerInput] = Field(min_length=1, max_length=100)


class QMirRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    mir_no: str | None
    mar_id: uuid.UUID | None
    mar_no: str | None
    mar_revision: int | None
    mar_status: QMarStatus | None
    engagement_id: uuid.UUID | None
    engagement_code: str | None
    category: QMaterialCategory
    material_description: str
    site_id: uuid.UUID | None
    delivery_note_no: str | None
    po_no: str | None
    supplier_id: uuid.UUID | None
    supplier_code: str | None
    delivered_at: datetime | None
    quantity: str
    unit: str
    lot_numbers: list[str]
    cert_heat_numbers: list[str]
    heat_mismatch: list[str]
    storage_zone_id: uuid.UUID | None
    storage_zone_code: str | None
    accepted_qty: str | None
    rejected_qty: str | None
    result: QMirResult | None
    decision_comment: str | None
    submitted_at: datetime | None
    submitted_by: UserRef | None
    decided_at: datetime | None
    decided_by: UserRef | None
    status: QMirStatus
    tests: list[QMirTest]
    failed_tests: int
    quarantine_ids: list[uuid.UUID]
    certificate_count: int
    checklist_response_id: uuid.UUID | None = None
    checklist: QMirChecklistRead | None = None
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QMirPage(ApiModel):
    items: list[QMirRead]
    total: int
    page: int
    page_size: int


class QQuarantineCreate(StrictInput):
    material_description: str = Field(min_length=1, max_length=200)
    quantity: Num
    unit: str = Field(min_length=1, max_length=10)
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    engagement_id: uuid.UUID | None = None
    ncr_id: uuid.UUID | None = None


class QQuarantineDispose(StrictInput):
    to_status: Literal["released", "returned", "scrapped"]
    return_note_no: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=1000)
    paper: QPaperSignoff | None = None


class QQuarantineLink(StrictInput):
    ncr_id: uuid.UUID


class QQuarantineRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    tag_no: str
    material_description: str
    mir_id: uuid.UUID | None
    mir_no: str | None
    engagement_id: uuid.UUID | None
    quantity: str
    unit: str
    site_id: uuid.UUID | None
    zone_id: uuid.UUID | None
    zone_code: str | None
    location_ref: str | None
    ncr_id: uuid.UUID | None
    ncr_no: str | None
    ncr_status: str | None
    quarantined_on: date
    age_days: int | None
    ageing: bool
    return_note_no: str | None
    disposal_note: str | None
    disposed_at: datetime | None
    status: QQuarantineStatus
    evidence_count: int
    actions: list[str]


class QQuarantinePage(ApiModel):
    items: list[QQuarantineRead]
    total: int
    page: int
    page_size: int


# ==== welding ====================================================================================


class QWpsCreate(StrictInput):
    wps_no: str = Field(min_length=2, max_length=40)
    standard: QWeldStandard
    processes: list[QWeldProcess] = Field(min_length=1)
    joint_types: list[QJointType] = Field(default_factory=list)
    base_material_group: str | None = Field(default=None, max_length=60)
    thickness_min_mm: Num
    thickness_max_mm: Num
    diameter_min_mm: Num | None = None
    diameter_max_mm: Num | None = None
    positions: list[str] = Field(default_factory=list)
    filler_class: str | None = Field(default=None, max_length=40)
    f_no: str | None = Field(default=None, max_length=10)
    a_no: str | None = Field(default=None, max_length=10)
    preheat_min_c: Num | None = None
    interpass_max_c: Num | None = None
    pwht: str | None = Field(default=None, max_length=200)
    gas: str | None = Field(default=None, max_length=80)
    prequalified: bool = False
    pqr_ids: list[uuid.UUID] = Field(default_factory=list)


class QWpsUpdate(StrictInput):
    standard: QWeldStandard | None = None
    processes: list[QWeldProcess] | None = None
    joint_types: list[QJointType] | None = None
    base_material_group: str | None = Field(default=None, max_length=60)
    thickness_min_mm: Num | None = None
    thickness_max_mm: Num | None = None
    diameter_min_mm: Num | None = None
    diameter_max_mm: Num | None = None
    positions: list[str] | None = None
    filler_class: str | None = Field(default=None, max_length=40)
    f_no: str | None = Field(default=None, max_length=10)
    a_no: str | None = Field(default=None, max_length=10)
    preheat_min_c: Num | None = None
    interpass_max_c: Num | None = None
    pwht: str | None = Field(default=None, max_length=200)
    gas: str | None = Field(default=None, max_length=80)
    prequalified: bool | None = None
    pqr_ids: list[uuid.UUID] | None = None


class QWpsRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    wps_no: str
    revision: int
    standard: QWeldStandard
    processes: list[str]
    joint_types: list[str]
    base_material_group: str | None
    thickness_min_mm: str
    thickness_max_mm: str
    diameter_min_mm: str | None
    diameter_max_mm: str | None
    positions: list[str]
    filler_class: str | None
    f_no: str | None
    a_no: str | None
    preheat_min_c: str | None
    interpass_max_c: str | None
    pwht: str | None
    gas: str | None
    prequalified: bool
    pqr_ids: list[uuid.UUID]
    approved_at: datetime | None
    status: QWpsStatus
    status_reason: str | None
    actions: list[str]


class QPqrResult(StrictInput):
    test: str = Field(min_length=1, max_length=40)
    value: str = Field(default="", max_length=60)
    result: Literal["pass", "fail"]


class QPqrResultRead(ApiModel):
    test: str
    value: str
    result: str


class QPqrCreate(StrictInput):
    pqr_no: str = Field(min_length=2, max_length=40)
    standard: QWeldStandard
    process: QWeldProcess
    test_date: date
    results: list[QPqrResult] = Field(default_factory=list, max_length=20)
    lab_supplier_id: uuid.UUID | None = None
    certificate_no: str | None = Field(default=None, max_length=60)


class QPqrRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    pqr_no: str
    standard: QWeldStandard
    process: QWeldProcess
    test_date: date
    results: list[QPqrResultRead]
    lab_supplier_id: uuid.UUID | None
    certificate_no: str | None
    approved_at: datetime | None
    status: QPqrStatus
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QWelderCreate(StrictInput):
    worker_id: uuid.UUID
    stamp: str = Field(min_length=2, max_length=10)
    engagement_id: uuid.UUID


class QWelderUpdate(StrictInput):
    status: QWelderStatus


class QWelderRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    worker_id: uuid.UUID
    worker_no: str | None
    full_name_en: str
    full_name_ar: str | None
    stamp: str
    engagement_id: uuid.UUID
    engagement_code: str | None
    status: QWelderStatus


class QWpqCreate(StrictInput):
    welder_id: uuid.UUID
    standard: QWeldStandard
    process: QWeldProcess
    test_wps_id: uuid.UUID | None = None
    test_date: date
    coupon_thickness_mm: Num | None = None
    coupon_diameter_mm: Num | None = None
    coupon_position: str | None = Field(default=None, max_length=4)
    positions: list[str] = Field(min_length=1)
    thickness_min_mm: Num
    thickness_max_mm: Num
    diameter_min_mm: Num | None = None
    f_no: str | None = Field(default=None, max_length=10)
    test_method: QWpqMethod
    result: QAcceptReject = QAcceptReject.accept
    examiner_supplier_id: uuid.UUID | None = None
    personnel_certificate_id: uuid.UUID | None = None
    revalidation_due: date | None = None


class QWpqConfirm(StrictInput):
    date: date


class QWpqRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    wpq_no: str | None
    welder_id: uuid.UUID
    stamp: str
    standard: QWeldStandard
    process: QWeldProcess
    test_wps_id: uuid.UUID | None
    test_date: date
    coupon_thickness_mm: str | None
    coupon_diameter_mm: str | None
    coupon_position: str | None
    positions: list[str]
    thickness_min_mm: str
    thickness_max_mm: str
    diameter_min_mm: str | None
    f_no: str | None
    test_method: QWpqMethod
    result: QAcceptReject
    examiner_supplier_id: uuid.UUID | None
    last_use: date | None
    continuity_until: date | None
    days_left: int | None
    revalidation_due: date | None
    confirmations: list[dict[str, Any]]
    status: QWpqStatus
    status_reason: str | None
    actions: list[str]


class QWeldWelder(StrictInput):
    welder_id: uuid.UUID | None = None
    stamp: str | None = Field(default=None, max_length=10)
    root: bool = False
    fill: bool = False
    cap: bool = False


class QWeldWelderRead(ApiModel):
    welder_id: str
    stamp: str
    root: bool
    fill: bool
    cap: bool


class QWeldCreate(StrictInput):
    joint_id: str = Field(min_length=3, max_length=30)
    wps_id: uuid.UUID
    process: QWeldProcess | None = None
    position: str = Field(min_length=2, max_length=4)
    joint_type: QJointType = QJointType.butt
    thickness_mm: Num
    diameter_mm: Num | None = None
    length_mm: Num | None = None
    welders: list[QWeldWelder] = Field(min_length=1, max_length=6)
    welded_on: date
    drawing_ref: str | None = Field(default=None, max_length=60)
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    lot_code: str | None = Field(default=None, max_length=40)
    ndt_method: QNdtMethod | None = None
    ndt_required_pct: Num | None = None
    override_reason: str | None = Field(default=None, max_length=1000)


class QWeldVisual(StrictInput):
    result: QAcceptReject
    defect_type: str | None = Field(default=None, max_length=120)


class QWeldSelect(StrictInput):
    reason: QNdtSelection = QNdtSelection.random


class QWeldLot(StrictInput):
    lot_code: str = Field(min_length=1, max_length=40)
    ndt_method: QNdtMethod
    ndt_required_pct: Num | None = None


class QWeldNdt(StrictInput):
    method: QNdtMethod | None = None
    result: QAcceptReject
    report_no: str = Field(min_length=1, max_length=60)
    attachment_id: uuid.UUID
    defect_type: str | None = Field(default=None, max_length=120)
    defect_length_mm: Num | None = None
    examined_length_mm: Num | None = None
    technician_name: str | None = Field(default=None, max_length=120)
    technician_user_id: uuid.UUID | None = None
    competence_code: str | None = Field(default=None, max_length=20)
    examined_on: date | None = None


class QWeldRepair(StrictInput):
    welders: list[QWeldWelder] = Field(default_factory=list, max_length=6)
    repaired_on: date | None = None


class QWeldSign(StrictInput):
    decision: Literal["approved", "rejected"]
    comment: str = Field(max_length=2000)
    paper: QPaperSignoff | None = None


class QWeldRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    joint_id: str
    engagement_id: uuid.UUID | None
    drawing_ref: str | None
    site_id: uuid.UUID | None
    zone_id: uuid.UUID | None
    system_id: uuid.UUID | None
    wps_id: uuid.UUID
    wps_no: str
    process: QWeldProcess
    position: str
    joint_type: QJointType
    diameter_mm: str | None
    thickness_mm: str
    length_mm: str | None
    welders: list[QWeldWelderRead]
    welded_on: date
    visual_result: QAcceptReject | None
    visual_defect: str | None
    lot_code: str | None
    ndt_method: QNdtMethod | None
    ndt_required_pct: str | None
    selected_for_ndt: bool
    selection_reason: QNdtSelection | None
    selected_from_id: uuid.UUID | None
    ndt_results: list[dict[str, Any]]
    repair_count: int
    override_reason: str | None
    status: QWeldStatus
    status_reason: str | None
    actions: list[str]
    warnings: list[ApiWarning] = Field(default_factory=list)
    progressive: list[str] = Field(default_factory=list)


class QWeldPage(ApiModel):
    items: list[QWeldRead]
    total: int
    page: int
    page_size: int


class QLotWelder(ApiModel):
    stamp: str
    welds: int
    examined: int
    rejected: int


class QLotSummary(ApiModel):
    lot_code: str
    ndt_method: str | None
    required_pct: str
    welds_visual_accepted: int
    examined: int
    required: int
    shortfall: int
    achieved_pct: str
    progressive: int
    pct100: int
    by_welder: list[QLotWelder]


class QWeldPick(ApiModel):
    id: uuid.UUID
    joint_id: str


class QRepairRate(ApiModel):
    welder_id: uuid.UUID
    stamp: str
    first_examinations: int
    rejected: int
    rate_pct: str
    rate_by_length_pct: str | None


class QContinuityRow(ApiModel):
    welder_id: uuid.UUID
    stamp: str
    wpq_id: uuid.UUID
    wpq_no: str | None
    process: QWeldProcess
    last_use: date | None
    continuity_until: date | None
    days_left: int | None
    status: QWpqStatus


class QWeldLotItem(ApiModel):
    lot_code: str
    welds: int
