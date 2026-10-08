"use client";
import { Lock, Plus, ShieldAlert, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Fragment, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCertCatalogue, useCertRefresh, useCertSettings, useHookPolicy, useHookReadiness } from "@/lib/api/cert";
import { TRADES } from "@/lib/access-enums";
import { CERT_LEVELS, EQUIPMENT_CERT_CATEGORIES, LIFTING_GEAR_COLOURS } from "@/lib/cert-enums";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { CertSetupSubNav, HookSeverity, HookStageBadge, Tick, UserName } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ───────────── Phase 4 settings (§3.17) ───────────── */

export function CertSettingsPage() {
  return <ProjectGate>{(p) => <CertSettings project={p} />}</ProjectGate>;
}

type NumKey =
  | "unverified_acceptance_hours"
  | "verification_due_days"
  | "defect_b_max_days"
  | "defect_b_default_days"
  | "scaffold_inspection_interval_days"
  | "arrival_inspection_hours"
  | "rigger_level_critical_min"
  | "hook_transition_days"
  | "hook_critical_transition_days"
  | "dangerous_defect_warning_count"
  | "ban_review_months"
  | "cert_scan_retention_years";
type DecKey = "scaffold_design_height_m" | "equipment_cert_warning_pct" | "personnel_cert_warning_pct" | "scaffold_tag_warning_pct";

const NUM_GROUPS: { title: "groupVerification" | "groupDefects" | "groupHooks" | "groupPersonnel" | "groupWarnings"; keys: { k: NumKey | DecKey; range: string; decimal?: boolean }[] }[] = [
  { title: "groupVerification", keys: [{ k: "unverified_acceptance_hours", range: "0–24" }, { k: "verification_due_days", range: "1–14" }] },
  {
    title: "groupDefects",
    keys: [
      { k: "defect_b_max_days", range: "1–30" },
      { k: "defect_b_default_days", range: "1–30" },
      { k: "arrival_inspection_hours", range: "1–24" },
      { k: "scaffold_inspection_interval_days", range: "1–7" },
      { k: "scaffold_design_height_m", range: "6.00–20.00", decimal: true },
    ],
  },
  { title: "groupHooks", keys: [{ k: "hook_transition_days", range: "0–30" }, { k: "hook_critical_transition_days", range: "0–7" }] },
  {
    title: "groupPersonnel",
    keys: [
      { k: "rigger_level_critical_min", range: "1–3" },
      { k: "ban_review_months", range: "1–12" },
      { k: "cert_scan_retention_years", range: "1–10" },
    ],
  },
  {
    title: "groupWarnings",
    keys: [
      { k: "equipment_cert_warning_pct", range: "80.0–100.0", decimal: true },
      { k: "personnel_cert_warning_pct", range: "80.0–100.0", decimal: true },
      { k: "scaffold_tag_warning_pct", range: "80.0–100.0", decimal: true },
      { k: "dangerous_defect_warning_count", range: "1–20" },
    ],
  },
];

function CertSettings({ project }: { project: Project }) {
  const t = useTranslations("certSettings");
  const me = useMeData();
  const q = useCertSettings(project.id);
  const cat = useCertCatalogue(project.id);
  const editable = canWrite(me, "cert_settings.edit", project.id);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <CertSetupSubNav />
      {q.isLoading || cat.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data && cat.data ? (
        <SettingsForm key={q.data.updated_at ?? "x"} project={project} s={q.data} catalogue={cat.data} editable={editable} />
      ) : null}
    </div>
  );
}

