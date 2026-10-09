"use client";
import { Flag, Plus, RefreshCcw, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState, NotFoundState } from "@/components/common/states";
import { Code, DaysLeft, StepDialog } from "@/components/access/common";
import { StackedDate } from "@/components/medical/common";
import { DecimalInput } from "@/components/ptw/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAspect, useAspects, useEnvPermit, useEnvPermits, useEnvPoints, useEnvProvider, useEnvProviders, useEnvRefresh } from "@/lib/api/env";
import { ASPECT_STATUSES, CONTROL_LEVELS, PERMIT_STATUSES, WASTE_CLASSES } from "@/lib/env-enums";
import { useRefLists } from "@/lib/reference";
import { useSearchState } from "@/lib/url-state";
import { Check, EnvPermitSubNav, EnvReasonDialog, EnvStatusBadge, NoNamesHint, useBi, useEnvCaps, useEnvRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/* ═════════════ aspects and impacts register (§3.1, ASP-1…ASP-3) ═════════════ */

export function AspectsPage() {
  return <ProjectGate>{(p) => <Aspects project={p} />}</ProjectGate>;
}

function Aspects({ project }: { project: Project }) {
  const t = useTranslations("env.aspects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const refs = useRefLists();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["AspectStatus"] | "";
  const sig = s.get("significant") ?? "";
  const q = useAspects(project.id, { status: status ? [status] : null, significant: sig ? sig === "1" : null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  const [creating, setCreating] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  const site = (id: string) => opts.sites.find((x) => x.value === id)?.code ?? "—";
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.aspects ? (
            <Button onClick={() => setCreating(true)} data-testid="aspect-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <SelectFilter id="as-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={ASPECT_STATUSES.map((x) => ({ value: x, label: te(`envAspectStatus.${x}`) }))} />
        <SelectFilter
          id="as-sig"
          label={t("significant")}
          value={sig}
          onChange={(v) => s.set({ significant: v })}
          options={[
            { value: "1", label: t("sigYes") },
            { value: "0", label: t("sigNo") },
          ]}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="aspects-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("activity")}</TH>
                <TH>{t("aspectImpact")}</TH>
                <TH>{t("sites")}</TH>
                <TH className="text-end">{t("score")}</TH>
                <TH>{t("reviewDue")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="aspect-row" data-no={a.aspect_no}>
                  <TD label={t("no")}>
                    <Link href={`/env-aspects/${a.id}`} className="font-medium text-primary hover:underline">
                      <Code>{a.aspect_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("activity")}>
                    {refs.label("activity", a.activity)}
                    <span className="block text-xs text-muted-foreground">{ref.label("condition", a.condition)}</span>
                  </TD>
                  <TD label={t("aspectImpact")}>
                    {ref.label("aspects", a.aspect)}
                    <span className="block text-xs text-muted-foreground">{ref.label("impacts", a.impact)}</span>
                  </TD>
                  <TD label={t("sites")}>
                    <Code>{a.site_ids.map(site).join(", ")}</Code>
                  </TD>
                  <TD label={t("score")} className="text-end">
                    <span className="tabular-nums font-semibold">{a.score}</span>
                    {a.significant ? (
                      <Badge tone="warning" className="ms-1" data-testid="significant">
                        {t("sigYes")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("reviewDue")}>
                    <StackedDate v={a.review_due_on} projectId={project.id} />
                    {a.review_flag ? (
                      <Badge tone="warning" data-testid="review-flag">
                        <Flag aria-hidden />
                        {t("reviewFlag")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envAspectStatus" status={a.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status || sig ? undefined : t("empty")} />
      )}
      {creating ? <AspectForm project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function AspectForm({ project, aspect, onClose }: { project: Project; aspect?: S["AspectRead"]; onClose: () => void }) {
  const t = useTranslations("env.aspects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const refs = useRefLists();
  const opts = useProjectOptions(project.id);
  const points = useEnvPoints(project.id);
  const refresh = useEnvRefresh();
  const [v, setV] = useState({
    activity: aspect?.activity ?? "",
    aspect: aspect?.aspect ?? "",
    impact: aspect?.impact ?? "",
    condition: aspect?.condition ?? "normal",
    site_ids: aspect?.site_ids ?? [],
    engagement_ids: aspect?.engagement_ids ?? [],
    severity: String(aspect?.severity ?? 3),
    likelihood: String(aspect?.likelihood ?? 3),
    legal_requirement: aspect?.legal_requirement ?? false,
    stakeholder_concern: aspect?.stakeholder_concern ?? false,
  });
  const [controls, setControls] = useState<S["AspectControl"][]>(aspect?.controls ?? []);
  const [links, setLinks] = useState<S["MonitoringLink"][]>(aspect?.monitoring_links ?? []);
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const score = Number(v.severity) * Number(v.likelihood);
  const ready = Boolean(v.activity && v.aspect && v.impact && v.site_ids.length);
  return (
    <StepDialog
      wide
      title={aspect ? t("editTitle", { no: aspect.aspect_no }) : t("new")}
      confirmLabel={tc("save")}
      disabled={!ready}
      testId="aspect-save"
      onConfirm={async () => {
        const body = {
          activity: v.activity as S["Activity"],
          aspect: v.aspect,
          impact: v.impact,
          condition: v.condition as S["AspectCondition"],
          site_ids: v.site_ids,
          engagement_ids: v.engagement_ids,
          severity: Number(v.severity),
          likelihood: Number(v.likelihood),
          legal_requirement: v.legal_requirement,
          stakeholder_concern: v.stakeholder_concern,
          controls: controls.filter((c) => c.text_en.trim()),
          monitoring_links: links.filter((l) => l.template_code || (l.point_id && l.parameter)),
        };
        if (aspect) await unwrap(api.PATCH("/api/v1/env-aspects/{aspect_id}", { params: { path: { aspect_id: aspect.id } }, body }));
        else await unwrap(api.POST("/api/v1/projects/{project_id}/env-aspects", { params: { path: { project_id: project.id } }, body }));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="as-activity" label={t("activity")} required>
          <Select value={v.activity} onChange={(e) => set({ activity: e.target.value })} data-testid="as-activity">
            <option value="">{tc("select")}</option>
            {refs.options("activity").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="as-condition" label={t("condition")} required>
          <Select value={v.condition} onChange={(e) => set({ condition: e.target.value as S["AspectCondition"] })}>
            {ref.options("condition").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="as-aspect" label={t("aspect")} required>
          <Select value={v.aspect} onChange={(e) => set({ aspect: e.target.value })} data-testid="as-aspect">
            <option value="">{tc("select")}</option>
            {ref.options("aspects").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="as-impact" label={t("impact")} required>
          <Select value={v.impact} onChange={(e) => set({ impact: e.target.value })} data-testid="as-impact">
            <option value="">{tc("select")}</option>
            {ref.options("impacts").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="as-sites" label={t("sites")} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} value={v.site_ids} onChange={(x) => set({ site_ids: x })} allLabel={tc("select")} testId="as-sites" />
        <MultiSelect id="as-engs" label={t("contractors")} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} value={v.engagement_ids} onChange={(x) => set({ engagement_ids: x })} allLabel={t("anyContractor")} />
        <FormField id="as-sev" label={t("severity")} required hint="1–5">
          <Input type="number" min={1} max={5} value={v.severity} onChange={(e) => set({ severity: e.target.value })} data-testid="as-severity" />
        </FormField>
        <FormField id="as-lik" label={t("likelihood")} required hint="1–5">
          <Input type="number" min={1} max={5} value={v.likelihood} onChange={(e) => set({ likelihood: e.target.value })} data-testid="as-likelihood" />
        </FormField>
        <Check id="as-legal" label={t("legal")} checked={v.legal_requirement} onChange={(c) => set({ legal_requirement: c })} testId="as-legal" />
        <Check id="as-stake" label={t("stakeholder")} checked={v.stakeholder_concern} onChange={(c) => set({ stakeholder_concern: c })} />
      </div>
      <p className="text-sm" data-testid="as-score-preview">
        {t("scorePreview", { score: Number.isFinite(score) ? score : 0 })} · {t("significantRule")}
      </p>
      <fieldset className="flex flex-col gap-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("controls")}</legend>
        {controls.map((c, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_10rem_auto]">
            <Input aria-label={t("controlEn")} placeholder={t("controlEn")} value={c.text_en} onChange={(e) => setControls(controls.map((x, j) => (j === i ? { ...x, text_en: e.target.value } : x)))} data-testid="as-control-en" />
            <Input aria-label={t("controlAr")} placeholder={t("controlAr")} dir="rtl" value={c.text_ar ?? ""} onChange={(e) => setControls(controls.map((x, j) => (j === i ? { ...x, text_ar: e.target.value } : x)))} />
            <Select aria-label={t("controlLevel")} value={c.control_level} onChange={(e) => setControls(controls.map((x, j) => (j === i ? { ...x, control_level: e.target.value as S["ControlLevel"] } : x)))} data-testid="as-control-level">
              {CONTROL_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {te(`controlLevel.${l}`)}
                </option>
              ))}
            </Select>
            <Button type="button" variant="ghost" className="min-h-touch" aria-label={t("remove")} onClick={() => setControls(controls.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-fit" onClick={() => setControls([...controls, { text_en: "", text_ar: "", control_level: "engineering" }])} data-testid="as-add-control">
          <Plus aria-hidden />
          {t("addControl")}
        </Button>
      </fieldset>
      <fieldset className="flex flex-col gap-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("links")}</legend>
        {links.map((l, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
            <Select aria-label={t("point")} value={l.point_id ?? ""} onChange={(e) => setLinks(links.map((x, j) => (j === i ? { ...x, point_id: e.target.value || null } : x)))} data-testid="as-link-point">
              <option value="">{t("noPoint")}</option>
              {(points.data?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.point_code}
                </option>
              ))}
            </Select>
            <Select aria-label={t("parameter")} value={l.parameter ?? ""} onChange={(e) => setLinks(links.map((x, j) => (j === i ? { ...x, parameter: (e.target.value || null) as S["Parameter"] | null } : x)))} data-testid="as-link-parameter">
              <option value="">—</option>
              {ref.options("parameters").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Input aria-label={t("templateCode")} placeholder={t("templateCode")} className="ltr" value={l.template_code ?? ""} onChange={(e) => setLinks(links.map((x, j) => (j === i ? { ...x, template_code: e.target.value.toUpperCase() || null } : x)))} />
            <Button type="button" variant="ghost" className="min-h-touch" aria-label={t("remove")} onClick={() => setLinks(links.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-fit" onClick={() => setLinks([...links, { point_id: null, parameter: null, template_code: null }])} data-testid="as-add-link">
          <Plus aria-hidden />
          {t("addLink")}
        </Button>
      </fieldset>
      <NoNamesHint />
    </StepDialog>
  );
}

export function AspectPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <AspectDetail project={p} id={id} />}</ProjectGate>;
}

function AspectDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.aspects");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const refs = useRefLists();
  const bi = useBi();
  const opts = useProjectOptions(project.id);
  const points = useEnvPoints(project.id, { enabled: caps.view });
  const refresh = useEnvRefresh();
  const q = useAspect(id, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "edit" | "activate" | "review" | "archive">("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data;
  if (!a) return <NotFoundState />;
  const pointCode = (pid: string | null | undefined) => (points.data?.items ?? []).find((p) => p.id === pid)?.point_code ?? "—";
  const transition = async (action: S["AspectAction"], reason?: string) => {
    await unwrap(api.POST("/api/v1/env-aspects/{aspect_id}/transitions", { params: { path: { aspect_id: a.id } }, body: { action, reason: reason ?? null } }));
    await refresh();
  };
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/env-aspects" }, { label: a.aspect_no }]} />
      <PageHeader
        title={<Code>{a.aspect_no}</Code>}
        badge={<EnvStatusBadge group="envAspectStatus" status={a.status} />}
        actions={
          caps.aspects && a.status !== "archived" ? (
            <>
              <Button variant="outline" onClick={() => setDialog("edit")} data-testid="aspect-edit">
                {tc("edit")}
              </Button>
              {a.status === "draft" ? (
                <Button onClick={() => setDialog("activate")} data-testid="aspect-activate">
                  {t("activate")}
                </Button>
              ) : (
                <Button onClick={() => setDialog("review")} data-testid="aspect-review">
                  <RefreshCcw aria-hidden />
                  {t("markReviewed")}
                </Button>
              )}
            </>
          ) : null
        }
      />
      {a.review_flag ? (
        <Alert tone="warning" className="mb-4" data-testid="review-flag">
          {t("reviewFlagHint")}
        </Alert>
      ) : null}
      <Card className="mb-4">
        <CardContent className="pt-4">
          <FieldList>
            <FieldItem label={t("activity")}>{refs.label("activity", a.activity)}</FieldItem>
            <FieldItem label={t("aspect")}>{ref.label("aspects", a.aspect)}</FieldItem>
            <FieldItem label={t("impact")}>{ref.label("impacts", a.impact)}</FieldItem>
            <FieldItem label={t("condition")}>{ref.label("condition", a.condition)}</FieldItem>
            <FieldItem label={t("sites")}>{a.site_ids.map((s) => opts.sites.find((x) => x.value === s)?.code ?? "—").join(", ")}</FieldItem>
            <FieldItem label={t("contractors")}>{a.engagement_ids.length ? a.engagement_ids.map((e) => opts.engagements.find((x) => x.value === e)?.code ?? "—").join(", ") : t("anyContractor")}</FieldItem>
            <FieldItem label={t("score")}>
              <span data-testid="aspect-score" className="tabular-nums">
                {a.severity} × {a.likelihood} = {a.score}
              </span>{" "}
              {a.significant ? (
                <Badge tone="warning" data-testid="significant">
                  {t("sigYes")}
                </Badge>
              ) : (
                <span className="text-muted-foreground">{t("sigNo")}</span>
              )}
            </FieldItem>
            <FieldItem label={t("legal")}>
              <YesNo value={a.legal_requirement} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("stakeholder")}>
              <YesNo value={a.stakeholder_concern} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("activatedOn")}>
              <StackedDate v={a.activated_on} projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("reviewDue")}>
              <span data-testid="review-due">
                <StackedDate v={a.review_due_on} projectId={project.id} />
              </span>
            </FieldItem>
            {a.status_reason ? (
              <FieldItem label={t("reason")} wide>
                <span dir="auto">{a.status_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("controls")}</CardTitle>
          </CardHeader>
          <CardContent>
            {a.controls.length ? (
              <ul className="flex flex-col gap-2" data-testid="aspect-controls">
                {a.controls.map((c, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge tone={c.control_level === "ppe" ? "warning" : "info"}>{te(`controlLevel.${c.control_level}`)}</Badge>
                    <span dir="auto">{bi(c.text_en, c.text_ar)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noControls")} />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("links")}</CardTitle>
          </CardHeader>
          <CardContent>
            {a.monitoring_links.length ? (
              <ul className="flex flex-col gap-2 text-sm" data-testid="aspect-links">
                {a.monitoring_links.map((l, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    {l.point_id ? (
                      <Link href={`/env-points/${l.point_id}`} className="text-primary hover:underline">
                        <Code>{pointCode(l.point_id)}</Code>
                      </Link>
                    ) : null}
                    {l.parameter ? <span>{ref.label("parameters", l.parameter)}</span> : null}
                    {l.template_code ? <Code>{l.template_code}</Code> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noLinks")} />
            )}
          </CardContent>
        </Card>
      </div>
      {caps.aspects && a.status !== "archived" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setDialog("archive")} data-testid="aspect-archive">
            {t("archive")}
          </Button>
        </RecordActions>
      ) : null}
      {dialog === "edit" ? <AspectForm project={project} aspect={a} onClose={() => setDialog("")} /> : null}
      {dialog === "activate" || dialog === "review" ? (
        <StepDialog
          title={dialog === "activate" ? t("activateTitle") : t("reviewTitle")}
          description={dialog === "activate" ? t("activateHint") : t("reviewHint")}
          confirmLabel={dialog === "activate" ? t("activate") : t("markReviewed")}
          testId="aspect-confirm"
          onConfirm={() => transition(dialog)}
          onClose={() => setDialog("")}
        />
      ) : null}
      {dialog === "archive" ? <EnvReasonDialog title={t("archiveTitle", { no: a.aspect_no })} confirmLabel={t("archive")} onConfirm={(r) => transition("archive", r)} onClose={() => setDialog("")} /> : null}
    </div>
  );
}

/* ═════════════ permits and licences (§3.3, §4.2, PRM-1…PRM-5) ═════════════ */

const PROJECT_TYPES: S["EnvPermitType"][] = [
  "ncec_env_permit_construction",
  "ncec_env_permit_operation",
  "eia_approval",
  "mwan_producer_registration",
  "municipal_construction_permit",
  "dewatering_discharge_permit",
  "sewer_discharge_permit",
  "cemp_approval",
  "other",
];
const PROVIDER_TYPES: S["EnvPermitType"][] = ["mwan_licence", "facility_authorisation", "lab_accreditation", "other"];

export function PermitStatusBadge({ p }: { p: Pick<S["EnvPermitRead"], "status" | "days_to_expiry"> }) {
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <EnvStatusBadge group="envPermitStatus" status={p.status} testId="permit-status" />
      {p.status === "valid" || p.status === "expiring" ? <DaysLeft days={p.days_to_expiry} /> : null}
    </span>
  );
}

export function EnvPermitsPage() {
  return <ProjectGate>{(p) => <Permits project={p} />}</ProjectGate>;
}

function Permits({ project }: { project: Project }) {
  const t = useTranslations("env.permits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["EnvPermitStatus"] | "";
  const q = useEnvPermits(project.id, { status: status ? [status] : null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  const [creating, setCreating] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.permits ? (
            <Button onClick={() => setCreating(true)} data-testid="permit-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EnvPermitSubNav />
      <ListToolbar>
        <SelectFilter id="pm-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={PERMIT_STATUSES.map((x) => ({ value: x, label: te(`envPermitStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="permits-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("requirement")}</TH>
                <TH>{t("reference")}</TH>
                <TH>{t("validTo")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="permit-row" data-no={p.record_no} data-status={p.status}>
                  <TD label={t("no")}>
                    <Link href={`/env-permits/${p.id}`} className="font-medium text-primary hover:underline">
                      <Code>{p.record_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("type")}>
                    {ref.label("permit_types", p.permit_type)}
                    <span className="block text-xs text-muted-foreground">{ref.label("issuers", p.issuer)}</span>
                  </TD>
                  <TD label={t("requirement")}>
                    {p.requirement_code ? <Code>{p.requirement_code}</Code> : "—"}
                    {p.required ? <span className="block text-xs text-muted-foreground">{t("required")}</span> : null}
                  </TD>
                  <TD label={t("reference")}>{p.reference_no ? <Code>{p.reference_no}</Code> : "—"}</TD>
                  <TD label={t("validTo")}>{p.valid_to ? <StackedDate v={p.valid_to} projectId={project.id} /> : <span className="text-muted-foreground">{t("noExpiry")}</span>}</TD>
                  <TD label={tc("status")}>
                    <PermitStatusBadge p={p} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status ? undefined : t("empty")} />
      )}
      {creating ? <PermitForm project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

/** Create / edit / renew a project permit, or add a provider licence (one form, PRM-1, PRV-2). */
function PermitForm({
  project,
  provider,
  permit,
  renew,
  onClose,
}: {
  project: Project;
  provider?: S["EnvProviderRead"];
  permit?: S["EnvPermitRead"];
  renew?: S["EnvPermitRead"];
  onClose: () => void;
}) {
  const t = useTranslations("env.permits");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const points = useEnvPoints(project.id, { enabled: !provider });
  const base = permit ?? renew;
  const [v, setV] = useState({
    permit_type: base?.permit_type ?? (provider ? "mwan_licence" : "ncec_env_permit_construction"),
    issuer: base?.issuer ?? (provider ? "mwan" : "ncec"),
    requirement_code: base?.requirement_code ?? "",
    required: base?.required ?? !provider,
    reference_no: permit?.reference_no ?? "",
    valid_from: permit?.valid_from ?? "",
    valid_to: permit?.valid_to ?? "",
    applies_from: base?.applies_from ?? "",
    applies_to: base?.applies_to ?? "",
    pending: false,
    activities: (base?.scope.activities ?? []) as string[],
    classes: (base?.scope.waste_classes ?? []) as string[],
    facility_code: base?.scope.facility_code ?? "",
  });
  const [conds, setConds] = useState<S["PermitCondition-Input"][]>((base?.conditions ?? []).map((c) => ({ ...c })));
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const types = provider ? PROVIDER_TYPES : PROJECT_TYPES;
  const scope: S["PermitScope"] = provider ? { activities: v.activities as S["LicenceActivity"][], waste_classes: v.classes as S["WasteClass"][], facility_code: v.facility_code || null } : (base?.scope ?? {});
  return (
    <StepDialog
      wide
      title={permit ? t("editTitle", { no: permit.record_no }) : renew ? t("renewTitle", { no: renew.record_no }) : provider ? t("newLicence", { code: provider.provider_code }) : t("new")}
      confirmLabel={tc("save")}
      testId="permit-save"
      onConfirm={async () => {
        const conditions = conds.filter((c) => c.code.trim() && c.text_en.trim()).map((c) => ({ ...c, limit_value: c.limit_value === "" ? null : c.limit_value }));
        if (permit) {
          await unwrap(
            api.PATCH("/api/v1/env-permits/{permit_id}", {
              params: { path: { permit_id: permit.id } },
              body: { reference_no: v.reference_no || null, valid_from: v.valid_from || null, valid_to: v.valid_to || null, applies_from: v.applies_from || null, applies_to: v.applies_to || null, required: v.required, conditions, scope },
            }),
          );
        } else {
          const body: S["EnvPermitCreate"] = {
            permit_type: v.permit_type as S["EnvPermitType"],
            issuer: v.issuer as S["Issuer"],
            requirement_code: v.requirement_code || null,
            required: v.required,
            applies_from: v.applies_from || null,
            applies_to: v.applies_to || null,
            reference_no: v.reference_no || null,
            valid_from: v.valid_from || null,
            valid_to: v.valid_to || null,
            pending: v.pending,
            scope,
            conditions,
            supersedes_id: renew?.id ?? null,
          };
          if (provider) await unwrap(api.POST("/api/v1/env-providers/{provider_id}/licences", { params: { path: { provider_id: provider.id } }, body }));
          else await unwrap(api.POST("/api/v1/projects/{project_id}/env-permits", { params: { path: { project_id: project.id } }, body }));
        }
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="pm-type" label={t("type")} required>
          <Select value={v.permit_type} disabled={Boolean(base)} onChange={(e) => set({ permit_type: e.target.value as S["EnvPermitType"] })} data-testid="pm-type">
            {types.map((x) => (
              <option key={x} value={x}>
                {ref.label("permit_types", x)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pm-issuer" label={t("issuer")} required>
          <Select value={v.issuer} disabled={Boolean(base)} onChange={(e) => set({ issuer: e.target.value as S["Issuer"] })} data-testid="pm-issuer">
            {ref.options("issuers").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        {!provider ? (
          <>
            <FormField id="pm-req" label={t("requirement")} hint={t("requirementHint")}>
              <Input className="ltr" maxLength={20} disabled={Boolean(base)} value={v.requirement_code} onChange={(e) => set({ requirement_code: e.target.value.toUpperCase() })} data-testid="pm-requirement" />
            </FormField>
            <Check id="pm-required" label={t("requiredHint")} checked={v.required} onChange={(c) => set({ required: c })} />
          </>
        ) : null}
        {!permit ? <Check id="pm-pending" label={t("pending")} checked={v.pending} onChange={(c) => set({ pending: c })} testId="pm-pending" /> : null}
        <FormField id="pm-ref" label={t("reference")} required={!v.pending}>
          <Input className="ltr" maxLength={40} value={v.reference_no} onChange={(e) => set({ reference_no: e.target.value })} data-testid="pm-reference" />
        </FormField>
        <FormField id="pm-from" label={t("validFrom")}>
          <Input type="date" value={v.valid_from} onChange={(e) => set({ valid_from: e.target.value })} data-testid="pm-valid-from" />
        </FormField>
        <FormField id="pm-to" label={t("validTo")} hint={t("validToHint")}>
          <Input type="date" value={v.valid_to} onChange={(e) => set({ valid_to: e.target.value })} data-testid="pm-valid-to" />
        </FormField>
        {!provider ? (
          <>
            <FormField id="pm-af" label={t("appliesFrom")}>
              <Input type="date" value={v.applies_from} onChange={(e) => set({ applies_from: e.target.value })} />
            </FormField>
            <FormField id="pm-at" label={t("appliesTo")} hint={t("appliesHint")}>
              <Input type="date" value={v.applies_to} onChange={(e) => set({ applies_to: e.target.value })} />
            </FormField>
          </>
        ) : (
          <>
            <MultiSelect id="pm-acts" label={t("activities")} options={ref.options("licence_activities")} value={v.activities} onChange={(x) => set({ activities: x })} allLabel={tc("select")} testId="pm-activities" />
            <MultiSelect id="pm-classes" label={t("classes")} options={WASTE_CLASSES.map((c) => ({ value: c, label: ref.label("waste_classes", c) }))} value={v.classes} onChange={(x) => set({ classes: x })} allLabel={tc("select")} testId="pm-classes" />
            <FormField id="pm-fac" label={t("facility")}>
              <Select value={v.facility_code} onChange={(e) => set({ facility_code: e.target.value })}>
                <option value="">{t("allFacilities")}</option>
                {provider.facilities.map((f) => (
                  <option key={f.facility_code} value={f.facility_code}>
                    {f.facility_code}
                  </option>
                ))}
              </Select>
            </FormField>
          </>
        )}
      </div>
      {!provider ? (
        <fieldset className="flex flex-col gap-2 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium">{t("conditions")}</legend>
          <p className="text-xs text-muted-foreground">{t("conditionsHint")}</p>
          {conds.map((c, i) => {
            const up = (p: Partial<S["PermitCondition-Input"]>) => setConds(conds.map((x, j) => (j === i ? { ...x, ...p } : x)));
            return (
              <div key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-6">
                <Input aria-label={t("condCode")} placeholder={t("condCode")} className="ltr" value={c.code} onChange={(e) => up({ code: e.target.value })} />
                <Input aria-label={t("condText")} placeholder={t("condText")} className="sm:col-span-2" value={c.text_en} onChange={(e) => up({ text_en: e.target.value })} />
                <Select aria-label={t("point")} value={c.point_id ?? ""} onChange={(e) => up({ point_id: e.target.value || null })}>
                  <option value="">{t("noPoint")}</option>
                  {(points.data?.items ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.point_code}
                    </option>
                  ))}
                </Select>
                <Select aria-label={t("parameter")} value={c.parameter ?? ""} onChange={(e) => up({ parameter: (e.target.value || null) as S["Parameter"] | null })}>
                  <option value="">—</option>
                  {ref.options("parameters").map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
                <div className="flex gap-1">
                  <DecimalInput placeholder={t("limit")} value={String(c.limit_value ?? "")} onChange={(x) => up({ limit_value: x })} />
                  <Button type="button" variant="ghost" className="min-h-touch" aria-label={t("remove")} onClick={() => setConds(conds.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              </div>
            );
          })}
          <Button type="button" variant="outline" className="w-fit" onClick={() => setConds([...conds, { code: "", text_en: "", text_ar: "" }])}>
            <Plus aria-hidden />
            {t("addCondition")}
          </Button>
        </fieldset>
      ) : null}
    </StepDialog>
  );
}

export function EnvPermitPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <PermitDetail project={p} id={id} />}</ProjectGate>;
}

function PermitDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.permits");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const bi = useBi();
  const refresh = useEnvRefresh();
  const q = useEnvPermit(id, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "edit" | "renew" | "suspend" | "cancel" | "reinstate">("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return <NotFoundState />;
  const transition = async (action: S["EnvPermitAction"], reason?: string) => {
    await unwrap(api.POST("/api/v1/env-permits/{permit_id}/transitions", { params: { path: { permit_id: p.id } }, body: { action, reason: reason ?? null } }));
    await refresh();
  };
  const live = !["cancelled", "superseded"].includes(p.status);
  return (
    <div>
      <Breadcrumbs items={[{ label: p.provider_id ? t("providerLicences") : t("title"), href: p.provider_id ? `/env-providers/${p.provider_id}` : "/env-permits" }, { label: p.record_no }]} />
      <PageHeader
        title={<Code>{p.record_no}</Code>}
        description={ref.label("permit_types", p.permit_type)}
        badge={<PermitStatusBadge p={p} />}
        actions={
          caps.permits && live ? (
            <>
              <Button variant="outline" onClick={() => setDialog("edit")} data-testid="permit-edit">
                {tc("edit")}
              </Button>
              {p.project_id && p.requirement_code ? (
                <Button onClick={() => setDialog("renew")} data-testid="permit-renew">
                  <RefreshCcw aria-hidden />
                  {t("renew")}
                </Button>
              ) : null}
              {p.status === "suspended" ? (
                <Button variant="outline" onClick={() => setDialog("reinstate")} data-testid="permit-reinstate">
                  {t("reinstate")}
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <Card className="mb-4">
        <CardContent className="pt-4">
          <FieldList>
            <FieldItem label={t("issuer")}>{ref.label("issuers", p.issuer)}</FieldItem>
            <FieldItem label={t("reference")}>{p.reference_no ? <Code>{p.reference_no}</Code> : "—"}</FieldItem>
            <FieldItem label={t("requirement")}>
              {p.requirement_code ? <Code>{p.requirement_code}</Code> : "—"} {p.required ? `· ${t("required")}` : ""}
            </FieldItem>
            <FieldItem label={t("validFrom")}>
              <StackedDate v={p.valid_from} projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("validTo")}>{p.valid_to ? <StackedDate v={p.valid_to} projectId={project.id} /> : t("noExpiry")}</FieldItem>
            <FieldItem label={t("applies")}>
              {p.applies_from || p.applies_to ? (
                <span className="inline-flex flex-wrap gap-1">
                  <StackedDate v={p.applies_from} projectId={project.id} /> – <StackedDate v={p.applies_to} projectId={project.id} />
                </span>
              ) : (
                t("projectLife")
              )}
            </FieldItem>
            {p.scope.activities?.length || p.scope.waste_classes?.length ? (
              <FieldItem label={t("scope")} wide>
                {(p.scope.activities ?? []).map((a) => ref.label("licence_activities", a)).join(", ")} · {(p.scope.waste_classes ?? []).map((c) => ref.label("waste_classes", c)).join(", ")}
                {p.scope.facility_code ? (
                  <>
                    {" "}
                    · <Code>{p.scope.facility_code}</Code>
                  </>
                ) : null}
              </FieldItem>
            ) : null}
            {p.status_reason ? (
              <FieldItem label={t("reason")} wide>
                <span dir="auto">{p.status_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {p.conditions.length ? (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">{t("conditions")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm" data-testid="permit-conditions">
              {p.conditions.map((c) => (
                <li key={c.code} className="flex flex-wrap items-center gap-2">
                  <Code>{c.code}</Code>
                  <span dir="auto">{bi(c.text_en, c.text_ar)}</span>
                  {c.parameter && c.limit_value ? (
                    <Badge tone="info">
                      {ref.label("parameters", c.parameter)} ≤ <bdi className="ltr">{c.limit_value}</bdi>
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("document")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Attachments ownerType="env_permit_document" ownerId={p.id} canUpload={caps.permits && live} canDelete={caps.permits && live} hint={t("documentHint")} />
        </CardContent>
      </Card>
      {caps.permits && live && p.status !== "suspended" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setDialog("suspend")} data-testid="permit-suspend">
            {t("suspend")}
          </Button>
          <Button variant="destructive-outline" onClick={() => setDialog("cancel")} data-testid="permit-cancel">
            {t("cancel")}
          </Button>
        </RecordActions>
      ) : null}
      {dialog === "edit" ? <PermitForm project={project} permit={p} onClose={() => setDialog("")} /> : null}
      {dialog === "renew" ? <PermitForm project={project} renew={p} onClose={() => setDialog("")} /> : null}
      {dialog === "suspend" || dialog === "cancel" ? (
        <EnvReasonDialog title={t(dialog === "suspend" ? "suspendTitle" : "cancelTitle", { no: p.record_no })} confirmLabel={t(dialog)} onConfirm={(r) => transition(dialog, r)} onClose={() => setDialog("")} />
      ) : null}
      {dialog === "reinstate" ? <StepDialog title={t("reinstate")} confirmLabel={t("reinstate")} onConfirm={() => transition("reinstate")} onClose={() => setDialog("")} /> : null}
    </div>
  );
}

/* ═════════════ providers (org-wide; transporters, facilities, labs; PRV-1, PRV-2) ═════════════ */

export function EnvProvidersPage() {
  return <ProjectGate>{(p) => <Providers project={p} />}</ProjectGate>;
}

function Providers({ project }: { project: Project }) {
  const t = useTranslations("env.providers");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const bi = useBi();
  const s = useSearchState();
  const kind = (s.get("kind") ?? "") as S["ProviderKind"] | "";
  const q = useEnvProviders({ kind: kind || null }, { enabled: caps.view });
  const [creating, setCreating] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.permits ? (
            <Button onClick={() => setCreating(true)} data-testid="provider-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EnvPermitSubNav />
      <ListToolbar>
        <SelectFilter id="pv-kind" label={t("kind")} value={kind} onChange={(v) => s.set({ kind: v })} options={ref.options("provider_kinds")} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="providers-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("name")}</TH>
              <TH>{t("kind")}</TH>
              <TH>{t("licence")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((p) => {
              const lic = (p.licences ?? []).filter((l) => l.status !== "superseded" && l.status !== "cancelled");
              const next = lic.slice().sort((a, b) => (a.valid_to ?? "9999").localeCompare(b.valid_to ?? "9999"))[0];
              return (
                <TR key={p.id} data-testid="provider-row" data-code={p.provider_code}>
                  <TD label={t("code")}>
                    <Link href={`/env-providers/${p.id}`} className="font-medium text-primary hover:underline">
                      <Code>{p.provider_code}</Code>
                    </Link>
                  </TD>
                  <TD label={t("name")}>{bi(p.name_en, p.name_ar)}</TD>
                  <TD label={t("kind")}>{p.kinds.map((k) => ref.label("provider_kinds", k)).join(", ")}</TD>
                  <TD label={t("licence")}>{next ? <PermitStatusBadge p={next} /> : <span className="text-muted-foreground">{t("noLicence")}</span>}</TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envProviderStatus" status={p.status} />
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={kind ? undefined : t("empty")} />
      )}
      {creating ? <ProviderForm onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function ProviderForm({ onClose }: { onClose: () => void }) {
  const t = useTranslations("env.providers");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const [v, setV] = useState({ provider_code: "", name_en: "", name_ar: "", cr_number: "", contact_email: "", phone: "" });
  const [kinds, setKinds] = useState<S["ProviderKind"][]>([]);
  const [facilities, setFacilities] = useState<S["Facility"][]>([]);
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  return (
    <StepDialog
      wide
      title={t("new")}
      confirmLabel={tc("save")}
      testId="provider-save"
      disabled={!v.provider_code || !v.name_en || !v.name_ar || !/^\d{10}$/.test(v.cr_number) || !kinds.length}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/env-providers", {
            body: { ...v, contact_email: v.contact_email || null, phone: v.phone || null, kinds, facilities: facilities.filter((f) => f.facility_code && f.name_en) },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="pv-code" label={t("code")} required hint="A–Z, 0–9, -">
          <Input className="ltr" maxLength={12} value={v.provider_code} onChange={(e) => set({ provider_code: e.target.value.toUpperCase() })} data-testid="pv-code" />
        </FormField>
        <FormField id="pv-cr" label={t("cr")} required hint={t("crHint")}>
          <Input className="ltr" inputMode="numeric" maxLength={10} value={v.cr_number} onChange={(e) => set({ cr_number: e.target.value.replace(/\D/g, "") })} data-testid="pv-cr" />
        </FormField>
        <FormField id="pv-en" label={t("nameEn")} required>
          <Input value={v.name_en} onChange={(e) => set({ name_en: e.target.value })} data-testid="pv-name-en" />
        </FormField>
        <FormField id="pv-ar" label={t("nameAr")} required>
          <Input dir="rtl" value={v.name_ar} onChange={(e) => set({ name_ar: e.target.value })} data-testid="pv-name-ar" />
        </FormField>
        <MultiSelect id="pv-kinds" label={t("kind")} options={ref.options("provider_kinds") as { value: S["ProviderKind"]; label: string }[]} value={kinds} onChange={setKinds} allLabel={tc("select")} testId="pv-kinds" />
        <FormField id="pv-email" label={t("email")} hint={t("orgContact")}>
          <Input type="email" className="ltr" value={v.contact_email} onChange={(e) => set({ contact_email: e.target.value })} />
        </FormField>
      </div>
      <fieldset className="flex flex-col gap-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("facilities")}</legend>
        <p className="text-xs text-muted-foreground">{t("facilitiesHint")}</p>
        {facilities.map((f, i) => {
          const up = (p: Partial<S["Facility"]>) => setFacilities(facilities.map((x, j) => (j === i ? { ...x, ...p } : x)));
          return (
            <div key={i} className="grid gap-2 sm:grid-cols-[8rem_1fr_8rem_10rem_auto]">
              <Input aria-label={t("facilityCode")} placeholder={t("facilityCode")} className="ltr" value={f.facility_code} onChange={(e) => up({ facility_code: e.target.value.toUpperCase() })} />
              <Input aria-label={t("nameEn")} placeholder={t("nameEn")} value={f.name_en} onChange={(e) => up({ name_en: e.target.value })} />
              <Input aria-label={t("city")} placeholder={t("city")} value={f.city ?? ""} onChange={(e) => up({ city: e.target.value })} />
              <Select aria-label={t("kind")} value={f.kind} onChange={(e) => up({ kind: e.target.value as S["ProviderKind"] })}>
                {ref.options("provider_kinds").map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
              <Button type="button" variant="ghost" className="min-h-touch" aria-label={t("remove")} onClick={() => setFacilities(facilities.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden />
              </Button>
            </div>
          );
        })}
        <Button type="button" variant="outline" className="w-fit" onClick={() => setFacilities([...facilities, { facility_code: "", name_en: "", name_ar: "", city: "", kind: kinds[0] ?? "recycler" }])}>
          <Plus aria-hidden />
          {t("addFacility")}
        </Button>
      </fieldset>
    </StepDialog>
  );
}

export function EnvProviderPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <ProviderDetail project={p} id={id} />}</ProjectGate>;
}

function ProviderDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.providers");
  const tp = useTranslations("env.permits");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const bi = useBi();
  const locale = useLocale();
  const refresh = useEnvRefresh();
  const q = useEnvProvider(id, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "licence" | S["ProviderAction"]>("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return <NotFoundState />;
  const transition = async (action: S["ProviderAction"], reason?: string) => {
    await unwrap(api.POST("/api/v1/env-providers/{provider_id}/transitions", { params: { path: { provider_id: p.id } }, body: { action, reason: reason ?? null } }));
    await refresh();
  };
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/env-providers" }, { label: p.provider_code }]} />
      <PageHeader
        title={bi(p.name_en, p.name_ar)}
        description={<Code>{p.provider_code}</Code>}
        badge={<EnvStatusBadge group="envProviderStatus" status={p.status} />}
        actions={
          caps.permits ? (
            <Button onClick={() => setDialog("licence")} data-testid="licence-new">
              <Plus aria-hidden />
              {t("addLicence")}
            </Button>
          ) : null
        }
      />
      <Card className="mb-4">
        <CardContent className="pt-4">
          <FieldList>
            <FieldItem label={t("kind")}>{p.kinds.map((k) => ref.label("provider_kinds", k)).join(", ")}</FieldItem>
            <FieldItem label={t("cr")}>
              <Code>{p.cr_number}</Code>
            </FieldItem>
            <FieldItem label={t("email")}>{p.contact_email ? <bdi className="ltr">{p.contact_email}</bdi> : "—"}</FieldItem>
            {p.status_reason ? (
              <FieldItem label={tp("reason")} wide>
                <span dir="auto">{p.status_reason}</span>
              </FieldItem>
            ) : null}
            {p.facilities.length ? (
              <FieldItem label={t("facilities")} wide>
                <ul className="flex flex-col gap-1">
                  {p.facilities.map((f) => (
                    <li key={f.facility_code}>
                      <Code>{f.facility_code}</Code> {locale === "ar" && f.name_ar ? f.name_ar : f.name_en}
                      {f.city ? ` · ${f.city}` : ""} · {ref.label("provider_kinds", f.kind)}
                    </li>
                  ))}
                </ul>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("licences")}</CardTitle>
        </CardHeader>
        <CardContent>
          {p.licences?.length ? (
            <Table data-testid="licences-table">
              <THead>
                <TR>
                  <TH>{tp("no")}</TH>
                  <TH>{tp("type")}</TH>
                  <TH>{tp("reference")}</TH>
                  <TH>{tp("scope")}</TH>
                  <TH>{tp("validTo")}</TH>
                  <TH>{tc("status")}</TH>
                </TR>
              </THead>
              <TBody>
                {p.licences.map((l) => (
                  <TR key={l.id} data-testid="licence-row" data-status={l.status}>
                    <TD label={tp("no")}>
                      <Link href={`/env-permits/${l.id}`} className="text-primary hover:underline">
                        <Code>{l.record_no}</Code>
                      </Link>
                    </TD>
                    <TD label={tp("type")}>{ref.label("permit_types", l.permit_type)}</TD>
                    <TD label={tp("reference")}>{l.reference_no ? <Code>{l.reference_no}</Code> : "—"}</TD>
                    <TD label={tp("scope")}>
                      <span className="text-xs">
                        {(l.scope.activities ?? []).map((a) => ref.label("licence_activities", a)).join(", ")}
                        <span className="block text-muted-foreground">{(l.scope.waste_classes ?? []).map((c) => ref.label("waste_classes", c)).join(", ")}</span>
                      </span>
                    </TD>
                    <TD label={tp("validTo")}>
                      <StackedDate v={l.valid_to} projectId={project.id} />
                    </TD>
                    <TD label={tc("status")}>
                      <PermitStatusBadge p={l} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState message={t("noLicence")} />
          )}
        </CardContent>
      </Card>
      {caps.settings ? (
        <RecordActions>
          {p.status !== "approved" ? (
            <Button variant="outline" onClick={() => setDialog("approve")} data-testid="provider-approve">
              {t("approve")}
            </Button>
          ) : null}
          {p.status === "approved" ? (
            <Button variant="destructive-outline" onClick={() => setDialog("suspend")} data-testid="provider-suspend">
              {t("suspend")}
            </Button>
          ) : null}
          {p.status !== "blacklisted" ? (
            <Button variant="destructive-outline" onClick={() => setDialog("blacklist")} data-testid="provider-blacklist">
              {t("blacklist")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
      {dialog === "licence" ? <PermitForm project={project} provider={p} onClose={() => setDialog("")} /> : null}
      {dialog === "approve" ? <StepDialog title={t("approve")} confirmLabel={t("approve")} onConfirm={() => transition("approve")} onClose={() => setDialog("")} /> : null}
      {dialog === "suspend" || dialog === "blacklist" ? (
        <EnvReasonDialog title={t(dialog === "suspend" ? "suspendTitle" : "blacklistTitle", { code: p.provider_code })} confirmLabel={t(dialog)} onConfirm={(r) => transition(dialog, r)} onClose={() => setDialog("")} />
      ) : null}
    </div>
  );
}
