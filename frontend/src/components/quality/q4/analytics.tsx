"use client";
import { Plus, RefreshCw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { api, openSignedUrl, unwrap } from "@/lib/api/client";
import { useQSuppliers } from "@/lib/api/quality/q0";
import { useQ4Evaluations, useQ4Kpis, useQ4Packs, useQ4Scores, useQ4SpcCharts } from "@/lib/api/quality/q4";
import { useQCaps, useRun } from "@/components/quality/q0/common";
import { Band, Ltr, Q4Gate, Q4Status, useForm, useName, type Project , useT } from "./common";

type Tile = { kpi: string; name_en: string; name_ar: string; unit: string; value: string | null; display: string; numerator: string | null; denominator: string | null; target: string | null; rag: string | null; chips: { code: string; label_en: string; label_ar: string; value: string | null }[] };

// ---- KPI page (§E.7) -------------------------------------------------------------------------

export function KpisPage() {
  return <Q4Gate>{(p) => <Kpis project={p} />}</Q4Gate>;
}

function Kpis({ project }: { project: Project }) {
  const t = useT("quality.q4.kpi");
  const name = useName();
  const [period, setPeriod] = useState({ date_from: "", date_to: "" });
  const q = period.date_from && period.date_to ? period : {};
  const r = useQ4Kpis(project.id, q);
  if (r.isLoading) return <LoadingState />;
  if (r.isError || !r.data) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const d = r.data;
  const tiles = d.tiles as unknown as Tile[];
  const ch = d.charts as Record<string, unknown>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex flex-wrap items-end gap-2" data-testid="q4-kpi-period">
        <FormField id="k-from" label={t("from")}><Input id="k-from" type="date" value={period.date_from} onChange={(e) => setPeriod((x) => ({ ...x, date_from: e.target.value }))} dir="ltr" /></FormField>
        <FormField id="k-to" label={t("to")}><Input id="k-to" type="date" value={period.date_to} onChange={(e) => setPeriod((x) => ({ ...x, date_to: e.target.value }))} dir="ltr" /></FormField>
        <p className="text-sm text-muted-foreground"><Ltr>{d.period_start} – {d.period_end}</Ltr></p>
      </div>
      {d.warnings.map((w) => <Alert key={String(w.code)} tone="warning" className="mb-2" data-testid="q4-warning" data-code={String(w.code)}><Ltr>{String(w.code)}</Ltr> — {name(String(w.message_en), String(w.message_ar))} (<Ltr>{String(w.month)}</Ltr>)</Alert>)}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="q4-tiles">
        {tiles.map((k) => (
          <Card key={k.kpi} data-testid="q4-tile" data-kpi={k.kpi} data-rag={k.rag ?? ""}><CardContent className="space-y-1 p-3">
            <div className="flex items-center justify-between gap-2"><span className="text-xs text-muted-foreground"><Ltr>{k.kpi}</Ltr></span>{k.rag ? <Q4Status value={k.rag} /> : null}</div>
            <p className="text-sm font-medium">{name(k.name_en, k.name_ar)}</p>
            <p className="text-2xl font-semibold"><Ltr>{k.display}</Ltr></p>
            {k.numerator !== null && k.denominator !== null ? <p className="text-xs text-muted-foreground"><Ltr>{k.numerator} / {k.denominator}</Ltr></p> : null}
            {k.target ? <p className="text-xs">{t("target")}: <Ltr>{Number(k.target)}</Ltr></p> : null}
            <div className="flex flex-wrap gap-1">{k.chips.slice(0, 4).map((c) => <Badge key={c.code} tone="neutral">{name(c.label_en, c.label_ar)}: <Ltr>{c.value ?? "—"}</Ltr></Badge>)}</div>
          </CardContent></Card>
        ))}
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {ch.C42 ? <ChartCard title={t("c42")}><Bars rows={(ch.C42 as { month: string; minor: number; major: number; critical: number }[]).map((x) => ({ label: x.month.slice(5), parts: [x.minor, x.major, x.critical] }))} legend={[t("minor"), t("major"), t("critical")]} /></ChartCard> : null}
        {ch.C43 ? <ChartCard title={t("c43")}><Pareto rows={(ch.C43 as { rows: { code: string; count: number; cumulative_pct: string }[] }).rows} /></ChartCard> : null}
        {ch.C44 ? <ChartCard title={t("c44")}><Bars rows={Object.entries((ch.C44 as { buckets: Record<string, number> }).buckets).map(([k, v]) => ({ label: k.replace("_", "–").replace("over–90", ">90"), parts: [v] }))} /></ChartCard> : null}
        {ch.C45 ? <ChartCard title={t("c45")}><Bars rows={(ch.C45 as { month: string; internal: string; external: string }[]).map((x) => ({ label: x.month.slice(5), parts: [Number(x.internal), Number(x.external)] }))} legend={[t("internal"), t("external")]} /></ChartCard> : null}
        {ch.C46 ? <ChartCard title={t("c46")}><Bars rows={(ch.C46 as { month: string; k141: string | null; k142: string | null }[]).map((x) => ({ label: x.month.slice(5), parts: [Number(x.k141 ?? 0), Number(x.k142 ?? 0)] }))} legend={["K-141", "K-142"]} /></ChartCard> : null}
        {ch.C49 ? <ChartCard title={t("c49")}><HeatGrid rows={ch.C49 as { zone: string; months: Record<string, string | null> }[]} /></ChartCard> : null}
        {ch.C50 ? <ChartCard title={t("c50")}><Bars rows={(ch.C50 as { code: string; score: string }[]).map((x) => ({ label: x.code, parts: [Number(x.score)] }))} /></ChartCard> : null}
        {ch.C51 ? <ChartCard title={t("c51")}><Table compact><TBody>{(ch.C51 as { process: string; dpmo: string | null; sigma_display: string }[]).map((x) => <TR key={x.process}><TD>{t.has(`proc.${x.process}`) ? t(`proc.${x.process}`) : x.process}</TD><TD><Ltr>{x.dpmo ?? "—"}</Ltr></TD><TD><Ltr>σ {x.sigma_display}</Ltr></TD></TR>)}</TBody></Table></ChartCard> : null}
      </div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card data-testid="q4-chart"><CardContent className="p-3"><p className="mb-2 text-sm font-medium">{title}</p>{children}</CardContent></Card>;
}

const COLORS = ["var(--color-primary, #2563eb)", "var(--color-warning, #d97706)", "var(--color-danger, #dc2626)"];

/** Stacked bars as SVG, always drawn left-to-right (axes are numbers and months). */
function Bars({ rows, legend }: { rows: { label: string; parts: number[] }[]; legend?: string[] }) {
  const W = 360, H = 160, pad = 18;
  const max = Math.max(1, ...rows.map((r) => r.parts.reduce((a, b) => a + b, 0)));
  const bw = rows.length ? (W - pad) / rows.length : 0;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" style={{ direction: "ltr" }} role="img">
        {rows.map((r, i) => { let y = H - pad; return (
          <g key={r.label + i}>{r.parts.map((v, j) => { const h = (v / max) * (H - pad * 2); y -= h; return <rect key={j} x={pad + i * bw + 2} y={y} width={Math.max(bw - 4, 1)} height={h} fill={COLORS[j % COLORS.length]} />; })}
            <text x={pad + i * bw + bw / 2} y={H - 4} fontSize="8" textAnchor="middle" fill="currentColor">{r.label}</text></g>
        ); })}
      </svg>
      {legend ? <div className="flex gap-3 text-xs">{legend.map((l, i) => <span key={l} className="flex items-center gap-1"><span className="inline-block h-2 w-2" style={{ background: COLORS[i % COLORS.length] }} />{l}</span>)}</div> : null}
    </div>
  );
}

