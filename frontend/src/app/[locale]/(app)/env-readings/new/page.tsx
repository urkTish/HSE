import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { NewEnvReadingPage } from "@/components/env/monitoring";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <NewEnvReadingPage />;
}
