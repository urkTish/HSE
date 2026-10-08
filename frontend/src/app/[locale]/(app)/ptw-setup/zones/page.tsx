import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ZonePtwProfilesPage } from "@/components/ptw/config";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ZonePtwProfilesPage />;
}