function Pareto({ rows }: { rows: { code: string; count: number; cumulative_pct: string }[] }) {
  const t = useT("quality.q4.kpi");
  return (
    <Table compact data-testid="q4-pareto"><THead><TR><TH>{t("category")}</TH><TH>{t("count")}</TH><TH>{t("cumulative")}</TH></TR></THead>
      <TBody>{rows.map((r) => <TR key={r.code}><TD>{t.has(`cat.${r.code}`) ? t(`cat.${r.code}`) : r.code}</TD><TD><Ltr>{r.count}</Ltr></TD><TD><Ltr className={Number(r.cumulative_pct) <= 80 ? "font-semibold" : ""}>{r.cumulative_pct} %</Ltr></TD></TR>)}</TBody></Table>
  );
}

function HeatGrid({ rows }: { rows: { zone: string; months: Record<string, string | null> }[] }) {
  const months = rows[0] ? Object.keys(rows[0].months) : [];
  const tone: Record<string, string> = { minor: "bg-amber-200", major: "bg-orange-400", critical: "bg-red-600" };
  return (
    <div className="overflow-x-auto" style={{ direction: "ltr" }}><table className="text-xs"><tbody>{rows.map((r) => (
      <tr key={r.zone}><td className="pe-2 font-medium">{r.zone}</td>{months.map((m) => <td key={m} title={`${m} ${r.months[m] ?? ""}`} className={`h-4 w-4 border ${tone[r.months[m] ?? ""] ?? ""}`} />)}</tr>
    ))}</tbody></table></div>
  );
}

