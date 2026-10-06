import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PlanListPage } from "@/components/inspections/inspection-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PlanListPage />;
}
