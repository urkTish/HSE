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
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQ3Counts, useQ3Damage, useQ3Fefo, useQ3Metrics, useQ3NearExpiry, useQ3Products, useQ3Throughput } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { StatusBadge, useBilingual, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { Kpi, Q3Gate, clean, fromLocalInput, nowLocal, useForm, usePrevMonth, type Project, type S } from "./common";

const TABS = ["metrics", "expiry", "fefo", "damage", "counts", "throughput"] as const;

export function StockPage() {
  return <Q3Gate>{(p) => <Stock project={p} />}</Q3Gate>;
}

function Stock({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const s = useSearchState();
  const tab = (s.get("tab") as (typeof TABS)[number]) || "expiry";
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
        {TABS.map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => s.set({ tab: k })} data-testid={`q3-stock-tab-${k}`}
            className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${tab === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
            {t(`tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "metrics" ? <Metrics project={project} /> : null}
      {tab === "expiry" ? <NearExpiry project={project} /> : null}
      {tab === "fefo" ? <Fefo project={project} /> : null}
      {tab === "damage" ? <Damage project={project} /> : null}
      {tab === "counts" ? <Counts project={project} /> : null}
      {tab === "throughput" ? <Throughput project={project} /> : null}
    </div>
  );
}

function Metrics({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.kpi");
  const def = usePrevMonth();
  const s = useSearchState();
  // the month is in the URL (?ym=2026-09) so a link or a test opens a fixed month
  const fromUrl = s.get("ym");
  const ym = fromUrl && /^\d{4}-\d{2}$/.test(fromUrl) ? fromUrl : `${def.year}-${String(def.month).padStart(2, "0")}`;
  const setYm = (v: string) => s.set({ ym: v || null });
  const [y = def.year, m = def.month] = ym.split("-").map(Number);
  const q = useQ3Metrics(project.id, y, m);
  const d = q.data;
  return (
    <div data-testid="q3-metrics">
      <FormField id="km-month" label={t("month")} className="mb-3 w-48"><Input id="km-month" type="month" value={ym} onChange={(e) => setYm(e.target.value)} dir="ltr" /></FormField>
      {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : d ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <Kpi label={t("k160")} value={d.k160.value as string | null} unit="%" testId="k160" />
          <Kpi label={t("k161")} value={d.k161.value as string | null} testId="k161" />
          <Kpi label={t("k162")} value={d.k162.value as string | null} unit="%" testId="k162" />
          <Kpi label={t("coverage")} value={d.k162.coverage_pct as string | null} unit="%" />
          <Kpi label={t("k163")} value={d.k163.value as string | null} unit="%" testId="k163" />
          <Kpi label={t("k164")} value={d.k164.value as string | null} unit="%" testId="k164" />
          <Kpi label={t("k165")} value={d.k165.value as string | null} unit="%" testId="k165" />
          <Kpi label={t("k166")} value={d.k166.value as string | null} unit="%" testId="k166" />
          <Kpi label={t("k167")} value={d.k167.value as string | null} unit="%" testId="k167" />
          <Kpi label={t("k168")} value={d.k168.value as string | null} unit="%" testId="k168" />
        </div>
      ) : null}
    </div>
  );
}

function NearExpiry({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3NearExpiry(project.id);
  const { run, busy, error } = useRun();
  const [sel, setSel] = useState<string[]>([]);
  const items = q.data?.items ?? [];
  const owners = Array.from(new Set(items.map((x) => x.owner?.code ?? "—")));
  return (
    <div data-testid="q3-near-expiry">
      <MutationError error={error} />
      {q.data?.snapshots.map((s) => <p key={s.id} className="mb-2 text-sm text-muted-foreground">{t("snapshotAsOf")} {dateTime(s.as_of)}</p>)}
      {q.isLoading ? <LoadingState /> : items.length ? owners.map((o) => (
        <Card key={o} className="mb-3"><CardContent className="p-4">
          <h3 className="mb-2 font-semibold">{o}</h3>
          <Table compact>
            <THead><TR><TH /><TH>{t("sku")}</TH><TH>{t("batch")}</TH><TH>{t("expiry")}</TH><TH>{t("daysLeft")}</TH><TH>{t("location")}</TH><TH>{t("qty")}</TH><TH /></TR></THead>
            <TBody>{items.filter((x) => (x.owner?.code ?? "—") === o).map((x) => (
              <TR key={x.stock_line_id} data-testid="q3-expiry-row" data-kind={x.kind} data-batch={x.batch}>
                <TD>{!x.on_hold ? <input type="checkbox" checked={sel.includes(x.stock_line_id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, x.stock_line_id] : s.filter((y) => y !== x.stock_line_id)))} aria-label={x.batch} /> : null}</TD>
                <TD label={t("sku")} className="ltr">{x.sku}</TD>
                <TD label={t("batch")} className="ltr">{x.batch}</TD>
                <TD label={t("expiry")} className="ltr">{x.expiry_date}</TD>
                <TD label={t("daysLeft")}><span dir="ltr">{x.days_left}</span></TD>
                <TD label={t("location")} className="ltr">{x.location}</TD>
                <TD label={t("qty")}><span dir="ltr">{x.qty}</span></TD>
                <TD>{x.kind === "expired" ? <Badge tone="danger">{t("expired")}</Badge> : <Badge tone="warning">{t("near")}</Badge>}{x.on_hold ? <Badge tone="info" className="ms-1">{t("onHold")}</Badge> : null}</TD>
              </TR>
            ))}</TBody>
          </Table>
        </CardContent></Card>
      )) : <EmptyState message={t("noExpiry")} />}
      {caps.write("hold.manage") && sel.length ? <Button disabled={busy} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/near-expiry/hold", { params: { path: { project_id: project.id } }, body: { stock_line_ids: sel } })); setSel([]); return o; })} data-testid="q3-expiry-hold">{t("placeHold", { n: sel.length })}</Button> : null}
    </div>
  );
}

function Fefo({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const name = useBilingual();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const products = useQ3Products(project.id);
  const list = useQ3Fefo(project.id, { page_size: 50 });
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ product_id: "", picked_batch: "", picked_expiry: "", location: "", order_ref: "", exception_reason: "", exception_note: "" });
  const [last, setLast] = useState<S["Q3FefoRead"] | null>(null);
  return (
    <div>
      {caps.write("stock.record") ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-fefo-form">
          <MutationError error={error} />
          <FormField id="ff-prod" label={t("product")} required><Select id="ff-prod" value={f.product_id} onChange={set("product_id")} data-testid="ff-product"><option value="">{tc("select")}</option>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.sku} — {name(p.description_en, p.description_ar)}</option>)}</Select></FormField>
          <FormField id="ff-batch" label={t("pickedBatch")} required><Input id="ff-batch" value={f.picked_batch} onChange={set("picked_batch")} dir="ltr" data-testid="ff-batch" /></FormField>
          <FormField id="ff-exp" label={t("pickedExpiry")}><Input id="ff-exp" type="date" value={f.picked_expiry} onChange={set("picked_expiry")} dir="ltr" data-testid="ff-expiry" /></FormField>
          <FormField id="ff-order" label={t("order")}><Input id="ff-order" value={f.order_ref} onChange={set("order_ref")} dir="ltr" /></FormField>
          <FormField id="ff-exc" label={t("exception")}><Select id="ff-exc" value={f.exception_reason} onChange={set("exception_reason")}><option value="">—</option>{options("fefo_exception").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          {f.exception_reason === "other" ? <FormField id="ff-note" label={tc("reason")}><Input id="ff-note" value={f.exception_note} onChange={set("exception_note")} /></FormField> : null}
          <div className="sm:col-span-3">
            <Button disabled={busy || !f.product_id || !f.picked_batch} onClick={() => void run(async () => {
              const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/fefo-checks", { params: { path: { project_id: project.id } }, body: { ...clean(f), site_id: opts.sites[0]?.value } as never }));
              setLast(o);
              return o;
            })} data-testid="ff-save">{t("check")}</Button>
          </div>
          {last ? <Alert tone={last.counts_compliant ? "success" : "danger"} className="sm:col-span-3" data-testid="ff-result" data-result={last.result}>{l("fefo_result", last.result)} · {t("eligible")} <span className="ltr">{last.eligible_batch ?? "—"} {last.eligible_earliest ?? ""}</span></Alert> : null}
        </CardContent></Card>
      ) : null}
      <Table compact data-testid="q3-fefo-table">
        <THead><TR><TH>{t("no")}</TH><TH>{t("at")}</TH><TH>{t("product")}</TH><TH>{t("pickedBatch")}</TH><TH>{t("eligible")}</TH><TH>{t("result")}</TH></TR></THead>
        <TBody>{(list.data?.items ?? []).map((x) => (
          <TR key={x.id}><TD className="ltr">{x.check_no}</TD><TD>{dateTime(x.checked_at)}</TD><TD className="ltr">{x.product?.sku}</TD><TD className="ltr">{x.picked_batch} {x.picked_expiry ?? ""}</TD><TD className="ltr">{x.eligible_batch ?? "—"} {x.eligible_earliest ?? ""}</TD><TD><StatusBadge kind="fefo_result" value={x.result} /></TD></TR>
        ))}</TBody>
      </Table>
    </div>
  );
}

function Damage({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const name = useBilingual();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const products = useQ3Products(project.id);
  const list = useQ3Damage(project.id, { page_size: 50 });
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ product_id: "", batch: "", qty: "", stage: "storage", cause: "forklift", location: "", note: "", owner_notified_at: "" });
  const [spot, setSpot] = useState(false);
  return (
    <div>
      {caps.write("stock.record") ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-damage-form">
          <MutationError error={error} />
          <FormField id="dm-prod" label={t("product")} required className="sm:col-span-2"><Select id="dm-prod" value={f.product_id} onChange={set("product_id")} data-testid="dm-product"><option value="">{tc("select")}</option>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.sku} — {name(p.description_en, p.description_ar)}</option>)}</Select></FormField>
          <FormField id="dm-batch" label={t("batch")} required><Input id="dm-batch" value={f.batch} onChange={set("batch")} dir="ltr" data-testid="dm-batch" /></FormField>
          <FormField id="dm-qty" label={t("qty")} required><Input id="dm-qty" value={f.qty} onChange={set("qty")} dir="ltr" inputMode="decimal" data-testid="dm-qty" /></FormField>
          <FormField id="dm-stage" label={t("stage")}><Select id="dm-stage" value={f.stage} onChange={set("stage")}>{options("damage_stage").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="dm-cause" label={t("cause")}><Select id="dm-cause" value={f.cause} onChange={set("cause")}>{options("damage_cause").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="dm-loc" label={t("location")}><Input id="dm-loc" value={f.location} onChange={set("location")} dir="ltr" /></FormField>
          <label className="flex min-h-touch items-center gap-2 text-sm"><input type="checkbox" checked={spot} onChange={(e) => setSpot(e.target.checked)} />{t("destroyedOnSpot")}</label>
          {spot ? <FormField id="dm-own" label={t("ownerNotified")}><Input id="dm-own" type="datetime-local" value={f.owner_notified_at || nowLocal()} onChange={set("owner_notified_at")} dir="ltr" /></FormField> : null}
          <div className="sm:col-span-4"><Button disabled={busy || !f.product_id || !f.batch || !f.qty} onClick={() => void run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/damage-reports", { params: { path: { project_id: project.id } }, body: { ...clean({ ...f, owner_notified_at: "" }), site_id: opts.sites[0]?.value, destroyed_on_spot: spot, owner_notified_at: spot ? fromLocalInput(f.owner_notified_at || nowLocal()) : null } as never })))} data-testid="dm-save">{t("report")}</Button></div>
          <p className="text-sm text-muted-foreground sm:col-span-4">{t("damageHint")}</p>
        </CardContent></Card>
      ) : null}
      <Table compact data-testid="q3-damage-table">
        <THead><TR><TH>{t("no")}</TH><TH>{t("at")}</TH><TH>{t("product")}</TH><TH>{t("qty")}</TH><TH>{t("cause")}</TH><TH>{t("hold")}</TH></TR></THead>
        <TBody>{(list.data?.items ?? []).map((x) => (
          <TR key={x.id}><TD className="ltr">{x.dmg_no}</TD><TD>{dateTime(x.reported_at)}</TD><TD className="ltr">{x.product?.sku} · {x.batch}</TD><TD><span dir="ltr">{x.qty}</span></TD><TD>{l("damage_cause", x.cause)}</TD><TD>{x.hold_id ? <Link className="text-primary hover:underline" href={`/quality/holds/${x.hold_id}`}>{t("hold")}</Link> : x.destroyed_on_spot ? t("destroyedOnSpot") : "—"}</TD></TR>
        ))}</TBody>
      </Table>
    </div>
  );
}

function Counts({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Counts(project.id);
  return (
    <div>
      <p className="mb-2 text-sm text-muted-foreground">{t("countsHint")} <Link className="text-primary hover:underline" href="/quality/imports">{t("goImport")}</Link></p>
      {q.isLoading ? <LoadingState /> : (q.data ?? []).length ? (
        <Table compact data-testid="q3-counts-table">
          <THead><TR><TH>{t("no")}</TH><TH>{t("at")}</TH><TH>{t("lines")}</TH><TH>{t("ira")}</TH></TR></THead>
          <TBody>{(q.data ?? []).map((c) => <TR key={c.id}><TD className="ltr">{c.cc_no}</TD><TD>{dateTime(c.counted_at)}</TD><TD><span dir="ltr">{c.lines_within} / {c.lines_counted}</span></TD><TD><span dir="ltr">{c.ira_pct ?? "—"} %</span></TD></TR>)}</TBody>
        </Table>
      ) : <EmptyState />}
    </div>
  );
}

function Throughput({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.stk");
  const tc = useTranslations("quality.common");
  const caps = useQCaps(project.id);
  const opts = useProjectOptions(project.id);
  const q = useQ3Throughput(project.id);
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ month: "", units_received: "", units_dispatched: "", deliveries: "", shipments: "" });
  return (
    <div>
      {caps.write("stock.record") ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-5" data-testid="q3-throughput-form">
          <MutationError error={error} />
          <FormField id="tp-m" label={t("month")}><Input id="tp-m" type="month" value={f.month} onChange={set("month")} dir="ltr" /></FormField>
          {(["units_received", "units_dispatched", "deliveries", "shipments"] as const).map((k) => <FormField key={k} id={`tp-${k}`} label={t(`tp.${k}`)}><Input id={`tp-${k}`} value={f[k]} onChange={set(k)} dir="ltr" inputMode="numeric" /></FormField>)}
          <div className="sm:col-span-5"><Button disabled={busy || !f.month} onClick={() => void run(() => unwrap(api.PUT("/api/v1/projects/{project_id}/quality/throughput", { params: { path: { project_id: project.id } }, body: { site_id: opts.sites[0]?.value, month: `${f.month}-01`, ...Object.fromEntries((["units_received", "units_dispatched", "deliveries", "shipments"] as const).filter((k) => f[k]).map((k) => [k, Number(f[k])])) } as never })))}>{tc("save")}</Button></div>
        </CardContent></Card>
      ) : null}
      <Table compact>
        <THead><TR><TH>{t("month")}</TH><TH>{t("tp.units_received")}</TH><TH>{t("tp.units_dispatched")}</TH><TH>{t("tp.deliveries")}</TH><TH>{t("tp.shipments")}</TH></TR></THead>
        <TBody>{(q.data ?? []).map((x) => <TR key={x.id}><TD className="ltr">{x.month.slice(0, 7)}</TD><TD><span dir="ltr">{x.units_received}</span></TD><TD><span dir="ltr">{x.units_dispatched}</span></TD><TD><span dir="ltr">{x.deliveries}</span></TD><TD><span dir="ltr">{x.shipments}</span></TD></TR>)}</TBody>
      </Table>
    </div>
  );
}
