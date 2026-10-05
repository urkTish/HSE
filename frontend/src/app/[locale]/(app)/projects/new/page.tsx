import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ProjectCreate } from "@/components/projects/project-create";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ProjectCreate />;
}
