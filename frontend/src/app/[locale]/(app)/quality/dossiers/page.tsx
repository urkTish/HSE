import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DossierListPage } from "@/components/quality/q1/dossiers";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DossierListPage />;
}
