"use client";
import { ErrorState, LoadingState } from "@/components/common/states";
import { ZoneForm } from "@/components/zones/zone-form";
import { useProject, useSite, useZone } from "@/lib/api/queries";

export function ZoneCreate({ projectId, siteId }: { projectId: string; siteId: string }) {
  const project = useProject(projectId);
  const site = useSite(siteId);
  if (site.isError) return <ErrorState error={site.error} />;
  if (!project.data || !site.data) return <LoadingState />;
  return <ZoneForm project={project.data} site={site.data} />;
}

export function ZoneEdit({ projectId, zoneId }: { projectId: string; zoneId: string }) {
  const project = useProject(projectId);
  const zone = useZone(zoneId);
  const site = useSite(zone.data?.site_id ?? "");
  if (zone.isError) return <ErrorState error={zone.error} />;
  if (!project.data || !zone.data || !site.data) return <LoadingState />;
  return <ZoneForm project={project.data} site={site.data} zone={zone.data} />;
}
