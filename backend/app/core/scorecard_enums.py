"""Phase 6g enumerations — contractor HSE scorecard, report packs and the generic register export
(spec 6g-scorecard-reports v1.0, §3.10 lists and §4 states). Every class carries the `Sc`
(scorecard), `Rp` (report packs) or `Xp` (exports) prefix so no name clashes with earlier modules
in the OpenAPI contract (DECISIONS D-202). EN/AR labels are served by GET /scorecard-reference."""

from enum import StrEnum

# ---- scorecard ---------------------------------------------------------------------------------


class ScPillar(StrEnum):
    """List PL."""

    LAG = "LAG"
    OBS = "OBS"
    CA = "CA"
    PTW = "PTW"
    CERT = "CERT"
    TRN = "TRN"
    FIT = "FIT"
    HEAT = "HEAT"
    EMG = "EMG"
    INS = "INS"
    TBT = "TBT"
    ENV = "ENV"
    NOT = "NOT"


class ScMetric(StrEnum):
    """List SM (default profile ORG v1)."""

    TRIR = "SM-TRIR"
    LTIFR = "SM-LTIFR"
    LTISR = "SM-LTISR"
    HIPO = "SM-HIPO"
    OBS = "SM-OBS"
    UNSAFE_CLOSE = "SM-UNSAFE-CLOSE"
    CA_ONTIME = "SM-CA-ONTIME"
    CA_OVERDUE = "SM-CA-OVERDUE"
    PTW_AUDIT = "SM-PTW-AUDIT"
    PTW_CRIT = "SM-PTW-CRIT"
    PTW_CLOSE = "SM-PTW-CLOSE"
    EQ_CERT = "SM-EQ-CERT"
    PERS_CERT = "SM-PERS-CERT"
    SCAF_TAG = "SM-SCAF-TAG"
    TRAIN = "SM-TRAIN"
    INDUCT = "SM-INDUCT"
    FIT = "SM-FIT"
    HEAT_WELF = "SM-HEAT-WELF"
    HEAT_BAN = "SM-HEAT-BAN"
    EMG_COVER = "SM-EMG-COVER"
    EMG_EQUIP = "SM-EMG-EQUIP"
    CHECKLIST = "SM-CHECKLIST"
    INSP_COVER = "SM-INSP-COVER"
    AUDIT = "SM-AUDIT"
    TBT = "SM-TBT"
    WASTE_COC = "SM-WASTE-COC"
    SPILL = "SM-SPILL"
    NOTIF = "SM-NOTIF"
    LESSON_ACK = "SM-LESSON-ACK"


class ScWindow(StrEnum):
    r12_rate = "r12_rate"
    month = "month"
    month_end = "month_end"
    latest_3m = "latest_3m"


class ScCap(StrEnum):
    """List CP."""

    CP1 = "CP-1"
    CP2 = "CP-2"
    CP3 = "CP-3"


class ScGrade(StrEnum):
    """List GB (`—` = null grade: insufficient coverage)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ScModule(StrEnum):
    """Keys of `source_live_from` (SN-5): the module that feeds each pillar's metrics."""

    phase1 = "phase1"
    access = "access"
    ptw = "ptw"
    cert = "cert"
    training = "training"
    medical = "medical"
    heat = "heat"
    emergency = "emergency"
    field = "field"
    toolbox = "toolbox"
    env = "env"
    followup = "followup"


class ScProfileStatus(StrEnum):
    draft = "draft"
    active = "active"
    retired = "retired"


class ScScope(StrEnum):
    own = "own"
    tree = "tree"


class ScCardStatus(StrEnum):
    """§4.1 (provisional cards are computed on read, never stored)."""

    provisional = "provisional"
    issued = "issued"
    final = "final"
    superseded = "superseded"


class ScTrend(StrEnum):
    improving = "improving"
    stable = "stable"
    declining = "declining"


class ScRankStatus(StrEnum):
    ranked = "ranked"
    low_exposure = "low_exposure"
    low_coverage = "low_coverage"


