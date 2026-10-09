import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FieldAuditsPage } from "@/components/field/audits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FieldAuditsPage />;
}
