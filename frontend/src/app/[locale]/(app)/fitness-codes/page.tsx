import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FitnessCodesPage } from "@/components/medical/catalogue";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FitnessCodesPage />;
}
