"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean; refetchInterval?: number | false };

/** Query keys for Phase 4 (third-party certification). Writes invalidate by the first element. */
export const ck = {
  catalogue: (pid: string) => ["cert-catalogue", pid] as const,
  settings: (pid: string) => ["cert-settings", pid] as const,
  hookPolicy: (pid: string) => ["hook-policy", pid] as const,
  hookReadiness: (pid: string, q: object) => ["hook-readiness", pid, q] as const,
  tpis: (q: object) => ["tpis", q] as const,
  tpi: (id: string) => ["tpi", id] as const,
  tpiImpact: (id: string) => ["tpi-impact", id] as const,
  approvals: (pid: string, q: object) => ["tpi-approvals", pid, q] as const,
  equipmentList: (q: object) => ["equipment", q] as const,
  equipment: (id: string) => ["equipment-item", id] as const,
  statusEvents: (id: string) => ["equipment-status-events", id] as const,
  configEvents: (id: string) => ["configuration-events", id] as const,
  deployments: (pid: string, q: object) => ["equipment-deployments", pid, q] as const,
  deployment: (id: string) => ["equipment-deployment", id] as const,
  eqSticker: (id: string) => ["equipment-sticker", id] as const,
  eqCerts: (pid: string, q: object) => ["equipment-certificates", pid, q] as const,
  eqCert: (id: string) => ["equipment-certificate", id] as const,
  eqCertVerifications: (id: string) => ["equipment-certificate-verifications", id] as const,
  verificationLog: (pid: string, q: object) => ["verification-log", pid, q] as const,
  scaffolds: (pid: string, q: object) => ["scaffolds", pid, q] as const,
  scaffold: (id: string) => ["scaffold", id] as const,
  scaffoldBoard: (pid: string, q: object) => ["scaffold-board", pid, q] as const,
  scaffoldInspections: (id: string) => ["scaffold-inspections", id] as const,
  scaffoldSticker: (id: string) => ["scaffold-sticker", id] as const,
  pcerts: (pid: string, q: object) => ["personnel-certificates", pid, q] as const,
  pcert: (id: string) => ["personnel-certificate", id] as const,
  pcertVerifications: (id: string) => ["personnel-certificate-verifications", id] as const,
  workerCerts: (wid: string, pid: string) => ["worker-certificates", wid, pid] as const,
  bans: (q: object) => ["certification-bans", q] as const,
  ban: (id: string) => ["certification-ban", id] as const,
  blacklist: (q: object) => ["blacklist-register", q] as const,
  defects: (pid: string, q: object) => ["defects", pid, q] as const,
  defect: (id: string) => ["defect", id] as const,
  defectPrompt: (iid: string) => ["incident-defect-prompt", iid] as const,
  imports: (pid: string, q: object) => ["certificate-imports", pid, q] as const,
  importBatch: (id: string, okRows: boolean) => ["certificate-import", id, okRows] as const,
  certKpis: (q: object) => ["kpi", "certification", q] as const,
};

/** Every Phase 4 prefix: a certification action can change service status, so we refresh them together. */
export const CERT_PREFIXES = [
  ...new Set(Object.values(ck).map((f) => (typeof f === "function" ? (f as (...a: string[]) => readonly unknown[])("", "", "")[0] : f[0]))),
  "dashboard",
  "kpi",
  "gas-detectors",
  "gas-detector",
  "permit",
  "permits",
  "history",
] as string[];

export function useCertRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(CERT_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);

/* ── configuration ── */

export function useCertCatalogue(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.catalogue(pid),
    queryFn: () => unwrap(api.GET("/api/v1/cert-catalogue", { params: { query: pid ? { project_id: pid } : {} } })),
    enabled: o.enabled ?? true,
    staleTime: 5 * 60_000,
  });
}

export function useCertSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.settings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/cert-settings", { params: { path: { project_id: pid } } })),
    enabled: on(pid, o),
  });
}

export function useHookPolicy(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.hookPolicy(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/hook-policy", { params: { path: { project_id: pid } } })),
    enabled: on(pid, o),
  });
}

export function useHookReadiness(pid: string, q: QueryOf<"get_hook_readiness">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.hookReadiness(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/hook-readiness", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── TPIs ── */

export function useTpis(q: QueryOf<"list_tpis">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.tpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/tpis", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

export function useTpi(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.tpi(id),
    queryFn: () => unwrap(api.GET("/api/v1/tpis/{tpi_id}", { params: { path: { tpi_id: id } } })),
    enabled: on(id, o),
  });
}

export function useTpiImpact(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.tpiImpact(id),
    queryFn: () => unwrap(api.GET("/api/v1/tpis/{tpi_id}/affected", { params: { path: { tpi_id: id } } })),
    enabled: on(id, o),
  });
}

export function useTpiApprovals(pid: string, q: QueryOf<"list_tpi_client_approvals">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.approvals(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/tpi-approvals", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── equipment ── */

export function useEquipmentList(q: QueryOf<"list_equipment">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.equipmentList(q),
    queryFn: () => unwrap(api.GET("/api/v1/equipment", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

export function useEquipment(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.equipment(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment/{equipment_id}", { params: { path: { equipment_id: id } } })),
    enabled: on(id, o),
  });
}

export function useEquipmentStatusEvents(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.statusEvents(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment/{equipment_id}/status-events", { params: { path: { equipment_id: id } } })),
    enabled: on(id, o),
  });
}

export function useConfigurationEvents(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.configEvents(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment/{equipment_id}/configuration-events", { params: { path: { equipment_id: id } } })),
    enabled: on(id, o),
  });
}

export function useEquipmentDeployments(pid: string, q: QueryOf<"list_equipment_deployments">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.deployments(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/equipment-deployments", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useEquipmentDeployment(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.deployment(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment-deployments/{deployment_id}", { params: { path: { deployment_id: id } } })),
    enabled: on(id, o),
  });
}

