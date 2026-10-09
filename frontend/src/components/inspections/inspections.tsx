"use client";
import { CalendarRange, ClipboardPlus, Pencil, Plus } from "lucide-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { LinkFilterNote } from "@/components/common/link-filter-note";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { FindingsEditor, findingsValid, toFindingInput, type FindingDraft } from "@/components/inspections/findings-editor";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useInspection, useInspectionPlan, useInspectionPlans, useInspections } from "@/lib/api/hse";
import { useProjectSettings } from "@/lib/api/queries";
import { ARABIC_SCRIPT, applyServerErrors } from "@/lib/forms";
import { DEFAULT_TIME_ZONE, todayInZone, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { useDisplay } from "@/lib/digits";
import { InspectionChecklistPanel } from "@/components/field/inspect";
import { OfflineLabel, ResultBadge } from "@/components/field/common";
import { useTemplates } from "@/lib/api/field";
import { ROTATIONS } from "@/lib/field-enums";
import { ASSIGNEE_ROLES, INSPECTION_FREQUENCIES, INSPECTION_STATUSES, INSPECTION_TIMELINESS, WEEKDAYS } from "@/lib/enums";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

export function InspectionList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inspections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const ref = useRefLists();
  const show = useDisplay(project.id);
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["InspectionStatus"][];
  const timeliness = s.getAll("timeliness") as Schemas["InspectionTimeliness"][];
  const sites = s.getAll("site_id");
  const engs = s.getAll("engagement_id");
  const type = (s.get("inspection_type") ?? "") as Schemas["InspectionType"] | "";
  const q = {
    status: status.length ? status : null,
    timeliness: timeliness.length ? timeliness : null,
    plan_id: s.get("plan_id") || null,
    inspection_type: type || null,
    site_id: sites.length ? sites : null,
    engagement_id: engs.length ? engs : null,
    assigned_to_me: s.getBool("assigned_to_me") ?? undefined,
    planned_from: s.get("planned_from") || null,
    planned_to: s.get("planned_to") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useInspections(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            {canWrite(me, "inspection.record", project.id) ? (
              <Button asChild>
                <Link href="/inspections/new" data-testid="new-unplanned">
                  <ClipboardPlus aria-hidden />
                  {t("unplanned")}
                </Link>
              </Button>
            ) : null}
            <Button variant="outline" asChild>
              <Link href="/inspection-plans" data-testid="open-plans">
                <CalendarRange aria-hidden />
                {t("plans")}
              </Link>
            </Button>
          </>
        }
      />
      <LinkFilterNote keys={["plan_id"]} />
      <ListToolbar>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="ins-from">{tc("dateFrom")}</Label>
          <Input id="ins-from" type="date" value={q.planned_from ?? ""} onChange={(e) => s.set({ planned_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="ins-to">{tc("dateTo")}</Label>
          <Input id="ins-to" type="date" value={q.planned_to ?? ""} onChange={(e) => s.set({ planned_to: e.target.value })} />
        </div>
        <MultiSelect id="ins-site" label={tc("site")} options={opts.sites} value={sites} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="ins-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="ins-type" label={t("fields.inspection_type")} value={type} onChange={(v) => s.set({ inspection_type: v })} options={ref.options("inspection_type")} />
        <MultiSelect id="ins-status" label={t("fields.status")} options={INSPECTION_STATUSES.map((x) => ({ value: x, label: te(`inspectionStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} testId="ins-status-filter" />
        <MultiSelect id="ins-time" label={t("fields.timeliness")} options={INSPECTION_TIMELINESS.map((x) => ({ value: x, label: te(`timeliness.${x}`) }))} value={timeliness} onChange={(v) => s.set({ timeliness: v })} />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={q.assigned_to_me === true} onChange={(e) => s.set({ assigned_to_me: e.target.checked ? "true" : null })} />
          {t("assignedToMe")}
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="inspections-table">
            <THead>
              <TR>
                <TH>{t("fields.ref")}</TH>
                <TH>{t("fields.inspection_type")}</TH>
                <TH>{t("fields.site")}</TH>
                <TH>{t("fields.engagement")}</TH>
                <TH>{t("fields.planned_date")}</TH>
                <TH>{t("fields.completed_at")}</TH>
                <TH className="text-end">{t("fields.score_pct")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((i) => (
                <TR key={i.id} data-testid="inspection-row">
                  <TD label={t("fields.ref")}>
                    <Link href={`/inspections/${i.id}`} className="ltr font-medium text-primary hover:underline">
                      {i.ref}
                    </Link>
                  </TD>
                  <TD label={t("fields.inspection_type")}>{ref.label("inspection_type", i.inspection_type)}</TD>
                  <TD label={t("fields.site")}>
                    <span className="ltr">
                      {i.site.code}
                      {i.zone ? ` / ${i.zone.code}` : ""}
                    </span>
                  </TD>
                  <TD label={t("fields.engagement")}>{i.engagement ? <span className="ltr">{i.engagement.short_code}</span> : "—"}</TD>
                  <TD label={t("fields.planned_date")}>{date(i.planned_date)}</TD>
                  <TD label={t("fields.completed_at")}>{date(i.completed_at)}</TD>
                  <TD label={t("fields.score_pct")} className="text-end tabular-nums">
                    {show(i.score_pct)}
                  </TD>
                  <TD label={t("fields.status")}>
                    <span className="inline-flex flex-wrap gap-1">
                      <StatusBadge status={i.status} label={te(`inspectionStatus.${i.status}`)} />
                      {i.status === "completed" ? <StatusBadge status={i.timeliness} label={te(`timeliness.${i.timeliness}`)} /> : null}
                    </span>
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

function ResultsFields({
  projectId,
  tz,
  completedAt,
  setCompletedAt,
  checked,
  setChecked,
  compliant,
  setCompliant,
  findings,
  setFindings,
}: {
  projectId: string;
  tz: string;
  completedAt: string;
  setCompletedAt: (v: string) => void;
  checked: string;
  setChecked: (v: string) => void;
  compliant: string;
  setCompliant: (v: string) => void;
  findings: FindingDraft[];
  setFindings: (v: FindingDraft[]) => void;
}) {
  const t = useTranslations("inspections");
  const exceeds = checked !== "" && compliant !== "" && Number(compliant) > Number(checked);
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField id="ins-completed" label={t("fields.completed_at")} required>
          <Input type="datetime-local" value={completedAt} max={utcToZonedInput(new Date().toISOString(), tz)} onChange={(e) => setCompletedAt(e.target.value)} />
        </FormField>
        <FormField id="ins-checked" label={t("fields.items_checked")}>
          <Input inputMode="numeric" className="ltr" value={checked} onChange={(e) => setChecked(e.target.value.replace(/\D/g, ""))} />
        </FormField>
        <FormField id="ins-compliant" label={t("fields.items_compliant")} error={exceeds ? t("compliantExceeds") : undefined}>
          <Input inputMode="numeric" className="ltr" value={compliant} onChange={(e) => setCompliant(e.target.value.replace(/\D/g, ""))} />
        </FormField>
      </div>
      <div>
        <p className="mb-2 text-sm font-medium">{t("findings")}</p>
        <FindingsEditor projectId={projectId} value={findings} onChange={setFindings} />
      </div>
    </>
  );
}

export function UnplannedInspectionForm({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inspections");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const ref = useRefLists();
  const opts = useProjectOptions(project.id);
  const settings = useProjectSettings(project.id);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const [type, setType] = useState("");
  const [siteId, setSiteId] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [engId, setEngId] = useState("");
  const [completedAt, setCompletedAt] = useState(utcToZonedInput(new Date().toISOString(), tz));
  const [checked, setChecked] = useState("");
  const [compliant, setCompliant] = useState("");
  const [findings, setFindings] = useState<FindingDraft[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);

  async function save() {
    if (!type || !siteId || !completedAt || !findingsValid(findings) || (checked && compliant && Number(compliant) > Number(checked))) {
      setMissing(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await unwrap(
        api.POST("/api/v1/projects/{project_id}/inspections", {
          params: { path: { project_id: project.id } },
          body: {
            inspection_type: type as Schemas["InspectionType"],
            site_id: siteId,
            zone_id: zoneId || null,
            engagement_id: engId || null,
            completed_at: zonedInputToUtc(completedAt, tz),
            items_checked: checked ? Number(checked) : null,
            items_compliant: compliant ? Number(compliant) : null,
            findings: findings.map(toFindingInput),
          },
        }),
      );
      qc.setQueryData(hk.inspection(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["inspections"] });
      toast.success(tc("created"));
      router.push(`/inspections/${saved.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6" data-testid="unplanned-form">
      <Alert tone="info">{t("unplannedHint")}</Alert>
      <FormSection title={t("unplanned")}>
        <FormField id="un-type" label={t("fields.inspection_type")} required error={missing && !type ? tv("required") : undefined}>
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">{tc("select")}</option>
            {ref.options("inspection_type").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="un-site" label={t("fields.site")} required error={missing && !siteId ? tv("required") : undefined}>
          <Select value={siteId} onChange={(e) => { setSiteId(e.target.value); setZoneId(""); }}>
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="un-zone" label={t("fields.zone")}>
          <Select value={zoneId} onChange={(e) => setZoneId(e.target.value)}>
            <option value="">{tc("noZone")}</option>
            {opts.zones.filter((z) => z.siteId === siteId).map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="un-eng" label={t("fields.engagement")}>
          <Select value={engId} onChange={(e) => setEngId(e.target.value)}>
            <option value="">{tc("anyContractor")}</option>
            {opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId)).map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
      </FormSection>
      <ResultsFields
        projectId={project.id}
        tz={tz}
        completedAt={completedAt}
        setCompletedAt={setCompletedAt}
        checked={checked}
        setChecked={setChecked}
        compliant={compliant}
        setCompliant={setCompliant}
        findings={findings}
        setFindings={setFindings}
      />
      {missing && !findingsValid(findings) ? <Alert tone="danger">{tv("required")}</Alert> : null}
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={busy} data-testid="save-inspection">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href="/inspections">{tc("cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}

export function InspectionDetail({ id }: { id: string }) {
  const t = useTranslations("inspections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const ref = useRefLists();
  const q = useInspection(id);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date, dateTime } = useFormatters(pid);
  const settings = useProjectSettings(pid);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const [completing, setCompleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [completedAt, setCompletedAt] = useState(utcToZonedInput(new Date().toISOString(), tz));
  const [checked, setChecked] = useState("");
  const [compliant, setCompliant] = useState("");
  const [findings, setFindings] = useState<FindingDraft[]>([]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const i = q.data;
  const open = i.status === "planned" || i.status === "missed";
  const canRecord = canWrite(me, "inspection.record", i.project_id) && open;
  const canCancel = canWrite(me, "inspection.plan_manage", i.project_id) && open;
  const lateNow = i.due_by ? todayInZone(tz) > i.due_by : false;

  async function complete() {
    if (!findingsValid(findings)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.POST("/api/v1/inspections/{inspection_id}/complete", {
          params: { path: { inspection_id: i.id } },
          body: {
            completed_at: zonedInputToUtc(completedAt, tz),
            items_checked: checked ? Number(checked) : null,
            items_compliant: compliant ? Number(compliant) : null,
            findings: findings.map(toFindingInput),
          },
        }),
      );
      qc.setQueryData(hk.inspection(i.id), next);
      await qc.invalidateQueries({ queryKey: ["inspections"] });
      toast.success(tc("saved"));
      setCompleting(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.POST("/api/v1/inspections/{inspection_id}/cancel", { params: { path: { inspection_id: i.id } }, body: { reason: reason.trim() } }));
      qc.setQueryData(hk.inspection(i.id), next);
      await qc.invalidateQueries({ queryKey: ["inspections"] });
      toast.success(tc("saved"));
      setCancelling(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const planName = locale === "ar" ? i.plan_name_ar ?? i.plan_name_en : i.plan_name_en;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: i.ref }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <div>
                <p className="ltr text-sm text-muted-foreground">{i.ref}</p>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <span data-testid="inspection-title">{ref.label("inspection_type", i.inspection_type)}</span>
                  <StatusBadge status={i.status} label={te(`inspectionStatus.${i.status}`)} />
                  <StatusBadge status={i.timeliness} label={te(`timeliness.${i.timeliness}`)} />
                  {i.result ? <ResultBadge result={i.result} testId="inspection-result" /> : null}
                  <OfflineLabel show={i.recorded_offline} minutes={i.offline_delay_min} />
                </CardTitle>
              </div>
              <div className="flex flex-wrap gap-2">
                {canRecord && !completing ? (
                  <Button size="sm" onClick={() => { setCompleting(true); setFindings([]); }} data-testid="record-results">
                    {t("complete")}
                  </Button>
                ) : null}
                {canCancel ? (
                  <Button size="sm" variant="outline" onClick={() => { setCancelling(true); setReason(""); setError(null); }} data-testid="cancel-inspection">
                    {t("cancel")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={t("fields.plan")}>{i.plan_id ? <Link href={`/inspection-plans/${i.plan_id}`} className="text-primary hover:underline">{planName}</Link> : te("timeliness.unplanned")}</FieldItem>
                <FieldItem label={t("fields.site")}>
                  <span className="ltr">{i.site.code}</span> — {name(i.site.name_en, i.site.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.zone")}>{i.zone ? `${i.zone.code} — ${name(i.zone.name_en, i.zone.name_ar)}` : "—"}</FieldItem>
                <FieldItem label={t("fields.engagement")}>{i.engagement ? <span className="ltr">{i.engagement.short_code}</span> : "—"}</FieldItem>
                <FieldItem label={t("fields.assignee")}>
                  {i.assignee ? name(i.assignee.full_name_en, i.assignee.full_name_ar) : i.assignee_role ? te(`assigneeRole.${i.assignee_role}`) : "—"}
                </FieldItem>
                <FieldItem label={t("fields.planned_date")}>{date(i.planned_date)}</FieldItem>
                <FieldItem label={t("fields.due_by")}>{date(i.due_by)}</FieldItem>
                <FieldItem label={t("fields.completed_at")}>{dateTime(i.completed_at)}</FieldItem>
                <FieldItem label={t("fields.inspector")}>{i.inspector ? name(i.inspector.full_name_en, i.inspector.full_name_ar) : "—"}</FieldItem>
                <FieldItem label={t("fields.items_checked")}>{show(i.items_checked)}</FieldItem>
                <FieldItem label={t("fields.items_compliant")}>{show(i.items_compliant)}</FieldItem>
                <FieldItem label={t("fields.score_pct")}>{show(i.score_pct)}</FieldItem>
                {i.cancel_reason ? <FieldItem label={t("fields.cancel_reason")}>{i.cancel_reason}</FieldItem> : null}
              </FieldList>
            </CardContent>
          </Card>
          <InspectionChecklistPanel inspection={i} />
          {completing ? (
            <Card data-testid="complete-card">
              <CardHeader>
                <CardTitle>{t("completeTitle")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {lateNow ? <Alert tone="warning">{t("lateNote")}</Alert> : null}
                <ResultsFields
                  projectId={i.project_id}
                  tz={tz}
                  completedAt={completedAt}
                  setCompletedAt={setCompletedAt}
                  checked={checked}
                  setChecked={setChecked}
                  compliant={compliant}
                  setCompliant={setCompliant}
                  findings={findings}
                  setFindings={setFindings}
                />
                <MutationError error={error} />
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => void complete()} disabled={busy || !completedAt || !findingsValid(findings)} data-testid="save-results">
                    {busy ? tc("saving") : tc("save")}
                  </Button>
                  <Button variant="ghost" onClick={() => setCompleting(false)}>
                    {tc("cancel")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>{t("findings")}</CardTitle>
            </CardHeader>
            <CardContent>
              {i.findings.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
              ) : (
                <ul className="flex flex-col divide-y" data-testid="findings-list">
                  {i.findings.map((f) => (
                    <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                      <span>
                        <StatusBadge status={f.severity === "critical" || f.severity === "high" ? "risk_high" : f.severity === "medium" ? "risk_medium" : "risk_low"} label={te(`findingSeverity.${f.severity}`)} /> {f.description}
                      </span>
                      {f.ca_id ? (
                        <Link href={`/actions/${f.ca_id}`} className="ltr text-primary hover:underline">
                          {f.ca_ref}
                        </Link>
                      ) : f.ca_required ? (
                        <span className="text-xs text-muted-foreground">{t("caRequired")}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">{can(me, "history.view", i.project_id) ? <HistoryPanel entityType="inspection" entityId={i.id} projectId={i.project_id} /> : null}</div>
      </div>
      <Dialog open={cancelling} onOpenChange={setCancelling}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("cancel")}</DialogTitle>
            <DialogDescription>{i.ref}</DialogDescription>
          </DialogHeader>
          <FormField id="cancel-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          </FormField>
          <MutationError error={error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelling(false)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void cancel()} disabled={busy || !reason.trim()} data-testid="cancel-confirm">
              {t("cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function PlanList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inspections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const locale = useLocale();
  const ref = useRefLists();
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const activeOnly = s.getBool("active") ?? true;
  const query = useInspectionPlans(project.id, { active: activeOnly ? true : undefined, page, page_size: PAGE_SIZE });
  const items = query.data?.items ?? [];
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: t("plans") }]} />
      <PageHeader
        title={t("plans")}
        description={t("plansSubtitle")}
        actions={
          canWrite(me, "inspection.plan_manage", project.id) ? (
            <Button asChild>
              <Link href="/inspection-plans/new" data-testid="new-plan">
                <Plus aria-hidden />
                {t("newPlan")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={activeOnly} onChange={(e) => s.set({ active: e.target.checked ? null : "false" })} />
          {t("activeOnly")}
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Table data-testid="plans-table">
            <THead>
              <TR>
                <TH>{t("fields.plan")}</TH>
                <TH>{t("fields.inspection_type")}</TH>
                <TH>{t("fields.site")}</TH>
                <TH>{t("fields.frequency")}</TH>
                <TH>{t("fields.assignee_role")}</TH>
                <TH>{t("nextPlanned")}</TH>
                <TH>{t("fields.active")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="plan-row">
                  <TD label={t("fields.plan")}>
                    <Link href={`/inspection-plans/${p.id}`} className="font-medium text-primary hover:underline">
                      {locale === "ar" ? p.name_ar : p.name_en}
                    </Link>
                  </TD>
                  <TD label={t("fields.inspection_type")}>{ref.label("inspection_type", p.inspection_type)}</TD>
                  <TD label={t("fields.site")}>
                    <span className="ltr">
                      {p.site.code}
                      {p.zone ? ` / ${p.zone.code}` : ""}
                    </span>
                  </TD>
                  <TD label={t("fields.frequency")}>
                    {te(`frequency.${p.frequency}`)}
                    {p.weekday ? ` · ${te(`weekday.${p.weekday}`)}` : ""}
                  </TD>
                  <TD label={t("fields.assignee_role")}>{te(`assigneeRole.${p.assignee_role}`)}</TD>
                  <TD label={t("nextPlanned")}>{date(p.next_planned_date)}</TD>
                  <TD label={t("fields.active")}>
                    <YesNo value={p.active} yes={tc("yes")} no={tc("no")} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
    </div>
  );
}

export function PlanForm({ project, plan }: { project: Schemas["ProjectRead"]; plan?: Schemas["InspectionPlanRead"] }) {
  const t = useTranslations("inspections");
  const locale = useLocale();
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const ref = useRefLists();
  const opts = useProjectOptions(project.id);
  const [error, setError] = useState<unknown>(null);
  const schema = useMemo(
    () =>
      z
        .object({
          name_en: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          name_ar: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })).regex(ARABIC_SCRIPT, tv("arabicRequired")),
          inspection_type: z.string().min(1, tv("required")),
          site_id: z.string().min(1, tv("required")),
          zone_id: z.string(),
          engagement_id: z.string(),
          frequency: z.enum(INSPECTION_FREQUENCIES),
          weekday: z.string(),
          start_date: z.string().min(1, tv("required")),
          end_date: z.string(),
          assignee_role: z.enum(ASSIGNEE_ROLES),
          assignee_user_id: z.string(),
          active: z.boolean(),
          template_code: z.string(),
          rotation: z.enum(ROTATIONS),
        })
        .superRefine((v, ctx) => {
          if ((v.frequency === "weekly" || v.frequency === "fortnightly") && !v.weekday) ctx.addIssue({ code: "custom", path: ["weekday"], message: tv("required") });
          if (v.end_date && v.end_date < v.start_date) ctx.addIssue({ code: "custom", path: ["end_date"], message: tv("endBeforeStart") });
        }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name_en: plan?.name_en ?? "",
      name_ar: plan?.name_ar ?? "",
      inspection_type: plan?.inspection_type ?? "",
      site_id: plan?.site.id ?? "",
      zone_id: plan?.zone?.id ?? "",
      engagement_id: plan?.engagement?.id ?? "",
      frequency: plan?.frequency ?? "weekly",
      weekday: plan?.weekday ?? "sunday",
      start_date: plan?.start_date ?? todayInZone(),
      end_date: plan?.end_date ?? "",
      assignee_role: plan?.assignee_role ?? "hse_officer",
      assignee_user_id: plan?.assignee?.id ?? "",
      active: plan?.active ?? true,
      template_code: plan?.template_code ?? "",
      rotation: plan?.rotation ?? "none",
    },
  });
  const [rotationList, setRotationList] = useState<string[]>(plan?.rotation_list ?? []);
  const { errors, isSubmitting } = form.formState;
  const siteId = useWatch({ control: form.control, name: "site_id" });
  const freq = useWatch({ control: form.control, name: "frequency" });
  const role = useWatch({ control: form.control, name: "assignee_role" });
  const itype = useWatch({ control: form.control, name: "inspection_type" });
  const rotation = useWatch({ control: form.control, name: "rotation" });
  const templates = useTemplates({ kind: "inspection", status: ["published"], project_id: project.id, inspection_type: (itype || null) as Schemas["InspectionType"] | null }, { enabled: Boolean(itype) });
  const rotationOptions = rotation === "zones" ? opts.zones.filter((z) => z.siteId === siteId) : opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId));

  async function save(v: Values) {
    setError(null);
    const weekday = freq === "weekly" || freq === "fortnightly" ? (v.weekday as Schemas["Weekday"]) : null;
    try {
      const saved = plan
        ? await unwrap(
            api.PATCH("/api/v1/inspection-plans/{plan_id}", {
              params: { path: { plan_id: plan.id } },
              body: {
                name_en: v.name_en.trim(),
                name_ar: v.name_ar.trim(),
                zone_id: v.zone_id || null,
                engagement_id: v.engagement_id || null,
                frequency: v.frequency,
                weekday,
                end_date: v.end_date || null,
                assignee_role: v.assignee_role,
                assignee_user_id: v.assignee_user_id || null,
                active: v.active,
                template_code: v.template_code || null,
                rotation: v.rotation,
                rotation_list: v.rotation === "none" ? [] : rotationList,
              },
            }),
          )
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/inspection-plans", {
              params: { path: { project_id: project.id } },
              body: {
                name_en: v.name_en.trim(),
                name_ar: v.name_ar.trim(),
                inspection_type: v.inspection_type as Schemas["InspectionType"],
                site_id: v.site_id,
                zone_id: v.zone_id || null,
                engagement_id: v.engagement_id || null,
                frequency: v.frequency,
                weekday,
                start_date: v.start_date,
                end_date: v.end_date || null,
                assignee_role: v.assignee_role,
                assignee_user_id: v.assignee_user_id || null,
                active: v.active,
                template_code: v.template_code || null,
                rotation: v.rotation,
                rotation_list: v.rotation === "none" ? [] : rotationList,
              },
            }),
          );
      qc.setQueryData(hk.plan(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["inspection-plans"] });
      await qc.invalidateQueries({ queryKey: ["inspections"] });
      toast.success(plan ? tc("saved") : tc("created"));
      router.push(`/inspection-plans/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="plan-form">
      {plan ? <Alert tone="info">{t("futureOnly")}</Alert> : null}
      <FormSection title={plan ? t("editPlan") : t("newPlan")}>
        <FormField id="name_en" label={t("fields.name_en")} required error={errors.name_en?.message}>
          <Input maxLength={150} {...form.register("name_en")} />
        </FormField>
        <FormField id="name_ar" label={t("fields.name_ar")} required error={errors.name_ar?.message}>
          <Input dir="rtl" maxLength={150} {...form.register("name_ar")} />
        </FormField>
        <FormField id="inspection_type" label={t("fields.inspection_type")} required error={errors.inspection_type?.message}>
          <Select disabled={Boolean(plan)} {...form.register("inspection_type")}>
            <option value="">{tc("select")}</option>
            {ref.options("inspection_type").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="site_id" label={t("fields.site")} required error={errors.site_id?.message}>
          <Select disabled={Boolean(plan)} {...form.register("site_id", { onChange: () => form.setValue("zone_id", "") })}>
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="zone_id" label={t("fields.zone")}>
          <Select {...form.register("zone_id")}>
            <option value="">{tc("noZone")}</option>
            {opts.zones.filter((z) => z.siteId === siteId).map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="engagement_id" label={t("fields.engagement")}>
          <Select {...form.register("engagement_id")}>
            <option value="">{tc("anyContractor")}</option>
            {opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId)).map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="frequency" label={t("fields.frequency")} required>
          <Select {...form.register("frequency")}>
            {INSPECTION_FREQUENCIES.map((x) => (
              <option key={x} value={x}>
                {te(`frequency.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {freq === "weekly" || freq === "fortnightly" ? (
          <FormField id="weekday" label={t("fields.weekday")} required error={errors.weekday?.message}>
            <Select {...form.register("weekday")}>
              {WEEKDAYS.map((x) => (
                <option key={x} value={x}>
                  {te(`weekday.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="start_date" label={t("fields.start_date")} required error={errors.start_date?.message}>
          <Input type="date" disabled={Boolean(plan)} {...form.register("start_date")} />
        </FormField>
        <FormField id="end_date" label={t("fields.end_date")} error={errors.end_date?.message}>
          <Input type="date" {...form.register("end_date")} />
        </FormField>
        <FormField id="assignee_role" label={t("fields.assignee_role")} required>
          <Select {...form.register("assignee_role")}>
            {ASSIGNEE_ROLES.map((x) => (
              <option key={x} value={x}>
                {te(`assigneeRole.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="assignee_user_id" label={t("fields.assignee")}>
          <UserSelect projectId={project.id} role={role} {...form.register("assignee_user_id")} />
        </FormField>
        <FormField id="template_code" label={t("fields.template")} hint={t("templateHint")}>
          <Select {...form.register("template_code")} data-testid="plan-template">
            <option value="">{t("noTemplate")}</option>
            {(templates.data?.items ?? []).map((x) => (
              <option key={x.id} value={x.template_code}>
                {x.template_code} — {locale === "ar" ? x.title_ar : x.title_en}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="rotation" label={t("fields.rotation")} hint={t("rotationHint")}>
          <Select {...form.register("rotation", { onChange: () => setRotationList([]) })} data-testid="plan-rotation">
            {ROTATIONS.map((x) => (
              <option key={x} value={x}>
                {te(`fdRotation.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {rotation !== "none" ? (
          <MultiSelect id="rotation_list" label={t("fields.rotation_list")} options={rotationOptions} value={rotationList} onChange={setRotationList} allLabel={tc("select")} testId="plan-rotation-list" />
        ) : null}
        <CheckboxField id="active" label={t("fields.active")}>
          <Checkbox {...form.register("active")} />
        </CheckboxField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-plan">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={plan ? `/inspection-plans/${plan.id}` : "/inspection-plans"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}

export function PlanDetail({ id }: { id: string }) {
  const t = useTranslations("inspections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const me = useMeData();
  const name = useLocalizedName();
  const ref = useRefLists();
  const q = useInspectionPlan(id);
  const pid = q.data?.project_id ?? null;
  const { date } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("inspections"), href: "/inspections" }, { label: t("plans"), href: "/inspection-plans" }, { label: locale === "ar" ? p.name_ar : p.name_en }]} />
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <span data-testid="plan-title">{locale === "ar" ? p.name_ar : p.name_en}</span>
            <StatusBadge status={p.active ? "active" : "inactive"} label={p.active ? t("fields.active") : tc("no")} />
          </CardTitle>
          <div className="flex gap-2">
            {canWrite(me, "inspection.plan_manage", p.project_id) ? (
              <Button size="sm" variant="outline" asChild>
                <Link href={`/inspection-plans/${p.id}/edit`} data-testid="edit-plan">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Link>
              </Button>
            ) : null}
            <Button size="sm" variant="outline" asChild>
              <Link href={`/inspections?plan_id=${p.id}&project=${p.project_id}`}>{t("title")}</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("fields.inspection_type")}>{ref.label("inspection_type", p.inspection_type)}</FieldItem>
            <FieldItem label={t("fields.site")}>
              <span className="ltr">{p.site.code}</span> — {name(p.site.name_en, p.site.name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.zone")}>{p.zone ? `${p.zone.code} — ${name(p.zone.name_en, p.zone.name_ar)}` : "—"}</FieldItem>
            <FieldItem label={t("fields.engagement")}>{p.engagement ? <span className="ltr">{p.engagement.short_code}</span> : "—"}</FieldItem>
            <FieldItem label={t("fields.frequency")}>
              {te(`frequency.${p.frequency}`)}
              {p.weekday ? ` · ${te(`weekday.${p.weekday}`)}` : ""}
            </FieldItem>
            <FieldItem label={t("fields.start_date")}>{date(p.start_date)}</FieldItem>
            <FieldItem label={t("fields.end_date")}>{date(p.end_date)}</FieldItem>
            <FieldItem label={t("fields.assignee_role")}>{te(`assigneeRole.${p.assignee_role}`)}</FieldItem>
            <FieldItem label={t("fields.assignee")}>{p.assignee ? name(p.assignee.full_name_en, p.assignee.full_name_ar) : "—"}</FieldItem>
            <FieldItem label={t("nextPlanned")}>{date(p.next_planned_date)}</FieldItem>
            <FieldItem label={t("fields.template")}>
              {p.template_code ? (
                <span className="ltr font-mono" data-testid="plan-template-code">
                  {p.template_code}
                </span>
              ) : (
                t("noTemplate")
              )}
            </FieldItem>
            <FieldItem label={t("fields.rotation")}>
              {te(`fdRotation.${p.rotation}`)}
              {p.rotation_list?.length ? ` · ${p.rotation_list.length}` : ""}
            </FieldItem>
          </FieldList>
          {p.without_checklist ? (
            <Alert tone="warning" className="mt-4" data-testid="plan-without-checklist">
              {t("withoutChecklist")}
            </Alert>
          ) : null}
        </CardContent>
      </Card>
      {can(me, "history.view", p.project_id) ? (
        <div className="mt-6">
          <HistoryPanel entityType="inspection_plan" entityId={p.id} projectId={p.project_id} />
        </div>
      ) : null}
    </div>
  );
}
