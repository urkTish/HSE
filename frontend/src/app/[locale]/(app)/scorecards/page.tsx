import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ScorecardsPage } from "@/components/scorecard/cards";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ScorecardsPage />;
}
