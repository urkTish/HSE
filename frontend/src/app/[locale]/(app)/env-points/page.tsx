import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EnvPointsPage } from "@/components/env/monitoring";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EnvPointsPage />;
}
