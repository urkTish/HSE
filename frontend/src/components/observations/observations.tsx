"use client";
import { Camera, ClipboardCheck, Pencil, Plus } from "lucide-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { LinkFilterNote } from "@/components/common/link-filter-note";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useObservation, useObservations } from "@/lib/api/hse";
import { useProjectSettings } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { OBSERVATION_STATUSES, OBSERVATION_TYPES, RISK_RATINGS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { useLocalDraft, useOnline } from "@/lib/local-draft";
import { can, canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { StackedDate } from "@/components/medical/common";

const PAGE_SIZE = 50;
const isUnsafe = (t: string) => t === "unsafe_act" || t === "unsafe_condition";

export function ObservationList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("observations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const ref = useRefLists();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["ObservationStatus"][];
  const types = s.getAll("obs_type") as Schemas["ObservationType"][];
  const sites = s.getAll("site_id");
  const engs = s.getAll("engagement_id");
  const risk = (s.get("risk_rating") ?? "") as Schemas["RiskRating"] | "";
  const q = {
    status: status.length ? status : null,
    obs_type: types.length ? types : null,
    category: (s.get("category") as Schemas["ObservationCategory"] | null) || null,
    risk_rating: risk || null,
    site_id: sites.length ? sites : null,
    zone_id: s.getAll("zone_id").length ? s.getAll("zone_id") : null,
    engagement_id: engs.length ? engs : null,
    include_subcontractors: s.getBool("include_subcontractors") ?? true,
    without_ca_over_hours: s.getInt("without_ca_over_hours", 0) || null,
    mine: s.getBool("mine") ?? undefined,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useObservations(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "observation.create", project.id) ? (
            <Button asChild>
              <Link href="/observations/new" data-testid="new-observation">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <LinkFilterNote keys={["without_ca_over_hours", "category", "zone_id"]} />
      <ListToolbar actions={can(me, "export.lists", project.id) ? <ExportButtons dataset="observations" params={{ project_id: project.id }} /> : null}>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="obs-from">{tc("dateFrom")}</Label>
          <Input id="obs-from" type="date" value={q.date_from ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="obs-to">{tc("dateTo")}</Label>
          <Input id="obs-to" type="date" value={q.date_to ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </div>
        <MultiSelect id="obs-site" label={tc("site")} options={opts.sites} value={sites} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="obs-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <MultiSelect id="obs-type" label={t("fields.obs_type")} options={OBSERVATION_TYPES.map((x) => ({ value: x, label: te(`observationType.${x}`) }))} value={types} onChange={(v) => s.set({ obs_type: v })} />
        <SelectFilter id="obs-risk" label={t("fields.risk_rating")} value={risk} onChange={(v) => s.set({ risk_rating: v })} options={RISK_RATINGS.map((x) => ({ value: x, label: te(`riskRating.${x}`) }))} />
        <MultiSelect
          id="obs-status"
          label={t("fields.status")}
          options={OBSERVATION_STATUSES.map((x) => ({ value: x, label: te(`observationStatus.${x}`) }))}
          value={status}
          onChange={(v) => s.set({ status: v })}
          testId="obs-status-filter"
        />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={q.mine === true} onChange={(e) => s.set({ mine: e.target.checked ? "true" : null })} />
          {t("mine")}
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="observations-table">
            <THead>
              <TR>
                <TH>{t("fields.ref")}</TH>
                <TH>{t("fields.observed_at")}</TH>
                <TH>{t("fields.obs_type")}</TH>
                <TH>{t("fields.category")}</TH>
                <TH>{t("fields.risk_rating")}</TH>
                <TH>{t("fields.site")}</TH>
                <TH>{t("fields.engagement")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((o) => (
                <TR key={o.id} data-testid="observation-row">
                  <TD label={t("fields.ref")}>
                    <Link href={`/observations/${o.id}`} className="ltr font-medium text-primary hover:underline">
                      {o.ref}
                    </Link>
                  </TD>
                  <TD label={t("fields.observed_at")}><StackedDate v={o.observed_at} time /></TD>
                  <TD label={t("fields.obs_type")}>{te(`observationType.${o.obs_type}`)}</TD>
                  <TD label={t("fields.category")}>{ref.label("observation_category", o.category)}</TD>
                  <TD label={t("fields.risk_rating")}>{o.risk_rating ? <StatusBadge status={`risk_${o.risk_rating}`} label={te(`riskRating.${o.risk_rating}`)} /> : "—"}</TD>
                  <TD label={t("fields.site")}>
                    <span className="ltr">
                      {o.site.code}
                      {o.zone ? ` / ${o.zone.code}` : ""}
                    </span>
                  </TD>
                  <TD label={t("fields.engagement")}>
                    <span className="ltr">{o.observed_engagement.short_code}</span>
                  </TD>
                  <TD label={t("fields.status")}>
                    <StatusBadge status={o.status} label={te(`observationStatus.${o.status}`)} />
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

export function ObservationForm({ project, obs }: { project: Schemas["ProjectRead"]; obs?: Schemas["ObservationRead"] }) {
  const t = useTranslations("observations");
  const te = useTranslations("enums");
  const tv = useTranslations("validation");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const online = useOnline();
  const opts = useProjectOptions(project.id);
  const ref = useRefLists();
  const settings = useProjectSettings(project.id);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const [error, setError] = useState<unknown>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const photoRef = useRef<HTMLInputElement>(null);
  const schema = useMemo(
    () =>
      z
        .object({
          site_id: z.string().min(1, tv("required")),
          zone_id: z.string(),
          observed_at: z.string().min(1, tv("required")),
          anonymous: z.boolean(),
          observed_engagement_id: z.string().min(1, tv("required")),
          obs_type: z.enum(OBSERVATION_TYPES),
          category: z.string().min(1, tv("required")),
          risk_rating: z.string(),
          description: z.string().trim().min(1, tv("required")).max(1000, tv("maxLength", { max: 1000 })),
          stop_work_applied: z.boolean(),
          immediate_action: z.string().max(500, tv("maxLength", { max: 500 })),
          closed_on_spot: z.boolean(),
        })
        .superRefine((v, ctx) => {
          if (isUnsafe(v.obs_type)) {
            if (!v.risk_rating) ctx.addIssue({ code: "custom", path: ["risk_rating"], message: tv("required") });
            if (!v.immediate_action.trim()) ctx.addIssue({ code: "custom", path: ["immediate_action"], message: tv("required") });
          }
        }),
    [tv],
  );
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      site_id: obs?.site.id ?? "",
      zone_id: obs?.zone?.id ?? "",
      observed_at: utcToZonedInput(obs?.observed_at ?? new Date().toISOString(), tz),
      anonymous: obs?.anonymous ?? false,
      observed_engagement_id: obs?.observed_engagement.id ?? "",
      obs_type: obs?.obs_type ?? "unsafe_condition",
      category: obs?.category ?? "",
      risk_rating: obs?.risk_rating ?? "",
      description: obs?.description ?? "",
      stop_work_applied: obs?.stop_work_applied ?? false,
      immediate_action: obs?.immediate_action ?? "",
      closed_on_spot: obs?.closed_on_spot ?? false,
    },
  });
  const draft = useLocalDraft(`observation.${project.id}`, form, !obs);
  const { errors, isSubmitting } = form.formState;
  const siteId = useWatch({ control: form.control, name: "site_id" });
  const type = useWatch({ control: form.control, name: "obs_type" });
  const unsafe = isUnsafe(type);
  const zones = opts.zones.filter((z) => z.siteId === siteId);
  const engagements = opts.engagements.filter((e) => !siteId || e.siteIds.includes(siteId));
  const text = `${useWatch({ control: form.control, name: "description" })} ${useWatch({ control: form.control, name: "immediate_action" })}`;

  async function save(v: Values) {
    setError(null);
    try {
      let saved: Schemas["ObservationRead"];
      if (obs) {
        saved = await unwrap(
          api.PATCH("/api/v1/observations/{observation_id}", {
            params: { path: { observation_id: obs.id } },
            body: {
              zone_id: v.zone_id || null,
              obs_type: v.obs_type,
              category: v.category as Schemas["ObservationCategory"],
              risk_rating: unsafe ? ((v.risk_rating || null) as Schemas["RiskRating"] | null) : null,
              description: v.description.trim(),
              stop_work_applied: v.stop_work_applied,
              immediate_action: v.immediate_action.trim() || null,
            },
          }),
        );
      } else {
        saved = await unwrap(
          api.POST("/api/v1/projects/{project_id}/observations", {
            params: { path: { project_id: project.id } },
            body: {
              site_id: v.site_id,
              zone_id: v.zone_id || null,
              observed_at: zonedInputToUtc(v.observed_at, tz),
              anonymous: v.anonymous,
              observed_engagement_id: v.observed_engagement_id,
              obs_type: v.obs_type,
              category: v.category as Schemas["ObservationCategory"],
              risk_rating: unsafe ? ((v.risk_rating || null) as Schemas["RiskRating"] | null) : null,
              description: v.description.trim(),
              stop_work_applied: v.stop_work_applied,
              immediate_action: v.immediate_action.trim() || null,
              closed_on_spot: unsafe ? v.closed_on_spot : null,
            },
          }),
        );
        for (const f of photos.slice(0, 3)) {
          const fd = new FormData();
          fd.set("owner_type", "observation");
          fd.set("owner_id", saved.id);
          fd.set("file", f);
          await postForm<Schemas["AttachmentRead"]>("/api/v1/attachments", fd);
        }
        draft.clear();
      }
      qc.setQueryData(hk.observation(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["observations"] });
      warn(saved.warnings);
      toast.success(obs ? tc("saved") : saved.status === "closed" ? t("savedClosed") : t("savedOpen"));
      router.push(`/observations/${saved.id}`);
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate className="flex max-w-3xl flex-col gap-6" data-testid="observation-form">
      {draft.restored ? (
        <Alert tone="info">
          <span className="flex flex-wrap items-center gap-2">
            {tc("draftRestored")}
            <Button type="button" size="sm" variant="ghost" onClick={() => { draft.clear(); form.reset(); }}>
              {tc("discardDraft")}
            </Button>
          </span>
        </Alert>
      ) : null}
      {!online ? <Alert tone="warning">{tc("offline")}</Alert> : null}
      <FormSection title={obs ? t("editTitle") : t("createTitle")}>
        <FormField id="obs_type" label={t("fields.obs_type")} required error={errors.obs_type?.message}>
          <Select {...form.register("obs_type")}>
            {OBSERVATION_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`observationType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="category" label={t("fields.category")} required error={errors.category?.message}>
          <Select {...form.register("category")}>
            <option value="">{tc("select")}</option>
            {ref.options("observation_category").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="observed_at" label={t("fields.observed_at")} required error={errors.observed_at?.message}>
          <Input type="datetime-local" disabled={Boolean(obs)} {...form.register("observed_at")} />
        </FormField>
        <FormField id="site_id" label={t("fields.site")} required error={errors.site_id?.message}>
          <Select disabled={Boolean(obs)} {...form.register("site_id", { onChange: () => form.setValue("zone_id", "") })}>
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="zone_id" label={t("fields.zone")} error={errors.zone_id?.message}>
          <Select {...form.register("zone_id")}>
            <option value="">{tc("noZone")}</option>
            {zones.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="observed_engagement_id" label={t("fields.engagement")} required error={errors.observed_engagement_id?.message}>
          <Select disabled={Boolean(obs)} {...form.register("observed_engagement_id")}>
            <option value="">{tc("select")}</option>
            {engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        {unsafe ? (
          <FormField id="risk_rating" label={t("fields.risk_rating")} required error={errors.risk_rating?.message}>
            <Select {...form.register("risk_rating")}>
              <option value="">{tc("select")}</option>
              {RISK_RATINGS.map((x) => (
                <option key={x} value={x}>
                  {te(`riskRating.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="description" label={t("fields.description")} required error={errors.description?.message} hint={t("noNamesHint")} className="sm:col-span-2">
          <Textarea rows={4} maxLength={1000} {...form.register("description")} />
        </FormField>
        {unsafe ? (
          <FormField id="immediate_action" label={t("fields.immediate_action")} required error={errors.immediate_action?.message} className="sm:col-span-2">
            <Textarea rows={2} maxLength={500} {...form.register("immediate_action")} />
          </FormField>
        ) : null}
        <div className="sm:col-span-2">
          <PossibleIdHint text={text} />
        </div>
        <CheckboxField id="stop_work_applied" label={t("fields.stop_work_applied")}>
          <Checkbox {...form.register("stop_work_applied")} />
        </CheckboxField>
        {unsafe && !obs ? (
          <CheckboxField id="closed_on_spot" label={t("fields.closed_on_spot")}>
            <Checkbox {...form.register("closed_on_spot")} />
          </CheckboxField>
        ) : null}
        {!obs ? (
          <CheckboxField id="anonymous" label={`${t("fields.anonymous")} — ${t("anonymousHint")}`}>
            <Checkbox {...form.register("anonymous")} />
          </CheckboxField>
        ) : null}
      </FormSection>
      {!obs ? (
        <FormSection title={t("photos")} description={t("photosHint")}>
          <div className="flex flex-col gap-2 sm:col-span-2">
            <input
              ref={photoRef}
              type="file"
              accept="image/*"
              capture="environment"
              multiple
              className="sr-only"
              data-testid="photo-input"
              onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, 3))}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" onClick={() => photoRef.current?.click()}>
                <Camera aria-hidden />
                {tc("takePhoto")}
              </Button>
              {photos.length > 0 ? <span className="text-sm text-muted-foreground">{t("photoCount", { count: photos.length })}</span> : null}
            </div>
          </div>
        </FormSection>
      ) : null}
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-observation">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button variant="ghost" asChild>
          <Link href={obs ? `/observations/${obs.id}` : "/observations"}>{tc("cancel")}</Link>
        </Button>
      </div>
      {!obs ? <p className="text-xs text-muted-foreground">{tc("draftSavedLocally")}</p> : null}
    </form>
  );
}

export function ObservationDetail({ id }: { id: string }) {
  const t = useTranslations("observations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const ref = useRefLists();
  const q = useObservation(id);
  const pid = q.data?.project_id ?? null;
  const { date, dateTime } = useFormatters(pid);
  const [closing, setClosing] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  const isMine = o.observer?.id === me?.id;
  const canEdit = (isMine || canWrite(me, "observation.close", o.project_id)) && o.status !== "closed";
  const canClose = canWrite(me, "observation.close", o.project_id) && o.status === "open";

  async function close() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.POST("/api/v1/observations/{observation_id}/close", { params: { path: { observation_id: o.id } }, body: { comment: comment.trim() } }));
      qc.setQueryData(hk.observation(o.id), next);
      await qc.invalidateQueries({ queryKey: ["observations"] });
      toast.success(tc("saved"));
      setClosing(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("observations"), href: "/observations" }, { label: o.ref }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <div>
                <p className="ltr text-sm text-muted-foreground">{o.ref}</p>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <span data-testid="observation-title">{te(`observationType.${o.obs_type}`)}</span>
                  <StatusBadge status={o.status} label={te(`observationStatus.${o.status}`)} />
                  {o.risk_rating ? <StatusBadge status={`risk_${o.risk_rating}`} label={te(`riskRating.${o.risk_rating}`)} /> : null}
                </CardTitle>
              </div>
              <div className="flex flex-wrap gap-2">
                {canEdit ? (
                  <Button size="sm" variant="outline" asChild>
                    <Link href={`/observations/${o.id}/edit`} data-testid="edit-observation">
                      <Pencil aria-hidden />
                      {tc("edit")}
                    </Link>
                  </Button>
                ) : null}
                {canClose ? (
                  <Button size="sm" variant="outline" onClick={() => setClosing(true)} data-testid="close-observation">
                    {t("close")}
                  </Button>
                ) : null}
                {canWrite(me, "ca.create", o.project_id) && o.status !== "closed" && isUnsafe(o.obs_type) ? (
                  <Button size="sm" asChild>
                    <Link href={`/actions/new?source_type=observation&source_id=${o.id}&source_ref=${encodeURIComponent(o.ref)}`} data-testid="raise-ca">
                      <ClipboardCheck aria-hidden />
                      {t("raiseAction")}
                    </Link>
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {o.ca_due_by && o.status === "open" ? <Alert tone="warning">{t("caDueBy")}: {dateTime(o.ca_due_by)}</Alert> : null}
              <ApiWarnings warnings={o.warnings} />
              <FieldList>
                <FieldItem label={t("fields.observed_at")}>{dateTime(o.observed_at)}</FieldItem>
                <FieldItem label={t("observer")}>
                  <span data-testid="observer">{o.observer ? name(o.observer.full_name_en, o.observer.full_name_ar) : t("anonymous")}</span>
                  {o.anonymous && o.observer ? ` (${t("anonymous")})` : ""}
                </FieldItem>
                <FieldItem label={t("fields.category")}>{ref.label("observation_category", o.category)}</FieldItem>
                <FieldItem label={t("fields.site")}>
                  <span className="ltr">{o.site.code}</span> — {name(o.site.name_en, o.site.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.zone")}>{o.zone ? `${o.zone.code} — ${name(o.zone.name_en, o.zone.name_ar)}` : "—"}</FieldItem>
                <FieldItem label={t("fields.engagement")}>
                  <span className="ltr">{o.observed_engagement.short_code}</span> — {name(o.observed_engagement.name_en, o.observed_engagement.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.stop_work_applied")}>
                  <YesNo value={o.stop_work_applied} yes={tc("yes")} no={tc("no")} />
                </FieldItem>
                {o.closed_on_spot !== null ? (
                  <FieldItem label={t("fields.closed_on_spot")}>
                    <YesNo value={o.closed_on_spot} yes={tc("yes")} no={tc("no")} />
                  </FieldItem>
                ) : null}
                <FieldItem label={t("fields.closed_at")}>{dateTime(o.closed_at)}</FieldItem>
                <FieldItem label={t("fields.description")} wide>
                  <span className="whitespace-pre-wrap">{o.description}</span>
                </FieldItem>
                {o.immediate_action ? (
                  <FieldItem label={t("fields.immediate_action")} wide>
                    <span className="whitespace-pre-wrap">{o.immediate_action}</span>
                  </FieldItem>
                ) : null}
                {o.closure_comment ? (
                  <FieldItem label={t("fields.closure_comment")} wide>
                    <span className="whitespace-pre-wrap">{o.closure_comment}</span>
                  </FieldItem>
                ) : null}
              </FieldList>
              {o.corrective_actions.length > 0 ? (
                <ul className="flex flex-col divide-y rounded-md border">
                  {o.corrective_actions.map((ca) => (
                    <li key={ca.id} className="flex flex-wrap items-center justify-between gap-2 p-2 text-sm">
                      <Link href={`/actions/${ca.id}`} className="text-primary hover:underline">
                        <span className="ltr">{ca.ref}</span> — {ca.title}
                      </Link>
                      <span className="inline-flex items-center gap-1">
                        {date(ca.due_date)}
                        <StatusBadge status={ca.overdue ? "overdue" : ca.status} label={te(`caStatus.${ca.status}`)} />
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("photos")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Attachments ownerType="observation" ownerId={o.id} canUpload={canEdit && o.attachment_count < 3} canDelete={canEdit} hint={t("photosHint")} max={3} />
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">{can(me, "history.view", o.project_id) ? <HistoryPanel entityType="observation" entityId={o.id} projectId={o.project_id} /> : null}</div>
      </div>
      <Dialog open={closing} onOpenChange={setClosing}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("close")}</DialogTitle>
          </DialogHeader>
          <FormField id="close-comment" label={t("closeComment")} required>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
          <MutationError error={error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setClosing(false)}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => void close()} disabled={busy || !comment.trim()} data-testid="close-confirm">
              {t("close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
