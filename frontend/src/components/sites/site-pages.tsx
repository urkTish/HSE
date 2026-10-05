"use client";
import { ErrorState, LoadingState } from "@/components/common/states";
import { SiteForm } from "@/components/sites/site-form";
import { useProject, useSite } from "@/lib/api/queries";

export function SiteCreate({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  if (!project.data) return <LoadingState />;
  return <SiteForm project={project.data} />;
}

export function SiteEdit({ projectId, siteId }: { projectId: string; siteId: string }) {
  const project = useProject(projectId);
  const site = useSite(siteId);
  if (site.isError) return <ErrorState error={site.error} />;
  if (!project.data || !site.data) return <LoadingState />;
  return <SiteForm project={project.data} site={site.data} />;
}
