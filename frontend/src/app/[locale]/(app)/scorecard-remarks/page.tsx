import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { RemarksPage } from "@/components/scorecard/remarks";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <RemarksPage />;
}
