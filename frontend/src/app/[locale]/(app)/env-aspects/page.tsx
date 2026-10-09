import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AspectsPage } from "@/components/env/register";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AspectsPage />;
}
