import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HeatSettingsPage } from "@/components/heat/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HeatSettingsPage />;
}
