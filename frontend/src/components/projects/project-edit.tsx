"use client";
import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/common/page-header";
import { LoadingState } from "@/components/common/states";
import { ProjectForm } from "@/components/projects/project-form";
import { useProject } from "@/lib/api/queries";

export function ProjectEdit({ projectId }: { projectId: string }) {
  const t = useTranslations("project");
  const q = useProject(projectId);
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <PageHeader title={t("editTitle")} />
      <ProjectForm project={q.data} />
    </div>
  );
}
