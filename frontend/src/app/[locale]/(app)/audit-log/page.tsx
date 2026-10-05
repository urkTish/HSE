import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AuditLog } from "@/components/audit/audit-log";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AuditLog />;
}
