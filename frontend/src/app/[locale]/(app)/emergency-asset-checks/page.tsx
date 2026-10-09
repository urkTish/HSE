import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AssetChecksPage } from "@/components/emergency/assets";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AssetChecksPage />;
}
