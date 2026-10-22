import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FirstSetup } from "@/components/auth/first-setup";

export default async function SetupPage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FirstSetup />;
}