// ---- SPC (§E.5) -------------------------------------------------------------------------------

export function SpcPage() {
  return <Q4Gate>{(p) => <Spc project={p} />}</Q4Gate>;
}

type SpcResult = { cl?: string; ucl?: string; lcl?: string; provisional?: boolean; limits_drawn?: boolean; points: { key: string; label: string; value: string; ucl?: string; lcl?: string }[]; signals: { index: number; rule: number; chart: string }[]; capability?: { cp: string | null; cpk: string | null } };

function Spc({ project }: { project: Project }) {
  const t = useT("quality.q4.spc");
  const tc = useTranslations("quality.common");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4SpcCharts(project.id);
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ code: "", title_en: "", source: "ir_rejection_weekly", subgroup_size: "" });
  const TYPE: Record<string, string> = { conc_strength_28d: "xbar_r", dft_spot: "xbar_r", slump: "imr", compaction_pct: "imr", zone_daily_mean_temp: "imr", ir_rejection_weekly: "p", receiving_rejection_weekly: "p" };
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("quality.author") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q4-spc-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4">
          <MutationError error={error} />
          <FormField id="s-code" label={t("code")} required><Input id="s-code" value={f.code} onChange={set("code")} dir="ltr" /></FormField>
          <FormField id="s-title" label={t("chartTitle")}><Input id="s-title" value={f.title_en} onChange={set("title_en")} /></FormField>
          <FormField id="s-src" label={t("source")}><Select id="s-src" value={f.source} onChange={set("source")}>{Object.keys(TYPE).map((x) => <option key={x} value={x}>{t(`sources.${x}`)}</option>)}</Select></FormField>
          <FormField id="s-n" label={t("n")}><Input id="s-n" value={f.subgroup_size} onChange={set("subgroup_size")} dir="ltr" inputMode="numeric" /></FormField>
          <div className="flex gap-2 sm:col-span-4"><Button disabled={busy || !f.code} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/spc-charts", { params: { path: { project_id: project.id } }, body: { code: f.code, title_en: f.title_en || f.code, source: f.source as "slump", chart_type: TYPE[f.source] as "imr", subgroup_size: f.subgroup_size ? Number(f.subgroup_size) : null } })); setAdding(false); return o; })}>{tc("save")}</Button><Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button></div>
        </CardContent></Card>
      ) : null}
      {r.isLoading ? <LoadingState /> : (r.data ?? []).length ? (
        <div className="grid gap-4 lg:grid-cols-2">{(r.data ?? []).map((c) => { const res = c.result as unknown as SpcResult; return (
          <Card key={c.id} data-testid="q4-spc-chart" data-code={c.code}><CardContent className="space-y-2 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium"><Ltr>{c.code}</Ltr> — {name(c.title_en, c.title_ar)}</p>{res.provisional ? <Badge tone="warning">{t("provisional")}</Badge> : null}</div>
            {res.limits_drawn ? <p className="text-xs"><Ltr>CL {res.cl ?? "—"} · UCL {res.ucl ?? "—"} · LCL {res.lcl ?? "—"}</Ltr></p> : <p className="text-xs text-muted-foreground">{t("noLimits")}</p>}
            <ControlChart res={res} />
            {res.capability?.cpk ? <p className="text-xs" data-testid="q4-spc-cpk"><Ltr>Cp {res.capability.cp ?? "—"} · Cpk {res.capability.cpk}</Ltr> — {t("shortTerm")}</p> : null}
            {res.signals.length ? <p className="text-xs text-danger" data-testid="q4-spc-signals">{t("signals")}: <Ltr>{res.signals.slice(-5).map((s) => `#${s.index + 1} R${s.rule}`).join(", ")}</Ltr></p> : null}
          </CardContent></Card>
        ); })}</div>
      ) : <EmptyState />}
    </div>
  );
}

