import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WorkforceListPage } from "@/components/workforce/workforce-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WorkforceListPage />;
}
