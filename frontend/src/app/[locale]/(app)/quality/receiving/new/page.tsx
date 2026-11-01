import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReceiptNewPage } from "@/components/quality/q3/receiving";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReceiptNewPage />;
}
