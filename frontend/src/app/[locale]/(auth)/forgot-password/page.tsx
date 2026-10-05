import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ForgotPassword } from "@/components/auth/password-reset";

export default async function ForgotPasswordPage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ForgotPassword />;
}
