"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQAlert, useQAlerts, useQComplaint, useQComplaints, useQCustomers, useQNcrs, useQObservation, useQObservations, useQPositions } from "@/lib/api/quality/q0";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { QGate, ReasonDialog, StatusBadge, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type S } from "./common";

const PAGE_SIZE = 50;

/** Inline Phase 1 CA form shared by the observation page (source quality_observation). */
function CaForm({ projectId, onAdd, busy }: { projectId: string; onAdd: (body: S["QNcrActionCreate"]) => Promise<unknown>; busy: boolean }) {
  const t = useTranslations("quality.ncr");
  const { options } = useQLabels();
  const [f, setF] = useState({ title: "", description: "", control_level: "administrative", owner_id: "", verifier_id: "", due_date: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Card>
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2" data-testid="q-ca-form">
        <FormField id="ca-title" label={t("titleField")} required className="sm:col-span-2"><Input value={f.title} onChange={set("title")} data-testid="q-ca-title" /></FormField>
        <FormField id="ca-desc" label={t("caDescription")} required className="sm:col-span-2"><Textarea value={f.description} onChange={set("description")} rows={2} data-testid="q-ca-description" /></FormField>
        <FormField id="ca-control" label={t("controlLevel")}>
          <Select value={f.control_level} onChange={set("control_level")} data-testid="q-ca-control">
            {options("control_level_quality").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="ca-due" label={t("due")}><Input type="date" value={f.due_date} onChange={set("due_date")} /></FormField>
        <FormField id="ca-owner" label={t("caOwner")} required><UserSelect projectId={projectId} value={f.owner_id} onChange={set("owner_id")} data-testid="q-ca-owner" /></FormField>
        <FormField id="ca-verifier" label={t("caVerifier")} required hint={t("caVerifierHint")}><UserSelect projectId={projectId} value={f.verifier_id} onChange={set("verifier_id")} data-testid="q-ca-verifier" /></FormField>
        <Button
          className="self-start"
          disabled={busy || !f.title || !f.description || !f.owner_id || !f.verifier_id}
          onClick={() => void onAdd({ ...f, control_level: f.control_level as S["ControlLevel"], due_date: f.due_date || null })}
          data-testid="q-ca-add"
        >
          {t("addAction")}
        </Button>
      </CardContent>
    </Card>
  );
}

function CaList({ actions, projectId }: { actions: S["QCaSummary"][]; projectId: string }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const { date } = useFormatters(projectId);
  if (!actions.length) return <EmptyState message={t("noActions")} />;
  return (
    <Table compact data-testid="q-actions">
      <THead><TR><TH>{t("caRef")}</TH><TH>{t("titleField")}</TH><TH>{tc("status")}</TH><TH>{t("controlLevel")}</TH><TH>{t("due")}</TH></TR></THead>
      <TBody>
        {actions.map((a) => (
          <TR key={a.id}>
            <TD label={t("caRef")}><Link href={`/actions/${a.id}`} className="ltr text-primary hover:underline">{a.ref}</Link></TD>
            <TD label={t("titleField")} dir="auto">{a.title}</TD>
            <TD label={tc("status")}>{a.status}</TD>
            <TD label={t("controlLevel")}>{l("control_level_quality", a.control_level)}</TD>
            <TD label={t("due")}>{date(a.due_date)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/* ═════════════ observations `/quality/observations` (Q-OBS) ═════════════ */

export function ObservationListPage() {
  return <QGate>{(p) => <Observations project={p} />}</QGate>;
}

function Observations({ project }: { project: Project }) {
  const t = useTranslations("quality.obs");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const ar = useLocale() === "ar";
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const r = useQObservations(project.id, { status: status ? [status as S["QObservationStatus"]] : null, mine: s.getBool("mine") ?? false, page, page_size: PAGE_SIZE });
  const showNew = s.getBool("new") ?? false;
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={caps.write("ncr.raise") && !showNew ? (
          <Button onClick={() => s.set({ new: "true" })} data-testid="q-obs-new"><Plus aria-hidden />{t("new")}</Button>
        ) : null}
      />
      {showNew ? <ObservationForm project={project} onDone={() => s.set({ new: null })} /> : null}
      <ListToolbar>
        <SelectFilter id="q-obs-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("observation_status")} />
        <SelectFilter id="q-obs-mine" label={tc("show")} value={s.getBool("mine") ? "mine" : ""} onChange={(v) => s.set({ mine: v === "mine" ? "true" : null, page: null })} options={[{ value: "mine", label: tc("mine") }]} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-obs-table">
            <THead><TR><TH>{t("no")}</TH><TH>{tc("status")}</TH><TH>{t("category")}</TH><TH>{t("description")}</TH><TH>{t("raisedBy")}</TH><TH>{t("raisedAt")}</TH></TR></THead>
            <TBody>
              {items.map((o) => (
                <TR key={o.id} data-testid="q-obs-row" data-no={o.obs_no}>
                  <TD label={t("no")}><Link href={`/quality/observations/${o.id}`} className="ltr font-medium text-primary hover:underline">{o.obs_no}</Link></TD>
                  <TD label={tc("status")}><StatusBadge kind="observation_status" value={o.status} /></TD>
                  <TD label={t("category")}>{l("ncr_category", o.category)}<span className="block text-xs text-muted-foreground">{o.site_code}</span></TD>
                  <TD label={t("description")} data-full="" className="md:min-w-64"><span dir="auto" className="line-clamp-2">{o.description}</span></TD>
                  <TD label={t("raisedBy")} className="text-xs">{userText(o.raised_by, ar)}</TD>
                  <TD label={t("raisedAt")} className="text-xs">{dateTime(o.raised_at)}</TD>
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

function ObservationForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.obs");
  const tn = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ site_id: "", zone_id: "", engagement_id: "", location_ref: "", category: "", description: "", suggested_action: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "")) as unknown as S["QObservationCreate"];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/observations", { params: { path: { project_id: project.id } }, body })), t("saved"));
    if (out) {
      onDone();
      router.push(`/quality/observations/${out.id}`);
    }
  }
  return (
    <Card className="mb-4">
      <CardContent className="grid gap-4 p-4 sm:grid-cols-2" data-testid="q-obs-form">
        <MutationError error={error} />
        <FormField id="obs-site" label={tn("site")} required>
          <Select value={f.site_id} onChange={(e) => setF((x) => ({ ...x, site_id: e.target.value, zone_id: "" }))} data-testid="obs-site">
            <option value="">{tc("select")}</option>
            {opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="obs-zone" label={tn("zone")}>
          <Select value={f.zone_id} onChange={set("zone_id")}>
            <option value="">—</option>
            {opts.zones.filter((z) => z.siteId === f.site_id).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="obs-cat" label={t("category")} required>
          <Select value={f.category} onChange={set("category")} data-testid="obs-category">
            <option value="">{tc("select")}</option>
            {options("ncr_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="obs-eng" label={tn("responsible")}>
          <Select value={f.engagement_id} onChange={set("engagement_id")}>
            <option value="">—</option>
            {opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="obs-loc" label={tn("location")} className="sm:col-span-2"><Input value={f.location_ref} onChange={set("location_ref")} maxLength={120} /></FormField>
        <FormField id="obs-desc" label={t("description")} required hint={tc("minChars", { n: 10 })} className="sm:col-span-2">
          <Textarea value={f.description} onChange={set("description")} rows={3} data-testid="obs-description" />
        </FormField>
        <FormField id="obs-sugg" label={t("suggested")} className="sm:col-span-2"><Textarea value={f.suggested_action} onChange={set("suggested_action")} rows={2} /></FormField>
        <div className="flex gap-2 sm:col-span-2">
          <Button onClick={() => void save()} disabled={busy || !f.site_id || !f.category || f.description.trim().length < 10} data-testid="obs-save">{tc("save")}</Button>
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function ObservationDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <ObservationDetail project={p} id={id} />}</QGate>;
}

function ObservationDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.obs");
  const tn = useTranslations("quality.ncr");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const ar = useLocale() === "ar";
  const { dateTime } = useFormatters(project.id);
  const router = useRouter();
  const q = useQObservation(id);
  const { run, busy, error } = useRun();
  const [closing, setClosing] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const o = q.data;
  if (!o) return null;
  const path = { params: { path: { obs_id: o.id } } };
  const live = o.status !== "closed";
  async function escalate() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/observations/{obs_id}/ncr", { ...path, body: { source_type: "observation", open: false } })), t("escalated"));
    if (out) router.push(`/quality/ncrs/${out.id}`);
  }
  return (
    <div data-testid="q-obs-detail" data-status={o.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/observations" }, { label: o.obs_no }]} />
      <PageHeader
        title={<span className="ltr">{o.obs_no}</span>}
        badge={<StatusBadge kind="observation_status" value={o.status} />}
        actions={
          <>
            {live && !o.ncr_id && caps.write("ncr.raise") ? <Button onClick={() => void escalate()} disabled={busy} data-testid="q-obs-escalate">{t("escalate")}</Button> : null}
            {live ? <Button variant="outline" onClick={() => setClosing(true)} data-testid="q-obs-close">{t("close")}</Button> : null}
          </>
        }
      />
      <MutationError error={error} />
      <ApiWarnings warnings={o.warnings} className="mb-3" />
      <Card className="mb-4">
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("category")}>{l("ncr_category", o.category)}</FieldItem>
            <FieldItem label={tn("site")}>{o.site_code ?? "—"}</FieldItem>
            <FieldItem label={tn("location")}>{o.location_ref ?? "—"}</FieldItem>
            <FieldItem label={t("raisedBy")}>{userText(o.raised_by, ar)} · {dateTime(o.raised_at)}</FieldItem>
            <FieldItem label={t("description")} wide><span dir="auto" className="whitespace-pre-wrap">{o.description}</span></FieldItem>
            {o.suggested_action ? <FieldItem label={t("suggested")} wide><span dir="auto">{o.suggested_action}</span></FieldItem> : null}
            {o.ncr_id ? <FieldItem label={t("ncr")}><Link href={`/quality/ncrs/${o.ncr_id}`} className="text-primary hover:underline">{t("openNcr")}</Link></FieldItem> : null}
            {o.status_reason ? <FieldItem label={t("closeReason")} wide>{o.status_reason}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{tn("photos")}</h3><Attachments ownerType="q_observation" ownerId={o.id} canUpload={live && caps.write("ncr.raise")} /></CardContent></Card>
      <h2 className="mb-2 text-sm font-semibold">{tn("tab.actions")}</h2>
      <div className="flex flex-col gap-3">
        <CaList actions={o.actions} projectId={project.id} />
        {live && caps.write("ncr.manage") ? <CaForm projectId={project.id} busy={busy} onAdd={(body) => run(() => unwrap(api.POST("/api/v1/quality/observations/{obs_id}/actions", { ...path, body })))} /> : null}
      </div>
      <div className="mt-4"><HistoryPanel entityType="q_observation" entityId={o.id} projectId={project.id} /></div>
      <ReasonDialog open={closing} onOpenChange={setClosing} title={t("close")} min={10} confirm={t("close")} testId="q-obs-close-dialog"
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/observations/{obs_id}/close", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ quality alerts `/quality/alerts` (Q-QAL) ═════════════ */

export function AlertListPage() {
  return <QGate>{(p) => <Alerts project={p} />}</QGate>;
}

function Alerts({ project }: { project: Project }) {
  const t = useTranslations("quality.alert");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const bi = useBilingual();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const r = useQAlerts(project.id, { status: status ? [status as S["QAlertStatus"]] : null, page, page_size: PAGE_SIZE });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("ncr.manage") ? <Button asChild data-testid="q-alert-new"><Link href="/quality/alerts/new"><Plus aria-hidden />{t("new")}</Link></Button> : null} />
      <ListToolbar>
        <SelectFilter id="q-alert-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("alert_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-alert-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("severity")}</TH><TH>{tc("status")}</TH><TH>{t("titleField")}</TH><TH>{t("acks")}</TH><TH>{t("validUntil")}</TH></TR></THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="q-alert-row" data-no={a.alert_no ?? ""}>
                  <TD label={t("no")}><Link href={`/quality/alerts/${a.id}`} className="ltr font-medium text-primary hover:underline">{a.alert_no ?? t("draft")}</Link></TD>
                  <TD label={t("severity")}><Badge tone={a.severity === "stop_use" ? "danger" : a.severity === "warning" ? "warning" : "info"}>{l("alert_severity", a.severity)}</Badge></TD>
                  <TD label={tc("status")}><StatusBadge kind="alert_status" value={a.status} />{a.i_am_recipient && !a.i_acked && a.ack_required ? <Badge tone="warning" className="ms-1">{t("toAck")}</Badge> : null}</TD>
                  <TD label={t("titleField")} data-full=""><span dir="auto">{bi(a.title_en, a.title_ar)}</span></TD>
                  <TD label={t("acks")} className="ltr">{a.ack_required ? `${a.ack_count}/${a.recipient_count}` : "—"}</TD>
                  <TD label={t("validUntil")}>{date(a.valid_until)}</TD>
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

export function AlertNewPage() {
  return <QGate>{(p) => <AlertForm project={p} />}</QGate>;
}

const DIST_ROLES = ["qa_qc_manager", "quality_engineer", "qc_inspector", "warehouse_qc", "hse_manager", "hse_officer", "site_engineer"];

function AlertForm({ project }: { project: Project }) {
  const t = useTranslations("quality.alert");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const positions = useQPositions(project.id);
  const ar = useLocale() === "ar";
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ title_en: "", title_ar: "", message_en: "", message_ar: "", severity: "warning", applies_to: "", valid_until: "", lots: "" });
  const [roles, setRoles] = useState<string[]>([]);
  const [pos, setPos] = useState<string[]>([]);
  const [engs, setEngs] = useState<string[]>([]);
  const [sites, setSites] = useState<string[]>([]);
  const [ack, setAck] = useState(true);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const ready = f.title_en && f.title_ar && f.message_en && f.message_ar && (roles.length || pos.length || engs.length);
  async function save() {
    const body: S["QAlertCreate"] = {
      title_en: f.title_en, title_ar: f.title_ar, message_en: f.message_en, message_ar: f.message_ar,
      severity: f.severity as S["QAlertSeverity"], applies_to: f.applies_to || null, valid_until: f.valid_until || null,
      lot_refs: f.lots.split(/[,\n]/).map((x) => x.trim()).filter(Boolean), site_ids: sites,
      dist_roles: roles, dist_positions: pos, dist_engagement_ids: engs, ack_required: ack,
    };
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/alerts", { params: { path: { project_id: project.id } }, body })), t("drafted"));
    if (out) router.push(`/quality/alerts/${out.id}`);
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/alerts" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <MutationError error={error} />
      <Card>
        <CardContent className="flex flex-col gap-4 p-4" data-testid="q-alert-form">
          <FormSection title={t("message")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="al-ten" label={t("titleEn")} required><Input value={f.title_en} onChange={set("title_en")} dir="ltr" data-testid="al-title-en" /></FormField>
              <FormField id="al-tar" label={t("titleAr")} required><Input value={f.title_ar} onChange={set("title_ar")} dir="rtl" data-testid="al-title-ar" /></FormField>
              <FormField id="al-men" label={t("messageEn")} required><Textarea value={f.message_en} onChange={set("message_en")} rows={3} dir="ltr" data-testid="al-msg-en" /></FormField>
              <FormField id="al-mar" label={t("messageAr")} required><Textarea value={f.message_ar} onChange={set("message_ar")} rows={3} dir="rtl" data-testid="al-msg-ar" /></FormField>
              <FormField id="al-sev" label={t("severity")}>
                <Select value={f.severity} onChange={set("severity")} data-testid="al-severity">
                  {options("alert_severity").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="al-valid" label={t("validUntil")}><Input type="date" value={f.valid_until} onChange={set("valid_until")} /></FormField>
              <FormField id="al-applies" label={t("appliesTo")} className="sm:col-span-2"><Textarea value={f.applies_to} onChange={set("applies_to")} rows={2} /></FormField>
              <FormField id="al-lots" label={t("lots")} hint={t("lotsHint")} className="sm:col-span-2"><Input value={f.lots} onChange={set("lots")} dir="ltr" /></FormField>
            </div>
          </FormSection>
          <FormSection title={t("distribution")} description={t("distributionHint")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <MultiSelect id="al-roles" label={t("roles")} options={DIST_ROLES.map((r) => ({ value: r, label: l("role", r) }))} value={roles} onChange={setRoles} allLabel={tc("select")} testId="al-roles" />
              <MultiSelect id="al-pos" label={t("positions")} options={(positions.data ?? []).map((p) => ({ value: p.code, label: ar ? p.name_ar : p.name_en }))} value={pos} onChange={setPos} allLabel={tc("select")} />
              <MultiSelect id="al-engs" label={t("engagements")} options={opts.engagements.map((e) => ({ value: e.value, label: e.label }))} value={engs} onChange={setEngs} allLabel={tc("select")} />
              <MultiSelect id="al-sites" label={t("sites")} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} value={sites} onChange={setSites} allLabel={t("allSites")} />
              <CheckboxField id="al-ack" label={t("ackRequired")}><Checkbox checked={ack} onChange={(e) => setAck(e.target.checked)} /></CheckboxField>
            </div>
          </FormSection>
          <Button className="self-start" onClick={() => void save()} disabled={busy || !ready} data-testid="al-save">{t("saveDraft")}</Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function AlertDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <AlertDetail project={p} id={id} />}</QGate>;
}

function AlertDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.alert");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const bi = useBilingual();
  const q = useQAlert(id);
  const { run, busy, error } = useRun();
  const [withdraw, setWithdraw] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data;
  if (!a) return null;
  const path = { params: { path: { alert_id: a.id } } };
  return (
    <div data-testid="q-alert-detail" data-status={a.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/alerts" }, { label: a.alert_no ?? t("draft") }]} />
      <PageHeader
        title={<span className="ltr">{a.alert_no ?? t("draft")}</span>}
        badge={<span className="flex gap-2"><StatusBadge kind="alert_status" value={a.status} /><Badge tone={a.severity === "stop_use" ? "danger" : a.severity === "warning" ? "warning" : "info"}>{l("alert_severity", a.severity)}</Badge></span>}
        description={bi(a.title_en, a.title_ar)}
        actions={
          <>
            {a.status === "draft" && caps.write("ncr.manage") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/alerts/{alert_id}/issue", { ...path, body: {} })), t("issuedToast"))} data-testid="q-alert-issue">{t("issue")}</Button> : null}
            {a.can_ack ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/alerts/{alert_id}/ack", path)), t("acked"))} data-testid="q-alert-ack">{t("ack")}</Button> : null}
            {a.status === "issued" && caps.write("ncr.manage") ? <Button variant="outline" onClick={() => setWithdraw(true)} data-testid="q-alert-withdraw">{t("withdraw")}</Button> : null}
          </>
        }
      />
      <MutationError error={error} />
      <ApiWarnings warnings={a.warnings} className="mb-3" />
      {a.severity === "stop_use" && a.status === "issued" ? <Alert tone="danger" className="mb-3">{t("stopUseBanner")}</Alert> : null}
      <Card className="mb-4">
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("message")} wide><span dir="auto" className="whitespace-pre-wrap">{bi(a.message_en, a.message_ar)}</span></FieldItem>
            {a.applies_to ? <FieldItem label={t("appliesTo")} wide>{a.applies_to}</FieldItem> : null}
            {a.lot_refs.length ? <FieldItem label={t("lots")} ltr>{a.lot_refs.join(", ")}</FieldItem> : null}
            <FieldItem label={t("validUntil")}>{date(a.valid_until)}</FieldItem>
            <FieldItem label={t("issuedAt")}>{a.issued_at ? dateTime(a.issued_at) : "—"}</FieldItem>
            <FieldItem label={t("roles")}>{a.dist_roles.map((r) => l("role", r)).join(", ") || "—"}</FieldItem>
            <FieldItem label={t("positions")} ltr>{a.dist_positions.join(", ") || "—"}</FieldItem>
            <FieldItem label={t("acks")} ltr><span data-testid="q-alert-acks">{a.ack_required ? `${a.ack_count}/${a.recipient_count}${a.ack_pct ? ` (${a.ack_pct}%)` : ""}` : t("noAck")}</span></FieldItem>
            {a.status_reason ? <FieldItem label={t("withdrawReason")} wide>{a.status_reason}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card className="mb-4"><CardContent className="p-4"><Attachments ownerType="q_alert" ownerId={a.id} canUpload={a.status === "draft" && caps.write("ncr.manage")} /></CardContent></Card>
      <HistoryPanel entityType="q_quality_alert" entityId={a.id} projectId={project.id} />
      <ReasonDialog open={withdraw} onOpenChange={setWithdraw} title={t("withdraw")} confirm={t("withdraw")} testId="q-alert-withdraw-dialog"
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/alerts/{alert_id}/withdraw", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ customer complaints `/quality/complaints` (Q-CMP) ═════════════ */

export function ComplaintListPage() {
  return <QGate>{(p) => <Complaints project={p} />}</QGate>;
}

function Complaints({ project }: { project: Project }) {
  const t = useTranslations("quality.complaint");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const bi = useBilingual();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const r = useQComplaints(project.id, { status: status ? [status as S["QComplaintStatus"]] : null, page, page_size: PAGE_SIZE });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("complaint.manage") ? <Button asChild data-testid="q-complaint-new"><Link href="/quality/complaints/new"><Plus aria-hidden />{t("new")}</Link></Button> : null} />
      <ListToolbar>
        <SelectFilter id="q-cmp-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("complaint_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-complaint-table">
            <THead><TR><TH>{t("no")}</TH><TH>{tc("status")}</TH><TH>{t("customer")}</TH><TH>{t("severity")}</TH><TH>{t("description")}</TH><TH>{t("received")}</TH><TH>{t("responseDue")}</TH></TR></THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="q-complaint-row" data-no={c.complaint_no}>
                  <TD label={t("no")}><Link href={`/quality/complaints/${c.id}`} className="ltr font-medium text-primary hover:underline">{c.complaint_no}</Link></TD>
                  <TD label={tc("status")}><StatusBadge kind="complaint_status" value={c.status} /></TD>
                  <TD label={t("customer")}>{c.customer ? bi(String(c.customer.name_en ?? ""), String(c.customer.name_ar ?? "")) : "—"}</TD>
                  <TD label={t("severity")}>{l("complaint_severity", c.severity)}</TD>
                  <TD label={t("description")} data-full=""><span dir="auto" className="line-clamp-2">{c.description}</span></TD>
                  <TD label={t("received")} className="text-xs">{dateTime(c.received_at)}</TD>
                  <TD label={t("responseDue")} className={`text-xs ${c.response_overdue ? "font-medium text-danger" : ""}`}>{dateTime(c.response_due_at)}</TD>
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

export function ComplaintNewPage() {
  return <QGate>{(p) => <ComplaintForm project={p} />}</QGate>;
}

function ComplaintForm({ project }: { project: Project }) {
  const t = useTranslations("quality.complaint");
  const tc = useTranslations("quality.common");
  const tn = useTranslations("quality.ncr");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const customers = useQCustomers(project.id);
  const bi = useBilingual();
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ customer_id: "", site_id: "", channel: "email", customer_reference: "", category: "", description: "", product_refs: "", severity: "medium", received_at: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "")) as Record<string, string>;
    if (body.received_at) body.received_at = new Date(body.received_at).toISOString();
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/complaints", { params: { path: { project_id: project.id } }, body: body as unknown as S["QComplaintCreate"] })), t("recorded"));
    if (out) router.push(`/quality/complaints/${out.id}`);
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/complaints" }, { label: t("new") }]} />
      <PageHeader title={t("new")} />
      <MutationError error={error} />
      <Card>
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2" data-testid="q-complaint-form">
          <FormField id="cmp-cust" label={t("customer")} required>
            <Select value={f.customer_id} onChange={set("customer_id")} data-testid="cmp-customer">
              <option value="">{tc("select")}</option>
              {(customers.data ?? []).filter((c) => c.status === "active").map((c) => <option key={c.id} value={c.id}>{c.code} — {bi(c.name_en, c.name_ar)}</option>)}
            </Select>
          </FormField>
          <FormField id="cmp-site" label={tn("site")}>
            <Select value={f.site_id} onChange={set("site_id")}>
              <option value="">—</option>
              {opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="cmp-channel" label={t("channel")}>
            <Select value={f.channel} onChange={set("channel")}>{options("complaint_channel").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="cmp-received" label={t("received")}><Input type="datetime-local" value={f.received_at} onChange={set("received_at")} /></FormField>
          <FormField id="cmp-cat" label={t("category")} required>
            <Select value={f.category} onChange={set("category")} data-testid="cmp-category">
              <option value="">{tc("select")}</option>
              {options("ncr_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="cmp-sev" label={t("severity")}>
            <Select value={f.severity} onChange={set("severity")}>{options("complaint_severity").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          </FormField>
          <FormField id="cmp-ref" label={t("customerRef")}><Input value={f.customer_reference} onChange={set("customer_reference")} dir="ltr" /></FormField>
          <FormField id="cmp-prod" label={t("productRefs")}><Input value={f.product_refs} onChange={set("product_refs")} dir="ltr" /></FormField>
          <FormField id="cmp-desc" label={t("description")} required hint={tc("minChars", { n: 10 })} className="sm:col-span-2">
            <Textarea value={f.description} onChange={set("description")} rows={4} data-testid="cmp-description" />
          </FormField>
          <Button className="self-start" onClick={() => void save()} disabled={busy || !f.customer_id || !f.category || f.description.trim().length < 10} data-testid="cmp-save">{tc("save")}</Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function ComplaintDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <ComplaintDetail project={p} id={id} />}</QGate>;
}

function ComplaintDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.complaint");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const bi = useBilingual();
  const q = useQComplaint(id);
  const ncrs = useQNcrs(project.id, { page_size: 100 });
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ investigation_note: "", justified: "", ncr_id: "", response_en: "", response_ar: "", satisfied: "" });
  const [withdraw, setWithdraw] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  if (!c) return null;
  const path = { params: { path: { complaint_id: c.id } } };
  const manage = caps.write("complaint.manage");
  const go = (to: S["QComplaintStatus"], extra: Partial<S["QComplaintTransition"]> = {}) =>
    run(() => unwrap(api.POST("/api/v1/quality/complaints/{complaint_id}/transitions", { ...path, body: { to_status: to, ...extra } })));
  const clean = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== ""));
  return (
    <div data-testid="q-complaint-detail" data-status={c.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/complaints" }, { label: c.complaint_no }]} />
      <PageHeader title={<span className="ltr">{c.complaint_no}</span>} badge={<StatusBadge kind="complaint_status" value={c.status} />}
        description={c.customer ? bi(String(c.customer.name_en ?? ""), String(c.customer.name_ar ?? "")) : undefined}
        actions={manage && ["received", "acknowledged", "under_investigation"].includes(c.status) ? <Button variant="outline" onClick={() => setWithdraw(true)} data-testid="q-cmp-withdraw">{t("withdraw")}</Button> : null} />
      <MutationError error={error} />
      <ApiWarnings warnings={c.warnings} className="mb-3" />
      {c.ack_overdue ? <Alert tone="danger" className="mb-3">{t("ackOverdue")}</Alert> : null}
      {c.response_overdue ? <Alert tone="danger" className="mb-3">{t("responseOverdue")}</Alert> : null}
      <Card className="mb-4">
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("channel")}>{l("complaint_channel", c.channel)}</FieldItem>
            <FieldItem label={t("severity")}>{l("complaint_severity", c.severity)}</FieldItem>
            <FieldItem label={t("category")}>{l("ncr_category", c.category)}</FieldItem>
            <FieldItem label={t("received")}>{dateTime(c.received_at)}</FieldItem>
            <FieldItem label={t("ackDue")}>{dateTime(c.ack_due_at)}</FieldItem>
            <FieldItem label={t("responseDue")}>{dateTime(c.response_due_at)}</FieldItem>
            {c.customer_reference ? <FieldItem label={t("customerRef")} ltr>{c.customer_reference}</FieldItem> : null}
            {c.product_refs ? <FieldItem label={t("productRefs")} ltr>{c.product_refs}</FieldItem> : null}
            <FieldItem label={t("description")} wide><span dir="auto" className="whitespace-pre-wrap">{c.description}</span></FieldItem>
            {c.investigation_note ? <FieldItem label={t("investigation")} wide><span dir="auto">{c.investigation_note}</span></FieldItem> : null}
            {c.justified ? <FieldItem label={t("justified")}>{l("justified", c.justified)}</FieldItem> : null}
            {c.ncr ? <FieldItem label={t("ncr")}><Link href={`/quality/ncrs/${String(c.ncr.id)}`} className="ltr text-primary hover:underline">{String(c.ncr.ncr_no ?? "")}</Link></FieldItem> : null}
            {c.response_en || c.response_ar ? <FieldItem label={t("response")} wide><span dir="auto">{bi(c.response_en, c.response_ar)}</span></FieldItem> : null}
            {c.satisfied ? <FieldItem label={t("satisfied")}>{l("satisfaction", c.satisfied)}</FieldItem> : null}
            {c.status_reason ? <FieldItem label={t("withdrawReason")} wide>{c.status_reason}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      {manage && c.status === "received" ? (
        <Button className="mb-4" disabled={busy} onClick={() => void go("acknowledged")} data-testid="q-cmp-ack">{t("acknowledge")}</Button>
      ) : null}
      {manage && c.status === "acknowledged" ? (
        <Card className="mb-4"><CardContent className="flex flex-col gap-3 p-4">
          <FormField id="cmp-inv" label={t("investigation")}><Textarea value={f.investigation_note} onChange={set("investigation_note")} rows={3} /></FormField>
          <Button className="self-start" disabled={busy} onClick={() => void go("under_investigation", clean({ investigation_note: f.investigation_note }))} data-testid="q-cmp-investigate">{t("investigate")}</Button>
        </CardContent></Card>
      ) : null}
      {manage && c.status === "under_investigation" ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-2" data-testid="q-cmp-respond-form">
          <FormField id="cmp-just" label={t("justified")} required>
            <Select value={f.justified} onChange={set("justified")} data-testid="cmp-justified">
              <option value="">{tc("select")}</option>
              {options("justified").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="cmp-ncr" label={t("ncr")} hint={t("ncrHint")}>
            <Select value={f.ncr_id} onChange={set("ncr_id")} data-testid="cmp-ncr">
              <option value="">—</option>
              {(ncrs.data?.items ?? []).filter((n) => n.ncr_no && n.status !== "voided").map((n) => <option key={n.id} value={n.id}>{n.ncr_no} — {n.title}</option>)}
            </Select>
          </FormField>
          <FormField id="cmp-ren" label={t("responseEn")}><Textarea value={f.response_en} onChange={set("response_en")} rows={3} dir="ltr" data-testid="cmp-response-en" /></FormField>
          <FormField id="cmp-rar" label={t("responseAr")}><Textarea value={f.response_ar} onChange={set("response_ar")} rows={3} dir="rtl" /></FormField>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <Button disabled={busy || !f.justified} onClick={() => void go("responded", clean({ justified: f.justified, ncr_id: f.ncr_id, response_en: f.response_en, response_ar: f.response_ar }))} data-testid="q-cmp-respond">{t("respond")}</Button>
            {caps.write("ncr.raise") && !c.ncr ? (
              <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/complaints/{complaint_id}/ncr", { ...path, body: { source_type: "complaint", open: false } })), t("ncrRaised"))} data-testid="q-cmp-raise-ncr">{t("raiseNcr")}</Button>
            ) : null}
          </div>
        </CardContent></Card>
      ) : null}
      {manage && c.status === "responded" ? (
        <Card className="mb-4"><CardContent className="flex flex-col gap-3 p-4">
          <FormField id="cmp-sat" label={t("satisfied")} required>
            <Select value={f.satisfied} onChange={set("satisfied")} data-testid="cmp-satisfied">
              <option value="">{tc("select")}</option>
              {options("satisfaction").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <Button className="self-start" disabled={busy || !f.satisfied} onClick={() => void go("closed", { satisfied: f.satisfied as S["QSatisfaction"] })} data-testid="q-cmp-close">{t("close")}</Button>
        </CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4"><Attachments ownerType="q_complaint" ownerId={c.id} canUpload={manage && c.status !== "closed"} /></CardContent></Card>
      {c.actions.length ? <div className="mb-4"><CaList actions={c.actions} projectId={project.id} /></div> : null}
      <HistoryPanel entityType="q_complaint" entityId={c.id} projectId={project.id} />
      <ReasonDialog open={withdraw} onOpenChange={setWithdraw} title={t("withdraw")} confirm={t("withdraw")}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/complaints/{complaint_id}/transitions", { ...path, body: { to_status: "withdrawn", reason } })).then(() => q.refetch())} />
    </div>
  );
}
