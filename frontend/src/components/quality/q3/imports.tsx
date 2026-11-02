"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { postImport, useQ3Imports, useQ3Studies, useQ3Trips, useQ3Zones } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ReasonDialog, StatusBadge, qError, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { Q3Gate, fromLocalInput, nowLocal, type Project, type S } from "./common";

export function ImportsPage() {
  return <Q3Gate>{(p) => <Imports project={p} />}</Q3Gate>;
}

type Result = Awaited<ReturnType<typeof postImport>>;

function Imports({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.imp");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const zones = useQ3Zones(project.id);
  const trips = useQ3Trips(project.id, { page_size: 100 });
  const studies = useQ3Studies(project.id);
  const hist = useQ3Imports(project.id, { page_size: 50 });
  const refresh = useRun();
  const [kind, setKind] = useState<S["QImportKind"]>((s.get("target") === "mapping_study" ? "readings" : "readings") as S["QImportKind"]);
  const [ttype, setTtype] = useState<S["QImportTarget"]>((s.get("target") as S["QImportTarget"]) || "point");
  const [target, setTarget] = useState(s.get("id") ?? "");
  const [unit, setUnit] = useState("C");
  const [tz, setTz] = useState("Asia/Riyadh");
  const [fmt, setFmt] = useState("");
  const [asOf, setAsOf] = useState(nowLocal());
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Result | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [voiding, setVoiding] = useState<string | null>(null);
  const site = opts.sites[0]?.value ?? "";
  const points = (zones.data ?? []).flatMap((z) => z.points.map((p) => ({ id: p.id, label: `${z.code} · ${p.code}` })));
  const targets = kind !== "readings" ? (kind === "products" ? [{ id: project.id, label: project.code }] : opts.sites.map((x) => ({ id: x.value, label: x.label })))
    : ttype === "point" ? points : ttype === "trip" ? (trips.data?.items ?? []).map((x) => ({ id: x.id, label: x.trip_no })) : (studies.data ?? []).map((x) => ({ id: x.id, label: x.map_no ?? x.zone_code }));
  const effTarget = kind === "readings" ? target : kind === "products" ? project.id : site;
  const effType: S["QImportTarget"] = kind === "readings" ? ttype : "site";
  const profile = JSON.stringify({ unit, timezone: tz, ...(fmt ? { date_format: fmt } : {}) });
  async function go(prev: boolean) {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const out = await postImport(project.id, { kind, target_type: effType, target_id: effTarget, profile, as_of: kind === "stock_snapshot" || kind === "cycle_count" ? fromLocalInput(asOf) ?? undefined : undefined }, file, prev);
      if (prev) setPreview(out);
      else { setResult(out); setPreview(null); await refresh.run(async () => out, ""); }
    } catch (e) {
      setError(qError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      {caps.write("reading.record") || caps.write("stock.record") ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-import-form">
          <MutationError error={error} />
          <FormField id="im-kind" label={t("kind")}><Select id="im-kind" value={kind} onChange={(e) => { setKind(e.target.value as S["QImportKind"]); setTarget(""); }} data-testid="im-kind">{options("import_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          {kind === "readings" ? (
            <>
              <FormField id="im-ttype" label={t("targetType")}><Select id="im-ttype" value={ttype} onChange={(e) => { setTtype(e.target.value as S["QImportTarget"]); setTarget(""); }} data-testid="im-ttype"><option value="point">{t("point")}</option><option value="trip">{t("trip")}</option><option value="mapping_study">{t("study")}</option></Select></FormField>
              <FormField id="im-target" label={t("target")}><Select id="im-target" value={target} onChange={(e) => setTarget(e.target.value)} data-testid="im-target"><option value="">{tc("select")}</option>{targets.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</Select></FormField>
              <FormField id="im-unit" label={t("unit")}><Select id="im-unit" value={unit} onChange={(e) => setUnit(e.target.value)} data-testid="im-unit"><option value="C">°C</option><option value="F">°F</option></Select></FormField>
              <FormField id="im-tz" label={t("timezone")}><Select id="im-tz" value={tz} onChange={(e) => setTz(e.target.value)} data-testid="im-tz"><option value="Asia/Riyadh">Asia/Riyadh</option><option value="UTC">UTC</option></Select></FormField>
              <FormField id="im-fmt" label={t("dateFormat")} hint={t("dateFormatHint")}><Input id="im-fmt" value={fmt} onChange={(e) => setFmt(e.target.value)} dir="ltr" placeholder="%d/%m/%Y %H:%M" /></FormField>
            </>
          ) : kind === "stock_snapshot" || kind === "cycle_count" ? (
            <FormField id="im-asof" label={t("asOf")}><Input id="im-asof" type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)} dir="ltr" /></FormField>
          ) : null}
          <FormField id="im-file" label={t("file")} className="sm:col-span-2"><Input id="im-file" type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); setResult(null); }} data-testid="im-file" /></FormField>
          <p className="text-sm text-muted-foreground sm:col-span-3">{t(`columns.${kind}`)}</p>
          <div className="flex gap-2 sm:col-span-3">
            <Button variant="outline" disabled={busy || !file} onClick={() => void go(true)} data-testid="im-preview">{t("preview")}</Button>
            <Button disabled={busy || !file || !effTarget} onClick={() => void go(false)} data-testid="im-go">{t("import")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {preview ? (
        <Card className="mb-4"><CardContent className="p-4" data-testid="q3-import-preview">
          <p className="mb-2 text-sm">{t("rowsInFile", { n: preview.rows })} · <span className="ltr">{preview.columns.join(", ")}</span></p>
          <Table compact><TBody>{preview.sample.map((r, i) => <TR key={i}><TD className="ltr text-xs">{JSON.stringify(r.raw)}</TD><TD className="ltr text-xs">{String(r.measured_at ?? "")} {String(r.temperature_c ?? "")} {String(r.error ?? "")}</TD></TR>)}</TBody></Table>
        </CardContent></Card>
      ) : null}
      {result ? (
        <Alert tone={result.rows_rejected ? "warning" : "success"} className="mb-4" data-testid="q3-import-result">
          <p>{t("result", { read: result.rows_read, ok: result.rows_accepted, bad: result.rows_rejected })}</p>
          {result.errors.slice(0, 20).map((e, i) => <p key={i} className="ltr text-xs">#{String(e.row)}: {String(e.reason)}</p>)}
          {result.excursions?.map((x) => <Link key={x.id} className="me-2 underline" href={`/quality/excursions/${x.id}`}>{x.exc_no}</Link>)}
        </Alert>
      ) : null}
      <h2 className="mb-2 text-base font-semibold">{t("history")}</h2>
      {hist.isLoading ? <LoadingState /> : (hist.data?.items ?? []).length ? (
        <Table compact data-testid="q3-import-history">
          <THead><TR><TH>{t("at")}</TH><TH>{t("kind")}</TH><TH>{t("file")}</TH><TH>{t("rows")}</TH><TH>{tc("status")}</TH><TH /></TR></THead>
          <TBody>{(hist.data?.items ?? []).map((b) => (
            <TR key={b.id} data-testid="q3-import-row"><TD>{dateTime(b.imported_at)}</TD><TD>{l("import_kind", b.kind)}</TD><TD className="ltr text-xs">{b.file_name}</TD><TD><span dir="ltr">{b.rows_accepted} / {b.rows_read}</span></TD><TD><StatusBadge kind="import_status" value={b.status} /></TD>
              <TD>{b.voidable && caps.write("quality.void") ? <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(b.id)} data-testid="im-void">{t("void")}</Button> : null}</TD></TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
      <ReasonDialog open={voiding !== null} onOpenChange={(v) => !v && setVoiding(null)} title={t("void")} description={t("voidHint")} confirm={t("void")} testId="q3-void-dialog"
        onSubmit={(text) => refresh.run(() => unwrap(api.POST("/api/v1/quality/imports/{batch_id}/void", { params: { path: { batch_id: voiding ?? "" } }, body: { reason: text } })))} />
    </div>
  );
}
