import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { SiteVehicleSettingsPage } from "@/components/site-vehicles/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <SiteVehicleSettingsPage />;
}
