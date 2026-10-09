"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Replace, TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { CLEARANCE_REASONS, NOTAM_STATUSES, NOTAM_TYPES, OBSTACLE_CONDITIONS, OBSTACLE_DECISIONS, OBSTACLE_EQUIPMENT_TYPES, OBSTACLE_STATUSES, OLS_SURFACES, WORKS_IMPACTS } from "@/lib/access-enums";
import { ak, useNotam, useNotams, useObstacle, useObstacles } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { todayInZone } from "@/lib/datetime";
import { joinList, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { AirportOnly, Code, StepDialog, VehicleSelect } from "./common";

const PAGE_SIZE = 50;
type Ntm = Schemas["NotamRequestRead"];
type Obs = Schemas["ObstacleRead"];

/* ───────────────────────────── UTC helpers (NT-3) ───────────────────────────── */

/** "2026-10-01T20:00" (UTC wall clock in a datetime-local input) → ISO UTC. */
export function utcInputToIso(v: string): string {
  return v ? new Date(`${v}:00Z`).toISOString() : "";
}
export function isoToUtcInput(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 16) : "";
}
/** NOTAM item B/C format YYMMDDHHMM (UTC). */
export function notamFormat(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCFullYear() % 100)}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}`;
}

/** UTC time with NOTAM format and Riyadh local time underneath. */
export function UtcTime({ iso, projectId }: { iso: string | null | undefined; projectId: string }) {
  const { dateTime } = useFormatters(projectId);
  const t = useTranslations("notams");
  if (!iso) return <>—</>;
  return (
    <span className="inline-flex flex-col">
      <bdi className="ltr font-mono text-sm" data-testid="notam-utc">
        {notamFormat(iso)} UTC
      </bdi>
      <span className="text-xs text-muted-foreground">
        {t("local")}: {dateTime(iso)}
      </span>
    </span>
  );
}

/* ───────────────────────────── NOTAM list ───────────────────────────── */

export function NotamListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<NotamList project={p} />}</AirportOnly>}</ProjectGate>;
}

function NotamList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("notams");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["NotamStatus"][];
  const query = useNotams(project.id, {
    status: status.length ? status : null,
    zone_id: s.get("zone_id") || null,
    works_impact: (s.get("works_impact") as Schemas["WorksImpact"] | null) || null,
    in_effect: s.getBool("in_effect") ?? null,
    late_request: s.getBool("late_request") ?? null,
    not_issued_within_hours: s.getInt("not_issued_within_hours", 0) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  const airside = opts.zones.filter((z) => z.zoneType === "airside");
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "notam.edit", project.id) ? (
            <Button asChild>
              <Link href="/notams/new" data-testid="new-notam">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="notam_requests" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="nt-status" label={tc("status")} options={NOTAM_STATUSES.map((x) => ({ value: x, label: te(`notamStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="nt-zone" label={tc("zone")} value={s.get("zone_id") ?? ""} onChange={(v) => s.set({ zone_id: v })} options={airside.map((z) => ({ value: z.value, label: z.label }))} />
        <SelectFilter id="nt-impact" label={t("fields.works_impact")} value={(s.get("works_impact") ?? "") as Schemas["WorksImpact"] | ""} onChange={(v) => s.set({ works_impact: v })} options={WORKS_IMPACTS.map((x) => ({ value: x, label: te(`worksImpact.${x}`) }))} />
        <SelectFilter id="nt-effect" label={t("inEffect")} value={s.get("in_effect") === "true" ? "true" : ""} onChange={(v) => s.set({ in_effect: v })} options={[{ value: "true", label: tc("yes") }]} />
        <SelectFilter id="nt-late" label={t("late")} value={s.get("late_request") === "true" ? "true" : ""} onChange={(v) => s.set({ late_request: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="notams-table">
            <THead>
              <TR>
                <TH>{t("fields.ntm_no")}</TH>
                <TH>{t("fields.zones")}</TH>
                <TH>{t("fields.works_impact")}</TH>
                <TH>{t("fields.notam_number")}</TH>
                <TH>{t("from")}</TH>
                <TH>{t("to")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((n) => (
                <TR key={n.id} data-testid="notam-row">
                  <TD label={t("fields.ntm_no")}>
                    <Link href={`/notams/${n.id}`} className="ltr font-medium text-primary hover:underline">
                      {n.ntm_no}
                    </Link>
                    {n.late_request ? (
                      <span className="ms-1">
                        <StatusBadge status="warn" label={t("late")} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("fields.zones")}>
                    <span className="ltr">{n.zones.map((z) => z.code).join(", ")}</span>
                  </TD>
                  <TD label={t("fields.works_impact")}>{joinList(n.works_impact.map((w) => te(`worksImpact.${w}`)))}</TD>
                  <TD label={t("fields.notam_number")}>{n.notam_number ? <Code>{n.notam_number}</Code> : "—"}</TD>
                  <TD label={t("from")}>
                    <UtcTime iso={n.effective_from_utc ?? n.requested_start_utc} projectId={project.id} />
                  </TD>
                  <TD label={t("to")}>
                    <UtcTime iso={n.effective_to_utc ?? n.requested_end_utc} projectId={project.id} />
                  </TD>
                  <TD label={tc("status")}>
                    <span data-testid="notam-row-status" data-status={n.status}>
                <StatusBadge status={n.status} label={te(`notamStatus.${n.status}`)} />
              </span>
                    {n.in_effect ? (
                      <span className="ms-1">
                        <StatusBadge status="active" label={t("inEffect")} />
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────────────────────── NOTAM form ───────────────────────────── */

export function NotamCreatePage() {
  const t = useTranslations("notams");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/notams" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <ProjectGate>{(p) => <AirportOnly project={p}>{<NotamForm project={p} />}</AirportOnly>}</ProjectGate>
    </div>
  );
}

export function NotamEditPage({ id }: { id: string }) {
  const t = useTranslations("notams");
  const q = useNotam(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/notams" }, { label: q.data.ntm_no, href: `/notams/${id}` }, { label: t("edit") }]} />
      <PageHeader title={t("edit")} />
      <ProjectById id={q.data.project_id}>{(p) => <NotamForm project={p} ntm={q.data} />}</ProjectById>
    </div>
  );
}

function NotamForm({ project, ntm }: { project: Schemas["ProjectRead"]; ntm?: Ntm }) {
  const t = useTranslations("notams");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const airside = opts.zones.filter((z) => z.zoneType === "airside");
  const [zones, setZones] = useState<string[]>(ntm?.zones.map((z) => z.id) ?? []);
  const [eng, setEng] = useState(ntm?.engagement?.id ?? "");
  const [impact, setImpact] = useState<Schemas["WorksImpact"][]>(ntm?.works_impact ?? []);
  const [descEn, setDescEn] = useState(ntm?.description_en ?? "");
  const [descAr, setDescAr] = useState(ntm?.description_ar ?? "");
  const [start, setStart] = useState(isoToUtcInput(ntm?.requested_start_utc));
  const [end, setEnd] = useState(isoToUtcInput(ntm?.requested_end_utc));
  const [schedule, setSchedule] = useState(ntm?.schedule_text ?? "");
  const [formError, setFormError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setFormError(null);
    if (!zones.length || !impact.length || !descEn.trim() || !descAr.trim() || !start || !end) {
      setFormError(tv("required"));
      return;
    }
    if (end <= start) {
      setFormError(t("endAfterStart"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = { zone_ids: zones, works_impact: impact, description_en: descEn.trim(), description_ar: descAr.trim(), requested_start_utc: utcInputToIso(start), requested_end_utc: utcInputToIso(end), schedule_text: schedule.trim() || null };
    try {
      const n = ntm
        ? await unwrap(api.PATCH("/api/v1/notam-requests/{ntm_id}", { params: { path: { ntm_id: ntm.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/notam-requests", { params: { path: { project_id: project.id } }, body: { ...body, engagement_id: eng || null } }));
      qc.setQueryData(ak.notam(n.id), n);
      await qc.invalidateQueries({ queryKey: ["notams"] });
      warn(n.warnings);
      toast.success(tc("saved"));
      router.push(`/notams/${n.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      data-testid="notam-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("works")}>
        <MultiSelect id="nf-zones" label={t("fields.zones")} options={airside.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} className="lg:w-full" />
        {!ntm ? (
          <FormField id="nf-eng" label={tc("contractor")}>
            <Select value={eng} onChange={(e) => setEng(e.target.value)}>
              <option value="">{tc("none")}</option>
              {opts.engagements.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <MultiSelect id="nf-impact" label={t("fields.works_impact")} options={WORKS_IMPACTS.map((x) => ({ value: x, label: te(`worksImpact.${x}`) }))} value={impact} onChange={(v) => setImpact(v as Schemas["WorksImpact"][])} className="lg:w-full" />
        <FormField id="nf-desc-en" label={t("fields.description_en")} required className="sm:col-span-2">
          <Textarea dir="ltr" rows={3} maxLength={1000} value={descEn} onChange={(e) => setDescEn(e.target.value)} />
        </FormField>
        <FormField id="nf-desc-ar" label={t("fields.description_ar")} required className="sm:col-span-2">
          <Textarea dir="rtl" lang="ar" rows={3} maxLength={1000} value={descAr} onChange={(e) => setDescAr(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("timesUtc")} description={t("timesUtcHint")}>
        <FormField id="nf-start" label={t("fields.requested_start_utc")} required hint={start ? `${notamFormat(utcInputToIso(start))} UTC` : undefined}>
          <Input type="datetime-local" className="ltr" value={start} onChange={(e) => setStart(e.target.value)} />
        </FormField>
        <FormField id="nf-end" label={t("fields.requested_end_utc")} required hint={end ? `${notamFormat(utcInputToIso(end))} UTC` : undefined}>
          <Input type="datetime-local" className="ltr" value={end} onChange={(e) => setEnd(e.target.value)} />
        </FormField>
        <FormField id="nf-schedule" label={t("fields.schedule_text")} hint={t("scheduleHint")} className="sm:col-span-2">
          <Input className="ltr uppercase" maxLength={200} value={schedule} onChange={(e) => setSchedule(e.target.value)} />
        </FormField>
      </FormSection>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-notam">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── NOTAM detail ───────────────────────────── */

type NtmStep = "submit" | "forward" | "issue" | "reject" | "cancel" | "replace";

export function NotamDetail({ id }: { id: string }) {
  const t = useTranslations("notams");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const q = useNotam(id);
  const qc = useQueryClient();
  const router = useRouter();
  const [step, setStep] = useState<NtmStep | null>(null);
  const [late, setLate] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const n = q.data;
  const pid = n.project_id;
  const edit = canWrite(me, "notam.edit", pid);
  const proc = canWrite(me, "notam.process", pid);
  const s = n.status;
  const steps: { k: NtmStep; show: boolean; destructive?: boolean }[] = [
    { k: "submit", show: s === "draft" && edit },
    { k: "forward", show: s === "submitted_to_ops" && proc },
    { k: "issue", show: s === "requested_from_ais" && proc },
    { k: "reject", show: (s === "submitted_to_ops" || s === "requested_from_ais") && proc, destructive: true },
    { k: "replace", show: s === "issued" && proc },
    { k: "cancel", show: s === "issued" && proc, destructive: true },
  ];
  async function transition(body: Schemas["NotamTransitionRequest"]) {
    const u = await unwrap(api.POST("/api/v1/notam-requests/{ntm_id}/transitions", { params: { path: { ntm_id: n.id } }, body }));
    qc.setQueryData(ak.notam(n.id), u);
    for (const k of ["notams", "waps", "wap", "wap-board"]) await qc.invalidateQueries({ queryKey: [k] });
    toast.success(te(`notamStatus.${body.to_status}`));
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/notams" }, { label: n.ntm_no }]} />
        <PageHeader
          title={n.ntm_no}
          description={joinList(n.works_impact.map((w) => te(`worksImpact.${w}`)))}
          actions={
            <>
              <span data-testid="notam-status" data-status={n.status}>
                <StatusBadge status={n.status} label={te(`notamStatus.${n.status}`)} />
              </span>
              {n.in_effect ? <StatusBadge status="active" label={t("inEffect")} /> : null}
              {s === "draft" && edit ? (
                <Button variant="outline" asChild>
                  <Link href={`/notams/${n.id}/edit`}>
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {steps.some((x) => x.show) ? (
        <div className="flex flex-wrap gap-2">
          {steps
            .filter((x) => x.show)
            .map((x) => (
              <Button
                key={x.k}
                variant={x.destructive ? "destructive" : "outline"}
                onClick={() => {
                  if (x.k === "submit") {
                    const leadMs = n.required_lead_days * 86400000;
                    setLate(new Date(n.requested_start_utc).getTime() - new Date().getTime() < leadMs);
                  }
                  setStep(x.k);
                }}
                data-testid={`ntm-${x.k}`}
              >
                {x.k === "replace" ? <Replace aria-hidden /> : null}
                {t(`step.${x.k}`)}
              </Button>
            ))}
        </div>
      ) : null}
      {n.late_request ? (
        <Alert tone="warning" data-testid="late-request">
          {t("lateHint", { days: n.required_lead_days })} {n.late_justification ? `— ${n.late_justification}` : ""}
        </Alert>
      ) : null}
      <ApiWarnings warnings={n.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("fields.zones")}>
              {n.zones.map((z) => (
                <span key={z.id} className="me-2">
                  <Code>{z.code}</Code> {name(z.name_en, z.name_ar)}
                </span>
              ))}
            </FieldItem>
            <FieldItem label={tc("contractor")}>{n.engagement?.short_code ?? "—"}</FieldItem>
            <FieldItem label={t("fields.description_en")} wide>
              <span dir="ltr">{n.description_en}</span>
            </FieldItem>
            <FieldItem label={t("fields.description_ar")} wide>
              <span dir="rtl">{n.description_ar}</span>
            </FieldItem>
            <FieldItem label={t("fields.requested_start_utc")}>
              <UtcTime iso={n.requested_start_utc} projectId={pid} />
            </FieldItem>
            <FieldItem label={t("fields.requested_end_utc")}>
              <UtcTime iso={n.requested_end_utc} projectId={pid} />
            </FieldItem>
            <FieldItem label={t("fields.schedule_text")} ltr>
              {n.schedule_text ?? "—"}
            </FieldItem>
            <FieldItem label={t("fields.required_lead_days")}>{n.required_lead_days}</FieldItem>
            <FieldItem label={t("fields.submitted_to_ops_at")}>
              <UtcTime iso={n.submitted_to_ops_at} projectId={pid} />
            </FieldItem>
            <FieldItem label={t("fields.notam_number")}>{n.notam_number ? <Code>{n.notam_number}</Code> : "—"}</FieldItem>
            <FieldItem label={t("fields.notam_type")}>{n.notam_type ? te(`notamType.${n.notam_type}`) : "—"}</FieldItem>
            <FieldItem label={t("fields.effective_from_utc")}>
              <UtcTime iso={n.effective_from_utc} projectId={pid} />
            </FieldItem>
            <FieldItem label={t("fields.effective_to_utc")}>
              <UtcTime iso={n.effective_to_utc} projectId={pid} />
            </FieldItem>
            <FieldItem label={t("fields.item_e_text")} wide>
              <pre className="ltr font-mono text-sm whitespace-pre-wrap">{n.item_e_text ?? "—"}</pre>
            </FieldItem>
            {n.replaces_ntm_id ? (
              <FieldItem label={t("replaces")}>
                <Link href={`/notams/${n.replaces_ntm_id}`} className="text-primary hover:underline">
                  {t("openRecord")}
                </Link>
              </FieldItem>
            ) : null}
            {n.replaced_by_ntm_id ? (
              <FieldItem label={t("replacedBy")}>
                <Link href={`/notams/${n.replaced_by_ntm_id}`} className="text-primary hover:underline">
                  {t("openRecord")}
                </Link>
              </FieldItem>
            ) : null}
            <FieldItem label={t("linkedWaps")}>
              {n.linked_wap_ids.length
                ? n.linked_wap_ids.map((w, i) => (
                    <Link key={w} href={`/waps/${w}`} className="me-2 text-primary hover:underline">
                      {t("wapN", { n: i + 1 })}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("fields.requested_by")}>{name(n.requested_by.full_name_en, n.requested_by.full_name_ar)}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="notam_request" entityId={n.id} />
      {step === "submit" ? <SubmitNotamDialog late={late} days={n.required_lead_days} onConfirm={(j) => transition({ to_status: "submitted_to_ops", late_justification: j })} onClose={() => setStep(null)} /> : null}
      {step === "forward" ? <StepDialog title={t("step.forward")} description={t("help.forward")} confirmLabel={t("step.forward")} onConfirm={() => transition({ to_status: "requested_from_ais" })} onClose={() => setStep(null)} /> : null}
      {step === "issue" ? <IssueNotamDialog ntm={n} mode="issue" onDone={(body) => transition({ to_status: "issued", ...body })} onClose={() => setStep(null)} /> : null}
      {step === "replace" ? (
        <IssueNotamDialog
          ntm={n}
          mode="replace"
          onDone={async (body) => {
            const r = await unwrap(
              api.POST("/api/v1/notam-requests/{ntm_id}/replace", {
                params: { path: { ntm_id: n.id } },
                body: { notam_number: body.notam_number ?? "", effective_from_utc: body.effective_from_utc ?? "", effective_to_utc: body.effective_to_utc ?? "", item_e_text: body.item_e_text ?? null },
              }),
            );
            for (const k of ["notams", "notam", "waps", "wap"]) await qc.invalidateQueries({ queryKey: [k] });
            toast.success(t("replacedDone", { no: r.ntm_no }));
            router.push(`/notams/${r.id}`);
          }}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "reject" || step === "cancel" ? (
        <ReasonDialog
          title={t(`step.${step}`)}
          help={t(`help.${step}`)}
          onConfirm={(r) => transition({ to_status: step === "reject" ? "rejected" : "cancelled", reason: r })}
          onClose={() => setStep(null)}
        />
      ) : null}
    </div>
  );
}

function ReasonDialog({ title, help, onConfirm, onClose }: { title: string; help?: string; onConfirm: (r: string) => Promise<unknown>; onClose: () => void }) {
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  return (
    <StepDialog title={title} description={help} destructive confirmLabel={title} disabled={reason.trim().length < 3} onConfirm={() => onConfirm(reason.trim())} onClose={onClose}>
      <FormField id="rd-reason" label={tc("reason")} required>
        <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function SubmitNotamDialog({ late, days, onConfirm, onClose }: { late: boolean; days: number; onConfirm: (j: string | null) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("notams");
  const [just, setJust] = useState("");
  return (
    <StepDialog
      title={t("step.submit")}
      description={t("help.submit")}
      warning={late ? t("lateWarning", { days }) : undefined}
      confirmLabel={t("step.submit")}
      disabled={late && just.trim().length < 10}
      onConfirm={() => onConfirm(late ? just.trim() : null)}
      onClose={onClose}
    >
      {late ? (
        <FormField id="ntm-late" label={t("fields.late_justification")} required>
          <Textarea rows={3} value={just} onChange={(e) => setJust(e.target.value)} />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

function IssueNotamDialog({
  ntm,
  mode,
  onDone,
  onClose,
}: {
  ntm: Ntm;
  mode: "issue" | "replace";
  onDone: (b: { notam_number: string; notam_type?: Schemas["NotamType"]; effective_from_utc: string; effective_to_utc: string; item_e_text: string | null }) => Promise<unknown>;
  onClose: () => void;
}) {
  const t = useTranslations("notams");
  const te = useTranslations("enums");
  const [num, setNum] = useState("");
  const [type, setType] = useState<Schemas["NotamType"]>(mode === "replace" ? "R" : "N");
  const [from, setFrom] = useState(isoToUtcInput(ntm.effective_from_utc ?? ntm.requested_start_utc));
  const [to, setTo] = useState(isoToUtcInput(ntm.effective_to_utc ?? ntm.requested_end_utc));
  const [e, setE] = useState(ntm.item_e_text ?? "");
  const valid = /^[A-Z]\d{4}\/\d{2}$/.test(num.trim().toUpperCase()) && from && to && to > from;
  return (
    <StepDialog
      title={t(`step.${mode}`)}
      description={t(`help.${mode}`)}
      confirmLabel={t(`step.${mode}`)}
      testId="issue-notam-confirm"
      disabled={!valid}
      wide
      onConfirm={() => onDone({ notam_number: num.trim().toUpperCase(), notam_type: mode === "issue" ? type : undefined, effective_from_utc: utcInputToIso(from), effective_to_utc: utcInputToIso(to), item_e_text: e.trim() || null })}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="in-num" label={t("fields.notam_number")} required hint={t("numberHint")}>
          <Input className="ltr uppercase" maxLength={12} value={num} onChange={(ev) => setNum(ev.target.value)} placeholder="A0999/26" />
        </FormField>
        {mode === "issue" ? (
          <FormField id="in-type" label={t("fields.notam_type")} required>
            <Select value={type} onChange={(ev) => setType(ev.target.value as Schemas["NotamType"])}>
              {NOTAM_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`notamType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="in-from" label={t("fields.effective_from_utc")} required hint={from ? `${notamFormat(utcInputToIso(from))} UTC` : undefined}>
          <Input type="datetime-local" className="ltr" value={from} onChange={(ev) => setFrom(ev.target.value)} />
        </FormField>
        <FormField id="in-to" label={t("fields.effective_to_utc")} required hint={to ? `${notamFormat(utcInputToIso(to))} UTC` : undefined}>
          <Input type="datetime-local" className="ltr" value={to} onChange={(ev) => setTo(ev.target.value)} />
        </FormField>
        <FormField id="in-e" label={t("fields.item_e_text")} className="sm:col-span-2">
          <Textarea dir="ltr" className="font-mono uppercase" rows={3} maxLength={2000} value={e} onChange={(ev) => setE(ev.target.value)} />
        </FormField>
      </div>
    </StepDialog>
  );
}

/* ───────────────────────────── Obstacle clearances ───────────────────────────── */

export function ObstacleListPage() {
  return <ProjectGate>{(p) => <ObstacleList project={p} />}</ProjectGate>;
}

function Ft({ m, ft }: { m: string | null | undefined; ft?: string | null }) {
  const t = useTranslations("obstacles");
  if (m === null || m === undefined) return <>—</>;
  const f = ft ?? (Number(m) / 0.3048).toFixed(2);
  return <bdi className="ltr tabular-nums">{t("mFt", { m, ft: f })}</bdi>;
}

function ObstacleList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("obstacles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["ObstacleStatus"][];
  const query = useObstacles(project.id, {
    status: status.length ? status : null,
    zone_id: s.get("zone_id") || null,
    reason: (s.get("reason") as Schemas["ClearanceReason"] | null) || null,
    active_on: s.get("active_on") || null,
    expiring_within_days: s.getInt("expiring_within_days", 0) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "obstacle.edit", project.id) ? (
            <Button asChild>
              <Link href="/obstacle-clearances/new" data-testid="new-obstacle">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="obstacle_clearances" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="ob-status" label={tc("status")} options={OBSTACLE_STATUSES.map((x) => ({ value: x, label: te(`obstacleStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="ob-zone" label={tc("zone")} value={s.get("zone_id") ?? ""} onChange={(v) => s.set({ zone_id: v })} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} />
        <SelectFilter id="ob-reason" label={t("reason")} value={(s.get("reason") ?? "") as Schemas["ClearanceReason"] | ""} onChange={(v) => s.set({ reason: v })} options={CLEARANCE_REASONS.map((x) => ({ value: x, label: te(`clearanceReason.${x}`) }))} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="obstacles-table">
            <THead>
              <TR>
                <TH>{t("fields.obs_no")}</TH>
                <TH>{t("fields.equipment")}</TH>
                <TH>{tc("zone")}</TH>
                <TH>{t("fields.max_height_m_agl")}</TH>
                <TH>{t("penetration")}</TH>
                <TH>{t("validity")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((o) => (
                <TR key={o.id} data-testid="obstacle-row">
                  <TD label={t("fields.obs_no")}>
                    <Link href={`/obstacle-clearances/${o.id}`} className="ltr font-medium text-primary hover:underline">
                      {o.obs_no}
                    </Link>
                  </TD>
                  <TD label={t("fields.equipment")}>
                    {te(`obstacleEquipment.${o.equipment_type}`)}
                    <span className="block text-xs text-muted-foreground">{o.vehicle ? o.vehicle.vehicle_no : o.equipment_desc}</span>
                  </TD>
                  <TD label={tc("zone")}>{o.zone ? <Code>{o.zone.code}</Code> : "—"}</TD>
                  <TD label={t("fields.max_height_m_agl")}>
                    <Ft m={o.heights.max_height_m_agl} ft={o.heights.max_height_ft_agl} />
                  </TD>
                  <TD label={t("penetration")}>{Number(o.heights.penetration_m) > 0 ? <StatusBadge status="danger" label={`${o.heights.penetration_m} m`} /> : "0"}</TD>
                  <TD label={t("validity")}>{o.valid_from ? `${date(o.valid_from)} – ${date(o.valid_to)}` : `${date(o.requested_from)} – ${date(o.requested_to)}`}</TD>
                  <TD label={tc("status")}>
                    <span data-testid="obstacle-row-status" data-status={o.status}>
                      <StatusBadge status={o.status} label={te(`obstacleStatus.${o.status}`)} />
                    </span>
                    {o.system_suspended ? <span className="flex items-center gap-1 text-xs text-warning font-medium"><TriangleAlert aria-hidden className="size-3.5 shrink-0" />{t("systemSuspended")}</span> : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

export function ObstacleCreatePage() {
  const t = useTranslations("obstacles");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/obstacle-clearances" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <ProjectGate>{(p) => <ObstacleForm project={p} />}</ProjectGate>
    </div>
  );
}

export function ObstacleEditPage({ id }: { id: string }) {
  const t = useTranslations("obstacles");
  const q = useObstacle(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/obstacle-clearances" }, { label: q.data.obs_no, href: `/obstacle-clearances/${id}` }, { label: t("edit") }]} />
      <PageHeader title={t("edit")} />
      <ProjectById id={q.data.project_id}>{(p) => <ObstacleForm project={p} obs={q.data} />}</ProjectById>
    </div>
  );
}

function HeightPanel({ h }: { h: Schemas["HeightFigures"] }) {
  const t = useTranslations("obstacles");
  const te = useTranslations("enums");
  const pen = Number(h.penetration_m) > 0;
  return (
    <div className="flex flex-col gap-3" data-testid="height-preview" data-required={h.clearance_required}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">{t("fields.max_height_m_agl")}</dt>
          <dd className="font-medium">
            <Ft m={h.max_height_m_agl} ft={h.max_height_ft_agl} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("top")}</dt>
          <dd className="font-medium" data-testid="top-amsl">
            <Ft m={h.top_elevation_m_amsl} ft={h.top_elevation_ft_amsl} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("olsLimit")}</dt>
          <dd className="font-medium">
            <Ft m={h.ols_limit_m_amsl} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("margin")}</dt>
          <dd className={pen ? "font-semibold text-destructive" : "font-medium"}>
            <Ft m={h.margin_m} ft={h.margin_ft} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("penetration")}</dt>
          <dd className={pen ? "font-semibold text-destructive" : "font-medium"} data-testid="penetration">
            <Ft m={h.penetration_m} ft={h.penetration_ft} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("zoneMax")}</dt>
          <dd className="font-medium">
            <Ft m={h.zone_max_equipment_height_m_agl} />
          </dd>
        </div>
      </dl>
      <Alert tone={h.clearance_required ? (pen ? "danger" : "warning") : "success"} data-testid="clearance-reasons" data-reasons={h.clearance_reasons.join(" ")}>
        {h.clearance_required ? t("required", { reasons: joinList(h.clearance_reasons.map((r) => te(`clearanceReason.${r}`))) }) : t("notRequired")}
      </Alert>
    </div>
  );
}

function ObstacleForm({ project, obs }: { project: Schemas["ProjectRead"]; obs?: Obs }) {
  const t = useTranslations("obstacles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const [f, setF] = useState({
    zone_id: obs?.zone?.id ?? "",
    engagement_id: obs?.engagement?.id ?? "",
    vehicle_id: obs?.vehicle?.id ?? "",
    equipment_desc: obs?.equipment_desc ?? "",
    equipment_type: (obs?.equipment_type ?? "mobile_crane") as Schemas["ObstacleEquipmentType"],
    location_lat: obs?.location_lat ?? "",
    location_lng: obs?.location_lng ?? "",
    location_desc: obs?.location_desc ?? "",
    ground_elevation_m_amsl: obs?.ground_elevation_m_amsl ?? "",
    max_height_m_agl: obs?.heights.max_height_m_agl ?? "",
    ols_surface: (obs?.ols_surface ?? "") as Schemas["OlsSurface"] | "",
    ols_limit_m_amsl: obs?.heights.ols_limit_m_amsl ?? "",
    ols_source_ref: obs?.ols_source_ref ?? "",
    requested_from: obs?.requested_from ?? todayInZone(),
    requested_to: obs?.requested_to ?? "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const body = {
    zone_id: f.zone_id || null,
    engagement_id: f.engagement_id || null,
    vehicle_id: f.vehicle_id || null,
    equipment_desc: f.equipment_desc.trim() || null,
    equipment_type: f.equipment_type,
    location_lat: f.location_lat,
    location_lng: f.location_lng,
    location_desc: f.location_desc.trim(),
    ground_elevation_m_amsl: f.ground_elevation_m_amsl,
    max_height_m_agl: f.max_height_m_agl,
    ols_surface: f.ols_surface || null,
    ols_limit_m_amsl: f.ols_limit_m_amsl || null,
    ols_source_ref: f.ols_source_ref.trim() || null,
    requested_from: f.requested_from,
    requested_to: f.requested_to || f.requested_from,
  };
  const ready = Boolean(f.location_lat && f.location_lng && f.ground_elevation_m_amsl && f.max_height_m_agl && f.location_desc.trim() && f.requested_from && (f.vehicle_id || f.equipment_desc.trim()) && (!project.is_airport || (f.zone_id && f.ols_surface)));
  const debounced = useDebounced(JSON.stringify(body), 400);
  const preview = useQuery({
    queryKey: ["obstacle-preview", project.id, debounced],
    queryFn: () => unwrap(api.POST("/api/v1/obstacle-clearances/preview", { body: { ...(JSON.parse(debounced) as typeof body), project_id: project.id } })),
    enabled: ready,
    gcTime: 0,
    retry: false,
  });
  async function save() {
    setFormError(null);
    if (!ready || !f.requested_to) {
      setFormError(tv("required"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const o = obs
        ? await unwrap(api.PATCH("/api/v1/obstacle-clearances/{obs_id}", { params: { path: { obs_id: obs.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/obstacle-clearances", { params: { path: { project_id: project.id } }, body }));
      qc.setQueryData(ak.obstacle(o.id), o);
      await qc.invalidateQueries({ queryKey: ["obstacles"] });
      warn(o.warnings);
      toast.success(tc("saved"));
      router.push(`/obstacle-clearances/${o.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const zonesForProject = project.is_airport ? opts.zones.filter((z) => z.zoneType === "airside") : opts.zones;
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      data-testid="obstacle-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("equipment")}>
        <FormField id="of-type" label={t("fields.equipment_type")} required>
          <Select value={f.equipment_type} onChange={set("equipment_type")}>
            {OBSTACLE_EQUIPMENT_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`obstacleEquipment.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="of-eng" label={tc("contractor")}>
          <Select value={f.engagement_id} onChange={set("engagement_id")}>
            <option value="">{tc("none")}</option>
            {opts.engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="of-vehicle" label={t("fields.vehicle")} hint={t("vehicleOrDesc")}>
          <VehicleSelect id="of-vehicle-sel" projectId={project.id} value={f.vehicle_id} onChange={(v) => setF((x) => ({ ...x, vehicle_id: v }))} placeholder={tc("none")} engagementId={f.engagement_id || null} />
        </FormField>
        <FormField id="of-desc" label={t("fields.equipment_desc")}>
          <Input maxLength={150} value={f.equipment_desc} onChange={set("equipment_desc")} />
        </FormField>
      </FormSection>
      <FormSection title={t("location")}>
        <FormField id="of-zone" label={tc("zone")} required={project.is_airport}>
          <Select value={f.zone_id} onChange={set("zone_id")}>
            <option value="">{tc("none")}</option>
            {zonesForProject.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="of-loc" label={t("fields.location_desc")} required>
          <Input maxLength={150} value={f.location_desc} onChange={set("location_desc")} />
        </FormField>
        <FormField id="of-lat" label={t("fields.location_lat")} required>
          <Input type="number" step="0.000001" className="ltr" value={f.location_lat} onChange={set("location_lat")} />
        </FormField>
        <FormField id="of-lng" label={t("fields.location_lng")} required>
          <Input type="number" step="0.000001" className="ltr" value={f.location_lng} onChange={set("location_lng")} />
        </FormField>
      </FormSection>
      <FormSection title={t("heights")} description={t("heightsHint")}>
        <FormField id="of-ground" label={t("fields.ground_elevation_m_amsl")} required>
          <Input type="number" step="0.01" className="ltr" value={f.ground_elevation_m_amsl} onChange={set("ground_elevation_m_amsl")} />
        </FormField>
        <FormField id="of-height" label={t("fields.max_height_m_agl")} required hint={f.max_height_m_agl ? `${(Number(f.max_height_m_agl) / 0.3048).toFixed(2)} ft` : undefined}>
          <Input type="number" step="0.01" className="ltr" value={f.max_height_m_agl} onChange={set("max_height_m_agl")} />
        </FormField>
        {project.is_airport ? (
          <>
            <FormField id="of-ols" label={t("fields.ols_surface")} required>
              <Select value={f.ols_surface} onChange={set("ols_surface")}>
                <option value="">{tc("select")}</option>
                {OLS_SURFACES.map((x) => (
                  <option key={x} value={x}>
                    {te(`olsSurface.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="of-ols-limit" label={t("fields.ols_limit_m_amsl")} hint={t("olsLimitHint")}>
              <Input type="number" step="0.01" className="ltr" value={f.ols_limit_m_amsl} onChange={set("ols_limit_m_amsl")} />
            </FormField>
            <FormField id="of-ols-ref" label={t("fields.ols_source_ref")}>
              <Input maxLength={40} className="ltr" value={f.ols_source_ref} onChange={set("ols_source_ref")} />
            </FormField>
          </>
        ) : null}
      </FormSection>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("preview")}</CardTitle>
        </CardHeader>
        <CardContent>
          {!ready ? <p className="text-sm text-muted-foreground">{t("previewHint")}</p> : preview.isError ? <MutationError error={preview.error} /> : preview.data ? <HeightPanel h={preview.data} /> : <LoadingState rows={2} />}
        </CardContent>
      </Card>
      <FormSection title={t("period")}>
        <FormField id="of-from" label={t("fields.requested_from")} required>
          <Input type="date" value={f.requested_from} onChange={set("requested_from")} />
        </FormField>
        <FormField id="of-to" label={t("fields.requested_to")} required>
          <Input type="date" min={f.requested_from} value={f.requested_to} onChange={set("requested_to")} />
        </FormField>
      </FormSection>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-obstacle">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

type ObsStep = "submit" | "decide" | "suspend" | "restore" | "withdraw";

export function ObstacleDetail({ id }: { id: string }) {
  const t = useTranslations("obstacles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const q = useObstacle(id);
  const qc = useQueryClient();
  const [step, setStep] = useState<ObsStep | null>(null);
  const [late, setLate] = useState(false);
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  const edit = canWrite(me, "obstacle.edit", o.project_id);
  const decide = canWrite(me, "obstacle.decide", o.project_id);
  const approved = o.status === "approved" || o.status === "approved_with_conditions";
  const steps: { k: ObsStep; show: boolean; destructive?: boolean }[] = [
    { k: "submit", show: o.status === "draft" && edit },
    { k: "decide", show: o.status === "submitted" && decide },
    { k: "suspend", show: approved && decide, destructive: true },
    { k: "restore", show: o.status === "suspended" && !o.system_suspended && decide },
    { k: "withdraw", show: (approved || o.status === "suspended") && (edit || decide), destructive: true },
  ];
  async function transition(body: Schemas["ObstacleTransitionRequest"]) {
    const u = await unwrap(api.POST("/api/v1/obstacle-clearances/{obs_id}/transitions", { params: { path: { obs_id: o.id } }, body }));
    qc.setQueryData(ak.obstacle(o.id), u);
    for (const k of ["obstacles", "waps", "wap", "wap-board"]) await qc.invalidateQueries({ queryKey: [k] });
    toast.success(te(`obstacleStatus.${body.to_status}`));
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/obstacle-clearances" }, { label: o.obs_no }]} />
        <PageHeader
          title={o.obs_no}
          description={`${te(`obstacleEquipment.${o.equipment_type}`)} · ${o.location_desc}`}
          actions={
            <>
              <span data-testid="obstacle-status" data-status={o.status}>
                <StatusBadge status={o.status} label={te(`obstacleStatus.${o.status}`)} />
              </span>
              {o.status === "draft" && edit ? (
                <Button variant="outline" asChild>
                  <Link href={`/obstacle-clearances/${o.id}/edit`}>
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {steps.some((x) => x.show) ? (
        <div className="flex flex-wrap gap-2">
          {steps
            .filter((x) => x.show)
            .map((x) => (
              <Button
                key={x.k}
                variant={x.destructive ? "destructive" : "outline"}
                onClick={() => {
                  if (x.k === "submit") setLate(false);
                  setStep(x.k);
                }}
                data-testid={`obs-${x.k}`}
              >
                {t(`step.${x.k}`)}
              </Button>
            ))}
        </div>
      ) : null}
      {o.system_suspended ? <Alert tone="warning">{t("systemSuspendedHint")}</Alert> : null}
      {o.late_request ? <Alert tone="warning">{t("lateHint")}</Alert> : null}
      <ApiWarnings warnings={o.warnings} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("heights")}</CardTitle>
        </CardHeader>
        <CardContent>
          <HeightPanel h={o.heights} />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={tc("zone")}>{o.zone ? `${o.zone.code} — ${name(o.zone.name_en, o.zone.name_ar)}` : "—"}</FieldItem>
            <FieldItem label={tc("contractor")}>{o.engagement?.short_code ?? "—"}</FieldItem>
            <FieldItem label={t("fields.vehicle")}>
              {o.vehicle ? (
                <Link href={`/vehicles/${o.vehicle.id}`} className="text-primary hover:underline">
                  {o.vehicle.vehicle_no}
                </Link>
              ) : (
                (o.equipment_desc ?? "—")
              )}
            </FieldItem>
            <FieldItem label={t("coords")} ltr>
              {o.location_lat}, {o.location_lng}
            </FieldItem>
            <FieldItem label={t("fields.ground_elevation_m_amsl")}>
              <Ft m={o.ground_elevation_m_amsl} />
            </FieldItem>
            <FieldItem label={t("fields.ols_surface")}>{o.ols_surface ? te(`olsSurface.${o.ols_surface}`) : "—"}</FieldItem>
            <FieldItem label={t("fields.ols_source_ref")} ltr>
              {o.ols_source_ref ?? "—"}
            </FieldItem>
            <FieldItem label={t("requestedPeriod")}>
              {date(o.requested_from)} – {date(o.requested_to)}
            </FieldItem>
            <FieldItem label={t("fields.authority_ref")} ltr>
              {o.authority_ref ?? "—"}
            </FieldItem>
            <FieldItem label={t("fields.decision")}>{o.decision ? te(`obstacleDecision.${o.decision}`) : "—"}</FieldItem>
            <FieldItem label={t("fields.approved_max_height_m_agl")}>
              <Ft m={o.approved_max_height_m_agl} ft={o.approved_max_height_ft_agl} />
            </FieldItem>
            <FieldItem label={t("fields.approved_top_m_amsl")}>
              <Ft m={o.approved_top_m_amsl} />
            </FieldItem>
            <FieldItem label={t("validity")}>{o.valid_from ? `${date(o.valid_from)} – ${date(o.valid_to)}` : "—"}</FieldItem>
            <FieldItem label={t("fields.conditions")} wide>
              {o.conditions.length ? joinList(o.conditions.map((c) => te(`obstacleCondition.${c}`))) : "—"}
              {o.conditions_text ? <span className="block text-sm">{o.conditions_text}</span> : null}
            </FieldItem>
            <FieldItem label={t("linkedNotams")}>
              {o.linked_ntm_ids.length
                ? o.linked_ntm_ids.map((n, i) => (
                    <Link key={n} href={`/notams/${n}`} className="me-2 text-primary hover:underline">
                      NOTAM {i + 1}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("fields.requested_by")}>{name(o.requested_by.full_name_en, o.requested_by.full_name_ar)}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="obstacle_clearance" entityId={o.id} />
      {step === "submit" ? (
        <SubmitObstacleDialog
          late={late}
          onLate={setLate}
          onConfirm={(j) => transition({ to_status: "submitted", late_justification: j })}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "decide" ? <DecisionDialog obs={o} onClose={() => setStep(null)} /> : null}
      {step === "suspend" ? <ReasonDialog title={t("step.suspend")} onConfirm={(r) => transition({ to_status: "suspended", reason: r })} onClose={() => setStep(null)} /> : null}
      {step === "withdraw" ? <ReasonDialog title={t("step.withdraw")} onConfirm={(r) => transition({ to_status: "withdrawn", reason: r })} onClose={() => setStep(null)} /> : null}
      {step === "restore" ? (
        <StepDialog title={t("step.restore")} confirmLabel={t("step.restore")} onConfirm={() => transition({ to_status: o.decision === "approved_with_conditions" ? "approved_with_conditions" : "approved" })} onClose={() => setStep(null)} />
      ) : null}
    </div>
  );
}

function SubmitObstacleDialog({ late, onLate, onConfirm, onClose }: { late: boolean; onLate: (v: boolean) => void; onConfirm: (j: string | null) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("obstacles");
  const [just, setJust] = useState("");
  return (
    <StepDialog title={t("step.submit")} description={t("help.submit")} confirmLabel={t("step.submit")} disabled={late && just.trim().length < 10} onConfirm={() => onConfirm(just.trim() || null)} onClose={onClose}>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={late} onChange={(e) => onLate(e.target.checked)} className="size-4" />
        {t("isLate")}
      </label>
      {late ? (
        <FormField id="ob-late" label={t("fields.late_justification")} required>
          <Textarea rows={3} value={just} onChange={(e) => setJust(e.target.value)} />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

function DecisionDialog({ obs, onClose }: { obs: Obs; onClose: () => void }) {
  const t = useTranslations("obstacles");
  const te = useTranslations("enums");
  const qc = useQueryClient();
  const notams = useNotams(obs.project_id, { status: ["issued", "requested_from_ais", "submitted_to_ops"], page_size: 100 }, { enabled: true });
  const [decision, setDecision] = useState<Schemas["ObstacleDecision"]>("approved");
  const [ref, setRef] = useState("");
  const [height, setHeight] = useState(obs.heights.max_height_m_agl);
  const [top, setTop] = useState(obs.heights.top_elevation_m_amsl);
  const [conds, setConds] = useState<Schemas["ObstacleCondition"][]>([]);
  const [condText, setCondText] = useState("");
  const [from, setFrom] = useState(obs.requested_from);
  const [to, setTo] = useState(obs.requested_to);
  const [ntms, setNtms] = useState<string[]>([]);
  const pen = obs.heights.clearance_reasons.includes("ols_penetration");
  const approving = decision !== "rejected";
  return (
    <StepDialog
      title={t("step.decide")}
      description={t("help.decide")}
      warning={pen && approving ? t("penetrationRule") : undefined}
      confirmLabel={t("step.decide")}
      testId="decision-confirm"
      wide
      onConfirm={async () => {
        const u = await unwrap(
          api.POST("/api/v1/obstacle-clearances/{obs_id}/decision", {
            params: { path: { obs_id: obs.id } },
            body: {
              decision,
              authority_ref: ref.trim() || null,
              approved_max_height_m_agl: approving ? height : null,
              approved_top_m_amsl: approving ? top : null,
              conditions: approving ? conds : [],
              conditions_text: condText.trim() || null,
              valid_from: approving ? from : null,
              valid_to: approving ? to : null,
              linked_ntm_ids: ntms,
            },
          }),
        );
        qc.setQueryData(ak.obstacle(obs.id), u);
        await qc.invalidateQueries({ queryKey: ["obstacles"] });
        toast.success(te(`obstacleDecision.${decision}`));
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="dc-decision" label={t("fields.decision")} required>
          <Select value={decision} onChange={(e) => setDecision(e.target.value as Schemas["ObstacleDecision"])}>
            {OBSTACLE_DECISIONS.map((x) => (
              <option key={x} value={x}>
                {te(`obstacleDecision.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dc-ref" label={t("fields.authority_ref")} required={pen}>
          <Input className="ltr" maxLength={40} value={ref} onChange={(e) => setRef(e.target.value)} />
        </FormField>
        {approving ? (
          <>
            <FormField id="dc-height" label={t("fields.approved_max_height_m_agl")} hint={t("capHint")}>
              <Input type="number" step="0.01" className="ltr" value={height} onChange={(e) => setHeight(e.target.value)} />
            </FormField>
            <FormField id="dc-top" label={t("fields.approved_top_m_amsl")}>
              <Input type="number" step="0.01" className="ltr" value={top} onChange={(e) => setTop(e.target.value)} />
            </FormField>
            <FormField id="dc-from" label={t("fields.valid_from")}>
              <Input type="date" min={obs.requested_from} max={obs.requested_to} value={from} onChange={(e) => setFrom(e.target.value)} />
            </FormField>
            <FormField id="dc-to" label={t("fields.valid_to")}>
              <Input type="date" min={from} max={obs.requested_to} value={to} onChange={(e) => setTo(e.target.value)} />
            </FormField>
            <div className="sm:col-span-2">
              <MultiSelect id="dc-conds" label={t("fields.conditions")} options={OBSTACLE_CONDITIONS.map((x) => ({ value: x, label: te(`obstacleCondition.${x}`) }))} value={conds} onChange={(v) => setConds(v as Schemas["ObstacleCondition"][])} className="lg:w-full" />
            </div>
            <FormField id="dc-ctext" label={t("fields.conditions_text")} className="sm:col-span-2">
              <Textarea rows={2} value={condText} onChange={(e) => setCondText(e.target.value)} />
            </FormField>
            {conds.includes("notam_required") ? (
              <div className="sm:col-span-2">
                <MultiSelect id="dc-ntms" label={t("linkedNotams")} options={(notams.data?.items ?? []).map((n) => ({ value: n.id, label: `${n.ntm_no}${n.notam_number ? ` · ${n.notam_number}` : ""}` }))} value={ntms} onChange={setNtms} className="lg:w-full" />
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </StepDialog>
  );
}
