import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TestTypesPage } from "@/components/quality/q2/testing";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TestTypesPage />;
}
