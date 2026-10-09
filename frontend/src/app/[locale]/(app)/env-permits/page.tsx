import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EnvPermitsPage } from "@/components/env/register";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EnvPermitsPage />;
}
