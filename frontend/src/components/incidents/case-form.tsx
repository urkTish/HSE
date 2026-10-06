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
import { useWarningToasts } from "@/components/common/api-warnings";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { useProjectOptions } from "@/components/common/pickers";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk } from "@/lib/api/hse";
import { AGE_BANDS, BODY_SIDES, ID_TYPES, PERMANENT_DISABILITY, PERSON_TYPES, PRIVACY_REASONS, TREATED_AT } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";
import { useRefLists } from "@/lib/reference";

const ID_RE: Record<Schemas["IdType"], RegExp> = { iqama: /^2\d{9}$/, national_id: /^1\d{9}$/, passport: /^[A-Z0-9]{6,9}$/ };
type Treatment = Schemas["Treatment"];

export function CaseForm({ incident, kase }: { incident: Schemas["IncidentRead"]; kase?: Schemas["InjuryCaseRead"] }) {
  const t = useTranslations("cases");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(incident.project_id);
  const ref = useRefLists();
  const [error, setError] = useState<unknown>(null);
  const hideIdentity = Boolean(kase?.redacted_groups.includes("identity"));
  const hideMedical = Boolean(kase?.redacted_groups.includes("medical"));
  const creating = !kase;

  const schema = useMemo(
    () =>
      z
        .object({
          person_type: z.enum(PERSON_TYPES),
          employer_engagement_id: z.string(),
          person_name: z.string().max(120, tv("maxLength", { max: 120 })),
          id_type: z.string(),
          id_number: z.string(),
          employee_no: z.string().max(20, tv("maxLength", { max: 20 })),
          nationality: z.string().refine((v) => v === "" || /^[A-Za-z]{2}$/.test(v), tv("invalid")),
          trade: z.string().min(1, tv("required")),
          age_band: z.string(),
          site_start_date: z.string(),
          hours_into_shift: z.string().refine((v) => v === "" || (/^\d{1,2}(\.\d)?$/.test(v) && Number(v) <= 16), tv("number")),
          illness: z.boolean(),
          body_part: z.string(),
          body_side: z.string(),
          nature: z.string(),
          mechanism: z.string().min(1, tv("required")),
          agency: z.string().min(1, tv("required")),
          treatments: z.array(z.string()),
          loss_of_consciousness: z.boolean(),
          treated_at: z.string(),
          fatal: z.boolean(),
          date_of_death: z.string(),
          away_start_date: z.string(),
          rtw_date: z.string(),
          restricted_start: z.string(),
          restricted_end: z.string(),
          transfer_start: z.string(),
          transfer_end: z.string(),
          permanent_disability: z.string(),
          commuting: z.boolean(),
          privacy_case: z.boolean(),
          privacy_reason: z.string(),
          medical_notes: z.string().max(2000, tv("maxLength", { max: 2000 })),
          gosi_case_ref: z.string().max(30, tv("maxLength", { max: 30 })),
        })
        .superRefine((v, ctx) => {
          const req = (k: keyof typeof v) => ctx.addIssue({ code: "custom", path: [k], message: tv("required") });
          if (v.person_type === "contractor_worker" && !v.employer_engagement_id) req("employer_engagement_id");
          if (!hideIdentity && creating && !v.person_name.trim()) req("person_name");
          if (v.id_number && !v.id_type) req("id_type");
          if (v.id_type && v.id_number && !ID_RE[v.id_type as Schemas["IdType"]].test(v.id_number)) ctx.addIssue({ code: "custom", path: ["id_number"], message: tv("idFormat") });
          if (!hideMedical) {
            if (!v.body_part) req("body_part");
            if (!v.nature) req("nature");
            if (!v.treated_at) req("treated_at");
            if (v.treatments.length === 0) req("treatments");
            if (v.fatal && !v.date_of_death) req("date_of_death");
            if (v.privacy_case && !v.privacy_reason) req("privacy_reason");
            if (v.rtw_date && v.away_start_date && v.rtw_date <= v.away_start_date) ctx.addIssue({ code: "custom", path: ["rtw_date"], message: tv("invalid") });
          }
        }),
    [tv, hideIdentity, hideMedical, creating],
  );
  type Values = z.infer<typeof schema>;
  const s = (x: string | null | undefined) => x ?? "";
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      person_type: kase?.person_type ?? "contractor_worker",
      employer_engagement_id: kase?.employer?.id ?? incident.responsible_engagement?.id ?? "",
      person_name: s(kase?.person_name),
      id_type: s(kase?.id_type),
      id_number: "",
      employee_no: s(kase?.employee_no),
      nationality: s(kase?.nationality),
      trade: s(kase?.trade),
      age_band: s(kase?.age_band),
      site_start_date: s(kase?.site_start_date),
      hours_into_shift: s(kase?.hours_into_shift),
      illness: kase?.illness ?? false,
      body_part: s(kase?.body_part),
      body_side: s(kase?.body_side),
      nature: s(kase?.nature),
      mechanism: s(kase?.mechanism),
      agency: s(kase?.agency),
      treatments: kase?.treatments ?? [],
      loss_of_consciousness: kase?.loss_of_consciousness ?? false,
      treated_at: s(kase?.treated_at),
      fatal: kase?.fatal ?? false,
      date_of_death: s(kase?.date_of_death),
      away_start_date: s(kase?.away_start_date),
      rtw_date: s(kase?.rtw_date),
      restricted_start: s(kase?.restricted_start),
      restricted_end: s(kase?.restricted_end),
      transfer_start: s(kase?.transfer_start),
      transfer_end: s(kase?.transfer_end),
      permanent_disability: kase?.permanent_disability ?? "none",
      commuting: kase?.commuting ?? false,
      privacy_case: kase?.privacy_case ?? false,
      privacy_reason: s(kase?.privacy_reason),
      medical_notes: s(kase?.medical_notes),
      gosi_case_ref: s(kase?.gosi_case_ref),
    },
  });
  const { errors, isSubmitting } = form.formState;
  const personType = useWatch({ control: form.control, name: "person_type" });
  const fatal = useWatch({ control: form.control, name: "fatal" });
  const privacy = useWatch({ control: form.control, name: "privacy_case" });
  const treatmentOpts = ref.options("treatment");
  const groups = Array.from(new Set(treatmentOpts.map((o) => o.group ?? "other")));

  async function save(v: Values) {
    setError(null);
    const n = (x: string) => x.trim() || null;
    const base = {
      person_type: v.person_type,
      employer_engagement_id: v.person_type === "contractor_worker" ? v.employer_engagement_id || null : null,
      trade: v.trade as Schemas["Trade"],
      mechanism: v.mechanism as Schemas["Mechanism"],
      agency: v.agency as Schemas["Agency"],
      commuting: v.commuting,
    };
    const identity = hideIdentity
      ? {}
      : {
          ...(v.person_name.trim() ? { person_name: v.person_name.trim() } : {}),
          id_type: (v.id_type || null) as Schemas["IdType"] | null,
          ...(v.id_number ? { id_number: v.id_number } : {}),
          employee_no: n(v.employee_no),
          nationality: v.nationality ? v.nationality.toUpperCase() : null,
          age_band: (v.age_band || null) as Schemas["AgeBand"] | null,
          site_start_date: v.site_start_date || null,
          hours_into_shift: v.hours_into_shift || null,
          gosi_case_ref: n(v.gosi_case_ref),
        };
    const medical = hideMedical
      ? {}
      : {
          illness: v.illness,
          body_part: v.body_part as Schemas["BodyPart"],
          body_side: (v.body_side || null) as Schemas["BodySide"] | null,
          nature: v.nature as Schemas["InjuryNature"],
          treatments: v.treatments as Treatment[],
          loss_of_consciousness: v.loss_of_consciousness,
          treated_at: v.treated_at as Schemas["TreatedAt"],
          fatal: v.fatal,
          date_of_death: v.fatal ? v.date_of_death || null : null,
          away_start_date: v.away_start_date || null,
          rtw_date: v.rtw_date || null,
          restricted_start: v.restricted_start || null,
          restricted_end: v.restricted_end || null,
          transfer_start: v.transfer_start || null,
          transfer_end: v.transfer_end || null,
          permanent_disability: v.permanent_disability as Schemas["PermanentDisability"],
          privacy_case: v.privacy_case,
          privacy_reason: v.privacy_case ? ((v.privacy_reason || null) as Schemas["PrivacyCaseReason"] | null) : null,
          medical_notes: n(v.medical_notes),
        };
    try {
      const saved = kase
        ? await unwrap(api.PATCH("/api/v1/injury-cases/{case_id}", { params: { path: { case_id: kase.id } }, body: { ...base, ...identity, ...medical } }))
        : await unwrap(
            api.POST("/api/v1/incidents/{incident_id}/injury-cases", {
              params: { path: { incident_id: incident.id } },
              body: { ...base, ...identity, ...medical, person_name: v.person_name.trim() } as Schemas["InjuryCaseCreate"],
            }),
          );
      qc.setQueryData(hk.injuryCase(saved.id), saved);
      await qc.invalidateQueries({ queryKey: hk.incident(incident.id) });
      await qc.invalidateQueries({ queryKey: ["incidents"] });
      warn(saved.warnings);
      toast.success(kase ? tc("saved") : tc("created"));
      router.push(`/injury-cases/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  const sel = (name: keyof Values, label: string, options: { value: string; label: string }[], required = false, empty = tc("select")) => (
    <FormField id={`case-${name}`} label={label} error={errors[name]?.message as string | undefined} required={required}>
      <Select {...form.register(name)}>
        <option value="">{empty}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </FormField>
  );
  const dateField = (name: keyof Values, label: string, required = false) => (
    <FormField id={`case-${name}`} label={label} error={errors[name]?.message as string | undefined} required={required}>
      <Input type="date" {...form.register(name)} />
    </FormField>
  );

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="case-form">
      <Alert tone="warning">{t("sensitiveNote")}</Alert>
      <FormSection title={t("title")}>
        {sel("person_type", t("fields.person_type"), PERSON_TYPES.map((x) => ({ value: x, label: te(`personType.${x}`) })), true)}
        {personType === "contractor_worker" ? sel("employer_engagement_id", t("fields.employer"), opts.engagements, true) : null}
        {sel("trade", t("fields.trade"), ref.options("trade"), true)}
        {sel("mechanism", t("fields.mechanism"), ref.options("mechanism"), true)}
        {sel("agency", t("fields.agency"), ref.options("agency"), true)}
        <CheckboxField id="case-commuting" label={t("fields.commuting")}>
          <Checkbox {...form.register("commuting")} />
        </CheckboxField>
      </FormSection>
      {!hideIdentity ? (
        <FormSection title={t("identity")}>
          <FormField id="case-person_name" label={t("fields.person_name")} error={errors.person_name?.message} required={creating}>
            <Input maxLength={120} autoComplete="off" {...form.register("person_name")} />
          </FormField>
          {sel("id_type", t("fields.id_type"), ID_TYPES.map((x) => ({ value: x, label: te(`idType.${x}`) })))}
          <FormField id="case-id_number" label={t("fields.id_number")} error={errors.id_number?.message} hint={kase?.id_number_masked ? kase.id_number_masked : undefined}>
            <Input className="ltr" autoComplete="off" maxLength={10} {...form.register("id_number")} />
          </FormField>
          <FormField id="case-employee_no" label={t("fields.employee_no")} error={errors.employee_no?.message}>
            <Input className="ltr" maxLength={20} {...form.register("employee_no")} />
          </FormField>
          <FormField id="case-nationality" label={t("fields.nationality")} error={errors.nationality?.message}>
            <Input className="ltr uppercase" maxLength={2} {...form.register("nationality")} />
          </FormField>
          {sel("age_band", t("fields.age_band"), AGE_BANDS.map((x) => ({ value: x, label: te(`ageBand.${x}`) })))}
          {dateField("site_start_date", t("fields.site_start_date"))}
          <FormField id="case-hours_into_shift" label={t("fields.hours_into_shift")} error={errors.hours_into_shift?.message}>
            <Input inputMode="decimal" className="ltr" {...form.register("hours_into_shift")} />
          </FormField>
          <FormField id="case-gosi_case_ref" label={t("fields.gosi_case_ref")} error={errors.gosi_case_ref?.message}>
            <Input className="ltr" maxLength={30} {...form.register("gosi_case_ref")} />
          </FormField>
        </FormSection>
      ) : null}
      {!hideMedical ? (
        <>
          <FormSection title={t("medical")}>
            {sel("body_part", t("fields.body_part"), ref.options("body_part"), true)}
            {sel("body_side", t("fields.body_side"), BODY_SIDES.map((x) => ({ value: x, label: te(`bodySide.${x}`) })))}
            {sel("nature", t("fields.nature"), ref.options("nature"), true)}
            {sel("treated_at", t("fields.treated_at"), TREATED_AT.map((x) => ({ value: x, label: te(`treatedAt.${x}`) })), true)}
            <Controller
              control={form.control}
              name="treatments"
              render={({ field }) => (
                <div className="flex flex-col gap-3 sm:col-span-2" data-testid="treatments">
                  {groups.map((g) => (
                    <CheckboxGroup
                      key={g}
                      id={`treatments-${g}`}
                      legend={`${t("fields.treatments")} — ${t.has(`treatmentGroup.${g as "other"}`) ? t(`treatmentGroup.${g as "other"}`) : g}`}
                      required
                      options={treatmentOpts.filter((o) => (o.group ?? "other") === g)}
                      value={field.value}
                      onChange={(v) => field.onChange([...field.value.filter((x) => !treatmentOpts.some((o) => o.value === x && (o.group ?? "other") === g)), ...v])}
                    />
                  ))}
                  {errors.treatments ? (
                    <p role="alert" className="text-xs font-medium text-destructive">
                      {errors.treatments.message}
                    </p>
                  ) : null}
                </div>
              )}
            />
            <CheckboxField id="case-illness" label={t("fields.illness")}>
              <Checkbox {...form.register("illness")} />
            </CheckboxField>
            <CheckboxField id="case-loc" label={t("fields.loss_of_consciousness")}>
              <Checkbox {...form.register("loss_of_consciousness")} />
            </CheckboxField>
            <CheckboxField id="case-fatal" label={t("fields.fatal")}>
              <Checkbox {...form.register("fatal")} />
            </CheckboxField>
            {fatal ? dateField("date_of_death", t("fields.date_of_death"), true) : null}
            <CheckboxField id="case-privacy" label={t("fields.privacy_case")}>
              <Checkbox {...form.register("privacy_case")} />
            </CheckboxField>
            {privacy ? sel("privacy_reason", t("fields.privacy_reason"), PRIVACY_REASONS.map((x) => ({ value: x, label: te(`privacyReason.${x}`) })), true) : null}
            <FormField id="case-medical_notes" label={t("fields.medical_notes")} error={errors.medical_notes?.message} className="sm:col-span-2">
              <Textarea maxLength={2000} {...form.register("medical_notes")} />
            </FormField>
          </FormSection>
          <FormSection title={t("absence")}>
            {dateField("away_start_date", t("fields.away_start_date"))}
            {dateField("rtw_date", t("fields.rtw_date"))}
            {dateField("restricted_start", t("fields.restricted_start"))}
            {dateField("restricted_end", t("fields.restricted_end"))}
            {dateField("transfer_start", t("fields.transfer_start"))}
            {dateField("transfer_end", t("fields.transfer_end"))}
            {sel("permanent_disability", t("fields.permanent_disability"), PERMANENT_DISABILITY.map((x) => ({ value: x, label: te(`permanentDisability.${x}`) })), true)}
          </FormSection>
        </>
      ) : (
        <Alert tone="info">{t("redacted", { groups: t("groups.medical") })}</Alert>
      )}
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-case">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={kase ? `/injury-cases/${kase.id}` : `/incidents/${incident.id}`}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
