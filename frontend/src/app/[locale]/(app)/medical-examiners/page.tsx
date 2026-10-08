import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MedicalExaminersPage } from "@/components/medical/catalogue";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MedicalExaminersPage />;
}
