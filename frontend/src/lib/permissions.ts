import type { Schemas } from "@/lib/api/client";

export type Me = Schemas["Me"];
export type Capability = Schemas["Capability"];

/**
 * UI-only capability check (rule 8: the server is the control; this just hides actions).
 * - Org capabilities (HSE Manager) apply to every project.
 * - With a projectId, only that project's grants count (rule 9).
 * - Without a projectId, any project granting the capability is enough.
 */
export function can(me: Me | undefined, capability: Capability, projectId?: string | null): boolean {
  if (!me) return false;
  if (me.org_capabilities.includes(capability)) return true;
  const projects = projectId ? me.projects.filter((p) => p.project_id === projectId) : me.projects;
  return projects.some((p) => p.capabilities.some((c) => c.capability === capability));
}

/** True when the user can only read in the project (viewer, or contractor suspended). */
export function isReadOnly(me: Me | undefined, projectId: string): boolean {
  if (!me) return true;
  if (me.is_hse_manager) return false;
  const access = me.projects.find((p) => p.project_id === projectId);
  return access ? access.read_only : true;
}

export function canWrite(me: Me | undefined, capability: Capability, projectId?: string | null): boolean {
  if (!can(me, capability, projectId)) return false;
  if (projectId && !me?.is_hse_manager && isReadOnly(me, projectId)) return false;
  return true;
}
