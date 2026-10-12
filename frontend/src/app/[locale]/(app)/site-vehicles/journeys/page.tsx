import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { JourneyPlansPage } from "@/components/site-vehicles/journeys";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <JourneyPlansPage />;
}
