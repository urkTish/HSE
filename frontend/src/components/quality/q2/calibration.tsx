"use client";
import { Plus, Printer, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { QrImage } from "@/components/access/common";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQMte, useQSuppliers } from "@/lib/api/quality/q0";
import { useQCalibration, useQCalibrations, useQMteCalibrations, useQMteLabel, useQOotReview, useQOotReviews } from "@/lib/api/quality/q2";
import { useFormatters } from "@/lib/use-formatters";
import { QGate, ReasonDialog, useQCaps, useQLabels, useRun, type Project } from "../q0/common";
import { DecisionDialog, Q2Badge, Signoffs, type S } from "./shared";

const CAL_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = { calibrated: "success", due_soon: "warning", overdue: "danger", out_of_service: "danger", limited_use: "warning" };

/* ═════════════ calibration board `/quality/calibration` (§C.4) ═════════════ */

export function CalibrationPage() {
  return <QGate>{(p) => <Board project={p} />}</QGate>;
}

function Board({ project }: { project: Project }) {
  const t = useTranslations("quality.cal");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const items = useQMte(project.id, { page_size: 200 });
  const cals = useQCalibrations(project.id, { status: "draft", page_size: 50 });
  const oots = useQOotReviews(project.id, { status: "open" });
  const all = items.data?.items ?? [];
  const counts = all.reduce<Record<string, number>>((acc, m) => ({ ...acc, [m.cal_status]: (acc[m.cal_status] ?? 0) + 1 }), {});
  const due = all.filter((m) => ["overdue", "due_soon", "out_of_service"].includes(m.cal_status)).sort((a, b) => String(a.cal_due_on).localeCompare(String(b.cal_due_on)));
  return (
    <div data-testid="q2-calibration">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex flex-wrap gap-2" data-testid="q2-cal-chips">
        {["calibrated", "due_soon", "overdue", "out_of_service", "limited_use", "not_required"].map((k) => (
          <Badge key={k} tone={CAL_TONE[k] ?? "neutral"} data-status={k} data-count={counts[k] ?? 0}>{l("cal_status", k)}: {counts[k] ?? 0}</Badge>
        ))}
      </div>
      <Card className="mb-4"><CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("dueList")}</h3>
        {due.length ? (
          <Table compact data-testid="q2-cal-due"><THead><TR><TH>{t("mte")}</TH><TH>{t("type")}</TH><TH>{t("due")}</TH><TH>{t("status")}</TH></TR></THead>
            <TBody>{due.map((m) => <TR key={m.id} data-no={m.mte_no} data-cal={m.cal_status}><TD label={t("mte")}><Link href={`/quality/mte/${m.id}`} className="ltr text-primary hover:underline">{m.mte_no}</Link></TD><TD label={t("type")}>{l("mte_type", m.mte_type)}</TD><TD label={t("due")}>{date(m.cal_due_on)}</TD><TD label={t("status")}><Badge tone={CAL_TONE[m.cal_status] ?? "neutral"}>{l("cal_status", m.cal_status)}</Badge></TD></TR>)}</TBody></Table>
        ) : <p className="text-sm text-muted-foreground">{t("nothingDue")}</p>}
      </CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("toAccept")}</h3>
        {(cals.data?.items ?? []).length ? <ul className="text-sm">{(cals.data?.items ?? []).map((c) => <li key={c.id}><Link href={`/quality/calibration/${c.id}`} className="ltr text-primary hover:underline">{c.mte_no} · {date(c.cal_date)}</Link></li>)}</ul> : <p className="text-sm text-muted-foreground">{t("none")}</p>}
      </CardContent></Card>
      <Card><CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("ootOpen")}</h3>
        {(oots.data ?? []).length ? <ul className="text-sm" data-testid="q2-oot-list">{(oots.data ?? []).map((r) => <li key={r.id} data-no={r.oot_no}><Link href={`/quality/calibration/oot/${r.id}`} className="ltr text-primary hover:underline">{r.oot_no}</Link> · {r.mte_no} · {t("decidedOf", { n: r.decided_count, total: r.item_count })} · {t("dueOn", { d: date(r.due_on) })}</li>)}</ul> : <p className="text-sm text-muted-foreground">{t("none")}</p>}
      </CardContent></Card>
    </div>
  );
}

