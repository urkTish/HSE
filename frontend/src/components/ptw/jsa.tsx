"use client";
import { GitBranch, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { StepDialog } from "@/components/access/common";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
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
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useJsa, useJsaRevisions, useJsaTemplates, usePtwRefresh, useRiskMatrix } from "@/lib/api/ptw";
import { can, canWrite } from "@/lib/permissions";
import { CONTROL_LEVELS, PERMIT_TYPES, PTW_HAZARDS } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { PermitNo, RiskBandBadge, TypeChips, userLabel } from "./common";
import { RiskMatrixView } from "./config";
import { useSigned } from "./signing";

type S = Schemas;
type Jsa = S["JsaRead"];
type Line = S["JsaHazardLineInput"];
type Step = { step_no: number; description_en: string; description_ar: string; hazards: Line[] };
const PAGE_SIZE = 50;
const HIGHER: S["ControlLevel"][] = ["elimination", "substitution", "engineering"];
const SCALE = [1, 2, 3, 4, 5];

/* ───────────── risk helpers ───────────── */

/** Band of L × S from the server's matrix (the single source of the band thresholds). */
function useBandOf() {
  const m = useRiskMatrix();
  return (l: number, s: number): S["RiskBand"] | null => m.data?.cells.find((c) => c.likelihood === l && c.severity === s)?.band ?? null;
}

const RANK: Record<S["RiskBand"], number> = { low: 0, medium: 1, high: 2, extreme: 3 };

/** Client-side checks that mirror JS-5 / JS-6 / JS-8 so the author sees problems while typing; the server decides. */
function lineIssues(l: Line, band: (l: number, s: number) => S["RiskBand"] | null): { error: string[]; warn: string[] } {
  const error: string[] = [];
  const warn: string[] = [];
  if (l.residual_l > l.initial_l || l.residual_s > l.initial_s) error.push("residualAboveInitial");
  const ib = band(l.initial_l, l.initial_s);
  const rb = band(l.residual_l, l.residual_s);
  if (rb === "extreme") error.push("residualExtreme");
  const ppeOnly = l.controls.length > 0 && l.controls.every((c) => c.level === "ppe");
  if (ppeOnly && ib && rb && RANK[rb] < RANK[ib]) error.push("ppeOnly");
  if (l.residual_s < l.initial_s && !l.controls.some((c) => HIGHER.includes(c.level))) warn.push("severityReduced");
  if (rb === "high" && !l.controls.some((c) => HIGHER.includes(c.level))) error.push("higherControl");
  if (!l.controls.length) error.push("noControls");
  return { error, warn };
}

function toSteps(j: Jsa | null): Step[] {
  if (!j || !j.steps.length) return [{ step_no: 1, description_en: "", description_ar: "", hazards: [] }];
  return j.steps.map((s) => ({
    step_no: s.step_no,
    description_en: s.description_en,
    description_ar: s.description_ar ?? "",
    hazards: s.hazards.map((h) => ({ hazard_code: h.hazard_code, description: h.description, initial_l: h.initial_l, initial_s: h.initial_s, controls: h.controls.map((c) => ({ ...c })), residual_l: h.residual_l, residual_s: h.residual_s })),
  }));
}

function stepsBody(steps: Step[]): S["JsaStepInput"][] {
  return steps.map((s, i) => ({ step_no: i + 1, description_en: s.description_en.trim(), description_ar: s.description_ar.trim() || null, hazards: s.hazards.map((h) => ({ ...h, description: h.description.trim(), controls: h.controls.filter((c) => c.text.trim()).map((c) => ({ text: c.text.trim(), level: c.level })) })) }));
}

/* ───────────── template library ───────────── */

export function JsaTemplatesPage() {
  return <ProjectGate>{(p) => <TemplateList project={p} />}</ProjectGate>;
}

