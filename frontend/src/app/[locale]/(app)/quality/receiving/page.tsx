import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReceivingListPage } from "@/components/quality/q3/receiving";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReceivingListPage />;
}
