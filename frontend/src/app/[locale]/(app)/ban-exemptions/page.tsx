import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { BanExemptionsPage } from "@/components/heat/ban";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <BanExemptionsPage />;
}
