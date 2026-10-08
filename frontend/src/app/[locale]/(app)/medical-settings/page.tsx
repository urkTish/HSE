import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MedicalSettingsPage } from "@/components/medical/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MedicalSettingsPage />;
}
