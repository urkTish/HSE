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
    (1-dashboard §5.10), 46-81 Phase 2 (2-access-permits §5.13), 82-104 Phase 3 (3-ptw §5.14),
    numbered in spec order.
    Rows with two capabilities (23, 32, 33, 41) are split into one value per action."""

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
    # ---- Phase 2 (2-access-permits §5.13) ----
    worker_view = "worker.view"  # 46
    worker_edit = "worker.edit"  # 47 workers & deployments; demobilise
    worker_unmask_id = "worker.unmask_id"  # 48 full ID / ID copy (audited)
    worker_ban = "worker.ban"  # 49
    induction_course_manage = "induction.course_manage"  # 50 courses & sessions
    induction_record = "induction.record"  # 51
    induction_suspend_revoke = "induction.suspend_revoke"  # 52 confirm suspension / revoke
    pass_application_create = "pass_application.create"  # 53 create / submit / withdraw
    pass_application_endorse = "pass_application.endorse"  # 54 endorse / return
    pass_application_process = "pass_application.process"  # 55 pass office progress, issue
    background_check_view = "background_check.view"  # 56
    credential_suspend_raise = "credential.suspend_raise"  # 57 (≤ 72 h, LC-3)
    credential_suspend_confirm = "credential.suspend_confirm"  # 58 confirm/lift; revoke
    credential_custody = "credential.custody"  # 59 return / loss
    adp_apply = "adp.apply"  # 60
    adp_issue = "adp.issue"  # 61 tests + issue
    offence_record = "offence.record"  # 62
    vehicle_edit = "vehicle.edit"  # 63 vehicles; apply for AVP
    avp_issue = "avp.issue"  # 64 inspection + issue
    wap_edit = "wap.edit"  # 65 create / submit / amend
    wap_approve = "wap.approve"  # 66 approve / reject / resume
    wap_suspend = "wap.suspend"  # 67 suspend WAP; declare / end ops suspension
    wap_close = "wap.close"  # 68 close / cancel
    notam_edit = "notam.edit"  # 69
    notam_process = "notam.process"  # 70
    obstacle_edit = "obstacle.edit"  # 71
    obstacle_decide = "obstacle.decide"  # 72
    access_works_view = "access_works.view"  # 73 WAPs, NOTAMs, obstacle clearances, ops events
    gate_check = "gate.check"  # 74
    gate_manage = "gate.manage"  # 75 gates and devices
    gate_log_view = "gate_log.view"  # 76 view / export gate log
    access_kpi_view = "access_kpi.view"  # 77 access KPIs, expiring items, action panel
    export_access = "export.access"  # 78 (IDs masked)
    export_access_identity = "export.access_identity"  # 79 full IDs / per-worker data report
    access_settings_edit = "access_settings.edit"  # 80 settings, AP-CAT/AP-AREA/OFF/VC, hooks
    zone_profile_edit = "zone_profile.edit"  # 81
    # ---- Phase 3 (3-ptw §5.14) ----
    permit_view = "permit.view"  # 82 permits, live board, gas tests, isolations, conflicts
    permit_prepare = "permit.prepare"  # 83 Draft permit, JSA instance, documents
    permit_receive = "permit.receive"  # 84 act as named receiver
    permit_area_review = "permit.area_review"  # 85 review as area authority (+appt)
    permit_hse_review = "permit.hse_review"  # 86 HSE review; accept High residual risk
    permit_issue = "permit.issue"  # 87 approve/issue/revalidate/resume/close (+appt issuer)
    permit_suspend = "permit.suspend"  # 88 suspend / stop work
    permit_cancel = "permit.cancel"  # 89
    gas_test_record = "gas_test.record"  # 90 gas tests and bump tests
    gas_detector_manage = "gas_detector.manage"  # 91 detectors and calibrations
    isolation_manage = "isolation.manage"  # 92 plan/apply/verify/remove points (+appt)
    personal_lock_record = "personal_lock.record"  # 93 personal locks on/off
    deisolation_authorise = "deisolation.authorise"  # 94
    lock_cut_approve = "lock_cut.approve"  # 95 IS-9
    jsa_template_manage = "jsa_template.manage"  # 96 (contractor reps propose)
    simops_coordinate = "simops.coordinate"  # 97 sign SIMOPS coordination
    ptw_zone_profile_edit = "ptw_zone_profile.edit"  # 98 zone PTW profiles, adjacency
    ptw_settings_edit = "ptw_settings.edit"  # 99 SIMOPS matrix, types, checklists, settings
    ptw_appointment_manage = "ptw_appointment.manage"  # 100 (issuer: HSE Manager only)
    ptw_audit_conduct = "ptw_audit.conduct"  # 101
    ptw_exemption_grant = "ptw_exemption.grant"  # 102 midday ban, energized, impairment, >90 %
    ptw_kpi_view = "ptw_kpi.view"  # 103 PTW KPIs, band, expiring items, action panel
    export_ptw = "export.ptw"  # 104


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
    # Phase 2
    worker = "worker"
    worker_deployment = "worker_deployment"
    induction_course = "induction_course"
    induction_record = "induction_record"
    zone_access_profile = "zone_access_profile"
    airport_pass_category = "airport_pass_category"
    airport_pass_area = "airport_pass_area"
    pass_application = "pass_application"
    airport_pass = "airport_pass"
    adp = "adp"
    airside_offence = "airside_offence"
    vehicle = "vehicle"
    avp = "avp"
    notam_request = "notam_request"
    obstacle_clearance = "obstacle_clearance"
    wap = "wap"
    ops_event = "ops_event"
    credential_event = "credential_event"
    gate = "gate"
    gate_device = "gate_device"
    gate_log = "gate_log"
    access_settings = "access_settings"
    # Phase 3
    permit = "permit"
    permit_shift = "permit_shift"
    permit_handover = "permit_handover"
    permit_suspension = "permit_suspension"
    permit_exemption = "permit_exemption"
    permit_type_config = "permit_type_config"
    zone_ptw_profile = "zone_ptw_profile"
    zone_adjacency = "zone_adjacency"
    ptw_appointment = "ptw_appointment"
    jsa = "jsa"
    gas_detector = "gas_detector"
    bump_test = "bump_test"
    gas_test = "gas_test"
    isolation_certificate = "isolation_certificate"
    lock = "lock"
    personal_lock_event = "personal_lock_event"
    simops_rule = "simops_rule"
    simops_conflict = "simops_conflict"
    simops_coordination = "simops_coordination"
    ptw_audit = "ptw_audit"
    ptw_settings = "ptw_settings"


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
    # Phase 2 access registers (IDs masked; full IDs only with capability 79 + purpose, P2-10)
    workers = "workers"
    deployments = "deployments"
    inductions = "inductions"
    pass_applications = "pass_applications"
    airport_passes = "airport_passes"
    adps = "adps"
    airside_offences = "airside_offences"
    vehicles = "vehicles"
    avps = "avps"
    waps = "waps"
    notam_requests = "notam_requests"
    obstacle_clearances = "obstacle_clearances"
    ops_events = "ops_events"
    gate_log = "gate_log"
    # Phase 3 PTW registers (capability 104; names only with capability 46, never signatures)
    permits = "permits"
    permit_suspensions = "permit_suspensions"
    gas_tests = "gas_tests"
    gas_detectors = "gas_detectors"
    isolations = "isolations"
    locks = "locks"
    ptw_appointments = "ptw_appointments"
    jsa_templates = "jsa_templates"
    simops_conflicts = "simops_conflicts"
    ptw_audits = "ptw_audits"


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
    # ---- Phase 2 (2-access-permits §7) ----
    induction_expiry = "induction_expiry"
    reinduction_due = "reinduction_due"
    worker_id_expiry = "worker_id_expiry"
    passport_registration = "passport_registration"
    airport_pass_expiry = "airport_pass_expiry"
    bg_recheck_due = "bg_recheck_due"
    pass_application_update = "pass_application_update"
    pass_application_stale = "pass_application_stale"
    adp_expiry = "adp_expiry"
    avp_expiry = "avp_expiry"
    vehicle_document_expiry = "vehicle_document_expiry"
    adp_suspended = "adp_suspended"
    adp_suspension_ended = "adp_suspension_ended"
    raised_suspension_pending = "raised_suspension_pending"
    credential_status_changed = "credential_status_changed"
    return_due = "return_due"
    return_overdue = "return_overdue"
    credential_lost = "credential_lost"
    lost_authority_not_notified = "lost_authority_not_notified"
    revoked_token_scanned = "revoked_token_scanned"
    admitted_despite_denial = "admitted_despite_denial"
    contractor_blacklisted_passes = "contractor_blacklisted_passes"
    wap_update = "wap_update"
    wap_blocked = "wap_blocked"
    wap_crew_excluded = "wap_crew_excluded"
    wap_suspended = "wap_suspended"
    wap_ending = "wap_ending"
    notam_ending = "notam_ending"
    notam_late = "notam_late"
    notam_not_issued = "notam_not_issued"
    notam_ended_with_waps = "notam_ended_with_waps"
    obstacle_clearance_update = "obstacle_clearance_update"
    obstacle_clearance_ending = "obstacle_clearance_ending"
    ops_suspension = "ops_suspension"
    # ---- Phase 3 (3-ptw §7) ----
    permit_requested = "permit_requested"
    permit_review_reminder = "permit_review_reminder"
    permit_reviewed = "permit_reviewed"
    permit_update = "permit_update"  # approved / returned / cancelled
    permit_not_issued = "permit_not_issued"
    permit_issue_lapsed = "permit_issue_lapsed"
    shift_end_approaching = "shift_end_approaching"
    shift_lapsed = "shift_lapsed"
    gas_retest_due = "gas_retest_due"
    gas_test_failed = "gas_test_failed"
    permit_suspended = "permit_suspended"
    midday_ban = "midday_ban"
    fire_watch_ended = "fire_watch_ended"
    permit_ending = "permit_ending"
    permit_expired = "permit_expired"
    post_expiry_check_pending = "post_expiry_check_pending"
    simops_conflict = "simops_conflict"
    ptw_critical_finding = "ptw_critical_finding"
    ptw_audits_behind_plan = "ptw_audits_behind_plan"
    gas_detector_calibration_due = "gas_detector_calibration_due"
    gas_detector_quarantined = "gas_detector_quarantined"
    ptw_appointment_expiry = "ptw_appointment_expiry"
    jsa_template_review_due = "jsa_template_review_due"
    isolation_review_due = "isolation_review_due"
    isolation_orphan = "isolation_orphan"
    lock_cut = "lock_cut"
    crew_eligibility_expiring = "crew_eligibility_expiring"
    ptw_exemption = "ptw_exemption"
    crew_excluded = "crew_excluded"
