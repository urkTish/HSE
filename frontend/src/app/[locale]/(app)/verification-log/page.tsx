import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { VerificationLogPage } from "@/components/cert/eq-certs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <VerificationLogPage />;
}
