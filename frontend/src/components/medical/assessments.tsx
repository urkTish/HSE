"use client";
import { ExternalLink, FileSearch, Plus, Stethoscope, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick, UploadField, UserName } from "@/components/cert/common";
import { useSigned } from "@/components/ptw/signing";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useDeployments } from "@/lib/api/access";
import { mk, useFitnessAssessment, useFitnessAssessments, useFitnessHolds, useFitnessReferrals, useFitnessVerifications, useMedicalRefresh } from "@/lib/api/medical";
import { todayInZone } from "@/lib/datetime";
import { ASSESSMENT_SOURCES, ASSESSMENT_STATUSES, ASSESSMENT_TYPES, FITNESS_OUTCOMES, FITNESS_SCAN_REASONS, FITNESS_VERIF_METHODS, FITNESS_VERIF_OUTCOMES, MED_VERIFICATION_STATUSES, RESTRICTION_CODES, RESTRICTION_WITH_TEXT, RESTRICTION_WITH_VALUE } from "@/lib/med-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { useQueryClient } from "@tanstack/react-query";
import {
  AssessmentStatusBadge,
  ExaminerSelect,
  FitnessCasesSubNav,
  FitnessCodeLabel,
  FitnessCodeSelect,
  MedProviderLabel,
  MedProviderSelect,
  MedVerificationBadge,
  NoDiagnosisHint,
  OutcomeBadge,
  RestrictionList,
  TierNote,
  useFitnessCatalogue,
  useMedCaps,
} from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/* ═════════════ list ═════════════ */

export function FitnessAssessmentsPage() {
  return <ProjectGate>{(p) => <Assessments project={p} />}</ProjectGate>;
}

