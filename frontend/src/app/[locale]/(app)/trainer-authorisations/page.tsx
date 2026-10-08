import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TrainerListPage } from "@/components/training/trainers";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TrainerListPage />;
}
