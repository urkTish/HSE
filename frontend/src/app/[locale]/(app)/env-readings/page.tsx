import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EnvReadingsPage } from "@/components/env/monitoring";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EnvReadingsPage />;
}
