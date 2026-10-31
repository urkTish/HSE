"use client";
import { Map as MapIcon, Plus, Upload } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type MouseEvent } from "react";
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
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQPlan, useQPlans, useQPunch, useQPunchItem } from "@/lib/api/quality/q1";
import { newUuid } from "@/lib/field-offline";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { useQualityRefresh } from "@/lib/api/quality/q0";
import { QGate, ReasonDialog, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type S } from "../q0/common";
import { emptyPaper, LinkList, PaperFields, paperReady, type PhotoIn, PhotoPicker, Q1Status, SignoffList } from "./shared";

type Item = S["QPunchListItem"];
type Plan = S["QFloorPlanRead"];
const PAGE_SIZE = 50;

const PIN_COLOUR: Record<string, string> = { open: "bg-danger", ready_for_review: "bg-warning", closed: "bg-success", voided: "bg-muted-foreground" };

/** The plan image with its pins (percent positions; the plan stays left-to-right in Arabic, no BIM, Q-PIN-02). */
function PlanView({ plan, pins, onPick, picked, testId = "q1-plan-view" }: { plan: Plan; pins: Item[]; onPick?: (x: number, y: number) => void; picked?: { x: number; y: number } | null; testId?: string }) {
  const t = useTranslations("quality.q1.punch");
  const ref = useRef<HTMLDivElement>(null);
  function click(e: MouseEvent<HTMLDivElement>) {
    if (!onPick || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    onPick(Math.round(((e.clientX - r.left) / r.width) * 10000) / 100, Math.round(((e.clientY - r.top) / r.height) * 10000) / 100);
  }
  return (
    <div dir="ltr" className="relative w-full overflow-hidden rounded-lg border bg-white" style={{ aspectRatio: `${plan.width_px} / ${plan.height_px}` }} ref={ref} onClick={click} data-testid={testId} role={onPick ? "button" : undefined} aria-label={onPick ? t("tapToPin") : undefined}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/api/v1/quality/floor-plans/${plan.id}/image`} alt={plan.title_en} className="absolute inset-0 size-full object-contain" draggable={false} />
      {pins.map((p) => (
        <Link key={p.id} href={`/quality/punch/${p.id}`} onClick={(e) => e.stopPropagation()} data-testid="q1-pin" data-status={p.status}
          className={`absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white text-[10px] font-bold text-white shadow ${PIN_COLOUR[p.status] ?? "bg-info"} ${p.pin_check ? "ring-2 ring-warning" : ""}`}
          style={{ left: `${p.pin_x_pct}%`, top: `${p.pin_y_pct}%` }} title={`${p.punch_no} (${p.category})`}>
          {p.category}
        </Link>
      ))}
      {picked ? <span className="absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary shadow" style={{ left: `${picked.x}%`, top: `${picked.y}%` }} data-testid="q1-pin-new" /> : null}
    </div>
  );
}

function PinLegend() {
  const t = useTranslations("quality.q1.punch");
  return (
    <p className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
      <span><span className="me-1 inline-block size-3 rounded-full bg-danger align-middle" />{t("legendOpen")}</span>
      <span><span className="me-1 inline-block size-3 rounded-full bg-warning align-middle" />{t("legendReady")}</span>
      <span><span className="me-1 inline-block size-3 rounded-full bg-success align-middle" />{t("legendClosed")}</span>
      <span>{t("legendLetter")}</span>
    </p>
  );
}

/* ═════════════ register `/quality/punch` ═════════════ */

export function PunchListPage() {
  return <QGate>{(p) => <Register project={p} />}</QGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.punch");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const b = useBilingual();
  const caps = useQCaps(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const planId = s.get("plan") ?? "";
  const plans = useQPlans(project.id, { zone_id: s.get("zone") || null });
  const r = useQPunch(project.id, {
    status: s.get("status") ? [s.get("status") as S["QPunchStatus"]] : null,
    zone_id: s.get("zone") || null,
    category: (s.get("category") || null) as S["QPunchCategory"] | null,
    engagement_id: s.get("engagement") || null,
    floor_plan_id: planId || null,
    overdue: s.getBool("overdue") ?? false,
    q: q || null,
    page,
    page_size: planId ? 200 : PAGE_SIZE,
  });
  const plan = useQPlan(planId);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            <Button variant="outline" asChild><Link href="/quality/floor-plans"><MapIcon aria-hidden />{t("plans")}</Link></Button>
            {caps.write("punch.record") ? (
              <Button asChild data-testid="q1-punch-new"><Link href="/quality/punch/new"><Plus aria-hidden />{t("new")}</Link></Button>
            ) : null}
          </>
        }
      />
      <ListToolbar>
        <SearchFilter id="q1-pu-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q1-pu-status" label={tc("status")} value={s.get("status") ?? ""} onChange={(v) => s.set({ status: v, page: null })} options={options("punch_status")} />
        <SelectFilter id="q1-pu-cat" label={t("category")} value={s.get("category") ?? ""} onChange={(v) => s.set({ category: v, page: null })} options={options("punch_category")} />
        <SelectFilter id="q1-pu-zone" label={t("zone")} value={s.get("zone") ?? ""} onChange={(v) => s.set({ zone: v, plan: null, page: null })} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} />
        <SelectFilter id="q1-pu-eng" label={t("contractor")} value={s.get("engagement") ?? ""} onChange={(v) => s.set({ engagement: v, page: null })} options={opts.engagements.map((e) => ({ value: e.value, label: e.label }))} />
        <SelectFilter id="q1-pu-overdue" label={tc("show")} value={s.getBool("overdue") ? "overdue" : ""} onChange={(v) => s.set({ overdue: v === "overdue" ? "true" : null, page: null })} options={[{ value: "overdue", label: tc("overdue") }]} />
        <SelectFilter id="q1-pu-plan" label={t("planView")} value={planId} onChange={(v) => s.set({ plan: v, page: null })} options={(plans.data ?? []).map((p) => ({ value: p.id, label: b(p.title_en, p.title_ar) }))} />
      </ListToolbar>
      {plan.data ? (
        <div className="mb-4">
          <PlanView plan={plan.data} pins={items.filter((x) => x.floor_plan_id === plan.data!.id && x.pin_x_pct != null)} />
          <PinLegend />
        </div>
      ) : null}
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q1-punch-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("category")}</TH>
                <TH>{tc("status")}</TH>
                <TH>{t("description")}</TH>
                <TH>{t("location")}</TH>
                <TH>{t("contractor")}</TH>
                <TH>{t("target")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="q1-punch-row" data-no={x.punch_no} data-status={x.status}>
                  <TD label={t("no")}><Link href={`/quality/punch/${x.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">{x.punch_no}</Link></TD>
                  <TD label={t("category")}><span className="ltr font-semibold">{x.category}</span></TD>
                  <TD label={tc("status")}><Q1Status kind="punch_status" value={x.status} /></TD>
                  <TD label={t("description")} data-full=""><span dir="auto">{b(x.description_en, x.description_ar)}</span></TD>
                  <TD label={t("location")} className="text-xs"><span dir="auto">{x.zone?.code} · {x.location_ref}</span>{x.floor_plan_id ? <span className="ms-1 text-muted-foreground">📍</span> : null}</TD>
                  <TD label={t("contractor")}>{x.engagement?.short_code ?? "—"}</TD>
                  <TD label={t("target")} className={x.overdue ? "font-medium text-danger" : ""} data-overdue={x.overdue ? "true" : undefined}>{date(x.target_date)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {!planId ? <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} /> : null}
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

/* ═════════════ record / walkdown `/quality/punch/new` (phone first) ═════════════ */

export function PunchNewPage() {
  return <QGate>{(p) => <NewItem project={p} />}</QGate>;
}

function NewItem({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.punch");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const b = useBilingual();
  const opts = useProjectOptions(project.id);
  const router = useRouter();
  const refresh = useQualityRefresh();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ site_id: "", zone_id: "", location_ref: "", discipline: "ARC", description_en: "", category: "B", raised_during: "walkdown", responsible_engagement_id: "" });
  const [photos, setPhotos] = useState<PhotoIn[]>([]);
  const [planId, setPlanId] = useState("");
  const [pin, setPin] = useState<{ x: number; y: number } | null>(null);
  const [walk, setWalk] = useState(false);
  const [count, setCount] = useState(0);
  const [cuid, setCuid] = useState(newUuid);
  const plans = useQPlans(project.id, { zone_id: f.zone_id || null }, { enabled: Boolean(f.zone_id) });
  const plan = useQPlan(planId);
  const existing = useQPunch(project.id, { floor_plan_id: planId || null, page_size: 200 }, { enabled: Boolean(planId) });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const ready = f.site_id && f.zone_id && f.responsible_engagement_id && f.description_en.trim() && f.location_ref.trim() && photos.length;
  async function save() {
    const body: S["QPunchCreate"] = {
      ...f, discipline: f.discipline as S["QDiscipline"], category: f.category as S["QPunchCategory"], raised_during: f.raised_during as S["QPunchRaisedDuring"],
      photos, pin: planId && pin ? { floor_plan_id: planId, x_pct: String(pin.x), y_pct: String(pin.y) } : null, client_uuid: cuid,
    };
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/punch", { params: { path: { project_id: project.id } }, body })), "");
    if (!out) return;
    toast.success(t("recorded", { no: out.punch_no }));
    if (walk) {
      // walkdown mode: keep site, zone, plan and contractor; next item
      setCount((n) => n + 1);
      setCuid(newUuid());
      setPhotos([]);
      setPin(null);
      setF((x) => ({ ...x, description_en: "", location_ref: "" }));
      await refresh();
    } else router.push(`/quality/punch/${out.id}`);
  }
  return (
    <div data-testid="q1-punch-form">
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/punch" }, { label: t("new") }]} />
      <PageHeader title={walk ? t("walkdown") : t("new")} description={t("newHint")} />
      <CheckboxField id="pu-walk" label={t("walkdownMode")}><Checkbox checked={walk} onChange={(e) => setWalk(e.target.checked)} data-testid="q1-punch-walkdown" /></CheckboxField>
      {walk && count ? <Alert tone="info" className="my-2" data-testid="q1-walk-count">{t("walkCount", { n: count })}</Alert> : null}
      <MutationError error={error} />
      <div className="mt-3 flex flex-col gap-4">
        <FormSection title={t("where")}>
          <FormField id="pu-site" label={t("site")} required>
            <Select value={f.site_id} onChange={set("site_id")} data-testid="q1-punch-site"><option value="">{tc("select")}</option>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="pu-zone" label={t("zone")} required>
            <Select value={f.zone_id} onChange={(e) => { set("zone_id")(e); setPlanId(""); setPin(null); }} data-testid="q1-punch-zone">
              <option value="">{tc("select")}</option>
              {opts.zones.filter((z) => !f.site_id || z.siteId === f.site_id).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="pu-eng" label={t("contractor")} required>
            <Select value={f.responsible_engagement_id} onChange={set("responsible_engagement_id")} data-testid="q1-punch-eng"><option value="">{tc("select")}</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="pu-plan" label={t("plan")}>
            <Select value={planId} onChange={(e) => { setPlanId(e.target.value); setPin(null); }} data-testid="q1-punch-plan">
              <option value="">—</option>
              {(plans.data ?? []).map((p) => <option key={p.id} value={p.id}>{b(p.title_en, p.title_ar)} · Rev.{p.revision}</option>)}
            </Select>
          </FormField>
          {plan.data ? (
            <div className="sm:col-span-2">
              <p className="mb-1 text-xs text-muted-foreground">{t("tapToPin")}</p>
              <PlanView plan={plan.data} pins={(existing.data?.items ?? []).filter((x) => x.pin_x_pct != null)} onPick={(x, y) => setPin({ x, y })} picked={pin} testId="q1-plan-pick" />
            </div>
          ) : null}
          <FormField id="pu-loc" label={t("location")} required><Input value={f.location_ref} onChange={set("location_ref")} maxLength={120} data-testid="q1-punch-location" /></FormField>
        </FormSection>
        <FormSection title={t("what")}>
          <FormField id="pu-desc" label={t("description")} hint={tc("noNames")} required className="sm:col-span-2"><Textarea value={f.description_en} onChange={set("description_en")} rows={2} maxLength={500} data-testid="q1-punch-desc" /></FormField>
          <FormField id="pu-cat" label={t("category")} required>
            <Select value={f.category} onChange={set("category")} data-testid="q1-punch-category">{options("punch_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="pu-disc" label={t("discipline")} required>
            <Select value={f.discipline} onChange={set("discipline")}>{options("discipline").map((o) => <option key={o.value} value={o.value}>{o.value} — {o.label}</option>)}</Select>
          </FormField>
          <FormField id="pu-during" label={t("raisedDuring")}>
            <Select value={f.raised_during} onChange={set("raised_during")}>{options("punch_raised_during").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="pu-photos" label={t("photoBefore")} required className="sm:col-span-2"><PhotoPicker value={photos} onChange={setPhotos} testId="q1-punch-photos" /></FormField>
        </FormSection>
        <div className="sticky bottom-0 flex gap-2 bg-background py-3">
          <Button disabled={busy || !ready} onClick={() => void save()} data-testid="q1-punch-save">{walk ? t("saveNext") : tc("save")}</Button>
          {walk ? <Button variant="outline" onClick={() => router.push("/quality/punch")}>{t("finishWalkdown")}</Button> : null}
        </div>
      </div>
    </div>
  );
}

/* ═════════════ item `/quality/punch/[id]` ═════════════ */

export function PunchDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <Detail project={p} id={id} />}</QGate>;
}

function Detail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.q1.punch");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const b = useBilingual();
  const { l } = useQLabels();
  const { date, dateTime } = useFormatters(project.id);
  const router = useRouter();
  const q = useQPunchItem(id);
  const plan = useQPlan(q.data?.floor_plan_id ?? "");
  const { run, busy, error } = useRun();
  const [after, setAfter] = useState<PhotoIn[]>([]);
  const [note, setNote] = useState("");
  const [verify, setVerify] = useState(false);
  const [comment, setComment] = useState("");
  const [paper, setPaper] = useState(false);
  const [pp, setPp] = useState(emptyPaper());
  const [voidOpen, setVoidOpen] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const it = q.data;
  if (!it) return null;
  const allowed = new Set(it.allowed_actions);
  const path = { params: { path: { item_id: it.id } } };
  async function decide(decision: "approved" | "rejected") {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/punch/{item_id}/verify", { ...path, body: { decision, comment: comment || null, paper: paper ? pp : null } })),
      decision === "approved" ? t("closedToast") : t("reopenedToast"));
    if (out) setVerify(false);
  }
  async function raiseNcr() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/ncrs", {
      params: { path: { project_id: it!.project_id } }, body: { source_type: "punch_item", source_id: it!.id, category: "workmanship", classification: "minor", open: false },
    })), "");
    if (out) router.push(`/quality/ncrs/${out.id}`);
  }
  return (
    <div data-testid="q1-punch-detail" data-status={it.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/punch" }, { label: it.punch_no }]} />
      <PageHeader
        title={<span className="ltr">{it.punch_no}</span>}
        badge={<span className="flex flex-wrap items-center gap-2"><span className="ltr rounded border px-2 text-sm font-semibold">{it.category}</span><Q1Status kind="punch_status" value={it.status} />{it.overdue ? <span className="text-xs font-medium text-danger">{tc("overdue")}</span> : null}</span>}
        description={<span dir="auto">{b(it.description_en, it.description_ar)}</span>}
        actions={
          <div className="flex flex-wrap gap-2">
            {allowed.has("verify") || allowed.has("paper_signoff") ? <Button onClick={() => { setVerify((v) => !v); setPaper(!allowed.has("verify")); }} data-testid="q1-punch-verify">{t("verify")}</Button> : null}
            {allowed.has("raise_ncr") ? <Button variant="outline" disabled={busy} onClick={() => void raiseNcr()} data-testid="q1-punch-ncr">{t("escalate")}</Button> : null}
            {allowed.has("void") ? <Button variant="ghost" onClick={() => setVoidOpen(true)}>{t("void")}</Button> : null}
          </div>
        }
      />
      <ApiWarnings warnings={it.warnings} className="mb-3" />
      <MutationError error={error} />
      {it.pin_check ? (
        <Alert tone="warning" className="mb-3" data-testid="q1-pin-check">
          <p>{t("pinCheck")}</p>
          {allowed.has("edit") ? <Button size="sm" className="mt-2" disabled={busy} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/punch/{item_id}", { ...path, body: { confirm_pin: true } })))} data-testid="q1-pin-confirm">{t("confirmPin")}</Button> : null}
        </Alert>
      ) : null}
      {verify ? (
        <Card className="mb-4" data-testid="q1-punch-verify-form">
          <CardContent className="flex flex-col gap-3 p-4">
            <FormField id="pu-v-comment" label={t("verifyComment")} hint={t("rejectNeedsComment")}><Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} data-testid="q1-punch-verify-comment" /></FormField>
            {allowed.has("verify") ? <CheckboxField id="pu-paper" label={t("paperInstead")}><Checkbox checked={paper} onChange={(e) => setPaper(e.target.checked)} /></CheckboxField> : null}
            {paper ? <PaperFields value={pp} onChange={setPp} /> : null}
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy || (paper && !paperReady(pp))} onClick={() => void decide("approved")} data-testid="q1-punch-close">{t("close")}</Button>
              <Button variant="outline" disabled={busy || comment.trim().length < 10 || (paper && !paperReady(pp))} onClick={() => void decide("rejected")} data-testid="q1-punch-reopen">{t("reopen")}</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="p-4">
            <FieldList className="lg:grid-cols-2">
              <FieldItem label={t("location")}>{it.site?.code} · {it.zone?.code} · <span dir="auto">{it.location_ref}</span></FieldItem>
              <FieldItem label={t("discipline")}>{l("discipline", it.discipline)}</FieldItem>
              <FieldItem label={t("contractor")}>{it.engagement?.short_code ?? "—"}</FieldItem>
              <FieldItem label={t("raisedDuring")}>{l("punch_raised_during", it.raised_during)}</FieldItem>
              <FieldItem label={t("raised")}>{dateTime(it.raised_at)} · {userText(it.raised_by, ar)}</FieldItem>
              <FieldItem label={t("target")}>{date(it.target_date)}</FieldItem>
              {it.ready_note ? <FieldItem label={t("fixNote")} wide>{it.ready_note}</FieldItem> : null}
              {it.closed_date ? <FieldItem label={t("closed")}>{date(it.closed_date)} · {userText(it.closed_by, ar)}</FieldItem> : null}
              {it.status_reason ? <FieldItem label={t("statusReason")} wide>{it.status_reason}</FieldItem> : null}
              {it.responsible.length ? <FieldItem label={t("verifier")} wide>{it.responsible.map((u) => userText(u, ar)).join(", ")}</FieldItem> : null}
              {it.ncrs.length ? <FieldItem label="NCR" wide>{it.ncrs.map((n) => <Link key={n.id} href={`/quality/ncrs/${n.id}`} className="ltr me-2 text-primary hover:underline">{n.ncr_no ?? "NCR"}</Link>)}</FieldItem> : null}
            </FieldList>
            <p className="mt-3 text-xs text-muted-foreground">{t("photosSummary", { before: it.photo_before_ids.length, after: it.photo_after_ids.length })}</p>
          </CardContent>
        </Card>
        {plan.data ? <div><PlanView plan={plan.data} pins={[it]} /><PinLegend /></div> : null}
      </div>
      {allowed.has("mark_ready") ? (
        <Card className="mt-4" data-testid="q1-punch-ready-form">
          <CardContent className="flex flex-col gap-3 p-4">
            <p className="font-medium">{t("markFixed")}</p>
            <FormField id="pu-note" label={t("fixNote")} hint={tc("minChars", { n: 10 })} required><Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} data-testid="q1-punch-fix-note" /></FormField>
            <PhotoPicker value={after} onChange={setAfter} testId="q1-punch-after" />
            <Button className="self-start" disabled={busy} data-testid="q1-punch-ready"
              onClick={async () => { const r = await run(() => unwrap(api.POST("/api/v1/quality/punch/{item_id}/ready", { ...path, body: { note, photos: after } })), t("readyToast")); if (r) { setAfter([]); setNote(""); } }}>
              {t("markFixed")}
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <div className="mt-6 flex flex-col gap-4">
        <h2 className="text-base font-semibold">{t("signoffs")}</h2>
        <SignoffList items={it.signoffs} recordType="punch_item" />
        <LinkList items={it.links} />
        <HistoryPanel entityType="q_punch_item" entityId={it.id} projectId={project.id} />
      </div>
      <ReasonDialog open={voidOpen} onOpenChange={setVoidOpen} title={t("void")} confirm={t("void")} min={20}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/punch/{item_id}/void", { ...path, body: { reason } })))} />
    </div>
  );
}

/* ═════════════ floor plans `/quality/floor-plans` ═════════════ */

export function FloorPlansPage() {
  return <QGate>{(p) => <Plans project={p} />}</QGate>;
}

function Plans({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.plan");
  const tc = useTranslations("quality.common");
  const b = useBilingual();
  const caps = useQCaps(project.id);
  const opts = useProjectOptions(project.id);
  const plans = useQPlans(project.id, {});
  const refresh = useQualityRefresh();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("punch.record") ? <Button onClick={() => setOpen((v) => !v)} data-testid="q1-plan-upload-open"><Upload aria-hidden />{t("upload")}</Button> : null} />
      {open ? <UploadForm projectId={project.id} zones={opts.zones.map((z) => ({ value: z.value, label: z.label }))} onDone={async () => { setOpen(false); await refresh(); }} /> : null}
      {plans.isLoading ? <LoadingState /> : (plans.data ?? []).length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="q1-plans">
          {(plans.data ?? []).map((p) => (
            <Link key={p.id} href={`/quality/floor-plans/${p.id}`} className="glass rounded-lg border p-3 text-sm hover:border-primary" data-testid="q1-plan-card">
              <p className="font-medium">{b(p.title_en, p.title_ar)} <span className="ltr text-xs text-muted-foreground">Rev.{p.revision}</span></p>
              <p className="text-xs text-muted-foreground">{p.zone?.code} · {p.level_label} · <span className="ltr">{p.width_px} × {p.height_px}</span></p>
              <p className="text-xs">{t("pinCount", { n: p.pin_count })} · {t("unpinned", { n: p.unpinned_count })}</p>
            </Link>
          ))}
        </div>
      ) : <EmptyState message={t("empty")} />}
      <span className="sr-only">{tc("status")}</span>
    </div>
  );
}

