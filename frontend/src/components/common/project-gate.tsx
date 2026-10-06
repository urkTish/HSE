"use client";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useProject } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";
import { useSearchState } from "@/lib/url-state";
import type { Schemas } from "@/lib/api/client";

/**
 * Project-scoped registers use the project chosen in the top bar. A `?project=` in the URL
 * (dashboard drill-down links) switches the current project first.
 */
export function ProjectGate({ children }: { children: (project: Schemas["ProjectRead"]) => ReactNode }) {
  const t = useTranslations("common");
  const { project, projects, setProjectId, isLoading } = useCurrentProject();
  const { get } = useSearchState();
  const wanted = get("project");
  useEffect(() => {
    if (wanted && wanted !== project?.id && projects.some((p) => p.id === wanted)) setProjectId(wanted);
  }, [wanted, project?.id, projects, setProjectId]);
  if (isLoading) return <LoadingState />;
  if (wanted && wanted !== project?.id && projects.some((p) => p.id === wanted)) return <LoadingState />;
  if (!project) return <Alert tone="info">{t("noProject")}</Alert>;
  return <>{children(project)}</>;
}

/** Loads a record's project (edit pages of project-scoped records). */
export function ProjectById({ id, children }: { id: string; children: (project: Schemas["ProjectRead"]) => ReactNode }) {
  const q = useProject(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <>{children(q.data)}</>;
}
