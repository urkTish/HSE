import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CompetencePage } from "@/components/quality/q2/competence";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CompetencePage />;
}
