"use client";
import { useTranslations } from "next-intl";
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
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, LoadingState, MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useQSuppliers } from "@/lib/api/quality/q0";
import { useQ3Schedules, useQ3Stations, useQ3Visits } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { ChecklistRunner, Q3Gate, fromLocalInput, nowLocal, type Project, type S } from "./common";

export function HygienePage() {
  return <Q3Gate>{(p) => <Hygiene project={p} />}</Q3Gate>;
}

function Hygiene({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.hyg");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const q = useQ3Schedules(project.id);
  const { run, busy, error } = useRun();
  const [running, setRunning] = useState<S["Q3ScheduleRead"] | null>(null);
  const [result, setResult] = useState<S["Q3CheckRunResult"] | null>(null);
  const items = (q.data ?? []).filter((s) => s.check_type === "hygiene");
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MutationError error={error} />
      {q.isLoading ? <LoadingState /> : items.length ? (
        <Table compact data-testid="q3-schedules">
          <THead><TR><TH>{t("zone")}</TH><TH>{t("frequency")}</TH><TH>{t("template")}</TH><TH>{t("current")}</TH><TH>{t("overdue")}</TH><TH /></TR></THead>
          <TBody>{items.map((s) => (
            <TR key={s.id} data-testid="q3-schedule" data-zone={s.zone?.code ?? ""}>
              <TD label={t("zone")} className="ltr">{s.zone?.code ?? s.site?.code}</TD>
              <TD label={t("frequency")}>{l("check_frequency", s.frequency)}</TD>
              <TD label={t("template")} className="ltr">{s.template_code}</TD>
              <TD label={t("current")}>{s.current ? <span dir="ltr">{String(s.current.from)} – {String(s.current.to)}</span> : "—"}</TD>
              <TD label={t("overdue")}>{s.overdue.length ? <Badge tone="danger" data-testid="q3-overdue">{s.overdue.length}</Badge> : <Badge tone="success">0</Badge>}</TD>
              <TD>{caps.write("storage.manage") ? <Button size="sm" onClick={() => { setRunning(s); setResult(null); }} data-testid="q3-run-check">{t("run")}</Button> : null}</TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
      {running ? (
        <Card className="mt-4"><CardContent className="p-4">
          <h2 className="mb-2 text-base font-semibold"><span className="ltr">{running.template_code}</span> · <span className="ltr">{running.zone?.code}</span></h2>
          <ChecklistRunner code={running.template_code} submitLabel={t("submit")} busy={busy}
            onSubmit={(a) => void run(async () => { const o = await unwrap(api.POST("/api/v1/quality/check-schedules/{schedule_id}/checks", { params: { path: { schedule_id: running.id } }, body: { answers: a } as never })); setResult(o); setRunning(null); return o; })} />
        </CardContent></Card>
      ) : null}
      {result ? <Alert tone={result.passed ? "success" : "danger"} className="mt-4" data-testid="q3-check-result">{result.passed ? t("passed") : t("failed")}{result.proposals.length ? ` — ${t("proposeNcr")}` : ""}</Alert> : null}
    </div>
  );
}

export function PestPage() {
  return <Q3Gate>{(p) => <Pest project={p} />}</Q3Gate>;
}

function Pest({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.pst");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const stations = useQ3Stations(project.id);
  const visits = useQ3Visits(project.id);
  const sup = useQSuppliers({ page_size: 200 });
  const { run, busy, error } = useRun();
  const [entering, setEntering] = useState(false);
  const [act, setAct] = useState<Record<string, string>>({});
  const [provider, setProvider] = useState("");
  const [at, setAt] = useState(nowLocal());
  const [last, setLast] = useState<S["Q3VisitRead"] | null>(null);
  const list = stations.data ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("storage.manage") && !entering ? <Button onClick={() => setEntering(true)} data-testid="q3-visit-new">{t("newVisit")}</Button> : null} />
      <MutationError error={error} />
      {entering ? (
        <Card className="mb-4"><CardContent className="p-4" data-testid="q3-visit-form">
          <div className="mb-3 grid gap-3 sm:grid-cols-3">
            <FormField id="pv-prov" label={t("provider")}><Select id="pv-prov" value={provider} onChange={(e) => setProvider(e.target.value)}><option value="">—</option>{(sup.data?.items ?? []).filter((s) => s.categories.includes("pest_control")).map((s) => <option key={s.id} value={s.id}>{s.supplier_code}</option>)}</Select></FormField>
            <FormField id="pv-at" label={t("visited")}><Input id="pv-at" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} dir="ltr" /></FormField>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">{list.map((s) => (
            <label key={s.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
              <span><span className="ltr">{s.code}</span> · <span className="ltr text-xs">{s.zone?.code}</span></span>
              <Select value={act[s.id] ?? "none"} onChange={(e) => setAct((x) => ({ ...x, [s.id]: e.target.value }))} className="w-28" data-testid={`pv-${s.code}`}>{options("pest_activity").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
            </label>
          ))}</div>
          <div className="mt-3 flex gap-2">
            <Button disabled={busy} onClick={() => void run(async () => {
              const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/pest-visits", { params: { path: { project_id: project.id } }, body: { site_id: opts.sites[0]?.value, provider_supplier_id: provider || null, visited_at: fromLocalInput(at), station_results: list.map((s) => ({ station_id: s.id, activity: act[s.id] ?? "none" })) } as never }));
              setLast(o); setEntering(false); setAct({});
              return o;
            })} data-testid="pv-save">{tc("save")}</Button>
            <Button variant="outline" onClick={() => setEntering(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {last?.proposals.length ? <Alert tone="danger" className="mb-3" data-testid="q3-pest-trend">{t("trend")}: {last.proposals.map((p) => String(p.station)).join(", ")}</Alert> : null}
      <h2 className="mb-2 text-base font-semibold">{t("stations")}</h2>
      <Table compact className="mb-4" data-testid="q3-stations">
        <THead><TR><TH>{t("code")}</TH><TH>{t("zone")}</TH><TH>{t("type")}</TH><TH>{t("trendCol")}</TH></TR></THead>
        <TBody>{list.map((s) => <TR key={s.id}><TD className="ltr">{s.code}</TD><TD className="ltr">{s.zone?.code ?? "—"}</TD><TD>{l("pest_station_type", s.station_type)}</TD><TD>{s.activity_trend ? <Badge tone="danger">{t("trendYes")}</Badge> : "—"}</TD></TR>)}</TBody>
      </Table>
      <h2 className="mb-2 text-base font-semibold">{t("visits")}</h2>
      <Table compact data-testid="q3-visits">
        <THead><TR><TH>{t("no")}</TH><TH>{t("visited")}</TH><TH>{t("activity")}</TH><TH>{t("notServiced")}</TH></TR></THead>
        <TBody>{(visits.data ?? []).map((v) => <TR key={v.id}><TD className="ltr">{v.visit_no}</TD><TD>{dateTime(v.visited_at)}</TD><TD><span dir="ltr">{v.station_results.filter((r) => r.activity !== "none").length}</span></TD><TD className="ltr">{v.not_serviced.join(", ") || "—"}</TD></TR>)}</TBody>
      </Table>
    </div>
  );
}
