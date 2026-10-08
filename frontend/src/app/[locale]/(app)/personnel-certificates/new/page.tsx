import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PersonnelCertNewPage } from "@/components/cert/personnel";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PersonnelCertNewPage />;
}
