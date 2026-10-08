import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FitnessGapsPage } from "@/components/medical/plan";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FitnessGapsPage />;
}
