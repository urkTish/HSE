"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
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
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQMte, useQSuppliers } from "@/lib/api/quality/q0";
import { useQ3Shipments, useQ3Trip, useQ3Trips } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ReasonDialog, StatusBadge, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { AttachmentPick, ChecklistRunner, Q3Gate, SeverityBadge, Temp, type Project, type S } from "./common";

const PAGE_SIZE = 50;

export function TransportListPage() {
  return <Q3Gate>{(p) => <Trips project={p} />}</Q3Gate>;
}

function Trips({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.trp");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const r = useQ3Trips(project.id, { status: (status || null) as S["QTripStatus"] | null, q: s.get("q") || null, page, page_size: PAGE_SIZE });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("transport.record") ? <Button asChild data-testid="q3-trip-new"><Link href="/quality/transport/new"><Plus aria-hidden />{t("new")}</Link></Button> : null} />
      <ListToolbar>
        <SearchFilter id="q3-trip-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v || null, page: null }); }} />
        <SelectFilter id="q3-trip-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("trip_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q3-trip-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("carrier")}</TH><TH>{t("departure")}</TH><TH>{t("shipments")}</TH><TH>{t("flags")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q3-trip-row" data-no={x.trip_no}>
                <TD label={t("no")}><Link href={`/quality/transport/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.trip_no}</Link></TD>
                <TD label={t("carrier")}>{x.carrier?.code ?? t("ownFleet")} <span className="ltr text-xs">{x.plate_text ?? ""}</span></TD>
                <TD label={t("departure")}>{dateTime(x.departed_at ?? x.planned_departure)}</TD>
                <TD label={t("shipments")}><span dir="ltr">{x.shipments}</span></TD>
                <TD label={t("flags")}><div className="flex flex-wrap gap-1">
                  {x.preload_passed === false ? <Badge tone="danger">{t("preloadFailed")}</Badge> : null}
                  {x.overridden ? <Badge tone="warning">{t("overridden")}</Badge> : null}
                  {x.transit_excursions ? <Badge tone="danger">{t("transitExcursion")}</Badge> : null}
                </div></TD>
                <TD label={tc("status")}><StatusBadge kind="trip_status" value={x.status} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

export function TripNewPage() {
  return <Q3Gate>{(p) => <TripNew project={p} />}</Q3Gate>;
}

function TripNew({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.trp");
  const tc = useTranslations("quality.common");
  const opts = useProjectOptions(project.id);
  const ships = useQ3Shipments(project.id, true);
  const sup = useQSuppliers({ page_size: 200 });
  const mte = useQMte(project.id, { mte_type: "temp_logger", page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [carrier, setCarrier] = useState("");
  const [plate, setPlate] = useState("");
  const [setpoint, setSetpoint] = useState("");
  const [logger, setLogger] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/trips", { params: { path: { project_id: project.id } }, body: {
      site_id: opts.sites[0]?.value, carrier_id: carrier || null, plate_text: plate || null,
      compartments: [{ code: "C1", setpoint: setpoint || null }], logger_mte_ids: logger ? [logger] : [],
      shipments: sel.map((id) => ({ shipment_id: id, compartment: "C1" })),
    } as never })));
    if (out) router.push(`/quality/transport/${out.id}`);
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/transport" }, { label: t("new") }]} />
      <PageHeader title={t("new")} />
      <Card><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-trip-form">
        <MutationError error={error} />
        <FormField id="tp-car" label={t("carrier")}><Select id="tp-car" value={carrier} onChange={(e) => setCarrier(e.target.value)}><option value="">{t("ownFleet")}</option>{(sup.data?.items ?? []).filter((s) => s.categories.includes("carrier")).map((s) => <option key={s.id} value={s.id}>{s.supplier_code}</option>)}</Select></FormField>
        <FormField id="tp-plate" label={t("plate")}><Input id="tp-plate" value={plate} onChange={(e) => setPlate(e.target.value)} dir="ltr" /></FormField>
        <FormField id="tp-sp" label={t("setpoint")}><Input id="tp-sp" value={setpoint} onChange={(e) => setSetpoint(e.target.value)} dir="ltr" inputMode="decimal" data-testid="tp-setpoint" /></FormField>
        <FormField id="tp-log" label={t("logger")}><Select id="tp-log" value={logger} onChange={(e) => setLogger(e.target.value)}><option value="">—</option>{(mte.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.mte_no}</option>)}</Select></FormField>
        <div className="sm:col-span-4">
          <p className="mb-2 text-sm font-medium">{t("pickShipments")}</p>
          {(ships.data ?? []).length ? (
            <ul className="divide-y rounded-md border">{(ships.data ?? []).map((s) => (
              <li key={s.id} className="flex items-center gap-2 p-2 text-sm">
                <input type="checkbox" checked={sel.includes(s.id)} onChange={(e) => setSel((x) => (e.target.checked ? [...x, s.id] : x.filter((y) => y !== s.id)))} data-testid="tp-ship" aria-label={s.shipment_ref} />
                <span className="ltr">{s.shipment_ref}</span> · {s.consignee_name} · <span className="ltr text-xs">{s.classes.join(", ")}</span>
              </li>
            ))}</ul>
          ) : <EmptyState message={t("noShipments")} />}
        </div>
        <div className="flex gap-2 sm:col-span-4">
          <Button disabled={busy || !sel.length} onClick={() => void save()} data-testid="tp-save">{t("plan")}</Button>
          <Button variant="outline" asChild><Link href="/quality/transport">{tc("cancel")}</Link></Button>
        </div>
      </CardContent></Card>
    </div>
  );
}

export function TripDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <TripDetail project={p} id={id} />}</Q3Gate>;
}

function TripDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.trp");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Trip(id);
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error } = useRun();
  const [box, setBox] = useState("");
  const [temps, setTemps] = useState<Record<string, { temp_c: string; mte_id: string }>>({});
  const [override, setOverride] = useState(false);
  const [pod, setPod] = useState<{ shipment: string; receiver: string; sig: string } | null>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const tr = q.data;
  if (!tr) return null;
  const rec = caps.write("transport.record");
  const probes = (mte.data?.items ?? []).filter((m) => m.mte_type !== "temp_logger");
  return (
    <div data-testid="q3-trip-detail" data-status={tr.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/transport" }, { label: tr.trip_no }]} />
      <PageHeader title={<span className="ltr">{tr.trip_no}</span>} badge={<StatusBadge kind="trip_status" value={tr.status} />} />
      <MutationError error={error} />
      {tr.readiness?.has_7b ? (
        <Alert tone={tr.readiness.readiness === "ready" ? "success" : "warning"} className="mb-3" data-testid="q3-trip-readiness">
          {t("readiness")}: {String(tr.readiness.readiness)} · {t("preUse")}: {String(tr.readiness.pre_use_today ?? "—")}
        </Alert>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("carrier")}>{tr.carrier?.code ?? t("ownFleet")}</FieldItem>
          <FieldItem label={t("plate")} ltr>{tr.plate_text ?? "—"}</FieldItem>
          <FieldItem label={t("compartments")}>{tr.compartments.map((c) => <span key={String(c.code)} className="me-2"><span className="ltr">{String(c.code)}</span> <Temp v={c.range_min as string | null} /> … <Temp v={c.range_max as string | null} /></span>)}</FieldItem>
          <FieldItem label={t("logger")} ltr>{tr.loggers.map((m) => m?.mte_no).join(", ") || "—"}</FieldItem>
          <FieldItem label={t("departure")}>{dateTime(tr.departed_at ?? tr.planned_departure)}</FieldItem>
          <FieldItem label={t("delivered")}>{dateTime(tr.delivered_at)}</FieldItem>
          <FieldItem label={t("transitData")}>{tr.transit_data ? t("yes") : t("no_")}</FieldItem>
        </FieldList>
      </CardContent></Card>
      {tr.status === "planned" && rec ? (
        <Card className="mb-4"><CardContent className="p-4" data-testid="q3-preload">
          <h2 className="mb-2 text-base font-semibold">{t("preload")}</h2>
          <ChecklistRunner code="QRPL" submitLabel={t("savePreload")} busy={busy}
            extra={
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <FormField id="pl-box" label={t("boxTemp")}><Input id="pl-box" value={box} onChange={(e) => setBox(e.target.value)} dir="ltr" inputMode="decimal" data-testid="pl-box" /></FormField>
                {tr.shipments.map((s) => (
                  <div key={String(s.id)} className="grid grid-cols-2 gap-2 sm:col-span-3">
                    <FormField id={`pl-t-${s.id}`} label={`${t("loadingTemp")} ${s.shipment_ref}`}><Input id={`pl-t-${s.id}`} value={temps[String(s.id)]?.temp_c ?? ""} onChange={(e) => setTemps((x) => ({ ...x, [String(s.id)]: { mte_id: x[String(s.id)]?.mte_id ?? probes[0]?.id ?? "", temp_c: e.target.value } }))} dir="ltr" inputMode="decimal" data-testid="pl-temp" /></FormField>
                    <FormField id={`pl-m-${s.id}`} label={t("probe")}><Select id={`pl-m-${s.id}`} value={temps[String(s.id)]?.mte_id ?? probes[0]?.id ?? ""} onChange={(e) => setTemps((x) => ({ ...x, [String(s.id)]: { temp_c: x[String(s.id)]?.temp_c ?? "", mte_id: e.target.value } }))}>{probes.map((m) => <option key={m.id} value={m.id}>{m.mte_no}</option>)}</Select></FormField>
                  </div>
                ))}
              </div>
            }
            onSubmit={(a) => void run(() => unwrap(api.POST("/api/v1/quality/trips/{trip_id}/preload", { params: { path: { trip_id: id } }, body: {
              answers: a, box_temp_c: box || null,
              loading_temps: tr.shipments.map((s) => ({ shipment_id: s.id, temp_c: temps[String(s.id)]?.temp_c, mte_id: temps[String(s.id)]?.mte_id || probes[0]?.id })),
            } as never })))} />
        </CardContent></Card>
      ) : null}
      {tr.status === "preload_checked" ? (
        <Card className="mb-4"><CardContent className="p-4">
          {tr.preload_passed === false ? <Alert tone="danger" className="mb-2" data-testid="q3-preload-failed">{t("preloadFailedHint")} <span className="ltr">{tr.preload_failures.join(", ")}</span>{!tr.override_allowed ? ` — ${t("noOverride")}` : ""}</Alert> : null}
          <div className="flex flex-wrap gap-2">
            {tr.preload_passed !== false && rec ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/trips/{trip_id}/dispatch", { params: { path: { trip_id: id } }, body: { request_override: false } })))} data-testid="q3-dispatch">{t("dispatch")}</Button> : null}
            {tr.preload_passed === false && tr.override_allowed && tr.can_override ? <Button variant="destructive-outline" onClick={() => setOverride(true)} data-testid="q3-override">{t("override")}</Button> : null}
            {tr.preload_passed === false && tr.override_allowed && !tr.can_override && rec && !tr.override_requested ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/trips/{trip_id}/dispatch", { params: { path: { trip_id: id } }, body: { request_override: true } })))} data-testid="q3-request-override">{t("requestOverride")}</Button> : null}
          </div>
        </CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4">
        <h2 className="mb-2 text-base font-semibold">{t("shipments")}</h2>
        <Table compact data-testid="q3-trip-shipments">
          <THead><TR><TH>{t("shipment")}</TH><TH>{t("consignee")}</TH><TH>{t("pod")}</TH><TH /></TR></THead>
          <TBody>{tr.shipments.map((s) => {
            const p = s.pod as { delivered_at?: string; exceptions?: unknown[] } | null;
            return (
              <TR key={String(s.id)} data-testid="q3-trip-shipment">
                <TD label={t("shipment")} className="ltr">{String(s.shipment_ref)}{s.stopped ? <Badge tone="danger" className="ms-1">{t("stopped")}</Badge> : null}{s.notify_consignee ? <Badge tone="warning" className="ms-1">{t("notifyConsignee")}</Badge> : null}</TD>
                <TD label={t("consignee")}>{String(s.consignee_name)}</TD>
                <TD label={t("pod")}>{p ? <>{dateTime(p.delivered_at)}{p.exceptions?.length ? <Badge tone="warning" className="ms-1">{t("exception")}</Badge> : null}</> : "—"}</TD>
                <TD>{!p && !s.stopped && tr.status === "dispatched" && rec ? <Button size="sm" onClick={() => setPod({ shipment: String(s.id), receiver: "", sig: "" })} data-testid="q3-pod-start">{t("recordPod")}</Button> : null}</TD>
              </TR>
            );
          })}</TBody>
        </Table>
        {pod ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-3" data-testid="q3-pod-form">
            <FormField id="pod-rec" label={t("receiver")}><Input id="pod-rec" value={pod.receiver} onChange={(e) => setPod({ ...pod, receiver: e.target.value })} data-testid="pod-receiver" /></FormField>
            <div className="sm:col-span-2"><p className="mb-1 text-sm">{t("signature")}</p><Attachments ownerType="q_pod" ownerId={id} canUpload hint={t("signatureHint")} /></div>
            <AttachmentPick ownerType="q_pod" ownerId={id} value={pod.sig} onChange={(v) => setPod({ ...pod, sig: v })} label={t("signatureFile")} id="pod-sig" />
            <div className="flex items-end gap-2"><Button disabled={busy || !pod.receiver || !pod.sig} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/quality/trips/{trip_id}/pods", { params: { path: { trip_id: id } }, body: { shipment_id: pod.shipment, receiver_name: pod.receiver, signature_attachment_id: pod.sig } as never })); setPod(null); return o; })} data-testid="pod-save">{t("savePod")}</Button></div>
          </div>
        ) : null}
        {tr.status === "dispatched" && rec ? <Button className="mt-3" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/trips/{trip_id}/deliver", { params: { path: { trip_id: id } } })))} data-testid="q3-deliver">{t("deliver")}</Button> : null}
      </CardContent></Card>
      {tr.excursions.length ? (
        <Card className="mb-4"><CardContent className="p-4">
          <h2 className="mb-2 text-base font-semibold">{t("transitExcursions")}</h2>
          <ul className="text-sm">{tr.excursions.filter((x) => !x.transient).map((x) => <li key={String(x.id)}><Link className="ltr text-primary hover:underline" href={`/quality/excursions/${x.id}`}>{String(x.exc_no)}</Link> <SeverityBadge value={String(x.severity)} label={l("excursion_severity", String(x.severity))} /> <span dir="ltr">{String(x.duration_min)} min</span></li>)}</ul>
        </CardContent></Card>
      ) : null}
      {tr.signoffs.length ? <Card><CardContent className="p-4"><ul className="text-sm">{tr.signoffs.map((s) => <li key={s.id} data-testid="q3-signoff">{s.step} · {ar ? s.text_ar : s.text_en}</li>)}</ul></CardContent></Card> : null}
      <ReasonDialog open={override} onOpenChange={setOverride} title={t("override")} description={t("overrideHint")} confirm={t("dispatch")} testId="q3-override-dialog"
        onSubmit={(text) => run(() => unwrap(api.POST("/api/v1/quality/trips/{trip_id}/dispatch", { params: { path: { trip_id: id } }, body: { override_reason: text, request_override: false } })))} />
    </div>
  );
}
