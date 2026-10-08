import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DefectListPage } from "@/components/cert/defects";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DefectListPage />;
}
