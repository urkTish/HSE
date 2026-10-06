import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { UnplannedInspectionPage } from "@/components/inspections/inspection-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <UnplannedInspectionPage />;
}
