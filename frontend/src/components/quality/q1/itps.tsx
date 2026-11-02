"use client";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQSystems } from "@/lib/api/quality/q0";
import { useQCriteriaPublished, useQItp, useQItpCoverage, useQItps } from "@/lib/api/quality/q1";
import { useQuery } from "@tanstack/react-query";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { QGate, ReasonDialog, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type S } from "../q0/common";
import { emptyPaper, LinkList, PaperFields, paperReady, PointTypeChip, Q1Status, SignoffList, Tabs } from "./shared";

type Itp = S["QItpRead"];
type PointIn = S["QItpPointInput"];
const PAGE_SIZE = 50;
const TYPES = ["H", "W", "R", "S"] as const;

/* ═════════════ register `/quality/itps` ═════════════ */

export function ItpListPage() {
  return <QGate>{(p) => <Register project={p} />}</QGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.itp");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const b = useBilingual();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const disc = s.get("discipline") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQItps(project.id, {
    status: status ? [status as S["QItpStatus"]] : null,
    discipline: (disc || null) as S["QDiscipline"] | null,
    current_only: !s.getBool("all_revisions"),
    q: q || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.write("itp.author") ? (
            <Button asChild data-testid="q1-itp-new">
              <Link href="/quality/itps/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <SearchFilter id="q1-itp-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q1-itp-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("itp_status")} />
        <SelectFilter id="q1-itp-disc" label={t("discipline")} value={disc} onChange={(v) => s.set({ discipline: v, page: null })} options={options("discipline")} />
        <SelectFilter id="q1-itp-rev" label={tc("show")} value={s.getBool("all_revisions") ? "all" : ""} onChange={(v) => s.set({ all_revisions: v === "all" ? "true" : null, page: null })}
          options={[{ value: "all", label: t("allRevisions") }]} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q1-itp-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("titleField")}</TH>
                <TH>{t("discipline")}</TH>
                <TH>{t("contractor")}</TH>
                <TH>{tc("status")}</TH>
                <TH>{t("points")}</TH>
                <TH>{t("approved")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((it) => (
                <TR key={it.id} data-testid="q1-itp-row" data-no={it.itp_no ?? ""} data-status={it.status}>
                  <TD label={t("no")}>
                    <Link href={`/quality/itps/${it.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">{it.display_no}</Link>
                  </TD>
                  <TD label={t("titleField")} data-full=""><span dir="auto">{b(it.title_en, it.title_ar)}</span></TD>
                  <TD label={t("discipline")}><span className="ltr">{it.discipline}</span></TD>
                  <TD label={t("contractor")}>{it.engagement?.short_code ?? "—"}</TD>
                  <TD label={tc("status")}><Q1Status kind="itp_status" value={it.status} />{it.approval_code ? <span className="ltr ms-1 text-xs">{it.approval_code}</span> : null}</TD>
                  <TD label={t("points")} className="ltr">{it.point_count}</TD>
                  <TD label={t("approved")}>{date(it.approved_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

/* ═════════════ builder (new and edit) ═════════════ */

function blankPoint(seq: number): PointIn {
  return { seq, activity_en: "", activity_ar: "", characteristic_en: "", characteristic_ar: "", point_type: "W", criteria_ids: [], verifying_record: "ir", test_type_codes: [] };
}

function toInput(p: S["QItpPointRead"]): PointIn {
  return {
    seq: p.seq, activity_en: p.activity_en, activity_ar: p.activity_ar, characteristic_en: p.characteristic_en, characteristic_ar: p.characteristic_ar,
    point_type: p.point_type, criteria_ids: p.criteria_ids, acceptance_text_en: p.acceptance_text_en, acceptance_text_ar: p.acceptance_text_ar,
    reference: p.reference, verifying_record: p.verifying_record, checklist_template_code: p.checklist_template_code, test_type_codes: p.test_type_codes,
    frequency_text: p.frequency_text, notice_hours: p.notice_hours, competence_code: p.competence_code,
  };
}

export function ItpNewPage() {
  return <QGate>{(p) => <Builder project={p} />}</QGate>;
}

function useChecklists(projectId: string, type: "ir_inspection" | "punch_walkdown") {
  return useQuery({
    queryKey: ["q-q1-checklists", projectId, type],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/q1-checklists", { params: { path: { project_id: projectId }, query: { quality_type: type } } })),
    staleTime: 5 * 60_000,
  });
}
export { useChecklists };

function Builder({ project, itp, onDone }: { project: Project; itp?: Itp; onDone?: () => void }) {
  const t = useTranslations("quality.q1.itp");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const systems = useQSystems(project.id);
  const crit = useQCriteriaPublished();
  const tpls = useChecklists(project.id, "ir_inspection");
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [h, setH] = useState({
    title_en: itp?.title_en ?? "", title_ar: itp?.title_ar ?? "", discipline: itp?.discipline ?? "STC", engagement_id: itp?.engagement?.id ?? "",
    work_package_en: itp?.work_package_en ?? "", method_statement_ref: itp?.method_statement_ref ?? "", change_note: itp?.change_note ?? "",
    spec_refs: (itp?.spec_refs ?? []).join("\n"), code_refs: (itp?.code_refs ?? []).join("\n"),
  });
  const [zones, setZones] = useState<string[]>(itp?.zones.map((z) => z.id) ?? []);
  const [sys, setSys] = useState<string[]>(itp?.systems.map((x) => x.id) ?? []);
  const [pts, setPts] = useState<PointIn[]>(itp ? itp.points.map(toInput) : [blankPoint(10)]);
  const set = (k: keyof typeof h) => (e: { target: { value: string } }) => setH((x) => ({ ...x, [k]: e.target.value }));
  const setPt = (i: number, patch: Partial<PointIn>) => setPts((xs) => xs.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const move = (i: number, d: -1 | 1) => setPts((xs) => {
    const j = i + d;
    if (j < 0 || j >= xs.length) return xs;
    const out = xs.slice();
    [out[i], out[j]] = [out[j]!, out[i]!];
    return out.map((p, k) => ({ ...p, seq: (k + 1) * 10 }));
  });
  const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);
  async function save(submit: boolean) {
    const body = {
      ...h, spec_refs: lines(h.spec_refs), code_refs: lines(h.code_refs), zone_ids: zones, system_ids: sys, points: pts,
      discipline: h.discipline as S["QDiscipline"],
    };
    const out = await run(async () => {
      const saved = itp
        ? await unwrap(api.PATCH("/api/v1/quality/itps/{itp_id}", { params: { path: { itp_id: itp.id } }, body: { ...body, engagement_id: undefined } }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/quality/itps", { params: { path: { project_id: project.id } }, body: { ...body, engagement_id: h.engagement_id } }));
      return submit ? unwrap(api.POST("/api/v1/quality/itps/{itp_id}/submit", { params: { path: { itp_id: saved.id } } })) : saved;
    }, submit ? t("submitted") : undefined);
    if (out) {
      if (onDone) onDone();
      else router.push(`/quality/itps/${out.id}`);
    }
  }
  const critOpts = (crit.data?.items ?? []).map((c) => ({ value: c.id, label: `${c.code} v${c.version} — ${ar ? c.title_ar || c.title_en : c.title_en}` }));
  return (
    <div data-testid="q1-itp-builder">
      {!itp ? <Breadcrumbs items={[{ label: t("title"), href: "/quality/itps" }, { label: t("new") }]} /> : null}
      {!itp ? <PageHeader title={t("new")} description={t("builderHint")} /> : null}
      <MutationError error={error} />
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-4 p-4">
          <FormSection title={t("header")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="itp-title-en" label={t("titleEn")} required><Input value={h.title_en} onChange={set("title_en")} maxLength={150} data-testid="q1-itp-title-en" /></FormField>
              <FormField id="itp-title-ar" label={t("titleAr")} required><Input dir="rtl" value={h.title_ar} onChange={set("title_ar")} maxLength={150} data-testid="q1-itp-title-ar" /></FormField>
              <FormField id="itp-disc" label={t("discipline")} required>
                <Select value={h.discipline} onChange={set("discipline")} disabled={Boolean(itp?.itp_no)} data-testid="q1-itp-discipline">
                  {options("discipline").map((o) => <option key={o.value} value={o.value}>{o.value} — {o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="itp-eng" label={t("contractor")} required>
                <Select value={h.engagement_id} onChange={set("engagement_id")} disabled={Boolean(itp)} data-testid="q1-itp-engagement">
                  <option value="">{tc("select")}</option>
                  {opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="itp-wp" label={t("workPackage")}><Input value={h.work_package_en} onChange={set("work_package_en")} /></FormField>
              <FormField id="itp-ms" label={t("methodStatement")}><Input className="ltr" value={h.method_statement_ref} onChange={set("method_statement_ref")} /></FormField>
              <MultiSelect id="itp-zones" label={t("zones")} value={zones} onChange={setZones} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} allLabel={tc("select")} />
              <MultiSelect id="itp-sys" label={t("systems")} value={sys} onChange={setSys} allLabel={tc("select")}
                options={(systems.data ?? []).map((x) => ({ value: x.id, label: `${x.code} — ${ar ? x.name_ar : x.name_en}` }))} />
              <FormField id="itp-spec" label={t("specRefs")} hint={t("oneLine")}><Textarea value={h.spec_refs} onChange={set("spec_refs")} rows={2} /></FormField>
              <FormField id="itp-code" label={t("codeRefs")} hint={t("oneLine")}><Textarea value={h.code_refs} onChange={set("code_refs")} rows={2} /></FormField>
              {itp && itp.revision > 0 ? (
                <FormField id="itp-note" label={t("changeNote")} required className="sm:col-span-2"><Textarea value={h.change_note} onChange={set("change_note")} rows={2} data-testid="q1-itp-change-note" /></FormField>
              ) : null}
            </div>
          </FormSection>
        </CardContent>
      </Card>
      <FormSection title={t("points")}>
        <div className="flex flex-col gap-3" data-testid="q1-itp-points">
          {pts.map((p, i) => (
            <Card key={i} data-testid="q1-itp-point" data-seq={p.seq}>
              <CardContent className="grid gap-3 p-3 sm:grid-cols-6">
                <div className="flex items-center gap-1 sm:col-span-6">
                  <span className="ltr font-mono text-sm font-semibold">{p.seq}</span>
                  <div className="flex gap-1" role="radiogroup" aria-label={t("pointType")}>
                    {TYPES.map((ty) => (
                      <button key={ty} type="button" role="radio" aria-checked={p.point_type === ty} onClick={() => setPt(i, { point_type: ty })} data-testid={`q1-pt-${p.seq}-${ty}`}
                        className={`min-h-touch rounded-md border px-2 text-sm ${p.point_type === ty ? "border-primary bg-primary/10 font-semibold" : ""}`}>
                        <span className="ltr">{ty}</span>
                      </button>
                    ))}
                  </div>
                  <span className="ms-auto flex gap-1">
                    <Button type="button" size="sm" variant="ghost" aria-label={t("moveUp")} onClick={() => move(i, -1)}><ArrowUp aria-hidden /></Button>
                    <Button type="button" size="sm" variant="ghost" aria-label={t("moveDown")} onClick={() => move(i, 1)}><ArrowDown aria-hidden /></Button>
                    <Button type="button" size="sm" variant="ghost" aria-label={tc("delete")} onClick={() => setPts((xs) => xs.filter((_, j) => j !== i))}><Trash2 aria-hidden /></Button>
                  </span>
                </div>
                <FormField id={`pt-${i}-act`} label={t("activityEn")} className="sm:col-span-3"><Input value={p.activity_en ?? ""} onChange={(e) => setPt(i, { activity_en: e.target.value })} data-testid={`q1-pt-${p.seq}-activity`} /></FormField>
                <FormField id={`pt-${i}-act-ar`} label={t("activityAr")} className="sm:col-span-3"><Input dir="rtl" value={p.activity_ar ?? ""} onChange={(e) => setPt(i, { activity_ar: e.target.value })} /></FormField>
                <FormField id={`pt-${i}-chr`} label={t("characteristic")} className="sm:col-span-3"><Input value={p.characteristic_en ?? ""} onChange={(e) => setPt(i, { characteristic_en: e.target.value })} data-testid={`q1-pt-${p.seq}-char`} /></FormField>
                <FormField id={`pt-${i}-acc`} label={t("acceptance")} className="sm:col-span-3"><Input value={p.acceptance_text_en ?? ""} onChange={(e) => setPt(i, { acceptance_text_en: e.target.value })} data-testid={`q1-pt-${p.seq}-acceptance`} /></FormField>
                <div className="sm:col-span-3">
                  <MultiSelect id={`pt-${i}-crit`} label={t("criteria")} value={p.criteria_ids ?? []} onChange={(v) => setPt(i, { criteria_ids: v })} options={critOpts} allLabel={tc("select")} testId={`q1-pt-${p.seq}-criteria`} />
                </div>
                <FormField id={`pt-${i}-tpl`} label={t("checklist")} className="sm:col-span-2">
                  <Select value={p.checklist_template_code ?? ""} onChange={(e) => setPt(i, { checklist_template_code: e.target.value || null })}>
                    <option value="">—</option>
                    {(tpls.data ?? []).map((x) => <option key={x.template_code} value={x.template_code}>{x.template_code} — {ar ? x.title_ar : x.title_en}</option>)}
                  </Select>
                </FormField>
                <FormField id={`pt-${i}-ver`} label={t("verifying")}>
                  <Select value={p.verifying_record ?? "ir"} onChange={(e) => setPt(i, { verifying_record: e.target.value as S["QVerifyingRecord"] })}>
                    {options("verifying_record").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </Select>
                </FormField>
                <FormField id={`pt-${i}-freq`} label={t("frequency")} className="sm:col-span-2"><Input value={p.frequency_text ?? ""} onChange={(e) => setPt(i, { frequency_text: e.target.value })} /></FormField>
                <FormField id={`pt-${i}-notice`} label={t("noticeHours")}><Input type="number" min={0} max={168} className="ltr" value={p.notice_hours ?? ""} onChange={(e) => setPt(i, { notice_hours: e.target.value === "" ? null : Number(e.target.value) })} /></FormField>
                <FormField id={`pt-${i}-comp`} label={t("competence")} className="sm:col-span-2"><Input className="ltr" value={p.competence_code ?? ""} onChange={(e) => setPt(i, { competence_code: e.target.value || null })} /></FormField>
              </CardContent>
            </Card>
          ))}
          <Button type="button" variant="outline" className="self-start" onClick={() => setPts((xs) => [...xs, blankPoint(((xs.at(-1)?.seq ?? 0) + 10))])} data-testid="q1-itp-add-point">
            <Plus aria-hidden />
            {t("addPoint")}
          </Button>
        </div>
      </FormSection>
      <div className="sticky bottom-0 mt-4 flex flex-wrap gap-2 bg-background py-3">
        <Button variant="outline" disabled={busy || (!itp && !h.engagement_id)} onClick={() => void save(false)} data-testid="q1-itp-save">{tc("save")}</Button>
        <Button disabled={busy || (!itp && !h.engagement_id)} onClick={() => void save(true)} data-testid="q1-itp-submit">{t("submit")}</Button>
        {onDone ? <Button variant="ghost" onClick={onDone}>{tc("cancel")}</Button> : null}
      </div>
    </div>
  );
}

/* ═════════════ detail `/quality/itps/[id]` ═════════════ */

const TABS = ["points", "coverage", "revisions", "signoffs", "links", "history"] as const;
type Tab = (typeof TABS)[number];

export function ItpDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <Detail project={p} id={id} />}</QGate>;
}

function Detail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.q1.itp");
  const b = useBilingual();
  const ar = useLocale() === "ar";
  const q = useQItp(id);
  const [tab, setTab] = useState<Tab>("points");
  const [editing, setEditing] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const it = q.data;
  if (!it) return null;
  if (editing) return <Builder project={project} itp={it} onDone={() => { setEditing(false); void q.refetch(); }} />;
  return (
    <div data-testid="q1-itp-detail" data-status={it.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/itps" }, { label: it.display_no }]} />
      <PageHeader
        title={<span className="ltr">{it.display_no}</span>}
        badge={<span className="flex flex-wrap items-center gap-2"><Q1Status kind="itp_status" value={it.status} />{it.approval_code ? <span className="ltr text-xs">{it.approval_code}</span> : null}</span>}
        description={b(it.title_en, it.title_ar)}
        actions={<Actions itp={it} onEdit={() => setEditing(true)} />}
      />
      {it.problems.length ? (
        <Alert tone="warning" className="mb-3" data-testid="q1-itp-problems">
          <p className="font-medium">{t("incomplete")}</p>
          <ul className="list-disc ps-5">{it.problems.map((x) => <li key={x}>{x}</li>)}</ul>
        </Alert>
      ) : null}
      {it.rp_not_set ? <Alert tone="danger" className="mb-3">{t("rpNotSet")}</Alert> : null}
      {it.status === "submitted" && it.responsible.length ? (
        <p className="mb-3 text-sm text-muted-foreground" data-testid="q1-itp-responsible">{t("awaiting", { names: it.responsible.map((u) => userText(u, ar)).join(", ") })}</p>
      ) : null}
      <Card className="mb-4">
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("discipline")}><span className="ltr">{it.discipline}</span></FieldItem>
            <FieldItem label={t("contractor")}>{it.engagement?.short_code ?? "—"}</FieldItem>
            <FieldItem label={t("zones")}>{it.zones.map((z) => z.code).join(", ") || t("wholeProject")}</FieldItem>
            <FieldItem label={t("systems")}>{it.systems.map((z) => z.code).join(", ") || "—"}</FieldItem>
            <FieldItem label={t("specRefs")}>{it.spec_refs.join("; ") || "—"}</FieldItem>
            <FieldItem label={t("codeRefs")}>{it.code_refs.join("; ") || "—"}</FieldItem>
            <FieldItem label={t("methodStatement")} ltr>{it.method_statement_ref ?? "—"}</FieldItem>
            <FieldItem label={t("preparedBy")}>{userText(it.prepared_by, ar)}</FieldItem>
            {it.change_note ? <FieldItem label={t("changeNote")} wide>{it.change_note}</FieldItem> : null}
            {it.decision_comment ? <FieldItem label={t("decisionComment")} wide>{it.decision_comment}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`tab.${k}`)} prefix="q1-itp" />
      {tab === "points" ? <Points itp={it} /> : null}
      {tab === "coverage" ? <Coverage id={it.id} /> : null}
      {tab === "revisions" ? <Revisions itp={it} /> : null}
      {tab === "signoffs" ? <SignoffList items={it.signoffs} recordType="itp" /> : null}
      {tab === "links" ? <LinkList items={it.links} /> : null}
      {tab === "history" ? <HistoryPanel entityType="q_itp" entityId={it.id} projectId={project.id} /> : null}
    </div>
  );
}

function Points({ itp, changed }: { itp: Itp; changed?: Set<number> }) {
  const t = useTranslations("quality.q1.itp");
  const b = useBilingual();
  const { l } = useQLabels();
  return (
    <Table compact data-testid="q1-itp-points-table">
      <THead>
        <TR>
          <TH>{t("seq")}</TH>
          <TH>{t("pointType")}</TH>
          <TH>{t("activity")}</TH>
          <TH>{t("characteristic")}</TH>
          <TH>{t("criteria")}</TH>
          <TH>{t("verifying")}</TH>
        </TR>
      </THead>
      <TBody>
        {itp.points.map((p) => (
          <TR key={p.id} data-testid="q1-point-row" data-seq={p.seq} data-changed={changed?.has(p.seq) ? "true" : undefined} className={changed?.has(p.seq) ? "bg-warning/10" : ""}>
            <TD label={t("seq")} className="ltr font-mono">{p.seq}</TD>
            <TD label={t("pointType")}><PointTypeChip value={p.point_type} /></TD>
            <TD label={t("activity")} data-full="">{b(p.activity_en, p.activity_ar)}</TD>
            <TD label={t("characteristic")}>{b(p.characteristic_en, p.characteristic_ar)}</TD>
            <TD label={t("criteria")} className="text-xs">
              {p.criteria.map((c) => <span key={c.id} className="ltr me-1 inline-block rounded border px-1">{c.code}</span>)}
              {p.acceptance_text_en || p.acceptance_text_ar ? <span className="block">{b(p.acceptance_text_en, p.acceptance_text_ar)}</span> : null}
              {p.checklist_template_code ? <span className="ltr block text-muted-foreground">{p.checklist_template_code}</span> : null}
            </TD>
            <TD label={t("verifying")} className="text-xs">{l("verifying_record", p.verifying_record)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function Coverage({ id }: { id: string }) {
  const t = useTranslations("quality.q1.itp");
  const q = useQItpCoverage(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  if (!c || !c.rows.length) return <EmptyState message={t("noCoverage")} />;
  const tone: Record<string, string> = {
    approved: "bg-success/15 text-success", approved_with_comments: "bg-success/10 text-success", rejected: "bg-danger/15 text-danger",
    scheduled: "bg-info/15", waived: "bg-warning/15", not_started: "text-muted-foreground",
  };
  const mark: Record<string, string> = { approved: "✓", approved_with_comments: "✓*", rejected: "✗", scheduled: "◷", waived: "W", not_started: "·" };
  return (
    <div className="overflow-x-auto" data-testid="q1-coverage">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="sticky start-0 bg-background p-2 text-start">{t("location")}</th>
            {c.points.map((p) => <th key={p.seq} className="p-2 text-center"><span className="ltr">{p.seq}</span> <PointTypeChip value={p.point_type} /></th>)}
          </tr>
        </thead>
        <tbody>
          {c.rows.map((r) => (
            <tr key={r.location_key} className="border-t">
              <td className="sticky start-0 bg-background p-2" dir="auto">{r.location_ref}</td>
              {r.cells.map((x) => (
                <td key={x.seq} className={`p-2 text-center ${tone[x.state] ?? ""}`} title={`${t(`cell.${x.state}`)}${x.ir_no ? ` · ${x.ir_no}` : ""}`} data-state={x.state}>
                  <span aria-hidden>{mark[x.state]}</span>
                  <span className="sr-only">{t(`cell.${x.state}`)}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">{t("coverageLegend")}</p>
    </div>
  );
}

function Revisions({ itp }: { itp: Itp }) {
  const t = useTranslations("quality.q1.itp");
  const { date } = useFormatters();
  const prevRev = [...itp.revisions].filter((r) => r.revision < itp.revision).sort((a, b) => b.revision - a.revision)[0];
  const prev = useQItp(prevRev?.id ?? "");
  const changed = useMemo(() => {
    const out = new Set<number>();
    if (!prev.data) return out;
    const before = new Map(prev.data.points.map((p) => [p.seq, p]));
    for (const p of itp.points) {
      const o = before.get(p.seq);
      const sig = (x: S["QItpPointRead"]) => JSON.stringify([x.point_type, x.activity_en, x.characteristic_en, x.criteria_ids, x.acceptance_text_en, x.checklist_template_code, x.verifying_record]);
      if (!o || sig(o) !== sig(p)) out.add(p.seq);
    }
    return out;
  }, [prev.data, itp.points]);
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-wrap gap-2" data-testid="q1-itp-revisions">
        {itp.revisions.map((r) => (
          <li key={r.id}>
            <Link href={`/quality/itps/${r.id}`} className={`glass inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${r.id === itp.id ? "border-primary" : ""}`}>
              <span className="ltr">Rev.{r.revision}</span>
              <Q1Status kind="itp_status" value={r.status} />
              <span className="text-xs text-muted-foreground">{date(r.approved_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
      {prevRev ? (
        <>
          <p className="text-sm text-muted-foreground" data-testid="q1-itp-compare">{t("compareWith", { rev: prevRev.revision, n: changed.size })}</p>
          <Points itp={itp} changed={changed} />
        </>
      ) : <p className="text-sm text-muted-foreground">{t("firstRevision")}</p>}
    </div>
  );
}

function Actions({ itp, onEdit }: { itp: Itp; onEdit: () => void }) {
  const t = useTranslations("quality.q1.itp");
  const tc = useTranslations("quality.common");
  const router = useRouter();
  const { run, busy, error } = useRun();
  const allowed = new Set(itp.allowed_actions);
  const [decide, setDecide] = useState(false);
  const [withdraw, setWithdraw] = useState(false);
  const path = { params: { path: { itp_id: itp.id } } };
  return (
    <div className="flex flex-col items-end gap-2">
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        {allowed.has("edit") ? <Button variant="outline" onClick={onEdit} data-testid="q1-itp-edit">{t("edit")}</Button> : null}
        {allowed.has("submit") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/itps/{itp_id}/submit", path)), t("submitted"))} data-testid="q1-itp-submit-btn">{t("submit")}</Button> : null}
        {allowed.has("decide") || allowed.has("paper_signoff") ? <Button onClick={() => setDecide((v) => !v)} data-testid="q1-itp-decide">{t("decide")}</Button> : null}
        {allowed.has("new_revision") ? (
          <Button variant="outline" disabled={busy} data-testid="q1-itp-new-rev"
            onClick={async () => { const r = await run(() => unwrap(api.POST("/api/v1/quality/itps/{itp_id}/revisions", { ...path, body: {} })), t("revisionCreated")); if (r) router.push(`/quality/itps/${r.id}`); }}>
            {t("newRevision")}
          </Button>
        ) : null}
        {allowed.has("withdraw") ? <Button variant="outline" onClick={() => setWithdraw(true)}>{t("withdraw")}</Button> : null}
        {allowed.has("delete") ? (
          <Button variant="ghost" disabled={busy} onClick={async () => { const r = await run(() => unwrap(api.DELETE("/api/v1/quality/itps/{itp_id}", path))); if (r !== undefined) router.push("/quality/itps"); }}>{tc("delete")}</Button>
        ) : null}
      </div>
      {decide ? <DecideForm itp={itp} paperOnly={!allowed.has("decide")} onDone={() => setDecide(false)} /> : null}
      <ReasonDialog open={withdraw} onOpenChange={setWithdraw} title={t("withdraw")} confirm={t("withdraw")} min={20}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/itps/{itp_id}/withdraw", { ...path, body: { reason } }))} />
    </div>
  );
}

function DecideForm({ itp, paperOnly, onDone }: { itp: Itp; paperOnly: boolean; onDone: () => void }) {
  const t = useTranslations("quality.q1.itp");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const { run, busy, error } = useRun();
  const [code, setCode] = useState<S["QApprovalCode"]>("A");
  const [comment, setComment] = useState("");
  const [paper, setPaper] = useState(paperOnly);
  const [pp, setPp] = useState(emptyPaper());
  const needs = code === "C" || code === "D" ? 20 : code === "B" ? 1 : 0;
  async function go() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/itps/{itp_id}/decide", {
      params: { path: { itp_id: itp.id } }, body: { code, comment: comment || null, paper: paper ? pp : null },
    })), t("decided"));
    if (out) onDone();
  }
  return (
    <Card className="w-full max-w-xl" data-testid="q1-itp-decide-form">
      <CardContent className="flex flex-col gap-3 p-4">
        <MutationError error={error} />
        <FormField id="itp-code" label={t("approvalCode")}>
          <Select value={code} onChange={(e) => setCode(e.target.value as S["QApprovalCode"])} data-testid="q1-itp-code">
            {options("approval_code").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="itp-comment" label={t("comment")} hint={needs > 1 ? tc("minChars", { n: needs }) : undefined} required={needs > 0}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} data-testid="q1-itp-comment" />
        </FormField>
        {!paperOnly ? <CheckboxField id="itp-paper" label={t("paperInstead")}><Checkbox checked={paper} onChange={(e) => setPaper(e.target.checked)} /></CheckboxField> : null}
        {paper ? <PaperFields value={pp} onChange={setPp} /> : null}
        <div className="flex gap-2">
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
          <Button disabled={busy || comment.trim().length < needs || (paper && !paperReady(pp))} onClick={() => void go()} data-testid="q1-itp-decide-confirm">{t("confirmDecision")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
