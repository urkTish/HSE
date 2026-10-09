import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FieldKpiPage } from "@/components/field/overview";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FieldKpiPage />;
}
