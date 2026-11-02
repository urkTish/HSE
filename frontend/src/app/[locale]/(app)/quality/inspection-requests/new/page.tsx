import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { IrNewPage } from "@/components/quality/q1/irs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <IrNewPage />;
}
