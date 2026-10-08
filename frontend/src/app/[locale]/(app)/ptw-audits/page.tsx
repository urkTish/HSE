import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PtwAuditListPage } from "@/components/ptw/audits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PtwAuditListPage />;
}
