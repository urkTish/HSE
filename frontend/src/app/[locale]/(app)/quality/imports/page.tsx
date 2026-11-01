import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ImportsPage } from "@/components/quality/q3/imports";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ImportsPage />;
}
