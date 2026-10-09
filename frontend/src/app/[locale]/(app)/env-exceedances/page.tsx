import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ExceedancesPage } from "@/components/env/monitoring";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ExceedancesPage />;
}
