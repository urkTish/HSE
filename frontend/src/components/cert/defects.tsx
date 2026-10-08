"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Wrench } from "lucide-react";
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
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, DaysLeft, StepDialog, WorkerLabel } from "@/components/access/common";
import { DateTimeInput } from "@/components/ptw/common";
import { useProject } from "@/lib/api/queries";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, useDefect, useDefects, useEquipment, useIncidentDefectPrompt, useScaffolds } from "@/lib/api/cert";
import { DEFECT_CATEGORIES, DEFECT_CLOSURE_METHODS, DEFECT_SOURCES, DEFECT_STATUSES, EQUIPMENT_CERT_CATEGORIES } from "@/lib/cert-enums";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { EquipmentPicker } from "./deployments";
import { DefectCategoryBadge, EquipmentLabel, EquipmentSubNav, Tick, UserName } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

export function DefectStatusBadge({ status }: { status: S["DefectStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="defect-status" data-status={status}>
      <StatusBadge status={status} label={te(`defectStatus.${status}`)} />
    </span>
  );
}

/* ───────────── list ───────────── */

export function DefectListPage() {
  return <ProjectGate>{(p) => <DefectList project={p} />}</ProjectGate>;
}

function DefectList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("defects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["DefectStatus"][];
  const cat = s.getAll("category") as S["DefectCategory"][];
  const ecat = s.getAll("equipment_category") as S["EquipmentCertCategory"][];
  const [create, setCreate] = useState(false);
  const q = useDefects(project.id, {
    status: status.length ? status : null,
    category: cat.length ? cat : null,
    source: (s.get("source") as S["DefectSource"]) ? [s.get("source") as S["DefectSource"]] : null,
    equipment_category: ecat.length ? ecat : null,
    equipment_id: s.get("equipment_id") || null,
    scaffold_id: s.get("scaffold_id") || null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    overdue: s.get("overdue") === "1" ? true : null,
    due_within_days: s.getInt("due", 0) || null,
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
          canWrite(me, "defect.raise", project.id) ? (
            <Button onClick={() => setCreate(true)} data-testid="new-defect">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EquipmentSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="equipment_defects" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="df-status" label={tc("status")} options={DEFECT_STATUSES.map((x) => ({ value: x, label: te(`defectStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="df-cat" label={t("category")} options={DEFECT_CATEGORIES.map((x) => ({ value: x, label: te(`defectCategory.${x}`) }))} value={cat} onChange={(v) => s.set({ category: v })} />
        <MultiSelect id="df-ecat" label={t("equipmentCategory")} options={EQUIPMENT_CERT_CATEGORIES.map((x) => ({ value: x, label: te(`eqc.${x}`) }))} value={ecat} onChange={(v) => s.set({ equipment_category: v })} />
        <SelectFilter id="df-source" label={t("source")} value={s.get("source") ?? ""} onChange={(v) => s.set({ source: v })} options={DEFECT_SOURCES.map((x) => ({ value: x, label: te(`defectSource.${x}`) }))} />
        <SelectFilter id="df-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="df-overdue" label={t("overdue")} value={s.get("overdue") ?? ""} onChange={(v) => s.set({ overdue: v })} options={[{ value: "1", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="defects-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("subject")}</TH>
                <TH>{t("category")}</TH>
                <TH>{t("description")}</TH>
                <TH>{t("due")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => (
                <TR key={d.id} data-testid="defect-row" data-no={d.defect_no}>
                  <TD label={t("no")}>
                    <Link href={`/defects/${d.id}`} className="font-medium text-primary hover:underline">
                      <Code>{d.defect_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">{te(`defectSource.${d.source}`)}</span>
                  </TD>
                  <TD label={t("subject")}>
                    {d.tag ? <Code className="font-medium">{d.tag}</Code> : null}
                    {d.equipment ? <span className="block text-xs text-muted-foreground">{te(`eqc.${d.equipment.category}`)}</span> : null}
                    {d.scaffold ? <span className="block text-xs text-muted-foreground">{t("scaffold")}</span> : null}
                  </TD>
                  <TD label={t("category")}>
                    <DefectCategoryBadge category={d.category} />
                  </TD>
                  <TD label={t("description")}>
                    <span className="line-clamp-2 text-sm">{d.description_en}</span>
                  </TD>
                  <TD label={t("due")}>
                    {d.due_date ? date(d.due_date) : "—"} {d.status === "open" || d.status === "rectified" ? <DaysLeft days={d.days_left} /> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <DefectStatusBadge status={d.status} />
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
      {create ? <DefectDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/** Raise a defect on an item or a scaffold. Category A takes it out of service at once (DF-3). */
export function DefectDialog({ project, equipment, scaffoldId, source: initialSource, sourceRef, onClose }: { project: S["ProjectRead"]; equipment?: S["EquipmentListItem"] | null; scaffoldId?: string; source?: S["DefectSource"]; sourceRef?: string; onClose: () => void }) {
  const t = useTranslations("defects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const scaffolds = useScaffolds(project.id, { page_size: 200 });
  const [kind, setKind] = useState<"equipment" | "scaffold">(scaffoldId ? "scaffold" : "equipment");
  const [eq, setEq] = useState<S["EquipmentListItem"] | null>(equipment ?? null);
  const [sc, setSc] = useState(scaffoldId ?? "");
  const [source, setSource] = useState<S["DefectSource"]>(initialSource ?? "site_inspection");
  const [cat, setCat] = useState<S["DefectCategory"]>("B");
  const [desc, setDesc] = useState("");
  const [tpiDue, setTpiDue] = useState("");
  const [physical, setPhysical] = useState(false);
  const valid = desc.trim().length >= 5 && (kind === "equipment" ? eq : sc);
  async function save() {
    const r = await unwrap(
      api.POST("/api/v1/projects/{project_id}/defects", {
        params: { path: { project_id: project.id } },
        body: {
          equipment_id: kind === "equipment" ? (eq?.id ?? null) : null,
          scaffold_id: kind === "scaffold" ? sc : null,
          source,
          source_ref: sourceRef ?? null,
          category: cat,
          description_en: desc.trim(),
          tpi_due_date: tpiDue || null,
          physical_tag_applied: physical,
        },
      }),
    );
    await qc.invalidateQueries({ queryKey: ["defects"] });
    await qc.invalidateQueries({ queryKey: ["equipment-item"] });
    toast.success(t("created", { no: r.defect_no }));
    router.push(`/defects/${r.id}`);
  }
  return (
    <StepDialog title={t("new")} description={t("newHint")} warning={cat === "A" ? t("aWarning") : undefined} confirmLabel={t("raise")} destructive={cat === "A"} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="defect-confirm">
      {!equipment && !scaffoldId ? (
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="mb-1 text-sm font-medium">{t("subject")}</legend>
          <label className="flex min-h-touch items-center gap-2">
            <input type="radio" checked={kind === "equipment"} onChange={() => setKind("equipment")} />
            {t("equipment")}
          </label>
          <label className="flex min-h-touch items-center gap-2">
            <input type="radio" checked={kind === "scaffold"} onChange={() => setKind("scaffold")} data-testid="df-kind-scaffold" />
            {t("scaffold")}
          </label>
        </fieldset>
      ) : null}
      {kind === "equipment" && !equipment ? <EquipmentPicker id="df-equipment" label={t("equipment")} value={eq} onChange={setEq} projectId={project.id} required /> : null}
      {kind === "scaffold" && !scaffoldId ? (
        <FormField id="df-scaffold" label={t("scaffold")} required>
          <Select value={sc} onChange={(e) => setSc(e.target.value)} data-testid="df-scaffold">
            <option value="">{tc("select")}</option>
            {(scaffolds.data?.items ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.tag} · {x.zone.code}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="df-source" label={t("source")} required>
          <Select value={source} onChange={(e) => setSource(e.target.value as S["DefectSource"])} data-testid="df-source">
            {DEFECT_SOURCES.map((x) => (
              <option key={x} value={x}>
                {te(`defectSource.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="df-tpi-due" label={t("tpiDueDate")} hint={t("tpiDueHint")}>
          <Input type="date" className="ltr" value={tpiDue} onChange={(e) => setTpiDue(e.target.value)} />
        </FormField>
      </div>
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1 text-sm font-medium">{t("category")}</legend>
        {DEFECT_CATEGORIES.map((c) => (
          <Button key={c} type="button" variant={cat === c ? "default" : "outline"} aria-pressed={cat === c} onClick={() => setCat(c)} data-testid={`df-cat-${c}`}>
            {te(`defectCategory.${c}`)}
          </Button>
        ))}
      </fieldset>
      <p className="text-xs text-muted-foreground">{t(`catHint.${cat}`)}</p>
      <FormField id="df-desc" label={t("description")} required>
        <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={1000} data-testid="df-description" />
      </FormField>
      <Tick id="df-physical" label={t("physicalTag")} checked={physical} onChange={setPhysical} />
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function DefectDetail({ id }: { id: string }) {
  const q = useDefect(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <DefectView project={p} d={q.data} />}</ProjectById>;
}

type DStep = "rectify" | "close" | "reopen" | "destroy" | "cancel" | null;

function DefectView({ project, d }: { project: S["ProjectRead"]; d: S["DefectRead"] }) {
  const t = useTranslations("defects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const eq = useEquipment(d.equipment?.id ?? "", { enabled: Boolean(d.equipment) });
  const [step, setStep] = useState<DStep>(null);
  const [text, setText] = useState("");
  const [doneBy, setDoneBy] = useState("");
  const [doneAt, setDoneAt] = useState("");
  const [method, setMethod] = useState<S["DefectClosureMethod"]>("tpi_certificate");
  const [lineId, setLineId] = useState("");
  const [reinspect, setReinspect] = useState(false);
  const [returned, setReturned] = useState(false);
  const allowed = (a: string) => d.allowed_actions.includes(a);
  const caps = {
    rectify: canWrite(me, "defect.rectify", project.id),
    close: canWrite(me, "defect.close", project.id),
    raise: canWrite(me, "defect.raise", project.id),
  };
  async function run() {
    const path = { params: { path: { defect_id: d.id } } };
    let r: S["DefectRead"];
    if (step === "rectify") r = await unwrap(api.POST("/api/v1/defects/{defect_id}/rectification", { ...path, body: { description: text.trim(), done_by_text: doneBy.trim(), done_at: doneAt || new Date().toISOString() } }));
    else if (step === "close") r = await unwrap(api.POST("/api/v1/defects/{defect_id}/close", { ...path, body: { method, cert_line_id: method === "tpi_certificate" ? lineId || null : null, note: text.trim(), requires_tpi_reinspection: method === "hse_verification" ? reinspect : null } }));
    else if (step === "reopen") r = await unwrap(api.POST("/api/v1/defects/{defect_id}/reopen", { ...path, body: { reason: text.trim() } }));
    else if (step === "destroy") r = await unwrap(api.POST("/api/v1/defects/{defect_id}/destroy", { ...path, body: { note: text.trim(), returned_to_manufacturer: returned } }));
    else r = await unwrap(api.POST("/api/v1/defects/{defect_id}/cancel", { ...path, body: { reason: text.trim() } }));
    qc.setQueryData(ck.defect(d.id), r);
    await refresh();
    toast.success(te(`defectStatus.${r.status}`));
  }
  const currentLine = eq.data?.current_line?.line;
  const valid = text.trim().length >= 5 && (step !== "rectify" || doneBy.trim().length >= 2) && (step !== "close" || method !== "tpi_certificate" || lineId);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/defects" }, { label: d.defect_no }]} />
        <PageHeader
          title={d.defect_no}
          description={`${d.tag ?? ""} · ${te(`defectSource.${d.source}`)}`}
          actions={
            <>
              <DefectCategoryBadge category={d.category} />
              <DefectStatusBadge status={d.status} />
              {caps.rectify && allowed("rectify") ? (
                <Button onClick={() => setStep("rectify")} data-testid="defect-rectify">
                  <Wrench aria-hidden />
                  {t("rectify")}
                </Button>
              ) : null}
              {caps.close && allowed("close") ? (
                <Button onClick={() => setStep("close")} data-testid="defect-close">
                  {t("close")}
                </Button>
              ) : null}
              {caps.close && allowed("reopen") ? (
                <Button variant="outline" onClick={() => setStep("reopen")} data-testid="defect-reopen">
                  {t("reopen")}
                </Button>
              ) : null}
              {caps.close && allowed("destroy") ? (
                <Button variant="destructive-outline" onClick={() => setStep("destroy")} data-testid="defect-destroy">
                  {t("destroy")}
                </Button>
              ) : null}
              {caps.raise && allowed("cancel") ? (
                <Button variant="outline" onClick={() => setStep("cancel")} data-testid="defect-cancel">
                  {t("cancel")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {d.category === "A" && (d.status === "open" || d.status === "rectified") ? (
        <Alert tone="danger" data-testid="defect-a-stop">
          {t("aOpen")}
        </Alert>
      ) : null}
      {d.overdue ? <Alert tone="danger">{t("overdueAlert")}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("subject")} wide>
              {d.equipment ? <EquipmentLabel e={d.equipment} /> : null}
              {d.scaffold ? (
                <Link href={`/scaffolds/${d.scaffold.id}`} className="text-primary hover:underline">
                  <Code>{d.scaffold.tag}</Code>
                </Link>
              ) : null}
            </FieldItem>
            <FieldItem label={tc("contractor")}>{d.engagement ? <Code>{d.engagement.short_code}</Code> : "—"}</FieldItem>
            <FieldItem label={t("raisedAt")}>{dateTime(d.raised_at)}</FieldItem>
            <FieldItem label={t("raisedBy")}>{d.raised_by_user ? <UserName u={d.raised_by_user} /> : d.raised_by_worker ? <WorkerLabel w={d.raised_by_worker} /> : "—"}</FieldItem>
            <FieldItem label={t("sourceRef")}>{d.source_ref ? <Code>{d.source_ref}</Code> : "—"}</FieldItem>
            <FieldItem label={t("certLine")}>{d.cert_line ? <Code>{d.cert_line.cert_no}</Code> : "—"}</FieldItem>
            <FieldItem label={t("tpiDueDate")}>{d.tpi_due_date ? date(d.tpi_due_date) : "—"}</FieldItem>
            <FieldItem label={t("due")}>
              {d.due_date ? date(d.due_date) : "—"} {d.status === "open" || d.status === "rectified" ? <DaysLeft days={d.days_left} /> : null}
            </FieldItem>
            <FieldItem label={t("physicalTag")}>{d.physical_tag_applied ? tc("yes") : tc("no")}</FieldItem>
            <FieldItem label={t("description")} wide>
              {locale === "ar" && d.description_ar ? d.description_ar : d.description_en}
            </FieldItem>
            {d.cancelled_reason ? (
              <FieldItem label={tc("reason")} wide>
                {d.cancelled_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {d.rectification ? (
        <Card data-testid="rectification">
          <CardHeader>
            <CardTitle className="text-base">{t("rectification")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>{d.rectification.description}</p>
            <p className="text-xs text-muted-foreground">
              {t("doneBy", { by: d.rectification.done_by_text, at: dateTime(d.rectification.done_at) })} · <UserName u={d.rectification.recorded_by} />
            </p>
          </CardContent>
        </Card>
      ) : null}
      {d.closure ? (
        <Card data-testid="closure">
          <CardHeader>
            <CardTitle className="text-base">{t("closure")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              <Badge tone="info">{te(`defectClosureMethod.${d.closure.method}`)}</Badge> {d.closure.cert_line ? <Code>{d.closure.cert_line.cert_no}</Code> : null}
            </p>
            <p className="mt-1">{d.closure.note}</p>
            <p className="text-xs text-muted-foreground">
              <UserName u={d.closure.closed_by} /> · {dateTime(d.closure.closed_at)}
            </p>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("photos")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Attachments ownerType="defect_photo" ownerId={d.id} canUpload={caps.raise && d.status !== "closed" && d.status !== "cancelled"} hint={t("photosHint")} />
        </CardContent>
      </Card>
      <HistoryPanel entityType="equipment_defect" entityId={d.id} />
      {step ? (
        <StepDialog
          title={t(`${step}Title`)}
          description={t(`${step}Hint`)}
          confirmLabel={t(step)}
          destructive={step === "destroy"}
          disabled={!valid}
          onClose={() => {
            setStep(null);
            setText("");
          }}
          onConfirm={run}
          testId="defect-step-confirm"
          wide={step === "close"}
        >
          {step === "rectify" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="dr-by" label={t("doneByLabel")} required>
                <Input value={doneBy} onChange={(e) => setDoneBy(e.target.value)} data-testid="dr-by" />
              </FormField>
              <FormField id="dr-at" label={t("doneAt")} hint={t("nowHint")}>
                <DateTimeInput id="dr-at" value={doneAt} onChange={setDoneAt} />
              </FormField>
            </div>
          ) : null}
          {step === "close" ? (
            <>
              <FormField id="dc-method" label={t("method")} required>
                <Select value={method} onChange={(e) => setMethod(e.target.value as S["DefectClosureMethod"])} data-testid="dc-method">
                  {DEFECT_CLOSURE_METHODS.filter((m) => m !== "destroyed").map((m) => (
                    <option key={m} value={m}>
                      {te(`defectClosureMethod.${m}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              {method === "tpi_certificate" ? (
                <FormField id="dc-line" label={t("afterRepairLine")} required hint={t("afterRepairHint")}>
                  <Select value={lineId} onChange={(e) => setLineId(e.target.value)} data-testid="dc-line">
                    <option value="">{tc("select")}</option>
                    {currentLine ? (
                      <option value={currentLine.line_id}>
                        {currentLine.cert_no} · {currentLine.tpi_code} · {te(`certStatus.${currentLine.status}`)}
                      </option>
                    ) : null}
                  </Select>
                </FormField>
              ) : (
                <Tick id="dc-reinspect" label={t("requiresReinspection")} checked={reinspect} onChange={setReinspect} />
              )}
            </>
          ) : null}
          {step === "destroy" ? <Tick id="dd-returned" label={t("returnedToManufacturer")} checked={returned} onChange={setReturned} /> : null}
          <FormField id="df-text" label={step === "rectify" ? t("whatWasDone") : step === "close" || step === "destroy" ? t("note") : tc("reason")} required>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} data-testid="df-step-text" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/* ───────────── incident prompt (DF-9) ───────────── */

/** On an incident whose agency is equipment: prompt to link or raise a defect. Changes nothing on the incident. */
export function IncidentDefectPrompt({ incidentId, projectId }: { incidentId: string; projectId: string }) {
  const t = useTranslations("defects");
  const me = useMeData();
  const q = useIncidentDefectPrompt(incidentId, { enabled: can(me, "cert_register.view", projectId) });
  const pq = useProject(projectId);
  const [open, setOpen] = useState(false);
  const d = q.data;
  const project = pq.data;
  if (!d || !project || (!d.prompt && !d.linked_defects.length)) return null;
  return (
    <Card data-testid="incident-defect-prompt">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("incidentPromptTitle")}</CardTitle>
        {d.prompt && canWrite(me, "defect.raise", project.id) ? (
          <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="raise-defect-from-incident">
            <Plus aria-hidden />
            {t("new")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        {d.prompt ? <p>{t("incidentPrompt", { agency: d.agency ?? "" })}</p> : null}
        {d.linked_defects.map((x) => (
          <Link key={x.id} href={`/defects/${x.id}`} className="flex items-center gap-2 text-primary hover:underline">
            <Code>{x.defect_no}</Code>
            <DefectCategoryBadge category={x.category} />
          </Link>
        ))}
      </CardContent>
      {open ? <DefectDialog project={project} source="incident" sourceRef={d.incident_ref} onClose={() => setOpen(false)} /> : null}
    </Card>
  );
}

