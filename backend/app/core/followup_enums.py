"""Phase 6f enumerations — incident follow-up (spec 6f-incident-followup v1.0, §3.11 lists and §4
states). Every class carries the `Fu` prefix so no name clashes with earlier modules in the OpenAPI
contract (DECISIONS D-202). EN/AR labels are served by GET /followup-reference."""

from enum import StrEnum


class FuStage(StrEnum):
    verbal = "verbal"
    written = "written"
    interim = "interim"
    final = "final"


class FuRuleSource(StrEnum):
    statutory = "statutory"
    client = "client"


class FuTrigger(StrEnum):
    """List NT."""

    recordable_contractor_case = "recordable_contractor_case"
    commuting_case = "commuting_case"
    fatality = "fatality"
    permanent_disability = "permanent_disability"
    lti = "lti"
    fire_explosion_do = "fire_explosion_do"
    any_do = "any_do"
    hipo = "hipo"
    gaca_airside_flag = "gaca_airside_flag"
    any_airside_flag = "any_airside_flag"
    env_ncec = "env_ncec"
    env_airside = "env_airside"
    any_recordable_case = "any_recordable_case"
    property_damage_ge_sar = "property_damage_ge_sar"


class FuDeadlineBasis(StrEnum):
    trigger = "trigger"
    investigation_due = "investigation_due"


class FuForm(StrEnum):
    """List PF."""

    GOSI_WIR = "GOSI-WIR"
    MHRSD_LTR = "MHRSD-LTR"
    CD_LTR = "CD-LTR"
    GACA_OCR = "GACA-OCR"
    AO_OCR = "AO-OCR"
    NCEC_EIR = "NCEC-EIR"
    CLIENT_FLASH = "CLIENT-FLASH"
    CLIENT_INTERIM = "CLIENT-INTERIM"
    CLIENT_FINAL = "CLIENT-FINAL"


class FuFiler(StrEnum):
    main_contractor = "main_contractor"
    employer_engagement = "employer_engagement"
    airport_operator = "airport_operator"


class FuFieldSet(StrEnum):
    """List FS."""

    none = "none"
    identity = "identity"
    identity_medical = "identity_medical"


class FuWaiverReason(StrEnum):
    """List WV."""

    not_covered_by_gosi = "not_covered_by_gosi"
    body_confirmed_not_required = "body_confirmed_not_required"
    reported_by_other_party = "reported_by_other_party"
    incident_reclassified = "incident_reclassified"


class FuRequirementStatus(StrEnum):
    """§4.1 (derived)."""

    due = "due"
    overdue = "overdue"
    submitted = "submitted"
    acknowledged = "acknowledged"
    waived = "waived"
    not_required = "not_required"


class FuPackStatus(StrEnum):
    """§4.2."""

    draft = "draft"
    approved = "approved"
    submitted = "submitted"
    superseded = "superseded"


class FuPackAction(StrEnum):
    approve = "approve"
    return_to_draft = "return_to_draft"


class FuChannel(StrEnum):
    portal = "portal"
    email = "email"
    hand_delivered = "hand_delivered"
    courier = "courier"
    phone_radio = "phone_radio"
    meeting = "meeting"


class FuSubmissionStatus(StrEnum):
    recorded = "recorded"
    acknowledged = "acknowledged"
    voided = "voided"


class FuRecipientRole(StrEnum):
    client = "client"
    pmc = "pmc"


class FuClientIdentity(StrEnum):
    none = "none"
    name_and_trade = "name_and_trade"


class FuLessonSource(StrEnum):
    incident = "incident"
    external = "external"


class FuLessonStatus(StrEnum):
    """§4.4."""

    draft = "draft"
    in_review = "in_review"
    published = "published"
    archived = "archived"


class FuLessonAction(StrEnum):
    submit = "submit"
    return_to_draft = "return_to_draft"
    publish = "publish"
    archive = "archive"


class FuAckResponse(StrEnum):
    will_brief = "will_brief"
    not_applicable = "not_applicable"


class FuDistributionStatus(StrEnum):
    pending = "pending"
    acknowledged = "acknowledged"
    not_applicable = "not_applicable"
    withdrawn = "withdrawn"


class FuLinkKind(StrEnum):
    topic = "topic"
    campaign = "campaign"
    template_change = "template_change"


class FuChangeStatus(StrEnum):
    open = "open"
    adopted = "adopted"
    rejected = "rejected"


class FuEffectResult(StrEnum):
    effective = "effective"
    partly_effective = "partly_effective"
    not_effective = "not_effective"


class FuCheckStatus(StrEnum):
    scheduled = "scheduled"
    completed = "completed"


class FuActionKind(StrEnum):
    """§8.2 action-panel items."""

    requirements_overdue = "requirements_overdue"
    packs_awaiting_approval = "packs_awaiting_approval"
    lessons_past_publish_due = "lessons_past_publish_due"
    acknowledgements_overdue = "acknowledgements_overdue"
    effectiveness_checks_overdue = "effectiveness_checks_overdue"
    template_changes_open = "template_changes_open"


class FuKpiGroupBy(StrEnum):
    body = "body"
    stage = "stage"
    month = "month"
    contractor = "contractor"
