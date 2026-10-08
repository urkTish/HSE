import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CertImportListPage } from "@/components/cert/imports";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CertImportListPage />;
}
