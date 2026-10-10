"use client";
import { CheckCircle2, Droplet, FileWarning, Plane, Plus, ShieldAlert, TriangleAlert, Waves } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
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
import { EmptyState, ErrorState, LoadingState, MutationError, NotFoundState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { AnswerButtons, PrivacyNote, ReadyBadge, fromLocalInput, nowLocal } from "@/components/emergency/common";
import { PhotoPicker } from "@/components/field/common";
import { StackedDate } from "@/components/medical/common";
import { DecimalInput } from "@/components/ptw/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEmergencyAssets } from "@/lib/api/emergency";
import { useComplaint, useComplaints, useConsignments, useEnvRefresh, useEnvSettings, useNearbyReadings, useSpill, useSpills, useWasteAreas } from "@/lib/api/env";
import { useIncidents } from "@/lib/api/hse";
import { COMPLAINT_STATUSES, ENV_REACHED, SPILL_STATUSES } from "@/lib/env-enums";
import { useRefLists } from "@/lib/reference";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Check, EnvEventSubNav, EnvReasonDialog, EnvStatusBadge, Measure, NoNamesHint, ResultBadge, StillNeeded, useBi, useEnvCaps, useEnvRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

function ReportableBadge({ reportable }: { reportable: boolean }) {
  const t = useTranslations("env.spills");
  return (
    <span data-testid="spill-reportable" data-reportable={reportable}>
      {reportable ? (
        <Badge tone="danger">
          <ShieldAlert aria-hidden />
          {t("reportable")}
        </Badge>
      ) : (
        <Badge tone="neutral">
          <Droplet aria-hidden />
          {t("minor")}
        </Badge>
      )}
    </span>
  );
}

/* ═════════════ spill log + spill kits (§3.13, SPL-1…SPL-7, K-125) ═════════════ */

export function SpillsPage() {
  return <ProjectGate>{(p) => <Spills project={p} />}</ProjectGate>;
}

function Spills({ project }: { project: Project }) {
  const t = useTranslations("env.spills");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["SpillStatus"] | "";
  const rep = s.get("reportable") ?? "";
  const q = useSpills(project.id, { status: status ? [status] : null, reportable: rep ? rep === "1" : null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.spill ? (
            <Button asChild className="min-h-12 sm:min-h-control">
              <Link href="/spills/new" data-testid="spill-new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EnvEventSubNav />
      <ListToolbar>
        <SelectFilter id="sp-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={SPILL_STATUSES.map((x) => ({ value: x, label: te(`envSpillStatus.${x}`) }))} />
        <SelectFilter
          id="sp-rep"
          label={t("reportable")}
          value={rep}
          onChange={(v) => s.set({ reportable: v })}
          options={[
            { value: "1", label: t("reportable") },
            { value: "0", label: t("minor") },
          ]}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="spills-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("occurred")}</TH>
                <TH>{t("substance")}</TH>
                <TH className="text-end">{t("quantity")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("classification")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="spill-row" data-no={x.spill_no} data-status={x.status}>
                  <TD label={t("no")}>
                    <Link href={`/spills/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.spill_no}</Code>
                    </Link>
                    {x.incident_ref ? (
                      <span className="block text-xs text-muted-foreground">
                        <Code>{x.incident_ref}</Code>
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("occurred")}>
                    <StackedDate v={x.occurred_at} time projectId={project.id} />
                  </TD>
                  <TD label={t("substance")}>
                    {ref.label("spill_substances", x.substance)}
                    <span className="block text-xs text-muted-foreground">{ref.label("spill_source", x.source)}</span>
                  </TD>
                  <TD label={t("quantity")} className="text-end">
                    <Measure v={x.quantity_l} unit="L" className="font-semibold" />
                  </TD>
                  <TD label={t("where")}>
                    <Code>{x.zone_code ?? "—"}</Code>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{x.responsible_code ?? ""}</Code>
                    </span>
                  </TD>
                  <TD label={t("classification")}>
                    <ReportableBadge reportable={x.reportable} />
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envSpillStatus" status={x.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status || rep ? undefined : t("empty")} />
      )}
      <SpillKits project={project} />
    </div>
  );
}

/** 6c spill-kit assets and their readiness (K-125, SPL-5): registered and checked in Emergency, used here. */
function SpillKits({ project }: { project: Project }) {
  const t = useTranslations("env.spills");
  const q = useEmergencyAssets(project.id, { asset_type: ["spill_kit"], page_size: 200 } as never);
  const items = (q.data?.items ?? []).filter((a) => a.asset_type === "spill_kit");
  return (
    <Card className="mt-6" id="spill-kits">
      <CardHeader>
        <CardTitle className="text-base">{t("kits")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("kitsHint")}</p>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : items.length ? (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="spill-kits">
            {items.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm" data-testid="spill-kit" data-ready={a.readiness.ready}>
                <span>
                  <Link href={`/emergency-asset-checks?asset=${a.id}`} className="font-medium text-primary hover:underline">
                    <Code>{a.asset_tag}</Code>
                  </Link>
                  <span className="block text-xs text-muted-foreground">
                    <Code>{a.zone_code ?? a.site_code}</Code>
                  </span>
                </span>
                <ReadyBadge ready={a.readiness.ready} reasons={a.readiness.reasons} />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message={t("noKits")} />
        )}
      </CardContent>
    </Card>
  );
}

export function NewSpillPage() {
  return <ProjectGate>{(p) => <NewSpill project={p} />}</ProjectGate>;
}

/** Phone spill report (SPL-1…SPL-5): facts first, then the Phase 1 incident details when it is reportable. */
function NewSpill({ project }: { project: Project }) {
  const t = useTranslations("env.spills");
  const td = useTranslations("envDesign");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const refs = useRefLists();
  const opts = useProjectOptions(project.id);
  const settings = useEnvSettings(project.id, { enabled: caps.spill });
  const refresh = useEnvRefresh();
  const router = useRouter();
  const [clientUuid] = useState(() => crypto.randomUUID());
  const [v, setV] = useState({
    occurred_at: nowLocal(),
    site_id: "",
    zone_id: "",
    responsible_engagement_id: "",
    substance: "diesel" as S["SpillSubstance"],
    source: "plant_leak" as S["SpillSource"],
    quantity_l: "",
    surface: "paved" as S["SpillSurface"],
    contained: "yes" as "yes" | "no",
    reached: "none" as S["EnvReached"],
    incident_id: "",
  });
  const [kits, setKits] = useState<string[]>([]);
  const [photos, setPhotos] = useState<S["PhotoInput"][]>([]);
  const [inc, setInc] = useState({ actual_severity: "1", potential_severity: "2", activity: "", shift: "day" as S["IncidentShift"], description: "", immediate_actions: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const assets = useEmergencyAssets(project.id, { asset_type: ["spill_kit"], site_id: v.site_id || null, page_size: 200 } as never, { enabled: caps.spill && Boolean(v.site_id) });
  const incidents = useIncidents(project.id, { incident_type: ["environmental"], site_id: v.site_id || null, page_size: 50, sort: "-occurred_at" } as never);
  if (!caps.spill) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const zone = opts.zoneById.get(v.zone_id);
  const airside = zone?.zone_type === "airside";
  // Preview of SPL-2 so the incident details are asked for up front; the server decides and returns `reportable`.
  const threshold = Number(settings.data?.spill_reportable_l ?? "20");
  // The same SPL-2 conditions, kept apart so the preview can say which ones apply.
  const why = [
    v.quantity_l !== "" && Number(v.quantity_l) >= threshold ? { k: "quantity", Icon: Droplet } : null,
    v.reached === "drain" || v.reached === "water_body" ? { k: "reached", Icon: Waves } : null,
    v.contained === "no" ? { k: "notContained", Icon: TriangleAlert } : null,
    airside && (settings.data?.airside_spill_always_reportable ?? true) ? { k: "airside", Icon: Plane } : null,
  ].filter((x): x is { k: "quantity" | "reached" | "notContained" | "airside"; Icon: typeof Droplet } => Boolean(x));
  const likelyReportable = why.length > 0;
  const needIncident = likelyReportable && !v.incident_id;
  const incidentReady = Boolean(inc.activity && inc.description.trim() && inc.immediate_actions.trim());
  const ready = Boolean(v.site_id && v.responsible_engagement_id && v.quantity_l && (!needIncident || incidentReady));
  const missing = [
    !v.site_id ? td("need.site") : "",
    !v.responsible_engagement_id ? td("need.contractor") : "",
    !v.quantity_l ? td("need.quantity") : "",
    needIncident && !incidentReady ? td("need.incident") : "",
  ].filter(Boolean);
  const yn = [
    { value: "yes" as const, label: tc("yes") },
    { value: "no" as const, label: tc("no") },
  ];
  const big = "h-12 text-base sm:h-control sm:text-sm";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/spills", {
          params: { path: { project_id: project.id } },
          body: {
            client_uuid: clientUuid,
            occurred_at: fromLocalInput(v.occurred_at) ?? new Date().toISOString(),
            site_id: v.site_id,
            zone_id: v.zone_id || null,
            responsible_engagement_id: v.responsible_engagement_id,
            substance: v.substance,
            source: v.source,
            quantity_l: v.quantity_l,
            surface: v.surface,
            contained: v.contained === "yes",
            reached: v.reached,
            spill_kit_asset_ids: kits,
            incident_id: v.incident_id || null,
            incident_fields: needIncident
              ? { actual_severity: Number(inc.actual_severity), potential_severity: Number(inc.potential_severity), activity: inc.activity as S["Activity"], shift: inc.shift, description: inc.description, immediate_actions: inc.immediate_actions }
              : null,
            photos,
          },
        }),
      );
      await refresh();
      toast.success(t("saved", { no: r.spill_no }));
      router.push(`/spills/${r.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <PageHeader title={t("newTitle")} description={t("newSubtitle")} />
      <FormField id="sp-at" label={t("occurred")} required hint={t("occurredHint")}>
        <Input id="sp-at" type="datetime-local" dir="ltr" className={big} value={v.occurred_at} onChange={(e) => set({ occurred_at: e.target.value })} data-testid="sp-at" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="sp-site" label={t("site")} required>
          <Select id="sp-site" className={big} value={v.site_id} onChange={(e) => set({ site_id: e.target.value, zone_id: "" })} data-testid="sp-site">
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sp-zone" label={t("zone")}>
          <Select id="sp-zone" className={big} value={v.zone_id} onChange={(e) => set({ zone_id: e.target.value })} data-testid="sp-zone">
            <option value="">—</option>
            {opts.zones
              .filter((z) => z.siteId === v.site_id)
              .map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="sp-eng" label={t("responsible")} required>
          <Select id="sp-eng" className={big} value={v.responsible_engagement_id} onChange={(e) => set({ responsible_engagement_id: e.target.value })} data-testid="sp-engagement">
            <option value="">{tc("select")}</option>
            {opts.engagements.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sp-qty" label={t("quantityL")} required hint={t("estimateHint")}>
          <DecimalInput id="sp-qty" value={v.quantity_l} onChange={(x) => set({ quantity_l: x })} className={big} data-testid="sp-quantity" />
        </FormField>
        <FormField id="sp-sub" label={t("substance")} required>
          <Select id="sp-sub" className={big} value={v.substance} onChange={(e) => set({ substance: e.target.value as S["SpillSubstance"] })} data-testid="sp-substance">
            {ref.options("spill_substances").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sp-src" label={t("source")} required>
          <Select id="sp-src" className={big} value={v.source} onChange={(e) => set({ source: e.target.value as S["SpillSource"] })} data-testid="sp-source">
            {ref.options("spill_source").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sp-surface" label={t("surface")} required>
          <Select id="sp-surface" className={big} value={v.surface} onChange={(e) => set({ surface: e.target.value as S["SpillSurface"] })} data-testid="sp-surface">
            {ref.options("surface").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sp-reached" label={t("reached")} required>
          <Select id="sp-reached" className={big} value={v.reached} onChange={(e) => set({ reached: e.target.value as S["EnvReached"] })} data-testid="sp-reached">
            {ENV_REACHED.map((r) => (
              <option key={r} value={r}>
                {t(`reachedOpt.${r}`)}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t("contained")}</legend>
        <div className="[&>div]:grid-cols-2 [&_button]:min-h-12 [&_button]:text-base">
          <AnswerButtons value={v.contained} options={yn} danger={["no"]} onChange={(x) => set({ contained: x })} testId="sp-contained" />
        </div>
      </fieldset>
      {v.site_id ? (
        <div className="flex flex-col gap-1">
          <MultiSelect
            id="sp-kits"
            label={t("kitsUsed")}
            options={(assets.data?.items ?? []).filter((a) => a.asset_type === "spill_kit").map((a) => ({ value: a.id, label: `${a.asset_tag}${a.zone_code ? ` · ${a.zone_code}` : ""}` }))}
            value={kits}
            onChange={setKits}
            allLabel={t("noKitUsed")}
            testId="sp-kits"
          />
          <p className="text-xs text-muted-foreground">{t("kitUsedHint")}</p>
        </div>
      ) : null}
      {likelyReportable ? (
        <Alert tone="warning" data-testid="sp-reportable-preview">
          <span className="flex flex-col gap-1">
              <span className="font-semibold">{td("whyReportable")}</span>
              <ul className="flex flex-col gap-1" data-testid="sp-reportable-why">
                {why.map(({ k, Icon }) => (
                  <li key={k} className="flex items-center gap-2" data-why={k}>
                    <Icon aria-hidden className="size-4 shrink-0" />
                    {td(`why.${k}`, { q: v.quantity_l, l: String(threshold) })}
                  </li>
                ))}
              </ul>
              <span className="text-xs">{td("reportableNext")}</span>
          </span>
        </Alert>
      ) : null}
      {likelyReportable ? (
        <fieldset className="flex flex-col gap-3 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium">{t("incident")}</legend>
          <FormField id="sp-inc" label={t("linkIncident")} hint={t("linkIncidentHint")}>
            <Select id="sp-inc" className={big} value={v.incident_id} onChange={(e) => set({ incident_id: e.target.value })} data-testid="sp-incident">
              <option value="">{t("createIncident")}</option>
              {(incidents.data?.items ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.ref}
                </option>
              ))}
            </Select>
          </FormField>
          {needIncident ? (
            <div className="grid gap-3 sm:grid-cols-2" data-testid="sp-incident-fields">
              <FormField id="sp-as" label={t("actualSeverity")} required>
                <Select id="sp-as" className={big} value={inc.actual_severity} onChange={(e) => setInc({ ...inc, actual_severity: e.target.value })} data-testid="sp-actual">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {refs.label("severity", n)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="sp-ps" label={t("potentialSeverity")} required>
                <Select id="sp-ps" className={big} value={inc.potential_severity} onChange={(e) => setInc({ ...inc, potential_severity: e.target.value })} data-testid="sp-potential">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {refs.label("severity", n)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="sp-act" label={t("activity")} required>
                <Select id="sp-act" className={big} value={inc.activity} onChange={(e) => setInc({ ...inc, activity: e.target.value })} data-testid="sp-activity">
                  <option value="">{tc("select")}</option>
                  {refs.options("activity").map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="sp-shift" label={t("shift")} required>
                <Select id="sp-shift" className={big} value={inc.shift} onChange={(e) => setInc({ ...inc, shift: e.target.value as S["IncidentShift"] })}>
                  <option value="day">{t("shiftDay")}</option>
                  <option value="night">{t("shiftNight")}</option>
                </Select>
              </FormField>
              <FormField id="sp-desc" label={t("description")} required hint={<NoNamesHint />}>
                <Textarea id="sp-desc" value={inc.description} maxLength={2000} onChange={(e) => setInc({ ...inc, description: e.target.value })} data-testid="sp-description" />
              </FormField>
              <FormField id="sp-imm" label={t("immediateActions")} required>
                <Textarea id="sp-imm" value={inc.immediate_actions} maxLength={2000} onChange={(e) => setInc({ ...inc, immediate_actions: e.target.value })} data-testid="sp-immediate" />
              </FormField>
            </div>
          ) : null}
        </fieldset>
      ) : null}
      <FormField id="sp-photos" label={t("photos")} hint={t("photoHint")}>
        <PhotoPicker value={photos} onChange={setPhotos} max={5} testId="sp-photos" />
      </FormField>
      <StillNeeded items={missing} testId="sp-missing" />
      <MutationError error={error} />
      <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={!ready || busy} onClick={() => void save()} data-testid="sp-save">
        {busy ? tc("saving") : t("save")}
      </Button>
    </div>
  );
}

export function SpillPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <SpillDetail project={p} id={id} />}</ProjectGate>;
}

function SpillDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.spills");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const q = useSpill(id, { enabled: caps.view });
  const kits = useEmergencyAssets(project.id, { asset_type: ["spill_kit"], page_size: 200 } as never, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "clean" | "close" | "void">("");
  const [cleanAt, setCleanAt] = useState(nowLocal());
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return <NotFoundState />;
  const transition = async (body: S["SpillTransition"]) => {
    await unwrap(api.POST("/api/v1/spills/{spill_id}/transitions", { params: { path: { spill_id: x.id } }, body }));
    await refresh();
  };
  const kitTag = (kid: string) => (kits.data?.items ?? []).find((a) => a.id === kid)?.asset_tag ?? "—";
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/spills" }, { label: x.spill_no }]} />
      <PageHeader
        title={<Code>{x.spill_no}</Code>}
        description={`${ref.label("spill_substances", x.substance)} · ${x.quantity_l} L`}
        badge={
          <span className="inline-flex flex-wrap gap-1">
            <EnvStatusBadge group="envSpillStatus" status={x.status} />
            <ReportableBadge reportable={x.reportable} />
          </span>
        }
        actions={
          <>
            {x.status === "reported" && caps.spill ? (
              <Button onClick={() => setDialog("clean")} data-testid="spill-clean">
                {t("cleanUp")}
              </Button>
            ) : null}
            {(x.status === "reported" || x.status === "cleaned_up") && caps.review ? (
              <Button variant={x.status === "cleaned_up" ? "default" : "outline"} onClick={() => setDialog("close")} data-testid="spill-close">
                {t("close")}
              </Button>
            ) : null}
          </>
        }
      />
      <ApiWarnings warnings={x.warnings} className="mb-4" />
      {x.incident_id ? (
        <Alert tone="info" className="mb-4" data-testid="spill-incident">
          <FileWarning aria-hidden className="me-1 inline size-4" />
          {t("incidentLinked")}{" "}
          <Link href={`/incidents/${x.incident_id}`} className="font-medium underline">
            <Code>{x.incident_ref ?? ""}</Code>
          </Link>
        </Alert>
      ) : null}
      <Card className="mb-4">
        <CardContent className="pt-4 sm:pt-5 sm:pt-5">
          <FieldList>
            <FieldItem label={t("occurred")}>
              <StackedDate v={x.occurred_at} time projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("where")}>
              <Code>{x.zone_code ?? "—"}</Code>
            </FieldItem>
            <FieldItem label={t("responsible")}>
              <Code>{x.responsible_code ?? "—"}</Code>
            </FieldItem>
            <FieldItem label={t("source")}>{ref.label("spill_source", x.source)}</FieldItem>
            <FieldItem label={t("surface")}>{ref.label("surface", x.surface)}</FieldItem>
            <FieldItem label={t("contained")}>
              <YesNo value={x.contained} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("reached")}>{t(`reachedOpt.${x.reached}`)}</FieldItem>
            <FieldItem label={t("kitsUsed")}>{x.spill_kit_asset_ids.length ? <Code>{x.spill_kit_asset_ids.map(kitTag).join(", ")}</Code> : "—"}</FieldItem>
            <FieldItem label={t("cleanedAt")}>{x.cleanup_completed_at ? <StackedDate v={x.cleanup_completed_at} time projectId={project.id} /> : "—"}</FieldItem>
            {x.void_reason ? (
              <FieldItem label={t("reason")} wide>
                <span dir="auto">{x.void_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {caps.void && x.status !== "voided" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setDialog("void")} data-testid="spill-void">
            {t("void")}
          </Button>
        </RecordActions>
      ) : null}
      {dialog === "clean" ? (
        <StepDialog title={t("cleanUp")} confirmLabel={t("cleanUp")} testId="clean-confirm" onConfirm={() => transition({ action: "clean_up", cleanup_completed_at: fromLocalInput(cleanAt), absorbed_and_binned: false })} onClose={() => setDialog("")}>
          <FormField id="cu-at" label={t("cleanedAt")} required>
            <Input type="datetime-local" dir="ltr" value={cleanAt} onChange={(e) => setCleanAt(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
      {dialog === "close" ? <CloseSpill project={project} x={x} onConfirm={transition} onClose={() => setDialog("")} /> : null}
      {dialog === "void" ? <EnvReasonDialog title={t("voidTitle", { no: x.spill_no })} description={t("voidHint")} confirmLabel={t("void")} onConfirm={(reason) => transition({ action: "void", reason, absorbed_and_binned: false })} onClose={() => setDialog("")} /> : null}
    </div>
  );
}

/** Close (SPL-6): cleanup time and where the cleanup waste went (a hazardous consignment or store). */
function CloseSpill({ project, x, onConfirm, onClose }: { project: Project; x: S["SpillRead"]; onConfirm: (b: S["SpillTransition"]) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("env.spills");
  const areas = useWasteAreas(project.id);
  const cons = useConsignments(project.id, { page_size: 100 });
  const [at, setAt] = useState(x.cleanup_completed_at ? "" : nowLocal());
  const [area, setArea] = useState("");
  const [consignments, setConsignments] = useState<string[]>([]);
  const [binned, setBinned] = useState(false);
  const hazAreas = (areas.data?.items ?? []).filter((a) => a.status === "active" && a.type === "hazardous_store");
  const hazCons = (cons.data?.items ?? []).filter((c) => c.waste_class === "hazardous" && c.status !== "voided");
  const small = Number(x.quantity_l) < 1 && x.surface === "paved";
  return (
    <StepDialog
      title={t("closeTitle", { no: x.spill_no })}
      description={t("closeHint")}
      confirmLabel={t("close")}
      testId="spill-close-confirm"
      onConfirm={() => onConfirm({ action: "close", cleanup_completed_at: at ? fromLocalInput(at) : null, cleanup_storage_area_id: area || null, cleanup_consignment_ids: consignments, absorbed_and_binned: binned })}
      onClose={onClose}
    >
      {!x.cleanup_completed_at ? (
        <FormField id="cs-at" label={t("cleanedAt")} required>
          <Input type="datetime-local" dir="ltr" value={at} onChange={(e) => setAt(e.target.value)} />
        </FormField>
      ) : null}
      <FormField id="cs-area" label={t("cleanupArea")}>
        <Select value={area} onChange={(e) => setArea(e.target.value)} data-testid="cs-area">
          <option value="">—</option>
          {hazAreas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.area_code}
            </option>
          ))}
        </Select>
      </FormField>
      <MultiSelect id="cs-cons" label={t("cleanupConsignments")} options={hazCons.map((c) => ({ value: c.id, label: c.consignment_no }))} value={consignments} onChange={setConsignments} allLabel="—" />
      {small ? <Check id="cs-binned" label={t("absorbedBinned")} checked={binned} onChange={setBinned} /> : null}
    </StepDialog>
  );
}

/* ═════════════ complaints (§3.15, CPL-1…CPL-3, P6e-2) ═════════════ */

export function ComplaintsPage() {
  return <ProjectGate>{(p) => <Complaints project={p} />}</ProjectGate>;
}

function Complaints({ project }: { project: Project }) {
  const t = useTranslations("env.complaints");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["ComplaintStatus"] | "";
  const q = useComplaints(project.id, { status: status ? [status] : null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.complaints ? (
            <Button asChild>
              <Link href="/env-complaints/new" data-testid="complaint-new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EnvEventSubNav />
      <ListToolbar>
        <SelectFilter id="cp-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={COMPLAINT_STATUSES.map((x) => ({ value: x, label: te(`envComplaintStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="complaints-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("received")}</TH>
                <TH>{t("category")}</TH>
                <TH>{t("site")}</TH>
                <TH>{t("dueOn")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="complaint-row" data-no={c.complaint_no} data-status={c.status}>
                  <TD label={t("no")}>
                    <Link href={`/env-complaints/${c.id}`} className="font-medium text-primary hover:underline">
                      <Code>{c.complaint_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("received")}>
                    <StackedDate v={c.received_at} time projectId={project.id} />
                    <span className="block text-xs text-muted-foreground">{ref.label("complaint_channel", c.channel)}</span>
                  </TD>
                  <TD label={t("category")}>{ref.label("complaint_category", c.category)}</TD>
                  <TD label={t("site")}>
                    <Code>{opts.sites.find((x) => x.value === c.site_id)?.code ?? "—"}</Code>
                  </TD>
                  <TD label={t("dueOn")}>
                    <StackedDate v={c.response_due_on} projectId={project.id} />
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envComplaintStatus" status={c.status} />
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
    </div>
  );
}

export function NewComplaintPage() {
  return <ProjectGate>{(p) => <NewComplaint project={p} />}</ProjectGate>;
}

function NewComplaint({ project }: { project: Project }) {
  const t = useTranslations("env.complaints");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEnvRefresh();
  const router = useRouter();
  const [v, setV] = useState({
    received_at: nowLocal(),
    channel: "phone" as S["ComplaintChannel"],
    category: "noise" as S["ComplaintCategory"],
    site_id: "",
    location_text: "",
    anonymous: false,
    complainant_name: "",
    complainant_contact: "",
    description: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!caps.complaints) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/env-complaints", {
          params: { path: { project_id: project.id } },
          body: {
            received_at: fromLocalInput(v.received_at) ?? new Date().toISOString(),
            channel: v.channel,
            category: v.category,
            site_id: v.site_id,
            location_text: v.location_text || null,
            anonymous: v.anonymous,
            complainant_name: v.anonymous ? null : v.complainant_name || null,
            complainant_contact: v.anonymous ? null : v.complainant_contact || null,
            description: v.description,
          },
        }),
      );
      await refresh();
      router.push(`/env-complaints/${r.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <PageHeader title={t("newTitle")} />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="cp-at" label={t("received")} required>
          <Input id="cp-at" type="datetime-local" dir="ltr" value={v.received_at} onChange={(e) => set({ received_at: e.target.value })} />
        </FormField>
        <FormField id="cp-channel" label={t("channel")} required hint={v.channel === "via_authority" ? t("authorityHint") : undefined}>
          <Select id="cp-channel" value={v.channel} onChange={(e) => set({ channel: e.target.value as S["ComplaintChannel"] })} data-testid="cp-channel">
            {ref.options("complaint_channel").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cp-category" label={t("category")} required>
          <Select id="cp-category" value={v.category} onChange={(e) => set({ category: e.target.value as S["ComplaintCategory"] })} data-testid="cp-category">
            {ref.options("complaint_category").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cp-site" label={t("site")} required>
          <Select id="cp-site" value={v.site_id} onChange={(e) => set({ site_id: e.target.value })} data-testid="cp-site">
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cp-loc" label={t("location")}>
          <Input id="cp-loc" maxLength={200} value={v.location_text} onChange={(e) => set({ location_text: e.target.value })} />
        </FormField>
      </div>
      <fieldset className="flex flex-col gap-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("complainant")}</legend>
        <PrivacyNote testId="cp-privacy">{t("privacy")}</PrivacyNote>
        <Check id="cp-anon" label={t("anonymous")} checked={v.anonymous} onChange={(c) => set({ anonymous: c })} testId="cp-anonymous" />
        {!v.anonymous ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="cp-name" label={t("name")}>
              <Input id="cp-name" maxLength={120} value={v.complainant_name} onChange={(e) => set({ complainant_name: e.target.value })} data-testid="cp-name" />
            </FormField>
            <FormField id="cp-contact" label={t("contact")}>
              <Input id="cp-contact" dir="ltr" maxLength={60} value={v.complainant_contact} onChange={(e) => set({ complainant_contact: e.target.value })} data-testid="cp-contact" />
            </FormField>
          </div>
        ) : null}
      </fieldset>
      <FormField id="cp-desc" label={t("description")} required hint={<NoNamesHint />}>
        <Textarea id="cp-desc" maxLength={2000} value={v.description} onChange={(e) => set({ description: e.target.value })} data-testid="cp-description" />
      </FormField>
      <MutationError error={error} />
      <Button className="w-fit" disabled={!v.site_id || !v.description.trim() || busy} onClick={() => void save()} data-testid="cp-save">
        {busy ? tc("saving") : t("save")}
      </Button>
    </div>
  );
}

export function ComplaintPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <ComplaintDetail project={p} id={id} />}</ProjectGate>;
}

function ComplaintDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.complaints");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const bi = useBi();
  const opts = useProjectOptions(project.id);
  const refresh = useEnvRefresh();
  const q = useComplaint(id, { enabled: caps.view });
  const c = q.data;
  const nearbyOn = Boolean(c && (c.category === "dust" || c.category === "noise") && caps.complaints);
  const nearby = useNearbyReadings(id, { enabled: nearbyOn });
  const [dialog, setDialog] = useState<"" | "respond" | "close" | "void" | "investigate">("");
  const [summary, setSummary] = useState("");
  const [sentAt, setSentAt] = useState(nowLocal());
  const [inv, setInv] = useState("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c) return <NotFoundState />;
  const transition = async (body: S["ComplaintTransition"]) => {
    await unwrap(api.POST("/api/v1/env-complaints/{complaint_id}/transitions", { params: { path: { complaint_id: c.id } }, body }));
    await refresh();
  };
  const patch = async (body: S["ComplaintUpdate"]) => {
    await unwrap(api.PATCH("/api/v1/env-complaints/{complaint_id}", { params: { path: { complaint_id: c.id } }, body }));
    await refresh();
  };
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/env-complaints" }, { label: c.complaint_no }]} />
      <PageHeader
        title={<Code>{c.complaint_no}</Code>}
        description={`${ref.label("complaint_category", c.category)} · ${ref.label("complaint_channel", c.channel)}`}
        badge={<EnvStatusBadge group="envComplaintStatus" status={c.status} />}
        actions={
          caps.complaints ? (
            <>
              {c.status === "open" || c.status === "responded" ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    setInv(c.investigation_en ?? "");
                    setDialog("investigate");
                  }}
                  data-testid="complaint-investigate"
                >
                  {t("investigation")}
                </Button>
              ) : null}
              {c.status === "open" ? (
                <Button onClick={() => setDialog("respond")} data-testid="complaint-respond">
                  {t("respond")}
                </Button>
              ) : null}
              {c.status === "responded" ? (
                <Button onClick={() => setDialog("close")} data-testid="complaint-close">
                  {t("close")}
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <Card className="mb-4">
        <CardContent className="pt-4 sm:pt-5 sm:pt-5">
          <FieldList>
            <FieldItem label={t("received")}>
              <StackedDate v={c.received_at} time projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("site")}>
              <Code>{opts.sites.find((x) => x.value === c.site_id)?.code ?? "—"}</Code>
            </FieldItem>
            <FieldItem label={t("location")}>{c.location_text ?? "—"}</FieldItem>
            <FieldItem label={t("dueOn")}>
              <StackedDate v={c.response_due_on} projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("complainant")} wide>
              {c.anonymous ? (
                t("anonymousShort")
              ) : c.complainant_name || c.complainant_contact ? (
                <span data-testid="complainant-contact">
                  {c.complainant_name ?? ""} {c.complainant_contact ? <bdi className="ltr">{c.complainant_contact}</bdi> : null}
                </span>
              ) : (
                <PrivacyNote testId="contact-held">{t("contactHeld")}</PrivacyNote>
              )}
            </FieldItem>
            <FieldItem label={t("description")} wide>
              <span dir="auto" className="whitespace-pre-wrap">
                {c.description}
              </span>
            </FieldItem>
            {c.investigation_en || c.investigation_ar ? (
              <FieldItem label={t("investigation")} wide>
                <span dir="auto" className="whitespace-pre-wrap">
                  {bi(c.investigation_en, c.investigation_ar)}
                </span>
              </FieldItem>
            ) : null}
            {c.response_sent_at ? (
              <FieldItem label={t("responseSent")}>
                <StackedDate v={c.response_sent_at} time projectId={project.id} />
              </FieldItem>
            ) : null}
            {c.response_summary ? (
              <FieldItem label={t("responseSummary")} wide>
                <span dir="auto">{c.response_summary}</span>
              </FieldItem>
            ) : null}
            <FieldItem label={t("linked")}>{t("linkedCount", { r: c.reading_ids.length, x: c.exceedance_ids.length })}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      {nearbyOn ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("nearby")}</CardTitle>
            <p className="text-xs text-muted-foreground">{t("nearbyHint")}</p>
          </CardHeader>
          <CardContent>
            {(nearby.data?.items ?? []).length ? (
              <ul className="flex flex-col divide-y text-sm" data-testid="nearby-readings">
                {(nearby.data?.items ?? []).map((r) => {
                  const linked = c.reading_ids.includes(r.id);
                  return (
                    <li key={r.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="nearby-reading">
                      <Code>{r.point_code}</Code>
                      <StackedDate v={r.window_end} time projectId={project.id} />
                      <bdi className="ltr font-semibold tabular-nums">{r.display}</bdi>
                      <ResultBadge result={r.result} background={r.background} />
                      {c.status !== "closed" && c.status !== "voided" ? (
                        <Button
                          size="sm"
                          variant={linked ? "outline" : "default"}
                          className={cn("ms-auto")}
                          onClick={() => void patch({ reading_ids: linked ? c.reading_ids.filter((x) => x !== r.id) : [...c.reading_ids, r.id], ...(r.exceedance_id && !linked && !c.exceedance_ids.includes(r.exceedance_id) ? { exceedance_ids: [...c.exceedance_ids, r.exceedance_id] } : {}) })}
                          data-testid="nearby-link"
                        >
                          {linked ? (
                            <>
                              <CheckCircle2 aria-hidden />
                              {t("linkedOne")}
                            </>
                          ) : (
                            t("link")
                          )}
                        </Button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState message={t("noNearby")} />
            )}
          </CardContent>
        </Card>
      ) : null}
      {caps.void && c.status === "open" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setDialog("void")} data-testid="complaint-void">
            {t("void")}
          </Button>
        </RecordActions>
      ) : null}
      {dialog === "respond" ? (
        <StepDialog title={t("respond")} confirmLabel={t("respond")} testId="respond-confirm" disabled={!summary.trim() || !sentAt} onConfirm={() => transition({ action: "respond", response_summary: summary.trim(), response_sent_at: fromLocalInput(sentAt) })} onClose={() => setDialog("")}>
          <FormField id="rs-at" label={t("responseSent")} required>
            <Input type="datetime-local" dir="ltr" value={sentAt} onChange={(e) => setSentAt(e.target.value)} />
          </FormField>
          <FormField id="rs-summary" label={t("responseSummary")} required hint={<NoNamesHint />}>
            <Textarea value={summary} maxLength={1000} onChange={(e) => setSummary(e.target.value)} data-testid="rs-summary" />
          </FormField>
        </StepDialog>
      ) : null}
      {dialog === "close" ? <StepDialog title={t("close")} confirmLabel={t("close")} testId="close-confirm" onConfirm={() => transition({ action: "close" })} onClose={() => setDialog("")} /> : null}
      {dialog === "investigate" ? (
        <StepDialog title={t("investigation")} confirmLabel={tc("save")} onConfirm={() => patch({ investigation_en: inv || null })} onClose={() => setDialog("")}>
          <FormField id="iv-text" label={t("investigation")} hint={<NoNamesHint />}>
            <Textarea value={inv} maxLength={2000} onChange={(e) => setInv(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
      {dialog === "void" ? <EnvReasonDialog title={t("voidTitle", { no: c.complaint_no })} confirmLabel={t("void")} onConfirm={(reason) => transition({ action: "void", reason })} onClose={() => setDialog("")} /> : null}
    </div>
  );
}
