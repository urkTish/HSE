import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FitnessHoldsPage } from "@/components/medical/holds";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FitnessHoldsPage />;
}