function SettingsForm({ project, s, catalogue, editable }: { project: Project; s: S["CertSettingsRead"]; catalogue: S["CertCatalogue"]; editable: boolean }) {
  const t = useTranslations("certSettings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const init = useMemo(() => {
    const v: Record<string, string> = {};
    for (const g of NUM_GROUPS) for (const x of g.keys) v[x.k] = String(s[x.k] ?? "");
    return v;
  }, [s]);
  const [nums, setNums] = useState<Record<string, string>>(init);
  const [requireClient, setRequireClient] = useState(s.require_client_approved_tpi);
  const [intervals, setIntervals] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(s.equipment_interval_months as Record<string, number>).map(([k, v]) => [k, String(v)])));
  const [caps, setCaps] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(s.personnel_cert_cap_months as Record<string, number>).map(([k, v]) => [k, String(v)])));
  const [trades, setTrades] = useState<Record<string, string>>({ ...(s.trade_cert_requirements as Record<string, string>) });
  const [critical, setCritical] = useState<string[]>(s.hook_critical_codes);
  const [colour, setColour] = useState<S["ColourScheme"]>({ enabled: s.lifting_gear_colour_scheme.enabled, periods: s.lifting_gear_colour_scheme.periods });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [impact, setImpact] = useState<S["ClientApprovalImpactItem"][] | null>(null);
  const typeLabel = (code: string) => {
    const x = catalogue.cert_types.find((c) => c.code === code);
    return x ? (locale === "ar" ? x.label_ar : x.label_en) : code;
  };
  const intDefaults = s.equipment_interval_defaults as Record<string, number>;
  const capDefaults = s.personnel_cert_cap_defaults as Record<string, number>;
  const hookCodes = [...new Set([...catalogue.personnel_hook_codes, ...catalogue.equipment_hook_codes])].sort();

  function buildBody(): S["CertSettingsUpdate"] {
    const body: Record<string, unknown> = {};
    for (const g of NUM_GROUPS)
      for (const x of g.keys) {
        if (nums[x.k] === init[x.k]) continue;
        body[x.k] = x.decimal ? nums[x.k] : Number(nums[x.k]);
      }
    if (requireClient !== s.require_client_approved_tpi) body.require_client_approved_tpi = requireClient;
    const iv = Object.fromEntries(Object.entries(intervals).map(([k, v]) => [k, Number(v)]));
    if (JSON.stringify(iv) !== JSON.stringify(s.equipment_interval_months)) body.equipment_interval_months = iv;
    const cp = Object.fromEntries(Object.entries(caps).map(([k, v]) => [k, Number(v)]));
    if (JSON.stringify(cp) !== JSON.stringify(s.personnel_cert_cap_months)) body.personnel_cert_cap_months = cp;
    const tr = Object.fromEntries(Object.entries(trades).filter(([, v]) => v));
    if (JSON.stringify(tr) !== JSON.stringify(s.trade_cert_requirements)) body.trade_cert_requirements = tr;
    if (JSON.stringify([...critical].sort()) !== JSON.stringify([...s.hook_critical_codes].sort())) body.hook_critical_codes = critical;
    if (JSON.stringify(colour) !== JSON.stringify({ enabled: s.lifting_gear_colour_scheme.enabled, periods: s.lifting_gear_colour_scheme.periods })) body.lifting_gear_colour_scheme = colour;
    return body as S["CertSettingsUpdate"];
  }
  const body = buildBody();
  const dirty = Object.keys(body).length > 0;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.PATCH("/api/v1/projects/{project_id}/cert-settings", { params: { path: { project_id: project.id } }, body }));
      toast.success(t("saved"));
      setImpact(r.client_approval_impact && r.client_approval_impact.length ? r.client_approval_impact : null);
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="cert-settings">
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      {impact ? (
        <Alert tone="warning" data-testid="client-approval-impact">
          <p className="font-medium">{t("impactTitle", { n: impact.length })}</p>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {impact.map((x) => (
              <li key={x.certificate_id}>
                <Link href={x.cert_kind === "equipment" ? `/equipment-certificates/${x.certificate_id}` : `/personnel-certificates/${x.certificate_id}`} className="text-primary hover:underline">
                  <Code>{x.cert_no}</Code>
                </Link>{" "}
                · {x.tpi_code} · {x.subject_ref} · {x.code} — {t("notInForceFrom", { d: date(x.not_in_force_from) })}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupTpi")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Tick id="cs-require-client" label={t("require_client_approved_tpi")} checked={requireClient} onChange={setRequireClient} disabled={!editable || s.require_client_approved_tpi} />
          <p className="mt-1 text-xs text-muted-foreground">{t("requireClientHint")}</p>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {NUM_GROUPS.map((g) => (
          <Card key={g.title}>
            <CardHeader>
              <CardTitle className="text-base">{t(g.title)}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              {g.keys.map((x) => (
                <FormField key={x.k} id={`cs-${x.k}`} label={t(x.k)} hint={t("allowed", { range: x.range })}>
                  <Input
                    id={`cs-${x.k}`}
                    inputMode={x.decimal ? "decimal" : "numeric"}
                    dir="ltr"
                    value={nums[x.k] ?? ""}
                    disabled={!editable}
                    onChange={(e) => setNums({ ...nums, [x.k]: e.target.value.replace(x.decimal ? /[^\d.]/g : /\D/g, "") })}
                    data-testid={`cs-${x.k}`}
                  />
                </FormField>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("hook_critical_codes")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{t("criticalHint")}</p>
          <MultiSelect
            id="cs-critical"
            label={t("hook_critical_codes")}
            options={hookCodes.map((c) => ({ value: c, label: c, disabled: s.hook_critical_codes.includes(c) }))}
            value={critical}
            onChange={(v) => setCritical([...new Set([...s.hook_critical_codes, ...v])])}
          />
          <div className="flex flex-wrap gap-1">
            {critical.map((c) => (
              <Badge key={c} tone="neutral">
                <Lock className="size-3" aria-hidden /> {c}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("equipment_interval_months")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-2 text-xs text-muted-foreground">{t("shortenOnly")}</p>
            <Table>
              <THead>
                <TR>
                  <TH>{t("category")}</TH>
                  <TH>{t("default")}</TH>
                  <TH>{t("months")}</TH>
                </TR>
              </THead>
              <TBody>
                {Object.keys(intDefaults).map((k) => (
                  <TR key={k}>
                    <TD label={t("category")}>{te.has(`eqc.${k as S["EquipmentCertCategory"]}`) ? te(`eqc.${k as S["EquipmentCertCategory"]}`) : k}</TD>
                    <TD label={t("default")}>{intDefaults[k]}</TD>
                    <TD label={t("months")}>
                      <Input aria-label={t("months")} className="w-20" dir="ltr" inputMode="numeric" disabled={!editable} value={intervals[k] ?? ""} onChange={(e) => setIntervals({ ...intervals, [k]: e.target.value.replace(/\D/g, "") })} data-testid={`cs-int-${k}`} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("personnel_cert_cap_months")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-2 text-xs text-muted-foreground">{t("shortenOnlyCap")}</p>
            <Table>
              <THead>
                <TR>
                  <TH>{t("certType")}</TH>
                  <TH>{t("default")}</TH>
                  <TH>{t("months")}</TH>
                </TR>
              </THead>
              <TBody>
                {Object.keys(capDefaults).map((k) => (
                  <TR key={k}>
                    <TD label={t("certType")}>
                      <Code>{k}</Code> <span className="text-muted-foreground">{typeLabel(k)}</span>
                    </TD>
                    <TD label={t("default")}>{capDefaults[k]}</TD>
                    <TD label={t("months")}>
                      <Input aria-label={t("months")} className="w-20" dir="ltr" inputMode="numeric" disabled={!editable} value={caps[k] ?? ""} onChange={(e) => setCaps({ ...caps, [k]: e.target.value.replace(/\D/g, "") })} data-testid={`cs-cap-${k}`} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("trade_cert_requirements")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{t("tradeHint")}</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {TRADES.map((tr) => {
              const locked = !!(s.trade_cert_requirements as Record<string, string>)[tr];
              return (
                <FormField key={tr} id={`cs-trade-${tr}`} label={te(`trade.${tr}`)}>
                  <Select id={`cs-trade-${tr}`} value={trades[tr] ?? ""} disabled={!editable || locked} onChange={(e) => setTrades({ ...trades, [tr]: e.target.value })}>
                    <option value="">{t("noRequirement")}</option>
                    {catalogue.cert_types.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.code}
                      </option>
                    ))}
                  </Select>
                </FormField>
              );
            })}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("lifting_gear_colour_scheme")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Tick id="cs-colour-enabled" label={t("colourEnabled")} checked={colour.enabled} disabled={!editable} onChange={(v) => setColour({ ...colour, enabled: v })} />
          {colour.enabled ? (
            <>
              {(colour.periods ?? []).map((p, i) => (
                <div key={i} className="flex flex-wrap items-end gap-2">
                  <FormField id={`cs-cp-from-${i}`} label={t("fromMmdd")}>
                    <Input id={`cs-cp-from-${i}`} dir="ltr" className="w-24" placeholder="01-01" value={p.from_mmdd} disabled={!editable} onChange={(e) => setColour({ ...colour, periods: (colour.periods ?? []).map((x, j) => (j === i ? { ...x, from_mmdd: e.target.value } : x)) })} />
                  </FormField>
                  <FormField id={`cs-cp-to-${i}`} label={t("toMmdd")}>
                    <Input id={`cs-cp-to-${i}`} dir="ltr" className="w-24" placeholder="03-31" value={p.to_mmdd} disabled={!editable} onChange={(e) => setColour({ ...colour, periods: (colour.periods ?? []).map((x, j) => (j === i ? { ...x, to_mmdd: e.target.value } : x)) })} />
                  </FormField>
                  <FormField id={`cs-cp-colour-${i}`} label={t("colour")}>
                    <Select id={`cs-cp-colour-${i}`} value={p.colour} disabled={!editable} onChange={(e) => setColour({ ...colour, periods: (colour.periods ?? []).map((x, j) => (j === i ? { ...x, colour: e.target.value as S["LiftingGearColour"] } : x)) })}>
                      {LIFTING_GEAR_COLOURS.map((c) => (
                        <option key={c} value={c}>
                          {te(`liftingGearColour.${c}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  {editable ? (
                    <Button variant="ghost" size="sm" onClick={() => setColour({ ...colour, periods: (colour.periods ?? []).filter((_, j) => j !== i) })}>
                      {tc("remove")}
                    </Button>
                  ) : null}
                </div>
              ))}
              {editable ? (
                <Button variant="outline" size="sm" className="self-start" onClick={() => setColour({ ...colour, periods: [...(colour.periods ?? []), { from_mmdd: "01-01", to_mmdd: "03-31", colour: "red" }] })}>
                  <Plus aria-hidden />
                  {t("addPeriod")}
                </Button>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        {t("alertSchedule", { days: s.alert_schedule_long_days.join(", ") })}
        {s.updated_at ? (
          <>
            {" · "}
            {t("lastUpdated", { at: dateTime(s.updated_at) })} <UserName u={s.updated_by} />
          </>
        ) : null}
      </p>
      <MutationError error={error} />
      {editable ? (
        <div className="sticky bottom-0 flex justify-end gap-2 border-t bg-background py-3">
          <Button onClick={() => void save()} disabled={!dirty || busy} data-testid="save-cert-settings">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/* ───────────── catalogue: categories + personnel cert types ───────────── */

export function CertCataloguePage() {
  return <ProjectGate>{(p) => <CertCatalogue project={p} />}</ProjectGate>;
}

function CertCatalogue({ project }: { project: Project }) {
  const t = useTranslations("certCatalogue");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const q = useCertCatalogue(project.id);
  const editable = canWrite(me, "cert_settings.edit", project.id);
  const [dialog, setDialog] = useState<S["CertTypeInfo"] | "new" | null>(null);
  const c = q.data;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          editable ? (
            <Button onClick={() => setDialog("new")} data-testid="new-cert-type">
              <Plus aria-hidden />
              {t("newType")}
            </Button>
          ) : null
        }
      />
      <CertSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : c ? (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("certTypes")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table data-testid="cert-types">
                <THead>
                  <TR>
                    <TH>{t("code")}</TH>
                    <TH>{t("label")}</TH>
                    <TH>{t("cap")}</TH>
                    <TH>{t("scope")}</TH>
                    <TH>{t("levels")}</TH>
                    <TH>{t("flags")}</TH>
                    {editable ? <TH /> : null}
                  </TR>
                </THead>
                <TBody>
                  {c.cert_types.map((x) => (
                    <TR key={x.code} data-testid={`cert-type-${x.code}`}>
                      <TD label={t("code")}>
                        <Code>{x.code}</Code>
                      </TD>
                      <TD label={t("label")}>{locale === "ar" ? x.label_ar : x.label_en}</TD>
                      <TD label={t("cap")}>
                        {t("monthsN", { n: x.cap_months })}
                        {x.cap_months !== x.default_cap_months ? <span className="text-xs text-muted-foreground"> ({t("defaultN", { n: x.default_cap_months })})</span> : null}
                      </TD>
                      <TD label={t("scope")} className="text-xs">
                        {x.scope_categories_allowed.map((s) => te(`eqc.${s}`)).join(" · ") || "—"}
                      </TD>
                      <TD label={t("levels")} className="text-xs">
                        {x.levels_allowed.join(" / ") || "—"}
                        {x.level_required ? ` (${t("required")})` : ""}
                      </TD>
                      <TD label={t("flags")}>
                        <div className="flex flex-wrap gap-1">
                          {x.critical ? <Badge tone="danger">{t("critical")}</Badge> : null}
                          {x.seeded ? <Badge tone="neutral">{t("seeded")}</Badge> : null}
                          {x.satisfies.length ? <Badge tone="neutral">{t("satisfies", { codes: x.satisfies.join(", ") })}</Badge> : null}
                        </div>
                      </TD>
                      {editable ? (
                        <TD>
                          <Button size="sm" variant="ghost" onClick={() => setDialog(x)} data-testid={`edit-cert-type-${x.code}`}>
                            {t("editLabels")}
                          </Button>
                        </TD>
                      ) : null}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("categories")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table data-testid="eq-categories">
                <THead>
                  <TR>
                    <TH>{t("category")}</TH>
                    <TH>{t("interval")}</TH>
                    <TH>{t("hookCode")}</TH>
                    <TH>{t("operatorCode")}</TH>
                    <TH>{t("subtypes")}</TH>
                    <TH>{t("configRule")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {c.equipment_categories.map((x) => (
                    <TR key={x.code}>
                      <TD label={t("category")}>{locale === "ar" ? x.label_ar : x.label_en}</TD>
                      <TD label={t("interval")}>
                        {x.interval_months != null ? t("monthsN", { n: x.interval_months }) : "—"}
                        {x.default_interval_months != null && x.interval_months !== x.default_interval_months ? <span className="text-xs text-muted-foreground"> ({t("defaultN", { n: x.default_interval_months })})</span> : null}
                      </TD>
                      <TD label={t("hookCode")}>
                        <Code>{x.hook_code}</Code>
                      </TD>
                      <TD label={t("operatorCode")}>{x.operator_code ? <Code>{x.operator_code}</Code> : "—"}</TD>
                      <TD label={t("subtypes")} className="text-xs">
                        {x.subtypes.map((s) => te(`eqSubtype.${s}`)).join(" · ") || "—"}
                        {x.subtype_required ? ` (${t("required")})` : ""}
                      </TD>
                      <TD label={t("configRule")}>{x.configuration_change_rule ? t("yes") : "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("hookCodes")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="mb-1 font-medium">{t("personnelCodes")}</p>
                <div className="flex flex-wrap gap-1">
                  {c.personnel_hook_codes.map((x) => (
                    <Badge key={x} tone={c.critical_codes.includes(x) ? "danger" : "neutral"}>
                      {x}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1 font-medium">{t("equipmentCodes")}</p>
                <div className="flex flex-wrap gap-1">
                  {c.equipment_hook_codes.map((x) => (
                    <Badge key={x} tone={c.critical_codes.includes(x) ? "danger" : "neutral"}>
                      {x}
                    </Badge>
                  ))}
                </div>
              </div>
              <p className="text-xs text-muted-foreground sm:col-span-2">{t("criticalLegend")}</p>
            </CardContent>
          </Card>
        </div>
      ) : (
        <EmptyState />
      )}
      {dialog ? <CertTypeDialog item={dialog === "new" ? null : dialog} onClose={() => setDialog(null)} /> : null}
    </div>
  );
}

function CertTypeDialog({ item, onClose }: { item: S["CertTypeInfo"] | null; onClose: () => void }) {
  const t = useTranslations("certCatalogue");
  const te = useTranslations("enums");
  const refresh = useCertRefresh();
  const [code, setCode] = useState(item?.code ?? "");
  const [en, setEn] = useState(item?.label_en ?? "");
  const [ar, setAr] = useState(item?.label_ar ?? "");
  const [cap, setCap] = useState("24");
  const [scope, setScope] = useState<S["EquipmentCertCategory"][]>([]);
  const [levels, setLevels] = useState<S["CertLevel"][]>([]);
  const codeOk = /^[A-Z][A-Z0-9-]{1,39}$/.test(code);
  return (
    <StepDialog
      title={item ? t("editLabelsTitle", { code: item.code }) : t("newType")}
      description={item ? undefined : t("newTypeHint")}
      confirmLabel={item ? t("saveLabels") : t("create")}
      disabled={!en.trim() || !ar.trim() || (!item && (!codeOk || !Number(cap)))}
      testId="cert-type-confirm"
      wide
      onConfirm={async () => {
        if (item) await unwrap(api.PATCH("/api/v1/cert-types/{code}", { params: { path: { code: item.code } }, body: { label_en: en.trim(), label_ar: ar.trim() } }));
        else await unwrap(api.POST("/api/v1/cert-types", { body: { code, label_en: en.trim(), label_ar: ar.trim(), cap_months: Number(cap), scope_categories_allowed: scope, levels_allowed: levels } }));
        toast.success(t("saved"));
        refresh();
      }}
      onClose={onClose}
    >
      {!item ? (
        <FormField id="ct-code" label={t("code")} required hint={t("codeHint")}>
          <Input id="ct-code" dir="ltr" value={code} onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ""))} data-testid="ct-code" />
        </FormField>
      ) : null}
      <FormField id="ct-en" label={t("labelEn")} required>
        <Input id="ct-en" dir="ltr" value={en} onChange={(e) => setEn(e.target.value)} data-testid="ct-en" />
      </FormField>
      <FormField id="ct-ar" label={t("labelAr")} required>
        <Input id="ct-ar" dir="rtl" value={ar} onChange={(e) => setAr(e.target.value)} data-testid="ct-ar" />
      </FormField>
      {!item ? (
        <>
          <FormField id="ct-cap" label={t("cap")} required hint={t("capHint")}>
            <Input id="ct-cap" dir="ltr" inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value.replace(/\D/g, ""))} data-testid="ct-cap" />
          </FormField>
          <MultiSelect id="ct-scope" label={t("scope")} options={EQUIPMENT_CERT_CATEGORIES.map((c) => ({ value: c, label: te(`eqc.${c}`) }))} value={scope} onChange={(v) => setScope(v as S["EquipmentCertCategory"][])} />
          <CheckboxGroup id="ct-levels" legend={t("levels")} options={CERT_LEVELS.map((l) => ({ value: l, label: te(`certLevel.${l}`) }))} value={levels} onChange={(v) => setLevels(v as S["CertLevel"][])} />
        </>
      ) : null}
    </StepDialog>
  );
}

/* ───────────── hook policy (§3.14, §4.8, HK4) + readiness (HK4-7) ───────────── */

export function HookPolicyPage() {
  return <ProjectGate>{(p) => <HookPolicy project={p} />}</ProjectGate>;
}

const P4_KINDS = ["equipment_certificate", "personnel_certificate"] as const;
/** Kinds shown on the hook policy page: Phase 4 kinds plus training_course (5-training HK5-1). */
const POLICY_KINDS = [...P4_KINDS, "training_course"] as const;

function HookPolicy({ project }: { project: Project }) {
  const t = useTranslations("hookPolicy");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const q = useHookPolicy(project.id);
  const refresh = useCertRefresh();
  const editable = canWrite(me, "cert_settings.edit", project.id);
  const trainingEditable = canWrite(me, "training_settings.edit", project.id);
  const [enable, setEnable] = useState(false);
  const [regOn, setRegOn] = useState("");
  const p = q.data;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          p && !p.enabled && editable ? (
            <Button onClick={() => setEnable(true)} data-testid="enable-phase4">
              <ShieldCheck aria-hidden />
              {t("enable")}
            </Button>
          ) : null
        }
      />
      <CertSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : p ? (
        <div className="flex flex-col gap-4" data-testid="hook-policy">
          <Alert tone="info">
            <div className="flex flex-wrap items-center gap-2">
              <HookSeverity hardStop />
              <span>{t("hardStopLegend")}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <HookSeverity warn />
              <span>{t("warnLegend")}</span>
            </div>
          </Alert>
          {!p.enabled ? <Alert tone="warning">{t("notEnabled")}</Alert> : null}
          {!p.training_enabled ? (
            <Alert tone="info" data-testid="training-hooks-off">
              {t("trainingNotEnabled")}{" "}
              <Link href="/training-settings" className="text-primary hover:underline">
                {t("openTrainingSettings")}
              </Link>
            </Alert>
          ) : null}
          <div className="grid gap-4 xl:grid-cols-2">
            {p.kinds
              .filter((k) => (POLICY_KINDS as readonly string[]).includes(k.kind))
              .map((k) => (
                <HookKindCard key={k.kind} project={project} k={k} editable={k.kind === "training_course" ? trainingEditable && !!p.training_enabled : editable && p.enabled} asOf={p.as_of} />
              ))}
          </div>
          {p.enabled || p.training_enabled || trainingEditable ? <Readiness project={project} kinds={p.enabled ? POLICY_KINDS : ["training_course"]} /> : null}
          <p className="text-xs text-muted-foreground">{t("asOf", { d: date(p.as_of) })}</p>
        </div>
      ) : null}
      {enable ? (
        <StepDialog
          title={t("enableTitle")}
          description={t("enableHint")}
          confirmLabel={t("enable")}
          testId="enable-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/hook-policy/enable", { params: { path: { project_id: project.id } }, body: { registered_on: regOn || null } }));
            toast.success(t("enabled"));
            refresh();
          }}
          onClose={() => setEnable(false)}
        >
          <FormField id="hp-reg" label={t("registeredOn")} hint={t("registeredOnHint")}>
            <Input id="hp-reg" type="date" dir="ltr" value={regOn} onChange={(e) => setRegOn(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

function HookKindCard({ project, k, editable, asOf }: { project: Project; k: S["HookPolicyStateRead"]; editable: boolean; asOf: string }) {
  const t = useTranslations("hookPolicy");
  const te = useTranslations("enums");
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const [sw, setSw] = useState(false);
  const [swAll, setSwAll] = useState(false);
  const [swCodes, setSwCodes] = useState<string[]>([]);
  const [defer, setDefer] = useState(false);
  const [newDate, setNewDate] = useState("");
  const [reason, setReason] = useState("");
  const notBlocked = k.codes.filter((c) => c.policy !== "block");
  const maxDefer = k.general_block_from ? addDays(k.general_block_from, 30) : null;
  return (
    <Card data-testid={`hook-kind-${k.kind}`} data-stage={k.stage}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {te(`hookKind.${k.kind}`)} <HookStageBadge stage={k.stage} />
        </CardTitle>
        {editable ? (
          <div className="flex flex-wrap gap-2">
            {notBlocked.length ? (
              <Button size="sm" variant="destructive-outline" onClick={() => setSw(true)} data-testid={`switch-${k.kind}`}>
                <ShieldAlert aria-hidden />
                {t("switchEarly")}
              </Button>
            ) : null}
            {!k.deferral_used && k.stage !== "block" && k.general_block_from && k.general_block_from > asOf ? (
              <Button size="sm" variant="outline" onClick={() => setDefer(true)} data-testid={`defer-${k.kind}`}>
                {t("defer")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">{t("registeredOn")}</dt>
            <dd>{k.provider_registered_on ? date(k.provider_registered_on) : "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t("criticalBlockFrom")}</dt>
            <dd data-testid={`critical-from-${k.kind}`}>{k.critical_block_from ? date(k.critical_block_from) : "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t("generalBlockFrom")}</dt>
            <dd data-testid={`general-from-${k.kind}`}>{k.general_block_from ? date(k.general_block_from) : "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t("nextBlock")}</dt>
            <dd>{k.next_block_date ? date(k.next_block_date) : "—"}</dd>
          </div>
        </dl>
        {k.deferral ? (
          <p className="text-xs" data-testid={`deferral-${k.kind}`}>
            {t("deferred", { from: date(k.deferral.original_date), to: date(k.deferral.new_date) })} · <UserName u={k.deferral.by} /> · {dateTime(k.deferral.at)} — {k.deferral.reason}
          </p>
        ) : null}
        {k.early_switches.map((e, i) => (
          <p key={i} className="text-xs">
            {t("switchedEarly", { at: dateTime(e.at) })} · <UserName u={e.by} /> — {e.all_codes ? t("allCodes") : e.codes.join(", ")}
          </p>
        ))}
        <Table>
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("policy")}</TH>
              <TH>{t("blockFrom")}</TH>
            </TR>
          </THead>
          <TBody>
            {k.codes.map((c) => (
              <TR key={c.code} data-testid={`hook-code-${c.code}`} data-policy={c.policy}>
                <TD label={t("code")}>
                  <span className="inline-flex flex-wrap items-center gap-1">
                    <Code>{c.code}</Code>
                    {c.critical ? <Badge tone="danger">{t("critical")}</Badge> : null}
                    {!c.implemented ? <Badge tone="neutral">{t("notImplemented")}</Badge> : null}
                  </span>
                </TD>
                <TD label={t("policy")}>
                  {c.policy === "block" ? (
                    <span className="inline-flex items-center gap-1 font-medium text-danger">
                      <Lock className="size-3.5" aria-hidden />
                      {te(`hookCodePolicy.${c.policy}`)}
                    </span>
                  ) : (
                    <span className="text-warning">{te(`hookCodePolicy.${c.policy}`)}</span>
                  )}
                  {c.switched_early_at ? <span className="block text-xs text-muted-foreground">{t("switchedEarly", { at: dateTime(c.switched_early_at) })}</span> : null}
                </TD>
                <TD label={t("blockFrom")}>{c.block_from ? date(c.block_from) : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
      {sw ? (
        <StepDialog
          title={t("switchTitle")}
          description={t("switchHint")}
          warning={t("switchWarning")}
          confirmLabel={t("switchConfirm")}
          destructive
          testId="switch-confirm"
          disabled={!swAll && !swCodes.length}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/hook-policy/{kind}/switch", { params: { path: { project_id: project.id, kind: k.kind } }, body: { all_codes: swAll, codes: swAll ? [] : swCodes, policy: "block" } }));
            toast.success(t("switched"));
            refresh();
          }}
          onClose={() => setSw(false)}
        >
          <Tick id="sw-all" label={t("allCodes")} checked={swAll} onChange={setSwAll} />
          {!swAll ? <CheckboxGroup id="sw-codes" legend={t("codes")} options={notBlocked.map((c) => ({ value: c.code, label: c.code }))} value={swCodes} onChange={setSwCodes} /> : null}
        </StepDialog>
      ) : null}
      {defer ? (
        <StepDialog
          title={t("deferTitle")}
          description={t("deferHint", { max: maxDefer ? date(maxDefer) : "—" })}
          confirmLabel={t("defer")}
          testId="defer-confirm"
          disabled={!newDate || reason.trim().length < 30}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/hook-policy/{kind}/deferral", { params: { path: { project_id: project.id, kind: k.kind } }, body: { new_date: newDate, reason: reason.trim() } }));
            toast.success(t("deferredOk"));
            refresh();
          }}
          onClose={() => setDefer(false)}
        >
          <FormField id="df-date" label={t("newDate")} required>
            <Input id="df-date" type="date" dir="ltr" min={k.general_block_from ?? undefined} max={maxDefer ?? undefined} value={newDate} onChange={(e) => setNewDate(e.target.value)} data-testid="defer-date" />
          </FormField>
          <FormField id="df-reason" label={t("reason")} required hint={t("reasonHint", { n: reason.trim().length })}>
            <Textarea id="df-reason" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} data-testid="defer-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </Card>
  );
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function Readiness({ project, kinds }: { project: Project; kinds: readonly S["HookKind"][] }) {
  const t = useTranslations("hookPolicy");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const { date } = useFormatters(project.id);
  const params = useSearchParams();
  const wanted = params.get("kind") as S["HookKind"] | null;
  const [kind, setKind] = useState<S["HookKind"]>(wanted && kinds.includes(wanted) ? wanted : (kinds[0] ?? "equipment_certificate"));
  const [onDate, setOnDate] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const q = useHookReadiness(project.id, { kind, on_date: onDate || null });
  const r = q.data;
  const subjectHref = (s: S["ReadinessSubject"]) =>
    s.subject_type === "equipment" ? `/equipment/${s.subject_id}` : s.subject_type === "scaffold" ? `/scaffolds/${s.subject_id}` : s.subject_type === "worker" ? `/workers/${s.subject_id}` : null;
  return (
    <Card data-testid="hook-readiness">
      <CardHeader className="flex flex-col gap-3">
        <CardTitle className="text-base">{t("readiness")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("readinessHint")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <FormField id="rd-kind" label={t("kind")}>
            <Select id="rd-kind" value={kind} onChange={(e) => setKind(e.target.value as S["HookKind"])} data-testid="rd-kind">
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {te(`hookKind.${k}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="rd-date" label={t("affectedOn")}>
            <Input id="rd-date" type="date" dir="ltr" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </FormField>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {q.isLoading ? (
          <LoadingState />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : r ? (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>{t("code")}</TH>
                  <TH>{t("policy")}</TH>
                  <TH>{t("inForceOfRequired")}</TH>
                  <TH>{t("readinessPct")}</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {r.codes.map((c) => (
                  <Fragment key={c.code}>
                    <TR data-testid={`readiness-${c.code}`}>
                      <TD label={t("code")}>
                        <span className="inline-flex items-center gap-1">
                          <Code>{c.code}</Code>
                          {c.critical ? <Badge tone="danger">{t("critical")}</Badge> : null}
                        </span>
                      </TD>
                      <TD label={t("policy")}>
                        {te(`hookCodePolicy.${c.policy}`)}
                        {c.block_from ? <span className="block text-xs text-muted-foreground">{t("fromDate", { d: date(c.block_from) })}</span> : null}
                      </TD>
                      <TD label={t("inForceOfRequired")}>
                        {c.in_force} / {c.required}
                      </TD>
                      <TD label={t("readinessPct")}>
                        <span className={c.readiness_pct != null && Number(c.readiness_pct) < 100 ? "font-medium text-warning" : undefined}>{c.readiness_display}</span>
                      </TD>
                      <TD>
                        {c.not_met.length ? (
                          <Button size="sm" variant="ghost" onClick={() => setOpen(open === c.code ? null : c.code)} aria-expanded={open === c.code}>
                            {t("notMetN", { n: c.not_met.length })}
                          </Button>
                        ) : null}
                      </TD>
                    </TR>
                    {open === c.code ? (
                      <TR>
                        <TD colSpan={5}>
                          <ul className="flex flex-col gap-1 text-sm">
                            {c.not_met.map((s) => {
                              const href = subjectHref(s);
                              return (
                                <li key={s.subject_id} className="flex flex-wrap items-center gap-2">
                                  {href ? (
                                    <Link href={href} className="text-primary hover:underline">
                                      <Code>{s.ref}</Code>
                                    </Link>
                                  ) : (
                                    <Code>{s.ref}</Code>
                                  )}
                                  {s.label ? <span>{s.label}</span> : null}
                                  <span className="text-muted-foreground">{te.has(`hookReason.${s.reason_code}`) ? te(`hookReason.${s.reason_code}` as never) : s.reason_code}</span>
                                  <HookSeverity hardStop={s.hard_stop} warn={!s.hard_stop} />
                                </li>
                              );
                            })}
                          </ul>
                        </TD>
                      </TR>
                    ) : null}
                  </Fragment>
                ))}
              </TBody>
            </Table>
            <div>
              <p className="mb-2 font-medium">{t("affected")}</p>
              {r.affected.length ? (
                <ul className="flex flex-col gap-2 text-sm" data-testid="readiness-affected">
                  {r.affected.map((a) => (
                    <li key={a.on_date}>
                      <span className="font-medium">{date(a.on_date)}</span>:{" "}
                      {a.permits.map((p) => (
                        <Link key={p.id} href={`/permits/${p.id}`} className="me-2 text-primary hover:underline">
                          <Code>{p.permit_no}</Code>
                        </Link>
                      ))}
                      {a.wap_nos.map((w) => (
                        <Code key={w}>{w}</Code>
                      ))}
                      {a.gate_codes.length ? <span className="ms-2 text-muted-foreground">{t("gates", { codes: a.gate_codes.join(", ") })}</span> : null}
                      {!a.permits.length && !a.wap_nos.length && !a.gate_codes.length ? <span className="text-muted-foreground">{tc("none")}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">{tc("none")}</p>
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
