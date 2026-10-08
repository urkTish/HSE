import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MedicalPlanPage } from "@/components/medical/plan";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MedicalPlanPage />;
}
