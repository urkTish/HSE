import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { IrBoardPage } from "@/components/quality/q1/irs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <IrBoardPage />;
}
