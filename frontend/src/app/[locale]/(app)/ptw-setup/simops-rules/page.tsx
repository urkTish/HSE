import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { SimopsRulesPage } from "@/components/ptw/config";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <SimopsRulesPage />;
}
