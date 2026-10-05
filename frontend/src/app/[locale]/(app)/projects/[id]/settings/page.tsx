import { initRequestLocale } from "@/i18n/server";
import { ProjectSettings } from "@/components/projects/project-settings";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ProjectSettings projectId={p.id} />;
}
