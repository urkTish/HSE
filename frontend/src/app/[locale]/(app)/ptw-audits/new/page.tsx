import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PtwAuditCreatePage } from "@/components/ptw/audits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PtwAuditCreatePage />;
}