function UploadForm({ projectId, zones, revisionOf, onDone }: { projectId: string; zones: { value: string; label: string }[]; revisionOf?: Plan; onDone: () => void }) {
  const t = useTranslations("quality.q1.plan");
  const tc = useTranslations("quality.common");
  const [f, setF] = useState({ zone_id: revisionOf?.zone?.id ?? "", level_label: revisionOf?.level_label ?? "", title_en: revisionOf?.title_en ?? "", title_ar: revisionOf?.title_ar ?? "", revision: "" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function go() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    for (const [k, v] of Object.entries(f)) if (v) fd.append(k, v);
    if (revisionOf) fd.append("revision_of", revisionOf.id);
    try {
      const res = await fetch(`/api/v1/projects/${projectId}/quality/floor-plans`, { method: "POST", body: fd, credentials: "same-origin" });
      if (!res.ok) {
        const { toApiError } = await import("@/lib/api/client");
        throw toApiError(res.status, await res.json().catch(() => null));
      }
      toast.success(t("uploaded"));
      onDone();
    } catch (e) {
      const { qError } = await import("../q0/common");
      setError(qError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="mb-4" data-testid="q1-plan-upload">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <MutationError error={error} />
        {!revisionOf ? (
          <>
            <FormField id="pl-zone" label={t("zone")} required><Select value={f.zone_id} onChange={set("zone_id")} data-testid="q1-plan-zone"><option value="">{tc("select")}</option>{zones.map((z) => <option key={z.value} value={z.value}>{z.label}</option>)}</Select></FormField>
            <FormField id="pl-level" label={t("level")} required><Input value={f.level_label} onChange={set("level_label")} data-testid="q1-plan-level" /></FormField>
            <FormField id="pl-en" label={t("titleEn")} required><Input value={f.title_en} onChange={set("title_en")} data-testid="q1-plan-title-en" /></FormField>
            <FormField id="pl-ar" label={t("titleAr")} required><Input dir="rtl" value={f.title_ar} onChange={set("title_ar")} data-testid="q1-plan-title-ar" /></FormField>
          </>
        ) : null}
        <FormField id="pl-rev" label={t("revision")}><Input className="ltr" value={f.revision} onChange={set("revision")} /></FormField>
        <FormField id="pl-file" label={t("image")} hint={t("imageHint")} required><Input type="file" accept="image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="q1-plan-file" /></FormField>
        <div className="flex gap-2 sm:col-span-2">
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
          <Button disabled={busy || !file || (!revisionOf && (!f.zone_id || !f.title_en || !f.title_ar))} onClick={() => void go()} data-testid="q1-plan-upload-confirm">{t("upload")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function FloorPlanPage({ id }: { id: string }) {
  return <QGate>{(p) => <PlanDetail project={p} id={id} />}</QGate>;
}

function PlanDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.q1.plan");
  const b = useBilingual();
  const caps = useQCaps(project.id);
  const q = useQPlan(id);
  const router = useRouter();
  const [rev, setRev] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return null;
  const check = p.pins.filter((x) => x.pin_check).length;
  return (
    <div data-testid="q1-plan-detail">
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/floor-plans" }, { label: b(p.title_en, p.title_ar) }]} />
      <PageHeader title={b(p.title_en, p.title_ar)} description={`${p.zone?.code ?? ""} · ${p.level_label} · Rev.${p.revision}`}
        badge={<Q1Status kind="plan_status" value={p.status} />}
        actions={caps.write("punch.record") && p.status === "current" ? <Button variant="outline" onClick={() => setRev((v) => !v)} data-testid="q1-plan-revise">{t("newRevision")}</Button> : null} />
      {rev ? <UploadForm projectId={project.id} zones={[]} revisionOf={p} onDone={() => { setRev(false); router.push("/quality/floor-plans"); }} /> : null}
      {check ? <Alert tone="warning" className="mb-3" data-testid="q1-plan-check">{t("checkPins", { n: check })}</Alert> : null}
      <PlanView plan={p} pins={p.pins} />
      <PinLegend />
      <p className="mt-2 text-sm" data-testid="q1-plan-pin-count">{t("pinCount", { n: p.pin_count })}</p>
    </div>
  );
}

export type { Item as PunchItem };
