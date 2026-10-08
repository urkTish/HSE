import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CertSettingsPage } from "@/components/cert/config";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CertSettingsPage />;
}
