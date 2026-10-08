"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, CalendarClock, CircleCheck, Clock, Eye, FileImage, IdCard, OctagonX, Pencil, Plus, Search, ShieldAlert, Trash2 } from "lucide-react";
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
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, DaysLeft, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { DecimalInput } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, usePersonnelCertificate, usePersonnelCertificates, usePersonnelCertVerifications, useWorkerCertificates } from "@/lib/api/cert";
import { WORKER_ID_TYPES } from "@/lib/access-enums";
import { CERT_SOURCES, CERTIFICATE_STATUSES, PERSONNEL_LIMITATION_CODES, SCAN_REASONS, VERIFICATION_STATUSES } from "@/lib/cert-enums";
import { can, canWrite } from "@/lib/permissions";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { CertStatePanel, CertStatusBadge, CertTransitionButtons, CertValidityView, PersonnelLimitations, PersonnelSubNav, Tick, TpiLabel, TpiSelect, UploadField, UserName, VerificationBadge, VerificationsCard, useCertTypes } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── list ───────────── */

export function PersonnelCertListPage() {
  return <ProjectGate>{(p) => <PersonnelCertList project={p} />}</ProjectGate>;
}

function PersonnelCertList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const { types, label } = useCertTypes(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["CertificateStatus"][];
  const verif = s.getAll("verification_status") as S["VerificationStatus"][];
  const ctype = s.getAll("cert_type");
  const q = usePersonnelCertificates(project.id, {
    q: s.get("q") || null,
    cert_type: ctype.length ? ctype : null,
    status: status.length ? status : null,
    verification_status: verif.length ? verif : null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    source: (s.get("source") as S["CertSource"]) || null,
    in_force: s.get("in_force") === "1" ? true : s.get("in_force") === "0" ? false : null,
    expiring_days: s.getInt("expiring", 0) || null,
    verification_overdue: s.get("overdue") === "1" ? true : null,
    worker_id: s.get("worker_id") || null,
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
          canWrite(me, "personnel_cert.submit", project.id) ? (
            <Button asChild data-testid="new-pcert">
              <Link href="/personnel-certificates/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <PersonnelSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="personnel_certificates" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="pc-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="pc-type" label={t("certType")} options={types.map((x) => ({ value: x.code, label: `${x.code} — ${label(x.code)}` }))} value={ctype} onChange={(v) => s.set({ cert_type: v })} />
        <MultiSelect id="pc-status" label={tc("status")} options={CERTIFICATE_STATUSES.map((x) => ({ value: x, label: te(`certStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="pc-verif" label={t("verification")} options={VERIFICATION_STATUSES.map((x) => ({ value: x, label: te(`verificationStatus.${x}`) }))} value={verif} onChange={(v) => s.set({ verification_status: v })} />
        <SelectFilter id="pc-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter
          id="pc-inforce"
          label={t("inForce")}
          value={s.get("in_force") ?? ""}
          onChange={(v) => s.set({ in_force: v })}
          options={[
            { value: "1", label: tc("yes") },
            { value: "0", label: tc("no") },
          ]}
        />
        <SelectFilter
          id="pc-exp"
          label={t("expiring")}
          value={s.get("expiring") ?? ""}
          onChange={(v) => s.set({ expiring: v })}
          options={[
            { value: "14", label: t("withinDays", { n: 14 }) },
            { value: "30", label: t("withinDays", { n: 30 }) },
          ]}
        />
        <SelectFilter id="pc-overdue" label={t("verificationOverdue")} value={s.get("overdue") ?? ""} onChange={(v) => s.set({ overdue: v })} options={[{ value: "1", label: tc("yes") }]} />
        <SelectFilter id="pc-source" label={t("source")} value={s.get("source") ?? ""} onChange={(v) => s.set({ source: v })} options={CERT_SOURCES.map((x) => ({ value: x, label: te(`certSource.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="pcerts-table">
            <THead>
              <TR>
                <TH>{t("holder")}</TH>
                <TH>{t("certType")}</TH>
                <TH>{t("certNo")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("verification")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="pcert-row" data-cert-no={c.cert_no} data-worker={c.worker.worker_no}>
                  <TD label={t("holder")}>
                    <WorkerLabel w={c.worker} />
                    {c.engagement ? <span className="block text-xs text-muted-foreground">{c.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("certType")}>
                    <Code>{c.cert_type}</Code>
                    {c.level ? <span className="ms-1 text-xs">({te(`certLevel.${c.level}`)})</span> : null}
                    <span className="block text-xs text-muted-foreground">{label(c.cert_type)}</span>
                  </TD>
                  <TD label={t("certNo")}>
                    <Link href={`/personnel-certificates/${c.id}`} className="font-medium text-primary hover:underline">
                      <Code>{c.cert_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{c.tpi_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("validUntil")}>
                    {c.valid_until ? date(c.valid_until) : "—"} {c.in_force ? <DaysLeft days={c.days_left} /> : null}
                    {c.limiting_factor ? <span className="block text-xs text-muted-foreground">{te(`certLimitingFactor.${c.limiting_factor}`)}</span> : null}
                    {c.in_force ? <Badge tone="success">{t("inForce")}</Badge> : null}
                  </TD>
                  <TD label={t("verification")}>
                    <VerificationBadge status={c.verification_status} />
                  </TD>
                  <TD label={tc("status")}>
                    <CertStatusBadge status={c.status} />
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
    </div>
  );
}

/* ───────────── worker link (PC-3: ID typed, matched, never stored or shown in full) ───────────── */

type Holder = { worker_id: string; worker_no: string; full_name_en?: string | null; full_name_ar?: string | null; masked?: string | null };

function HolderPicker({ projectId, value, onChange, onId }: { projectId: string; value: Holder | null; onChange: (h: Holder | null) => void; onId: (id: S["IdOnCard"]) => void }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const [mode, setMode] = useState<"search" | "id">("search");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [type, setType] = useState<S["WorkerIdType"]>("iqama");
  const [num, setNum] = useState("");
  const [res, setRes] = useState<S["WorkerListItem"][] | null>(null);
  const [error, setError] = useState<unknown>(null);
  async function lookup() {
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/workers/lookup", { body: { id_type: type, id_number: num.trim(), passport_country: null } }));
      setRes(r.items);
      if (r.items.length === 1) {
        const w = r.items[0] as S["WorkerListItem"];
        onChange({ worker_id: w.id, worker_no: w.worker_no, full_name_en: w.full_name_en, full_name_ar: w.full_name_ar, masked: w.id_number_masked });
        onId({ shown: true, id_type: type, id_number: num.trim() });
      }
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="flex flex-col gap-2 sm:col-span-2" data-testid="holder-picker">
      <fieldset className="flex flex-wrap gap-4 text-sm">
        <legend className="mb-1 text-sm font-medium">{t("findHolder")}</legend>
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "search"} onChange={() => setMode("search")} />
          {t("byNameNo")}
        </label>
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "id"} onChange={() => setMode("id")} data-testid="holder-by-id" />
          {t("byIdNumber")}
        </label>
      </fieldset>
      {mode === "search" ? (
        <DeploymentPicker
          id="pc-holder"
          projectId={projectId}
          value={dep}
          onChange={(d) => {
            setDep(d);
            onChange(d ? { worker_id: d.worker_id, worker_no: d.worker_no, full_name_en: d.full_name_en, full_name_ar: d.full_name_ar } : null);
          }}
          label={t("holder")}
          required
        />
      ) : (
        <div className="grid gap-2 sm:grid-cols-[10rem_1fr_auto] sm:items-end">
          <FormField id="pc-lk-type" label={t("idType")}>
            <Select value={type} onChange={(e) => setType(e.target.value as S["WorkerIdType"])}>
              {WORKER_ID_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`workerIdType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="pc-lk-num" label={t("idOnCard")}>
            <Input value={num} onChange={(e) => setNum(e.target.value)} className="ltr font-mono" autoComplete="off" data-testid="pc-lookup-id" />
          </FormField>
          <Button variant="outline" onClick={() => void lookup()} disabled={num.trim().length < 5} data-testid="pc-lookup">
            <Search aria-hidden />
            {t("find")}
          </Button>
          <div className="sm:col-span-3">
            <MutationError error={error} />
            {res && res.length === 0 ? <p className="text-sm text-muted-foreground">{t("noWorkerForId")}</p> : null}
          </div>
        </div>
      )}
      {value ? (
        <p className="text-sm" data-testid="holder-selected">
          {t("holderSelected")} <WorkerLabel w={{ id: value.worker_id, worker_no: value.worker_no, full_name_en: value.full_name_en, full_name_ar: value.full_name_ar }} />
          {value.masked ? <Code className="ms-2 text-muted-foreground">{value.masked}</Code> : null}
        </p>
      ) : null}
    </div>
  );
}

/* ───────────── create / edit ───────────── */

export function PersonnelCertNewPage() {
  return <ProjectGate>{(p) => <PersonnelCertForm project={p} />}</ProjectGate>;
}

function PersonnelCertForm({ project, cert }: { project: S["ProjectRead"]; cert?: S["PersonnelCertRead"] }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tErr = useTranslations("errors");
  const qc = useQueryClient();
  const router = useRouter();
  const { types } = useCertTypes(project.id);
  const [holder, setHolder] = useState<Holder | null>(cert ? { worker_id: cert.worker.id, worker_no: cert.worker.worker_no, full_name_en: cert.worker.full_name_en, full_name_ar: cert.worker.full_name_ar } : null);
  const [idOnCard, setIdOnCard] = useState<S["IdOnCard"]>({ shown: true, id_type: "iqama", id_number: "" });
  const [ctype, setCtype] = useState(cert?.cert_type ?? "");
  const [tpi, setTpi] = useState(cert?.tpi.id ?? "");
  const [certNo, setCertNo] = useState(cert?.cert_no ?? "");
  const [issued, setIssued] = useState(cert?.issued_on ?? "");
  const [expiry, setExpiry] = useState(cert?.printed_expiry ?? "");
  const [scope, setScope] = useState<S["EquipmentCertCategory"][]>(cert?.scope_categories ?? []);
  const [cap, setCap] = useState(cert?.max_capacity_t ?? "");
  const [level, setLevel] = useState<S["CertLevel"] | "">(cert?.level ?? "");
  const [lims, setLims] = useState<{ code: S["PersonnelLimitationCode"]; text: string }[]>(cert?.limitations.map((l) => ({ code: l.code, text: l.text ?? "" })) ?? []);
  const [medical, setMedical] = useState(cert?.medical_restriction_on_card ?? false);
  const [nameAs, setNameAs] = useState(cert?.name_as_printed ?? "");
  const [theory, setTheory] = useState(cert?.assessment?.theory_on ?? "");
  const [practical, setPractical] = useState(cert?.assessment?.practical_on ?? "");
  const [url, setUrl] = useState(cert?.tpi_verification_url ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const info = types.find((x) => x.code === ctype);
  const base = {
    cert_type: ctype,
    tpi_id: tpi,
    cert_no: certNo.trim(),
    issued_on: issued,
    printed_expiry: expiry || null,
    scope_categories: scope,
    max_capacity_t: cap || null,
    level: level || null,
    limitations: lims.map((l) => ({ code: l.code, text: l.text.trim() || null })),
    medical_restriction_on_card: medical,
    name_as_printed: nameAs.trim(),
    assessment: theory || practical ? { theory_on: theory || null, practical_on: practical || null, language: null } : null,
    tpi_verification_url: url.trim() || null,
    worker_id: holder?.worker_id ?? "",
  };
  const idValid = !idOnCard.shown || Boolean(idOnCard.id_number?.trim());
  const ready = Boolean(holder && ctype && tpi && certNo.trim() && issued && nameAs.trim() && (!info?.level_required || level));
  const previewKey = useDebounced(JSON.stringify(base), 600);
  const preview = useQuery({
    queryKey: ["pcert-preview", project.id, previewKey],
    queryFn: () => unwrap(api.POST("/api/v1/projects/{project_id}/personnel-certificates/preview", { params: { path: { project_id: project.id } }, body: JSON.parse(previewKey) as S["PersonnelCertPreviewRequest"] })),
    enabled: ready,
    retry: false,
    placeholderData: keepPreviousData,
  });
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (cert) {
        const { worker_id: _w, ...upd } = base;
        void _w;
        const r = await unwrap(api.PATCH("/api/v1/personnel-certificates/{certificate_id}", { params: { path: { certificate_id: cert.id } }, body: { ...upd, id_on_card: idOnCard.id_number ? idOnCard : null } }));
        qc.setQueryData(ck.pcert(cert.id), r);
        await qc.invalidateQueries({ queryKey: ["personnel-certificates"] });
        toast.success(tc("saved"));
        router.push(`/personnel-certificates/${cert.id}`);
      } else {
        const r = await unwrap(api.POST("/api/v1/projects/{project_id}/personnel-certificates", { params: { path: { project_id: project.id } }, body: { ...base, id_on_card: { ...idOnCard, id_number: idOnCard.shown ? idOnCard.id_number?.trim() || null : null } } }));
        await qc.invalidateQueries({ queryKey: ["personnel-certificates"] });
        toast.success(t("created", { no: r.cert_no }));
        router.push(`/personnel-certificates/${r.id}`);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const pv = preview.data;
  const codeText = (c: string) => (tErr.has(`code.${c}` as never) ? tErr(`code.${c}` as never) : c);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/personnel-certificates" }, { label: cert ? cert.cert_no : t("new") }]} />
        <PageHeader title={cert ? t("edit") : t("new")} description={t("newHint")} />
      </div>
      <FormSection title={t("holderSection")}>
        {!cert ? (
          <HolderPicker projectId={project.id} value={holder} onChange={setHolder} onId={setIdOnCard} />
        ) : (
          <FieldItem label={t("holder")}>
            <WorkerLabel w={cert.worker} />
          </FieldItem>
        )}
        <FormField id="pc-name" label={t("nameAsPrinted")} required hint={t("nameAsPrintedHint")}>
          <Input value={nameAs} onChange={(e) => setNameAs(e.target.value)} data-testid="pc-name-as-printed" />
        </FormField>
        <div className="flex flex-col gap-2 sm:col-span-2" data-testid="id-on-card">
          <Tick id="pc-id-shown" label={t("idShownOnCard")} checked={Boolean(idOnCard.shown)} onChange={(v) => setIdOnCard({ ...idOnCard, shown: v })} />
          {idOnCard.shown ? (
            <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
              <FormField id="pc-id-type" label={t("idType")}>
                <Select value={idOnCard.id_type ?? "iqama"} onChange={(e) => setIdOnCard({ ...idOnCard, id_type: e.target.value as S["WorkerIdType"] })}>
                  {WORKER_ID_TYPES.map((x) => (
                    <option key={x} value={x}>
                      {te(`workerIdType.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="pc-id-num" label={t("idOnCard")} required={!cert} hint={t("idOnCardHint")}>
                <Input value={idOnCard.id_number ?? ""} onChange={(e) => setIdOnCard({ ...idOnCard, id_number: e.target.value })} className="ltr font-mono" autoComplete="off" data-testid="pc-id-number" />
              </FormField>
            </div>
          ) : null}
        </div>
      </FormSection>
      <FormSection title={t("certSection")}>
        <FormField id="pc-type" label={t("certType")} required>
          <Select
            value={ctype}
            onChange={(e) => {
              setCtype(e.target.value);
              setLevel("");
              setScope([]);
            }}
            data-testid="pc-cert-type"
          >
            <option value="">{tc("select")}</option>
            {types.map((x) => (
              <option key={x.code} value={x.code}>
                {x.code} — {x.label_en}
                {x.critical ? " ★" : ""}
              </option>
            ))}
          </Select>
        </FormField>
        <TpiSelect id="pc-tpi" label={t("tpi")} value={tpi} onChange={(v) => setTpi(v)} kind="personnel_certification_body" required />
        <FormField id="pc-no" label={t("certNo")} required>
          <Input value={certNo} onChange={(e) => setCertNo(e.target.value)} className="ltr" data-testid="pc-cert-no" />
        </FormField>
        <FormField id="pc-issued" label={t("issuedOn")} required>
          <Input type="date" className="ltr" value={issued} onChange={(e) => setIssued(e.target.value)} data-testid="pc-issued" />
        </FormField>
        <FormField id="pc-expiry" label={t("printedExpiry")} hint={t("printedExpiryHint", { months: info?.cap_months ?? "—" })}>
          <Input type="date" className="ltr" value={expiry} onChange={(e) => setExpiry(e.target.value)} data-testid="pc-expiry" />
        </FormField>
        {info?.levels_allowed.length ? (
          <FormField id="pc-level" label={t("level")} required={info.level_required}>
            <Select value={level} onChange={(e) => setLevel(e.target.value as S["CertLevel"])} data-testid="pc-level">
              <option value="">—</option>
              {info.levels_allowed.map((x) => (
                <option key={x} value={x}>
                  {te(`certLevel.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        {info?.scope_categories_allowed.length ? (
          <>
            <MultiSelect id="pc-scope" label={t("scopeCategories")} options={info.scope_categories_allowed.map((c) => ({ value: c, label: te(`eqc.${c}`) }))} value={scope} onChange={setScope} testId="pc-scope" />
            <FormField id="pc-cap" label={t("maxCapacity")}>
              <DecimalInput id="pc-cap" value={cap} onChange={setCap} data-testid="pc-cap" />
            </FormField>
          </>
        ) : null}
        <FormField id="pc-theory" label={t("theoryOn")}>
          <Input type="date" className="ltr" value={theory} onChange={(e) => setTheory(e.target.value)} />
        </FormField>
        <FormField id="pc-practical" label={t("practicalOn")}>
          <Input type="date" className="ltr" value={practical} onChange={(e) => setPractical(e.target.value)} />
        </FormField>
        <FormField id="pc-url" label={t("verificationUrl")}>
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} className="ltr" />
        </FormField>
        <fieldset className="flex flex-col gap-2 sm:col-span-2">
          <legend className="mb-1 text-sm font-medium">{t("limitations")}</legend>
          {lims.map((l, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[14rem_1fr_auto]">
              <Select aria-label={t("limitations")} value={l.code} onChange={(e) => setLims(lims.map((x, j) => (j === i ? { ...x, code: e.target.value as S["PersonnelLimitationCode"] } : x)))}>
                {PERSONNEL_LIMITATION_CODES.map((c) => (
                  <option key={c} value={c}>
                    {te(`personnelLimitation.${c}`)}
                  </option>
                ))}
              </Select>
              <Input aria-label={t("limitationText")} placeholder={t("limitationText")} value={l.text} onChange={(e) => setLims(lims.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
              <Button variant="ghost" onClick={() => setLims(lims.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden />
                <span className="sr-only">{tc("remove")}</span>
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" className="self-start" onClick={() => setLims([...lims, { code: "supervised_only", text: "" }])}>
            <Plus aria-hidden />
            {t("addLimitation")}
          </Button>
        </fieldset>
        <div className="sm:col-span-2">
          <Tick id="pc-medical" label={t("medicalOnCard")} checked={medical} onChange={setMedical} />
          <p className="text-xs text-muted-foreground">{t("medicalHint")}</p>
        </div>
      </FormSection>
      <Card data-testid="pcert-preview">
        <CardHeader>
          <CardTitle className="text-base">{t("preview")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {!ready ? (
            <p className="text-muted-foreground">{t("previewNeeds")}</p>
          ) : preview.isError ? (
            <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
          ) : pv ? (
            <>
              <CertValidityView v={pv.validity} projectId={project.id} />
              <span className="flex flex-wrap items-center gap-2">
                <span data-testid="preview-name-match" data-match={pv.name_match}>
                  <Badge tone={pv.name_match === "exact" ? "success" : pv.name_match === "partial" ? "warning" : "danger"}>{t("nameMatch", { m: te(`nameMatch.${pv.name_match}`) })}</Badge>
                </span>
                {pv.tpi_acceptable ? <Badge tone="success">{t("tpiAcceptable")}</Badge> : <Badge tone="danger">{t("tpiNotAcceptable")}</Badge>}
                {pv.tpi_reason ? <span className="text-xs text-destructive">{codeText(pv.tpi_reason)}</span> : null}
              </span>
              <IssueList errors={pv.errors} warnings={pv.warnings} />
            </>
          ) : (
            <LoadingState rows={1} />
          )}
        </CardContent>
      </Card>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={!ready || !idValid || busy} data-testid="save-pcert">
          {busy ? tc("saving") : cert ? tc("save") : t("saveDraft")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={cert ? `/personnel-certificates/${cert.id}` : "/personnel-certificates"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}

function IssueList({ errors, warnings }: { errors: S["ApiWarning"][]; warnings: S["ApiWarning"][] }) {
  const locale = useLocale();
  const msg = (w: S["ApiWarning"]) => (locale === "ar" && w.message_ar ? w.message_ar : w.message);
  if (!errors.length && !warnings.length) return null;
  return (
    <ul className="flex flex-col gap-1" data-testid="preview-issues">
      {errors.map((w, i) => (
        <li key={`e${i}`} className="flex gap-2 text-destructive" data-code={w.code} data-kind="error">
          <Badge tone="danger">{w.code}</Badge>
          {msg(w)}
        </li>
      ))}
      {warnings.map((w, i) => (
        <li key={`w${i}`} className="flex gap-2" data-code={w.code} data-kind="warning">
          <Badge tone="warning">{w.code}</Badge>
          {msg(w)}
        </li>
      ))}
    </ul>
  );
}

/* ───────────── detail ───────────── */

export function PersonnelCertDetail({ id }: { id: string }) {
  const q = usePersonnelCertificate(id);
  const s = useSearchState();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => (s.get("edit") === "1" ? <PersonnelCertForm project={p} cert={q.data} /> : <PersonnelCertView project={p} c={q.data} />)}</ProjectById>;
}

function PersonnelCertView({ project, c }: { project: S["ProjectRead"]; c: S["PersonnelCertRead"] }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const s = useSearchState();
  const { date, dateTime } = useFormatters(project.id);
  const verifs = usePersonnelCertVerifications(c.id);
  const refresh = useCertRefresh();
  const [scanSide, setScanSide] = useState<S["ScanSide"] | null>(null);
  const [review, setReview] = useState(false);
  const [note, setNote] = useState("");
  const submit = canWrite(me, "personnel_cert.submit", project.id);
  const verify = canWrite(me, "cert.verify", project.id);
  const scanView = can(me, "personnel_cert.scan_view", project.id);
  const notAccepted = locale === "ar" ? c.not_accepted_message_ar : c.not_accepted_message_en;
  async function setScan(side: "front" | "back", id: string | null) {
    const r = await unwrap(api.PATCH("/api/v1/personnel-certificates/{certificate_id}", { params: { path: { certificate_id: c.id } }, body: side === "front" ? { scan_front_attachment_id: id } : { scan_back_attachment_id: id } }));
    qc.setQueryData(ck.pcert(c.id), r);
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/personnel-certificates" }, { label: c.cert_no }]} />
        <PageHeader
          title={`${c.cert_type} — ${c.cert_no}`}
          description={`${locale === "ar" ? c.cert_type_label_ar : c.cert_type_label_en} · ${c.record_no}`}
          actions={
            <>
              <CertStatusBadge status={c.status} />
              <VerificationBadge status={c.verification_status} />
              {submit && c.status === "draft" ? (
                <Button variant="outline" onClick={() => s.set({ edit: "1" })} data-testid="edit-pcert">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              <CertTransitionButtons kind="personnel" id={c.id} actions={c.allowed_actions} needsIdentityTick={c.name_match !== "exact" && !c.identity_confirmed_by_tpi} />
            </>
          }
        />
      </div>
      {notAccepted ? (
        <Alert tone="danger" data-testid="not-accepted">
          {notAccepted}
        </Alert>
      ) : null}
      {(c.prompts ?? []).map((p, i) => (
        <Alert key={i} tone="info" data-testid="pcert-prompt" data-code={p.code}>
          {locale === "ar" && p.message_ar ? p.message_ar : p.message}
          {p.code === "CONSIDER_WORKER_BAN" || /ban/i.test(p.code) ? (
            <Link href={`/workers/${c.worker.id}`} className="ms-2 font-medium underline">
              {t("openWorker")}
            </Link>
          ) : null}
        </Alert>
      ))}
      {c.status === "draft" && !c.has_scan_front ? <Alert tone="info">{t("scanNeeded")}</Alert> : null}
      <ApiWarnings warnings={c.warnings} />
      {c.status_reason ? (
        <Alert tone={c.status === "suspended" || c.status === "revoked" || c.status === "rejected" ? "danger" : "info"}>
          {te(`certStatusReason.${c.status_reason}`)}
          {c.status_reason_text ? ` — ${c.status_reason_text}` : ""}
        </Alert>
      ) : null}
      <PersonnelCertStatePanel c={c} projectId={project.id} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("holder")} wide>
                <WorkerLabel w={c.worker} link />
                {c.engagement ? <Code className="ms-2 text-muted-foreground">{c.engagement.short_code}</Code> : null}
              </FieldItem>
              <FieldItem label={t("tpi")} wide>
                <TpiLabel tpi={c.tpi} />
              </FieldItem>
              <FieldItem label={t("issuedOn")}>{date(c.issued_on)}</FieldItem>
              <FieldItem label={t("printedExpiry")}>{c.printed_expiry ? date(c.printed_expiry) : "—"}</FieldItem>
              <FieldItem label={t("level")}>{c.level ? te(`certLevel.${c.level}`) : "—"}</FieldItem>
              <FieldItem label={t("scopeCategories")}>{c.scope_categories.length ? c.scope_categories.map((x) => te(`eqc.${x}`)).join(" · ") : "—"}</FieldItem>
              <FieldItem label={t("maxCapacity")}>{c.max_capacity_t ? `${c.max_capacity_t} t` : "—"}</FieldItem>
              <FieldItem label={t("nameAsPrinted")}>
                {c.name_as_printed}{" "}
                <span data-testid="name-match" data-match={c.name_match}>
                  <Badge tone={c.name_match === "exact" ? "success" : c.name_match === "partial" ? "warning" : "danger"}>{te(`nameMatch.${c.name_match}`)}</Badge>
                </span>
                {c.identity_confirmed_by_tpi ? <Badge tone="info">{t("identityConfirmedByTpi")}</Badge> : null}
              </FieldItem>
              <FieldItem label={t("idMatch")}>
                <span data-testid="id-match" data-result={c.id_match_result}>
                  <IdCard aria-hidden className="me-1 inline size-4" />
                  {te(`idMatch.${c.id_match_result}`)}
                </span>
              </FieldItem>
              <FieldItem label={t("assessment")}>
                {c.assessment ? `${c.assessment.theory_on ? date(c.assessment.theory_on) : "—"} / ${c.assessment.practical_on ? date(c.assessment.practical_on) : "—"}` : "—"}
              </FieldItem>
              <FieldItem label={t("source")}>{te(`certSource.${c.source}`)}</FieldItem>
              <FieldItem label={t("submitted")}>
                {c.submitted_by ? (
                  <>
                    <UserName u={c.submitted_by} /> · {c.submitted_at ? dateTime(c.submitted_at) : ""}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("reviewed")}>
                {c.reviewed_by ? (
                  <>
                    <UserName u={c.reviewed_by} /> · {c.reviewed_at ? dateTime(c.reviewed_at) : ""}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("verificationDue")}>{c.verification_due_on ? date(c.verification_due_on) : "—"}</FieldItem>
              <FieldItem label={t("limitations")} wide>
                {c.limitations.length ? <PersonnelLimitations items={c.limitations} /> : "—"}
              </FieldItem>
              {c.superseded_by_id ? (
                <FieldItem label={te("certStatus.superseded")} wide>
                  <Link href={`/personnel-certificates/${c.superseded_by_id}`} className="text-primary hover:underline">
                    {t("newerCard")}
                  </Link>
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          {/* PC-13 / P4-1: the flag is only in the response for capability 119. */}
          {c.medical_restriction_on_card !== undefined && c.medical_restriction_on_card !== null ? (
            <Card data-testid="medical-flag" data-flag={c.medical_restriction_on_card ? "yes" : "no"}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldAlert aria-hidden className="size-4" />
                  {t("medicalTitle")}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <p>{c.medical_restriction_on_card ? t("medicalYes") : t("medicalNo")}</p>
                {c.medical_restriction_on_card ? (
                  c.restriction_reviewed_at ? (
                    <p className="text-success" data-testid="restriction-reviewed">
                      {t("restrictionReviewedAt", { at: dateTime(c.restriction_reviewed_at) })}
                    </p>
                  ) : canWrite(me, "cert.review", project.id) ? (
                    <Button variant="outline" onClick={() => setReview(true)} data-testid="restriction-review">
                      {t("recordRestrictionReview")}
                    </Button>
                  ) : (
                    <Badge tone="warning">{t("restrictionReviewPending")}</Badge>
                  )
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileImage aria-hidden className="size-4" />
                {t("scans")}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              {(["front", "back"] as const).map((side) => {
                const has = side === "front" ? c.has_scan_front : c.has_scan_back;
                return (
                  <div key={side} className="flex flex-wrap items-center justify-between gap-2">
                    <span>{te(`scanSide.${side}`)}</span>
                    {has ? (
                      scanView ? (
                        <Button size="sm" variant="outline" onClick={() => setScanSide(side)} data-testid={`open-scan-${side}`}>
                          <Eye aria-hidden />
                          {t("openScan")}
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">{t("scanOnFile")}</span>
                      )
                    ) : (
                      <span className="text-xs text-muted-foreground">{t("noScan")}</span>
                    )}
                  </div>
                );
              })}
              {submit && c.status === "draft" ? (
                <>
                  <UploadField id="pc-scan-front" label={t("uploadFront")} ownerType="personnel_cert_scan" ownerId={c.id} accept="image/jpeg,image/png,application/pdf" value={null} onChange={(v) => void setScan("front", v)} hint={t("scanHint")} />
                  <UploadField id="pc-scan-back" label={t("uploadBack")} ownerType="personnel_cert_scan" ownerId={c.id} accept="image/jpeg,image/png,application/pdf" value={null} onChange={(v) => void setScan("back", v)} />
                </>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
      <VerificationsCard kind="personnel" id={c.id} projectId={project.id} tpi={c.tpi} canRecord={verify && (c.status === "submitted" || c.status === "accepted")} query={verifs} />
      <HistoryPanel entityType="personnel_certificate" entityId={c.id} />
      {scanSide ? <ScanDialog id={c.id} side={scanSide} onClose={() => setScanSide(null)} /> : null}
      {review ? (
        <StepDialog
          title={t("recordRestrictionReview")}
          description={t("restrictionReviewHint")}
          confirmLabel={t("recordRestrictionReview")}
          onClose={() => setReview(false)}
          onConfirm={async () => {
            const r = await unwrap(api.POST("/api/v1/personnel-certificates/{certificate_id}/restriction-review", { params: { path: { certificate_id: c.id } }, body: { note: note.trim() || null } }));
            qc.setQueryData(ck.pcert(c.id), r);
            await refresh();
          }}
          testId="restriction-review-confirm"
        >
          <FormField id="rr-note" label={t("note")} hint={t("noMedicalDetails")}>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/** P4-3: opening a scan needs a reason, is audited (sensitive_field_read) and the URL lives ≤ 5 min. */
const PENDING: S["CertificateStatus"][] = ["draft", "submitted"];
const ENDED: S["CertificateStatus"][] = ["superseded", "historic"];

/** In force or not, from the server's validity (strictest wins); the reason and the limiting factor come with it. */
function PersonnelCertStatePanel({ c, projectId }: { c: S["PersonnelCertRead"]; projectId: string }) {
  const t = useTranslations("cert");
  const td = useTranslations("certDesign");
  const te = useTranslations("enums");
  const v = c.validity;
  const pending = !v.in_force && PENDING.includes(c.status);
  const ended = !v.in_force && ENDED.includes(c.status);
  return (
    <CertStatePanel
      tone={v.in_force ? (v.expiring ? "warning" : "success") : pending ? "info" : ended ? "neutral" : "danger"}
      Icon={v.in_force ? (v.expiring ? CalendarClock : CircleCheck) : pending ? Clock : ended ? Archive : OctagonX}
      word={v.in_force ? t("inForce") : t("notInForce")}
      sub={!v.in_force ? te(`certStatus.${c.status}`) : undefined}
      line={v.in_force ? td("pc.inForceLine") : pending ? td("pc.pendingLine") : td("pc.notInForceLine")}
      testId="pcert-state"
      data={{ "data-in-force": v.in_force ? "yes" : "no" }}
    >
      <CertValidityView v={v} projectId={projectId} hideBadge />
    </CertStatePanel>
  );
}

function ScanDialog({ id, side, onClose }: { id: string; side: S["ScanSide"]; onClose: () => void }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const [reason, setReason] = useState<S["ScanReason"]>("verification");
  const [text, setText] = useState("");
  async function open() {
    const r = await unwrap(api.POST("/api/v1/personnel-certificates/{certificate_id}/scan-url", { params: { path: { certificate_id: id } }, body: { side, reason, reason_text: text.trim() || null } }));
    window.open(r.url, "_blank", "noopener");
  }
  return (
    <StepDialog title={t("openScanTitle")} description={t("openScanHint")} confirmLabel={t("openScan")} onConfirm={open} onClose={onClose} disabled={reason === "other" && text.trim().length < 5} testId="scan-confirm">
      <FormField id="sd-reason" label={t("scanReason")} required>
        <Select value={reason} onChange={(e) => setReason(e.target.value as S["ScanReason"])} data-testid="scan-reason">
          {SCAN_REASONS.map((x) => (
            <option key={x} value={x}>
              {te(`scanReason.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="sd-text" label={t("details")} required={reason === "other"}>
        <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} data-testid="scan-reason-text" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── worker certificates (worker detail tab) ───────────── */

export function WorkerCertificatesPanel({ workerId, projectId }: { workerId: string; projectId: string }) {
  const t = useTranslations("pcerts");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const { date } = useFormatters(projectId);
  const q = useWorkerCertificates(workerId, projectId);
  const d = q.data;
  return (
    <Card data-testid="worker-certificates">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("workerCerts")}</CardTitle>
        {canWrite(me, "personnel_cert.submit", projectId) ? (
          <Button size="sm" variant="outline" asChild>
            <Link href="/personnel-certificates/new">
              <Plus aria-hidden />
              {t("new")}
            </Link>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : d ? (
          <>
            {d.banned ? (
              <Alert tone="danger" data-testid="cert-ban">
                {(locale === "ar" ? d.ban_message_ar : d.ban_message_en) ?? t("certBanned")}
              </Alert>
            ) : null}
            {d.trade_requirement ? (
              <p className="text-sm" data-testid="trade-requirement" data-met={d.trade_requirement_met ? "yes" : "no"}>
                {t("tradeRequires", { code: d.trade_requirement })}{" "}
                {d.trade_requirement_met ? <Badge tone="success">{t("met")}</Badge> : <Badge tone="danger">{te("hookReason.CERT_MISSING")}</Badge>}
              </p>
            ) : null}
            {d.certificates.length ? (
              <ul className="flex flex-col divide-y">
                {d.certificates.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" data-testid="worker-cert" data-type={c.cert_type} data-in-force={c.in_force ? "yes" : "no"}>
                    <span>
                      <Code className="font-medium">{c.cert_type}</Code> {locale === "ar" ? c.cert_type_label_ar : c.cert_type_label_en}
                      {c.level ? ` (${te(`certLevel.${c.level}`)})` : ""}
                      <span className="block text-xs text-muted-foreground">
                        <Link href={`/personnel-certificates/${c.id}`} className="hover:underline">
                          <Code>{c.cert_no}</Code>
                        </Link>{" "}
                        · <Code>{c.tpi_code}</Code>
                        {c.scope_categories.length ? ` · ${c.scope_categories.map((x) => te(`eqc.${x}`)).join(", ")}` : ""}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      {c.valid_until ? <span className="text-xs">{date(c.valid_until)}</span> : null}
                      {c.in_force ? <Badge tone="success">{t("inForce")}</Badge> : <Badge tone="danger">{c.not_in_force_reason && te.has(`hookReason.${c.not_in_force_reason as S["HookReasonCode"]}`) ? te(`hookReason.${c.not_in_force_reason as S["HookReasonCode"]}`) : te(`certStatus.${c.status}`)}</Badge>}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("noWorkerCerts")}</p>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

