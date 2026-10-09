import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ChecklistRunPage } from "@/components/field/run";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ChecklistRunPage />;
}
