import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TrainingImportListPage } from "@/components/training/imports";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TrainingImportListPage />;
}
