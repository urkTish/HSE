import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FieldFindingsPage } from "@/components/field/inspect";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FieldFindingsPage />;
}
