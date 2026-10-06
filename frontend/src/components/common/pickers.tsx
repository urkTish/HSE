"use client";
import { useMemo, type SelectHTMLAttributes } from "react";
import { useTranslations } from "next-intl";
import { Select } from "@/components/ui/select";
import { useEngagements, useSites, useUsers, useZones } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import type { Schemas } from "@/lib/api/client";

export interface ProjectOptions {
  sites: { value: string; label: string; code: string }[];
  zones: { value: string; label: string; siteId: string; zoneType: Schemas["ZoneType"] }[];
  engagements: { value: string; label: string; tier: number; code: string; status: Schemas["ContractorStatus"]; siteIds: string[] }[];
  zoneById: Map<string, Schemas["ZoneRead"]>;
  isLoading: boolean;
}

/** Sites, zones and contractor engagements of a project for selects and filters. */
export function useProjectOptions(projectId: string): ProjectOptions {
  const name = useLocalizedName();
  const sites = useSites(projectId, { page_size: 200, sort: "code" });
  const zones = useZones(projectId, { page_size: 200, sort: "code" });
  const engagements = useEngagements(projectId, { page_size: 200 });
  return useMemo(() => {
    const zs = zones.data?.items ?? [];
    return {
      sites: (sites.data?.items ?? []).map((s) => ({ value: s.id, label: `${s.code} — ${name(s.name_en, s.name_ar)}`, code: s.code })),
      zones: zs.map((z) => ({ value: z.id, label: `${z.code} — ${name(z.name_en, z.name_ar)}`, siteId: z.site_id, zoneType: z.zone_type })),
      engagements: (engagements.data?.items ?? [])
        .slice()
        .sort((a, b) => a.tier - b.tier || a.contractor.short_code.localeCompare(b.contractor.short_code))
        .map((e) => ({ value: e.id, label: `${e.contractor.short_code} · T${e.tier}`, tier: e.tier, code: e.contractor.short_code, status: e.contractor.status, siteIds: e.site_ids })),
      zoneById: new Map(zs.map((z) => [z.id, z])),
      isLoading: sites.isLoading || zones.isLoading || engagements.isLoading,
    };
  }, [sites.data, zones.data, engagements.data, name, sites.isLoading, zones.isLoading, engagements.isLoading]);
}

/** Active users who hold a role on the project (owner, verifier, investigator pickers). */
export function UserSelect({
  projectId,
  role,
  placeholder,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { projectId: string; role?: Schemas["Role"]; placeholder?: string }) {
  const t = useTranslations("common");
  const name = useLocalizedName();
  const q = useUsers({ project_id: projectId, status: ["active"], role, page_size: 200, sort: "name" });
  return (
    <Select {...props}>
      <option value="">{placeholder ?? t("select")}</option>
      {(q.data?.items ?? []).map((u) => (
        <option key={u.id} value={u.id}>
          {name(u.full_name_en, u.full_name_ar)}
          {u.job_title ? ` — ${u.job_title}` : ""}
        </option>
      ))}
    </Select>
  );
}

export function userName(u: { full_name_en: string; full_name_ar?: string | null } | null | undefined, locale: string): string {
  if (!u) return "—";
  return locale === "ar" && u.full_name_ar ? u.full_name_ar : u.full_name_en;
}

/** Active project users as {value,label} options (multi-selects such as investigation teams). */
export function useUserOptions(projectId: string): { value: string; label: string }[] {
  const name = useLocalizedName();
  const q = useUsers({ project_id: projectId, status: ["active"], page_size: 200, sort: "name" });
  return useMemo(() => (q.data?.items ?? []).map((u) => ({ value: u.id, label: name(u.full_name_en, u.full_name_ar) })), [q.data, name]);
}
