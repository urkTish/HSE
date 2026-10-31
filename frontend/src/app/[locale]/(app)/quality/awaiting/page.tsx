import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AwaitingPage } from "@/components/quality/q0/home";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AwaitingPage />;
}
