"use client";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { MutationError } from "@/components/common/states";
import { newPasswordSchema } from "@/components/auth/password-fields";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";

export function ForgotPassword() {
  const t = useTranslations("auth.forgot");
  const tl = useTranslations("auth.login");
  const tv = useTranslations("validation");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const schema = useMemo(() => z.object({ email: z.string().trim().min(1, tv("required")).email(tv("email")) }), [tv]);
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  async function onSubmit(v: Values) {
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/auth/password-reset", { body: v }));
      setSent(true);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="text-xl">{t("title")}</span>
        </CardTitle>
        <CardDescription>{t("subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {sent ? (
          <Alert tone="success">{t("sent")}</Alert>
        ) : (
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            <FormField id="email" label={tl("email")} error={form.formState.errors.email?.message} required>
              <Input type="email" autoComplete="username" className="ltr" {...form.register("email")} />
            </FormField>
            <MutationError error={error} />
            <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
              {t("submit")}
            </Button>
          </form>
        )}
        <Link href="/login" className="text-center text-sm text-primary hover:underline">
          {t("backToLogin")}
        </Link>
      </CardContent>
    </Card>
  );
}

export function ResetPassword() {
  const t = useTranslations("auth.reset");
  const ti = useTranslations("auth.invite");
  const ta = useTranslations("auth");
  const tv = useTranslations("validation");
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const schema = useMemo(() => newPasswordSchema(tv), [tv]);
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/auth/password-reset/confirm", { body: { token, new_password: v.password } }));
      router.replace({ pathname: "/login", query: { reason: "password-reset" } });
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="text-xl">{t("title")}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {token.length < 16 ? (
          <Alert tone="danger">{t("missingToken")}</Alert>
        ) : (
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            <FormField id="password" label={ti("password")} error={errors.password?.message} hint={ta("passwordPolicy")} required>
              <Input type="password" autoComplete="new-password" {...form.register("password")} />
            </FormField>
            <FormField id="confirm" label={ti("confirmPassword")} error={errors.confirm?.message} required>
              <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
            </FormField>
            <MutationError error={error} />
            <Button type="submit" size="lg" disabled={isSubmitting}>
              {t("submit")}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
