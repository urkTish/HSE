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
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { AIRSIDE_AREAS, MOVEMENT_AREAS, ZONE_TYPES } from "@/lib/enums";
import { applyServerErrors, ARABIC_SCRIPT, emptyToNull, numberOrNull } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";

/** Zone types allowed by rule 18 and the site side (spec §3.3). */
export function allowedZoneTypes(project: Schemas["ProjectRead"], site: Schemas["SiteRead"]): Schemas["ZoneType"][] {
  if (!project.is_airport) return ["other"];
  if (site.site_side === "airside") return ["airside"];
  if (site.site_side === "landside") return ["landside", "other"];
  return [...ZONE_TYPES];
}

const numberIn = (min: number, max: number) => (v: string) =>
  v.trim() === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max);

export function ZoneForm({
  project,
  site,
  zone,
}: {
  project: Schemas["ProjectRead"];
  site: Schemas["SiteRead"];
  zone?: Schemas["ZoneRead"];
}) {
  const t = useTranslations("zone");
  const ta = useTranslations("zone.airside");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const types = allowedZoneTypes(project, site);
  const typeOptions = zone && !types.includes(zone.zone_type) ? [zone.zone_type, ...types] : types;

  const schema = useMemo(
    () =>
      z
        .object({
          code: z.string().trim().regex(/^[A-Za-z0-9-]{1,16}$/, tv("zoneCode")),
          name_en: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          name_ar: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })).regex(ARABIC_SCRIPT, tv("arabicRequired")),
          zone_type: z.enum(ZONE_TYPES),
          airside: z.object({
            airside_area: z.union([z.enum(AIRSIDE_AREAS), z.literal("")]),
            in_movement_area: z.boolean(),
            runway_ref: z.string().trim(),
            security_restricted_area: z.boolean(),
            notam_required_for_works: z.boolean(),
            ols_height_limit_m_amsl: z.string(),
            max_equipment_height_m_agl: z.string(),
            escort_required: z.boolean(),
            adp_required: z.boolean(),
            fod_control_required: z.boolean(),
            works_safety_plan_ref: z.string().trim().max(40, tv("maxLength", { max: 40 })),
          }),
        })
        .superRefine((v, ctx) => {
          if (v.zone_type !== "airside") return;
          const a = v.airside;
          if (!a.airside_area) ctx.addIssue({ code: "custom", path: ["airside", "airside_area"], message: tv("required") });
          if (a.airside_area && MOVEMENT_AREAS.includes(a.airside_area) && !a.in_movement_area) {
            ctx.addIssue({ code: "custom", path: ["airside", "in_movement_area"], message: tv("movementArea") });
          }
          if (a.runway_ref && !/^\d{2}[LRC]?\/\d{2}[LRC]?$/.test(a.runway_ref)) {
            ctx.addIssue({ code: "custom", path: ["airside", "runway_ref"], message: tv("runwayRef") });
          }
          if (!numberIn(0, 3000)(a.ols_height_limit_m_amsl)) {
            ctx.addIssue({ code: "custom", path: ["airside", "ols_height_limit_m_amsl"], message: tv("range", { min: 0, max: 3000 }) });
          }
          if (!numberIn(0, 300)(a.max_equipment_height_m_agl)) {
            ctx.addIssue({ code: "custom", path: ["airside", "max_equipment_height_m_agl"], message: tv("range", { min: 0, max: 300 }) });
          }
        }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const a = zone?.airside;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: zone?.code ?? "",
      name_en: zone?.name_en ?? "",
      name_ar: zone?.name_ar ?? "",
      zone_type: zone?.zone_type ?? types[0] ?? "other",
      airside: {
        airside_area: a?.airside_area ?? "",
        in_movement_area: a?.in_movement_area ?? false,
        runway_ref: a?.runway_ref ?? "",
        security_restricted_area: a?.security_restricted_area ?? true,
        notam_required_for_works: a?.notam_required_for_works ?? false,
        ols_height_limit_m_amsl: a?.ols_height_limit_m_amsl != null ? String(a.ols_height_limit_m_amsl) : "",
        max_equipment_height_m_agl: a?.max_equipment_height_m_agl != null ? String(a.max_equipment_height_m_agl) : "",
        escort_required: a?.escort_required ?? false,
        adp_required: a?.adp_required ?? false,
        fod_control_required: a?.fod_control_required ?? true,
        works_safety_plan_ref: a?.works_safety_plan_ref ?? "",
      },
    },
  });
  const { errors, isSubmitting } = form.formState;
  const isAirside = useWatch({ control: form.control, name: "zone_type" }) === "airside";
  const ae = errors.airside;

  async function onSubmit(v: Values) {
    setError(null);
    const airside: Schemas["AirsideAttributesInput"] | null =
      v.zone_type === "airside" && v.airside.airside_area
        ? {
            airside_area: v.airside.airside_area,
            in_movement_area: v.airside.in_movement_area,
            runway_ref: emptyToNull(v.airside.runway_ref),
            security_restricted_area: v.airside.security_restricted_area,
            notam_required_for_works: v.airside.notam_required_for_works,
            ols_height_limit_m_amsl: numberOrNull(v.airside.ols_height_limit_m_amsl),
            max_equipment_height_m_agl: numberOrNull(v.airside.max_equipment_height_m_agl),
            escort_required: v.airside.escort_required,
            adp_required: v.airside.adp_required,
            fod_control_required: v.airside.fod_control_required,
            works_safety_plan_ref: emptyToNull(v.airside.works_safety_plan_ref),
          }
        : null;
    const body = { code: v.code, name_en: v.name_en, name_ar: v.name_ar, zone_type: v.zone_type, airside };
    try {
      const saved = zone
        ? await unwrap(api.PATCH("/api/v1/zones/{zone_id}", { params: { path: { zone_id: zone.id } }, body }))
        : await unwrap(api.POST("/api/v1/sites/{site_id}/zones", { params: { path: { site_id: site.id } }, body }));
      qc.setQueryData(keys.zone(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["zones", project.id] });
      await qc.invalidateQueries({ queryKey: ["history"] });
      toast.success(zone ? tc("saved") : tc("created"));
      router.push(`/projects/${project.id}/zones/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  const check = (key: "in_movement_area" | "security_restricted_area" | "notam_required_for_works" | "escort_required" | "adp_required" | "fod_control_required") => (
    <CheckboxField id={`airside-${key}`} label={ta(key)} error={ae?.[key]?.message}>
      <Checkbox {...form.register(`airside.${key}`)} />
    </CheckboxField>
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="zone-form">
      <FormSection title={zone ? t("editTitle") : t("createTitle")} description={`${t("fields.site")}: ${site.code}`}>
        <FormField id="code" label={t("fields.code")} error={errors.code?.message} required>
          <Input className="ltr" {...form.register("code")} />
        </FormField>
        <FormField
          id="zone_type"
          label={t("fields.zone_type")}
          error={errors.zone_type?.message}
          hint={!project.is_airport ? t("typeHintNonAirport") : undefined}
          required
        >
          <Select {...form.register("zone_type")}>
            {typeOptions.map((x) => (
              <option key={x} value={x}>
                {t(`type.${x}`)}
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
      </FormSection>
      {isAirside ? (
        <FormSection title={ta("title")} description={ta("subtitle")}>
          <FormField id="airside-area" label={ta("airside_area")} error={ae?.airside_area?.message} required>
            <Select
              {...form.register("airside.airside_area", {
                onChange: (e: { target: { value: string } }) => {
                  const v = e.target.value as Schemas["AirsideArea"];
                  if (MOVEMENT_AREAS.includes(v)) {
                    form.setValue("airside.in_movement_area", true);
                    form.setValue("airside.notam_required_for_works", true);
                  }
                },
              })}
            >
              <option value="">{tc("select")}</option>
              {AIRSIDE_AREAS.map((x) => (
                <option key={x} value={x}>
                  {t(`area.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="airside-runway_ref" label={ta("runway_ref")} error={ae?.runway_ref?.message} hint={ta("runwayRefHint")}>
            <Input className="ltr" {...form.register("airside.runway_ref")} />
          </FormField>
          <FormField id="airside-ols" label={ta("ols_height_limit_m_amsl")} error={ae?.ols_height_limit_m_amsl?.message}>
            <Input inputMode="decimal" className="ltr" {...form.register("airside.ols_height_limit_m_amsl")} />
          </FormField>
          <FormField id="airside-maxh" label={ta("max_equipment_height_m_agl")} error={ae?.max_equipment_height_m_agl?.message}>
            <Input inputMode="decimal" className="ltr" {...form.register("airside.max_equipment_height_m_agl")} />
          </FormField>
          <FormField id="airside-wsp" label={ta("works_safety_plan_ref")} error={ae?.works_safety_plan_ref?.message}>
            <Input className="ltr" {...form.register("airside.works_safety_plan_ref")} />
          </FormField>
          <div className="grid gap-1 sm:col-span-2 sm:grid-cols-2">
            {check("in_movement_area")}
            {check("security_restricted_area")}
            {check("notam_required_for_works")}
            {check("escort_required")}
            {check("adp_required")}
            {check("fod_control_required")}
          </div>
        </FormSection>
      ) : null}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={zone ? `/projects/${project.id}/zones/${zone.id}` : `/projects/${project.id}/sites/${site.id}`}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
