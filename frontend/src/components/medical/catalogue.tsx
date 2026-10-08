"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { useUserOptions } from "@/components/common/pickers";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useContractors, useProjects } from "@/lib/api/queries";
import { mk, useFitnessCodes, useMedicalExaminers, useMedicalProvider, useMedicalProviderAffected, useMedicalProviders, useMedicalRefresh } from "@/lib/api/medical";
import { useCurrentProject } from "@/lib/current-project";
import { EXAMINER_STATUSES, FITNESS_CATEGORIES, MED_BLACKLIST_SCOPES, MED_PROVIDER_KINDS, MED_PROVIDER_STATUSES, SIGNING_CLASSES, EXAMINER_CLASSES, TYPICAL_TESTS, RESTRICTION_CODES } from "@/lib/med-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ExaminerStatusBadge, MedicalCatalogueSubNav, MedProviderStatusBadge, useMedCaps } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ═════════════ fitness codes (§3.1, MC-1…MC-5) ═════════════ */

export function FitnessCodesPage() {
  const t = useTranslations("medical.codes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { project } = useCurrentProject();
  const caps = useMedCaps();
  const s = useSearchState();
  const inactive = s.get("inactive") === "1";
  const q = useFitnessCodes({ project_id: project?.id ?? null, include_inactive: inactive });
  const qc = useQueryClient();
  const [edit, setEdit] = useState<S["FitnessCodeRead"] | "new" | null>(null);
  const [del, setDel] = useState<S["FitnessCodeRead"] | null>(null);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.codeEdit ? (
            <Button onClick={() => setEdit("new")} data-testid="new-fitness-code">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <MedicalCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="fitness_codes" /> : null}>
        <Tick id="fc-inactive" label={t("showInactive")} checked={inactive} onChange={(v) => s.set({ inactive: v ? "1" : "" })} />
      </ListToolbar>
      {project ? <p className="mb-2 text-xs text-muted-foreground">{t("projectNote", { code: project.code })}</p> : null}
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="fitness-codes-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("category")}</TH>
              <TH>{t("validity")}</TH>
              <TH>{t("examiners")}</TH>
              <TH>{t("providers")}</TH>
              <TH>{t("negatedBy")}</TH>
              <TH>{tc("status")}</TH>
              {caps.codeEdit ? <TH /> : null}
            </TR>
          </THead>
          <TBody>
            {items.map((c) => (
              <TR key={c.code} data-testid="fitness-code-row" data-code={c.code}>
                <TD label={t("code")}>
                  <Code className="font-medium">{c.code}</Code>
                  <span className="block text-sm">{locale === "ar" ? c.name_ar : c.name_en}</span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {c.hook_code ? <Badge tone="info">{t("hookCode")}</Badge> : null}
                    {c.critical_on_project ? <Badge tone="danger">{t("critical")}</Badge> : null}
                  </span>
                </TD>
                <TD label={t("category")}>{te(`fitnessCategory.${c.category}`)}</TD>
                <TD label={t("validity")}>
                  <span data-testid="fc-validity">{t("months", { n: c.validity_months })}</span>
                  {c.effective_validity_months != null && c.effective_validity_months !== c.validity_months ? (
                    <span className="block text-xs text-warning" data-testid="fc-effective">
                      {t("onProject", { n: c.effective_validity_months })}
                    </span>
                  ) : null}
                </TD>
                <TD label={t("examiners")}>
                  <span className="text-sm">{c.examiner_classes.map((x) => te(`examinerClass.${x}`)).join(" · ")}</span>
                </TD>
                <TD label={t("providers")}>
                  <span className="text-sm">{c.provider_kinds.map((x) => te(`medProviderKind.${x}`)).join(" · ")}</span>
                </TD>
                <TD label={t("negatedBy")}>
                  <span className="text-xs">{c.negated_by.map((x) => te(`restriction.${x}`)).join(" · ") || "—"}</span>
                </TD>
                <TD label={tc("status")}>{c.active ? <Badge tone="success">{t("active")}</Badge> : <Badge tone="neutral">{t("inactive")}</Badge>}</TD>
                {caps.codeEdit ? (
                  <TD>
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEdit(c)} aria-label={tc("edit")} data-testid={`edit-fc-${c.code}`}>
                        <Pencil aria-hidden />
                      </Button>
                      {!c.in_use ? (
                        <Button size="sm" variant="ghost" onClick={() => setDel(c)} aria-label={tc("delete")}>
                          <Trash2 aria-hidden />
                        </Button>
                      ) : null}
                    </span>
                  </TD>
                ) : null}
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {edit ? <FitnessCodeDialog code={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} /> : null}
      {del ? (
        <StepDialog
          title={t("deleteTitle", { code: del.code })}
          description={t("deleteHint")}
          confirmLabel={tc("delete")}
          destructive
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/fitness-codes/{code}", { params: { path: { code: del.code } } }));
            await qc.invalidateQueries({ queryKey: ["fitness-codes"] });
            toast.success(tc("saved"));
          }}
          onClose={() => setDel(null)}
        />
      ) : null}
    </div>
  );
}

