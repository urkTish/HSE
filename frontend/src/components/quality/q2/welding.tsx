"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useAttachments } from "@/lib/api/hse";
import { useQContinuity, useQPqrs, useQRepairRates, useQWeld, useQWeldLot, useQWeldLots, useQWelders, useQWelds, useQWps, useQWpqs } from "@/lib/api/quality/q2";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { QGate, ReasonDialog, useQCaps, useQLabels, useRun, type Project } from "../q0/common";
import { DecisionDialog, Q2Badge, Signoffs, clean, type S } from "./shared";

const TABS = ["welds", "lots", "continuity", "rates", "wps", "pqr", "welders", "wpq"] as const;

export function WeldingPage() {
  return <QGate>{(p) => <Welding project={p} />}</QGate>;
}

function Welding({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const s = useSearchState();
  const tab = (s.get("tab") as (typeof TABS)[number]) || "welds";
  return (
    <div data-testid="q2-welding">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
        {TABS.map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => s.set({ tab: k })} data-testid={`q2-wld-tab-${k}`}
            className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${tab === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
            {t(`tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "welds" ? <Welds project={project} /> : null}
      {tab === "lots" ? <Lots project={project} /> : null}
      {tab === "continuity" ? <Continuity project={project} /> : null}
      {tab === "rates" ? <Rates project={project} /> : null}
      {tab === "wps" ? <WpsList project={project} /> : null}
      {tab === "pqr" ? <PqrList project={project} /> : null}
      {tab === "welders" ? <Welders project={project} /> : null}
      {tab === "wpq" ? <Wpqs project={project} /> : null}
    </div>
  );
}

function Welds({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { date } = useFormatters(project.id);
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 300);
  const r = useQWelds(project.id, { q: q || null, page_size: 100 });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      {caps.write("welding.record") && !adding ? <Button className="mb-3" onClick={() => setAdding(true)} data-testid="q2-weld-new"><Plus aria-hidden />{t("newWeld")}</Button> : null}
      {adding ? <WeldForm project={project} onDone={() => setAdding(false)} /> : null}
      <ListToolbar><SearchFilter id="q2-weld-q" value={search} onChange={setSearch} /></ListToolbar>
      {r.isLoading ? <LoadingState /> : items.length ? (
        <Table compact data-testid="q2-weld-table">
          <THead><TR><TH>{t("joint")}</TH><TH>{t("wps")}</TH><TH>{t("welders")}</TH><TH>{t("weldedOn")}</TH><TH>{t("lot")}</TH><TH>{t("selection")}</TH><TH>{tc("status")}</TH></TR></THead>
          <TBody>{items.map((w) => (
            <TR key={w.id} data-testid="q2-weld-row" data-joint={w.joint_id} data-status={w.status}>
              <TD label={t("joint")}><Link href={`/quality/welding/welds/${w.id}`} className="ltr font-medium text-primary hover:underline">{w.joint_id}</Link></TD>
              <TD label={t("wps")} className="ltr">{w.wps_no}</TD>
              <TD label={t("welders")} className="ltr">{w.welders.map((x) => x.stamp).join(", ")}</TD>
              <TD label={t("weldedOn")}>{date(w.welded_on)}</TD>
              <TD label={t("lot")} className="ltr">{w.lot_code ?? "—"}</TD>
              <TD label={t("selection")}>{w.selection_reason ? l("ndt_selection", w.selection_reason) : "—"}</TD>
              <TD label={tc("status")}><Q2Badge value={w.status} label={l("weld_status", w.status)} /></TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function WeldForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.wld");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const wps = useQWps(project.id);
  const welders = useQWelders(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ joint_id: "", wps_id: "", position: "2G", joint_type: "butt", thickness_mm: "", diameter_mm: "", length_mm: "", stamp: "", welded_on: "", lot_code: "", ndt_method: "", ndt_required_pct: "", override_reason: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const { stamp, ...rest } = f;
    const body = { ...clean(rest), welders: [{ stamp, root: true, fill: true, cap: true }] } as unknown as S["QWeldCreate"];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/welds", { params: { path: { project_id: project.id } }, body })));
    if (out) { onDone(); router.push(`/quality/welding/welds/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q2-weld-form">
      <MutationError error={error} />
      <FormField id="w-joint" label={t("joint")} required><Input value={f.joint_id} onChange={set("joint_id")} dir="ltr" data-testid="weld-joint" /></FormField>
      <FormField id="w-wps" label={t("wps")} required><Select value={f.wps_id} onChange={set("wps_id")} data-testid="weld-wps"><option value="">{tc("select")}</option>{(wps.data ?? []).filter((x) => x.status === "approved").map((x) => <option key={x.id} value={x.id}>{x.wps_no} Rev.{x.revision}</option>)}</Select></FormField>
      <FormField id="w-stamp" label={t("stamp")} required><Select value={f.stamp} onChange={set("stamp")} data-testid="weld-stamp"><option value="">{tc("select")}</option>{(welders.data ?? []).filter((x) => x.status === "active").map((x) => <option key={x.id} value={x.stamp}>{x.stamp}</option>)}</Select></FormField>
      <FormField id="w-date" label={t("weldedOn")} required><Input type="date" value={f.welded_on} onChange={set("welded_on")} data-testid="weld-date" /></FormField>
      <FormField id="w-pos" label={t("position")}><Input value={f.position} onChange={set("position")} dir="ltr" /></FormField>
      <FormField id="w-type" label={t("jointType")}><Select value={f.joint_type} onChange={set("joint_type")}>{options("joint_type").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="w-th" label={t("thickness")} required><Input value={f.thickness_mm} onChange={set("thickness_mm")} dir="ltr" inputMode="decimal" data-testid="weld-thickness" /></FormField>
      <FormField id="w-dia" label={t("diameter")}><Input value={f.diameter_mm} onChange={set("diameter_mm")} dir="ltr" inputMode="decimal" /></FormField>
      <FormField id="w-lot" label={t("lot")}><Input value={f.lot_code} onChange={set("lot_code")} dir="ltr" /></FormField>
      <FormField id="w-ndt" label={t("ndtMethod")}><Select value={f.ndt_method} onChange={set("ndt_method")}><option value="">—</option>{options("ndt_method").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="w-pct" label={t("ndtPct")}><Input value={f.ndt_required_pct} onChange={set("ndt_required_pct")} dir="ltr" inputMode="decimal" /></FormField>
      <FormField id="w-ovr" label={t("override")} hint={t("overrideHint")}><Input value={f.override_reason} onChange={set("override_reason")} /></FormField>
      <div className="flex gap-2 sm:col-span-4">
        <Button disabled={busy || !f.joint_id || !f.wps_id || !f.stamp || !f.welded_on || !f.thickness_mm} onClick={() => void save()} data-testid="weld-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

function Lots({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const lots = useQWeldLots(project.id);
  const [code, setCode] = useState("");
  const pick = code || lots.data?.[0]?.lot_code || "";
  const s = useQWeldLot(project.id, pick);
  return (
    <div data-testid="q2-lots">
      <FormField id="lot-pick" label={t("lot")}><Select value={pick} onChange={(e) => setCode(e.target.value)} data-testid="q2-lot-pick">{(lots.data ?? []).map((x) => <option key={x.lot_code} value={x.lot_code}>{x.lot_code} ({x.welds})</option>)}</Select></FormField>
      {s.data ? (
        <Card className="mt-3" data-testid="q2-lot-summary"><CardContent className="p-4"><FieldList>
          <FieldItem label={t("ndtMethod")} ltr>{s.data.ndt_method ?? "—"} · {s.data.required_pct} %</FieldItem>
          <FieldItem label={t("visualAccepted")} ltr>{s.data.welds_visual_accepted}</FieldItem>
          <FieldItem label={t("examined")} ltr><span data-testid="q2-lot-examined">{s.data.examined}</span> / {s.data.required}</FieldItem>
          <FieldItem label={t("achieved")} ltr><span data-testid="q2-lot-achieved">{s.data.achieved_pct} %</span></FieldItem>
          <FieldItem label={t("shortfall")} ltr>{s.data.shortfall}</FieldItem>
          <FieldItem label={t("progressive")} ltr>{s.data.progressive} · 100 %: {s.data.pct100}</FieldItem>
        </FieldList>
          <Table compact className="mt-3"><THead><TR><TH>{t("stamp")}</TH><TH>{t("welds")}</TH><TH>{t("examined")}</TH><TH>{t("rejected")}</TH></TR></THead>
            <TBody>{s.data.by_welder.map((w) => <TR key={w.stamp}><TD label={t("stamp")} className="ltr">{w.stamp}</TD><TD label={t("welds")}>{w.welds}</TD><TD label={t("examined")}>{w.examined}</TD><TD label={t("rejected")}>{w.rejected}</TD></TR>)}</TBody></Table>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

function Continuity({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const r = useQContinuity(project.id);
  const rows = r.data ?? [];
  return rows.length ? (
    <Table compact data-testid="q2-continuity"><THead><TR><TH>{t("stamp")}</TH><TH>{t("process")}</TH><TH>{t("lastUse")}</TH><TH>{t("until")}</TH><TH>{t("daysLeft")}</TH><TH>{t("status")}</TH></TR></THead>
      <TBody>{rows.map((x) => (
        <TR key={x.wpq_id} data-stamp={x.stamp} data-status={x.status}>
          <TD label={t("stamp")} className="ltr">{x.stamp}</TD><TD label={t("process")} className="ltr">{x.process}</TD>
          <TD label={t("lastUse")}>{date(x.last_use)}</TD><TD label={t("until")}>{date(x.continuity_until)}</TD>
          <TD label={t("daysLeft")} className={(x.days_left ?? 99) < 30 ? "font-semibold text-danger" : ""}>{x.days_left ?? "—"}</TD>
          <TD label={t("status")}><Q2Badge value={x.status} label={l("wpq_status", x.status)} /></TD>
        </TR>
      ))}</TBody></Table>
  ) : <EmptyState message={t("emptyWpq")} />;
}

function Rates({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const r = useQRepairRates(project.id);
  const rows = r.data ?? [];
  return rows.length ? (
    <Table compact data-testid="q2-rates"><THead><TR><TH>{t("stamp")}</TH><TH>{t("firstExams")}</TH><TH>{t("rejected")}</TH><TH>{t("rate")}</TH><TH>{t("rateLength")}</TH></TR></THead>
      <TBody>{rows.map((x) => <TR key={x.welder_id} data-stamp={x.stamp}><TD label={t("stamp")} className="ltr">{x.stamp}</TD><TD label={t("firstExams")}>{x.first_examinations}</TD><TD label={t("rejected")}>{x.rejected}</TD><TD label={t("rate")} className="ltr">{x.rate_pct} %</TD><TD label={t("rateLength")} className="ltr">{x.rate_by_length_pct ?? "—"}</TD></TR>)}</TBody></Table>
  ) : <EmptyState message={t("emptyRates")} />;
}

function WpsList({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const { l } = useQLabels();
  const r = useQWps(project.id);
  const { run, busy, error } = useRun();
  const [approving, setApproving] = useState<string | null>(null);
  return (
    <div>
      <MutationError error={error} />
      {(r.data ?? []).length ? (
        <Table compact data-testid="q2-wps-table"><THead><TR><TH>{t("wps")}</TH><TH>{t("standard")}</TH><TH>{t("process")}</TH><TH>{t("thicknessRange")}</TH><TH>{t("positions")}</TH><TH>{t("status")}</TH><TH /></TR></THead>
          <TBody>{(r.data ?? []).map((x) => (
            <TR key={x.id} data-no={x.wps_no} data-status={x.status}>
              <TD label={t("wps")} className="ltr">{x.wps_no} Rev.{x.revision}</TD><TD label={t("standard")}>{l("weld_standard", x.standard)}</TD>
              <TD label={t("process")} className="ltr">{x.processes.join(", ")}</TD><TD label={t("thicknessRange")} className="ltr">{x.thickness_min_mm}–{x.thickness_max_mm} mm</TD>
              <TD label={t("positions")} className="ltr">{x.positions.join(" ")}</TD><TD label={t("status")}><Q2Badge value={x.status} label={l("wps_status", x.status)} /></TD>
              <TD label="">
                {x.actions.includes("submit") ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/wps/{wps_id}/submit", { params: { path: { wps_id: x.id } } })))}>{t("submit")}</Button> : null}
                {x.actions.includes("approve") ? <Button size="sm" variant="ghost" onClick={() => setApproving(x.id)} data-testid="q2-wps-approve">{t("approve")}</Button> : null}
              </TD>
            </TR>
          ))}</TBody></Table>
      ) : <EmptyState message={t("emptyWps")} />}
      <ApproveDialog id={approving} onClose={() => setApproving(null)} submit={(id, d, c) => unwrap(api.POST("/api/v1/quality/wps/{wps_id}/approve", { params: { path: { wps_id: id } }, body: { decision: d as "approved", comment: c || null } }))} />
    </div>
  );
}

function ApproveDialog({ id, onClose, submit }: { id: string | null; onClose: () => void; submit: (id: string, d: string, c: string) => Promise<unknown> }) {
  const t = useTranslations("quality.wld");
  const tq = useTranslations("quality.q2");
  return (
    <DecisionDialog open={Boolean(id)} onOpenChange={(v) => { if (!v) onClose(); }} title={t("approve")}
      options={[{ value: "approved", label: tq("approve") }, { value: "approved_with_comments", label: tq("approveWithComments") }, { value: "returned", label: tq("return") }, { value: "rejected", label: tq("reject") }]}
      needsComment={(v) => v === "returned" || v === "rejected"} onSubmit={(d, c) => submit(id ?? "", d, c).then(onClose)} />
  );
}

function PqrList({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const r = useQPqrs(project.id);
  return (r.data ?? []).length ? (
    <Table compact data-testid="q2-pqr-table"><THead><TR><TH>{t("pqr")}</TH><TH>{t("standard")}</TH><TH>{t("process")}</TH><TH>{t("testDate")}</TH><TH>{t("status")}</TH></TR></THead>
      <TBody>{(r.data ?? []).map((x) => <TR key={x.id}><TD label={t("pqr")} className="ltr">{x.pqr_no}</TD><TD label={t("standard")}>{l("weld_standard", x.standard)}</TD><TD label={t("process")} className="ltr">{x.process}</TD><TD label={t("testDate")}>{date(x.test_date)}</TD><TD label={t("status")}><Q2Badge value={x.status} label={l("pqr_status", x.status)} /></TD></TR>)}</TBody></Table>
  ) : <EmptyState message={t("emptyPqr")} />;
}

function Welders({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const { l } = useQLabels();
  const r = useQWelders(project.id);
  return (r.data ?? []).length ? (
    <Table compact data-testid="q2-welder-table"><THead><TR><TH>{t("stamp")}</TH><TH>{t("name")}</TH><TH>{t("contractor")}</TH><TH>{t("status")}</TH></TR></THead>
      <TBody>{(r.data ?? []).map((x) => <TR key={x.id}><TD label={t("stamp")} className="ltr">{x.stamp}</TD><TD label={t("name")}>{x.full_name_en}</TD><TD label={t("contractor")} className="ltr">{x.engagement_code ?? "—"}</TD><TD label={t("status")}>{l("welder_status", x.status)}</TD></TR>)}</TBody></Table>
  ) : <EmptyState message={t("emptyWelders")} />;
}

function Wpqs({ project }: { project: Project }) {
  const t = useTranslations("quality.wld");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const r = useQWpqs(project.id);
  const [approving, setApproving] = useState<string | null>(null);
  return (
    <div>
      {(r.data ?? []).length ? (
        <Table compact data-testid="q2-wpq-table"><THead><TR><TH>{t("wpq")}</TH><TH>{t("stamp")}</TH><TH>{t("process")}</TH><TH>{t("positions")}</TH><TH>{t("thicknessRange")}</TH><TH>{t("until")}</TH><TH>{t("status")}</TH><TH /></TR></THead>
          <TBody>{(r.data ?? []).map((x) => (
            <TR key={x.id} data-stamp={x.stamp} data-status={x.status}>
              <TD label={t("wpq")} className="ltr">{x.wpq_no ?? "—"}</TD><TD label={t("stamp")} className="ltr">{x.stamp}</TD><TD label={t("process")} className="ltr">{x.process}</TD>
              <TD label={t("positions")} className="ltr">{x.positions.join(" ")}</TD><TD label={t("thicknessRange")} className="ltr">{x.thickness_min_mm}–{x.thickness_max_mm}</TD>
              <TD label={t("until")}>{date(x.continuity_until)}</TD><TD label={t("status")}><Q2Badge value={x.status} label={l("wpq_status", x.status)} /></TD>
              <TD label="">{x.actions.includes("approve") ? <Button size="sm" variant="ghost" onClick={() => setApproving(x.id)}>{t("approve")}</Button> : null}</TD>
            </TR>
          ))}</TBody></Table>
      ) : <EmptyState message={t("emptyWpq")} />}
      <ApproveDialog id={approving} onClose={() => setApproving(null)} submit={(id, d, c) => unwrap(api.POST("/api/v1/quality/wpqs/{wpq_id}/approve", { params: { path: { wpq_id: id } }, body: { decision: d as "approved", comment: c || null } }))} />
    </div>
  );
}

export function WeldDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <WeldDetail project={p} id={id} />}</QGate>;
}

function WeldDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.wld");
  const tq = useTranslations("quality.q2");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const q = useQWeld(id);
  const files = useAttachments("q_weld", id);
  const { run, busy, error } = useRun();
  const [defect, setDefect] = useState("");
  const [ndt, setNdt] = useState({ result: "accept", report_no: "", attachment_id: "", defect_type: "", defect_length_mm: "" });
  const [signing, setSigning] = useState(false);
  const [voiding, setVoiding] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const w = q.data;
  if (!w) return null;
  const path = { params: { path: { weld_id: w.id } } };
  const can = (a: string) => w.actions.includes(a);
  return (
    <div data-testid="q2-weld-detail" data-status={w.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/welding" }, { label: w.joint_id }]} />
      <PageHeader title={<span className="ltr">{w.joint_id}</span>} description={w.wps_no}
        badge={<Q2Badge value={w.status} label={l("weld_status", w.status)} testId="q2-weld-status" />}
        actions={<>
          {can("select") ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/select", { ...path, body: { reason: "random" } })))} data-testid="q2-weld-select">{t("select")}</Button> : null}
          {can("repair") || can("repair2") ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/repair", { ...path, body: {} })))} data-testid="q2-weld-repair">{t("repair")}</Button> : null}
          {can("sign_repair2") ? <Button onClick={() => setSigning(true)} data-testid="q2-weld-sign">{t("approveR2")}</Button> : null}
          {can("void") ? <Button variant="outline" onClick={() => setVoiding(true)}>{t("void")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <ApiWarnings warnings={w.warnings} className="mb-3" />
      {(w.progressive ?? []).length ? <Alert tone="warning" className="mb-3" data-testid="q2-progressive">{t("progressiveAdded", { list: (w.progressive ?? []).join(", ") })}</Alert> : null}
      {w.override_reason ? <Alert tone="danger" className="mb-3">{t("overrideNote")}: {w.override_reason}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("process")} ltr>{w.process} · {w.position} · {l("joint_type", w.joint_type)}</FieldItem>
        <FieldItem label={t("thickness")} ltr>{w.thickness_mm} mm{w.diameter_mm ? ` · Ø ${w.diameter_mm}` : ""}</FieldItem>
        <FieldItem label={t("welders")} ltr>{w.welders.map((x) => x.stamp).join(", ")}</FieldItem>
        <FieldItem label={t("weldedOn")}>{date(w.welded_on)}</FieldItem>
        <FieldItem label={t("lot")} ltr>{w.lot_code ?? "—"} {w.ndt_method ? `· ${w.ndt_method} ${w.ndt_required_pct ?? ""} %` : ""}</FieldItem>
        <FieldItem label={t("selection")}>{w.selection_reason ? l("ndt_selection", w.selection_reason) : "—"}</FieldItem>
        <FieldItem label={t("repairs")} ltr>{w.repair_count}</FieldItem>
      </FieldList></CardContent></Card>
      {can("visual") ? (
        <Card className="mb-4" data-testid="q2-visual-form"><CardContent className="flex flex-wrap items-end gap-3 p-4">
          <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/visual", { ...path, body: { result: "accept" } })))} data-testid="q2-visual-accept">{t("visualAccept")}</Button>
          <FormField id="vt-def" label={t("defect")}><Input value={defect} onChange={(e) => setDefect(e.target.value)} /></FormField>
          <Button variant="outline" disabled={busy || !defect} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/visual", { ...path, body: { result: "reject", defect_type: defect } })))} data-testid="q2-visual-reject">{t("visualReject")}</Button>
        </CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("reports")}</h3><Attachments ownerType="q_weld" ownerId={w.id} canUpload={w.status !== "voided"} /></CardContent></Card>
      {can("ndt") ? (
        <Card className="mb-4" data-testid="q2-ndt-form"><CardContent className="grid gap-3 p-4 sm:grid-cols-3">
          <FormField id="ndt-res" label={t("ndtResult")}><Select value={ndt.result} onChange={(e) => setNdt({ ...ndt, result: e.target.value })} data-testid="q2-ndt-result">{["accept", "reject"].map((v) => <option key={v} value={v}>{l("accept_reject", v)}</option>)}</Select></FormField>
          <FormField id="ndt-rno" label={t("reportNo")}><Input value={ndt.report_no} onChange={(e) => setNdt({ ...ndt, report_no: e.target.value })} dir="ltr" data-testid="q2-ndt-report" /></FormField>
          <FormField id="ndt-att" label={t("reportFile")} hint={t("reportFileHint")}><Select value={ndt.attachment_id} onChange={(e) => setNdt({ ...ndt, attachment_id: e.target.value })} data-testid="q2-ndt-attachment"><option value="">—</option>{(files.data?.items ?? []).map((a) => <option key={a.id} value={a.id}>{a.file_name}</option>)}</Select></FormField>
          {ndt.result === "reject" ? <><FormField id="ndt-def" label={t("defect")}><Input value={ndt.defect_type} onChange={(e) => setNdt({ ...ndt, defect_type: e.target.value })} /></FormField>
            <FormField id="ndt-len" label={t("defectLength")}><Input value={ndt.defect_length_mm} onChange={(e) => setNdt({ ...ndt, defect_length_mm: e.target.value })} dir="ltr" /></FormField></> : null}
          <Button className="self-end" disabled={busy || !ndt.report_no || !ndt.attachment_id} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/ndt", { ...path, body: { ...(clean(ndt) as unknown as S["QWeldNdt"]), result: ndt.result as S["QAcceptReject"] } })))} data-testid="q2-ndt-save">{tq("confirm")}</Button>
        </CardContent></Card>
      ) : null}
      {w.ndt_results.length ? (
        <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("ndtResults")}</h3>
          <Table compact><THead><TR><TH>{t("ndtMethod")}</TH><TH>{t("reportNo")}</TH><TH>{t("ndtResult")}</TH><TH>{t("defect")}</TH><TH>{t("round")}</TH></TR></THead>
            <TBody>{w.ndt_results.map((r, i) => <TR key={i}><TD label={t("ndtMethod")} className="ltr">{String(r.method)}</TD><TD label={t("reportNo")} className="ltr">{String(r.report_no)}</TD><TD label={t("ndtResult")}>{l("accept_reject", String(r.result))}</TD><TD label={t("defect")}>{String(r.defect_type ?? "—")}</TD><TD label={t("round")} className="ltr">R{String(r.repair_round)}</TD></TR>)}</TBody></Table>
        </CardContent></Card>
      ) : null}
      <Signoffs recordType="weld" recordId={w.id} />
      <HistoryPanel entityType="q_weld" entityId={w.id} projectId={project.id} />
      <DecisionDialog open={signing} onOpenChange={setSigning} title={t("approveR2")} options={[{ value: "approved", label: tq("approve") }, { value: "rejected", label: tq("reject") }]} needsComment={() => true}
        onSubmit={(d, c) => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/sign-repair2", { ...path, body: { decision: d as "approved", comment: c } })).then(() => q.refetch())} />
      <ReasonDialog open={voiding} onOpenChange={setVoiding} title={t("void")} confirm={t("void")} onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/welds/{weld_id}/void", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}
