"use client";
import { CalendarDays, Download, LayoutGrid, List, Plus, Sun } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { OutboxPanel } from "@/components/field/offline";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError, downloadFile, unwrap } from "@/lib/api/client";
import { useQMte, useQSystems } from "@/lib/api/quality/q0";
import { useQIr, useQIrLocations, useQIrs, useQItp, useQItps } from "@/lib/api/quality/q1";
import { newUuid, submitWithOutbox } from "@/lib/field-offline";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { useMeData } from "@/components/shell/me-context";
import { QGate, qError, ReasonDialog, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type S } from "../q0/common";
import { BlockerList, emptyPaper, LinkList, PaperFields, paperReady, type PhotoIn, PhotoPicker, PointTypeChip, Q1Status, SignoffList, Tabs } from "./shared";

type Ir = S["QIrRead"];
const PAGE_SIZE = 50;
const VIEWS = ["today", "board", "calendar", "register"] as const;
type View = (typeof VIEWS)[number];
const BOARD: S["QIrStatus"][] = ["submitted", "scheduled", "witness_waived", "reinspection_requested", "rejected"];

/** Local date-time string for <input type="datetime-local"> in the browser's zone. */
function localInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* ═════════════ board `/quality/inspection-requests` ═════════════ */

export function IrBoardPage() {
  return <QGate>{(p) => <Board project={p} />}</QGate>;
}

