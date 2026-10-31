"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQMte } from "@/lib/api/quality/q0";
import { useQ3Zone, useQ3ZoneReport, useQ3Zones } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { ReasonDialog, useBilingual, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { LIVE_TONE, Q3Gate, Section, Temp, clean, fromLocalInput, nowLocal, useForm, type Project, type S } from "./common";

export function StorageListPage() {
  return <Q3Gate>{(p) => <StorageList project={p} />}</Q3Gate>;
}

function StorageList({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.sto");
  const { l } = useQLabels();
  const name = useBilingual();
  const caps = useQCaps(project.id);
  const z = useQ3Zones(project.id);
  const [adding, setAdding] = useState(false);
  const zones = z.data ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("storage.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-zone-new"><Plus aria-hidden />{t("newZone")}</Button> : null} />
      {adding ? <ZoneForm project={project} onDone={() => setAdding(false)} /> : null}
      {z.isLoading ? <LoadingState /> : z.isError ? <ErrorState error={z.error} onRetry={() => z.refetch()} /> : zones.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="q3-zones">
          {zones.map((x) => (
            <Link key={x.zone_id} href={`/quality/storage/${x.zone_id}`} data-testid="q3-zone-card" data-code={x.code} data-status={x.live_status ?? ""}
              className="block rounded-lg border p-4 hover:border-primary">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold"><span className="ltr">{x.code}</span> · {name(x.name_en, x.name_ar)}</p>
                <Badge tone={LIVE_TONE[x.live_status ?? ""] ?? "neutral"}>{t(`live.${x.live_status ?? "in_range"}`)}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{l("storage_class", x.storage_class)} · <Temp v={x.temp_min} /> … <Temp v={x.temp_max} /></p>
              <p className="mt-1 text-xs text-muted-foreground">{l("mapping_state", x.mapping_state)}{x.mapped_until ? <> · <span dir="ltr">{x.mapped_until}</span></> : null} · {t("points", { n: x.points.length })}</p>
            </Link>
          ))}
        </div>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function ZoneForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.logistics.sto");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ zone_id: "", storage_class: "chilled", role: "storage", setpoint: "" });
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-zone-form">
      <MutationError error={error} />
      <FormField id="z-zone" label={t("zone")} required><Select id="z-zone" value={f.zone_id} onChange={set("zone_id")}><option value="">{tc("select")}</option>{opts.zones.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="z-class" label={t("class")}><Select id="z-class" value={f.storage_class} onChange={set("storage_class")}>{options("storage_class").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="z-role" label={t("role")}><Select id="z-role" value={f.role} onChange={set("role")}>{options("zone_role").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="z-sp" label={t("setpoint")}><Input id="z-sp" value={f.setpoint} onChange={set("setpoint")} dir="ltr" inputMode="decimal" /></FormField>
      <div className="flex gap-2 sm:col-span-4">
        <Button disabled={busy || !f.zone_id} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/storage-zones", { params: { path: { project_id: project.id } }, body: clean(f) as never })); onDone(); return o; })}>{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

// ---- zone detail ---------------------------------------------------------------------------------

export function ZoneDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <ZoneDetail project={p} id={id} />}</Q3Gate>;
}

function iso(d: Date) {
  return d.toISOString();
}

function ZoneDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.sto");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const name = useBilingual();
  const caps = useQCaps(project.id);
  const q = useQ3Zone(id);
  const [days, setDays] = useState(7);
  const range = useMemo(() => {
    const end = new Date();
    return { start: iso(new Date(end.getTime() - days * 86400_000)), end: iso(end) };
  }, [days]);
  const rep = useQ3ZoneReport(id, range.start, range.end);
  const { dateTime } = useFormatters(project.id);
  const { run, busy, error } = useRun();
  const [edit, setEdit] = useState(false);
  const [note, setNote] = useState<"" | "layout" | "hvac">("");
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const z = q.data;
  if (!z) return null;
  const manage = caps.write("storage.manage");
  return (
    <div data-testid="q3-zone-detail" data-code={z.code}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/storage" }, { label: z.code }]} />
      <PageHeader title={<><span className="ltr">{z.code}</span> · {name(z.name_en, z.name_ar)}</>} badge={<Badge tone={LIVE_TONE[z.live_status ?? ""] ?? "neutral"}>{t(`live.${z.live_status ?? "in_range"}`)}</Badge>}
        actions={manage ? <div className="flex gap-2"><Button variant="outline" onClick={() => setEdit((x) => !x)} data-testid="q3-zone-edit">{t("edit")}</Button><Button variant="outline" onClick={() => setNote("layout")}>{t("changeNote")}</Button></div> : null} />
      <MutationError error={error} />
      {z.mapping_state !== "mapped" ? <Alert tone="warning" className="mb-3" data-testid="q3-zone-not-mapped">{l("mapping_state", z.mapping_state)}{z.remap_reason ? ` (${z.remap_reason})` : ""}</Alert> : null}
      {edit ? <ZoneEdit zone={z} onDone={() => setEdit(false)} /> : (
        <Card className="mb-4"><CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("class")}>{l("storage_class", z.storage_class)}</FieldItem>
            <FieldItem label={t("range")}><Temp v={z.temp_min} /> … <Temp v={z.temp_max} /></FieldItem>
            <FieldItem label={t("setpoint")}><Temp v={z.setpoint} /></FieldItem>
            <FieldItem label={t("alarmDelay")}><span dir="ltr">{z.alarm_delay_minutes} min</span></FieldItem>
            <FieldItem label={t("bands")}><span dir="ltr">d1 {z.d1} · d2 {z.d2} °C · t1 {z.t1} · t2 {z.t2} min</span></FieldItem>
            <FieldItem label={t("mapping")}>{l("mapping_state", z.mapping_state)} {z.mapped_until ? <span dir="ltr">· {z.mapped_until}</span> : null}</FieldItem>
          </FieldList>
        </CardContent></Card>
      )}
      <Section title={t("profile")} testId="q3-zone-chart"
        actions={<Select value={String(days)} onChange={(e) => setDays(Number(e.target.value))} className="w-32">{[1, 7, 30].map((d) => <option key={d} value={d}>{t("lastDays", { n: d })}</option>)}</Select>}>
        {rep.isLoading ? <LoadingState rows={2} /> : rep.data ? (
          <>
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label={t("coverage")} value={rep.data.coverage_pct} unit="%" />
              <Stat label={t("tor")} value={rep.data.tor_pct} unit="%" />
              <Stat label={t("outMinutes")} value={rep.data.out_minutes} />
              <Stat label={t("gaps")} value={rep.data.gaps.length} />
            </div>
            <ProfileChart report={rep.data} />
            {rep.data.gaps.length ? (
              <ul className="mt-2 space-y-1 text-sm" data-testid="q3-gaps">
                {rep.data.gaps.map((g) => (
                  <li key={String(g.from)}>{t("gapRow", { from: dateTime(String(g.from)), to: dateTime(String(g.to)), n: Number(g.minutes) })}</li>
                ))}
              </ul>
            ) : null}
            {rep.data.series.some((s) => s.mkt) ? (
              <p className="mt-2 text-sm" data-testid="q3-mkt">{t("mkt")}: {rep.data.series.filter((s) => s.mkt).map((s) => <span key={String(s.code)} className="me-3"><span className="ltr">{String(s.code)}</span> <Temp v={(s.mkt as { mkt_c: string }).mkt_c} />{(s.mkt as { warning?: string }).warning ? <Badge tone="danger" className="ms-1">{t("mktAbove")}</Badge> : null}</span>)}</p>
            ) : null}
          </>
        ) : null}
      </Section>
      <Section title={t("pointsTitle")} actions={manage ? <AddPoint zoneId={id} /> : null}>
        <Table compact data-testid="q3-points">
          <THead><TR><TH>{t("point")}</TH><TH>{t("position")}</TH><TH>{t("interval")}</TH><TH>{t("logger")}</TH><TH /></TR></THead>
          <TBody>{z.points.map((pt) => <PointRow key={pt.id} point={pt} project={project} manage={manage} />)}</TBody>
        </Table>
      </Section>
      <ReasonDialog open={note !== ""} onOpenChange={(v) => !v && setNote("")} title={t("changeNote")} description={t("changeNoteHint")} confirm={tc("save")} testId="q3-change-note"
        onSubmit={(text) => run(() => unwrap(api.POST("/api/v1/quality/storage-zones/{zone_id}/change-notes", { params: { path: { zone_id: id } }, body: { kind: note || "layout", note: text } })))} />
      {busy ? null : null}
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string | number | null | undefined; unit?: string }) {
  return (
    <div className="rounded-md border p-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-semibold tabular-nums" dir="ltr">{value ?? "—"}{unit && value !== null && value !== undefined ? ` ${unit}` : ""}</p>
    </div>
  );
}

/** C48: readings per point against the range; excursions shaded, gaps marked (inline SVG). */
function ProfileChart({ report }: { report: S["Q3ZoneReport"] }) {
  const t = useTranslations("quality.logistics.sto");
  const W = 800;
  const H = 220;
  const a = new Date(report.start).getTime();
  const b = new Date(report.end).getTime();
  const lo = report.zone.temp_min !== null ? Number(report.zone.temp_min) : null;
  const hi = report.zone.temp_max !== null ? Number(report.zone.temp_max) : null;
  const vals = report.series.flatMap((s) => (s.values as { c: string | null }[]).map((v) => (v.c === null ? NaN : Number(v.c)))).filter((x) => Number.isFinite(x));
  const ymin = Math.min(...vals, lo ?? Infinity, hi ?? Infinity) - 1;
  const ymax = Math.max(...vals, lo ?? -Infinity, hi ?? -Infinity) + 1;
  const x = (tm: number) => ((tm - a) / (b - a || 1)) * W;
  const y = (v: number) => H - ((v - ymin) / (ymax - ymin || 1)) * H;
  const colors = ["var(--color-primary)", "var(--color-info)", "var(--color-warning)", "var(--color-success)"];
  if (!vals.length) return <EmptyState message={t("noReadings")} />;
  return (
    <svg style={{ direction: "ltr" }} viewBox={`0 0 ${W} ${H}`} className="h-56 w-full rounded-md border bg-card" role="img" aria-label={t("profile")}>
      {report.excursions.map((e) => {
        const s = new Date(String(e.started_at)).getTime();
        const en = e.ended_at ? new Date(String(e.ended_at)).getTime() : b;
        return <rect key={String(e.id)} x={x(s)} y={0} width={Math.max(2, x(en) - x(s))} height={H} fill={e.transient ? "var(--color-warning-bg)" : "var(--color-danger-bg)"} />;
      })}
      {report.gaps.map((g, i) => <rect key={i} x={x(new Date(String(g.from)).getTime())} y={H - 6} width={Math.max(2, x(new Date(String(g.to)).getTime()) - x(new Date(String(g.from)).getTime()))} height={6} fill="var(--color-neutral)" />)}
      {lo !== null ? <line x1={0} x2={W} y1={y(lo)} y2={y(lo)} stroke="var(--color-danger)" strokeDasharray="4 4" /> : null}
      {hi !== null ? <line x1={0} x2={W} y1={y(hi)} y2={y(hi)} stroke="var(--color-danger)" strokeDasharray="4 4" /> : null}
      {report.series.map((s, i) => {
        const pts = (s.values as { t: string; c: string | null }[]).filter((v) => v.c !== null).map((v) => `${x(new Date(v.t).getTime()).toFixed(1)},${y(Number(v.c)).toFixed(1)}`).join(" ");
        return <polyline key={String(s.point_id)} points={pts} fill="none" stroke={colors[i % colors.length]} strokeWidth={1.2} />;
      })}
      {hi !== null ? <text x={4} y={y(hi) - 3} fontSize={11} fill="currentColor">{String(hi).replace("-", "−")} °C</text> : null}
      {lo !== null ? <text x={4} y={y(lo) + 12} fontSize={11} fill="currentColor">{String(lo).replace("-", "−")} °C</text> : null}
    </svg>
  );
}

function ZoneEdit({ zone, onDone }: { zone: S["Q3ZoneRead"]; onDone: () => void }) {
  const t = useTranslations("quality.logistics.sto");
  const tc = useTranslations("quality.common");
  const { run, busy, error } = useRun();
  const [f, set] = useForm({
    temp_min: zone.temp_min ?? "", temp_max: zone.temp_max ?? "", setpoint: zone.setpoint ?? "", alarm_delay_minutes: String(zone.alarm_delay_minutes),
    d1: zone.d1, d2: zone.d2, t1: String(zone.t1), t2: String(zone.t2),
  });
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-zone-edit-form">
      <MutationError error={error} />
      {(["temp_min", "temp_max", "setpoint", "alarm_delay_minutes", "d1", "d2", "t1", "t2"] as const).map((k) => (
        <FormField key={k} id={`ze-${k}`} label={t(`f.${k}`)}><Input id={`ze-${k}`} value={f[k]} onChange={set(k)} dir="ltr" inputMode="decimal" data-testid={`ze-${k}`} /></FormField>
      ))}
      <p className="text-sm text-muted-foreground sm:col-span-4">{t("rangeChangeHint")}</p>
      <div className="flex gap-2 sm:col-span-4">
        <Button disabled={busy} onClick={() => void run(async () => {
          const body: Record<string, unknown> = clean(f);
          for (const k of ["alarm_delay_minutes", "t1", "t2"]) if (body[k] !== undefined) body[k] = Number(body[k]);
          const o = await unwrap(api.PATCH("/api/v1/quality/storage-zones/{zone_id}", { params: { path: { zone_id: zone.zone_id } }, body: body as never }));
          onDone();
          return o;
        })} data-testid="ze-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

function AddPoint({ zoneId }: { zoneId: string }) {
  const t = useTranslations("quality.logistics.sto");
  const { run, busy } = useRun();
  const [code, setCode] = useState("");
  return (
    <div className="flex gap-2">
      <Input value={code} onChange={(e) => setCode(e.target.value)} dir="ltr" placeholder={t("pointCode")} className="w-32" data-testid="q3-point-code" />
      <Button size="sm" disabled={busy || !code} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/quality/storage-zones/{zone_id}/points", { params: { path: { zone_id: zoneId } }, body: { code, position: "general" } })); setCode(""); return o; })}>{t("addPoint")}</Button>
    </div>
  );
}

function PointRow({ point, project, manage }: { point: S["Q3PointRead"]; project: Project; manage: boolean }) {
  const t = useTranslations("quality.logistics.sto");
  const { l } = useQLabels();
  const mte = useQMte(project.id, { mte_type: "temp_logger", page_size: 200 });
  const { run, busy } = useRun();
  const [pick, setPick] = useState("");
  const current = point.loggers.find((x) => !x.to) as { mte?: { mte_no: string; cal_status: string } } | undefined;
  return (
    <TR data-testid="q3-point" data-code={point.code}>
      <TD label={t("point")} className="ltr font-medium">{point.code}</TD>
      <TD label={t("position")}>{l("point_position", point.position)}</TD>
      <TD label={t("interval")}><span dir="ltr">{point.interval_minutes} min</span></TD>
      <TD label={t("logger")}>{current?.mte ? <><span className="ltr">{current.mte.mte_no}</span> <Badge tone={current.mte.cal_status === "calibrated" ? "success" : "warning"}>{l("cal_status", current.mte.cal_status)}</Badge></> : "—"}</TD>
      <TD>{manage ? (
        <div className="flex gap-1">
          <Select value={pick} onChange={(e) => setPick(e.target.value)} className="w-36"><option value="">{t("logger")}</option>{(mte.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.mte_no}</option>)}</Select>
          <Button size="sm" variant="outline" disabled={busy || !pick} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/monitoring-points/{point_id}/loggers", { params: { path: { point_id: point.id } }, body: { mte_id: pick } as never })))}>{t("assign")}</Button>
        </div>
      ) : null}</TD>
    </TR>
  );
}

// ---- manual readings (phone) ------------------------------------------------------------------------

export function ReadingsPage() {
  return <Q3Gate>{(p) => <Readings project={p} />}</Q3Gate>;
}

function Readings({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.rdg");
  const tc = useTranslations("quality.common");
  const z = useQ3Zones(project.id);
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error } = useRun();
  const [f, set, setF] = useForm({ zone: "", point: "", temperature_c: "", humidity_pct: "", mte_id: "", measured_at: nowLocal() });
  const [last, setLast] = useState<S["Q3ManualReadingResult"] | null>(null);
  const zones = z.data ?? [];
  const points = zones.find((x) => x.zone_id === f.zone)?.points ?? [];
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/monitoring-points/{point_id}/readings", { params: { path: { point_id: f.point } }, body: { measured_at: fromLocalInput(f.measured_at), temperature_c: f.temperature_c || null, humidity_pct: f.humidity_pct || null, mte_id: f.mte_id || null } as never })));
    if (out) {
      setLast(out);
      setF((x) => ({ ...x, temperature_c: "", humidity_pct: "", measured_at: nowLocal() }));
    }
  }
  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <Card><CardContent className="grid gap-3 p-4" data-testid="q3-reading-form">
        <MutationError error={error} />
        <FormField id="rd-zone" label={t("zone")} required><Select id="rd-zone" value={f.zone} onChange={set("zone")} data-testid="rd-zone"><option value="">{tc("select")}</option>{zones.map((x) => <option key={x.zone_id} value={x.zone_id}>{x.code}</option>)}</Select></FormField>
        <FormField id="rd-point" label={t("point")} required><Select id="rd-point" value={f.point} onChange={set("point")} data-testid="rd-point"><option value="">{tc("select")}</option>{points.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}</Select></FormField>
        <FormField id="rd-temp" label={t("temp")}><Input id="rd-temp" value={f.temperature_c} onChange={set("temperature_c")} dir="ltr" inputMode="decimal" className="text-lg" data-testid="rd-temp" /></FormField>
        <FormField id="rd-rh" label={t("rh")}><Input id="rd-rh" value={f.humidity_pct} onChange={set("humidity_pct")} dir="ltr" inputMode="decimal" /></FormField>
        <FormField id="rd-mte" label={t("probe")} required><Select id="rd-mte" value={f.mte_id} onChange={set("mte_id")} data-testid="rd-mte"><option value="">{tc("select")}</option>{(mte.data?.items ?? []).filter((m) => m.mte_type !== "temp_logger").map((m) => <option key={m.id} value={m.id}>{m.mte_no} · {m.description}</option>)}</Select></FormField>
        <FormField id="rd-at" label={t("at")}><Input id="rd-at" type="datetime-local" value={f.measured_at} onChange={set("measured_at")} dir="ltr" /></FormField>
        <Button size="lg" disabled={busy || !f.point || (!f.temperature_c && !f.humidity_pct)} onClick={() => void save()} data-testid="rd-save">{t("save")}</Button>
        {last ? (
          <Alert tone={last.excursions.length ? "danger" : "success"} data-testid="rd-result">
            {t("saved")} <Temp v={last.reading.temperature_c} />
            {last.excursions.map((x) => <Link key={x.id} href={`/quality/excursions/${x.id}`} className="ms-2 underline">{x.exc_no}</Link>)}
          </Alert>
        ) : null}
      </CardContent></Card>
    </div>
  );
}