class ScLineStatus(StrEnum):
    scored = "scored"
    not_applicable = "not_applicable"
    insufficient_volume = "insufficient_volume"
    source_not_live = "source_not_live"
    excluded_by_manager = "excluded_by_manager"


class ScRemarkKind(StrEnum):
    comment = "comment"
    dispute = "dispute"


class ScDisputeReason(StrEnum):
    """List DR."""

    data_error = "data_error"
    wrong_attribution = "wrong_attribution"
    not_applicable = "not_applicable"
    other = "other"


class ScResolution(StrEnum):
    upheld_data_corrected = "upheld_data_corrected"
    upheld_metric_excluded = "upheld_metric_excluded"
    rejected = "rejected"


class ScRemarkStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    withdrawn = "withdrawn"


class ScWatchLevel(StrEnum):
    """List WLL."""

    watch = "watch"
    improvement_plan = "improvement_plan"
    suspension_review = "suspension_review"


class ScWatchStatus(StrEnum):
    open = "open"
    closed = "closed"


class ScWatchDecision(StrEnum):
    suspend = "suspend"
    continue_with_conditions = "continue_with_conditions"
    remove_from_project = "remove_from_project"


class ScWatchProposal(StrEnum):
    """What the system proposes on an open entry (WL-3, WL-4, WL-6)."""

    improvement_plan = "improvement_plan"
    suspension_review = "suspension_review"
    close = "close"


class ScWatchAction(StrEnum):
    confirm_escalation = "confirm_escalation"
    submit_pip = "submit_pip"
    accept_pip = "accept_pip"
    decide = "decide"
    close = "close"


class ScKpiGroupBy(StrEnum):
    month = "month"
    contractor = "contractor"


# ---- report packs ------------------------------------------------------------------------------


class RpType(StrEnum):
    """List RT."""

    MCR = "MCR"
    SCP = "SCP"
    CPS = "CPS"
    OSHA300 = "OSHA300"
    HEAT = "HEAT"


class RpStatus(StrEnum):
    """§4.4."""

    draft = "draft"
    in_review = "in_review"
    issued = "issued"
    superseded = "superseded"


class RpAction(StrEnum):
    submit_for_review = "submit_for_review"
    return_to_draft = "return_to_draft"
    review = "review"
    issue = "issue"
    regenerate = "regenerate"


class RpFileKind(StrEnum):
    pdf_en = "pdf_en"
    pdf_ar = "pdf_ar"
    pdf_bilingual = "pdf_bilingual"
    xlsx = "xlsx"


class RpMemberKind(StrEnum):
    user = "user"
    external = "external"


class RpLanguage(StrEnum):
    en = "en"
    ar = "ar"
    both = "both"


class RpLanguages(StrEnum):
    """Setting `report_languages`."""

    en_ar_separate = "en_ar_separate"
    bilingual_single = "bilingual_single"


class RpChannel(StrEnum):
    in_app = "in_app"
    email = "email"


class RpDeliveryStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    bounced = "bounced"
    failed = "failed"


# ---- generic register export -------------------------------------------------------------------


class XpPdpl(StrEnum):
    none = "none"
    personal = "personal"
    sensitive = "sensitive"
    never = "never"


class XpMaskMode(StrEnum):
    """List MM."""

    omit = "omit"
    mask_id = "mask_id"
    person_n = "person_n"
    role_only = "role_only"
    privacy_case = "privacy_case"


class XpPurposeRule(StrEnum):
    sensitive_column = "sensitive_column"
    injured_identity = "injured_identity"
    always = "always"
    never = "never"


class XpPurpose(StrEnum):
    """List EP."""

    gosi = "gosi"
    mhrsd = "mhrsd"
    client_report = "client_report"
    legal = "legal"
    insurance = "insurance"
    audit = "audit"
    data_subject_request = "data_subject_request"
    internal_analysis = "internal_analysis"
    other = "other"


class XpFormat(StrEnum):
    csv = "csv"
    xlsx = "xlsx"
    pdf = "pdf"


class XpJobStatus(StrEnum):
    queued = "queued"
    ready = "ready"
    expired = "expired"
    failed = "failed"


class XpFrequency(StrEnum):
    weekly = "weekly"
    monthly = "monthly"
