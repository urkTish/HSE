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
import { FormField, FormSection } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { PROJECT_TYPES } from "@/lib/enums";
import { applyServerErrors, ARABIC_SCRIPT, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";

export function ProjectForm({ project }: { project?: Schemas["ProjectRead"] }) {
  const t = useTranslations("project");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const editing = Boolean(project);

  const schema = useMemo(
    () =>
      z
        .object({
          code: z.string().trim().regex(/^[A-Z0-9-]{3,12}$/, tv("projectCode")),
          name_en: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          name_ar: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })).regex(ARABIC_SCRIPT, tv("arabicRequired")),
          project_type: z.enum(PROJECT_TYPES, { message: tv("required") }),
          client_name_en: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          client_name_ar: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          city: z.string().trim().min(1, tv("required")).max(80, tv("maxLength", { max: 80 })),
          start_date: z.string().min(1, tv("required")),
          planned_end_date: z.string(),
          airport_icao: z.string().trim(),
        })
        .superRefine((v, ctx) => {
          if (v.planned_end_date && v.start_date && v.planned_end_date < v.start_date) {
            ctx.addIssue({ code: "custom", path: ["planned_end_date"], message: tv("endBeforeStart") });
          }
          if (v.project_type === "airport") {
            if (!v.airport_icao) ctx.addIssue({ code: "custom", path: ["airport_icao"], message: tv("icaoRequired") });
            else if (!/^[A-Z]{4}$/.test(v.airport_icao)) ctx.addIssue({ code: "custom", path: ["airport_icao"], message: tv("icao") });
          }
        }),
    [tv],
  );
  type Values = z.infer<typeof schema>;

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: project?.code ?? "",
      name_en: project?.name_en ?? "",
      name_ar: project?.name_ar ?? "",
      project_type: project?.project_type ?? "airport",
      client_name_en: project?.client_name_en ?? "",
      client_name_ar: project?.client_name_ar ?? "",
      city: project?.city ?? "",
      start_date: project?.start_date ?? "",
      planned_end_date: project?.planned_end_date ?? "",
      airport_icao: project?.airport_icao ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const isAirport = useWatch({ control: form.control, name: "project_type" }) === "airport";

  async function onSubmit(v: Values) {
    setError(null);
    const body = {
      name_en: v.name_en,
      name_ar: v.name_ar,
      project_type: v.project_type,
      client_name_en: v.client_name_en,
      client_name_ar: v.client_name_ar,
      city: v.city,
      start_date: v.start_date,
      planned_end_date: emptyToNull(v.planned_end_date),
      airport_icao: v.project_type === "airport" ? emptyToNull(v.airport_icao) : null,
    };
    try {
      const saved = project
        ? await unwrap(api.PATCH("/api/v1/projects/{project_id}", { params: { path: { project_id: project.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects", { body: { ...body, code: v.code } }));
      qc.setQueryData(keys.project(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["projects"] });
      await qc.invalidateQueries({ queryKey: ["history"] });
      toast.success(project ? tc("saved") : tc("created"));
      router.push(`/projects/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="project-form">
      <FormSection title={t("fields.name")}>
        <FormField id="code" label={t("fields.code")} error={errors.code?.message} hint={t("codeHint")} required>
          <Input className="ltr uppercase" disabled={editing} {...form.register("code")} />
        </FormField>
        <FormField id="project_type" label={t("fields.project_type")} error={errors.project_type?.message} required>
          <Select {...form.register("project_type")}>
            {PROJECT_TYPES.map((p) => (
              <option key={p} value={p}>
                {t(`type.${p}`)}
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
        <FormField id="client_name_en" label={t("fields.client_name_en")} error={errors.client_name_en?.message} required>
          <Input dir="ltr" {...form.register("client_name_en")} />
        </FormField>
        <FormField id="client_name_ar" label={t("fields.client_name_ar")} error={errors.client_name_ar?.message} required>
          <Input dir="rtl" lang="ar" {...form.register("client_name_ar")} />
        </FormField>
        <FormField id="city" label={t("fields.city")} error={errors.city?.message} required>
          <Input {...form.register("city")} />
        </FormField>
        {isAirport ? (
          <FormField id="airport_icao" label={t("fields.airport_icao")} error={errors.airport_icao?.message} hint={t("icaoHint")} required>
            <Input className="ltr uppercase" maxLength={4} {...form.register("airport_icao")} />
          </FormField>
        ) : null}
        <FormField id="start_date" label={t("fields.start_date")} error={errors.start_date?.message} required>
          <Input type="date" {...form.register("start_date")} />
        </FormField>
        <FormField id="planned_end_date" label={t("fields.planned_end_date")} error={errors.planned_end_date?.message}>
          <Input type="date" {...form.register("planned_end_date")} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={project ? `/projects/${project.id}` : "/projects"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
