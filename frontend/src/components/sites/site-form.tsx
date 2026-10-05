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
import { FormField, FormSection } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { SITE_SIDES } from "@/lib/enums";
import { applyServerErrors, ARABIC_SCRIPT, numberOrNull } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";

function inRange(min: number, max: number) {
  return (v: string) => v.trim() === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max);
}

export function SiteForm({ project, site }: { project: Schemas["ProjectRead"]; site?: Schemas["SiteRead"] }) {
  const t = useTranslations("site");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const sides = SITE_SIDES.filter((s) => project.is_airport || s === "landside" || s === "other");

  const schema = useMemo(
    () =>
      z.object({
        code: z.string().trim().regex(/^[A-Za-z0-9-]{1,12}$/, tv("siteCode")),
        name_en: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
        name_ar: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })).regex(ARABIC_SCRIPT, tv("arabicRequired")),
        site_side: z.enum(SITE_SIDES),
        gps_lat: z.string().refine(inRange(16, 33), tv("latitude")),
        gps_lng: z.string().refine(inRange(34, 56), tv("longitude")),
      }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: site?.code ?? "",
      name_en: site?.name_en ?? "",
      name_ar: site?.name_ar ?? "",
      site_side: site?.site_side ?? (project.is_airport ? "airside" : "other"),
      gps_lat: site?.gps_lat != null ? String(site.gps_lat) : "",
      gps_lng: site?.gps_lng != null ? String(site.gps_lng) : "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    setError(null);
    const body = { ...v, gps_lat: numberOrNull(v.gps_lat), gps_lng: numberOrNull(v.gps_lng) };
    try {
      const saved = site
        ? await unwrap(api.PATCH("/api/v1/sites/{site_id}", { params: { path: { site_id: site.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/sites", { params: { path: { project_id: project.id } }, body }));
      qc.setQueryData(keys.site(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["sites", project.id] });
      toast.success(site ? tc("saved") : tc("created"));
      router.push(`/projects/${project.id}/sites/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="site-form">
      <FormSection title={site ? t("editTitle") : t("createTitle")}>
        <FormField id="code" label={t("fields.code")} error={errors.code?.message} required>
          <Input className="ltr" {...form.register("code")} />
        </FormField>
        <FormField id="site_side" label={t("fields.site_side")} error={errors.site_side?.message} required>
          <Select {...form.register("site_side")}>
            {sides.map((s) => (
              <option key={s} value={s}>
                {t(`side.${s}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="name_en" label={t("fields.name_en")} error={errors.name_en?.message} required>
          <Input dir="ltr" {...form.register("name_en")} />
        </FormField>
        <FormField id="name_ar" label={t("fields.name_ar")} error={errors.name_ar?.message} required>
          <Input dir="rtl" lang="ar" {...form.register("name_ar")} />
        </FormField>
        <FormField id="gps_lat" label={t("fields.gps_lat")} error={errors.gps_lat?.message} hint={t("gpsHint")}>
          <Input inputMode="decimal" className="ltr" {...form.register("gps_lat")} />
        </FormField>
        <FormField id="gps_lng" label={t("fields.gps_lng")} error={errors.gps_lng?.message}>
          <Input inputMode="decimal" className="ltr" {...form.register("gps_lng")} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={site ? `/projects/${project.id}/sites/${site.id}` : `/projects/${project.id}/sites`}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
