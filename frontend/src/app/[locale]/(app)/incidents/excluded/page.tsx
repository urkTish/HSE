import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ExcludedCasesPage } from "@/components/incidents/incident-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ExcludedCasesPage />;
}
