import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EffectivenessChecksPage } from "@/components/followup/lessons";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EffectivenessChecksPage />;
}
