"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6d (field assurance). Writes invalidate by the first element. */
export const fk = {
  reference: () => ["field-reference"] as const,
  settings: (pid: string) => ["field-settings", pid] as const,
  templates: (q: object) => ["checklist-templates", q] as const,
  template: (id: string) => ["checklist-template", id] as const,
  topics: (q: object) => ["toolbox-topics", q] as const,
  topic: (id: string) => ["toolbox-topic", id] as const,
  response: (id: string) => ["checklist-response", id] as const,
  findings: (pid: string, q: object) => ["field-findings", pid, q] as const,
  stops: (pid: string, q: object) => ["stop-work-orders", pid, q] as const,
  stop: (id: string) => ["stop-work-order", id] as const,
  actions: (pid: string) => ["field-action-panel", pid] as const,
  band: (pid: string) => ["field-band", pid] as const,
  audits: (pid: string, q: object) => ["field-audits", pid, q] as const,
  audit: (id: string) => ["field-audit", id] as const,
  programme: (pid: string) => ["audit-programme", pid] as const,
  talks: (pid: string, q: object) => ["toolbox-talks", pid, q] as const,
  talk: (id: string) => ["toolbox-talk", id] as const,
  suggestions: (pid: string, q: object) => ["toolbox-suggestions", pid, q] as const,
  campaigns: (pid: string, q: object) => ["briefing-campaigns", pid, q] as const,
  campaign: (id: string) => ["briefing-campaign", id] as const,
  kpis: (q: object) => ["kpi", "field-assurance", q] as const,
};

/** Every Phase 6d prefix plus the Phase 1 inspection, CA, permit and dashboard consumers. */
export const FIELD_PREFIXES = [
  ...new Set(Object.values(fk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "inspections",
  "inspection",
  "inspection-plans",
  "permit",
  "permits",
  "corrective-actions",
  "history",
];

export function useFieldRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(FIELD_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useFieldReference() {
  return useQuery({ queryKey: fk.reference(), queryFn: () => unwrap(api.GET("/api/v1/field-reference")), staleTime: 10 * 60_000 });
}

export function useFieldSettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/field-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useTemplates(q: QueryOf<"list_checklist_templates"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.templates(q), queryFn: () => unwrap(api.GET("/api/v1/checklist-templates", { params: { query: { page_size: 200, ...q } } })), enabled: o.enabled ?? true, ...list });
}

export function useTemplate(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.template(id), queryFn: () => unwrap(api.GET("/api/v1/checklist-templates/{template_id}", { params: { path: { template_id: id } } })), enabled: on(id, o) });
}

export function useTopics(q: QueryOf<"list_toolbox_topics"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.topics(q), queryFn: () => unwrap(api.GET("/api/v1/toolbox-topics", { params: { query: { page_size: 200, ...q } } })), enabled: o.enabled ?? true, ...list });
}

export function useTopic(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.topic(id), queryFn: () => unwrap(api.GET("/api/v1/toolbox-topics/{topic_id}", { params: { path: { topic_id: id } } })), enabled: on(id, o) });
}

export function useChecklistResponse(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.response(id), queryFn: () => unwrap(api.GET("/api/v1/checklist-responses/{response_id}", { params: { path: { response_id: id } } })), enabled: on(id, o) });
}

export function useFieldFindings(pid: string, q: QueryOf<"list_field_findings"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.findings(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/field-findings", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useStopWorkOrders(pid: string, q: QueryOf<"list_stop_work_orders"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.stops(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/stop-work-orders", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useStopWorkOrder(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.stop(id), queryFn: () => unwrap(api.GET("/api/v1/stop-work-orders/{order_id}", { params: { path: { order_id: id } } })), enabled: on(id, o) });
}

export function useFieldActionPanel(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.actions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/field-action-panel", { params: P(pid) })), enabled: on(pid, o) });
}

/** Field band (§8.1 item 2) is live: refreshed every minute. */
export function useFieldBand(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.band(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/field-band", { params: P(pid) })), enabled: on(pid, o), refetchInterval: 60_000 });
}

export function useFieldAudits(pid: string, q: QueryOf<"list_field_audits"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.audits(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/field-audits", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useFieldAudit(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.audit(id), queryFn: () => unwrap(api.GET("/api/v1/field-audits/{audit_id}", { params: { path: { audit_id: id } } })), enabled: on(id, o) });
}

export function useAuditProgramme(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.programme(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/audit-programme", { params: P(pid) })), enabled: on(pid, o) });
}

export function useToolboxTalks(pid: string, q: QueryOf<"list_toolbox_talks"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.talks(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/toolbox-talks", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useToolboxTalk(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.talk(id), queryFn: () => unwrap(api.GET("/api/v1/toolbox-talks/{talk_id}", { params: { path: { talk_id: id } } })), enabled: on(id, o) });
}

export function useToolboxSuggestions(pid: string, q: QueryOf<"get_toolbox_suggestions">, o: Opt = {}) {
  return useQuery({
    queryKey: fk.suggestions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/toolbox-suggestions", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o) && Boolean(q.site_id) && Boolean(q.host_engagement_id),
  });
}

export function useCampaigns(pid: string, q: QueryOf<"list_briefing_campaigns"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fk.campaigns(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/briefing-campaigns", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useCampaign(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fk.campaign(id), queryFn: () => unwrap(api.GET("/api/v1/briefing-campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })), enabled: on(id, o) });
}

export function useFieldKpis(q: QueryOf<"get_field_assurance_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: fk.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/field-assurance", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
