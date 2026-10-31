import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ItpNewPage } from "@/components/quality/q1/itps";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ItpNewPage />;
}
