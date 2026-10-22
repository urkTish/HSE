import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MfaSetupPage } from "@/components/auth/mfa";

export default async function MfaSetupRoute({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MfaSetupPage />;
}
