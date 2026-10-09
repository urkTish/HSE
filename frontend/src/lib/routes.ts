import type { Schemas } from "@/lib/api/client";
import { toQueryString } from "@/lib/url-state";

/** UI route of a record by entity type (null when the UI has no page for it). */
export function entityRoute(type: Schemas["EntityType"] | string | null | undefined, id: string | null | undefined, projectId?: string | null): string | null {
  if (!id) {
    if (type === "cert_settings") return "/cert-settings";
    if (type === "hook_policy_state") return "/hook-policy";
    if (type === "training_settings") return "/training-settings";
    if (type === "medical_settings") return "/medical-settings";
    if (type === "heat_settings" || type === "heat_regime_table") return "/heat-settings";
    if (type === "project_settings" && projectId) return `/projects/${projectId}/settings`;
    if (type === "hse_settings" && projectId) return `/hse-settings?project=${projectId}`;
    return null;
  }
  switch (type) {
    case "project":
      return `/projects/${id}`;
    case "contractor":
      return `/contractors/${id}`;
    case "user":
      return `/users/${id}`;
    case "site":
      return projectId ? `/projects/${projectId}/sites/${id}` : null;
    case "zone":
      return projectId ? `/projects/${projectId}/zones/${id}` : null;
    case "project_engagement":
      return projectId ? `/projects/${projectId}/engagements/${id}` : null;
    case "workforce_return":
      return `/workforce/${id}`;
    case "workforce_import_batch":
      return `/workforce/imports/${id}`;
    case "incident":
      return `/incidents/${id}`;
    case "injury_case":
      return `/injury-cases/${id}`;
    case "investigation":
      return `/incidents/${id}`;
    case "observation":
      return `/observations/${id}`;
    case "inspection_plan":
      return `/inspection-plans/${id}`;
    case "inspection":
      return `/inspections/${id}`;
    case "corrective_action":
      return `/actions/${id}`;
    case "hse_meeting":
      return `/meetings/${id}`;
    case "monthly_report":
      return `/reports/${id}`;
    case "worker":
      return `/workers/${id}`;
    case "worker_deployment":
      return `/deployments/${id}`;
    case "induction_course":
      return `/induction-courses/${id}`;
    case "induction_record":
      return `/inductions/${id}`;
    case "zone_access_profile":
      return `/zone-profiles`;
    case "airport_pass_category":
    case "airport_pass_area":
      return `/pass-setup`;
    case "pass_application":
      return `/pass-applications/${id}`;
    case "airport_pass":
      return `/airport-passes/${id}`;
    case "adp":
      return `/adps/${id}`;
    case "airside_offence":
      return `/offences/${id}`;
    case "vehicle":
      return `/vehicles/${id}`;
    case "avp":
      return `/avps/${id}`;
    case "notam_request":
      return `/notams/${id}`;
    case "obstacle_clearance":
      return `/obstacle-clearances/${id}`;
    case "wap":
      return `/waps/${id}`;
    case "ops_event":
      return `/ops-events/${id}`;
    case "gate":
      return `/gates/${id}`;
    case "access_settings":
      return `/access-settings`;
    case "permit":
      return `/permits/${id}`;
    case "permit_shift":
    case "permit_handover":
    case "permit_suspension":
    case "permit_exemption":
      return null;
    case "permit_type_config":
      return `/ptw-setup/types`;
    case "zone_ptw_profile":
      return `/ptw-setup/zones`;
    case "zone_adjacency":
      return `/ptw-setup/adjacency`;
    case "simops_rule":
      return `/ptw-setup/simops-rules`;
    case "ptw_settings":
      return `/ptw-setup/settings`;
    case "ptw_appointment":
      return `/ptw-appointments/${id}`;
    case "jsa":
      return `/jsas/${id}`;
    case "gas_detector":
      return `/gas-detectors/${id}`;
    case "gas_test":
      return `/gas-tests/${id}`;
    case "isolation_certificate":
      return `/isolations/${id}`;
    case "lock":
    case "personal_lock_event":
      return `/locks`;
    case "simops_conflict":
      return `/simops-conflicts/${id}`;
    case "ptw_audit":
      return `/ptw-audits/${id}`;
    // Phase 4 — third-party certification
    case "tpi":
      return `/tpis/${id}`;
    case "tpi_accreditation":
    case "tpi_client_approval":
      return null;
    case "equipment_item":
      return `/equipment/${id}`;
    case "equipment_deployment":
      return `/equipment-deployments/${id}`;
    case "equipment_certificate":
      return `/equipment-certificates/${id}`;
    case "configuration_event":
      return null;
    case "scaffold":
      return `/scaffolds/${id}`;
    case "scaffold_inspection":
      return null;
    case "personnel_certificate":
      return `/personnel-certificates/${id}`;
    case "cert_verification":
      return `/verification-log`;
    case "equipment_defect":
      return `/defects/${id}`;
    case "certification_ban":
      return `/certification-bans`;
    case "hook_policy_state":
      return `/hook-policy`;
    case "cert_import_batch":
      return `/certificate-imports/${id}`;
    case "cert_settings":
      return `/cert-settings`;
    case "cert_type":
      return `/cert-catalogue`;
    // Phase 5 — training
    case "training_course":
      return /^[0-9a-f-]{36}$/.test(id) ? `/training-courses` : `/training-courses/${encodeURIComponent(id)}`;
    case "training_provider":
      return `/training-providers/${id}`;
    case "training_provider_accreditation":
      return null;
    case "trainer_authorisation":
      return `/trainer-authorisations/${id}`;
    case "training_matrix_line":
      return `/training-matrix`;
    case "training_exemption":
      return `/training-exemptions`;
    case "training_session":
      return `/training-sessions/${id}`;
    case "training_record":
      return `/training-records/${id}`;
    case "training_verification":
      return `/training-verification-log`;
    case "training_import_batch":
      return `/training-imports/${id}`;
    case "training_settings":
      return `/training-settings`;
    // Phase 6a — occupational health
    case "fitness_code":
      return /^[0-9a-f-]{36}$/.test(id) ? `/fitness-codes` : `/fitness-codes?q=${encodeURIComponent(id)}`;
    case "medical_provider":
      return `/medical-providers/${id}`;
    case "medical_examiner":
      return `/medical-examiners`;
    case "medical_plan_line":
      return `/medical-plan`;
    case "health_profile":
      return null;
    case "fitness_assessment":
      return `/fitness-assessments/${id}`;
    case "fitness_verification":
      return `/fitness-assessments`;
    case "fitness_hold":
      return `/fitness-holds`;
    case "fitness_referral":
      return `/fitness-referrals`;
    case "medical_import_batch":
      return `/medical-imports/${id}`;
    case "medical_settings":
      return `/medical-settings`;
    case "heat_instrument":
      return `/heat-instruments`;
    case "monitoring_point":
      return `/monitoring-points`;
    case "rest_station":
      return `/rest-stations`;
    case "wbgt_reading":
      return `/wbgt-readings`;
    case "acclimatisation_plan":
      return `/acclimatisation-plans/${id}`;
    case "heat_welfare_check":
      return `/heat-welfare-checks`;
    case "ban_patrol":
      return `/ban-patrols`;
    case "ban_exemption":
      return `/ban-exemptions`;
    case "heat_illness_entry":
      return `/heat-illness-log/${id}`;
    case "heat_season_report":
      return `/heat-season-report`;
    case "heat_settings":
    case "heat_regime_table":
      return `/heat-settings`;
    case "training_profile":
    case "training_nomination":
    case "training_retraining_note":
      return null;
    default:
      return null;
  }
}

