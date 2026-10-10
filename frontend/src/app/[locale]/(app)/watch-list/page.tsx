import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WatchListPage } from "@/components/scorecard/watch";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WatchListPage />;
}
