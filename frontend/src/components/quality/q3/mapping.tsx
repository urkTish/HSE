"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQMte } from "@/lib/api/quality/q0";
import { useQ3Studies, useQ3Study, useQ3Zones } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { StatusBadge, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { Q3Gate, Temp, fromLocalInput, type Project, type S } from "./common";

export function MappingListPage() {
  return <Q3Gate>{(p) => <Studies project={p} />}</Q3Gate>;
}

function Studies({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.map");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { date } = useFormatters(project.id);
  const q = useQ3Studies(project.id);
  const zones = useQ3Zones(project.id);
  const [adding, setAdding] = useState(false);
  const unmapped = (zones.data ?? []).filter((z) => z.storage_class === "pharma_2_8" && z.mapping_state !== "mapped");
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("storage.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-map-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {unmapped.length ? <Alert tone="danger" className="mb-3" data-testid="q3-pharma-unmapped">{t("pharmaUnmapped", { zones: unmapped.map((z) => z.code).join(", ") })}</Alert> : null}
      <Table compact className="mb-4" data-testid="q3-map-zones">
        <THead><TR><TH>{t("zone")}</TH><TH>{t("state")}</TH><TH>{t("validUntil")}</TH></TR></THead>
        <TBody>{(zones.data ?? []).map((z) => <TR key={z.zone_id}><TD className="ltr">{z.code}</TD><TD><Badge tone={z.mapping_state === "mapped" ? "success" : "warning"}>{l("mapping_state", z.mapping_state)}</Badge></TD><TD>{date(z.mapped_until)}</TD></TR>)}</TBody>
      </Table>
      {adding ? <StudyForm project={project} onDone={() => setAdding(false)} /> : null}
      {q.isLoading ? <LoadingState /> : (q.data ?? []).length ? (
        <Table compact data-testid="q3-map-table">
          <THead><TR><TH>{t("no")}</TH><TH>{t("zone")}</TH><TH>{t("purpose")}</TH><TH>{t("loggers")}</TH><TH>{t("validUntil")}</TH><TH>{tc("status")}</TH></TR></THead>
          <TBody>{(q.data ?? []).map((m) => (
            <TR key={m.id}><TD><Link className="ltr font-medium text-primary hover:underline" href={`/quality/mapping/${m.id}`}>{m.map_no ?? t("draft")}</Link></TD><TD className="ltr">{m.zone_code}</TD><TD>{l("mapping_purpose", m.purpose)}</TD><TD><span dir="ltr">{m.loggers}</span></TD><TD>{date(m.valid_until)}</TD><TD><StatusBadge kind="mapping_status" value={m.status} /></TD></TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function StudyForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.logistics.map");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const zones = useQ3Zones(project.id);
  const mte = useQMte(project.id, { mte_type: "temp_logger", page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ zone_id: "", purpose: "periodic", season: "summer", start: "", end: "", interval: "5" });
  const [loggers, setLoggers] = useState<string[]>([]);
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/mapping-studies", { params: { path: { project_id: project.id } }, body: {
      zone_id: f.zone_id, purpose: f.purpose as S["QMappingPurpose"], season: f.season as S["QSeason"], planned_start: fromLocalInput(f.start), planned_end: fromLocalInput(f.end), interval_minutes: Number(f.interval),
      loggers: loggers.map((m, i) => ({ mte_id: m, position_code: `L${String(i + 1).padStart(2, "0")}` })),
    } as never })));
    if (out) { onDone(); router.push(`/quality/mapping/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-map-form">
      <MutationError error={error} />
      <FormField id="mp-zone" label={t("zone")}><Select id="mp-zone" value={f.zone_id} onChange={(e) => setF({ ...f, zone_id: e.target.value })}><option value="">{tc("select")}</option>{(zones.data ?? []).map((z) => <option key={z.zone_id} value={z.zone_id}>{z.code}</option>)}</Select></FormField>
      <FormField id="mp-purpose" label={t("purpose")}><Select id="mp-purpose" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>{options("mapping_purpose").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mp-season" label={t("season")}><Select id="mp-season" value={f.season} onChange={(e) => setF({ ...f, season: e.target.value })}>{options("season").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mp-start" label={t("start")}><Input id="mp-start" type="datetime-local" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} dir="ltr" /></FormField>
      <FormField id="mp-end" label={t("end")}><Input id="mp-end" type="datetime-local" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} dir="ltr" /></FormField>
      <FormField id="mp-int" label={t("interval")}><Input id="mp-int" value={f.interval} onChange={(e) => setF({ ...f, interval: e.target.value })} dir="ltr" inputMode="numeric" /></FormField>
      <div className="sm:col-span-3">
        <p className="mb-1 text-sm font-medium">{t("pickLoggers", { n: loggers.length })}</p>
        <div className="flex flex-wrap gap-2">{(mte.data?.items ?? []).map((m) => (
          <label key={m.id} className="flex items-center gap-1 rounded-md border px-2 py-1 text-sm"><input type="checkbox" checked={loggers.includes(m.id)} onChange={(e) => setLoggers((x) => (e.target.checked ? [...x, m.id] : x.filter((y) => y !== m.id)))} /><span className="ltr">{m.mte_no}</span></label>
        ))}</div>
      </div>
      <div className="flex gap-2 sm:col-span-3"><Button disabled={busy || !f.zone_id || !f.start || !f.end || !loggers.length} onClick={() => void save()}>{tc("save")}</Button><Button variant="outline" onClick={onDone}>{tc("cancel")}</Button></div>
    </CardContent></Card>
  );
}

export function MappingDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <Study project={p} id={id} />}</Q3Gate>;
}

function Study({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.map");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const q = useQ3Study(id);
  const { run, busy, error } = useRun();
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const m = q.data;
  if (!m) return null;
  const res = m.results as { loggers?: Record<string, string | number | boolean>[]; hot_spot?: string; cold_spot?: string; zone_min_c?: string; zone_max_c?: string } | null;
  const manage = caps.write("storage.manage");
  return (
    <div data-testid="q3-map-detail" data-status={m.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/mapping" }, { label: m.map_no ?? t("draft") }]} />
      <PageHeader title={<span className="ltr">{m.map_no ?? t("draft")}</span>} badge={<StatusBadge kind="mapping_status" value={m.status} />} />
      <MutationError error={error} />
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("zone")} ltr>{String(m.zone.code)}</FieldItem>
          <FieldItem label={t("purpose")}>{l("mapping_purpose", m.purpose)}</FieldItem>
          <FieldItem label={t("season")}>{l("season", m.season)}</FieldItem>
          <FieldItem label={t("start")}>{dateTime(m.actual_start ?? m.planned_start)}</FieldItem>
          <FieldItem label={t("end")}>{dateTime(m.actual_end ?? m.planned_end)}</FieldItem>
          <FieldItem label={t("interval")}><span dir="ltr">{m.interval_minutes} min</span></FieldItem>
          <FieldItem label={t("loggers")}><span dir="ltr">{m.loggers.length}</span></FieldItem>
          <FieldItem label={t("validUntil")}>{date(m.valid_until)}</FieldItem>
        </FieldList>
        <div className="mt-3 flex flex-wrap gap-2">
          {manage && (m.status === "draft" || m.status === "data_loaded") ? <Button variant="outline" asChild><Link href={`/quality/imports?target=mapping_study&id=${m.id}`}>{t("importData")}</Link></Button> : null}
          {manage && (m.status === "data_loaded" || m.status === "evaluated") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mapping-studies/{study_id}/evaluate", { params: { path: { study_id: id } } })))} data-testid="q3-map-evaluate">{t("evaluate")}</Button> : null}
          {m.can_approve ? <Button disabled={busy || !m.passed} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mapping-studies/{study_id}/approve", { params: { path: { study_id: id } }, body: { decision: "approved" } })))} data-testid="q3-map-approve">{t("approve")}</Button> : null}
          {m.can_approve ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mapping-studies/{study_id}/approve", { params: { path: { study_id: id } }, body: { decision: "returned" } })))}>{t("reject")}</Button> : null}
        </div>
      </CardContent></Card>
      {res?.loggers ? (
        <Card className="mb-4"><CardContent className="p-4" data-testid="q3-map-results">
          <h2 className="mb-2 text-base font-semibold">{t("results")} {m.passed ? <Badge tone="success">{t("pass")}</Badge> : <Badge tone="danger">{t("fail")}</Badge>}</h2>
          <p className="mb-2 text-sm">{t("hot")}: <span className="ltr">{res.hot_spot}</span> · {t("cold")}: <span className="ltr">{res.cold_spot}</span> · <Temp v={res.zone_min_c} /> … <Temp v={res.zone_max_c} /></p>
          <Table compact>
            <THead><TR><TH>{t("position")}</TH><TH>{t("min")}</TH><TH>{t("max")}</TH><TH>{t("mean")}</TH><TH>{t("inRange")}</TH></TR></THead>
            <TBody>{res.loggers.map((r) => (
              <TR key={String(r.position_code)} className={r.in_range === false ? "bg-danger-bg" : ""}><TD className="ltr">{String(r.position_code)}</TD><TD><Temp v={r.min_c as string} /></TD><TD><Temp v={r.max_c as string} /></TD><TD><Temp v={r.mean_c as string} /></TD><TD><span dir="ltr">{String(r.pct_in_range ?? "—")} %</span></TD></TR>
            ))}</TBody>
          </Table>
        </CardContent></Card>
      ) : null}
      <Card><CardContent className="p-4"><h2 className="mb-2 text-base font-semibold">{t("report")}</h2><Attachments ownerType="q_mapping_report" ownerId={id} canUpload={manage} /></CardContent></Card>
    </div>
  );
}