const DETAIL: [RegExp, string][] = [
  [/^\/api\/v1\/incidents\/([0-9a-f-]{36})(?:\/investigation)?$/, "/incidents/$1"],
  [/^\/api\/v1\/injury-cases\/([0-9a-f-]{36})$/, "/injury-cases/$1"],
  [/^\/api\/v1\/observations\/([0-9a-f-]{36})$/, "/observations/$1"],
  [/^\/api\/v1\/inspections\/([0-9a-f-]{36})$/, "/inspections/$1"],
  [/^\/api\/v1\/inspection-plans\/([0-9a-f-]{36})$/, "/inspection-plans/$1"],
  [/^\/api\/v1\/corrective-actions\/([0-9a-f-]{36})$/, "/actions/$1"],
  [/^\/api\/v1\/workforce-returns\/([0-9a-f-]{36})$/, "/workforce/$1"],
  [/^\/api\/v1\/workforce-imports\/([0-9a-f-]{36})$/, "/workforce/imports/$1"],
  [/^\/api\/v1\/hse-meetings\/([0-9a-f-]{36})$/, "/meetings/$1"],
  [/^\/api\/v1\/monthly-reports\/([0-9a-f-]{36})$/, "/reports/$1"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/workforce-months(?:\/.*)?$/, "/workforce/months"],
  [/^\/api\/v1\/workers\/([0-9a-f-]{36})(?:\/.*)?$/, "/workers/$1"],
  [/^\/api\/v1\/deployments\/([0-9a-f-]{36})(?:\/access-card)?$/, "/deployments/$1"],
  [/^\/api\/v1\/induction-courses\/([0-9a-f-]{36})$/, "/induction-courses/$1"],
  [/^\/api\/v1\/inductions\/([0-9a-f-]{36})$/, "/inductions/$1"],
  [/^\/api\/v1\/pass-applications\/([0-9a-f-]{36})$/, "/pass-applications/$1"],
  [/^\/api\/v1\/airport-passes\/([0-9a-f-]{36})$/, "/airport-passes/$1"],
  [/^\/api\/v1\/adps\/([0-9a-f-]{36})$/, "/adps/$1"],
  [/^\/api\/v1\/airside-offences\/([0-9a-f-]{36})$/, "/offences/$1"],
  [/^\/api\/v1\/vehicles\/([0-9a-f-]{36})$/, "/vehicles/$1"],
  [/^\/api\/v1\/avps\/([0-9a-f-]{36})$/, "/avps/$1"],
  [/^\/api\/v1\/notam-requests\/([0-9a-f-]{36})$/, "/notams/$1"],
  [/^\/api\/v1\/obstacle-clearances\/([0-9a-f-]{36})$/, "/obstacle-clearances/$1"],
  [/^\/api\/v1\/waps\/([0-9a-f-]{36})$/, "/waps/$1"],
  [/^\/api\/v1\/ops-events\/([0-9a-f-]{36})$/, "/ops-events/$1"],
  [/^\/api\/v1\/gates\/([0-9a-f-]{36})$/, "/gates/$1"],
  [/^\/api\/v1\/credentials\/induction\/([0-9a-f-]{36})$/, "/inductions/$1"],
  [/^\/api\/v1\/credentials\/airport_pass\/([0-9a-f-]{36})$/, "/airport-passes/$1"],
  [/^\/api\/v1\/credentials\/adp\/([0-9a-f-]{36})$/, "/adps/$1"],
  [/^\/api\/v1\/credentials\/avp\/([0-9a-f-]{36})$/, "/avps/$1"],
  [/^\/api\/v1\/credentials\/access_card\/([0-9a-f-]{36})$/, "/deployments/$1"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/access-settings$/, "/access-settings"],
  [/^\/api\/v1\/permits\/([0-9a-f-]{36})(?:\/(?:print|closure-pack))?$/, "/permits/$1"],
  [/^\/api\/v1\/ptw-appointments\/([0-9a-f-]{36})$/, "/ptw-appointments/$1"],
  [/^\/api\/v1\/jsas\/([0-9a-f-]{36})$/, "/jsas/$1"],
  [/^\/api\/v1\/gas-detectors\/([0-9a-f-]{36})$/, "/gas-detectors/$1"],
  [/^\/api\/v1\/gas-tests\/([0-9a-f-]{36})$/, "/gas-tests/$1"],
  [/^\/api\/v1\/isolations\/([0-9a-f-]{36})$/, "/isolations/$1"],
  [/^\/api\/v1\/simops-conflicts\/([0-9a-f-]{36})$/, "/simops-conflicts/$1"],
  [/^\/api\/v1\/ptw-audits\/([0-9a-f-]{36})$/, "/ptw-audits/$1"],
  [/^\/api\/v1\/tpis\/([0-9a-f-]{36})(?:\/affected)?$/, "/tpis/$1"],
  [/^\/api\/v1\/equipment\/([0-9a-f-]{36})(?:\/.*)?$/, "/equipment/$1"],
  [/^\/api\/v1\/equipment-deployments\/([0-9a-f-]{36})(?:\/arrival-inspection)?$/, "/equipment-deployments/$1"],
  [/^\/api\/v1\/equipment-deployments\/([0-9a-f-]{36})\/sticker$/, "/equipment-deployments/$1/sticker"],
  [/^\/api\/v1\/equipment-certificates\/([0-9a-f-]{36})(?:\/verifications)?$/, "/equipment-certificates/$1"],
  [/^\/api\/v1\/scaffolds\/([0-9a-f-]{36})(?:\/inspections)?$/, "/scaffolds/$1"],
  [/^\/api\/v1\/scaffolds\/([0-9a-f-]{36})\/sticker$/, "/scaffolds/$1/sticker"],
  [/^\/api\/v1\/personnel-certificates\/([0-9a-f-]{36})(?:\/verifications)?$/, "/personnel-certificates/$1"],
  [/^\/api\/v1\/defects\/([0-9a-f-]{36})$/, "/defects/$1"],
  [/^\/api\/v1\/certificate-imports\/([0-9a-f-]{36})$/, "/certificate-imports/$1"],
  [/^\/api\/v1\/certification-bans(?:\/[0-9a-f-]{36})?$/, "/certification-bans"],
  [/^\/api\/v1\/blacklist-register$/, "/blacklist-register"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/(?:hook-policy|hook-readiness)$/, "/hook-policy"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/cert-settings$/, "/cert-settings"],
  [/^\/api\/v1\/training-courses\/([^/]+)$/, "/training-courses/$1"],
  [/^\/api\/v1\/training-providers\/([0-9a-f-]{36})(?:\/(?:affected|acceptability))?$/, "/training-providers/$1"],
  [/^\/api\/v1\/trainer-authorisations\/([0-9a-f-]{36})$/, "/trainer-authorisations/$1"],
  [/^\/api\/v1\/training-sessions\/([0-9a-f-]{36})(?:\/nominations)?$/, "/training-sessions/$1"],
  [/^\/api\/v1\/training-records\/([0-9a-f-]{36})(?:\/verifications)?$/, "/training-records/$1"],
  [/^\/api\/v1\/training-records\/([0-9a-f-]{36})\/certificate$/, "/training-records/$1/certificate"],
  [/^\/api\/v1\/training-imports\/([0-9a-f-]{36})$/, "/training-imports/$1"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/training-settings$/, "/training-settings"],
  [/^\/api\/v1\/medical-providers\/([0-9a-f-]{36})(?:\/affected)?$/, "/medical-providers/$1"],
  [/^\/api\/v1\/fitness-assessments\/([0-9a-f-]{36})(?:\/verifications)?$/, "/fitness-assessments/$1"],
  [/^\/api\/v1\/deployments\/([0-9a-f-]{36})\/(?:health-profile|fitness-requirements)$/, "/worker-health/$1"],
  [/^\/api\/v1\/medical-imports\/([0-9a-f-]{36})$/, "/medical-imports/$1"],
  [/^\/api\/v1\/projects\/[0-9a-f-]{36}\/medical-settings$/, "/medical-settings"],
];

