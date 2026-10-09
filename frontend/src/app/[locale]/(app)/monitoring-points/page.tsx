import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MonitoringPointsPage } from "@/components/heat/setup";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MonitoringPointsPage />;
}
