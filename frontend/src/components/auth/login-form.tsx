"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/common/form-field";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError, unwrap } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { useErrorMessage } from "@/lib/i18n-helpers";

export function LoginForm() {
  const t = useTranslations("auth.login");
  const tv = useTranslations("validation");
  const msg = useErrorMessage();
  const router = useRouter();
  const qc = useQueryClient();
  const params = useSearchParams();
  const reason = params.get("reason");
  const next = params.get("next");
  const [error, setError] = useState<unknown>(null);

  const schema = useMemo(
    () =>
      z.object({
        email: z.string().trim().min(1, tv("required")).email(tv("email")),
        password: z.string().min(1, tv("required")),
      }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const res = await unwrap(api.POST("/api/v1/auth/login", { body: values }));
      qc.clear();
      const locale = res.user.display_language;
      if (res.user.privacy_ack_required) {
        router.replace("/privacy", { locale });
        return;
      }
      qc.setQueryData(keys.me, res.user);
      const dest = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
      router.replace(dest, { locale });
    } catch (e) {
      setError(e);
      form.resetField("password");
    }
  }

  const locked = error instanceof ApiError && error.code === "ACCOUNT_LOCKED";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="text-xl">{t("title")}</span>
        </CardTitle>
        <CardDescription>{t("subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {reason === "expired" && !error ? <Alert tone="warning" data-testid="session-expired">{t("sessionExpired")}</Alert> : null}
          {reason === "signed-out" && !error ? <Alert tone="info">{t("signedOut")}</Alert> : null}
          {reason === "password-reset" && !error ? <Alert tone="success">{t("passwordReset")}</Alert> : null}
          {error ? (
            <Alert tone="danger" data-testid="login-error">
              {locked ? <p className="font-semibold">{t("lockedTitle")}</p> : null}
              <p>{msg(error)}</p>
            </Alert>
          ) : null}
          <FormField id="email" label={t("email")} error={errors.email?.message} required>
            <Input type="email" autoComplete="username" inputMode="email" className="ltr h-touch" {...form.register("email")} />
          </FormField>
          <FormField id="password" label={t("password")} error={errors.password?.message} required>
            <Input type="password" autoComplete="current-password" className="h-touch" {...form.register("password")} />
          </FormField>
          <Button type="submit" size="lg" disabled={isSubmitting}>
            {isSubmitting ? t("submitting") : t("submit")}
          </Button>
          <Link href="/forgot-password" className="inline-flex min-h-touch items-center justify-center text-sm font-medium text-primary underline-offset-4 hover:underline">
            {t("forgot")}
          </Link>
        </form>
      </CardContent>
    </Card>
  );
}
