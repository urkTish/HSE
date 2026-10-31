import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { RecallsListPage } from "@/components/quality/q3/recalls";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <RecallsListPage />;
}
