import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { VehicleCreatePage } from "@/components/access/vehicles";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <VehicleCreatePage />;
}
