import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EmergencyInfoPage } from "@/components/emergency/board";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EmergencyInfoPage />;
}
