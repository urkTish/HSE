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
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useAttachments } from "@/lib/api/hse";
import { useQMte } from "@/lib/api/quality/q0";
import { useQ3Excursion, useQ3Excursions } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ReasonDialog, StatusBadge, useQLabels, useRun } from "@/components/quality/q0/common";
import { Q3Gate, SeverityBadge, Temp, type Project, type S } from "./common";

const PAGE_SIZE = 50;

export function ExcursionsListPage() {
  return <Q3Gate>{(p) => <ExcursionsList project={p} />}</Q3Gate>;
}

function ExcursionsList({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.exc");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const sev = s.get("severity") ?? "";
  const kind = s.get("kind") ?? "";
  const transients = s.get("transients") === "1";
  const r = useQ3Excursions(project.id, {
    status: status ? [status as S["QExcursionStatus"]] : null,
    severity: (sev || null) as S["QExcursionSeverity"] | null,
    kind: (kind || null) as S["QExcursionKind"] | null,
    transients,
    page,
    page_size: PAGE_SIZE,
  });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ListToolbar>
        <SelectFilter id="q3-exc-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("excursion_status")} />
        <SelectFilter id="q3-exc-sev" label={t("severity")} value={sev} onChange={(v) => s.set({ severity: v, page: null })} options={options("excursion_severity")} />
        <SelectFilter id="q3-exc-kind" label={t("kind")} value={kind} onChange={(v) => s.set({ kind: v, page: null })} options={options("excursion_kind")} />
        <label className="flex min-h-touch items-center gap-2 text-sm"><input type="checkbox" checked={transients} onChange={(e) => s.set({ transients: e.target.checked ? "1" : null, page: null })} data-testid="q3-exc-transients" />{t("transients")}</label>
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q3-exc-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("where")}</TH><TH>{t("started")}</TH><TH>{t("duration")}</TH><TH>{t("peak")}</TH><TH>{t("severity")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q3-exc-row" data-no={x.exc_no ?? ""} data-severity={x.severity}>
                <TD label={t("no")}>{x.exc_no ? <Link href={`/quality/excursions/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.exc_no}</Link> : <span className="text-muted-foreground">{t("transient")}</span>}</TD>
                <TD label={t("where")}><span className="ltr">{x.zone?.code ?? (x.trip_id ? t("trip") : "—")}</span> · {l("storage_class", x.storage_class)}</TD>
                <TD label={t("started")}>{dateTime(x.started_at)}</TD>
                <TD label={t("duration")}><span dir="ltr">{x.duration_min} min{x.ended_at ? "" : " …"}</span>{x.data_gap ? <Badge tone="warning" className="ms-1">{t("dataGap")}</Badge> : null}</TD>
                <TD label={t("peak")}><Temp v={x.peak_value} unit={unitOf(x.kind)} /> <span className="text-xs text-muted-foreground" dir="ltr">(+{x.max_deviation})</span></TD>
                <TD label={t("severity")}><SeverityBadge value={x.severity} label={l("excursion_severity", x.severity)} />{!x.acknowledged && x.exc_no ? <Badge tone="danger" className="ms-1">{t("unack")}</Badge> : null}</TD>
                <TD label={tc("status")}><StatusBadge kind="excursion_status" value={x.status} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

/** Humidity excursions are in %RH, the others in °C (D-352). */
function unitOf(kind: string): string {
  return kind === "humidity" ? "%RH" : "°C";
}

export function ExcursionDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <ExcursionDetail project={p} id={id} />}</Q3Gate>;
}

type ImpactRow = { hold_line_id: string; decision: string; justification: string; evidence_attachment_id: string; owner_decision_attachment_id: string; owner_contact_name: string };

function ExcursionDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.exc");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Excursion(id);
  const { run, busy, error } = useRun();
  const [cause, setCause] = useState("");
  const [closing, setClosing] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [rows, setRows] = useState<Record<string, ImpactRow>>({});
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const a = new Set(x.allowed_actions);
  const row = (ln: S["Q3ImpactLineRead"]): ImpactRow =>
    rows[ln.hold_line.id] ?? {
      hold_line_id: ln.hold_line.id,
      decision: ln.decision ?? "release",
      justification: ln.justification ?? "",
      evidence_attachment_id: ln.evidence_attachment_id ?? "",
      owner_decision_attachment_id: ln.owner_decision_attachment_id ?? "",
      owner_contact_name: ln.owner_contact_name ?? "",
    };
  const setRow = (ln: S["Q3ImpactLineRead"], patch: Partial<ImpactRow>) => setRows((r) => ({ ...r, [ln.hold_line.id]: { ...row(ln), ...patch } }));
  const lines = () => x.impact_lines.map((ln) => Object.fromEntries(Object.entries(row(ln)).filter(([, v]) => v !== "")));
  return (
    <div data-testid="q3-exc-detail" data-status={x.status} data-severity={x.severity}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/excursions" }, { label: x.exc_no ?? t("transient") }]} />
      <PageHeader title={<span className="ltr">{x.exc_no ?? t("transient")}</span>} badge={<><SeverityBadge value={x.severity} label={l("excursion_severity", x.severity)} /> <StatusBadge kind="excursion_status" value={x.status} /></>}
        actions={a.has("acknowledge") && !x.acknowledged_at ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/excursions/{exc_id}/acknowledge", { params: { path: { exc_id: id } } })))} data-testid="q3-exc-ack">{t("ack")}</Button> : null} />
      <MutationError error={error} />
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("where")}>{x.zone ? <Link className="ltr text-primary hover:underline" href={`/quality/storage/${x.zone.id}`}>{x.zone.code}</Link> : x.trip ? <Link className="ltr text-primary hover:underline" href={`/quality/transport/${x.trip.id}`}>{x.trip.trip_no}</Link> : "—"}</FieldItem>
          <FieldItem label={t("class")}>{l("storage_class", x.storage_class)}</FieldItem>
          <FieldItem label={t("range")}><Temp v={x.range_min} unit={unitOf(x.kind)} /> … <Temp v={x.range_max} unit={unitOf(x.kind)} /></FieldItem>
          <FieldItem label={t("started")}>{dateTime(x.started_at)}</FieldItem>
          <FieldItem label={t("ended")}>{x.ended_at ? dateTime(x.ended_at) : t("ongoing")}</FieldItem>
          <FieldItem label={t("duration")}><span dir="ltr" data-testid="q3-exc-duration">{x.duration_min} min</span></FieldItem>
          <FieldItem label={t("peak")}><Temp v={x.peak_value} unit={unitOf(x.kind)} /> {x.peak_point ? <span className="ltr text-xs">({x.peak_point})</span> : null}</FieldItem>
          <FieldItem label={t("maxDev")}><span dir="ltr">{x.max_deviation} {unitOf(x.kind)}</span></FieldItem>
          <FieldItem label={t("degreeMinutes")}><span dir="ltr" data-testid="q3-exc-dm">{x.degree_minutes} {unitOf(x.kind)}·min</span></FieldItem>
          <FieldItem label={t("cause")}>{x.cause ? l("excursion_cause", x.cause) : "—"}</FieldItem>
          <FieldItem label={t("ncr")}>{x.ncr ? <Link className="ltr text-primary hover:underline" href={`/quality/ncrs/${x.ncr.id}`}>{x.ncr.ncr_no ?? t("ncrDraft")}</Link> : "—"}</FieldItem>
          <FieldItem label={t("hold")}>{x.hold ? <Link className="ltr text-primary hover:underline" href={`/quality/holds/${x.hold.id}`}>{x.hold.hold_no}</Link> : "—"}</FieldItem>
        </FieldList>
        {x.data_gap ? <Alert tone="warning" className="mt-3">{t("dataGapHint")}</Alert> : null}
        {x.impact_required && x.status !== "closed" && x.status !== "dismissed" ? <Alert tone="info" className="mt-3" data-testid="q3-exc-impact-required">{t("impactRequired")}</Alert> : null}
      </CardContent></Card>
      {a.has("cause") ? (
        <Card className="mb-4"><CardContent className="flex flex-wrap items-end gap-2 p-4">
          <FormField id="x-cause" label={t("cause")}><Select id="x-cause" value={cause || x.cause || ""} onChange={(e) => setCause(e.target.value)} data-testid="x-cause"><option value="">{tc("select")}</option>{options("excursion_cause").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <Button disabled={busy || !(cause || x.cause)} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/excursions/{exc_id}/cause", { params: { path: { exc_id: id } }, body: { cause: (cause || x.cause) as S["QExcursionCause"] } })))} data-testid="x-cause-save">{t("saveCause")}</Button>
          {a.has("close_no_impact") ? <Button variant="outline" onClick={() => setClosing(true)} data-testid="x-close">{t("closeNoImpact")}</Button> : null}
          {a.has("dismiss") ? <Button variant="destructive-outline" onClick={() => setDismissing(true)} data-testid="x-dismiss">{t("dismiss")}</Button> : null}
        </CardContent></Card>
      ) : null}
      {x.impact_lines.length ? (
        <Card className="mb-4"><CardContent className="p-4" data-testid="q3-impact">
          <h2 className="mb-2 text-base font-semibold">{t("impact")}</h2>
          <Table>
            <THead><TR><TH>{t("line")}</TH><TH>{t("owner")}</TH><TH>{t("decision")}</TH><TH>{t("justification")}</TH><TH>{t("ownerFile")}</TH></TR></THead>
            <TBody>{x.impact_lines.map((ln) => {
              const r = row(ln);
              const editable = a.has("impacts");
              return (
                <TR key={ln.hold_line.id} data-testid="q3-impact-row">
                  <TD label={t("line")}><span className="ltr">{ln.hold_line.sku} · {ln.hold_line.batch}</span> · <span dir="ltr">{ln.hold_line.qty}</span></TD>
                  <TD label={t("owner")}>{ln.hold_line.owner?.code ?? "—"}{ln.hold_line.owner?.owner_release_approval ? <Badge tone="info" className="ms-1">{t("ownerDecides")}</Badge> : null}</TD>
                  <TD label={t("decision")}>{editable ? <Select value={r.decision} onChange={(e) => setRow(ln, { decision: e.target.value })} data-testid="impact-decision">{options("impact_decision").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select> : l("impact_decision", ln.decision)}</TD>
                  <TD label={t("justification")}>{editable ? <Textarea rows={2} value={r.justification} onChange={(e) => setRow(ln, { justification: e.target.value })} data-testid="impact-justification" /> : ln.justification ?? "—"}</TD>
                  <TD label={t("ownerFile")}>{editable && x.hold ? <HoldFile holdId={x.hold.id} value={r.owner_decision_attachment_id} onChange={(v) => setRow(ln, { owner_decision_attachment_id: v })} /> : ln.owner_decision_attachment_id ? t("onFile") : "—"}</TD>
                </TR>
              );
            })}</TBody>
          </Table>
          {a.has("impacts") && x.hold ? (
            <>
              <p className="mt-3 text-sm text-muted-foreground">{t("filesHint")}</p>
              <Attachments ownerType="q_hold" ownerId={x.hold.id} canUpload />
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.PUT("/api/v1/quality/excursions/{exc_id}/impacts", { params: { path: { exc_id: id } }, body: { lines: lines() } as never })))} data-testid="impact-save">{tc("save")}</Button>
                {a.has("assess") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/excursions/{exc_id}/assess", { params: { path: { exc_id: id } }, body: { lines: lines() } as never })))} data-testid="impact-assess">{t("assess")}</Button> : null}
              </div>
            </>
          ) : null}
        </CardContent></Card>
      ) : null}
      {x.signoffs.length ? (
        <Card><CardContent className="p-4"><h2 className="mb-2 text-base font-semibold">{t("signoffs")}</h2>
          <ul className="text-sm">{x.signoffs.map((s) => <li key={s.id} data-testid="q3-signoff">{s.step} · {s.decision} · {s.text_en} · {dateTime(s.signed_at)}</li>)}</ul>
        </CardContent></Card>
      ) : null}
      <ReasonDialog open={closing} onOpenChange={setClosing} title={t("closeNoImpact")} label={t("noImpactNote")} confirm={t("close")} testId="q3-exc-close-dialog"
        onSubmit={(text) => run(() => unwrap(api.POST("/api/v1/quality/excursions/{exc_id}/close", { params: { path: { exc_id: id } }, body: { note: text } })))} />
      {dismissing ? <DismissForm project={project} id={id} onDone={() => setDismissing(false)} /> : null}
    </div>
  );
}

function HoldFile({ holdId, value, onChange }: { holdId: string; value: string; onChange: (v: string) => void }) {
  const t = useTranslations("quality.logistics.common");
  const files = useAttachments("q_hold", holdId);
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} data-testid="impact-owner-file">
      <option value="">{t("noFile")}</option>
      {(files.data?.items ?? []).map((f) => <option key={f.id} value={f.id}>{f.file_name}</option>)}
    </Select>
  );
}

function DismissForm({ project, id, onDone }: { project: Project; id: string; onDone: () => void }) {
  const t = useTranslations("quality.logistics.exc");
  const tc = useTranslations("quality.common");
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error } = useRun();
  const [kind, setKind] = useState<"calibration_check" | "second_instrument">("calibration_check");
  const [m, setM] = useState("");
  const [m2, setM2] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  return (
    <Card className="mt-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-2" data-testid="q3-dismiss-form">
      <MutationError error={error} />
      <Alert tone="warning" className="sm:col-span-2">{t("dismissHint")}</Alert>
      <FormField id="ds-kind" label={t("evidenceKind")}><Select id="ds-kind" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}><option value="calibration_check">{t("calibrationCheck")}</option><option value="second_instrument">{t("secondInstrument")}</option></Select></FormField>
      <FormField id="ds-mte" label={t("faulty")}><Select id="ds-mte" value={m} onChange={(e) => setM(e.target.value)} data-testid="ds-mte"><option value="">{tc("select")}</option>{(mte.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.mte_no}</option>)}</Select></FormField>
      {kind === "calibration_check" ? <FormField id="ds-err" label={t("errorC")}><Input id="ds-err" value={err} onChange={(e) => setErr(e.target.value)} dir="ltr" data-testid="ds-error" /></FormField> : <FormField id="ds-m2" label={t("secondInstrument")}><Select id="ds-m2" value={m2} onChange={(e) => setM2(e.target.value)}><option value="">{tc("select")}</option>{(mte.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.mte_no}</option>)}</Select></FormField>}
      <FormField id="ds-note" label={tc("reason")} hint={tc("minChars", { n: 20 })} className="sm:col-span-2"><Textarea id="ds-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-testid="ds-note" /></FormField>
      <div className="flex gap-2 sm:col-span-2">
        <Button variant="destructive" disabled={busy || !m || note.trim().length < 20} onClick={() => void run(async () => {
          const o = await unwrap(api.POST("/api/v1/quality/excursions/{exc_id}/dismiss", { params: { path: { exc_id: id } }, body: { evidence_kind: kind, mte_id: m, second_mte_id: m2 || null, error_c: err || null, note } as never }));
          onDone();
          return o;
        })} data-testid="ds-save">{t("dismiss")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}
