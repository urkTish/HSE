"""Phase 6d enumerations — field assurance (spec 6d-field-assurance v1.0, §3.15 lists and §4
states). Exported into the OpenAPI contract so the frontend gets typed unions."""

from enum import StrEnum


class TemplateKind(StrEnum):
    """§3.1."""

    inspection = "inspection"
    audit = "audit"


class AuditType(StrEnum):
    """List AT (client_requested counts as contractor_hse when an auditee is set)."""

    contractor_hse = "contractor_hse"
    system_iso45001 = "system_iso45001"
    client_requested = "client_requested"


class VersionStatus(StrEnum):
    """§4.1 template and topic versions."""

    draft = "draft"
    published = "published"
    superseded = "superseded"
    retired = "retired"


class VersionAction(StrEnum):
    publish = "publish"
    retire = "retire"


class ItemType(StrEnum):
    """List IT."""

    yes_no = "yes_no"
    rating_0_3 = "rating_0_3"
    numeric = "numeric"
    single_select = "single_select"
    text = "text"
    photo = "photo"
    count_ = "count"


SCORED_TYPES = frozenset(
    {ItemType.yes_no, ItemType.rating_0_3, ItemType.numeric, ItemType.single_select}
)


class StopRule(StrEnum):
    none = "none"
    stop_work = "stop_work"


class OptionMapping(StrEnum):
    compliant = "compliant"
    non_compliant = "non_compliant"
    info = "info"


class YesNoAnswer(StrEnum):
    compliant = "compliant"
    non_compliant = "non_compliant"
    na = "na"


class FindingSeverity(StrEnum):
    """List FS (inspections) ∪ list AF (audits)."""

    minor = "minor"
    major = "major"
    critical = "critical"
    major_nc = "major_nc"
    minor_nc = "minor_nc"
    observation = "observation"
    ofi = "ofi"


INSPECTION_SEVERITIES = (FindingSeverity.minor, FindingSeverity.major, FindingSeverity.critical)
AUDIT_GRADES = (
    FindingSeverity.ofi,
    FindingSeverity.observation,
    FindingSeverity.minor_nc,
    FindingSeverity.major_nc,
)


class AuditGrade(StrEnum):
    """List AG."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ResponseResult(StrEnum):
    pass_ = "pass"
    fail = "fail"


class ResponseOwnerType(StrEnum):
    inspection = "inspection"
    audit = "audit"


class Rotation(StrEnum):
    """ISP-2."""

    none = "none"
    zones = "zones"
    engagements = "engagements"


class StopOrderStatus(StrEnum):
    """§4.3."""

    active = "active"
    released = "released"
    voided = "voided"


class InstructedRole(StrEnum):
    supervisor = "supervisor"
    foreman = "foreman"
    operator = "operator"
    permit_receiver = "permit_receiver"
    other = "other"


class AuditStatus(StrEnum):
    """§4.4."""

    planned = "planned"
    in_progress = "in_progress"
    fieldwork_complete = "fieldwork_complete"
    issued = "issued"
    closed = "closed"
    cancelled = "cancelled"
    voided = "voided"


class AuditAction(StrEnum):
    start = "start"
    complete_fieldwork = "complete_fieldwork"
    issue = "issue"
    cancel = "cancel"
    void = "void"


class ProgrammeScope(StrEnum):
    engagement = "engagement"
    project = "project"


class ProgrammeLineStatus(StrEnum):
    due = "due"
    overdue = "overdue"


class TopicCategory(StrEnum):
    """Phase 1 list O ∪ {general, emergency, health}."""

    work_at_height = "work_at_height"
    lifting = "lifting"
    excavation = "excavation"
    scaffolding = "scaffolding"
    electrical = "electrical"
    hot_work = "hot_work"
    ppe = "ppe"
    housekeeping = "housekeeping"
    traffic_plant = "traffic_plant"
    airside_fod_control = "airside_fod_control"
    airside_driving = "airside_driving"
    heat_stress = "heat_stress"
    confined_space = "confined_space"
    manual_handling = "manual_handling"
    tools_equipment = "tools_equipment"
    environmental = "environmental"
    fire_safety = "fire_safety"
    welfare = "welfare"
    permit_compliance = "permit_compliance"
    behaviour_other = "behaviour_other"
    general = "general"
    emergency = "emergency"
    health = "health"


class LinkedRefKind(StrEnum):
    incident = "incident"
    observation_category = "observation_category"
    template_item = "template_item"
    lesson = "lesson"


class TalkShift(StrEnum):
    day = "day"
    night = "night"


class TalkStatus(StrEnum):
    """§4.6."""

    delivered = "delivered"
    locked = "locked"
    voided = "voided"


class AttendanceMethod(StrEnum):
    card_scan = "card_scan"
    list = "list"


class UnderstoodLanguage(StrEnum):
    """TBT-6 (as Phase 5 AT-6)."""

    talk_language = "talk_language"
    interpreter = "interpreter"
    none = "none"


class CampaignReason(StrEnum):
    incident = "incident"
    lesson = "lesson"
    client_instruction = "client_instruction"
    regulatory = "regulatory"
    seasonal = "seasonal"
    audit_finding = "audit_finding"


class CampaignStatus(StrEnum):
    """§4.5."""

    draft = "draft"
    issued = "issued"
    closed = "closed"
    cancelled = "cancelled"


class CampaignAction(StrEnum):
    issue = "issue"
    cancel = "cancel"


class SuggestionSource(StrEnum):
    """TBT-9 order."""

    campaign = "campaign"
    lesson = "lesson"
    incident = "incident"
    failed_item = "failed_item"
    observation_category = "observation_category"


class FieldActionKind(StrEnum):
    """§8.2 action-panel items."""

    stop_work_active = "stop_work_active"
    plan_without_checklist = "plan_without_checklist"
    not_inspected_this_week = "not_inspected_this_week"
    audit_lines_overdue = "audit_lines_overdue"
    audit_reports_overdue = "audit_reports_overdue"
    campaigns_unmet = "campaigns_unmet"
    offline_rejected = "offline_rejected"


class FieldKpiGroupBy(StrEnum):
    """FM-2 / §8.1 breakdowns (aggregates only)."""

    inspection_type = "inspection_type"
    template = "template"
    item_code = "item_code"
    contractor = "contractor"
    zone = "zone"
    month = "month"
    language = "language"
