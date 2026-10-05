import type { ReactNode } from "react";
import { initRequestLocale } from "@/i18n/server";
import { ProjectLayout } from "@/components/projects/project-layout";

export default async function Layout({ children, params }: { children: ReactNode; params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const { id } = await params;
  return <ProjectLayout projectId={id}>{children}</ProjectLayout>;
}
