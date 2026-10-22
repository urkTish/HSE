"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent, type ReactNode } from "react";
import { PrivacyText } from "@/components/auth/privacy-text";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, usePrivacyNotice } from "@/lib/api/queries";
import { meetsPasswordPolicy } from "@/lib/password";

export const setupKey = ["setup-status"] as const;

export function useSetupStatus() {
  return useQuery({ queryKey: setupKey, queryFn: () => unwrap(api.GET("/api/v1/setup")), staleTime: 30_000, retry: false });
}

const PROJECT_TYPES = ["airport", "building_highrise", "infrastructure", "industrial", "other"] as const;
type ProjectType = (typeof PROJECT_TYPES)[number];

const EMPTY = {
  setup_token: "",
  organisation_name_en: "",
  organisation_name_ar: "",
  code: "",
  name_en: "",
  name_ar: "",
  project_type: "airport" as ProjectType,
  client_name_en: "",
  client_name_ar: "",
  city: "",
  start_date: "",
  airport_iata: "",
  full_name_en: "",
  full_name_ar: "",
  email: "",
  password: "",
  confirm: "",
};
type Values = typeof EMPTY;
const ARABIC = /[؀-ۿ]/;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border p-3 sm:p-4">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  );
}

/** D-306: first-time setup of an empty install — organisation, first project, first administrator. */
export function FirstSetup() {
  const t = useTranslations("firstSetup");
  const tp = useTranslations("project");
  const tu = useTranslations("user");
  const tv = useTranslations("validation");
  const ta = useTranslations("auth");
  const locale = useLocale() === "ar" ? "ar" : "en";
  const qc = useQueryClient();
  const router = useRouter();
  const status = useSetupStatus();
  const notice = usePrivacyNotice();
  const [v, setV] = useState<Values>(EMPTY);
  const [ack, setAck] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof Values | "ack", string>>>({});

  const run = useMutation({
    mutationFn: () => {
      const body: Schemas["SetupRequest"] = {
        organisation_name_en: v.organisation_name_en.trim(),
        organisation_name_ar: v.organisation_name_ar.trim(),
        project: {
          code: v.code.trim(),
          name_en: v.name_en.trim(),
          name_ar: v.name_ar.trim(),
          project_type: v.project_type,
          client_name_en: v.client_name_en.trim(),
          client_name_ar: v.client_name_ar.trim(),
          city: v.city.trim(),
          start_date: v.start_date,
          airport_iata: v.project_type === "airport" && v.airport_iata.trim() ? v.airport_iata.trim().toUpperCase() : null,
        },
        admin: {
          email: v.email.trim(),
          full_name_en: v.full_name_en.trim(),
          full_name_ar: v.full_name_ar.trim() || null,
          preferred_language: locale,
          password: v.password,
        },
        privacy_notice_version: notice.data?.version ?? "",
        setup_token: v.setup_token.trim() || null,
      };
      return unwrap(api.POST("/api/v1/setup", { body }));
    },
    onSuccess: (res) => {
      qc.clear();
      if (res.user) qc.setQueryData(keys.me, res.user);
      router.replace("/", { locale: res.user?.display_language ?? locale });
    },
  });

  const set = (k: keyof Values) => (e: { target: { value: string } }) => setV((s) => ({ ...s, [k]: e.target.value }));

  function validate(): boolean {
    const e: Partial<Record<keyof Values | "ack", string>> = {};
    const required: (keyof Values)[] = [
      "organisation_name_en",
      "organisation_name_ar",
      "code",
      "name_en",
      "name_ar",
      "client_name_en",
      "client_name_ar",
      "city",
      "start_date",
      "full_name_en",
      "email",
      "password",
      "confirm",
    ];
    if (status.data?.token_required) required.unshift("setup_token");
    for (const k of required) if (!v[k].trim()) e[k] = tv("required");
    for (const k of ["organisation_name_ar", "name_ar", "client_name_ar"] as const) {
      if (v[k].trim() && !ARABIC.test(v[k])) e[k] = tv("arabicRequired");
    }
    if (v.email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email.trim())) e.email = tv("email");
    if (v.password && !meetsPasswordPolicy(v.password)) e.password = tv("passwordPolicy");
    if (v.confirm && v.password !== v.confirm) e.confirm = tv("passwordMismatch");
    if (!ack) e.ack = ta("privacy.mustAck");
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function submit(ev: FormEvent) {
    ev.preventDefault();
    if (validate()) run.mutate();
  }

  if (status.isLoading) return <LoadingState rows={4} />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  if (!status.data?.needed) {
    return (
      <Card data-testid="setup-locked">
        <CardHeader>
          <CardTitle>
            <span className="text-xl">{t("title")}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Alert tone="info">{t("locked")}</Alert>
          <Button asChild>
            <Link href="/login">{t("toLogin")}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const field = (k: keyof Values, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}, hint?: string) => (
    <FormField id={`setup-${k}`} label={label} error={errors[k]} hint={hint} required={k !== "full_name_ar" && k !== "airport_iata"}>
      <Input value={v[k]} onChange={set(k)} className="h-touch" {...props} />
    </FormField>
  );

  return (
    <Card data-testid="first-setup">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2 text-xl">
            <Building2 aria-hidden className="size-5 text-primary" />
            {t("title")}
          </span>
        </CardTitle>
        <CardDescription>{t("intro")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          {status.data.token_required ? (
            <Section title={t("tokenTitle")}>{field("setup_token", t("token"), { autoComplete: "off", className: "ltr h-touch" }, t("tokenHint"))}</Section>
          ) : null}
          <Section title={t("organisation")}>
            {field("organisation_name_en", t("orgNameEn"), { dir: "ltr" })}
            {field("organisation_name_ar", t("orgNameAr"), { dir: "rtl", lang: "ar" })}
          </Section>
          <Section title={t("project")}>
            {field("code", tp("fields.code"), { className: "ltr h-touch", maxLength: 12 }, t("codeHint"))}
            {field("name_en", tp("fields.name_en"), { dir: "ltr" })}
            {field("name_ar", tp("fields.name_ar"), { dir: "rtl", lang: "ar" })}
            <FormField id="setup-project_type" label={tp("fields.project_type")} required>
              <Select value={v.project_type} onChange={set("project_type")}>
                {PROJECT_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {tp(`type.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            {v.project_type === "airport" ? field("airport_iata", tp("fields.airport_iata"), { className: "ltr h-touch", maxLength: 3 }) : null}
            {field("client_name_en", tp("fields.client_name_en"), { dir: "ltr" })}
            {field("client_name_ar", tp("fields.client_name_ar"), { dir: "rtl", lang: "ar" })}
            {field("city", tp("fields.city"))}
            {field("start_date", tp("fields.start_date"), { type: "date", className: "ltr h-touch" })}
          </Section>
          <Section title={t("admin")}>
            <p className="text-sm text-muted-foreground">{t("adminHint")}</p>
            {field("full_name_en", tu("fields.full_name_en"), { dir: "ltr" })}
            {field("full_name_ar", tu("fields.full_name_ar"), { dir: "rtl", lang: "ar" })}
            {field("email", tu("fields.email"), { type: "email", autoComplete: "username", className: "ltr h-touch" })}
            {field("password", t("password"), { type: "password", autoComplete: "new-password" }, ta("passwordPolicy"))}
            {field("confirm", t("confirmPassword"), { type: "password", autoComplete: "new-password" })}
          </Section>
          <Section title={ta("privacy.title")}>
            {notice.data ? <PrivacyText notice={notice.data} /> : <LoadingState rows={2} />}
            <CheckboxField id="setup-ack" label={ta("privacy.acknowledge")} error={errors.ack}>
              <Checkbox checked={ack} onChange={(e) => setAck(e.target.checked)} />
            </CheckboxField>
          </Section>
          <MutationError error={run.error} />
          <Button type="submit" size="lg" disabled={run.isPending || !notice.data} data-testid="setup-submit">
            {run.isPending ? t("submitting") : t("submit")}
          </Button>
          <p className="text-xs text-muted-foreground">{t("after")}</p>
        </form>
      </CardContent>
    </Card>
  );
}
