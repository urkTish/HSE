import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { QualitySettingsPage } from "@/components/quality/q0/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <QualitySettingsPage />;
}
