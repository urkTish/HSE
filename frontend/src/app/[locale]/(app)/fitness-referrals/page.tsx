import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FitnessReferralsPage } from "@/components/medical/holds";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FitnessReferralsPage />;
}