function TemplateList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const types = s.getAll("work_type") as S["PermitType"][];
  const status = s.getAll("status") as S["JsaStatus"][];
  const q = useJsaTemplates(project.id, {
    work_type: types.length ? types : null,
    status: status.length ? status : null,
    engagement_id: s.get("engagement_id") || null,
    review_due: s.getBool("review_due") ?? null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("templates")}
        description={t("templatesHint")}
        actions={
          canWrite(me, "jsa_template.manage", project.id) ? (
            <Button asChild>
              <Link href="/jsa-templates/new" data-testid="new-jsa-template">
                <Plus aria-hidden />
                {t("newTemplate")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <SearchFilter id="jt-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="jt-type" label={t("workTypes")} options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))} value={types} onChange={(v) => s.set({ work_type: v })} />
        <MultiSelect id="jt-status" label={tc("status")} options={(["draft", "submitted", "approved", "review_due", "superseded"] as const).map((x) => ({ value: x, label: te(`jsaStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="jt-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((e) => ({ value: e.value, label: e.label }))} />
        <SelectFilter id="jt-due" label={t("reviewDue")} value={s.get("review_due") === "true" ? "true" : ""} onChange={(v) => s.set({ review_due: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="jsa-templates-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("titleCol")}</TH>
                <TH>{t("workTypes")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("residual")}</TH>
                <TH>{t("reviewDueOn")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((j) => (
                <TR key={j.id} data-testid="jsa-template-row" data-jsa-no={j.jsa_no}>
                  <TD label={t("no")}>
                    <Link href={`/jsas/${j.id}`} className="ltr font-medium text-primary hover:underline">
                      {j.jsa_no}
                    </Link>
                    {j.revision ? <span className="ms-1 text-xs text-muted-foreground">r{j.revision}</span> : null}
                  </TD>
                  <TD label={t("titleCol")}>{locale === "ar" && j.title_ar ? j.title_ar : j.title_en}</TD>
                  <TD label={t("workTypes")}>
                    <TypeChips types={j.work_types} short />
                  </TD>
                  <TD label={tc("contractor")}>{j.engagement?.short_code ?? t("projectWide")}</TD>
                  <TD label={t("residual")}>{j.governing_residual_band ? <RiskBandBadge band={j.governing_residual_band} /> : "—"}</TD>
                  <TD label={t("reviewDueOn")}>
                    <span className="ltr">{j.review_due_on ? date(j.review_due_on) : "—"}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={j.status} label={te(`jsaStatus.${j.status}`)} />
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

export function JsaTemplateCreatePage() {
  return <ProjectGate>{(p) => <TemplateCreate project={p} />}</ProjectGate>;
}

function TemplateCreate({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("jsa");
  const tc = useTranslations("common");
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const [eng, setEng] = useState("");
  const [types, setTypes] = useState<S["PermitType"][]>([]);
  const [titleEn, setTitleEn] = useState("");
  const [titleAr, setTitleAr] = useState("");
  const [steps, setSteps] = useState<Step[]>(toSteps(null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const j = await unwrap(
        api.POST("/api/v1/projects/{project_id}/jsa-templates", {
          params: { path: { project_id: project.id } },
          body: { engagement_id: eng || null, work_types: types, title_en: titleEn.trim(), title_ar: titleAr.trim() || null, steps: stepsBody(steps) },
        }),
      );
      toast.success(t("createdToast", { no: j.jsa_no }));
      router.push(`/jsas/${j.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("templates"), href: "/jsa-templates" }, { label: t("newTemplate") }]} />
        <PageHeader title={t("newTemplate")} description={t("newTemplateHint")} />
      </div>
      <FormSection title={t("about")}>
        <FormField id="jt-title-en" label={t("titleEn")} required>
          <Input id="jt-title-en" value={titleEn} maxLength={150} onChange={(e) => setTitleEn(e.target.value)} />
        </FormField>
        <FormField id="jt-title-ar" label={t("titleAr")}>
          <Input id="jt-title-ar" dir="rtl" value={titleAr} maxLength={150} onChange={(e) => setTitleAr(e.target.value)} />
        </FormField>
        <FormField id="jt-eng" label={t("owner")} hint={t("ownerHint")}>
          <Select id="jt-eng" value={eng} onChange={(e) => setEng(e.target.value)}>
            <option value="">{t("projectWide")}</option>
            {opts.engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <WorkTypesField value={types} onChange={setTypes} />
      </FormSection>
      <JsaStepsEditor steps={steps} onChange={setSteps} />
      <MutationError error={error} />
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={busy || !titleEn.trim() || !types.length} data-testid="save-jsa">
          {busy ? tc("saving") : t("createDraft")}
        </Button>
      </div>
    </div>
  );
}

function WorkTypesField({ value, onChange }: { value: S["PermitType"][]; onChange: (v: S["PermitType"][]) => void }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  return (
    <CheckboxGroup
      id="jsa-types"
      legend={t("workTypes")}
      options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))}
      value={value}
      onChange={(v) => onChange(v as S["PermitType"][])}
      className="sm:col-span-2"
    />
  );
}

/* ───────────── steps editor with the 5×5 preview ───────────── */

export function JsaStepsEditor({ steps, onChange }: { steps: Step[]; onChange: (s: Step[]) => void }) {
  const t = useTranslations("jsa");
  const band = useBandOf();
  const highlight = useMemo(() => steps.flatMap((s) => s.hazards.map((h) => ({ l: h.residual_l, s: h.residual_s }))), [steps]);
  const set = (i: number, p: Partial<Step>) => onChange(steps.map((s, k) => (k === i ? { ...s, ...p } : s)));
  const setLine = (i: number, j: number, p: Partial<Line>) => set(i, { hazards: (steps[i]?.hazards ?? []).map((h, k) => (k === j ? { ...h, ...p } : h)) });
  const governing = steps
    .flatMap((s) => s.hazards)
    .map((h) => band(h.residual_l, h.residual_s))
    .reduce<S["RiskBand"] | null>((a, b) => (b && (!a || RANK[b] > RANK[a]) ? b : a), null);
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="flex flex-col gap-4" data-testid="jsa-steps-editor">
        {steps.map((s, i) => (
          <Card key={i} data-testid="jsa-step">
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">{t("stepN", { n: i + 1 })}</CardTitle>
              {steps.length > 1 ? (
                <Button size="sm" variant="ghost" onClick={() => onChange(steps.filter((_, k) => k !== i))} aria-label={t("removeStep")}>
                  <Trash2 aria-hidden />
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField id={`st-${i}-en`} label={t("stepEn")} required>
                  <Textarea id={`st-${i}-en`} rows={2} value={s.description_en} onChange={(e) => set(i, { description_en: e.target.value })} />
                </FormField>
                <FormField id={`st-${i}-ar`} label={t("stepAr")}>
                  <Textarea id={`st-${i}-ar`} dir="rtl" rows={2} value={s.description_ar} onChange={(e) => set(i, { description_ar: e.target.value })} />
                </FormField>
              </div>
              {s.hazards.map((h, j) => (
                <LineEditor key={j} id={`l-${i}-${j}`} line={h} onChange={(p) => setLine(i, j, p)} onRemove={() => set(i, { hazards: s.hazards.filter((_, k) => k !== j) })} />
              ))}
              <div>
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="add-hazard"
                  onClick={() => set(i, { hazards: [...s.hazards, { hazard_code: "fall_from_height", description: "", initial_l: 3, initial_s: 3, controls: [{ text: "", level: "engineering" }], residual_l: 2, residual_s: 3 }] })}
                >
                  <Plus aria-hidden />
                  {t("addHazard")}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        <div>
          <Button variant="outline" onClick={() => onChange([...steps, { step_no: steps.length + 1, description_en: "", description_ar: "", hazards: [] }])} data-testid="add-step">
            <Plus aria-hidden />
            {t("addStep")}
          </Button>
        </div>
      </div>
      <aside className="flex flex-col gap-2 lg:sticky lg:top-4 lg:self-start">
        <p className="text-sm font-medium">
          {t("governing")}: {governing ? <RiskBandBadge band={governing} /> : "—"}
        </p>
        <p className="text-xs text-muted-foreground">{t("matrixHint")}</p>
        <RiskMatrixView highlight={highlight} compact />
      </aside>
    </div>
  );
}

function ScorePick({ id, label, l, s, onChange }: { id: string; label: string; l: number; s: number; onChange: (l: number, s: number) => void }) {
  const band = useBandOf();
  const b = band(l, s);
  return (
    <fieldset className="flex flex-wrap items-end gap-2 rounded-md border p-2">
      <legend className="px-1 text-xs font-medium">{label}</legend>
      <FormField id={`${id}-l`} label="L">
        <Select id={`${id}-l`} className="w-16" value={String(l)} onChange={(e) => onChange(Number(e.target.value), s)} data-testid={`${id}-l`}>
          {SCALE.map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id={`${id}-s`} label="S">
        <Select id={`${id}-s`} className="w-16" value={String(s)} onChange={(e) => onChange(l, Number(e.target.value))} data-testid={`${id}-s`}>
          {SCALE.map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </Select>
      </FormField>
      <span className="pb-2" data-testid={`${id}-score`} data-band={b ?? undefined}>
        <RiskBandBadge band={b} score={l * s} />
      </span>
    </fieldset>
  );
}

function LineEditor({ id, line, onChange, onRemove }: { id: string; line: Line; onChange: (p: Partial<Line>) => void; onRemove: () => void }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const band = useBandOf();
  const issues = lineIssues(line, band);
  const setCtl = (k: number, p: Partial<S["JsaControlInput"]>) => onChange({ controls: line.controls.map((c, i) => (i === k ? { ...c, ...p } : c)) });
  return (
    <div className="flex flex-col gap-3 rounded-md border bg-surface p-3" data-testid="jsa-line-editor">
      <div className="grid gap-3 sm:grid-cols-[14rem_1fr_auto]">
        <FormField id={`${id}-hz`} label={t("hazard")} required>
          <Select id={`${id}-hz`} value={line.hazard_code} onChange={(e) => onChange({ hazard_code: e.target.value as S["Hazard"] })} data-testid="line-hazard">
            {PTW_HAZARDS.map((h) => (
              <option key={h} value={h}>
                {te(`hazard.${h}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`${id}-desc`} label={t("hazardDesc")} required>
          <Input id={`${id}-desc`} value={line.description} onChange={(e) => onChange({ description: e.target.value })} />
        </FormField>
        <div className="flex items-end">
          <Button size="sm" variant="ghost" onClick={onRemove} aria-label={t("removeHazard")}>
            <Trash2 aria-hidden />
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        <ScorePick id={`${id}-init`} label={t("initial")} l={line.initial_l} s={line.initial_s} onChange={(l, s) => onChange({ initial_l: l, initial_s: s })} />
        <ScorePick id={`${id}-res`} label={t("residualRisk")} l={line.residual_l} s={line.residual_s} onChange={(l, s) => onChange({ residual_l: l, residual_s: s })} />
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium">{t("controls")}</p>
        {line.controls.map((c, k) => (
          <div key={k} className="flex flex-wrap gap-2 sm:flex-nowrap">
            <Select aria-label={t("controlLevel")} className="sm:w-44" value={c.level} onChange={(e) => setCtl(k, { level: e.target.value as S["ControlLevel"] })} data-testid="control-level">
              {CONTROL_LEVELS.map((x) => (
                <option key={x} value={x}>
                  {te(`controlLevel.${x}`)}
                </option>
              ))}
            </Select>
            <Input aria-label={t("controlText")} value={c.text} onChange={(e) => setCtl(k, { text: e.target.value })} data-testid="control-text" />
            <Button size="sm" variant="ghost" onClick={() => onChange({ controls: line.controls.filter((_, i) => i !== k) })} aria-label={t("removeControl")}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <div>
          <Button size="sm" variant="outline" onClick={() => onChange({ controls: [...line.controls, { text: "", level: "administrative" }] })} data-testid="add-control">
            <Plus aria-hidden />
            {t("addControl")}
          </Button>
        </div>
      </div>
      {issues.error.length || issues.warn.length ? (
        <ul className="flex flex-col gap-1 text-xs" data-testid="line-issues">
          {issues.error.map((k) => (
            <li key={k} className="text-danger" data-issue={k}>
              {t(`issue.${k as "ppeOnly"}`)}
            </li>
          ))}
          {issues.warn.map((k) => (
            <li key={k} className="text-warning" data-issue={k}>
              {t(`issue.${k as "ppeOnly"}`)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ───────────── JSA page (template or permit instance) ───────────── */

type JStep = "submit" | "approve" | "return" | "accept" | "revise";

export function JsaDetail({ id }: { id: string }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const q = useJsa(id);
  const [editing, setEditing] = useState(false);
  const [step, setStep] = useState<JStep | null>(null);
  const { date, dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const j = q.data;
  const pid = j.project_id;
  const author = j.is_template ? canWrite(me, "jsa_template.manage", pid) : canWrite(me, "permit.prepare", pid);
  const approver = j.is_template ? canWrite(me, "jsa_template.manage", pid) : canWrite(me, "permit.issue", pid);
  const acceptor = canWrite(me, "permit.receive", pid) || canWrite(me, "permit.issue", pid) || canWrite(me, "permit.hse_review", pid);
  const steps: { k: JStep; show: boolean; tone: "default" | "outline" }[] = [
    { k: "submit", show: j.status === "draft" && author, tone: "default" },
    { k: "accept", show: !j.is_template && j.status === "submitted" && j.required_acceptances.length > 0 && acceptor, tone: "default" },
    { k: "approve", show: j.status === "submitted" && approver, tone: "default" },
    { k: "return", show: j.status === "submitted" && approver, tone: "outline" },
    { k: "revise", show: (j.status === "approved" || j.status === "review_due") && (author || approver), tone: "outline" },
  ];
  const highlight = j.steps.flatMap((s) => s.hazards.map((h) => ({ l: h.residual_l, s: h.residual_s })));
  return (
    <div className="flex flex-col gap-5" data-testid="jsa-detail" data-status={j.status}>
      <div>
        <Breadcrumbs
          items={
            j.is_template
              ? [{ label: t("templates"), href: "/jsa-templates" }, { label: j.jsa_no }]
              : [{ label: t("permits"), href: "/permits" }, ...(j.permit ? [{ label: j.permit.display_no, href: `/permits/${j.permit.id}?tab=jsa` }] : []), { label: j.jsa_no }]
          }
        />
        <PageHeader
          title={
            <span>
              <bdi className="ltr">{j.jsa_no}</bdi>
              {j.revision ? <span className="ms-2 text-base text-muted-foreground">r{j.revision}</span> : null}
            </span>
          }
          description={locale === "ar" && j.title_ar ? j.title_ar : j.title_en}
          actions={
            <span data-testid="jsa-status" data-status={j.status}>
              <StatusBadge status={j.status} label={te(`jsaStatus.${j.status}`)} />
            </span>
          }
        />
      </div>
      {steps.some((x) => x.show) || (j.status === "draft" && author && !editing) ? (
        <div className="flex flex-wrap gap-2" data-testid="jsa-actions">
          {j.status === "draft" && author && !editing ? (
            <Button variant="outline" onClick={() => setEditing(true)} data-testid="edit-jsa">
              {tc("edit")}
            </Button>
          ) : null}
          {steps
            .filter((x) => x.show)
            .map((x) => (
              <Button key={x.k} variant={x.tone} onClick={() => setStep(x.k)} data-testid={`jsa-${x.k}`}>
                {x.k === "revise" ? <GitBranch aria-hidden /> : null}
                {t(`step.${x.k}`)}
              </Button>
            ))}
        </div>
      ) : null}
      {j.returned_comment && j.status === "draft" ? (
        <Alert tone="warning" data-testid="jsa-returned">
          {t("returnedWith", { comment: j.returned_comment })}
        </Alert>
      ) : null}
      {j.status === "review_due" ? <Alert tone="warning">{t("reviewDueHint")}</Alert> : null}
      {j.missing_mandatory_hazards.length ? (
        <Alert tone="danger" data-testid="missing-hazards">
          {t("missingHazards", { list: j.missing_mandatory_hazards.map((h) => te(`hazard.${h}`)).join(", ") })}
        </Alert>
      ) : null}

      <Card>
        <CardContent className="pt-5">
          <FieldList>
            {j.permit ? (
              <FieldItem label={t("permit")}>
                <PermitNo p={j.permit} />
              </FieldItem>
            ) : null}
            {j.template ? (
              <FieldItem label={t("fromTemplate")}>
                <Link href={`/jsas/${j.template.id}`} className="ltr text-primary hover:underline">
                  {j.template.jsa_no}
                </Link>
              </FieldItem>
            ) : null}
            <FieldItem label={t("workTypes")}>
              <TypeChips types={j.work_types} />
            </FieldItem>
            {j.is_template ? <FieldItem label={t("owner")}>{j.engagement?.short_code ?? t("projectWide")}</FieldItem> : null}
            <FieldItem label={t("governing")}>
              <span data-testid="governing-band" data-band={j.governing_residual_band ?? undefined}>
                {j.governing_residual_band ? <RiskBandBadge band={j.governing_residual_band} score={j.max_residual_score} /> : "—"}
              </span>
            </FieldItem>
            <FieldItem label={t("maxInitial")}>
              <bdi className="ltr tabular-nums">{j.max_initial_score ?? "—"}</bdi>
            </FieldItem>
            <FieldItem label={t("mandatory")}>{j.mandatory_hazards.length ? j.mandatory_hazards.map((h) => te(`hazard.${h}`)).join(", ") : "—"}</FieldItem>
            {j.is_template ? (
              <FieldItem label={t("reviewDueOn")}>
                <span className="ltr">{j.review_due_on ? date(j.review_due_on) : "—"}</span>
              </FieldItem>
            ) : null}
            {j.approved_by ? (
              <FieldItem label={t("approvedBy")}>
                {userLabel(j.approved_by, locale)} · <span className="ltr">{j.approved_at ? dateTime(j.approved_at) : ""}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>

      {editing ? (
        <JsaEdit j={j} onDone={() => setEditing(false)} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
          <JsaStepsView j={j} />
          <aside className="flex flex-col gap-2 lg:sticky lg:top-4 lg:self-start">
            <p className="text-xs text-muted-foreground">{t("matrixHint")}</p>
            <RiskMatrixView highlight={highlight} compact />
          </aside>
        </div>
      )}

      {!j.is_template ? <Acceptances j={j} /> : null}
      {!j.is_template && j.crew_briefings.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("briefings")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y rounded-md border text-sm">
              {j.crew_briefings.map((b, i) => (
                <li key={i} className="p-2">
                  {t("briefingLine", { shift: b.shift_no, n: b.worker_count, name: userLabel(b.briefed_by, locale) })} · <span className="[unicode-bidi:isolate]">{dateTime(b.at)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <Revisions id={j.id} projectId={pid} />
      <HistoryPanel entityType="jsa" entityId={j.id} projectId={pid} />
      {step ? <JsaStepDialog j={j} step={step} onClose={() => setStep(null)} /> : null}
    </div>
  );
}

function JsaStepsView({ j }: { j: Jsa }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const locale = useLocale();
  return (
    <div className="flex flex-col gap-4" data-testid="jsa-steps">
      {j.steps.map((s) => (
        <Card key={s.step_no}>
          <CardHeader>
            <CardTitle className="text-base">
              {t("stepN", { n: s.step_no })} · <span className="font-normal">{locale === "ar" && s.description_ar ? s.description_ar : s.description_en}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {s.hazards.length === 0 ? <p className="text-sm text-muted-foreground">{t("noHazards")}</p> : null}
            {s.hazards.map((h) => (
              <div key={h.id} className="flex flex-col gap-2 rounded-md border p-3 text-sm" data-testid="jsa-line" data-hazard={h.hazard_code} data-residual-band={h.residual_band}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{te(`hazard.${h.hazard_code}`)}</span>
                  <span className="text-muted-foreground">{h.description}</span>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <span className="inline-flex items-center gap-1">
                    {t("initial")} <bdi className="ltr tabular-nums">{h.initial_l}×{h.initial_s}</bdi> <RiskBandBadge band={h.initial_band} score={h.initial_score} />
                  </span>
                  <span aria-hidden>→</span>
                  <span className="inline-flex items-center gap-1" data-testid="line-residual">
                    {t("residualRisk")} <bdi className="ltr tabular-nums">{h.residual_l}×{h.residual_s}</bdi> <RiskBandBadge band={h.residual_band} score={h.residual_score} />
                  </span>
                </div>
                <ul className="flex flex-col gap-0.5">
                  {h.controls.map((c, i) => (
                    <li key={i} className="flex gap-2">
                      <span className={cn("shrink-0 rounded px-1.5 text-xs", HIGHER.includes(c.level) ? "bg-success-bg text-success" : "bg-muted text-muted-foreground")}>{te(`controlLevel.${c.level}`)}</span>
                      <span>{c.text}</span>
                    </li>
                  ))}
                </ul>
                {h.warnings.length ? (
                  <ul className="text-xs text-warning" data-testid="line-warnings">
                    {h.warnings.map((w) => (
                      <li key={w} data-code={w}>
                        {te(`jsaWarning.${w}`)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function JsaEdit({ j, onDone }: { j: Jsa; onDone: () => void }) {
  const t = useTranslations("jsa");
  const tc = useTranslations("common");
  const refresh = usePtwRefresh();
  const [titleEn, setTitleEn] = useState(j.title_en);
  const [titleAr, setTitleAr] = useState(j.title_ar ?? "");
  const [types, setTypes] = useState<S["PermitType"][]>(j.work_types);
  const [steps, setSteps] = useState<Step[]>(() => toSteps(j));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.PATCH("/api/v1/jsas/{jsa_id}", { params: { path: { jsa_id: j.id } }, body: { title_en: titleEn.trim(), title_ar: titleAr.trim() || null, work_types: types, steps: stepsBody(steps) } }));
      await refresh();
      toast.success(tc("saved"));
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <FormSection title={t("about")}>
        <FormField id="je-title-en" label={t("titleEn")} required>
          <Input id="je-title-en" value={titleEn} maxLength={150} onChange={(e) => setTitleEn(e.target.value)} />
        </FormField>
        <FormField id="je-title-ar" label={t("titleAr")}>
          <Input id="je-title-ar" dir="rtl" value={titleAr} maxLength={150} onChange={(e) => setTitleAr(e.target.value)} />
        </FormField>
        <WorkTypesField value={types} onChange={setTypes} />
      </FormSection>
      <JsaStepsEditor steps={steps} onChange={setSteps} />
      <MutationError error={error} />
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onDone}>
          {tc("cancel")}
        </Button>
        <Button onClick={() => void save()} disabled={busy || !titleEn.trim() || !types.length} data-testid="save-jsa">
          {busy ? tc("saving") : tc("save")}
        </Button>
      </div>
    </div>
  );
}

function Acceptances({ j }: { j: Jsa }) {
  const t = useTranslations("jsa");
  const locale = useLocale();
  const { dateTime } = useFormatters(j.project_id);
  return (
    <Card data-testid="residual-acceptances">
      <CardHeader>
        <CardTitle className="text-base">{t("acceptances")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {j.governing_residual_band ? <p className="text-muted-foreground">{t(`acceptRule.${j.governing_residual_band}`)}</p> : null}
        {j.residual_acceptances.length ? (
          <ul className="flex flex-col divide-y rounded-md border">
            {j.residual_acceptances.map((a, i) => (
              <li key={i} className="flex flex-col gap-0.5 p-2" data-testid="acceptance">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{userLabel(a.accepted_by, locale)}</span>
                  <span className="text-xs text-muted-foreground">{a.accepted_as}</span>
                  <RiskBandBadge band={a.band} />
                  <span className="[unicode-bidi:isolate] text-xs text-muted-foreground">{dateTime(a.accepted_at)}</span>
                </span>
                {a.alarp_justification ? <span className="text-xs">{t("alarp")}: {a.alarp_justification}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">{t("noAcceptances")}</p>
        )}
        {j.required_acceptances.length ? (
          <p className="text-warning" data-testid="acceptances-needed">
            {t("stillNeeded", { list: j.required_acceptances.map((r) => (["receiver", "issuer", "hse"].includes(r) ? t(`who.${r as "hse"}`) : r)).join(", ") })}
          </p>
        ) : j.governing_residual_band ? (
          <p className="text-success">{t("acceptanceComplete")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function JsaStepDialog({ j, step, onClose }: { j: Jsa; step: JStep; onClose: () => void }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const refresh = usePtwRefresh();
  const router = useRouter();
  const signed = useSigned();
  const [comment, setComment] = useState("");
  const [alarp, setAlarp] = useState("");
  const path = { params: { path: { jsa_id: j.id } } };
  const high = j.governing_residual_band === "high";
  let disabled = false;
  let body: React.ReactNode = null;
  let run: () => Promise<unknown>;
  const transition = (to: S["JsaStatus"]) => async () => {
    await signed(() => unwrap(api.POST("/api/v1/jsas/{jsa_id}/transitions", { ...path, body: { to_status: to, comment: comment.trim() || null } })));
    await refresh();
    toast.success(te(`jsaStatus.${to}`));
  };
  switch (step) {
    case "submit":
      run = transition("submitted");
      body = <p className="text-sm">{t("submitHint")}</p>;
      break;
    case "approve":
      run = transition("approved");
      body = <p className="text-sm">{j.is_template ? t("approveTemplateHint") : t("approveHint")}</p>;
      break;
    case "return":
      disabled = comment.trim().length < 10;
      run = transition("draft");
      body = (
        <FormField id="jsa-comment" label={t("returnComment")} required hint={t("min10")}>
          <Textarea id="jsa-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
        </FormField>
      );
      break;
    case "accept":
      disabled = high && alarp.trim().length < 30;
      run = async () => {
        await signed(() => unwrap(api.POST("/api/v1/jsas/{jsa_id}/residual-acceptances", { ...path, body: { alarp_justification: alarp.trim() || null } })));
        await refresh();
        toast.success(t("acceptedToast"));
      };
      body = (
        <>
          <p className="text-sm">
            {t("acceptBody")} {j.governing_residual_band ? <RiskBandBadge band={j.governing_residual_band} /> : null}
          </p>
          <FormField id="jsa-alarp" label={t("alarp")} required={high} hint={high ? t("alarpHint") : t("optional")}>
            <Textarea id="jsa-alarp" value={alarp} onChange={(e) => setAlarp(e.target.value)} data-testid="alarp" />
          </FormField>
        </>
      );
      break;
    case "revise":
      run = async () => {
        const n = await unwrap(api.POST("/api/v1/jsas/{jsa_id}/revisions", path));
        await refresh();
        toast.success(t("revisedToast", { no: n.jsa_no }));
        router.push(`/jsas/${n.id}`);
      };
      body = <p className="text-sm">{j.is_template ? t("reviseTemplateHint") : t("reviseHint")}</p>;
      break;
  }
  return (
    <StepDialog title={t(`stepTitle.${step}`)} confirmLabel={t(`step.${step}`)} disabled={disabled} onConfirm={run} onClose={onClose} testId="jsa-step-confirm">
      {body}
    </StepDialog>
  );
}

function Revisions({ id, projectId }: { id: string; projectId: string }) {
  const t = useTranslations("jsa");
  const te = useTranslations("enums");
  const q = useJsaRevisions(id);
  const { dateTime } = useFormatters(projectId);
  const items = q.data ?? [];
  if (items.length < 2) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("revisions")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y rounded-md border text-sm">
          {items.map((r) => (
            <li key={r.id} className={cn("flex flex-wrap items-center gap-2 p-2", r.id === id && "bg-muted")}>
              <Link href={`/jsas/${r.id}`} className="ltr font-medium text-primary hover:underline">
                {r.jsa_no} r{r.revision}
              </Link>
              <StatusBadge status={r.status} label={te(`jsaStatus.${r.status}`)} />
              <span className="[unicode-bidi:isolate] text-xs text-muted-foreground">{dateTime(r.updated_at)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/* ───────────── create the permit's JSA ───────────── */

export function CreatePermitJsa({ permit }: { permit: S["PermitRead"] }) {
  const t = useTranslations("jsa");
  const me = useMeData();
  const router = useRouter();
  const refresh = usePtwRefresh();
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const [tpl, setTpl] = useState("");
  const tq = useJsaTemplates(permit.project_id, { work_type: permit.work_types, status: ["approved"], page_size: 100 }, { enabled: open });
  if (!(permit.status === "draft" && can(me, "permit.prepare", permit.project_id))) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)} data-testid="create-jsa">
        <Plus aria-hidden />
        {t("createForPermit")}
      </Button>
      {open ? (
        <StepDialog
          title={t("createForPermit")}
          description={t("createForPermitHint")}
          confirmLabel={t("create")}
          onClose={() => setOpen(false)}
          testId="create-jsa-confirm"
          onConfirm={async () => {
            const j = await unwrap(
              api.POST("/api/v1/permits/{permit_id}/jsa", {
                params: { path: { permit_id: permit.id } },
                body: tpl ? { template_id: tpl } : { work_types: permit.work_types, title_en: permit.title },
              }),
            );
            await refresh();
            router.push(`/jsas/${j.id}`);
          }}
        >
          <FormField id="cj-tpl" label={t("template")}>
            <Select id="cj-tpl" value={tpl} onChange={(e) => setTpl(e.target.value)}>
              <option value="">{t("blank")}</option>
              {(tq.data?.items ?? []).map((x) => (
                <option key={x.id} value={x.id}>
                  {x.jsa_no} · {locale === "ar" && x.title_ar ? x.title_ar : x.title_en}
                </option>
              ))}
            </Select>
          </FormField>
        </StepDialog>
      ) : null}
    </>
  );
}
