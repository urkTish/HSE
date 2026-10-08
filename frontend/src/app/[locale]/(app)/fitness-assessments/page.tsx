import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FitnessAssessmentsPage } from "@/components/medical/assessments";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FitnessAssessmentsPage />;
}