function ControlChart({ res }: { res: SpcResult }) {
  const W = 360, H = 140, pad = 10;
  const pts = res.points.slice(-40).map((p) => Number(p.value));
  if (!pts.length) return null;
  const lim = [res.ucl, res.lcl, res.cl].filter(Boolean).map(Number);
  const pu = res.points.slice(-40).flatMap((p) => [p.ucl, p.lcl].filter(Boolean).map(Number));
  const lo = Math.min(...pts, ...lim, ...pu), hi = Math.max(...pts, ...lim, ...pu);
  const y = (v: number) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - pad * 2);
  const x = (i: number) => pad + (i / Math.max(pts.length - 1, 1)) * (W - pad * 2);
  const off = res.points.length - pts.length;
  const sig = new Set(res.signals.filter((s) => s.chart !== "r" && s.chart !== "mr").map((s) => s.index - off));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-36 w-full" style={{ direction: "ltr" }} role="img">
      {[res.ucl, res.cl, res.lcl].map((v, i) => v ? <line key={i} x1={pad} x2={W - pad} y1={y(Number(v))} y2={y(Number(v))} stroke={i === 1 ? "currentColor" : "#dc2626"} strokeDasharray={i === 1 ? "" : "4 3"} strokeWidth="1" /> : null)}
      <polyline fill="none" stroke="#2563eb" strokeWidth="1.5" points={pts.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
      {pts.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={sig.has(i) ? 3.5 : 2} fill={sig.has(i) ? "#dc2626" : "#2563eb"} />)}
    </svg>
  );
}

// ---- suppliers (§E.3) ------------------------------------------------------------------------------

export function SupplierScoresPage() {
  return <Q4Gate>{(p) => <SupplierScores project={p} />}</Q4Gate>;
}

function SupplierScores({ project }: { project: Project }) {
  const t = useT("quality.q4.sup");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4Scores(project.id);
  const { run, busy, error } = useRun();
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("supplier.manage") ? <Button variant="outline" disabled={busy} data-testid="q4-scores-recompute" onClick={() => void run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/supplier-scores/recompute", { params: { path: { project_id: project.id }, query: {} } })))}><RefreshCw aria-hidden />{t("recompute")}</Button> : null} />
      <MutationError error={error} />
      {r.isLoading ? <LoadingState /> : (r.data ?? []).length ? (
        <Table data-testid="q4-scores"><THead><TR><TH>{t("supplier")}</TH><TH>{t("period")}</TH><TH>{t("score")}</TH><TH>{t("band")}</TH><TH>M1–M6</TH><TH>{t("status")}</TH></TR></THead>
          <TBody>{(r.data ?? []).map((s) => { const pts = ((s.metrics as { points?: Record<string, string> }).points ?? {}); return (
            <TR key={s.id} data-testid="q4-score-row"><TD label={t("supplier")}>{s.supplier ? name(String(s.supplier.name_en), String(s.supplier.name_ar)) : "—"}</TD><TD label={t("period")}><Ltr>{s.period_start} – {s.period_end}</Ltr></TD><TD label={t("score")}><Ltr className="font-semibold">{s.score ?? "—"}</Ltr></TD><TD label={t("band")}><Band band={s.band} /></TD><TD label="M1–M6"><Ltr className="text-xs">{["M1", "M2", "M3", "M4", "M5", "M6"].map((m) => `${m} ${pts[m] ?? "—"}`).join(" · ")}</Ltr></TD><TD label={t("status")}><Q4Status value={s.status} /></TD></TR>
          ); })}</TBody></Table>
      ) : <EmptyState />}
      <Evaluations project={project} />
    </div>
  );
}

