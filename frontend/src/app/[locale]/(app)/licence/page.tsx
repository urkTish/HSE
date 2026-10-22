import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { LicencePage } from "@/components/licence/licence-page";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <LicencePage />;
}
