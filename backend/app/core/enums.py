"""Domain enumerations (spec 0-foundation §3, §4, §5.6, §5.10).

These are exported into the OpenAPI contract so the frontend gets typed unions.
"""

from enum import IntEnum, StrEnum


class Role(StrEnum):
    """Platform roles (§3.8). hse_manager is organisation-wide; all others are per project."""

    hse_manager = "hse_manager"
    hse_officer = "hse_officer"
    site_engineer = "site_engineer"
    permit_issuer = "permit_issuer"
    permit_receiver = "permit_receiver"
    contractor_hse_rep = "contractor_hse_rep"
    viewer_client = "viewer_client"


class Capability(StrEnum):
    """Rows of the permission matrix: 1-19 Phase 0 (0-foundation §5.10), 20-45 Phase 1
    (1-dashboard §5.10), numbered in spec order. Rows with two capabilities (23, 32, 33, 41)
    are split into one value per action."""

    project_manage = "project.manage"  # 1
    project_view = "project.view"  # 2
    site_zone_manage = "site_zone.manage"  # 3
    site_zone_view = "site_zone.view"  # 4
    contractor_create = "contractor.create"  # 5
    contractor_approve = "contractor.approve"  # 6
    engagement_manage = "engagement.manage"  # 7
    contractor_view = "contractor.view"  # 8
    contractor_view_contacts = "contractor.view_contacts"  # 9
    user_invite = "user.invite"  # 10
    user_view_directory = "user.view_directory"  # 11
    user_view_contacts = "user.view_contacts"  # 12
    user_manage_status = "user.manage_status"  # 13
    settings_edit = "settings.edit"  # 14
    settings_view = "settings.view"  # 15
    audit_log_read = "audit_log.read"  # 16
    history_view = "history.view"  # 17
    export_lists = "export.lists"  # 18
    profile_edit_own = "profile.edit_own"  # 19
    # ---- Phase 1 (1-dashboard §5.10) ----
    workforce_edit = "workforce.edit"  # 20
    workforce_import = "workforce.import"  # 21
    workforce_verify = "workforce.verify"  # 22
    workforce_lock = "workforce.lock"  # 23 lock month
    workforce_unlock = "workforce.unlock"  # 23 unlock (Locked → Verified)
    workforce_view = "workforce.view"  # 24
    incident_report = "incident.report"  # 25
    incident_classify = "incident.classify"  # 26
    investigation_edit = "investigation.edit"  # 27
    investigation_approve = "investigation.approve"  # 28
    injury_identity_view = "injury.identity_view"  # 29
    injury_medical_view = "injury.medical_view"  # 30
    incident_view = "incident.view"  # 31
    observation_create = "observation.create"  # 32
    observation_close = "observation.close"  # 32
    inspection_plan_manage = "inspection.plan_manage"  # 33
    inspection_record = "inspection.record"  # 33
    ca_create = "ca.create"  # 34
    ca_update_own = "ca.update_own"  # 35
    ca_verify = "ca.verify"  # 36
    ca_approve_extension = "ca.approve_extension"  # 37 (also cancel)
    dashboard_view = "dashboard.view"  # 38
    breakdown_sensitive_view = "breakdown.sensitive_view"  # 39
    ai_ask = "ai.ask"  # 40
    monthly_report_generate = "monthly_report.generate"  # 41
    monthly_report_review = "monthly_report.review"  # 41
    monthly_report_publish = "monthly_report.publish"  # 41
    monthly_report_view = "monthly_report.view"  # 41 (R = published only)
    export_kpis = "export.kpis"  # 42
    export_identity = "export.identity"  # 43
    hse_settings_edit = "hse_settings.edit"  # 44
    observer_identity_view = "observer.identity_view"  # 45


class CapabilityScope(StrEnum):
    """Matrix legend (§5.10): all projects, assigned project, assigned sites, contractor tree
    (own engagement + downstream subcontractors), own engagement only."""

    all = "all"
    project = "project"
    sites = "sites"
    contractor_tree = "contractor_tree"
    own_engagement = "own_engagement"


