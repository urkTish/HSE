import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EmergencyKpiPage } from "@/components/emergency/board";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EmergencyKpiPage />;
}
