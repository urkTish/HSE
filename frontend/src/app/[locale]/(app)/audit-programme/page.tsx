import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AuditProgrammePage } from "@/components/field/audits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AuditProgrammePage />;
}