export function Evaluations({ project, supplierId }: { project: Project; supplierId?: string }) {
  const t = useT("quality.q4.sup");
  const tc = useTranslations("quality.common");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4Evaluations(project.id, supplierId);
  const sups = useQSuppliers({});
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ supplier_id: supplierId ?? "", kind: "initial", method: "document_review", recommendation: "approve", score: "80" });
  const act = (id: string, action: "submit" | "approve" | "return" | "cancel") => run(() => unwrap(api.POST("/api/v1/quality/supplier-evaluations/{eid}/transition", { params: { path: { eid: id } }, body: { action, comment: action === "return" ? t("returnComment") : null } })));
  return (
    <div className="mt-6" data-testid="q4-evaluations">
      <div className="mb-2 flex items-center justify-between"><p className="font-medium">{t("evaluations")}</p>{caps.write("supplier.manage") && !adding ? <Button size="sm" onClick={() => setAdding(true)} data-testid="q4-sev-new"><Plus aria-hidden />{t("newEvaluation")}</Button> : null}</div>
      <MutationError error={error} />
      {adding ? (
        <Card className="mb-3"><CardContent className="grid gap-3 p-3 sm:grid-cols-5">
          {supplierId ? null : <FormField id="e-sup" label={t("supplier")} required><Select id="e-sup" value={f.supplier_id} onChange={set("supplier_id")}><option value="">{tc("select")}</option>{(sups.data?.items ?? []).map((s) => <option key={s.id} value={s.id}>{s.supplier_code}</option>)}</Select></FormField>}
          <FormField id="e-kind" label={t("kind")}><Select id="e-kind" value={f.kind} onChange={set("kind")}>{["initial", "periodic", "for_cause"].map((x) => <option key={x} value={x}>{t(`kinds.${x}`)}</option>)}</Select></FormField>
          <FormField id="e-method" label={t("method")}><Select id="e-method" value={f.method} onChange={set("method")}>{["questionnaire", "audit", "document_review", "trial_order"].map((x) => <option key={x} value={x}>{t(`methods.${x}`)}</option>)}</Select></FormField>
          <FormField id="e-rec" label={t("recommendation")}><Select id="e-rec" value={f.recommendation} onChange={set("recommendation")}>{["approve", "conditional", "reject", "suspend"].map((x) => <option key={x} value={x}>{t(`recs.${x}`)}</option>)}</Select></FormField>
          <FormField id="e-score" label={t("overall")}><Input id="e-score" value={f.score} onChange={set("score")} dir="ltr" inputMode="numeric" /></FormField>
          <div className="flex gap-2 sm:col-span-5"><Button disabled={busy || !f.supplier_id} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/supplier-evaluations", { params: { path: { project_id: project.id } }, body: { supplier_id: f.supplier_id, kind: f.kind as "initial", method: f.method as "audit", recommendation: f.recommendation as "approve", criteria: [{ criterion: t("overall"), weight: "100", score: f.score || "0" }] } })); setAdding(false); return o; })}>{tc("save")}</Button><Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button></div>
        </CardContent></Card>
      ) : null}
      {(r.data ?? []).length ? (
        <Table compact><THead><TR><TH>{t("no")}</TH><TH>{t("supplier")}</TH><TH>{t("kind")}</TH><TH>{t("total")}</TH><TH>{t("recommendation")}</TH><TH>{t("status")}</TH><TH>{t("nextDue")}</TH><TH /></TR></THead>
          <TBody>{(r.data ?? []).map((e) => (
            <TR key={e.id} data-testid="q4-sev-row"><TD label={t("no")}><Ltr>{e.sev_no ?? "—"}</Ltr></TD><TD label={t("supplier")}>{e.supplier ? name(String(e.supplier.name_en), String(e.supplier.name_ar)) : "—"}</TD><TD label={t("kind")}>{t(`kinds.${e.kind}`)}</TD><TD label={t("total")}><Ltr>{e.total ?? "—"}</Ltr></TD><TD label={t("recommendation")}>{e.recommendation ? t(`recs.${e.recommendation}`) : "—"}</TD><TD label={t("status")}><Q4Status value={e.status} /></TD><TD label={t("nextDue")}><Ltr>{e.next_evaluation_due ?? "—"}</Ltr></TD>
              <TD><div className="flex gap-1">{e.status === "draft" && caps.write("supplier.manage") ? <Button size="sm" disabled={busy} onClick={() => void act(e.id, "submit")} data-testid="q4-sev-submit">{t("submit")}</Button> : null}{e.can_approve ? <><Button size="sm" disabled={busy} onClick={() => void act(e.id, "approve")} data-testid="q4-sev-approve">{t("approve")}</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void act(e.id, "return")}>{t("return")}</Button></> : null}</div></TD></TR>
          ))}</TBody></Table>
      ) : <EmptyState />}
    </div>
  );
}

/** Supplier page tab (registry `tabsQ4`, host supplier): evaluations and the latest scores. */
export function SupplierQualityTab({ recordId, projectId }: { recordId: string; projectId: string | null }) {
  const t = useT("quality.q4.sup");
  const r = useQ4Scores(projectId ?? "", recordId, { enabled: Boolean(projectId) });
  if (!projectId) return <EmptyState />;
  return (
    <div data-testid="q4-supplier-tab">
      <p className="mb-2 font-medium">{t("scores")}</p>
      {(r.data ?? []).length ? <Table compact><TBody>{(r.data ?? []).map((s) => <TR key={s.id}><TD><Ltr>{s.period_start} – {s.period_end}</Ltr></TD><TD><Ltr className="font-semibold">{s.score ?? "—"}</Ltr></TD><TD><Band band={s.band} /></TD><TD><Q4Status value={s.status} /></TD></TR>)}</TBody></Table> : <EmptyState />}
      <ProjectScoped projectId={projectId} supplierId={recordId} />
    </div>
  );
}