/** Map an API record path (`detail_path`) to the UI page; null when there is none. */
export function apiPathToRoute(path: string | null | undefined): string | null {
  if (!path) return null;
  const clean = path.split("?")[0] ?? path;
  for (const [re, to] of DETAIL) {
    if (re.test(clean)) return clean.replace(re, to);
  }
  return null;
}

const LISTS: [RegExp, string][] = [
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/corrective-actions$/, "/actions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/incidents$/, "/incidents"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/observations$/, "/observations"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/inspections$/, "/inspections"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/workforce-returns$/, "/workforce"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/hse-meetings$/, "/meetings"],
  [/^\/api\/v1\/workers$/, "/workers"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/deployments$/, "/workers"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/inductions$/, "/inductions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/induction-sessions$/, "/inductions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/pass-applications$/, "/pass-applications"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/airport-passes$/, "/airport-passes"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/adps$/, "/adps"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/airside-offences$/, "/offences"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/vehicles$/, "/vehicles"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/avps$/, "/avps"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/notam-requests$/, "/notams"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/obstacle-clearances$/, "/obstacle-clearances"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/waps$/, "/waps"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/wap-board$/, "/wap-board"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/ops-events$/, "/ops-events"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/gate-log$/, "/gate-log"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/permits$/, "/permits"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/ptw-board$/, "/ptw-board"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/permit-suspensions$/, "/permit-suspensions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/ptw-appointments$/, "/ptw-appointments"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/jsa-templates$/, "/jsa-templates"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/gas-detectors$/, "/gas-detectors"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/gas-tests$/, "/gas-tests"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/isolations$/, "/isolations"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/locks$/, "/locks"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/simops-conflicts$/, "/simops-conflicts"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/ptw-audits$/, "/ptw-audits"],
  [/^\/api\/v1\/tpis$/, "/tpis"],
  [/^\/api\/v1\/equipment$/, "/equipment"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/equipment-deployments$/, "/equipment-deployments"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/equipment-certificates$/, "/equipment-certificates"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/personnel-certificates$/, "/personnel-certificates"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/verification-log$/, "/verification-log"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/scaffolds$/, "/scaffolds"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/scaffold-board$/, "/scaffold-board"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/defects$/, "/defects"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/certificate-imports$/, "/certificate-imports"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/hook-readiness$/, "/hook-policy"],
  [/^\/api\/v1\/certification-bans$/, "/certification-bans"],
  [/^\/api\/v1\/training-courses$/, "/training-courses"],
  [/^\/api\/v1\/training-providers$/, "/training-providers"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/trainer-authorisations$/, "/trainer-authorisations"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-matrix$/, "/training-matrix"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-exemptions$/, "/training-exemptions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-gaps(?:\/summary)?$/, "/training-gaps"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/refresher-plan$/, "/refresher-plan"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-sessions$/, "/training-sessions"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-records$/, "/training-records"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-verification-log$/, "/training-verification-log"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/training-imports$/, "/training-imports"],
  [/^\/api\/v1\/fitness-codes$/, "/fitness-codes"],
  [/^\/api\/v1\/medical-providers$/, "/medical-providers"],
  [/^\/api\/v1\/medical-examiners$/, "/medical-examiners"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/medical-plan$/, "/medical-plan"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/fitness-gaps$/, "/fitness-gaps"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/fitness-assessments$/, "/fitness-assessments"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/fitness-holds$/, "/fitness-holds"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/fitness-referrals$/, "/fitness-referrals"],
  [/^\/api\/v1\/projects\/([0-9a-f-]{36})\/medical-imports$/, "/medical-imports"],
];

/** Map an action-panel `ListLink` to the UI list with the same filters in the URL. */
export function listLinkToRoute(link: Schemas["ListLink"] | null | undefined): string | null {
  if (!link) return null;
  for (const [re, to] of LISTS) {
    const m = re.exec(link.path);
    if (m) {
      const query: Record<string, string | string[]> = { ...link.query };
      if (m[1]) query.project = m[1];
      if (!m[1] && typeof query.project_id === "string") query.project = query.project_id;
      return `${to}${toQueryString(query)}`;
    }
  }
  return apiPathToRoute(link.path);
}
