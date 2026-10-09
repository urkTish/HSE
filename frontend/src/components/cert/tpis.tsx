"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, OctagonAlert, Pencil, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
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
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, DaysLeft, StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, useTpi, useTpiApprovals, useTpiImpact, useTpis } from "@/lib/api/cert";
import { useContractors } from "@/lib/api/queries";
import { ACCREDITATION_BODIES, ACCREDITATION_STANDARDS, EQUIPMENT_CERT_CATEGORIES, TPI_KINDS, TPI_STATUSES } from "@/lib/cert-enums";
import { todayInZone } from "@/lib/datetime";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { CertSetupSubNav, TpiLabel, TpiSelect, UploadField, UserName, useCertTypes } from "./common";
import { RecordActions } from "@/components/common/record-actions";

type S = Schemas;
const PAGE_SIZE = 50;

function TpiStatus({ status, accepted }: { status: S["TpiStatus"] | null | undefined; accepted?: boolean }) {
  const te = useTranslations("enums");
  const t = useTranslations("tpis");
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="tpi-status" data-status={status ?? ""}>
      {status ? <StatusBadge status={status} label={te(`tpiStatus.${status}`)} /> : null}
      {accepted ? (
        <Badge tone="success">
          <BadgeCheck aria-hidden />
          {t("acceptedForUse")}
        </Badge>
      ) : null}
    </span>
  );
}

/* ───────────── list ───────────── */

