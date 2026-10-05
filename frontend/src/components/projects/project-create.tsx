"use client";
import { useTranslations } from "next-intl";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { ProjectForm } from "@/components/projects/project-form";

export function ProjectCreate() {
  const t = useTranslations("project");
  const tn = useTranslations("nav");
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("projects"), href: "/projects" }, { label: t("createTitle") }]} />
      <PageHeader title={t("createTitle")} />
      <ProjectForm />
    </div>
  );
}
