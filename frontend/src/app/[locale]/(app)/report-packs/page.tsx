import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReportPacksPage } from "@/components/scorecard/packs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReportPacksPage />;
}