export function TpiListPage() {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["TpiStatus"][];
  const kind = s.getAll("kind") as S["TpiKind"][];
  const [create, setCreate] = useState(false);
  const q = useTpis({ q: s.get("q") || null, status: status.length ? status : null, kind: kind.length ? kind : null, page, page_size: PAGE_SIZE });
  const items = q.data?.items ?? [];
  const { date } = useFormatters();
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          can(me, "tpi.edit") ? (
            <Button onClick={() => setCreate(true)} data-testid="new-tpi">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.cert") ? <ExportButtons dataset="tpis" /> : null}>
        <SearchFilter id="tpi-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="tpi-status" label={tc("status")} options={TPI_STATUSES.map((x) => ({ value: x, label: te(`tpiStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="tpi-kind" label={t("kinds")} options={TPI_KINDS.map((x) => ({ value: x, label: te(`tpiKind.${x}`) }))} value={kind} onChange={(v) => s.set({ kind: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="tpis-table">
            <THead>
              <TR>
                <TH>{t("code")}</TH>
                <TH>{t("name")}</TH>
                <TH>{t("kinds")}</TH>
                <TH>{t("country")}</TH>
                <TH>{t("accreditation")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="tpi-row" data-code={x.tpi_code}>
                  <TD label={t("code")}>
                    <Link href={`/tpis/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.tpi_code}</Code>
                    </Link>
                  </TD>
                  <TD label={t("name")}>{locale === "ar" ? x.legal_name_ar : x.legal_name_en}</TD>
                  <TD label={t("kinds")}>
                    <span className="text-xs">{x.kinds.map((k) => te(`tpiKind.${k}`)).join(" · ")}</span>
                  </TD>
                  <TD label={t("country")}>
                    <Code>{x.country}</Code>
                  </TD>
                  <TD label={t("accreditation")}>
                    {x.accreditation_lapsed ? (
                      <Badge tone="danger">{t("lapsed")}</Badge>
                    ) : x.next_accreditation_expiry ? (
                      <span className="text-sm">{date(x.next_accreditation_expiry)}</span>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={tc("status")}>
                    <TpiStatus status={x.status} accepted={x.accepted_for_use} />
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
      {create ? <TpiDialog onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/* ───────────── create / edit ───────────── */

function TpiDialog({ tpi, onClose }: { tpi?: S["TpiRead"]; onClose: () => void }) {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const contractors = useContractors({ page_size: 200 });
  const [code, setCode] = useState(tpi?.tpi_code ?? "");
  const [nameEn, setNameEn] = useState(tpi?.legal_name_en ?? "");
  const [nameAr, setNameAr] = useState(tpi?.legal_name_ar ?? "");
  const [kinds, setKinds] = useState<S["TpiKind"][]>(tpi?.kinds ?? []);
  const [country, setCountry] = useState(tpi?.country ?? "SA");
  const [cr, setCr] = useState(tpi?.cr_number ?? "");
  const [foreign, setForeign] = useState(tpi?.foreign_reg_no ?? "");
  const [portal, setPortal] = useState(tpi?.verification_portal_url ?? "");
  const [domains, setDomains] = useState((tpi?.verification_domains ?? []).join(", "));
  const [email, setEmail] = useState(tpi?.verification_email ?? "");
  const [phone, setPhone] = useState(tpi?.verification_phone ?? "");
  const [contact, setContact] = useState(tpi?.contact_name ?? "");
  const [mobile, setMobile] = useState(tpi?.contact_mobile ?? "");
  const [affiliated, setAffiliated] = useState<string[]>(tpi?.affiliated_contractor_ids ?? []);
  const domainList = domains
    .split(/[\s,]+/)
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean);
  const saudi = country.trim().toUpperCase() === "SA";
  const regOk = saudi ? /^\d{10}$/.test(cr.trim()) : foreign.trim().length > 0;
  const valid = code.trim().length >= 2 && nameEn.trim() && nameAr.trim() && kinds.length > 0 && country.trim().length === 2 && domainList.length > 0 && regOk;
  async function save() {
    const common = {
      legal_name_en: nameEn.trim(),
      legal_name_ar: nameAr.trim(),
      kinds,
      country: country.trim().toUpperCase(),
      cr_number: cr.trim() || null,
      foreign_reg_no: foreign.trim() || null,
      verification_portal_url: portal.trim() || null,
      verification_domains: domainList,
      verification_email: email.trim() || null,
      verification_phone: phone.trim() || null,
      contact_name: contact.trim() || null,
      contact_mobile: mobile.trim() || null,
      affiliated_contractor_ids: affiliated,
    };
    if (tpi) {
      const r = await unwrap(api.PATCH("/api/v1/tpis/{tpi_id}", { params: { path: { tpi_id: tpi.id } }, body: common }));
      qc.setQueryData(ck.tpi(tpi.id), r);
      await qc.invalidateQueries({ queryKey: ["tpis"] });
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(api.POST("/api/v1/tpis", { body: { ...common, tpi_code: code.trim().toUpperCase() } }));
    await qc.invalidateQueries({ queryKey: ["tpis"] });
    toast.success(t("created", { code: r.tpi_code }));
    router.push(`/tpis/${r.id}`);
  }
  return (
    <StepDialog title={tpi ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-tpi">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="tpi-code" label={t("code")} required hint={t("codeHint")}>
          <Input value={code} disabled={Boolean(tpi)} onChange={(e) => setCode(e.target.value)} maxLength={16} className="ltr uppercase" data-testid="tpi-code" />
        </FormField>
        <FormField id="tpi-country" label={t("country")} required hint={t("countryHint")}>
          <Input value={country} onChange={(e) => setCountry(e.target.value)} maxLength={2} className="ltr uppercase" data-testid="tpi-country" />
        </FormField>
        <FormField id="tpi-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" data-testid="tpi-name-en" />
        </FormField>
        <FormField id="tpi-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" data-testid="tpi-name-ar" />
        </FormField>
      </div>
      {/* BD-3: no training-provider kind — training belongs to Phase 5. */}
      <CheckboxGroup id="tpi-kinds" legend={t("kinds")} required options={TPI_KINDS.map((k) => ({ value: k, label: te(`tpiKind.${k}`) }))} value={kinds} onChange={setKinds} hint={t("kindsHint")} />
      <div className="grid gap-3 sm:grid-cols-2">
        {saudi ? (
          <FormField id="tpi-cr" label={t("crNumber")} required hint={t("crHint")}>
            <Input value={cr} onChange={(e) => setCr(e.target.value.replace(/\D/g, ""))} maxLength={10} inputMode="numeric" className="ltr" data-testid="tpi-cr" />
          </FormField>
        ) : (
          <FormField id="tpi-foreign" label={t("foreignRegNo")} required>
            <Input value={foreign} onChange={(e) => setForeign(e.target.value)} maxLength={30} className="ltr" data-testid="tpi-foreign" />
          </FormField>
        )}
        <FormField id="tpi-portal" label={t("portal")}>
          <Input type="url" value={portal} onChange={(e) => setPortal(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="tpi-domains" label={t("domains")} required hint={t("domainsHint")}>
          <Input value={domains} onChange={(e) => setDomains(e.target.value)} className="ltr" data-testid="tpi-domains" />
        </FormField>
        <FormField id="tpi-email" label={t("verificationEmail")}>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="tpi-phone" label={t("verificationPhone")}>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="ltr" inputMode="tel" />
        </FormField>
        <FormField id="tpi-contact" label={t("contactName")}>
          <Input value={contact} onChange={(e) => setContact(e.target.value)} />
        </FormField>
        <FormField id="tpi-mobile" label={t("contactMobile")}>
          <Input value={mobile} onChange={(e) => setMobile(e.target.value)} className="ltr" inputMode="tel" />
        </FormField>
      </div>
      <MultiSelect
        id="tpi-affiliated"
        label={t("affiliated")}
        allLabel={t("none")}
        options={(contractors.data?.items ?? []).map((c) => ({ value: c.id, label: `${c.short_code} — ${c.legal_name_en}` }))}
        value={affiliated}
        onChange={setAffiliated}
      />
      <p className="text-xs text-muted-foreground">{t("affiliatedHint")}</p>
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function TpiDetail({ id }: { id: string }) {
  const q = useTpi(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <TpiView tpi={q.data} />;
}

type TpiStep = "submit" | "approve" | "suspend" | "reinstate" | "blacklist" | "lift" | "edit" | null;

function TpiView({ tpi }: { tpi: S["TpiRead"] }) {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date, dateTime } = useFormatters();
  const refresh = useCertRefresh();
  const [step, setStep] = useState<TpiStep>(null);
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState<S["TpiBlacklistScope"]>("all_certificates");
  const [from, setFrom] = useState(todayInZone());
  const [acc, setAcc] = useState<S["AccreditationRead"] | "new" | null>(null);
  const edit = can(me, "tpi.edit");
  const manager = can(me, "cert.blacklist");
  const impact = useTpiImpact(tpi.id, { enabled: step === "blacklist" || step === "suspend" });
  async function transition(to: S["TpiStatus"]) {
    await unwrap(
      api.POST("/api/v1/tpis/{tpi_id}/transitions", {
        params: { path: { tpi_id: tpi.id } },
        body: { to_status: to, reason: reason.trim() || null, blacklist_scope: to === "blacklisted" ? scope : null, blacklist_from: to === "blacklisted" && scope === "issued_from" ? from : null },
      }),
    );
    await refresh();
    toast.success(te(`tpiStatus.${to}`));
  }
  async function registerCheck(a: S["AccreditationRead"]) {
    await unwrap(api.POST("/api/v1/tpi-accreditations/{accreditation_id}/register-check", { params: { path: { accreditation_id: a.id } }, body: {} }));
    await refresh();
    toast.success(t("registerChecked"));
  }
  const st = tpi.status;
  const stepCfg: Record<Exclude<TpiStep, "edit" | null>, { to: S["TpiStatus"]; destructive: boolean; reason: boolean }> = {
    submit: { to: "pending_approval", destructive: false, reason: false },
    approve: { to: "approved", destructive: false, reason: false },
    reinstate: { to: "approved", destructive: false, reason: true },
    suspend: { to: "suspended", destructive: true, reason: true },
    blacklist: { to: "blacklisted", destructive: true, reason: true },
    lift: { to: "suspended", destructive: false, reason: true },
  };
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/tpis" }, { label: tpi.tpi_code }]} />
        <PageHeader
          title={`${tpi.tpi_code} — ${locale === "ar" ? tpi.legal_name_ar : tpi.legal_name_en}`}
          description={tpi.kinds.map((k) => te(`tpiKind.${k}`)).join(" · ")}
          actions={
            <>
              <TpiStatus status={st} accepted={tpi.accepted_for_use} />
              {edit && st !== "blacklisted" ? (
                <Button variant="outline" onClick={() => setStep("edit")} data-testid="edit-tpi">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {edit && st === "draft" ? (
                <Button onClick={() => setStep("submit")} data-testid="tpi-submit">
                  {t("submit")}
                </Button>
              ) : null}
              {manager && st === "pending_approval" ? (
                <Button onClick={() => setStep("approve")} data-testid="tpi-approve">
                  {t("approve")}
                </Button>
              ) : null}
              {manager && st === "approved" ? (
                <Button variant="outline" onClick={() => setStep("suspend")} data-testid="tpi-suspend">
                  {t("suspend")}
                </Button>
              ) : null}
              {manager && st === "suspended" ? (
                <Button onClick={() => setStep("reinstate")} data-testid="tpi-reinstate">
                  {t("reinstate")}
                </Button>
              ) : null}
              {manager && st === "blacklisted" ? (
                <Button variant="outline" onClick={() => setStep("lift")} data-testid="tpi-lift">
                  {t("lift")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {tpi.accreditation_lapsed ? <Alert tone="warning">{t("lapsedHint")}</Alert> : null}
      {st === "blacklisted" ? (
        <Alert tone="danger" data-testid="tpi-blacklisted">
          {t("blacklistedSince", { date: tpi.blacklist_from ? date(tpi.blacklist_from) : "—", scope: tpi.blacklist_scope ? te(`tpiBlacklistScope.${tpi.blacklist_scope}`) : "" })}
        </Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("nameEn")}>{tpi.legal_name_en}</FieldItem>
            <FieldItem label={t("nameAr")}>{tpi.legal_name_ar}</FieldItem>
            <FieldItem label={t("country")} ltr>
              {tpi.country}
            </FieldItem>
            <FieldItem label={t("crNumber")} ltr>
              {tpi.cr_number ?? tpi.foreign_reg_no ?? "—"}
            </FieldItem>
            <FieldItem label={t("domains")} ltr>
              {tpi.verification_domains.join(", ")}
            </FieldItem>
            <FieldItem label={t("portal")} ltr>
              {tpi.verification_portal_url ?? "—"}
            </FieldItem>
            <FieldItem label={t("verificationEmail")} ltr>
              {tpi.verification_email ?? "—"}
            </FieldItem>
            <FieldItem label={t("verificationPhone")} ltr>
              {tpi.verification_phone ?? "—"}
            </FieldItem>
            <FieldItem label={t("approvedBy")}>
              {tpi.approved_by ? (
                <>
                  <UserName u={tpi.approved_by} /> · {tpi.approved_at ? dateTime(tpi.approved_at) : ""}
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            {tpi.status_reason ? (
              <FieldItem label={tc("reason")} wide>
                {tpi.status_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("accreditations")}</CardTitle>
          {edit ? (
            <Button variant="outline" onClick={() => setAcc("new")} data-testid="new-accreditation">
              <Plus aria-hidden />
              {t("addAccreditation")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {tpi.accreditations.length ? (
            <Table data-testid="accreditations-table">
              <THead>
                <TR>
                  <TH>{t("standard")}</TH>
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
                {tpi.accreditations.map((a) => (
                  <TR key={a.id} data-testid="accreditation-row" data-counts={a.counts ? "yes" : "no"}>
                    <TD label={t("standard")}>
                      {te(`accreditationStandard.${a.standard}`)}
                      <span className="block text-xs text-muted-foreground">{te(`accreditationBody.${a.accreditation_body}`)}</span>
                    </TD>
                    <TD label={t("accreditationNo")}>
                      <Code>{a.accreditation_no}</Code>
                    </TD>
                    <TD label={t("scope")}>
                      <span className="text-xs">{[...a.scope_categories.map((c) => te(`eqc.${c}`)), ...a.scope_cert_types].join(" · ") || "—"}</span>
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
                      {!a.counts ? <span className="flex items-center gap-1 text-xs text-destructive font-medium"><OctagonAlert aria-hidden className="size-3.5 shrink-0" />{t("doesNotCount")}</span> : null}
                    </TD>
                    <TD label={tc("actions")}>
                      {edit ? (
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
      <HistoryPanel entityType="tpi" entityId={tpi.id} />
      {step === "edit" ? <TpiDialog tpi={tpi} onClose={() => setStep(null)} /> : null}
      {acc ? <AccreditationDialog tpi={tpi} acc={acc === "new" ? undefined : acc} onClose={() => setAcc(null)} /> : null}
      {step && step !== "edit" ? (
        <StepDialog
          title={t(`${step}Title`)}
          description={step === "blacklist" ? t("blacklistHint") : step === "suspend" ? t("suspendHint") : step === "lift" ? t("liftHint") : undefined}
          confirmLabel={t(step)}
          destructive={stepCfg[step].destructive}
          disabled={stepCfg[step].reason && reason.trim().length < (step === "blacklist" ? 20 : 5)}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={() => transition(stepCfg[step].to)}
          testId="tpi-confirm"
          wide={step === "blacklist"}
        >
          {step === "blacklist" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="tpi-scope" label={t("blacklistScope")} required>
                <Select value={scope} onChange={(e) => setScope(e.target.value as S["TpiBlacklistScope"])} data-testid="tpi-scope">
                  <option value="all_certificates">{te("tpiBlacklistScope.all_certificates")}</option>
                  <option value="issued_from">{te("tpiBlacklistScope.issued_from")}</option>
                </Select>
              </FormField>
              {scope === "issued_from" ? (
                <FormField id="tpi-from" label={t("blacklistFrom")} required>
                  <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} />
                </FormField>
              ) : null}
            </div>
          ) : null}
          {(step === "blacklist" || step === "suspend") && impact.data ? (
            <Alert tone="warning" data-testid="tpi-impact">
              {t("impact", { certs: impact.data.revoked_certificates, items: impact.data.equipment.length, holders: impact.data.holders.length, detectors: impact.data.gas_detector_ids.length })}
            </Alert>
          ) : null}
          {stepCfg[step].reason ? (
            <FormField id="tpi-reason" label={tc("reason")} required hint={step === "blacklist" ? t("reason20") : undefined}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="tpi-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
      {manager && st !== "blacklisted" ? (
        <RecordActions className="mt-0">
          <Button variant="destructive-outline" onClick={() => setStep("blacklist")} data-testid="tpi-blacklist">
            {t("blacklist")}
          </Button>
        </RecordActions>
      ) : null}
    </div>
  );
}

function AccreditationDialog({ tpi, acc, onClose }: { tpi: S["TpiRead"]; acc?: S["AccreditationRead"]; onClose: () => void }) {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useCertRefresh();
  const { types } = useCertTypes("");
  const [body, setBody] = useState<S["AccreditationBody"]>(acc?.accreditation_body ?? "sac");
  const [std, setStd] = useState<S["AccreditationStandard"]>(acc?.standard ?? "iso_iec_17020");
  const [no, setNo] = useState(acc?.accreditation_no ?? "");
  const [cats, setCats] = useState<S["EquipmentCertCategory"][]>(acc?.scope_categories ?? []);
  const [ctypes, setCtypes] = useState<string[]>(acc?.scope_cert_types ?? []);
  const [from, setFrom] = useState(acc?.valid_from ?? "");
  const [until, setUntil] = useState(acc?.valid_until ?? "");
  const [file, setFile] = useState<string | null>(acc?.certificate_attachment_id ?? null);
  const valid = no.trim() && from && until && file;
  async function save() {
    const b = { accreditation_body: body, standard: std, accreditation_no: no.trim(), scope_categories: cats, scope_cert_types: ctypes, valid_from: from, valid_until: until, certificate_attachment_id: file as string };
    if (acc) await unwrap(api.PATCH("/api/v1/tpi-accreditations/{accreditation_id}", { params: { path: { accreditation_id: acc.id } }, body: b }));
    else await unwrap(api.POST("/api/v1/tpis/{tpi_id}/accreditations", { params: { path: { tpi_id: tpi.id } }, body: b }));
    await refresh();
    toast.success(tc("saved"));
  }
  return (
    <StepDialog title={acc ? t("editAccreditation") : t("addAccreditation")} description={t("accreditationHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-accreditation">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="acc-body" label={t("accreditationBody")} required>
          <Select value={body} onChange={(e) => setBody(e.target.value as S["AccreditationBody"])}>
            {ACCREDITATION_BODIES.map((x) => (
              <option key={x} value={x}>
                {te(`accreditationBody.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="acc-std" label={t("standard")} required hint={t("standardHint")}>
          <Select value={std} onChange={(e) => setStd(e.target.value as S["AccreditationStandard"])} data-testid="acc-standard">
            {ACCREDITATION_STANDARDS.map((x) => (
              <option key={x} value={x}>
                {te(`accreditationStandard.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="acc-no" label={t("accreditationNo")} required>
          <Input value={no} onChange={(e) => setNo(e.target.value)} className="ltr" data-testid="acc-no" />
        </FormField>
        <div />
        <FormField id="acc-from" label={t("validFrom")} required>
          <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="acc-from" />
        </FormField>
        <FormField id="acc-until" label={t("validUntil")} required>
          <Input type="date" className="ltr" value={until} onChange={(e) => setUntil(e.target.value)} data-testid="acc-until" />
        </FormField>
      </div>
      {std === "iso_iec_17024" ? (
        <MultiSelect id="acc-ctypes" label={t("scopeCertTypes")} options={types.map((c) => ({ value: c.code, label: `${c.code} — ${c.label_en}` }))} value={ctypes} onChange={setCtypes} />
      ) : (
        <MultiSelect id="acc-cats" label={t("scopeCategories")} options={EQUIPMENT_CERT_CATEGORIES.map((c) => ({ value: c, label: te(`eqc.${c}`) }))} value={cats} onChange={setCats} testId="acc-cats" />
      )}
      <UploadField id="acc-file" label={t("certificateFile")} ownerType="tpi_accreditation_certificate" ownerId={tpi.id} accept="application/pdf" value={file} onChange={(v) => setFile(v)} required hint={t("pdfHint")} />
    </StepDialog>
  );
}

/* ───────────── client approvals (per project) ───────────── */

export function TpiApprovalsPage() {
  return <ProjectGate>{(p) => <TpiApprovals project={p} />}</ProjectGate>;
}

function TpiApprovals({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const q = useTpiApprovals(project.id, {});
  const [create, setCreate] = useState(false);
  const [withdraw, setWithdraw] = useState<S["ClientApprovalRead"] | null>(null);
  const edit = canWrite(me, "tpi.edit", project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("approvalsTitle")}
        description={t("approvalsSubtitle")}
        actions={
          edit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-approval">
              <Plus aria-hidden />
              {t("newApproval")}
            </Button>
          ) : null
        }
      />
      <CertSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="approvals-table">
          <THead>
            <TR>
              <TH>{t("tpi")}</TH>
              <TH>{t("approvalRef")}</TH>
              <TH>{t("scope")}</TH>
              <TH>{t("validUntil")}</TH>
              <TH>{tc("status")}</TH>
              <TH>
                <span className="sr-only">{tc("actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {items.map((a) => (
              <TR key={a.id} data-testid="approval-row">
                <TD label={t("tpi")}>
                  <TpiLabel tpi={a.tpi} />
                </TD>
                <TD label={t("approvalRef")}>
                  <Code>{a.approval_ref}</Code>
                </TD>
                <TD label={t("scope")}>
                  <span className="text-xs">{[...a.scope_categories.map((c) => te(`eqc.${c}`)), ...a.scope_cert_types].join(" · ") || t("allScope")}</span>
                </TD>
                <TD label={t("validUntil")}>
                  {date(a.valid_until)} {a.status === "active" ? <DaysLeft days={a.days_left} /> : null}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={a.status} label={te(`clientApprovalStatus.${a.status}`)} />
                </TD>
                <TD label={tc("actions")}>
                  {edit && a.status === "active" ? (
                    <Button size="sm" variant="destructive-outline" onClick={() => setWithdraw(a)} data-testid="withdraw-approval">
                      {t("withdraw")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("noApprovals")} />
      )}
      {create ? <ApprovalDialog project={project} onClose={() => setCreate(false)} /> : null}
      {withdraw ? (
        <StepDialog
          title={t("withdrawTitle")}
          description={t("withdrawHint")}
          confirmLabel={t("withdraw")}
          destructive
          onClose={() => setWithdraw(null)}
          onConfirm={async () => {
            await unwrap(api.PATCH("/api/v1/tpi-approvals/{approval_id}", { params: { path: { approval_id: withdraw.id } }, body: { status: "withdrawn" } }));
            await refresh();
          }}
          testId="withdraw-confirm"
        />
      ) : null}
    </div>
  );
}

function ApprovalDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("tpis");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useCertRefresh();
  const { types } = useCertTypes(project.id);
  const [tpi, setTpi] = useState("");
  const [ref, setRef] = useState("");
  const [cats, setCats] = useState<S["EquipmentCertCategory"][]>([]);
  const [ctypes, setCtypes] = useState<string[]>([]);
  const [until, setUntil] = useState("");
  async function save() {
    await unwrap(api.POST("/api/v1/projects/{project_id}/tpi-approvals", { params: { path: { project_id: project.id } }, body: { tpi_id: tpi, approval_ref: ref.trim(), scope_categories: cats, scope_cert_types: ctypes, valid_until: until } }));
    await refresh();
    toast.success(tc("saved"));
  }
  return (
    <StepDialog title={t("newApproval")} description={t("approvalHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!tpi || !ref.trim() || !until} wide testId="save-approval">
      <TpiSelect id="ap-tpi" label={t("tpi")} value={tpi} onChange={(v) => setTpi(v)} required />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ap-ref" label={t("approvalRef")} required>
          <Input value={ref} onChange={(e) => setRef(e.target.value)} className="ltr" data-testid="ap-ref" />
        </FormField>
        <FormField id="ap-until" label={t("validUntil")} required>
          <Input type="date" className="ltr" value={until} onChange={(e) => setUntil(e.target.value)} data-testid="ap-until" />
        </FormField>
      </div>
      <MultiSelect id="ap-cats" label={t("scopeCategories")} allLabel={t("allScope")} options={EQUIPMENT_CERT_CATEGORIES.map((c) => ({ value: c, label: te(`eqc.${c}`) }))} value={cats} onChange={setCats} />
      <MultiSelect id="ap-ctypes" label={t("scopeCertTypes")} allLabel={t("allScope")} options={types.map((c) => ({ value: c.code, label: `${c.code} — ${c.label_en}` }))} value={ctypes} onChange={setCtypes} />
    </StepDialog>
  );
}
