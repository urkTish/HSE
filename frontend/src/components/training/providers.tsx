"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Pencil, Plus, Search } from "lucide-react";
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
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, DaysLeft, StepDialog, WorkerLabel } from "@/components/access/common";
import { UploadField, UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useContractors } from "@/lib/api/queries";
import { tk, useProviderAcceptability, useTrainingProvider, useTrainingProviderImpact, useTrainingProviders, useTrainingRefresh } from "@/lib/api/training";
import { useCurrentProject } from "@/lib/current-project";
import { todayInZone } from "@/lib/datetime";
import { ACB_CODES, PROVIDER_KINDS, PROVIDER_STATUSES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { CourseSelect, ProviderStatusBadge, TrainingCatalogueSubNav, useCourseCatalogue, useTrainingCaps } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

function Accepted({ status, accepted }: { status: S["TrainingProviderStatus"] | null; accepted: boolean }) {
  const t = useTranslations("training.providers");
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <ProviderStatusBadge status={status} />
      {accepted ? (
        <Badge tone="success" data-testid="provider-accepted">
          <BadgeCheck aria-hidden />
          {t("acceptedForUse")}
        </Badge>
      ) : null}
    </span>
  );
}

/* ───────────── list ───────────── */

export function ProviderListPage() {
  const t = useTranslations("training.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useTrainingCaps();
  const { date } = useFormatters();
  const { courses } = useCourseCatalogue();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["TrainingProviderStatus"][];
  const kind = s.getAll("kind") as S["TrainingProviderKind"][];
  const [create, setCreate] = useState(false);
  const q = useTrainingProviders({
    q: s.get("q") || null,
    status: status.length ? status : null,
    kind: kind.length ? kind : null,
    course_code: s.get("course") || null,
    accreditation_body: s.get("acb") ? [s.get("acb") as S["AccreditationBodyCode"]] : null,
    accreditation_expiring_days: s.getInt("expiring", 0) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.providerEdit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-provider">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <TrainingCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_providers" /> : null}>
        <SearchFilter id="prov-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="prov-status" label={tc("status")} options={PROVIDER_STATUSES.map((x) => ({ value: x, label: te(`providerStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="prov-kind" label={t("kind")} options={PROVIDER_KINDS.map((x) => ({ value: x, label: te(`providerKind.${x}`) }))} value={kind} onChange={(v) => s.set({ kind: v })} />
        <SelectFilter id="prov-course" label={t("course")} value={s.get("course") ?? ""} onChange={(v) => s.set({ course: v })} options={courses.map((c) => ({ value: c.code, label: c.code }))} />
        <SelectFilter id="prov-acb" label={t("accreditationBody")} value={s.get("acb") ?? ""} onChange={(v) => s.set({ acb: v })} options={ACB_CODES.map((x) => ({ value: x, label: te(`acb.${x}`) }))} />
        <SelectFilter
          id="prov-exp"
          label={t("expiring")}
          value={s.get("expiring") ?? ""}
          onChange={(v) => s.set({ expiring: v })}
          options={[
            { value: "30", label: t("withinDays", { n: 30 }) },
            { value: "90", label: t("withinDays", { n: 90 }) },
          ]}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="providers-table">
            <THead>
              <TR>
                <TH>{t("code")}</TH>
                <TH>{t("name")}</TH>
                <TH>{t("kind")}</TH>
                <TH>{t("accreditedCourses")}</TH>
                <TH>{t("nextExpiry")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="provider-row" data-code={p.provider_code}>
                  <TD label={t("code")}>
                    <Link href={`/training-providers/${p.id}`} className="font-medium text-primary hover:underline">
                      <Code>{p.provider_code}</Code>
                    </Link>
                  </TD>
                  <TD label={t("name")}>{locale === "ar" ? p.legal_name_ar : p.legal_name_en}</TD>
                  <TD label={t("kind")}>
                    <span className="text-sm">{te(`providerKind.${p.kind}`)}</span>
                    {p.contractor_short_code ? <Code className="ms-1 text-xs text-muted-foreground">{p.contractor_short_code}</Code> : null}
                  </TD>
                  <TD label={t("accreditedCourses")}>
                    <span className="text-xs">{p.accredited_course_codes.join(" · ") || "—"}</span>
                  </TD>
                  <TD label={t("nextExpiry")}>{p.next_accreditation_expiry ? date(p.next_accreditation_expiry) : "—"}</TD>
                  <TD label={tc("status")}>
                    <Accepted status={p.status} accepted={p.accepted_for_use} />
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

/* ───────────── create / edit ───────────── */

function ProviderDialog({ provider, onClose }: { provider?: S["ProviderRead"]; onClose: () => void }) {
  const t = useTranslations("training.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const contractors = useContractors({ page_size: 200 });
  const [code, setCode] = useState(provider?.provider_code ?? "");
  const [kind, setKind] = useState<S["TrainingProviderKind"]>(provider?.kind ?? "external");
  const [contractor, setContractor] = useState(provider?.contractor_id ?? "");
  const [nameEn, setNameEn] = useState(provider?.legal_name_en ?? "");
  const [nameAr, setNameAr] = useState(provider?.legal_name_ar ?? "");
  const [country, setCountry] = useState(provider?.country ?? "SA");
  const [cr, setCr] = useState(provider?.cr_number ?? "");
  const [foreign, setForeign] = useState(provider?.foreign_reg_no ?? "");
  const [portal, setPortal] = useState(provider?.verification_portal_url ?? "");
  const [domains, setDomains] = useState((provider?.verification_domains ?? []).join(", "));
  const [email, setEmail] = useState(provider?.verification_email ?? "");
  const [phone, setPhone] = useState(provider?.verification_phone ?? "");
  const [contact, setContact] = useState(provider?.contact_name ?? "");
  const [mobile, setMobile] = useState(provider?.contact_mobile ?? "");
  const external = kind === "external";
  const domainList = domains
    .split(/[\s,]+/)
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean);
  const saudi = country.trim().toUpperCase() === "SA";
  const regOk = !external || (saudi ? /^\d{10}$/.test(cr.trim()) : foreign.trim().length > 0);
  const valid = /^[A-Z0-9-]{2,12}$/.test(code.trim().toUpperCase()) && nameEn.trim() && nameAr.trim() && (kind !== "contractor_internal" || contractor) && (!external || (country.trim().length === 2 && domainList.length > 0)) && regOk;
  async function save() {
    const common = {
      legal_name_en: nameEn.trim(),
      legal_name_ar: nameAr.trim(),
      country: external ? country.trim().toUpperCase() : null,
      cr_number: external && saudi ? cr.trim() : null,
      foreign_reg_no: external && !saudi ? foreign.trim() : null,
      verification_portal_url: portal.trim() || null,
      verification_domains: domainList,
      verification_email: email.trim() || null,
      verification_phone: phone.trim() || null,
      contact_name: contact.trim() || null,
      contact_mobile: mobile.trim() || null,
    };
    if (provider) {
      const r = await unwrap(api.PATCH("/api/v1/training-providers/{provider_id}", { params: { path: { provider_id: provider.id } }, body: common }));
      qc.setQueryData(tk.provider(provider.id), r);
      await qc.invalidateQueries({ queryKey: ["training-providers"] });
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(api.POST("/api/v1/training-providers", { body: { ...common, provider_code: code.trim().toUpperCase(), kind, contractor_id: kind === "contractor_internal" ? contractor : null } }));
    await qc.invalidateQueries({ queryKey: ["training-providers"] });
    toast.success(t("created", { code: r.provider_code }));
    router.push(`/training-providers/${r.id}`);
  }
  return (
    <StepDialog title={provider ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-provider">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="prov-code" label={t("code")} required hint={t("codeHint")}>
          <Input value={code} disabled={Boolean(provider)} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={12} className="ltr uppercase" data-testid="prov-code" />
        </FormField>
        <FormField id="prov-kind" label={t("kind")} required>
          <Select value={kind} disabled={Boolean(provider)} onChange={(e) => setKind(e.target.value as S["TrainingProviderKind"])} data-testid="prov-kind">
            {PROVIDER_KINDS.map((x) => (
              <option key={x} value={x}>
                {te(`providerKind.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {kind === "contractor_internal" ? (
          <FormField id="prov-contractor" label={t("contractor")} required>
            <Select value={contractor} disabled={Boolean(provider)} onChange={(e) => setContractor(e.target.value)} data-testid="prov-contractor">
              <option value="">{tc("select")}</option>
              {(contractors.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.short_code} — {c.legal_name_en}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="prov-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" maxLength={200} data-testid="prov-name-en" />
        </FormField>
        <FormField id="prov-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" maxLength={200} data-testid="prov-name-ar" />
        </FormField>
      </div>
      {external ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="prov-country" label={t("country")} required hint={t("countryHint")}>
            <Input value={country} onChange={(e) => setCountry(e.target.value)} maxLength={2} className="ltr uppercase" data-testid="prov-country" />
          </FormField>
          {saudi ? (
            <FormField id="prov-cr" label={t("crNumber")} required hint={t("crHint")}>
              <Input value={cr} onChange={(e) => setCr(e.target.value.replace(/\D/g, ""))} maxLength={10} inputMode="numeric" className="ltr" data-testid="prov-cr" />
            </FormField>
          ) : (
            <FormField id="prov-foreign" label={t("foreignRegNo")} required>
              <Input value={foreign} onChange={(e) => setForeign(e.target.value)} maxLength={30} className="ltr" />
            </FormField>
          )}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="prov-domains" label={t("domains")} required={external} hint={t("domainsHint")}>
          <Input value={domains} onChange={(e) => setDomains(e.target.value)} className="ltr" data-testid="prov-domains" />
        </FormField>
        <FormField id="prov-portal" label={t("portal")}>
          <Input type="url" value={portal} onChange={(e) => setPortal(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="prov-email" label={t("verificationEmail")}>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="prov-phone" label={t("verificationPhone")}>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="ltr" inputMode="tel" />
        </FormField>
        <FormField id="prov-contact" label={t("contactName")}>
          <Input value={contact} onChange={(e) => setContact(e.target.value)} />
        </FormField>
        <FormField id="prov-mobile" label={t("contactMobile")}>
          <Input value={mobile} onChange={(e) => setMobile(e.target.value)} className="ltr" inputMode="tel" />
        </FormField>
      </div>
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function ProviderDetail({ id }: { id: string }) {
  const q = useTrainingProvider(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProviderView p={q.data} />;
}

type Action = S["TrainingProviderAction"];
const NEEDS_REASON: Action[] = ["return", "suspend", "reinstate", "blacklist", "lift_blacklist"];

function availableActions(st: S["TrainingProviderStatus"] | null, edit: boolean, decide: boolean): Action[] {
  const out: Action[] = [];
  if (edit && st === "draft") out.push("submit");
  if (decide && st === "pending_approval") out.push("approve", "return");
  if (decide && st === "approved") out.push("suspend");
  if (decide && st === "suspended") out.push("reinstate");
  if (decide && st && st !== "blacklisted") out.push("blacklist");
  if (decide && st === "blacklisted") out.push("lift_blacklist");
  return out;
}

function ProviderView({ p }: { p: S["ProviderRead"] }) {
  const t = useTranslations("training.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { date, dateTime } = useFormatters();
  const refresh = useTrainingRefresh();
  const caps = useTrainingCaps();
  const [action, setAction] = useState<Action | null>(null);
  const [edit, setEdit] = useState(false);
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState<S["ProviderBlacklistScope"]>("all_records");
  const [from, setFrom] = useState(todayInZone());
  const [effective, setEffective] = useState(todayInZone());
  const [acc, setAcc] = useState<S["ProviderAccreditationRead"] | "new" | null>(null);
  const impact = useTrainingProviderImpact(p.id, { enabled: action === "blacklist" || action === "suspend" });
  const actions = availableActions(p.status, caps.providerEdit, caps.providerDecide);
  async function transition(a: Action) {
    const r = await unwrap(
      api.POST("/api/v1/training-providers/{provider_id}/transitions", {
        params: { path: { provider_id: p.id } },
        body: {
          action: a,
          reason: reason.trim() || null,
          blacklist_scope: a === "blacklist" ? scope : null,
          blacklist_from: a === "blacklist" && scope === "issued_from" ? from : null,
          effective_on: a === "suspend" ? effective : null,
        },
      }),
    );
    await refresh();
    toast.success(r.status ? te(`providerStatus.${r.status}`) : tc("saved"));
  }
  async function registerCheck(a: S["ProviderAccreditationRead"]) {
    await unwrap(api.POST("/api/v1/training-provider-accreditations/{accreditation_id}/register-check", { params: { path: { accreditation_id: a.id } }, body: {} }));
    await refresh();
    toast.success(t("registerChecked"));
  }
  const minReason = action === "blacklist" ? 20 : 5;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-providers" }, { label: p.provider_code }]} />
        <PageHeader
          title={`${p.provider_code} — ${locale === "ar" ? p.legal_name_ar : p.legal_name_en}`}
          description={te(`providerKind.${p.kind}`) + (p.contractor_short_code ? ` · ${p.contractor_short_code}` : "")}
          actions={
            <>
              <Accepted status={p.status} accepted={p.accepted_for_use} />
              {caps.providerEdit && p.status !== "blacklisted" ? (
                <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-provider">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {actions.map((a) => (
                <Button key={a} variant={a === "blacklist" ? "destructive-outline" : a === "suspend" || a === "return" ? "outline" : "default"} onClick={() => setAction(a)} data-testid={`provider-${a}`}>
                  {te(`providerAction.${a}`)}
                </Button>
              ))}
            </>
          }
        />
      </div>
      {p.status === "blacklisted" ? (
        <Alert tone="danger" data-testid="provider-blacklisted">
          {t("blacklistedSince", { date: p.blacklist_from ? date(p.blacklist_from) : "—", scope: p.blacklist_scope ? te(`providerBlacklistScope.${p.blacklist_scope}`) : "" })}
        </Alert>
      ) : null}
      {p.status === "suspended" && p.suspended_from ? <Alert tone="warning">{t("suspendedFrom", { date: date(p.suspended_from) })}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("nameEn")}>{p.legal_name_en}</FieldItem>
            <FieldItem label={t("nameAr")}>{p.legal_name_ar}</FieldItem>
            {p.kind === "external" ? (
              <>
                <FieldItem label={t("country")} ltr>
                  {p.country ?? "—"}
                </FieldItem>
                <FieldItem label={t("crNumber")} ltr>
                  {p.cr_number ?? p.foreign_reg_no ?? "—"}
                </FieldItem>
              </>
            ) : null}
            <FieldItem label={t("domains")} ltr>
              {p.verification_domains.join(", ") || "—"}
            </FieldItem>
            <FieldItem label={t("portal")} ltr>
              {p.verification_portal_url ?? "—"}
            </FieldItem>
            <FieldItem label={t("verificationEmail")} ltr>
              {p.verification_email ?? "—"}
            </FieldItem>
            <FieldItem label={t("verificationPhone")} ltr>
              {p.verification_phone ?? "—"}
            </FieldItem>
            <FieldItem label={t("contactName")}>{p.contact_name ?? "—"}</FieldItem>
            <FieldItem label={t("approvedBy")}>
              {p.approved_by ? (
                <>
                  <UserName u={p.approved_by} /> · {p.approved_at ? dateTime(p.approved_at) : ""}
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            {p.status_reason ? (
              <FieldItem label={tc("reason")} wide>
                {p.status_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("accreditations")}</CardTitle>
          {caps.providerEdit ? (
            <Button variant="outline" onClick={() => setAcc("new")} data-testid="new-accreditation">
              <Plus aria-hidden />
              {t("addAccreditation")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {p.accreditations.length ? (
            <Table data-testid="accreditations-table">
              <THead>
                <TR>
                  <TH>{t("accreditationBody")}</TH>
                  <TH>{t("accreditationNo")}</TH>
                  <TH>{t("scope")}</TH>
                  <TH>{t("valid")}</TH>
                  <TH>{t("registerCheck")}</TH>
                  <TH>
                    <span className="sr-only">{tc("actions")}</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {p.accreditations.map((a) => (
                  <TR key={a.id} data-testid="accreditation-row" data-counts={a.counts ? "yes" : "no"}>
                    <TD label={t("accreditationBody")}>{te(`acb.${a.accreditation_body}`)}</TD>
                    <TD label={t("accreditationNo")}>
                      <Code>{a.accreditation_no}</Code>
                    </TD>
                    <TD label={t("scope")}>
                      <span className="text-xs">{a.scope_course_codes.join(" · ")}</span>
                    </TD>
                    <TD label={t("valid")}>
                      <span className="text-sm">
                        {date(a.valid_from)} – {date(a.valid_until)}
                      </span>{" "}
                      <DaysLeft days={a.days_left} />
                    </TD>
                    <TD label={t("registerCheck")}>
                      {a.register_checked_at ? (
                        <span className="text-xs">
                          {dateTime(a.register_checked_at)} · <UserName u={a.register_checked_by} />
                        </span>
                      ) : (
                        <Badge tone="warning" data-testid="register-not-checked">
                          {t("notChecked")}
                        </Badge>
                      )}
                      {!a.counts ? <span className="block text-xs text-destructive">{t("doesNotCount")}</span> : null}
                    </TD>
                    <TD label={tc("actions")}>
                      {caps.providerEdit ? (
                        <span className="flex flex-wrap gap-2">
                          <Button size="sm" variant="outline" onClick={() => void registerCheck(a).catch((e: unknown) => toast.error(String(e)))} data-testid="register-check">
                            {t("recordRegisterCheck")}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setAcc(a)}>
                            <Pencil aria-hidden />
                            <span className="sr-only">{tc("edit")}</span>
                          </Button>
                        </span>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState message={t("noAccreditations")} />
          )}
        </CardContent>
      </Card>
      <AcceptabilityCard p={p} />
      <HistoryPanel entityType="training_provider" entityId={p.id} />
      {edit ? <ProviderDialog provider={p} onClose={() => setEdit(false)} /> : null}
      {acc ? <AccreditationDialog p={p} acc={acc === "new" ? undefined : acc} onClose={() => setAcc(null)} /> : null}
      {action ? (
        <StepDialog
          title={t("confirmAction", { action: te(`providerAction.${action}`) })}
          description={action === "blacklist" ? t("blacklistHint") : action === "suspend" ? t("suspendHint") : action === "lift_blacklist" ? t("liftHint") : action === "approve" ? t("approveHint") : undefined}
          confirmLabel={te(`providerAction.${action}`)}
          destructive={action === "blacklist" || action === "suspend"}
          disabled={NEEDS_REASON.includes(action) && reason.trim().length < minReason}
          onClose={() => {
            setAction(null);
            setReason("");
          }}
          onConfirm={() => transition(action)}
          testId="provider-confirm"
          wide={action === "blacklist"}
        >
          {action === "blacklist" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="prov-scope" label={t("blacklistScope")} required>
                <Select value={scope} onChange={(e) => setScope(e.target.value as S["ProviderBlacklistScope"])} data-testid="prov-scope">
                  <option value="all_records">{te("providerBlacklistScope.all_records")}</option>
                  <option value="issued_from">{te("providerBlacklistScope.issued_from")}</option>
                </Select>
              </FormField>
              {scope === "issued_from" ? (
                <FormField id="prov-from" label={t("blacklistFrom")} required>
                  <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="prov-from" />
                </FormField>
              ) : null}
            </div>
          ) : null}
          {action === "suspend" ? (
            <FormField id="prov-effective" label={t("suspendFrom")} required>
              <Input type="date" className="ltr" value={effective} onChange={(e) => setEffective(e.target.value)} />
            </FormField>
          ) : null}
          {(action === "blacklist" || action === "suspend") && impact.data ? (
            <Alert tone="warning" data-testid="provider-impact">
              {t("impact", { records: impact.data.records_revoked, holders: impact.data.holders.length, sessions: impact.data.sessions_not_allowed.length })}
              {impact.data.holders.length ? (
                <ul className="mt-2 max-h-40 overflow-auto text-xs">
                  {impact.data.holders.slice(0, 50).map((h) => (
                    <li key={`${h.worker_id}-${h.record_no}`}>
                      <WorkerLabel w={{ id: h.worker_id, worker_no: h.worker_no, full_name_en: h.full_name_en, full_name_ar: h.full_name_ar }} /> · <Code>{h.course_code}</Code> · <Code>{h.record_no}</Code>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Alert>
          ) : null}
          {NEEDS_REASON.includes(action) ? (
            <FormField id="prov-reason" label={tc("reason")} required hint={action === "blacklist" ? t("reason20") : t("reasonHint")}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="prov-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </div>
  );
}

function AccreditationDialog({ p, acc, onClose }: { p: S["ProviderRead"]; acc?: S["ProviderAccreditationRead"]; onClose: () => void }) {
  const t = useTranslations("training.providers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useTrainingRefresh();
  const { courses } = useCourseCatalogue(null, { active: true });
  const [body, setBody] = useState<S["AccreditationBodyCode"]>(acc?.accreditation_body ?? "srca");
  const [no, setNo] = useState(acc?.accreditation_no ?? "");
  const [scope, setScope] = useState<string[]>(acc?.scope_course_codes ?? []);
  const [from, setFrom] = useState(acc?.valid_from ?? "");
  const [until, setUntil] = useState(acc?.valid_until ?? "");
  const [file, setFile] = useState<string | null>(acc?.certificate_attachment_id ?? null);
  const valid = no.trim() && scope.length && from && until && until > from && file;
  async function save() {
    const b = { accreditation_body: body, accreditation_no: no.trim(), scope_course_codes: scope, valid_from: from, valid_until: until, certificate_attachment_id: file as string };
    if (acc) await unwrap(api.PATCH("/api/v1/training-provider-accreditations/{accreditation_id}", { params: { path: { accreditation_id: acc.id } }, body: b }));
    else await unwrap(api.POST("/api/v1/training-providers/{provider_id}/accreditations", { params: { path: { provider_id: p.id } }, body: b }));
    await refresh();
    toast.success(tc("saved"));
  }
  return (
    <StepDialog title={acc ? t("editAccreditation") : t("addAccreditation")} description={t("accreditationHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-accreditation">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="acc-body" label={t("accreditationBody")} required>
          <Select value={body} onChange={(e) => setBody(e.target.value as S["AccreditationBodyCode"])} data-testid="acc-body">
            {ACB_CODES.map((x) => (
              <option key={x} value={x}>
                {te(`acb.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="acc-no" label={t("accreditationNo")} required>
          <Input value={no} onChange={(e) => setNo(e.target.value)} maxLength={40} className="ltr" data-testid="acc-no" />
        </FormField>
        <FormField id="acc-from" label={t("validFrom")} required>
          <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="acc-from" />
        </FormField>
        <FormField id="acc-until" label={t("validUntil")} required>
          <Input type="date" className="ltr" value={until} onChange={(e) => setUntil(e.target.value)} data-testid="acc-until" />
        </FormField>
      </div>
      <MultiSelect id="acc-scope" label={t("scope")} options={courses.filter((c) => c.category !== "induction_link").map((c) => ({ value: c.code, label: `${c.code} — ${c.name_en}` }))} value={scope} onChange={setScope} testId="acc-scope" />
      {/* Owner of the upload is the provider (accreditation id does not exist yet); see PROGRESS contract request. */}
      <UploadField id="acc-file" label={t("certificateFile")} ownerType="training_accreditation_certificate" ownerId={p.id} accept="application/pdf" value={file} onChange={(v) => setFile(v)} required hint={t("pdfHint")} />
    </StepDialog>
  );
}

/** PV-3 acceptability for a course on a date (and optionally for a worker, NOT_OWN_TREE). */
function AcceptabilityCard({ p }: { p: S["ProviderRead"] }) {
  const t = useTranslations("training.providers");
  const te = useTranslations("enums");
  const { project } = useCurrentProject();
  const { date } = useFormatters(project?.id);
  const [course, setCourse] = useState("");
  const [on, setOn] = useState(todayInZone());
  const [run, setRun] = useState(false);
  const q = useProviderAcceptability(p.id, { course_code: course, on_date: [on || todayInZone()], project_id: project?.id ?? null }, { enabled: run });
  return (
    <Card data-testid="acceptability">
      <CardHeader>
        <CardTitle className="text-base">{t("acceptabilityTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">{t("acceptabilityHint")}</p>
        <div className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
          <CourseSelect
            id="acc-check-course"
            label={t("course")}
            value={course}
            onChange={(v) => {
              setCourse(v);
              setRun(false);
            }}
          />
          <FormField id="acc-check-on" label={t("onDate")}>
            <Input
              type="date"
              className="ltr"
              value={on}
              onChange={(e) => {
                setOn(e.target.value);
                setRun(false);
              }}
            />
          </FormField>
          <Button variant="outline" disabled={!course} onClick={() => setRun(true)} data-testid="acc-check">
            <Search aria-hidden />
            {t("check")}
          </Button>
        </div>
        {run && q.isError ? <MutationError error={q.error} /> : null}
        {run && q.data ? (
          <ul className="flex flex-col gap-1 text-sm" data-testid="acceptability-result">
            {q.data.items.map((i) => (
              <li key={i.on_date} className="flex flex-wrap items-center gap-2" data-acceptable={i.acceptable ? "yes" : "no"} data-reason={i.reason ?? ""}>
                <span className="ltr">{date(i.on_date)}</span>
                {i.acceptable ? <Badge tone="success">{t("acceptable")}</Badge> : <Badge tone="danger">{i.reason ? te(`providerUnacceptable.${i.reason}`) : t("notAcceptable")}</Badge>}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
