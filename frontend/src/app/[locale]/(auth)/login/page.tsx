import { Suspense } from "react";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { LoginForm } from "@/components/auth/login-form";

export default async function LoginPage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
