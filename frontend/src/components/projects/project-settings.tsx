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
import { Alert } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { HistoryPanel } from "@/components/common/history-panel";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useProject, useProjectSettings } from "@/lib/api/queries";
import { formatDate, formatDateTime, todayInZone } from "@/lib/datetime";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { KPI_BASES } from "@/lib/enums";
import { can, canWrite } from "@/lib/permissions";

const bases = KPI_BASES.map(String) as ["200000", "1000000"];

export function ProjectSettings({ projectId }: { projectId: string }) {
  const q = useProjectSettings(projectId);
  const project = useProject(projectId);
  if (q.isLoading || project.isLoading) return <LoadingState />;
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return <SettingsForm settings={q.data} closed={project.data?.status === "closed"} />;
}

function SettingsForm({ settings, closed }: { settings: Schemas["ProjectSettingsRead"]; closed: boolean }) {
  const t = useTranslations("settings");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const locale = useLocale() === "ar" ? "ar" : "en";
  const name = useLocalizedName();
  const fe = useFieldErrorTranslator();
  const me = useMeData();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const editable = canWrite(me, "settings.edit", settings.project_id) && !closed;

  const schema = useMemo(
    () =>
      z.object({
        ltifr_base_hours: z.enum(bases),
        rate_base_hours: z.enum(bases),
        timezone: z.enum(["Asia/Riyadh"]),
        show_hijri: z.boolean(),
        hijri_calendar: z.enum(["umm_al_qura"]),
        default_language: z.enum(["en", "ar"]),
        week_start: z.enum(["sunday", "monday"]),
        digits: z.enum(["western", "arabic_indic"]),
        date_format_en: z.enum(["DD MMM YYYY", "DD/MM/YYYY"]),
        audit_retention_years: z.coerce.number({ message: tv("number") }).int().min(1, tv("range", { min: 1, max: 10 })).max(10, tv("range", { min: 1, max: 10 })),
        inactive_account_days: z.coerce
          .number({ message: tv("number") })
          .int()
          .min(30, tv("range", { min: 30, max: 365 }))
          .max(365, tv("range", { min: 30, max: 365 })),
      }),
    [tv],
  );
  type In = z.input<typeof schema>;
  type Out = z.output<typeof schema>;

  const form = useForm<In, unknown, Out>({
    resolver: zodResolver(schema),
    defaultValues: {
      ltifr_base_hours: String(settings.ltifr_base_hours) as "200000" | "1000000",
      rate_base_hours: String(settings.rate_base_hours) as "200000" | "1000000",
      timezone: settings.timezone,
      show_hijri: settings.show_hijri,
      hijri_calendar: settings.hijri_calendar,
      default_language: settings.default_language,
      week_start: settings.week_start,
      digits: settings.digits,
      date_format_en: settings.date_format_en,
      audit_retention_years: settings.audit_retention_years,
      inactive_account_days: settings.inactive_account_days,
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  const w = form.watch();

  async function onSubmit(v: Out) {
    setError(null);
    try {
      const res = await unwrap(
        api.PATCH("/api/v1/projects/{project_id}/settings", {
          params: { path: { project_id: settings.project_id } },
          body: {
            ...v,
            ltifr_base_hours: Number(v.ltifr_base_hours) as Schemas["KpiBaseHours"],
            rate_base_hours: Number(v.rate_base_hours) as Schemas["KpiBaseHours"],
          },
        }),
      );
      qc.setQueryData(keys.settings(settings.project_id), res);
      await qc.invalidateQueries({ queryKey: ["history"] });
      form.reset({ ...v, ltifr_base_hours: v.ltifr_base_hours, rate_base_hours: v.rate_base_hours });
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  const today = todayInZone(settings.timezone);
  const preview = formatDate(today, {
    locale,
    timeZone: settings.timezone,
    showHijri: Boolean(w.show_hijri),
    digits: w.digits ?? "western",
    dateFormatEn: w.date_format_en ?? "DD MMM YYYY",
  });
  const displayPrefs = { locale, timeZone: settings.timezone, showHijri: settings.show_hijri, digits: settings.digits, dateFormatEn: settings.date_format_en } as const;
  const hours = (v: string) => t("hours", { value: Number(v) });

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-6 lg:col-span-2" data-testid="settings-form">
        {!editable ? <Alert tone="info">{t("readOnlyNote")}</Alert> : null}
        <FormSection title={t("kpi")}>
          <FormField id="ltifr_base_hours" label={t("fields.ltifr_base_hours")} error={errors.ltifr_base_hours?.message}>
            <Select disabled={!editable} {...form.register("ltifr_base_hours")}>
              {bases.map((b) => (
                <option key={b} value={b}>
                  {hours(b)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="rate_base_hours" label={t("fields.rate_base_hours")} error={errors.rate_base_hours?.message}>
            <Select disabled={!editable} {...form.register("rate_base_hours")}>
              {bases.map((b) => (
                <option key={b} value={b}>
                  {hours(b)}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="text-sm">
            <span className="text-muted-foreground">{t("ltifrLabel")}: </span>
            <span className="font-medium" data-testid="ltifr-label">
              {name(settings.ltifr_base_label_en, settings.ltifr_base_label_ar)}
            </span>
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">{t("rateLabel")}: </span>
            <span className="font-medium" data-testid="rate-label">
              {name(settings.rate_base_label_en, settings.rate_base_label_ar)}
            </span>
          </div>
        </FormSection>
        <FormSection title={t("display")}>
          <FormField id="timezone" label={t("fields.timezone")}>
            <Select disabled={!editable} {...form.register("timezone")}>
              <option value="Asia/Riyadh">{t("timezone.Asia/Riyadh")}</option>
            </Select>
          </FormField>
          <FormField id="default_language" label={t("fields.default_language")}>
            <Select disabled={!editable} {...form.register("default_language")}>
              <option value="en">{tc("english")}</option>
              <option value="ar">{tc("arabic")}</option>
            </Select>
          </FormField>
          <FormField id="week_start" label={t("fields.week_start")}>
            <Select disabled={!editable} {...form.register("week_start")}>
              <option value="sunday">{t("weekStart.sunday")}</option>
              <option value="monday">{t("weekStart.monday")}</option>
            </Select>
          </FormField>
          <FormField id="digits" label={t("fields.digits")}>
            <Select disabled={!editable} {...form.register("digits")}>
              <option value="western">{t("digits.western")}</option>
              <option value="arabic_indic">{t("digits.arabic_indic")}</option>
            </Select>
          </FormField>
          <FormField id="date_format_en" label={t("fields.date_format_en")}>
            <Select disabled={!editable} {...form.register("date_format_en")}>
              <option value="DD MMM YYYY">DD MMM YYYY</option>
              <option value="DD/MM/YYYY">DD/MM/YYYY</option>
            </Select>
          </FormField>
          <FormField id="hijri_calendar" label={t("fields.hijri_calendar")}>
            <Select disabled={!editable} {...form.register("hijri_calendar")}>
              <option value="umm_al_qura">{t("hijriCalendar.umm_al_qura")}</option>
            </Select>
          </FormField>
          <CheckboxField id="show_hijri" label={t("fields.show_hijri")}>
            <Checkbox disabled={!editable} {...form.register("show_hijri")} />
          </CheckboxField>
          <div className="text-sm sm:col-span-2">
            <span className="text-muted-foreground">{t("preview")}: </span>
            <span className="font-medium" data-testid="date-preview" data-date={today}>
              {preview}
            </span>
          </div>
        </FormSection>
        <FormSection title={t("retention")}>
          <FormField id="audit_retention_years" label={t("fields.audit_retention_years")} error={errors.audit_retention_years?.message}>
            <Input type="number" min={1} max={10} disabled={!editable} {...form.register("audit_retention_years")} />
          </FormField>
          <FormField id="inactive_account_days" label={t("fields.inactive_account_days")} error={errors.inactive_account_days?.message}>
            <Input type="number" min={30} max={365} disabled={!editable} {...form.register("inactive_account_days")} />
          </FormField>
        </FormSection>
        <p className="text-xs text-muted-foreground">
          {settings.saved_at ? t("lastSaved", { date: formatDateTime(settings.saved_at, displayPrefs) }) : t("neverSaved")}
        </p>
        <MutationError error={error} />
        {editable ? (
          <div>
            <Button type="submit" disabled={isSubmitting || !isDirty} data-testid="save-settings">
              {isSubmitting ? tc("saving") : tc("save")}
            </Button>
          </div>
        ) : null}
      </form>
      {can(me, "history.view", settings.project_id) ? (
        <HistoryPanel entityType="project_settings" entityId={settings.project_id} projectId={settings.project_id} />
      ) : null}
    </div>
  );
}