function Assessments({ project }: { project: Project }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useMedCaps(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["AssessmentStatus"][];
  const source = s.getAll("source") as S["AssessmentSource"][];
  const verif = s.getAll("verification") as S["VerificationStatus"][];
  const mine = s.get("mine") === "1";
  const q = useFitnessAssessments(project.id, {
    q: s.get("q") || null,
    status: status.length ? status : null,
    source: source.length ? source : null,
    verification_status: verif.length ? verif : null,
    awaiting_signoff_mine: mine,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  const tier = items[0]?.tier;
  const tier2 = tier === "functional" || tier === "clinical_admin";
  const tier3 = tier === "clinical_admin";
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.recordClinic || caps.submitExternal ? (
            <Button asChild>
              <Link href="/fitness-assessments/new" data-testid="new-assessment">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <FitnessCasesSubNav />
      <ListToolbar>
        <SearchFilter id="fa-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="fa-status" label={tc("status")} options={ASSESSMENT_STATUSES.map((x) => ({ value: x, label: te(`assessmentStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="fa-source" label={t("source")} options={ASSESSMENT_SOURCES.map((x) => ({ value: x, label: te(`assessmentSource.${x}`) }))} value={source} onChange={(v) => s.set({ source: v })} />
        {tier3 ? <MultiSelect id="fa-verif" label={t("verification")} options={MED_VERIFICATION_STATUSES.map((x) => ({ value: x, label: te(`verificationStatus.${x}`) }))} value={verif} onChange={(v) => s.set({ verification: v })} /> : null}
        {caps.recordClinic ? <Tick id="fa-mine" label={t("awaitingMine")} checked={mine} onChange={(v) => s.set({ mine: v ? "1" : "" })} /> : null}
      </ListToolbar>
      <TierNote tier={tier} />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="assessments-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("examinedOn")}</TH>
                <TH>{t("source")}</TH>
                <TH>{t("lines")}</TH>
                {tier3 ? <TH>{t("verification")}</TH> : null}
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="assessment-row" data-no={a.assessment_no} data-status={a.status}>
                  <TD label={t("no")}>
                    <Link href={`/fitness-assessments/${a.id}`} className="font-medium text-primary hover:underline">
                      <Code>{a.assessment_no}</Code>
                    </Link>
                    {tier3 && a.assessment_type ? <span className="block text-xs text-muted-foreground">{te(`assessmentType.${a.assessment_type}`)}</span> : null}
                  </TD>
                  <TD label={t("worker")}>
                    <WorkerLabel w={a.worker} link />
                    {a.engagement_short_code ? <Code className="block text-xs text-muted-foreground">{a.engagement_short_code}</Code> : null}
                  </TD>
                  <TD label={t("examinedOn")}>{date(a.examined_on)}</TD>
                  <TD label={t("source")}>{te(`assessmentSource.${a.source}`)}</TD>
                  <TD label={t("lines")}>
                    <ul className="flex flex-col gap-0.5 text-xs">
                      {a.lines.map((l) => (
                        <li key={l.id} className="flex flex-wrap items-center gap-1">
                          <Code>{l.code}</Code>
                          {tier2 ? <OutcomeBadge outcome={l.outcome} /> : null}
                        </li>
                      ))}
                    </ul>
                  </TD>
                  {tier3 ? (
                    <TD label={t("verification")}>
                      <MedVerificationBadge status={a.verification_status} />
                    </TD>
                  ) : null}
                  <TD label={tc("status")}>
                    <AssessmentStatusBadge status={a.status} />
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

/* ═════════════ new assessment (site clinic or external certificate; §3.6, FA-1…FA-10) ═════════════ */

interface LineDraft {
  key: number;
  code: string;
  outcome: S["FitnessOutcome"] | "";
  restrictions: { code: S["RestrictionCode"]; value: string; text: string }[];
  restriction_review_date: string;
  unfit_review_date: string;
  printed_next_due: string;
}

let lineKey = 0;
const emptyLine = (code = ""): LineDraft => ({ key: ++lineKey, code, outcome: "", restrictions: [], restriction_review_date: "", unfit_review_date: "", printed_next_due: "" });

export function NewAssessmentPage() {
  return <ProjectGate>{(p) => <NewAssessment project={p} />}</ProjectGate>;
}

function NewAssessment({ project }: { project: Project }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useMedCaps(project.id);
  const router = useRouter();
  const signed = useSigned();
  const warn = useWarningToasts();
  const s = useSearchState();
  const workerNo = s.get("worker_no") ?? "";
  const pre = useDeployments(project.id, { q: workerNo || null, page_size: 5 }, { enabled: Boolean(workerNo) });
  const [source, setSource] = useState<S["AssessmentSource"]>(caps.recordClinic ? "site_clinic" : "external_certificate");
  // undefined = not picked yet: fall back to the ?worker_no= prefill.
  const [picked, setD] = useState<S["DeploymentRead"] | null | undefined>(undefined);
  const [type, setType] = useState<S["AssessmentType"] | "">((s.get("type") as S["AssessmentType"]) ?? "");
  const [holdId, setHoldId] = useState(s.get("hold") ?? "");
  const [referralPick, setReferralId] = useState(s.get("referral") ?? "");
  const [provider, setProvider] = useState("");
  const [examiner, setExaminer] = useState("");
  const [examinedOn, setExaminedOn] = useState(todayInZone());
  const [certNo, setCertNo] = useState("");
  const [nameAsPrinted, setNameAsPrinted] = useState("");
  const [idOnCard, setIdOnCard] = useState("");
  const [historic, setHistoric] = useState(false);
  const [notice, setNotice] = useState(false);
  const [lines, setLines] = useState<LineDraft[]>([emptyLine("GEN-FIT")]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const d = picked !== undefined ? picked : (pre.data?.items.find((x) => x.worker_no === workerNo) ?? null);
  const holds = useFitnessHolds(project.id, { worker_id: d?.worker_id ?? null, status: ["active"], page_size: 20 }, { enabled: Boolean(d) && type === "return_to_work" });
  const referrals = useFitnessReferrals(project.id, { worker_id: d?.worker_id ?? null, status: ["open"], page_size: 20 }, { enabled: Boolean(d) && type === "referral" });
  // A referral picked from the referrals list also releases its hold (FH-3), so a single referral is pre-selected.
  const onlyReferral = type === "referral" && referrals.data?.items.length === 1 ? (referrals.data.items[0]?.id ?? "") : "";
  const referralId = referralPick || onlyReferral;
  const external = source === "external_certificate";
  const linesOk = lines.length > 0 && lines.every((l) => l.code && l.outcome && (l.outcome !== "fit_with_restrictions" || l.restrictions.length > 0) && (l.outcome !== "temporarily_unfit" || l.unfit_review_date));
  const valid = d && type && provider && examiner && examinedOn && notice && linesOk && (!external || certNo.trim()) && (type !== "return_to_work" || holdId) && (type !== "referral" || referralId);

  function patchLine(key: number, p: Partial<LineDraft>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...p } : l)));
  }

  async function save() {
    if (!d || !type) return;
    setBusy(true);
    setError(null);
    try {
      const body: S["FitnessAssessmentCreate"] = {
        worker_id: d.worker_id,
        assessment_type: type,
        source,
        provider_id: provider,
        examiner_id: examiner,
        examined_on: examinedOn,
        certificate_no: external ? certNo.trim() : null,
        related_hold_id: type === "return_to_work" ? holdId || null : null,
        related_referral_id: type === "referral" ? referralId || null : null,
        purpose_notice_given: notice,
        name_as_printed: external ? nameAsPrinted.trim() || null : null,
        id_on_card: external ? idOnCard.trim() || null : null,
        historic: external && historic,
        lines: lines.map((l) => ({
          code: l.code,
          outcome: l.outcome as S["FitnessOutcome"],
          restrictions: l.outcome === "fit_with_restrictions" ? l.restrictions.map((r) => ({ code: r.code, value: r.value ? Number(r.value) : null, text: r.text.trim() || null })) : [],
          restriction_review_date: l.outcome === "fit_with_restrictions" ? l.restriction_review_date || null : null,
          unfit_review_date: l.outcome === "temporarily_unfit" ? l.unfit_review_date || null : null,
          printed_next_due: l.printed_next_due || null,
        })),
      };
      const r = await signed(() => unwrap(api.POST("/api/v1/projects/{project_id}/fitness-assessments", { params: { path: { project_id: project.id } }, body })));
      warn(r.warnings);
      toast.success(t("created", { no: r.assessment_no }));
      router.push(`/fitness-assessments/${r.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!caps.recordClinic && !caps.submitExternal) return <Alert tone="info">{t("noAccess")}</Alert>;
  return (
    <div className="mx-auto max-w-4xl">
      <Breadcrumbs items={[{ label: t("title"), href: "/fitness-assessments" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <Alert tone="info" className="mb-4">
        {t("boundary")}
      </Alert>
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="grid gap-3 pt-5 sm:grid-cols-2">
            <FormField id="fa-src" label={t("source")} required>
              <Select value={source} onChange={(e) => setSource(e.target.value as S["AssessmentSource"])} data-testid="fa-src">
                {caps.recordClinic ? <option value="site_clinic">{te("assessmentSource.site_clinic")}</option> : null}
                {caps.submitExternal ? <option value="external_certificate">{te("assessmentSource.external_certificate")}</option> : null}
              </Select>
            </FormField>
            <FormField id="fa-type" label={t("type")} required>
              <Select value={type} onChange={(e) => setType(e.target.value as S["AssessmentType"])} data-testid="fa-type">
                <option value="">{tc("select")}</option>
                {ASSESSMENT_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {te(`assessmentType.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <div className="sm:col-span-2">
              <DeploymentPicker id="fa-worker" projectId={project.id} value={d} onChange={setD} label={t("worker")} required status={["mobilised", "pending_induction"]} />
            </div>
            {type === "return_to_work" ? (
              <FormField id="fa-hold" label={t("relatedHold")} required hint={t("relatedHint")}>
                <Select value={holdId} onChange={(e) => setHoldId(e.target.value)} data-testid="fa-hold">
                  <option value="">{tc("select")}</option>
                  {(holds.data?.items ?? []).map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.hold_no}
                    </option>
                  ))}
                </Select>
              </FormField>
            ) : null}
            {type === "referral" ? (
              <FormField id="fa-referral" label={t("relatedReferral")} required hint={t("relatedHint")}>
                <Select value={referralId} onChange={(e) => setReferralId(e.target.value)} data-testid="fa-referral">
                  <option value="">{tc("select")}</option>
                  {(referrals.data?.items ?? []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.referral_no}
                    </option>
                  ))}
                </Select>
              </FormField>
            ) : null}
            <MedProviderSelect
              id="fa-provider"
              label={t("provider")}
              required
              projectId={project.id}
              kinds={external ? ["external_clinic", "contractor_clinic"] : ["site_clinic"]}
              value={provider}
              onChange={(v) => {
                setProvider(v);
                setExaminer("");
              }}
            />
            <ExaminerSelect id="fa-examiner" label={t("examiner")} required providerId={provider} value={examiner} onChange={setExaminer} />
            <FormField id="fa-examined" label={t("examinedOn")} required hint={external ? undefined : t("backdateHint")}>
              <Input type="date" value={examinedOn} max={todayInZone()} onChange={(e) => setExaminedOn(e.target.value)} className="ltr" data-testid="fa-examined" />
            </FormField>
            {external ? (
              <>
                <FormField id="fa-cert" label={t("certificateNo")} required>
                  <Input value={certNo} onChange={(e) => setCertNo(e.target.value)} maxLength={40} className="ltr" data-testid="fa-cert" />
                </FormField>
                <FormField id="fa-name" label={t("nameAsPrinted")}>
                  <Input value={nameAsPrinted} onChange={(e) => setNameAsPrinted(e.target.value)} maxLength={120} data-testid="fa-name" />
                </FormField>
                <FormField id="fa-id" label={t("idOnCard")} hint={t("idOnCardHint")}>
                  <Input value={idOnCard} onChange={(e) => setIdOnCard(e.target.value.replace(/\s/g, ""))} maxLength={20} className="ltr" autoComplete="off" data-testid="fa-id" />
                </FormField>
                {caps.clinical ? <Tick id="fa-historic" label={t("historic")} checked={historic} onChange={setHistoric} /> : null}
              </>
            ) : null}
          </CardContent>
        </Card>
        <Card data-testid="fa-lines">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">{t("lines")}</CardTitle>
            <Button size="sm" variant="outline" disabled={lines.length >= 11} onClick={() => setLines((ls) => [...ls, emptyLine()])} data-testid="fa-add-line">
              <Plus aria-hidden />
              {t("addLine")}
            </Button>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-xs text-muted-foreground">{t("linesHint")}</p>
            {lines.map((l, i) => (
              <LineEditor
                key={l.key}
                index={i}
                line={l}
                projectId={project.id}
                exclude={lines.filter((x) => x.key !== l.key).map((x) => x.code)}
                onChange={(p) => patchLine(l.key, p)}
                onRemove={lines.length > 1 ? () => setLines((ls) => ls.filter((x) => x.key !== l.key)) : undefined}
              />
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-5">
            <Tick id="fa-notice" label={t("purposeNotice")} checked={notice} onChange={setNotice} />
            {!external ? <p className="text-xs text-muted-foreground">{t("signNote")}</p> : <p className="text-xs text-muted-foreground">{t("externalNote")}</p>}
            <MutationError error={error} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" asChild>
                <Link href="/fitness-assessments">{tc("cancel")}</Link>
              </Button>
              <Button onClick={() => void save()} disabled={!valid || busy} data-testid="fa-save">
                <Stethoscope aria-hidden />
                {busy ? tc("saving") : external ? t("saveDraft") : t("saveRecord")}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LineEditor({ index, line, projectId, exclude, onChange, onRemove }: { index: number; line: LineDraft; projectId: string; exclude: string[]; onChange: (p: Partial<LineDraft>) => void; onRemove?: () => void }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [add, setAdd] = useState<S["RestrictionCode"] | "">("");
  const restricted = line.outcome === "fit_with_restrictions";
  return (
    <fieldset className="rounded-md border p-3" data-testid={`fa-line-${index}`}>
      <legend className="px-1 text-sm font-medium">{t("lineN", { n: index + 1 })}</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        <FitnessCodeSelect id={`fa-line-${index}-code`} label={t("code")} required projectId={projectId} value={line.code} exclude={exclude} onChange={(code) => onChange({ code })} />
        <FormField id={`fa-line-${index}-outcome`} label={t("outcome")} required>
          <Select value={line.outcome} onChange={(e) => onChange({ outcome: e.target.value as S["FitnessOutcome"], restrictions: [] })} data-testid={`fa-line-${index}-outcome`}>
            <option value="">{tc("select")}</option>
            {FITNESS_OUTCOMES.map((x) => (
              <option key={x} value={x}>
                {te(`fitnessOutcome.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`fa-line-${index}-next`} label={t("printedNextDue")}>
          <Input type="date" value={line.printed_next_due} onChange={(e) => onChange({ printed_next_due: e.target.value })} className="ltr" />
        </FormField>
        {line.outcome === "temporarily_unfit" ? (
          <FormField id={`fa-line-${index}-unfit`} label={t("unfitReview")} required>
            <Input type="date" value={line.unfit_review_date} onChange={(e) => onChange({ unfit_review_date: e.target.value })} className="ltr" data-testid={`fa-line-${index}-unfit`} />
          </FormField>
        ) : null}
      </div>
      {restricted ? (
        <div className="mt-3 flex flex-col gap-2">
          <p className="text-sm font-medium">{t("restrictions")}</p>
          {line.restrictions.map((r, i) => (
            <div key={`${r.code}-${i}`} className="flex flex-wrap items-end gap-2" data-testid="fa-restriction" data-code={r.code}>
              <span className="min-w-48 text-sm">{te(`restriction.${r.code}`)}</span>
              {RESTRICTION_WITH_VALUE.includes(r.code) ? (
                <FormField id={`fa-r-${index}-${i}-v`} label={t("kgLabel")}>
                  <Input value={r.value} inputMode="numeric" className="ltr w-24" onChange={(e) => onChange({ restrictions: line.restrictions.map((x, j) => (j === i ? { ...x, value: e.target.value.replace(/\D/g, "") } : x)) })} />
                </FormField>
              ) : null}
              {RESTRICTION_WITH_TEXT.includes(r.code) ? (
                <FormField id={`fa-r-${index}-${i}-t`} label={t("functionalLimit")} hint={t("functionalOnly")}>
                  <Input value={r.text} maxLength={100} onChange={(e) => onChange({ restrictions: line.restrictions.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} data-testid="fa-r-text" />
                </FormField>
              ) : null}
              {RESTRICTION_WITH_TEXT.includes(r.code) ? <PossibleIdHint text={r.text} /> : null}
              <Button size="sm" variant="ghost" aria-label={tc("delete")} onClick={() => onChange({ restrictions: line.restrictions.filter((_, j) => j !== i) })}>
                <Trash2 aria-hidden />
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap items-end gap-2">
            <FormField id={`fa-line-${index}-add-r`} label={t("addRestriction")}>
              <Select value={add} onChange={(e) => setAdd(e.target.value as S["RestrictionCode"])} data-testid={`fa-line-${index}-add-r`}>
                <option value="">{tc("select")}</option>
                {RESTRICTION_CODES.filter((c) => !line.restrictions.some((r) => r.code === c)).map((c) => (
                  <option key={c} value={c}>
                    {te(`restriction.${c}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <Button
              size="sm"
              variant="outline"
              disabled={!add}
              onClick={() => {
                if (!add) return;
                onChange({ restrictions: [...line.restrictions, { code: add, value: "", text: "" }] });
                setAdd("");
              }}
              data-testid={`fa-line-${index}-add-r-btn`}
            >
              <Plus aria-hidden />
              {tc("add")}
            </Button>
          </div>
          <FormField id={`fa-line-${index}-review`} label={t("restrictionReview")} hint={t("restrictionReviewHint")}>
            <Input type="date" value={line.restriction_review_date} onChange={(e) => onChange({ restriction_review_date: e.target.value })} className="ltr sm:w-48" data-testid={`fa-line-${index}-review`} />
          </FormField>
          <p className="text-xs text-muted-foreground">
            <NoDiagnosisHint />
          </p>
        </div>
      ) : null}
      {onRemove ? (
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="ghost" onClick={onRemove}>
            <Trash2 aria-hidden />
            {t("removeLine")}
          </Button>
        </div>
      ) : null}
    </fieldset>
  );
}

/* ═════════════ detail (§4.3 transitions, FV verification, scan view P6-5) ═════════════ */

export function AssessmentDetail({ id }: { id: string }) {
  const q = useFitnessAssessment(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  return <ProjectById id={a.project_id}>{(p) => <AssessmentView project={p} a={a} />}</ProjectById>;
}

type AAction = S["AssessmentAction"];

function AssessmentView({ project, a }: { project: Project; a: S["FitnessAssessmentRead"] }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useMedCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const { label } = useFitnessCatalogue(project.id);
  const refresh = useMedicalRefresh();
  const qc = useQueryClient();
  const signed = useSigned();
  const warn = useWarningToasts();
  const [action, setAction] = useState<AAction | null>(null);
  const [scan, setScan] = useState(false);
  const [verify, setVerify] = useState(false);
  const tier2 = a.tier !== "status";
  const tier3 = a.tier === "clinical_admin";
  const actions = a.allowed_actions ?? [];
  const external = a.source === "external_certificate";
  const canUpload = external && a.status === "draft" && caps.submitExternal;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/fitness-assessments" }, { label: a.assessment_no }]} />
      <PageHeader
        title={<Code>{a.assessment_no}</Code>}
        badge={
          <span className="inline-flex flex-wrap items-center gap-1">
            <AssessmentStatusBadge status={a.status} />
            <MedVerificationBadge status={a.verification_status} />
            {a.historic ? <Badge tone="neutral">{t("historicBadge")}</Badge> : null}
          </span>
        }
        actions={
          <>
            {actions.map((x) => (
              <Button key={x} variant={x === "reject" || x === "revoke" ? "destructive-outline" : x === "return" ? "outline" : "default"} onClick={() => setAction(x)} data-testid={`fa-${x}`}>
                {te(`assessmentAction.${x}`)}
              </Button>
            ))}
            {a.has_scan && caps.scan ? (
              <Button variant="outline" onClick={() => setScan(true)} data-testid="fa-open-scan">
                <FileSearch aria-hidden />
                {t("openScan")}
              </Button>
            ) : null}
          </>
        }
      />
      <ApiWarnings warnings={a.warnings} className="mb-4" />
      <TierNote tier={a.tier} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("worker")}>
                <WorkerLabel w={a.worker} link />
              </FieldItem>
              <FieldItem label={t("project")}>{project.code}</FieldItem>
              <FieldItem label={t("source")}>{te(`assessmentSource.${a.source}`)}</FieldItem>
              {a.assessment_type ? <FieldItem label={t("type")}>{te(`assessmentType.${a.assessment_type}`)}</FieldItem> : null}
              <FieldItem label={t("examinedOn")}>{date(a.examined_on)}</FieldItem>
              <FieldItem label={t("certificateNo")} ltr>
                {a.certificate_no}
              </FieldItem>
              {a.provider ? (
                <FieldItem label={t("provider")}>
                  <MedProviderLabel p={a.provider} />
                </FieldItem>
              ) : null}
              {a.examiner ? (
                <FieldItem label={t("examiner")}>
                  <Code>{a.examiner.examiner_no}</Code> {locale === "ar" ? a.examiner.full_name_ar : a.examiner.full_name_en} · {te(`examinerClass.${a.examiner.classification}`)}
                </FieldItem>
              ) : null}
              {a.related_hold_no ? (
                <FieldItem label={t("relatedHold")} ltr>
                  {a.related_hold_no}
                </FieldItem>
              ) : null}
              {a.related_referral_no ? (
                <FieldItem label={t("relatedReferral")} ltr>
                  {a.related_referral_no}
                </FieldItem>
              ) : null}
              {a.recorded_by ? (
                <FieldItem label={t("recordedBy")}>
                  <UserName u={a.recorded_by} />
                </FieldItem>
              ) : null}
              {a.signed_by ? (
                <FieldItem label={t("signedBy")}>
                  <UserName u={a.signed_by} /> {a.signed_at ? `· ${dateTime(a.signed_at)}` : ""}
                </FieldItem>
              ) : null}
              {a.submitted_by ? (
                <FieldItem label={t("submittedBy")}>
                  <UserName u={a.submitted_by} /> {a.submitted_at ? `· ${dateTime(a.submitted_at)}` : ""}
                </FieldItem>
              ) : null}
              {a.reviewed_by ? (
                <FieldItem label={t("reviewedBy")}>
                  <UserName u={a.reviewed_by} /> {a.reviewed_at ? `· ${dateTime(a.reviewed_at)}` : ""}
                </FieldItem>
              ) : null}
              {a.verification_due_on ? <FieldItem label={t("verificationDue")}>{date(a.verification_due_on)}</FieldItem> : null}
              {a.name_as_printed ? (
                <FieldItem label={t("nameAsPrinted")}>
                  {a.name_as_printed} {a.name_match ? <Badge tone={a.name_match === "exact" ? "success" : "warning"}>{te(`nameMatch.${a.name_match}`)}</Badge> : null}
                </FieldItem>
              ) : null}
              {a.id_match_result ? <FieldItem label={t("idMatch")}>{te(`idMatch.${a.id_match_result}`)}</FieldItem> : null}
              {a.clinical_data_present != null ? <FieldItem label={t("clinicalData")}>{a.clinical_data_present ? tc("yes") : tc("no")}</FieldItem> : null}
              {a.status_reason ? <FieldItem label={t("statusReason")}>{a.status_reason}</FieldItem> : null}
              {a.revoke ? (
                <FieldItem label={t("revoked")}>
                  {a.revoke.reason ?? a.revoke.code} · <UserName u={a.revoke.by} /> · {dateTime(a.revoke.at)}
                </FieldItem>
              ) : null}
              <FieldItem label={t("purposeNoticeShort")}>{a.purpose_notice_given ? tc("yes") : tc("no")}</FieldItem>
              <FieldItem label={t("scan")}>{a.has_scan ? t("scanAttached") : t("noScan")}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        {canUpload ? (
          <Card data-testid="fa-scan-upload">
            <CardHeader>
              <CardTitle className="text-base">{t("scan")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <UploadField
                id="fa-scan"
                label={t("uploadScan")}
                ownerType="fitness_scan"
                ownerId={a.id}
                accept="application/pdf,image/jpeg,image/png"
                value={null}
                onChange={async () => {
                  await qc.invalidateQueries({ queryKey: mk.assessment(a.id) });
                  toast.success(t("scanUploaded"));
                }}
                hint={t("scanHint")}
              />
            </CardContent>
          </Card>
        ) : null}
      </div>
      <Card className="mt-4" data-testid="fa-lines-view">
        <CardHeader>
          <CardTitle className="text-base">{t("lines")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>{t("code")}</TH>
                {tier2 ? <TH>{t("outcome")}</TH> : null}
                {tier2 ? <TH>{t("restrictions")}</TH> : null}
                <TH>{t("validUntil")}</TH>
                <TH>{t("lineState")}</TH>
              </TR>
            </THead>
            <TBody>
              {a.lines.map((l) => (
                <TR key={l.id} data-testid="fa-line" data-code={l.code} data-state={l.line_state}>
                  <TD label={t("code")}>
                    <FitnessCodeLabel code={l.code} name={label(l.code)} />
                  </TD>
                  {tier2 ? (
                    <TD label={t("outcome")}>
                      <OutcomeBadge outcome={l.outcome} />
                      {l.unfit_review_date ? <span className="block text-xs">{t("reassessOn", { d: date(l.unfit_review_date) })}</span> : null}
                    </TD>
                  ) : null}
                  {tier2 ? (
                    <TD label={t("restrictions")}>
                      <RestrictionList items={l.restrictions} />
                      {l.restriction_review_date ? <span className="block text-xs">{t("reviewOn", { d: date(l.restriction_review_date) })}</span> : null}
                    </TD>
                  ) : null}
                  <TD label={t("validUntil")}>
                    <span data-testid="line-valid-until">{l.effective_valid_until ? date(l.effective_valid_until) : "—"}</span>
                    {l.limiting_factor ? <span className="block text-xs text-muted-foreground">{t("limitedBy", { f: te(`fitnessLimitingFactor.${l.limiting_factor}`) })}</span> : null}
                    {l.printed_next_due ? <span className="block text-xs text-muted-foreground">{t("printedNextDueOn", { d: date(l.printed_next_due) })}</span> : null}
                  </TD>
                  <TD label={t("lineState")}>{te(`fitnessLineState.${l.line_state}`)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      {tier3 && external ? <Verifications a={a} projectId={project.id} canRecord={caps.review && a.status !== "draft" && a.status !== "rejected" && a.status !== "revoked"} onRecord={() => setVerify(true)} /> : null}
      {tier3 ? (
        <div className="mt-4">
          <HistoryPanel entityType="fitness_assessment" entityId={a.id} projectId={project.id} />
        </div>
      ) : null}
      {action ? (
        <ActionDialog
          a={a}
          action={action}
          onClose={() => setAction(null)}
          run={async (body) => {
            const r = await signed(() => unwrap(api.POST("/api/v1/fitness-assessments/{assessment_id}/transitions", { params: { path: { assessment_id: a.id } }, body })));
            warn(r.warnings);
            await refresh();
          }}
        />
      ) : null}
      {scan ? <ScanDialog a={a} onClose={() => setScan(false)} /> : null}
      {verify && a.provider ? <VerifyDialog a={a} onClose={() => setVerify(false)} /> : null}
    </div>
  );
}

function ActionDialog({ a, action, run, onClose }: { a: S["FitnessAssessmentRead"]; action: AAction; run: (b: S["FitnessAssessmentTransition"]) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  const [clinical, setClinical] = useState<"" | "yes" | "no">("");
  const min = action === "revoke" ? 20 : action === "return" ? 10 : action === "reject" ? 10 : 0;
  const review = action === "accept" || action === "reject";
  const needsClinical = review && a.source === "external_certificate";
  const disabled = reason.trim().length < min || (needsClinical && !clinical);
  return (
    <StepDialog
      title={te(`assessmentAction.${action}`)}
      description={t(`actionHint.${action}`)}
      confirmLabel={te(`assessmentAction.${action}`)}
      destructive={action === "reject" || action === "revoke"}
      disabled={disabled}
      testId="fa-confirm"
      onConfirm={() => run({ action, reason: reason.trim() || null, clinical_data_present: needsClinical ? clinical === "yes" : null })}
      onClose={onClose}
    >
      {needsClinical ? (
        <FormField id="fa-clinical" label={t("clinicalQuestion")} required hint={t("clinicalHint")}>
          <Select value={clinical} onChange={(e) => setClinical(e.target.value as "" | "yes" | "no")} data-testid="fa-clinical">
            <option value="">{tc("select")}</option>
            <option value="no">{tc("no")}</option>
            <option value="yes">{tc("yes")}</option>
          </Select>
        </FormField>
      ) : null}
      {min > 0 || action === "accept" ? (
        <FormField id="fa-reason" label={t("reason")} required={min > 0} hint={min ? t("reasonMin", { min, n: reason.trim().length }) : undefined}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="fa-reason" />
        </FormField>
      ) : null}
      {action === "sign" ? <p className="text-xs text-muted-foreground">{t("signNote")}</p> : null}
    </StepDialog>
  );
}

function ScanDialog({ a, onClose }: { a: S["FitnessAssessmentRead"]; onClose: () => void }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [reason, setReason] = useState<S["FitnessScanReason"] | "">("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState<S["SignedUrlRead"] | null>(null);
  const got = useRef<S["SignedUrlRead"] | null>(null);
  const { dateTime } = useFormatters(a.project_id);
  return (
    <StepDialog
      title={t("openScan")}
      description={t("scanReasonHint")}
      confirmLabel={url ? tc("close") : t("getLink")}
      disabled={!url && (!reason || (reason === "other" && text.trim().length < 5))}
      testId="scan-confirm"
      onConfirm={async () => {
        if (url) return;
        const r = await unwrap(api.POST("/api/v1/fitness-assessments/{assessment_id}/scan-url", { params: { path: { assessment_id: a.id } }, body: { reason: reason as S["FitnessScanReason"], reason_text: text.trim() || null } }));
        got.current = r;
      }}
      onClose={() => (got.current && !url ? setUrl(got.current) : onClose())}
    >
      {url ? (
        <Alert tone="success" data-testid="scan-link">
          <a href={url.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline">
            <ExternalLink aria-hidden className="size-4" />
            {t("scanLink")}
          </a>
          <span className="block text-xs">{t("expiresAt", { at: dateTime(url.expires_at) })}</span>
        </Alert>
      ) : (
        <>
          <FormField id="scan-reason" label={t("scanReason")} required>
            <Select value={reason} onChange={(e) => setReason(e.target.value as S["FitnessScanReason"])} data-testid="scan-reason">
              <option value="">{tc("select")}</option>
              {FITNESS_SCAN_REASONS.map((x) => (
                <option key={x} value={x}>
                  {te(`fitnessScanReason.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {reason === "other" ? (
            <FormField id="scan-text" label={t("reason")} required>
              <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} />
            </FormField>
          ) : null}
          <p className="text-xs text-muted-foreground">{t("scanAudited")}</p>
        </>
      )}
    </StepDialog>
  );
}

function Verifications({ a, projectId, canRecord, onRecord }: { a: S["FitnessAssessmentRead"]; projectId: string; canRecord: boolean; onRecord: () => void }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(projectId);
  const q = useFitnessVerifications(a.id);
  return (
    <Card className="mt-4" data-testid="fa-verifications">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("verifications")}</CardTitle>
        {canRecord ? (
          <Button size="sm" onClick={onRecord} data-testid="fa-verify">
            {t("recordVerification")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState rows={1} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data?.items.length ? (
          <ul className="flex flex-col gap-2 text-sm">
            {q.data.items.map((v) => (
              <li key={v.id} className="rounded-md border p-2" data-testid="fa-verification" data-outcome={v.outcome}>
                <span className="font-medium">{te(`fitnessVerifOutcome.${v.outcome}`)}</span> · {te(`fitnessVerifMethod.${v.method}`)} · <span className="ltr">{v.channel_used}</span>
                <span className="block text-xs text-muted-foreground">
                  {dateTime(v.performed_at)} · <UserName u={v.performed_by} /> · {v.reference} → {te(`verificationStatus.${v.verification_status_after}`)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noVerifications")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function VerifyDialog({ a, onClose }: { a: S["FitnessAssessmentRead"]; onClose: () => void }) {
  const t = useTranslations("medical.assessments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const [method, setMethod] = useState<S["FitnessVerificationMethod"]>("clinic_portal");
  const [channel, setChannel] = useState("");
  const [outcome, setOutcome] = useState<S["FitnessVerificationOutcome"] | "">("");
  const [reference, setReference] = useState("");
  return (
    <StepDialog
      title={t("recordVerification")}
      description={t("verifyHint")}
      confirmLabel={tc("save")}
      disabled={!channel.trim() || !outcome || !reference.trim()}
      testId="verify-confirm"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/fitness-assessments/{assessment_id}/verifications", { params: { path: { assessment_id: a.id } }, body: { method, channel_used: channel.trim(), outcome: outcome as S["FitnessVerificationOutcome"], reference: reference.trim() } }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="fv-method" label={t("method")} required>
        <Select value={method} onChange={(e) => setMethod(e.target.value as S["FitnessVerificationMethod"])} data-testid="fv-method">
          {FITNESS_VERIF_METHODS.map((x) => (
            <option key={x} value={x}>
              {te(`fitnessVerifMethod.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="fv-channel" label={t("channel")} required hint={t("channelHint")}>
        <Input value={channel} onChange={(e) => setChannel(e.target.value)} className="ltr" data-testid="fv-channel" />
      </FormField>
      <FormField id="fv-outcome" label={t("verifOutcome")} required>
        <Select value={outcome} onChange={(e) => setOutcome(e.target.value as S["FitnessVerificationOutcome"])} data-testid="fv-outcome">
          <option value="">{tc("select")}</option>
          {FITNESS_VERIF_OUTCOMES.map((x) => (
            <option key={x} value={x}>
              {te(`fitnessVerifOutcome.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="fv-ref" label={t("verifReference")} required>
        <Input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={120} data-testid="fv-ref" />
      </FormField>
    </StepDialog>
  );
}
