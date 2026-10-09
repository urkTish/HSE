import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EnvSettingsPage } from "@/components/env/overview";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EnvSettingsPage />;
}
