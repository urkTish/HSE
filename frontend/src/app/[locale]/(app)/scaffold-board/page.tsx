import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ScaffoldBoardPage } from "@/components/cert/scaffolds";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ScaffoldBoardPage />;
}
