import type { Schemas } from "@/lib/api/client";
import { toQueryString } from "@/lib/url-state";

/** UI route of a record by entity type (null when the UI has no page for it). */
export function entityRoute(type: Schemas["EntityType"] | string | null | undefined, id: string | null | undefined, projectId?: string | null): string | null {
  if (!id) {
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
