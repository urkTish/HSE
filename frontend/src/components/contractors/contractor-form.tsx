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
import { CONTRACTOR_CATEGORIES } from "@/lib/enums";
import { applyServerErrors, ARABIC_SCRIPT, emptyToNull } from "@/lib/forms";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";

export function ContractorForm({ contractor }: { contractor?: Schemas["ContractorRead"] }) {
  const t = useTranslations("contractor");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);

  const schema = useMemo(
    () =>
      z.object({
        legal_name_en: z.string().trim().min(1, tv("required")).max(200, tv("maxLength", { max: 200 })),
        legal_name_ar: z.string().trim().min(1, tv("required")).max(200, tv("maxLength", { max: 200 })).regex(ARABIC_SCRIPT, tv("arabicRequired")),
        short_code: z.string().trim().regex(/^[A-Z0-9]{2,10}$/, tv("shortCode")),
        cr_number: z.string().trim().regex(/^[12457]\d{9}$/, tv("crNumber")),
        cr_expiry_date: z.string(),
        vat_number: z.string().trim().refine((v) => v === "" || /^3\d{13}3$/.test(v), tv("vatNumber")),
        contractor_category: z.enum(CONTRACTOR_CATEGORIES),
        primary_contact_name: z.string().trim().min(1, tv("required")).max(120, tv("maxLength", { max: 120 })),
        primary_contact_mobile: z.string().trim().regex(/^\+[1-9]\d{7,14}$/, tv("mobile")),
        primary_contact_email: z.string().trim().min(1, tv("required")).email(tv("email")),
      }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      legal_name_en: contractor?.legal_name_en ?? "",
      legal_name_ar: contractor?.legal_name_ar ?? "",
      short_code: contractor?.short_code ?? "",
      cr_number: contractor?.cr_number ?? "",
      cr_expiry_date: contractor?.cr_expiry_date ?? "",
      vat_number: contractor?.vat_number ?? "",
      contractor_category: contractor?.contractor_category ?? "civil",
      primary_contact_name: contractor?.primary_contact_name ?? "",
      primary_contact_mobile: contractor?.primary_contact_mobile ?? "",
      primary_contact_email: contractor?.primary_contact_email ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    setError(null);
    const body = { ...v, cr_expiry_date: emptyToNull(v.cr_expiry_date), vat_number: emptyToNull(v.vat_number) };
    try {
      const saved = contractor
        ? await unwrap(api.PATCH("/api/v1/contractors/{contractor_id}", { params: { path: { contractor_id: contractor.id } }, body }))
        : await unwrap(api.POST("/api/v1/contractors", { body }));
      qc.setQueryData(keys.contractor(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["contractors"] });
      toast.success(contractor ? tc("saved") : tc("created"));
      router.push(`/contractors/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="contractor-form">
      <FormSection title={t("fields.legal_name")}>
        <FormField id="legal_name_en" label={t("fields.legal_name_en")} error={errors.legal_name_en?.message} required>
          <Input dir="ltr" {...form.register("legal_name_en")} />
        </FormField>
        <FormField id="legal_name_ar" label={t("fields.legal_name_ar")} error={errors.legal_name_ar?.message} required>
          <Input dir="rtl" lang="ar" {...form.register("legal_name_ar")} />
        </FormField>
        <FormField id="short_code" label={t("fields.short_code")} error={errors.short_code?.message} required>
          <Input className="ltr uppercase" {...form.register("short_code")} />
        </FormField>
        <FormField id="contractor_category" label={t("fields.contractor_category")} error={errors.contractor_category?.message} required>
          <Select {...form.register("contractor_category")}>
            {CONTRACTOR_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`category.${c}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cr_number" label={t("fields.cr_number")} error={errors.cr_number?.message} hint={t("crHint")} required>
          <Input inputMode="numeric" className="ltr" maxLength={10} {...form.register("cr_number")} />
        </FormField>
        <FormField id="cr_expiry_date" label={t("fields.cr_expiry_date")} error={errors.cr_expiry_date?.message}>
          <Input type="date" {...form.register("cr_expiry_date")} />
        </FormField>
        <FormField id="vat_number" label={t("fields.vat_number")} error={errors.vat_number?.message} hint={t("vatHint")}>
          <Input inputMode="numeric" className="ltr" maxLength={15} {...form.register("vat_number")} />
        </FormField>
      </FormSection>
      <FormSection title={t("contact")}>
        <FormField id="primary_contact_name" label={t("fields.primary_contact_name")} error={errors.primary_contact_name?.message} required>
          <Input {...form.register("primary_contact_name")} />
        </FormField>
        <FormField id="primary_contact_mobile" label={t("fields.primary_contact_mobile")} error={errors.primary_contact_mobile?.message} hint={t("mobileHint")} required>
          <Input type="tel" className="ltr" {...form.register("primary_contact_mobile")} />
        </FormField>
        <FormField id="primary_contact_email" label={t("fields.primary_contact_email")} error={errors.primary_contact_email?.message} required>
          <Input type="email" className="ltr" {...form.register("primary_contact_email")} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={contractor ? `/contractors/${contractor.id}` : "/contractors"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}
