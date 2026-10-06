import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WorkforceMonthsPage } from "@/components/workforce/workforce-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WorkforceMonthsPage />;
}
