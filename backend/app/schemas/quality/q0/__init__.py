"""API schemas of package Q0 (spec 8-quality Part A). Every name carries the `Q` prefix so no
name clashes with earlier modules in the OpenAPI contract. Money and quantities are decimal
strings (K-R8 convention)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.core.enums import Capability
from app.core.hse_enums import CaPriority, CaStatus, ControlLevel
from app.core.quality.common import (
    QAccreditationBody,
    QAccreditationStandard,
    QActiveStatus,
    QAlertSeverity,
    QAlertStatus,
    QAssigneeKind,
    QCalStatus,
    QCauseCategory,
    QComplaintChannel,
    QComplaintSeverity,
    QComplaintStatus,
    QCostType,
    QCriterionKind,
    QCriterionStatus,
    QCustomerKind,
    QCustomerStatus,
    QDetectionStage,
    QDiscipline,
    QDisposition,
    QEffectiveness,
    QJustified,
    QLinkKind,
    QMteCheckKind,
    QMteOwnerKind,
    QMteStatus,
    QMteType,
    QMteUseVerdict,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QNumberReset,
    QObservationStatus,
    QProfileScope,
    QRcaMethod,
    QRecordType,
    QSatisfaction,
    QSectorProfile,
    QSettingKind,
    QSignoffChannel,
    QSupplierCategory,
    QSupplierStatus,
    QVerdict,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef

Text150 = Field(min_length=1, max_length=150)


# ---- settings and profile -----------------------------------------------------------------------


class QSettingsRead(ApiModel):
    project_id: uuid.UUID
    sector_profile: QSectorProfile | None = Field(description="Null until Quality is configured.")
    suggested_profile: QSectorProfile = Field(description="Q-PRF-06 default from the project type.")
    quality_start_date: date | None
    values: dict[str, Any] = Field(description="Every registry key, defaults merged (Q-SET-01).")
    changed_keys: list[str]
    profile_changed_at: datetime | None
    updated_at: datetime | None
    can_edit: bool


class QSettingsUpdate(StrictInput):
    values: dict[str, Any] | None = None
    quality_start_date: date | None = None
    clear_quality_start_date: bool = False


class QProfileSet(StrictInput):
    sector_profile: QSectorProfile
    reason: str | None = Field(
        default=None, max_length=1000, description="Required (≥ 20 chars) to change a set profile."
    )
    quality_start_date: date | None = None


class QSettingDefRead(ApiModel):
    key: str
    part: str
    kind: QSettingKind
    default: Any
    label_en: str
    label_ar: str
    min: str | None
    max: str | None
    options: list[str]
    keys: list[str]
    profile: QProfileScope


# ---- positions, matrix, numbering ---------------------------------------------------------------


class QPositionHolderRead(ApiModel):
    id: uuid.UUID
    user: UserRef
    valid_from: date
    valid_to: date | None


class QPositionRead(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    profile: QProfileScope
    active: bool
    holders: list[QPositionHolderRead]


class QPositionCreate(StrictInput):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,20}$")
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str = Field(min_length=1, max_length=120)
    profile: QProfileScope = QProfileScope.both


class QPositionUpdate(StrictInput):
    name_en: str | None = Field(default=None, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    profile: QProfileScope | None = None
    active: bool | None = None


class QHolderCreate(StrictInput):
    user_id: uuid.UUID
    valid_from: date | None = None
    valid_to: date | None = None


class QHolderEnd(StrictInput):
    valid_to: date | None = None


class QRpRuleRead(ApiModel):
    id: uuid.UUID
    record_type: QRecordType
    step: str
    qualifier: str | None
    record_id: uuid.UUID | None
    assignee_kind: QAssigneeKind
    assignee: str
    self_approval_allowed: bool
    own_tree_allowed: bool
    paper_allowed: bool
    active: bool
    reason: str | None
    part: str | None
    profile: QProfileScope | None
    capability: Capability | None
    step_en: str
    step_ar: str


class QRpRuleCreate(StrictInput):
    record_type: QRecordType
    step: str = Field(max_length=40)
    qualifier: str | None = Field(default=None, max_length=40)
    assignee_kind: QAssigneeKind
    assignee: str = Field(max_length=64, description="User id, role code or position code.")
    self_approval_allowed: bool = False
    own_tree_allowed: bool = False
    paper_allowed: bool = True


class QRpRuleUpdate(StrictInput):
    assignee_kind: QAssigneeKind | None = None
    assignee: str | None = Field(default=None, max_length=64)
    self_approval_allowed: bool | None = None
    own_tree_allowed: bool | None = None
    paper_allowed: bool | None = None
    active: bool | None = None


class QReassign(StrictInput):
    """Q-RPM-09: one pending step on one record (HSE Manager or 239)."""

    record_type: QRecordType
    record_id: uuid.UUID
    step: str = Field(max_length=40)
    assignee_kind: QAssigneeKind
    assignee: str = Field(max_length=64)
    reason: str = Field(min_length=20, max_length=1000)


class QNumberingRead(ApiModel):
    record_type: QRecordType
    prefix: str
    format: str
    reset: QNumberReset
    preview: str
    part: str
    profile: QProfileScope


class QNumberingUpdate(StrictInput):
    format: str = Field(min_length=3, max_length=60)
    reset: QNumberReset = QNumberReset.yearly


class QRecordTypeRead(ApiModel):
    code: QRecordType
    part: str
    profile: QProfileScope
    prefix: str
    en: str
    ar: str
    steps: list[dict[str, Any]]


class QReference(ApiModel):
    """Lists and record types with EN / AR labels (one call for the UI)."""

    record_types: list[QRecordTypeRead]
    labels: dict[str, dict[str, list[str]]]
    positions_default: list[dict[str, str]]


# ---- criteria ----------------------------------------------------------------------------------


class QCriterionRead(ApiModel):
    id: uuid.UUID
    code: str
    version: int
    title_en: str
    title_ar: str
    profile: QProfileScope
    kind: QCriterionKind
    unit: str | None
    min_value: str | None
    max_value: str | None
    target: str | None
    tol_minus: str | None
    tol_plus: str | None
    rule_code: str | None
    params: dict[str, Any]
    reference: str | None
    note_en: str | None
    note_ar: str | None
    project_ids: list[uuid.UUID]
    status: QCriterionStatus
    status_reason: str | None
    published_at: datetime | None
    rule_installed: bool


class QCriterionPage(ApiModel):
    items: list[QCriterionRead]
    total: int
    page: int
    page_size: int


class QCriterionCreate(StrictInput):
    code: str = Field(pattern=r"^[A-Z0-9-]{3,20}$")
    title_en: str = Text150
    title_ar: str = Field(default="", max_length=150)
    profile: QProfileScope = QProfileScope.both
    kind: QCriterionKind
    unit: str | None = Field(default=None, max_length=20)
    min_value: str | None = None
    max_value: str | None = None
    target: str | None = None
    tol_minus: str | None = None
    tol_plus: str | None = None
    rule_code: str | None = Field(default=None, max_length=40)
    params: dict[str, Any] = Field(default_factory=dict)
    reference: str | None = Field(default=None, max_length=120)
    note_en: str | None = Field(default=None, max_length=1000)
    note_ar: str | None = Field(default=None, max_length=1000)
    project_ids: list[uuid.UUID] = Field(default_factory=list)


class QCriterionUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    profile: QProfileScope | None = None
    kind: QCriterionKind | None = None
    unit: str | None = Field(default=None, max_length=20)
    min_value: str | None = None
    max_value: str | None = None
    target: str | None = None
    tol_minus: str | None = None
    tol_plus: str | None = None
    rule_code: str | None = Field(default=None, max_length=40)
    params: dict[str, Any] | None = None
    reference: str | None = Field(default=None, max_length=120)
    note_en: str | None = Field(default=None, max_length=1000)
    note_ar: str | None = Field(default=None, max_length=1000)
    project_ids: list[uuid.UUID] | None = None


class QCriterionTransition(StrictInput):
    action: Literal["publish", "retire"]
    reason: str | None = Field(default=None, max_length=500)


class QEvaluateRequest(StrictInput):
    value: str | float | None = None
    verdict: Literal["pass", "fail"] | None = None
    params: dict[str, Any] = Field(default_factory=dict, description="Inputs of a coded rule.")


class QEvaluateRead(ApiModel):
    criterion_id: uuid.UUID
    code: str
    version: int
    verdict: QVerdict
    reason_en: str
    reason_ar: str


# ---- systems, customers, suppliers, M&TE --------------------------------------------------------


class QSystemRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    discipline: QDiscipline
    parent_id: uuid.UUID | None
    zone_ids: list[uuid.UUID]
    status: QActiveStatus


class QSystemCreate(StrictInput):
    code: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    name_en: str = Text150
    name_ar: str = Text150
    discipline: QDiscipline
    parent_id: uuid.UUID | None = None
    zone_ids: list[uuid.UUID] = Field(default_factory=list)


class QSystemUpdate(StrictInput):
    name_en: str | None = Field(default=None, max_length=150)
    name_ar: str | None = Field(default=None, max_length=150)
    discipline: QDiscipline | None = None
    parent_id: uuid.UUID | None = None
    zone_ids: list[uuid.UUID] | None = None
    status: QActiveStatus | None = None


class QCustomerRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    kind: QCustomerKind
    owner_release_approval: bool
    status: QCustomerStatus
    contact_name: str | None
    contact_mobile: str | None
    contact_email: str | None
    contacts_visible: bool


class QCustomerCreate(StrictInput):
    code: str = Field(pattern=r"^[A-Z0-9-]{2,12}$")
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    kind: QCustomerKind
    owner_release_approval: bool = False
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, max_length=20)
    contact_email: str | None = Field(default=None, max_length=254)


class QCustomerUpdate(StrictInput):
    name_en: str | None = Field(default=None, max_length=200)
    name_ar: str | None = Field(default=None, max_length=200)
    kind: QCustomerKind | None = None
    owner_release_approval: bool | None = None
    status: QCustomerStatus | None = None
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, max_length=20)
    contact_email: str | None = Field(default=None, max_length=254)


class QAccreditationRead(ApiModel):
    id: uuid.UUID
    body: QAccreditationBody
    standard: QAccreditationStandard
    number: str
    scope_text: str | None
    scope_codes: list[str]
    valid_from: date | None
    valid_until: date
    valid: bool


class QSupplierRead(ApiModel):
    id: uuid.UUID
    supplier_code: str
    legal_name_en: str
    legal_name_ar: str
    cr_number: str | None
    vat_number: str | None
    country: str
    categories: list[QSupplierCategory]
    contractor_id: uuid.UUID | None
    contractor_code: str | None
    tpi_id: uuid.UUID | None
    scope_en: str | None
    scope_ar: str | None
    contact_name: str | None
    contact_mobile: str | None
    contact_email: str | None
    contacts_visible: bool
    status: QSupplierStatus
    status_reason: str | None
    status_changed_at: datetime | None
    approved_scope: str | None
    next_evaluation_due: date | None
    accreditations: list[QAccreditationRead]


class QSupplierPage(ApiModel):
    items: list[QSupplierRead]
    total: int
    page: int
    page_size: int


class QSupplierCreate(StrictInput):
    supplier_code: str = Field(pattern=r"^[A-Z0-9-]{2,12}$")
    legal_name_en: str = Field(min_length=1, max_length=200)
    legal_name_ar: str = Field(min_length=1, max_length=200)
    categories: list[QSupplierCategory] = Field(min_length=1)
    cr_number: str | None = Field(default=None, pattern=r"^[1-7]\d{9}$")
    vat_number: str | None = Field(default=None, max_length=15)
    country: str = Field(default="SA", min_length=2, max_length=2)
    contractor_id: uuid.UUID | None = None
    tpi_id: uuid.UUID | None = None
    scope_en: str | None = Field(default=None, max_length=500)
    scope_ar: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, max_length=20)
    contact_email: str | None = Field(default=None, max_length=254)


class QSupplierUpdate(StrictInput):
    legal_name_en: str | None = Field(default=None, max_length=200)
    legal_name_ar: str | None = Field(default=None, max_length=200)
    categories: list[QSupplierCategory] | None = None
    cr_number: str | None = Field(default=None, pattern=r"^[1-7]\d{9}$")
    vat_number: str | None = Field(default=None, max_length=15)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    contractor_id: uuid.UUID | None = None
    tpi_id: uuid.UUID | None = None
    scope_en: str | None = Field(default=None, max_length=500)
    scope_ar: str | None = Field(default=None, max_length=500)
    approved_scope: str | None = Field(default=None, max_length=1000)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, max_length=20)
    contact_email: str | None = Field(default=None, max_length=254)


class QAccreditationCreate(StrictInput):
    body: QAccreditationBody
    standard: QAccreditationStandard
    number: str = Field(min_length=1, max_length=60)
    scope_text: str | None = Field(default=None, max_length=1000)
    scope_codes: list[str] = Field(default_factory=list)
    valid_from: date | None = None
    valid_until: date


class QSupplierTransition(StrictInput):
    to_status: QSupplierStatus
    reason: str | None = Field(default=None, max_length=1000)
    project_id: uuid.UUID | None = Field(
        default=None, description="Project whose matrix resolves supplier.approve / .suspend."
    )
    condition: str | None = Field(default=None, max_length=1000)


class QMteRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    mte_no: str
    mte_type: QMteType
    description: str
    manufacturer: str | None
    model: str | None
    serial_no: str | None
    range_text: str | None
    resolution: str | None
    tolerance_value: str | None
    tolerance_unit: str | None
    owner_kind: QMteOwnerKind
    owner_engagement_id: uuid.UUID | None
    owner_supplier_id: uuid.UUID | None
    site_id: uuid.UUID | None
    site_code: str | None
    zone_id: uuid.UUID | None
    zone_code: str | None
    custodian_user_id: uuid.UUID | None
    check_kind: QMteCheckKind
    interval_months: int | None
    cal_status: QCalStatus
    cal_status_reason: str | None
    cal_due_on: date | None
    last_calibration_id: uuid.UUID | None
    equipment_item_id: uuid.UUID | None
    status: QMteStatus
    label_printed_at: datetime | None


class QMtePage(ApiModel):
    items: list[QMteRead]
    total: int
    page: int
    page_size: int


class QMteCreate(StrictInput):
    mte_type: QMteType
    description: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_no: str | None = Field(default=None, max_length=80)
    range_text: str | None = Field(default=None, max_length=80)
    resolution: str | None = Field(default=None, max_length=40)
    tolerance_value: str | None = None
    tolerance_unit: str | None = Field(default=None, max_length=20)
    owner_kind: QMteOwnerKind = QMteOwnerKind.own
    owner_engagement_id: uuid.UUID | None = None
    owner_supplier_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    custodian_user_id: uuid.UUID | None = None
    check_kind: QMteCheckKind = QMteCheckKind.calibration
    interval_months: int | None = Field(default=None, ge=1, le=120)
    equipment_item_id: uuid.UUID | None = None


class QMteUpdate(StrictInput):
    mte_type: QMteType | None = None
    description: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_no: str | None = Field(default=None, max_length=80)
    range_text: str | None = Field(default=None, max_length=80)
    resolution: str | None = Field(default=None, max_length=40)
    tolerance_value: str | None = None
    tolerance_unit: str | None = Field(default=None, max_length=20)
    owner_kind: QMteOwnerKind | None = None
    owner_engagement_id: uuid.UUID | None = None
    owner_supplier_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    custodian_user_id: uuid.UUID | None = None
    check_kind: QMteCheckKind | None = None
    interval_months: int | None = Field(default=None, ge=1, le=120)
    equipment_item_id: uuid.UUID | None = None
    status: QMteStatus | None = None


class QMteUsageCreate(StrictInput):
    record_type: QRecordType
    record_id: uuid.UUID
    used_at: datetime | None = None
    value_note: str | None = Field(default=None, max_length=200)


class QMteUsageRead(ApiModel):
    id: uuid.UUID
    mte_id: uuid.UUID
    record_type: str
    record_id: uuid.UUID
    used_at: datetime
    verdict: QMteUseVerdict
    cal_status_at_use: QCalStatus
    value_note: str | None
    warnings: list[ApiWarning] = Field(default_factory=list)


# ---- links, sign-offs, awaiting, home -----------------------------------------------------------


class QLinkRead(ApiModel):
    id: uuid.UUID
    kind: QLinkKind
    direction: Literal["outgoing", "incoming"]
    record_type: str
    record_id: uuid.UUID
    ref: str | None
    title: str | None
    link_path: str | None
    voided: bool
    visible: bool
    created_at: datetime


class QLinkCreate(StrictInput):
    from_type: QRecordType
    from_id: uuid.UUID
    to_type: QRecordType
    to_id: uuid.UUID
    kind: QLinkKind = QLinkKind.relates


class QSignoffRead(ApiModel):
    id: uuid.UUID
    record_type: str
    record_id: uuid.UUID
    step: str
    decision: str
    comment: str | None
    signed_by: UserRef
    signed_at: datetime
    signer_capacity: str
    channel: QSignoffChannel
    external_name: str | None
    external_organisation: str | None
    external_position: str | None
    external_signed_on: date | None
    evidence_attachment_ids: list[uuid.UUID]
    text_en: str
    text_ar: str


class QPendingItem(ApiModel):
    record_type: QRecordType
    record_id: uuid.UUID
    project_id: uuid.UUID
    ref: str
    title: str
    step: str
    waiting_since: datetime
    waiting_hours: int
    link_path: str
    part: str


class QAwaitingRead(ApiModel):
    count: int
    items: list[QPendingItem]


class QHomeRead(ApiModel):
    project_id: uuid.UUID
    sector_profile: QSectorProfile | None
    needs_profile: bool
    can_configure: bool
    awaiting_count: int
    ncr_by_class: dict[str, int]
    ncr_by_status: dict[str, int]
    ncr_open: int
    ncr_overdue: int
    containment_overdue: int
    steps_without_rp: list[dict[str, Any]]
    stop_use_alerts: list[dict[str, Any]]
    my_open_ncrs: list[dict[str, Any]]
    tiles: list[dict[str, Any]]


# ---- NCR ----------------------------------------------------------------------------------------


class QSupplierRef(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    status: QSupplierStatus


class QCaSummary(ApiModel):
    id: uuid.UUID
    ref: str
    title: str
    status: CaStatus
    priority: CaPriority
    control_level: ControlLevel
    due_date: date
    owner_id: uuid.UUID
    verifier_id: uuid.UUID


class QNcrListItem(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    ncr_no: str | None
    title: str
    status: QNcrStatus
    classification: QNcrClass | None
    category: QNcrCategory | None
    source_type: QNcrSourceType
    source_ref: str | None
    detection_stage: QDetectionStage | None
    profile: QSectorProfile
    site_code: str | None
    responsible_engagement: EngagementRef | None
    supplier: QSupplierRef | None
    owner: UserRef | None = Field(description="Null for the Viewer / Client (P8).")
    opened_at: datetime | None
    target_close_date: date | None
    closed_date: date | None
    age_days: int | None
    overdue: bool
    repeat: bool
    cost_gross_sar: str | None = Field(description="Null for the Viewer / Client.")
    before_quality_start: bool


class QNcrPage(ApiModel):
    items: list[QNcrListItem]
    total: int
    page: int
    page_size: int


class QNcrStepRead(ApiModel):
    step: str
    pending: bool
    responsible_set: bool
    resolvers: list[UserRef | None]
    me: bool


class QNcrRcaRead(ApiModel):
    method: QRcaMethod
    data: dict[str, Any]
    root_cause: str | None
    cause_category: QCauseCategory | None
    complete: bool


class QNcrLineRead(ApiModel):
    id: uuid.UUID
    disposition: QDisposition
    quantity: str | None
    note: str | None
    repair_procedure: str | None
    return_ref: str | None
    destruction_evidenced: bool


class QNcrCostRead(ApiModel):
    id: uuid.UUID
    cost_type: QCostType
    description: str | None
    quantity: str
    unit: str | None
    rate_sar: str
    amount_sar: str
    recoverable: bool
    recovered_sar: str
    entered_at: datetime


class QNcrRead(QNcrListItem):
    source_id: uuid.UUID | None
    item_key: str | None
    site: SiteRef
    zone: ZoneRef | None
    system_id: uuid.UUID | None
    location_ref: str | None
    requirement_en: str | None
    requirement_ar: str | None
    finding_en: str | None
    finding_ar: str | None
    customer_id: uuid.UUID | None
    quantity: str | None
    unit: str | None
    lot_refs: list[str]
    raised_by: UserRef | None
    opened_date: date | None
    containment_en: str | None
    containment_ar: str | None
    containment_done_at: datetime | None
    containment_by: UserRef | None
    containment_due_at: datetime | None
    containment_overdue: bool
    no_product_affected: bool
    cause_category: QCauseCategory | None
    rca: QNcrRcaRead | None
    disposition_lines: list[QNcrLineRead]
    disposition_justification_en: str | None
    disposition_justification_ar: str | None
    disposition_proposed_at: datetime | None
    disposition_approved_at: datetime | None
    implementation_note: str | None
    implemented_at: datetime | None
    supplier_response: dict[str, Any] | None
    repeat_of: dict[str, Any] | None
    closed_at: datetime | None
    closure_days: int | None
    on_time: bool | None
    effectiveness: dict[str, Any] | None
    no_cost_reason: str | None
    cost_recovered_sar: str | None
    cost_net_sar: str | None
    failure_class: Literal["internal", "external"] | None
    cost_lines: list[QNcrCostRead]
    cost_lines_visible: bool
    duplicate_of_id: uuid.UUID | None
    status_reason: str | None
    reopened_count: int
    actions: list[QCaSummary]
    steps: list[QNcrStepRead]
    signoffs: list[QSignoffRead]
    links: list[QLinkRead]
    photo_count: int
    evidence_count: int
    allowed_actions: list[str]
    names_hidden: bool
    warnings: list[ApiWarning]
    created_at: datetime
    updated_at: datetime


class QNcrCreate(StrictInput):
    """Draft (or with `open = true`, opened at once). From a source the adapter fills site, zone,
    system, engagement, supplier, item key, detection stage, title and requirement (Q-NCR-02)."""

    source_type: QNcrSourceType = QNcrSourceType.manual
    source_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=150)
    requirement_en: str | None = Field(default=None, max_length=1000)
    requirement_ar: str | None = Field(default=None, max_length=1000)
    finding_en: str | None = Field(default=None, max_length=2000)
    finding_ar: str | None = Field(default=None, max_length=2000)
    category: QNcrCategory | None = None
    detection_stage: QDetectionStage | None = None
    classification: QNcrClass | None = None
    responsible_engagement_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    quantity: str | None = None
    unit: str | None = Field(default=None, max_length=10)
    lot_refs: list[str] | None = Field(default=None, max_length=50)
    owner_id: uuid.UUID | None = None
    client_uuid: uuid.UUID | None = Field(default=None, description="Offline draft idempotency.")
    open: bool = False


class QNcrUpdate(StrictInput):
    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=150)
    requirement_en: str | None = Field(default=None, max_length=1000)
    requirement_ar: str | None = Field(default=None, max_length=1000)
    finding_en: str | None = Field(default=None, max_length=2000)
    finding_ar: str | None = Field(default=None, max_length=2000)
    category: QNcrCategory | None = None
    detection_stage: QDetectionStage | None = None
    classification: QNcrClass | None = None
    responsible_engagement_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    quantity: str | None = None
    unit: str | None = Field(default=None, max_length=10)
    lot_refs: list[str] | None = Field(default=None, max_length=50)
    owner_id: uuid.UUID | None = None


class QNcrClassChange(StrictInput):
    classification: QNcrClass
    reason: str | None = Field(default=None, max_length=1000)


class QNcrContainment(StrictInput):
    containment_en: str | None = Field(default=None, max_length=1000)
    containment_ar: str | None = Field(default=None, max_length=1000)
    no_product_affected: bool | None = None
    done: bool = False


class QNcrRcaSave(StrictInput):
    method: QRcaMethod
    data: dict[str, Any] = Field(default_factory=dict)
    root_cause: str | None = Field(default=None, max_length=2000)
    cause_category: QCauseCategory | None = None
    final: bool = Field(default=True, description="Check completeness now (RCA_INCOMPLETE).")


class QNcrLineInput(StrictInput):
    disposition: QDisposition
    quantity: str | None = None
    note: str | None = Field(default=None, max_length=1000)
    repair_procedure: str | None = Field(default=None, max_length=300)
    return_ref: str | None = Field(default=None, max_length=80)
    destruction_evidenced: bool = False


class QNcrDispositionSave(StrictInput):
    lines: list[QNcrLineInput]
    disposition_justification_en: str | None = Field(default=None, max_length=2000)
    disposition_justification_ar: str | None = Field(default=None, max_length=2000)


class QNcrLineUpdate(StrictInput):
    return_ref: str | None = Field(default=None, max_length=80)
    destruction_evidenced: bool | None = None
    note: str | None = Field(default=None, max_length=1000)


class QPaperScan(StrictInput):
    file_name: str = Field(max_length=255)
    content_base64: str


class QPaperSignoff(StrictInput):
    """Q-RPM-08: the decision of an external signatory recorded with ≥ 1 signed scan."""

    name: str = Field(min_length=1, max_length=120)
    organisation: str = Field(min_length=1, max_length=150)
    position: str = Field(min_length=1, max_length=120)
    signed_on: date
    scans: list[QPaperScan] = Field(default_factory=list)


class QNcrSign(StrictInput):
    step: Literal["disposition", "concession", "close"]
    decision: Literal["approved", "returned", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)
    paper: QPaperSignoff | None = None


class QNcrImplement(StrictInput):
    implementation_note: str | None = Field(default=None, max_length=1000)


class QReasonInput(StrictInput):
    reason: str = Field(min_length=1, max_length=2000)


class QNcrVoid(StrictInput):
    reason: str = Field(min_length=1, max_length=2000)
    duplicate_of: uuid.UUID | None = None


class QNcrCostCreate(StrictInput):
    cost_type: QCostType
    description: str | None = Field(default=None, max_length=300)
    quantity: str | None = Field(
        default=None, description="Hours, days or units; 1 for a lump sum."
    )
    unit: str | None = Field(default=None, max_length=10)
    rate_sar: str | None = Field(default=None, description="Defaults to the project rate.")
    recoverable: bool = False
    recovered_sar: str | None = None


class QNcrCostUpdate(StrictInput):
    description: str | None = Field(default=None, max_length=300)
    recovered_sar: str | None = None


class QNcrNoCost(StrictInput):
    reason: str | None = Field(default=None, max_length=500)


class QNcrActionCreate(StrictInput):
    """A Phase 1 CA (source quality_ncr) created inline (Q-CAP-02 / -03)."""

    title: str = Text150
    description: str = Field(min_length=1, max_length=2000)
    control_level: ControlLevel
    priority: CaPriority | None = Field(default=None, description="Default from the NCR class.")
    priority_reason: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID
    verifier_id: uuid.UUID
    responsible_engagement_id: uuid.UUID | None = None
    due_date: date | None = None


class QNcrEffectiveness(StrictInput):
    result: QEffectiveness
    note: str | None = Field(default=None, max_length=1000)


class QNcrSupplierResponse(StrictInput):
    action: Literal["request", "receive", "accept", "reject"]
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)


# ---- observations, alerts, complaints -----------------------------------------------------------


class QObservationRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    obs_no: str
    site_id: uuid.UUID
    site_code: str | None
    zone_id: uuid.UUID | None
    system_id: uuid.UUID | None
    location_ref: str | None
    engagement_id: uuid.UUID | None
    category: QNcrCategory
    description: str
    suggested_action: str | None
    raised_by: UserRef | None
    raised_at: datetime
    status: QObservationStatus
    status_reason: str | None
    closed_at: datetime | None
    ncr_id: uuid.UUID | None
    actions: list[QCaSummary]
    links: list[QLinkRead]
    warnings: list[ApiWarning]


class QObservationPage(ApiModel):
    items: list[QObservationRead]
    total: int
    page: int
    page_size: int


class QObservationCreate(StrictInput):
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    system_id: uuid.UUID | None = None
    location_ref: str | None = Field(default=None, max_length=120)
    engagement_id: uuid.UUID | None = None
    category: QNcrCategory
    description: str = Field(min_length=10, max_length=2000)
    suggested_action: str | None = Field(default=None, max_length=1000)


class QAlertRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    alert_no: str | None
    title_en: str
    title_ar: str
    message_en: str
    message_ar: str
    severity: QAlertSeverity
    applies_to: str | None
    site_ids: list[uuid.UUID]
    supplier_ids: list[uuid.UUID]
    lot_refs: list[str]
    valid_until: date | None
    dist_roles: list[str]
    dist_positions: list[str]
    dist_engagement_ids: list[uuid.UUID]
    dist_user_ids: list[uuid.UUID]
    ack_required: bool
    status: QAlertStatus
    status_reason: str | None
    issued_at: datetime | None
    recipient_count: int
    ack_count: int
    ack_pct: str | None
    i_am_recipient: bool
    i_acked: bool
    can_ack: bool
    warnings: list[ApiWarning] = Field(default_factory=list)


class QAlertPage(ApiModel):
    items: list[QAlertRead]
    total: int
    page: int
    page_size: int


class QAlertCreate(StrictInput):
    title_en: str = Field(min_length=1, max_length=200)
    title_ar: str = Field(min_length=1, max_length=200)
    message_en: str = Field(min_length=1, max_length=2000)
    message_ar: str = Field(min_length=1, max_length=2000)
    severity: QAlertSeverity
    applies_to: str | None = Field(default=None, max_length=1000)
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    supplier_ids: list[uuid.UUID] = Field(default_factory=list)
    lot_refs: list[str] = Field(default_factory=list)
    valid_until: date | None = None
    dist_roles: list[str] = Field(default_factory=list)
    dist_positions: list[str] = Field(default_factory=list)
    dist_engagement_ids: list[uuid.UUID] = Field(default_factory=list)
    dist_user_ids: list[uuid.UUID] = Field(default_factory=list)
    ack_required: bool = False


class QAlertUpdate(StrictInput):
    title_en: str | None = Field(default=None, max_length=200)
    title_ar: str | None = Field(default=None, max_length=200)
    message_en: str | None = Field(default=None, max_length=2000)
    message_ar: str | None = Field(default=None, max_length=2000)
    severity: QAlertSeverity | None = None
    applies_to: str | None = Field(default=None, max_length=1000)
    site_ids: list[uuid.UUID] | None = None
    lot_refs: list[str] | None = None
    valid_until: date | None = None
    dist_roles: list[str] | None = None
    dist_positions: list[str] | None = None
    dist_engagement_ids: list[uuid.UUID] | None = None
    dist_user_ids: list[uuid.UUID] | None = None
    ack_required: bool | None = None


class QCommentInput(StrictInput):
    comment: str | None = Field(default=None, max_length=1000)


class QComplaintRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    complaint_no: str
    customer: dict[str, Any] | None
    site_id: uuid.UUID | None
    received_at: datetime
    channel: QComplaintChannel
    customer_reference: str | None
    category: QNcrCategory
    description: str
    product_refs: str | None
    severity: QComplaintSeverity
    acknowledged_at: datetime | None
    ack_method: str | None
    ack_due_at: datetime
    ack_overdue: bool
    response_due_at: datetime
    response_overdue: bool
    investigation_note: str | None
    justified: QJustified | None
    ncr: dict[str, Any] | None
    response_en: str | None
    response_ar: str | None
    responded_at: datetime | None
    satisfied: QSatisfaction | None
    closed_at: datetime | None
    status: QComplaintStatus
    status_reason: str | None
    actions: list[QCaSummary]
    signoffs: list[QSignoffRead]
    links: list[QLinkRead]
    warnings: list[ApiWarning] = Field(default_factory=list)


class QComplaintPage(ApiModel):
    items: list[QComplaintRead]
    total: int
    page: int
    page_size: int


class QComplaintCreate(StrictInput):
    customer_id: uuid.UUID
    site_id: uuid.UUID | None = None
    received_at: datetime | None = None
    channel: QComplaintChannel
    customer_reference: str | None = Field(default=None, max_length=80)
    category: QNcrCategory
    description: str = Field(min_length=10, max_length=2000)
    product_refs: str | None = Field(default=None, max_length=500)
    severity: QComplaintSeverity


class QComplaintTransition(StrictInput):
    to_status: QComplaintStatus
    acknowledged_at: datetime | None = None
    ack_method: str | None = Field(default=None, max_length=40)
    investigation_note: str | None = Field(default=None, max_length=2000)
    justified: QJustified | None = None
    ncr_id: uuid.UUID | None = None
    response_en: str | None = Field(default=None, max_length=2000)
    response_ar: str | None = Field(default=None, max_length=2000)
    satisfied: QSatisfaction | None = None
    comment: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=1000)


# ---- checklists (6d kind quality, §A.7) ----------------------------------------------------------


class QChecklistTypeRead(ApiModel):
    code: str
    part: str
    profile: QProfileScope
    owner_type: str | None
