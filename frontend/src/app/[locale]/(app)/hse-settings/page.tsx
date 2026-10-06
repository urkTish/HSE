import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HseSettingsRoute } from "@/components/hse-settings/admin-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HseSettingsRoute />;
}
