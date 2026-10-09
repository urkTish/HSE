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
    oh_practitioner = "oh_practitioner"  # 6a §3.0 (assigned by the HSE Manager only, OH-1)


class Capability(StrEnum):
    """Rows of the permission matrix: 1-19 Phase 0 (0-foundation §5.10), 20-45 Phase 1
    (1-dashboard §5.10), 46-81 Phase 2 (2-access-permits §5.13), 82-104 Phase 3 (3-ptw §5.14),
    numbered in spec order; 105-124 Phase 4 (4-third-party-cert §5.15); 125-145 Phase 5
    (5-training §5.15); 146-165 Phase 6a (6a-occupational-health §5.15).
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
    # ---- Phase 4 (4-third-party-cert §5.15) ----
    cert_register_view = "cert_register.view"  # 105 equipment, deployments, certs, scaffolds,
    # defects, TPI list (no personal data)
    equipment_edit = "equipment.edit"  # 106 items, deployments, scaffolds, submit equipment
    # certificates, configuration events (site engineers: scaffolds + configuration events)
    cert_review = "cert.review"  # 107 review / accept / return / reject; TPI revocation notice
    cert_verify = "cert.verify"  # 108 record verification with the TPI
    equipment_mobilise = "equipment.mobilise"  # 109 approve mobilisation, arrival, demobilise
    defect_raise = "defect.raise"  # 110 raise defect / tag out (stop use)
    defect_rectify = "defect.rectify"  # 111
    defect_close = "defect.close"  # 112 close defect / return to service; retire; require
    # scaffold re-inspection
    scaffold_inspect = "scaffold.inspect"  # 113 (inspector must hold SCAFFOLD-INSPECTOR)
    tpi_edit = "tpi.edit"  # 114 TPI organisations, accreditations, client approvals
    cert_blacklist = "cert.blacklist"  # 115 approve/suspend/blacklist TPI; blacklist
    # equipment; certification ban (HSE Manager only)
    cert_suspend = "cert.suspend"  # 116 suspend / reinstate a certificate
    personnel_cert_view = "personnel_cert.view"  # 117 (also needs 46)
    personnel_cert_submit = "personnel_cert.submit"  # 118
    personnel_cert_scan_view = "personnel_cert.scan_view"  # 119 scans + medical flag (audited)
    cert_import = "cert.import"  # 120 (tpi_register_file: HSE Officer / Manager only)
    cert_check = "cert.check"  # 121 EQ sticker, AC card in certificates mode, cert_no lookup
    cert_kpi_view = "cert_kpi.view"  # 122 KPIs, expiring items, action panel, readiness
    export_cert = "export.cert"  # 123 (IDs never; names only with 46)
    cert_settings_edit = "cert_settings.edit"  # 124 settings, lists, early switch, deferral
    # ---- Phase 5 (5-training §5.15) ----
    training_catalogue_view = "training_catalogue.view"  # 125 catalogue, providers, matrix,
    # session calendar (no attendee names)
    training_course_edit = "training_course.edit"  # 126 catalogue (tighten only, CC-2)
    training_provider_edit = "training_provider.edit"  # 127 providers, accreditations, submit
    training_provider_decide = "training_provider.decide"  # 128 approve / suspend / blacklist
    training_matrix_edit = "training_matrix.edit"  # 129 manual lines (loosening: Manager,
    # MX-8); exemptions
    training_profile_edit = "training_profile.edit"  # 130 matrix roles, work zones
    trainer_authorise = "trainer.authorise"  # 131 grant / suspend / withdraw authorisations
    training_session_manage = "training_session.manage"  # 132 create / schedule / cancel;
    # session from refresher plan (contractor reps: own contractor_internal provider, TA-6)
    training_nominate = "training.nominate"  # 133 nominate / withdraw attendees
    training_attendance_record = "training_attendance.record"  # 134 (+ the session's trainers)
    training_session_close = "training_session.close"  # 135 close + issue records (SoD SS-8)
    training_record_view = "training_record.view"  # 136 records, attendance, gaps (names: 46)
    training_record_submit = "training_record.submit"  # 137 external records
    training_record_review = "training_record.review"  # 138 accept / return / reject; verify
    training_scan_view = "training_scan.view"  # 139 open certificate scans (reason, audited)
    training_record_suspend = "training_record.suspend"  # 140 suspend / reinstate / revoke
    training_import = "training.import"  # 141 (provider_register_file: HSE Officer / Manager)
    training_check = "training.check"  # 142 TR QR, AC card in competence mode
    training_kpi_view = "training_kpi.view"  # 143 KPIs, expiring, action panel, plan, readiness
    export_training = "export.training"  # 144 (IDs and scans never; names only with 46)
    training_settings_edit = "training_settings.edit"  # 145 settings, hooks enable / switch /
    # deferral, void a session (HSE Manager only)
    # ---- Phase 6a (6a-occupational-health §5.15) ----
    fitness_catalogue_view = "fitness_catalogue.view"  # 146 catalogue, providers, plan
    fitness_code_edit = "fitness_code.edit"  # 147 catalogue (tighten only, MC-3)
    medical_provider_edit = "medical_provider.edit"  # 148 providers, examiners, submit
    medical_provider_decide = "medical_provider.decide"  # 149 approve / suspend / blacklist;
    # suspend / withdraw examiner registrations
    medical_plan_edit = "medical_plan.edit"  # 150 manual plan lines (loosening: Manager, MR-5)
    health_profile_edit = "health_profile.edit"  # 151 exposure groups
    fitness_record_clinic = "fitness.record_clinic"  # 152 site-clinic assessments; sign as
    # the linked examiner (not in the HSE Manager's org-wide grant, OH-3)
    fitness_submit_external = "fitness.submit_external"  # 153 external certificates
    fitness_review = "fitness.review"  # 154 review / accept / return / reject; verification
    fitness_status_view = "fitness.status_view"  # 155 tier 1 (OH-2)
    fitness_functional_view = "fitness.functional_view"  # 156 tier 2: outcome, restrictions
    fitness_clinical_view = "fitness.clinical_view"  # 157 tier 3: reasons, provider, examiner,
    # verification outcomes; revoke assessments
    fitness_referral_raise = "fitness_referral.raise"  # 158
    fitness_hold_manage = "fitness_hold.manage"  # 159 manual hold; cancel holds and referrals
    # with holds (HSE Officer: place only)
    fitness_scan_view = "fitness_scan.view"  # 160 open scans (reason, audited)
    fitness_import = "fitness.import"  # 161 (clinic_register_file: Manager / OH; contractor_file)
    medical_kpi_view = "medical_kpi.view"  # 162 KPIs, expiring, action panel, readiness
    export_medical = "export.medical"  # 163 (tier rules; never scans)
    medical_settings_edit = "medical_settings.edit"  # 164 settings, enable hooks, switch,
    # deferral (HSE Manager only)
    fitness_subject_report = "fitness.subject_report"  # 165 per-worker data-subject report
    # ---- Phase 6b (6b-heat-stress §5.13) ----
    heat_view = "heat.view"  # 166 heat board, readings, stations, exemptions, patrols, duty list
    heat_reading_record = "heat_reading.record"  # 167 manual WBGT readings
    heat_register_manage = "heat_register.manage"  # 168 instruments, points, devices, stations,
    # reading imports
    heat_welfare_record = "heat_welfare.record"  # 169 welfare checks
    heat_patrol_record = "heat_patrol.record"  # 170 midday-ban patrols
    heat_exemption_grant = "heat_exemption.grant"  # 171 non-permit ban exemptions (Manager)
    heat_plan_manage = "heat_plan.manage"  # 172 confirm plan days, prior experience, cancel
    heat_log_view = "heat_log.view"  # 173 view / review the heat-illness log
    heat_kpi_view = "heat_kpi.view"  # 174 KPIs, action panel, season report
    heat_settings_edit = "heat_settings.edit"  # 175 settings, regime table, enforcement, issue
    export_heat = "export.heat"  # 176 registers (never photos or review texts below 173)
    heat_void = "heat.void"  # 177 void readings, checks and patrols
    # ---- Phase 6c (6c-emergency-drills §5.13) ----
    emergency_view = "emergency.view"  # 178 ERP, APs, contacts, roster, teams, assets, drills
    erp_prepare = "erp.prepare"  # 179 ERP drafts, scenarios, APs, contacts, zone profiles
    erp_approve = "erp.approve"  # 180 approve ERP, 6c settings, enforcement (Manager)
    emergency_roster_manage = "emergency_roster.manage"  # 181 roster and rescue teams
    emergency_asset_manage = "emergency_asset.manage"  # 182 register / retire assets, stickers
    emergency_check_record = "emergency_check.record"  # 183 asset checks, tag out
    drill_plan = "drill.plan"  # 184 plan / cancel drills; see unannounced drills
    drill_run = "drill.run"  # 185 start, timings, muster (scan, tick, resolve, sheet)
    drill_evaluate = "drill.evaluate"  # 186 evaluate drills, findings
    emergency_declare = "emergency.declare"  # 187 declare an event, timeline, external calls
    emergency_all_clear = "emergency.all_clear"  # 188 All Clear; review events
    emergency_kpi_view = "emergency_kpi.view"  # 189 6c KPIs, action panel, exports
    emergency_void = "emergency.void"  # 190 void drills, checks, events, musters
    # ---- Phase 6d (6d-field-assurance §5.13) ----
    field_library_view = "field_library.view"  # 191 template and topic libraries
    field_library_author = "field_library.author"  # 192 template and topic drafts
    field_library_publish = "field_library.publish"  # 193 publish / retire; 6d settings (Manager)
    field_audit_conduct = "field_audit.conduct"  # 194 plan, cancel, conduct audits; programme
    field_audit_issue = "field_audit.issue"  # 195 issue audit reports
    stop_work_release = "stop_work.release"  # 196 release stop-work orders
    briefing_campaign_manage = "briefing_campaign.manage"  # 197 issue / cancel campaigns
    toolbox_record = "toolbox.record"  # 198 record toolbox talks and attendance
    toolbox_names_view = "toolbox_names.view"  # 199 attendance names and signatures
    field_view = "field.view"  # 200 6d registers, responses, KPIs, action panel, exports
    field_void = "field.void"  # 201 void inspections (6d), audits, talks, stop-work orders
    # ---- Phase 6e (6e-environmental §5.17) ----
    env_view = "env.view"  # 202 6e registers, KPIs, action panel; exports (personal per P6e)
    env_aspect_manage = "env_aspect.manage"  # 203 aspects register
    env_permit_manage = "env_permit.manage"  # 204 permits, licences and providers
    waste_area_manage = "waste_area.manage"  # 205 waste streams and storage areas
    consignment_record = "consignment.record"  # 206 consignments and receipts
    consignment_close = "consignment.close"  # 207 close; discrepancies and rejections
    env_monitoring_manage = "env_monitoring.manage"  # 208 instruments, points, limits, devices
    env_reading_record = "env_reading.record"  # 209 readings (manual, visual, lab) and water
    env_review = "env.review"  # 210 review exceedances; close spills
    spill_record = "spill.record"  # 211 spills and spill-kit use
    env_complaint = "env_complaint.manage"  # 212 complaints; complainant data
    env_settings = "env.settings"  # 213 6e settings; provider decisions (HSE Manager)
    env_void = "env.void"  # 214 void 6e records


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
    cert_check_view = "cert_check_view"  # 4-third-party-cert VF-9 (no entry recorded)
    training_qr_view = "training_qr_view"  # 5-training CK5-1 (TR QR scan; no entry recorded)


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
    # Phase 4
    tpi = "tpi"
    tpi_accreditation = "tpi_accreditation"
    tpi_client_approval = "tpi_client_approval"
    equipment_item = "equipment_item"
    equipment_deployment = "equipment_deployment"
    equipment_certificate = "equipment_certificate"
    configuration_event = "configuration_event"
    scaffold = "scaffold"
    scaffold_inspection = "scaffold_inspection"
    personnel_certificate = "personnel_certificate"
    cert_verification = "cert_verification"
    equipment_defect = "equipment_defect"
    certification_ban = "certification_ban"
    hook_policy_state = "hook_policy_state"
    cert_import_batch = "cert_import_batch"
    cert_settings = "cert_settings"
    cert_type = "cert_type"
    # Phase 5
    training_course = "training_course"
    training_provider = "training_provider"
    training_provider_accreditation = "training_provider_accreditation"
    trainer_authorisation = "trainer_authorisation"
    training_matrix_line = "training_matrix_line"
    training_profile = "training_profile"
    training_exemption = "training_exemption"
    training_session = "training_session"
    training_nomination = "training_nomination"
    training_record = "training_record"
    training_verification = "training_verification"
    training_import_batch = "training_import_batch"
    training_settings = "training_settings"
    training_retraining_note = "training_retraining_note"
    # Phase 6a
    fitness_code = "fitness_code"
    medical_provider = "medical_provider"
    medical_examiner = "medical_examiner"
    medical_plan_line = "medical_plan_line"
    health_profile = "health_profile"
    fitness_assessment = "fitness_assessment"
    fitness_verification = "fitness_verification"
    fitness_hold = "fitness_hold"
    fitness_referral = "fitness_referral"
    medical_import_batch = "medical_import_batch"
    medical_settings = "medical_settings"
    # Phase 6b
    heat_instrument = "heat_instrument"
    monitoring_point = "monitoring_point"
    wbgt_reading = "wbgt_reading"
    heat_regime_table = "heat_regime_table"
    acclimatisation_plan = "acclimatisation_plan"
    rest_station = "rest_station"
    heat_welfare_check = "heat_welfare_check"
    ban_patrol = "ban_patrol"
    ban_exemption = "ban_exemption"
    heat_illness_entry = "heat_illness_entry"
    heat_season_report = "heat_season_report"
    heat_settings = "heat_settings"
    # Phase 6c
    erp = "erp"
    assembly_point = "assembly_point"
    emergency_contact = "emergency_contact"
    zone_emergency_profile = "zone_emergency_profile"
    emergency_roster = "emergency_roster"
    rescue_team = "rescue_team"
    emergency_asset = "emergency_asset"
    emergency_asset_check = "emergency_asset_check"
    emergency_drill = "emergency_drill"
    emergency_muster = "emergency_muster"
    emergency_event = "emergency_event"
    emergency_settings = "emergency_settings"
    muster_device = "muster_device"
    # Phase 6d
    checklist_template = "checklist_template"
    toolbox_topic = "toolbox_topic"
    checklist_response = "checklist_response"
    field_finding = "field_finding"
    stop_work_order = "stop_work_order"
    field_audit = "field_audit"
    toolbox_talk = "toolbox_talk"
    briefing_campaign = "briefing_campaign"
    field_settings = "field_settings"
    # Phase 6e
    env_settings = "env_settings"
    env_aspect = "env_aspect"
    env_provider = "env_provider"
    env_permit = "env_permit"
    waste_stream = "waste_stream"
    waste_storage_area = "waste_storage_area"
    waste_consignment = "waste_consignment"
    env_instrument = "env_instrument"
    env_point = "env_point"
    env_reading = "env_reading"
    background_declaration = "background_declaration"
    env_exceedance = "env_exceedance"
    spill = "spill"
    water_entry = "water_entry"
    discharge_day = "discharge_day"
    env_complaint = "env_complaint"
    env_monitor_device = "env_monitor_device"


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
    # Phase 4 certification registers (capability 123; never ID numbers, scans, the medical
    # flag, ban reasons or verification-failure details; names only with capability 46)
    tpis = "tpis"
    equipment = "equipment"
    equipment_deployments = "equipment_deployments"
    equipment_certificates = "equipment_certificates"
    scaffolds = "scaffolds"
    personnel_certificates = "personnel_certificates"
    cert_verifications = "cert_verifications"
    equipment_defects = "equipment_defects"
    blacklist_register = "blacklist_register"
    cert_imports = "cert_imports"
    # Phase 5 training registers (capability 144; never ID numbers or scans; names only with
    # capability 46; scores only for HSE Manager / Officer, P5-5)
    training_courses = "training_courses"
    training_providers = "training_providers"
    trainer_authorisations = "trainer_authorisations"
    training_matrix = "training_matrix"
    training_sessions = "training_sessions"
    training_attendance = "training_attendance"
    training_records = "training_records"
    training_verifications = "training_verifications"
    training_gaps = "training_gaps"
    refresher_plan = "refresher_plan"
    training_hours = "training_hours"
    training_imports = "training_imports"
    # Phase 6a registers (capability 163; tier-aware columns; never scans, ID numbers or reason
    # texts below tier 3; Viewer/Client aggregates only)
    fitness_codes = "fitness_codes"
    medical_providers = "medical_providers"
    medical_examiners = "medical_examiners"
    medical_plan = "medical_plan"
    fitness_status = "fitness_status"
    fitness_gaps = "fitness_gaps"
    fitness_holds = "fitness_holds"
    fitness_referrals = "fitness_referrals"
    fitness_verifications = "fitness_verifications"
    medical_imports = "medical_imports"


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
    # ---- Phase 4 (4-third-party-cert §7) ----
    equipment_cert_expiry = "equipment_cert_expiry"
    equipment_quarantined = "equipment_quarantined"
    personnel_cert_expiry = "personnel_cert_expiry"
    personnel_cert_expiring_on_crew = "personnel_cert_expiring_on_crew"
    tpi_accreditation_expiry = "tpi_accreditation_expiry"
    tpi_client_approval_expiry = "tpi_client_approval_expiry"
    certificate_submitted = "certificate_submitted"
    certificate_review_reminder = "certificate_review_reminder"
    certificate_returned = "certificate_returned"  # returned or rejected
    verification_due = "verification_due"
    verification_unable = "verification_unable"
    verification_failed = "verification_failed"
    scaffold_tag_expiry = "scaffold_tag_expiry"
    scaffold_tag_red = "scaffold_tag_red"  # red or inspection_required
    equipment_stop_use = "equipment_stop_use"  # A defect raised or tagged out
    defect_rectification_due = "defect_rectification_due"
    equipment_out_of_service = "equipment_out_of_service"  # B overdue, failed inspection
    configuration_event = "configuration_event"
    arrival_inspection_due = "arrival_inspection_due"
    blacklist_changed = "blacklist_changed"  # equipment / person / TPI (BL-2)
    ban_review_due = "ban_review_due"
    hook_block_approaching = "hook_block_approaching"
    hook_policy_changed = "hook_policy_changed"
    trade_cert_missing = "trade_cert_missing"
    cert_import_update = "cert_import_update"
    # ---- Phase 5 (5-training §7) ----
    training_record_expiry = "training_record_expiry"
    training_expiring_on_crew = "training_expiring_on_crew"
    training_refresher_due = "training_refresher_due"
    training_refresher_booked_late = "training_refresher_booked_late"
    training_gap_on_live_work = "training_gap_on_live_work"
    training_gap_at_mobilisation = "training_gap_at_mobilisation"
    training_session_update = "training_session_update"  # scheduled / rescheduled / cancelled
    training_session_reminder = "training_session_reminder"
    training_session_close_due = "training_session_close_due"
    training_session_voided = "training_session_voided"
    training_record_submitted = "training_record_submitted"
    training_verification_due = "training_verification_due"
    training_verification_unable = "training_verification_unable"
    training_verification_failed = "training_verification_failed"
    training_record_status = "training_record_status"  # returned / rejected / suspended /
    # revoked (no reason to contractor roles, TR-13)
    training_cert_no_reused = "training_cert_no_reused"
    trainer_authorisation_expiry = "trainer_authorisation_expiry"
    trainer_authorisation_lapsed_sessions = "trainer_authorisation_lapsed_sessions"
    training_provider_accreditation_expiry = "training_provider_accreditation_expiry"
    training_provider_status = "training_provider_status"  # suspended / blacklisted
    training_attempts_exceeded = "training_attempts_exceeded"
    training_import_update = "training_import_update"
    # ---- Phase 6a (6a-occupational-health §7; texts per P6-7, never outcomes to tier 1) ----
    fitness_expiry = "fitness_expiry"
    fitness_expiring_on_crew = "fitness_expiring_on_crew"
    fitness_review_due = "fitness_review_due"  # restriction / temporarily-unfit review
    fitness_hold_created = "fitness_hold_created"
    fitness_referral_raised = "fitness_referral_raised"
    fitness_referral_overdue = "fitness_referral_overdue"
    fitness_work_during_hold = "fitness_work_during_hold"
    fitness_rtw_before_clearance = "fitness_rtw_before_clearance"
    fitness_restricted_days_prompt = "fitness_restricted_days_prompt"
    fitness_signoff_due = "fitness_signoff_due"
    fitness_certificate_submitted = "fitness_certificate_submitted"
    fitness_verification_due = "fitness_verification_due"
    fitness_verification_unable = "fitness_verification_unable"
    fitness_verification_failed = "fitness_verification_failed"
    fitness_clinical_data_rejected = "fitness_clinical_data_rejected"
    fitness_cert_no_reused = "fitness_cert_no_reused"
    fitness_permanently_unfit = "fitness_permanently_unfit"
    fitness_second_opinion = "fitness_second_opinion"
    medical_licence_expiry = "medical_licence_expiry"  # provider or examiner licence
    medical_provider_status = "medical_provider_status"
    medical_reexamination_list = "medical_reexamination_list"  # MP-6 affected workers
    exposure_group_removed = "exposure_group_removed"  # WP-2
    fitness_catalogue_shortened = "fitness_catalogue_shortened"  # MC-3
    medical_import_update = "medical_import_update"
    # ---- Phase 6b (6b-heat-stress §7) ----
    heat_regime_raised = "heat_regime_raised"  # HA-1 / HA-2 (stop, may resume)
    heat_reading_overdue = "heat_reading_overdue"  # HA-4
    heat_ban_prewarn = "heat_ban_prewarn"  # HA-6
    heat_ban_violation = "heat_ban_violation"  # MB-3
    heat_exemption = "heat_exemption"  # granted / ending tomorrow / revoked
    heat_welfare_fail = "heat_welfare_fail"  # RS-3
    heat_welfare_missing = "heat_welfare_missing"
    heat_plan_created = "heat_plan_created"
    heat_plan_unconfirmed = "heat_plan_unconfirmed"  # AP-8
    heat_illness_entry = "heat_illness_entry"
    heat_review_overdue = "heat_review_overdue"  # HI-4
    heat_calibration_expiry = "heat_calibration_expiry"
    heat_coverage_gap = "heat_coverage_gap"  # required zone without an active point
    # ---- Phase 6c (6c-emergency-drills §7) ----
    emergency_event = "emergency_event"  # EV-2 declared
    emergency_unaccounted = "emergency_unaccounted"  # MU-8 / MU-6 found_on_site
    emergency_coverage_short = "emergency_coverage_short"  # EO-7
    emergency_drill_due = "emergency_drill_due"  # DP-4
    emergency_evaluation_overdue = "emergency_evaluation_overdue"  # DR-6 / EV-5
    emergency_asset_failed = "emergency_asset_failed"  # EA-4
    emergency_asset_due = "emergency_asset_due"  # check overdue, service / consumable due
    emergency_team_not_current = "emergency_team_not_current"  # RT-2
    emergency_erp_review = "emergency_erp_review"  # ER-7 / ER-8
    # ---- Phase 6d (6d-field-assurance §7) ----
    stop_work_order = "stop_work_order"  # FND-7 Active, > 24 h
    critical_item_failure = "critical_item_failure"  # FND-6
    inspection_coverage_gap = "inspection_coverage_gap"  # ISP-4
    audit_due = "audit_due"  # AUD-7
    audit_report_overdue = "audit_report_overdue"  # AUD-5
    briefing_campaign = "briefing_campaign"  # CMP-4
    offline_submission_rejected = "offline_submission_rejected"  # EXE-6
    field_library_review = "field_library_review"  # TPL-6
    # ---- Phase 6e (6e-environmental §7) ----
    env_exceedance = "env_exceedance"  # EXD-1 / EXD-6 / EXD-5 review due
    airside_dust_alert = "airside_dust_alert"  # AIR-1
    env_spill_reportable = "env_spill_reportable"  # SPL-3
    env_permit_expiry = "env_permit_expiry"  # PRM-3 (permits and provider licences)
    env_instrument_calibration = "env_instrument_calibration"  # MON-1
    consignment_overdue = "consignment_overdue"  # CON-6
    consignment_rejected = "consignment_rejected"  # CON-8
    haz_storage_deadline = "haz_storage_deadline"  # WST-5
    post_storm_check = "post_storm_check"  # AIR-4
    discharge_permit_invalid = "discharge_permit_invalid"  # WAT-3
    env_complaint = "env_complaint"  # CPL-1
    aspect_review = "aspect_review"  # ASP-3
