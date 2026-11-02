import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ExcursionsListPage } from "@/components/quality/q3/excursions";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ExcursionsListPage />;
}
