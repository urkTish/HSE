import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { InspectionListPage } from "@/components/inspections/inspection-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <InspectionListPage />;
}
