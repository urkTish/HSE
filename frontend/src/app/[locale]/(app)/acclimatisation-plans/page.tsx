import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AcclimatisationPlansPage } from "@/components/heat/plans";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AcclimatisationPlansPage />;
}
