import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HeatDutyListPage } from "@/components/heat/board";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HeatDutyListPage />;
}