function ProjectScoped({ projectId, supplierId }: { projectId: string; supplierId: string }) {
  return <Evaluations project={{ id: projectId } as Project} supplierId={supplierId} />;
}

// ---- reports (6g packs filtered to Quality types, §E.8) ----------------------------------------------

const QTYPES = ["QMR", "QNCR", "QSUP", "QMRV"];

export function ReportsPage() {
  return <Q4Gate>{(p) => <Reports project={p} />}</Q4Gate>;
}

function Reports({ project }: { project: Project }) {
  const t = useT("quality.q4.rpt");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const caps = useQCaps(project.id);
  const r = useQ4Packs(project.id);
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ report_type: "QMR", month: "" });
  const rows = (r.data?.items ?? []).filter((x) => QTYPES.includes(x.report_type));
  const prep = caps.write("quality_report_pack.manage");
  const step = (id: string, action: "submit_for_review" | "review" | "issue" | "regenerate") => run(() => unwrap(api.POST("/api/v1/report-packs/{pack_id}/transitions", { params: { path: { pack_id: id } }, body: { action } as never })));
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MutationError error={error} />
      {prep ? (
        <Card className="mb-4"><CardContent className="flex flex-wrap items-end gap-3 p-3" data-testid="q4-pack-form">
          <FormField id="p-type" label={t("type")}><Select id="p-type" value={f.report_type} onChange={set("report_type")}>{QTYPES.map((x) => <option key={x} value={x}>{t(`types.${x}`)}</option>)}</Select></FormField>
          <FormField id="p-month" label={t("month")} required><Input id="p-month" type="month" value={f.month} onChange={set("month")} dir="ltr" data-testid="q4-pack-month" /></FormField>
          <Button disabled={busy || !f.month} data-testid="q4-pack-create" onClick={() => void run(() => unwrap(api.POST("/api/v1/report-packs", { body: { report_type: f.report_type as "QMR", project_id: project.id, month: f.month, with_names: false } })))}>{tc("save")}</Button>
        </CardContent></Card>
      ) : null}
      {r.isLoading ? <LoadingState /> : rows.length ? (
        <Table data-testid="q4-packs"><THead><TR><TH>{t("doc")}</TH><TH>{t("type")}</TH><TH>{t("period")}</TH><TH>{t("status")}</TH><TH /></TR></THead>
          <TBody>{rows.map((x) => (
            <TR key={x.id} data-testid="q4-pack-row"><TD label={t("doc")}><Ltr>{x.doc_no} R{x.revision}</Ltr></TD><TD label={t("type")}>{t(`types.${x.report_type}`)}</TD><TD label={t("period")}><Ltr>{x.period_start} – {x.period_end}</Ltr></TD><TD label={t("status")}><Q4Status value={x.status} /></TD>
              <TD><div className="flex flex-wrap gap-1">
                {prep && x.status === "draft" ? <Button size="sm" variant="outline" disabled={busy} onClick={() => void step(x.id, "submit_for_review")} data-testid="q4-pack-submit">{t("submit")}</Button> : null}
                {prep && x.status === "in_review" && !x.reviewed_by ? <Button size="sm" variant="outline" disabled={busy} onClick={() => void step(x.id, "review")} data-testid="q4-pack-review">{t("review")}</Button> : null}
                {prep && x.status === "in_review" && x.reviewed_by ? <Button size="sm" disabled={busy} onClick={() => void step(x.id, "issue")} data-testid="q4-pack-issue">{t("issue")}</Button> : null}
                {x.status === "issued" ? (["pdf_en", "pdf_ar"] as const).map((k) => <Button key={k} size="sm" variant="outline" onClick={() => void openSignedUrl(() => unwrap(api.GET("/api/v1/report-packs/{pack_id}/files/{kind}/url", { params: { path: { pack_id: x.id, kind: k } } })))} data-testid={`q4-pack-${k}`}>{k === "pdf_ar" ? (ar ? "PDF عربي" : "PDF AR") : "PDF EN"}</Button>) : null}
              </div></TD></TR>
          ))}</TBody></Table>
      ) : <EmptyState />}
    </div>
  );
}
