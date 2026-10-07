import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AdpCreatePage } from "@/components/access/adps";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AdpCreatePage />;
}
