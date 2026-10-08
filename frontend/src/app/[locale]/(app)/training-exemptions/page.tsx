import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ExemptionsPage } from "@/components/training/gaps";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ExemptionsPage />;
}
