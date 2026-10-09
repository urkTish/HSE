import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WelfareChecksPage } from "@/components/heat/welfare";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WelfareChecksPage />;
}