class ProjectType(StrEnum):
    airport = "airport"
    building_highrise = "building_highrise"
    infrastructure = "infrastructure"
    industrial = "industrial"
    other = "other"


class ProjectStatus(StrEnum):
    """Project lifecycle (§4.1)."""

    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    closed = "closed"


class SiteSide(StrEnum):
    airside = "airside"
    landside = "landside"
    mixed = "mixed"
    other = "other"


class SiteStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class ZoneType(StrEnum):
    """airside/landside only on airport projects (§5.3 rule 18)."""

    airside = "airside"
    landside = "landside"
    other = "other"


class ZoneStatus(StrEnum):
    """Zone lifecycle (§4.4)."""

    active = "active"
    temporarily_closed = "temporarily_closed"
    archived = "archived"


class AirsideArea(StrEnum):
    runway = "runway"
    runway_strip = "runway_strip"
    resa = "resa"
    taxiway = "taxiway"
    taxiway_strip = "taxiway_strip"
    apron = "apron"
    ils_critical = "ils_critical"
    ils_sensitive = "ils_sensitive"
    airside_road = "airside_road"
    other_airside = "other_airside"


MOVEMENT_AREAS: frozenset[AirsideArea] = frozenset(
    {
        AirsideArea.runway,
        AirsideArea.runway_strip,
        AirsideArea.resa,
        AirsideArea.taxiway,
        AirsideArea.taxiway_strip,
        AirsideArea.apron,
    }
)


class ContractorCategory(StrEnum):
    civil = "civil"
    mep = "mep"
    steel = "steel"
    airfield = "airfield"
    scaffolding = "scaffolding"
    lifting = "lifting"
    facade = "facade"
    specialist = "specialist"
    consultant = "consultant"
    other = "other"


