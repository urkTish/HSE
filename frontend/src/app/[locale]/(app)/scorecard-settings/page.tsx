import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ScorecardSettingsPage } from "@/components/scorecard/settings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ScorecardSettingsPage />;
}
