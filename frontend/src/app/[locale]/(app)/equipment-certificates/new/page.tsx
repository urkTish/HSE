import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { EqCertNewPage } from "@/components/cert/eq-certs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <EqCertNewPage />;
}
