"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { useProjectOptions } from "@/components/common/pickers";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk } from "@/lib/api/hse";
import { todayInZone } from "@/lib/datetime";
import { SHIFTS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";

const DEC = /^\d+(\.\d{1,2})?$/;
const INT = /^\d+$/;

export function WorkforceForm({ project, ret }: { project: Schemas["ProjectRead"]; ret?: Schemas["WorkforceReturnRead"] }) {
  const t = useTranslations("workforce");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const [error, setError] = useState<unknown>(null);

  const schema = useMemo(
    () =>
      z
        .object({
          site_id: z.string().min(1, tv("required")),
          zone_id: z.string(),
          engagement_id: z.string().min(1, tv("required")),
          work_date: z.string().min(1, tv("required")),
          shift: z.enum(SHIFTS),
          no_work: z.boolean(),
          headcount: z.string().regex(INT, tv("number")),
          man_hours: z.string().regex(DEC, tv("number")),
          toolbox_talks: z.string().regex(INT, tv("number")),
          toolbox_attendees: z.string().regex(INT, tv("number")),
          inductions: z.string().regex(INT, tv("number")),
          training_hours: z.string().regex(DEC, tv("number")),
          remarks: z.string().max(500, tv("maxLength", { max: 500 })),
        })
        .refine((v) => !v.no_work || (Number(v.headcount) === 0 && Number(v.man_hours) === 0), { message: t("noWorkHint"), path: ["no_work"] }),
    [tv, t],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      site_id: ret?.site.id ?? "",
      zone_id: ret?.zone?.id ?? "",
      engagement_id: ret?.engagement.id ?? "",
      work_date: ret?.work_date ?? todayInZone(),
      shift: ret?.shift ?? "day",
      no_work: ret?.no_work ?? false,
      headcount: String(ret?.headcount ?? ""),
      man_hours: ret?.man_hours ?? "",
      toolbox_talks: String(ret?.toolbox_talks ?? 0),
      toolbox_attendees: String(ret?.toolbox_attendees ?? 0),
      inductions: String(ret?.inductions ?? 0),
      training_hours: ret?.training_hours ?? "0",
      remarks: ret?.remarks ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const siteId = useWatch({ control: form.control, name: "site_id" });
  const remarks = useWatch({ control: form.control, name: "remarks" });
  const zones = opts.zones.filter((z) => z.siteId === siteId);
  const engagements = opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId));

  async function save(v: Values, submit: boolean) {
    setError(null);
    const common = {
      zone_id: v.zone_id || null,
      shift: v.shift,
      no_work: v.no_work,
      headcount: Number(v.headcount),
      man_hours: v.man_hours,
      toolbox_talks: Number(v.toolbox_talks),
      toolbox_attendees: Number(v.toolbox_attendees),
      inductions: Number(v.inductions),
      training_hours: v.training_hours,
      remarks: v.remarks.trim() || null,
    };
    try {
      const saved = ret
        ? await unwrap(api.PATCH("/api/v1/workforce-returns/{return_id}", { params: { path: { return_id: ret.id } }, body: common }))
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/workforce-returns", {
              params: { path: { project_id: project.id } },
              body: { ...common, site_id: v.site_id, engagement_id: v.engagement_id, work_date: v.work_date, submit },
            }),
          );
      qc.setQueryData(hk.ret(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
      warn(saved.warnings);
      toast.success(ret ? tc("saved") : tc("created"));
      router.push(`/workforce/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit((v) => save(v, false))} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="return-form">
      <FormSection title={ret ? t("editTitle") : t("createTitle")}>
        <FormField id="work_date" label={t("fields.work_date")} error={errors.work_date?.message} required>
          <Input type="date" max={todayInZone()} disabled={Boolean(ret)} {...form.register("work_date")} />
        </FormField>
        <FormField id="shift" label={t("fields.shift")} error={errors.shift?.message} required>
          <Select {...form.register("shift")}>
            {SHIFTS.map((s) => (
              <option key={s} value={s}>
                {te(`shift.${s}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="site_id" label={t("fields.site")} error={errors.site_id?.message} required>
          <Select disabled={Boolean(ret)} {...form.register("site_id")}>
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
        <FormField id="engagement_id" label={t("fields.engagement")} error={errors.engagement_id?.message} required>
          <Select disabled={Boolean(ret)} {...form.register("engagement_id")}>
            <option value="">{tc("select")}</option>
            {engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <CheckboxField id="no_work" label={`${t("fields.no_work")} — ${t("noWorkHint")}`} error={errors.no_work?.message}>
          <Checkbox {...form.register("no_work")} />
        </CheckboxField>
        <FormField id="headcount" label={t("fields.headcount")} error={errors.headcount?.message} required>
          <Input inputMode="numeric" className="ltr" {...form.register("headcount")} />
        </FormField>
        <FormField id="man_hours" label={t("fields.man_hours")} error={errors.man_hours?.message} hint={t("manHoursHint")} required>
          <Input inputMode="decimal" className="ltr" {...form.register("man_hours")} />
        </FormField>
        <FormField id="toolbox_talks" label={t("fields.toolbox_talks")} error={errors.toolbox_talks?.message}>
          <Input inputMode="numeric" className="ltr" {...form.register("toolbox_talks")} />
        </FormField>
        <FormField id="toolbox_attendees" label={t("fields.toolbox_attendees")} error={errors.toolbox_attendees?.message}>
          <Input inputMode="numeric" className="ltr" {...form.register("toolbox_attendees")} />
        </FormField>
        <FormField id="inductions" label={t("fields.inductions")} error={errors.inductions?.message}>
          <Input inputMode="numeric" className="ltr" {...form.register("inductions")} />
        </FormField>
        <FormField id="training_hours" label={t("fields.training_hours")} error={errors.training_hours?.message}>
          <Input inputMode="decimal" className="ltr" {...form.register("training_hours")} />
        </FormField>
        <FormField id="remarks" label={t("fields.remarks")} error={errors.remarks?.message} hint={t("remarksHint")} className="sm:col-span-2">
          <Textarea maxLength={500} {...form.register("remarks")} />
        </FormField>
        <div className="sm:col-span-2">
          <PossibleIdHint text={remarks} />
        </div>
      </FormSection>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        {ret ? (
          <Button type="submit" disabled={isSubmitting} data-testid="save">
            {isSubmitting ? tc("saving") : tc("save")}
          </Button>
        ) : (
          <>
            <Button type="button" disabled={isSubmitting} onClick={form.handleSubmit((v) => save(v, true))} data-testid="save-submit">
              {t("saveSubmit")}
            </Button>
            <Button type="submit" variant="outline" disabled={isSubmitting} data-testid="save">
              {t("saveDraft")}
            </Button>
          </>
        )}
        <Button variant="ghost" asChild>
          <Link href={ret ? `/workforce/${ret.id}` : "/workforce"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