/* ═════════════ M&TE detail tabs (registry/tabs-q2.tsx) ═════════════ */

type Pt = { nominal: string; as_found: string; as_left: string; tolerance: string };

export function MteCalibrationsTab({ recordId, projectId }: { recordId: string; projectId: string | null }) {
  const t = useTranslations("quality.cal");
  const { l } = useQLabels();
  const caps = useQCaps(projectId ?? "");
  const { date } = useFormatters(projectId);
  const q = useQMteCalibrations(recordId);
  const [adding, setAdding] = useState(false);
  const rows = q.data ?? [];
  return (
    <div data-testid="q2-mte-calibrations">
      {caps.write("mte.manage") && !adding ? <Button className="mb-3" onClick={() => setAdding(true)} data-testid="q2-cal-new"><Plus aria-hidden />{t("new")}</Button> : null}
      {adding ? <CalForm mteId={recordId} onDone={() => setAdding(false)} /> : null}
      {q.isLoading ? <LoadingState /> : rows.length ? (
        <Table compact><THead><TR><TH>{t("no")}</TH><TH>{t("kind")}</TH><TH>{t("date")}</TH><TH>{t("provider")}</TH><TH>{t("asFound")}</TH><TH>{t("nextDue")}</TH><TH>{t("status")}</TH></TR></THead>
          <TBody>{rows.map((c) => (
            <TR key={c.id} data-testid="q2-cal-row" data-status={c.status}>
              <TD label={t("no")}><Link href={`/quality/calibration/${c.id}`} className="ltr text-primary hover:underline">{c.cal_no ?? t("draft")}</Link></TD>
              <TD label={t("kind")}>{l("cal_kind", c.kind)}</TD><TD label={t("date")}>{date(c.cal_date)}</TD>
              <TD label={t("provider")} className="ltr">{c.provider_code ?? (c.in_house ? t("inHouse") : "—")}</TD>
              <TD label={t("asFound")}>{c.as_found_ok ? <Badge tone="success">{t("inTol")}</Badge> : <Badge tone="danger">{t("outTol")}</Badge>}</TD>
              <TD label={t("nextDue")}>{date(c.next_due)}</TD>
              <TD label={t("status")}><Q2Badge value={c.status === "accepted" ? "approved" : c.status} label={l("cal_record_status", c.status)} /></TD>
            </TR>
          ))}</TBody></Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function CalForm({ mteId, onDone }: { mteId: string; onDone: () => void }) {
  const t = useTranslations("quality.cal");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const sup = useQSuppliers({ page_size: 200 });
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ kind: "calibration", cal_date: "", provider_supplier_id: "", certificate_no: "", verification_note: "" });
  const [pts, setPts] = useState<Pt[]>([{ nominal: "", as_found: "", as_left: "", tolerance: "" }]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const labs = (sup.data?.items ?? []).filter((x) => x.categories.includes("calibration_lab"));
  async function save() {
    const points = pts.filter((p) => p.nominal && p.as_found).map((p) => ({ nominal: p.nominal, as_found: p.as_found, as_left: p.as_left || null, tolerance: p.tolerance || null }));
    const body = {
      kind: f.kind as S["QCalKind"], cal_date: f.cal_date, provider_supplier_id: f.provider_supplier_id || null,
      in_house: !f.provider_supplier_id, certificate_no: f.certificate_no || null, verification_note: f.verification_note || null, points,
    };
    const out = await run(() => unwrap(api.POST("/api/v1/quality/mte/{mte_id}/calibrations", { params: { path: { mte_id: mteId } }, body })));
    if (out) onDone();
  }
  const upd = (i: number, k: keyof Pt, v: string) => setPts(pts.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-cal-form">
      <MutationError error={error} />
      <FormField id="cal-kind" label={t("kind")}><Select value={f.kind} onChange={set("kind")} data-testid="cal-kind">{options("cal_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="cal-date" label={t("date")} required><Input type="date" value={f.cal_date} onChange={set("cal_date")} data-testid="cal-date" /></FormField>
      <FormField id="cal-prov" label={t("provider")}><Select value={f.provider_supplier_id} onChange={set("provider_supplier_id")} data-testid="cal-provider"><option value="">{t("inHouse")}</option>{labs.map((x) => <option key={x.id} value={x.id}>{x.supplier_code}</option>)}</Select></FormField>
      <FormField id="cal-cert" label={t("certificateNo")}><Input value={f.certificate_no} onChange={set("certificate_no")} dir="ltr" data-testid="cal-cert" /></FormField>
      {f.kind === "verification" ? <FormField id="cal-ver" label={t("verificationNote")} className="sm:col-span-2"><Input value={f.verification_note} onChange={set("verification_note")} /></FormField> : null}
      <div className="sm:col-span-3">
        <h3 className="mb-2 text-sm font-semibold">{t("points")}</h3>
        {pts.map((p, i) => (
          <div key={i} className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]">
            {(["nominal", "as_found", "as_left", "tolerance"] as const).map((k) => <Input key={k} aria-label={t(`pt.${k}`)} placeholder={t(`pt.${k}`)} value={p[k]} onChange={(e) => upd(i, k, e.target.value)} dir="ltr" inputMode="decimal" data-testid={`cal-${k}`} />)}
            <Button variant="ghost" size="sm" aria-label={t("removePoint")} onClick={() => setPts(pts.filter((_, j) => j !== i))}><Trash2 aria-hidden /></Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setPts([...pts, { nominal: "", as_found: "", as_left: "", tolerance: "" }])}><Plus aria-hidden />{t("addPoint")}</Button>
      </div>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.cal_date} onClick={() => void save()} data-testid="cal-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function MteOotTab({ recordId, projectId }: { recordId: string; projectId: string | null }) {
  const t = useTranslations("quality.cal");
  const { l } = useQLabels();
  const { date } = useFormatters(projectId);
  const q = useQOotReviews(projectId ?? "", {});
  const rows = (q.data ?? []).filter((r) => r.mte_id === recordId);
  return rows.length ? (
    <ul className="text-sm" data-testid="q2-mte-oot">{rows.map((r) => <li key={r.id}><Link href={`/quality/calibration/oot/${r.id}`} className="ltr text-primary hover:underline">{r.oot_no}</Link> · {date(r.period_from)} – {date(r.period_to)} · {l("oot_status", r.status)}</li>)}</ul>
  ) : <EmptyState message={t("noOot")} />;
}

export function MteLabelTab({ recordId, projectId }: { recordId: string; projectId: string | null }) {
  const t = useTranslations("quality.cal");
  const caps = useQCaps(projectId ?? "");
  return (
    <div data-testid="q2-mte-label-tab">
      <LabelCard mteId={recordId} />
      <div className="mt-3 flex gap-2">
        <Button asChild variant="outline"><Link href={`/quality/calibration/label/${recordId}`} data-testid="q2-label-open"><Printer aria-hidden />{t("printLabel")}</Link></Button>
        {caps.write("mte.manage") ? null : null}
      </div>
    </div>
  );
}

/** The status label (Q-CAL-05): bilingual EN / AR whatever the screen language; QR opens the record after sign-in. */
function LabelCard({ mteId }: { mteId: string }) {
  const q = useQMteLabel(mteId);
  const { date } = useFormatters();
  if (q.isLoading) return <LoadingState />;
  const x = q.data;
  if (!x) return null;
  const bg = { green: "bg-green-600", amber: "bg-amber-500", red: "bg-red-600", grey: "bg-gray-500" }[x.colour];
  const url = typeof window !== "undefined" ? `${window.location.origin}/en${x.path}` : x.path;
  return (
    <div className="inline-flex w-80 flex-col gap-2 rounded-md border-2 border-black bg-white p-3 text-black" dir="ltr" data-testid="q2-label" data-colour={x.colour}>
      <div className={`rounded px-2 py-1 text-center font-bold text-white ${bg}`}>{x.status_en} · <span dir="rtl">{x.status_ar}</span></div>
      <div className="flex items-center gap-3">
        <QrImage payload={url} size={96} label={x.mte_no} />
        <div className="text-sm">
          <p className="text-lg font-bold">{x.mte_no}</p>
          <p>{x.project_code}</p>
          <p>Cal / <span dir="rtl">المعايرة</span>: {date(x.cal_date)}</p>
          <p>Due / <span dir="rtl">الاستحقاق</span>: {date(x.due_on)}</p>
        </div>
      </div>
      <p className="text-xs">{x.description}</p>
    </div>
  );
}

export function LabelPrintPage({ id }: { id: string }) {
  return <QGate>{() => <LabelPrint id={id} />}</QGate>;
}

function LabelPrint({ id }: { id: string }) {
  const t = useTranslations("quality.cal");
  const { run, busy } = useRun();
  async function print() {
    await run(() => unwrap(api.POST("/api/v1/quality/mte/{mte_id}/label", { params: { path: { mte_id: id } } })), "");
    window.print();
  }
  return (
    <div data-testid="q2-label-page">
      <div className="mb-3 flex gap-2 print:hidden">
        <Button disabled={busy} onClick={() => void print()} data-testid="q2-label-print"><Printer aria-hidden />{t("printLabel")}</Button>
        <Button asChild variant="outline"><Link href={`/quality/mte/${id}`}>{t("backToMte")}</Link></Button>
      </div>
      <LabelCard mteId={id} />
    </div>
  );
}

/* ═════════════ calibration record `/quality/calibration/[id]` ═════════════ */

export function CalibrationDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <CalDetail project={p} id={id} />}</QGate>;
}

function CalDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.cal");
  const tq = useTranslations("quality.q2");
  const { l } = useQLabels();
  const { date } = useFormatters(project.id);
  const q = useQCalibration(id);
  const [deciding, setDeciding] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  if (!c) return null;
  return (
    <div data-testid="q2-cal-detail" data-status={c.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/calibration" }, { label: c.mte_no ?? "", href: `/quality/mte/${c.mte_id}` }, { label: c.cal_no ?? t("draft") }]} />
      <PageHeader title={<span className="ltr">{c.cal_no ?? t("draft")}</span>} description={`${c.mte_no} · ${l("cal_kind", c.kind)}`}
        badge={<Q2Badge value={c.status === "accepted" ? "approved" : c.status} label={l("cal_record_status", c.status)} testId="q2-cal-status" />}
        actions={c.actions.includes("accept") ? <Button onClick={() => setDeciding(true)} data-testid="q2-cal-decide">{t("decide")}</Button> : null} />
      <ApiWarnings warnings={c.warnings} className="mb-3" />
      {!c.as_found_ok ? <Alert tone="danger" className="mb-3">{t("asFoundOut", { e: c.max_found_error ?? "" })}</Alert> : null}
      {!c.as_left_ok ? <Alert tone="danger" className="mb-3">{t("asLeftOut")}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("date")}>{date(c.cal_date)}</FieldItem>
        <FieldItem label={t("provider")} ltr>{c.provider_code ?? (c.in_house ? `${t("inHouse")} ${c.reference_mte_no ?? ""}` : "—")}</FieldItem>
        <FieldItem label={t("certificateNo")} ltr>{c.certificate_no ?? "—"}</FieldItem>
        <FieldItem label={t("nextDue")}>{date(c.next_due)}</FieldItem>
        {c.verification_note ? <FieldItem label={t("verificationNote")} wide>{c.verification_note}</FieldItem> : null}
      </FieldList></CardContent></Card>
      {c.points.length ? (
        <Card className="mb-4"><CardContent className="p-4"><Table compact data-testid="q2-cal-points"><THead><TR><TH>{t("pt.nominal")}</TH><TH>{t("pt.as_found")}</TH><TH>{t("pt.as_left")}</TH><TH>{t("pt.tolerance")}</TH><TH>{t("error")}</TH><TH /></TR></THead>
          <TBody>{c.points.map((p, i) => <TR key={i} data-in={p.in_tolerance ? "1" : "0"}><TD label={t("pt.nominal")} className="ltr">{p.nominal}</TD><TD label={t("pt.as_found")} className="ltr">{p.as_found}</TD><TD label={t("pt.as_left")} className="ltr">{p.as_left ?? "—"}</TD><TD label={t("pt.tolerance")} className="ltr">± {p.tolerance}</TD><TD label={t("error")} className="ltr">{p.error}</TD><TD label="">{p.in_tolerance ? <Badge tone="success">{t("inTol")}</Badge> : <Badge tone="danger">{t("outTol")}</Badge>}</TD></TR>)}</TBody></Table></CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("certificate")}</h3><Attachments ownerType="q_calibration_cert" ownerId={c.id} canUpload={c.status === "draft"} /></CardContent></Card>
      <Signoffs recordType="calibration" recordId={c.id} />
      <HistoryPanel entityType="q_calibration" entityId={c.id} projectId={project.id} />
      <DecisionDialog open={deciding} onOpenChange={setDeciding} title={t("decide")} options={[{ value: "approved", label: tq("accept") }, { value: "rejected", label: tq("reject") }]} needsComment={(v) => v === "rejected"}
        onSubmit={(d, cm) => unwrap(api.POST("/api/v1/quality/calibrations/{cal_id}/decide", { params: { path: { cal_id: c.id } }, body: { decision: d as "approved", comment: cm || null } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ OOT review `/quality/calibration/oot/[id]` (Q-CAL-04) ═════════════ */

export function OotReviewPage({ id }: { id: string }) {
  return <QGate>{(p) => <Oot project={p} id={id} />}</QGate>;
}

function Oot({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.oot");
  const tq = useTranslations("quality.q2");
  const { l, recordType } = useQLabels();
  const { date, dateTime } = useFormatters(project.id);
  const q = useQOotReview(id);
  const { run, busy, error } = useRun();
  const [accepting, setAccepting] = useState(false);
  const [noImpact, setNoImpact] = useState<string | null>(null);
  const [recheck, setRecheck] = useState<string | null>(null);
  const [ncr, setNcr] = useState<string | null>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) return null;
  const decideItems = r.actions.includes("decide_items");
  const decide = (itemId: string, body: S["QOotItemDecide"]) => unwrap(api.POST("/api/v1/quality/oot-items/{item_id}/decision", { params: { path: { item_id: itemId } }, body })).then(() => q.refetch());
  return (
    <div data-testid="q2-oot-detail" data-status={r.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/calibration" }, { label: r.oot_no }]} />
      <PageHeader title={<span className="ltr">{r.oot_no}</span>} description={t("subtitle", { mte: r.mte_no, e: r.error_abs })}
        badge={<Q2Badge value={r.status} label={l("oot_status", r.status)} testId="q2-oot-status" />}
        actions={<>
          {decideItems && r.proposed_no_impact ? <Button variant="outline" onClick={() => setAccepting(true)} data-testid="q2-oot-accept">{t("acceptProposals")}</Button> : null}
          {r.actions.includes("close") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/oot-reviews/{review_id}/close", { params: { path: { review_id: r.id } }, body: {} })))} data-testid="q2-oot-close">{t("close")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("period")}>{date(r.period_from)} – {date(r.period_to)}</FieldItem>
        <FieldItem label={t("error")} ltr>{r.error_abs}</FieldItem>
        <FieldItem label={t("due")}>{date(r.due_on)}</FieldItem>
        <FieldItem label={t("progress")} ltr><span data-testid="q2-oot-progress">{r.decided_count} / {r.item_count}</span></FieldItem>
        <FieldItem label={t("proposed")} ltr>{r.proposed_no_impact}</FieldItem>
        <FieldItem label={t("ncrs")} ltr>{r.ncr_count}</FieldItem>
      </FieldList></CardContent></Card>
      <Table compact data-testid="q2-oot-items"><THead><TR><TH>{t("record")}</TH><TH>{t("usedAt")}</TH><TH>{t("value")}</TH><TH>{t("limits")}</TH><TH>{t("margin")}</TH><TH>{t("proposal")}</TH><TH>{t("decision")}</TH><TH /></TR></THead>
        <TBody>{r.items.map((i) => (
          <TR key={i.id} data-testid="q2-oot-item" data-proposed={i.proposed ?? ""} data-decision={i.decision ?? ""}>
            <TD label={t("record")}>{recordType(i.record_type)} <span className="ltr">{i.ref ?? ""}</span></TD>
            <TD label={t("usedAt")}>{dateTime(i.used_at)}</TD>
            <TD label={t("value")} className="ltr">{i.value ?? "—"}</TD>
            <TD label={t("limits")} className="ltr">{[i.limit_low, i.limit_high].map((x) => x ?? "…").join(" – ")}</TD>
            <TD label={t("margin")} className={i.margin && Number(i.margin) <= Number(i.error_abs) ? "ltr font-semibold text-danger" : "ltr"}>{i.margin ?? "—"}</TD>
            <TD label={t("proposal")}>{i.proposed ? l("oot_decision", i.proposed) : "—"}</TD>
            <TD label={t("decision")}>{i.decision ? <span>{l("oot_decision", i.decision)}{i.ncr_id ? <> · <Link href={`/quality/ncrs/${i.ncr_id}`} className="text-primary hover:underline">{t("openNcr")}</Link></> : null}</span> : "—"}</TD>
            <TD label="">{decideItems && !i.decision ? (
              <span className="flex flex-wrap gap-1">
                <Button size="sm" variant="ghost" onClick={() => setNoImpact(i.id)} data-testid="q2-oot-no-impact">{l("oot_decision", "no_impact")}</Button>
                <Button size="sm" variant="ghost" onClick={() => setRecheck(i.id)} data-testid="q2-oot-recheck">{l("oot_decision", "recheck")}</Button>
                <Button size="sm" variant="ghost" onClick={() => setNcr(i.id)} data-testid="q2-oot-ncr">{l("oot_decision", "ncr")}</Button>
              </span>
            ) : null}</TD>
          </TR>
        ))}</TBody></Table>
      <div className="mt-4"><Signoffs recordType="oot_review" recordId={r.id} /></div>
      <ReasonDialog open={accepting} onOpenChange={setAccepting} title={t("acceptProposals")} min={10} confirm={tq("confirm")} label={t("justification")} testId="q2-oot-accept-dialog"
        onSubmit={(j) => unwrap(api.POST("/api/v1/quality/oot-reviews/{review_id}/accept-proposals", { params: { path: { review_id: r.id } }, body: { justification: j } })).then(() => q.refetch())} />
      <ReasonDialog open={Boolean(noImpact)} onOpenChange={(v) => { if (!v) setNoImpact(null); }} title={l("oot_decision", "no_impact")} min={10} confirm={tq("confirm")} label={t("justification")}
        onSubmit={(j) => decide(noImpact ?? "", { decision: "no_impact", justification: j })} />
      <ReasonDialog open={Boolean(recheck)} onOpenChange={(v) => { if (!v) setRecheck(null); }} title={l("oot_decision", "recheck")} min={3} confirm={tq("confirm")} label={t("recheckRef")}
        onSubmit={(j) => decide(recheck ?? "", { decision: "recheck", recheck_ref: j.slice(0, 60) })} />
      <ReasonDialog open={Boolean(ncr)} onOpenChange={(v) => { if (!v) setNcr(null); }} title={l("oot_decision", "ncr")} min={10} confirm={tq("confirm")} label={t("justification")} testId="q2-oot-ncr-dialog"
        onSubmit={(j) => decide(ncr ?? "", { decision: "ncr", justification: j })} />
    </div>
  );
}