function FitnessCodeDialog({ code, onClose }: { code?: S["FitnessCodeRead"]; onClose: () => void }) {
  const t = useTranslations("medical.codes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const [c, setC] = useState(code?.code ?? "");
  const [nameEn, setNameEn] = useState(code?.name_en ?? "");
  const [nameAr, setNameAr] = useState(code?.name_ar ?? "");
  const [category, setCategory] = useState<S["FitnessCategory"]>(code?.category ?? "task");
  const [validity, setValidity] = useState(String(code?.validity_months ?? 12));
  const [examiners, setExaminers] = useState<S["ExaminerClass"][]>(code?.examiner_classes ?? ["occupational_physician", "physician"]);
  const [kinds, setKinds] = useState<S["MedicalProviderKind"][]>(code?.provider_kinds ?? ["site_clinic", "external_clinic"]);
  const [tests, setTests] = useState<S["TypicalTest"][]>(code?.typical_tests ?? []);
  const [negated, setNegated] = useState<S["RestrictionCode"][]>(code?.negated_by ?? []);
  const [active, setActive] = useState(code?.active ?? true);
  const months = Number(validity);
  const valid = /^[A-Z0-9-]{2,24}$/.test(c) && nameEn.trim() && nameAr.trim() && months >= 1 && months <= 60 && examiners.length > 0 && kinds.length > 0;
  return (
    <StepDialog
      title={code ? t("editTitle", { code: code.code }) : t("new")}
      description={code ? t("tightenOnly") : t("newHint")}
      confirmLabel={tc("save")}
      disabled={!valid}
      wide
      testId="save-fitness-code"
      onConfirm={async () => {
        if (code) {
          await unwrap(
            api.PATCH("/api/v1/fitness-codes/{code}", {
              params: { path: { code: code.code } },
              body: { name_en: nameEn.trim(), name_ar: nameAr.trim(), validity_months: months, examiner_classes: examiners, provider_kinds: kinds, typical_tests: tests, negated_by: negated, active },
            }),
          );
        } else {
          await unwrap(api.POST("/api/v1/fitness-codes", { body: { code: c, name_en: nameEn.trim(), name_ar: nameAr.trim(), category, validity_months: months, examiner_classes: examiners, provider_kinds: kinds, typical_tests: tests, active } }));
        }
        toast.success(tc("saved"));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="fc-code" label={t("code")} required hint={t("codeHint")}>
          <Input value={c} disabled={Boolean(code)} onChange={(e) => setC(e.target.value.toUpperCase())} maxLength={24} className="ltr uppercase" data-testid="fc-code" />
        </FormField>
        <FormField id="fc-category" label={t("category")} required>
          <Select value={category} disabled={Boolean(code)} onChange={(e) => setCategory(e.target.value as S["FitnessCategory"])} data-testid="fc-category">
            {FITNESS_CATEGORIES.map((x) => (
              <option key={x} value={x}>
                {te(`fitnessCategory.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="fc-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" maxLength={150} data-testid="fc-name-en" />
        </FormField>
        <FormField id="fc-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" maxLength={150} data-testid="fc-name-ar" />
        </FormField>
        <FormField id="fc-validity" label={t("validityMonths")} required hint={t("validityHint")}>
          <Input value={validity} onChange={(e) => setValidity(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="ltr" data-testid="fc-validity-input" />
        </FormField>
        {code ? <Tick id="fc-active" label={t("active")} checked={active} onChange={setActive} /> : null}
      </div>
      <CheckboxGroup id="fc-examiners" legend={t("examiners")} required options={SIGNING_CLASSES.map((x) => ({ value: x, label: te(`examinerClass.${x}`) }))} value={examiners} onChange={setExaminers} />
      <CheckboxGroup id="fc-kinds" legend={t("providers")} required options={MED_PROVIDER_KINDS.map((x) => ({ value: x, label: te(`medProviderKind.${x}`) }))} value={kinds} onChange={setKinds} hint={t("contractorClinicHint")} />
      <CheckboxGroup id="fc-tests" legend={t("typicalTests")} hint={t("typicalTestsHint")} columns={2} options={TYPICAL_TESTS.map((x) => ({ value: x, label: te(`typicalTest.${x}`) }))} value={tests} onChange={setTests} />
      {code ? <CheckboxGroup id="fc-negated" legend={t("negatedBy")} hint={t("negatedHint")} options={RESTRICTION_CODES.map((x) => ({ value: x, label: te(`restriction.${x}`) }))} value={negated} onChange={setNegated} /> : null}
    </StepDialog>
  );
}

/* ═════════════ providers (§3.2, §4.1, MP-1…MP-6) ═════════════ */

export function MedicalProvidersPage() {
  const t = useTranslations("medical.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useMedCaps();
  const { date } = useFormatters();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["MedicalProviderStatus"][];
  const kind = s.getAll("kind") as S["MedicalProviderKind"][];
  const [create, setCreate] = useState(false);
  const q = useMedicalProviders({ q: s.get("q") || null, status: status.length ? status : null, kind: kind.length ? kind : null, page, page_size: PAGE_SIZE });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.providerEdit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-med-provider">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <MedicalCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="medical_providers" /> : null}>
        <SearchFilter id="mp-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="mp-status" label={tc("status")} options={MED_PROVIDER_STATUSES.map((x) => ({ value: x, label: te(`medProviderStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="mp-kind" label={t("kind")} options={MED_PROVIDER_KINDS.map((x) => ({ value: x, label: te(`medProviderKind.${x}`) }))} value={kind} onChange={(v) => s.set({ kind: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="med-providers-table">
            <THead>
              <TR>
                <TH>{t("code")}</TH>
                <TH>{t("name")}</TH>
                <TH>{t("kind")}</TH>
                <TH>{t("licence")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="med-provider-row" data-code={p.provider_code}>
                  <TD label={t("code")}>
                    <Link href={`/medical-providers/${p.id}`} className="font-medium text-primary hover:underline">
                      <Code>{p.provider_code}</Code>
                    </Link>
                  </TD>
                  <TD label={t("name")}>{locale === "ar" ? p.legal_name_ar : p.legal_name_en}</TD>
                  <TD label={t("kind")}>{te(`medProviderKind.${p.kind}`)}</TD>
                  <TD label={t("licence")}>
                    <Code>{p.moh_licence_no}</Code>
                    <span className="block text-xs text-muted-foreground">{t("validTo", { d: date(p.licence_valid_until) })}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <MedProviderStatusBadge status={p.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
      {create ? <ProviderDialog onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/** datetime-local value of "now" for "licence checked at" defaults. */
function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function ProviderDialog({ provider, onClose }: { provider?: S["MedicalProviderRead"]; onClose: () => void }) {
  const t = useTranslations("medical.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const contractors = useContractors({ page_size: 200 });
  const projects = useProjects({ page_size: 200 });
  const [code, setCode] = useState(provider?.provider_code ?? "");
  const [kind, setKind] = useState<S["MedicalProviderKind"]>(provider?.kind ?? "external_clinic");
  const [contractor, setContractor] = useState(provider?.contractor_id ?? "");
  const [projectIds, setProjectIds] = useState<string[]>(provider?.project_ids ?? []);
  const [nameEn, setNameEn] = useState(provider?.legal_name_en ?? "");
  const [nameAr, setNameAr] = useState(provider?.legal_name_ar ?? "");
  const [licence, setLicence] = useState(provider?.moh_licence_no ?? "");
  const [validTo, setValidTo] = useState(provider?.licence_valid_until ?? "");
  const [checked, setChecked] = useState(Boolean(provider?.licence_checked_at));
  const [checkedAt, setCheckedAt] = useState(provider?.licence_checked_at ? provider.licence_checked_at.slice(0, 16) : nowLocal());
  const [domains, setDomains] = useState((provider?.verification_domains ?? []).join(", "));
  const [email, setEmail] = useState(provider?.verification_email ?? "");
  const [phone, setPhone] = useState(provider?.verification_phone ?? "");
  const [portal, setPortal] = useState(provider?.verification_portal_url ?? "");
  const domainList = domains
    .split(/[\s,]+/)
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean);
  const valid =
    /^[A-Z0-9-]{2,12}$/.test(code) &&
    nameEn.trim() &&
    nameAr.trim() &&
    licence.trim() &&
    validTo &&
    (kind !== "site_clinic" || projectIds.length > 0) &&
    (kind !== "contractor_clinic" || contractor) &&
    (kind === "site_clinic" || domainList.length > 0);
  async function save() {
    const common = {
      legal_name_en: nameEn.trim(),
      legal_name_ar: nameAr.trim(),
      moh_licence_no: licence.trim(),
      licence_valid_until: validTo,
      licence_checked_at: checked ? new Date(checkedAt).toISOString() : null,
      verification_domains: domainList,
      verification_email: email.trim() || null,
      verification_phone: phone.trim() || null,
      verification_portal_url: portal.trim() || null,
      project_ids: kind === "site_clinic" ? projectIds : [],
    };
    if (provider) {
      const r = await unwrap(api.PATCH("/api/v1/medical-providers/{provider_id}", { params: { path: { provider_id: provider.id } }, body: common }));
      qc.setQueryData(mk.provider(provider.id), r);
      await qc.invalidateQueries({ queryKey: ["medical-providers"] });
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(api.POST("/api/v1/medical-providers", { body: { ...common, provider_code: code, kind, contractor_id: kind === "contractor_clinic" ? contractor : null } }));
    await qc.invalidateQueries({ queryKey: ["medical-providers"] });
    toast.success(t("created", { code: r.provider_code }));
    router.push(`/medical-providers/${r.id}`);
  }
  return (
    <StepDialog title={provider ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-med-provider">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="mp-code" label={t("code")} required hint={t("codeHint")}>
          <Input value={code} disabled={Boolean(provider)} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={12} className="ltr uppercase" data-testid="mp-code" />
        </FormField>
        <FormField id="mp-kind" label={t("kind")} required>
          <Select value={kind} disabled={Boolean(provider)} onChange={(e) => setKind(e.target.value as S["MedicalProviderKind"])} data-testid="mp-kind">
            {MED_PROVIDER_KINDS.map((x) => (
              <option key={x} value={x}>
                {te(`medProviderKind.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="mp-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" maxLength={200} data-testid="mp-name-en" />
        </FormField>
        <FormField id="mp-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" maxLength={200} data-testid="mp-name-ar" />
        </FormField>
        {kind === "contractor_clinic" ? (
          <FormField id="mp-contractor" label={t("contractor")} required>
            <Select value={contractor} disabled={Boolean(provider)} onChange={(e) => setContractor(e.target.value)} data-testid="mp-contractor">
              <option value="">{tc("select")}</option>
              {(contractors.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.short_code} — {c.legal_name_en}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="mp-licence" label={t("mohLicence")} required>
          <Input value={licence} onChange={(e) => setLicence(e.target.value)} maxLength={40} className="ltr" data-testid="mp-licence" />
        </FormField>
        <FormField id="mp-valid" label={t("licenceValidUntil")} required>
          <Input type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} className="ltr" data-testid="mp-valid" />
        </FormField>
      </div>
      {kind === "site_clinic" ? (
        <CheckboxGroup id="mp-projects" legend={t("projects")} required options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.code }))} value={projectIds} onChange={setProjectIds} />
      ) : null}
      <Tick id="mp-checked" label={t("licenceChecked")} checked={checked} onChange={setChecked} />
      {checked ? (
        <FormField id="mp-checked-at" label={t("licenceCheckedAt")} hint={t("licenceCheckedHint")}>
          <Input type="datetime-local" value={checkedAt} onChange={(e) => setCheckedAt(e.target.value)} className="ltr" data-testid="mp-checked-at" />
        </FormField>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="mp-domains" label={t("domains")} required={kind !== "site_clinic"} hint={t("domainsHint")}>
          <Input value={domains} onChange={(e) => setDomains(e.target.value)} className="ltr" data-testid="mp-domains" />
        </FormField>
        <FormField id="mp-portal" label={t("portal")}>
          <Input type="url" value={portal} onChange={(e) => setPortal(e.target.value)} className="ltr" data-testid="mp-portal" />
        </FormField>
        <FormField id="mp-email" label={t("email")}>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="mp-phone" label={t("phone")}>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="ltr" inputMode="tel" />
        </FormField>
      </div>
    </StepDialog>
  );
}

export function MedicalProviderDetail({ id }: { id: string }) {
  const q = useMedicalProvider(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProviderView p={q.data} />;
}

type PAction = S["MedicalProviderAction"];
const NEEDS_REASON: PAction[] = ["return", "suspend", "reinstate", "blacklist", "lift_blacklist"];

function ProviderView({ p }: { p: S["MedicalProviderRead"] }) {
  const t = useTranslations("medical.providers");
  const te = useTranslations("enums");
  const locale = useLocale();
  const { date, dateTime } = useFormatters();
  const refresh = useMedicalRefresh();
  const caps = useMedCaps();
  const projects = useProjects({ page_size: 200 });
  const [action, setAction] = useState<PAction | null>(null);
  const [edit, setEdit] = useState(false);
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState<S["MedicalBlacklistScope"]>("all_records");
  const [from, setFrom] = useState("");
  const affected = useMedicalProviderAffected(p.id, { enabled: p.status === "blacklisted" && caps.clinical });
  const examiners = useMedicalExaminers({ provider_id: p.id, page_size: 100 });
  const projectCodes = p.project_ids.map((x) => projects.data?.items.find((pp) => pp.id === x)?.code ?? "…");
  const needsReason = action ? NEEDS_REASON.includes(action) : false;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/medical-providers" }, { label: p.provider_code }]} />
      <PageHeader
        title={locale === "ar" ? p.legal_name_ar : p.legal_name_en}
        badge={<MedProviderStatusBadge status={p.status} />}
        actions={
          <>
            {caps.providerEdit && p.status !== "blacklisted" ? (
              <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-med-provider">
                <Pencil aria-hidden />
                {t("edit")}
              </Button>
            ) : null}
            {p.allowed_actions.map((a) => (
              <Button key={a} variant={a === "blacklist" || a === "suspend" ? "destructive-outline" : a === "approve" || a === "submit" ? "default" : "outline"} onClick={() => setAction(a)} data-testid={`mp-${a}`}>
                {te(`medProviderAction.${a}`)}
              </Button>
            ))}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("code")} ltr>
                <Code>{p.provider_code}</Code>
              </FieldItem>
              <FieldItem label={t("kind")}>{te(`medProviderKind.${p.kind}`)}</FieldItem>
              {p.kind === "site_clinic" ? <FieldItem label={t("projects")}>{projectCodes.join(" · ")}</FieldItem> : null}
              <FieldItem label={t("mohLicence")} ltr>
                {p.moh_licence_no}
              </FieldItem>
              <FieldItem label={t("licenceValidUntil")}>{date(p.licence_valid_until)}</FieldItem>
              <FieldItem label={t("licenceCheckedAt")}>
                {p.licence_checked_at ? (
                  <span data-testid="mp-licence-checked">
                    {dateTime(p.licence_checked_at)} · <UserName u={p.licence_checked_by} />
                  </span>
                ) : (
                  <span className="text-warning" data-testid="mp-licence-unchecked">
                    {t("notChecked")}
                  </span>
                )}
              </FieldItem>
              <FieldItem label={t("domains")} ltr>
                {p.verification_domains.join(", ") || "—"}
              </FieldItem>
              <FieldItem label={t("portal")} ltr>
                {p.verification_portal_url ?? "—"}
              </FieldItem>
              <FieldItem label={t("email")} ltr>
                {p.verification_email ?? "—"}
              </FieldItem>
              <FieldItem label={t("phone")} ltr>
                {p.verification_phone ?? "—"}
              </FieldItem>
              {p.approved_on ? <FieldItem label={t("approvedOn")}>{date(p.approved_on)}</FieldItem> : null}
              {p.status_reason ? <FieldItem label={t("statusReason")}>{p.status_reason}</FieldItem> : null}
              {p.blacklist_scope ? (
                <FieldItem label={t("blacklistScope")}>
                  {te(`medBlacklistScope.${p.blacklist_scope}`)}
                  {p.blacklist_from ? ` · ${date(p.blacklist_from)}` : ""}
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("examiners")}</CardTitle>
          </CardHeader>
          <CardContent>
            {examiners.data?.items.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {examiners.data.items.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center gap-2">
                    <Code>{x.examiner_no}</Code>
                    <span>{locale === "ar" ? x.full_name_ar : x.full_name_en}</span>
                    <ExaminerStatusBadge status={x.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">—</p>
            )}
          </CardContent>
        </Card>
      </div>
      {affected.data?.length ? (
        <Card className="mt-4" data-testid="mp-affected">
          <CardHeader>
            <CardTitle className="text-base">{t("affected", { n: affected.data.length })}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-wrap gap-3 text-sm">
              {affected.data.map((w) => (
                <li key={w.id}>
                  <WorkerLabel w={w} link />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <div className="mt-4">
        <HistoryPanel entityType="medical_provider" entityId={p.id} />
      </div>
      {edit ? <ProviderDialog provider={p} onClose={() => setEdit(false)} /> : null}
      {action ? (
        <StepDialog
          title={te(`medProviderAction.${action}`)}
          description={action === "approve" ? t("approveHint") : action === "blacklist" ? t("blacklistHint") : undefined}
          confirmLabel={te(`medProviderAction.${action}`)}
          destructive={action === "blacklist" || action === "suspend"}
          testId="mp-confirm"
          disabled={(needsReason && reason.trim().length < 10) || (action === "blacklist" && scope === "issued_from" && !from)}
          onConfirm={async () => {
            await unwrap(
              api.POST("/api/v1/medical-providers/{provider_id}/transitions", {
                params: { path: { provider_id: p.id } },
                body: { action, reason: reason.trim() || null, blacklist_scope: action === "blacklist" ? scope : null, blacklist_from: action === "blacklist" && scope === "issued_from" ? from : null },
              }),
            );
            setReason("");
            await refresh();
          }}
          onClose={() => setAction(null)}
        >
          {action === "blacklist" ? (
            <>
              <FormField id="mp-scope" label={t("blacklistScope")} required>
                <Select value={scope} onChange={(e) => setScope(e.target.value as S["MedicalBlacklistScope"])} data-testid="mp-scope">
                  {MED_BLACKLIST_SCOPES.map((x) => (
                    <option key={x} value={x}>
                      {te(`medBlacklistScope.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              {scope === "issued_from" ? (
                <FormField id="mp-from" label={t("blacklistFrom")} required>
                  <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="ltr" />
                </FormField>
              ) : null}
            </>
          ) : null}
          {needsReason ? (
            <FormField id="mp-reason" label={t("reason")} required hint={t("reasonHint")}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="mp-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </div>
  );
}

/* ═════════════ examiners (§3.3, EX-1…EX-5) ═════════════ */

export function MedicalExaminersPage() {
  const t = useTranslations("medical.examiners");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useMedCaps();
  const { date } = useFormatters();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["ExaminerStatus"][];
  const q = useMedicalExaminers({ q: s.get("q") || null, status: status.length ? status : null, page, page_size: PAGE_SIZE });
  const providers = useMedicalProviders({ page_size: 200 });
  const [dialog, setDialog] = useState<S["ExaminerRead"] | "new" | null>(null);
  const [action, setAction] = useState<{ x: S["ExaminerRead"]; a: S["ExaminerAction"] } | null>(null);
  const [reason, setReason] = useState("");
  const refresh = useMedicalRefresh();
  const items = q.data?.items ?? [];
  const pcode = (id: string) => providers.data?.items.find((p) => p.id === id)?.provider_code ?? "…";
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.providerEdit ? (
            <Button onClick={() => setDialog("new")} data-testid="new-examiner">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <MedicalCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="medical_examiners" /> : null}>
        <SearchFilter id="ex-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="ex-status" label={tc("status")} options={EXAMINER_STATUSES.map((x) => ({ value: x, label: te(`examinerStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="examiners-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("name")}</TH>
                <TH>{t("classification")}</TH>
                <TH>{t("licence")}</TH>
                <TH>{t("providers")}</TH>
                <TH>{tc("status")}</TH>
                {caps.providerEdit || caps.providerDecide ? <TH /> : null}
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="examiner-row" data-no={x.examiner_no}>
                  <TD label={t("no")}>
                    <Code>{x.examiner_no}</Code>
                  </TD>
                  <TD label={t("name")}>
                    {locale === "ar" ? x.full_name_ar : x.full_name_en}
                    {x.user ? <span className="block text-xs text-muted-foreground">{t("linkedTo", { name: x.user.full_name_en })}</span> : null}
                  </TD>
                  <TD label={t("classification")}>{te(`examinerClass.${x.classification}`)}</TD>
                  <TD label={t("licence")}>
                    {x.scfhs_licence_no ? <Code>{x.scfhs_licence_no}</Code> : <span className="text-muted-foreground">{t("licenceHidden")}</span>}
                    {x.licence_valid_until ? <span className="block text-xs text-muted-foreground">{t("validTo", { d: date(x.licence_valid_until) })}</span> : null}
                  </TD>
                  <TD label={t("providers")}>
                    <span className="text-xs">{x.provider_ids.map(pcode).join(" · ")}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <ExaminerStatusBadge status={x.status} />
                    {x.status_reason ? <span className="block text-xs text-muted-foreground">{x.status_reason}</span> : null}
                  </TD>
                  {caps.providerEdit || caps.providerDecide ? (
                    <TD>
                      <span className="flex flex-wrap gap-1">
                        {caps.providerEdit && (x.status === "active" || x.status === "suspended") ? (
                          <Button size="sm" variant="ghost" onClick={() => setDialog(x)} aria-label={tc("edit")}>
                            <Pencil aria-hidden />
                          </Button>
                        ) : null}
                        {caps.providerDecide && x.status === "active" ? (
                          <Button size="sm" variant="outline" onClick={() => setAction({ x, a: "suspend" })} data-testid="ex-suspend">
                            {te("examinerAction.suspend")}
                          </Button>
                        ) : null}
                        {caps.providerDecide && x.status === "suspended" ? (
                          <Button size="sm" variant="outline" onClick={() => setAction({ x, a: "reinstate" })}>
                            {te("examinerAction.reinstate")}
                          </Button>
                        ) : null}
                        {caps.providerDecide && (x.status === "active" || x.status === "suspended") ? (
                          <Button size="sm" variant="destructive-outline" onClick={() => setAction({ x, a: "withdraw" })}>
                            {te("examinerAction.withdraw")}
                          </Button>
                        ) : null}
                      </span>
                    </TD>
                  ) : null}
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
      {dialog ? <ExaminerDialog examiner={dialog === "new" ? undefined : dialog} onClose={() => setDialog(null)} /> : null}
      {action ? (
        <StepDialog
          title={te(`examinerAction.${action.a}`)}
          description={`${action.x.examiner_no} — ${locale === "ar" ? action.x.full_name_ar : action.x.full_name_en}`}
          confirmLabel={te(`examinerAction.${action.a}`)}
          destructive={action.a !== "reinstate"}
          disabled={reason.trim().length < 10}
          testId="ex-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/medical-examiners/{examiner_id}/transitions", { params: { path: { examiner_id: action.x.id } }, body: { action: action.a, reason: reason.trim() } }));
            setReason("");
            await refresh();
          }}
          onClose={() => setAction(null)}
        >
          <FormField id="ex-reason" label={t("reason")} required hint={t("reasonHint")}>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="ex-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

function ExaminerDialog({ examiner, onClose }: { examiner?: S["ExaminerRead"]; onClose: () => void }) {
  const t = useTranslations("medical.examiners");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const { project } = useCurrentProject();
  const users = useUserOptions(project?.id ?? "");
  const providers = useMedicalProviders({ page_size: 200, status: ["approved"] });
  const [nameEn, setNameEn] = useState(examiner?.full_name_en ?? "");
  const [nameAr, setNameAr] = useState(examiner?.full_name_ar ?? "");
  const [licence, setLicence] = useState(examiner?.scfhs_licence_no ?? "");
  const [cls, setCls] = useState<S["ExaminerClass"]>(examiner?.classification ?? "physician");
  const [validTo, setValidTo] = useState(examiner?.licence_valid_until ?? "");
  const [checkedAt, setCheckedAt] = useState(nowLocal());
  const [providerIds, setProviderIds] = useState<string[]>(examiner?.provider_ids ?? []);
  const [user, setUser] = useState(examiner?.user?.id ?? "");
  const valid = nameEn.trim() && nameAr.trim() && providerIds.length > 0 && (examiner || (licence.trim() && validTo && checkedAt));
  return (
    <StepDialog
      title={examiner ? t("edit") : t("new")}
      description={t("newHint")}
      confirmLabel={tc("save")}
      disabled={!valid}
      wide
      testId="save-examiner"
      onConfirm={async () => {
        if (examiner) {
          await unwrap(api.PATCH("/api/v1/medical-examiners/{examiner_id}", { params: { path: { examiner_id: examiner.id } }, body: { full_name_en: nameEn.trim(), full_name_ar: nameAr.trim(), provider_ids: providerIds, user_id: user || null } }));
        } else {
          await unwrap(
            api.POST("/api/v1/medical-examiners", {
              body: { full_name_en: nameEn.trim(), full_name_ar: nameAr.trim(), scfhs_licence_no: licence.trim(), classification: cls, licence_valid_until: validTo, licence_checked_at: new Date(checkedAt).toISOString(), provider_ids: providerIds, user_id: user || null },
            }),
          );
        }
        toast.success(tc("saved"));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ex-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" maxLength={120} data-testid="ex-name-en" />
        </FormField>
        <FormField id="ex-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" maxLength={120} data-testid="ex-name-ar" />
        </FormField>
        {!examiner ? (
          <>
            <FormField id="ex-licence" label={t("licence")} required>
              <Input value={licence} onChange={(e) => setLicence(e.target.value)} maxLength={30} className="ltr" data-testid="ex-licence" />
            </FormField>
            <FormField id="ex-class" label={t("classification")} required>
              <Select value={cls} onChange={(e) => setCls(e.target.value as S["ExaminerClass"])} data-testid="ex-class">
                {EXAMINER_CLASSES.map((x) => (
                  <option key={x} value={x}>
                    {te(`examinerClass.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="ex-valid" label={t("licenceValidUntil")} required>
              <Input type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} className="ltr" data-testid="ex-valid" />
            </FormField>
            <FormField id="ex-checked" label={t("licenceCheckedAt")} required hint={t("licenceCheckedHint")}>
              <Input type="datetime-local" value={checkedAt} onChange={(e) => setCheckedAt(e.target.value)} className="ltr" />
            </FormField>
          </>
        ) : null}
        <FormField id="ex-user" label={t("user")} hint={t("userHint")}>
          <Select value={user} onChange={(e) => setUser(e.target.value)} data-testid="ex-user">
            <option value="">{tc("none")}</option>
            {users.map((u) => (
              <option key={u.value} value={u.value}>
                {u.label}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      {cls === "nurse" && !examiner ? <Alert tone="info">{t("nurseNote")}</Alert> : null}
      <CheckboxGroup id="ex-providers" legend={t("providers")} required options={(providers.data?.items ?? []).map((p) => ({ value: p.id, label: p.provider_code }))} value={providerIds} onChange={setProviderIds} />
    </StepDialog>
  );
}
