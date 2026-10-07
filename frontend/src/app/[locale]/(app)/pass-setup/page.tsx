import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PassSetupPage } from "@/components/access/setup";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PassSetupPage />;
}
