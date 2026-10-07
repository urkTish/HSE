"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Car, FilePlus2, Gauge, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { AREA_CATEGORIES, LICENCE_CLASSES, LICENCE_ISSUERS, OFFENCE_STATUSES, VALIDITY_STATUSES, VEHICLE_CLASSES } from "@/lib/access-enums";
import { ak, useAdp, useAdps, useOffence, useOffences } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { todayInZone, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { joinList, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { AirportOnly, Code, DaysLeft, DeploymentPicker, StepDialog, SubNav, ValidityBadge, ValidityLine, VehicleSelect, personName } from "./common";
import { CredentialPanel } from "./credential-actions";

const PAGE_SIZE = 50;
type Adp = Schemas["AdpRead"];

function AdpSubNav() {
  const t = useTranslations("adps");
  return (
    <SubNav
      items={[
        { href: "/adps", label: t("title"), testId: "sub-adps" },
        { href: "/offences", label: t("offences"), testId: "sub-offences" },
      ]}
    />
  );
}

/* ───────────────────────────── ADP list ───────────────────────────── */

export function AdpListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<AdpList project={p} />}</AirportOnly>}</ProjectGate>;
}

function AdpList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const validity = s.getAll("validity_status") as Schemas["ValidityStatus"][];
  const engs = s.getAll("engagement_id");
  const q: Parameters<typeof useAdps>[1] = {
    validity_status: validity.length ? validity : null,
    category: (s.get("category") as Schemas["AreaCategory"] | null) || null,
    engagement_id: engs.length ? engs : null,
    expiring_within_days: s.getInt("expiring_within_days", 0) || null,
    worker_id: s.get("worker_id") || null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useAdps(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "adp.apply", project.id) ? (
            <Button asChild>
              <Link href="/adps/new" data-testid="new-adp">
                <Plus aria-hidden />
                {t("apply")}
              </Link>
            </Button>
          ) : null
        }
      />
      <AdpSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="adps" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="adp-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="adp-validity" label={tc("status")} options={VALIDITY_STATUSES.map((x) => ({ value: x, label: te(`validityStatus.${x}`) }))} value={validity} onChange={(v) => s.set({ validity_status: v })} />
        <SelectFilter id="adp-cat" label={t("fields.category")} value={(q.category ?? "") as Schemas["AreaCategory"] | ""} onChange={(v) => s.set({ category: v })} options={AREA_CATEGORIES.map((x) => ({ value: x, label: te(`areaCategory.${x}`) }))} />
        <MultiSelect id="adp-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="adps-table">
            <THead>
              <TR>
                <TH>{t("fields.adp_no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("fields.category")}</TH>
                <TH>{t("fields.vehicle_classes")}</TH>
                <TH>{t("points")}</TH>
                <TH>{t("effectiveUntil")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="adp-row">
                  <TD label={t("fields.adp_no")}>
                    <Link href={`/adps/${a.id}`} className="ltr font-medium text-primary hover:underline">
                      {a.adp_no ?? t("pendingNo")}
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <Code>{a.worker.worker_no}</Code> {personName(a.worker, locale)}
                    {a.engagement ? <span className="block text-xs text-muted-foreground">{a.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("fields.category")}>{te(`areaCategory.${a.category}`)}</TD>
                  <TD label={t("fields.vehicle_classes")}>{joinList(a.vehicle_classes.map((c) => te(`vehicleClass.${c}`)))}</TD>
                  <TD label={t("points")}>{a.points ? `${a.points.points_12m} / ${a.points.threshold}` : "—"}</TD>
                  <TD label={t("effectiveUntil")}>
                    {date(a.validity.effective_valid_until)} {a.validity.validity_status === "active" ? <DaysLeft days={a.validity.days_left} /> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <ValidityBadge status={a.validity.validity_status} />
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

/* ───────────────────────────── Apply ───────────────────────────── */

export function AdpCreatePage() {
  const t = useTranslations("adps");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/adps" }, { label: t("apply") }]} />
      <PageHeader title={t("apply")} description={t("applyHint")} />
      <ProjectGate>{(p) => <AirportOnly project={p}>{<AdpForm project={p} />}</AirportOnly>}</ProjectGate>
    </div>
  );
}

function AdpForm({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const [dep, setDep] = useState<Schemas["DeploymentRead"] | null>(null);
  const [cat, setCat] = useState<Schemas["AreaCategory"]>("apron");
  const [classes, setClasses] = useState<Schemas["VehicleClass"][]>(["light"]);
  const [issuer, setIssuer] = useState<Schemas["LicenceIssuer"]>("ksa");
  const [lclass, setLclass] = useState<Schemas["LicenceClass"]>("private");
  const [expiry, setExpiry] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    const e: Record<string, string> = {};
    if (!dep) e.dep = tv("required");
    if (!expiry) e.expiry = tv("required");
    if (classes.length === 0) e.classes = tv("required");
    setErrors(e);
    if (Object.keys(e).length || !dep) return;
    setBusy(true);
    setError(null);
    try {
      const a = await unwrap(
        api.POST("/api/v1/projects/{project_id}/adps", {
          params: { path: { project_id: project.id } },
          body: { deployment_id: dep.id, category: cat, vehicle_classes: classes, licence_issuer: issuer, licence_class: lclass, licence_expiry_date: expiry },
        }),
      );
      qc.setQueryData(ak.adp(a.id), a);
      await qc.invalidateQueries({ queryKey: ["adps"] });
      toast.success(t("applied"));
      router.push(`/adps/${a.id}`);
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
      data-testid="adp-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("driver")}>
        <div className="sm:col-span-2">
          <DeploymentPicker id="adp-worker" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("worker")} required error={errors.dep} />
        </div>
        <FormField id="adp-cat-sel" label={t("fields.category")} required hint={t("categoryHint")}>
          <Select value={cat} onChange={(e) => setCat(e.target.value as Schemas["AreaCategory"])}>
            {AREA_CATEGORIES.map((x) => (
              <option key={x} value={x}>
                {te(`areaCategory.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <div>
          <MultiSelect id="adp-classes" label={t("fields.vehicle_classes")} options={VEHICLE_CLASSES.map((x) => ({ value: x, label: te(`vehicleClass.${x}`) }))} value={classes} onChange={(v) => setClasses(v as Schemas["VehicleClass"][])} className="lg:w-full" />
          {errors.classes ? <p className="text-xs font-medium text-destructive">{errors.classes}</p> : null}
        </div>
      </FormSection>
      <FormSection title={t("licence")} description={t("licenceHint")}>
        <FormField id="adp-issuer" label={t("fields.licence_issuer")} required>
          <Select value={issuer} onChange={(e) => setIssuer(e.target.value as Schemas["LicenceIssuer"])}>
            {LICENCE_ISSUERS.map((x) => (
              <option key={x} value={x}>
                {te(`licenceIssuer.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="adp-lclass" label={t("fields.licence_class")} required>
          <Select value={lclass} onChange={(e) => setLclass(e.target.value as Schemas["LicenceClass"])}>
            {LICENCE_CLASSES.map((x) => (
              <option key={x} value={x}>
                {te(`licenceClass.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="adp-expiry" label={t("fields.licence_expiry_date")} required error={errors.expiry}>
          <Input type="date" min={todayInZone()} value={expiry} onChange={(e) => setExpiry(e.target.value)} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-adp">
          {busy ? tc("saving") : t("apply")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── ADP detail ───────────────────────────── */

export function AdpDetail({ id }: { id: string }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const [asOf, setAsOf] = useState<string>("");
  const q = useAdp(id, asOf || null);
  const qc = useQueryClient();
  const [step, setStep] = useState<"tests" | "issue" | "withdraw" | null>(null);
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  const pending = a.validity.validity_status === "pending";
  const issue = canWrite(me, "adp.issue", a.project_id);
  const apply = canWrite(me, "adp.apply", a.project_id);
  async function refresh(u: Adp) {
    qc.setQueryData(ak.adp(a.id), u);
    await qc.invalidateQueries({ queryKey: ["adps"] });
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/adps" }, { label: a.adp_no ?? t("pendingNo") }]} />
        <PageHeader
          title={a.adp_no ?? t("pendingTitle")}
          description={`${a.worker.worker_no} · ${personName(a.worker, locale)} · ${te(`areaCategory.${a.category}`)}`}
          actions={<ValidityBadge status={a.validity.validity_status} />}
        />
      </div>
      {pending && (issue || apply) ? (
        <div className="flex flex-wrap gap-2" data-testid="adp-actions">
          {issue ? (
            <>
              <Button variant="outline" onClick={() => setStep("tests")} data-testid="record-tests">
                <FilePlus2 aria-hidden />
                {t("recordTests")}
              </Button>
              <Button onClick={() => setStep("issue")} data-testid="issue-adp">
                {t("issue")}
              </Button>
            </>
          ) : null}
          <Button variant="destructive" onClick={() => setStep("withdraw")} data-testid="withdraw-adp">
            {t("withdraw")}
          </Button>
        </div>
      ) : null}
      {!pending ? <ValidityLine v={a.validity} projectId={a.project_id} /> : null}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("worker")}>
                <Link href={`/workers/${a.worker.id}`} className="text-primary hover:underline">
                  <Code>{a.worker.worker_no}</Code> {personName(a.worker, locale)}
                </Link>
              </FieldItem>
              <FieldItem label={tc("contractor")}>{a.engagement?.short_code ?? "—"}</FieldItem>
              <FieldItem label={t("fields.category")}>{te(`areaCategory.${a.category}`)}</FieldItem>
              <FieldItem label={t("fields.vehicle_classes")}>{joinList(a.vehicle_classes.map((c) => te(`vehicleClass.${c}`)))}</FieldItem>
              <FieldItem label={t("fields.licence_issuer")}>{te(`licenceIssuer.${a.licence_issuer}`)}</FieldItem>
              <FieldItem label={t("fields.licence_class")}>{te(`licenceClass.${a.licence_class}`)}</FieldItem>
              <FieldItem label={t("fields.licence_expiry_date")}>{date(a.licence_expiry_date)}</FieldItem>
              <FieldItem label={t("fields.theory")}>{a.theory_test_date ? `${date(a.theory_test_date)} · ${a.theory_score_pct ?? "—"}%` : "—"}</FieldItem>
              <FieldItem label={t("fields.practical")}>
                {a.practical_test_date ? `${date(a.practical_test_date)} · ${a.practical_result ? te(`practicalResult.${a.practical_result}`) : "—"}` : "—"}
                {a.practical_examiner ? <span className="block text-xs text-muted-foreground">{a.practical_examiner}</span> : null}
              </FieldItem>
              <FieldItem label={t("fields.practical_included_manoeuvring")}>
                <YesNo value={a.practical_included_manoeuvring} yes={tc("yes")} no={tc("no")} />
              </FieldItem>
              <FieldItem label={t("fields.rtf_competence")}>
                <YesNo value={a.rtf_competence} yes={tc("yes")} no={tc("no")} />
              </FieldItem>
              <FieldItem label={t("fields.issued_on")}>{date(a.issued_on)}</FieldItem>
              <FieldItem label={t("fields.own_valid_until")}>{date(a.own_valid_until)}</FieldItem>
              <FieldItem label={t("pass")}>
                {a.pass_id ? (
                  <Link href={`/airport-passes/${a.pass_id}`} className="text-primary hover:underline">
                    {t("openPass")}
                  </Link>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("suspensionsInWindow")}>{a.suspension_count_window}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          <Card data-testid="adp-points">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gauge aria-hidden className="size-4" />
                {t("points")}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {a.points ? (
                <>
                  <p className="text-3xl font-bold tabular-nums" data-testid="points-value">
                    {a.points.points_12m}
                    <span className="text-base font-normal text-muted-foreground"> / {a.points.threshold}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">{t("pointsWindow", { from: date(a.points.window_start_exclusive), to: date(a.points.as_of) })}</p>
                  {a.points.points_12m >= a.points.threshold ? <Alert tone="danger">{t("thresholdReached")}</Alert> : null}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
              <FormField id="points-as-of" label={t("pointsAsOf")}>
                <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
              </FormField>
            </CardContent>
          </Card>
          {!pending ? <CredentialPanel kind="adp" id={a.id} projectId={a.project_id} onChanged={() => void qc.invalidateQueries({ queryKey: ak.adp(a.id) })} /> : null}
        </div>
      </div>
      <WorkerOffences projectId={a.project_id} workerId={a.worker.id} />
      <HistoryPanel entityType="adp" entityId={a.id} />
      {step === "tests" ? <TestsDialog adp={a} onSaved={refresh} onClose={() => setStep(null)} /> : null}
      {step === "issue" ? <IssueAdpDialog adp={a} onSaved={refresh} onClose={() => setStep(null)} /> : null}
      {step === "withdraw" ? (
        <StepDialog
          title={t("withdraw")}
          description={t("withdrawHint")}
          destructive
          confirmLabel={t("withdraw")}
          onConfirm={async () => {
            const u = await unwrap(api.POST("/api/v1/adps/{adp_id}/withdraw", { params: { path: { adp_id: a.id } } }));
            await refresh(u);
            toast.success(t("withdrawn"));
          }}
          onClose={() => setStep(null)}
        />
      ) : null}
    </div>
  );
}

function TestsDialog({ adp, onSaved, onClose }: { adp: Adp; onSaved: (a: Adp) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [theoryDate, setTheoryDate] = useState(adp.theory_test_date ?? "");
  const [score, setScore] = useState(adp.theory_score_pct ?? "");
  const [practDate, setPractDate] = useState(adp.practical_test_date ?? "");
  const [result, setResult] = useState<Schemas["PracticalTestResult"] | "">(adp.practical_result ?? "");
  const [examiner, setExaminer] = useState(adp.practical_examiner ?? "");
  const [manoeuvring, setManoeuvring] = useState(adp.practical_included_manoeuvring ?? false);
  const [rtf, setRtf] = useState(adp.rtf_competence ?? false);
  return (
    <StepDialog
      title={t("recordTests")}
      description={t("testsHint")}
      confirmLabel={tc("save")}
      testId="save-tests"
      wide
      onConfirm={async () => {
        const u = await unwrap(
          api.PATCH("/api/v1/adps/{adp_id}", {
            params: { path: { adp_id: adp.id } },
            body: {
              theory_test_date: theoryDate || null,
              theory_score_pct: score || null,
              practical_test_date: practDate || null,
              practical_result: result || null,
              practical_examiner: examiner.trim() || null,
              practical_included_manoeuvring: manoeuvring,
              rtf_competence: rtf,
            },
          }),
        );
        await onSaved(u);
        toast.success(tc("saved"));
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="t-theory-date" label={t("fields.theory_test_date")}>
          <Input type="date" max={todayInZone()} value={theoryDate} onChange={(e) => setTheoryDate(e.target.value)} />
        </FormField>
        <FormField id="t-theory-score" label={t("fields.theory_score_pct")}>
          <Input type="number" min={0} max={100} step="0.01" value={score} onChange={(e) => setScore(e.target.value)} />
        </FormField>
        <FormField id="t-pract-date" label={t("fields.practical_test_date")}>
          <Input type="date" max={todayInZone()} value={practDate} onChange={(e) => setPractDate(e.target.value)} />
        </FormField>
        <FormField id="t-pract-result" label={t("fields.practical_result")}>
          <Select value={result} onChange={(e) => setResult(e.target.value as Schemas["PracticalTestResult"] | "")}>
            <option value="">{tc("select")}</option>
            {(["passed", "failed"] as const).map((x) => (
              <option key={x} value={x}>
                {te(`practicalResult.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="t-examiner" label={t("fields.practical_examiner")} className="sm:col-span-2">
          <Input maxLength={120} value={examiner} onChange={(e) => setExaminer(e.target.value)} />
        </FormField>
        <CheckboxField id="t-manoeuvring" label={t("fields.practical_included_manoeuvring")}>
          <Checkbox checked={manoeuvring} onChange={(e) => setManoeuvring(e.target.checked)} />
        </CheckboxField>
        <CheckboxField id="t-rtf" label={t("fields.rtf_competence")}>
          <Checkbox checked={rtf} onChange={(e) => setRtf(e.target.checked)} />
        </CheckboxField>
      </div>
      {adp.category === "manoeuvring" && (!rtf || !manoeuvring) ? <Alert tone="warning">{t("rtfRequired")}</Alert> : null}
    </StepDialog>
  );
}

function IssueAdpDialog({ adp, onSaved, onClose }: { adp: Adp; onSaved: (a: Adp) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("adps");
  const [no, setNo] = useState("");
  const [issued, setIssued] = useState(todayInZone());
  const [until, setUntil] = useState("");
  return (
    <StepDialog
      title={t("issue")}
      description={t("issueHint")}
      confirmLabel={t("issue")}
      testId="issue-adp-confirm"
      disabled={!no.trim() || !issued || !until}
      onConfirm={async () => {
        const u = await unwrap(api.POST("/api/v1/adps/{adp_id}/issue", { params: { path: { adp_id: adp.id } }, body: { adp_no: no.trim(), issued_on: issued, own_valid_until: until } }));
        await onSaved(u);
        toast.success(t("issued", { no: u.adp_no ?? "" }));
      }}
      onClose={onClose}
    >
      <FormField id="ia-no" label={t("fields.adp_no")} required>
        <Input className="ltr" maxLength={30} value={no} onChange={(e) => setNo(e.target.value)} />
      </FormField>
      <FormField id="ia-on" label={t("fields.issued_on")} required>
        <Input type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
      </FormField>
      <FormField id="ia-until" label={t("fields.own_valid_until")} required>
        <Input type="date" min={issued} value={until} onChange={(e) => setUntil(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function WorkerOffences({ projectId, workerId }: { projectId: string; workerId: string }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const locale = useLocale();
  const { dateTime } = useFormatters(projectId);
  const q = useOffences(projectId, { worker_id: workerId, page_size: 50 });
  const items = q.data?.items ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("offences")}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noOffences")}</p>
        ) : (
          <ul className="flex flex-col divide-y" data-testid="worker-offences">
            {items.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Link href={`/offences/${o.id}`} className="ltr font-medium text-primary hover:underline">
                  {o.offence_no}
                </Link>
                <span>{locale === "ar" ? o.offence_label_ar : o.offence_label_en}</span>
                <span className="text-muted-foreground">{dateTime(o.offence_at)}</span>
                <span className="font-medium tabular-nums">{t("pointsN", { n: o.points })}</span>
                <StatusBadge status={o.status} label={te(`offenceStatus.${o.status}`)} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* ───────────────────────────── Offences ───────────────────────────── */

export function OffenceListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<OffenceList project={p} />}</AirportOnly>}</ProjectGate>;
}

function OffenceList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const refs = useRefLists();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["OffenceStatus"][];
  const codes = s.getAll("offence_code");
  const engs = s.getAll("engagement_id");
  const query = useOffences(project.id, {
    status: status.length ? status : null,
    offence_code: codes.length ? codes : null,
    engagement_id: engs.length ? engs : null,
    worker_id: s.get("worker_id") || null,
    zone_id: s.get("zone_id") || null,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("offences")}
        description={t("offencesHint")}
        actions={
          canWrite(me, "offence.record", project.id) ? (
            <Button asChild>
              <Link href="/offences/new" data-testid="new-offence">
                <Plus aria-hidden />
                {t("recordOffence")}
              </Link>
            </Button>
          ) : null
        }
      />
      <AdpSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="airside_offences" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="of-status" label={tc("status")} options={OFFENCE_STATUSES.map((x) => ({ value: x, label: te(`offenceStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="of-code" label={t("fields.offence_code")} options={refs.options("airside_offence").map((o) => ({ value: o.value, label: `${o.value} · ${o.label}` }))} value={codes} onChange={(v) => s.set({ offence_code: v })} />
        <MultiSelect id="of-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="offences-table">
            <THead>
              <TR>
                <TH>{t("fields.offence_no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("fields.offence_code")}</TH>
                <TH>{t("fields.offence_at")}</TH>
                <TH>{tc("zone")}</TH>
                <TH>{t("points")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((o) => (
                <TR key={o.id} data-testid="offence-row">
                  <TD label={t("fields.offence_no")}>
                    <Link href={`/offences/${o.id}`} className="ltr font-medium text-primary hover:underline">
                      {o.offence_no}
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <Code>{o.worker.worker_no}</Code> {personName(o.worker, locale)}
                  </TD>
                  <TD label={t("fields.offence_code")}>
                    <Code>{o.offence_code}</Code> {locale === "ar" ? o.offence_label_ar : o.offence_label_en}
                  </TD>
                  <TD label={t("fields.offence_at")}>{dateTime(o.offence_at)}</TD>
                  <TD label={tc("zone")}>
                    <Code>{o.zone.code}</Code> {name(o.zone.name_en, o.zone.name_ar)}
                  </TD>
                  <TD label={t("points")}>
                    {o.points}
                    {o.immediate_suspension ? (
                      <span className="ms-1">
                        <StatusBadge status="suspended" label={t("immediate")} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={o.status} label={te(`offenceStatus.${o.status}`)} />
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

export function OffenceCreatePage() {
  const t = useTranslations("adps");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("offences"), href: "/offences" }, { label: t("recordOffence") }]} />
      <PageHeader title={t("recordOffence")} description={t("recordOffenceHint")} />
      <ProjectGate>{(p) => <AirportOnly project={p}>{<OffenceForm project={p} />}</AirportOnly>}</ProjectGate>
    </div>
  );
}

function OffenceForm({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("adps");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const refs = useRefLists();
  const opts = useProjectOptions(project.id);
  const airside = opts.zones.filter((z) => z.zoneType === "airside");
  const [dep, setDep] = useState<Schemas["DeploymentRead"] | null>(null);
  const [code, setCode] = useState("");
  const [at, setAt] = useState(() => utcToZonedInput(new Date().toISOString()));
  const [zone, setZone] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const item = refs.items("airside_offence").find((i) => i.code === code);
  async function save() {
    const e: Record<string, string> = {};
    if (!dep) e.dep = tv("required");
    if (!code) e.code = tv("required");
    if (!zone) e.zone = tv("required");
    setErrors(e);
    if (Object.keys(e).length || !dep) return;
    setBusy(true);
    setError(null);
    try {
      const o = await unwrap(
        api.POST("/api/v1/projects/{project_id}/airside-offences", {
          params: { path: { project_id: project.id } },
          body: { worker_id: dep.worker_id, offence_code: code, offence_at: zonedInputToUtc(at), zone_id: zone, vehicle_id: vehicle || null, notes: notes.trim() || null },
        }),
      );
      qc.setQueryData(ak.offence(o.id), o);
      for (const k of ["offences", "adps", "adp", "worker"]) await qc.invalidateQueries({ queryKey: [k] });
      toast.success(t("offenceSaved", { no: o.offence_no }));
      router.push(`/offences/${o.id}`);
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
      data-testid="offence-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("offence")}>
        <div className="sm:col-span-2">
          <DeploymentPicker id="of-worker" projectId={project.id} value={dep} onChange={setDep} label={t("worker")} required error={errors.dep} />
        </div>
        <FormField id="of-code-sel" label={t("fields.offence_code")} required error={errors.code} className="sm:col-span-2">
          <Select value={code} onChange={(e) => setCode(e.target.value)}>
            <option value="">{tc("select")}</option>
            {refs.options("airside_offence").map((o) => (
              <option key={o.value} value={o.value}>
                {o.value} · {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        {code === "OFF-05" || code === "OFF-06" ? (
          <Alert tone="warning" className="sm:col-span-2">
            {t("immediateHint")}
          </Alert>
        ) : item ? null : null}
        <FormField id="of-at" label={t("fields.offence_at")} required>
          <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
        </FormField>
        <FormField id="of-zone" label={tc("zone")} required error={errors.zone}>
          <Select value={zone} onChange={(e) => setZone(e.target.value)}>
            <option value="">{tc("select")}</option>
            {airside.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="of-vehicle" label={t("fields.vehicle")}>
          <VehicleSelect id="of-vehicle-sel" projectId={project.id} value={vehicle} onChange={(v) => setVehicle(v)} placeholder={tc("none")} />
        </FormField>
        <FormField id="of-notes" label={t("fields.notes")} className="sm:col-span-2" hint={tc("pdplHint")}>
          <Textarea rows={3} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-offence">
          <Car aria-hidden />
          {busy ? tc("saving") : t("recordOffence")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

export function OffenceDetail({ id }: { id: string }) {
  const t = useTranslations("adps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const name = useLocalizedName();
  const q = useOffence(id);
  const qc = useQueryClient();
  const [to, setTo] = useState<Schemas["OffenceStatus"] | null>(null);
  const [reason, setReason] = useState("");
  const { dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  const canAct = canWrite(me, "credential.suspend_confirm", o.project_id) || canWrite(me, "adp.issue", o.project_id);
  const next: Schemas["OffenceStatus"][] = o.status === "recorded" ? ["disputed", "upheld", "withdrawn"] : o.status === "disputed" ? ["upheld", "withdrawn"] : [];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("offences"), href: "/offences" }, { label: o.offence_no }]} />
        <PageHeader title={o.offence_no} description={`${o.offence_code} · ${locale === "ar" ? o.offence_label_ar : o.offence_label_en}`} actions={<StatusBadge status={o.status} label={te(`offenceStatus.${o.status}`)} />} />
      </div>
      {canAct && next.length ? (
        <div className="flex flex-wrap gap-2">
          {next.map((s) => (
            <Button
              key={s}
              variant={s === "withdrawn" ? "destructive" : "outline"}
              onClick={() => {
                setReason("");
                setTo(s);
              }}
              data-testid={`offence-${s}`}
            >
              {te(`offenceStatus.${s}`)}
            </Button>
          ))}
        </div>
      ) : null}
      {o.resulting_actions.length ? (
        <Alert tone="warning" data-testid="resulting-actions">
          {o.resulting_actions.map((a) => t(`result.${a as "adp_suspended_points" | "adp_suspended_violation" | "adp_revoked"}`)).join(" · ")}
        </Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("worker")}>
              <Link href={`/workers/${o.worker.id}`} className="text-primary hover:underline">
                <Code>{o.worker.worker_no}</Code> {personName(o.worker, locale)}
              </Link>
            </FieldItem>
            <FieldItem label={t("fields.adp_no")}>
              {o.adp_id ? (
                <Link href={`/adps/${o.adp_id}`} className="ltr text-primary hover:underline">
                  {o.adp_no}
                </Link>
              ) : (
                t("noAdp")
              )}
            </FieldItem>
            <FieldItem label={t("fields.offence_at")}>{dateTime(o.offence_at)}</FieldItem>
            <FieldItem label={tc("zone")}>
              <Code>{o.zone.code}</Code> {name(o.zone.name_en, o.zone.name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.vehicle")} ltr>
              {o.vehicle ? o.vehicle.vehicle_no : "—"}
            </FieldItem>
            <FieldItem label={t("points")}>
              {o.points} {o.immediate_suspension ? `· ${t("immediate")}` : ""}
            </FieldItem>
            <FieldItem label={t("fields.reported_by")}>{name(o.reported_by.full_name_en, o.reported_by.full_name_ar)}</FieldItem>
            <FieldItem label={t("fields.incident")}>
              {o.incident_id ? (
                <Link href={`/incidents/${o.incident_id}`} className="text-primary hover:underline">
                  {t("openIncident")}
                </Link>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("fields.notes")} wide>
              {o.notes ?? "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("evidence")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Attachments ownerType="offence_evidence" ownerId={o.id} canUpload={canWrite(me, "offence.record", o.project_id)} />
        </CardContent>
      </Card>
      <HistoryPanel entityType="airside_offence" entityId={o.id} />
      {to ? (
        <StepDialog
          title={te(`offenceStatus.${to}`)}
          description={to === "withdrawn" ? t("withdrawOffenceHint") : undefined}
          destructive={to === "withdrawn"}
          confirmLabel={te(`offenceStatus.${to}`)}
          disabled={reason.trim().length < 10}
          onConfirm={async () => {
            const u = await unwrap(api.POST("/api/v1/airside-offences/{offence_id}/transitions", { params: { path: { offence_id: o.id } }, body: { to_status: to, reason: reason.trim() } }));
            qc.setQueryData(ak.offence(o.id), u);
            for (const k of ["offences", "adps", "adp"]) await qc.invalidateQueries({ queryKey: [k] });
            toast.success(tc("saved"));
          }}
          onClose={() => setTo(null)}
        >
          <FormField id="of-reason" label={tc("reason")} required hint={t("min10")}>
            <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}
