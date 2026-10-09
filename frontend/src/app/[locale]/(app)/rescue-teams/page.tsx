import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { RescueTeamsPage } from "@/components/emergency/org";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <RescueTeamsPage />;
}