function Board({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const view = (s.get("view") as View) || (caps.has("ir.inspect") ? "today" : "board");
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.write("ir.submit") ? (
            <Button asChild data-testid="q1-ir-new">
              <Link href="/quality/inspection-requests/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <div className="mb-4 flex flex-wrap gap-1" role="tablist">
        {VIEWS.map((v) => {
          const Icon = { today: Sun, board: LayoutGrid, calendar: CalendarDays, register: List }[v];
          return (
            <Button key={v} size="sm" variant={view === v ? "default" : "outline"} role="tab" aria-selected={view === v} onClick={() => s.set({ view: v, page: null })} data-testid={`q1-ir-view-${v}`}>
              <Icon aria-hidden />
              {t(`view.${v}`)}
            </Button>
          );
        })}
      </div>
      {view === "today" ? <Today project={project} /> : null}
      {view === "board" ? <Columns project={project} /> : null}
      {view === "calendar" ? <Calendar project={project} /> : null}
      {view === "register" ? <Register project={project} /> : null}
      <span className="sr-only">{tc("status")}</span>
    </div>
  );
}

function IrCard({ ir }: { ir: S["QIrListItem"] }) {
  const t = useTranslations("quality.q1.ir");
  const ar = useLocale() === "ar";
  const { dateTime } = useFormatters();
  return (
    <Link href={`/quality/inspection-requests/${ir.id}`} className="glass block rounded-lg border p-3 text-sm hover:border-primary" data-testid="q1-ir-card" data-no={ir.ir_no ?? ""} data-status={ir.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="ltr font-medium">{ir.ir_no ?? t("draft")}</span>
        <PointTypeChip value={ir.governing_type} />
        <Q1Status kind="ir_status" value={ir.status} />
        {ir.short_notice ? <span className="text-xs text-warning">{t("shortNotice")}</span> : null}
        {ir.reblocked ? <span className="text-xs text-danger">{t("reblocked")}</span> : null}
        {ir.needs_confirmation ? <span className="text-xs text-warning">{t("needsConfirmation")}</span> : null}
      </div>
      <p className="mt-1" dir="auto">{ir.location_ref}</p>
      <p className="text-xs text-muted-foreground">
        <span className="ltr">{ir.itp_display_no}</span> · {t("pointsShort", { seqs: ir.point_seqs.join(", ") })} · {ir.engagement?.short_code ?? ""}
      </p>
      {ir.scheduled_at ? <p className="text-xs">{t("scheduledFor", { at: dateTime(ir.scheduled_at) })}{ir.inspector ? ` · ${userText(ir.inspector, ar)}` : ""}</p> : null}
    </Link>
  );
}

function Today({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.ir");
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start.getTime() + 86_400_000);
  const mine = useQIrs(project.id, { inspector_me: true, scheduled_from: start.toISOString(), scheduled_to: end.toISOString(), status: ["scheduled", "witness_waived"], page_size: 100 });
  const asks = useQIrs(project.id, { mine: true, page_size: 20, status: ["draft", "submitted", "scheduled", "rejected"] });
  return (
    <div className="flex flex-col gap-6" data-testid="q1-ir-today">
      <section>
        <h2 className="mb-2 text-base font-semibold">{t("myInspectionsToday")}</h2>
        {mine.isLoading ? <LoadingState /> : (mine.data?.items ?? []).length ? (
          <div className="grid gap-2 sm:grid-cols-2">{mine.data?.items.map((x) => <IrCard key={x.id} ir={x} />)}</div>
        ) : <EmptyState message={t("noneToday")} />}
      </section>
      {(asks.data?.items ?? []).length ? (
        <section>
          <h2 className="mb-2 text-base font-semibold">{t("myRequests")}</h2>
          <div className="grid gap-2 sm:grid-cols-2">{asks.data?.items.map((x) => <IrCard key={x.id} ir={x} />)}</div>
        </section>
      ) : null}
    </div>
  );
}

function Columns({ project }: { project: Project }) {
  const { l } = useQLabels();
  const r = useQIrs(project.id, { status: BOARD, page_size: 200 });
  if (r.isLoading) return <LoadingState />;
  if (r.isError) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const items = r.data?.items ?? [];
  return (
    <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5" data-testid="q1-ir-board">
      {BOARD.map((st) => {
        const col = items.filter((x) => x.status === st);
        return (
          <section key={st} className="flex min-w-0 flex-col gap-2" data-testid={`q1-ir-col-${st}`}>
            <h2 className="text-sm font-semibold">{l("ir_status", st)} <span className="ltr text-muted-foreground">({col.length})</span></h2>
            {col.map((x) => <IrCard key={x.id} ir={x} />)}
          </section>
        );
      })}
    </div>
  );
}

function Calendar({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.ir");
  const ar = useLocale() === "ar";
  const { date } = useFormatters(project.id);
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start.getTime() + 7 * 86_400_000);
  const r = useQIrs(project.id, { scheduled_from: start.toISOString(), scheduled_to: end.toISOString(), status: ["scheduled"], page_size: 200 });
  const days = useMemo(() => {
    const out = new Map<string, Map<string, S["QIrListItem"][]>>();
    for (const x of r.data?.items ?? []) {
      if (!x.scheduled_at) continue;
      const d = x.scheduled_at.slice(0, 10);
      const who = userText(x.inspector, ar);
      const m = out.get(d) ?? new Map<string, S["QIrListItem"][]>();
      m.set(who, [...(m.get(who) ?? []), x]);
      out.set(d, m);
    }
    return [...out.entries()].sort();
  }, [r.data, ar]);
  if (r.isLoading) return <LoadingState />;
  if (!days.length) return <EmptyState message={t("noneScheduled")} />;
  return (
    <div className="flex flex-col gap-4" data-testid="q1-ir-calendar">
      {days.map(([d, byInsp]) => (
        <section key={d}>
          <h2 className="mb-2 text-sm font-semibold">{date(d)}</h2>
          {[...byInsp.entries()].map(([who, xs]) => (
            <div key={who} className="mb-2">
              <p className="mb-1 text-xs text-muted-foreground">{who}</p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{xs.map((x) => <IrCard key={x.id} ir={x} />)}</div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const gov = s.get("type") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQIrs(project.id, {
    status: status ? [status as S["QIrStatus"]] : null,
    governing_type: (gov || null) as S["QPointType"] | null,
    mine: s.getBool("mine") ?? false,
    q: q || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = r.data?.items ?? [];
  return (
    <div>
      <ListToolbar>
        <SearchFilter id="q1-ir-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q1-ir-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("ir_status")} />
        <SelectFilter id="q1-ir-type" label={t("pointType")} value={gov} onChange={(v) => s.set({ type: v, page: null })} options={options("point_type")} />
        <SelectFilter id="q1-ir-mine" label={tc("show")} value={s.getBool("mine") ? "mine" : ""} onChange={(v) => s.set({ mine: v === "mine" ? "true" : null, page: null })} options={[{ value: "mine", label: tc("mine") }]} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : items.length ? (
        <>
          <Table compact data-testid="q1-ir-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("pointType")}</TH>
                <TH>{tc("status")}</TH>
                <TH>{t("location")}</TH>
                <TH>{t("itp")}</TH>
                <TH>{t("contractor")}</TH>
                <TH>{t("scheduled")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="q1-ir-row" data-no={x.ir_no ?? ""} data-status={x.status}>
                  <TD label={t("no")}><Link href={`/quality/inspection-requests/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.ir_no ?? t("draft")}</Link></TD>
                  <TD label={t("pointType")}><PointTypeChip value={x.governing_type} /></TD>
                  <TD label={tc("status")}><Q1Status kind="ir_status" value={x.status} /></TD>
                  <TD label={t("location")} data-full=""><span dir="auto">{x.location_ref}</span></TD>
                  <TD label={t("itp")} className="ltr text-xs">{x.itp_display_no} · {x.point_seqs.join(", ")}</TD>
                  <TD label={t("contractor")}>{x.engagement?.short_code ?? "—"}</TD>
                  <TD label={t("scheduled")}>{dateTime(x.scheduled_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

/* ═════════════ raise `/quality/inspection-requests/new` (phone first) ═════════════ */

export function IrNewPage() {
  return <QGate>{(p) => <Raise project={p} />}</QGate>;
}

function Raise({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const b = useBilingual();
  const opts = useProjectOptions(project.id);
  const systems = useQSystems(project.id);
  const itps = useQItps(project.id, { status: ["approved"], page_size: 200 });
  const router = useRouter();
  const { run, busy, error, setError } = useRun();
  const [itpId, setItpId] = useState("");
  const itp = useQItp(itpId);
  const [seqs, setSeqs] = useState<number[]>([]);
  const [f, setF] = useState(() => ({ site_id: "", zone_id: "", system_id: "", location_ref: "", extent: "", proposed_at: localInput(new Date(Date.now() + 26 * 3_600_000)), self_check_note: "" }));
  const [selfCheck, setSelfCheck] = useState(false);
  const [shortReason, setShortReason] = useState("");
  const [needShort, setNeedShort] = useState(false);
  const [cuid] = useState(newUuid);
  const locs = useQIrLocations(project.id, { itp_family_id: itp.data?.family_id ?? null, zone_id: f.zone_id || null }, { enabled: Boolean(itp.data) });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const zones = opts.zones.filter((z) => !f.site_id || z.siteId === f.site_id).filter((z) => !itp.data?.zones.length || itp.data.zones.some((x) => x.id === z.value));
  async function save(submit: boolean) {
    const body: S["QIrCreate"] = {
      itp_id: itpId, point_seqs: seqs, site_id: f.site_id, zone_id: f.zone_id || null, system_id: f.system_id || null, location_ref: f.location_ref,
      extent: f.extent || null, proposed_at: f.proposed_at ? new Date(f.proposed_at).toISOString() : null, self_check_done: selfCheck,
      self_check_note: f.self_check_note || null, client_uuid: cuid, submit, short_notice_reason: needShort ? shortReason : null,
    };
    setError(null);
    try {
      const out = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/inspection-requests", { params: { path: { project_id: project.id } }, body }));
      toast.success(submit ? t("submittedToast", { no: out.ir_no ?? "" }) : tc("saved"));
      router.push(`/quality/inspection-requests/${out.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "IR_NOTICE_TOO_SHORT") setNeedShort(true);
      setError(qError(e));
    }
  }
  const ready = itpId && seqs.length && f.site_id && f.location_ref.trim();
  return (
    <div data-testid="q1-ir-raise">
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/inspection-requests" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <MutationError error={error} />
      <div className="flex flex-col gap-4">
        <FormSection title={t("whichPoint")}>
          <FormField id="ir-itp" label={t("itp")} required className="sm:col-span-2">
            <Select value={itpId} onChange={(e) => { setItpId(e.target.value); setSeqs([]); }} data-testid="q1-ir-itp">
              <option value="">{tc("select")}</option>
              {(itps.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.display_no} — {b(x.title_en, x.title_ar)}</option>)}
            </Select>
          </FormField>
          {itp.data ? (
            <div className="flex flex-col gap-1 sm:col-span-2" role="group" aria-label={t("points")} data-testid="q1-ir-points">
              {itp.data.points.map((p) => (
                <label key={p.id} className="flex min-h-touch items-center gap-3 rounded-md border px-3 text-sm">
                  <Checkbox checked={seqs.includes(p.seq)} onChange={(e) => setSeqs((xs) => (e.target.checked ? [...xs, p.seq].sort((a, c) => a - c) : xs.filter((x) => x !== p.seq)))} data-testid={`q1-ir-point-${p.seq}`} />
                  <span className="ltr font-mono">{p.seq}</span>
                  <PointTypeChip value={p.point_type} />
                  <span dir="auto">{b(p.activity_en, p.activity_ar)}</span>
                </label>
              ))}
            </div>
          ) : null}
        </FormSection>
        <FormSection title={t("where")}>
          <FormField id="ir-site" label={t("site")} required>
            <Select value={f.site_id} onChange={set("site_id")} data-testid="q1-ir-site">
              <option value="">{tc("select")}</option>
              {opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="ir-zone" label={t("zone")}>
            <Select value={f.zone_id} onChange={set("zone_id")} data-testid="q1-ir-zone">
              <option value="">—</option>
              {zones.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="ir-sys" label={t("system")}>
            <Select value={f.system_id} onChange={set("system_id")}>
              <option value="">—</option>
              {(systems.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.code} — {ar ? x.name_ar : x.name_en}</option>)}
            </Select>
          </FormField>
          <FormField id="ir-loc" label={t("location")} required hint={t("locationHint")}>
            <Input value={f.location_ref} onChange={set("location_ref")} list="ir-loc-list" maxLength={120} data-testid="q1-ir-location" />
          </FormField>
          <datalist id="ir-loc-list">{(locs.data ?? []).map((x) => <option key={x.location_key} value={x.location_ref} />)}</datalist>
          <FormField id="ir-extent" label={t("extent")}><Input value={f.extent} onChange={set("extent")} maxLength={150} /></FormField>
          <FormField id="ir-when" label={t("proposedAt")} required>
            <Input type="datetime-local" value={f.proposed_at} onChange={set("proposed_at")} data-testid="q1-ir-proposed" />
          </FormField>
        </FormSection>
        <FormSection title={t("selfCheck")}>
          <CheckboxField id="ir-self" label={t("selfCheckDone")}><Checkbox checked={selfCheck} onChange={(e) => setSelfCheck(e.target.checked)} data-testid="q1-ir-selfcheck" /></CheckboxField>
          <FormField id="ir-self-note" label={t("selfCheckNote")} hint={tc("noNames")}><Textarea value={f.self_check_note} onChange={set("self_check_note")} rows={2} /></FormField>
          {needShort ? (
            <FormField id="ir-short" label={t("shortNoticeReason")} hint={tc("minChars", { n: 20 })} required className="sm:col-span-2">
              <Textarea value={shortReason} onChange={(e) => setShortReason(e.target.value)} rows={2} data-testid="q1-ir-short-reason" />
            </FormField>
          ) : null}
        </FormSection>
        <div className="sticky bottom-0 flex flex-wrap gap-2 bg-background py-3">
          <Button variant="outline" disabled={busy || !ready} onClick={() => void run(() => save(false), "")} data-testid="q1-ir-save">{t("saveDraft")}</Button>
          <Button disabled={busy || !ready} onClick={() => void save(true)} data-testid="q1-ir-submit">{t("submit")}</Button>
        </div>
      </div>
    </div>
  );
}

/* ═════════════ detail `/quality/inspection-requests/[id]` ═════════════ */

const TABS = ["rounds", "comments", "signoffs", "links", "history"] as const;
type Tab = (typeof TABS)[number];

export function IrDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <Detail project={p} id={id} />}</QGate>;
}

function Detail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.q1.ir");
  const ar = useLocale() === "ar";
  const b = useBilingual();
  const { dateTime } = useFormatters(project.id);
  const q = useQIr(id);
  const [tab, setTab] = useState<Tab>("rounds");
  const [panel, setPanel] = useState<string | null>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const ir = q.data;
  if (!ir) return null;
  const allowed = new Set(ir.allowed_actions);
  const cur = ir.rounds.find((r) => r.round_no === ir.current_round);
  return (
    <div data-testid="q1-ir-detail" data-status={ir.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/inspection-requests" }, { label: ir.ir_no ?? t("draft") }]} />
      <PageHeader
        title={<span className="ltr">{ir.ir_no ?? t("draft")}</span>}
        badge={<span className="flex flex-wrap items-center gap-2"><PointTypeChip value={ir.governing_type} /><Q1Status kind="ir_status" value={ir.status} />{ir.short_notice ? <span className="text-xs text-warning">{t("shortNotice")}</span> : null}</span>}
        description={<span dir="auto">{ir.location_ref}</span>}
        actions={<HeaderActions ir={ir} onPanel={setPanel} />}
      />
      <ApiWarnings warnings={ir.warnings} className="mb-3" />
      {ir.ncr_prompt ? (
        <Alert tone="warning" className="mb-3" data-testid="q1-ir-ncr-prompt">
          <p>{t("ncrOffered")}</p>
          {allowed.has("raise_ncr") ? <RaiseNcr ir={ir} /> : null}
        </Alert>
      ) : null}
      {ir.hold_blockers.length && ir.status !== "draft" ? (
        <Alert tone="danger" className="mb-3" data-testid="q1-ir-hold-alert"><p className="font-medium">{ir.reblocked ? t("reblocked") : t("holdNotReleased")}</p><BlockerList items={ir.hold_blockers} testId="q1-ir-holds" /></Alert>
      ) : null}
      {ir.needs_confirmation ? <Alert tone="warning" className="mb-3" data-testid="q1-ir-confirm-alert">{t("needsConfirmationBody")}</Alert> : null}
      {ir.rp_not_set ? <Alert tone="danger" className="mb-3">{t("rpNotSet")}</Alert> : null}
      <Card className="mb-4">
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("itp")}><Link href={`/quality/itps/${ir.itp_id}`} className="ltr text-primary hover:underline">{ir.itp_display_no}</Link></FieldItem>
            <FieldItem label={t("contractor")}>{ir.engagement?.short_code ?? "—"}</FieldItem>
            <FieldItem label={t("siteZone")}>{ir.site?.code}{ir.zone ? ` · ${ir.zone.code}` : ""}{ir.system ? ` · ${ir.system.code}` : ""}</FieldItem>
            <FieldItem label={t("proposedAt")}>{dateTime(ir.proposed_at)}</FieldItem>
            <FieldItem label={t("requestedBy")}>{userText(ir.requested_by, ar)}</FieldItem>
            <FieldItem label={t("selfCheck")}><YesNo value={ir.self_check_done} yes={t("yes")} no={t("no2")} /></FieldItem>
            {ir.extent ? <FieldItem label={t("extent")}>{ir.extent}</FieldItem> : null}
            {ir.short_notice_reason ? <FieldItem label={t("shortNoticeReason")} wide>{ir.short_notice_reason}</FieldItem> : null}
            {ir.responsible.length ? <FieldItem label={t("responsible")} wide>{ir.responsible.map((u) => userText(u, ar)).join(", ")}</FieldItem> : null}
            {ir.status_reason ? <FieldItem label={t("statusReason")} wide>{ir.status_reason}</FieldItem> : null}
          </FieldList>
          <ul className="mt-4 flex flex-col gap-1" data-testid="q1-ir-point-list">
            {ir.points.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="ltr font-mono">{p.seq}</span><PointTypeChip value={p.point_type} />
                <span dir="auto">{b(p.activity_en, p.activity_ar)} — {b(p.characteristic_en, p.characteristic_ar)}</span>
                {p.criteria.map((c) => <span key={c.id} className="ltr rounded border px-1 text-xs">{c.code}</span>)}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      {panel === "schedule" || panel === "reschedule" ? <ScheduleForm ir={ir} resched={panel === "reschedule"} onDone={() => setPanel(null)} /> : null}
      {panel === "decide" || panel === "review" || panel === "paper" ? <Runner ir={ir} project={project} review={ir.status === "witness_waived"} paperOnly={panel === "paper"} onDone={() => setPanel(null)} /> : null}
      {panel === "waive" ? <Runner ir={ir} project={project} waive onDone={() => setPanel(null)} /> : null}
      {panel === "reinspect" ? <Reinspect ir={ir} onDone={() => setPanel(null)} /> : null}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`tab.${k}`)} prefix="q1-ir" />
      {tab === "rounds" ? <Rounds ir={ir} canUpload={Boolean(cur) && (allowed.has("decide") || allowed.has("waive"))} /> : null}
      {tab === "comments" ? <Comments ir={ir} /> : null}
      {tab === "signoffs" ? <SignoffList items={ir.signoffs} recordType="ir" /> : null}
      {tab === "links" ? (
        <div className="flex flex-col gap-3">
          {ir.ncrs.length ? (
            <ul className="flex flex-col gap-2" data-testid="q1-ir-ncrs">
              {ir.ncrs.map((n) => <li key={n.id}><Link href={`/quality/ncrs/${n.id}`} className="ltr text-primary hover:underline">{n.ncr_no ?? "NCR"}</Link> <Q1Status kind="ncr_status" value={n.status} /></li>)}
            </ul>
          ) : null}
          <LinkList items={ir.links} />
        </div>
      ) : null}
      {tab === "history" ? <HistoryPanel entityType="q_ir" entityId={ir.id} projectId={project.id} /> : null}
    </div>
  );
}

function HeaderActions({ ir, onPanel }: { ir: Ir; onPanel: (p: string | null) => void }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const { run, busy, error } = useRun();
  const allowed = new Set(ir.allowed_actions);
  const [dlg, setDlg] = useState<"cancel" | "void" | "return" | null>(null);
  const path = { params: { path: { ir_id: ir.id } } };
  const btn = (key: string, label: string, onClick: () => void, variant: "default" | "outline" | "ghost" = "outline") =>
    allowed.has(key) ? <Button key={key} variant={variant} disabled={busy} onClick={onClick} data-testid={`q1-ir-${key}`}>{label}</Button> : null;
  return (
    <div className="flex flex-col items-end gap-2">
      <MutationError error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        {btn("submit", t("submit"), () => void run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/submit", { ...path, body: {} })), t("submitted")), "default")}
        {btn("schedule", t("schedule"), () => onPanel("schedule"), "default")}
        {btn("reschedule", t("reschedule"), () => onPanel("reschedule"))}
        {btn("attend", t("attend"), () => void run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/attend", path)), t("attended")))}
        {btn("decide", t("inspect"), () => onPanel("decide"), "default")}
        {btn("review", t("review"), () => onPanel("review"), "default")}
        {btn("paper_signoff", t("paperSignoff"), () => onPanel("paper"))}
        {btn("waive", t("waive"), () => onPanel("waive"))}
        {btn("request_reinspection", t("requestReinspection"), () => onPanel("reinspect"), "default")}
        {btn("confirm_offline", t("confirmOffline"), () => void run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/confirm-offline", { ...path, body: { discard: false } })), t("confirmed")), "default")}
        {btn("return", t("return"), () => setDlg("return"))}
        {btn("cancel", t("cancel"), () => setDlg("cancel"), "ghost")}
        {btn("void", t("void"), () => setDlg("void"), "ghost")}
        {ir.ir_no ? (
          <>
            <Button variant="outline" onClick={() => void downloadFile(`/api/v1/quality/inspection-requests/${ir.id}/pdf?lang=en`, `${ir.ir_no}-EN.pdf`)} data-testid="q1-ir-pdf-en"><Download aria-hidden />PDF EN</Button>
            <Button variant="outline" onClick={() => void downloadFile(`/api/v1/quality/inspection-requests/${ir.id}/pdf?lang=ar`, `${ir.ir_no}-AR.pdf`)} data-testid="q1-ir-pdf-ar"><Download aria-hidden />PDF AR</Button>
          </>
        ) : null}
      </div>
      <ReasonDialog open={dlg === "cancel"} onOpenChange={(v) => setDlg(v ? "cancel" : null)} title={t("cancel")} confirm={t("cancel")} min={20}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/cancel", { ...path, body: { reason } })))} />
      <ReasonDialog open={dlg === "void"} onOpenChange={(v) => setDlg(v ? "void" : null)} title={t("void")} description={t("voidHint")} confirm={t("void")} min={20}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/void", { ...path, body: { reason } })))} />
      <ReasonDialog open={dlg === "return"} onOpenChange={(v) => setDlg(v ? "return" : null)} title={t("return")} confirm={t("return")} min={20} label={tc("reason")}
        onSubmit={(comment) => run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/return", { ...path, body: { comment } })))} />
    </div>
  );
}

function RaiseNcr({ ir }: { ir: Ir }) {
  const t = useTranslations("quality.q1.ir");
  const router = useRouter();
  const { run, busy, error } = useRun();
  const cur = ir.rounds.find((r) => r.round_no === ir.current_round) ?? ir.rounds.at(-1);
  async function go() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/ncrs", {
      params: { path: { project_id: ir.project_id } },
      body: { source_type: "ir", source_id: ir.id, category: cur?.reject_category ?? "workmanship", classification: "minor", owner_id: ir.requested_by?.id ?? null, open: false },
    })), t("ncrDraft"));
    if (out) router.push(`/quality/ncrs/${out.id}`);
  }
  return (
    <div className="mt-2">
      <MutationError error={error} />
      <Button size="sm" disabled={busy} onClick={() => void go()} data-testid="q1-ir-raise-ncr">{t("raiseNcr")}</Button>
    </div>
  );
}

function ScheduleForm({ ir, resched, onDone }: { ir: Ir; resched: boolean; onDone: () => void }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const me = useMeData();
  const { run, busy, error } = useRun();
  const [at, setAt] = useState(() => localInput(new Date(Date.now() + 2 * 3_600_000)));
  const [insp, setInsp] = useState(ir.responsible.some((u) => u.id === me.id) ? me.id : (ir.responsible[0]?.id ?? ""));
  const [reason, setReason] = useState("");
  async function go() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/schedule", {
      params: { path: { ir_id: ir.id } }, body: { scheduled_at: new Date(at).toISOString(), inspector_id: insp || null, reason: resched ? reason : null },
    })), t("scheduledToast"));
    if (out) onDone();
  }
  return (
    <Card className="mb-4" data-testid="q1-ir-schedule-form">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <MutationError error={error} />
        <FormField id="sch-at" label={t("scheduledAt")} required><Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} data-testid="q1-ir-schedule-at" /></FormField>
        <FormField id="sch-insp" label={t("inspector")} required>
          <Select value={insp} onChange={(e) => setInsp(e.target.value)} data-testid="q1-ir-inspector">
            {ir.responsible.map((u) => <option key={u.id} value={u.id}>{userText(u, ar)}</option>)}
          </Select>
        </FormField>
        {resched ? <FormField id="sch-reason" label={tc("reason")} required className="sm:col-span-2"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></FormField> : null}
        <div className="flex gap-2 sm:col-span-2">
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
          <Button disabled={busy || !at || !insp || (resched && reason.trim().length < 10)} onClick={() => void go()} data-testid="q1-ir-schedule-confirm">{t("schedule")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

type Answer = { item_code: string; answer: string; note?: string };

/** The inspection run on the phone: checklists, measurements (with M&TE), photos, result, sign-off. */
function Runner({ ir, project, review = false, waive = false, paperOnly = false, onDone }: { ir: Ir; project: Project; review?: boolean; waive?: boolean; paperOnly?: boolean; onDone: () => void }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const { options } = useQLabels();
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error, setError } = useRun();
  const [answers, setAnswers] = useState<Record<string, Record<string, Answer>>>({});
  const crit = ir.points.flatMap((p) => p.criteria.map((c) => ({ seq: p.seq, c })));
  const [meas, setMeas] = useState<Record<string, { value: string; mte_id: string; verdict: string }>>({});
  const [photos, setPhotos] = useState<PhotoIn[]>([]);
  const [result, setResult] = useState<S["QIrResult"] | "">("");
  const [comment, setComment] = useState("");
  const [comments, setComments] = useState<string[]>([""]);
  const [category, setCategory] = useState("");
  const [closeFirst, setCloseFirst] = useState(false);
  const [raiseNcr, setRaiseNcr] = useState(false);
  const [paper, setPaper] = useState(paperOnly);
  const [pp, setPp] = useState(emptyPaper());
  const [cuid] = useState(newUuid);
  const recordedAt = useMemo(() => new Date().toISOString(), []);
  const lists = review ? [] : ir.checklists;
  const setA = (seq: number, code: string, patch: Partial<Answer>) =>
    setAnswers((x) => ({ ...x, [seq]: { ...(x[seq] ?? {}), [code]: { item_code: code, answer: "compliant", ...(x[seq]?.[code] ?? {}), ...patch } } }));
  function body(): S["QIrDecide"] {
    const ans: Record<string, S["AnswerInput"][]> = {};
    for (const cl of lists) {
      if (cl.seq == null) continue;
      ans[String(cl.seq)] = cl.items.map((it) => {
        const a = answers[cl.seq!]?.[it.item_code];
        return { item_code: it.item_code, answer: a?.answer ?? "compliant", note: a?.note || null, photos: [], fixed_on_spot: false, ca_required: false };
      });
    }
    return {
      result: (result || "approved") as S["QIrResult"], comment: comment || null,
      comments: result === "approved_with_comments" ? comments.filter((c) => c.trim()).map((c) => ({ text_en: ar ? null : c, text_ar: ar ? c : null })) : [],
      reject_category: result === "rejected" ? (category as S["QNcrCategory"]) : null,
      close_comments_before_next_hold: closeFirst, answers: result === "not_ready" ? {} : ans,
      measurements: result === "not_ready" ? [] : crit.map(({ seq, c }) => {
        const m = meas[`${seq}:${c.id}`];
        return { point_seq: seq, criterion_id: c.id, value: m?.value && c.kind !== "pass_fail" && c.kind !== "text" ? m.value : null, verdict: m?.verdict ? (m.verdict as "pass" | "fail") : null, mte_id: m?.mte_id || null };
      }),
      photos, raise_ncr: raiseNcr, paper: paper ? pp : null, client_uuid: cuid, recorded_at: recordedAt, ncr_owner_id: null,
    };
  }
  async function go() {
    if (waive) {
      const out = await run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/waive", {
        params: { path: { ir_id: ir.id } }, body: { answers: body().answers, measurements: body().measurements, photos, comment: comment || null },
      })), t("waivedToast"));
      if (out) onDone();
      return;
    }
    setError(null);
    const r = await submitWithOutbox<{ id: string }>("q_ir_round", project.id, { ...body(), ir_id: ir.id }, `${ir.ir_no} · ${result}`);
    if (r.status === "queued") {
      toast.info(t("queued"));
      onDone();
      return;
    }
    if (r.status === "rejected") {
      setError(qError(r.error));
      return;
    }
    await run(async () => r.record, t("decidedToast"));
    onDone();
  }
  const needsPhoto = result === "rejected" || waive;
  const ok = (waive || result) && (!needsPhoto || photos.length > 0 || ir.rounds.some((x) => x.round_no === ir.current_round && x.photo_ids.length))
    && (result !== "rejected" || category) && (result !== "approved_with_comments" || comments.some((c) => c.trim())) && (!paper || paperReady(pp));
  return (
    <Card className="mb-4" data-testid="q1-ir-runner">
      <CardContent className="flex flex-col gap-4 p-4">
        <p className="font-medium">{waive ? t("waiveTitle") : review ? t("reviewTitle") : t("runTitle")}</p>
        <MutationError error={error} />
        {lists.map((cl) => (
          <FormSection key={`${cl.seq}-${cl.template_code}`} title={`${t("checklistFor", { seq: cl.seq ?? 0 })} · ${cl.template_code} — ${ar ? cl.title_ar : cl.title_en}`}>
            <ul className="flex flex-col gap-2 sm:col-span-2" data-testid={`q1-runner-list-${cl.seq}`}>
              {cl.items.map((it) => {
                const a = answers[cl.seq!]?.[it.item_code];
                const val = a?.answer ?? "compliant";
                return (
                  <li key={it.item_code} className="rounded-md border p-2 text-sm" data-item={it.item_code}>
                    <p dir="auto">{ar ? it.text_ar || it.text_en : it.text_en}{it.critical ? <span className="ms-1 text-xs font-semibold text-danger">{t("critical")}</span> : null}</p>
                    <div className="mt-1 flex flex-wrap gap-1" role="radiogroup">
                      {(["compliant", "non_compliant", ...(it.na_allowed ? ["na"] : [])] as ("compliant" | "non_compliant" | "na")[]).map((v) => (
                        <button key={v} type="button" role="radio" aria-checked={val === v} onClick={() => setA(cl.seq!, it.item_code, { answer: v })} data-testid={`q1-ans-${cl.seq}-${it.item_code}-${v}`}
                          className={`min-h-touch rounded-md border px-3 text-xs ${val === v ? (v === "non_compliant" ? "border-danger bg-danger/10 font-semibold" : "border-primary bg-primary/10 font-semibold") : ""}`}>
                          {t(`answer.${v}`)}
                        </button>
                      ))}
                    </div>
                    {val === "non_compliant" ? <Input className="mt-1" placeholder={t("ncNote")} value={a?.note ?? ""} onChange={(e) => setA(cl.seq!, it.item_code, { note: e.target.value })} data-testid={`q1-ans-${cl.seq}-${it.item_code}-note`} /> : null}
                  </li>
                );
              })}
            </ul>
          </FormSection>
        ))}
        {crit.length && !review ? (
          <FormSection title={t("measurements")}>
            {crit.map(({ seq, c }) => {
              const k = `${seq}:${c.id}`;
              const m = meas[k] ?? { value: "", mte_id: "", verdict: "" };
              const setM = (patch: Partial<typeof m>) => setMeas((x) => ({ ...x, [k]: { ...m, ...patch } }));
              const verdictOnly = c.kind === "pass_fail" || c.kind === "text";
              return (
                <div key={k} className="grid gap-2 rounded-md border p-2 sm:col-span-2 sm:grid-cols-3" data-testid={`q1-meas-${seq}-${c.code}`}>
                  <p className="text-sm sm:col-span-3"><span className="ltr font-mono">{seq}</span> · <span className="ltr">{c.code} v{c.version}</span> — {ar ? c.title_ar || c.title_en : c.title_en}</p>
                  {verdictOnly ? (
                    <Select value={m.verdict} onChange={(e) => setM({ verdict: e.target.value })} aria-label={t("verdict")} data-testid={`q1-meas-${seq}-${c.code}-verdict`}>
                      <option value="">{tc("select")}</option>
                      <option value="pass">{t("pass")}</option>
                      <option value="fail">{t("fail")}</option>
                    </Select>
                  ) : (
                    <Input inputMode="decimal" className="ltr" placeholder={c.unit ?? t("value")} aria-label={t("value")} value={m.value} onChange={(e) => setM({ value: e.target.value })} data-testid={`q1-meas-${seq}-${c.code}-value`} />
                  )}
                  <Select value={m.mte_id} onChange={(e) => setM({ mte_id: e.target.value })} aria-label={t("mte")}>
                    <option value="">{t("noMte")}</option>
                    {(mte.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.mte_no} — {x.description}</option>)}
                  </Select>
                </div>
              );
            })}
          </FormSection>
        ) : null}
        <FormField id="run-photos" label={t("photos")} required={needsPhoto}><PhotoPicker value={photos} onChange={setPhotos} max={20} testId="q1-run-photos" /></FormField>
        {!waive ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium">{t("result")}</p>
            <div className="flex flex-wrap gap-2" role="radiogroup">
              {(["approved", "approved_with_comments", "rejected", ...(review ? [] : ["not_ready"])] as ("approved" | "approved_with_comments" | "rejected" | "not_ready")[]).map((r) => (
                <Button key={r} type="button" variant={result === r ? "default" : "outline"} role="radio" aria-checked={result === r} onClick={() => setResult(r)} data-testid={`q1-result-${r}`}>{t(`resultLabel.${r}`)}</Button>
              ))}
            </div>
          </div>
        ) : null}
        {result === "approved_with_comments" ? (
          <div className="flex flex-col gap-2" data-testid="q1-run-comments">
            {comments.map((c, i) => <Input key={i} value={c} placeholder={t("commentN", { n: i + 1 })} onChange={(e) => setComments((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))} data-testid={`q1-run-comment-${i}`} />)}
            <Button type="button" size="sm" variant="ghost" className="self-start" onClick={() => setComments((xs) => [...xs, ""])}>{t("addComment")}</Button>
            <CheckboxField id="run-close-first" label={t("closeBeforeNextHold")}><Checkbox checked={closeFirst} onChange={(e) => setCloseFirst(e.target.checked)} /></CheckboxField>
          </div>
        ) : null}
        {result === "rejected" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="run-cat" label={t("rejectCategory")} required>
              <Select value={category} onChange={(e) => setCategory(e.target.value)} data-testid="q1-run-category">
                <option value="">{tc("select")}</option>
                {options("ncr_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </FormField>
            <CheckboxField id="run-ncr" label={t("raiseNcrNow")}><Checkbox checked={raiseNcr} onChange={(e) => setRaiseNcr(e.target.checked)} data-testid="q1-run-raise-ncr" /></CheckboxField>
            {ir.ncr_required_next || ir.current_round >= 2 ? <p className="text-xs text-warning sm:col-span-2">{t("ncrRequiredHint")}</p> : null}
          </div>
        ) : null}
        <FormField id="run-comment" label={t("comment")} hint={result === "rejected" || result === "not_ready" ? tc("minChars", { n: 10 }) : tc("noNames")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} data-testid="q1-run-comment" />
        </FormField>
        {!waive && !paperOnly ? <CheckboxField id="run-paper" label={t("paperInstead")}><Checkbox checked={paper} onChange={(e) => setPaper(e.target.checked)} /></CheckboxField> : null}
        {paper ? <PaperFields value={pp} onChange={setPp} /> : null}
        <OutboxPanel kind="q_ir_round" projectId={project.id} />
        <div className="sticky bottom-0 flex gap-2 bg-background py-2">
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
          <Button disabled={busy || !ok} onClick={() => void go()} data-testid="q1-run-sign">{waive ? t("recordWaiver") : t("sign")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Reinspect({ ir, onDone }: { ir: Ir; onDone: () => void }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const { run, busy, error } = useRun();
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<PhotoIn[]>([]);
  return (
    <Card className="mb-4" data-testid="q1-ir-reinspect-form">
      <CardContent className="flex flex-col gap-3 p-4">
        <MutationError error={error} />
        <FormField id="re-note" label={t("correctionNote")} hint={tc("minChars", { n: 20 })} required><Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} data-testid="q1-reinspect-note" /></FormField>
        <PhotoPicker value={photos} onChange={setPhotos} testId="q1-reinspect-photos" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
          <Button disabled={busy || note.trim().length < 20 || !photos.length} data-testid="q1-reinspect-confirm"
            onClick={async () => { const r = await run(() => unwrap(api.POST("/api/v1/quality/inspection-requests/{ir_id}/reinspection", { params: { path: { ir_id: ir.id } }, body: { note, photos } }))); if (r) onDone(); }}>
            {t("requestReinspection")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Rounds({ ir, canUpload }: { ir: Ir; canUpload: boolean }) {
  const t = useTranslations("quality.q1.ir");
  const ar = useLocale() === "ar";
  const { dateTime } = useFormatters();
  const { l } = useQLabels();
  if (!ir.rounds.length) return <EmptyState message={t("noRounds")} />;
  return (
    <div className="flex flex-col gap-3" data-testid="q1-ir-rounds">
      {[...ir.rounds].reverse().map((r) => (
        <Card key={r.id} data-testid="q1-ir-round" data-round={r.round_no} data-result={r.result ?? ""}>
          <CardContent className="flex flex-col gap-2 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t("roundN", { n: r.round_no })}</span>
              {r.result ? <Q1Status kind="ir_result" value={r.result} /> : null}
              {r.review_result ? <span className="text-xs">{t("reviewed")}: <Q1Status kind="ir_result" value={r.review_result} /></span> : null}
              {r.needs_confirmation ? <span className="text-xs text-warning">{t("needsConfirmation")}</span> : null}
            </div>
            <p className="text-xs text-muted-foreground">
              {r.scheduled_at ? t("scheduledFor", { at: dateTime(r.scheduled_at) }) : t("notScheduled")}
              {r.inspector ? ` · ${userText(r.inspector, ar)}` : ""}
              {r.reschedule_count ? ` · ${t("rescheduled", { n: r.reschedule_count })}` : ""}
            </p>
            {r.correction_note ? <p dir="auto">{t("correctionNote")}: {r.correction_note}</p> : null}
            {r.comment ? <p dir="auto">{r.comment}</p> : null}
            {r.reject_category ? <p className="text-xs">{t("rejectCategory")}: {l("ncr_category", r.reject_category)}</p> : null}
            {r.measurements.length ? (
              <ul className="text-xs" data-testid="q1-round-measurements">
                {r.measurements.map((m, i) => (
                  <li key={i}>
                    <span className="ltr">{m.point_seq} · {m.criterion_code ?? m.name} = {m.value ?? "—"} {m.unit ?? ""}</span>
                    {m.verdict ? <span className={`ms-1 ${m.verdict === "fail" ? "text-danger" : ""}`}>({l("verdict", m.verdict)})</span> : null}
                    {m.mte_no ? <span className="ltr ms-1 text-muted-foreground">{m.mte_no}{m.mte_cal_due_on ? ` · ${m.mte_cal_due_on}` : ""}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {r.responses.map((x) => (
              <p key={x.seq} className="text-xs">
                <span className="ltr">{x.template_code}</span> · {t("checklistScore", { ok: x.compliant_count ?? 0, n: x.applicable_count ?? 0 })}
                {x.critical_fail_count ? <span className="ms-1 text-danger">{t("criticalFails", { n: x.critical_fail_count })}</span> : null}
              </p>
            ))}
            <ApiWarnings warnings={(r.warnings ?? []) as S["ApiWarning"][]} />
            {r.round_no === ir.current_round || r.photo_ids.length ? (
              <Attachments ownerType="q_ir_round" ownerId={r.id} canUpload={canUpload && r.round_no === ir.current_round} canDelete={false} max={20} />
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function Comments({ ir }: { ir: Ir }) {
  const t = useTranslations("quality.q1.ir");
  const tc = useTranslations("quality.common");
  const b = useBilingual();
  const { date } = useFormatters();
  const { run, busy, error } = useRun();
  const [reply, setReply] = useState<Record<string, string>>({});
  if (!ir.comments.length) return <EmptyState message={t("noComments")} />;
  return (
    <div className="flex flex-col gap-2" data-testid="q1-ir-comments">
      <MutationError error={error} />
      {ir.comments.map((c) => (
        <Card key={c.id} data-testid="q1-ir-comment" data-status={c.status}>
          <CardContent className="flex flex-col gap-2 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Q1Status kind="ir_comment_status" value={c.status} />
              <span className={`text-xs ${c.overdue ? "font-medium text-danger" : "text-muted-foreground"}`}>{t("dueOn", { d: date(c.due_on) })}</span>
            </div>
            <p dir="auto">{b(c.text_en, c.text_ar)}</p>
            {c.response_text ? <p className="text-xs" dir="auto">{t("response")}: {c.response_text}</p> : null}
            {c.reopen_comment ? <p className="text-xs text-warning" dir="auto">{c.reopen_comment}</p> : null}
            {c.status !== "closed" ? (
              <div className="flex flex-wrap gap-2">
                <Input className="min-w-48 flex-1" value={reply[c.id] ?? ""} onChange={(e) => setReply((x) => ({ ...x, [c.id]: e.target.value }))} placeholder={t("responsePlaceholder")} data-testid="q1-comment-reply" />
                <Button size="sm" variant="outline" disabled={busy || (reply[c.id] ?? "").trim().length < 10}
                  onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/ir-comments/{comment_id}/respond", { params: { path: { comment_id: c.id } }, body: { response_text: reply[c.id] ?? "", photos: [] } })))}
                  data-testid="q1-comment-respond">{t("respond")}</Button>
                <Button size="sm" disabled={busy}
                  onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/ir-comments/{comment_id}/close", { params: { path: { comment_id: c.id } }, body: { accept: true } })))}
                  data-testid="q1-comment-close">{t("closeComment")}</Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ))}
      <span className="sr-only">{tc("status")}</span>
    </div>
  );
}
