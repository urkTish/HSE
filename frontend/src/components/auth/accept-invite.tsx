"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { LoadingState, MutationError } from "@/components/common/states";
import { PrivacyText } from "@/components/auth/privacy-text";
import { newPasswordSchema } from "@/components/auth/password-fields";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/datetime";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { useLocale } from "next-intl";

export function AcceptInvite() {
  const t = useTranslations("auth.invite");
  const tp = useTranslations("auth.privacy");
  const tv = useTranslations("validation");
  const ta = useTranslations("auth");
  const locale = useLocale() === "ar" ? "ar" : "en";
  const msg = useErrorMessage();
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);

  const info = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => unwrap(api.POST("/api/v1/auth/invitations/validate", { body: { token } })),
    enabled: token.length >= 16,
    retry: false,
  });

  const schema = useMemo(
    () => newPasswordSchema(tv).and(z.object({ ack: z.boolean().refine((v) => v, tp("mustAck")) })),
    [tv, tp],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "", ack: false } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    if (!info.data) return;
    setError(null);
    try {
      const res = await unwrap(
        api.POST("/api/v1/auth/invitations/accept", {
          body: { token, password: v.password, privacy_notice_version: info.data.privacy_notice.version, preferred_language: locale },
        }),
      );
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "invitation" });
      qc.setQueryData(keys.me, res.user);
      router.replace("/", { locale: res.user.display_language });
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
        {info.data ? (
          <CardDescription>{t("welcome", { name: info.data.full_name_en, email: info.data.email })}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent>
        {token.length < 16 ? (
          <Alert tone="danger">{t("missingToken")}</Alert>
        ) : info.isLoading ? (
          <LoadingState rows={2} />
        ) : info.isError ? (
          <Alert tone="danger" data-testid="invite-error">
            {msg(info.error)}
          </Alert>
        ) : info.data ? (
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              {t("expiresAt", {
                date: formatDateTime(info.data.expires_at, {
                  locale,
                  timeZone: "Asia/Riyadh",
                  showHijri: false,
                  digits: "western",
                  dateFormatEn: "DD MMM YYYY",
                }),
              })}
            </p>
            <FormField id="password" label={t("password")} error={errors.password?.message} hint={ta("passwordPolicy")} required>
              <Input type="password" autoComplete="new-password" {...form.register("password")} />
            </FormField>
            <FormField id="confirm" label={t("confirmPassword")} error={errors.confirm?.message} required>
              <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
            </FormField>
            <PrivacyText notice={info.data.privacy_notice} />
            <CheckboxField id="ack" label={tp("acknowledge")} error={errors.ack?.message}>
              <Checkbox {...form.register("ack")} />
            </CheckboxField>
            <MutationError error={error} />
            <Button type="submit" size="lg" disabled={isSubmitting}>
              {isSubmitting ? t("submitting") : t("submit")}
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
