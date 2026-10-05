"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { FormField, FormSection } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { AssignmentFields, assignmentSchema, emptyAssignment, toAssignmentCreate, type AssignmentValue } from "@/components/users/assignment-fields";
import { userProfileShape } from "@/components/users/user-fields";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useContractors } from "@/lib/api/queries";
import { EMPLOYER_TYPES } from "@/lib/enums";
import { applyServerErrors, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";

export function UserInvite() {
  const t = useTranslations("user");
  const ta = useTranslations("assignment");
  const tn = useTranslations("nav");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const locale = useLocale() === "ar" ? "ar" : "en";
  const fe = useFieldErrorTranslator();
  const name = useLocalizedName();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const contractors = useContractors({ page_size: 200, sort: "short_code" });

  const schema = useMemo(
    () =>
      z
        .object({
          email: z.string().trim().min(1, tv("required")).email(tv("email")),
          ...userProfileShape(tv),
          assignment: assignmentSchema(tv),
        })
        .superRefine((v, ctx) => {
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
      email: "",
      full_name_en: "",
      full_name_ar: "",
      mobile: "",
      employer_type: "client",
      employer_contractor_id: "",
      job_title: "",
      preferred_language: locale,
      assignment: emptyAssignment,
    },
  });
  const { errors, isSubmitting } = form.formState;
  const employerType = form.watch("employer_type");
  const assignment = form.watch("assignment") as AssignmentValue;

  async function onSubmit(v: Values) {
    setError(null);
    try {
      const user = await unwrap(
        api.POST("/api/v1/users", {
          body: {
            email: v.email,
            full_name_en: v.full_name_en,
            full_name_ar: emptyToNull(v.full_name_ar),
            mobile: emptyToNull(v.mobile),
            employer_type: v.employer_type,
            employer_contractor_id: v.employer_type === "contractor" ? emptyToNull(v.employer_contractor_id) : null,
            job_title: emptyToNull(v.job_title),
            preferred_language: v.preferred_language,
            role_assignments: [toAssignmentCreate(v.assignment as AssignmentValue)],
          },
        }),
      );
      await qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(t("inviteSent"));
      router.push(`/users/${user.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("users"), href: "/users" }, { label: t("inviteTitle") }]} />
      <PageHeader title={t("inviteTitle")} />
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="invite-form">
        <FormSection title={t("fields.name")}>
          <FormField id="email" label={t("fields.email")} error={errors.email?.message} required>
            <Input type="email" className="ltr" {...form.register("email")} />
          </FormField>
          <FormField id="mobile" label={t("fields.mobile")} error={errors.mobile?.message}>
            <Input type="tel" className="ltr" {...form.register("mobile")} />
          </FormField>
          <FormField id="full_name_en" label={t("fields.full_name_en")} error={errors.full_name_en?.message} required>
            <Input dir="ltr" {...form.register("full_name_en")} />
          </FormField>
          <FormField id="full_name_ar" label={t("fields.full_name_ar")} error={errors.full_name_ar?.message}>
            <Input dir="rtl" lang="ar" {...form.register("full_name_ar")} />
          </FormField>
          <FormField id="employer_type" label={t("fields.employer_type")} error={errors.employer_type?.message} required>
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
          <FormField id="job_title" label={t("fields.job_title")} error={errors.job_title?.message}>
            <Input {...form.register("job_title")} />
          </FormField>
          <FormField id="preferred_language" label={t("fields.preferred_language")}>
            <Select {...form.register("preferred_language")}>
              <option value="en">{tc("english")}</option>
              <option value="ar">{tc("arabic")}</option>
            </Select>
          </FormField>
        </FormSection>
        <fieldset className="rounded-lg border bg-surface p-5">
          <legend className="px-1 text-base font-semibold">{ta("assignTitle")}</legend>
          <AssignmentFields
            idPrefix="assignment"
            value={assignment}
            onChange={(v) => form.setValue("assignment", v, { shouldValidate: form.formState.isSubmitted })}
            errors={errors.assignment}
          />
        </fieldset>
        <MutationError error={error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={isSubmitting} data-testid="save">
            {isSubmitting ? tc("saving") : t("invite")}
          </Button>
          <Button variant="outline" asChild>
            <Link href="/users">{tc("cancel")}</Link>
          </Button>
        </div>
      </form>
    </div>
  );
}
