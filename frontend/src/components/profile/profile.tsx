"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, FormSection } from "@/components/common/form-field";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { PageHeader } from "@/components/common/page-header";
import { MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { AccessSummary } from "@/components/users/access-summary";
import { usePathname, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { applyServerErrors, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";
import { meetsPasswordPolicy } from "@/lib/password";
import { useLocale } from "next-intl";

export function Profile() {
  const t = useTranslations("profile");
  const tu = useTranslations("user");
  const ta = useTranslations("auth");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const fe = useFieldErrorTranslator();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [error, setError] = useState<unknown>(null);
  const [pwError, setPwError] = useState<unknown>(null);

  const schema = useMemo(
    () =>
      z.object({
        full_name_en: z.string().trim().min(1, tv("required")).max(120, tv("maxLength", { max: 120 })),
        full_name_ar: z.string().trim().max(120, tv("maxLength", { max: 120 })),
        mobile: z.string().trim().refine((v) => v === "" || /^\+[1-9]\d{7,14}$/.test(v), tv("mobile")),
        preferred_language: z.enum(["en", "ar"]),
      }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name_en: me.full_name_en, full_name_ar: me.full_name_ar ?? "", mobile: me.mobile ?? "", preferred_language: me.preferred_language },
  });

  const pwSchema = useMemo(
    () =>
      z
        .object({
          current: z.string().min(1, tv("required")),
          password: z.string().min(1, tv("required")).refine(meetsPasswordPolicy, tv("passwordPolicy")),
          confirm: z.string().min(1, tv("required")),
        })
        .refine((v) => v.password === v.confirm, { path: ["confirm"], message: tv("passwordMismatch") }),
    [tv],
  );
  type PwValues = z.infer<typeof pwSchema>;
  const pwForm = useForm<PwValues>({ resolver: zodResolver(pwSchema), defaultValues: { current: "", password: "", confirm: "" } });

  async function onSubmit(v: Values) {
    setError(null);
    try {
      const res = await unwrap(
        api.PATCH("/api/v1/auth/me", {
          body: { full_name_en: v.full_name_en, full_name_ar: emptyToNull(v.full_name_ar), mobile: emptyToNull(v.mobile), preferred_language: v.preferred_language },
        }),
      );
      qc.setQueryData(keys.me, res);
      form.reset(v);
      toast.success(t("updated"));
      if (res.display_language !== locale) router.replace(pathname, { locale: res.display_language });
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  async function onPassword(v: PwValues) {
    setPwError(null);
    try {
      await unwrap(api.POST("/api/v1/auth/me/password", { body: { current_password: v.current, new_password: v.password } }));
      pwForm.reset();
      toast.success(t("passwordChanged"));
    } catch (e) {
      setPwError(e);
    }
  }

  const e = form.formState.errors;
  const pe = pwForm.formState.errors;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4" data-testid="profile-form">
            <FormSection title={t("personal")}>
              <FieldItem label={tu("fields.email")} ltr>{me.email}</FieldItem>
              <FieldItem label={tu("fields.employer_type")}>{tu(`employerType.${me.employer_type}`)}</FieldItem>
              <FormField id="full_name_en" label={tu("fields.full_name_en")} error={e.full_name_en?.message} required>
                <Input dir="ltr" {...form.register("full_name_en")} />
              </FormField>
              <FormField id="full_name_ar" label={tu("fields.full_name_ar")} error={e.full_name_ar?.message}>
                <Input dir="rtl" lang="ar" {...form.register("full_name_ar")} />
              </FormField>
              <FormField id="mobile" label={tu("fields.mobile")} error={e.mobile?.message}>
                <Input type="tel" className="ltr" {...form.register("mobile")} />
              </FormField>
              <FormField id="preferred_language" label={tu("fields.preferred_language")}>
                <Select {...form.register("preferred_language")}>
                  <option value="en">{tc("english")}</option>
                  <option value="ar">{tc("arabic")}</option>
                </Select>
              </FormField>
            </FormSection>
            <MutationError error={error} />
            <div>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {tc("save")}
              </Button>
            </div>
          </form>
          <form onSubmit={pwForm.handleSubmit(onPassword)} noValidate className="flex flex-col gap-4" data-testid="password-form">
            <FormSection title={t("password")} description={ta("passwordPolicy")}>
              <FormField id="current" label={t("currentPassword")} error={pe.current?.message} required className="sm:col-span-2">
                <Input type="password" autoComplete="current-password" {...pwForm.register("current")} />
              </FormField>
              <FormField id="new-password" label={t("newPassword")} error={pe.password?.message} required>
                <Input type="password" autoComplete="new-password" {...pwForm.register("password")} />
              </FormField>
              <FormField id="confirm-password" label={t("confirmPassword")} error={pe.confirm?.message} required>
                <Input type="password" autoComplete="new-password" {...pwForm.register("confirm")} />
              </FormField>
            </FormSection>
            <MutationError error={pwError} />
            <div>
              <Button type="submit" disabled={pwForm.formState.isSubmitting}>
                {t("password")}
              </Button>
            </div>
          </form>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{t("access")}</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList className="mb-4 sm:grid-cols-1 lg:grid-cols-1">
              <FieldItem label={tu("fields.status")}>{tu(`status.${me.status}`)}</FieldItem>
            </FieldList>
            <AccessSummary me={me} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
