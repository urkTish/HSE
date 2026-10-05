import { initRequestLocale } from "@/i18n/server";
import { ProjectEdit } from "@/components/projects/project-edit";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ProjectEdit projectId={p.id} />;
}
