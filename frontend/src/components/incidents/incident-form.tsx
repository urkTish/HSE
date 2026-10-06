"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { useProjectOptions } from "@/components/common/pickers";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk } from "@/lib/api/hse";
import { useProjectSettings } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { AIRSIDE_FLAGS, ASSET_TYPES, DO_CATEGORIES, ENV_CATEGORIES, ENV_REACHED, INCIDENT_SHIFTS, INCIDENT_TYPES, NOT_WORK_RELATED_REASONS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";
import { useLocalDraft, useOnline } from "@/lib/local-draft";
import { useRefLists } from "@/lib/reference";

type IncType = Schemas["IncidentType"];
type Flag = Schemas["AirsideFlag"];
const DEC = /^\d+(\.\d{1,2})?$/;

export function IncidentForm({ project, incident }: { project: Schemas["ProjectRead"]; incident?: Schemas["IncidentRead"] }) {
  const t = useTranslations("incidents");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const online = useOnline();
  const opts = useProjectOptions(project.id);
  const ref = useRefLists();
  const settings = useProjectSettings(project.id);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const [error, setError] = useState<unknown>(null);

  const schema = useMemo(
    () =>
      z
        .object({
          site_id: z.string().min(1, tv("required")),
          zone_id: z.string(),
          location_detail: z.string().max(200, tv("maxLength", { max: 200 })),
          responsible_engagement_id: z.string(),
          occurred_at: z.string().min(1, tv("required")),
          shift: z.string(),
          incident_types: z.array(z.enum(INCIDENT_TYPES)).min(1, tv("required")),
          primary_type: z.string().min(1, tv("required")),
          title: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          description: z.string().max(4000, tv("maxLength", { max: 4000 })),
          immediate_actions: z.string().max(2000, tv("maxLength", { max: 2000 })),
          activity: z.string(),
          work_related: z.boolean(),
          not_work_related_reason: z.string(),
          work_related_rationale: z.string().max(500, tv("maxLength", { max: 500 })),
          actual_severity: z.string(),
          potential_severity: z.string(),
          ambient_temp_c: z.string().refine((v) => v === "" || (/^\d{1,2}(\.\d)?$/.test(v) && Number(v) <= 60), tv("number")),
          airside_flags: z.array(z.enum(AIRSIDE_FLAGS)),
          pd_asset_type: z.string(),
          pd_cost: z.string(),
          env_category: z.string(),
          env_substance: z.string(),
          env_quantity: z.string(),
          env_contained: z.boolean(),
          env_reached: z.string(),
          do_category: z.string(),
        })
        .superRefine((v, ctx) => {
          if (v.incident_types.includes("near_miss") && v.incident_types.length > 1) ctx.addIssue({ code: "custom", path: ["incident_types"], message: t("nearMissExclusive") });
          if (v.primary_type && !v.incident_types.includes(v.primary_type as IncType)) ctx.addIssue({ code: "custom", path: ["primary_type"], message: t("primaryMustBeSelected") });
          if (!v.work_related && !v.not_work_related_reason) ctx.addIssue({ code: "custom", path: ["not_work_related_reason"], message: tv("required") });
          if (v.actual_severity && v.potential_severity && Number(v.potential_severity) < Number(v.actual_severity))
            ctx.addIssue({ code: "custom", path: ["potential_severity"], message: t("potentialBelowActual") });
          if (v.incident_types.includes("property_damage")) {
            if (!v.pd_asset_type) ctx.addIssue({ code: "custom", path: ["pd_asset_type"], message: tv("required") });
            if (!DEC.test(v.pd_cost)) ctx.addIssue({ code: "custom", path: ["pd_cost"], message: tv("number") });
          }
          if (v.incident_types.includes("environmental")) {
            if (!v.env_category) ctx.addIssue({ code: "custom", path: ["env_category"], message: tv("required") });
            if (!v.env_reached) ctx.addIssue({ code: "custom", path: ["env_reached"], message: tv("required") });
            if (v.env_quantity && !DEC.test(v.env_quantity)) ctx.addIssue({ code: "custom", path: ["env_quantity"], message: tv("number") });
          }
          if (v.incident_types.includes("dangerous_occurrence") && !v.do_category) ctx.addIssue({ code: "custom", path: ["do_category"], message: tv("required") });
        }),
    [tv, t],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      site_id: incident?.site.id ?? "",
      zone_id: incident?.zone?.id ?? "",
      location_detail: incident?.location_detail ?? "",
      responsible_engagement_id: incident?.responsible_engagement?.id ?? "",
      occurred_at: incident ? utcToZonedInput(incident.occurred_at, tz) : "",
      shift: incident?.shift ?? "day",
      incident_types: incident?.incident_types ?? [],
      primary_type: incident?.primary_type ?? "",
      title: incident?.title ?? "",
      description: incident?.description ?? "",
      immediate_actions: incident?.immediate_actions ?? "",
      activity: incident?.activity ?? "",
      work_related: incident?.work_related ?? true,
      not_work_related_reason: incident?.not_work_related_reason ?? "",
      work_related_rationale: incident?.work_related_rationale ?? "",
      actual_severity: incident?.actual_severity ? String(incident.actual_severity) : "",
      potential_severity: incident?.potential_severity ? String(incident.potential_severity) : "",
      ambient_temp_c: incident?.ambient_temp_c ?? "",
      airside_flags: incident?.airside_flags ?? [],
      pd_asset_type: incident?.property_damage?.asset_type ?? "",
      pd_cost: incident?.property_damage?.estimated_cost_sar ?? "",
      env_category: incident?.environmental?.category ?? "",
      env_substance: incident?.environmental?.substance ?? "",
      env_quantity: incident?.environmental?.quantity_l ?? "",
      env_contained: incident?.environmental?.contained ?? false,
      env_reached: incident?.environmental?.reached ?? "",
      do_category: incident?.dangerous_occurrence?.category ?? "",
    },
  });
  const draft = useLocalDraft(`incident.${project.id}`, form, !incident);
  const { errors, isSubmitting } = form.formState;
  const siteId = useWatch({ control: form.control, name: "site_id" });
  const zoneId = useWatch({ control: form.control, name: "zone_id" });
  const types = useWatch({ control: form.control, name: "incident_types" });
  const workRelated = useWatch({ control: form.control, name: "work_related" });
  const textForHint = `${useWatch({ control: form.control, name: "title" })} ${useWatch({ control: form.control, name: "description" })} ${useWatch({ control: form.control, name: "immediate_actions" })}`;
  const zones = opts.zones.filter((z) => z.siteId === siteId);
  const engagements = opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId));
  const airside = opts.zoneById.get(zoneId)?.zone_type === "airside";
  const sev = ref.options("severity");

  async function save(v: Values, report: boolean) {
    setError(null);
    const has = (x: IncType) => v.incident_types.includes(x);
    const body = {
      site_id: v.site_id,
      zone_id: v.zone_id || null,
      location_detail: v.location_detail.trim() || null,
      responsible_engagement_id: v.responsible_engagement_id || null,
      occurred_at: zonedInputToUtc(v.occurred_at, tz),
      shift: (v.shift || null) as Schemas["IncidentShift"] | null,
      incident_types: v.incident_types,
      primary_type: v.primary_type as IncType,
      title: v.title.trim(),
      description: v.description.trim() || null,
      immediate_actions: v.immediate_actions.trim() || null,
      activity: (v.activity || null) as Schemas["Activity"] | null,
      work_related: v.work_related,
      not_work_related_reason: v.work_related ? null : ((v.not_work_related_reason || null) as Schemas["NotWorkRelatedReason"] | null),
      work_related_rationale: v.work_related ? null : v.work_related_rationale.trim() || null,
      actual_severity: v.actual_severity ? Number(v.actual_severity) : null,
      potential_severity: v.potential_severity ? Number(v.potential_severity) : null,
      ambient_temp_c: v.ambient_temp_c || null,
      airside_flags: airside ? v.airside_flags : [],
      property_damage: has("property_damage") ? { asset_type: v.pd_asset_type as Schemas["AssetType"], estimated_cost_sar: v.pd_cost } : null,
      environmental: has("environmental")
        ? {
            category: v.env_category as Schemas["EnvCategory"],
            substance: v.env_substance.trim() || null,
            quantity_l: v.env_quantity || null,
            contained: v.env_contained,
            reached: v.env_reached as Schemas["EnvReached"],
          }
        : null,
      dangerous_occurrence: has("dangerous_occurrence") ? { category: v.do_category as Schemas["DangerousOccurrenceCategory"] } : null,
    };
    try {
      let saved = incident
        ? await unwrap(api.PATCH("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: incident.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/incidents", { params: { path: { project_id: project.id } }, body }));
      draft.clear();
      warn(saved.warnings);
      if (report && saved.status === "draft" && !has("injury_illness")) {
        saved = await unwrap(api.POST("/api/v1/incidents/{incident_id}/transitions", { params: { path: { incident_id: saved.id } }, body: { to_status: "reported" } }));
      }
      qc.setQueryData(hk.incident(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["incidents"] });
      toast.success(incident ? tc("saved") : tc("created"));
      router.push(`/incidents/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit((v) => save(v, false))} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="incident-form">
      {draft.restored ? (
        <Alert tone="info">
          <span className="flex flex-wrap items-center gap-2">
            {tc("draftRestored")}
            <Button type="button" size="sm" variant="ghost" onClick={() => { draft.clear(); form.reset(); }}>
              {tc("discardDraft")}
            </Button>
          </span>
        </Alert>
      ) : null}
      {!online ? <Alert tone="warning">{tc("offline")}</Alert> : null}
      <Alert tone="info">{t("p3Hint")}</Alert>
      <FormSection title={incident ? t("editTitle") : t("createTitle")}>
        <FormField id="occurred_at" label={t("fields.occurred_at")} error={errors.occurred_at?.message} required>
          <Input type="datetime-local" max={utcToZonedInput(new Date().toISOString(), tz)} {...form.register("occurred_at")} />
        </FormField>
        <FormField id="shift" label={t("fields.shift")} error={errors.shift?.message}>
          <Select {...form.register("shift")}>
            {INCIDENT_SHIFTS.map((s) => (
              <option key={s} value={s}>
                {te(`shift.${s}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="site_id" label={t("fields.site")} error={errors.site_id?.message} required>
          <Select {...form.register("site_id", { onChange: () => form.setValue("zone_id", "") })}>
            <option value="">{tc("select")}</option>
            {opts.sites.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="zone_id" label={t("fields.zone")} error={errors.zone_id?.message}>
          <Select {...form.register("zone_id")}>
            <option value="">{tc("noZone")}</option>
            {zones.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="location_detail" label={t("fields.location_detail")} error={errors.location_detail?.message}>
          <Input maxLength={200} {...form.register("location_detail")} />
        </FormField>
        <FormField id="responsible_engagement_id" label={t("fields.responsible_engagement")} error={errors.responsible_engagement_id?.message} required>
          <Select {...form.register("responsible_engagement_id")}>
            <option value="">{tc("select")}</option>
            {engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <Controller
          control={form.control}
          name="incident_types"
          render={({ field }) => (
            <CheckboxGroup
              id="incident_types"
              legend={t("fields.incident_types")}
              required
              className="sm:col-span-2"
              options={INCIDENT_TYPES.map((x) => ({ value: x, label: te(`incidentType.${x}`) }))}
              value={field.value}
              onChange={(v) => {
                field.onChange(v);
                const p = form.getValues("primary_type");
                if (v.length === 1) form.setValue("primary_type", v[0] ?? "");
                else if (p && !v.includes(p as IncType)) form.setValue("primary_type", "");
              }}
              error={errors.incident_types?.message}
              hint={t("nearMissExclusive")}
            />
          )}
        />
        <FormField id="primary_type" label={t("fields.primary_type")} error={errors.primary_type?.message} required>
          <Select {...form.register("primary_type")}>
            <option value="">{tc("select")}</option>
            {types.map((x) => (
              <option key={x} value={x}>
                {te(`incidentType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="activity" label={t("fields.activity")} error={errors.activity?.message} required>
          <Select {...form.register("activity")}>
            <option value="">{tc("select")}</option>
            {ref.options("activity").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="title" label={t("fields.title")} error={errors.title?.message} hint={t("p3Hint")} required className="sm:col-span-2">
          <Input maxLength={150} {...form.register("title")} />
        </FormField>
        <FormField id="description" label={t("fields.description")} error={errors.description?.message} required className="sm:col-span-2">
          <Textarea rows={5} maxLength={4000} {...form.register("description")} />
        </FormField>
        <FormField id="immediate_actions" label={t("fields.immediate_actions")} error={errors.immediate_actions?.message} required className="sm:col-span-2">
          <Textarea rows={3} maxLength={2000} {...form.register("immediate_actions")} />
        </FormField>
        <div className="sm:col-span-2">
          <PossibleIdHint text={textForHint} />
        </div>
        <FormField id="actual_severity" label={t("fields.actual_severity")} error={errors.actual_severity?.message} required>
          <Select {...form.register("actual_severity")}>
            <option value="">{tc("select")}</option>
            {sev.map((o) => (
              <option key={o.value} value={o.value}>
                {o.value} — {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="potential_severity" label={t("fields.potential_severity")} error={errors.potential_severity?.message} required>
          <Select {...form.register("potential_severity")}>
            <option value="">{tc("select")}</option>
            {sev.map((o) => (
              <option key={o.value} value={o.value}>
                {o.value} — {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ambient_temp_c" label={t("fields.ambient_temp_c")} error={errors.ambient_temp_c?.message}>
          <Input inputMode="decimal" className="ltr" {...form.register("ambient_temp_c")} />
        </FormField>
        <CheckboxField id="work_related" label={t("fields.work_related")} error={errors.work_related?.message}>
          <Checkbox {...form.register("work_related")} />
        </CheckboxField>
        {!workRelated ? (
          <>
            <FormField id="not_work_related_reason" label={t("fields.not_work_related_reason")} error={errors.not_work_related_reason?.message} required>
              <Select {...form.register("not_work_related_reason")}>
                <option value="">{tc("select")}</option>
                {NOT_WORK_RELATED_REASONS.map((x) => (
                  <option key={x} value={x}>
                    {te(`notWorkRelated.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="work_related_rationale" label={t("fields.work_related_rationale")} error={errors.work_related_rationale?.message}>
              <Textarea maxLength={500} {...form.register("work_related_rationale")} />
            </FormField>
          </>
        ) : null}
        {airside ? (
          <Controller
            control={form.control}
            name="airside_flags"
            render={({ field }) => (
              <CheckboxGroup<Flag>
                id="airside_flags"
                legend={t("fields.airside_flags")}
                className="sm:col-span-2"
                options={AIRSIDE_FLAGS.map((x) => ({ value: x, label: te(`airsideFlag.${x}`) }))}
                value={field.value}
                onChange={field.onChange}
                hint={t("airsideOnly")}
              />
            )}
          />
        ) : null}
      </FormSection>
      {types.includes("property_damage") ? (
        <FormSection title={t("fields.pd")}>
          <FormField id="pd_asset_type" label={t("fields.asset_type")} error={errors.pd_asset_type?.message} required>
            <Select {...form.register("pd_asset_type")}>
              <option value="">{tc("select")}</option>
              {ASSET_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`assetType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="pd_cost" label={t("fields.estimated_cost_sar")} error={errors.pd_cost?.message} required>
            <Input inputMode="decimal" className="ltr" {...form.register("pd_cost")} />
          </FormField>
        </FormSection>
      ) : null}
      {types.includes("environmental") ? (
        <FormSection title={t("fields.env")}>
          <FormField id="env_category" label={t("fields.env_category")} error={errors.env_category?.message} required>
            <Select {...form.register("env_category")}>
              <option value="">{tc("select")}</option>
              {ENV_CATEGORIES.map((x) => (
                <option key={x} value={x}>
                  {te(`envCategory.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="env_reached" label={t("fields.reached")} error={errors.env_reached?.message} required>
            <Select {...form.register("env_reached")}>
              <option value="">{tc("select")}</option>
              {ENV_REACHED.map((x) => (
                <option key={x} value={x}>
                  {te(`envReached.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="env_substance" label={t("fields.substance")} error={errors.env_substance?.message}>
            <Input maxLength={100} {...form.register("env_substance")} />
          </FormField>
          <FormField id="env_quantity" label={t("fields.quantity_l")} error={errors.env_quantity?.message}>
            <Input inputMode="decimal" className="ltr" {...form.register("env_quantity")} />
          </FormField>
          <CheckboxField id="env_contained" label={t("fields.contained")}>
            <Checkbox {...form.register("env_contained")} />
          </CheckboxField>
        </FormSection>
      ) : null}
      {types.includes("dangerous_occurrence") ? (
        <FormSection title={t("fields.do")}>
          <FormField id="do_category" label={t("fields.do_category")} error={errors.do_category?.message} required>
            <Select {...form.register("do_category")}>
              <option value="">{tc("select")}</option>
              {DO_CATEGORIES.map((x) => (
                <option key={x} value={x}>
                  {te(`doCategory.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        </FormSection>
      ) : null}
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        {!incident && !types.includes("injury_illness") ? (
          <Button type="button" disabled={isSubmitting} onClick={form.handleSubmit((v) => save(v, true))} data-testid="save-report">
            {t("saveReport")}
          </Button>
        ) : null}
        <Button type="submit" variant={incident || types.includes("injury_illness") ? "default" : "outline"} disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : incident ? tc("save") : t("saveDraft")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={incident ? `/incidents/${incident.id}` : "/incidents"}>{tc("cancel")}</Link>
        </Button>
      </div>
      {!incident ? <p className="text-xs text-muted-foreground">{tc("draftSavedLocally")}</p> : null}
    </form>
  );
}
