import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { JourneyPlanNewPage } from "@/components/site-vehicles/journeys";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <JourneyPlanNewPage />;
}
