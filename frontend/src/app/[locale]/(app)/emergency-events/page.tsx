import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EmergencyEventsPage } from "@/components/emergency/events";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EmergencyEventsPage />;
}
