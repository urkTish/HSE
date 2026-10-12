import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { SiteVehicleNewPage } from "@/components/site-vehicles/vehicles";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <SiteVehicleNewPage />;
}
