"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Ban, Camera, CreditCard, FileDown, Pencil, Plus, Printer, RefreshCw, Search, ShieldCheck, UserCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { DEPLOYMENT_STATUSES, EXPORT_PURPOSES_ACCESS, TRADES, WORKER_ID_TYPES, WORKER_LANGUAGES, WORKER_PERSON_TYPES, WORKER_STATUSES } from "@/lib/access-enums";
import { ak, useAccessCard, useDeployment, useEligibility, useInductions, useWorker, useWorkers } from "@/lib/api/access";
import { ApiError, api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useCurrentProject } from "@/lib/current-project";
import { formatDate, todayInZone, zonedInputToUtc } from "@/lib/datetime";
import { applyServerErrors } from "@/lib/forms";
import { useErrorMessage, useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { AccessPrintHeader, BiLabel, Code, EligibilityItems, MaskedIdNumber, QrImage, SubNav, WorkerPhoto, personName } from "./common";
import { CredentialPanel } from "./credential-actions";
import { WorkerCertificatesPanel } from "@/components/cert/personnel";

const PAGE_SIZE = 50;

export function WorkerSubNav() {
  const t = useTranslations("workers");
  const ti = useTranslations("inductions");
  const me = useMeData();
  const { projectId } = useCurrentProject();
  return (
    <SubNav
      items={[
        { href: "/workers", label: t("title"), testId: "sub-workers" },
        { href: "/inductions", label: ti("records"), show: can(me, "worker.view", projectId) || can(me, "induction.record", projectId), testId: "sub-inductions" },
        { href: "/induction-courses", label: ti("courses"), show: can(me, "induction.course_manage", projectId) || can(me, "induction.record", projectId), testId: "sub-courses" },
      ]}
    />
  );
}

export function WorkerList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const engs = s.getAll("engagement_id");
  const depStatus = s.getAll("deployment_status") as Schemas["DeploymentStatus"][];
  const status = s.getAll("status") as Schemas["WorkerStatus"][];
  const q: Parameters<typeof useWorkers>[0] = {
    project_id: project.id,
    q: s.get("q") || null,
    engagement_id: engs.length ? engs : null,
    include_subcontractors: s.getBool("include_subcontractors") ?? true,
    site_id: s.getAll("site_id").length ? s.getAll("site_id") : null,
    deployment_status: depStatus.length ? depStatus : null,
    status: status.length ? status : null,
    person_type: (s.get("person_type") as Schemas["WorkerPersonType"] | null) || null,
    trade: (s.get("trade") as Schemas["Trade"] | null) || null,
    sort: "worker_no",
    page,
    page_size: PAGE_SIZE,
  };
  const query = useWorkers(q);
  const items = query.data?.items ?? [];
  const [lookup, setLookup] = useState(false);
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            <Button variant="outline" onClick={() => setLookup(true)} data-testid="id-lookup">
              <Search aria-hidden />
              {t("lookup")}
            </Button>
            {canWrite(me, "worker.edit", project.id) ? (
              <Button asChild>
                <Link href="/workers/new" data-testid="new-worker">
                  <Plus aria-hidden />
                  {t("new")}
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      <WorkerSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="workers" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="wk-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="wk-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <MultiSelect
          id="wk-dep"
          label={t("deploymentStatus")}
          options={DEPLOYMENT_STATUSES.map((x) => ({ value: x, label: te(`deploymentStatus.${x}`) }))}
          value={depStatus}
          onChange={(v) => s.set({ deployment_status: v })}
        />
        <SelectFilter id="wk-trade" label={t("fields.trade")} value={(q.trade ?? "") as Schemas["Trade"] | ""} onChange={(v) => s.set({ trade: v })} options={TRADES.map((x) => ({ value: x, label: te(`trade.${x}`) }))} />
        <SelectFilter
          id="wk-type"
          label={t("fields.person_type")}
          value={(q.person_type ?? "") as Schemas["WorkerPersonType"] | ""}
          onChange={(v) => s.set({ person_type: v })}
          options={WORKER_PERSON_TYPES.map((x) => ({ value: x, label: te(`workerPersonType.${x}`) }))}
        />
        <MultiSelect id="wk-site" label={tc("site")} options={opts.sites} value={s.getAll("site_id")} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="wk-status" label={t("fields.status")} options={WORKER_STATUSES.map((x) => ({ value: x, label: te(`workerStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="workers-table">
            <THead>
              <TR>
                <TH>{t("fields.worker_no")}</TH>
                <TH>{t("fields.name")}</TH>
                <TH>{t("fields.id_number")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("fields.trade")}</TH>
                <TH>{t("deploymentStatus")}</TH>
                <TH>{t("inductions")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((w) => (
                <TR key={w.id} data-testid="worker-row" data-worker-no={w.worker_no}>
                  <TD label={t("fields.worker_no")}>
                    <Link href={`/workers/${w.id}`} className="ltr font-medium text-primary hover:underline">
                      {w.worker_no}
                    </Link>
                  </TD>
                  <TD label={t("fields.name")}>{personName(w, locale)}</TD>
                  <TD label={t("fields.id_number")}>
                    <bdi className="ltr font-mono tabular-nums" data-testid="masked-id">
                      {w.id_number_masked ?? "—"}
                    </bdi>
                    {w.id_expiry_date ? <span className="block text-xs text-muted-foreground">{date(w.id_expiry_date)}</span> : null}
                  </TD>
                  <TD label={tc("contractor")}>{w.deployment?.engagement ? <Code>{w.deployment.engagement.short_code}</Code> : w.person_type !== "contractor_worker" ? te(`workerPersonType.${w.person_type}`) : "—"}</TD>
                  <TD label={t("fields.trade")}>{w.deployment ? te(`trade.${w.deployment.trade}`) : "—"}</TD>
                  <TD label={t("deploymentStatus")}>{w.deployment ? <StatusBadge status={w.deployment.status} label={te(`deploymentStatus.${w.deployment.status}`)} /> : "—"}</TD>
                  <TD label={t("inductions")}>
                    <span className="flex flex-wrap gap-1">
                      {(w.deployment?.inductions ?? []).map((i) => (
                        <StatusBadge key={i.course_code} status={i.status} label={`${i.course_code} · ${te(`inductionStatus.${i.status}`)}`} />
                      ))}
                    </span>
                  </TD>
                  <TD label={t("fields.status")}>
                    <StatusBadge status={w.status} label={te(`workerStatus.${w.status}`)} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
      {lookup ? <IdLookupDialog onClose={() => setLookup(false)} /> : null}
    </div>
  );
}

/** WK-3: exact full-number match through the blind index; POST so the number stays out of URLs. */
function IdLookupDialog({ onClose }: { onClose: () => void }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [type, setType] = useState<Schemas["WorkerIdType"]>("iqama");
  const [num, setNum] = useState("");
  const [country, setCountry] = useState("");
  const [res, setRes] = useState<Schemas["WorkerListItem"][] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/workers/lookup", { body: { id_type: type, id_number: num.trim(), passport_country: type === "passport" ? country.trim().toUpperCase() || null : null } }));
      setRes(r.items);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("lookup")}</DialogTitle>
          <DialogDescription>{t("lookupHint")}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-3"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <FormField id="lk-type" label={t("fields.id_type")}>
            <Select value={type} onChange={(e) => setType(e.target.value as Schemas["WorkerIdType"])}>
              {WORKER_ID_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`workerIdType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="lk-number" label={t("fields.id_number")} required>
            <Input value={num} onChange={(e) => setNum(e.target.value)} inputMode={type === "iqama" || type === "national_id" ? "numeric" : "text"} className="ltr font-mono" autoComplete="off" />
          </FormField>
          {type === "passport" ? (
            <FormField id="lk-country" label={t("fields.passport_country")}>
              <Input value={country} onChange={(e) => setCountry(e.target.value)} maxLength={2} className="ltr uppercase" />
            </FormField>
          ) : null}
          <MutationError error={error} />
          {res ? (
            res.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="lookup-none">
                {t("lookupNone")}
              </p>
            ) : (
              <ul className="flex flex-col divide-y rounded-md border" data-testid="lookup-results">
                {res.map((w) => (
                  <li key={w.id}>
                    <Link href={`/workers/${w.id}`} className="flex min-h-touch items-center gap-2 px-3 text-sm text-primary hover:bg-accent" onClick={onClose}>
                      <Code>{w.worker_no}</Code> {personName(w, locale)}
                    </Link>
                  </li>
                ))}
              </ul>
            )
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {tc("close")}
            </Button>
            <Button type="submit" disabled={busy || num.trim().length < 6} data-testid="lookup-run">
              <Search aria-hidden />
              {tc("search")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const ISO2 = /^[A-Z]{2}$/;

function deploymentSchema(tv: (k: "required") => string) {
  return z.object({
    engagement_id: z.string(),
    employee_no: z.string().max(20),
    trade: z.string().min(1, tv("required")),
    site_ids: z.array(z.string()).min(1, tv("required")),
    mobilised_on: z.string().min(1, tv("required")),
    planned_demob_on: z.string(),
  });
}

export function WorkerForm({ project, worker }: { project: Schemas["ProjectRead"]; worker?: Schemas["WorkerRead"] }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const [error, setError] = useState<unknown>(null);
  const [existing, setExisting] = useState<{ id: string; no: string } | null>(null);
  const editing = Boolean(worker);
  const schema = useMemo(
    () =>
      z
        .object({
          person_type: z.enum(WORKER_PERSON_TYPES),
          full_name_en: z.string().trim().min(1, tv("required")).max(120),
          full_name_ar: z.string().trim().min(1, tv("required")).max(120),
          id_type: z.enum(WORKER_ID_TYPES),
          id_number: z.string().trim(),
          passport_country: z.string().trim(),
          id_expiry_date: z.string().min(1, tv("required")),
          nationality: z.string().trim().toUpperCase().regex(ISO2, t("iso2")),
          adult_attestation: z.boolean(),
          primary_language: z.enum(WORKER_LANGUAGES),
          dep: deploymentSchema(tv),
        })
        .superRefine((v, ctx) => {
          if (!editing && v.id_number.length < 6) ctx.addIssue({ code: "custom", path: ["id_number"], message: tv("required") });
          if (v.id_number) {
            const re = v.id_type === "iqama" ? /^2\d{9}$/ : v.id_type === "national_id" ? /^1\d{9}$/ : v.id_type === "gcc_id" ? /^[A-Z0-9]{6,15}$/ : /^[A-Z0-9]{6,9}$/;
            if (!re.test(v.id_number.toUpperCase())) ctx.addIssue({ code: "custom", path: ["id_number"], message: t(`idFormat.${v.id_type}`) });
          }
          if (v.id_type === "passport" && !ISO2.test(v.passport_country.toUpperCase())) ctx.addIssue({ code: "custom", path: ["passport_country"], message: t("iso2") });
          if (!editing && !v.adult_attestation) ctx.addIssue({ code: "custom", path: ["adult_attestation"], message: t("adultRequired") });
          if (!editing && v.person_type === "contractor_worker" && !v.dep.engagement_id) ctx.addIssue({ code: "custom", path: ["dep", "engagement_id"], message: tv("required") });
        }),
    [tv, t, editing],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      person_type: worker?.person_type ?? "contractor_worker",
      full_name_en: worker?.full_name_en ?? "",
      full_name_ar: worker?.full_name_ar ?? "",
      id_type: worker?.id_type ?? "iqama",
      id_number: "",
      passport_country: worker?.passport_country ?? "",
      id_expiry_date: worker?.id_expiry_date ?? "",
      nationality: worker?.nationality ?? "",
      adult_attestation: worker?.adult_attestation ?? false,
      primary_language: worker?.primary_language ?? "en",
      dep: { engagement_id: "", employee_no: "", trade: "", site_ids: [], mobilised_on: todayInZone(), planned_demob_on: "" },
    },
  });
  const { errors, isSubmitting } = form.formState;
  const idType = useWatch({ control: form.control, name: "id_type" });
  const personType = useWatch({ control: form.control, name: "person_type" });
  const engId = useWatch({ control: form.control, name: "dep.engagement_id" });
  const siteIds = useWatch({ control: form.control, name: "dep.site_ids" });
  const eng = opts.engagements.find((e) => e.value === engId);
  const siteOptions = opts.sites.filter((s) => !eng || eng.siteIds.includes(s.value));

  async function save(v: Values) {
    setError(null);
    setExisting(null);
    try {
      let saved: Schemas["WorkerRead"];
      if (worker) {
        saved = await unwrap(
          api.PATCH("/api/v1/workers/{worker_id}", {
            params: { path: { worker_id: worker.id } },
            body: {
              full_name_en: v.full_name_en,
              full_name_ar: v.full_name_ar,
              id_type: v.id_number ? v.id_type : undefined,
              id_number: v.id_number ? v.id_number.toUpperCase() : undefined,
              passport_country: v.id_type === "passport" ? v.passport_country.toUpperCase() : null,
              id_expiry_date: v.id_expiry_date,
              nationality: v.nationality.toUpperCase(),
              primary_language: v.primary_language,
            },
          }),
        );
      } else {
        saved = await unwrap(
          api.POST("/api/v1/workers", {
            body: {
              person_type: v.person_type,
              full_name_en: v.full_name_en,
              full_name_ar: v.full_name_ar,
              id_type: v.id_type,
              id_number: v.id_number.toUpperCase(),
              passport_country: v.id_type === "passport" ? v.passport_country.toUpperCase() : null,
              id_expiry_date: v.id_expiry_date,
              nationality: v.nationality.toUpperCase(),
              adult_attestation: v.adult_attestation,
              primary_language: v.primary_language,
              deployment: {
                project_id: project.id,
                engagement_id: v.person_type === "contractor_worker" ? v.dep.engagement_id : null,
                employee_no: v.dep.employee_no.trim() || null,
                trade: v.dep.trade as Schemas["Trade"],
                site_ids: v.dep.site_ids,
                mobilised_on: v.dep.mobilised_on,
                planned_demob_on: v.dep.planned_demob_on || null,
              },
            },
          }),
        );
      }
      // The ID number typed here is not kept anywhere after saving.
      form.setValue("id_number", "");
      qc.setQueryData(ak.worker(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["workers"] });
      await qc.invalidateQueries({ queryKey: ["deployments"] });
      warn(saved.warnings);
      toast.success(worker ? tc("saved") : t("created", { no: saved.worker_no }));
      router.push(`/workers/${saved.id}`);
    } catch (e) {
      setError(e);
      if (e instanceof ApiError && e.code === "WORKER_EXISTS" && typeof e.meta.worker_id === "string") {
        setExisting({ id: e.meta.worker_id, no: String(e.meta.worker_no ?? "") });
      }
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate autoComplete="off" className="flex max-w-3xl flex-col gap-6" data-testid="worker-form">
      <FormSection title={t("person")}>
        <FormField id="person_type" label={t("fields.person_type")} required error={errors.person_type?.message}>
          <Select disabled={editing} {...form.register("person_type")}>
            {WORKER_PERSON_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`workerPersonType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="primary_language" label={t("fields.primary_language")} required error={errors.primary_language?.message}>
          <Select {...form.register("primary_language")}>
            {WORKER_LANGUAGES.map((x) => (
              <option key={x} value={x}>
                {te(`workerLanguage.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="full_name_en" label={t("fields.full_name_en")} required error={errors.full_name_en?.message}>
          <Input dir="ltr" maxLength={120} {...form.register("full_name_en")} />
        </FormField>
        <FormField id="full_name_ar" label={t("fields.full_name_ar")} required error={errors.full_name_ar?.message}>
          <Input dir="rtl" lang="ar" maxLength={120} {...form.register("full_name_ar")} />
        </FormField>
        <FormField id="nationality" label={t("fields.nationality")} required error={errors.nationality?.message} hint={t("iso2Hint")}>
          <Input maxLength={2} className="ltr uppercase" {...form.register("nationality")} />
        </FormField>
      </FormSection>
      <FormSection title={t("identity")} description={editing ? t("idEditHint") : t("idHint")}>
        <FormField id="id_type" label={t("fields.id_type")} required error={errors.id_type?.message}>
          <Select {...form.register("id_type")}>
            {WORKER_ID_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`workerIdType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="id_number" label={editing ? t("fields.id_number_new") : t("fields.id_number")} required={!editing} error={errors.id_number?.message}>
          <Input className="ltr font-mono" inputMode={idType === "iqama" || idType === "national_id" ? "numeric" : "text"} autoComplete="off" maxLength={15} {...form.register("id_number")} />
        </FormField>
        {idType === "passport" ? (
          <FormField id="passport_country" label={t("fields.passport_country")} required error={errors.passport_country?.message}>
            <Input maxLength={2} className="ltr uppercase" {...form.register("passport_country")} />
          </FormField>
        ) : null}
        <FormField id="id_expiry_date" label={t("fields.id_expiry_date")} required error={errors.id_expiry_date?.message}>
          <Input type="date" {...form.register("id_expiry_date")} />
        </FormField>
        {!editing ? (
          <div className="sm:col-span-2">
            <CheckboxField id="adult_attestation" label={t("fields.adult_attestation")} error={errors.adult_attestation?.message}>
              <Checkbox {...form.register("adult_attestation")} />
            </CheckboxField>
          </div>
        ) : null}
      </FormSection>
      {!editing ? (
        <FormSection title={t("deploymentOn", { code: project.code })} description={t("deploymentHint")}>
          {personType === "contractor_worker" ? (
            <FormField id="dep.engagement_id" label={tc("contractor")} required error={errors.dep?.engagement_id?.message}>
              <Select {...form.register("dep.engagement_id", { onChange: () => form.setValue("dep.site_ids", []) })}>
                <option value="">{tc("select")}</option>
                {opts.engagements
                  .filter((e) => e.status === "approved")
                  .map((e) => (
                    <option key={e.value} value={e.value}>
                      {e.label}
                    </option>
                  ))}
              </Select>
            </FormField>
          ) : null}
          <FormField id="dep.trade" label={t("fields.trade")} required error={errors.dep?.trade?.message}>
            <Select {...form.register("dep.trade")}>
              <option value="">{tc("select")}</option>
              {TRADES.map((x) => (
                <option key={x} value={x}>
                  {te(`trade.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="dep.employee_no" label={t("fields.employee_no")} error={errors.dep?.employee_no?.message}>
            <Input className="ltr" maxLength={20} {...form.register("dep.employee_no")} />
          </FormField>
          <div className="flex flex-col gap-1.5">
            <MultiSelect id="dep-sites" label={`${t("fields.sites")} *`} options={siteOptions} value={siteIds} onChange={(v) => form.setValue("dep.site_ids", v, { shouldValidate: true })} className="lg:w-full" testId="dep-sites" />
            {errors.dep?.site_ids?.message ? (
              <p role="alert" className="text-xs font-medium text-destructive">
                {errors.dep.site_ids.message}
              </p>
            ) : null}
          </div>
          <FormField id="dep.mobilised_on" label={t("fields.mobilised_on")} required error={errors.dep?.mobilised_on?.message}>
            <Input type="date" {...form.register("dep.mobilised_on")} />
          </FormField>
          <FormField id="dep.planned_demob_on" label={t("fields.planned_demob_on")} error={errors.dep?.planned_demob_on?.message}>
            <Input type="date" {...form.register("dep.planned_demob_on")} />
          </FormField>
        </FormSection>
      ) : null}
      <MutationError error={error} />
      {existing ? (
        <Alert tone="info" data-testid="worker-exists">
          {t("existsOpen")}{" "}
          <Link href={`/workers/${existing.id}`} className="font-medium text-primary underline">
            <Code>{existing.no}</Code>
          </Link>
        </Alert>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-worker">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={worker ? `/workers/${worker.id}` : "/workers"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}

export function WorkerDetail({ id }: { id: string }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const name = useLocalizedName();
  const { project } = useCurrentProject();
  const q = useWorker(id);
  const { date } = useFormatters(project?.id);
  const [ban, setBan] = useState<null | "banned" | "active">(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const msg = useErrorMessage();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const w = q.data;
  const full = personName(w, locale);
  const here = w.deployments.filter((d) => d.project_id === project?.id);
  const current = here.find((d) => d.status !== "demobilised") ?? here[0] ?? null;
  const pid = project?.id ?? null;
  const canEdit = canWrite(me, "worker.edit", pid);

  async function uploadPhoto(files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    try {
      const fd = new FormData();
      fd.set("owner_type", "worker_photo");
      fd.set("owner_id", w.id);
      fd.set("file", f);
      await postForm<Schemas["AttachmentRead"]>("/api/v1/attachments", fd);
      await qc.invalidateQueries({ queryKey: ak.worker(w.id) });
      toast.success(t("photoSaved"));
    } catch (e) {
      toast.error(msg(e));
    } finally {
      if (photoRef.current) photoRef.current.value = "";
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workers"), href: "/workers" }, { label: w.worker_no }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <WorkerPhoto attachmentId={w.photo_attachment_id} name={full} />
                <div className="min-w-0">
                  <p className="text-sm text-muted-foreground" data-testid="worker-no">
                    <Code>{w.worker_no}</Code>
                  </p>
                  <CardTitle className="flex flex-wrap items-center gap-2" data-testid="worker-title">
                    {full}
                    <StatusBadge status={w.status} label={te(`workerStatus.${w.status}`)} />
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">{locale === "ar" ? w.full_name_en : w.full_name_ar}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {canEdit && w.status !== "anonymised" ? (
                  <>
                    <Button size="sm" variant="outline" asChild>
                      <Link href={`/workers/${w.id}/edit`} data-testid="edit-worker">
                        <Pencil aria-hidden />
                        {tc("edit")}
                      </Link>
                    </Button>
                    <input ref={photoRef} type="file" accept="image/jpeg,image/png" capture="user" className="sr-only" onChange={(e) => void uploadPhoto(e.target.files)} data-testid="photo-input" />
                    <Button size="sm" variant="outline" onClick={() => photoRef.current?.click()}>
                      <Camera aria-hidden />
                      {w.photo_attachment_id ? t("replacePhoto") : t("addPhoto")}
                    </Button>
                  </>
                ) : null}
                {canWrite(me, "worker.ban", pid) && (w.status === "active" || w.status === "inactive") ? (
                  <Button size="sm" variant="destructive" onClick={() => setBan("banned")} data-testid="ban-worker">
                    <Ban aria-hidden />
                    {t("ban")}
                  </Button>
                ) : null}
                {canWrite(me, "worker.ban", pid) && w.status === "banned" ? (
                  <Button size="sm" variant="outline" onClick={() => setBan("active")} data-testid="lift-ban">
                    <UserCheck aria-hidden />
                    {t("liftBan")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <ApiWarnings warnings={w.warnings} />
              {w.status === "banned" && w.ban_reason ? <Alert tone="danger">{t("bannedBecause", { reason: w.ban_reason })}</Alert> : null}
              {w.id_expired ? <Alert tone="danger">{t("idExpired")}</Alert> : null}
              <FieldList>
                <FieldItem label={t("fields.id_number")}>
                  <MaskedIdNumber worker={w} />
                </FieldItem>
                <FieldItem label={t("fields.id_expiry_date")}>{date(w.id_expiry_date)}</FieldItem>
                <FieldItem label={t("fields.person_type")}>{te(`workerPersonType.${w.person_type}`)}</FieldItem>
                <FieldItem label={t("fields.nationality")}>
                  <Code>{w.nationality ?? "—"}</Code>
                </FieldItem>
                <FieldItem label={t("fields.primary_language")}>{te(`workerLanguage.${w.primary_language}`)}</FieldItem>
                <FieldItem label={t("fields.user")}>{w.user ? name(w.user.full_name_en, w.user.full_name_ar) : "—"}</FieldItem>
              </FieldList>
            </CardContent>
          </Card>
          {current && pid ? <DeploymentCard id={current.id} worker={w} /> : <Alert tone="info">{t("notOnProject")}</Alert>}
          {pid ? <EligibilityChecker workerId={w.id} projectId={pid} /> : null}
          {pid && can(me, "personnel_cert.view", pid) ? <WorkerCertificatesPanel workerId={w.id} projectId={pid} /> : null}
          {pid && current ? <WorkerInductions workerId={w.id} deploymentId={current.id} projectId={pid} /> : null}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("allDeployments")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col divide-y" data-testid="deployments">
                {w.deployments.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <span>
                      <Code className="font-medium">{d.project_code}</Code>
                      {d.engagement ? (
                        <>
                          {" · "}
                          <Code>{d.engagement.short_code}</Code>
                        </>
                      ) : null}{" "}
                      · {te(`trade.${d.trade}`)}
                    </span>
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      {date(d.mobilised_on)}
                      {d.demobilised_on ? ` → ${date(d.demobilised_on)}` : ""}
                      <StatusBadge status={d.status} label={te(`deploymentStatus.${d.status}`)} />
                    </span>
                  </li>
                ))}
              </ul>
              {pid && canEdit && !current?.status.match(/pending_induction|mobilised/) && w.status !== "banned" ? <NewDeployment workerId={w.id} project={project} /> : null}
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          {pid && can(me, "export.access_identity", pid) ? <DataReport worker={w} /> : null}
          {can(me, "history.view", pid) ? <HistoryPanel entityType="worker" entityId={w.id} projectId={pid} /> : null}
        </div>
      </div>
      {ban ? <BanDialog worker={w} to={ban} onClose={() => setBan(null)} /> : null}
    </div>
  );
}

function BanDialog({ worker, to, onClose }: { worker: Schemas["WorkerRead"]; to: "banned" | "active"; onClose: () => void }) {
  const t = useTranslations("workers");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      const w = await unwrap(api.POST("/api/v1/workers/{worker_id}/transitions", { params: { path: { worker_id: worker.id } }, body: { to_status: to, reason: reason.trim() } }));
      qc.setQueryData(ak.worker(w.id), w);
      await qc.invalidateQueries({ queryKey: ["workers"] });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{to === "banned" ? t("ban") : t("liftBan")}</DialogTitle>
          <DialogDescription>{to === "banned" ? t("banHelp") : t("liftBanHelp")}</DialogDescription>
        </DialogHeader>
        <FormField id="ban-reason" label={tc("reason")} required hint={t("banReasonHint")}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={to === "banned" ? "destructive" : "default"} disabled={busy || reason.trim().length < 10} onClick={() => void go()} data-testid="ban-confirm">
            {to === "banned" ? t("ban") : t("liftBan")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeploymentCard({ id, worker }: { id: string; worker: Schemas["WorkerRead"] }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const q = useDeployment(id);
  const [demob, setDemob] = useState(false);
  const [edit, setEdit] = useState(false);
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState rows={2} />;
  const d = q.data;
  const canEdit = canWrite(me, "worker.edit", d.project_id);
  return (
    <Card data-testid="deployment-card" data-status={d.status}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {t("deployment")}
          <StatusBadge status={d.status} label={te(`deploymentStatus.${d.status}`)} />
        </CardTitle>
        <div className="flex flex-wrap gap-2">
          {canEdit && d.status !== "demobilised" ? (
            <Button size="sm" variant="outline" onClick={() => setEdit(true)} data-testid="edit-deployment">
              <Pencil aria-hidden />
              {tc("edit")}
            </Button>
          ) : null}
          {canEdit && d.status === "mobilised" ? (
            <Button size="sm" variant="destructive" onClick={() => setDemob(true)} data-testid="demobilise">
              {t("demobilise")}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ApiWarnings warnings={d.warnings} />
        <FieldList>
          <FieldItem label={tc("contractor")}>{d.engagement ? `${d.engagement.short_code} — ${name(d.engagement.name_en, d.engagement.name_ar)}` : te(`workerPersonType.${worker.person_type}`)}</FieldItem>
          <FieldItem label={t("fields.trade")}>{te(`trade.${d.trade}`)}</FieldItem>
          <FieldItem label={t("fields.employee_no")}>
            <Code>{d.employee_no ?? "—"}</Code>
          </FieldItem>
          <FieldItem label={t("fields.sites")}>{d.sites.map((s) => s.code).join(", ")}</FieldItem>
          <FieldItem label={t("fields.mobilised_on")}>{date(d.mobilised_on)}</FieldItem>
          <FieldItem label={t("fields.planned_demob_on")}>{date(d.planned_demob_on)}</FieldItem>
          {d.demobilised_on ? <FieldItem label={t("fields.demobilised_on")}>{date(d.demobilised_on)}</FieldItem> : null}
        </FieldList>
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">{t("inductions")}</p>
          <div className="flex flex-wrap gap-1.5" data-testid="induction-badges">
            {d.inductions.length === 0 ? <span className="text-sm text-muted-foreground">—</span> : null}
            {d.inductions.map((i) => (
              <StatusBadge key={i.course_code} status={i.status} label={`${i.course_code} · ${te(`inductionStatus.${i.status}`)}${i.valid_until ? ` · ${date(i.valid_until)}` : ""}`} />
            ))}
          </div>
        </div>
        {d.credentials.length > 0 ? (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-muted-foreground">{t("credentials")}</p>
            <ul className="flex flex-col divide-y rounded-md border" data-testid="credential-badges">
              {d.credentials.map((c) => {
                const href = c.kind === "airport_pass" ? `/airport-passes/${c.id}` : c.kind === "adp" ? `/adps/${c.id}` : c.kind === "induction" ? `/inductions/${c.id}` : null;
                const label = te(`credentialKind.${c.kind as Schemas["CredentialKind"]}`);
                return (
                  <li key={`${c.kind}-${c.id}`} className="flex flex-wrap items-center justify-between gap-2 p-2 text-sm">
                    <span>
                      {label} ·{" "}
                      {href ? (
                        <Link href={href} className="text-primary hover:underline">
                          <Code>{c.number}</Code>
                        </Link>
                      ) : (
                        <Code>{c.number}</Code>
                      )}
                      {c.detail ? <span className="ms-2 text-xs text-muted-foreground">{c.detail}</span> : null}
                    </span>
                    <span className="flex items-center gap-2 text-xs">
                      {c.effective_valid_until ? date(c.effective_valid_until) : null}
                      <StatusBadge status={c.validity_status} label={te(`validityStatus.${c.validity_status}`)} />
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
        <AccessCardBlock deployment={d} />
      </CardContent>
      {demob ? <DemobiliseDialog deployment={d} onClose={() => setDemob(false)} /> : null}
      {edit ? <EditDeploymentDialog deployment={d} onClose={() => setEdit(false)} /> : null}
    </Card>
  );
}

function AccessCardBlock({ deployment }: { deployment: Schemas["DeploymentRead"] }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const mobilised = deployment.status === "mobilised";
  const card = useAccessCard(deployment.id, { enabled: mobilised && deployment.access_card.token_status !== null });
  const [reissue, setReissue] = useState(false);
  const [reason, setReason] = useState<Schemas["AccessCardReissueReason"]>("damaged");
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const { date } = useFormatters(deployment.project_id);
  if (deployment.status === "pending_induction")
    return (
      <Alert tone="info" data-testid="card-pending">
        {t("cardAfterInduction")}
      </Alert>
    );
  async function doReissue() {
    setError(null);
    try {
      const c = await unwrap(
        api.POST("/api/v1/deployments/{deployment_id}/access-card/reissue", { params: { path: { deployment_id: deployment.id } }, body: { reason, reason_text: text.trim() || null } }),
      );
      qc.setQueryData(ak.accessCard(deployment.id), c);
      await qc.invalidateQueries({ queryKey: ak.deployment(deployment.id) });
      await qc.invalidateQueries({ queryKey: ["credential"] });
      toast.success(t("cardReissued"));
      setReissue(false);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3" data-testid="access-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium">
          <CreditCard aria-hidden className="size-4" />
          {t("accessCard")}
        </p>
        {deployment.access_card.token_status ? <StatusBadge status={deployment.access_card.token_status} label={te(`qrTokenStatus.${deployment.access_card.token_status}`)} /> : null}
      </div>
      {card.isError ? (
        <ErrorState error={card.error} />
      ) : card.data ? (
        <div className="flex flex-wrap items-center gap-4">
          <QrImage payload={card.data.qr_payload} size={132} label={t("cardQr", { no: card.data.printed_ref })} />
          <div className="flex flex-col gap-1 text-sm">
            <span>
              {t("printedRef")}: <Code className="font-semibold" data-testid="printed-ref">{card.data.printed_ref}</Code>
            </span>
            <span className="text-muted-foreground">
              {t("issuedOn", { date: date(card.data.issued_on) })} · {t("reissues", { count: card.data.reissue_count })}
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild>
                <Link href={`/deployments/${deployment.id}/card`} data-testid="print-card">
                  <Printer aria-hidden />
                  {t("printCard")}
                </Link>
              </Button>
              {canWrite(me, "worker.edit", deployment.project_id) && mobilised ? (
                <Button size="sm" variant="outline" onClick={() => setReissue(true)} data-testid="reissue-card">
                  <RefreshCw aria-hidden />
                  {t("reissueCard")}
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      ) : mobilised ? (
        <LoadingState rows={1} />
      ) : null}
      {mobilised || deployment.access_card.token_status ? <CredentialPanel kind="access_card" id={deployment.id} projectId={deployment.project_id} /> : null}
      <Dialog open={reissue} onOpenChange={setReissue}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("reissueCard")}</DialogTitle>
            <DialogDescription>{t("reissueHelp")}</DialogDescription>
          </DialogHeader>
          <FormField id="reissue-reason" label={tc("reason")} required>
            <Select value={reason} onChange={(e) => setReason(e.target.value as Schemas["AccessCardReissueReason"])}>
              {(["lost", "damaged", "other"] as const).map((r) => (
                <option key={r} value={r}>
                  {te(`reissueReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="reissue-text" label={tc("comment")}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} />
          </FormField>
          <MutationError error={error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setReissue(false)}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => void doReissue()} data-testid="reissue-confirm">
              {t("reissueCard")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DemobiliseDialog({ deployment, onClose }: { deployment: Schemas["DeploymentRead"]; onClose: () => void }) {
  const t = useTranslations("workers");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [on, setOn] = useState(todayInZone());
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  async function go() {
    setError(null);
    try {
      const d = await unwrap(
        api.POST("/api/v1/deployments/{deployment_id}/transitions", { params: { path: { deployment_id: deployment.id } }, body: { to_status: "demobilised", demobilised_on: on, reason: reason.trim() || null } }),
      );
      qc.setQueryData(ak.deployment(d.id), d);
      await qc.invalidateQueries({ queryKey: ["worker"] });
      await qc.invalidateQueries({ queryKey: ["workers"] });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("demobilise")}</DialogTitle>
          <DialogDescription>{t("demobiliseHelp")}</DialogDescription>
        </DialogHeader>
        <FormField id="demob-on" label={t("fields.demobilised_on")} required>
          <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
        </FormField>
        <FormField id="demob-reason" label={t("reasonOptional")}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant="destructive" disabled={!on} onClick={() => void go()} data-testid="demob-confirm">
            {t("demobilise")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditDeploymentDialog({ deployment, onClose }: { deployment: Schemas["DeploymentRead"]; onClose: () => void }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const opts = useProjectOptions(deployment.project_id);
  const eng = opts.engagements.find((e) => e.value === deployment.engagement?.id);
  const [trade, setTrade] = useState<Schemas["Trade"]>(deployment.trade);
  const [emp, setEmp] = useState(deployment.employee_no ?? "");
  const [sites, setSites] = useState(deployment.sites.map((s) => s.id));
  const [mob, setMob] = useState(deployment.mobilised_on);
  const [demob, setDemob] = useState(deployment.planned_demob_on ?? "");
  const [error, setError] = useState<unknown>(null);
  async function go() {
    setError(null);
    try {
      const d = await unwrap(
        api.PATCH("/api/v1/deployments/{deployment_id}", {
          params: { path: { deployment_id: deployment.id } },
          body: { trade, employee_no: emp.trim() || null, site_ids: sites, mobilised_on: mob, planned_demob_on: demob || null },
        }),
      );
      qc.setQueryData(ak.deployment(d.id), d);
      await qc.invalidateQueries({ queryKey: ["workers"] });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("editDeployment")}</DialogTitle>
        </DialogHeader>
        <FormField id="ed-trade" label={t("fields.trade")} required>
          <Select value={trade} onChange={(e) => setTrade(e.target.value as Schemas["Trade"])}>
            {TRADES.map((x) => (
              <option key={x} value={x}>
                {te(`trade.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ed-emp" label={t("fields.employee_no")}>
          <Input value={emp} onChange={(e) => setEmp(e.target.value)} maxLength={20} className="ltr" />
        </FormField>
        <MultiSelect id="ed-sites" label={t("fields.sites")} options={opts.sites.filter((s) => !eng || eng.siteIds.includes(s.value))} value={sites} onChange={setSites} className="lg:w-full" />
        <FormField id="ed-mob" label={t("fields.mobilised_on")} required>
          <Input type="date" value={mob} onChange={(e) => setMob(e.target.value)} />
        </FormField>
        <FormField id="ed-demob" label={t("fields.planned_demob_on")}>
          <Input type="date" value={demob} onChange={(e) => setDemob(e.target.value)} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button disabled={sites.length === 0 || !mob} onClick={() => void go()} data-testid="save-deployment">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewDeployment({ workerId, project }: { workerId: string; project: Schemas["ProjectRead"] | null }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const opts = useProjectOptions(project?.id ?? "");
  const [open, setOpen] = useState(false);
  const [engId, setEngId] = useState("");
  const [trade, setTrade] = useState<Schemas["Trade"] | "">("");
  const [sites, setSites] = useState<string[]>([]);
  const [mob, setMob] = useState(todayInZone());
  const [error, setError] = useState<unknown>(null);
  if (!project) return null;
  const eng = opts.engagements.find((e) => e.value === engId);
  async function go() {
    if (!project) return;
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/projects/{project_id}/deployments", {
          params: { path: { project_id: project.id } },
          body: { worker_id: workerId, engagement_id: engId || null, trade: trade as Schemas["Trade"], site_ids: sites, mobilised_on: mob },
        }),
      );
      await qc.invalidateQueries({ queryKey: ak.worker(workerId) });
      await qc.invalidateQueries({ queryKey: ["workers"] });
      toast.success(tc("created"));
      setOpen(false);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <>
      <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)} data-testid="new-deployment">
        <Plus aria-hidden />
        {t("newDeployment", { code: project.code })}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("newDeployment", { code: project.code })}</DialogTitle>
          </DialogHeader>
          <FormField id="nd-eng" label={tc("contractor")}>
            <Select value={engId} onChange={(e) => setEngId(e.target.value)}>
              <option value="">{t("noEngagement")}</option>
              {opts.engagements
                .filter((e) => e.status === "approved")
                .map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField id="nd-trade" label={t("fields.trade")} required>
            <Select value={trade} onChange={(e) => setTrade(e.target.value as Schemas["Trade"] | "")}>
              <option value="">{tc("select")}</option>
              {TRADES.map((x) => (
                <option key={x} value={x}>
                  {te(`trade.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <MultiSelect id="nd-sites" label={t("fields.sites")} options={opts.sites.filter((s) => !eng || eng.siteIds.includes(s.value))} value={sites} onChange={setSites} className="lg:w-full" />
          <FormField id="nd-mob" label={t("fields.mobilised_on")} required>
            <Input type="date" value={mob} onChange={(e) => setMob(e.target.value)} />
          </FormField>
          <MutationError error={error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button disabled={!trade || sites.length === 0 || !mob} onClick={() => void go()}>
              {tc("create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** "Can this worker enter zone X (now or at a time)?" — ZP-3 items from the API. */
function EligibilityChecker({ workerId, projectId }: { workerId: string; projectId: string }) {
  const t = useTranslations("workers");
  const tc = useTranslations("common");
  const opts = useProjectOptions(projectId);
  const [zone, setZone] = useState("");
  const [at, setAt] = useState("");
  const q = useEligibility(workerId, zone, at ? zonedInputToUtc(at) : null);
  return (
    <Card data-testid="eligibility-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck aria-hidden className="size-4" />
          {t("canEnter")}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="elig-zone">{tc("zone")}</Label>
            <Select id="elig-zone" value={zone} onChange={(e) => setZone(e.target.value)} data-testid="elig-zone">
              <option value="">{tc("select")}</option>
              {opts.zones.map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="elig-at">{t("atTime")}</Label>
            <Input id="elig-at" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </div>
        </div>
        {!zone ? null : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data ? (
          <LoadingState rows={2} />
        ) : (
          <div className="flex flex-col gap-2">
            <Alert tone={q.data.eligible ? (q.data.items.some((i) => i.status === "warn" || i.status === "expiring") ? "warning" : "success") : "danger"} data-testid="eligibility-verdict" data-eligible={q.data.eligible}>
              <span className="font-medium">{q.data.eligible ? t("eligible") : t("notEligible")}</span>
              {q.data.escort_required ? <span className="ms-2">· {t("escortRequired")}</span> : null}
            </Alert>
            <EligibilityItems items={q.data.items} projectId={projectId} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function WorkerInductions({ workerId, deploymentId, projectId }: { workerId: string; deploymentId: string; projectId: string }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const me = useMeData();
  const { date, dateTime } = useFormatters(projectId);
  const q = useInductions(projectId, { worker_id: workerId, page_size: 50 });
  const items = q.data?.items ?? [];
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("inductionRecords")}</CardTitle>
        {canWrite(me, "induction.record", projectId) ? (
          <Button size="sm" asChild>
            <Link href={`/inductions/new?deployment_id=${deploymentId}`} data-testid="record-induction">
              <Plus aria-hidden />
              {t("recordInduction")}
            </Link>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {q.isError ? (
          <ErrorState error={q.error} />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">—</p>
        ) : (
          <ul className="flex flex-col divide-y" data-testid="worker-inductions">
            {items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <Link href={`/inductions/${i.id}`} className="text-primary hover:underline">
                  <Code>{i.course_code}</Code> · <Code className="text-muted-foreground">{i.induction_no}</Code>
                </Link>
                <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {dateTime(i.delivered_at)}
                  {i.valid_until ? ` → ${date(i.valid_until)}` : ""}
                  <StatusBadge status={i.status} label={te(`inductionStatus.${i.status}`)} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** P2-11: per-worker data report (capability 79, purpose required, audited). Downloaded as JSON. */
function DataReport({ worker }: { worker: Schemas["WorkerRead"] }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [purpose, setPurpose] = useState<Schemas["ExportPurpose"] | "">("");
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  async function go() {
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/workers/{worker_id}/data-report", { params: { path: { worker_id: worker.id } }, body: { purpose: purpose as Schemas["ExportPurpose"], purpose_text: text.trim() || null } }));
      const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `${worker.worker_no}-data-report.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
      setOpen(false);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("dataReport")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <p className="text-muted-foreground">{t("dataReportHint")}</p>
        <Button size="sm" variant="outline" className="self-start" onClick={() => setOpen(true)}>
          <FileDown aria-hidden />
          {t("dataReport")}
        </Button>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("dataReport")}</DialogTitle>
          </DialogHeader>
          <FormField id="dr-purpose" label={t("purpose")} required>
            <Select value={purpose} onChange={(e) => setPurpose(e.target.value as Schemas["ExportPurpose"] | "")}>
              <option value="">{tc("select")}</option>
              {EXPORT_PURPOSES_ACCESS.map((p) => (
                <option key={p} value={p}>
                  {te(`exportPurpose.${p}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="dr-text" label={tc("comment")} required={purpose === "other"}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} />
          </FormField>
          <MutationError error={error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button disabled={!purpose || (purpose === "other" && !text.trim())} onClick={() => void go()}>
              {t("dataReport")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** Printable access card: photo, names, worker_no, employer, QR and printed reference (no ID number). */
export function AccessCardPrint({ deploymentId }: { deploymentId: string }) {
  const t = useTranslations("workers");
  const tc = useTranslations("common");
  const q = useAccessCard(deploymentId);
  const { prefs } = useFormatters();
  // The card is 54 mm tall: one calendar line (Gregorian, project digits) instead of the two-calendar date.
  const date = (v: string) => formatDate(v, { ...prefs, showHijri: false });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <div className="flex flex-col items-start gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="print-now">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/deployments/${deploymentId}`}>{tc("back")}</Link>
        </Button>
      </div>
      {/* ID-1 card size (85.6 × 54 mm), black on white: prints the same from a light or dark screen. */}
      <div
        dir="ltr"
        className="paper flex h-[54mm] w-[86mm] flex-col gap-1.5 overflow-hidden rounded-[3mm] border border-black bg-white px-[3mm] py-[2.5mm] text-black shadow-sm print:shadow-none"
        data-testid="card-print"
      >
        <AccessPrintHeader title="cardTitle" variant="card" />
        <div className="flex min-h-0 flex-1 gap-2">
          <WorkerPhoto attachmentId={c.photo_attachment_id} name={c.full_name_en} size={76} />
          <div className="flex min-w-0 flex-1 flex-col">
            <p lang="en" dir="ltr" className="truncate text-[9pt] leading-tight font-bold">
              {c.full_name_en}
            </p>
            <p lang="ar" dir="rtl" className="truncate text-end text-[9.5pt] leading-tight font-bold">
              {c.full_name_ar}
            </p>
            <p className="mt-1 text-[8pt] leading-tight">
              <Code className="font-mono font-semibold">{c.worker_no}</Code>
            </p>
            {c.employer_short_code ? (
              <p className="text-[7.5pt] leading-tight">
                <Code>{c.employer_short_code}</Code>
              </p>
            ) : null}
            <p className="mt-auto text-[6.5pt] leading-tight">
              <BiLabel k="issued" className="text-[6pt]" /> <bdi className="whitespace-nowrap">{date(c.issued_on)}</bdi>
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-center">
            <QrImage payload={c.qr_payload} size={84} label={t("cardQr", { no: c.printed_ref })} />
          </div>
        </div>
        <p className="ltr border-t border-black pt-0.5 text-center font-mono text-[9pt] font-bold tracking-wide" data-testid="card-printed-ref">
          {c.printed_ref}
        </p>
      </div>
    </div>
  );
}
