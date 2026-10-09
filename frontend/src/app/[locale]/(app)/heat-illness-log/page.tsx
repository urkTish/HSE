import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HeatLogPage } from "@/components/heat/log";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HeatLogPage />;
}