class ContractorStatus(StrEnum):
    """Contractor master-record lifecycle (§4.2)."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    suspended = "suspended"
    demobilised = "demobilised"
    blacklisted = "blacklisted"


class EmployerType(StrEnum):
    client = "client"
    pmc_consultant = "pmc_consultant"
    contractor = "contractor"


class Language(StrEnum):
    en = "en"
    ar = "ar"


class UserStatus(StrEnum):
    """User lifecycle (§4.3)."""

    invited = "invited"
    active = "active"
    locked = "locked"
    deactivated = "deactivated"


class KpiBaseHours(IntEnum):
    """Allowed KPI normalisation bases (§3.9, §5.5 rule 31)."""

    h200k = 200_000
    h1m = 1_000_000


class WeekStart(StrEnum):
    sunday = "sunday"
    monday = "monday"


class DigitStyle(StrEnum):
    western = "western"
    arabic_indic = "arabic_indic"


class DateFormatEn(StrEnum):
    dd_mmm_yyyy = "DD MMM YYYY"
    dd_mm_yyyy = "DD/MM/YYYY"


class HijriCalendar(StrEnum):
    umm_al_qura = "umm_al_qura"


class ProjectTimezone(StrEnum):
    asia_riyadh = "Asia/Riyadh"


class AuditAction(StrEnum):
    """Audited actions (§5.6 rule 35, plus privacy_notice_acknowledged and
    audit_chain_verified)."""

    login_success = "login_success"
    login_failed = "login_failed"
    logout = "logout"
    account_locked = "account_locked"
    password_reset_requested = "password_reset_requested"
    password_changed = "password_changed"
    mfa_changed = "mfa_changed"
    user_invited = "user_invited"
    user_status_changed = "user_status_changed"
    role_assigned = "role_assigned"
    role_revoked = "role_revoked"
    create = "create"
    update = "update"
    status_change = "status_change"
    archive = "archive"
    settings_changed = "settings_changed"
    sensitive_field_read = "sensitive_field_read"
    export = "export"
    access_denied = "access_denied"
    audit_log_viewed = "audit_log_viewed"
    audit_chain_verified = "audit_chain_verified"
    retention_purge = "retention_purge"
    privacy_notice_acknowledged = "privacy_notice_acknowledged"


AUTH_ACTIONS: frozenset[AuditAction] = frozenset(
    {
        AuditAction.login_success,
        AuditAction.login_failed,
        AuditAction.logout,
        AuditAction.account_locked,
        AuditAction.password_reset_requested,
        AuditAction.password_changed,
        AuditAction.mfa_changed,
    }
)


class AuditResult(StrEnum):
    success = "success"
    denied = "denied"
    failed = "failed"


class EntityType(StrEnum):
    """Entity types referenced by audit entries and change history."""

    project = "project"
    site = "site"
    zone = "zone"
    contractor = "contractor"
    project_engagement = "project_engagement"
    user = "user"
    role_assignment = "role_assignment"
    project_settings = "project_settings"
    audit_log = "audit_log"
    # Phase 1
    workforce_return = "workforce_return"
    workforce_import_batch = "workforce_import_batch"
    workforce_month = "workforce_month"
    incident = "incident"
    injury_case = "injury_case"
    investigation = "investigation"
    observation = "observation"
    inspection_plan = "inspection_plan"
    inspection = "inspection"
    corrective_action = "corrective_action"
    hse_meeting = "hse_meeting"
    hse_settings = "hse_settings"
    reference_list_item = "reference_list_item"
    attachment = "attachment"
    ai_answer = "ai_answer"
    monthly_report = "monthly_report"
    kpi = "kpi"


class ExportDataset(StrEnum):
    """Lists that can be exported (§5.8 rule 49, capability 18)."""

    projects = "projects"
    sites = "sites"
    zones = "zones"
    contractors = "contractors"
    engagements = "engagements"
    users = "users"
    audit_log = "audit_log"
    # Phase 1 registers (incidents: identity columns only with capability 43 + purpose)
    workforce_returns = "workforce_returns"
    incidents = "incidents"
    observations = "observations"
    inspections = "inspections"
    corrective_actions = "corrective_actions"
    hse_meetings = "hse_meetings"


class ExportFormat(StrEnum):
    csv = "csv"
    xlsx = "xlsx"


class NotificationKind(StrEnum):
    """In-app notification kinds (§7)."""

    account_locked = "account_locked"
    contractor_cr_expiry = "contractor_cr_expiry"
    contractor_submitted = "contractor_submitted"
    contractor_status_changed = "contractor_status_changed"
    engagement_parent_blacklisted = "engagement_parent_blacklisted"
    settings_changed = "settings_changed"
    audit_chain_break = "audit_chain_break"
    last_hse_manager_risk = "last_hse_manager_risk"
    role_assignment_ending = "role_assignment_ending"
    invite_expired = "invite_expired"
    inactive_account = "inactive_account"
    # ---- Phase 1 (1-dashboard §7) ----
    incident_reported = "incident_reported"
    incident_unclassified = "incident_unclassified"
    external_notification_due = "external_notification_due"
    investigation_due = "investigation_due"
    preliminary_report_missing = "preliminary_report_missing"
    open_lti_case = "open_lti_case"
    case_restated = "case_restated"
    ca_assigned = "ca_assigned"
    ca_due = "ca_due"
    ca_overdue = "ca_overdue"
    ca_pending_verification = "ca_pending_verification"
    high_risk_observation_without_ca = "high_risk_observation_without_ca"
    daily_return_missing = "daily_return_missing"
    data_completeness_low = "data_completeness_low"
    month_lock_approaching = "month_lock_approaching"
    inspection_due = "inspection_due"
    inspection_missed = "inspection_missed"
    leading_warning = "leading_warning"
    lti_free_milestone = "lti_free_milestone"
    monthly_report_ready = "monthly_report_ready"
    import_committed_with_warnings = "import_committed_with_warnings"
