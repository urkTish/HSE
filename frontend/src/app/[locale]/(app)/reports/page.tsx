import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReportListPage } from "@/components/reports/report-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReportListPage />;
}
