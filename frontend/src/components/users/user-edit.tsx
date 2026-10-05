"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { FormField, FormSection } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { userProfileShape } from "@/components/users/user-fields";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useContractors, useUser } from "@/lib/api/queries";
import { EMPLOYER_TYPES } from "@/lib/enums";
import { applyServerErrors, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";

export function UserEdit({ userId }: { userId: string }) {
  const q = useUser(userId);
  if (q.isError) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingState />;
  return <UserEditForm user={q.data} />;
}

function UserEditForm({ user }: { user: Schemas["UserRead"] }) {
  const t = useTranslations("user");
  const tn = useTranslations("nav");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const name = useLocalizedName();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const contractors = useContractors({ page_size: 200, sort: "short_code" });
  const schema = useMemo(
    () =>
      z.object(userProfileShape(tv)).superRefine((v, ctx) => {
        if (v.employer_type === "contractor" && !v.employer_contractor_id) {
          ctx.addIssue({ code: "custom", path: ["employer_contractor_id"], message: tv("employerContractor") });
        }
      }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name_en: user.full_name_en,
      full_name_ar: user.full_name_ar ?? "",
      mobile: user.mobile ?? "",
      employer_type: user.employer_type,
      employer_contractor_id: user.employer_contractor_id ?? "",
      job_title: user.job_title ?? "",
      preferred_language: user.preferred_language,
    },
  });
  const { errors, isSubmitting } = form.formState;
  const employerType = useWatch({ control: form.control, name: "employer_type" });

  async function onSubmit(v: Values) {
    setError(null);
    try {
      const saved = await unwrap(
        api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: {
            full_name_en: v.full_name_en,
            full_name_ar: emptyToNull(v.full_name_ar),
            mobile: emptyToNull(v.mobile),
            employer_type: v.employer_type,
            employer_contractor_id: v.employer_type === "contractor" ? emptyToNull(v.employer_contractor_id) : null,
            job_title: emptyToNull(v.job_title),
            preferred_language: v.preferred_language,
          },
        }),
      );
      qc.setQueryData(keys.user(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(tc("saved"));
      router.push(`/users/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: tn("users"), href: "/users" },
          { label: name(user.full_name_en, user.full_name_ar), href: `/users/${user.id}` },
          { label: t("editTitle") },
        ]}
      />
      <PageHeader title={t("editTitle")} />
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6">
        <FormSection title={t("fields.name")}>
          <FormField id="full_name_en" label={t("fields.full_name_en")} error={errors.full_name_en?.message} required>
            <Input dir="ltr" {...form.register("full_name_en")} />
          </FormField>
          <FormField id="full_name_ar" label={t("fields.full_name_ar")} error={errors.full_name_ar?.message}>
            <Input dir="rtl" lang="ar" {...form.register("full_name_ar")} />
          </FormField>
          <FormField id="mobile" label={t("fields.mobile")} error={errors.mobile?.message}>
            <Input type="tel" className="ltr" {...form.register("mobile")} />
          </FormField>
          <FormField id="job_title" label={t("fields.job_title")} error={errors.job_title?.message}>
            <Input {...form.register("job_title")} />
          </FormField>
          <FormField id="employer_type" label={t("fields.employer_type")} required>
            <Select {...form.register("employer_type")}>
              {EMPLOYER_TYPES.map((e) => (
                <option key={e} value={e}>
                  {t(`employerType.${e}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {employerType === "contractor" ? (
            <FormField id="employer_contractor_id" label={t("fields.employer_contractor")} error={errors.employer_contractor_id?.message} required>
              <Select {...form.register("employer_contractor_id")}>
                <option value="">{tc("select")}</option>
                {(contractors.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.short_code} — {name(c.legal_name_en, c.legal_name_ar)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          <FormField id="preferred_language" label={t("fields.preferred_language")}>
            <Select {...form.register("preferred_language")}>
              <option value="en">{tc("english")}</option>
              <option value="ar">{tc("arabic")}</option>
            </Select>
          </FormField>
        </FormSection>
        <MutationError error={error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={isSubmitting} data-testid="save">
            {isSubmitting ? tc("saving") : tc("save")}
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/users/${user.id}`}>{tc("cancel")}</Link>
          </Button>
        </div>
      </form>
    </div>
  );
}
