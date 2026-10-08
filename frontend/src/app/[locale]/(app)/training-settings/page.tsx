import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TrainingSettingsPage } from "@/components/training/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TrainingSettingsPage />;
}
