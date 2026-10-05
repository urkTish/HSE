import { Suspense } from "react";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ResetPassword } from "@/components/auth/password-reset";

export default async function ResetPasswordPage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return (
    <Suspense>
      <ResetPassword />
    </Suspense>
  );
}
