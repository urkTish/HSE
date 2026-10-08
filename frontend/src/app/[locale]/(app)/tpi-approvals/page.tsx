import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TpiApprovalsPage } from "@/components/cert/tpis";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TpiApprovalsPage />;
}