export function useEquipmentSticker(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.eqSticker(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment-deployments/{deployment_id}/sticker", { params: { path: { deployment_id: id } } })),
    enabled: on(id, o),
    retry: false,
  });
}

/* ── equipment certificates ── */

export function useEquipmentCertificates(pid: string, q: QueryOf<"list_equipment_certificates">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.eqCerts(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/equipment-certificates", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useEquipmentCertificate(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.eqCert(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment-certificates/{certificate_id}", { params: { path: { certificate_id: id } } })),
    enabled: on(id, o),
  });
}

export function useEquipmentCertVerifications(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.eqCertVerifications(id),
    queryFn: () => unwrap(api.GET("/api/v1/equipment-certificates/{certificate_id}/verifications", { params: { path: { certificate_id: id } } })),
    enabled: on(id, o),
  });
}

export function useVerificationLog(pid: string, q: QueryOf<"get_verification_log">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.verificationLog(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/verification-log", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── scaffolds ── */

export function useScaffolds(pid: string, q: QueryOf<"list_scaffolds">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.scaffolds(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scaffolds", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useScaffold(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.scaffold(id),
    queryFn: () => unwrap(api.GET("/api/v1/scaffolds/{scaffold_id}", { params: { path: { scaffold_id: id } } })),
    enabled: on(id, o),
  });
}

export function useScaffoldBoard(pid: string, q: QueryOf<"get_scaffold_board">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.scaffoldBoard(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scaffold-board", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    refetchInterval: o.refetchInterval ?? 60_000,
    ...list,
  });
}

export function useScaffoldInspections(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.scaffoldInspections(id),
    queryFn: () => unwrap(api.GET("/api/v1/scaffolds/{scaffold_id}/inspections", { params: { path: { scaffold_id: id } } })),
    enabled: on(id, o),
  });
}

export function useScaffoldSticker(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.scaffoldSticker(id),
    queryFn: () => unwrap(api.GET("/api/v1/scaffolds/{scaffold_id}/sticker", { params: { path: { scaffold_id: id } } })),
    enabled: on(id, o),
    retry: false,
  });
}

/* ── personnel certificates ── */

export function usePersonnelCertificates(pid: string, q: QueryOf<"list_personnel_certificates">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.pcerts(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/personnel-certificates", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function usePersonnelCertificate(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.pcert(id),
    queryFn: () => unwrap(api.GET("/api/v1/personnel-certificates/{certificate_id}", { params: { path: { certificate_id: id } } })),
    enabled: on(id, o),
  });
}

export function usePersonnelCertVerifications(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.pcertVerifications(id),
    queryFn: () => unwrap(api.GET("/api/v1/personnel-certificates/{certificate_id}/verifications", { params: { path: { certificate_id: id } } })),
    enabled: on(id, o),
  });
}

export function useWorkerCertificates(wid: string, pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.workerCerts(wid, pid),
    queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}/certificates", { params: { path: { worker_id: wid }, query: pid ? { project_id: pid } : {} } })),
    enabled: on(wid, o),
  });
}

/* ── bans, blacklist ── */

export function useCertificationBans(q: QueryOf<"list_certification_bans">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.bans(q),
    queryFn: () => unwrap(api.GET("/api/v1/certification-bans", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

export function useBlacklistRegister(q: QueryOf<"get_blacklist_register">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.blacklist(q),
    queryFn: () => unwrap(api.GET("/api/v1/blacklist-register", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

/* ── defects ── */

export function useDefects(pid: string, q: QueryOf<"list_defects">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.defects(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/defects", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useDefect(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.defect(id),
    queryFn: () => unwrap(api.GET("/api/v1/defects/{defect_id}", { params: { path: { defect_id: id } } })),
    enabled: on(id, o),
  });
}

export function useIncidentDefectPrompt(iid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ck.defectPrompt(iid),
    queryFn: () => unwrap(api.GET("/api/v1/incidents/{incident_id}/defect-prompt", { params: { path: { incident_id: iid } } })),
    enabled: on(iid, o),
    retry: false,
  });
}

/* ── imports ── */

export function useCertImports(pid: string, q: QueryOf<"list_certificate_imports">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.imports(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/certificate-imports", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useCertImport(id: string, includeOk: boolean, o: Opt = {}) {
  return useQuery({
    queryKey: ck.importBatch(id, includeOk),
    queryFn: () => unwrap(api.GET("/api/v1/certificate-imports/{batch_id}", { params: { path: { batch_id: id }, query: { include_ok_rows: includeOk } } })),
    enabled: on(id, o),
    ...list,
  });
}

/* ── KPIs ── */

export function useCertKpis(q: QueryOf<"get_cert_kpis">, o: Opt = {}) {
  return useQuery({
    queryKey: ck.certKpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/certification", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}
