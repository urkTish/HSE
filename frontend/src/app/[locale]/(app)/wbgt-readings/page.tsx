import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WbgtReadingsPage } from "@/components/heat/readings";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WbgtReadingsPage />;
}
