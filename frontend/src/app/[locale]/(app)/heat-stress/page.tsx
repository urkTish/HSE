import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HeatKpiPage } from "@/components/heat/report";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HeatKpiPage />;
}
