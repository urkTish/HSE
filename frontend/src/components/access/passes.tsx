"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Pencil, Plus, ShieldQuestion } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { BACKGROUND_STATUSES, CUSTODY_STATUSES, PASS_APPLICATION_STATUSES, PASS_APPLICATION_TYPES, VALIDITY_STATUSES } from "@/lib/access-enums";
import { ak, useAirportPass, useAirportPasses, usePassApplication, usePassApplications, usePassAreas, usePassCategories } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { todayInZone, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { AirportOnly, Code, DaysLeft, DeploymentPicker, EligibilityItems, StepDialog, SubNav, ValidityBadge, ValidityLine, personName } from "./common";
import { CredentialPanel } from "./credential-actions";
import { StackedDate } from "@/components/medical/common";

const PAGE_SIZE = 50;
type App = Schemas["PassApplicationRead"];
type AppStatus = Schemas["PassApplicationStatus"];

function PassSubNav() {
  const t = useTranslations("passes");
  const tn = useTranslations("nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/pass-applications", label: t("applications"), testId: "sub-applications" },
        { href: "/airport-passes", label: t("passes"), testId: "sub-passes" },
        { href: "/pass-setup", label: tn("passSetup"), show: can(me, "access_settings.edit"), testId: "sub-pass-setup" },
      ]}
    />
  );
}

/* ───────────────────────────── Applications list ───────────────────────────── */

export function PassApplicationListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<ApplicationList project={p} />}</AirportOnly>}</ProjectGate>;
}

function ApplicationList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as AppStatus[];
  const engs = s.getAll("engagement_id");
  const q: Parameters<typeof usePassApplications>[1] = {
    status: status.length ? status : null,
    application_type: (s.get("application_type") as Schemas["PassApplicationType"] | null) || null,
    engagement_id: engs.length ? engs : null,
    stale: s.getBool("stale") ?? null,
    worker_id: s.get("worker_id") || null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = usePassApplications(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("applications")}
        description={t("applicationsHint")}
        actions={
          canWrite(me, "pass_application.create", project.id) ? (
            <Button asChild>
              <Link href="/pass-applications/new" data-testid="new-application">
                <Plus aria-hidden />
                {t("newApplication")}
              </Link>
            </Button>
          ) : null
        }
      />
      <PassSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="pass_applications" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="pa-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="pa-status" label={tc("status")} options={PASS_APPLICATION_STATUSES.map((x) => ({ value: x, label: te(`passAppStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter
          id="pa-type"
          label={t("fields.application_type")}
          value={(q.application_type ?? "") as Schemas["PassApplicationType"] | ""}
          onChange={(v) => s.set({ application_type: v })}
          options={PASS_APPLICATION_TYPES.map((x) => ({ value: x, label: te(`passAppType.${x}`) }))}
        />
        <MultiSelect id="pa-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="pa-stale" label={t("stale")} value={s.get("stale") === "true" ? "true" : ""} onChange={(v) => s.set({ stale: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="applications-table">
            <THead>
              <TR>
                <TH>{t("fields.application_no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("fields.application_type")}</TH>
                <TH>{t("fields.pass_category")}</TH>
                <TH>{t("fields.requested_area_codes")}</TH>
                <TH>{t("fields.requested_valid_until")}</TH>
                <TH>{t("daysLodged")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="application-row">
                  <TD label={t("fields.application_no")}>
                    <Link href={`/pass-applications/${a.id}`} className="ltr font-medium text-primary hover:underline">
                      {a.application_no}
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <Code>{a.worker.worker_no}</Code> {personName(a.worker, locale)}
                    {a.sponsor_engagement ? <span className="block text-xs text-muted-foreground">{a.sponsor_engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("fields.application_type")}>{te(`passAppType.${a.application_type}`)}</TD>
                  <TD label={t("fields.pass_category")}>
                    <Code>{a.pass_category}</Code>
                  </TD>
                  <TD label={t("fields.requested_area_codes")}>
                    <span className="ltr">{a.requested_area_codes.join(", ")}</span>
                  </TD>
                  <TD label={t("fields.requested_valid_until")}><StackedDate v={a.requested_valid_until} /></TD>
                  <TD label={t("daysLodged")}>
                    {a.days_lodged != null ? a.days_lodged : "—"}
                    {a.stale ? (
                      <span className="ms-1">
                        <StatusBadge status="warn" label={t("stale")} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={a.status} label={locale === "ar" ? a.status_label_ar : a.status_label_en} />
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
    </div>
  );
}

/* ───────────────────────────── Application form ───────────────────────────── */

export function PassApplicationCreatePage() {
  const t = useTranslations("passes");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("applications"), href: "/pass-applications" }, { label: t("newApplication") }]} />
      <PageHeader title={t("newApplication")} description={t("newHint")} />
      <ProjectGate>{(p) => <AirportOnly project={p}>{<ApplicationForm project={p} />}</AirportOnly>}</ProjectGate>
    </div>
  );
}

export function PassApplicationEditPage({ id }: { id: string }) {
  const t = useTranslations("passes");
  const q = usePassApplication(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("applications"), href: "/pass-applications" }, { label: a.application_no, href: `/pass-applications/${a.id}` }, { label: t("editApplication") }]} />
      <PageHeader title={t("editApplication")} />
      <ProjectById id={a.project_id}>{(p) => <ApplicationForm project={p} app={a} />}</ProjectById>
    </div>
  );
}

