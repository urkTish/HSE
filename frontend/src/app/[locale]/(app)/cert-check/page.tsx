import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CertCheckPage } from "@/components/cert/check";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CertCheckPage />;
}
