"""Server-side permission matrix and project/site/contractor scoping (spec §5.2, §5.10).

A ``Principal`` is built once per request from the user's *active* role assignments (today in
Asia/Riyadh). Permissions are the union of assignments within the project being accessed.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import (
    AuditAction,
    AuditResult,
    Capability,
    CapabilityScope,
    ContractorStatus,
    EntityType,
    Role,
)
from app.core.errors import ApiError, ErrorCode, not_found
from app.models import Contractor, Project, ProjectEngagement, RoleAssignment, User, UserSession
from app.services import audit
from app.services.audit import AuditActor

C = Capability
S = CapabilityScope

# Phase 3 (3-ptw §5.14): capabilities the HSE Manager does NOT hold org-wide ("—" in the
# manager column: preparing, receiving, area review, issuing, isolating, personal locks,
# de-isolation, SIMOPS signatures). They come only from a project role assignment.
MANAGER_EXCLUDED: frozenset[Capability] = frozenset(
    {
        C.permit_prepare,
        C.permit_receive,
        C.permit_area_review,
        C.permit_issue,
        C.isolation_manage,
        C.personal_lock_record,
        C.deisolation_authorise,
        C.simops_coordinate,
        # 6a OH-3 (DECISIONS #55): the manager never records clinical assessments
        C.fitness_record_clinic,
    }
)
MANAGER_CAPABILITIES: tuple[Capability, ...] = tuple(
    c for c in Capability if c not in MANAGER_EXCLUDED
)

# Spec §5.10, one dict per role. Missing capability = "—".
MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_manager: dict.fromkeys(MANAGER_CAPABILITIES, S.all),
    Role.hse_officer: {
        C.project_view: S.project,
        C.site_zone_manage: S.project,
        C.site_zone_view: S.project,
        C.contractor_create: S.project,
        C.engagement_manage: S.project,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_invite: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.audit_log_read: S.project,
        C.history_view: S.project,
        C.export_lists: S.project,
        C.profile_edit_own: S.all,
        # Phase 1 (1-dashboard §5.10)
        C.workforce_edit: S.project,
        C.workforce_import: S.project,
        C.workforce_verify: S.project,
        C.workforce_view: S.project,
        C.incident_report: S.project,
        C.incident_classify: S.project,
        C.investigation_edit: S.project,
        C.investigation_approve: S.project,
        C.injury_identity_view: S.project,
        C.injury_medical_view: S.project,
        C.incident_view: S.project,
        C.observation_create: S.project,
        C.observation_close: S.project,
        C.inspection_plan_manage: S.project,
        C.inspection_record: S.project,
        C.ca_create: S.project,
        C.ca_update_own: S.project,
        C.ca_verify: S.project,
        C.ca_approve_extension: S.project,
        C.dashboard_view: S.project,
        C.breakdown_sensitive_view: S.project,
        C.ai_ask: S.project,
        C.monthly_report_generate: S.project,
        C.monthly_report_review: S.project,
        C.monthly_report_view: S.project,
        C.export_kpis: S.project,
        C.export_identity: S.project,
    },
    Role.site_engineer: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.history_view: S.sites,
        C.export_lists: S.sites,
        C.profile_edit_own: S.all,
        # Phase 1
        C.workforce_edit: S.sites,
        C.workforce_view: S.sites,
        C.incident_report: S.sites,
        C.investigation_edit: S.sites,
        C.incident_view: S.sites,
        C.observation_create: S.sites,
        C.observation_close: S.sites,
        C.inspection_record: S.sites,
        C.ca_create: S.sites,
        C.ca_update_own: S.sites,
        C.ca_verify: S.sites,
        C.dashboard_view: S.sites,
        C.ai_ask: S.sites,
        C.export_kpis: S.sites,
    },
    Role.permit_issuer: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.project,
        C.contractor_view_contacts: S.project,
        C.user_view_directory: S.project,
        C.user_view_contacts: S.project,
        C.settings_view: S.project,
        C.history_view: S.sites,
        C.profile_edit_own: S.all,
        # Phase 1
        C.workforce_view: S.sites,
        C.incident_report: S.sites,
        C.incident_view: S.sites,
        C.observation_create: S.sites,
        C.ca_update_own: S.sites,
        C.dashboard_view: S.sites,
        C.ai_ask: S.sites,
    },
    Role.permit_receiver: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.own_engagement,
        C.contractor_view_contacts: S.own_engagement,
        C.user_view_directory: S.own_engagement,
        C.user_view_contacts: S.own_engagement,
        C.settings_view: S.project,
        C.history_view: S.own_engagement,
        C.profile_edit_own: S.all,
        # Phase 1
        C.workforce_view: S.own_engagement,
        C.incident_report: S.own_engagement,
        C.incident_view: S.own_engagement,
        C.observation_create: S.own_engagement,
        C.ca_update_own: S.own_engagement,
        C.dashboard_view: S.own_engagement,
        C.ai_ask: S.own_engagement,
    },
    Role.contractor_hse_rep: {
        C.project_view: S.project,
        C.site_zone_view: S.sites,
        C.contractor_view: S.contractor_tree,
        C.contractor_view_contacts: S.contractor_tree,
        C.user_view_directory: S.contractor_tree,
        C.user_view_contacts: S.contractor_tree,
        C.settings_view: S.project,
        C.history_view: S.contractor_tree,
        C.export_lists: S.contractor_tree,
        C.profile_edit_own: S.all,
        # Phase 1
        C.workforce_edit: S.contractor_tree,
        C.workforce_import: S.contractor_tree,
        C.workforce_view: S.contractor_tree,
        C.incident_report: S.contractor_tree,
        C.investigation_edit: S.contractor_tree,
        C.injury_identity_view: S.contractor_tree,
        C.incident_view: S.contractor_tree,
        C.observation_create: S.contractor_tree,
        C.observation_close: S.contractor_tree,
        C.inspection_record: S.contractor_tree,
        C.ca_create: S.contractor_tree,
        C.ca_update_own: S.contractor_tree,
        C.ca_verify: S.contractor_tree,
        C.dashboard_view: S.contractor_tree,
        C.ai_ask: S.contractor_tree,
        C.export_kpis: S.contractor_tree,
    },
    Role.viewer_client: {
        C.project_view: S.project,
        C.site_zone_view: S.project,
        C.contractor_view: S.project,
        C.settings_view: S.project,
        C.history_view: S.project,
        C.export_lists: S.project,
        C.profile_edit_own: S.all,
        # Phase 1
        C.workforce_view: S.project,
        C.incident_view: S.project,
        C.dashboard_view: S.project,
        C.ai_ask: S.project,
        C.monthly_report_view: S.project,
        C.export_kpis: S.project,
    },
}

# Phase 2 (2-access-permits §5.13), rows 46-81. Viewer/Client rows 73 and 77 are aggregates /
# no-names reads (WA-19, KA-4), enforced in the services.
PHASE2_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: {
        **dict.fromkeys(
            [
                C.worker_view, C.worker_edit, C.worker_unmask_id, C.induction_course_manage,
                C.induction_record, C.induction_suspend_revoke, C.pass_application_create,
                C.pass_application_endorse, C.pass_application_process, C.background_check_view,
                C.credential_suspend_raise, C.credential_suspend_confirm, C.credential_custody,
                C.adp_apply, C.adp_issue, C.offence_record, C.vehicle_edit, C.avp_issue,
                C.wap_edit, C.wap_approve, C.wap_suspend, C.wap_close, C.notam_edit,
                C.notam_process, C.obstacle_edit, C.obstacle_decide, C.access_works_view,
                C.gate_check, C.gate_manage, C.gate_log_view, C.access_kpi_view, C.export_access,
                C.export_access_identity, C.zone_profile_edit,
            ],
            S.project,
        ),
    },
    Role.site_engineer: dict.fromkeys(
        [
            C.worker_view, C.credential_suspend_raise, C.offence_record, C.wap_edit,
            C.wap_suspend, C.wap_close, C.notam_edit, C.obstacle_edit, C.access_works_view,
            C.gate_check, C.gate_log_view, C.access_kpi_view, C.export_access,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.worker_view, C.credential_suspend_raise, C.offence_record, C.wap_approve,
            C.wap_suspend, C.wap_close, C.access_works_view, C.gate_check, C.access_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [C.worker_view, C.wap_edit, C.wap_close, C.access_works_view, C.access_kpi_view],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.worker_view, C.worker_edit, C.worker_unmask_id, C.induction_record,
            C.pass_application_create, C.credential_custody, C.adp_apply, C.vehicle_edit,
            C.wap_edit, C.wap_close, C.notam_edit, C.obstacle_edit, C.access_works_view,
            C.gate_check, C.gate_log_view, C.access_kpi_view, C.export_access,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys([C.access_works_view, C.access_kpi_view], S.project),
}  # fmt: skip
for _role, _caps in PHASE2_MATRIX.items():
    MATRIX[_role].update(_caps)

# Phase 3 (3-ptw §5.14), rows 82-104. "+appt" (85, 87, 92, 97) and the gas tester / issuer
# appointment checks are enforced in the services on top of these rows. Viewer/Client rows
# 82, 103 and 104 are counts / aggregates / no-names (PT-19), also enforced in the services.
PHASE3_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.permit_view, C.permit_area_review, C.permit_hse_review, C.permit_suspend,
            C.permit_cancel, C.gas_test_record, C.gas_detector_manage, C.isolation_manage,
            C.jsa_template_manage, C.simops_coordinate, C.ptw_zone_profile_edit,
            C.ptw_appointment_manage, C.ptw_audit_conduct, C.ptw_kpi_view, C.export_ptw,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.permit_view, C.permit_prepare, C.permit_area_review, C.permit_suspend,
            C.gas_test_record, C.isolation_manage, C.personal_lock_record, C.simops_coordinate,
            C.ptw_audit_conduct, C.ptw_kpi_view, C.export_ptw,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.permit_view, C.permit_area_review, C.permit_issue, C.permit_suspend,
            C.permit_cancel, C.gas_test_record, C.isolation_manage, C.personal_lock_record,
            C.deisolation_authorise, C.simops_coordinate, C.ptw_audit_conduct, C.ptw_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.permit_view, C.permit_prepare, C.permit_receive, C.permit_suspend,
            C.permit_cancel, C.gas_test_record, C.personal_lock_record, C.ptw_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.permit_view, C.permit_prepare, C.permit_suspend, C.gas_test_record,
            C.gas_detector_manage, C.personal_lock_record, C.jsa_template_manage,
            C.ptw_audit_conduct, C.ptw_kpi_view, C.export_ptw,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys([C.permit_view, C.ptw_kpi_view, C.export_ptw], S.project),
}  # fmt: skip
for _role, _caps in PHASE3_MATRIX.items():
    MATRIX[_role].update(_caps)

# Phase 4 (4-third-party-cert §5.15), rows 105-124. Parenthesised restrictions (site engineers
# edit only scaffolds / configuration events under 106 and only arrival under 109; contractor
# reps demobilise only own deployments and import contractor_file only; Viewer/Client read-only,
# aggregates, no names) are enforced in the services on top of these rows. 115 and 124 are
# HSE Manager only (the manager holds every capability not in MANAGER_EXCLUDED).
PHASE4_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.cert_register_view, C.equipment_edit, C.cert_review, C.cert_verify,
            C.equipment_mobilise, C.defect_raise, C.defect_rectify, C.defect_close,
            C.scaffold_inspect, C.tpi_edit, C.cert_suspend, C.personnel_cert_view,
            C.personnel_cert_submit, C.personnel_cert_scan_view, C.cert_import, C.cert_check,
            C.cert_kpi_view, C.export_cert,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.cert_register_view, C.equipment_edit, C.equipment_mobilise, C.defect_raise,
            C.defect_rectify, C.scaffold_inspect, C.personnel_cert_view, C.cert_check,
            C.cert_kpi_view, C.export_cert,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.cert_register_view, C.defect_raise, C.personnel_cert_view, C.cert_check,
            C.cert_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.cert_register_view, C.defect_raise, C.personnel_cert_view, C.cert_check,
            C.cert_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.cert_register_view, C.equipment_edit, C.equipment_mobilise, C.defect_raise,
            C.defect_rectify, C.scaffold_inspect, C.personnel_cert_view,
            C.personnel_cert_submit, C.personnel_cert_scan_view, C.cert_import, C.cert_check,
            C.cert_kpi_view, C.export_cert,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys(
        [C.cert_register_view, C.cert_kpi_view, C.export_cert], S.project
    ),
}  # fmt: skip
for _role, _caps in PHASE4_MATRIX.items():
    MATRIX[_role].update(_caps)

# 5-training §5.15 (capabilities 125-145). The HSE Manager holds all of them (A); 126, 128 and
# 145 are HSE-Manager-only. Contractor HSE Rep 132 / 134 / 141 narrow further in the services
# (TA-6 own contractor_internal provider, own sessions, contractor_file only).
PHASE5_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.training_catalogue_view, C.training_provider_edit, C.training_matrix_edit,
            C.training_profile_edit, C.trainer_authorise, C.training_session_manage,
            C.training_nominate, C.training_attendance_record, C.training_session_close,
            C.training_record_view, C.training_record_submit, C.training_record_review,
            C.training_scan_view, C.training_record_suspend, C.training_import,
            C.training_check, C.training_kpi_view, C.export_training,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.training_catalogue_view, C.training_profile_edit, C.training_nominate,
            C.training_record_view, C.training_check, C.training_kpi_view, C.export_training,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.training_catalogue_view, C.training_record_view, C.training_check,
            C.training_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.training_catalogue_view, C.training_record_view, C.training_check,
            C.training_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.training_catalogue_view, C.training_profile_edit, C.training_session_manage,
            C.training_nominate, C.training_attendance_record, C.training_record_view,
            C.training_record_submit, C.training_scan_view, C.training_import,
            C.training_check, C.training_kpi_view, C.export_training,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys(
        [C.training_catalogue_view, C.training_kpi_view, C.export_training], S.project
    ),
}  # fmt: skip
for _role, _caps in PHASE5_MATRIX.items():
    MATRIX[_role].update(_caps)

# 6a-occupational-health §5.15 (capabilities 146-165) and §11.1 (Phase 0/1 rows of the new
# Occupational Health Practitioner role). Parenthesised narrowing (HSE Officer 159 place only,
# Contractor HSE Rep contractor_file imports only, Viewer/Client aggregates only) is enforced in
# the services. 147, 149 and 164 are HSE Manager only.
MATRIX[Role.oh_practitioner] = {
    C.project_view: S.project,
    C.site_zone_view: S.project,
    C.contractor_view: S.project,
    C.user_view_directory: S.project,
    C.user_view_contacts: S.project,
    C.settings_view: S.project,
    C.history_view: S.project,
    C.profile_edit_own: S.all,
    C.injury_identity_view: S.project,
    C.injury_medical_view: S.project,
    C.incident_view: S.project,
}
PHASE6A_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.medical_provider_edit, C.medical_plan_edit,
            C.health_profile_edit, C.fitness_submit_external, C.fitness_status_view,
            C.fitness_functional_view, C.fitness_referral_raise, C.fitness_hold_manage,
            C.medical_kpi_view, C.export_medical,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.health_profile_edit, C.fitness_status_view,
            C.fitness_functional_view, C.fitness_referral_raise, C.medical_kpi_view,
            C.export_medical,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.fitness_status_view, C.fitness_referral_raise,
            C.medical_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.fitness_status_view, C.fitness_referral_raise,
            C.medical_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.health_profile_edit, C.fitness_submit_external,
            C.fitness_status_view, C.fitness_functional_view, C.fitness_referral_raise,
            C.fitness_import, C.medical_kpi_view, C.export_medical,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys(
        [C.fitness_catalogue_view, C.medical_kpi_view, C.export_medical], S.project
    ),
    Role.oh_practitioner: dict.fromkeys(
        [
            C.fitness_catalogue_view, C.medical_provider_edit, C.medical_plan_edit,
            C.health_profile_edit, C.fitness_record_clinic, C.fitness_submit_external,
            C.fitness_review, C.fitness_status_view, C.fitness_functional_view,
            C.fitness_clinical_view, C.fitness_referral_raise, C.fitness_hold_manage,
            C.fitness_scan_view, C.fitness_import, C.medical_kpi_view, C.export_medical,
            C.fitness_subject_report,
        ],
        S.project,
    ),
}  # fmt: skip
for _role, _caps in PHASE6A_MATRIX.items():
    MATRIX[_role].update(_caps)

# 6b-heat-stress §5.13 (capabilities 166-177). 171 and 175 are HSE Manager only. Parenthesised
# narrowing (173 view-only for site engineers / reps / OH; Viewer/Client aggregates and issued
# reports only) is enforced in the services.
PHASE6B_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.heat_view, C.heat_reading_record, C.heat_register_manage, C.heat_welfare_record,
            C.heat_patrol_record, C.heat_plan_manage, C.heat_log_view, C.heat_kpi_view,
            C.export_heat, C.heat_void,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.heat_view, C.heat_reading_record, C.heat_welfare_record, C.heat_patrol_record,
            C.heat_plan_manage, C.heat_log_view, C.heat_kpi_view, C.export_heat,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.heat_view, C.heat_reading_record, C.heat_welfare_record, C.heat_patrol_record,
            C.heat_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.heat_view, C.heat_reading_record, C.heat_welfare_record, C.heat_plan_manage,
            C.heat_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.heat_view, C.heat_reading_record, C.heat_welfare_record, C.heat_plan_manage,
            C.heat_log_view, C.heat_kpi_view, C.export_heat,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys([C.heat_view, C.heat_kpi_view, C.export_heat], S.project),
    Role.oh_practitioner: dict.fromkeys(
        [C.heat_view, C.heat_plan_manage, C.heat_log_view, C.heat_kpi_view], S.project
    ),
}  # fmt: skip
for _role, _caps in PHASE6B_MATRIX.items():
    MATRIX[_role].update(_caps)

# 6c-emergency-drills §5.13 (capabilities 178-190). 180 is HSE Manager only. Narrowing in
# parentheses (site engineers: 188 All Clear only; Viewer/Client: 178 read-only and 189 aggregates)
# is enforced in the services.
PHASE6C_MATRIX: dict[Role, dict[Capability, CapabilityScope]] = {
    Role.hse_officer: dict.fromkeys(
        [
            C.emergency_view, C.erp_prepare, C.emergency_roster_manage, C.emergency_asset_manage,
            C.emergency_check_record, C.drill_plan, C.drill_run, C.drill_evaluate,
            C.emergency_declare, C.emergency_all_clear, C.emergency_kpi_view, C.emergency_void,
        ],
        S.project,
    ),
    Role.site_engineer: dict.fromkeys(
        [
            C.emergency_view, C.emergency_roster_manage, C.emergency_asset_manage,
            C.emergency_check_record, C.drill_plan, C.drill_run, C.drill_evaluate,
            C.emergency_declare, C.emergency_all_clear, C.emergency_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_issuer: dict.fromkeys(
        [
            C.emergency_view, C.emergency_check_record, C.drill_run, C.emergency_declare,
            C.emergency_kpi_view,
        ],
        S.sites,
    ),
    Role.permit_receiver: dict.fromkeys(
        [
            C.emergency_view, C.emergency_check_record, C.drill_run, C.emergency_declare,
            C.emergency_kpi_view,
        ],
        S.own_engagement,
    ),
    Role.contractor_hse_rep: dict.fromkeys(
        [
            C.emergency_view, C.emergency_roster_manage, C.emergency_asset_manage,
            C.emergency_check_record, C.drill_run, C.emergency_declare, C.emergency_kpi_view,
        ],
        S.contractor_tree,
    ),
    Role.viewer_client: dict.fromkeys([C.emergency_view, C.emergency_kpi_view], S.project),
    Role.oh_practitioner: dict.fromkeys(
        [C.emergency_view, C.emergency_declare, C.emergency_kpi_view], S.project
    ),
}  # fmt: skip
for _role, _caps in PHASE6C_MATRIX.items():
    MATRIX[_role].update(_caps)

SCOPE_RANK = {S.own_engagement: 1, S.contractor_tree: 2, S.sites: 3, S.project: 4, S.all: 5}
ROLE_RANK = {r: i for i, r in enumerate(Role)}  # lower index = more senior
OFFICER_ASSIGNABLE = frozenset(
    {
        Role.site_engineer,
        Role.permit_issuer,
        Role.permit_receiver,
        Role.contractor_hse_rep,
        Role.viewer_client,
    }
)
CONTRACTOR_ROLES = frozenset({Role.contractor_hse_rep, Role.permit_receiver})


@dataclass(frozen=True)
class Grant:
    scope: CapabilityScope
    site_ids: frozenset[uuid.UUID] | None = None  # None = all sites
    engagement_ids: frozenset[uuid.UUID] | None = None  # None = all engagements

    def covers_site(self, site_id: uuid.UUID | None) -> bool:
        return self.site_ids is None or (site_id is not None and site_id in self.site_ids)

    def covers_engagement(self, engagement_id: uuid.UUID | None) -> bool:
        return self.engagement_ids is None or (
            engagement_id is not None and engagement_id in self.engagement_ids
        )


FULL = Grant(S.all)


def _merge(a: Grant | None, b: Grant) -> Grant:
    if a is None:
        return b
    scope = a.scope if SCOPE_RANK[a.scope] >= SCOPE_RANK[b.scope] else b.scope
    sites = None if a.site_ids is None or b.site_ids is None else a.site_ids | b.site_ids
    engs = (
        None
        if a.engagement_ids is None or b.engagement_ids is None
        else a.engagement_ids | b.engagement_ids
    )
    return Grant(scope, sites, engs)


@dataclass
class ProjectScope:
    project_id: uuid.UUID
    project_code: str
    assignments: list[RoleAssignment] = field(default_factory=list)
    grants: dict[Capability, Grant] = field(default_factory=dict)

    @property
    def roles(self) -> set[Role]:
        return {a.role for a in self.assignments}

    @property
    def read_only(self) -> bool:
        return self.roles == {Role.viewer_client}

    @property
    def primary_role(self) -> Role:
        return min(self.roles, key=lambda r: ROLE_RANK[r])


def engagement_descendants(db: Session, engagement_id: uuid.UUID) -> set[uuid.UUID]:
    """Spec K4: the engagement plus every engagement whose parent chain reaches it."""
    eng = db.get(ProjectEngagement, engagement_id)
    if eng is None:
        return set()
    rows = db.execute(
        select(ProjectEngagement.id, ProjectEngagement.parent_engagement_id).where(
            ProjectEngagement.project_id == eng.project_id
        )
    ).all()
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for rid, parent in rows:
        if parent is not None:
            children.setdefault(parent, []).append(rid)
    out = {engagement_id}
    stack = [engagement_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


@dataclass
class Principal:
    user: User
    session: UserSession | None
    today: date
    is_manager: bool
    projects: dict[uuid.UUID, ProjectScope]
    employer_status: ContractorStatus | None
    active_assignments: list[RoleAssignment]

    # ---- capability lookup -------------------------------------------------------------
    def grant(self, project_id: uuid.UUID | None, cap: Capability) -> Grant | None:
        if self.is_manager and cap not in MANAGER_EXCLUDED:
            return FULL
        if project_id is None:
            return None
        scope = self.projects.get(project_id)
        return scope.grants.get(cap) if scope else None

    def project_grants(self, cap: Capability) -> dict[uuid.UUID, Grant] | None:
        """Grants per project for a capability; ``None`` means every project (manager)."""
        if self.is_manager and cap not in MANAGER_EXCLUDED:
            return None
        return {pid: g for pid, s in self.projects.items() if (g := s.grants.get(cap))}

    def has_any(self, cap: Capability) -> bool:
        if self.is_manager and cap not in MANAGER_EXCLUDED:
            return True
        return any(cap in s.grants for s in self.projects.values())

    def has_role_anywhere(self, role: Role) -> bool:
        return any(role in s.roles for s in self.projects.values())

    def can_see_project(self, project_id: uuid.UUID) -> bool:
        return self.is_manager or project_id in self.projects

    def actor(self, project_id: uuid.UUID | None = None) -> AuditActor:
        if self.is_manager:
            return AuditActor(self.user.id, Role.hse_manager, project_id)
        scope = self.projects.get(project_id) if project_id else None
        if scope:
            return AuditActor(self.user.id, scope.primary_role, project_id)
        roles = sorted({a.role for a in self.active_assignments}, key=lambda r: ROLE_RANK[r])
        return AuditActor(self.user.id, roles[0] if roles else None, project_id)

    # ---- guards -------------------------------------------------------------------------
    def ensure_writer(self) -> None:
        """Rule 28: users of a suspended contractor keep read access but cannot write."""
        if self.employer_status == ContractorStatus.suspended:
            raise ApiError(
                403,
                ErrorCode.CONTRACTOR_SUSPENDED,
                "Your contractor is suspended: changes are blocked.",
                "المقاول الذي تتبع له موقوف: التعديلات محظورة.",
            )

    def require(self, project_id: uuid.UUID | None, cap: Capability) -> Grant:
        self.ensure_writer()
        g = self.grant(project_id, cap)
        if g is None:
            scope = self.projects.get(project_id) if project_id else None
            if scope and scope.read_only:
                raise ApiError(
                    403,
                    ErrorCode.READ_ONLY_ROLE,
                    "Your role on this project is read-only.",
                    "دورك في هذا المشروع للاطلاع فقط.",
                )
            raise forbidden_error()
        return g

    def require_any(self, cap: Capability) -> None:
        self.ensure_writer()
        if not self.has_any(cap):
            raise forbidden_error()


def forbidden_error(message: str = "You do not have permission for this action.") -> ApiError:
    return ApiError(
        403,
        ErrorCode.FORBIDDEN,
        message,
        "ليس لديك صلاحية لتنفيذ هذا الإجراء.",
    )


def deny(
    db: Session,
    p: Principal,
    entity_type: EntityType,
    entity_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    what: str = "Resource",
) -> ApiError:
    """Rule 12: out-of-scope by ID → 404 plus an ``access_denied`` audit entry."""
    audit.record(
        db,
        AuditAction.access_denied,
        p.actor(project_id),
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        result=AuditResult.denied,
        defer=True,
    )
    return not_found(what)


def active_assignments(db: Session, user_id: uuid.UUID, day: date) -> list[RoleAssignment]:
    rows = db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.valid_from <= day,
        )
    ).all()
    return [a for a in rows if a.is_active_on(day)]


def build_principal(db: Session, user: User, session: UserSession | None) -> Principal:
    day = today()
    assignments = active_assignments(db, user.id, day)
    is_manager = any(a.role == Role.hse_manager for a in assignments)
    project_ids = {a.project_id for a in assignments if a.project_id}
    codes = dict(
        db.execute(select(Project.id, Project.code).where(Project.id.in_(project_ids))).all()
    )
    projects: dict[uuid.UUID, ProjectScope] = {}
    tree_cache: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for a in assignments:
        if a.project_id is None:
            continue
        scope = projects.setdefault(a.project_id, ProjectScope(a.project_id, codes[a.project_id]))
        scope.assignments.append(a)
        for cap, cap_scope in MATRIX[a.role].items():
            engs: frozenset[uuid.UUID] | None = None
            if cap_scope == S.contractor_tree and a.contractor_engagement_id:
                eid = a.contractor_engagement_id
                if eid not in tree_cache:
                    tree_cache[eid] = frozenset(engagement_descendants(db, eid))
                engs = tree_cache[eid]
            elif cap_scope == S.own_engagement and a.contractor_engagement_id:
                engs = frozenset({a.contractor_engagement_id})
            elif cap_scope in (S.contractor_tree, S.own_engagement):
                engs = frozenset()
            sites = frozenset(a.site_ids) if a.site_ids else None
            scope.grants[cap] = _merge(scope.grants.get(cap), Grant(cap_scope, sites, engs))
    employer_status = None
    if user.employer_contractor_id:
        employer_status = db.scalar(
            select(Contractor.status).where(Contractor.id == user.employer_contractor_id)
        )
    return Principal(
        user=user,
        session=session,
        today=day,
        is_manager=is_manager,
        projects=projects,
        employer_status=employer_status,
        active_assignments=assignments,
    )


def capability_list(scope: ProjectScope) -> Iterable[tuple[Capability, Grant]]:
    return sorted(scope.grants.items(), key=lambda kv: list(Capability).index(kv[0]))
