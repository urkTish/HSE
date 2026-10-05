"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./client";
import type { operations } from "./schema";

export type QueryOf<Op extends keyof operations> = NonNullable<operations[Op]["parameters"]["query"]>;

export const keys = {
  me: ["me"] as const,
  privacyNotice: ["privacy-notice"] as const,
  projects: (q?: QueryOf<"list_projects">) => ["projects", q ?? {}] as const,
  project: (id: string) => ["project", id] as const,
  settings: (projectId: string) => ["project-settings", projectId] as const,
  sites: (projectId: string, q?: QueryOf<"list_sites">) => ["sites", projectId, q ?? {}] as const,
  site: (id: string) => ["site", id] as const,
  zones: (projectId: string, q?: QueryOf<"list_zones">) => ["zones", projectId, q ?? {}] as const,
  zone: (id: string) => ["zone", id] as const,
  contractors: (q?: QueryOf<"list_contractors">) => ["contractors", q ?? {}] as const,
  contractor: (id: string) => ["contractor", id] as const,
  engagements: (projectId: string, q?: QueryOf<"list_engagements">) => ["engagements", projectId, q ?? {}] as const,
  engagement: (id: string) => ["engagement", id] as const,
  users: (q?: QueryOf<"list_users">) => ["users", q ?? {}] as const,
  user: (id: string) => ["user", id] as const,
  roleAssignments: (userId: string) => ["role-assignments", userId] as const,
  audit: (q?: QueryOf<"list_audit_log">) => ["audit-log", q ?? {}] as const,
  history: (type: string, id: string, page: number) => ["history", type, id, page] as const,
  notifications: (unreadOnly: boolean) => ["notifications", unreadOnly] as const,
};

export function useMe(enabled = true) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
    retry: false,
    staleTime: 60_000,
    enabled,
  });
}

export function usePrivacyNotice() {
  return useQuery({
    queryKey: keys.privacyNotice,
    queryFn: () => unwrap(api.GET("/api/v1/privacy-notice")),
    staleTime: Infinity,
  });
}

export function useProjects(q: QueryOf<"list_projects"> = {}) {
  return useQuery({
    queryKey: keys.projects(q),
    queryFn: () => unwrap(api.GET("/api/v1/projects", { params: { query: q } })),
    placeholderData: keepPreviousData,
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useProjectSettings(projectId: string | null | undefined) {
  return useQuery({
    queryKey: keys.settings(projectId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/settings", { params: { path: { project_id: projectId ?? "" } } })),
    enabled: Boolean(projectId),
    staleTime: 60_000,
  });
}

export function useSites(projectId: string, q: QueryOf<"list_sites"> = {}) {
  return useQuery({
    queryKey: keys.sites(projectId, q),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/sites", { params: { path: { project_id: projectId }, query: q } })),
    enabled: Boolean(projectId),
    placeholderData: keepPreviousData,
  });
}

export function useSite(id: string) {
  return useQuery({
    queryKey: keys.site(id),
    queryFn: () => unwrap(api.GET("/api/v1/sites/{site_id}", { params: { path: { site_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useZones(projectId: string, q: QueryOf<"list_zones"> = {}) {
  return useQuery({
    queryKey: keys.zones(projectId, q),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/zones", { params: { path: { project_id: projectId }, query: q } })),
    enabled: Boolean(projectId),
    placeholderData: keepPreviousData,
  });
}

export function useZone(id: string) {
  return useQuery({
    queryKey: keys.zone(id),
    queryFn: () => unwrap(api.GET("/api/v1/zones/{zone_id}", { params: { path: { zone_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useContractors(q: QueryOf<"list_contractors"> = {}, enabled = true) {
  return useQuery({
    queryKey: keys.contractors(q),
    queryFn: () => unwrap(api.GET("/api/v1/contractors", { params: { query: q } })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useContractor(id: string) {
  return useQuery({
    queryKey: keys.contractor(id),
    queryFn: () => unwrap(api.GET("/api/v1/contractors/{contractor_id}", { params: { path: { contractor_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useEngagements(projectId: string, q: QueryOf<"list_engagements"> = {}, enabled = true) {
  return useQuery({
    queryKey: keys.engagements(projectId, q),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/engagements", { params: { path: { project_id: projectId }, query: q } }),
      ),
    enabled: Boolean(projectId) && enabled,
    placeholderData: keepPreviousData,
  });
}

export function useEngagement(id: string) {
  return useQuery({
    queryKey: keys.engagement(id),
    queryFn: () => unwrap(api.GET("/api/v1/engagements/{engagement_id}", { params: { path: { engagement_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useUsers(q: QueryOf<"list_users"> = {}, enabled = true) {
  return useQuery({
    queryKey: keys.users(q),
    queryFn: () => unwrap(api.GET("/api/v1/users", { params: { query: q } })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useUser(id: string) {
  return useQuery({
    queryKey: keys.user(id),
    queryFn: () => unwrap(api.GET("/api/v1/users/{user_id}", { params: { path: { user_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useRoleAssignments(userId: string) {
  return useQuery({
    queryKey: keys.roleAssignments(userId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/users/{user_id}/role-assignments", { params: { path: { user_id: userId } } })),
    enabled: Boolean(userId),
  });
}

export function useAuditLog(q: QueryOf<"list_audit_log">) {
  return useQuery({
    queryKey: keys.audit(q),
    queryFn: () => unwrap(api.GET("/api/v1/audit-log", { params: { query: q } })),
    placeholderData: keepPreviousData,
  });
}

export function useHistory(entityType: Schemas["EntityType"], entityId: string, page: number) {
  return useQuery({
    queryKey: keys.history(entityType, entityId, page),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/history/{entity_type}/{entity_id}", {
          params: { path: { entity_type: entityType, entity_id: entityId }, query: { page, page_size: 20 } },
        }),
      ),
    enabled: Boolean(entityId),
    placeholderData: keepPreviousData,
  });
}

export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: keys.notifications(unreadOnly),
    queryFn: () =>
      unwrap(api.GET("/api/v1/notifications", { params: { query: { unread_only: unreadOnly, page: 1, page_size: 20 } } })),
    refetchInterval: 60_000,
  });
}
