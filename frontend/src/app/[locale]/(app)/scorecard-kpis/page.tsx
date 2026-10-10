import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ScorecardKpiPage } from "@/components/scorecard/kpis";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ScorecardKpiPage />;
}
