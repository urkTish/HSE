import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TransportListPage } from "@/components/quality/q3/transport";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TransportListPage />;
}
