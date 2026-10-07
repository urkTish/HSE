import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ZoneProfilesPage } from "@/components/access/setup";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ZoneProfilesPage />;
}
