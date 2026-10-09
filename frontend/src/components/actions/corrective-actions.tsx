"use client";
import { AlertTriangle, CalendarPlus, Pencil, Plus } from "lucide-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
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
import { ApiWarnings, PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { LinkFilterNote } from "@/components/common/link-filter-note";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useCorrectiveAction, useCorrectiveActions } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { CA_PRIORITIES, CA_SOURCE_TYPES, CA_STATUSES, CONTROL_LEVELS, OVERDUE_BUCKETS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { entityRoute } from "@/lib/routes";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { StackedDate } from "@/components/medical/common";

const PAGE_SIZE = 50;
type CaStatus = Schemas["CaStatus"];

export function CaList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("ca");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const show = useDisplay(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as CaStatus[];
  const prio = s.getAll("priority") as Schemas["CaPriority"][];
  const cl = s.getAll("control_level") as Schemas["ControlLevel"][];
  const sites = s.getAll("site_id");
  const engs = s.getAll("engagement_id");
  const bucket = (s.get("overdue_bucket") ?? "") as Schemas["OverdueBucket"] | "";
  const source = (s.get("source_type") ?? "") as Schemas["CaSourceType"] | "";
  const q = {
    status: status.length ? status : null,
    overdue: s.getBool("overdue") ?? null,
    overdue_bucket: bucket || null,
    verification_overdue: s.getBool("verification_overdue") ?? null,
    priority: prio.length ? prio : null,
    control_level: cl.length ? cl : null,
    source_type: source || null,
    source_id: s.get("source_id") || null,
    site_id: sites.length ? sites : null,
    engagement_id: engs.length ? engs : null,
    include_subcontractors: s.getBool("include_subcontractors") ?? true,
    owner_is_me: s.getBool("owner_is_me") ?? false,
    verifier_is_me: s.getBool("verifier_is_me") ?? false,
    due_from: s.get("due_from") || null,
    due_to: s.get("due_to") || null,
    as_of: s.get("as_of") || null,
    q: s.get("q") || null,
    sort: "due_date" as const,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useCorrectiveActions(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "ca.create", project.id) ? (
            <Button asChild>
              <Link href="/actions/new?source_type=other" data-testid="new-ca">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <LinkFilterNote keys={["verification_overdue", "source_id", "as_of", "overdue"]} />
      <ListToolbar actions={can(me, "export.lists", project.id) ? <ExportButtons dataset="corrective_actions" params={{ project_id: project.id, status: status.join(",") || null }} /> : null}>
        <SearchFilter id="ca-q" placeholder={tc("search")} value={q.q ?? ""} onChange={(v) => s.set({ q: v })} />
        <MultiSelect id="ca-status" label={t("fields.status")} options={CA_STATUSES.map((x) => ({ value: x, label: te(`caStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} testId="ca-status-filter" />
        <MultiSelect id="ca-prio" label={t("fields.priority")} options={CA_PRIORITIES.map((x) => ({ value: x, label: te(`caPriority.${x}`) }))} value={prio} onChange={(v) => s.set({ priority: v })} />
        <MultiSelect id="ca-cl" label={t("fields.control_level")} options={CONTROL_LEVELS.map((x) => ({ value: x, label: te(`controlLevel.${x}`) }))} value={cl} onChange={(v) => s.set({ control_level: v })} />
        <SelectFilter id="ca-bucket" label={t("overdue")} value={bucket} onChange={(v) => s.set({ overdue_bucket: v })} options={OVERDUE_BUCKETS.map((x) => ({ value: x, label: te(`overdueBucket.${x}`) }))} />
        <SelectFilter id="ca-source" label={t("fields.source")} value={source} onChange={(v) => s.set({ source_type: v })} options={CA_SOURCE_TYPES.map((x) => ({ value: x, label: te(`caSource.${x}`) }))} />
        <MultiSelect id="ca-site" label={tc("site")} options={opts.sites} value={sites} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="ca-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="ca-due-to">{t("fields.due_date")}</Label>
          <Input id="ca-due-to" type="date" value={q.due_to ?? ""} onChange={(e) => s.set({ due_to: e.target.value })} />
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={q.owner_is_me} onChange={(e) => s.set({ owner_is_me: e.target.checked ? "true" : null })} data-testid="owner-is-me" />
          {t("ownerIsMe")}
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={q.verifier_is_me} onChange={(e) => s.set({ verifier_is_me: e.target.checked ? "true" : null })} />
          {t("verifierIsMe")}
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="ca-table">
            <THead>
              <TR>
                <TH>{t("fields.ref")}</TH>
                <TH>{t("fields.title")}</TH>
                <TH>{t("fields.source")}</TH>
                <TH>{t("fields.priority")}</TH>
                <TH>{t("fields.control_level")}</TH>
                <TH>{t("fields.owner")}</TH>
                <TH>{t("fields.engagement")}</TH>
                <TH>{t("fields.due_date")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="ca-row" data-ref={c.ref}>
                  <TD label={t("fields.ref")}>
                    <Link href={`/actions/${c.id}`} className="ltr font-medium text-primary hover:underline">
                      {c.ref}
                    </Link>
                  </TD>
                  <TD label={t("fields.title")} className="md:min-w-48">{c.title}</TD>
                  <TD label={t("fields.source")}>
                    {te(`caSource.${c.source.type}`)}
                    {c.source.ref && c.source.type !== "ai_recommendation" ? <span className="ltr block text-xs text-muted-foreground">{c.source.ref}</span> : null}
                  </TD>
                  <TD label={t("fields.priority")}>{te(`caPriority.${c.priority}`)}</TD>
                  <TD label={t("fields.control_level")}>{te(`controlLevel.${c.control_level}`)}</TD>
                  <TD label={t("fields.owner")}>{name(c.owner.full_name_en, c.owner.full_name_ar)}</TD>
                  <TD label={t("fields.engagement")}>
                    <span className="ltr">{c.responsible_engagement.short_code}</span>
                  </TD>
                  <TD label={t("fields.due_date")} className="md:min-w-40">
                    <span className="flex flex-col items-start">
                      <StackedDate v={c.due_date} />
                      {c.overdue && c.days_overdue ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive">
                          <AlertTriangle aria-hidden className="size-3.5 shrink-0" />
                          {t("daysOverdue", { days: show(c.days_overdue), n: c.days_overdue })}
                        </span>
                      ) : null}
                    </span>
                  </TD>
                  <TD label={t("fields.status")}>
                    <span className="inline-flex flex-wrap gap-1">
                      <StatusBadge status={c.status} label={te(`caStatus.${c.status}`)} />
                      {c.overdue ? <StatusBadge status="overdue" label={t("overdue")} /> : null}
                      {c.verification_overdue ? <StatusBadge status="late" label={t("verificationOverdue")} /> : null}
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

export function CaForm({ project, ca }: { project: Schemas["ProjectRead"]; ca?: Schemas["CaRead"] }) {
  const t = useTranslations("ca");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const sourceType = (ca?.source.type ?? s.get("source_type") ?? "other") as Schemas["CaSourceType"];
  const sourceId = ca?.source.id ?? s.get("source_id");
  const sourceRef = ca?.source.ref ?? s.get("source_ref");
  const aiRecId = s.get("ai_recommendation_id");
  const fromAi = !ca && sourceType === "ai_recommendation";
  const [error, setError] = useState<unknown>(null);
  const schema = useMemo(
    () =>
      z
        .object({
          title: z.string().trim().min(1, tv("required")).max(150, tv("maxLength", { max: 150 })),
          description: z.string().trim().min(1, tv("required")).max(2000, tv("maxLength", { max: 2000 })),
          control_level: z.enum(CONTROL_LEVELS),
          priority: z.enum(CA_PRIORITIES),
          owner_id: z.string().min(1, tv("required")),
          verifier_id: z.string().min(1, tv("required")),
          responsible_engagement_id: z.string(),
          site_id: z.string(),
          zone_id: z.string(),
          due_date: z.string(),
        })
        .superRefine((v, ctx) => {
          if (v.owner_id && v.owner_id === v.verifier_id) ctx.addIssue({ code: "custom", path: ["verifier_id"], message: tv("invalid") });
          if (sourceType === "other" || sourceType === "ai_recommendation") {
            if (!v.site_id) ctx.addIssue({ code: "custom", path: ["site_id"], message: tv("required") });
            if (!v.responsible_engagement_id) ctx.addIssue({ code: "custom", path: ["responsible_engagement_id"], message: tv("required") });
          }
        }),
    [tv, sourceType],
  );
  type Values = z.infer<typeof schema>;
  const initialCl = (s.get("control_level") ?? "") as Schemas["ControlLevel"];
  const initialPrio = (s.get("priority") ?? "") as Schemas["CaPriority"];
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: ca?.title ?? s.get("title") ?? "",
      description: ca?.description ?? s.get("description") ?? "",
      control_level: ca?.control_level ?? (CONTROL_LEVELS.includes(initialCl) ? initialCl : "engineering"),
      priority: ca?.priority ?? (CA_PRIORITIES.includes(initialPrio) ? initialPrio : "medium"),
      owner_id: ca?.owner.id ?? "",
      verifier_id: ca?.verifier.id ?? "",
      responsible_engagement_id: ca?.responsible_engagement.id ?? s.get("engagement_id") ?? "",
      site_id: ca?.site.id ?? s.get("site_id") ?? "",
      zone_id: ca?.zone?.id ?? s.get("zone_id") ?? "",
      due_date: "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const siteId = useWatch({ control: form.control, name: "site_id" });
  const cl = useWatch({ control: form.control, name: "control_level" });
  const text = `${useWatch({ control: form.control, name: "title" })} ${useWatch({ control: form.control, name: "description" })}`;

  async function save(v: Values) {
    setError(null);
    try {
      const saved = ca
        ? await unwrap(
            api.PATCH("/api/v1/corrective-actions/{ca_id}", {
              params: { path: { ca_id: ca.id } },
              body: {
                title: v.title.trim(),
                description: v.description.trim(),
                control_level: v.control_level,
                priority: v.priority,
                owner_id: v.owner_id,
                verifier_id: v.verifier_id,
                zone_id: v.zone_id || null,
              },
            }),
          )
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/corrective-actions", {
              params: { path: { project_id: project.id } },
              body: {
                title: v.title.trim(),
                description: v.description.trim(),
                control_level: v.control_level,
                priority: v.priority,
                owner_id: v.owner_id,
                verifier_id: v.verifier_id,
                responsible_engagement_id: v.responsible_engagement_id || null,
                due_date: v.due_date || null,
                source_type: sourceType,
                source_id: sourceType === "other" ? null : sourceId,
                ai_recommendation_id: sourceType === "ai_recommendation" ? aiRecId : null,
                site_id: v.site_id || null,
                zone_id: v.zone_id || null,
              },
            }),
          );
      qc.setQueryData(hk.ca(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["corrective-actions"] });
      if (sourceType === "incident" && sourceId) await qc.invalidateQueries({ queryKey: hk.incident(sourceId) });
      if (sourceType === "observation" && sourceId) await qc.invalidateQueries({ queryKey: hk.observation(sourceId) });
      warn(saved.warnings);
      toast.success(ca ? tc("saved") : tc("created"));
      router.push(`/actions/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="ca-form">
      {fromAi ? (
        <Alert tone="info" data-testid="ai-prefill-note">
          {t("fromAi")}
        </Alert>
      ) : null}
      {sourceType !== "other" && sourceRef ? (
        <p className="text-sm text-muted-foreground">
          {t("fromSource", { source: `${te(`caSource.${sourceType}`)} ${sourceType === "ai_recommendation" ? "" : sourceRef}` })}
        </p>
      ) : null}
      <FormSection title={ca ? t("editTitle") : t("createTitle")}>
        <FormField id="title" label={t("fields.title")} required error={errors.title?.message} className="sm:col-span-2">
          <Input maxLength={150} {...form.register("title")} />
        </FormField>
        <FormField id="description" label={t("fields.description")} required error={errors.description?.message} className="sm:col-span-2">
          <Textarea rows={4} maxLength={2000} {...form.register("description")} />
        </FormField>
        <div className="sm:col-span-2">
          <PossibleIdHint text={text} />
        </div>
        <FormField id="control_level" label={t("fields.control_level")} required error={errors.control_level?.message}>
          <Select {...form.register("control_level")}>
            {CONTROL_LEVELS.map((x) => (
              <option key={x} value={x}>
                {te(`controlLevel.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="priority" label={t("fields.priority")} required error={errors.priority?.message}>
          <Select {...form.register("priority")}>
            {CA_PRIORITIES.map((x) => (
              <option key={x} value={x}>
                {te(`caPriority.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {cl === "ppe" ? (
          <div className="sm:col-span-2">
            <Alert tone="warning">{t("ppeWarning")}</Alert>
          </div>
        ) : null}
        <FormField id="owner_id" label={t("fields.owner")} required error={errors.owner_id?.message}>
          <UserSelect projectId={project.id} {...form.register("owner_id")} />
        </FormField>
        <FormField id="verifier_id" label={t("fields.verifier")} required error={errors.verifier_id?.message}>
          <UserSelect projectId={project.id} {...form.register("verifier_id")} />
        </FormField>
        {!ca ? (
          <>
            <FormField id="site_id" label={t("fields.site")} required={sourceType === "other" || fromAi} error={errors.site_id?.message}>
              <Select {...form.register("site_id", { onChange: () => form.setValue("zone_id", "") })}>
                <option value="">{sourceType === "other" || fromAi ? tc("select") : t("fromSource", { source: te(`caSource.${sourceType}`) })}</option>
                {opts.sites.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="responsible_engagement_id" label={t("fields.engagement")} required={sourceType === "other" || fromAi} error={errors.responsible_engagement_id?.message}>
              <Select {...form.register("responsible_engagement_id")}>
                <option value="">{sourceType === "other" || fromAi ? tc("select") : t("fromSource", { source: te(`caSource.${sourceType}`) })}</option>
                {opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId)).map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="due_date" label={t("fields.due_date")} hint={t("dueDefaultHint")} error={errors.due_date?.message}>
              <Input type="date" {...form.register("due_date")} />
            </FormField>
          </>
        ) : null}
        <FormField id="zone_id" label={t("fields.zone")}>
          <Select {...form.register("zone_id")}>
            <option value="">{tc("noZone")}</option>
            {opts.zones.filter((z) => z.siteId === (siteId || ca?.site.id)).map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-ca">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={ca ? `/actions/${ca.id}` : "/actions"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </form>
  );
}

function transitionLabel(from: CaStatus, to: CaStatus, t: ReturnType<typeof useTranslations<"ca">>): string {
  if (from === "open" && to === "in_progress") return t("accept");
  if (to === "pending_verification") return t("markDone");
  if (from === "pending_verification" && to === "closed") return t("verifyClose");
  if (from === "pending_verification" && to === "in_progress") return t("reject");
  if (to === "cancelled") return t("cancelCa");
  if (from === "closed") return t("reopen");
  return to;
}

export function CaDetail({ id }: { id: string }) {
  const t = useTranslations("ca");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const q = useCorrectiveAction(id);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date, dateTime } = useFormatters(pid);
  const [to, setTo] = useState<CaStatus | null>(null);
  const [extOpen, setExtOpen] = useState(false);
  const [decide, setDecide] = useState<{ ext: Schemas["CaExtensionRead"]; approve: boolean } | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  const isOwner = c.owner.id === me.id;
  const editable = (isOwner || canWrite(me, "ca.create", c.project_id)) && (c.status === "open" || c.status === "in_progress");
  const canEvidence = (isOwner || canWrite(me, "ca.create", c.project_id)) && c.status !== "closed" && c.status !== "cancelled";
  const canDecide = canWrite(me, "ca.approve_extension", c.project_id) && !isOwner;
  const pending = c.extensions.some((x) => x.status === "requested");
  const srcRoute = c.source.id && c.source.type !== "ai_recommendation" && c.source.type !== "other" ? entityRoute(c.source.type, c.source.id, c.project_id) : null;

  async function refresh(next?: Schemas["CaRead"]) {
    if (next) qc.setQueryData(hk.ca(c.id), next);
    else await qc.invalidateQueries({ queryKey: hk.ca(c.id) });
    await qc.invalidateQueries({ queryKey: ["corrective-actions"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("actions"), href: "/actions" }, { label: c.ref }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <div>
                <p className="ltr text-sm text-muted-foreground" data-testid="ca-ref">
                  {c.ref}
                </p>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <span data-testid="ca-title">{c.title}</span>
                  <StatusBadge status={c.status} label={te(`caStatus.${c.status}`)} />
                  {c.overdue ? <StatusBadge status="overdue" label={c.days_overdue ? t("daysOverdue", { days: show(c.days_overdue), n: c.days_overdue }) : t("overdue")} /> : null}
                  {c.verification_overdue ? <StatusBadge status="late" label={t("verificationOverdue")} /> : null}
                </CardTitle>
              </div>
              {editable ? (
                <Button size="sm" variant="outline" asChild>
                  <Link href={`/actions/${c.id}/edit`} data-testid="edit-ca">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <ApiWarnings warnings={c.warnings} />
              <FieldList>
                <FieldItem label={t("fields.source")}>
                  {te(`caSource.${c.source.type}`)}
                  {srcRoute ? (
                    <>
                      {" · "}
                      <Link href={srcRoute} className="ltr text-primary hover:underline">
                        {c.source.ref}
                      </Link>
                    </>
                  ) : null}
                </FieldItem>
                <FieldItem label={t("fields.priority")}>{te(`caPriority.${c.priority}`)}</FieldItem>
                <FieldItem label={t("fields.control_level")}>{te(`controlLevel.${c.control_level}`)}</FieldItem>
                <FieldItem label={t("fields.owner")}>{name(c.owner.full_name_en, c.owner.full_name_ar)}</FieldItem>
                <FieldItem label={t("fields.verifier")}>{name(c.verifier.full_name_en, c.verifier.full_name_ar)}</FieldItem>
                <FieldItem label={t("fields.engagement")}>
                  <span className="ltr">{c.responsible_engagement.short_code}</span>
                </FieldItem>
                <FieldItem label={t("fields.site")}>
                  <span className="ltr">
                    {c.site.code}
                    {c.zone ? ` / ${c.zone.code}` : ""}
                  </span>
                </FieldItem>
                <FieldItem label={t("fields.due_date")}>
                  <span data-testid="ca-due">{date(c.due_date)}</span>
                </FieldItem>
                <FieldItem label={t("originalDue")}>{date(c.original_due_date)}</FieldItem>
                <FieldItem label={t("fields.completed_at")}>{dateTime(c.completed_at)}</FieldItem>
                <FieldItem label={t("fields.verified_at")}>{dateTime(c.verified_at)}</FieldItem>
                {c.cancel_reason ? <FieldItem label={t("fields.cancel_reason")}>{c.cancel_reason}</FieldItem> : null}
                <FieldItem label={t("fields.description")} wide>
                  <span className="whitespace-pre-wrap">{c.description}</span>
                </FieldItem>
                {c.evidence_text ? (
                  <FieldItem label={t("fields.evidence_text")} wide>
                    <span className="whitespace-pre-wrap">{c.evidence_text}</span>
                  </FieldItem>
                ) : null}
                {c.verification_comment ? (
                  <FieldItem label={t("fields.verification_comment")} wide>
                    <span className="whitespace-pre-wrap">{c.verification_comment}</span>
                  </FieldItem>
                ) : null}
              </FieldList>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("evidenceFiles")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Attachments ownerType="corrective_action_evidence" ownerId={c.id} canUpload={canEvidence} canDelete={canEvidence && c.status !== "pending_verification"} hint={t("evidenceHint")} onChange={() => void refresh()} />
            </CardContent>
          </Card>
          <Card data-testid="extensions-card">
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>{t("extensions")}</CardTitle>
              {isOwner && !pending && (c.status === "open" || c.status === "in_progress") ? (
                <Button size="sm" variant="outline" onClick={() => setExtOpen(true)} data-testid="request-extension">
                  <CalendarPlus aria-hidden />
                  {t("requestExtension")}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {c.extensions.length === 0 ? (
                <p className="text-sm text-muted-foreground">—</p>
              ) : (
                <ul className="flex flex-col divide-y">
                  {c.extensions.map((x) => (
                    <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" data-testid="extension-row">
                      <span>
                        {date(x.previous_due_date)} → <strong>{date(x.new_due_date)}</strong> · {name(x.requested_by.full_name_en, x.requested_by.full_name_ar)}
                        <span className="block text-muted-foreground">{x.reason}</span>
                        {x.decision_comment ? <span className="block text-muted-foreground">{x.decision_comment}</span> : null}
                      </span>
                      <span className="inline-flex items-center gap-2">
                        <StatusBadge status={x.status === "approved" ? "completed" : x.status === "rejected" ? "rejected" : "requested"} label={te(`extensionStatus.${x.status}`)} />
                        {x.status === "requested" && canDecide ? (
                          <>
                            <Button size="sm" onClick={() => setDecide({ ext: x, approve: true })} data-testid="approve-extension">
                              {t("approve")}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setDecide({ ext: x, approve: false })} data-testid="reject-extension">
                              {t("rejectExt")}
                            </Button>
                          </>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          {c.allowed_transitions.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("fields.status")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {c.allowed_transitions.map((x) => (
                  <Button key={x} size="sm" variant={x === "cancelled" ? "destructive" : x === "closed" || x === "pending_verification" ? "default" : "outline"} onClick={() => setTo(x)} data-testid={`transition-${x}`}>
                    {transitionLabel(c.status, x, t)}
                  </Button>
                ))}
              </CardContent>
            </Card>
          ) : null}
          {can(me, "history.view", c.project_id) ? <HistoryPanel entityType="corrective_action" entityId={c.id} projectId={c.project_id} /> : null}
        </div>
      </div>
      {to ? <CaTransitionDialog ca={c} to={to} onClose={() => setTo(null)} onDone={refresh} /> : null}
      {extOpen ? <ExtensionRequestDialog ca={c} onClose={() => setExtOpen(false)} onDone={refresh} /> : null}
      {decide ? <ExtensionDecisionDialog ca={c} ext={decide.ext} approve={decide.approve} onClose={() => setDecide(null)} onDone={refresh} /> : null}
    </div>
  );
}

function CaTransitionDialog({ ca: c, to, onClose, onDone }: { ca: Schemas["CaRead"]; to: CaStatus; onClose: () => void; onDone: (n: Schemas["CaRead"]) => Promise<void> }) {
  const t = useTranslations("ca");
  const tt = useTranslations("transitions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const evidence = to === "pending_verification";
  const rejecting = c.status === "pending_verification" && to === "in_progress";
  const needsReason = to === "cancelled" || c.status === "closed";
  const [text, setText] = useState(c.evidence_text ?? "");
  const [err, setErr] = useState<string>();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    if (evidence && text.trim().length < 20 && c.evidence_attachment_count === 0) return setErr(t("evidenceHint"));
    if (rejecting && !text.trim()) return setErr(t("commentRequired"));
    if (needsReason && !text.trim()) return setErr(tt("reasonRequired"));
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.POST("/api/v1/corrective-actions/{ca_id}/transitions", {
          params: { path: { ca_id: c.id } },
          body: {
            to_status: to,
            evidence_text: evidence ? text.trim() || null : null,
            comment: !evidence && !needsReason ? text.trim() || null : null,
            reason: needsReason ? text.trim() : null,
          },
        }),
      );
      toast.success(tt("done", { status: te(`caStatus.${to}`) }));
      await onDone(next);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const label = evidence ? t("evidence") : needsReason ? tc("reason") : rejecting ? t("comment") : tt("reasonOptional");
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{transitionLabel(c.status, to, t)}</DialogTitle>
          <DialogDescription>{tt("dialogBody", { from: te(`caStatus.${c.status}`) })}</DialogDescription>
        </DialogHeader>
        <FormField id="ca-transition-text" label={label} required={evidence || rejecting || needsReason} hint={evidence ? t("evidenceHint") : undefined} error={err}>
          <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={to === "cancelled" ? "destructive" : "default"} onClick={() => void submit()} disabled={busy} data-testid="transition-confirm">
            {busy ? tc("saving") : tt("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ExtensionRequestDialog({ ca: c, onClose, onDone }: { ca: Schemas["CaRead"]; onClose: () => void; onDone: (n: Schemas["CaRead"]) => Promise<void> }) {
  const t = useTranslations("ca");
  const tc = useTranslations("common");
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.POST("/api/v1/corrective-actions/{ca_id}/extensions", { params: { path: { ca_id: c.id } }, body: { new_due_date: due, reason: reason.trim() } }));
      toast.success(tc("saved"));
      await onDone(next);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("requestExtension")}</DialogTitle>
          <DialogDescription>
            {t("fields.due_date")}: {c.due_date}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="ext-due" label={t("newDueDate")} required>
            <Input type="date" min={c.due_date} value={due} onChange={(e) => setDue(e.target.value)} />
          </FormField>
          <FormField id="ext-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          </FormField>
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !due || !reason.trim()} data-testid="extension-submit">
            {tc("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ExtensionDecisionDialog({
  ca: c,
  ext,
  approve,
  onClose,
  onDone,
}: {
  ca: Schemas["CaRead"];
  ext: Schemas["CaExtensionRead"];
  approve: boolean;
  onClose: () => void;
  onDone: (n: Schemas["CaRead"]) => Promise<void>;
}) {
  const t = useTranslations("ca");
  const tc = useTranslations("common");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.POST("/api/v1/corrective-actions/{ca_id}/extensions/{extension_id}/decision", {
          params: { path: { ca_id: c.id, extension_id: ext.id } },
          body: { approve, comment: comment.trim() || null },
        }),
      );
      toast.success(tc("saved"));
      await onDone(next);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{approve ? t("approve") : t("rejectExt")}</DialogTitle>
          <DialogDescription>
            {ext.previous_due_date} → {ext.new_due_date}
          </DialogDescription>
        </DialogHeader>
        <FormField id="ext-comment" label={t("decisionComment")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={approve ? "default" : "destructive"} onClick={() => void submit()} disabled={busy} data-testid="decision-confirm">
            {approve ? t("approve") : t("rejectExt")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
