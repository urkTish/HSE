"use client";
import { Ban, ClipboardCheck, OctagonAlert, Repeat, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import { useCurrentProject } from "@/lib/current-project";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useChecklistResponse, useFieldFindings, useFieldRefresh, useStopWorkOrder, useStopWorkOrders } from "@/lib/api/field";
import { INSPECTION_SEVERITIES, STOP_STATUSES } from "@/lib/field-enums";
import { useSearchState } from "@/lib/url-state";
import { CriticalMark, FieldInspectSubNav, FieldReasonDialog, FieldSeverityBadge, NoNamesHint, OfflineLabel, PhotoPicker, ResultBadge, Score, StopStatusBadge, useBi, useFieldCaps, useFieldRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ Phase 1 inspection: checklist, score, findings, void (§11.2, EXE-9) ═════════════ */

/** Shown on the Phase 1 inspection page: "Run checklist" for open instances, the response once submitted. */
export function InspectionChecklistPanel({ inspection }: { inspection: S["InspectionRead"] }) {
  const t = useTranslations("field.insp");
  const caps = useFieldCaps(inspection.project_id);
  const [voiding, setVoiding] = useState(false);
  const open = inspection.status === "planned" || inspection.status === "missed";
  const completed = inspection.status === "completed";
  return (
    <>
      {open && caps.record ? (
        <Card data-testid="run-checklist-card">
          <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
            <ClipboardCheck aria-hidden className="size-5 text-primary" />
            <span className="flex-1">{t("runHint")}</span>
            <Button asChild className="min-h-11">
              <Link href={`/field-inspections/new?inspection=${inspection.id}`} data-testid="run-checklist">
                {t("run")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}
      {inspection.status === "voided" ? (
        <Alert tone="warning" data-testid="inspection-voided">
          {t("voided")} {inspection.void_reason ? <span dir="auto">— {inspection.void_reason}</span> : null}
        </Alert>
      ) : null}
      {inspection.response_id ? <ResponseCard id={inspection.response_id} canVoid={completed && caps.void} onVoid={() => setVoiding(true)} /> : completed && caps.void ? (
        <div>
          <Button variant="outline" onClick={() => setVoiding(true)} data-testid="void-inspection">
            <Ban aria-hidden />
            {t("void")}
          </Button>
        </div>
      ) : null}
      {voiding ? (
        <FieldReasonDialog
          title={t("voidTitle")}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/inspections/{inspection_id}/void", { params: { path: { inspection_id: inspection.id } }, body: { reason } }))}
          onClose={() => setVoiding(false)}
        />
      ) : null}
    </>
  );
}

function ResponseCard({ id, canVoid, onVoid }: { id: string; canVoid: boolean; onVoid: () => void }) {
  const t = useTranslations("field.insp");
  const q = useChecklistResponse(id);
  if (q.isLoading) return <LoadingState rows={3} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) return null;
  return (
    <Card data-testid="response-card" data-result={r.result ?? ""}>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <ClipboardCheck aria-hidden className="size-5" />
          {t("checklist")}
          <Code data-testid="response-template">
            {r.template_code} v{r.template_version}
          </Code>
          <OfflineLabel show={r.recorded_offline} minutes={r.offline_delay_min} />
          {r.voided ? <StatusBadge status="voided" label={t("voidedShort")} /> : null}
        </CardTitle>
        {canVoid && !r.voided ? (
          <Button size="sm" variant="outline" onClick={onVoid} data-testid="void-inspection">
            <Ban aria-hidden />
            {t("void")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <Score v={r.score_pct} className="text-3xl font-semibold" testId="response-score" />
          <ResultBadge result={r.result} testId="response-result" />
          <span className="text-sm text-muted-foreground">{t("items", { compliant: r.compliant_count, applicable: r.applicable_count })}</span>
          {r.pass_mark_pct ? <span className="text-sm text-muted-foreground">{t("passMark", { v: r.pass_mark_pct })}</span> : null}
          {r.critical_fail_count ? (
            <Badge tone="danger" data-testid="critical-fails">
              <OctagonAlert aria-hidden />
              {t("criticalFails", { n: r.critical_fail_count })}
            </Badge>
          ) : null}
          {r.self_inspection ? <Badge tone="info">{t("selfInspection")}</Badge> : null}
        </div>
        {r.stop_work_order_id ? (
          <Alert tone="danger">
            <span className="inline-flex flex-wrap items-center gap-2">
              <OctagonAlert aria-hidden className="size-4" />
              {t("stopOrder")}
              <Link href={`/stop-work-orders/${r.stop_work_order_id}`} className="font-semibold underline" data-testid="response-stop">
                {r.stop_work_order_no}
              </Link>
            </span>
          </Alert>
        ) : null}
        <FindingsTable findings={r.findings} />
        <details className="rounded-md border p-3 text-sm" data-testid="response-answers">
          <summary className="cursor-pointer font-medium">{t("answers", { n: r.answers.length })}</summary>
          <ul className="mt-2 flex flex-col divide-y">
            {r.answers.map((a) => (
              <li key={a.item_code} className="flex flex-wrap items-start gap-2 py-1.5" data-testid="answer-row" data-code={a.item_code} data-compliant={a.compliant === null ? "" : String(a.compliant)}>
                <Code className="shrink-0">{a.item_code}</Code>
                <span className="min-w-24">
                  <AnswerValue a={a} />
                </span>
                {a.note ? (
                  <span className="flex-1 text-muted-foreground" dir="auto">
                    {a.note}
                  </span>
                ) : null}
                {a.raise_defect_for ? (
                  <Link href="/defects" className="text-primary underline">
                    {t("raiseDefect", { tag: a.raise_defect_for })}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
        {r.answers.some((a) => a.photo_ids?.length) ? (
          <div>
            <p className="mb-1 text-sm font-medium">{t("photos")}</p>
            <Attachments ownerType="field_photo" ownerId={r.id} canUpload={false} />
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {t("inspector")}: <UserName u={r.inspector} />
        </p>
      </CardContent>
    </Card>
  );
}

function AnswerValue({ a }: { a: S["AnswerRead"] }) {
  const te = useTranslations("enums");
  if (!a.applicable && a.answer !== "na" && (a.item_type === "yes_no" || a.item_type === "rating_0_3")) return <span className="text-muted-foreground">{te("fdAnswer.na")}</span>;
  if (a.item_type === "numeric") return <bdi className="ltr">{a.numeric_value ?? (a.answer === "na" ? te("fdAnswer.na") : "—")}</bdi>;
  if (a.item_type === "count") return <bdi className="ltr">{a.count_value ?? "—"}</bdi>;
  if (a.item_type === "text") return <span dir="auto">{a.answer ?? "—"}</span>;
  if (a.item_type === "photo") return <span>{a.photo_ids?.length ?? 0}</span>;
  const tone = a.compliant === false ? "danger" : a.compliant ? "success" : "neutral";
  const text = a.item_type === "yes_no" && a.answer ? te(`fdAnswer.${a.answer as "compliant"}`) : (a.answer ?? "—");
  return <Badge tone={tone}>{text}</Badge>;
}

export function FindingsTable({ findings, showOwner = false }: { findings: S["FieldFindingRead"][]; showOwner?: boolean }) {
  const t = useTranslations("field.insp");
  const te = useTranslations("enums");
  const bi = useBi();
  if (!findings.length) return <p className="text-sm text-muted-foreground">{t("noFindings")}</p>;
  return (
    <Table data-testid="fd-findings">
      <THead>
        <TR>
          <TH>{t("finding")}</TH>
          {showOwner ? <TH>{t("owner")}</TH> : null}
          <TH>{t("severity")}</TH>
          <TH>{t("description")}</TH>
          <TH>{t("ca")}</TH>
        </TR>
      </THead>
      <TBody>
        {findings.map((f) => (
          <TR key={f.id} data-testid="fd-finding" data-no={f.finding_no} data-repeat={f.repeat_of ? "yes" : "no"} data-severity={f.severity}>
            <TD label={t("finding")}>
              <span className="flex flex-col gap-1">
                <Code className="text-xs">{f.finding_no}</Code>
                {f.item_code ? (
                  <span className="text-xs">
                    <Code>{f.item_code}</Code> {f.critical_item ? <CriticalMark /> : null}
                  </span>
                ) : null}
              </span>
            </TD>
            {showOwner ? (
              <TD label={t("owner")}>
                <span className="flex flex-col text-xs">
                  <Code>{f.owner_ref}</Code>
                  <span>
                    {f.site.code}
                    {f.zone ? ` · ${f.zone.code}` : ""}
                    {f.responsible_engagement ? ` · ${f.responsible_engagement.short_code}` : ""}
                  </span>
                  <StackedDate v={f.completed_date} />
                </span>
              </TD>
            ) : null}
            <TD label={t("severity")}>
              <span className="flex flex-col items-start gap-1">
                <FieldSeverityBadge severity={f.severity} />
                {f.repeat_of ? (
                  <Badge tone="warning" data-testid="repeat-mark">
                    <Repeat aria-hidden />
                    {t("repeat")}
                  </Badge>
                ) : null}
                {f.voided ? <StatusBadge status="voided" label={t("voidedShort")} /> : null}
              </span>
            </TD>
            <TD label={t("description")}>
              <span className="flex flex-col gap-0.5 text-sm">
                {f.item_text_en ? <span className="text-xs text-muted-foreground">{bi(f.item_text_en, f.item_text_ar)}</span> : null}
                <span dir="auto">{bi(f.description_en, f.description_ar) || "—"}</span>
                {f.repeat_of ? (
                  <span className="text-xs text-muted-foreground">
                    {t("repeatOf")} <Code>{f.repeat_of}</Code>
                  </span>
                ) : null}
              </span>
            </TD>
            <TD label={t("ca")}>
              {f.ca_id ? (
                <span className="flex flex-col items-start gap-1">
                  <Link href={`/actions/${f.ca_id}`} className="ltr text-primary hover:underline" data-testid="finding-ca">
                    {f.ca_ref}
                  </Link>
                  {f.ca_status ? <StatusBadge status={f.ca_status} label={te(`caStatus.${f.ca_status}`)} /> : null}
                </span>
              ) : f.fixed_on_spot ? (
                <Badge tone="success">
                  <ShieldCheck aria-hidden />
                  {t("fixedOnSpot")}
                </Badge>
              ) : (
                <span className="text-xs text-muted-foreground">{t("noCa")}</span>
              )}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/* ═════════════ findings register (§8.3) ═════════════ */

export function FieldFindingsPage() {
  return <ProjectGate>{(p) => <Findings project={p} />}</ProjectGate>;
}

function Findings({ project }: { project: Project }) {
  const t = useTranslations("field.findings");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { severity } = useFieldRef();
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const eng = s.get("eng") ?? "";
  const sev = s.get("severity") ?? "";
  const repeat = s.get("repeat") ?? "";
  const from = s.get("from") ?? "";
  const to = s.get("to") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useFieldFindings(
    project.id,
    { site_id: site || null, engagement_id: eng || null, severity: sev ? [sev as S["app__core__field_enums__FindingSeverity"]] : null, repeat: repeat ? repeat === "yes" : null, date_from: from || null, date_to: to || null, page, page_size: 50 },
    { enabled: caps.view },
  );
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldInspectSubNav />
      <ListToolbar>
        <SelectFilter id="ff-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="ff-eng" label={t("engagement")} value={eng} onChange={(v) => s.set({ eng: v, page: null })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="ff-sev" label={t("severity")} value={sev} onChange={(v) => s.set({ severity: v, page: null })} options={INSPECTION_SEVERITIES.map((x) => ({ value: x, label: severity(x) }))} />
        <SelectFilter id="ff-repeat" label={t("repeat")} value={repeat as "yes" | "no" | ""} onChange={(v) => s.set({ repeat: v, page: null })} options={[{ value: "yes", label: t("repeatYes") }, { value: "no", label: t("repeatNo") }]} />
        <DateFilter id="ff-from" label={t("from")} value={from} onChange={(v) => s.set({ from: v, page: null })} />
        <DateFilter id="ff-to" label={t("to")} value={to} onChange={(v) => s.set({ to: v, page: null })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <>
          <FindingsTable findings={q.data.items} showOwner />
          <Pagination page={page} pageSize={50} total={q.data.total} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ stop-work orders (§3.9, FND-7…FND-9) ═════════════ */

export function StopWorkOrdersPage() {
  return <ProjectGate>{(p) => <Stops project={p} />}</ProjectGate>;
}

function Stops({ project }: { project: Project }) {
  const t = useTranslations("field.stop");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const opts = useProjectOptions(project.id);
  const bi = useBi();
  const s = useSearchState();
  const status = (s.get("status") ?? "") as S["StopOrderStatus"] | "";
  const site = s.get("site") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useStopWorkOrders(project.id, { status: status ? [status] : null, site_id: site || null, page, page_size: 50 }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldInspectSubNav />
      <ListToolbar>
        <SelectFilter id="sw-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={STOP_STATUSES.map((x) => ({ value: x, label: te(`fdStopStatus.${x}`) }))} />
        <SelectFilter id="sw-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <>
          <Table data-testid="stops-table">
            <THead>
              <TR>
                <TH>{t("order")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("activity")}</TH>
                <TH>{t("raised")}</TH>
                <TH>{t("ca")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.items.map((o) => (
                <TR key={o.id} data-testid="stop-row" data-no={o.order_no} data-status={o.status}>
                  <TD label={t("order")}>
                    <Link href={`/stop-work-orders/${o.id}`} className="font-medium text-primary hover:underline">
                      <Code>{o.order_no}</Code>
                    </Link>
                    <span className="block text-xs">
                      <Code>{o.item_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("where")}>
                    {o.site.code}
                    {o.zone ? ` · ${o.zone.code}` : ""}
                    {o.engagement ? <span className="block text-xs text-muted-foreground">{o.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("activity")}>
                    <span dir="auto">{bi(o.activity_en, o.activity_ar)}</span>
                  </TD>
                  <TD label={t("raised")}>
                    <StackedDate v={o.raised_at} time projectId={project.id} />
                    <OfflineLabel show={o.recorded_offline} />
                  </TD>
                  <TD label={t("ca")}>
                    {o.ca_id ? (
                      <Link href={`/actions/${o.ca_id}`} className="ltr text-primary hover:underline">
                        {o.ca_ref}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={tc("status")}>
                    <StopStatusBadge status={o.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data.total} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

export function StopWorkOrderPage({ id }: { id: string }) {
  const t = useTranslations("field.stop");
  const te = useTranslations("enums");
  const tn = useTranslations("field.nav");
  const bi = useBi();
  const { label } = useFieldRef();
  const q = useStopWorkOrder(id);
  const { projectId } = useCurrentProject();
  const caps = useFieldCaps(projectId);
  const [dialog, setDialog] = useState<"release" | "void" | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  const active = o.status === "active";
  const caReady = o.ca_status === "in_progress" || o.ca_status === "pending_verification" || o.ca_status === "closed";
  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumbs items={[{ label: tn("stops"), href: "/stop-work-orders" }, { label: o.order_no }]} />
      <Card data-testid="stop-detail" data-status={o.status}>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <Code>{o.order_no}</Code>
            <StopStatusBadge status={o.status} />
            <OfflineLabel show={o.recorded_offline} />
          </CardTitle>
          {active ? (
            <div className="flex flex-wrap gap-2">
              {caps.release ? (
                <Button onClick={() => setDialog("release")} data-testid="stop-release">
                  <ShieldCheck aria-hidden />
                  {t("release")}
                </Button>
              ) : null}
              {caps.void ? (
                <Button variant="outline" onClick={() => setDialog("void")} data-testid="stop-void">
                  <Ban aria-hidden />
                  {t("void")}
                </Button>
              ) : null}
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {active ? (
            <div role="alert" className="flex items-start gap-3 rounded-md border-2 border-danger bg-danger-bg p-3 text-danger">
              <OctagonAlert aria-hidden className="size-7 shrink-0" />
              <span className="text-sm font-semibold">{t("activeNote")}</span>
            </div>
          ) : null}
          <FieldList>
            <FieldItem label={t("item")}>
              <Code>{o.item_code}</Code>
            </FieldItem>
            <FieldItem label={t("inspection")}>{o.inspection_ref ? <Code>{o.inspection_ref}</Code> : "—"}</FieldItem>
            <FieldItem label={t("where")}>
              {o.site.code}
              {o.zone ? ` · ${o.zone.code}` : ""}
              {o.engagement ? ` · ${o.engagement.short_code}` : ""}
            </FieldItem>
            <FieldItem label={t("activity")} wide>
              <span dir="auto">{bi(o.activity_en, o.activity_ar)}</span>
            </FieldItem>
            <FieldItem label={t("instructed")}>
              {label("instructed_roles", o.instructed_role)} · <StackedDate v={o.instructed_at} time />
            </FieldItem>
            <FieldItem label={t("raised")}>
              <StackedDate v={o.raised_at} time />
            </FieldItem>
            <FieldItem label={t("permits")}>{o.permits.length ? o.permits.map((p) => <Code key={p.id} className="me-1">{p.permit_no}</Code>) : "—"}</FieldItem>
            <FieldItem label={t("ca")}>
              {o.ca_id ? (
                <span className="inline-flex flex-wrap items-center gap-2">
                  <Link href={`/actions/${o.ca_id}`} className="ltr text-primary hover:underline">
                    {o.ca_ref}
                  </Link>
                  {o.ca_status ? <StatusBadge status={o.ca_status} label={te(`caStatus.${o.ca_status}`)} /> : null}
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
            {o.released_at ? (
              <>
                <FieldItem label={t("releasedBy")}>
                  <UserName u={o.released_by} /> · <StackedDate v={o.released_at} time />
                </FieldItem>
                <FieldItem label={t("releaseNote")} wide>
                  <span dir="auto">{o.release_note}</span>
                </FieldItem>
              </>
            ) : null}
            {o.status_reason ? (
              <FieldItem label={t("voidReason")} wide>
                <span dir="auto">{o.status_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
          {o.release_photo_ids.length ? <Attachments ownerType="stop_work_photo" ownerId={o.id} canUpload={false} /> : null}
        </CardContent>
      </Card>
      {dialog === "release" ? <ReleaseDialog o={o} caReady={caReady} onClose={() => setDialog(null)} /> : null}
      {dialog === "void" ? (
        <FieldReasonDialog
          title={t("voidTitle")}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/stop-work-orders/{order_id}/void", { params: { path: { order_id: o.id } }, body: { reason } }))}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

function ReleaseDialog({ o, caReady, onClose }: { o: S["StopWorkRead"]; caReady: boolean; onClose: () => void }) {
  const t = useTranslations("field.stop");
  const refresh = useFieldRefresh();
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<S["PhotoInput"][]>([]);
  return (
    <StepDialog
      title={t("releaseTitle")}
      description={o.order_no}
      warning={!caReady ? t("caNotStarted") : undefined}
      confirmLabel={t("release")}
      disabled={note.trim().length < 20 || photos.length === 0}
      testId="release-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/stop-work-orders/{order_id}/release", { params: { path: { order_id: o.id } }, body: { release_note: note.trim(), photos } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rel-note" label={t("releaseNote")} required hint={t("releaseNoteHint", { n: note.trim().length })}>
        <Textarea maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} data-testid="release-note" />
      </FormField>
      <NoNamesHint />
      <div>
        <p className="mb-1 text-sm font-medium">
          {t("releasePhotos")} <span className="text-danger">*</span>
        </p>
        <PhotoPicker value={photos} onChange={setPhotos} testId="release-photos" required />
      </div>
    </StepDialog>
  );
}
