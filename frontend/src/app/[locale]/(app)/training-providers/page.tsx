import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ProviderListPage } from "@/components/training/providers";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ProviderListPage />;
}
