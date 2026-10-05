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
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { FormField, FormSection } from "@/components/common/form-field";
import { FieldItem } from "@/components/common/field-list";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useContractors, useEngagements, useSites } from "@/lib/api/queries";
import { applyServerErrors, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";

export function EngagementForm({ projectId, engagement }: { projectId: string; engagement?: Schemas["EngagementRead"] }) {
  const t = useTranslations("engagement");
  const tcs = useTranslations("contractor.status");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const name = useLocalizedName();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const editing = Boolean(engagement);
  const contractors = useContractors({ page_size: 200, sort: "short_code" }, !editing);
  const engagements = useEngagements(projectId, { page_size: 200 });
  const sites = useSites(projectId, { page_size: 100, sort: "code" });

  const schema = useMemo(
    () =>
      z
        .object({
          contractor_id: z.string(),
          tier: z.enum(["1", "2", "3"]),
          parent_engagement_id: z.string(),
          scope_of_work_en: z.string().trim().min(1, tv("required")).max(500, tv("maxLength", { max: 500 })),
          scope_of_work_ar: z.string().trim().min(1, tv("required")).max(500, tv("maxLength", { max: 500 })),
          site_ids: z.array(z.string()).min(1, tv("atLeastOneSite")),
          mobilisation_date: z.string().min(1, tv("required")),
          demobilisation_date: z.string(),
        })
        .superRefine((v, ctx) => {
          if (!editing && !v.contractor_id) ctx.addIssue({ code: "custom", path: ["contractor_id"], message: tv("required") });
          if (!editing && v.tier !== "1" && !v.parent_engagement_id) {
            ctx.addIssue({ code: "custom", path: ["parent_engagement_id"], message: tv("parentRequired") });
          }
          if (v.demobilisation_date && v.demobilisation_date < v.mobilisation_date) {
            ctx.addIssue({ code: "custom", path: ["demobilisation_date"], message: tv("endBeforeStart") });
          }
        }),
    [tv, editing],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      contractor_id: engagement?.contractor_id ?? "",
      tier: engagement ? (String(engagement.tier) as "1" | "2" | "3") : "1",
      parent_engagement_id: engagement?.parent_engagement_id ?? "",
      scope_of_work_en: engagement?.scope_of_work_en ?? "",
      scope_of_work_ar: engagement?.scope_of_work_ar ?? "",
      site_ids: engagement?.site_ids ?? [],
      mobilisation_date: engagement?.mobilisation_date ?? "",
      demobilisation_date: engagement?.demobilisation_date ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const tier = Number(form.watch("tier"));
  const parentOptions = (engagements.data?.items ?? []).filter((e) => e.tier === tier - 1 && e.id !== engagement?.id);
  const parent = engagement?.parent_engagement_id
    ? engagements.data?.items.find((e) => e.id === engagement.parent_engagement_id)
    : undefined;

  async function onSubmit(v: Values) {
    setError(null);
    try {
      let saved: Schemas["EngagementRead"];
      if (engagement) {
        saved = await unwrap(
          api.PATCH("/api/v1/engagements/{engagement_id}", {
            params: { path: { engagement_id: engagement.id } },
            body: {
              scope_of_work_en: v.scope_of_work_en,
              scope_of_work_ar: v.scope_of_work_ar,
              site_ids: v.site_ids,
              mobilisation_date: v.mobilisation_date,
              demobilisation_date: emptyToNull(v.demobilisation_date),
            },
          }),
        );
      } else {
        saved = await unwrap(
          api.POST("/api/v1/projects/{project_id}/engagements", {
            params: { path: { project_id: projectId } },
            body: {
              contractor_id: v.contractor_id,
              tier: Number(v.tier),
              parent_engagement_id: v.tier === "1" ? null : emptyToNull(v.parent_engagement_id),
              scope_of_work_en: v.scope_of_work_en,
              scope_of_work_ar: v.scope_of_work_ar,
              site_ids: v.site_ids,
              mobilisation_date: v.mobilisation_date,
              demobilisation_date: emptyToNull(v.demobilisation_date),
            },
          }),
        );
      }
      qc.setQueryData(keys.engagement(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["engagements", projectId] });
      toast.success(engagement ? tc("saved") : tc("created"));
      router.push(`/projects/${projectId}/engagements/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="engagement-form">
      <FormSection title={engagement ? t("editTitle") : t("createTitle")}>
        {engagement ? (
          <>
            <FieldItem label={t("fields.contractor")}>
              <span className="ltr">{engagement.contractor.short_code}</span> — {name(engagement.contractor.legal_name_en, engagement.contractor.legal_name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.tier")}>{t(`tier.${String(engagement.tier) as "1" | "2" | "3"}`)}</FieldItem>
            <FieldItem label={t("fields.parent")} ltr>{parent?.contractor.short_code ?? t("noParent")}</FieldItem>
          </>
        ) : (
          <>
            <FormField id="contractor_id" label={t("fields.contractor")} error={errors.contractor_id?.message} required className="sm:col-span-2">
              <Select {...form.register("contractor_id")}>
                <option value="">{tc("select")}</option>
                {(contractors.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.short_code} — {name(c.legal_name_en, c.legal_name_ar)} ({tcs(c.status)})
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="tier" label={t("fields.tier")} error={errors.tier?.message} required>
              <Select {...form.register("tier", { onChange: () => form.setValue("parent_engagement_id", "") })}>
                {(["1", "2", "3"] as const).map((x) => (
                  <option key={x} value={x}>
                    {t(`tier.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="parent_engagement_id" label={t("fields.parent")} error={errors.parent_engagement_id?.message} hint={t("parentHint")} required={tier > 1}>
              <Select disabled={tier === 1} {...form.register("parent_engagement_id")}>
                <option value="">{tier === 1 ? t("noParent") : tc("select")}</option>
                {tier > 1
                  ? parentOptions.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.contractor.short_code} — {t("tierShort", { tier: e.tier })}
                      </option>
                    ))
                  : null}
              </Select>
            </FormField>
          </>
        )}
        <FormField id="scope_of_work_en" label={t("fields.scope_of_work_en")} error={errors.scope_of_work_en?.message} hint={tc("pdplHint")} required>
          <Textarea dir="ltr" maxLength={500} {...form.register("scope_of_work_en")} />
        </FormField>
        <FormField id="scope_of_work_ar" label={t("fields.scope_of_work_ar")} error={errors.scope_of_work_ar?.message} required>
          <Textarea dir="rtl" lang="ar" maxLength={500} {...form.register("scope_of_work_ar")} />
        </FormField>
        <FormField id="mobilisation_date" label={t("fields.mobilisation_date")} error={errors.mobilisation_date?.message} required>
          <Input type="date" {...form.register("mobilisation_date")} />
        </FormField>
        <FormField id="demobilisation_date" label={t("fields.demobilisation_date")} error={errors.demobilisation_date?.message}>
          <Input type="date" {...form.register("demobilisation_date")} />
        </FormField>
        <fieldset className="sm:col-span-2" aria-describedby={errors.site_ids ? "site_ids-error" : undefined}>
          <legend className="mb-2 text-sm font-medium">
            {t("fields.sites")} <span className="text-destructive" aria-hidden>*</span>
          </legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {(sites.data?.items ?? []).map((s) => (
              <label key={s.id} className="flex min-h-touch items-center gap-3 text-sm">
                <Checkbox value={s.id} {...form.register("site_ids")} />
                <span>
                  <span className="ltr">{s.code}</span> — {name(s.name_en, s.name_ar)}
                </span>
              </label>
            ))}
          </div>
          {errors.site_ids ? (
            <p id="site_ids-error" role="alert" className="text-xs font-medium text-destructive">
              {errors.site_ids.message}
            </p>
          ) : null}
        </fieldset>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={engagement ? `/projects/${projectId}/engagements/${engagement.id}` : `/projects/${projectId}/engagements`}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
