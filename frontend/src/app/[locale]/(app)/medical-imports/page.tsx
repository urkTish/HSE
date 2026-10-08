import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MedicalImportsPage } from "@/components/medical/imports";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MedicalImportsPage />;
}
