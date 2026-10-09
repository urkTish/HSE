import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ZoneProfilesPage } from "@/components/emergency/plan";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ZoneProfilesPage />;
}