function ApplicationForm({ project, app }: { project: Schemas["ProjectRead"]; app?: App }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const locale = useLocale();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const cats = usePassCategories(project.id);
  const areas = usePassAreas(project.id);
  const [dep, setDep] = useState<Schemas["DeploymentRead"] | null>(null);
  const [type, setType] = useState<Schemas["PassApplicationType"]>(app?.application_type ?? "new");
  const [letter, setLetter] = useState(app?.sponsor_letter_ref ?? "");
  const [cat, setCat] = useState(app?.pass_category ?? "");
  const [codes, setCodes] = useState<string[]>(app?.requested_area_codes ?? []);
  const [until, setUntil] = useState(app?.requested_valid_until ?? "");
  const [just, setJust] = useState(app?.justification ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const category = (cats.data?.items ?? []).find((c) => c.code === cat);

  async function save() {
    const e: Record<string, string> = {};
    if (!app && !dep) e.dep = tv("required");
    if (!letter.trim()) e.letter = tv("required");
    if (!cat) e.cat = tv("required");
    if (codes.length === 0) e.codes = tv("required");
    if (!until) e.until = tv("required");
    if (!just.trim()) e.just = tv("required");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const saved = app
        ? await unwrap(
            api.PATCH("/api/v1/pass-applications/{application_id}", {
              params: { path: { application_id: app.id } },
              body: { sponsor_letter_ref: letter.trim(), pass_category: cat, requested_area_codes: codes, requested_valid_until: until, justification: just.trim() },
            }),
          )
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/pass-applications", {
              params: { path: { project_id: project.id } },
              body: { application_type: type, deployment_id: dep!.id, sponsor_letter_ref: letter.trim(), pass_category: cat, requested_area_codes: codes, requested_valid_until: until, justification: just.trim() },
            }),
          );
      qc.setQueryData(ak.application(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["pass-applications"] });
      warn(saved.warnings);
      toast.success(tc("saved"));
      router.push(`/pass-applications/${saved.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      data-testid="application-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("applicant")}>
        {app ? (
          <p className="text-sm sm:col-span-2">
            <Code>{app.worker.worker_no}</Code> {personName(app.worker, locale)}
          </p>
        ) : (
          <div className="sm:col-span-2">
            <DeploymentPicker id="pa-worker" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("worker")} required error={errors.dep} />
          </div>
        )}
        <FormField id="pa-type-sel" label={t("fields.application_type")} required>
          <Select value={type} disabled={Boolean(app)} onChange={(e) => setType(e.target.value as Schemas["PassApplicationType"])}>
            {PASS_APPLICATION_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`passAppType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pa-letter" label={t("fields.sponsor_letter_ref")} required error={errors.letter}>
          <Input className="ltr" maxLength={40} value={letter} onChange={(e) => setLetter(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("request")}>
        <FormField id="pa-cat" label={t("fields.pass_category")} required error={errors.cat}>
          <Select value={cat} onChange={(e) => setCat(e.target.value)} data-testid="pa-cat">
            <option value="">{tc("select")}</option>
            {(cats.data?.items ?? [])
              .filter((c) => c.active)
              .map((c) => (
                <option key={c.id} value={c.code}>
                  {c.code} — {locale === "ar" ? c.name_ar : c.name_en}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="pa-until" label={t("fields.requested_valid_until")} required error={errors.until} hint={app?.max_valid_until ? t("maxUntil", { date: app.max_valid_until }) : category ? t("maxDays", { days: category.max_validity_days }) : undefined}>
          <Input type="date" min={todayInZone()} value={until} onChange={(e) => setUntil(e.target.value)} />
        </FormField>
        <div className="sm:col-span-2">
          <MultiSelect
            id="pa-areas"
            label={t("fields.requested_area_codes")}
            options={(areas.data?.items ?? []).filter((a) => a.active).map((a) => ({ value: a.code, label: `${a.code} — ${locale === "ar" ? a.name_ar : a.name_en}` }))}
            value={codes}
            onChange={setCodes}
            className="lg:w-full"
          />
          {errors.codes ? (
            <p role="alert" className="mt-1 text-xs font-medium text-destructive">
              {errors.codes}
            </p>
          ) : null}
        </div>
        {category?.escorted ? (
          <Alert tone="info" className="sm:col-span-2">
            {t("escortedCategory")}
          </Alert>
        ) : null}
        <FormField id="pa-just" label={t("fields.justification")} required error={errors.just} hint={t("justificationHint")} className="sm:col-span-2">
          <Textarea rows={3} maxLength={500} value={just} onChange={(e) => setJust(e.target.value)} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-application">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── Application detail ───────────────────────────── */

type Step = "submit" | "return" | "endorse" | "lodge" | "approve" | "refuse" | "withdraw" | "cancel" | "issue" | "bg";

function isEligibilityItem(x: unknown): x is Schemas["EligibilityItem"] {
  return typeof x === "object" && x !== null && "kind" in x && "status" in x;
}

export function PassApplicationDetail({ id }: { id: string }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const name = useLocalizedName();
  const q = usePassApplication(id);
  const qc = useQueryClient();
  const [step, setStep] = useState<Step | null>(null);
  const { date, dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  const pid = a.project_id;
  const create = canWrite(me, "pass_application.create", pid);
  const endorse = canWrite(me, "pass_application.endorse", pid);
  const process = canWrite(me, "pass_application.process", pid);
  const bgView = can(me, "background_check.view", pid);
  const s = a.status;
  const open = ["draft", "submitted", "endorsed", "lodged"].includes(s);
  const steps: { k: Step; show: boolean; destructive?: boolean; primary?: boolean }[] = [
    { k: "submit", show: s === "draft" && create, primary: true },
    { k: "return", show: s === "submitted" && endorse },
    { k: "endorse", show: s === "submitted" && endorse, primary: true },
    { k: "lodge", show: s === "endorsed" && process, primary: true },
    { k: "bg", show: (s === "endorsed" || s === "lodged" || s === "approved") && process && bgView },
    { k: "approve", show: s === "lodged" && process, primary: true },
    { k: "refuse", show: s === "lodged" && process, destructive: true },
    { k: "issue", show: s === "approved" && process, primary: true },
    { k: "cancel", show: s === "approved" && process, destructive: true },
    { k: "withdraw", show: open && (create || endorse), destructive: true },
  ];
  const snapshot = Array.isArray(a.prerequisite_snapshot) ? a.prerequisite_snapshot.filter(isEligibilityItem) : [];
  async function refresh(u: App) {
    qc.setQueryData(ak.application(a.id), u);
    await qc.invalidateQueries({ queryKey: ["pass-applications"] });
  }
  async function transition(body: Schemas["PassApplicationTransitionRequest"]) {
    const u = await unwrap(api.POST("/api/v1/pass-applications/{application_id}/transitions", { params: { path: { application_id: a.id } }, body }));
    await refresh(u);
    toast.success(t("movedTo", { status: te(`passAppStatus.${body.to_status}`) }));
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("applications"), href: "/pass-applications" }, { label: a.application_no }]} />
        <PageHeader
          title={a.application_no}
          description={`${a.worker.worker_no} · ${personName(a.worker, locale)} · ${te(`passAppType.${a.application_type}`)}`}
          actions={
            <>
              <span data-testid="application-status" data-status={s}>
                <StatusBadge status={s} label={locale === "ar" ? a.status_label_ar : a.status_label_en} />
              </span>
              {s === "draft" && create ? (
                <Button variant="outline" asChild>
                  <Link href={`/pass-applications/${a.id}/edit`} data-testid="edit-application">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
              {a.issued_pass_id ? (
                <Button variant="outline" asChild>
                  <Link href={`/airport-passes/${a.issued_pass_id}`} data-testid="open-pass">
                    <BadgeCheck aria-hidden />
                    {t("openPass")}
                  </Link>
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {steps.some((x) => x.show) ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("actions")} data-testid="application-actions">
          {steps
            .filter((x) => x.show)
            .map((x) => (
              <Button key={x.k} variant={x.destructive ? "destructive" : x.primary ? "default" : "outline"} onClick={() => setStep(x.k)} data-testid={`step-${x.k}`}>
                {t(`step.${x.k}`)}
              </Button>
            ))}
        </div>
      ) : null}
      {a.stale ? <Alert tone="warning">{t("staleHint", { days: a.days_lodged ?? 0 })}</Alert> : null}
      <ApiWarnings warnings={a.warnings} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("worker")}>
                <Link href={`/workers/${a.worker.id}`} className="text-primary hover:underline">
                  <Code>{a.worker.worker_no}</Code> {personName(a.worker, locale)}
                </Link>
              </FieldItem>
              <FieldItem label={t("fields.sponsor_engagement")}>{a.sponsor_engagement?.short_code ?? t("clientStaff")}</FieldItem>
              <FieldItem label={t("fields.sponsor_letter_ref")} ltr>
                {a.sponsor_letter_ref}
              </FieldItem>
              <FieldItem label={t("fields.client_sponsor")}>{a.client_sponsor ? name(a.client_sponsor.full_name_en, a.client_sponsor.full_name_ar) : "—"}</FieldItem>
              <FieldItem label={t("fields.pass_category")}>
                <Code>{a.pass_category}</Code>
              </FieldItem>
              <FieldItem label={t("fields.requested_area_codes")} ltr>
                {a.requested_area_codes.join(", ")}
              </FieldItem>
              <FieldItem label={t("fields.requested_valid_until")}>{date(a.requested_valid_until)}</FieldItem>
              <FieldItem label={t("fields.max_valid_until")}>{date(a.max_valid_until)}</FieldItem>
              <FieldItem label={t("fields.justification")} wide>
                {a.justification}
              </FieldItem>
              <FieldItem label={t("fields.submitted_at")}>{a.submitted_at ? `${dateTime(a.submitted_at)} · ${a.submitted_by ? name(a.submitted_by.full_name_en, a.submitted_by.full_name_ar) : ""}` : "—"}</FieldItem>
              <FieldItem label={t("fields.lodged_at")}>{dateTime(a.lodged_at)}</FieldItem>
              <FieldItem label={t("fields.authority_ref")} ltr>
                {a.authority_ref ?? "—"}
              </FieldItem>
              <FieldItem label={t("daysLodged")}>{a.days_lodged ?? "—"}</FieldItem>
              <FieldItem label={t("fields.has_id_copy")}>{a.has_id_copy ? tc("yes") : tc("no")}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          {bgView && "background_check" in a ? (
            <Card data-testid="background-check">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldQuestion aria-hidden className="size-4" />
                  {t("backgroundCheck")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-xs text-muted-foreground">{t("sensitive")}</p>
                {a.background_check ? (
                  <FieldList>
                    <FieldItem label={tc("status")}>
                      <StatusBadge status={a.background_check.status} label={te(`bgStatus.${a.background_check.status}`)} />
                    </FieldItem>
                    <FieldItem label={t("fields.check_date")}>{date(a.background_check.check_date)}</FieldItem>
                    <FieldItem label={t("fields.recheck_due")}>{date(a.background_check.recheck_due)}</FieldItem>
                  </FieldList>
                ) : (
                  <p className="text-sm">—</p>
                )}
                {a.outcome_note ? <p className="mt-2 text-sm">{a.outcome_note}</p> : null}
              </CardContent>
            </Card>
          ) : null}
          {(s === "draft" || a.has_id_copy) && (create || can(me, "worker.unmask_id", pid)) ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("idCopy")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Attachments ownerType="pass_application_id_copy" ownerId={a.id} canUpload={s === "draft" && create} canDelete={s === "draft" && create} max={1} hint={t("idCopyHint")} onChange={() => void q.refetch()} />
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
      {snapshot.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("prerequisites")}</CardTitle>
          </CardHeader>
          <CardContent>
            <EligibilityItems items={snapshot} projectId={pid} />
          </CardContent>
        </Card>
      ) : null}
      <HistoryPanel entityType="pass_application" entityId={a.id} />
      {step === "submit" ? <StepDialog title={t("step.submit")} description={t("help.submit")} confirmLabel={t("step.submit")} onConfirm={() => transition({ to_status: "submitted" })} onClose={() => setStep(null)} /> : null}
      {step === "return" ? <ReasonStep title={t("step.return")} help={t("help.return")} onClose={() => setStep(null)} onConfirm={(r) => transition({ to_status: "draft", reason: r })} /> : null}
      {step === "withdraw" ? <ReasonStep title={t("step.withdraw")} help={t("help.withdraw")} destructive onClose={() => setStep(null)} onConfirm={(r) => transition({ to_status: "withdrawn", reason: r })} /> : null}
      {step === "cancel" ? <ReasonStep title={t("step.cancel")} help={t("help.cancel")} destructive onClose={() => setStep(null)} onConfirm={(r) => transition({ to_status: "cancelled", reason: r })} /> : null}
      {step === "endorse" ? <EndorseStep projectId={pid} meId={me.id} onClose={() => setStep(null)} onConfirm={(uid) => transition({ to_status: "endorsed", client_sponsor_user_id: uid })} /> : null}
      {step === "lodge" ? <LodgeStep onClose={() => setStep(null)} onConfirm={(at, ref) => transition({ to_status: "lodged", lodged_at: at, authority_ref: ref })} /> : null}
      {step === "approve" ? <OutcomeStep to="approved" onClose={() => setStep(null)} onConfirm={(note) => transition({ to_status: "approved", outcome_note: note })} /> : null}
      {step === "refuse" ? <OutcomeStep to="refused" onClose={() => setStep(null)} onConfirm={(note) => transition({ to_status: "refused", outcome_note: note })} /> : null}
      {step === "bg" ? <BackgroundStep app={a} onClose={() => setStep(null)} onSaved={refresh} /> : null}
      {step === "issue" ? <IssueStep app={a} onClose={() => setStep(null)} onSaved={() => q.refetch()} /> : null}
    </div>
  );
}

function ReasonStep({ title, help, destructive, onConfirm, onClose }: { title: string; help: string; destructive?: boolean; onConfirm: (reason: string) => Promise<unknown>; onClose: () => void }) {
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  return (
    <StepDialog title={title} description={help} destructive={destructive} confirmLabel={title} disabled={reason.trim().length < 3} onConfirm={() => onConfirm(reason.trim())} onClose={onClose}>
      <FormField id="step-reason" label={tc("reason")} required hint={tc("pdplHint")}>
        <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function EndorseStep({ projectId, meId, onConfirm, onClose }: { projectId: string; meId: string; onConfirm: (userId: string) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("passes");
  const [uid, setUid] = useState(meId);
  return (
    <StepDialog title={t("step.endorse")} description={t("help.endorse")} confirmLabel={t("step.endorse")} disabled={!uid} onConfirm={() => onConfirm(uid)} onClose={onClose}>
      <FormField id="endorse-sponsor" label={t("fields.client_sponsor")} required>
        <UserSelect projectId={projectId} value={uid} onChange={(e) => setUid(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function LodgeStep({ onConfirm, onClose }: { onConfirm: (at: string, ref: string) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("passes");
  const [at, setAt] = useState(() => utcToZonedInput(new Date().toISOString()));
  const [ref, setRef] = useState("");
  return (
    <StepDialog title={t("step.lodge")} description={t("help.lodge")} confirmLabel={t("step.lodge")} disabled={!at || !ref.trim()} onConfirm={() => onConfirm(zonedInputToUtc(at), ref.trim())} onClose={onClose}>
      <FormField id="lodge-at" label={t("fields.lodged_at")} required>
        <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
      </FormField>
      <FormField id="lodge-ref" label={t("fields.authority_ref")} required>
        <Input className="ltr" maxLength={40} value={ref} onChange={(e) => setRef(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function OutcomeStep({ to, onConfirm, onClose }: { to: "approved" | "refused"; onConfirm: (note: string | null) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("passes");
  const k = to === "approved" ? "approve" : "refuse";
  const [note, setNote] = useState("");
  return (
    <StepDialog title={t(`step.${k}`)} description={t(`help.${k}`)} destructive={to === "refused"} confirmLabel={t(`step.${k}`)} onConfirm={() => onConfirm(note.trim() || null)} onClose={onClose}>
      <FormField id="outcome-note" label={t("fields.outcome_note")} hint={t("outcomeNoteHint")}>
        <Textarea rows={2} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function BackgroundStep({ app, onSaved, onClose }: { app: App; onSaved: (a: App) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const [status, setStatus] = useState<Schemas["BackgroundCheckStatus"]>(app.background_check?.status ?? "submitted");
  const [on, setOn] = useState(app.background_check?.check_date ?? "");
  return (
    <StepDialog
      title={t("step.bg")}
      description={t("help.bg")}
      confirmLabel={t("step.bg")}
      disabled={status === "cleared" && !on}
      onConfirm={async () => {
        const u = await unwrap(api.PUT("/api/v1/pass-applications/{application_id}/background-check", { params: { path: { application_id: app.id } }, body: { status, check_date: on || null } }));
        await onSaved(u);
        toast.success(t("bgSaved"));
      }}
      onClose={onClose}
    >
      <FormField id="bg-status" label={t("backgroundCheck")} required>
        <Select value={status} onChange={(e) => setStatus(e.target.value as Schemas["BackgroundCheckStatus"])}>
          {BACKGROUND_STATUSES.map((x) => (
            <option key={x} value={x}>
              {te(`bgStatus.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="bg-date" label={t("fields.check_date")} required={status === "cleared"}>
        <Input type="date" max={todayInZone()} value={on} onChange={(e) => setOn(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function IssueStep({ app, onSaved, onClose }: { app: App; onSaved: () => void; onClose: () => void }) {
  const t = useTranslations("passes");
  const router = useRouter();
  const qc = useQueryClient();
  const [no, setNo] = useState("");
  const [codes, setCodes] = useState<string[]>(app.requested_area_codes);
  const [issued, setIssued] = useState(todayInZone());
  const [expiry, setExpiry] = useState(app.requested_valid_until);
  return (
    <StepDialog
      title={t("step.issue")}
      description={t("help.issue")}
      confirmLabel={t("step.issue")}
      disabled={!no.trim() || codes.length === 0 || !issued || !expiry}
      testId="issue-confirm"
      onConfirm={async () => {
        const p = await unwrap(
          api.POST("/api/v1/pass-applications/{application_id}/issue", { params: { path: { application_id: app.id } }, body: { pass_no: no.trim(), area_codes: codes, issued_on: issued, card_expiry_date: expiry } }),
        );
        qc.setQueryData(ak.pass(p.id), p);
        for (const k of ["pass-applications", "pass-application", "airport-passes", "worker", "workers", "deployment"]) await qc.invalidateQueries({ queryKey: [k] });
        toast.success(t("issued", { no: p.pass_no }));
        onSaved();
        router.push(`/airport-passes/${p.id}`);
      }}
      onClose={onClose}
    >
      <FormField id="issue-no" label={t("fields.pass_no")} required hint={t("passNoHint")}>
        <Input className="ltr" maxLength={30} value={no} onChange={(e) => setNo(e.target.value)} />
      </FormField>
      <MultiSelect id="issue-areas" label={t("fields.area_codes")} options={app.requested_area_codes.map((c) => ({ value: c, label: c }))} value={codes} onChange={setCodes} className="lg:w-full" />
      <FormField id="issue-on" label={t("fields.issued_on")} required>
        <Input type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
      </FormField>
      <FormField id="issue-expiry" label={t("fields.card_expiry_date")} required hint={t("expiryHint")}>
        <Input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────────────────────── Issued passes ───────────────────────────── */

export function AirportPassListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<PassList project={p} />}</AirportOnly>}</ProjectGate>;
}

function PassList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const cats = usePassCategories(project.id);
  const areas = usePassAreas(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const validity = s.getAll("validity_status") as Schemas["ValidityStatus"][];
  const custody = s.getAll("custody_status") as Schemas["CustodyStatus"][];
  const engs = s.getAll("engagement_id");
  const q: Parameters<typeof useAirportPasses>[1] = {
    validity_status: validity.length ? validity : null,
    custody_status: custody.length ? custody : null,
    return_overdue: s.getBool("return_overdue") ?? null,
    pass_category: s.getAll("pass_category").length ? s.getAll("pass_category") : null,
    area_code: s.getAll("area_code").length ? s.getAll("area_code") : null,
    engagement_id: engs.length ? engs : null,
    expiring_within_days: s.getInt("expiring_within_days", 0) || null,
    worker_id: s.get("worker_id") || null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useAirportPasses(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("passes")} description={t("passesHint")} />
      <PassSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="airport_passes" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="ap-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchPassHint")} />
        <MultiSelect id="ap-validity" label={tc("status")} options={VALIDITY_STATUSES.map((x) => ({ value: x, label: te(`validityStatus.${x}`) }))} value={validity} onChange={(v) => s.set({ validity_status: v })} />
        <MultiSelect id="ap-custody" label={t("custody")} options={CUSTODY_STATUSES.map((x) => ({ value: x, label: te(`custodyStatus.${x}`) }))} value={custody} onChange={(v) => s.set({ custody_status: v })} />
        <MultiSelect id="ap-cat" label={t("fields.pass_category")} options={(cats.data?.items ?? []).map((c) => ({ value: c.code, label: c.code }))} value={s.getAll("pass_category")} onChange={(v) => s.set({ pass_category: v })} />
        <MultiSelect id="ap-area" label={t("fields.area_codes")} options={(areas.data?.items ?? []).map((c) => ({ value: c.code, label: c.code }))} value={s.getAll("area_code")} onChange={(v) => s.set({ area_code: v })} />
        <MultiSelect id="ap-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="ap-overdue" label={t("returnOverdue")} value={s.get("return_overdue") === "true" ? "true" : ""} onChange={(v) => s.set({ return_overdue: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="passes-table">
            <THead>
              <TR>
                <TH>{t("fields.pass_no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("fields.pass_category")}</TH>
                <TH>{t("fields.area_codes")}</TH>
                <TH>{t("fields.card_expiry_date")}</TH>
                <TH>{t("effectiveUntil")}</TH>
                <TH>{t("custody")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="pass-row">
                  <TD label={t("fields.pass_no")}>
                    <Link href={`/airport-passes/${p.id}`} className="ltr font-medium text-primary hover:underline">
                      {p.pass_no}
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <Code>{p.worker.worker_no}</Code> {personName(p.worker, locale)}
                    {p.engagement ? <span className="block text-xs text-muted-foreground">{p.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("fields.pass_category")}>
                    <Code>{p.pass_category}</Code> {p.escorted ? <span className="text-xs text-muted-foreground">({t("escorted")})</span> : null}
                  </TD>
                  <TD label={t("fields.area_codes")}>
                    <span className="ltr">{p.area_codes.join(", ")}</span>
                  </TD>
                  <TD label={t("fields.card_expiry_date")}><StackedDate v={p.card_expiry_date} /></TD>
                  <TD label={t("effectiveUntil")}>
                    <span className="flex flex-col items-start gap-0.5">
                      <StackedDate v={p.validity.effective_valid_until} />
                      {p.validity.validity_status === "active" ? <DaysLeft days={p.validity.days_left} /> : null}
                      {p.validity.limiting_factor ? <span className="text-xs text-muted-foreground">{te(`limitingFactor.${p.validity.limiting_factor}`)}</span> : null}
                    </span>
                  </TD>
                  <TD label={t("custody")}>
                    {p.validity.custody_status ? <StatusBadge status={p.validity.return_overdue ? "return_overdue" : p.validity.custody_status} label={p.validity.return_overdue ? t("returnOverdue") : te(`custodyStatus.${p.validity.custody_status}`)} /> : "—"}
                  </TD>
                  <TD label={tc("status")}>
                    <ValidityBadge status={p.validity.validity_status} />
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
    </div>
  );
}

export function AirportPassDetail({ id }: { id: string }) {
  const t = useTranslations("passes");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const q = useAirportPass(id);
  const qc = useQueryClient();
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("passes"), href: "/airport-passes" }, { label: p.pass_no }]} />
        <PageHeader title={p.pass_no} description={`${p.worker.worker_no} · ${personName(p.worker, locale)}`} actions={<ValidityBadge status={p.validity.validity_status} />} />
      </div>
      <ValidityLine v={p.validity} projectId={p.project_id} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("worker")}>
                <Link href={`/workers/${p.worker.id}`} className="text-primary hover:underline">
                  <Code>{p.worker.worker_no}</Code> {personName(p.worker, locale)}
                </Link>
              </FieldItem>
              <FieldItem label={t("fields.sponsor_engagement")}>{p.engagement?.short_code ?? t("clientStaff")}</FieldItem>
              <FieldItem label={t("fields.pass_category")}>
                <Code>{p.pass_category}</Code> {p.escorted ? `(${t("escorted")})` : ""}
              </FieldItem>
              <FieldItem label={t("fields.card_colour")}>{te(`cardColour.${p.card_colour}`)}</FieldItem>
              <FieldItem label={t("fields.area_codes")} ltr>
                {p.area_codes.join(", ")}
              </FieldItem>
              <FieldItem label={t("fields.issued_on")}>{date(p.issued_on)}</FieldItem>
              <FieldItem label={t("fields.card_expiry_date")}>{date(p.card_expiry_date)}</FieldItem>
              <FieldItem label={t("effectiveUntil")}>{date(p.validity.effective_valid_until)}</FieldItem>
              {can(me, "background_check.view", p.project_id) && "background_recheck_due" in p ? <FieldItem label={t("fields.recheck_due")}>{date(p.background_recheck_due)}</FieldItem> : null}
              <FieldItem label={t("application")}>
                <Link href={`/pass-applications/${p.application_id}`} className="text-primary hover:underline">
                  {t("openApplication")}
                </Link>
              </FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <CredentialPanel kind="airport_pass" id={p.id} projectId={p.project_id} onChanged={() => void qc.invalidateQueries({ queryKey: ak.pass(p.id) })} />
      </div>
      <HistoryPanel entityType="airport_pass" entityId={p.id} />
    </div>
  );
}
